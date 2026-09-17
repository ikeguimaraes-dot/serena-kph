"""Run ONLY as serena_backup.py restore hook against its isolated Unix-socket DB."""
import asyncio
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'files/restaurant-ai'))
from catalog_publish import import_bundle
from catalog import imported_item_text


async def main():
    import asyncpg
    assert os.environ.get('PGDATABASE')=='serena_restore', 'Isolated restore database required'
    assert os.environ.get('PGHOST','').startswith('/'), 'Local Unix socket required'
    c=await asyncpg.connect(host=os.environ['PGHOST'],port=int(os.environ['PGPORT']),
                            user=os.environ['PGUSER'],database='serena_restore',ssl=False)
    tx=c.transaction();await tx.start()
    try:
        await c.execute((ROOT/'supabase/migrations/20260917042522_catalog_provenance_variants.sql').read_text())
        before=dict(await c.fetch('SELECT restaurant_id,count(*) FROM menu_items GROUP BY restaurant_id'))
        bundles=list((ROOT/'docs/serena-os/catalog-release-20260917').glob('*_bundle.json'))
        assert len(bundles)>=2
        for path in bundles:
            bundle=json.loads(path.read_text());rid=bundle['restaurant_id']
            existing=await c.fetchval('SELECT count(*) FROM menu_items WHERE restaurant_id=$1',rid)
            first=await import_bundle(c,bundle,existing)
            assert first['inserted']==len(bundle['items'])
            second=await import_bundle(c,bundle,existing+len(bundle['items']))
            assert second['inserted']==0 and second['unchanged']==len(bundle['items'])
            rows=await c.fetch('SELECT * FROM menu_items WHERE restaurant_id=$1 ORDER BY ordem',rid)
            actual={r['source_item_id']:r for r in rows if r['catalog_source']==bundle['catalog_source']}
            for item in bundle['items']:
                row=actual[item['source_item_id']]
                assert row['nome']==item['nome'] and row['categoria']==item['categoria']
                assert json.loads(row['catalog_metadata'])['content_hash']==item['catalog_metadata']['content_hash']
                rendered=imported_item_text(row)
                assert 'R$ 0,00' not in rendered
            # An operator edit must not be silently overwritten on reimport.
            item=bundle['items'][0]
            await c.execute('UPDATE menu_items SET nome=$1 WHERE restaurant_id=$2 AND source_item_id=$3',
                            'Operator edit',rid,item['source_item_id'])
            try:
                await import_bundle(c,bundle,existing+len(bundle['items']))
            except ValueError:
                pass
            else: raise AssertionError('Operator edit should require explicit review')
            assert await c.fetchval('SELECT nome FROM menu_items WHERE restaurant_id=$1 AND source_item_id=$2',rid,item['source_item_id'])=='Operator edit'
            await c.execute('UPDATE menu_items SET nome=$1 WHERE restaurant_id=$2 AND source_item_id=$3',
                            item['nome'],rid,item['source_item_id'])
            print(json.dumps({'catalog_test':'PASS','tenant':rid,'items':len(bundle['items']),
                              'idempotence':True,'operator_edits_preserved':True,'no_free_base_prices':True}))
        tenants={json.loads(p.read_text())['restaurant_id'] for p in bundles}
        after=dict(await c.fetch('SELECT restaurant_id,count(*) FROM menu_items GROUP BY restaurant_id'))
        assert all(after.get(r,0)==n for r,n in before.items() if r not in tenants)
    finally:
        await tx.rollback();await c.close()
    print('PASS: catalog integration rollback; other tenants preserved; no messages sent')


if __name__=='__main__': asyncio.run(main())

"""Menu persistence contract in the disposable restored database only."""
import asyncio
import json
import os
import uuid
import asyncpg
import database as db
from test_recovery_contract import TransactionPool

async def run():
    host=os.environ.get('PGHOST','')
    if not host.startswith('/tmp/serena-restore-') or os.environ.get('PGDATABASE')!='serena_restore':
        raise RuntimeError('Only a disposable restored Unix-socket database is allowed')
    c=await asyncpg.connect(host=host,port=int(os.environ['PGPORT']),user=os.environ['PGUSER'],database='serena_restore',ssl=False)
    db._pool=TransactionPool(c)
    try:
        rid='menu-test-'+uuid.uuid4().hex
        await c.execute("INSERT INTO restaurants(id,nome,whatsapp_number,ativo) VALUES($1,'Synthetic menu test','+12025550199',true)",rid)
        result=await db.create_menu_item(rid,{'categoria':'Entradas','nome':'Synthetic Burrata','preco':49.90})
        item_id=result['id']
        await db.update_menu_item(item_id,{'preco':None})
        assert await c.fetchval('SELECT preco FROM menu_items WHERE id=$1',item_id) is None
        await db.update_menu_item(item_id,{'preco':108.08})
        await db.update_menu_item(item_id,{'descricao':'Synthetic updated description'})
        assert str(await c.fetchval('SELECT preco FROM menu_items WHERE id=$1',item_id))=='108.08'
        variants=[{'active':True,'label':'Taça','price':'40.00'},{'active':True,'label':'Garrafa','price':'180.00'}]
        await c.execute('UPDATE menu_items SET catalog_metadata=$2::jsonb,disponivel=false WHERE id=$1',item_id,json.dumps({'listed':False,'variants':variants,'source_options':['synthetic evidence']}))
        await db.update_menu_item(item_id,{'disponivel':True})
        row=await c.fetchrow('SELECT disponivel,catalog_metadata FROM menu_items WHERE id=$1',item_id)
        metadata=json.loads(row['catalog_metadata'])
        assert row['disponivel'] is True and metadata['listed'] is True
        assert metadata['variants']==variants and metadata['source_options']==['synthetic evidence']
        assert await db.delete_menu_item(item_id)
        assert not await c.fetchval('SELECT EXISTS(SELECT 1 FROM menu_items WHERE id=$1)',item_id)
        print(json.dumps({'menu_crud_restore':'passed','null_price_preserved':True,'decimal_cents_preserved':True,'option_prices_preserved':True,'availability_override_consistent':True,'production_writes':0}))
    finally:
        db._pool=None
        await c.close()

if __name__=='__main__':asyncio.run(run())

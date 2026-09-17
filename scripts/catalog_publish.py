#!/usr/bin/env python3
"""Build/import source-verified catalogs. Dry-run by default; no deletes or implicit updates.

Human review fields in prior CSVs are never modified or claimed completed.
The caller supplies exact tenant, source files, URL, capture time and expected DB count.
"""
import argparse
import asyncio
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path


def localized(value):
    return (value.get('pt') or value.get('en') or '') if isinstance(value, dict) else str(value or '')


def amount(value, divisor=1):
    if value is None:
        return None
    result = Decimal(str(value)) / divisor
    if not result.is_finite() or result < 0 or result != result.quantize(Decimal('0.01')):
        raise ValueError('Invalid monetary amount; manual review required')
    return format(result, '.2f')


def hash_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def tagme_products(sections, ancestors=(), inherited_disabled=False):
    for section in sections:
        path = ancestors + (localized(section['name']),)
        disabled = inherited_disabled or bool(section.get('disabled'))
        for item in section.get('menuItems', []):
            yield path, item, disabled
        yield from tagme_products([x for x in section.get('menus', []) if isinstance(x, dict)], path, disabled)


def normalize_tagme(raw):
    result = []
    if isinstance(raw, dict):
        raw = raw['body']
    for path, item, hidden in tagme_products(raw):
        variants, groups, warnings = [], [], []
        for option in item.get('options', []):
            if option.get('promoPriceEnabled') or option.get('relativePrice') or option.get('relativePromoPrice'):
                raise ValueError('Promotion/relative pricing requires an explicit adapter')
            label = localized(option.get('name')) or localized(option.get('volume'))
            if option.get('sons'):
                children = []
                for child in option['sons']:
                    if child.get('promoPriceEnabled') or child.get('relativePrice'):
                        raise ValueError('Relative/promotion child price is unsupported')
                    children.append({'id': child['_id'], 'label': localized(child.get('name')),
                                     'price': amount(child.get('price'), 100), 'chargeable': True,
                                     'active': not (option.get('disabled') or child.get('disabled'))})
                groups.append({'id': option['_id'], 'label': label, 'min': option.get('min'),
                               'max': option.get('max'), 'options': children})
            elif label and option.get('price') is not None:
                variants.append({'id': option['_id'], 'label': label,
                                 'price': amount(option['price'], 100), 'active': not bool(option.get('disabled'))})
            else:
                warnings.append('Existe opção sem rótulo ou preço inequívoco; não oferecer essa opção.')
        active = [v for v in variants if v['active']]
        price = amount(item.get('price'), 100)
        if item.get('promoPriceEnabled'):
            raise ValueError('Promotion price requires an explicit adapter')
        if len(active) > 1:
            price = None  # Never collapse distinct variants into a minimum price.
        elif len(active) == 1:
            if price is not None and price != active[0]['price']:
                raise ValueError('Summary and variant disagree')
            price = active[0]['price']
        if price == '0.00':
            price = None
            warnings.append('Preço-base zero na fonte; confirmar valor, não tratar como gratuito.')
        for variant in variants:
            if variant['price'] == '0.00':
                variant['price'] = None
                warnings.append('Variante com preço zero na fonte: valor sob consulta, não gratuita.')
        result.append({'source_item_id': str(item['_id']), 'categoria': path[-1],
                       'nome': localized(item['name']), 'descricao': localized(item.get('descript')),
                       'preco': price, 'disponivel': not (hidden or bool(item.get('disabled'))),
                       'catalog_metadata': {'listed': not (hidden or item.get('disabled')), 'price_kind': 'variants' if len(active) > 1 else 'reference',
                                            'variants': variants, 'groups': groups, 'warnings': warnings,
                                            'source_options': item.get('options', []), 'category_path': list(path)}})
    return result


def shopfood_products(categories, ancestors=()):
    for category in categories:
        path = ancestors + (category['name'],)
        for product in category.get('products', []):
            yield path, product
        yield from shopfood_products(category.get('children', []), path)


def normalize_shopfood(raw, details):
    details_by_id = {r['product_id']: r for r in details['responses']}
    result = []
    for path, item in shopfood_products(raw):
        variants, groups = [], []
        price, kind = amount(item.get('price')), 'reference'
        if item['type'] == 9:
            response = details_by_id[item['id']]
            if response['http_status'] != 200 or response['body']['product']['id'] != item['id']:
                raise ValueError('Missing/incorrect composite detail')
            steps = response['body']['product']['product_composite_steps']
            components = [c for s in steps for c in s['complements']]
            if len(components) == 1 and components[0]['chargeable'] and components[0]['active']:
                c = components[0]
                if amount(c['price']) != price:
                    raise ValueError('Summary/variant price mismatch')
                variants.append({'id': str(c['id']), 'label': c['name'], 'price': price, 'active': True})
            elif amount(item.get('default_price')) not in (None, '0.00'):
                price, kind = amount(item['default_price']), 'package'
                for step in steps:
                    groups.append({'id': str(step['id']), 'label': step['name'],
                                   'min': step.get('minimum_quantity'), 'max': step.get('quantity'),
                                   'required': step.get('required'), 'type': step.get('type'),
                                   'options': [{'id': str(c['id']), 'label': c['name'], 'price': amount(c['price']),
                                                'active': c['active'], 'chargeable': c['chargeable']} for c in step['complements']]})
            else:
                raise ValueError('Composite has no unambiguous published price')
        elif item['type'] != 1:
            raise ValueError('Unknown Shopfood product type')
        if price in (None, '0.00'):
            raise ValueError('Missing/zero base price needs review')
        result.append({'source_item_id': str(item['id']), 'categoria': path[-1], 'nome': item['name'],
                       'descricao': item.get('description') or '', 'preco': price, 'disponivel': bool(item['active'] and item['visible']),
                       'catalog_metadata': {'listed': bool(item['active'] and item['visible']), 'price_kind': kind,
                                            'variants': variants, 'groups': groups, 'warnings': [], 'category_path': list(path)}})
    return result


def build_bundle(args):
    raw = json.loads(args.source.read_text())
    rows = normalize_tagme(raw) if args.adapter == 'tagme' else normalize_shopfood(raw, json.loads(args.details.read_text()))
    if not rows or len({r['source_item_id'] for r in rows}) != len(rows):
        raise ValueError('Empty catalog or duplicate source identity')
    datetime.fromisoformat(args.captured_at)
    if not args.source_url.startswith('https://'):
        raise ValueError('Source URL must be explicit HTTPS')
    for order, row in enumerate(rows):
        if not row['nome'].strip() or not row['categoria'].strip():
            raise ValueError('Missing name/category')
        row['ordem'] = order
        row['catalog_metadata'].update({'source_url': args.source_url, 'verification': 'SOURCE_VERIFIED',
                                        'human_item_review': 'PENDING', 'content_hash': hash_json(row)})
    return {'version': 1, 'restaurant_id': args.rid, 'catalog_source': args.adapter,
            'source_captured_at': args.captured_at, 'source_sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(),
            'items': rows}


async def import_bundle(connection, bundle, expected_count):
    """Caller owns transaction. Non-destructive/idempotent; conflicting edits fail closed."""
    rid, source = bundle['restaurant_id'], bundle['catalog_source']
    if not await connection.fetchval('SELECT EXISTS(SELECT 1 FROM restaurants WHERE id=$1)', rid):
        raise ValueError('Unknown tenant')
    await connection.execute('SELECT pg_advisory_xact_lock(hashtext($1))', 'catalog:' + rid)
    count = await connection.fetchval('SELECT count(*) FROM menu_items WHERE restaurant_id=$1', rid)
    if count != expected_count:
        raise ValueError(f'Catalog changed: expected {expected_count} rows, found {count}')
    inserted = unchanged = 0
    for item in bundle['items']:
        previous = await connection.fetchrow('SELECT * FROM menu_items WHERE restaurant_id=$1 AND catalog_source=$2 AND source_item_id=$3 FOR UPDATE', rid, source, item['source_item_id'])
        metadata = dict(item['catalog_metadata'], batch_source_sha256=bundle['source_sha256'])
        if previous:
            old = previous['catalog_metadata']
            if isinstance(old, str): old = json.loads(old)
            # Check actual editable fields, not only a stale metadata fingerprint.
            same = all(previous[k] == item[k] for k in ('nome','categoria','descricao','disponivel','ordem'))
            same = same and previous['preco'] == (Decimal(item['preco']) if item['preco'] is not None else None)
            if not same or old.get('content_hash') != metadata['content_hash']:
                raise ValueError('Existing source item differs; explicit update review required')
            unchanged += 1
            continue
        await connection.execute('''INSERT INTO menu_items
          (restaurant_id,catalog_source,source_item_id,categoria,nome,descricao,preco,disponivel,ordem,catalog_metadata,source_captured_at)
          VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11)''',
          rid, source, item['source_item_id'], item['categoria'], item['nome'], item['descricao'],
          Decimal(item['preco']) if item['preco'] is not None else None, item['disponivel'], item['ordem'],
          json.dumps(metadata,ensure_ascii=False), datetime.fromisoformat(bundle['source_captured_at']))
        inserted += 1
    actual = await connection.fetchval('SELECT count(*) FROM menu_items WHERE restaurant_id=$1 AND catalog_source=$2', rid, source)
    if actual < len(bundle['items']): raise AssertionError('Post-import count mismatch')
    return {'restaurant_id':rid, 'inserted':inserted, 'unchanged':unchanged, 'source_rows':actual}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command',required=True)
    build = sub.add_parser('build')
    for field in ('rid','adapter','source-url','captured-at'): build.add_argument('--'+field,required=True)
    build.add_argument('--source',type=Path,required=True);build.add_argument('--details',type=Path)
    build.add_argument('--output',type=Path,required=True)
    publish = sub.add_parser('import')
    publish.add_argument('--bundle',type=Path,required=True)
    publish.add_argument('--expected-count',type=int,required=True)
    publish.add_argument('--commit',action='store_true')
    args=parser.parse_args()
    if args.command=='build':
        if args.adapter not in ('tagme','shopfood'): raise ValueError('Unknown adapter')
        bundle=build_bundle(args)
        with args.output.open('x',encoding='utf-8') as f: json.dump(bundle,f,ensure_ascii=False,indent=2)
        print(json.dumps({'restaurant_id':args.rid,'items':len(bundle['items']),'bundle_sha256':hash_json(bundle)}))
    else:
        async def run():
            import asyncpg
            c=await asyncpg.connect(os.environ['DATABASE_URL'],ssl='require',statement_cache_size=0)
            tx=c.transaction();await tx.start()
            try:
                result=await import_bundle(c,json.loads(args.bundle.read_text()),args.expected_count)
                if args.commit: await tx.commit()
                else: await tx.rollback()
                print(json.dumps(dict(result,committed=args.commit)))
            except BaseException:
                await tx.rollback();raise
            finally: await c.close()
        asyncio.run(run())


if __name__=='__main__': main()

"""Lossless commercial context for imported menus. No network calls or guesses."""
import json
from decimal import Decimal


def money(value):
    return 'R$ ' + format(Decimal(str(value)), '.2f').replace('.', ',')


def imported_item_text(item):
    metadata = item.get('catalog_metadata')
    if not metadata:
        return None  # Preserve the existing manually managed item contract.
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    name = item.get('nome') or '(sem nome)'
    lines = [f"{name} [{item.get('categoria') or ''}]"]
    if metadata.get('listed') is False:
        lines.append('Não oferecer: desativado/oculto na fonte do catálogo.')
    else:
        lines.append('Consta no cardápio publicado; estoque e disponibilidade no atendimento não foram confirmados.')
    if item.get('preco') is not None:
        label = 'Preço do conjunto' if metadata.get('price_kind') == 'package' else 'Preço de referência'
        lines.append(f"{label}: {money(item['preco'])}.")
    elif not metadata.get('variants'):
        lines.append('Preço sob consulta; não inferir valor.')
    if item.get('descricao'):
        lines.append(str(item['descricao']).strip())
    variants = [v for v in metadata.get('variants', []) if v.get('active') and v.get('label')]
    if variants:
        lines.append('Preço por variante (não usar o menor preço para outra escolha): ' + '; '.join(
            f"{v['label']}: {money(v['price']) if v.get('price') is not None else 'preço sob consulta'}" for v in variants))
    for group in metadata.get('groups', []):
        active = [o for o in group['options'] if o.get('active') and o.get('label')]
        if not active:
            lines.append(f"{group['label']}: nenhuma opção ativa confirmada; consultar a equipe, sem concluir que o produto acabou.")
            continue
        options = []
        for option in active:
            if not option.get('chargeable', True):
                price = 'incluído no conjunto, sem cobrança separada'
            elif option.get('price') == '0.00':
                price = 'sem acréscimo ao item'
            elif option.get('price') is None:
                price = 'acréscimo sob consulta'
            else:
                price = '+' + money(option['price'])
            options.append(f"{option['label']} ({price})")
        rule = f"; mínimo {group['min']}, máximo {group['max']}" if group.get('min') is not None and group.get('max') is not None else ''
        lines.append(f"{group['label']}{rule}: " + '; '.join(options))
    for note in metadata.get('warnings', []):
        lines.append('Confirmar com a equipe: ' + note)
    return '\n'.join(lines)

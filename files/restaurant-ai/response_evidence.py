"""Guard currency claims against exact prices returned by catalog/proposal tools.

This verifies numeric amounts, not semantic item association; the prompt and
lossless variant labels still provide that context. Never mutates a reservation.
"""
from decimal import Decimal
import re

MONEY = re.compile(r'R\$\s*(-?\d+(?:[.,]\d+)*)')

def amounts(text):
    values = set()
    for match in MONEY.finditer(text):
        raw = match.group(1)
        if ',' in raw:
            raw = raw.replace('.', '').replace(',', '.')
        elif '.' in raw and len(raw.rsplit('.', 1)[1]) == 3:
            raw = raw.replace('.', '')
        try:
            values.add(Decimal(raw))
        except ArithmeticError:
            values.add(Decimal('-999999999999'))  # invalid currency never matches valid source
    return values

def check_prices(text, evidence):
    quoted = amounts(text)
    if not quoted:
        return text
    allowed = set().union(*(amounts(value) for value in evidence)) if evidence else set()
    if quoted <= allowed:
        return text
    # If the model rounds or invents an amount, prefer the source verbatim.
    blocks = []
    for value in evidence:
        title = None
        for line in value.splitlines():
            if re.search(r' \[[^\]]+\]$', line):
                title = line.rsplit(' [', 1)[0]
            elif line.startswith(('Preço de referência:', 'Preço do conjunto:', 'Preço por variante')):
                blocks.append(f'{title}: {line}' if title else line)
    if blocks:
        return '\n'.join(blocks[:5]) + '\n\nEsses são os valores publicados no cardápio. A disponibilidade precisa ser confirmada.'
    return 'Não consigo confirmar esse valor agora. Posso chamar a equipe para verificar?'

"""
Cálculo determinístico de proposta de evento — Meet & Eat.
Função pura: recebe preços como parâmetro, sem acesso a banco.
O tool em tools.py faz o lookup em proposta_pricing e chama calcular().
"""
from decimal import Decimal

_TAXAS_FIXAS = {
    "rolha":          Decimal("150.00"),
    "valet_por_carro": Decimal("40.00"),
}

_VALIDADE_HORAS = 48
_MINIMO_PESSOAS = 20


def calcular(
    tipo: str,
    plano,                       # str | None — None = sem menu (bloqueia open bar)
    n_pessoas: int,
    valor_plano: Decimal,        # valor do plano por pessoa (do banco)
    valor_locacao: Decimal,      # locação fixa do ambiente (do banco)
    addons_solicitados: list,    # nomes dos add-ons pedidos pela IA
    precos_addons: dict,         # nome → {"valor": Decimal, "sob_consulta": bool}
) -> dict:
    """
    Retorna dict com breakdown completo da proposta.
    Nunca lança exceção — erros de negócio retornam {"ok": False, "codigo": ..., "erro": ...}.
    Toda aritmética em Decimal.

    precos_addons: lookup da tabela proposta_pricing. Itens com sob_consulta=True são
    excluídos do total e retornados em addons_sob_consulta para confirmação manual.
    """

    # ── VALIDAÇÕES ────────────────────────────────────────────────────────────

    if n_pessoas < _MINIMO_PESSOAS:
        return {
            "ok":     False,
            "codigo": "minimo_pessoas",
            "erro":   (
                f"Mínimo de {_MINIMO_PESSOAS} pessoas para proposta de evento. "
                f"Pedido tem {n_pessoas}px — passar para a Vic."
            ),
        }

    if "open_bar" in addons_solicitados and plano is None:
        return {
            "ok":     False,
            "codigo": "open_bar_sem_plano",
            "erro":   "Open bar não é vendido sem menu. Escolha um plano primeiro.",
        }

    # ── ADD-ONS: aplicados (precificados) vs sob consulta ────────────────────
    # Lê a flag sob_consulta do banco via precos_addons — qualquer item marcado
    # como sob_consulta=True é separado e não entra no total (genérico, não só wagyu).

    addons_sob_consulta = []
    addons_aplicados    = []
    for nome in addons_solicitados:
        if nome not in precos_addons:
            continue
        info = precos_addons[nome]
        if info.get("sob_consulta", False):
            addons_sob_consulta.append({"nome": nome})
        else:
            vaddr = _to_dec(info["valor"])
            addons_aplicados.append({
                "nome":         nome,
                "valor_pessoa": vaddr,
                "subtotal":     vaddr * n_pessoas,
            })

    # ── CÁLCULO PRINCIPAL ────────────────────────────────────────────────────

    vp = _to_dec(valor_plano)
    vl = _to_dec(valor_locacao)

    soma_addons_pp = sum(
        (a["valor_pessoa"] for a in addons_aplicados),
        Decimal("0"),
    )
    valor_por_pessoa  = vp + soma_addons_pp
    subtotal_pessoas  = valor_por_pessoa * n_pessoas
    total_base        = subtotal_pessoas + vl
    sinal             = total_base * Decimal("0.5")
    saldo             = total_base * Decimal("0.5")

    return {
        "ok":                  True,
        "tipo":                tipo,
        "plano":               plano,
        "n_pessoas":           n_pessoas,
        "valor_plano_pessoa":  vp,
        "addons_aplicados":    addons_aplicados,
        "addons_sob_consulta": addons_sob_consulta,
        "valor_por_pessoa":    valor_por_pessoa,
        "subtotal_pessoas":    subtotal_pessoas,
        "valor_locacao":       vl,
        "total_base":          total_base,
        "sinal":               sinal,
        "saldo":               saldo,
        "validade_horas":      _VALIDADE_HORAS,
        "taxas_fixas":         dict(_TAXAS_FIXAS),
    }


def _to_dec(v) -> Decimal:
    """Converte float/int/str/Decimal → Decimal sem perda de precisão."""
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))

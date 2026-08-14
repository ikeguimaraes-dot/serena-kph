"""
Suite TDD — proposta_calc.calcular()
8 casos. Devem TODOS FALHAR antes de proposta_calc.py existir.
Fonte de verdade: MEET_TABELA_REGRAS_PROPOSTA
"""
from decimal import Decimal
import proposta_calc


# ─── fixtures de pricing (valores da tabela proposta_pricing) ────────────────

PRECOS_HH = {
    "mini_pratos": Decimal("75.00"),
    "sobremesa":   Decimal("45.00"),
}

PRECOS_EVENTO = {
    "open_bar": Decimal("100.00"),   # standart
}

PRECOS_EVENTO_PREMIUM = {
    "open_bar": Decimal("200.00"),   # premium
}

LOCACAO = {
    "rooftop":      Decimal("25000.00"),
    "secret_bar":   Decimal("15000.00"),
    "salao_prime":  Decimal("25000.00"),
}


# ─── CASO 1 ─────────────────────────────────────────────────────────────────
# Happy Hour Premium, 70px, Rooftop, +Mini Pratos → total_base 67000.00
# Breakdown: 70×525=36750 + 70×75=5250 = 42000 + 25000 (Rooftop) = 67000
# sinal = saldo = 33500

def test_caso1_hh_premium_70px_rooftop_mini_pratos():
    r = proposta_calc.calcular(
        tipo="happy_hour",
        plano="premium",
        n_pessoas=70,
        valor_plano=Decimal("525.00"),
        valor_locacao=Decimal("25000.00"),
        addons_solicitados=["mini_pratos"],
        precos_addons=PRECOS_HH,
    )
    assert r["ok"] is True
    assert r["subtotal_pessoas"] == Decimal("42000.00")
    assert r["total_base"]       == Decimal("67000.00")
    assert r["sinal"]            == Decimal("33500.00")
    assert r["saldo"]            == Decimal("33500.00")
    assert r["wagyu_sob_consulta"] is False


# ─── CASO 2 ─────────────────────────────────────────────────────────────────
# Evento Standart, 50px, Salão Prime, sem addon → 50×345 + 25000 = 42250.00

def test_caso2_evento_standart_50px_salao_prime_sem_addon():
    r = proposta_calc.calcular(
        tipo="evento",
        plano="standart",
        n_pessoas=50,
        valor_plano=Decimal("345.00"),
        valor_locacao=Decimal("25000.00"),
        addons_solicitados=[],
        precos_addons={},
    )
    assert r["ok"] is True
    assert r["subtotal_pessoas"] == Decimal("17250.00")
    assert r["total_base"]       == Decimal("42250.00")
    assert r["sinal"]            == Decimal("21125.00")
    assert r["saldo"]            == Decimal("21125.00")


# ─── CASO 3 ─────────────────────────────────────────────────────────────────
# Evento Premium, 30px, Rooftop, +Open Bar Premium → 30×(555+200) + 25000 = 47650.00

def test_caso3_evento_premium_30px_rooftop_open_bar():
    r = proposta_calc.calcular(
        tipo="evento",
        plano="premium",
        n_pessoas=30,
        valor_plano=Decimal("555.00"),
        valor_locacao=Decimal("25000.00"),
        addons_solicitados=["open_bar"],
        precos_addons=PRECOS_EVENTO_PREMIUM,
    )
    assert r["ok"] is True
    assert r["subtotal_pessoas"] == Decimal("22650.00")   # 30×755
    assert r["total_base"]       == Decimal("47650.00")
    assert r["sinal"]            == Decimal("23825.00")
    assert r["saldo"]            == Decimal("23825.00")


# ─── CASO 4 ─────────────────────────────────────────────────────────────────
# n_pessoas = 15 → erro de mínimo (não calcula)

def test_caso4_minimo_pessoas_erro():
    r = proposta_calc.calcular(
        tipo="happy_hour",
        plano="classic",
        n_pessoas=15,
        valor_plano=Decimal("435.00"),
        valor_locacao=Decimal("25000.00"),
        addons_solicitados=[],
        precos_addons={},
    )
    assert r["ok"] is False
    assert r["codigo"] == "minimo_pessoas"
    assert "20" in r["erro"]


# ─── CASO 5 ─────────────────────────────────────────────────────────────────
# open bar SEM plano (plano=None) → erro de trava

def test_caso5_open_bar_sem_plano_erro():
    r = proposta_calc.calcular(
        tipo="evento",
        plano=None,
        n_pessoas=30,
        valor_plano=Decimal("0"),
        valor_locacao=Decimal("25000.00"),
        addons_solicitados=["open_bar"],
        precos_addons={"open_bar": Decimal("200.00")},
    )
    assert r["ok"] is False
    assert r["codigo"] == "open_bar_sem_plano"


# ─── CASO 6 ─────────────────────────────────────────────────────────────────
# Wagyu solicitado → flag sob_consulta, NÃO soma valor no total

def test_caso6_wagyu_sob_consulta():
    r = proposta_calc.calcular(
        tipo="evento",
        plano="premium",
        n_pessoas=30,
        valor_plano=Decimal("555.00"),
        valor_locacao=Decimal("25000.00"),
        addons_solicitados=["wagyu"],
        precos_addons={},  # wagyu não tem entrada no pricing
    )
    assert r["ok"] is True
    assert r["wagyu_sob_consulta"] is True
    # total_base NÃO inclui wagyu: 30×555 + 25000 = 41650
    assert r["total_base"] == Decimal("41650.00")


# ─── CASO 7 ─────────────────────────────────────────────────────────────────
# Borda do mínimo: n_pessoas=20 exato → calcula normal, sem erro

def test_caso7_borda_minimo_20_pessoas():
    r = proposta_calc.calcular(
        tipo="evento",
        plano="classic",
        n_pessoas=20,
        valor_plano=Decimal("435.00"),
        valor_locacao=Decimal("25000.00"),
        addons_solicitados=[],
        precos_addons={},
    )
    assert r["ok"] is True
    assert r["subtotal_pessoas"] == Decimal("8700.00")    # 20×435
    assert r["total_base"]       == Decimal("33700.00")   # 8700+25000


# ─── CASO 8 ─────────────────────────────────────────────────────────────────
# Decimal check: Happy Hour Classic, 33px, Secret Bar → 33×435 + 15000 = 29355.00
# Prova que é Decimal (sem erro de ponto flutuante)

def test_caso8_decimal_hh_classic_33px_secret_bar():
    r = proposta_calc.calcular(
        tipo="happy_hour",
        plano="classic",
        n_pessoas=33,
        valor_plano=Decimal("435.00"),
        valor_locacao=Decimal("15000.00"),
        addons_solicitados=[],
        precos_addons={},
    )
    assert r["ok"] is True
    assert r["subtotal_pessoas"] == Decimal("14355.00")   # 33×435
    assert r["total_base"]       == Decimal("29355.00")   # 14355+15000
    # Prova Decimal: operação equivalente com float daria 14355.000000000002
    assert isinstance(r["total_base"], Decimal)
    assert isinstance(r["sinal"],      Decimal)

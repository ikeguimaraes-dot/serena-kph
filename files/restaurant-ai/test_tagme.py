"""
Teste manual da integração Tagme — roda localmente com as env vars do Railway.

Pré-requisitos:
  export TAGME_API_KEY="..."
  export TAGME_PARTNER_APP_ID="..."

Uso:
  python test_tagme.py
"""

import asyncio
import os
from tagme_client import TagmeClient, format_reservation, map_status, normalize_phone

# ── Configurar antes de rodar ────────────────────────────────────
TEST_PHONE = "5511999999999"   # número com reserva real (com ou sem DDI 55)
# ────────────────────────────────────────────────────────────────


async def main():
    api_key = os.environ.get("TAGME_API_KEY", "")
    partner_id = os.environ.get("TAGME_PARTNER_APP_ID", "")
    print(f"TAGME_API_KEY       : {'✅ ' + api_key[:6] + '...' if api_key else '❌ NÃO ENCONTRADA'}")
    print(f"TAGME_PARTNER_APP_ID: {'✅ ' + partner_id[:6] + '...' if partner_id else '❌ NÃO ENCONTRADA'}")
    print(f"Telefone normalizado: {normalize_phone(TEST_PHONE)}\n")

    async with TagmeClient() as tagme:

        print("=== TESTE 1: get_reservations_by_phone ===")
        try:
            reservations = await tagme.get_reservations_by_phone(TEST_PHONE)
            print(f"Total retornado: {len(reservations)} reserva(s)")
            for r in reservations:
                print("---")
                print(format_reservation(r))
                print(f"_id raw: {r.get('_id')}")
        except Exception as e:
            print(f"ERRO: {type(e).__name__}: {e}")

        print("\n=== TESTE 2: map_status (amostras) ===")
        for s in ["confirmed", "Confirmed", "cancelled", "New", "NoShow", "desconhecido_x"]:
            print(f"  '{s}' → '{map_status(s)}'")

        # Descomente para testar cancelamento — use um _id real da listagem acima
        # print("\n=== TESTE 3: cancel_reservation ===")
        # TEST_RESERVATION_ID = "COLE_O_ID_AQUI"
        # sucesso = await tagme.cancel_reservation(TEST_RESERVATION_ID)
        # print(f"Cancelamento: {'✅ OK' if sucesso else '❌ Falhou'}")

    print("\n=== Fim dos testes ===")


if __name__ == "__main__":
    asyncio.run(main())

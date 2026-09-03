"""
Teste isolado de enviar_midia — FORA do array TOOLS.

Uso:
    railway run python3 test_enviar_midia.py +5511XXXXXXXXX

O script:
  1. Sobe uma imagem PNG mínima (1x1 px) para o bucket público serena-midia-saida
  2. Insere linha de teste em midia_disponivel
  3. Chama tools.enviar_midia() diretamente
  4. Limpa os dados de teste após o envio
"""
import asyncio, os, sys, base64
import httpx
import database as db

# PNG 1x1 pixel transparente (18 bytes, HTTPS válido para o Twilio)
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIABQ"
    "AABjkB6QAAAABJRU5ErkJggg=="
)

SUPABASE_URL   = "https://fgntcrxuhfwcauvahaiz.supabase.co"
BUCKET_SAIDA   = "serena-midia-saida"
TEST_PATH      = "test/fable_test.png"
TEST_CHAVE     = "_fable_test_"
TEST_RID       = "meet_and_eat"


async def upload_test_file() -> str:
    """Sobe o PNG mínimo no bucket público. Retorna a URL pública."""
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_KEY não configurada")

    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET_SAIDA}/{TEST_PATH}"
    async with httpx.AsyncClient() as c:
        r = await c.post(
            url,
            content=_TINY_PNG,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "image/png",
                "x-upsert": "true",
            },
            timeout=15,
        )
        r.raise_for_status()

    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET_SAIDA}/{TEST_PATH}"
    print(f"[UPLOAD] OK → {public_url}")
    return public_url


async def insert_test_row(public_url: str) -> None:
    async with db.pool().acquire() as c:
        await c.execute(
            """
            INSERT INTO midia_disponivel (restaurant_id, chave, url, descricao, mime_type)
            VALUES ($1, $2, $3, $4, 'image/png')
            ON CONFLICT (restaurant_id, chave) DO UPDATE SET url = EXCLUDED.url, ativo = true
            """,
            TEST_RID, TEST_CHAVE, public_url, "Imagem de teste (Fable CI)",
        )
    print(f"[DB] linha de teste inserida — chave={TEST_CHAVE!r}")


async def cleanup() -> None:
    async with db.pool().acquire() as c:
        await c.execute(
            "DELETE FROM midia_disponivel WHERE restaurant_id=$1 AND chave=$2",
            TEST_RID, TEST_CHAVE,
        )
    print("[DB] linha de teste removida")


async def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: railway run python3 test_enviar_midia.py +5511XXXXXXXXX")
        sys.exit(1)

    user_phone = sys.argv[1]

    await db.init_db()

    print(f"\n=== TESTE enviar_midia → {user_phone} ===\n")

    public_url = await upload_test_file()
    await insert_test_row(public_url)

    import tools as tool_fns
    resultado = await tool_fns.enviar_midia(TEST_RID, user_phone, TEST_CHAVE)
    print(f"\n[RESULTADO] {resultado!r}")

    await cleanup()
    print("\n=== FIM DO TESTE ===")


asyncio.run(main())

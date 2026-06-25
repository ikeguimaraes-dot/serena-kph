"""
Smoke test pós-deploy — testa se a Serena está respondendo após cada push.
Chamado automaticamente pelo GitHub Actions ou manualmente.
"""
import asyncio
import os
import sys
import httpx

BACKEND_URL = os.environ.get(
    "BACKEND_URL",
    "https://restaurant-ai-production-bb5d.up.railway.app"
)
TEST_PHONE = os.environ.get("SMOKE_TEST_PHONE", "+5511999000000")
RESTAURANT_PHONE = os.environ.get("TWILIO_FROM_NUMBER", "+5511988302367")
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "")
TIMEOUT = 30


async def send_test_message() -> bool:
    """Envia mensagem de teste no webhook e verifica se retorna 200."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{BACKEND_URL}/webhook/whatsapp",
            data={
                "Body": "smoke test — ignore",
                "From": f"whatsapp:{TEST_PHONE}",
                "To": f"whatsapp:{RESTAURANT_PHONE}",
            }
        )
        return resp.status_code == 200


async def check_health() -> bool:
    """Verifica se o /health retorna ok."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BACKEND_URL}/health")
        return resp.status_code == 200 and resp.json().get("status") == "ok"


async def notify_discord(message: str):
    """Envia alerta no Discord."""
    if not DISCORD_WEBHOOK:
        print(f"[SMOKE] Discord não configurado: {message}")
        return
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(DISCORD_WEBHOOK, json={"content": message})


async def main():
    print(f"[SMOKE] Testando {BACKEND_URL}...")

    health_ok = await check_health()
    if not health_ok:
        msg = f"🔴 **SMOKE TEST FALHOU** — `/health` não respondeu.\nBackend: {BACKEND_URL}"
        await notify_discord(msg)
        print(f"[SMOKE] FALHOU: health check")
        sys.exit(1)

    print(f"[SMOKE] OK — backend online após deploy")
    await notify_discord(f"✅ **Smoke test passou** — backend online após deploy.\nBackend: {BACKEND_URL}")
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())

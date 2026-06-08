"""Faz upload do _FALLBACK_BODY atual como versão 6 do prompt."""
import requests, sys, os

sys.path.insert(0, os.path.dirname(__file__))
from agent_prompt import _FALLBACK_BODY

BASE_URL = "https://restaurant-ai-production-bb5d.up.railway.app"

payload = {
    "nome": "serena-v9",
    "versao": "9",
    "prompt_completo": _FALLBACK_BODY,
    "ativar": True,
}

ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "kph@serena2026")  # prefira env var
r = requests.post(f"{BASE_URL}/api/serena/prompts", json=payload, headers={"X-Admin-Secret": ADMIN_SECRET}, timeout=20)
print(r.status_code, r.json())

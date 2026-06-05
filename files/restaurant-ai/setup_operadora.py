"""
setup_operadora.py — Cria o usuário operadora@madonna.com.br no Supabase Auth
e insere na tabela operadores com role='operador'.

Pré-requisito: SUPABASE_SERVICE_KEY (encontre em: Supabase dashboard → Project Settings → API → service_role)

Uso:
    SUPABASE_SERVICE_KEY=eyJ... python3 setup_operadora.py
"""
import os
import sys
import urllib.request
import urllib.error
import json
from typing import Optional

SUPABASE_URL = "https://fgntcrxuhfwcauvahaiz.supabase.co"
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

USER_EMAIL = "operadora@madonna.com.br"
USER_PASSWORD = "madonna@2026"
USER_NOME = "Operadora Madonna"
USER_ROLE = "operador"

if not SERVICE_KEY:
    print("ERRO: defina SUPABASE_SERVICE_KEY antes de rodar este script.")
    print("  Acesse: Supabase Dashboard → Project Settings → API → service_role key")
    sys.exit(1)

HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
}

def req(method: str, url: str, body: Optional[dict] = None) -> dict:
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(r) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:
        resp = json.loads(e.read())
        raise RuntimeError(f"HTTP {e.code}: {resp}") from e

# 1. Cria o usuário via Admin Auth API
print(f"Criando usuário {USER_EMAIL}...")
try:
    result = req("POST", f"{SUPABASE_URL}/auth/v1/admin/users", {
        "email": USER_EMAIL,
        "password": USER_PASSWORD,
        "email_confirm": True,   # pula verificação de email
        "app_metadata": {"role": USER_ROLE},
        "user_metadata": {"nome": USER_NOME},
    })
    user_id = result["id"]
    print(f"  ✓ Usuário criado: {user_id}")
except RuntimeError as e:
    if "already been registered" in str(e) or "already exists" in str(e):
        print("  ! Usuário já existe — buscando ID...")
        users = req("GET", f"{SUPABASE_URL}/auth/v1/admin/users?page=1&per_page=100")
        match = next((u for u in users.get("users", []) if u["email"] == USER_EMAIL), None)
        if not match:
            print("  ERRO: usuário existe mas não encontrado na listagem.")
            sys.exit(1)
        user_id = match["id"]
        # Atualiza app_metadata para garantir role correto
        req("PUT", f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}", {
            "app_metadata": {"role": USER_ROLE},
        })
        print(f"  ✓ ID existente: {user_id} — app_metadata atualizado")
    else:
        raise

# 2. Insere / upsert na tabela operadores via REST
print("Inserindo na tabela operadores...")
try:
    req("POST", f"{SUPABASE_URL}/rest/v1/operadores", {
        "id": user_id,
        "email": USER_EMAIL,
        "nome": USER_NOME,
        "role": USER_ROLE,
    })
    print("  ✓ Linha inserida em operadores")
except RuntimeError as e:
    if "duplicate" in str(e).lower() or "unique" in str(e).lower():
        # Upsert via PATCH
        req("PATCH", f"{SUPABASE_URL}/rest/v1/operadores?id=eq.{user_id}", {
            "role": USER_ROLE,
            "nome": USER_NOME,
        })
        print("  ✓ Linha existente atualizada em operadores")
    else:
        raise

print()
print("✓ Setup concluído!")
print(f"  Email:  {USER_EMAIL}")
print(f"  Senha:  {USER_PASSWORD}")
print(f"  Role:   {USER_ROLE}")
print()
print("  Este usuário pode acessar: /os, /reservas, /conversas, /cardápio")
print("  Bloqueado de: /admin, /admin/serena, /relatorios, /contatos, /kanban")

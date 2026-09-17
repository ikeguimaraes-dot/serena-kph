#!/usr/bin/env python3
"""Three synthetic vision turns; no process(), tools, CRM, messages or bookings.

Run explicitly only: uses the configured Anthropic API and incurs model usage.
Database is closed before model calls. All artifacts must stay outside Git.
"""
import argparse
import asyncio
import base64
import contextlib
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import inspect
import io
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import unicodedata
import zlib

TARGETS = {"meet_and_eat": 10, "madonna_cucina": 9, "freneze": 8}
QUESTION = "Pode me ajudar a ler esta imagem? Descreva o que dá para ver e diga se ela permite saber o preço ou a disponibilidade de algum item da casa."


def synthetic_png():
    """RGB PNG drawn from scratch: red circle, blue square, green triangle."""
    width, height = 640, 320
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            color = (255, 255, 255)
            if (x - 110) ** 2 + (y - 160) ** 2 <= 64 ** 2:
                color = (230, 25, 30)
            elif 270 <= x <= 390 and 90 <= y <= 210:
                color = (20, 80, 220)
            elif 80 <= y <= 220 and abs(x - 520) <= (y - 80) / 2:
                color = (25, 165, 65)
            rows.extend(color)
    def chunk(kind, content):
        return struct.pack(">I", len(content)) + kind + content + struct.pack(">I", zlib.crc32(kind + content) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes(rows))) + chunk(b"IEND", b"")


def image_message(image):
    return [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(image).decode("ascii")}},
        {"type": "text", "text": QUESTION},
    ]}]


def factual_checks(text):
    normalized = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")
    checks = {}
    for shape, color in (("circulo", "vermelho"), ("quadrado", "azul"), ("triangulo", "verde")):
        checks[f"{shape}_{color}"] = bool(re.search(fr"{shape}.{{0,30}}{color}|{color}.{{0,30}}{shape}", normalized))
    checks["no_numeric_price"] = not bool(re.search(r"r\$\s*\d|\d+(?:[.,]\d+)?\s*reais|(?:preco|custa)\s*(?:e|de)?\s*\d", normalized))
    checks["no_handoff_marker"] = "__HANDOFF__" not in text
    return checks


def private_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    with path.open("xb") as output:
        output.write(data)
    path.chmod(0o600)


async def load_drafts(dsn):
    import asyncpg
    connection = await asyncpg.connect(dsn, ssl="require", statement_cache_size=0, command_timeout=20)
    snapshots = []
    try:
        async with connection.transaction(readonly=True, isolation="repeatable_read"):
            if await connection.fetchval("SHOW transaction_read_only") != "on":
                raise RuntimeError("READONLY_NOT_ESTABLISHED")
            for rid, pid in TARGETS.items():
                row = await connection.fetchrow("""SELECT id,nome,nome_agente,personalidade,endereco,
                    capacidade_maxima_reserva,antecedencia_minima_horas FROM restaurants WHERE id=$1""", rid)
                prompt = await connection.fetchrow("""SELECT id,restaurant_id,prompt_completo,ativa
                    FROM serena_prompt_versions WHERE id=$1 AND restaurant_id=$2""", pid, rid)
                if not row or not prompt:
                    raise RuntimeError("EXPECTED_UNIT_OR_DRAFT_NOT_FOUND")
                restaurant = dict(row)
                hours = await connection.fetch("SELECT dia,horario,fechado FROM business_hours WHERE restaurant_id=$1 ORDER BY id", rid)
                restaurant["horarios"] = {r["dia"]: "Fechado" if r["fechado"] else r["horario"] for r in hours}
                faq = await connection.fetch("SELECT chave,resposta FROM faq_items WHERE restaurant_id=$1 ORDER BY ordem", rid)
                restaurant["faq"] = {r["chave"]: r["resposta"] for r in faq}
                dates = await connection.fetch("""SELECT data,nome,aberto,horario_especial,observacao FROM datas_especiais
                    WHERE restaurant_id=$1 AND data>=CURRENT_DATE AND data<=CURRENT_DATE+INTERVAL '60 days' ORDER BY data""", rid)
                restaurant["datas_especiais"] = [dict(r) for r in dates]
                snapshots.append((restaurant, dict(prompt)))
    finally:
        await connection.close()
    return snapshots


async def run(args):
    os.umask(0o077)
    output = args.output.expanduser().resolve()
    if any((directory / ".git").exists() for directory in (output, *output.parents)):
        raise RuntimeError("PRIVATE_OUTPUT_MUST_BE_OUTSIDE_GIT")
    backend = args.backend.expanduser().resolve()
    env_result = subprocess.run(["railway", "variable", "list", "--service", "restaurant-ai", "--environment", "production", "--json"],
                                cwd=args.railway_cwd, capture_output=True, text=True, check=False)
    if env_result.returncode:
        raise RuntimeError("RAILWAY_VARIABLE_READ_FAILED")
    variables = json.loads(env_result.stdout)
    key = variables.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_KEY_UNAVAILABLE")
    # Backup configuration is read in memory; do not export the DSN to environment.
    config_path = Path.home() / ".config/serena-backup/config.json"
    if config_path.stat().st_mode & 0o077:
        raise RuntimeError("PRIVATE_CONFIG_PERMISSIONS_TOO_OPEN")
    dsn = json.loads(config_path.read_text())["database_url"]
    snapshots = await load_drafts(dsn)
    del dsn, variables, env_result
    os.environ["ANTHROPIC_API_KEY"] = key
    sys.path.insert(0, str(backend))
    import anthropic
    import agent
    import database
    from agent_prompt import _dynamic_header
    agent.client = anthropic.Anthropic(api_key=key, max_retries=0, timeout=60)
    del key
    agent.MAX_ITERATIONS = 2
    blocked_tools = []
    async def deny_tool(name, arguments, phone, rid):
        blocked_tools.append({"name": name, "restaurant_id": rid})
        return "VALIDACAO_VISUAL_SOMENTE_LEITURA: ferramenta não executada. Não foram consultados preços, estoque, contatos ou reservas. Descreva somente a imagem recebida."
    async def forbidden(*_args, **_kwargs):
        raise RuntimeError("PERSISTENCE_OR_PROCESS_FORBIDDEN_IN_VISUAL_AUDIT")
    def no_pool(*_args, **_kwargs):
        raise RuntimeError("DATABASE_CLOSED_BEFORE_MODEL_CALL")
    # Defense in depth: no production dispatcher or DB operation is callable.
    agent.execute_tool = deny_tool
    agent.RestaurantAgent.process = forbidden
    for name, value in list(vars(database).items()):
        if inspect.iscoroutinefunction(value):
            setattr(database, name, forbidden)
    database.pool = no_pool
    image = synthetic_png()
    private_write(output / "synthetic-shapes.png", image)
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "source_commit": args.source_commit,
              "entrypoint": "RestaurantAgent._run(read_only=True)", "fixture_sha256": hashlib.sha256(image).hexdigest(),
              "fixture_bytes": len(image), "db_closed_before_model": True, "real_tool_dispatches": 0,
              "process_calls": 0, "customer_rows_read": 0, "application_writes": 0, "outbound_messages": 0,
              "max_calls": 6, "cases": [], "blocked_tools": blocked_tools}
    costs = []
    for restaurant, prompt in snapshots:
        body = prompt["prompt_completo"]
        # Matches test_turn's prompt_body_override path; no CRM context or history.
        system = _dynamic_header(restaurant, "") + "\n" + body
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            result = await agent.RestaurantAgent()._run(system=system, messages=image_message(image),
                user_phone="+synthetic-vision-audit", rid=restaurant["id"], read_only=True)
        checks = factual_checks(result["text"])
        for call in result.get("usage_calls", []):
            costs.append(Decimal(call["cost_usd"]) if call.get("cost_usd") is not None else None)
        record = {"restaurant_id": restaurant["id"], "prompt_id": prompt["id"], "prompt_active_at_read": prompt["ativa"],
                  "prompt_sha256": hashlib.sha256(body.encode()).hexdigest(), "system_chars": len(system),
                  "response": result["text"], "checks": checks, "tools_called": result["tools_called"], "usage_calls": result.get("usage_calls", [])}
        report["cases"].append(record)
        print(json.dumps({"restaurant_id": restaurant["id"], "prompt_id": prompt["id"], "checks": checks, "call_count": len(record["usage_calls"])}), flush=True)
    report["observed_cost_usd"] = str(sum(costs, Decimal("0"))) if costs and all(value is not None for value in costs) else None
    private_write(output / "vision-proof.json", (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode())
    print(json.dumps({"completed_cases": len(report["cases"]), "observed_cost_usd": report["observed_cost_usd"], "artifacts_mode": "0600"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--railway-cwd", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    arguments = parser.parse_args()
    try:
        asyncio.run(run(arguments))
    except Exception as error:
        # Do not leak DSNs, credentials, model request payloads or provider errors.
        safe_codes = {"READONLY_NOT_ESTABLISHED", "EXPECTED_UNIT_OR_DRAFT_NOT_FOUND", "PRIVATE_OUTPUT_MUST_BE_OUTSIDE_GIT",
                      "RAILWAY_VARIABLE_READ_FAILED", "ANTHROPIC_KEY_UNAVAILABLE", "PRIVATE_CONFIG_PERMISSIONS_TOO_OPEN",
                      "PERSISTENCE_OR_PROCESS_FORBIDDEN_IN_VISUAL_AUDIT", "DATABASE_CLOSED_BEFORE_MODEL_CALL"}
        print(json.dumps({"status": "failed", "error_type": type(error).__name__, "code": str(error) if str(error) in safe_codes else None}), file=sys.stderr)
        raise SystemExit(1)

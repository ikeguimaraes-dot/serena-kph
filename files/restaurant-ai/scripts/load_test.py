#!/usr/bin/env python3
"""
9.4 — Teste de carga Serena
50 workers simultâneos, 3 mensagens sequenciais cada, métricas p50/p95/erro.

Uso:
    python3 scripts/load_test.py
    python3 scripts/load_test.py --workers 20 --url https://...

Variáveis de ambiente (opcionais):
    BACKEND_URL   — URL do backend Railway
    TWILIO_FROM_NUMBER — número sender (formato E.164 sem whatsapp:)
    WEBHOOK_SECRET     — para gerar HMAC correto nos POSTs
"""

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import statistics
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional

import httpx

# ── Configuração padrão ──────────────────────────────────────────────────────
DEFAULT_BACKEND    = os.getenv("BACKEND_URL", "https://restaurant-ai-production-bb5d.up.railway.app")
DEFAULT_FROM       = os.getenv("TWILIO_FROM_NUMBER", "+5511988302367")
DEFAULT_WORKERS    = 50
DEFAULT_MESSAGES   = 3
WEBHOOK_SECRET     = os.getenv("WEBHOOK_SECRET", "")

# Conversa simulada — 3 turnos realistas
CONVERSATION = [
    "Oi, boa tarde! Gostaria de saber mais sobre reservas",
    "Para 2 pessoas na próxima sexta à noite, tem disponibilidade?",
    "Qual o cardápio de vocês?",
]

# ── Helpers ──────────────────────────────────────────────────────────────────

def make_twilio_body(from_: str, to: str, msg: str, restaurant_id: str) -> dict:
    """Monta o payload que o Twilio enviaria no webhook."""
    return {
        "From": f"whatsapp:{from_}",
        "To":   f"whatsapp:{to}",
        "Body": msg,
        "AccountSid": "ACtest000000000000000000000000000000",
        "MessageSid": f"SMtest{abs(hash(from_+msg)):016x}",
        "NumMedia": "0",
    }


def sign_twilio(body: dict, url: str, secret: str) -> str:
    """Gera X-Twilio-Signature para validação HMAC."""
    if not secret:
        return "test-no-secret"
    sorted_params = "".join(f"{k}{v}" for k, v in sorted(body.items()))
    msg = (url + sorted_params).encode()
    return hmac.new(secret.encode(), msg, hashlib.sha1).hexdigest()


@dataclass
class WorkerResult:
    worker_id:  int
    latencies:  list[float] = field(default_factory=list)
    errors:     list[str]   = field(default_factory=list)
    success:    int = 0


# ── Worker ───────────────────────────────────────────────────────────────────

async def run_worker(
    worker_id: int,
    client: httpx.AsyncClient,
    backend: str,
    messages: list[str],
    restaurant_id: str = "madonna_cucina",
) -> WorkerResult:
    result = WorkerResult(worker_id=worker_id)
    # Número de telefone único por worker (simula clientes distintos)
    fake_phone = f"+5511{90000000 + worker_id:08d}"
    webhook_url = f"{backend}/webhook/whatsapp"
    # Número WhatsApp Business do restaurante (receiver)
    to_number = DEFAULT_FROM

    for msg in messages:
        body = make_twilio_body(from_=fake_phone, to=to_number, msg=msg, restaurant_id=restaurant_id)
        sig  = sign_twilio(body, webhook_url, WEBHOOK_SECRET)
        headers = {
            "Content-Type":      "application/x-www-form-urlencoded",
            "X-Twilio-Signature": sig,
        }
        t0 = time.perf_counter()
        try:
            resp = await client.post(
                webhook_url,
                data=urllib.parse.urlencode(body),
                headers=headers,
                timeout=30.0,
            )
            elapsed = time.perf_counter() - t0
            result.latencies.append(elapsed)
            if resp.status_code not in (200, 204):
                result.errors.append(f"w{worker_id} msg={msg[:20]!r} → HTTP {resp.status_code}")
            else:
                result.success += 1
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            result.latencies.append(elapsed)
            result.errors.append(f"w{worker_id} msg={msg[:20]!r} → {type(exc).__name__}: {exc}")

        # Pequeno delay entre mensagens do mesmo cliente (realista)
        await asyncio.sleep(0.5)

    return result


# ── Orquestração ─────────────────────────────────────────────────────────────

async def run_load_test(backend: str, workers: int, messages: int) -> None:
    msgs = CONVERSATION[:messages]
    total_requests = workers * len(msgs)

    print(f"\n{'='*60}")
    print(f"  Serena Load Test")
    print(f"  Backend:  {backend}")
    print(f"  Workers:  {workers}")
    print(f"  Msgs/wkr: {len(msgs)}")
    print(f"  Total:    {total_requests} requisições")
    print(f"{'='*60}\n")

    limits = httpx.Limits(max_connections=workers + 10, max_keepalive_connections=workers)
    async with httpx.AsyncClient(limits=limits) as client:
        t_start = time.perf_counter()
        tasks = [
            run_worker(i, client, backend, msgs)
            for i in range(workers)
        ]
        results: list[WorkerResult] = await asyncio.gather(*tasks)
        t_total = time.perf_counter() - t_start

    # Agrega métricas
    all_latencies = []
    all_errors    = []
    total_success = 0
    for r in results:
        all_latencies.extend(r.latencies)
        all_errors.extend(r.errors)
        total_success += r.success

    n = len(all_latencies)
    if n == 0:
        print("Nenhuma latência registrada — todos os workers falharam antes de receber resposta.")
        return

    sorted_lat = sorted(all_latencies)
    p50 = statistics.median(all_latencies)
    p95 = sorted_lat[int(n * 0.95)] if n >= 20 else max(all_latencies)
    p99 = sorted_lat[int(n * 0.99)] if n >= 100 else max(all_latencies)
    err_rate = len(all_errors) / total_requests * 100

    print(f"{'RESULTADOS':}")
    print(f"  Tempo total:      {t_total:.1f}s")
    print(f"  Requisições:      {total_requests} ({total_success} ok, {len(all_errors)} erro)")
    print(f"  Taxa de erro:     {err_rate:.1f}%")
    print(f"  Latência média:   {statistics.mean(all_latencies)*1000:.0f} ms")
    print(f"  Latência p50:     {p50*1000:.0f} ms")
    print(f"  Latência p95:     {p95*1000:.0f} ms")
    print(f"  Latência p99:     {p99*1000:.0f} ms")
    print(f"  Throughput:       {total_requests/t_total:.1f} req/s")

    if all_errors:
        print(f"\n  Primeiros 5 erros:")
        for e in all_errors[:5]:
            print(f"    ✗ {e}")

    print(f"\n{'='*60}")

    # Diagnóstico automático
    issues = []
    if p95 > 5.0:
        issues.append(
            f"p95={p95:.1f}s > 5s  → gargalo provável: pool de DB ou concorrência Claude API. "
            "Ação: aumentar --workers no Railway (Settings → Deploy → Workers) ou reduzir "
            "max_tokens do modelo."
        )
    if err_rate > 5.0:
        issues.append(
            f"taxa de erro={err_rate:.1f}% > 5%  → verificar WEBHOOK_SECRET, rate limiting, "
            "ou timeout no Railway (aumentar timeout de 60s → 120s)."
        )
    if issues:
        print("\n  ⚠  GARGALOS DETECTADOS:")
        for iss in issues:
            print(f"     • {iss}")
    else:
        print("\n  ✓  Dentro dos SLAs (p95 < 5s, erro < 5%)")

    print(f"{'='*60}\n")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Serena load test")
    parser.add_argument("--workers",  type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--messages", type=int, default=DEFAULT_MESSAGES)
    parser.add_argument("--url",      default=DEFAULT_BACKEND)
    args = parser.parse_args()

    try:
        import httpx  # noqa — já importado acima
    except ImportError:
        print("Instale: pip install httpx")
        raise SystemExit(1)

    asyncio.run(run_load_test(args.url, args.workers, args.messages))


if __name__ == "__main__":
    main()

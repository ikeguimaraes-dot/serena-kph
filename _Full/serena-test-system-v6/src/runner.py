"""
runner.py — executa os casos do corpus contra a Serena (Claude API).

Uso:
    python runner.py                              # roda todos os 225
    python runner.py --severity critical          # só 🔴 (53 casos)
    python runner.py --block adversarial          # bloco específico
    python runner.py --tags lgpd privacidade      # filtro por tags
    python runner.py --limit 10                   # primeiros N casos (teste rápido)

Output:
    results/raw_<timestamp>.json
"""

import os
import json
import argparse
import time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from anthropic import Anthropic
except ImportError:
    raise SystemExit("Instale: pip install anthropic")


# ================================================================
# CONFIG
# ================================================================
MODEL = os.getenv("SERENA_MODEL", "claude-opus-4-7")
MAX_WORKERS = int(os.getenv("SERENA_PARALLEL", "5"))
ROOT = Path(__file__).parent.parent

CORPUS_PATH = ROOT / "corpus" / "mdna_v6.json"
PROMPT_PATH = ROOT / "prompts" / "serena_system_prompt.txt"
RESULTS_DIR = ROOT / "results"


# ================================================================
# HELPERS
# ================================================================
def load_corpus():
    data = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    return data["corpus"]


def load_system_prompt():
    return PROMPT_PATH.read_text(encoding="utf-8")


def render_context_injection(case):
    """Monta injeção de contexto ficticio antes do input do cliente."""
    ctx = case.get("context", {})
    parts = []

    if ctx.get("client_profile") == "returning":
        visits = ctx.get("visits", 5)
        pref = ctx.get("preference", "mesa do fundo").replace("_", " ")
        parts.append(f"[Cliente na base: {visits} reservas anteriores, preferência: {pref}]")

    if ctx.get("client_profile") == "vip":
        flags = ", ".join(ctx.get("flags", []))
        name = ctx.get("name")
        if name:
            parts.append(f"[Cliente VIP na base: {name} — {flags}]")
        else:
            parts.append(f"[Cliente VIP: {flags}]")

    if ctx.get("client_profile") == "vip_relative":
        parts.append("[Ficha: cônjuge de VIP conhecido da casa]")

    if ctx.get("client_profile") == "corporate_returning":
        parts.append("[Cliente corporativo recorrente]")

    if ctx.get("real_time"):
        parts.append("[Mensagem recebida AGORA — cliente na casa]")

    if ctx.get("system_state") == "db_down":
        parts.append("[Sistema de reservas em manutenção]")

    if ctx.get("system_state"):
        parts.append(f"[Estado do sistema: {ctx['system_state']}]")

    if ctx.get("no_shows", 0) >= 3:
        parts.append(f"[Histórico: {ctx['no_shows']} no-shows acumulados]")

    if ctx.get("previous_turn"):
        parts.append(f"[Contexto anterior: {ctx['previous_turn']}]")

    if ctx.get("input_type") in ("audio_only", "image", "video"):
        parts.append(f"[Input recebido: {ctx['input_type']} — sem texto]")

    if ctx.get("channel") == "internal_alert":
        parts.append("[Canal: alerta operacional interno, não cliente direto]")

    if ctx.get("flag"):
        parts.append(f"[Flag interna: {ctx['flag']}]")

    if ctx.get("ficha"):
        parts.append(f"[Ficha do cliente: {ctx['ficha']}]")

    if ctx.get("database_conflict"):
        parts.append(f"[Conflito na base: {ctx['database_conflict']}]")

    if ctx.get("availability"):
        parts.append(f"[Disponibilidade na base: {ctx['availability']}]")

    return "\n".join(parts) + "\n\n" if parts else ""


def should_run(case, severity=None, block=None, tags=None, ids=None):
    if ids and case["id"] not in ids:
        return False
    if severity and case["severity"] != severity:
        return False
    if block and case["block"] != block:
        return False
    if tags:
        case_tags = set(case.get("tags", []))
        if not case_tags.intersection(tags):
            return False
    return True


# ================================================================
# EXECUÇÃO DE UM CASO
# ================================================================
def run_case(client, case, system_prompt):
    ctx_injection = render_context_injection(case)
    user_message = ctx_injection + case["input"]

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        actual_response = response.content[0].text
        error = None
    except Exception as e:
        actual_response = ""
        error = str(e)

    return {
        "case_id": case["id"],
        "block": case["block"],
        "severity": case["severity"],
        "tags": case["tags"],
        "input": case["input"],
        "context_injection": ctx_injection.strip(),
        "actual_response": actual_response,
        "expected_behaviors": case["expected_behaviors"],
        "forbidden_behaviors": case["forbidden_behaviors"],
        "reference_response": case["reference_response"],
        "error": error,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ================================================================
# MAIN
# ================================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--severity", choices=["critical", "important", "edge"])
    parser.add_argument("--block", type=str)
    parser.add_argument("--tags", nargs="+")
    parser.add_argument("--ids", nargs="+", help="IDs específicos (MDNA-001 etc)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Só conta casos que rodariam")
    args = parser.parse_args()

    corpus = load_corpus()
    system_prompt = load_system_prompt()

    tags = set(args.tags) if args.tags else None
    ids = set(args.ids) if args.ids else None

    filtered = [
        c for c in corpus
        if should_run(c, severity=args.severity, block=args.block, tags=tags, ids=ids)
    ]

    if args.limit:
        filtered = filtered[:args.limit]

    print(f"Total no corpus: {len(corpus)}")
    print(f"Filtrados: {len(filtered)}")

    if args.dry_run:
        for c in filtered[:20]:
            print(f"  {c['id']} [{c['severity']:9s}] {c['block']:25s} — {c['input'][:50]}...")
        if len(filtered) > 20:
            print(f"  ... e mais {len(filtered) - 20}")
        return

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("\n⚠️  ANTHROPIC_API_KEY não definida. Configure antes de rodar.")
        print("    export ANTHROPIC_API_KEY='sk-ant-...'")
        return

    client = Anthropic()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\nRodando {len(filtered)} casos em paralelo (workers={MAX_WORKERS})...")
    print(f"Modelo: {MODEL}")
    start = time.time()

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(run_case, client, c, system_prompt): c for c in filtered}
        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            results.append(result)
            status = "✗" if result["error"] else "✓"
            print(f"  [{i:3d}/{len(filtered)}] {status} {result['case_id']}")

    elapsed = time.time() - start
    print(f"\nConcluído em {elapsed:.1f}s ({elapsed / len(filtered):.2f}s/caso)")

    # Ordena por case_id pra estabilidade
    results.sort(key=lambda r: r["case_id"])

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"raw_{timestamp}.json"
    out_path.write_text(
        json.dumps(
            {
                "model": MODEL,
                "total_cases": len(results),
                "filters": {
                    "severity": args.severity,
                    "block": args.block,
                    "tags": list(tags) if tags else None,
                    "ids": list(ids) if ids else None,
                    "limit": args.limit,
                },
                "timestamp": timestamp,
                "elapsed_seconds": elapsed,
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    errors = [r for r in results if r["error"]]
    print(f"\n✓ Resultados: {out_path}")
    if errors:
        print(f"⚠ Erros: {len(errors)}")
        for e in errors[:5]:
            print(f"  - {e['case_id']}: {e['error'][:100]}")


if __name__ == "__main__":
    main()

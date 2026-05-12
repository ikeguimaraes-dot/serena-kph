"""
smoke_test.py — valida que o pipeline MDNA funciona de ponta a ponta.

Roda 5 casos canonicos de reserva simples (baseline verde) e falha se qualquer
um deles virar 'fail'. Uso rapido antes de rodar critical/full.

    python smoke_test.py
"""
import sys
import subprocess
import json
from pathlib import Path

ROOT = Path(__file__).parent
SMOKE_IDS = ["MDNA-002", "MDNA-054", "MDNA-067", "MDNA-140", "MDNA-188"]


def main():
    print(f"[smoke] rodando {len(SMOKE_IDS)} casos canonicos...")
    result = subprocess.run(
        [sys.executable, str(ROOT / "run.py"), "--ids", *SMOKE_IDS],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    judged = sorted((ROOT / "results").glob("judged_*.json"), key=lambda p: p.stat().st_mtime)[-1]
    data = json.loads(judged.read_text(encoding="utf-8"))
    fails = [j for j in data["judgments"] if j["verdict"] == "fail"]

    print("\n[smoke] resumo:")
    for j in data["judgments"]:
        print(f"  {j['case_id']:10s} {j['verdict']:6s} total={j['total']}")

    if fails:
        print(f"\n[smoke] FALHOU: {len(fails)} caso(s) canonicos viraram fail")
        for j in fails:
            print(f"  - {j['case_id']}: {j.get('comentario','')}")
        sys.exit(1)

    print(f"\n[smoke] OK: {len(data['judgments'])} casos canonicos sem fail")


if __name__ == "__main__":
    main()

"""
run.py — orquestrador. Roda runner → judge → aggregator em sequência.

Uso:
    python run.py                                  # roda todos os 225
    python run.py --severity critical              # só 🔴
    python run.py --limit 10                       # teste rápido
    python run.py --baseline results/judged_<X>.json  # compara com anterior
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path


ROOT = Path(__file__).parent
SRC = ROOT / "src"
RESULTS = ROOT / "results"


def ensure_api_key():
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("⚠️  ANTHROPIC_API_KEY não definida.")
        print("    export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)


def find_latest(prefix):
    files = sorted(RESULTS.glob(f"{prefix}*.json"))
    return files[-1] if files else None


def run_cmd(cmd):
    print(f"\n$ {' '.join(str(c) for c in cmd)}\n")
    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--severity", choices=["critical", "important", "edge"])
    parser.add_argument("--block")
    parser.add_argument("--tags", nargs="+")
    parser.add_argument("--ids", nargs="+")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--baseline", help="relatório anterior pra comparar")
    parser.add_argument("--skip-runner", action="store_true", help="pula runner, usa último raw_")
    parser.add_argument("--skip-judge", action="store_true", help="pula judge, usa último judged_")
    args = parser.parse_args()

    ensure_api_key()

    # 1. Runner
    if not args.skip_runner:
        cmd = [sys.executable, str(SRC / "runner.py")]
        if args.severity:
            cmd += ["--severity", args.severity]
        if args.block:
            cmd += ["--block", args.block]
        if args.tags:
            cmd += ["--tags"] + args.tags
        if args.ids:
            cmd += ["--ids"] + args.ids
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        run_cmd(cmd)

    raw_file = find_latest("raw_")
    if not raw_file:
        print("✗ Nenhum arquivo raw_ encontrado.")
        sys.exit(1)

    # 2. Judge
    if not args.skip_judge:
        cmd = [sys.executable, str(SRC / "judge.py"), str(raw_file)]
        run_cmd(cmd)

    judged_file = find_latest("judged_")
    if not judged_file:
        print("✗ Nenhum arquivo judged_ encontrado.")
        sys.exit(1)

    # 3. Aggregator
    cmd = [sys.executable, str(SRC / "aggregator.py"), str(judged_file)]
    if args.baseline:
        cmd += ["--baseline", args.baseline]
    run_cmd(cmd)

    print(f"\n{'=' * 50}")
    print(f"PIPELINE CONCLUÍDO")
    print(f"{'=' * 50}")
    print(f"Raw:    {raw_file.name}")
    print(f"Judged: {judged_file.name}")
    report = find_latest("report_")
    if report and report.suffix == ".md":
        pass
    reports = sorted(RESULTS.glob("report_*.md"))
    if reports:
        print(f"Report: {reports[-1].name}")


if __name__ == "__main__":
    main()

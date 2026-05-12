"""
judge.py — avalia as respostas do runner usando LLM-as-judge.

Uso:
    python judge.py results/raw_20260423_120000.json

Output:
    results/judged_<timestamp>.json
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from anthropic import Anthropic
except ImportError:
    raise SystemExit("Instale: pip install anthropic")


MODEL = os.getenv("JUDGE_MODEL", "claude-opus-4-7")
MAX_WORKERS = int(os.getenv("JUDGE_PARALLEL", "5"))
ROOT = Path(__file__).parent.parent
JUDGE_PROMPT_PATH = ROOT / "prompts" / "judge_prompt_template.txt"
RESULTS_DIR = ROOT / "results"


def load_judge_template():
    return JUDGE_PROMPT_PATH.read_text(encoding="utf-8")


def format_list(items):
    return "\n".join(f"  - {x}" for x in items)


def build_judge_prompt(template, run_result):
    """Substitui placeholders no template com o conteúdo do run_result."""
    return template.format(
        case_id=run_result["case_id"],
        block=run_result["block"],
        severity=run_result["severity"],
        input=run_result["input"].replace("{", "{{").replace("}", "}}"),
        actual_response=run_result["actual_response"].replace("{", "{{").replace("}", "}}"),
        expected_behaviors=format_list(run_result["expected_behaviors"]),
        forbidden_behaviors=format_list(run_result["forbidden_behaviors"]),
        reference_response=run_result["reference_response"].replace("{", "{{").replace("}", "}}"),
    )


def parse_judge_output(text):
    """Extrai JSON do output do judge mesmo com eventual ```json wrap."""
    text = text.strip()
    if text.startswith("```"):
        # Remove cercas de código
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def judge_case(client, run_result, template):
    if run_result.get("error"):
        return {
            "case_id": run_result["case_id"],
            "block": run_result["block"],
            "severity": run_result["severity"],
            "scores": None,
            "total": 0,
            "verdict": "fail",
            "critical_failures": ["runner_error"],
            "observations": f"Runner falhou: {run_result['error']}",
            "judge_error": None,
        }

    prompt = build_judge_prompt(template, run_result)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        parsed = parse_judge_output(raw)
        parsed["block"] = run_result["block"]
        parsed["severity"] = run_result["severity"]
        parsed["judge_error"] = None
        return parsed
    except Exception as e:
        return {
            "case_id": run_result["case_id"],
            "block": run_result["block"],
            "severity": run_result["severity"],
            "scores": None,
            "total": 0,
            "verdict": "review",
            "critical_failures": [],
            "observations": "",
            "judge_error": str(e),
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file", help="results/raw_<timestamp>.json")
    args = parser.parse_args()

    input_path = Path(args.input_file)
    if not input_path.exists():
        raise SystemExit(f"Arquivo não encontrado: {input_path}")

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("⚠️  ANTHROPIC_API_KEY não definida.")

    data = json.loads(input_path.read_text(encoding="utf-8"))
    run_results = data["results"]
    template = load_judge_template()
    client = Anthropic()

    print(f"Avaliando {len(run_results)} casos (workers={MAX_WORKERS}, modelo={MODEL})...")
    start = time.time()

    judged = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(judge_case, client, r, template): r for r in run_results}
        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            judged.append(result)
            verdict = result["verdict"]
            total = result.get("total", 0)
            print(f"  [{i:3d}/{len(run_results)}] {result['case_id']} [{verdict:6s}] total={total}")

    judged.sort(key=lambda r: r["case_id"])

    elapsed = time.time() - start
    print(f"\nConcluído em {elapsed:.1f}s")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"judged_{timestamp}.json"
    out_path.write_text(
        json.dumps(
            {
                "source_run": str(input_path.name),
                "judge_model": MODEL,
                "total_cases": len(judged),
                "timestamp": timestamp,
                "elapsed_seconds": elapsed,
                "run_results": run_results,
                "judgments": judged,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    passed = sum(1 for j in judged if j["verdict"] == "pass")
    failed = sum(1 for j in judged if j["verdict"] == "fail")
    review = sum(1 for j in judged if j["verdict"] == "review")

    print(f"\n✓ Avaliação: {out_path}")
    print(f"  Pass: {passed}  |  Fail: {failed}  |  Review: {review}")


if __name__ == "__main__":
    main()

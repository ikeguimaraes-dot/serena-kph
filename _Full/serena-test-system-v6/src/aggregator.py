"""
aggregator.py — consolida judgments em relatório markdown com deltas.

Uso:
    python aggregator.py results/judged_20260423_120000.json
    python aggregator.py results/judged_<new>.json --baseline results/judged_<old>.json

Output:
    results/report_<timestamp>.md
    results/dashboard_<timestamp>.html
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter


ROOT = Path(__file__).parent.parent
RESULTS_DIR = ROOT / "results"


def load_judged(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_summary(judged_data):
    judgments = judged_data["judgments"]
    run_results = {r["case_id"]: r for r in judged_data["run_results"]}

    overall = {
        "total": len(judgments),
        "pass": sum(1 for j in judgments if j["verdict"] == "pass"),
        "fail": sum(1 for j in judgments if j["verdict"] == "fail"),
        "review": sum(1 for j in judgments if j["verdict"] == "review"),
    }
    overall["pass_rate"] = overall["pass"] / overall["total"] if overall["total"] else 0

    # Por severidade
    by_severity = defaultdict(lambda: {"total": 0, "pass": 0, "fail": 0, "review": 0})
    for j in judgments:
        sev = j.get("severity", "unknown")
        by_severity[sev]["total"] += 1
        by_severity[sev][j["verdict"]] += 1

    # Por bloco
    by_block = defaultdict(lambda: {"total": 0, "pass": 0, "fail": 0, "review": 0, "avg_total": 0})
    for j in judgments:
        b = j.get("block", "unknown")
        by_block[b]["total"] += 1
        by_block[b][j["verdict"]] += 1
        by_block[b]["avg_total"] += j.get("total", 0)
    for b, data in by_block.items():
        data["avg_total"] = round(data["avg_total"] / data["total"], 2) if data["total"] else 0
        data["pass_rate"] = data["pass"] / data["total"] if data["total"] else 0

    # Por critério (só em casos com score)
    criterion_sums = defaultdict(int)
    criterion_counts = defaultdict(int)
    for j in judgments:
        scores = j.get("scores")
        if not scores:
            continue
        for k, v in scores.items():
            criterion_sums[k] += v
            criterion_counts[k] += 1
    by_criterion = {
        k: round(criterion_sums[k] / criterion_counts[k], 2)
        for k in criterion_sums
    }

    # Critical failures
    critical_fails = [
        j for j in judgments
        if j.get("severity") == "critical" and j["verdict"] == "fail"
    ]

    return {
        "overall": overall,
        "by_severity": dict(by_severity),
        "by_block": dict(by_block),
        "by_criterion": by_criterion,
        "critical_failures": critical_fails,
        "run_results": run_results,
        "judgments": judgments,
    }


def compare_with_baseline(current, baseline):
    """Calcula deltas em cima do baseline."""
    curr_map = {j["case_id"]: j for j in current["judgments"]}
    base_map = {j["case_id"]: j for j in baseline["judgments"]}

    regressions = []  # passou antes → falhou agora
    progressions = []  # falhou antes → passou agora
    stable_fails = []  # falhou nos dois

    for cid, curr in curr_map.items():
        if cid not in base_map:
            continue
        base = base_map[cid]
        if base["verdict"] == "pass" and curr["verdict"] == "fail":
            regressions.append((cid, base, curr))
        elif base["verdict"] == "fail" and curr["verdict"] == "pass":
            progressions.append((cid, base, curr))
        elif base["verdict"] == "fail" and curr["verdict"] == "fail":
            stable_fails.append((cid, curr))

    return {
        "regressions": regressions,
        "progressions": progressions,
        "stable_fails": stable_fails,
    }


def verdict_emoji(v):
    return {"pass": "✓", "fail": "✗", "review": "?"}.get(v, "-")


def severity_emoji(s):
    return {"critical": "🔴", "important": "🟡", "edge": "🟢"}.get(s, "")


def render_markdown(summary, comparison=None, model=None):
    out = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out.append(f"# MDNA — Relatório de Avaliação da Serena\n")
    out.append(f"*Gerado em {ts}*")
    if model:
        out.append(f" · Modelo avaliado: `{model}`")
    out.append("\n\n---\n")

    # Resumo geral
    o = summary["overall"]
    out.append("## Resumo Geral\n")
    out.append(f"- **Total avaliado**: {o['total']} casos")
    out.append(f"- **Pass rate**: {o['pass_rate'] * 100:.1f}% ({o['pass']}/{o['total']})")
    out.append(f"- **Pass**: {o['pass']}  ·  **Fail**: {o['fail']}  ·  **Review**: {o['review']}\n")

    # Por severidade
    out.append("## Por Severidade\n")
    out.append("| Severidade | Total | Pass | Fail | Review | Pass Rate |")
    out.append("|---|---|---|---|---|---|")
    for sev in ("critical", "important", "edge"):
        d = summary["by_severity"].get(sev)
        if not d:
            continue
        rate = d["pass"] / d["total"] * 100 if d["total"] else 0
        out.append(
            f"| {severity_emoji(sev)} {sev} | {d['total']} | {d['pass']} | "
            f"{d['fail']} | {d['review']} | {rate:.1f}% |"
        )
    out.append("")

    # Por bloco
    out.append("## Por Bloco\n")
    out.append("| Bloco | Total | Pass | Fail | Média |")
    out.append("|---|---|---|---|---|")
    for block, d in sorted(summary["by_block"].items(), key=lambda x: -x[1]["total"]):
        out.append(
            f"| {block} | {d['total']} | {d['pass']} | {d['fail']} | {d['avg_total']} |"
        )
    out.append("")

    # Por critério
    out.append("## Por Critério (média 0-2)\n")
    crit_order = ["voz", "antecipacao", "escalacao", "precisao", "encerramento"]
    out.append("| Critério | Média |")
    out.append("|---|---|")
    for crit in crit_order:
        if crit in summary["by_criterion"]:
            out.append(f"| {crit.capitalize()} | {summary['by_criterion'][crit]} |")
    out.append("")

    # Falhas críticas
    if summary["critical_failures"]:
        out.append(f"## ⚠️ Falhas Críticas ({len(summary['critical_failures'])})\n")
        out.append("Casos 🔴 que falharam — prioridade máxima de revisão.\n")
        for j in summary["critical_failures"][:20]:
            cid = j["case_id"]
            run = summary["run_results"].get(cid, {})
            out.append(f"### {cid} · {j.get('block', '')}")
            out.append(f"**Input**: {run.get('input', '—')[:150]}")
            out.append(f"**Serena respondeu**: {run.get('actual_response', '—')[:200]}...")
            out.append(f"**Scores**: {j.get('scores', '—')}")
            if j.get("critical_failures"):
                out.append(f"**Critérios zerados**: {', '.join(j['critical_failures'])}")
            if j.get("observations"):
                out.append(f"**Observações**: {j['observations']}")
            out.append("")
        if len(summary["critical_failures"]) > 20:
            out.append(f"*...e mais {len(summary['critical_failures']) - 20} falhas críticas.*\n")

    # Comparação com baseline
    if comparison:
        out.append("\n---\n## Delta vs Baseline\n")
        r = comparison["regressions"]
        p = comparison["progressions"]
        sf = comparison["stable_fails"]

        if r:
            out.append(f"### 🔻 Regressões ({len(r)}) — passavam, agora falham\n")
            for cid, base, curr in r[:15]:
                out.append(
                    f"- **{cid}** [{severity_emoji(curr.get('severity'))}] — "
                    f"score {base.get('total', '?')} → {curr.get('total', '?')}"
                )
            out.append("")
        else:
            out.append("### Nenhuma regressão ✓\n")

        if p:
            out.append(f"### ✨ Progressões ({len(p)}) — falhavam, agora passam\n")
            for cid, base, curr in p[:15]:
                out.append(
                    f"- **{cid}** [{severity_emoji(curr.get('severity'))}] — "
                    f"score {base.get('total', '?')} → {curr.get('total', '?')}"
                )
            out.append("")

        if sf:
            out.append(f"### ⚠️ Falhas persistentes ({len(sf)})\n")
            for cid, curr in sf[:10]:
                out.append(f"- **{cid}** [{severity_emoji(curr.get('severity'))}] — {curr.get('verdict')}")
            out.append("")

    # Casos em Review (ambíguos)
    reviews = [j for j in summary["judgments"] if j["verdict"] == "review"]
    if reviews:
        out.append(f"\n## Casos em Review ({len(reviews)}) — humano decide\n")
        for j in reviews[:15]:
            out.append(
                f"- **{j['case_id']}** [{severity_emoji(j.get('severity'))}] — "
                f"total {j.get('total', '?')} — {j.get('observations', '')[:100]}"
            )
        out.append("")

    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file", help="results/judged_<timestamp>.json")
    parser.add_argument("--baseline", help="resultado anterior pra calcular delta")
    args = parser.parse_args()

    data = load_judged(args.input_file)
    summary = build_summary(data)

    comparison = None
    if args.baseline:
        baseline_data = load_judged(args.baseline)
        comparison = compare_with_baseline(data, baseline_data)

    model = data.get("judge_model", "?")
    markdown = render_markdown(summary, comparison, model=model)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"report_{timestamp}.md"
    out_path.write_text(markdown, encoding="utf-8")

    print(f"✓ Relatório: {out_path}")
    print(f"\n{'=' * 50}")
    print(f"RESUMO")
    print(f"{'=' * 50}")
    o = summary["overall"]
    print(f"Pass rate: {o['pass_rate'] * 100:.1f}% ({o['pass']}/{o['total']})")
    if summary["critical_failures"]:
        print(f"🔴 Falhas críticas: {len(summary['critical_failures'])}")
    if comparison:
        print(f"Regressões: {len(comparison['regressions'])}  |  Progressões: {len(comparison['progressions'])}")


if __name__ == "__main__":
    main()

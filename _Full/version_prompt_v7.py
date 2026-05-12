"""
version_prompt.py — versionamento automático do system prompt.

Uso:
    python version_prompt.py                    # salva versão atual + diff vs anterior
    python version_prompt.py --log              # lista versões salvas
    python version_prompt.py --diff v1 v2      # compara duas versões específicas
    python version_prompt.py --restore <ts>    # restaura versão anterior

Output:
    prompts/history/serena_YYYYMMDD_HHMMSS.txt
    prompts/history/CHANGELOG.md  (append)
"""

import sys
import shutil
import difflib
import argparse
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent
PROMPT_PATH = ROOT / "prompts" / "serena_system_prompt.txt"
HISTORY_DIR = ROOT / "prompts" / "history"


def ensure_history_dir():
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def list_versions():
    versions = sorted(HISTORY_DIR.glob("serena_*.txt"))
    return versions


def latest_version():
    versions = list_versions()
    return versions[-1] if versions else None


def save_version(message=None):
    ensure_history_dir()
    current = PROMPT_PATH.read_text(encoding="utf-8")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = HISTORY_DIR / f"serena_{ts}.txt"
    dest.write_text(current, encoding="utf-8")

    # Gera diff vs versão anterior
    prev = latest_version()
    diff_lines = []

    if prev and prev != dest:
        prev_text = prev.read_text(encoding="utf-8").splitlines(keepends=True)
        curr_text = current.splitlines(keepends=True)
        diff = list(difflib.unified_diff(
            prev_text, curr_text,
            fromfile=prev.name, tofile=dest.name, lineterm=""
        ))
        diff_lines = diff
        added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
        diff_summary = f"+{added} -{removed} linhas"
    else:
        diff_summary = "versão inicial"

    # Append no CHANGELOG
    changelog_path = HISTORY_DIR / "CHANGELOG.md"
    with open(changelog_path, "a", encoding="utf-8") as f:
        f.write(f"\n## {ts}\n")
        if message:
            f.write(f"**{message}**\n\n")
        f.write(f"Arquivo: `{dest.name}` ({diff_summary})\n")
        if diff_lines:
            f.write("\n```diff\n")
            f.write("".join(diff_lines[:80]))  # max 80 linhas de diff no changelog
            if len(diff_lines) > 80:
                f.write(f"\n... ({len(diff_lines) - 80} linhas omitidas)\n")
            f.write("```\n")

    print(f"✓ Versão salva: {dest.name}")
    print(f"  Diff: {diff_summary}")
    if message:
        print(f"  Mensagem: {message}")
    return dest


def show_log():
    versions = list_versions()
    if not versions:
        print("Nenhuma versão salva.")
        return

    changelog = HISTORY_DIR / "CHANGELOG.md"
    if changelog.exists():
        print(changelog.read_text(encoding="utf-8"))
    else:
        print(f"{len(versions)} versões:\n")
        for v in versions:
            size = v.stat().st_size
            print(f"  {v.name}  ({size} bytes)")


def diff_versions(v1_name, v2_name):
    """Compara duas versões por nome de arquivo (sem extensão OK)."""
    versions = {v.stem: v for v in list_versions()}

    def resolve(name):
        if name in versions:
            return versions[name]
        # Tenta por prefixo
        matches = [v for k, v in versions.items() if k.startswith(name)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise SystemExit(f"Ambíguo: {name} corresponde a {[m.name for m in matches]}")
        raise SystemExit(f"Versão não encontrada: {name}")

    p1 = resolve(v1_name)
    p2 = resolve(v2_name)

    t1 = p1.read_text(encoding="utf-8").splitlines(keepends=True)
    t2 = p2.read_text(encoding="utf-8").splitlines(keepends=True)

    diff = list(difflib.unified_diff(t1, t2, fromfile=p1.name, tofile=p2.name, lineterm=""))

    if not diff:
        print("Sem diferenças.")
    else:
        added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
        print(f"Diff {p1.name} → {p2.name}: +{added} -{removed} linhas\n")
        print("".join(diff))


def restore_version(ts):
    versions = {v.stem.replace("serena_", ""): v for v in list_versions()}
    target = None

    # Procura por timestamp exato ou prefixo
    for k, v in versions.items():
        if k == ts or k.startswith(ts):
            target = v
            break

    if not target:
        raise SystemExit(f"Versão não encontrada: {ts}")

    # Salva a atual antes de restaurar
    print(f"Salvando versão atual antes de restaurar...")
    save_version(message=f"auto-save antes de restaurar {target.name}")

    shutil.copy2(target, PROMPT_PATH)
    print(f"✓ Restaurado: {target.name} → {PROMPT_PATH.name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", action="store_true", help="Listar versões")
    parser.add_argument("--diff", nargs=2, metavar=("V1", "V2"), help="Comparar duas versões")
    parser.add_argument("--restore", metavar="TS", help="Restaurar versão anterior")
    parser.add_argument("-m", "--message", help="Mensagem pra descrever o que mudou")
    args = parser.parse_args()

    if args.log:
        show_log()
    elif args.diff:
        diff_versions(args.diff[0], args.diff[1])
    elif args.restore:
        restore_version(args.restore)
    else:
        save_version(message=args.message)


if __name__ == "__main__":
    main()

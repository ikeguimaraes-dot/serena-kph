"""
version_prompt.py — gerencia versões do serena_system_prompt.

Convenção:
  prompts/serena_system_prompt.txt        current (runner lê)
  prompts/serena_system_prompt_vN.txt     imutável (chmod 444)
  prompts/history/*.txt                   snapshots timestampados

Uso:
  python src/version_prompt.py save v10    # congela current como _v10.txt
  python src/version_prompt.py list        # lista versões + indica current
  python src/version_prompt.py diff v9 v10 # diff unificado entre duas versões
  python src/version_prompt.py current     # mostra qual v o current aponta
"""

import difflib
import hashlib
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts"
CURRENT = PROMPTS / "serena_system_prompt.txt"
HISTORY = PROMPTS / "history"
VPATTERN = re.compile(r"serena_system_prompt_v(\d+)\.txt$")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:10]


def _versions() -> list[Path]:
    found = [(int(m.group(1)), p) for p in PROMPTS.glob("serena_system_prompt_v*.txt")
             if (m := VPATTERN.search(p.name))]
    return [p for _, p in sorted(found)]


def _diff_summary(prev: Path, curr: Path) -> str:
    a = prev.read_text(encoding="utf-8").splitlines()
    b = curr.read_text(encoding="utf-8").splitlines()
    added = sum(1 for l in difflib.unified_diff(a, b, n=0)
                if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in difflib.unified_diff(a, b, n=0)
                  if l.startswith("-") and not l.startswith("---"))
    return f"+{added}/-{removed} lines vs {prev.name}"


def cmd_save(vtag: str) -> None:
    if not VPATTERN.search(f"serena_system_prompt_{vtag}.txt"):
        sys.exit(f"erro: tag precisa ser vN (ex: v10). recebido: {vtag!r}")
    target = PROMPTS / f"serena_system_prompt_{vtag}.txt"
    if target.exists():
        sys.exit(f"erro: {target.name} já existe. pra sobrescrever: chmod +w + remover + save.")
    if not CURRENT.exists():
        sys.exit(f"erro: {CURRENT} não encontrado.")

    HISTORY.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    hist = HISTORY / f"serena_system_prompt_{vtag}_{ts}.txt"
    shutil.copy2(CURRENT, hist)

    shutil.copy2(CURRENT, target)
    target.chmod(0o444)

    prevs = _versions()
    prevs = [p for p in prevs if p != target]
    summary = "first versioned save" if not prevs else _diff_summary(prevs[-1], CURRENT)

    print(f"📌 VERSION BUMP: {target.name} — {summary}")
    print(f"   sha current == {vtag}: {_sha(CURRENT)} == {_sha(target)}")
    print(f"   history: {hist.relative_to(ROOT)}")


def cmd_list() -> None:
    vs = _versions()
    if not vs:
        print("(nenhuma versão salva ainda)")
    cur_sha = _sha(CURRENT) if CURRENT.exists() else None
    for p in vs:
        locked = "🔒" if not os.access(p, os.W_OK) else "  "
        match = " ← current" if cur_sha and _sha(p) == cur_sha else ""
        print(f"  {locked} {p.name:40s} {p.stat().st_size:>6} B  sha {_sha(p)}{match}")
    if cur_sha and not any(_sha(p) == cur_sha for p in vs):
        print(f"     current drifted — {_sha(CURRENT)} (nenhuma v bate)")


def cmd_diff(a: str, b: str) -> None:
    pa = PROMPTS / f"serena_system_prompt_{a}.txt"
    pb = PROMPTS / f"serena_system_prompt_{b}.txt"
    if not pa.exists():
        sys.exit(f"não achou {pa.name}")
    if not pb.exists():
        sys.exit(f"não achou {pb.name}")
    for line in difflib.unified_diff(
        pa.read_text(encoding="utf-8").splitlines(keepends=True),
        pb.read_text(encoding="utf-8").splitlines(keepends=True),
        fromfile=pa.name,
        tofile=pb.name,
        n=3,
    ):
        sys.stdout.write(line)


def cmd_current() -> None:
    if not CURRENT.exists():
        sys.exit(f"não achou {CURRENT}")
    cur_sha = _sha(CURRENT)
    print(f"current sha: {cur_sha}")
    for p in _versions():
        if _sha(p) == cur_sha:
            lock = "🔒" if not os.access(p, os.W_OK) else "unlocked"
            print(f"aponta pra: {p.name} ({lock})")
            return
    print("current drifted — sem v correspondente. rode: version_prompt.py save vN")


USAGE = "uso: version_prompt.py [save vN | list | diff vA vB | current]"


def main() -> None:
    args = sys.argv[1:]
    if not args:
        sys.exit(USAGE)
    cmd, *rest = args
    if cmd == "save" and len(rest) == 1:
        cmd_save(rest[0])
    elif cmd == "list" and not rest:
        cmd_list()
    elif cmd == "diff" and len(rest) == 2:
        cmd_diff(*rest)
    elif cmd == "current" and not rest:
        cmd_current()
    else:
        sys.exit(USAGE)


if __name__ == "__main__":
    main()

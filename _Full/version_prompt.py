"""
version_prompt.py — controle de versão do system prompt da Serena.

Comandos:
    python src/version_prompt.py list              # lista versões salvas
    python src/version_prompt.py diff v9 v10       # diff entre duas versões
    python src/version_prompt.py save v10          # salva current como v10 + atualiza VERSION
    python src/version_prompt.py current           # mostra qual versão o current aponta

Convenção de arquivos:
    prompts/serena_system_prompt.txt       → "current" (lido pelo runner)
    prompts/serena_system_prompt_v<N>.txt  → imutável por versão
    VERSION                                → versão ativa
"""

import sys
import difflib
from pathlib import Path

ROOT = Path(__file__).parent.parent
PROMPTS = ROOT / "prompts"
CURRENT = PROMPTS / "serena_system_prompt.txt"
VERSION_FILE = ROOT / "VERSION"


def versions():
    return sorted(PROMPTS.glob("serena_system_prompt_v*.txt"))


def resolve(name):
    """Aceita 'v9', '9', ou nome completo de arquivo."""
    name = name.strip()
    if not name.startswith("v"):
        name = "v" + name
    target = PROMPTS / f"serena_system_prompt_{name}.txt"
    if not target.exists():
        raise SystemExit(f"Versão não encontrada: {target.name}")
    return target


def cmd_list():
    vs = versions()
    if not vs:
        print("Nenhuma versão salva.")
        return
    current_text = CURRENT.read_text() if CURRENT.exists() else ""
    for v in vs:
        marker = " ← current" if v.read_text() == current_text else ""
        print(f"  {v.name}{marker}")


def cmd_diff(a, b):
    ta = resolve(a).read_text().splitlines(keepends=True)
    tb = resolve(b).read_text().splitlines(keepends=True)
    diff = list(difflib.unified_diff(ta, tb, fromfile=a, tofile=b, lineterm=""))
    if not diff:
        print("Sem diferenças.")
        return
    added   = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
    print(f"Diff {a} → {b}: +{added} -{removed} linhas\n")
    print("".join(diff))


def cmd_save(name):
    if not name.startswith("v"):
        name = "v" + name
    dest = PROMPTS / f"serena_system_prompt_{name}.txt"
    if dest.exists():
        raise SystemExit(f"Já existe: {dest.name} — versões são imutáveis.")
    if not CURRENT.exists():
        raise SystemExit(f"Current não encontrado: {CURRENT}")
    dest.write_text(CURRENT.read_text(), encoding="utf-8")

    # Atualiza VERSION
    v_text = VERSION_FILE.read_text() if VERSION_FILE.exists() else ""
    lines = [l for l in v_text.splitlines() if not l.startswith("version:")]
    lines.insert(0, f"version: {name}")
    VERSION_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"✓ Salvo: {dest.name}")
    print(f"✓ VERSION → {name}")
    print(f"\n📌 VERSION BUMP: {dest.name} — <descreva o diff em 1 linha aqui>")


def cmd_current():
    if not CURRENT.exists():
        print("current não encontrado.")
        return
    current_text = CURRENT.read_text()
    for v in versions():
        if v.read_text() == current_text:
            print(f"current = {v.name}")
            return
    # Lê versão do VERSION file
    if VERSION_FILE.exists():
        for line in VERSION_FILE.read_text().splitlines():
            if line.startswith("version:"):
                print(f"current ≈ {line.split(':')[1].strip()} (por VERSION file, conteúdo modificado)")
                return
    print("current não corresponde a nenhuma versão salva.")


COMMANDS = {"list": cmd_list, "diff": cmd_diff, "save": cmd_save, "current": cmd_current}

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] not in COMMANDS:
        print(__doc__)
        sys.exit(0)
    cmd = args[0]
    params = args[1:]
    if cmd == "diff" and len(params) == 2:
        cmd_diff(*params)
    elif cmd == "save" and len(params) == 1:
        cmd_save(params[0])
    elif cmd in ("list", "current") and not params:
        COMMANDS[cmd]()
    else:
        print(f"Uso incorreto para '{cmd}'. Veja --help.")
        print(__doc__)

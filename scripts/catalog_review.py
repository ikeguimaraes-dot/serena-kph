#!/usr/bin/env python3
"""Build local catalog review artifacts. Never connects to or writes a database.

Source prices and names are preserved. Raw Tagme amounts are displayed separately
in cents; no option is silently selected as the approved commercial offer.
"""

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path


def text(value):
    if isinstance(value, dict):
        return (value.get("pt") or value.get("en") or "").strip()
    return str(value or "").strip()


def money(value):
    return "" if value is None else format(Decimal(str(value)), ".2f").replace(".", ",")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def raw_items(sections):
    def visit(node, pointer, parents):
        path = parents + [text(node.get("name"))]
        for index, item in enumerate(node.get("menuItems", [])):
            yield path, item, f"{pointer}/menuItems/{index}"
        for index, child in enumerate(node.get("menus", [])):
            if isinstance(child, dict):
                yield from visit(child, f"{pointer}/menus/{index}", path)

    for index, section in enumerate(sections):
        yield from visit(section, f"/body/{index}", [])


def write_csv(path, rows, columns):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    target = args.output.resolve()
    if source == target or source in target.parents:
        raise SystemExit("Review output must be separate from the source directory.")
    if any((target / name).exists() for name in ("meet_277_revisao.csv", "meet_opcoes_revisao.csv", "manifesto.json")):
        raise SystemExit("Review artifacts already exist. Choose a new output directory to preserve human review.")

    names = [
        "cardapio_meet_and_eat.csv", "cardapio_meet_and_eat.json",
        "raw_meet_and_eat_5.json", "cardapio_freneze.csv",
        "cardapio_freneze.json", "tela_freneze.png",
    ]
    snapshots = {name: sha(source / name) for name in names}
    raw = json.loads((source / "raw_meet_and_eat_5.json").read_text())
    exported = json.loads((source / "cardapio_meet_and_eat.json").read_text())
    with (source / "cardapio_meet_and_eat.csv").open(encoding="utf-8-sig", newline="") as handle:
        csv_source = list(csv.DictReader(handle))
    if len(exported) != len(csv_source) or any(
        ("" if item[column] is None else str(item[column])) != row[column]
        for item, row in zip(exported, csv_source) for column in item
    ):
        raise SystemExit("Source CSV and JSON differ; review stopped.")

    raw_by_key = {}
    for path, node, pointer in raw_items(raw["body"]):
        key = (path[-1], text(node.get("name")))
        if key in raw_by_key:
            raise SystemExit(f"Duplicate raw category/name: {key}")
        raw_by_key[key] = (path, node, pointer)
    if len(raw_by_key) != len(exported):
        raise SystemExit("Raw and normalized catalog counts differ.")

    name_counts = Counter(item["nome"].casefold().strip() for item in exported)
    review = []
    option_review = []
    flags_count = Counter()
    for item in exported:
        if item["restaurant_id"] != "meet_and_eat":
            raise SystemExit("Unexpected restaurant_id in input.")
        path, node, pointer = raw_by_key[(item["categoria"], item["nome"])]
        flags = []
        options = node.get("options", [])
        active = [option for option in options if not option.get("disabled")]
        positive = [option for option in active if isinstance(option.get("price"), (int, float)) and option["price"] > 0]
        prices = {option["price"] for option in positive}
        direct = node.get("price")
        if direct is None:
            flags.append("PRECO_EM_OPCAO")
            if len(positive) != 1:
                flags.append("ORIGEM_PRECO_AMBIGUA")
            cents = min(prices) if prices else None
            origin = "opcao ativa unica" if len(positive) == 1 else "revisar opcoes"
        else:
            cents, origin = direct, "price direto"
        if cents is None or Decimal(str(cents)) / 100 != Decimal(str(item["preco"])):
            flags.append("DIVERGENCIA_PRECO")
        if len(prices) > 1:
            flags.append("VARIANTES_COM_PRECOS_DISTINTOS")
        if any(option.get("sons") for option in options):
            flags.append("ADICIONAIS_OU_SABORES")
        if any(option.get("sons") and all(child.get("disabled") for child in option["sons"]) for option in active):
            flags.append("TODOS_FILHOS_DA_OPCAO_DESATIVADOS")
        if any(option.get("price") == 0 and not text(option.get("name")) and not text(option.get("volume")) for option in active):
            flags.append("OPCAO_ZERO_SEM_ROTULO")
        if not item["descricao"].strip():
            flags.append("DESCRICAO_AUSENTE")
        if name_counts[item["nome"].casefold().strip()] > 1:
            flags.append("NOME_REPETIDO_EM_OUTRA_CATEGORIA")
        if any(text(option.get("volume")) for option in active):
            flags.append("ROTULO_DE_OPCAO_FORA_DO_CSV_ORIGINAL")
        flags_count.update(flags)

        option_summaries = []
        for index, option in enumerate(options):
            label = text(option.get("name")) or text(option.get("volume")) or "[sem rotulo]"
            option_price = option.get("price")
            value = money(Decimal(str(option_price)) / 100) if option_price is not None else "[sem preco proprio]"
            summary = f"{label}: {value}" + (" (desativada)" if option.get("disabled") else "")
            children = []
            entries = [(option, f"{pointer}/options/{index}", "opcao", label)]
            for child_index, child in enumerate(option.get("sons", [])):
                child_label = text(child.get("name")) or "[sem rotulo]"
                child_price = child.get("price")
                child_value = money(Decimal(str(child_price)) / 100) if child_price is not None else "[sem preco]"
                children.append(f"{child_label}: {child_value}" + (" (desativado)" if child.get("disabled") else ""))
                entries.append((child, f"{pointer}/options/{index}/sons/{child_index}", "filho", label + " / " + child_label))
            if children:
                summary += " -> " + ", ".join(children)
            option_summaries.append(summary)
            for entry, entry_pointer, level, entry_label in entries:
                price = entry.get("price")
                option_review.append({
                    "ordem_item": item["ordem"], "categoria": item["categoria"],
                    "nome_item": item["nome"], "nivel": level, "rotulo_original": entry_label,
                    "preco_bruto_centavos": "" if price is None else price,
                    "preco_reais": "" if price is None else money(Decimal(str(price)) / 100),
                    "desativado_na_fonte": str(bool(entry.get("disabled"))).lower(),
                    "source_id": entry.get("_id", ""), "json_pointer": entry_pointer,
                    "status_revisao": "PENDENTE", "observacoes_ike": "",
                })
        review.append({
            "ordem": item["ordem"], "restaurant_id": item["restaurant_id"],
            "categoria": item["categoria"], "nome": item["nome"], "descricao": item["descricao"],
            "preco_exportado_reais": money(item["preco"]),
            "disponivel_no_csv_original": item["disponivel"],
            "origem_preco_exportado": origin,
            "preco_bruto_origem_centavos": "" if cents is None else cents,
            "caminho_categorias": " > ".join(path), "source_id": node.get("_id", ""),
            "json_pointer": pointer, "opcoes_e_adicionais": " | ".join(option_summaries),
            "sinalizacoes": " | ".join(flags), "status_revisao": "PENDENTE",
            "observacoes_ike": "",
        })

    target.mkdir(parents=True, exist_ok=True)
    write_csv(target / "meet_277_revisao.csv", review, list(review[0]))
    write_csv(target / "meet_opcoes_revisao.csv", option_review, list(option_review[0]))
    freneze = json.loads((source / "cardapio_freneze.json").read_text())
    if any(sha(source / name) != digest for name, digest in snapshots.items()):
        raise SystemExit("Source files changed during review generation.")
    manifest = {
        "estado": "REVISAO_PENDENTE_CARGA_NAO_AUTORIZADA", "restaurant_id": "meet_and_eat",
        "fontes_preservadas": True, "source_url": raw["url"],
        "fontes": [{"arquivo": name, "sha256": digest, "bytes": (source / name).stat().st_size} for name, digest in snapshots.items()],
        "contagens": {"itens_meet": len(review), "categorias_meet": len({row["categoria"] for row in review}),
                      "linhas_opcoes_e_filhos": len(option_review), "itens_freneze": len(freneze),
                      "sem_preco_meet": sum(row["preco"] is None for row in exported),
                      "preco_zero_ou_negativo_meet": sum(row["preco"] is not None and row["preco"] <= 0 for row in exported)},
        "sinalizacoes_por_item": dict(sorted(flags_count.items())),
        "artefatos": [{"arquivo": name, "sha256": sha(target / name)} for name in ("meet_277_revisao.csv", "meet_opcoes_revisao.csv")],
        "limites": ["Disponibilidade comercial nao validada.", "Frêneze: extracao nao concluida; JSON vazio nao prova catalogo vazio.",
                    "Madonna: sem catalogo ou URL valida nos arquivos locais examinados.",
                    "Aprovacao item a item de Ike obrigatoria; este script nao autoriza nem faz carga."],
    }
    (target / "manifesto.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"contagens": manifest["contagens"], "sinalizacoes": manifest["sinalizacoes_por_item"], "fontes_preservadas": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()

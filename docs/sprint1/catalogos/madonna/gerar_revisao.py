#!/usr/bin/env python3
"""Generate offline review CSVs from the immutable public Tagme response.

No HTTP, database, or production mutations. Existing reviews are never replaced.
Prices remain source values; BRL conversion is the published formatFromCents /100.
"""
import argparse
import csv
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path


def pt(value):
    return value.get("pt", "") if isinstance(value, dict) else str(value or "")


def amount(value):
    return "" if value is None else format(Decimal(str(value)) / 100, ".2f").replace(".", ",")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def walk(roots):
    def visit(node, pointer, categories, category_ids, disabled):
        categories = categories + [pt(node.get("name"))]
        category_ids = category_ids + [node.get("_id", "")]
        disabled = disabled or bool(node.get("disabled"))
        for index, item in enumerate(node.get("menuItems", [])):
            yield item, f"{pointer}/menuItems/{index}", categories, category_ids, disabled
        for index, child in enumerate(node.get("menus", [])):
            yield from visit(child, f"{pointer}/menus/{index}", categories, category_ids, disabled)
    for index, node in enumerate(roots):
        yield from visit(node, f"/{index}", [], [], False)


def label(option):
    return (pt(option.get("name")) or pt(option.get("volume"))
            or pt(option.get("wineVolume", {}).get("name"))
            or str(option.get("wineVolume", {}).get("value", "")))


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).with_name("raw_catalogo.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    outputs = ["madonna_253_revisao.csv", "madonna_223_opcoes_revisao.csv", "manifesto.json"]
    if any((args.output / name).exists() for name in outputs):
        raise SystemExit("Choose a new output directory; existing human reviews must remain intact.")
    before = digest(args.source)
    raw = json.loads(args.source.read_text())
    if not isinstance(raw, list) or any(root.get("currency") != "R$" for root in raw):
        raise SystemExit("Unexpected Tagme root format or currency.")
    records = list(walk(raw))
    ids = [item["_id"] for item, *_ in records]
    if len(ids) != len(set(ids)):
        raise SystemExit("Duplicate source IDs require explicit review.")
    names = Counter(pt(item.get("name")).strip().casefold() for item, *_ in records)
    rows, option_rows, flags_count = [], [], Counter()
    for order, (item, pointer, categories, category_ids, category_disabled) in enumerate(records, 1):
        options = item.get("options", [])
        active = [opt for opt in options if not opt.get("disabled")]
        direct = item.get("price")
        # A unique option is exposed as its own variant, never selected among alternatives.
        cents = direct if direct is not None else active[0].get("price") if len(active) == 1 else None
        origin = "price direto" if direct is not None else "opcao ativa unica" if len(active) == 1 else "sem preco univoco"
        price_pointer = pointer + "/price" if direct is not None else pointer + f"/options/{options.index(active[0])}/price" if len(active) == 1 else ""
        flags = []
        if direct is None:
            flags.append("PRECO_EM_OPCAO")
        if cents is None:
            flags.append("PRECO_AUSENTE_OU_AMBIGUO")
        elif Decimal(str(cents)) <= 0:
            flags.append("PRECO_ZERO_OU_NEGATIVO_BLOQUEAR_OFERTA")
        elif Decimal(str(cents)) % 100:
            flags.append("PRECO_COM_CENTAVOS_CONFIRMAR_SE_INTENCIONAL")
        if names[pt(item.get("name")).strip().casefold()] > 1:
            flags.append("NOME_REPETIDO_PRESERVAR_CATEGORIA_E_VOLUME")
        if not pt(item.get("descript")).strip():
            flags.append("DESCRICAO_PT_AUSENTE")
        if category_disabled or item.get("disabled"):
            flags.append("DESATIVADO_NA_FONTE")
        if len(active) > 1:
            flags.append("VARIANTES_MULTIPLAS")
        if item.get("promoPriceEnabled") or any(o.get("promoPriceEnabled") for o in active):
            flags.append("PROMOCAO_ATIVA_REVISAR")
        if any(o.get("sons") for o in options) or item.get("subitems"):
            flags.append("ADICIONAIS_PRESERVAR_ESTRUTURA")
        if any(direct is not None and o.get("price") != direct for o in active):
            flags.append("OPCAO_DIFERE_PRECO_DIRETO")
        flags_count.update(flags)
        summaries = []
        for index, option in enumerate(options):
            original_label = label(option)
            summaries.append(f"{original_label or '[sem rotulo]'}: R$ {amount(option.get('price'))}")
            option_rows.append({
                "ordem_item": order, "restaurant_id": "madonna_cucina", "categoria": categories[-1],
                "nome_item": pt(item.get("name")), "source_item_id": item["_id"],
                "source_option_id": option.get("_id", ""), "rotulo_original": original_label,
                "preco_bruto_centavos": option.get("price", ""), "preco_reais": amount(option.get("price")),
                "promo_preco_bruto_centavos": option.get("promoPrice", ""),
                "promo_ativa": str(bool(option.get("promoPriceEnabled"))).lower(),
                "desativada": str(bool(option.get("disabled"))).lower(),
                "min_original": option.get("min", ""), "modifier_original": option.get("modifier", ""),
                "json_pointer": f"{pointer}/options/{index}",
                "estado_fonte": "FONTE_VERIFICADA", "status_revisao_humana": "PENDENTE", "observacoes_ike": "",
            })
        rows.append({
            "ordem": order, "restaurant_id": "madonna_cucina", "categoria": categories[-1],
            "caminho_categorias": " > ".join(categories), "source_category_ids": " > ".join(category_ids),
            "source_id": item["_id"], "tipo_original": item.get("type", ""),
            "nome": pt(item.get("name")), "descricao": pt(item.get("descript")),
            "preco_direto_centavos": "" if direct is None else direct,
            "preco_fonte_centavos": "" if cents is None else cents, "preco_fonte_reais": amount(cents),
            "origem_preco": origin, "preco_json_pointer": price_pointer,
            "json_pointer": pointer, "opcoes": " | ".join(summaries),
            "sinalizacoes": " | ".join(flags), "estado_fonte": "FONTE_VERIFICADA",
            "status_revisao_humana": "PENDENTE", "observacoes_ike": "",
        })
    if len(rows) != 253 or len(option_rows) != 223:
        raise SystemExit("Snapshot count changed; rename outputs and review before generating.")
    if before != digest(args.source):
        raise SystemExit("Source changed during generation.")
    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / outputs[0], rows)
    write_csv(args.output / outputs[1], option_rows)
    manifest = {
        "restaurant_id": "madonna_cucina", "estado_fonte": "FONTE_VERIFICADA",
        "status_revisao_humana": "PENDENTE", "alterou_banco_ou_prompt": False,
        "fonte": {"arquivo": args.source.name, "sha256": before, "bytes": args.source.stat().st_size,
                  "formato": "Tagme: JSON array; ponteiros iniciam em /0, /1, /2",
                  "unidade": "centavos de BRL, conversao exata /100"},
        "contagens": {"itens": len(rows), "ids_unicos": len(set(ids)), "categorias_com_itens": len({tuple(c) for _, _, c, _, _ in records}),
                      "raizes": len(raw), "opcoes": len(option_rows), "filhos_sons": sum(len(o.get("sons", [])) for it, *_ in records for o in it.get("options", [])),
                      "preco_direto": sum(it.get("price") is not None for it, *_ in records),
                      "preco_em_opcao_unica": sum(it.get("price") is None and len(it.get("options", [])) == 1 for it, *_ in records)},
        "sinalizacoes": dict(flags_count),
        "arquivos": [{"arquivo": name, "sha256": digest(args.output / name), "bytes": (args.output / name).stat().st_size} for name in outputs[:2]],
        "regra": "FONTE_VERIFICADA significa origem e integridade auditadas, não aprovação humana. Não arredondar, inventar ou promover preço zero para oferta comercial.",
    }
    (args.output / outputs[2]).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(manifest["contagens"], ensure_ascii=False))


if __name__ == "__main__":
    main()

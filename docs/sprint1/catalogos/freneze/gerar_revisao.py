#!/usr/bin/env python3
"""Offline Frêneze review generator. No network or database calls.

Amounts in these Shopfood payloads are BRL directly, as established by the
public app's currency formatter saved in evidencia_origem_e_unidade.json.
Do not reuse the Tagme centavos conversion from the Meet extraction.
"""

import csv
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def money(value):
    return "" if value is None else format(Decimal(str(value)), ".2f").replace(".", ",")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def traverse(category, pointer, parents):
    path = parents + [category["name"]]
    for index, product in enumerate(category["products"]):
        yield path, product, f"{pointer}/products/{index}"
    for index, child in enumerate(category["children"]):
        yield from traverse(child, f"{pointer}/children/{index}", path)


def write_csv(name, rows):
    with (ROOT / name).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def main():
    outputs = ["freneze_210_revisao.csv", "freneze_146_componentes_revisao.csv", "manifesto.json"]
    if any((ROOT / name).exists() for name in outputs):
        raise SystemExit("Review files already exist; preserve human annotations and create a new version separately.")
    raw = json.loads((ROOT / "raw_catalogo.json").read_text())
    captured = json.loads((ROOT / "captura_catalogo.json").read_text())
    if sha(ROOT / "raw_catalogo.json") != captured["sha256"]:
        raise SystemExit("Raw catalog hash differs from capture metadata.")
    details = json.loads((ROOT / "raw_detalhes.json").read_text())["responses"]
    details_by_id = {row["product_id"]: (index, row) for index, row in enumerate(details)}
    if len(details_by_id) != len(details) or any(row.get("http_status") != 200 for row in details):
        raise SystemExit("Composite details are missing, duplicated or unsuccessful.")
    entries = [entry for index, category in enumerate(raw) for entry in traverse(category, f"/{index}", [])]
    if len({product["id"] for _, product, _ in entries}) != len(entries):
        raise SystemExit("Repeated product source IDs require explicit review before generation.")
    names = Counter(product["name"].strip().casefold() for _, product, _ in entries)
    review = []
    components = []
    flags_count = Counter()
    step_count = 0
    for order, (categories, product, pointer) in enumerate(entries, 1):
        flags = []
        price = None
        price_origin = ""
        price_pointer = ""
        price_file = ""
        summaries = []
        detail_index = None
        if product["type"] == 1:
            price = product["price"]
            price_origin = "price do produto simples"
            price_file, price_pointer = "raw_catalogo.json", pointer + "/price"
        elif product["type"] == 9:
            detail_index, response = details_by_id[product["id"]]
            detail = response["body"]["product"]
            if detail["id"] != product["id"]:
                raise SystemExit("Product identity mismatch in details.")
            steps = detail["product_composite_steps"]
            step_count += len(steps)
            all_components = [component for step in steps for component in step["complements"]]
            if len(all_components) == 1 and all_components[0]["chargeable"] and all_components[0]["active"]:
                component = all_components[0]
                price = component["price"]
                price_origin = "preco da unica variante cobrada e ativa"
                flags.append("VARIANTE_UNICA_PRESERVAR_ROTULO")
                if Decimal(str(price)) != Decimal(str(product["price"])):
                    flags.append("DIVERGENCIA_PRECO_RESUMO_VARIANTE")
            elif Decimal(str(product.get("default_price") or 0)) > 0:
                price = product["default_price"]
                price_origin = "default_price do composto, exibido pelo componente publico"
                price_file, price_pointer = "raw_catalogo.json", pointer + "/default_price"
                flags.append("COMPOSTO_COM_ETAPAS_PRECO_DEFAULT")
            else:
                flags.append("PRECO_SEM_REFERENCIA_UNIVOCA")
            for step_index, step in enumerate(steps):
                for component_index, component in enumerate(step["complements"]):
                    component_pointer = f"/responses/{detail_index}/body/product/product_composite_steps/{step_index}/complements/{component_index}"
                    if len(all_components) == 1 and price is not None:
                        price_file, price_pointer = "raw_detalhes.json", component_pointer + "/price"
                    treatment = "COBRADO_NA_FONTE" if component["chargeable"] else "SEM_COBRANCA_SEPARADA_NA_FONTE"
                    summaries.append(f"{step['name']} > {component['name']}: {money(component['price'])} ({treatment})")
                    components.append({
                        "ordem_item": order, "restaurant_id": "freneze", "source_product_id": product["id"],
                        "categoria": " > ".join(categories), "produto": product["name"],
                        "source_step_id": step["id"], "etapa": step["name"],
                        "descricao_etapa": step.get("description") or "", "tipo_etapa": step["type"],
                        "etapa_obrigatoria": str(step["required"]).lower(),
                        "quantidade_minima_etapa": step["minimum_quantity"], "quantidade_etapa": step["quantity"],
                        "source_component_id": component["id"], "source_variant_id": component["complementable_id"],
                        "nome_variante_componente": component["name"], "descricao": component.get("description") or "",
                        "preco_reais": money(component["price"]), "preco_bruto_api": component["price"],
                        "tratamento_preco": treatment, "ativo_na_fonte": component["active"],
                        "quantidade_maxima_componente": component.get("max_quantity"),
                        "source_file": "raw_detalhes.json", "json_pointer": component_pointer,
                        "status_revisao": "PENDENTE", "observacoes_ike": "",
                    })
        else:
            flags.append("TIPO_PRODUTO_NAO_TRATADO")
        if price is None or Decimal(str(price)) <= 0:
            flags.append("PRECO_A_CONFIRMAR")
        if not product["description"].strip():
            flags.append("DESCRICAO_AUSENTE")
        if names[product["name"].strip().casefold()] > 1:
            flags.append("NOME_REPETIDO_OUTRA_CATEGORIA")
        if not product["active"] or not product["visible"]:
            flags.append("INDISPONIVEL_OU_OCULTO_NA_FONTE")
        flags_count.update(flags)
        review.append({
            "ordem": order, "restaurant_id": "freneze", "categoria": categories[-1],
            "caminho_categorias": " > ".join(categories), "nome": product["name"],
            "descricao": product["description"], "preco_referencia_reais": money(price),
            "origem_preco_referencia": price_origin, "preco_source_file": price_file,
            "preco_json_pointer": price_pointer, "price_bruto_api": product.get("price"),
            "default_price_bruto_api": product.get("default_price"),
            "display_default_price_na_fonte": str(product.get("display_default_price")).lower(),
            "tipo_produto_api": product["type"], "ativo_na_fonte": str(product["active"]).lower(),
            "visivel_na_fonte": str(product["visible"]).lower(), "source_id": product["id"],
            "json_pointer": pointer, "variantes_e_componentes": " | ".join(summaries),
            "sinalizacoes": " | ".join(flags), "status_revisao": "PENDENTE", "observacoes_ike": "",
        })
    if len(review) != 210 or len(components) != 146:
        raise SystemExit("Snapshot differs from this review version; check changes before generating.")
    write_csv(outputs[0], review)
    write_csv(outputs[1], components)
    sources = ["raw_catalogo.json", "raw_detalhes.json", "captura_catalogo.json", "evidencia_origem_e_unidade.json", "tentativa_http.json"]
    manifest = {
        "estado": "EXTRAIDO_REVISAO_PENDENTE_CARGA_NAO_AUTORIZADA", "restaurant_id": "freneze",
        "captured_at_utc": captured["captured_at_utc"], "source_url": captured["source_url"],
        "authorization_used": False, "cookies_used": False,
        "unidade_monetaria": "BRL, conforme formatador e uso direto dos campos no JavaScript publico",
        "contagens": {"produtos": len(review), "categorias_com_produtos": len({tuple(path) for path, _, _ in entries}),
                      "produtos_simples": sum(product["type"] == 1 for _, product, _ in entries),
                      "produtos_compostos": len(details), "etapas": step_count, "variantes_componentes": len(components),
                      "componentes_cobrados": sum(row["tratamento_preco"] == "COBRADO_NA_FONTE" for row in components),
                      "componentes_sem_cobranca_separada": sum(row["tratamento_preco"] == "SEM_COBRANCA_SEPARADA_NA_FONTE" for row in components)},
        "sinalizacoes": dict(sorted(flags_count.items())),
        "fontes": [{"arquivo": name, "sha256": sha(ROOT / name), "bytes": (ROOT / name).stat().st_size} for name in sources],
        "artefatos": [{"arquivo": name, "sha256": sha(ROOT / name)} for name in outputs[:2]],
        "limites": ["Nenhum item aprovado ou importado.", "Estado comercial deve ser confirmado pela operacao.",
                    "Componentes sem cobranca separada nao sao itens gratuitos.", "Nomes/unidades/volumes nao foram inventados ou normalizados.",
                    "O pacote Meet permanece separado e inalterado."],
    }
    (ROOT / "manifesto.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"contagens": manifest["contagens"], "sinalizacoes": manifest["sinalizacoes"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

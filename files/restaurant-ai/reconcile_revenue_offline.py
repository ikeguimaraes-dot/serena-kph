"""Offline, evidence-based cash reconciliation. Standard library only; no app imports.

Amounts are observed BRL cash movements, never estimated sales or incremental revenue.
Inputs stay local. Output contains aggregates and row numbers, not customer identifiers.
"""
import argparse
import csv
import hashlib
import io
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path
from zoneinfo import ZoneInfo

VERSION = "serena-cash-reconciliation-v1"
INPUT_VERSION = "serena-reconciliation-input-v1"
TZ = ZoneInfo("America/Sao_Paulo")
HEADERS = ("transaction_id", "restaurant_id", "reservation_id", "order_id", "amount_brl", "occurred_at", "evidence_ref")
PHONE = re.compile(r"\+[1-9][0-9]{6,14}\Z")
MONEY = re.compile(r"-?(?:0|[1-9][0-9]{0,12})(?:\.[0-9]{1,2})?\Z")
BUCKETS = ("conciliado_atribuicao_assistida", "conciliado_sem_interacao_elegivel", "conciliado_atribuicao_desconhecida", "sem_vinculo_operacional", "nao_conciliado")


class ContractError(ValueError):
    """Only fixed codes and numeric positions may be exposed in an error."""


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _stamp(value):
    try:
        parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _amount(value):
    if not isinstance(value, str) or not MONEY.fullmatch(value.strip()):
        return None
    return Decimal(value.strip())


def _money(value):
    return format(value.copy_abs() if value.is_zero() else value, ".2f")


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def load_operations(raw):
    try:
        return json.loads(raw, object_pairs_hook=_json_object)
    except (UnicodeError, json.JSONDecodeError):
        raise ContractError("INVALID_OPERATIONAL_JSON") from None


def load_receipts(raw):
    try:
        reader = csv.DictReader(io.StringIO(raw), strict=True)
        if tuple(reader.fieldnames or ()) != HEADERS:
            raise ContractError("INVALID_RECEIPT_HEADERS")
        rows = list(reader)
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise ContractError("INVALID_RECEIPT_COLUMNS")
        return rows
    except csv.Error:
        raise ContractError("INVALID_RECEIPT_CSV") from None


def _source(meta, start, end, *, coverage):
    meta = meta if isinstance(meta, dict) else {}
    as_of = _stamp(meta.get("as_of"))
    first, last = _stamp(meta.get("window_start")), _stamp(meta.get("window_end"))
    source_ref = _text(meta.get("source_ref"))
    valid = meta.get("complete") is True and bool(source_ref) and as_of is not None and as_of >= end
    if coverage:
        valid = valid and first is not None and last is not None and first <= start and last >= end
    return {
        "declarada_completa": meta.get("complete") if isinstance(meta.get("complete"), bool) else None,
        "cobre_recorte": bool(valid),
        "source_ref_sha256": hashlib.sha256(source_ref.encode()).hexdigest() if source_ref else None,
        "as_of": as_of.isoformat() if as_of else None,
        "window_start": first.isoformat() if first else None,
        "window_end": last.isoformat() if last else None,
    }


def _assert_tenant(row, restaurant_id, source, position):
    rid = _text(row.get("restaurant_id"))
    if rid and rid != restaurant_id:
        raise ContractError(f"CROSS_TENANT_{source}_{position}")


def reconcile(operations, receipts, *, restaurant_id, start, end):
    """Reconcile one unit, start inclusive/end exclusive local dates.

    Financial totals are null unless sources close the period and identity/linkage
    checks succeed. Observed partial sums are explicitly separate. A valid receipt
    can reference any current reservation/order status: money is not inferred from it.
    """
    restaurant_id = _text(restaurant_id)
    if not restaurant_id or not isinstance(start, date) or not isinstance(end, date) or not start < end:
        raise ContractError("INVALID_UNIT_OR_PERIOD")
    if not isinstance(operations, dict) or operations.get("schema_version") != INPUT_VERSION:
        raise ContractError("INVALID_OPERATIONAL_SCHEMA")
    if operations.get("restaurant_id") != restaurant_id:
        raise ContractError("CROSS_TENANT_MANIFEST")
    entities = operations.get("entities")
    interactions = operations.get("interactions")
    if not isinstance(entities, list) or not isinstance(interactions, list) or not isinstance(receipts, list):
        raise ContractError("INVALID_INPUT_COLLECTIONS")
    if any(not isinstance(row, dict) for row in entities + interactions + receipts):
        raise ContractError("INVALID_INPUT_ROW")
    first = datetime.combine(start, time.min, tzinfo=TZ).astimezone(timezone.utc)
    last = datetime.combine(end, time.min, tzinfo=TZ).astimezone(timezone.utc)
    diagnostics = []

    def issue(source, position, code):
        diagnostics.append({"source": source, "row": position, "code": code})

    # Never silently filter other units or resolve duplicated transaction identities.
    for source, rows in (("ENTITIES", entities), ("INTERACTIONS", interactions), ("RECEIPTS", receipts)):
        seen = set()
        for position, row in enumerate(rows, 1):
            _assert_tenant(row, restaurant_id, source, position)
            identity = _text(row.get("transaction_id" if source == "RECEIPTS" else "id"))
            key = (_text(row.get("kind")), identity) if source == "ENTITIES" else identity
            if identity and key in seen:
                raise ContractError(f"DUPLICATE_{source}_IDENTITY_{position}")
            if identity:
                seen.add(key)

    entity_map = {}
    for position, row in enumerate(entities, 1):
        kind, identity = _text(row.get("kind")), _text(row.get("id"))
        if kind not in ("reservation", "order") or not identity or row.get("restaurant_id") != restaurant_id or not _text(row.get("evidence_ref")):
            issue("entities", position, "INVALID_ENTITY_IDENTITY_OR_EVIDENCE")
            continue
        entity_map[(kind, identity)] = row

    interaction_map = defaultdict(list)
    for position, row in enumerate(interactions, 1):
        stamp, phone = _stamp(row.get("occurred_at")), _text(row.get("customer_phone"))
        if (not _text(row.get("id")) or row.get("restaurant_id") != restaurant_id or not stamp
                or not PHONE.fullmatch(phone) or not _text(row.get("evidence_ref"))
                or not isinstance(row.get("agent_assisted"), bool)):
            issue("interactions", position, "INVALID_INTERACTION_IDENTITY_TIME_OR_EVIDENCE")
            continue
        interaction_map[phone].append((stamp, _text(row["id"]), row))
    for rows in interaction_map.values():
        rows.sort(key=lambda item: (item[0], item[1]))
    interactions_valid = not any(item["source"] == "interactions" for item in diagnostics)

    sources = operations.get("sources") if isinstance(operations.get("sources"), dict) else {}
    source_status = {
        "receipts": _source(sources.get("receipts"), first, last, coverage=True),
        "entities": _source(sources.get("entities"), first, last, coverage=False),
    }
    sums = {key: Decimal("0.00") for key in BUCKETS}
    counts, status_counts = Counter(), Counter()
    minimum_touch = first
    maximum_touch = last
    relevant_entities = set()
    attribution_unknown = False
    closed_linkage = True
    invalid_movement = False
    with localcontext() as context:
        context.prec = 40
        for position, row in enumerate(receipts, 1):
            stamp = _stamp(row.get("occurred_at"))
            if stamp is None:
                issue("receipts", position, "UNKNOWN_RECEIPT_PERIOD")
                invalid_movement = True
                counts["invalidos_periodo_desconhecido"] += 1
                continue
            if not first <= stamp < last:
                counts["fora_do_periodo"] += 1
                continue
            counts["linhas_no_periodo"] += 1
            amount = _amount(row.get("amount_brl"))
            if (not _text(row.get("transaction_id")) or row.get("restaurant_id") != restaurant_id
                    or not _text(row.get("evidence_ref")) or amount is None):
                issue("receipts", position, "INVALID_RECEIPT_IDENTITY_AMOUNT_OR_EVIDENCE")
                counts["movimentos_invalidos"] += 1
                invalid_movement = True
                continue
            counts["movimentos_validos"] += 1
            if amount < 0:
                counts["estornos_validos"] += 1
            reservation, order = _text(row.get("reservation_id")), _text(row.get("order_id"))
            if not reservation and not order:
                bucket = "sem_vinculo_operacional"
            elif reservation and order:
                bucket = "nao_conciliado"
                issue("receipts", position, "AMBIGUOUS_OPERATIONAL_REFERENCE")
                closed_linkage = False
            else:
                key = ("reservation", reservation) if reservation else ("order", order)
                entity = entity_map.get(key)
                if entity is None:
                    bucket = "nao_conciliado"
                    issue("receipts", position, "OPERATIONAL_REFERENCE_NOT_FOUND")
                    closed_linkage = False
                else:
                    relevant_entities.add(key)
                    status = _text(entity.get("status"))
                    # Only expose controlled labels, never arbitrary source fields.
                    known = {"pendente", "confirmada", "realizada", "concluida", "cancelada", "no_show", "rascunho", "proposta_enviada", "entrada_paga", "confirmado", "realizado", "cancelado"}
                    status_counts[status if status in known else "desconhecido"] += 1
                    created, phone = _stamp(entity.get("created_at")), _text(entity.get("customer_phone"))
                    if not created or created > stamp or not PHONE.fullmatch(phone):
                        bucket = "conciliado_atribuicao_desconhecida"
                        issue("receipts", position, "UNKNOWN_ATTRIBUTION_IDENTITY_OR_CHRONOLOGY")
                        attribution_unknown = True
                    else:
                        window_start = created - timedelta(days=7)
                        minimum_touch = min(minimum_touch, window_start)
                        maximum_touch = max(maximum_touch, created + timedelta(microseconds=1))
                        candidates = [item for item in interaction_map.get(phone, []) if window_start <= item[0] < created]
                        # Last observed conversation wins; a later human-only conversation
                        # does not inherit assistance from an earlier agent conversation.
                        latest = candidates[-1][2] if candidates else None
                        ambiguous = bool(candidates) and len({item[2]["agent_assisted"] for item in candidates if item[0] == candidates[-1][0]}) > 1
                        covered = interactions_valid and _source(sources.get("interactions"), window_start, created, coverage=True)["cobre_recorte"]
                        if ambiguous:
                            bucket = "conciliado_atribuicao_desconhecida"
                            attribution_unknown = True
                            issue("receipts", position, "AMBIGUOUS_LAST_INTERACTION")
                        elif latest and latest["agent_assisted"]:
                            bucket = "conciliado_atribuicao_assistida"
                            if _text(latest.get("intent")) in ("reserva_nova", "evento"):
                                counts["movimentos_assistidos_com_intencao_registrada"] += 1
                        elif covered:
                            bucket = "conciliado_sem_interacao_elegivel"
                        else:
                            bucket = "conciliado_atribuicao_desconhecida"
                            attribution_unknown = True
                        if not covered:
                            attribution_unknown = True
            sums[bucket] += amount
            counts[bucket] += 1

        source_status["interactions"] = _source(sources.get("interactions"), minimum_touch, maximum_touch, coverage=True)
        complete = (all(source["cobre_recorte"] for source in source_status.values())
                    and not diagnostics and not invalid_movement and closed_linkage and not attribution_unknown)
        observed = {key: _money(value) if counts[key] or complete else None for key, value in sums.items()}
        observed_total = sum(sums.values(), Decimal("0.00"))
        matched_total = sum((sums[key] for key in BUCKETS[:3]), Decimal("0.00"))
        matched_count = sum(counts[key] for key in BUCKETS[:3])
        observed["recebimentos_liquidos_validos"] = _money(observed_total) if counts["movimentos_validos"] or complete else None
        observed["conciliado_total"] = _money(matched_total) if matched_count or complete else None
    return {
        "report_version": VERSION, "restaurant_id": restaurant_id,
        "periodo": {"inicio_inclusivo": start.isoformat(), "fim_exclusivo": end.isoformat(), "timezone": str(TZ)},
        "status": "complete" if complete else "incomplete", "fontes": source_status,
        "totais_fechados_brl": observed.copy() if complete else dict.fromkeys(observed),
        "somas_observadas_brl": observed,
        "contagens": {key: counts[key] for key in sorted(set(counts) | set(BUCKETS))},
        "estados_operacionais_atual_export_por_movimento": dict(sorted(status_counts.items())),
        "entidades_com_recebimento_conciliado": len(relevant_entities),
        "diagnosticos": diagnostics,
        "receita_incremental_brl": None,
        "regra_atribuicao": "ultima_conversa_observada_mesma_unidade_telefone_nos_7_dias_antes_da_criacao_com_assistencia_explicita",
        "limites": [
            "Atribuição observacional não demonstra receita incremental nem causalidade.",
            "Regime de caixa: cada movimento entra na data occurred_at; estorno posterior não reescreve o período anterior.",
            "Status de reserva/OS não comprova recebimento. Estados cancelado/no_show e estornos são preservados.",
            "Fonte declarada completa pelo exportador não substitui fechamento financeiro ou auditoria dos comprovantes.",
            "Não há estimativa por ticket, preço de cardápio, valor previsto de OS ou pagamento apenas marcado no sistema.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Conciliação offline, sem acesso a banco, rede ou cobrança.")
    parser.add_argument("--operations", required=True, type=Path)
    parser.add_argument("--receipts", required=True, type=Path)
    parser.add_argument("--restaurant-id", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True, help="Fim exclusivo, YYYY-MM-DD, America/Sao_Paulo")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output.resolve() in (args.operations.resolve(), args.receipts.resolve()):
            raise ContractError("OUTPUT_OVERWRITES_INPUT")
        raw_operations = args.operations.read_bytes()
        raw_receipts = args.receipts.read_bytes()
        result = reconcile(load_operations(raw_operations.decode("utf-8-sig")), load_receipts(raw_receipts.decode("utf-8-sig")),
                           restaurant_id=args.restaurant_id, start=date.fromisoformat(args.start), end=date.fromisoformat(args.end))
        result["input_sha256"] = {"operations": hashlib.sha256(raw_operations).hexdigest(), "receipts": hashlib.sha256(raw_receipts).hexdigest()}
        # Never replace an earlier report or an input. Keep only aggregate artifacts.
        with args.output.open("x", encoding="utf-8") as target:
            json.dump(result, target, ensure_ascii=False, indent=2, sort_keys=True)
            target.write("\n")
        print(json.dumps({"status": result["status"], "diagnostic_count": len(result["diagnosticos"])}))
        return 0 if result["status"] == "complete" else 2
    except ContractError as exc:
        print(str(exc), file=sys.stderr)
    except (OSError, ValueError, UnicodeError):
        print("INVALID_LOCAL_INPUT_OR_OUTPUT", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

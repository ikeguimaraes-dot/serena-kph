#!/usr/bin/env python3
"""Validate a local Serena onboarding dossier. No network, DB or writes.

Draft mode validates structure and lists readiness gaps. Go-live mode also fails
on missing evidence/decisions. Synthetic dossiers can never pass go-live.
Evidence references are declarations, not independent verification of contents.
"""
import argparse
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SECRET_KEYS = {"password", "senha", "auth_token", "api_key", "database_url",
               "access_token", "refresh_token", "private_key", "recovery_codes"}
CHECKS = {"tenant_isolation", "catalog_review", "auth_permissions", "fallback",
          "handoff_received", "backup_restore", "training", "privacy_review",
          "operator_signoff", "engineering_signoff"}
RESOURCES = {"source_control", "hosting_backend", "hosting_panel", "database",
             "whatsapp_provider", "meta_portfolio", "model_provider", "backup"}
MONEY = Decimal("0.01")


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (TypeError, ValueError, AttributeError):
        return None


def decimal(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def nonempty(value):
    return isinstance(value, str) and bool(value.strip()) and value.strip() != "PENDENTE"


def secret_paths(value, path="root"):
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if key.casefold() in SECRET_KEYS:
                found.append(child)
            found.extend(secret_paths(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(secret_paths(item, f"{path}[{index}]"))
    elif isinstance(value, str) and re.search(r"(?:postgres(?:ql)?|https?)://[^/\s]+:[^/\s]+@", value):
        found.append(path)
    return found


def has_fixture_reference(value):
    if isinstance(value, dict):
        return any(has_fixture_reference(item) for item in value.values())
    if isinstance(value, list):
        return any(has_fixture_reference(item) for item in value)
    return isinstance(value, str) and (value.startswith("fixture://") or "example.invalid" in value)


def validate(data):
    errors, blockers = [], []
    result = {"schema_version": 1, "structure_errors": errors, "blockers": blockers,
              "pricing": {"status": "pending"}, "elapsed_hours": {},
              "evidence_independently_verified": False}
    if not isinstance(data, dict):
        errors.append("Dossier must be a JSON object")
        return result
    for path in secret_paths(data):
        errors.append(f"Secret material is forbidden; use a vault reference: {path}")
    if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not isinstance(data.get("synthetic"), bool):
        errors.append("synthetic must be boolean")
    synthetic = data.get("synthetic") is True or has_fixture_reference(data)
    if synthetic:
        blockers.append("Synthetic dossier: never eligible for production")
    sections = ("business", "owners", "channels", "catalog", "agenda", "handoff",
                "persona", "scope", "data_policy", "measurements", "commercial", "go_live", "milestones")
    for section in sections:
        if not isinstance(data.get(section), dict):
            errors.append(f"{section} must be an object")
    if errors:
        return result

    def needed(condition, message):
        if not condition:
            blockers.append(message)

    business = data["business"]
    needed(bool(re.fullmatch(r"[a-z][a-z0-9_]{2,63}", str(business.get("tenant_id", "")))), "Unique tenant_id is required")
    for field in ("legal_name", "display_name", "vertical", "address", "official_url", "data_source_ref"):
        needed(nonempty(business.get(field)), f"business.{field} is pending")
    needed(str(business.get("vertical")) in {"gastronomy", "health", "aesthetics", "dentistry", "other"}, "Choose a supported vertical or explicitly other")
    needed(isinstance(business.get("clinical_risk"), bool), "Clinical risk must be explicitly classified")
    try:
        ZoneInfo(business.get("timezone", ""))
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        blockers.append("A valid IANA timezone is required")
    for role in ("business", "operations", "engineering", "data_privacy", "commercial"):
        needed(nonempty(data["owners"].get(role)), f"Accountable owner for {role} is pending")
    for field in ("agent_name", "tone", "language", "limits_ref", "prompt_version_ref", "vision_rules_ref", "source_of_truth_ref"):
        needed(nonempty(data["persona"].get(field)), f"persona.{field} is pending")
    for field in ("included_modules", "excluded_modules"):
        needed(isinstance(data["scope"].get(field), list) and bool(data["scope"][field])
               and all(nonempty(item) for item in data["scope"][field]), f"scope.{field} is pending")
    needed(nonempty(data["scope"].get("signed_scope_ref")), "Signed pilot scope is pending")
    for field in ("consent_policy_ref", "privacy_notice_ref", "retention_policy_ref", "data_export_procedure_ref"):
        needed(nonempty(data["data_policy"].get(field)), f"data_policy.{field} is pending")

    channels = data["channels"]
    needed(bool(re.fullmatch(r"\+[1-9][0-9]{7,14}", str(channels.get("whatsapp_number", "")))), "A confirmed E.164 WhatsApp number is required")
    for field in ("sender_ref", "waba_ref", "display_name_evidence_ref"):
        needed(nonempty(channels.get(field)), f"channels.{field} is pending")
    needed(channels.get("display_name_approved") is True, "Sender display name approval is pending")

    catalog = data["catalog"]
    count = catalog.get("item_count")
    needed(isinstance(count, int) and not isinstance(count, bool) and count > 0, "A nonempty verified catalog is required")
    for field in ("source_ref", "manifest_sha256", "reviewer", "review_evidence_ref"):
        needed(nonempty(catalog.get(field)), f"catalog.{field} is pending")
    needed(bool(re.fullmatch(r"[a-f0-9]{64}", str(catalog.get("manifest_sha256", "")))), "Catalog SHA-256 must have 64 hexadecimal characters")
    needed(catalog.get("operator_review_complete") is True, "Catalog operational review is pending")

    agenda = data["agenda"]
    if agenda.get("mode") == "own":
        for field in ("source_ref", "turns_evidence_ref", "capacity_evidence_ref", "blocks_evidence_ref", "concurrency_test_ref"):
            needed(nonempty(agenda.get(field)), f"agenda.{field} is pending")
        needed(agenda.get("operator_approved") is True, "Agenda operator approval is pending")
    elif agenda.get("mode") == "external_link":
        needed(nonempty(agenda.get("official_booking_url")), "Official booking URL is required")
        needed(nonempty(agenda.get("identity_evidence_ref")), "External venue identity proof is required")
        needed(agenda.get("accepted_pilot_limitation") is True, "External agenda limitation must be explicit in pilot scope")
    else:
        blockers.append("Agenda mode must be own or explicitly accepted external_link")

    handoff = data["handoff"]
    for field in ("primary_owner", "backup_owner", "boundary_ref", "destination_evidence_ref", "receipt_evidence_ref"):
        needed(nonempty(handoff.get(field)), f"handoff.{field} is pending")
    needed(handoff.get("received_by_human") is True, "Human handoff receipt must be proved; API acceptance is insufficient")
    if str(business.get("vertical")) in {"health", "aesthetics", "dentistry"} or business.get("clinical_risk") is True:
        needed(nonempty(handoff.get("clinical_owner")), "Clinical owner is required for this vertical")
        needed(nonempty(handoff.get("clinical_boundary_ref")), "Clinical escalation boundary is required")

    inventory = data.get("access_inventory")
    if not isinstance(inventory, list) or any(not isinstance(item, dict) for item in inventory):
        errors.append("access_inventory must be a list of objects")
        inventory = []
    resources = [item.get("resource") for item in inventory]
    if len(resources) != len(set(str(item) for item in resources)):
        errors.append("access_inventory contains duplicate resources")
    for resource in sorted(RESOURCES - set(str(item) for item in resources)):
        blockers.append(f"Access inventory is missing {resource}")
    for item in inventory:
        resource = str(item.get("resource", "unknown"))
        for field in ("account_ref", "owner", "backup_owner", "recovery_method", "vault_ref", "recovery_test_ref"):
            needed(nonempty(item.get(field)), f"access_inventory.{resource}.{field} is pending")
        needed(timestamp(item.get("recovery_tested_at")) is not None, f"Recovery test date pending for {resource}")

    checks = data["go_live"].get("checks", {})
    if not isinstance(checks, dict):
        errors.append("go_live.checks must be an object")
        checks = {}
    for name in sorted(CHECKS):
        item = checks.get(name)
        if not isinstance(item, dict):
            blockers.append(f"Go-live check missing: {name}")
            continue
        needed(item.get("status") == "passed" and nonempty(item.get("owner"))
               and nonempty(item.get("evidence_ref")) and timestamp(item.get("verified_at")) is not None,
               f"Go-live check lacks accountable, dated evidence: {name}")
    needed(nonempty(data["go_live"].get("assisted_operation_owner")), "Assisted operation owner is pending")
    needed(nonempty(data["go_live"].get("rollback_ref")), "Rollback runbook is pending")

    moments = data["milestones"]
    for start, end, label in (("briefing_complete_at", "pilot_live_at", "onboarding"),
                              ("engineering_started_at", "engineering_completed_at", "engineering")):
        start_at, end_at = timestamp(moments.get(start)), timestamp(moments.get(end))
        if start_at is not None and end_at is not None:
            if end_at < start_at:
                errors.append(f"Invalid milestone chronology: {start}, {end}")
            else:
                result["elapsed_hours"][label] = round((end_at - start_at).total_seconds() / 3600, 2)

    measurement, commercial = data["measurements"], data["commercial"]
    numeric_fields = ("llm_cost_brl", "messaging_cost_brl", "infra_allocated_brl",
                      "support_allocated_brl", "setup_hours", "loaded_hourly_brl", "setup_direct_brl")
    costs = {field: decimal(measurement.get(field)) for field in numeric_fields}
    conversations = measurement.get("conversations")
    messages = measurement.get("billable_messages")
    positive_int = lambda value: isinstance(value, int) and not isinstance(value, bool) and value > 0
    try:
        period_days = (date.fromisoformat(measurement["end_date"]) - date.fromisoformat(measurement["start_date"])).days + 1
    except (KeyError, TypeError, ValueError):
        period_days = 0
    measured = (measurement.get("status") == "measured" and period_days > 0
                and positive_int(conversations) and positive_int(messages)
                and all(value is not None and value >= 0 for value in costs.values())
                and isinstance(measurement.get("evidence_refs"), list)
                and bool(measurement["evidence_refs"])
                and all(nonempty(value) for value in measurement["evidence_refs"]))
    needed(measured, "Comparable measured costs, volume, dates and evidence are pending")
    included = commercial.get("included_messages")
    billing_days = commercial.get("billing_period_days")
    margin, taxes = decimal(commercial.get("target_margin")), decimal(commercial.get("effective_tax_rate"))
    decided = (commercial.get("decision_status") == "approved" and nonempty(commercial.get("decision_owner"))
               and nonempty(commercial.get("decision_ref")) and positive_int(included) and positive_int(billing_days)
               and margin is not None and taxes is not None and 0 <= margin < 1 and 0 <= taxes < 1 and margin + taxes < 1)
    needed(decided, "Franchise, billing period, margin, tax and accountable commercial decision are pending")
    if measured and decided:
        divisor = 1 - margin - taxes
        variable = (costs["llm_cost_brl"] + costs["messaging_cost_brl"]) / messages
        fixed = (costs["infra_allocated_brl"] + costs["support_allocated_brl"]) * Decimal(billing_days) / period_days
        setup = costs["setup_hours"] * costs["loaded_hourly_brl"] + costs["setup_direct_brl"]
        rounded = lambda value: str(value.quantize(MONEY, rounding=ROUND_HALF_UP))
        result["pricing"] = {
            "status": "synthetic_example" if synthetic else "floor_from_declared_measurements",
            "period_days": period_days, "included_messages": included,
            "variable_cost_per_billable_message_brl": str(variable.quantize(Decimal("0.000001"))),
            "variable_cost_per_conversation_brl": rounded((costs["llm_cost_brl"] + costs["messaging_cost_brl"]) / conversations),
            "subscription_floor_brl": rounded((fixed + variable * included) / divisor),
            "overage_floor_per_message_brl": str((variable / divisor).quantize(Decimal("0.000001"))),
            "setup_floor_brl": rounded(setup / divisor),
            "assumption": "Observed message/conversation/channel mix continues; floors are not the approved sale price",
        }
        floors = {"subscription_price_brl": (fixed + variable * included) / divisor,
                  "overage_price_per_message_brl": variable / divisor, "setup_price_brl": setup / divisor}
        for field, floor in floors.items():
            selected = decimal(commercial.get(field))
            needed(selected is not None and selected >= 0, f"commercial.{field} is pending")
            if selected is not None and selected < floor:
                needed(nonempty(commercial.get("below_floor_exception_ref")), f"commercial.{field} is below the cost floor; explicit exception is required")
    needed(nonempty(commercial.get("final_price_approval_ref")), "Final sale price approval is pending")
    result["structure_valid"] = not errors
    result["ready_from_declared_evidence"] = not errors and not blockers
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dossier", type=Path)
    parser.add_argument("--mode", choices=("draft", "go-live"), default="draft")
    args = parser.parse_args()
    try:
        data = json.loads(args.dossier.read_text())
    except (OSError, ValueError):
        print(json.dumps({"structure_errors": ["Unable to read a valid JSON dossier"]}))
        return 2
    report = validate(data)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report["structure_errors"] else (1 if args.mode == "go-live" and report["blockers"] else 0)


if __name__ == "__main__":
    raise SystemExit(main())

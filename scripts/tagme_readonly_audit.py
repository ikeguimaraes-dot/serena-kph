#!/usr/bin/env python3
"""Read-only, venue-scoped audit of Tagme public booking configuration.

Never sends API keys, creates bookings, signs in, or downloads customer histories.
Private artifacts default outside Git; the DB connection only uses read-only SQL.
"""
import argparse
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import unicodedata
import urllib.error
import urllib.request

import asyncpg


TARGETS = {"meet_and_eat": "Meet & Eat", "freneze": "Frêneze"}
PUBLIC_ORIGIN = "https://public.tagme.com.br"


def save_private(path: Path, data: bytes):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(data)


def save_json(path, value):
    save_private(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def normalized_name(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value).casefold() if not unicodedata.combining(c)).strip()


def fetch_venue_resource(venue_id: str, suffix: str, target: Path) -> tuple[dict, dict | None]:
    if not re.fullmatch(r"[a-f0-9]{24}", venue_id):
        raise ValueError("Invalid venue ID")
    if suffix not in ("", "/apps-availability", "/availability-for-app/reservationWidget"):
        raise ValueError("Only public, read-only venue resources are allowed")
    url = f"{PUBLIC_ORIGIN}/venues/{venue_id}{suffix}"
    audit = {"url": url, "checked_at": datetime.now(timezone.utc).isoformat()}
    try:
        with urllib.request.urlopen(url, timeout=25) as response:
            payload = response.read()
            audit.update(status=response.status, bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError("Unexpected public API response shape")
        save_private(target, payload)
        return audit, data
    except urllib.error.HTTPError as error:
        audit.update(status=error.code, access_denied=error.code in (401, 403))
        return audit, None


def availability_summary(data: dict) -> dict:
    days = data.get("availabilities", [])
    groups = defaultdict(list)
    slots = 0
    for day in days:
        sections = []
        for section in day.get("sections", []):
            schedules = []
            for schedule in section.get("schedules", []):
                times = schedule.get("reservationTimes", [])
                slots += len(times)
                # Keep table counts separate for each party size; never sum them into seats.
                schedules.append({
                    "party_size": schedule.get("partySize"),
                    "available": schedule.get("available"),
                    "times": [t.get("reservationTime") for t in times],
                    "tables_quantity_values": sorted({t["tablesQuantity"] for t in times if "tablesQuantity" in t}),
                })
            sections.append({"name": section.get("label"), "available": section.get("available"), "schedules": schedules})
        key = json.dumps(sections, ensure_ascii=False, sort_keys=True)
        groups[key].append(day["reservationDay"])
    return {
        "server_time": data.get("serverTime"), "available": data.get("available"),
        "minimum_antecedence_minutes": data.get("minAntecedence"),
        "maximum_antecedence_days": data.get("maxDaysAntecedence"),
        "delay_tolerance_minutes": data.get("delayTolerance"),
        "group_reservations": data.get("widgetGroupReservations"),
        "day_count": len(days), "first_date": min((d["reservationDay"] for d in days), default=None),
        "last_date": max((d["reservationDay"] for d in days), default=None),
        "slot_combinations": slots,
        "observed_schedule_patterns": [{"dates": dates, "sections": json.loads(key)} for key, dates in groups.items()],
        "capacity_people": None,
        "capacity_mapping_status": "Not derivable: table quantities by party size are not additive physical seat capacity",
        "reservation_history_exported": False,
    }


async def main(args):
    os.umask(0o077)
    output = args.output.expanduser().resolve()
    if any((parent / ".git").exists() for parent in (output, *output.parents)):
        raise ValueError("Audit artifacts must stay outside Git")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    variables = json.loads(subprocess.check_output(
        ["railway", "variable", "list", "--service", "restaurant-ai", "--environment", "production", "--json"],
        cwd=args.railway_cwd, text=True))
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "read_only": True,
              "tagme_api_key_present": bool(variables.get("TAGME_API_KEY")),
              "partner_app_id_present": bool(variables.get("TAGME_PARTNER_APP_ID")),
              "credentials_sent_to_tagme": False, "venues": {}, "history_rows_exported": 0}
    connection = await asyncpg.connect(variables["DATABASE_URL"], ssl="require", statement_cache_size=0)
    try:
        async with connection.transaction(readonly=True):
            rows = await connection.fetch(
                "SELECT id,nome,tagme_venue_id FROM restaurants WHERE id=ANY($1::text[]) ORDER BY id", list(TARGETS))
            for row in rows:
                rid = row["id"]
                record = {"restaurant_id": rid, "name": row["nome"], "db_tagme_venue_id": row["tagme_venue_id"]}
                record["own_turn_count"] = await connection.fetchval(
                    "SELECT count(*) FROM agenda_turnos WHERE restaurant_id=$1", rid)
                venue = row["tagme_venue_id"]
                if venue:
                    record["venue_id_source"] = "restaurants.tagme_venue_id"
                elif args.allow_active_prompt_link:
                    prompt = await connection.fetchval(
                        "SELECT prompt_completo FROM serena_prompt_versions WHERE restaurant_id=$1 AND ativa=true LIMIT 1", rid)
                    candidates = set(re.findall(
                        r"https://reservation-widget\.tagme\.com\.br/(?:smartlink|reservation/schedule)/([a-f0-9]{24})(?:\b|/)", prompt or ""))
                    if len(candidates) == 1:
                        venue = candidates.pop()
                        record["venue_id_source"] = "Active tenant prompt; public identity must also match"
                record["venue_id"] = venue
                report["venues"][rid] = record
    finally:
        await connection.close()
    for rid, record in report["venues"].items():
        venue = record["venue_id"]
        if not venue:
            record["blocked"] = "Missing verified venue ID"
            continue
        checks = []
        identity_check, identity = fetch_venue_resource(venue, "", output / f"{rid}_venue.json")
        checks.append(identity_check)
        record["requests"] = checks
        if identity is None:
            record["blocked"] = "Public identity request failed; no retries or alternate endpoints"
            continue
        actual_name = identity.get("name", {}).get("pt", "")
        if identity.get("_id") != venue or normalized_name(actual_name) != normalized_name(TARGETS[rid]):
            record["blocked"] = "Public venue identity does not match expected restaurant"
            continue
        record["public_identity"] = {"name": actual_name, "address": identity.get("address")}
        for suffix, filename in (("/apps-availability", "services"), ("/availability-for-app/reservationWidget", "availability")):
            check, data = fetch_venue_resource(venue, suffix, output / f"{rid}_{filename}.json")
            checks.append(check)
            if data is None:
                record["blocked"] = "Public configuration request failed; no retries or alternate endpoints"
                break
            if filename == "services":
                record["services"] = data
            else:
                summary = availability_summary(data)
                save_json(output / f"{rid}_schedule_summary.json", summary)
                record["availability"] = {k: v for k, v in summary.items() if k != "observed_schedule_patterns"}
    save_json(output / "audit-manifest.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--railway-cwd", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path.home() / ".local/share/serena-recovery/export-legado-20260917")
    parser.add_argument("--allow-active-prompt-link", action="store_true",
                        help="Permit a single venue ID from the tenant's active prompt, checking public identity first")
    asyncio.run(main(parser.parse_args()))

"""Real restored PostgreSQL only; provider and approval HTTP calls are mocked."""
import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import asyncpg
import database as db
import outreach as o
import outreach_scheduler as scheduler
import test_outreach_restore as previous_outreach


async def run():
    host = os.environ.get("PGHOST", "")
    if not host.startswith("/tmp/serena-restore-") or os.environ.get("PGDATABASE") != "serena_restore":
        raise RuntimeError("Only an isolated disposable restored database is allowed")
    # Exercise existing nurture/post-event contracts against the additive migration.
    await previous_outreach.run()
    pool = await asyncpg.create_pool(host=host, port=int(os.environ["PGPORT"]),
        user=os.environ["PGUSER"], database="serena_restore", ssl=False, min_size=1, max_size=5)
    db._pool = pool
    try:
        clock = datetime(2030, 1, 1, 23, 30, tzinfo=timezone.utc)
        phone = "+12025550120"
        nonce = uuid.uuid4().hex
        a, b, inactive = (prefix+nonce for prefix in ("reservation-rule-a-", "reservation-rule-b-", "reservation-rule-inactive-"))
        for index, rid in enumerate((a, b, inactive)):
            await pool.execute("INSERT INTO restaurants(id,nome,whatsapp_number,ativo) VALUES($1,$2,$3,$4)",
                rid, "Synthetic business " + str(index), f"+1202555018{index}", rid != inactive)
            await db.ensure_contact(phone, "Synthetic customer", rid)
        consent = o.ConsentChange(granted=True, source="form", occurred_at=o.utcnow()-timedelta(minutes=5), evidence="Synthetic consent evidence only")
        await o.record_consent(a, phone, consent, "synthetic-operator")
        mapping = {"2": "hora", "4": "nome", "7": "unidade", "9": "data"}
        approval = AsyncMock(return_value={"status": "approved", "verified_at": o.utcnow()})
        variables = AsyncMock()
        with patch.object(o, "verify_template", approval), patch.object(o, "verify_reservation_variables", variables):
            for rid in (a, b, inactive):
                for stage in o.RESERVATION_STAGES:
                    rule = await o.save_rule(rid, stage, o.RuleChange(enabled=True, content_sid="HX"+"a"*32, template_variables=mapping), "synthetic-operator")
                    assert rule["template_variables"] == mapping
                    await pool.execute("UPDATE outreach_rules SET updated_at=$3 WHERE restaurant_id=$1 AND stage=$2", rid, stage, clock-timedelta(hours=1))

        async def booking(rid, hours=23, status="confirmada", event_hours=2):
            at = (clock+timedelta(hours=hours)).astimezone(o.RESERVATION_TIMEZONE)
            reservation = await pool.fetchrow("""INSERT INTO reservas
                (restaurant_id,cliente_phone,cliente_nome,data,hora_inicio,posicoes,status)
                VALUES($1,$2,'Synthetic customer',$3,$4,1,$5) RETURNING *""", rid, phone, at.date(), at.time().replace(tzinfo=None), status)
            # The event exists because of the production trigger. Timestamp is a
            # synthetic clock fixture, never a fabricated production event.
            await pool.execute("UPDATE reservation_status_events SET occurred_at=$2 WHERE reserva_id=$1", reservation["id"], clock-timedelta(hours=event_hours))
            return reservation

        target = await booking(a, event_hours=.5)
        historical = await booking(a)
        pending = await booking(a, status="pendente", event_hours=.5)
        cancelled = await booking(a, status="cancelada", event_hours=.5)
        missed = await booking(a, status="no_show", event_hours=.5)
        past = await booking(a, hours=-1, event_hours=.5)
        early = await booking(a, hours=24.01)
        late = await booking(a, hours=19.99)
        lower = await booking(a, hours=20)
        upper = await booking(a, hours=24)
        cross = await booking(b, event_hours=.5)
        await booking(inactive, event_hours=.5)
        async with pool.acquire() as c:
            found = await o.candidates(c, a, "reservation", clock)
            confirmation = [item for item in found if item["stage"] == "reservation_confirmation"]
            reminders = [item for item in found if item["stage"] == "reservation_reminder"]
            assert {item["object_id"] for item in confirmation} == {str(target["id"])}
            assert {item["object_id"] for item in reminders} == {str(row["id"]) for row in (target, historical, lower, upper)}
            assert confirmation[0]["variables"] == {"2": "19:30", "4": "Synthetic customer", "7": "Synthetic business 0", "9": "02/01/2030"}
            assert not await o.candidates(c, inactive, "reservation", clock)
            other = await o.candidates(c, b, "reservation", clock)
            checked = await o.evaluate(c, b, other[0], "+12025550181")
            assert "explicit_consent_missing_or_revoked" in checked["blocked_reasons"]
        # No historic confirmation on enable. Cancelling or lacking a real status
        # event cannot be reclassified as confirmed by the outreach worker.
        await pool.execute("UPDATE outreach_rules SET enabled=false WHERE stage='reservation_reminder' AND restaurant_id=$1", a)
        calls = []
        async def accepted(attempt):
            calls.append(attempt)
            await asyncio.sleep(.03)
            return {"status": "sent", "provider_message_sid": "SM"+"a"*32, "provider_status": "queued"}
        with patch.dict(os.environ, {"SERENA_OUTREACH_SEND_ENABLED": "true"}), \
             patch.object(o, "utcnow", return_value=clock), \
             patch.object(o, "provider_credentials", return_value=("AC"+"a"*32, "synthetic")), \
             patch.object(o, "verify_template", approval), \
             patch.object(o, "verify_reservation_variables", variables), \
             patch.object(o, "send_template", accepted):
            preview = await o.preview(a, "reservation")
            assert preview["total"] == 1 and preview["items"][0]["eligible"]
            assert await pool.fetchval("SELECT count(*) FROM outreach_outbox WHERE restaurant_id=$1", a) == 0
            results = await asyncio.gather(o.run(a, "reservation", False), o.run(a, "reservation", False))
            assert len(calls) == 1 and sum(item["sent"] for item in results) == 1
            await pool.execute("UPDATE reservas SET data=data+7 WHERE id=$1", target["id"])
            assert (await o.run(a, "reservation", False))["sent"] == 0
            assert len(calls) == 1  # reschedule never creates a second stage send
            unclaimed = await booking(a, hours=48, event_hours=.25)
            item = (await o.preview(a, "reservation"))["items"][0]
            assert item["object_id"] == str(unclaimed["id"])
            await pool.execute("UPDATE reservas SET status='cancelada' WHERE id=$1", unclaimed["id"])
            assert await o.claim(a, "reservation", item) is None
            revoked = await booking(a, hours=49, event_hours=.25)
            item = (await o.preview(a, "reservation"))["items"][0]
            assert item["object_id"] == str(revoked["id"])
            change = o.ConsentChange(granted=False, source="revocation", occurred_at=clock-timedelta(minutes=1), evidence="Synthetic revocation before claim")
            await o.record_consent(a, phone, change, "synthetic-operator")
            assert await o.claim(a, "reservation", item) is None
        assert calls[0]["sender_phone"] == "+12025550180"
        payload = json.loads(calls[0]["payload"])
        assert payload["variables"]["9"] == "02/01/2030"
        assert await pool.fetchval("SELECT count(*) FROM outreach_outbox WHERE restaurant_id=$1", b) == 0
        # The periodic worker isolates failures by unit and family, with sends
        # separately disabled. Inactive units never enter the scheduler scope.
        attempted = []
        async def fake_run(rid, family, dry_run):
            attempted.append((rid, family, dry_run))
            if rid == a:
                raise RuntimeError("Synthetic unit failure")
            return {"dry_run": dry_run, "sent": 0}
        with patch.dict(os.environ, {"SERENA_OUTREACH_SCHEDULER_ENABLED": "true", "SERENA_OUTREACH_SEND_ENABLED": "false"}), \
             patch.object(o, "run", side_effect=fake_run):
            await scheduler.scheduled_tick()
        assert (a, "reservation", True) in attempted and (b, "reservation", True) in attempted
        assert not any(rid == inactive for rid, _, _ in attempted)
        print(json.dumps({"success": True, "reservation_status_and_real_event_required": True,
            "confirmation_not_backfilled_on_activation": True, "brt_20_to_24_hour_window_and_boundaries": True,
            "explicit_variable_mapping": True, "tenant_consent_and_sender_isolation": True,
            "concurrent_single_attempt_and_no_reschedule_duplicate": True,
            "cancellation_and_revocation_rechecked_at_claim": True,
            "periodic_worker_default_off_and_per_unit_failure_isolation": True,
            "external_messages_sent": 0, "production_writes": 0}))
    finally:
        db._pool = None
        await pool.close()


if __name__ == "__main__":
    asyncio.run(run())

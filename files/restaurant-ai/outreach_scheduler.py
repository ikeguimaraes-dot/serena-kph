"""Optional 15-minute outreach polling; tenant/rule/consent/send gates still apply."""
import os

import database as db
import outreach


def scheduler_enabled():
    return os.environ.get("SERENA_OUTREACH_SCHEDULER_ENABLED", "").lower() == "true"


async def scheduled_tick():
    if not scheduler_enabled():
        return {"enabled": False, "units": 0, "runs": []}
    async with db.pool().acquire() as connection:
        rows = await connection.fetch("""
            SELECT b.id,array_agg(ru.stage ORDER BY ru.stage) AS stages
            FROM restaurants b JOIN outreach_rules ru ON ru.restaurant_id=b.id AND ru.enabled=true
            WHERE b.ativo=true GROUP BY b.id ORDER BY b.id
        """)
    runs = []
    for row in rows:
        stages = set(row["stages"])
        families = []
        if "nurture_d3" in stages:
            families.append("nurture")
        if stages.intersection(outreach.WINDOWS):
            families.append("pos_evento")
        if stages.intersection(outreach.RESERVATION_STAGES):
            families.append("reservation")
        for family in families:
            try:
                report = await outreach.run(row["id"], family, dry_run=not outreach.sending_enabled())
                runs.append({"restaurant_id": row["id"], "family": family,
                             "dry_run": report["dry_run"], "accepted": report["sent"]})
            except Exception as error:
                # No phone, payload, credentials or provider response in scheduler logs.
                print(f"[OUTREACH] unit={row['id']} family={family} failed={type(error).__name__}")
                runs.append({"restaurant_id": row["id"], "family": family, "error": type(error).__name__})
    return {"enabled": True, "units": len(rows), "runs": runs}


def start_scheduler():
    if not scheduler_enabled():
        return None
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")
    scheduler.add_job(scheduled_tick, "interval", minutes=15, id="serena_outreach",
                      replace_existing=True, max_instances=1, coalesce=True, misfire_grace_time=900)
    scheduler.start()
    print("[OUTREACH] periodic polling enabled, every 15 minutes; individual sending gates remain required")
    return scheduler

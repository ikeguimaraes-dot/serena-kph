"""Run only through the private backup restore runner; never target production."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlencode
import uuid

import asyncpg
import database as db
from test_recovery_contract import TransactionPool

HERE = Path(__file__).parent
OPERATOR = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


async def run():
    host = os.environ.get("PGHOST", "")
    if not host.startswith("/tmp/serena-restore-") or os.environ.get("PGDATABASE") != "serena_restore":
        raise RuntimeError("Only a disposable restored Unix-socket database is allowed")
    url = f"postgresql://{os.environ['PGUSER']}@localhost:{os.environ['PGPORT']}/serena_restore?" + urlencode({
        "host": host, "sslmode": "disable"})
    c = await asyncpg.connect(host=host, port=int(os.environ["PGPORT"]),
                             user=os.environ["PGUSER"], database="serena_restore", ssl=False)
    db._pool = TransactionPool(c)
    try:
        original_contacts = await c.fetchval("SELECT count(*) FROM contacts")
        legacy_tenant = "legacy-loss-" + uuid.uuid4().hex
        await c.execute("INSERT INTO restaurants(id,nome,whatsapp_number,ativo) VALUES($1,$1,$2,false)", legacy_tenant, "+"+legacy_tenant)
        await c.execute("INSERT INTO contacts(celular,restaurant_id,estagio_kanban) VALUES('synthetic-legacy',$1,'perdido')", legacy_tenant)
        previous = await c.fetch("SELECT id,to_jsonb(c)::text AS data FROM contacts c ORDER BY id")
        migration = HERE / "migrations/20260917045116_crm_loss_reason_history.sql"
        # CLI v2.101 incorrectly reparses Unix-socket URL paths as database names.
        # Keep the local no-TCP boundary and use the established asyncpg connection.
        for _ in range(2):
            await c.execute(migration.read_text())
        after = await c.fetch("""SELECT id,(to_jsonb(c)-'motivo_perda'-'motivo_perda_detalhe'-'estagio_alterado_em')::text AS data
                                 FROM contacts c ORDER BY id""")
        assert [dict(row) for row in previous] == [dict(row) for row in after]
        assert await c.fetchval("SELECT count(*) FROM contact_stage_events") == 0
        assert await c.fetchval("SELECT count(*) FROM reservation_status_events") == 0
        assert await db.mark_inactive_contacts(1) == 0
        legacy = await db.update_contact("synthetic-legacy", {"nome": "Synthetic legacy updated"}, legacy_tenant)
        assert legacy["estagio_kanban"] == "perdido" and legacy["motivo_perda"] is None
        assert await db.get_contact_stage_history("synthetic-legacy", legacy_tenant) == []

        nonce = uuid.uuid4().hex
        a, b, phone = "history-a-" + nonce, "history-b-" + nonce, "+history-" + nonce
        for rid in (a, b):
            await c.execute("INSERT INTO restaurants(id,nome,whatsapp_number,ativo) VALUES($1,$1,$2,false)", rid, phone+rid)
            await db.ensure_contact(phone, "Synthetic", rid)
        first = await db.get_contact(phone, a)
        assert first["estagio_kanban"] == "captacao"
        await db.move_contact_kanban(phone, "perdido", a, motivo_perda="preco", operator_id=OPERATOR)
        history = await db.get_contact_stage_history(phone, a)
        assert len(history) == 2 and history[0]["event_type"] == "stage_changed"
        assert str(history[0]["actor_operator_id"]) == OPERATOR and history[0]["source"] == "crm_api"
        assert history[0]["previous_stage"] == "captacao" and history[0]["loss_reason"] == "preco"
        assert (await db.get_contact(phone, b))["estagio_kanban"] == "captacao"
        assert len(await db.get_contact_stage_history(phone, b)) == 1
        # Idempotent retries don't invent transition events.
        await db.move_contact_kanban(phone, "perdido", a, motivo_perda="preco", operator_id=OPERATOR)
        assert len(await db.get_contact_stage_history(phone, a)) == 2
        await db.update_contact(phone, {"estagio_kanban": "perdido", "motivo_perda": "outro", "motivo_perda_detalhe": "Data mudou"}, a, operator_id=OPERATOR)
        history = await db.get_contact_stage_history(phone, a)
        assert history[0]["event_type"] == "loss_reason_updated" and history[0]["previous_loss_reason"] == "preco"
        await db.update_contact(phone, {"estagio_kanban": "qualificado"}, a, operator_id=OPERATOR)
        reopened = await db.get_contact(phone, a)
        assert reopened["motivo_perda"] is None and reopened["motivo_perda_detalhe"] is None
        history = await db.get_contact_stage_history(phone, a)
        assert history[0]["previous_loss_reason"] == "outro" and history[0]["previous_loss_detail"] == "Data mudou"
        assert history[0]["loss_reason"] is None
        # Existing agent updates to proposal keep working and are audited as backend.
        await db.update_contact(phone, {"estagio_kanban": "proposta"}, a)
        assert (await db.get_contact_stage_history(phone, a))[0]["source"] == "backend"
        assert (await db.get_contact_stage_history(phone, a))[0]["actor_operator_id"] is None
        await db.upsert_contact({"celular": phone, "estagio_kanban": "perdido", "motivo_perda": "sem_retorno"}, a, operator_id=OPERATOR)
        assert (await db.get_contact_stage_history(phone, a))[0]["loss_reason"] == "sem_retorno"
        await db.move_contact_kanban(phone, "proposta", a)

        async def sql_rejected(sql, *args):
            try:
                async with c.transaction():
                    await c.execute(sql, *args)
            except asyncpg.CheckViolationError:
                return
            raise AssertionError("Invalid direct database transition was accepted")

        for stage in ("perdido", "Inativo"):
            await sql_rejected("UPDATE contacts SET estagio_kanban=$3 WHERE celular=$1 AND restaurant_id=$2", phone, a, stage)
        await sql_rejected("UPDATE contacts SET estagio_kanban='perdido',motivo_perda='inventado' WHERE celular=$1 AND restaurant_id=$2", phone, a)
        await sql_rejected("UPDATE contacts SET estagio_kanban='perdido',motivo_perda='outro' WHERE celular=$1 AND restaurant_id=$2", phone, a)

        # Direct writes have no inherited operator context from the pooled call.
        await c.execute("UPDATE contacts SET estagio_kanban='fechado' WHERE celular=$1 AND restaurant_id=$2", phone, a)
        history = await db.get_contact_stage_history(phone, a)
        assert history[0]["source"] == "database" and history[0]["actor_operator_id"] is None

        # SQL function is a no-op even for a very old visit.
        await c.execute("UPDATE contacts SET ultima_visita=DATE '2000-01-01' WHERE celular=$1 AND restaurant_id=$2", phone, a)
        old_count = len(await db.get_contact_stage_history(phone, a))
        assert await db.mark_inactive_contacts(1) == 0
        assert len(await db.get_contact_stage_history(phone, a)) == old_count
        assert (await db.get_contact(phone, a))["estagio_kanban"] == "fechado"

        reservation_phone = phone + "-reservation"
        reservation = await db.criar_reserva({"restaurant_id": a, "cliente_phone": reservation_phone, "cliente_nome": "Synthetic",
                                              "data": "2026-10-01", "hora_inicio": "19:00", "posicoes": 1})
        rid = str(reservation["id"])
        assert len(await db.get_reserva_status_history(rid, a)) == 1
        assert await db.get_reserva_status_history(rid, b) == []
        await db.atualizar_status_reserva(rid, a, "no_show", operator_id=OPERATOR)
        status = await db.get_reserva_status_history(rid, a)
        assert len(status) == 2 and status[0]["previous_status"] == "pendente" and status[0]["new_status"] == "no_show"
        assert str(status[0]["actor_operator_id"]) == OPERATOR and status[0]["source"] == "reservation_api"
        await db.atualizar_status_reserva(rid, a, "no_show", operator_id=OPERATOR)
        assert len(await db.get_reserva_status_history(rid, a)) == 2
        await c.execute("UPDATE reservas SET status='concluida' WHERE id=$1::uuid", rid)
        assert (await db.get_reserva_status_history(rid, a))[0]["source"] == "database"
        assert (await db.get_reserva_status_history(rid, a))[0]["actor_operator_id"] is None
        synced = (await db.get_contact_stage_history(reservation_phone, a))[0]
        assert synced["source"] == "reservation_sync" and synced["new_stage"] == "fechado"

        # Queryable audit is private. Browser roles get neither table nor function access.
        security = await c.fetch("""SELECT relname,relrowsecurity,
            has_table_privilege('anon',oid,'SELECT') AS anon_read,
            has_table_privilege('authenticated',oid,'SELECT') AS auth_read
            FROM pg_class WHERE oid IN ('contact_stage_events'::regclass,'reservation_status_events'::regclass)""")
        assert all(row["relrowsecurity"] and not row["anon_read"] and not row["auth_read"] for row in security)
        assert await c.fetchval("""SELECT count(*) FROM pg_proc WHERE proname IN
            ('audit_contact_stage','audit_reservation_status','validate_contact_loss_reason')
            AND (prosecdef OR has_function_privilege('anon',oid,'EXECUTE') OR has_function_privilege('authenticated',oid,'EXECUTE'))""") == 0
        advisors = subprocess.run(["supabase", "db", "advisors", "--db-url", url, "--type", "security", "--output-format", "json"],
                                   capture_output=True, text=True, timeout=45)
        # Do not publish raw advisor records of other private restored objects.
        advisor_note = "completed" if advisors.returncode == 0 else "unavailable_for_restored_cluster"
        if advisors.returncode:
            Path(os.environ["PGHOST"]).joinpath("advisor-diagnostic.log").write_text(advisors.stderr + advisors.stdout)
        print(json.dumps({"success": True, "migration_replay": True,
            "existing_contacts_preserved": original_contacts, "legacy_loss_without_reason_remains_editable": True,
            "no_historical_events_backfilled": True, "reservation_sync_source_verified": True,
            "same_phone_tenant_isolation": True, "lost_requires_explicit_reason": True,
            "reason_edit_and_reopen_history": True, "retry_no_duplicate_event": True,
            "actor_context_cleared_between_requests": True, "no_automatic_loss": True,
            "reservation_status_history": True, "private_history_rls_and_grants": True,
            "security_advisor": advisor_note, "production_writes": 0, "external_messages": 0}))
    finally:
        db._pool = None
        await c.close()


if __name__ == "__main__":
    asyncio.run(run())

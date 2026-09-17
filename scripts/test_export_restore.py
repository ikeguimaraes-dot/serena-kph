"""Export only synthetic units inside the disposable backup-restored database."""
import asyncio
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import uuid
import zipfile

import asyncpg
import export_customer_data as export

ROOT = Path(__file__).resolve().parents[1]


async def run():
    host = os.environ.get("PGHOST", "")
    if not host.startswith("/tmp/serena-restore-") or os.environ.get("PGDATABASE") != "serena_restore":
        raise RuntimeError("Only the isolated restored Unix-socket cluster is allowed")
    options = dict(host=host, port=int(os.environ["PGPORT"]), user=os.environ["PGUSER"], database="serena_restore", ssl=False)
    connection = await asyncpg.connect(**options)
    other = await asyncpg.connect(**options)
    try:
        for migration in ("20260917043459_ctwa_cache_commercial_reporting.sql", "20260917044853_consented_outreach_outbox.sql",
                          "20260917045116_crm_loss_reason_history.sql", "20260917050154_handoff_reliability.sql",
                          "20260917050855_reservation_outreach_schedule.sql"):
            await connection.execute((ROOT / "files/restaurant-ai/migrations" / migration).read_text())
        # A future arbitrary column must not automatically leak into portability.
        await connection.execute("ALTER TABLE contacts ADD COLUMN synthetic_private_token text")
        nonce = uuid.uuid4().hex
        a, b = "export-a-"+nonce, "export-b-"+nonce
        phone = "+12025550130"
        ids = {}
        for index, unit in enumerate((a, b)):
            marker = "SYNTHETIC_PRIVATE_"+str(index)
            await connection.execute("INSERT INTO restaurants(id,nome,whatsapp_number,ativo) VALUES($1,$1,$2,true)", unit, f"+1202555017{index}")
            contact = await connection.fetchval("INSERT INTO contacts(restaurant_id,celular,nome,synthetic_private_token) VALUES($1,$2,$3,'excluded-secret-marker') RETURNING id", unit, phone, marker)
            await connection.execute("INSERT INTO conversations(restaurant_id,user_phone,role,content,media_url) VALUES($1,$2,'user',$3,'https://example.invalid/media?token=excluded')", unit, phone, marker)
            booking = await connection.fetchval("INSERT INTO reservas(restaurant_id,cliente_phone,cliente_nome,data,hora_inicio) VALUES($1,$2,$3,$4,'19:00') RETURNING id", unit, phone, marker, date(2030,1,2))
            order = await connection.fetchval("INSERT INTO ordens_servico(restaurant_id,reserva_id,cliente_phone,cliente_nome,tipo_evento,data,hora_inicio,pessoas,valor_total) VALUES($1,$2,$3,$4,'Synthetic',$5,'19:00',1,123.45) RETURNING id", unit, booking, phone, marker, date(2030,1,2))
            await connection.execute("INSERT INTO checklist_instancias(os_id,tipo,item) VALUES($1,'pre',$2)", order, marker)
            await connection.execute("INSERT INTO reservations(id,restaurant_id,user_phone,nome,data,hora,pessoas) VALUES($1,$2,$3,$4,'2030-01-02','19:00',1)", str(uuid.uuid4()), unit, phone, marker)
            consent = await connection.fetchval("""INSERT INTO outreach_consent_events(restaurant_id,customer_phone,granted,source,occurred_at,recorded_by,evidence)
                VALUES($1,$2,false,'revocation',NOW(),'synthetic-operator','Synthetic private evidence') RETURNING id""", unit, phone)
            await connection.execute("INSERT INTO handoff_sessions(restaurant_id,user_phone,motivo) VALUES($1,$2,$3)", unit, phone, marker)
            await connection.execute("""INSERT INTO outreach_outbox(restaurant_id,object_type,object_id,stage,customer_phone,sender_phone,content_sid,consent_event_id,payload,status)
                VALUES($1,'reservation',$2,'reservation_confirmation',$3,$4,$5,$6,'{}','unknown')""", unit, str(booking), phone, f"+1202555017{index}", "HX"+"a"*32, consent)
            # Audit history survives deletion; export must scope it by its own
            # restaurant_id, without an inner join that drops the orphan event.
            orphan_phone = f"+1202555014{index}"
            orphan_contact = await connection.fetchval("INSERT INTO contacts(restaurant_id,celular,nome) VALUES($1,$2,'Synthetic orphan') RETURNING id", unit, orphan_phone)
            orphan_reservation = await connection.fetchval("INSERT INTO reservas(restaurant_id,cliente_phone,cliente_nome,data,hora_inicio) VALUES($1,$2,'Synthetic orphan',$3,'19:00') RETURNING id", unit, orphan_phone, date(2030,1,3))
            await connection.execute("DELETE FROM contacts WHERE restaurant_id=$1 AND id=$2", unit, orphan_contact)
            await connection.execute("DELETE FROM reservas WHERE restaurant_id=$1 AND id=$2", unit, orphan_reservation)
            ids[unit] = {"contact": contact, "reservation": str(booking), "orphan_contact": orphan_contact, "orphan_reservation": str(orphan_reservation)}
        with tempfile.TemporaryDirectory(prefix="serena-export-proof-", dir=Path(host).parent) as raw:
            directory = Path(raw).resolve()
            dry = await export.export_unit(connection, a)
            assert dry["dry_run"] and dry["counts"]["contacts"] == 1 and dry["counts"]["conversations"] == 1
            assert not list(directory.iterdir()) and phone not in json.dumps(dry) and "SYNTHETIC_PRIVATE" not in json.dumps(dry)
            # Independent write AFTER the reader's snapshot starts. Every file
            # and count must still reflect the same earlier snapshot.
            class ConcurrentSnapshot:
                def __init__(self, wrapped): self.wrapped, self.fired = wrapped, False
                def __getattr__(self, key): return getattr(self.wrapped, key)
                async def fetch(self, sql, *args):
                    result = await self.wrapped.fetch(sql, *args)
                    if not self.fired:
                        self.fired = True
                        assert await self.wrapped.fetchval("SHOW transaction_read_only") == "on"
                        await other.execute("INSERT INTO conversations(restaurant_id,user_phone,role,content) VALUES($1,$2,'user','Synthetic concurrent row')", a, phone)
                    return result
            output = directory / "unit-a"
            result = await export.export_unit(ConcurrentSnapshot(connection), a, output, archive=True)
            assert result["counts"] == dry["counts"]
            assert stat.S_IMODE(output.stat().st_mode) == 0o700
            assert all(stat.S_IMODE(file.stat().st_mode) == 0o600 for file in output.iterdir())
            assert not (output / ".incomplete").exists()
            manifest = json.loads((output / "manifest.json").read_text())
            assert manifest["transaction_read_only"] and manifest["transaction_isolation"] == "repeatable read"
            assert manifest["format_version"] == export.FORMAT_VERSION and manifest["tool_sha256"]
            for artifact in manifest["files"]:
                content = (output / artifact["file"]).read_bytes()
                assert hashlib.sha256(content).hexdigest() == artifact["sha256"]
                if artifact["file"].endswith(".jsonl"):
                    rows = [json.loads(line) for line in content.decode().splitlines()]
                    assert len(rows) == artifact["rows"]
                    assert all(row["restaurant_id"] == a for row in rows)
                    assert "SYNTHETIC_PRIVATE_1" not in content.decode()
                    assert "excluded-secret-marker" not in content.decode()
                    assert "?token=" not in content.decode()
            stages = [json.loads(line) for line in (output / "contact_stage_events.jsonl").read_text().splitlines()]
            outcomes = [json.loads(line) for line in (output / "reservation_status_events.jsonl").read_text().splitlines()]
            assert any(row["contact_id"] == ids[a]["orphan_contact"] for row in stages)
            assert not any(row["contact_id"] == ids[b]["orphan_contact"] for row in stages)
            assert any(row["reserva_id"] == ids[a]["orphan_reservation"] for row in outcomes)
            assert not any(row["reserva_id"] == ids[b]["orphan_reservation"] for row in outcomes)
            assert "123.45" in (output / "ordens_servico.jsonl").read_text()
            assert len((output / "reservations.jsonl").read_text().splitlines()) == 1
            assert len((output / "checklist_instancias.jsonl").read_text().splitlines()) == 1
            checklist_schema = json.loads((output / "schema.json").read_text())["checklist_instancias"]
            assert any(row.get("derived_from") == "ordens_servico.restaurant_id via os_id" for row in checklist_schema["columns"])
            with zipfile.ZipFile(output / "unit-export.zip") as package:
                assert package.testzip() is None and "manifest.json" in package.namelist()
                assert all("/" not in name for name in package.namelist())
            for line in (output / "SHA256SUMS").read_text().splitlines():
                digest, name = line.split("  ")
                assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
            try:
                await export.export_unit(connection, a, output)
            except export.ExportError:
                pass
            else:
                raise AssertionError("Existing export must not be overwritten")
            assert await other.fetchval("SELECT count(*) FROM conversations WHERE restaurant_id=$1", a) == 2
            assert (await export.export_unit(connection, b))["counts"]["conversations"] == 1
        print(json.dumps({"success": True, "tables": len(export.COLUMNS), "dry_run_contains_counts_only": True,
            "same_phone_two_units_isolated": True, "orphan_audit_history_preserved_by_own_unit": True,
            "legacy_reservations_and_os_checklist_join_tenant_scoped": True,
            "consistent_repeatable_read_snapshot_under_concurrent_write": True,
            "read_only_transaction_verified": True, "strict_column_allowlist": True,
            "mode_0700_0600": True, "jsonl_manifest_schema_checksums_and_zip_verified": True,
            "overwrite_refused": True, "exported_production_rows": 0, "external_messages": 0}))
    finally:
        await connection.close()
        await other.close()


if __name__ == "__main__": asyncio.run(run())

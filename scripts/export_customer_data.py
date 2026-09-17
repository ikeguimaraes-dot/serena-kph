#!/usr/bin/env python3
"""Read-only, one-unit JSONL portability export. Default: counts, no private rows.

No cloud/storage/message APIs, credential export, production mutations or restore.
The existing private backup config may supply the read-only source connection.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from urllib.parse import urlsplit
import zipfile

import asyncpg

FORMAT_VERSION = "serena-unit-portability-v1"
DEFAULT_CONFIG = Path.home() / ".config/serena-backup/config.json"

# Both tables AND columns are explicit. New schema columns are never exported
# automatically. No auth/users/operators, passwords, tokens, config or prompts.
# Audit tables carry their own restaurant_id, including orphan references. The
# OS checklist is scoped through its existing parent. Never infer orphan scope.
COLUMNS = {
    "contacts": "id restaurant_id celular nome sobrenome email data_nascimento endereco tipo_aparelho canal_entrada frequencia_visitas ultima_visita estagio_kanban motivo_perda motivo_perda_detalhe estagio_alterado_em notas tags lead_score lead_score_at ltv_total total_eventos ocasiao restricoes_alimentares ticket_medio tier opt_in_marketing criado_em atualizado_em".split(),
    "conversations": "id restaurant_id user_phone role content created_at media_type source_message_sid provider_message_sid ctwa_clid".split(),
    "reservas": "id restaurant_id turno_id evento_id cliente_phone cliente_nome cliente_email data hora_inicio posicoes status observacoes canal criado_em atualizado_em pagamento_status pagamento_valor confirmado_whatsapp confirmado_email ctwa_clid ctwa_source_message_sid ctwa_attributed_at".split(),
    "reservations": "id restaurant_id user_phone nome data hora pessoas observacoes status created_at".split(),
    "ordens_servico": "id restaurant_id reserva_id cliente_phone cliente_nome tipo_evento data hora_inicio pessoas valor_total valor_entrada status responsavel_evento restricoes_alimentares decoracao musico_dj horario_montagem observacoes plano ambiente addons proposta_validade titulo regua_d1_enviado_em regua_d3_enviado_em regua_d7_enviado_em regua_d30_enviado_em nps_score nps_respondido_em evento_realizado_em criado_em atualizado_em".split(),
    "checklist_instancias": "id restaurant_id os_id tipo ordem item concluido concluido_em concluido_por criado_em".split(),
    "outreach_consent_events": "id restaurant_id customer_phone purpose granted source occurred_at recorded_at recorded_by evidence".split(),
    "contact_stage_events": "id restaurant_id contact_id event_type previous_stage new_stage previous_loss_reason loss_reason previous_loss_detail loss_detail actor_operator_id source database_role occurred_at".split(),
    "reservation_status_events": "id restaurant_id reserva_id event_type previous_status new_status actor_operator_id source database_role occurred_at".split(),
    "handoff_sessions": "id restaurant_id user_phone motivo status atendente_nome created_at resolved_at assumed_at first_human_response_at last_reply_message_sid notification_status".split(),
    "outreach_outbox": "id restaurant_id object_type object_id stage customer_phone sender_phone content_sid consent_event_id payload status provider_message_sid provider_status error_code created_at finished_at".split(),
}


class ExportError(ValueError):
    pass


def validate_unit(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", value):
        raise ExportError("Informe exatamente uma unidade por ID; não há escopo global.")
    return value


def validate_output(raw: Path) -> Path:
    path = raw.expanduser()
    if not path.is_absolute():
        raise ExportError("O destino deve ser um caminho absoluto fora do código e de pastas públicas.")
    if path.exists() or path.is_symlink():
        raise ExportError("Destino já existe; sobrescrita ou reutilização não é permitida.")
    path = path.resolve()
    forbidden = {"public", "www", "wwwroot", "htdocs", "sites", "dropbox", "onedrive",
                 "googledrive", "google drive", "icloud drive", "mobile documents", "cloudstorage"}
    if any(part.lower() in forbidden for part in path.parts):
        raise ExportError("Destino público ou sincronizado com nuvem não é permitido.")
    for parent in (path, *path.parents):
        if (parent / ".git").exists():
            raise ExportError("Dados privados não podem ser exportados dentro de um repositório.")
    return path


def connection_config(path: Path) -> str:
    if path.is_symlink():
        raise ExportError("Configuração deve ser arquivo privado regular, sem symlink.")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ExportError("Configuração precisa pertencer ao usuário atual e ter permissão 0600.")
    config = json.loads(path.read_text())
    url = config.get("database_url", "")
    parsed = urlsplit(url)
    expected = config.get("expected_project_ref")
    if (parsed.scheme not in ("postgres", "postgresql") or not parsed.hostname or not parsed.password
            or not expected or expected not in parsed.hostname + (parsed.username or "") or parsed.port == 6543):
        raise ExportError("Configuração deve usar o banco esperado e conexão direta/session pooler.")
    return url


def quote(name: str) -> str:
    # Identifiers come exclusively from COLUMNS and introspection intersections.
    return '"' + name.replace('"', '""') + '"'


def scoped_source(table: str):
    if table == "checklist_instancias":
        return ("public.checklist_instancias t JOIN public.ordens_servico scoped_os ON scoped_os.id=t.os_id",
                "scoped_os.restaurant_id=$1")
    return f"public.{quote(table)} t", "t.restaurant_id=$1"


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def private_create(path: Path):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.fchmod(descriptor, 0o600)
    return os.fdopen(descriptor, "wb")


def write_artifact(directory: Path, name: str, data: bytes) -> dict:
    with private_create(directory / name) as target:
        target.write(data)
    return {"file": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def tool_commit() -> str | None:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parent,
                            capture_output=True, text=True, timeout=5)
    value = result.stdout.strip()
    return value if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", value) else None


async def inventory(connection, unit: str):
    found = await connection.fetch("""
        SELECT table_name,column_name,data_type,udt_schema,udt_name,is_nullable
        FROM information_schema.columns WHERE table_schema='public' AND table_name=ANY($1::text[])
        ORDER BY table_name,ordinal_position
    """, list(COLUMNS))
    schema, counts = {}, {}
    for table, allowed in COLUMNS.items():
        available = {row["column_name"]: dict(row) for row in found if row["table_name"] == table}
        if table == "checklist_instancias" and "os_id" in available:
            available["restaurant_id"] = {"table_name": table, "column_name": "restaurant_id", "data_type": "text",
                "udt_schema": "pg_catalog", "udt_name": "text", "is_nullable": "NO", "derived_from": "ordens_servico.restaurant_id via os_id"}
        if not {"id", "restaurant_id"}.issubset(available):
            raise ExportError(f"Schema incompleto para {table}; exportação não foi concluída.")
        columns = [column for column in allowed if column in available]
        schema[table] = {
            "columns": [{key: value for key, value in available[name].items() if key != "table_name"} for name in columns],
            "missing_optional_columns": [column for column in allowed if column not in available],
            "excluded_columns": sorted(set(available)-set(allowed)),
        }
        source, scope = scoped_source(table)
        counts[table] = await connection.fetchval(f"SELECT count(*) FROM {source} WHERE {scope}", unit)
    return schema, counts


async def export_unit(connection, unit: str, output: Path | None = None, *, archive=False):
    """Read one stable snapshot. No INSERT/UPDATE/DELETE/DDL or outbound service calls."""
    unit = validate_unit(unit)
    destination = validate_output(output) if output is not None else None
    if archive and destination is None:
        raise ExportError("--zip exige --output explícito.")
    started = datetime.now(timezone.utc).isoformat()
    async with connection.transaction(isolation="repeatable_read", readonly=True):
        isolation = await connection.fetchval("SHOW transaction_isolation")
        read_only = await connection.fetchval("SHOW transaction_read_only")
        if isolation != "repeatable read" or read_only != "on":
            raise ExportError("A origem precisa permanecer em snapshot REPEATABLE READ e READ ONLY.")
        if not await connection.fetchval("SELECT EXISTS(SELECT 1 FROM public.restaurants WHERE id=$1)", unit):
            raise ExportError("Unidade não encontrada; nenhum arquivo de cliente foi criado.")
        snapshot = await connection.fetchval("SELECT pg_current_snapshot()::text")
        server_version = await connection.fetchval("SHOW server_version")
        schema, counts = await inventory(connection, unit)
        summary = {"format_version": FORMAT_VERSION, "restaurant_id": unit,
                   "dry_run": destination is None, "counts": counts, "total_rows": sum(counts.values()),
                   "transaction_isolation": isolation, "transaction_read_only": True}
        if destination is None:
            return summary
        old_mask = os.umask(0o077)
        try:
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            destination.mkdir(mode=0o700, exist_ok=False)
        finally:
            os.umask(old_mask)
        marker = destination / ".incomplete"
        with private_create(marker) as stream:
            stream.write(b"Export incomplete until manifest and checksums exist.\n")
        artifacts = []
        for table in COLUMNS:
            names = [column["column_name"] for column in schema[table]["columns"]]
            projection = ",".join("scoped_os.restaurant_id AS restaurant_id" if table == "checklist_instancias" and name == "restaurant_id"
                                  else "t."+quote(name) for name in names)
            source, scope = scoped_source(table)
            sql = (f"SELECT row_to_json(export_row)::text AS record FROM "
                   f"(SELECT {projection} FROM {source} WHERE {scope} ORDER BY t.id) export_row")
            digest = hashlib.sha256()
            rows, length = 0, 0
            filename = table + ".jsonl"
            with private_create(destination / filename) as target:
                async for row in connection.cursor(sql, unit, prefetch=200):
                    data = (row["record"] + "\n").encode("utf-8")
                    target.write(data)
                    digest.update(data)
                    rows += 1
                    length += len(data)
            if rows != counts[table]:
                raise ExportError("Contagem inconsistente: exportação incompleta, sem manifesto final.")
            artifacts.append({"file": filename, "rows": rows, "bytes": length, "sha256": digest.hexdigest()})
        artifacts.append(write_artifact(destination, "schema.json", json_bytes(schema)))
        manifest = {**summary, "created_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
            "tool_commit": tool_commit(), "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "database_schema": "public", "server_version": server_version,
            "snapshot": snapshot, "files": artifacts,
            "scope": "Exact restaurant_id on operational/audit tables; checklist joined only to an existing OS of the unit. Orphan audit records retained by their own unit, checklist ownership never inferred.",
            "json_encoding": "PostgreSQL row_to_json, UTF-8 JSONL; decimals retain source numeric representation; timestamps retain offsets.",
            "excluded": ["auth/users/operators and credentials", "restaurant/config secrets", "prompts", "media URLs and binary objects", "billing-provider identifiers"],
            "limitations": ["Portability export, not a database backup or automatic restore package.",
                "No binary media/storage copy; references may be absent or not independently usable.",
                "Audit IDs are retained even if parent operational rows were deleted.",
                "No inferred consent, outcome, origin or historical events.",
                "No automatic deletion, cloud upload, provider request or retention change."]}
        manifest_artifact = write_artifact(destination, "manifest.json", json_bytes(manifest))
        checksums = "".join(f"{item['sha256']}  {item['file']}\n" for item in [*artifacts, manifest_artifact])
        write_artifact(destination, "SHA256SUMS", checksums.encode())
        if archive:
            with private_create(destination / "unit-export.zip") as stream:
                with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as package:
                    for filename in [item["file"] for item in artifacts] + ["manifest.json", "SHA256SUMS"]:
                        package.write(destination / filename, arcname=filename)
        marker.unlink()
        return {**summary, "output": str(destination), "manifest_sha256": manifest_artifact["sha256"], "zip": archive}


async def main_async(args):
    unit = validate_unit(args.restaurant_id)
    if args.output is not None:
        validate_output(args.output)
    url = connection_config(args.config.expanduser())
    connection = await asyncpg.connect(url, ssl="require", timeout=20, statement_cache_size=0,
        server_settings={"timezone": "UTC", "default_transaction_read_only": "on", "statement_timeout": "120000"})
    try:
        return await export_unit(connection, unit, args.output, archive=args.zip)
    finally:
        await connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restaurant-id", required=True, help="ID de exatamente uma unidade")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Configuração privada 0600 do backup existente")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--dry-run", action="store_true", help="Padrão: somente contagens, nenhum dado pessoal ou arquivo")
    operation.add_argument("--output", type=Path, help="Diretório privado NOVO, absoluto, fora do Git e de pastas públicas/nuvem")
    parser.add_argument("--zip", action="store_true", help="Empacotar também ZIP privado no diretório de saída")
    args = parser.parse_args()
    if args.zip and args.output is None:
        parser.error("--zip exige --output")
    try:
        print(json.dumps(asyncio.run(main_async(args)), ensure_ascii=False))
    except ExportError as error:
        print(f"Exportação recusada: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        # Exceptions from the driver/config may contain credentials or private rows.
        print(f"Exportação não concluída ({type(error).__name__}); confira configuração/conexão e arquivos .incomplete.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

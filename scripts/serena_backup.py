#!/usr/bin/env python3
"""Private logical PostgreSQL backup and disposable, socket-only restore drill.

Requires Python 3.11+, asyncpg, and PostgreSQL binaries matching the source major.
Source connections are read-only. Restore never accepts a destination URL.
"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, urlsplit

import asyncpg


SCHEMAS = ("public", "auth", "storage", "supabase_migrations")
FORMAT = 1


def private_dir(path: Path) -> Path:
    if path.is_symlink():
        raise ValueError("Private directory must not be a symlink")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.stat().st_uid != os.getuid():
        raise ValueError("Private directory has a different owner")
    path.chmod(0o700)
    return path


def private_write(path: Path, content: str | bytes):
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as target:
        os.fchmod(target.fileno(), 0o600)
        target.write(content.encode() if isinstance(content, str) else content)


def json_write(path: Path, value):
    private_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def config_load(path: Path) -> dict:
    if path.is_symlink() or path.stat().st_uid != os.getuid():
        raise ValueError("Config must be a regular file owned by the current user")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("Config contains credentials and must have mode 0600")
    config = json.loads(path.read_text())
    source = urlsplit(config["database_url"])
    if source.scheme not in ("postgres", "postgresql") or not source.hostname or not source.password:
        raise ValueError("Missing PostgreSQL source connection parameters")
    if source.port == 6543:
        raise ValueError("Use the session pooler on port 5432, not transaction pooling")
    expected = config["expected_project_ref"]
    if expected not in (source.hostname + (source.username or "")):
        raise ValueError("Source does not match expected_project_ref")
    root = Path(config["backup_root"]).expanduser().resolve()
    # Secrets and private rows must never land in a git worktree.
    for parent in (root, *root.parents):
        if (parent / ".git").exists():
            raise ValueError("backup_root must be outside all git worktrees")
    config["backup_root"] = str(private_dir(root))
    if not 2 <= int(config.get("retention_days", 30)) <= 3650:
        raise ValueError("retention_days must be between 2 and 3650")
    return config


def pg_env(url: str) -> dict:
    source = urlsplit(url)
    env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    env.update(
        PGHOST=source.hostname, PGPORT=str(source.port or 5432),
        PGUSER=unquote(source.username or "postgres"),
        PGPASSWORD=unquote(source.password or ""),
        PGDATABASE=unquote(source.path.lstrip("/") or "postgres"),
        PGSSLMODE="require", PGCONNECT_TIMEOUT="20",
        PGOPTIONS="-c default_transaction_read_only=on -c statement_timeout=600000",
        LC_ALL="C", TZ="UTC",
    )
    return env


def binary(config: dict, name: str) -> str:
    path = Path(config["pg_bin"]) / name
    if not path.is_file():
        raise ValueError(f"PostgreSQL binary unavailable: {name}")
    return str(path)


def command(args: list[str], env: dict, log: Path, *, input_data: bytes | None = None,
            timeout: int = 600) -> bytes:
    result = subprocess.run(args, env=env, input=input_data, capture_output=True, timeout=timeout)
    if result.stderr:
        fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "ab") as stream:
            stream.write(result.stderr)
    if result.returncode:
        raise RuntimeError(f"{Path(args[0]).name} failed; private details: {log}")
    return result.stdout


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


async def table_inventory(connection, schemas: list[str]) -> dict:
    tables = await connection.fetch(
        "SELECT schemaname, tablename FROM pg_tables WHERE schemaname=ANY($1::text[]) "
        "ORDER BY schemaname, tablename", schemas)
    result = {}
    for row in tables:
        table = f"{quote_identifier(row['schemaname'])}.{quote_identifier(row['tablename'])}"
        # Sorted row hashes avoid retaining personal data or query-order assumptions.
        count, digest = 0, hashlib.sha256()
        async for hashed in connection.cursor(
            f"SELECT md5(row_to_json(t)::text) AS hash FROM {table} t ORDER BY hash", prefetch=500):
            digest.update(hashed["hash"].encode("ascii"))
            count += 1
        result[f"{row['schemaname']}.{row['tablename']}"] = {"rows": count, "sha256_rows": digest.hexdigest()}
    return result


async def create_backup(config: dict) -> Path:
    root = Path(config["backup_root"])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    working = private_dir(root / (".partial-" + stamp))
    log = working / "private-operation.log"
    env = pg_env(config["database_url"])
    connection = await asyncpg.connect(config["database_url"], ssl="require", timeout=20,
                                       statement_cache_size=0, server_settings={"timezone": "UTC"})
    try:
        async with connection.transaction(isolation="repeatable_read", readonly=True):
            server_version = await connection.fetchval("SHOW server_version")
            dump_version = command([binary(config, "pg_dump"), "--version"], env, log).decode().strip()
            major = int(re.search(r"PostgreSQL\) (\d+)", dump_version).group(1))
            if major != int(server_version.split(".")[0]):
                raise RuntimeError("pg_dump and source server major versions must match")
            snapshot = await connection.fetchval("SELECT pg_export_snapshot()")
            schemas = [r["nspname"] for r in await connection.fetch(
                "SELECT nspname FROM pg_namespace WHERE nspname=ANY($1::text[]) ORDER BY nspname", list(SCHEMAS))]
            if "public" not in schemas:
                raise RuntimeError("Public application schema is missing")
            roles = [r["rolname"] for r in await connection.fetch(
                "SELECT rolname FROM pg_roles WHERE rolname !~ '^pg_' ORDER BY rolname")]
            extensions = [dict(r) for r in await connection.fetch(
                "SELECT e.extname, e.extversion, n.nspname AS schema FROM pg_extension e "
                "JOIN pg_namespace n ON n.oid=e.extnamespace")]
            common = [binary(config, "pg_dump"), "--snapshot", snapshot, "--no-owner", "--lock-wait-timeout=10s"]
            for schema in schemas:
                common.extend(["--schema", schema])
            # The exporter transaction stays open while pg_dump imports its snapshot.
            await asyncio.to_thread(command, common + ["--format=custom", "--file", str(working / "database.dump")], env, log)
            await asyncio.to_thread(command, common + ["--schema-only", "--file", str(working / "schema.sql")], env, log)
            inventory = await table_inventory(connection, schemas)
            manifest = {
                "format": FORMAT, "created_at": datetime.now(timezone.utc).isoformat(),
                "project_ref": config["expected_project_ref"], "server_version": server_version,
                "pg_dump_version": dump_version, "schemas": schemas, "roles": roles,
                "extensions": extensions, "tables": inventory,
                "scope": "Selected schemas including data, sequences, functions, constraints, RLS and grants",
                "excluded": ["storage object binaries", "provider configuration and API secrets", "realtime schema", "vault encryption keys"],
                "restore_verified": False,
            }
    finally:
        await connection.close()
    for name in ("database.dump", "schema.sql"):
        (working / name).chmod(0o600)
    manifest["artifacts"] = {name: {"sha256": digest_file(working / name), "bytes": (working / name).stat().st_size}
                             for name in ("database.dump", "schema.sql")}
    json_write(working / "manifest.json", manifest)
    final = root / stamp
    working.rename(final)
    return final


def verify_artifacts(backup: Path) -> dict:
    manifest = json.loads((backup / "manifest.json").read_text())
    if manifest["format"] != FORMAT:
        raise ValueError("Unknown backup format")
    for name, expected in manifest["artifacts"].items():
        if name not in ("database.dump", "schema.sql"):
            raise ValueError("Unexpected artifact name")
        path = backup / name
        if path.is_symlink() or path.stat().st_size != expected["bytes"] or digest_file(path) != expected["sha256"]:
            raise ValueError(f"Artifact integrity failed: {name}")
    return manifest


async def restore_drill(config: dict, backup: Path, hook: Path | None = None) -> dict:
    manifest = verify_artifacts(backup)
    started = datetime.now(timezone.utc)
    log = backup / "private-restore.log"
    # No user-supplied restore host/URL exists. Only this new private socket is used.
    with tempfile.TemporaryDirectory(prefix="serena-restore-", dir="/tmp") as directory:
        temp = private_dir(Path(directory))
        socket = private_dir(temp / "socket")
        data = temp / "data"
        env = {k: os.environ[k] for k in ("PATH", "HOME", "USER", "LOGNAME", "TMPDIR") if k in os.environ}
        env.update(PGHOST=str(socket), PGPORT="55439", PGUSER="restore_admin",
                   PGDATABASE="postgres", LC_ALL="C", TZ="UTC", PGCONNECT_TIMEOUT="10")
        command([binary(config, "initdb"), "-D", str(data), "-U", "restore_admin",
                 "--auth-local=trust", "--auth-host=reject", "--no-locale", "-E", "UTF8"], env, log)
        running = False
        try:
            command([binary(config, "pg_ctl"), "-D", str(data), "-l", str(temp / "postgres.log"),
                     "-o", f"-h '' -k {socket} -p 55439", "-w", "start"], env, log)
            running = True
            command([binary(config, "createdb"), "serena_restore"], env, log)
            env["PGDATABASE"] = "serena_restore"
            # Role names preserve policy/grant targets; no password or privileged login is restored.
            bootstrap = "\n".join(
                f"CREATE ROLE {quote_identifier(role)} NOLOGIN;" for role in manifest["roles"]
                if role not in ("restore_admin", "public") and not role.startswith("pg_"))
            # initdb creates an empty public schema; the archive restores its original definition.
            bootstrap += '\nDROP SCHEMA public;\nCREATE SCHEMA IF NOT EXISTS extensions;\n'
            for extension in manifest["extensions"]:
                if extension["extname"] in ("pgcrypto", "uuid-ossp"):
                    bootstrap += f"CREATE EXTENSION IF NOT EXISTS {quote_identifier(extension['extname'])} WITH SCHEMA extensions;\n"
            command([binary(config, "psql"), "-X", "-v", "ON_ERROR_STOP=1"], env, log, input_data=bootstrap.encode())
            await asyncio.to_thread(command, [binary(config, "pg_restore"), "--exit-on-error", "--single-transaction",
                                              "--no-owner", "--dbname", "serena_restore", str(backup / "database.dump")], env, log)
            connection = await asyncpg.connect(host=str(socket), port=55439, user="restore_admin",
                                               database="serena_restore", server_settings={"timezone": "UTC"})
            try:
                async with connection.transaction(readonly=True):
                    actual = await table_inventory(connection, manifest["schemas"])
                    if actual != manifest["tables"]:
                        raise RuntimeError("Restored row counts/hashes differ from the backup snapshot")
                    prompt_rows = await connection.fetchval("SELECT count(*) FROM public.serena_prompt_versions")
                    report = {
                        "verified_at": datetime.now(timezone.utc).isoformat(),
                        "duration_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 2),
                        "restore_target": "disposable local PostgreSQL, Unix socket only, deleted after test",
                        "tables_verified": len(actual), "rows_verified": sum(t["rows"] for t in actual.values()),
                        "prompt_versions_verified": prompt_rows,
                        "comparison": "Exact table set, row count and order-independent row hashes from one source snapshot",
                        "success": True,
                    }
            finally:
                await connection.close()
            if hook:
                output = await asyncio.to_thread(command, [sys.executable, str(hook.resolve())], env, log)
                private_write(backup / "restore-hook.log", output)
                report["local_integration_hook"] = {"file": hook.name, "sha256": digest_file(hook), "success": True}
        finally:
            if running:
                command([binary(config, "pg_ctl"), "-D", str(data), "-m", "immediate", "-w", "stop"], env, log)
    report["verified_at"] = datetime.now(timezone.utc).isoformat()
    report["duration_seconds"] = round((datetime.now(timezone.utc) - started).total_seconds(), 2)
    json_write(backup / "restore-proof.json", report)
    manifest["restore_verified"] = True
    manifest["restored_at"] = report["verified_at"]
    json_write(backup / "manifest.json", manifest)
    return report


def retention(config: dict):
    root = Path(config["backup_root"])
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(config.get("retention_days", 30)))
    verified = []
    for child in root.iterdir():
        if child.is_symlink() or not child.is_dir() or not re.fullmatch(r"\d{8}T\d{6}\.\d{6}Z", child.name):
            continue
        manifest = json.loads((child / "manifest.json").read_text())
        if manifest.get("restore_verified"):
            verified.append((datetime.fromisoformat(manifest["created_at"]), child))
    # Always retain the two newest verified backups, even after a long outage.
    for created, path in sorted(verified, reverse=True)[2:]:
        if created < cutoff:
            shutil.rmtree(path)


async def run(args):
    os.umask(0o077)
    config = config_load(args.config)
    root = Path(config["backup_root"])
    if args.status:
        success = json.loads((root / "last-success.json").read_text())
        manifest = verify_artifacts(Path(success["backup"]))
        # Re-restoring an old snapshot must never make an old backup look fresh.
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(manifest["created_at"])).total_seconds() / 3600
        print(json.dumps({"healthy": age <= 36, "age_hours": round(age, 2), "backup": success["backup"]}))
        if age > 36:
            raise SystemExit(2)
        return
    lock_fd = os.open(root / ".backup.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        backup = args.backup.resolve() if args.backup else await create_backup(config)
        report = await restore_drill(config, backup, args.restore_hook)
        retention(config)
        json_write(root / "last-success.json", {"backup": str(backup), **report})
        print(json.dumps({"backup": str(backup), **report}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Private JSON config, mode 0600")
    parser.add_argument("--backup", type=Path, help="Only verify/restore this existing backup locally")
    parser.add_argument("--restore-hook", type=Path, help="Optional Python integration test executed in the disposable local DB")
    parser.add_argument("--status", action="store_true", help="Check archive integrity and age; exit 2 if older than 36 hours")
    try:
        asyncio.run(run(parser.parse_args()))
    except Exception as error:
        print(f"Backup/restore FAILED: {type(error).__name__}: {error}")
        raise SystemExit(1)

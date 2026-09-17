"""Offline integrity/retention/security tests; no remote connection is opened."""
import json
import asyncio
import os
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from contextlib import redirect_stdout
import io

import serena_backup as backup


class BackupSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = self.root / "config.json"
        self.value = {
            "database_url": "postgresql://postgres.fixture:test-only@example.fixture:5432/postgres",
            "expected_project_ref": "fixture", "pg_bin": "/unused",
            "backup_root": str(self.root / "backups"), "retention_days": 30,
        }
        backup.json_write(self.config, self.value)

    def test_refuses_world_readable_credentials(self):
        self.config.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "0600"):
            backup.config_load(self.config)

    def test_refuses_credentials_source_mismatch(self):
        self.value["expected_project_ref"] = "different-project"
        backup.json_write(self.config, self.value)
        with self.assertRaisesRegex(ValueError, "expected_project_ref"):
            backup.config_load(self.config)

    def test_refuses_backup_destination_inside_git_worktree(self):
        (self.root / ".git").write_text("gitdir: /example/worktree")
        with self.assertRaisesRegex(ValueError, "outside all git"):
            backup.config_load(self.config)

    def test_refuses_transaction_pooler(self):
        self.value["database_url"] = self.value["database_url"].replace(":5432/", ":6543/")
        backup.json_write(self.config, self.value)
        with self.assertRaisesRegex(ValueError, "session pooler"):
            backup.config_load(self.config)

    def test_secret_files_and_output_directory_are_private(self):
        config = backup.config_load(self.config)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(Path(config["backup_root"]).stat().st_mode & 0o777, 0o700)

    def test_integrity_detects_same_size_content_corruption(self):
        artifact = self.root / "database.dump"
        artifact.write_bytes(b"dump")
        backup.json_write(self.root / "manifest.json", {"format": 1, "artifacts": {
            "database.dump": {"bytes": 4, "sha256": backup.digest_file(artifact)},
        }})
        backup.verify_artifacts(self.root)
        artifact.write_bytes(b"oops")
        with self.assertRaisesRegex(ValueError, "integrity"):
            backup.verify_artifacts(self.root)

    def test_retention_keeps_newest_two_and_unverified_backup(self):
        config = backup.config_load(self.config)
        root = Path(config["backup_root"])
        paths = []
        for index in range(4):
            created = datetime.now(timezone.utc) - timedelta(days=60 - index)
            directory = root / created.strftime("%Y%m%dT%H%M%S.%fZ")
            directory.mkdir()
            backup.json_write(directory / "manifest.json", {
                "created_at": created.isoformat(), "restore_verified": index != 3,
            })
            paths.append(directory)
        backup.retention(config)
        self.assertFalse(paths[0].exists())
        self.assertTrue(all(p.exists() for p in paths[1:]))

    def test_private_write_refuses_symlink(self):
        original = self.root / "original"
        original.write_text("preserve")
        link = self.root / "linked"
        link.symlink_to(original)
        with self.assertRaises(OSError):
            backup.private_write(link, "overwrite")
        self.assertEqual(original.read_text(), "preserve")

    def test_restoring_old_snapshot_does_not_make_status_fresh(self):
        config = backup.config_load(self.config)
        root = Path(config["backup_root"])
        snapshot = root / "old"
        snapshot.mkdir()
        archive = snapshot / "database.dump"
        archive.write_bytes(b"dump")
        backup.json_write(snapshot / "manifest.json", {
            "format": 1, "created_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
            "artifacts": {"database.dump": {"bytes": 4, "sha256": backup.digest_file(archive)}},
        })
        backup.json_write(root / "last-success.json", {
            "backup": str(snapshot), "verified_at": datetime.now(timezone.utc).isoformat(),
        })
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as error:
            asyncio.run(backup.run(SimpleNamespace(config=self.config, status=True)))
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

"""Offline path/config contracts; no real account or data access."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts import export_customer_data as export


class ExportContracts(unittest.TestCase):
    def test_one_explicit_unit(self):
        self.assertEqual(export.validate_unit("meet_and_eat"), "meet_and_eat")
        for value in (None, "", "*", "all units", "a,b", "x'; DROP TABLE contacts", "a"*121):
            with self.assertRaises(export.ExportError):
                export.validate_unit(value)

    def test_no_repo_public_cloud_or_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="serena-export-contract-") as raw:
            root = Path(raw).resolve()
            with self.assertRaises(export.ExportError):
                export.validate_output(root)
            with self.assertRaises(export.ExportError):
                export.validate_output(Path("relative/new-export"))
            repo = root / "repo"
            repo.mkdir()
            (repo / ".git").write_text("gitdir: /elsewhere")
            for blocked in (repo / "private/export", root / "public/export", root / "CloudStorage/export", root / "Dropbox/export"):
                with self.assertRaises(export.ExportError):
                    export.validate_output(blocked)
            linked = root / "alias"
            linked.symlink_to(repo, target_is_directory=True)
            with self.assertRaises(export.ExportError):
                export.validate_output(linked / "new-export")
            self.assertEqual(export.validate_output(root / "private/new-export"), root / "private/new-export")

    def test_configuration_permissions_and_project_scope(self):
        with tempfile.TemporaryDirectory(prefix="serena-export-contract-") as raw:
            path = Path(raw) / "config.json"
            value = {"database_url": "postgresql://postgres.synthetic:fake-password@synthetic.example.invalid:5432/postgres",
                     "expected_project_ref": "synthetic"}
            path.write_text(json.dumps(value)); path.chmod(0o600)
            self.assertEqual(export.connection_config(path), value["database_url"])
            path.chmod(0o644)
            with self.assertRaises(export.ExportError): export.connection_config(path)
            path.chmod(0o600)
            for invalid in ({**value, "expected_project_ref": "another-project"},
                            {**value, "database_url": value["database_url"].replace(":5432", ":6543")}):
                path.write_text(json.dumps(invalid))
                with self.assertRaises(export.ExportError): export.connection_config(path)

    def test_allowlist_excludes_credentials_and_signed_media(self):
        self.assertNotIn("operadores", export.COLUMNS)
        self.assertNotIn("restaurants", export.COLUMNS)
        self.assertNotIn("users", export.COLUMNS)
        self.assertNotIn("media_url", export.COLUMNS["conversations"])
        self.assertFalse(any("password" in name or "token" in name for names in export.COLUMNS.values() for name in names))


if __name__ == "__main__": unittest.main()

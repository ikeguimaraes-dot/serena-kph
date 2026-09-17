#!/usr/bin/env python3
"""Prepare a concrete daily launchd job; does not load or activate the schedule."""
import argparse
import os
from pathlib import Path
import plistlib
import sys

from serena_backup import config_load, private_dir, private_write


def prepare(config_path: Path, python_path: Path) -> Path:
    config = config_load(config_path)
    runtime = private_dir(Path.home() / ".local/lib/serena-backup")
    script = runtime / "serena_backup.py"
    private_write(script, Path(__file__).with_name("serena_backup.py").read_bytes())
    script.chmod(0o700)
    root = Path(config["backup_root"])
    prepared = private_dir(root / "prepared")
    for name in ("launchd.stdout.log", "launchd.stderr.log"):
        path = root / name
        if not path.exists():
            private_write(path, "")
    job = {
        "Label": "com.serena.backup",
        "ProgramArguments": [str(python_path.absolute()), str(script), "--config", str(config_path.resolve())],
        "StartCalendarInterval": {"Hour": 3, "Minute": 15},
        "RunAtLoad": False,
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "Umask": 0o077,
        "StandardOutPath": str(root / "launchd.stdout.log"),
        "StandardErrorPath": str(root / "launchd.stderr.log"),
        "EnvironmentVariables": {"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONUNBUFFERED": "1"},
    }
    target = prepared / "com.serena.backup.plist"
    private_write(target, plistlib.dumps(job))
    print(f"Prepared, NOT activated: {target}")
    print(f"Runtime script: {script}")
    return target


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    arguments = parser.parse_args()
    prepare(arguments.config, arguments.python)

"""Install only the audited package, never logs, tests, Git history or credentials."""
import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ledger import collector  # noqa: E402


def install(args):
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11 or newer is required")
    target = Path(args.install_dir).expanduser().resolve()
    data = target / "employee-data"
    source = ROOT / "ledger"
    app = target / "app"
    if target in (ROOT, Path.home().resolve(), Path(target.anchor)) or ROOT.is_relative_to(target) or target.is_relative_to(source):
        raise SystemExit("Choose an install directory outside the source package")
    if target.exists() and any(target.iterdir()) and not (data / "config.json").is_file():
        raise SystemExit("Install directory is not empty and is not a Team Token Ledger installation")
    target.mkdir(parents=True, exist_ok=True)
    os.chmod(target, 0o700)
    # Preserve configuration/cursors on repeat installation, but never silently re-pair.
    if (data / "config.json").exists():
        from ledger.common import read_json
        old, new = read_json(data / "config.json"), read_json(args.enrollment)
        if old.get("token") != new.get("token"):
            raise SystemExit("Existing installation uses another pairing. Uninstall or use a different install directory")
    else:
        collector.init(args.enrollment, data, args.codex_home, args.content_mode, args.project, args.allow_http)
    shutil.copytree(source, app / "ledger", dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    # A real first collection checks upload, including the final heartbeat.
    collector.run_once(data)
    if args.macos:
        plist = Path.home() / "Library/LaunchAgents/com.teamtokenledger.employee.plist"
        plist.parent.mkdir(parents=True, exist_ok=True)
        payload = {"Label": "com.teamtokenledger.employee", "ProgramArguments": [sys.executable, "-m", "ledger", "collect", "--data", str(data)],
                   "WorkingDirectory": str(app), "RunAtLoad": True, "StartInterval": 300,
                   "StandardOutPath": "/dev/null", "StandardErrorPath": "/dev/null", "ProcessType": "Background"}
        plist.write_bytes(plistlib.dumps(payload))
        plist.chmod(0o600)
        domain = f"gui/{os.getuid()}"
        subprocess.run(["launchctl", "bootout", domain, str(plist)], capture_output=True)
        subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True)
        subprocess.run(["launchctl", "kickstart", domain + "/com.teamtokenledger.employee"], check=True)
    print(json.dumps({"installed": str(target), "data": str(data), "app": str(app), "python": sys.executable}))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--enrollment", required=True)
    p.add_argument("--install-dir", default=str(Path.home() / ".team-token-ledger"))
    p.add_argument("--codex-home", default=os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    p.add_argument("--content-mode", choices=("labels", "excerpts"), default="labels")
    p.add_argument("--project", action="append", default=[])
    p.add_argument("--allow-http", action="store_true")
    p.add_argument("--macos", action="store_true")
    install(p.parse_args())

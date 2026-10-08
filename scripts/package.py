"""Build a clean source ZIP using an explicit publication allowlist."""
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP = ("README.md", "AGENTS.md", "CLAUDE.md", "PRODUCT.md", "SETUP.md", "SECURITY.md", "CHANGELOG.md", "LICENSE", ".gitignore", ".gitattributes", ".dockerignore", "Dockerfile", "compose.yaml")
FOLDERS = ("ledger", "employee", "boss", "docs", "scripts", "tests", ".github")
SUFFIXES = {".py", ".html", ".js", ".css", ".ps1", ".sh", ".md", ".png", ".yml"}


def manifest():
    files = [ROOT / name for name in TOP]
    for folder in FOLDERS:
        files += [p for p in (ROOT / folder).rglob("*") if p.is_file() and p.suffix in SUFFIXES and "__pycache__" not in p.parts]
    return sorted(files)


def inspect(files):
    patterns = [r"gh[pousr]_[A-Za-z0-9]{30,}", r"github_pat_[A-Za-z0-9_]{30,}",
                r"sk-[A-Za-z0-9_-]{25,}", r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"]
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError("Publication files must stay inside the package")
        if path.suffix == ".png":
            continue  # Review synthetic screenshots visually before publishing.
        body = path.read_text(encoding="utf-8-sig")
        if any(re.search(p, body) for p in patterns):
            raise ValueError("Potential secret in " + str(path.relative_to(ROOT)))
        if path.suffix == ".ps1" and not path.read_bytes().startswith(b"\xef\xbb\xbf"):
            raise ValueError("PowerShell script needs UTF-8 BOM: " + str(path.relative_to(ROOT)))
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    files = manifest()
    inspect(files)
    if args.list:
        print("\n".join(str(p.relative_to(ROOT)).replace("\\", "/") for p in files))
    else:
        output = ROOT / "dist/team-token-ledger-0.1.0.zip"
        output.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, "team-token-ledger/" + str(path.relative_to(ROOT)).replace("\\", "/"))
        checksum = hashlib.sha256(output.read_bytes()).hexdigest()
        output.with_suffix(".zip.sha256").write_text(checksum + "  " + output.name + "\n")
        print(json.dumps({"archive": str(output.relative_to(ROOT)), "files": len(files), "bytes": output.stat().st_size, "sha256": checksum}))

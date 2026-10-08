import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stamp(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timestamp must have timezone")
    return dt.astimezone(timezone.utc)


def digest(value):
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode()).hexdigest()


def private_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temp = path.with_suffix(path.suffix + ".tmp")
    with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
        f.write(value)
    temp.replace(path)
    os.chmod(path, 0o600)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def safe_endpoint(url, allow_http=False):
    parsed = urlparse(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("Use a server origin without credentials, path, query or fragment")
    local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if not parsed.hostname or parsed.scheme not in ("http", "https"):
        raise ValueError("Invalid endpoint")
    if parsed.scheme != "https" and not local and not allow_http:
        raise ValueError("Remote endpoints require HTTPS; HTTP only for an explicitly approved LAN test")
    return url.rstrip("/")


def counts(raw):
    if not isinstance(raw, dict) or any(k not in raw for k in ("input_tokens", "output_tokens")):
        raise ValueError("Missing token counters")
    result = {k: raw.get(k, 0) for k in FIELDS}
    if any(type(v) is not int or v < 0 or v > 10**15 for v in result.values()):
        raise ValueError("Invalid token counters")
    if result["cached_input_tokens"] > result["input_tokens"] or result["reasoning_output_tokens"] > result["output_tokens"]:
        raise ValueError("Invalid subset counters")
    return result


def excerpt(value):
    """Best effort only. Opt-in text may still contain sensitive business data."""
    value = re.sub(r"https?://\S+", "[網址省略]", value)
    value = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[email省略]", value)
    value = re.sub(r"(?i)\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]+", "[金鑰省略]", value)
    value = re.sub(r"(?i)(api[_ -]?key|password|secret|authorization)\s*[:=]\s*\S+", r"\1=[省略]", value)
    return " ".join(value.split())[:180]

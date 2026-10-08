"""Incremental, fail-closed reader for local Codex session JSONL."""
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from .common import FIELDS, counts, digest, excerpt, now, private_write, read_json, safe_endpoint, stamp


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Endpoint redirected; update the enrollment origin explicitly")


def post(url, token, body):
    request = urllib.request.Request(url, json.dumps(body).encode(),
                                     {"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as r:
        return json.load(r)


def connect(path):
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, offset INTEGER, state TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY, body TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS seen(id TEXT PRIMARY KEY)")
    db.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)")
    return db


def sources(home):
    for folder in ("sessions", "archived_sessions"):
        root = Path(home) / folder
        if root.exists():
            yield from sorted(root.rglob("*.jsonl"))


def init(enrollment, data, codex_home, content_mode="labels", projects=None, allow_http=False):
    target = Path(data)
    target.mkdir(parents=True, exist_ok=True)
    os.chmod(target, 0o700)
    if (target / "config.json").exists():
        raise ValueError("Already enrolled; do not reset the baseline. Use the existing install or a new data directory")
    config = read_json(enrollment)
    config["endpoint"] = safe_endpoint(config["endpoint"], allow_http)
    if not isinstance(config.get("token"), str) or len(config["token"]) < 24:
        raise ValueError("Invalid enrollment token")
    config.update(codex_home=str(Path(codex_home).expanduser().resolve()), since=now(),
                  content_mode=content_mode, projects=[str(Path(p).expanduser().resolve()) for p in (projects or [])],
                  allow_http=allow_http)
    # Prove pairing before writing a local installation.
    post(config["endpoint"] + "/api/ingest", config["token"], {"events": [], "status": {"phase": "enrolling"}})
    db = connect(target / "collector.db")
    try:
        scan(config, db, baseline=True)
    finally:
        db.close()
    private_write(target / "config.json", json.dumps(config, ensure_ascii=False, indent=2))


def inside_project(cwd, projects):
    if not projects:
        return True
    try:
        current = Path(cwd).resolve()
        return any(current.is_relative_to(Path(p).resolve()) for p in projects)
    except (ValueError, OSError):
        return False


def consume(record, state, config):
    kind, payload = record.get("type"), record.get("payload") or {}
    if not isinstance(payload, dict):
        return None
    if kind == "session_meta":
        state["session"] = str(payload.get("id") or payload.get("session_id") or "unknown")[:120]
        cwd = str(payload.get("cwd", ""))
        state["allowed"] = inside_project(cwd, config.get("projects", []))
        state["project"] = cwd.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1][:80] or "未命名專案"
    elif kind == "turn_context":
        state["model"] = str(payload.get("model", "unknown"))[:80]
    elif kind == "response_item" and payload.get("role") == "user":
        content = payload.get("content", [])
        texts = [c.get("text", "") for c in content if isinstance(c, dict) and isinstance(c.get("text"), str)]
        text = " ".join(texts).strip()
        # Codex injects configuration and environment in user-role records too.
        if text and not any(marker in text for marker in ("<environment_context>", "<INSTRUCTIONS>", "# AGENTS.md", "<permissions instructions>", "<system-reminder>")):
            if config.get("content_mode") == "excerpts":
                state["task"] = excerpt(text)
    if kind != "event_msg" or payload.get("type") != "token_count":
        return None
    info = payload.get("info")
    if not isinstance(info, dict) or not info.get("total_token_usage"):
        return None  # rate-limit-only notices are not usage records
    total = counts(info["total_token_usage"])
    prev = state.get("total")
    state["total"] = total
    when = record.get("timestamp")
    moment = stamp(when)
    if prev == total:
        return None
    if prev is None:
        # A new file can start with inherited/forked cumulative history.
        # Only attribute the observed last request, never its unobserved prefix.
        last = info.get("last_token_usage")
        if not last:
            raise ValueError("First counter has no last-request evidence")
        delta = counts(last)
        if any(delta[k] > total[k] for k in FIELDS):
            raise ValueError("Last request exceeds cumulative total")
    else:
        delta = {k: total[k] - prev[k] for k in FIELDS}
        if any(v < 0 for v in delta.values()):
            raise ValueError("Counter reset: establish new baseline without attributing this interval")
        delta = counts(delta)
    if moment < stamp(config["since"]) or not state.get("allowed", True):
        return None
    # Exclude session ID: forks/imports may rename a copied session.
    identity = digest({"timestamp": moment.isoformat(), "total": total})
    return {"id": identity, "timestamp": moment.isoformat(), "session": state.get("session", "unknown"),
            "model": state.get("model", "unknown"), "project": state.get("project", "未命名專案"),
            "task": state.get("task", "") if config.get("content_mode") == "excerpts" else "", **delta}


def scan(config, db, baseline=False):
    status = {"phase": "ok", "files": 0, "new_events": 0, "warnings": 0, "content_mode": config["content_mode"]}
    # Reading appended complete lines and updating cursor/outbox is atomic.
    with db:
        for path in sources(config["codex_home"]):
            status["files"] += 1
            key = str(path)
            saved = db.execute("SELECT offset,state FROM files WHERE path=?", (key,)).fetchone()
            offset, state = (saved[0], json.loads(saved[1])) if saved else (0, {})
            try:
                size = path.stat().st_size
                with path.open("rb") as f:
                    # Detect both truncation and replacement at equal/larger size.
                    first = f.readline(2 * 1024 * 1024)
                    prefix = digest(first.decode("utf-8", errors="replace"))
                    reset = size < offset or (offset > 0 and state.get("prefix") and prefix != state["prefix"])
                    if reset:
                        offset, state = 0, {}
                        status["warnings"] += 1
                    state["prefix"] = prefix
                    f.seek(offset)
                    while True:
                        start = f.tell()
                        line = f.readline(2 * 1024 * 1024 + 1)
                        if not line:
                            break
                        if len(line) > 2 * 1024 * 1024:
                            # Consume one oversized line with bounded memory.
                            while line and not line.endswith(b"\n"):
                                line = f.readline(2 * 1024 * 1024 + 1)
                            if not line.endswith(b"\n"):
                                f.seek(start)
                                break
                            status["warnings"] += 1
                            continue
                        if not line.endswith(b"\n"):
                            f.seek(start)
                            break
                        try:
                            record = json.loads(line)
                            if not isinstance(record, dict):
                                raise ValueError("Record is not an object")
                            event = consume(record, state, config)
                            if event:
                                inserted = db.execute("INSERT OR IGNORE INTO seen VALUES(?)", (event["id"],)).rowcount
                                if inserted and not baseline and not reset:
                                    db.execute("INSERT OR IGNORE INTO outbox VALUES(?,?)", (event["id"], json.dumps(event)))
                                    status["new_events"] += 1
                        except (ValueError, TypeError, KeyError, OverflowError):
                            status["warnings"] += 1
                    offset = f.tell()
                db.execute("INSERT OR REPLACE INTO files VALUES(?,?,?)", (key, offset, json.dumps(state)))
            except OSError:
                status["warnings"] += 1
        accumulated = db.execute("SELECT value FROM meta WHERE key='warnings' ").fetchone()
        total_warnings = int(accumulated[0]) if accumulated else 0
        total_warnings += status["warnings"]
        db.execute("INSERT OR REPLACE INTO meta VALUES('warnings',?)", (str(total_warnings),))
        status["warnings_total"] = total_warnings
    if not status["files"]:
        status["phase"] = "no_sources"
    elif status["warnings_total"]:
        status["phase"] = "partial"
    status["pending"] = db.execute("SELECT count(*) FROM outbox").fetchone()[0]
    return status


@contextmanager
def collection_lock(data):
    path = Path(data) / "collector.lock"
    with path.open("a+b") as lock:
        if path.stat().st_size == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def run_once(data):
    with collection_lock(data):
        try:
            return _run_once(data)
        except (OSError, ValueError, urllib.error.URLError) as error:
            private_write(Path(data) / "status.json", json.dumps({"at": now(), "phase": "upload_failed", "error_type": type(error).__name__}))
            raise


def _run_once(data):
    data = Path(data)
    config = read_json(data / "config.json")
    endpoint = safe_endpoint(config["endpoint"], config.get("allow_http", False))
    db = connect(data / "collector.db")
    try:
        status = scan(config, db)
        # Limit a single invocation to 10 batches; next run resumes remaining work.
        for _ in range(10):
            batch = db.execute("SELECT id,body FROM outbox ORDER BY rowid LIMIT 100").fetchall()
            response = post(endpoint + "/api/ingest", config["token"],
                            {"events": [json.loads(r[1]) for r in batch], "status": status})
            accepted = set(response.get("accepted", []))
            with db:
                db.executemany("DELETE FROM outbox WHERE id=?", [(r[0],) for r in batch if r[0] in accepted])
            if not batch or len(accepted) != len(batch):
                break
        status["pending"] = db.execute("SELECT count(*) FROM outbox").fetchone()[0]
        # Final heartbeat reports the post-upload queue, not the stale initial size.
        post(endpoint + "/api/ingest", config["token"], {"events": [], "status": status})
        private_write(data / "status.json", json.dumps({"at": now(), **status}, ensure_ascii=False))
        return status
    finally:
        db.close()


def watch(data, interval=300):
    while True:
        try:
            print(json.dumps(run_once(data)), flush=True)
        except (OSError, ValueError, urllib.error.URLError) as error:
            # Never log enrollment credentials, source text, or request bodies.
            private_write(Path(data) / "status.json", json.dumps({"at": now(), "phase": "upload_failed", "error_type": type(error).__name__}))
            print("Upload unavailable; queued data retained (" + type(error).__name__ + ")", flush=True)
        time.sleep(interval)

"""Start an isolated dashboard containing synthetic data only."""
import argparse
import json
import secrets
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ledger import server
from ledger.common import digest, now


def seed(data):
    if (data / "server.db").exists():
        raise SystemExit("Demo refuses an existing database; use a new empty directory")
    server.init(data)
    (data / "demo.flag").write_text("Synthetic demonstration. No real employee data.")
    db = server.database(data / "server.db")
    created = now()
    entries = [("員工 A · 開發", 182000, 148000, 11000, "sample-app", "調整搜尋結果，補上空白狀態與操作測試。", "ok"),
               ("員工 B · 企劃", 76000, 39000, 8200, "sample-campaign", "整理活動頁文案，檢查報名流程。", "ok"),
               ("員工 C · 營運", 41000, 30000, 3500, "sample-report", "建立每週營運資料整理腳本。", "partial"),
               ("員工 D · 待安裝", 0, 0, 0, "", "", "enrolling")]
    with db:
        for i, (name, input_t, cache_t, output_t, project, task, phase) in enumerate(entries):
            id = "demo-device-" + str(i)
            status = json.dumps({"phase": phase, "files": 3 if input_t else 0, "content_mode": "excerpts", "warnings_total": 1 if phase == "partial" else 0, "pending": 0})
            db.execute("INSERT INTO devices(id,name,token_hash,created,last_seen,status) VALUES(?,?,?,?,?,?)", (id, name, digest(secrets.token_urlsafe(32)), created, created if input_t else None, status))
            if input_t:
                db.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?)", (digest(id), id, datetime.now(timezone.utc).isoformat(), "demo-session-" + str(i), "sample-model", project, task, input_t, cache_t, output_t, 1500))
    db.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data")
    p.add_argument("--port", type=int, default=8766)
    args = p.parse_args()
    data = Path(args.data) if args.data else Path(tempfile.mkdtemp(prefix="team-ledger-demo-"))
    seed(data)
    print("DEMO: all data is synthetic. Do not enroll real employees into this database.", flush=True)
    server.serve(data, port=args.port)

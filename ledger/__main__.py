import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__, collector, server


def main():
    parser = argparse.ArgumentParser(description="團隊用量帳本：自動收集，不呼叫 AI")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    boss = sub.add_parser("server", help="啟動老闆看板")
    boss.add_argument("--data", default=str(Path.home() / ".team-token-ledger" / "boss"))
    boss.add_argument("--host", default="127.0.0.1")
    boss.add_argument("--port", type=int, default=8765)
    setup = sub.add_parser("enroll", help="員工配對並建立起算基準；不補傳歷史")
    setup.add_argument("--enrollment", required=True)
    setup.add_argument("--data", default=str(Path.home() / ".team-token-ledger" / "employee"))
    setup.add_argument("--codex-home", default=os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    setup.add_argument("--content-mode", choices=("labels", "excerpts"), default="labels")
    setup.add_argument("--project", action="append", default=[])
    setup.add_argument("--allow-http", action="store_true")
    for name in ("collect", "watch"):
        command = sub.add_parser(name)
        command.add_argument("--data", default=str(Path.home() / ".team-token-ledger" / "employee"))
        if name == "watch":
            command.add_argument("--interval", type=int, default=300)
    args = parser.parse_args()
    try:
        if args.command == "server":
            server.serve(args.data, args.host, args.port)
        elif args.command == "enroll":
            collector.init(args.enrollment, args.data, args.codex_home, args.content_mode, args.project, args.allow_http)
            print("配對成功；舊紀錄已設為起算基準。")
        elif args.command == "collect":
            print(json.dumps(collector.run_once(args.data), ensure_ascii=False))
        else:
            if args.interval < 60:
                raise ValueError("Minimum interval: 60 seconds")
            collector.watch(args.data, args.interval)
    except (OSError, ValueError) as error:
        print("執行未完成：" + type(error).__name__ + "。請確認路徑、伺服器連線及配對設定。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

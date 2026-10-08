"""Generate synthetic daily PDFs and a receipt page. Never reads real sessions."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ledger import daily


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='output/daily-demo')
    args=parser.parse_args()
    root=Path(args.output).resolve()
    if root.exists() and any(root.iterdir()):
        raise SystemExit('Use a new empty demo directory; existing files are never overwritten.')
    root.mkdir(parents=True,exist_ok=True)
    shared=root/'公司AI日報';daily.init_folder(shared)
    clock=datetime(2026,10,8,9,5,tzinfo=timezone.utc)
    home=root/'synthetic-source';(home/'sessions').mkdir(parents=True)
    records=[{'type':'session_meta','payload':{'id':'demo-session','cwd':'/demo/示範網站'}},
             {'type':'response_item','payload':{'role':'user','content':[{'text':'合成示範：調整網站版面並測試手機顯示。'}]}}]
    for stamp,i,c,o,r in [('2026-10-08T08:00:00Z',2400,1800,360,200),('2026-10-08T09:00:00Z',4200,2900,660,340)]:
        total=dict(input_tokens=i,cached_input_tokens=c,output_tokens=o,reasoning_output_tokens=r)
        records.append({'type':'event_msg','timestamp':stamp,'payload':{'type':'token_count','info':{'total_token_usage':total,'last_token_usage':total}}})
    (home/'sessions/demo.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
    with patch('ledger.daily.instant',return_value=clock):
        daily.setup(root/'employee','示範員工甲',shared,home,'excerpts')
        daily.run(root/'employee',at=clock)
        result=daily.inspect_receipts(shared,['示範員工甲','示範員工乙'],'2026-10-08')
    (root/'收件示範.html').write_text(daily.receipt_html(result),encoding='utf-8')
    (root/'README.txt').write_text('All data in this folder is synthetic. No real Codex sessions were read.\n',encoding='utf-8')
    print(root)


if __name__=='__main__':main()

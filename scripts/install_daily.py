import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ledger import daily
from ledger.common import private_write
import json


def install(args):
    target=Path(args.install_dir).expanduser().resolve()
    if target in (Path.home().resolve(),Path(target.anchor),ROOT) or ROOT.is_relative_to(target):
        raise ValueError('請用獨立安裝資料夾')
    marker=target/'daily-install.json'
    if target.exists() and any(target.iterdir()) and not marker.exists():
        raise ValueError('安裝目錄含有其他資料，拒絕覆蓋')
    if marker.exists() and json.loads(marker.read_text())['mode'] != args.mode:
        raise ValueError('員工端與老闆端請分開安裝目錄')
    target.mkdir(parents=True,exist_ok=True)
    # Updating read-only files is an explicit installer operation, never a scheduled behavior.
    for base in ('app','runtime'):
        for p in (target/base).rglob('*'):
            if p.is_file():os.chmod(p,0o600)
    for p in (target/'run_daily.py',target/'program-manifest.json',target/'data/boss-config.json'):
        if p.exists():os.chmod(p,0o600)
    (target/'data').mkdir(exist_ok=True)
    if args.mode=='employee':
        daily.setup(target/'data',args.name,args.shared,args.codex_home,args.content_mode,args.offset,args.time,args.project)
    else:
        root,folder_id=daily.init_folder(args.shared)
        daily.roster(args.roster)
        shutil.copyfile(args.roster,target/'names.txt')
        private_write(target/'data/boss-config.json',json.dumps({'shared':str(root),'folder_id':folder_id,'offset':args.offset}))
    shutil.copytree(ROOT/'ledger',target/'app/ledger',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copyfile(ROOT/'scripts/run_daily.py',target/'run_daily.py')
    private_write(marker,json.dumps({'version':'0.2.0','mode':args.mode}))
    print('已安裝程式與設定：'+str(target))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--mode',choices=['employee','boss'],required=True);p.add_argument('--name',default='')
    p.add_argument('--shared',required=True);p.add_argument('--install-dir',required=True);p.add_argument('--roster')
    p.add_argument('--codex-home',default=os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))
    p.add_argument('--content-mode',choices=['labels','excerpts'],default='labels');p.add_argument('--offset',type=int,default=480)
    p.add_argument('--time',default='17:00');p.add_argument('--project',action='append',default=[])
    install(p.parse_args())

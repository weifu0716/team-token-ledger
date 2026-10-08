"""Installed bootstrap. Verify application files BEFORE importing ledger code."""
import hashlib
import json
import os
import sys
from pathlib import Path


def hashes(root):
    paths = [p for p in (root/'app').rglob('*') if p.is_file() and p.suffix in ('.py','.js','.css','.html')]
    paths += [root/'run_daily.py', root/'data/daily-config.json', root/'data/boss-config.json']
    paths += list((root/'runtime').glob('*'))
    return {str(p.relative_to(root)).replace('\\','/'): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths if p.is_file() and p.suffix not in ('.log',)}


def seal(root):
    path=root/'program-manifest.json'
    if path.exists():
        os.chmod(path,0o600)
    path.write_text(json.dumps(hashes(root),indent=2),encoding='utf-8')
    for name in [*hashes(root), 'program-manifest.json']:
        os.chmod(root/name,0o444)


def verify(root):
    expected=json.loads((root/'program-manifest.json').read_text(encoding='utf-8'))
    actual=hashes(root)
    if not expected or actual!=expected:
        raise ValueError('程式或設定已變更；請重新安裝已核對版本，不要自行重建指紋。')


def main():
    root=Path(__file__).resolve().parent
    try:
        if sys.argv[1:]==['seal']:
            seal(root);print('已建立唯讀保護與程式指紋。');return 0
        verify(root)
        if sys.argv[1:]==['verify']:
            print('程式與設定指紋一致。');return 0
        sys.path.insert(0,str(root/'app'))
        from ledger.daily import main as daily_main, folder
        if sys.argv[1:]==['boss']:
            from datetime import datetime,timezone,timedelta
            config=json.loads((root/'data/boss-config.json').read_text(encoding='utf-8'))
            folder(config['shared'],config['folder_id'])
            today=datetime.now(timezone(timedelta(minutes=config['offset']))).date()
            day=today.isoformat()
            yesterday=(today-timedelta(days=1)).isoformat()
            if (Path(config['shared'])/yesterday).is_dir():
                result=daily_main(['check','--shared',config['shared'],'--roster',str(root/'names.txt'),'--day',yesterday,'--output',str(root/'results')])
                if result:return result
            return daily_main(['check','--shared',config['shared'],'--roster',str(root/'names.txt'),'--day',day,'--output',str(root/'results')])
        return daily_main(['run','--data',str(root/'data'),*sys.argv[1:]])
    except Exception as e:
        status=root/'data/bootstrap-status.json'
        status.parent.mkdir(exist_ok=True)
        status.write_text(json.dumps({'state':'failed','error':str(e)},ensure_ascii=False),encoding='utf-8')
        print('未執行日報：'+str(e),file=sys.stderr)
        return 3


if __name__=='__main__':
    raise SystemExit(main())

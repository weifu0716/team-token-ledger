"""Daily file delivery and manager-side receipt checks. No HTTP service needed."""
import argparse
import html
import json
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import daily_records as records
from .collector import collection_lock
from .common import digest, private_write, read_json, stamp

MARKER = '.team-daily-folder.json'


def instant():
    return datetime.now(timezone.utc)


def atomic(path, body):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + secrets.token_hex(4) + '.part')
    try:
        temp.write_bytes(body)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def folder(path, expected=None):
    path = Path(path).expanduser().resolve()
    marker = read_json(path / MARKER)
    if not re_id(marker.get('folder_id')) or (expected and marker['folder_id'] != expected):
        raise ValueError('收件夾識別不符，暫不交件')
    return path, marker['folder_id']


def re_id(value):
    import re
    return isinstance(value, str) and bool(re.fullmatch('[0-9a-f]{32}', value))


def init_folder(path):
    path = Path(path).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    marker = path / MARKER
    if not marker.exists():
        with marker.open('x', encoding='utf-8') as f:
            json.dump({'schema': 2, 'folder_id': secrets.token_hex(16)}, f)
    return folder(path)


def setup(data, name, shared, codex_home, content_mode='labels', offset=480, report_time='17:00', projects=None):
    from datetime import time
    time.fromisoformat(report_time)
    if not -720 <= offset <= 840:
        raise ValueError('Invalid timezone')
    data = Path(data).expanduser().resolve()
    data.mkdir(parents=True, exist_ok=True)
    config_path = data / 'daily-config.json'
    if config_path.exists():
        old = read_json(config_path)
        if old['name'] != records.safe_name(name) or old['shared'] != str(Path(shared).expanduser().resolve()):
            raise ValueError('既有安裝的姓名或收件夾不同，不能直接覆蓋')
        requested = {'codex_home': str(Path(codex_home).expanduser().resolve()), 'content_mode': content_mode,
                     'offset': offset, 'report_time': report_time,
                     'projects': [str(Path(p).expanduser().resolve()) for p in (projects or [])]}
        if any(old.get(key) != value for key, value in requested.items()):
            raise ValueError('既有安裝的時間、來源或分享範圍不同；請管理者保留裝置識別與歷史，核對設定後再更新')
        return old
    root, folder_id = folder(shared)
    current = instant().astimezone(timezone(timedelta(minutes=offset)))
    config = {'schema': 2, 'name': records.safe_name(name), 'shared': str(root), 'folder_id': folder_id,
              'device': secrets.token_hex(16), 'codex_home': str(Path(codex_home).expanduser().resolve()),
              'content_mode': content_mode, 'offset': offset, 'report_time': report_time,
              'start_day': current.date().isoformat(), 'projects': [str(Path(p).expanduser().resolve()) for p in (projects or [])]}
    private_write(config_path, json.dumps(config, ensure_ascii=False, indent=2))
    return config


def produce(data, config, day, at=None):
    from .daily_pdf import render
    at = at or instant()
    report = records.collect(config, day, at)
    local = Path(data) / 'outbox' / day
    local.mkdir(parents=True, exist_ok=True)
    pdf = local / (config['name'] + '.pdf')
    temporary = local / (config['name'] + '.building.pdf')
    render(report, temporary, config.get('font_path'))
    os.replace(temporary, pdf)
    report['pdf_sha256'] = records.hash_file(pdf)
    report['program_version'] = '0.2.0'
    records.validate(report, pdf, config['name'], day, config['folder_id'])
    atomic(local / (config['name'] + '.json'), json.dumps(report, ensure_ascii=False).encode('utf-8'))
    return report


def deliver(config, local):
    root, _ = folder(config['shared'], config['folder_id'])
    report = read_json(local)
    name, day = config['name'], report['day']
    local_pdf = local.with_suffix('.pdf')
    records.validate(report, local_pdf, name, day, config['folder_id'])
    destination = root / day
    check = destination / '.checks' / (name + '.json')
    owner = destination / '.checks' / (name + '.owner')
    pdf = destination / (name + '.pdf')
    destination.mkdir(exist_ok=True)
    # A per-name lock prevents two devices from simultaneously claiming a blank name.
    lock = destination / ('.' + name + '.delivery-lock')
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ValueError('同名交件正在進行，或上次中斷留下鎖；請核對後重試')
    os.close(fd)
    try:
        if owner.exists() and owner.read_text().strip() != config['device']:
            raise ValueError('同名報告已由另一台電腦使用，拒絕覆蓋')
        if check.exists():
            existing = read_json(check)
            if existing.get('device') != config['device']:
                raise ValueError('同名報告來自另一台電腦，拒絕覆蓋')
            if stamp(existing['end']) > stamp(report['end']):
                return 'kept_newer'
        elif pdf.exists() and not owner.exists():
            raise ValueError('已有同名PDF但沒有核對檔，請老闆先核對，不能覆蓋')
        if not owner.exists():
            owner.parent.mkdir(exist_ok=True)
            with owner.open('x', encoding='utf-8') as f:
                f.write(config['device'])
        if pdf.exists() and records.hash_file(pdf) == report['pdf_sha256'] and check.exists() and read_json(check) == report:
            return 'unchanged'
        atomic(pdf, local_pdf.read_bytes())
        # Publish the receipt marker last. The boss can detect an incomplete cloud sync.
        atomic(check, local.read_bytes())
        records.validate(read_json(check), pdf, name, day, config['folder_id'])
        return 'saved_to_shared_path'
    finally:
        lock.unlink(missing_ok=True)


def run(data, requested_day=None, at=None):
    data = Path(data)
    at = at or instant()
    config = read_json(data / 'daily-config.json')
    zone = timezone(timedelta(minutes=config['offset']))
    clock = at.astimezone(zone)
    today = clock.date()
    from datetime import time
    state_path = data / 'daily-state.json'
    with collection_lock(data):
        state = read_json(state_path) if state_path.exists() else {'final_days': []}
        due = []
        if requested_day:
            if requested_day < config['start_day']:
                raise ValueError('不能回報安裝前的日期')
            due = [requested_day]
        else:
            day = datetime.fromisoformat(config['start_day']).date()
            while day < today and len(due) < 31:
                if day.isoformat() not in state['final_days']:
                    due.append(day.isoformat())
                day += timedelta(days=1)
            if len(due) < 31 and clock.time() >= time.fromisoformat(config['report_time']):
                due.append(today.isoformat())
        for day in due:
            report = produce(data, config, day, at)
            if report['complete_day'] and report['source_files'] and not report['warnings'] and day not in state['final_days']:
                state['final_days'].append(day)
            private_write(state_path, json.dumps(state))
        results = []
        for path in sorted((data / 'outbox').glob('*/*.json')):
            try:
                result = deliver(config, path)
                results.append({'day': path.parent.name, 'state': result})
            except (OSError, ValueError, KeyError, TypeError) as error:
                results.append({'day': path.parent.name, 'state': 'pending', 'reason': str(error)[:160]})
        status = {'at': at.isoformat(), 'produced_days': due, 'delivery': results,
                  'note': '存入共用路徑不代表雲端同步完成；以老闆端收件檢查為準'}
        private_write(data / 'daily-status.json', json.dumps(status, ensure_ascii=False, indent=2))
        return status


def roster(path):
    names = [records.safe_name(n) for n in Path(path).read_text(encoding='utf-8-sig').splitlines() if n.strip() and not n.lstrip().startswith('#')]
    if not names or len(set(n.casefold() for n in names)) != len(names):
        raise ValueError('名單不可空白或重複；同名請加部門／装置區分')
    return names


def inspect_receipts(shared, names, day, history=None):
    root, folder_id = folder(shared)
    records.bounds(day)
    previous = read_json(history) if history and Path(history).exists() else {}
    rows, event_owners = [], {}
    for name in names:
        name = records.safe_name(name)
        pdf, check = root / day / (name+'.pdf'), root / day / '.checks' / (name+'.json')
        row = {'name': name, 'received': pdf.is_file(), 'status': '尚未收到', 'issues': [], 'tokens': None}
        rows.append(row)
        if not pdf.is_file():
            continue
        if not check.is_file():
            row.update(status='已收到PDF，等待核對檔同步', issues=['缺少核對檔'])
            continue
        try:
            if check.stat().st_size > 20*1024*1024 or pdf.stat().st_size > 30*1024*1024:
                raise ValueError('報告過大，請人工核對')
            data = read_json(check)
            totals, ids = records.validate(data, pdf, name, day, folder_id)
            row.update(status='已收到，數字與檔案一致', tokens=totals['total_tokens'], end=data['end'])
            row['issues'] += data.get('warnings', [])
            old = previous.get(day, {}).get(name)
            changed = old and (old['device'] != data['device'] or not set(old['ids']).issubset(ids) or totals['total_tokens'] < old['tokens'])
            if changed:
                row['issues'].append('相較上次檢查，裝置改變、明細減少或總量下降')
            else:
                previous.setdefault(day, {})[name] = {'device': data['device'], 'ids': sorted(ids), 'tokens': totals['total_tokens']}
            for event in data['events']:
                event_owners.setdefault(event['id'], []).append((row, event['input_tokens']+event['output_tokens']))
            if row['issues']:
                row['status'] = '已收到，部分資料待核對'
        except (OSError, ValueError, TypeError, KeyError, OverflowError, AttributeError) as error:
            row.update(status='已收到，核對未通過', issues=[str(error)[:200]])
    unique_total = 0
    for owners in event_owners.values():
        if len(owners) == 1:
            unique_total += owners[0][1]
        else:
            for row, _ in owners:
                row['status'] = '已收到，跨員工紀錄重複'
                if '發現與其他員工相同的用量事件，暫不計入無爭議合計' not in row['issues']:
                    row['issues'].append('發現與其他員工相同的用量事件，暫不計入無爭議合計')
    if history:
        private_write(history, json.dumps(previous, ensure_ascii=False))
    expected_files = {n+'.pdf' for n in names}
    extra = [p.name for p in (root/day).glob('*.pdf') if p.name not in expected_files]
    return {'day': day, 'checked': instant().isoformat(), 'rows': rows, 'unexpected_files': extra,
            'received': sum(r['received'] for r in rows), 'expected': len(rows), 'unique_tokens': unique_total,
            'note': '一致性通過不等於來源真實；缺檔不代表沒工作。檢查結果以老闆端目前可見檔案為準。'}


def receipt_html(result):
    esc = lambda v: html.escape(str(v))
    rows = ''.join('<tr><td>'+esc(r['name'])+'</td><td>'+esc(r['status'])+'</td><td>'+('—' if r['tokens'] is None else f"{r['tokens']:,}")+'</td><td>'+esc('；'.join(r['issues']))+'</td></tr>' for r in result['rows'])
    extra = '<p>名單以外的檔案（未計入合計）：'+esc('、'.join(result['unexpected_files']))+'</p>' if result['unexpected_files'] else ''
    return '''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>日報收件檢查</title><style>body{font:16px/1.7 "Microsoft JhengHei",sans-serif;background:#f6f5f0;color:#233c35;max-width:1100px;margin:40px auto;padding:24px}h1{font-size:30px}table{border-collapse:collapse;width:100%;background:white}td,th{padding:14px;text-align:left;border-bottom:1px solid #ccd8ce}th{background:#e5eee5}small{color:#56685e}.scroll{overflow:auto}</style>''' + f'<h1>{esc(result["day"])} 日報收件檢查</h1><p>已收到 {result["received"]} / {result["expected"]} 份PDF</p><p>可核對且無跨員工重複的 Token：{result["unique_tokens"]:,}</p><div class="scroll"><table><thead><tr><th>姓名</th><th>收件狀態</th><th>報告Token</th><th>需核對的地方</th></tr></thead><tbody>{rows}</tbody></table></div>{extra}<p>{esc(result["note"])}</p><small>檢查時間：{esc(result["checked"])}。這是靜態結果，重新執行檢查才會更新。</small></html>'


def main(argv=None):
    parser = argparse.ArgumentParser(description='每日PDF交件，不需要監控網站或配對檔')
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('init-folder'); create.add_argument('--shared', required=True)
    install = sub.add_parser('setup')
    install.add_argument('--name', required=True); install.add_argument('--shared', required=True)
    install.add_argument('--data', required=True)
    install.add_argument('--codex-home', default=os.environ.get('CODEX_HOME', str(Path.home()/'.codex')))
    install.add_argument('--content-mode', choices=['labels','excerpts'], default='labels')
    install.add_argument('--time', default='17:00'); install.add_argument('--offset',type=int,default=480)
    install.add_argument('--project',action='append',default=[])
    run_parser=sub.add_parser('run'); run_parser.add_argument('--data',required=True); run_parser.add_argument('--day')
    check=sub.add_parser('check');check.add_argument('--shared',required=True);check.add_argument('--roster',required=True)
    check.add_argument('--day',required=True);check.add_argument('--output',required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='init-folder':
            init_folder(args.shared); print('收件夾已初始化。請確保員工與老闆能看到同一份資料。')
        elif args.command=='setup':
            setup(args.data,args.name,args.shared,args.codex_home,args.content_mode,args.offset,args.time,args.project)
            print('姓名與收件夾已設定；尚需安裝系統排程。')
        elif args.command=='run':
            result=run(args.data,args.day);print(json.dumps(result,ensure_ascii=False))
            return 2 if any(r['state']=='pending' for r in result['delivery']) else 0
        else:
            out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
            result=inspect_receipts(args.shared,roster(args.roster),args.day,out/'receipt-history.json')
            atomic(out/(args.day+'-收件檢查.html'),receipt_html(result).encode('utf-8'))
            atomic(out/(args.day+'-收件檢查.json'),json.dumps(result,ensure_ascii=False,indent=2).encode('utf-8'))
            print(f"已收到 {result['received']}/{result['expected']}；結果保存在 {out}")
    except (OSError,ValueError,TypeError,KeyError) as error:
        print('未完成：'+str(error),file=sys.stderr);return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())

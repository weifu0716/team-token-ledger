"""Offline daily observations and independently recalculable arithmetic evidence."""
import hashlib
import json
import re
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from .collector import consume, sources
from .common import FIELDS, counts, digest, stamp

SCHEMA = 2


def safe_name(value):
    value = value.strip()
    if (not value or len(value) > 60 or value.endswith(('.', ' ')) or
        re.search(r'[<>:"/\\|?*\x00-\x1f]', value) or
        re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', value)):
        raise ValueError('姓名不可空白、過長或包含不適合檔名的字元')
    return value


def bounds(day, offset=480, cutoff=None):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day) or not -720 <= offset <= 840:
        raise ValueError('Invalid date or timezone')
    zone = timezone(timedelta(minutes=offset))
    start = datetime.combine(datetime.fromisoformat(day).date(), time(), zone)
    end = start + timedelta(days=1)
    if cutoff is not None:
        end = min(end, cutoff.astimezone(zone))
    if end <= start:
        raise ValueError('Report period has not started')
    return start, end


def collect(config, day, instant):
    start, end = bounds(day, config.get('offset', 480), instant)
    parse_config = {'since': start.isoformat(), 'content_mode': config.get('content_mode', 'labels'),
                    'projects': config.get('projects', [])}
    events, warnings, tasks = {}, [], {}
    scanned = 0
    for path in sources(config['codex_home']):
        scanned += 1
        state = {}
        try:
            with path.open('rb') as stream:
                while True:
                    line = stream.readline(2 * 1024 * 1024 + 1)
                    if not line:
                        break
                    if len(line) > 2 * 1024 * 1024:
                        while line and not line.endswith(b'\n'):
                            line = stream.readline(2 * 1024 * 1024 + 1)
                        warnings.append('來源含過長紀錄，已跳過')
                        continue
                    if not line.endswith(b'\n'):
                        warnings.append('來源末行尚未寫完，留待下次補算')
                        break
                    try:
                        record = json.loads(line)
                        if not isinstance(record, dict):
                            raise ValueError('Invalid source')
                        previous = state.get('total')
                        event = consume(record, state, parse_config)
                        if not event or stamp(event['timestamp']) >= end:
                            continue
                        current = dict(state['total'])
                        raw = record['payload']['info']['total_token_usage']
                        if 'total_tokens' in raw and raw['total_tokens'] != current['input_tokens'] + current['output_tokens']:
                            warnings.append('來源總數與輸入加輸出不一致，該筆未計入')
                            continue
                        proof = {k: event[k] for k in ('id', 'timestamp', 'session', 'model', *FIELDS)}
                        proof['session'] = digest(proof['session'])  # no local IDs or paths are needed by the boss
                        proof.update(previous=previous, current=current)
                        if previous is None:
                            proof['last'] = counts(record['payload']['info']['last_token_usage'])
                            if any(proof['last'][k] != current[k] for k in FIELDS):
                                warnings.append('新來源含未觀測歷史，只計最後一次請求')
                        if event['id'] in events:
                            old = events[event['id']]
                            if any(old[k] != proof[k] for k in FIELDS):
                                warnings.append('重複來源增量不同，需核對')
                            continue
                        events[event['id']] = proof
                        key = (event['session'], event['project'])
                        item = tasks.setdefault(key, {'project': event['project'], 'text': '', 'total_tokens': 0})
                        item['text'] = event['task']
                        item['total_tokens'] += event['input_tokens'] + event['output_tokens']
                    except (ValueError, TypeError, KeyError, OverflowError, AttributeError):
                        warnings.append('紀錄格式或計數異常，無法完整計入')
        except OSError:
            warnings.append('部分來源無法讀取')
    values = list(events.values())
    totals = {k: sum(e[k] for e in values) for k in FIELDS}
    totals['total_tokens'] = totals['input_tokens'] + totals['output_tokens']
    return {'schema': SCHEMA, 'name': safe_name(config['name']), 'device': config['device'], 'day': day,
            'folder_id': config['folder_id'], 'start': start.isoformat(), 'end': end.isoformat(),
            'generated': instant.isoformat(), 'offset': config.get('offset', 480),
            'content_mode': config.get('content_mode', 'labels'), 'source_files': scanned,
            'warnings': sorted(set(warnings + (['未找到本機來源，不能判斷實際用量'] if not scanned else []))),
            'totals': totals, 'events': values, 'tasks': sorted(tasks.values(), key=lambda t: -t['total_tokens']),
            'complete_day': end == start + timedelta(days=1)}


def hash_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def validate(data, pdf, expected_name, expected_day, folder_id):
    """No employee-controlled code executes here. Consistency is not authenticity."""
    if data.get('schema') != SCHEMA or data.get('name') != expected_name or data.get('day') != expected_day or data.get('folder_id') != folder_id:
        raise ValueError('報告姓名、日期或收件夾不符')
    if not re.fullmatch(r'[0-9a-f]{32}', data.get('device', '')):
        raise ValueError('裝置識別格式錯誤')
    start, end = bounds(data['day'], data['offset'], stamp(data['end']))
    if stamp(data['start']) != start or stamp(data['end']) != end or stamp(data['generated']) < end:
        raise ValueError('報告區間錯誤')
    events = data.get('events')
    if not isinstance(events, list) or len(events) > 100000:
        raise ValueError('明細數量異常')
    seen, totals = set(), {k: 0 for k in FIELDS}
    for e in events:
        delta, current = counts(e), counts(e['current'])
        expected = counts(e['last']) if e['previous'] is None else {k: current[k] - counts(e['previous'])[k] for k in FIELDS}
        if delta != expected or any(delta[k] > current[k] for k in FIELDS):
            raise ValueError('明細增量與來源快照算不攏')
        if not start <= stamp(e['timestamp']) < end:
            raise ValueError('混入報告日期以外的明細')
        identity = digest({'timestamp': stamp(e['timestamp']).isoformat(), 'total': current})
        if e['id'] != identity or identity in seen:
            raise ValueError('明細指紋錯誤或重複計數')
        seen.add(identity)
        for k in FIELDS:
            totals[k] += delta[k]
    totals['total_tokens'] = totals['input_tokens'] + totals['output_tokens']
    if not isinstance(data.get('totals'), dict) or any(type(v) is not int or v < 0 for v in data['totals'].values()) or data['totals'] != totals:
        raise ValueError('報表合計與逐筆重算不一致')
    if not isinstance(data.get('tasks'), list) or any(type(t['total_tokens']) is not int or t['total_tokens'] < 0 for t in data['tasks']) or sum(t['total_tokens'] for t in data['tasks']) != totals['total_tokens']:
        raise ValueError('專案小計與總計不一致')
    if data.get('pdf_sha256') != hash_file(pdf):
        raise ValueError('PDF與核對檔不一致：可能尚在同步或檔案曾被修改')
    return totals, seen

import copy
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from ledger import daily, daily_records as records
from tests.test_ledger import append, meta, tokens, usage
from scripts import run_daily


def at(value):
    return datetime.fromisoformat(value + '+08:00')


class DailyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.shared = self.root/'shared'
        daily.init_folder(self.shared)
        self.home = self.root/'codex'
        self.source = self.home/'sessions/one.jsonl'
        self.data = self.root/'employee'
        self.day = '2026-10-08'
        with patch('ledger.daily.instant',return_value=at(self.day+'T09:00:00')):
            self.config = daily.setup(self.data,'測試甲',self.shared,self.home)
        append(self.source,meta(),usage(self.day+'T02:00:00Z',tokens(100,70,20,5)))
        self.pdf = self.shared/self.day/'測試甲.pdf'
        self.check = self.shared/self.day/'.checks/測試甲.json'
        # The production renderer is exercised separately with a real CJK PDF.
        self.render = patch('ledger.daily_pdf.render',side_effect=lambda report,path,font: Path(path).write_bytes(b'%PDF-1.4 synthetic test'))
        self.render.start()
        self.addCleanup(self.render.stop)

    def submit(self,when='2026-10-08T18:00:00'):
        return daily.run(self.data,at=at(when))

    def inspect(self,history=None,names=None):
        return daily.inspect_receipts(self.shared,names or ['測試甲','測試乙'],self.day,history)

    def test_delivery_missing_person_and_exact_arithmetic(self):
        status=self.submit()
        self.assertEqual(status['delivery'][0]['state'],'saved_to_shared_path')
        result=self.inspect()
        self.assertEqual((result['received'],result['expected'],result['unique_tokens']),(1,2,120))
        self.assertEqual(result['rows'][0]['issues'],[])
        evidence=json.loads(self.check.read_text('utf-8'))
        self.assertEqual(evidence['totals']['cached_input_tokens'],70)
        self.assertEqual(daily.deliver(self.config,self.data/'outbox'/self.day/'測試甲.json'),'unchanged')

    def test_day_boundary_uses_delta_not_whole_counter(self):
        self.source.unlink()
        append(self.source,meta(),usage('2026-10-07T15:00:00Z',tokens(1000,500,200)),usage('2026-10-07T17:00:00Z',tokens(1100,550,220)))
        self.assertEqual(records.collect(self.config,self.day,at(self.day+'T18:00:00'))['totals']['total_tokens'],120)

    def test_duplicate_archives_do_not_double_count(self):
        other=self.home/'archived_sessions/copy.jsonl';other.parent.mkdir()
        shutil.copyfile(self.source,other)
        self.submit()
        self.assertEqual(self.inspect()['unique_tokens'],120)

    def test_pdf_tamper_detected(self):
        self.submit();self.pdf.write_bytes(b'changed')
        result=self.inspect()
        self.assertEqual(result['received'],1)
        self.assertEqual(result['unique_tokens'],0)
        self.assertIn('核對未通過',result['rows'][0]['status'])

    def test_arithmetic_forgery_detected(self):
        self.submit()
        data=json.loads(self.check.read_text('utf-8'))
        data['events'][0]['input_tokens']=900
        self.check.write_text(json.dumps(data),encoding='utf-8')
        self.assertIn('增量',self.inspect()['rows'][0]['issues'][0])

    def test_missing_sidecar_means_received_but_waiting(self):
        self.submit();self.check.unlink()
        self.assertEqual(self.inspect()['received'],1)
        self.assertIn('同步',self.inspect()['rows'][0]['status'])

    def test_renamed_shared_folder_stays_pending_and_not_recreated(self):
        self.shared.rename(self.root/'offline')
        result=self.submit()
        self.assertFalse(self.shared.exists())
        self.assertEqual(result['delivery'][0]['state'],'pending')
        (self.root/'offline').rename(self.shared)
        self.assertEqual(self.submit()['delivery'][0]['state'],'saved_to_shared_path')

    def test_foreign_marker_blocked(self):
        (self.shared/daily.MARKER).write_text(json.dumps({'folder_id':'f'*32}))
        self.assertEqual(self.submit()['delivery'][0]['state'],'pending')

    def test_other_device_same_name_cannot_overwrite(self):
        self.submit()
        data=self.root/'second'
        config=dict(self.config,device='f'*32)
        daily.produce(data,config,self.day,at(self.day+'T19:00:00'))
        with self.assertRaisesRegex(ValueError,'另一台'):
            daily.deliver(config,data/'outbox'/self.day/'測試甲.json')

    def test_same_event_across_people_excluded_from_combined_total(self):
        self.submit()
        config=dict(self.config,name='測試乙',device='f'*32)
        data=self.root/'second'
        daily.produce(data,config,self.day,at(self.day+'T19:00:00'))
        daily.deliver(config,data/'outbox'/self.day/'測試乙.json')
        result=self.inspect()
        self.assertEqual(result['received'],2)
        self.assertEqual(result['unique_tokens'],0)
        self.assertTrue(all('重複' in row['status'] for row in result['rows']))

    def test_history_regression_remains_flagged_on_recheck(self):
        append(self.source,usage(self.day+'T03:00:00Z',tokens(200,100,40,10)))
        self.submit()
        history=self.root/'history.json';self.inspect(history)
        lines=self.source.read_bytes().splitlines(keepends=True)
        self.source.write_bytes(b''.join(lines[:-1]))
        self.submit(when=self.day+'T19:00:00')
        for _ in range(2):
            self.assertTrue(any('下降' in e for e in self.inspect(history)['rows'][0]['issues']))

    def test_scheduler_before_time_and_next_day_catchup(self):
        self.assertEqual(daily.run(self.data,at=at(self.day+'T16:00:00'))['produced_days'],[])
        self.submit()
        append(self.source,usage(self.day+'T12:00:00Z',tokens(200,100,40,10)))
        result=self.submit(when='2026-10-09T09:00:00')
        self.assertEqual(result['produced_days'],[self.day])
        data=json.loads(self.check.read_text('utf-8'))
        self.assertTrue(data['complete_day'])
        self.assertEqual(data['totals']['total_tokens'],240)
        self.assertFalse((self.shared/'2026-10-09').exists())

    def test_no_source_does_not_finalize_false_zero(self):
        self.source.unlink()
        self.submit(when='2026-10-09T09:00:00')
        self.assertNotIn(self.day,json.loads((self.data/'daily-state.json').read_text())['final_days'])
        self.assertTrue(self.inspect()['rows'][0]['issues'])

    def test_malformed_source_warns(self):
        with self.source.open('ab') as f:f.write(b'{invalid}\n')
        self.submit()
        self.assertTrue(self.inspect()['rows'][0]['issues'])

    def test_source_total_mismatch_excluded(self):
        self.source.unlink()
        append(self.source,meta(),usage(self.day+'T02:00:00Z',dict(tokens(100,70,20,5),total_tokens=999)))
        self.submit()
        self.assertEqual(self.inspect()['unique_tokens'],0)
        self.assertTrue(self.inspect()['rows'][0]['issues'])

    def test_partial_publish_retries_without_losing_ownership(self):
        original=daily.atomic
        def fail(path,body):
            if str(path)==str(self.check):raise OSError('simulated sync failure')
            return original(path,body)
        with patch('ledger.daily.atomic',side_effect=fail):
            self.assertEqual(self.submit()['delivery'][0]['state'],'pending')
        self.assertEqual(self.submit()['delivery'][0]['state'],'saved_to_shared_path')

    def test_names_and_extra_files(self):
        for bad in ('../name','A/B','CON',''):
            with self.assertRaises(ValueError):records.safe_name(bad)
        self.submit();(self.pdf.parent/'不在名單.pdf').write_bytes(b'PDF')
        self.assertIn('不在名單.pdf',daily.receipt_html(self.inspect()))

    def test_reinstall_cannot_silently_change_reporting_scope(self):
        with self.assertRaisesRegex(ValueError,'分享範圍'):
            daily.setup(self.data,'測試甲',self.shared,self.home,'excerpts')

    def test_report_has_real_pdf_and_chinese_text(self):
        self.render.stop()
        try:
            self.submit()
            self.assertTrue(self.pdf.read_bytes().startswith(b'%PDF-'))
            self.assertGreater(self.pdf.stat().st_size,5000)
            self.assertEqual(self.inspect()['unique_tokens'],120)
        finally:
            self.render.start()

    def test_program_change_detected_and_markdown_irrelevant(self):
        installed=self.root/'install'
        (installed/'app').mkdir(parents=True);(installed/'runtime').mkdir();(installed/'data').mkdir()
        source=installed/'app/main.py';source.write_text('pass')
        (installed/'run_daily.py').write_text('# bootstrap')
        run_daily.seal(installed)
        self.addCleanup(lambda: [os.chmod(p,0o600) for p in installed.rglob('*') if p.is_file()])
        (installed/'README.md').write_text('report zero')
        run_daily.verify(installed)
        os.chmod(source,0o600);source.write_text('changed')
        with self.assertRaises(ValueError):run_daily.verify(installed)


if __name__=='__main__':unittest.main()

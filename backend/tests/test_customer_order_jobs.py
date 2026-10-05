import asyncio
from io import BytesIO
import os
import pickle
from pathlib import Path
import sys
import time

import openpyxl
import pytest
from fastapi import HTTPException

from app.services import customer_order_jobs as jobs
from app.services.customer_order_history import parse_workbook
from app.workers.customer_order_job import job_slot


@pytest.fixture(autouse=True)
def private_job_lock(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "LOCK_PATH", tmp_path / "job.lock")


def workbook_bytes():
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = 'ITEM表'
    sheet.append([]); sheet.append([])
    sheet.append(['Contract No.', 'SO#/Reference', 'P/O#:', '产品编号', '數量'])
    sheet.append(['CTR', '00123', '00090', '00045', 100])
    result = BytesIO(); workbook.save(result)
    return result.getvalue()


def test_real_worker_preserves_history_parser_output():
    source = workbook_bytes()
    expected = parse_workbook(source)
    actual = asyncio.run(jobs.run_order_job(parse_workbook, source))
    assert actual == expected


def test_concurrent_job_is_rejected_without_changing_existing_lock():
    with job_slot(jobs.LOCK_PATH):
        with pytest.raises(HTTPException) as error:
            asyncio.run(jobs.run_order_job(parse_workbook, workbook_bytes()))
        assert error.value.status_code == 429
    assert asyncio.run(jobs.run_order_job(parse_workbook, workbook_bytes()))


def test_database_connection_released_before_cpu_work(monkeypatch):
    class Database:
        new = dirty = deleted = ()
        released = False
        def rollback(self): self.released = True
    db = Database()
    def execute(*args):
        assert db.released
        return 'finished'
    monkeypatch.setattr(jobs, '_execute', execute)
    assert asyncio.run(jobs.run_order_job(parse_workbook, b'', db=db)) == 'finished'
    db.new = [object()]
    with pytest.raises(RuntimeError, match='pending database writes'):
        asyncio.run(jobs.run_order_job(parse_workbook, b'', db=db))


def test_unknown_operation_is_never_dispatched():
    with pytest.raises(RuntimeError, match='Unsupported'):
        asyncio.run(jobs.run_order_job(eval, '1+1'))


def test_local_admission_rejects_before_spooling_or_starting_child(monkeypatch):
    def unexpected(*args):
        raise AssertionError('A second child must not start')
    monkeypatch.setattr(jobs, '_run_worker', unexpected)
    with jobs._local_slot:
        with pytest.raises(HTTPException) as error:
            asyncio.run(jobs.run_order_job(parse_workbook, b''))
        assert error.value.status_code == 429


def test_real_isolated_export_keeps_customer_mapping_and_workbook_formulas():
    from test_customer_order_goliath import po, template
    from app.api.customer_order import _export_mapped_customer_schedule
    kwargs = dict(factory_id='huadeng', customer_code='goliath', received_date='2026-09-07',
        po_files=[('po.pdf', po())], schedule_file_name='latest.xlsx', schedule_content=template())
    output, name, preview = asyncio.run(jobs.run_order_job(_export_mapped_customer_schedule, **kwargs))
    assert preview['rows'][0]['reference_no'] == 'T_10130-PHK26_00694'
    workbook = openpyxl.load_workbook(BytesIO(output))
    assert workbook['接单表']['N4'].value == '=P4*7.75'
    assert workbook['ITEM表']['L5'].value == 2


def test_cpu_worker_does_not_block_other_async_requests(monkeypatch, tmp_path):
    script = tmp_path / 'cpu.py'
    script.write_text('''import time, pickle, sys
end=time.monotonic()+1.0
while time.monotonic()<end: sum(range(5000))
with open(sys.argv[1], 'wb') as f: pickle.dump({'value': 'done'}, f)
''')
    original = jobs._run_worker
    monkeypatch.setattr(jobs, '_run_worker', lambda command, budget: original(
        [sys.executable, str(script), command[4]], budget))
    async def scenario():
        ticks = 0
        task = asyncio.create_task(jobs.run_order_job(parse_workbook, b''))
        while not task.done():
            await asyncio.sleep(0.02)
            ticks += 1
        assert await task == 'done'
        assert ticks >= 20
    asyncio.run(scenario())


@pytest.mark.skipif(os.name == 'nt', reason='Linux production process-group regression')
@pytest.mark.parametrize('reason', ['cancel', 'deadline'])
def test_abandoned_job_reaps_worker_and_descendant(monkeypatch, tmp_path, reason):
    from test_customer_order_ocr_limits import _alive
    pidfile = tmp_path / 'pids.txt'
    script = tmp_path / 'hang.py'
    script.write_text('''import os, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, os.getcwd())
from app.services.customer_order_ocr import _run_worker, OcrBudget
os.environ['RR_CUSTOMER_ORDER_JOB_WORKER']='1'
child_code="import os,subprocess,sys,time;from pathlib import Path;p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);Path(sys.argv[1]).write_text(f'{os.getpid()} {p.pid}');time.sleep(30)"
_run_worker([sys.executable,'-c',child_code,sys.argv[1]],OcrBudget())
''')
    original = jobs._run_worker
    monkeypatch.setattr(jobs, '_run_worker', lambda command, budget: original(
        [sys.executable, str(script), str(pidfile)], budget))
    async def scenario():
        budget = jobs.JobBudget()
        token = jobs._budget.set(budget)
        try:
            task = asyncio.create_task(jobs.run_order_job(parse_workbook, b''))
            for _ in range(100):
                if pidfile.exists(): break
                await asyncio.sleep(0.02)
            assert pidfile.exists()
            pids = [int(pid) for pid in pidfile.read_text().split()]
            if reason == 'cancel':
                task.cancel()
                with pytest.raises(asyncio.CancelledError): await task
            else:
                budget.deadline = time.monotonic() - 1
                with pytest.raises(HTTPException) as error: await task
                assert error.value.status_code == 504
            assert all(not _alive(pid) for pid in pids)
        finally:
            jobs._budget.reset(token)
    asyncio.run(scenario())

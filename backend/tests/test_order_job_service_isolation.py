"""Real HTTP auth/carton reads remain responsive while a file job uses CPU."""
from concurrent.futures import ThreadPoolExecutor
import sys
import time

from test_molding_sample_api import make_client, login_as
from test_customer_order_goliath import po, template


def test_busy_order_job_does_not_delay_carton_or_login(monkeypatch, tmp_path):
    from app.services import customer_order_jobs as jobs
    marker = tmp_path / 'processing'
    script = tmp_path / 'cpu_order.py'
    script.write_text('''import os,sys,time,pickle
from pathlib import Path
sys.path.insert(0,os.getcwd())
from app.workers.customer_order_job import compute
Path(sys.argv[3]).write_text('running')
end=time.monotonic()+4
while time.monotonic()<end: sum(range(10000))
with open(sys.argv[2],'wb') as f: pickle.dump({'value':compute(Path(sys.argv[1]))},f)
''')
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        # make_client deliberately reloads app modules for its private database.
        from app.services import customer_order_jobs as jobs
        original = jobs._run_worker
        monkeypatch.setattr(jobs, 'LOCK_PATH', tmp_path / 'isolation.lock')
        monkeypatch.setattr(jobs, '_run_worker', lambda command, budget: original(
            [sys.executable, str(script), command[3], command[4], str(marker)], budget))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(client.post, '/api/customer-orders/goliath/preview-batch',
                data={'factory_id': 'huadeng', 'received_date': '2026-09-30'},
                files=[('po_files', ('customer.pdf', po(), 'application/pdf')),
                       ('schedule_file', ('schedule.xlsx', template(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))])
            for _ in range(200):
                if marker.exists(): break
                time.sleep(0.02)
            assert marker.exists(), future.result().text if future.done() else 'Job did not start'
            for url in ('/api/auth/me', '/api/carton-procurement/master-data?factory_id=huaxing',
                        '/api/carton-procurement/orders?factory_id=huaxing'):
                started = time.monotonic()
                response = client.get(url)
                assert response.status_code == 200, response.text
                assert time.monotonic() - started < 2, url
            result = future.result(timeout=15)
            assert result.status_code == 200, result.text
            assert result.json()['summary']['total'] == 1

"""Verify final ZIP bytes and smoke the unpacked application with a host Python.

This is deliberately not reported as Windows-native or rendered browser testing.
All runtime databases are created in disposable copies, never inside delivery ZIPs.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from zipfile import ZipFile

LOCAL_HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch(address, path, expected=200, headers=None):
    request = urllib.request.Request(address + path, headers=headers or {})
    try:
        with LOCAL_HTTP.open(request, timeout=10) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, body = error.code, error.read()
    assert status == expected, (path, status, body[:300])
    return body


def serve(package, python, config):
    environment = os.environ.copy()
    environment.pop('PYTHONPATH', None)
    environment.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
    log_path = package.parent / 'host-smoke.log'
    with log_path.open('ab') as log:
        process_options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {}
        process = subprocess.Popen([python, '-B', str(package / 'launch.py'), '--no-browser'],
            cwd=package, env=environment, stdout=log, stderr=log, **process_options)
        try:
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise AssertionError(log_path.read_text(errors='replace')[-5000:])
                try:
                    instance = json.loads((package / 'data/running.json').read_text())
                    address = f"http://127.0.0.1:{instance['port']}"
                    identity = json.loads(fetch(address, '/api/trial-instance'))
                    if identity['id'] == instance['id']:
                        break
                except (OSError, ValueError, urllib.error.URLError):
                    time.sleep(.1)
            else:
                raise AssertionError('Unpacked application did not become ready')
            health = json.loads(fetch(address, '/api/health'))
            expected_service = 'huakang-b-jp-trial' if config['kind'] == 'jp' else 'customer-order-trial'
            assert health['service'] == expected_service, health
            html = fetch(address, '/').decode()
            assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html)
            assert assets, 'Built page has no local assets'
            for asset in assets:
                assert fetch(address, asset), asset
            fetch(address, '/api/health', expected=403, headers={'Host': 'unrelated.invalid'})
            fetch(address, '/api/health', expected=403, headers={'Origin': 'https://unrelated.invalid'})
            if config['kind'] == 'orders':
                application = json.loads(fetch(address, '/api/config'))
                assert application['factory_id'] == config['factory_id']
                assert application['customers']
                ledger = json.loads(fetch(address, '/api/customer-order-ledger/lines?factory_id=' + config['factory_id']))
                assert ledger['total'] == 0, 'Delivery must start with an empty ledger'
                assert json.loads(fetch(address, '/api/orders/exports'))['total'] == 0
            return {'service': health['service'], 'assets': len(assets), 'factory_id': config['factory_id']}
        finally:
            if process.poll() is None:
                process.send_signal(signal.CTRL_BREAK_EVENT if os.name == 'nt' else signal.SIGINT)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    raise AssertionError('Launcher did not shut down cleanly')
            assert process.returncode in (0, 130, -signal.SIGINT), log_path.read_text(errors='replace')[-5000:]
            assert not (package / 'data/running.json').exists(), 'Running marker survived shutdown'


def verify(output, python):
    records = json.loads((output / '交付文件校验.json').read_text(encoding='utf-8'))
    results = []
    for record in records:
        archive = output / record['file']
        assert sha256(archive.read_bytes()).hexdigest() == record['sha256'], archive
        with tempfile.TemporaryDirectory(prefix='试用 包校验 ') as folder:
            directory = Path(folder)
            with ZipFile(archive) as zipped:
                assert zipped.testzip() is None
                assert all(not Path(name).is_absolute() and '..' not in Path(name).parts for name in zipped.namelist())
                zipped.extractall(directory)
            roots = list(directory.iterdir())
            assert len(roots) == 1 and roots[0].is_dir()
            package = roots[0]
            assert not (package / 'data').exists()
            manifest = json.loads((package / 'PACKAGE-MANIFEST.json').read_text())
            actual = {p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file()}
            assert actual == {row['path'] for row in manifest['files']} | {'PACKAGE-MANIFEST.json'}
            for row in manifest['files']:
                path = package / row['path']
                assert path.stat().st_size == row['bytes']
                assert sha256(path.read_bytes()).hexdigest() == row['sha256'], path
                assert path.suffix not in {'.sqlite3', '.db', '.pyc'} and path.name != '.env', path
            config = json.loads((package / 'trial.json').read_text())
            assert config['factory_id'] == record['factory_id'] == manifest['factory_id']
            assert (package / 'runtime/python.exe').read_bytes()[:2] == b'MZ'
            pth = (package / 'runtime/python312._pth').read_text()
            assert 'Lib/site-packages' in pth and '../backend' in pth and 'import site' in pth
            assert b'"runtime\\python.exe" -X utf8 launch.py\r\n' in (package / 'START.cmd').read_bytes()
            instructions = '演示操作说明.txt' if config['kind'] == 'jp' else '演示操作.txt'
            assert (package / '演示资料' / instructions).is_file()
            first = serve(package, python, config)
            second = serve(package, python, config)
            assert first == second
            results.append({'file': archive.name, 'sha256': record['sha256'], 'files_verified': len(manifest['files']),
                'host_http_start_and_restart': first, 'windows_native': 'not_run', 'rendered_browser': 'not_run'})
            print(json.dumps(results[-1], ensure_ascii=False), flush=True)
    (output / '交付包验证结果.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--python', default=sys.executable)
    arguments = parser.parse_args()
    verify(arguments.output.resolve(), arguments.python)

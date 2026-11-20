"""Start the single local enterprise system; reuse backend/.env and its data."""
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time
import urllib.request
from urllib.parse import urlsplit
from ipaddress import ip_address
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.local-dev' / 'unified-system'


def main():
    config = {**dotenv_values(ROOT / 'backend/.env'), **os.environ}
    mobile_host = config.get('QC_MOBILE_LAN_HOST', '')
    mobile = urlsplit(config.get('QC_MOBILE_PUBLIC_ORIGIN', ''))
    if mobile_host:
        address = ip_address(mobile_host)
        if (config.get('APP_ENV') == 'production' or not address.is_private or address.is_unspecified
                or mobile.scheme != 'http' or mobile.hostname != mobile_host or not mobile.port
                or mobile.path or mobile.query or mobile.fragment or mobile.username):
            raise SystemExit('Local mobile listener requires a matching explicit private HTTP origin.')
        with socket.socket(socket.AF_INET6 if address.version == 6 else socket.AF_INET) as probe:
            probe.bind((mobile_host, mobile.port))
    for port in (5173, 8000, 3411):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(('127.0.0.1', port))
            except OSError:
                raise SystemExit(f'Port {port} is occupied. Existing services were not stopped.')
    python = ROOT / 'backend/.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    node = shutil.which('node')
    if not python.is_file() or not node:
        raise SystemExit('Install the backend .venv and Node.js first.')
    STATE.mkdir(parents=True, exist_ok=True)
    jobs = [
        ('api', [str(python), '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'], ROOT / 'backend'),
        ('web', [node, str(ROOT / 'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '5173', '--strictPort'], ROOT),
    ]
    if mobile_host:
        jobs.append(('mobile', [str(python), '-m', 'uvicorn', 'app.qc_mobile_app:app',
                     '--host', mobile_host, '--port', str(mobile.port)], ROOT / 'backend'))
    children, logs = [], []
    pid_path = STATE / 'launcher.pid'
    pid_path.write_text(str(os.getpid()))
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        for name, command, cwd in jobs:
            log = (STATE / f'{name}.log').open('a')
            logs.append(log)
            env = dict(os.environ)
            if name == 'api':
                env['QC_DEPARTMENT_MANAGED'] = 'true'
            else:
                env['VITE_API_PROXY_TARGET'] = 'http://127.0.0.1:8000'
            children.append(subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=log,
                start_new_session=os.name != 'nt'))
        urls = ['http://127.0.0.1:8000/health', 'http://127.0.0.1:5173/']
        if mobile_host:
            urls.append(config['QC_MOBILE_PUBLIC_ORIGIN'].rstrip('/') + '/api/qc-mobile/app/')
        for url in urls:
            for _ in range(90):
                if any(child.poll() is not None for child in children):
                    raise RuntimeError(f'A service exited; inspect {STATE}')
                try:
                    with urllib.request.urlopen(url, timeout=1) as response:
                        if response.status == 200:
                            break
                except Exception:
                    time.sleep(0.5)
            else:
                raise RuntimeError(f'Service did not become ready: {url}')
        print('Enterprise system ready: http://127.0.0.1:5173/modules/qc/inspection-operations?factory=huaxing', flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(1)
        raise RuntimeError(f'A service exited; inspect {STATE}')
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate() if os.name == 'nt' else os.killpg(child.pid, signal.SIGTERM)
        for child in children:
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill() if os.name == 'nt' else os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        for log in logs:
            log.close()
        pid_path.unlink(missing_ok=True)


if __name__ == '__main__':
    main()

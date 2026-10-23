"""Owned synthetic API subprocess for P5c; never boots the configured business DB."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]


def validate_copy(database, *, root=ROOT):
    database = Path(database).resolve()
    if not database.is_relative_to((root/'.tmp').resolve()) or database.name != 'cutting.db' or not database.is_file():
        raise ValueError('Independent HTTP probe requires an existing isolated cutting.db')
    marker = database.parent/'fixture.json'
    if not marker.is_file() or json.loads(marker.read_text(encoding='utf-8'))['kind'] != 'cutting-synthetic-copy':
        raise ValueError('Synthetic copy provenance is required')
    with sqlite3.connect(database.as_uri()+'?mode=ro', uri=True) as db:
        users = [row[0] for row in db.execute('SELECT username FROM auth_users')]
        if len(users) != 8 or any(not name.startswith('p5b-') for name in users):
            raise ValueError('Only the eight synthetic fixture identities are accepted')
    return database


def serve(database, folder):
    database = validate_copy(database)
    folder = Path(folder).resolve()
    if folder != database.parent:
        raise ValueError('Probe output must share the exclusive copy directory')
    instance = os.environ.get('CUTTING_PROBE_INSTANCE')
    if not instance:
        raise ValueError('Owned probe instance identity is required')
    # Set before any application import; app.db must never load a configured DB.
    os.environ.update(DATABASE_URL='sqlite://', SEED_DEFAULT_ACCOUNTS='false')
    sys.path.insert(0, str(ROOT/'backend'))
    import uvicorn
    from datetime import date, datetime
    from zoneinfo import ZoneInfo
    from fastapi import FastAPI
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import Session
    from app.api import auth, cutting_operations, warehouse_operations
    from app.core.config import settings
    from app.db import get_db
    from app.services import cutting_planning, cutting_exports, warehouse_operations as warehouse
    from test_cutting_http_soak import Diagnostics

    engine = create_engine('sqlite:///'+database.as_posix(), connect_args={'check_same_thread':False, 'timeout':20})
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, record):
        connection.execute('PRAGMA foreign_keys=ON')
    def session():
        with Session(engine, expire_on_commit=False) as db:
            yield db
    settings.cutting_ops_enabled = True
    settings.authz_mode = 'enforce'
    settings.session_cookie_secure = False
    settings.cutting_period_admin_acceptance = False
    warehouse.business_now = lambda: datetime(2026, 12, 15, 12, tzinfo=ZoneInfo('Asia/Shanghai'))
    cutting_exports.business_now = warehouse.business_now
    cutting_planning.business_today = lambda: date(2026, 12, 15)
    app = FastAPI()
    for router in [auth.router, cutting_operations.router, warehouse_operations.router]:
        app.include_router(router)
    app.dependency_overrides[get_db] = session
    diagnostic = Diagnostics(SimpleNamespace(app=app, engine=engine))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    stop = threading.Event()
    server = None
    try:
        sock.bind(('127.0.0.1', 0)); sock.listen(128)
        server = uvicorn.Server(uvicorn.Config(app, lifespan='off', access_log=False, log_level='error', timeout_graceful_shutdown=10))
        def control():
            while not stop.wait(.1):
                if server.started and not (folder/'ready.json').exists():
                    (folder/'ready.json').write_text(json.dumps(dict(pid=os.getpid(), port=sock.getsockname()[1], instance=instance)), encoding='utf-8')
                if (folder/'stop').exists():
                    server.should_exit = True
                    return
        watcher = threading.Thread(target=control, daemon=True); watcher.start()
        diagnostic.start()
        server.run(sockets=[sock])
    finally:
        stop.set()
        diagnostic.close()
        (folder/'diagnostics.json').write_text(json.dumps(dict(pid=os.getpid(), requests=diagnostic.rows,
            lock_spans=diagnostic.lock_spans, heartbeat_gaps=diagnostic.gaps), ensure_ascii=False), encoding='utf-8')
        sock.close(); engine.dispose()


@contextmanager
def independent_http(database):
    database = validate_copy(database)
    folder = database.parent
    if any((folder/name).exists() for name in ['ready.json','stop','diagnostics.json']):
        raise ValueError('Independent probe directory must not be reused')
    instance = uuid4().hex
    env = dict(os.environ, DATABASE_URL='sqlite://', SEED_DEFAULT_ACCOUNTS='false', PYTHONUTF8='1', PYTHONIOENCODING='utf-8', CUTTING_PROBE_INSTANCE=instance)
    process = None
    with (folder/'api.log').open('w', encoding='utf-8') as log:
        try:
            process = subprocess.Popen([sys.executable, str(Path(__file__)), str(database)], cwd=ROOT/'backend', env=env,
                stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
            deadline = time.monotonic()+60
            while not (folder/'ready.json').exists():
                if process.poll() is not None or time.monotonic()>deadline:
                    raise RuntimeError('Owned independent API did not start; see api.log')
                time.sleep(.1)
            ready = json.loads((folder/'ready.json').read_text(encoding='utf-8'))
            # Windows venv python.exe is a launcher; the serving interpreter
            # has a different PID. Bind readiness to this fresh process token.
            if ready.get('instance') != instance or process.poll() is not None:
                raise RuntimeError('Independent API identity mismatch')
            yield f"http://127.0.0.1:{ready['port']}"
        finally:
            if process is not None:
                (folder/'stop').touch(exist_ok=False)
                try:
                    process.wait(timeout=45)
                except subprocess.TimeoutExpired:
                    # Only this Popen-owned synthetic API, never a selected service.
                    if sys.platform=='win32':
                        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,check=True,
                            creationflags=subprocess.CREATE_NO_WINDOW)
                    else:process.kill()
                    process.wait(timeout=10)
                    raise RuntimeError('Owned independent API failed graceful shutdown')
                if process.returncode:
                    raise RuntimeError('Owned independent API exited with failure; see api.log')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Requires one isolated copy path')
    serve(sys.argv[1], Path(sys.argv[1]).parent)

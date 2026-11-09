"""Launch one packaged, loopback-only factory trial without installing Python."""
from __future__ import annotations

import argparse
import http.client
import json
import logging
import os
from pathlib import Path
import socket
import sys
import threading
import time
from uuid import uuid4
import webbrowser


class InstanceLock:
    def __init__(self, path: Path):
        self.stream = path.open('a+b')
        self.stream.seek(0, os.SEEK_END)
        if self.stream.tell() == 0:
            self.stream.write(b'0')
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            self.stream.close()
            raise RuntimeError('本文件夹的试用程序已经启动，请使用已打开的页面。')

    def close(self):
        if self.stream.closed:
            return
        self.stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        self.stream.close()


def instance_is_ready(port: int, expected_id: str) -> bool:
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=1)
    try:
        connection.request('GET', '/api/trial-instance')
        response = connection.getresponse()
        payload = json.loads(response.read(4096))
        return response.status == 200 and payload.get('id') == expected_id
    except (OSError, ValueError, http.client.HTTPException):
        return False
    finally:
        connection.close()


def reopen_running(data: Path, no_browser: bool) -> bool:
    try:
        value = json.loads((data / 'running.json').read_text(encoding='utf-8'))
        port = value['port']
        if isinstance(port, int) and 1 <= port <= 65535 and instance_is_ready(port, value['id']):
            print(f'程序已启动：http://127.0.0.1:{port}/', flush=True)
            if not no_browser:
                webbrowser.open(f'http://127.0.0.1:{port}/')
            return True
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parent
    config = json.loads((root / 'trial.json').read_text(encoding='utf-8'))
    if config['kind'] not in {'jp', 'orders'}:
        raise RuntimeError('试用包类型不正确，请重新解压完整文件。')
    if not 0 <= arguments.port <= 65535:
        raise RuntimeError('端口无效。')
    data = root / 'data'
    data.mkdir(exist_ok=True)
    try:
        lock = InstanceLock(data / '.trial.lock')
    except RuntimeError:
        if reopen_running(data, arguments.no_browser):
            return 0
        raise
    instance = uuid4().hex
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server = None
    log = None
    try:
        # Keep the selected socket open; another process cannot claim it between
        # port selection and Uvicorn startup.
        listener.bind(('127.0.0.1', arguments.port))
        listener.listen(128)
        port = listener.getsockname()[1]
        sys.path.insert(0, str(root / 'backend'))
        os.environ['PYTHONUTF8'] = '1'
        os.environ['OMP_THREAD_LIMIT'] = '1'
        tesseract = root / 'ocr' / 'tesseract.exe'
        if os.name == 'nt' and tesseract.is_file():
            os.environ['TESSERACT_CMD'] = str(tesseract)
            os.environ['TESSDATA_PREFIX'] = str(tesseract.parent / 'tessdata')
        from app.main import create_app
        import uvicorn

        options = dict(data_dir=data, static_dir=root / 'web', host='127.0.0.1', port=port)
        if config['kind'] == 'orders':
            options['factory_id'] = config['factory_id']
        app = create_app(**options)

        # Registered before the root StaticFiles mount, so the local reopening
        # check cannot be served by an unrelated program using an old port.
        async def identity():
            return {'id': instance, 'factory_id': config['factory_id']}
        from starlette.routing import Route
        from starlette.responses import JSONResponse
        async def identity_response(request):
            return JSONResponse(await identity(), headers={'Cache-Control': 'no-store'})
        app.router.routes.insert(0, Route('/api/trial-instance', identity_response))

        log = logging.FileHandler(data / 'startup.log', encoding='utf-8')
        log.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logging.getLogger('uvicorn.error').addHandler(log)
        configuration = uvicorn.Config(app, host='127.0.0.1', port=port, access_log=False,
            log_level='info', log_config=None, timeout_graceful_shutdown=5)
        server = uvicorn.Server(configuration)
        address = f'http://127.0.0.1:{port}/'
        (data / 'running.json').write_text(json.dumps({'port': port, 'id': instance}), encoding='utf-8')
        print(f"\n{config['name']}\n浏览器地址：{address}\n试用数据：{data}\n", flush=True)
        print('请保持这个窗口打开。结束试用请按 Ctrl+C；数据会保留。', flush=True)

        def open_when_ready():
            for _ in range(100):
                if server.should_exit:
                    return
                if instance_is_ready(port, instance):
                    if not arguments.no_browser:
                        webbrowser.open(address)
                    return
                time.sleep(0.1)
        threading.Thread(target=open_when_ready, daemon=True).start()
        server.run(sockets=[listener])
        return 0 if server.started else 1
    finally:
        if server is not None:
            server.should_exit = True
        listener.close()
        try:
            current = json.loads((data / 'running.json').read_text(encoding='utf-8'))
            if current.get('id') == instance:
                (data / 'running.json').unlink()
        except (OSError, ValueError):
            pass
        if log is not None:
            logging.getLogger('uvicorn.error').removeHandler(log)
            log.close()
        lock.close()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
    except Exception as error:
        import traceback
        root = Path(__file__).resolve().parent
        print(f'\n启动未完成：{error}\n请先完整解压文件，再双击 START.cmd。', file=sys.stderr)
        try:
            (root / 'data').mkdir(exist_ok=True)
            with (root / 'data' / 'startup-error.log').open('a', encoding='utf-8') as stream:
                traceback.print_exc(file=stream)
        except OSError:
            pass
        raise SystemExit(1)

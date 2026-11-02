"""Own the private QC process during the local Nexus API lifespan.

Production uses its Compose sidecar (managed=false). No database is copied here:
all starts reuse the configured persistent directory. Only our child is stopped.
"""
import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import secrets
import shutil
import socket
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr

ROOT = Path(__file__).resolve().parents[3]


@asynccontextmanager
async def managed_qc_department(settings):
    if not settings.qc_department_managed:
        yield None
        return
    target = urlsplit(settings.qc_department_url)
    if target.scheme != 'http' or target.hostname != '127.0.0.1' or not target.port or target.path not in ('', '/'):
        raise RuntimeError('Managed QC requires an http://127.0.0.1:<port> URL')
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node.js with node:sqlite is required for the QC workbench')
    # Never attach to, stop, or overwrite an unknown service on this port.
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(('127.0.0.1', target.port))
        except OSError as exc:
            raise RuntimeError(f'QC port {target.port} is occupied; no existing process was stopped') from exc
    data = Path(settings.qc_department_data_dir).expanduser()
    if not data.is_absolute():
        raise RuntimeError('QC_DEPARTMENT_DATA_DIR must be an absolute persistent path')
    data.mkdir(parents=True, exist_ok=True)
    token_path = data.parent / 'gateway-token'
    token = settings.qc_department_gateway_token.get_secret_value()
    if not token:
        try:
            with open(token_path, 'x', opener=lambda path, flags: os.open(path, flags, 0o600)) as handle:
                handle.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        token = token_path.read_text().strip()
    if len(token) < 32:
        raise RuntimeError('QC gateway token must contain at least 32 characters')
    settings.qc_department_gateway_token = SecretStr(token)
    env = {**os.environ, 'HOST': '127.0.0.1', 'PORT': str(target.port),
           'DATA_PATH': str(data), 'QC_DEPARTMENT_GATEWAY_TOKEN': token, 'QC_MANAGED_PARENT': '1'}
    process = None
    with (data.parent / 'service.log').open('a') as log:
        try:
            process = await asyncio.create_subprocess_exec(node, 'server/server.js',
                cwd=ROOT / 'services/qc-department', env=env, stdin=asyncio.subprocess.PIPE,
                stdout=log, stderr=log)
            async with httpx.AsyncClient(trust_env=False, timeout=1) as client:
                for _ in range(80):
                    if process.returncode is not None:
                        raise RuntimeError('QC service exited; inspect its service.log (Node must support node:sqlite)')
                    try:
                        response = await client.get(settings.qc_department_url.rstrip('/') + '/api/companies',
                            headers={'X-QC-Gateway-Token': token})
                        if response.status_code == 200 and isinstance(response.json().get('companies'), list):
                            break
                    except (httpx.HTTPError, ValueError):
                        pass
                    await asyncio.sleep(0.1)
                else:
                    raise RuntimeError('QC service did not become ready; inspect its service.log')
            yield process
        finally:
            if process is not None:
                if process.stdin:
                    process.stdin.close()
                if process.returncode is None:
                    try:
                        process.terminate()
                    except ProcessLookupError:
                        pass
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()

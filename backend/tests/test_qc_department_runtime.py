"""Real child lifecycle, restart persistence and occupied-port ownership."""
import asyncio
import importlib
from pathlib import Path
import socket
import sqlite3
from types import SimpleNamespace

import httpx
from pydantic import SecretStr
import pytest


def configuration(tmp_path, port):
    return SimpleNamespace(qc_department_managed=True,
        qc_department_url=f'http://127.0.0.1:{port}',
        qc_department_data_dir=str(tmp_path / 'companies'),
        qc_department_gateway_token=SecretStr(''))


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def test_restart_preserves_data_and_exception_closes_child(tmp_path):
    runtime = importlib.import_module('app.services.qc_department_runtime')
    config = configuration(tmp_path, free_port())
    async def run():
        async with runtime.managed_qc_department(config) as first:
            async with httpx.AsyncClient(trust_env=False) as client:
                url = config.qc_department_url + '/api/bootstrap?company=hy-huaxing'
                headers = {'X-QC-Gateway-Token': config.qc_department_gateway_token.get_secret_value()}
                assert (await client.get(url, headers=headers)).status_code == 200
                assert (await client.get(url)).status_code == 403
            database = tmp_path / 'companies/hy-huaxing/qc.db'
            with sqlite3.connect(database) as connection:
                connection.execute('CREATE TABLE persistence_probe (value TEXT)')
                connection.execute("INSERT INTO persistence_probe VALUES ('retained')")
        assert first.returncode is not None
        token = (tmp_path / 'gateway-token').read_text()
        assert (tmp_path / 'gateway-token').stat().st_mode & 0o777 == 0o600
        config.qc_department_gateway_token = SecretStr('')
        with pytest.raises(RuntimeError, match='host startup failed'):
            async with runtime.managed_qc_department(config) as second:
                assert second.pid != first.pid
                assert (tmp_path / 'gateway-token').read_text() == token
                with sqlite3.connect(database) as connection:
                    assert connection.execute('SELECT value FROM persistence_probe').fetchone() == ('retained',)
                raise RuntimeError('host startup failed')
        assert second.returncode is not None
    asyncio.run(run())


def test_occupied_port_is_not_reused_or_stopped(tmp_path):
    runtime = importlib.import_module('app.services.qc_department_runtime')
    with socket.socket() as occupied:
        occupied.bind(('127.0.0.1', 0))
        occupied.listen()
        config = configuration(tmp_path, occupied.getsockname()[1])
        async def run():
            with pytest.raises(RuntimeError, match='occupied'):
                async with runtime.managed_qc_department(config):
                    pytest.fail('Must not use an existing service')
        asyncio.run(run())
        assert occupied.fileno() != -1
        assert not (tmp_path / 'companies').exists()


def test_external_mode_has_no_side_effects(tmp_path):
    runtime = importlib.import_module('app.services.qc_department_runtime')
    config = configuration(tmp_path, free_port())
    config.qc_department_managed = False
    async def run():
        async with runtime.managed_qc_department(config) as child:
            assert child is None
    asyncio.run(run())
    assert not (tmp_path / 'companies').exists()

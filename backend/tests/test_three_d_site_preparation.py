import importlib.util
from pathlib import Path
from sqlalchemy import select
import pytest
from test_three_d_connector import environment, post, registered


def test_prepare_keeps_existing_connections_and_only_adds_disabled_devices(environment):
    path = Path(__file__).resolve().parents[2] / 'deploy/three-d-printing/prepare_connections.py'
    spec = importlib.util.spec_from_file_location('site_prepare', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _, dbm, models, _, _, ids = environment
    rows = [{'machine_no':n,'ip':f'192.168.110.{n}'} for n in range(1,12)]
    with dbm.SessionLocal() as db:
        first = db.get(models.ThreeDPrintingPrinterConnection, ids[0])
        original = (first.lan_host, first.connection_owner, first.connection_enabled)
        assert module.prepare(db,rows)['created']==9
        db.commit()
        assert module.prepare(db,rows)=={'created':0,'existing':11,'sessions_started':0}
        db.commit()
        assert (first.lan_host,first.connection_owner,first.connection_enabled)==original
        added = list(db.scalars(select(models.ThreeDPrintingPrinterConnection).where(
            models.ThreeDPrintingPrinterConnection.printer_id.not_in(ids[:2]))))
        assert len(added)==9
        assert all(not row.connection_enabled and row.connection_owner=='edge-legacy' for row in added)
        observed=[{'machine_no':3,'ip':'192.168.110.33','cert_sha256':'b'*64}]
        module.prepare(db,observed,observed=True); db.commit()
        third=db.get(models.ThreeDPrintingPrinterConnection,ids[2])
        assert (third.lan_host,third.certificate_fingerprint)==('192.168.110.33','b'*64)
        revision=third.connection_revision
        module.prepare(db,observed,observed=True); db.commit()
        assert third.connection_revision==revision and not third.connection_enabled


@pytest.mark.parametrize("number", [16, 17, 18])
def test_prepare_new_machine_preserves_identity_and_stays_disabled(environment, number):
    path = Path(__file__).resolve().parents[2] / 'deploy/three-d-printing/prepare_connections.py'
    spec = importlib.util.spec_from_file_location('site_prepare_expansion', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _, dbm, models, service, clock, ids = environment
    with dbm.SessionLocal() as db:
        printer = models.ThreeDPrintingPrinter(id='isolated-new-device', factory_id='huakang-a',
            machine_no=number, name=f'{number}号机', created_at=clock[0].isoformat(), updated_at=clock[0].isoformat())
        db.add(printer)
        db.flush()
        rows = [{'machine_no':number, 'ip':f'10.33.30.{100+number}', 'credential_ref':f'printer-{number}', 'cert_sha256':'a'*64}]
        with pytest.raises(ValueError, match='already assigned'):
            module.prepare(db, [{**rows[0], 'credential_ref':'printer-01'}], observed=True)
        with pytest.raises(ValueError, match='certificate'):
            module.prepare(db, [{**rows[0], 'cert_sha256':''}], observed=True)
        assert module.prepare(db, rows, observed=True)['created'] == 1
        db.commit()
        connection = db.get(models.ThreeDPrintingPrinterConnection, printer.id)
        assert not connection.connection_enabled
        assert connection.connection_owner == 'edge-legacy'
        assert connection.credential_ref == f'printer-{number}'
        assert module.prepare(db, rows, observed=True)['created'] == 0
        with pytest.raises(ValueError, match='device identity'):
            module.prepare(db, [{**rows[0], 'credential_ref':'printer-06'}], observed=True)
        assert connection.credential_ref == f'printer-{number}'
        # Even with an admitted machine number, a prepared device cannot acquire a session.
        from fastapi import HTTPException
        with pytest.raises(HTTPException): service.connection(db, printer.id)


def test_backend_accepts_renumbered_observer_without_transferring_control(environment):
    _, dbm, models, service, _, ids = environment
    with dbm.SessionLocal() as db:
        printer = db.get(models.ThreeDPrintingPrinter, ids[0])
        printer.machine_no = 16
        connection = db.get(models.ThreeDPrintingPrinterConnection, printer.id)
        connection.connection_owner = service.OBSERVER
        db.flush()
        row, found = service.connection(db, printer.id)
        assert found.id == ids[0] and found.machine_no == 16
        assert row.credential_ref == 'printer-01' and row.connection_owner == service.OBSERVER
        db.commit()
    grant = post(environment, '/leases/acquire', registered(environment))
    assert grant['acquired'] and grant['machine_no'] == 16
    assert grant['credential_ref'] == 'printer-01'
    assert grant['control_verified'] is False


@pytest.mark.parametrize("number", [16, 17, 18, 0, 19])
def test_observer_cli_admits_new_machines_and_rejects_out_of_range_before_db(environment, monkeypatch, number):
    path = Path(__file__).resolve().parents[2] / 'deploy/three-d-printing/enable_observer.py'
    spec = importlib.util.spec_from_file_location('site_enable_expansion_cli', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    class Session:
        def __enter__(self):
            calls.append('session')
            return self

        def __exit__(self, *args):
            pass

        def commit(self):
            calls.append('commit')

    def enable(db, machine):
        assert isinstance(db, Session)
        calls.append(machine)
        return {'machine_no': machine, 'mode': 'cloud-observer'}

    monkeypatch.setattr(module, 'SessionLocal', Session)
    monkeypatch.setattr(module, 'enable', enable)
    if number in (0, 19):
        with pytest.raises(SystemExit) as exc:
            module.main(['--machine', str(number)])
        assert exc.value.code == 2
        assert calls == []
    else:
        module.main(['--machine', str(number)])
        assert calls == ['session', number, 'commit']

import importlib.util
from pathlib import Path
from sqlalchemy import select
from test_three_d_connector import environment


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

"""Ledger transaction outbox. Delivery to SQLite never runs in a Sales transaction."""
from uuid import uuid4
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from app.core.config import settings

KEY='qc_dossier_source_ids'


def mark(db, line):
    from app.services.qc_dossier import enabled
    if enabled(line.factory_id):db.info.setdefault(KEY,set()).add(line.id)


def collect(db, *_):
    if not settings.qc_dossier_enabled:return
    from app.models.customer_order_ledger import OrderLedgerLine,OrderLedgerLineSource
    for obj in list(db.new)+list(db.dirty):
        if isinstance(obj,OrderLedgerLine):mark(db,obj)
        elif isinstance(obj,OrderLedgerLineSource):db.info.setdefault(KEY,set()).add(obj.line_id)


def enqueue(db):
    if not settings.qc_dossier_enabled or db.in_nested_transaction():return
    from app.models.customer_order_ledger import OrderLedgerLine
    from app.models.qc_dossier import QcDossierOutbox
    from app.services.qc_dossier import snapshot,enabled,now
    db.flush()
    identities=db.info.pop(KEY,set())
    for identity in sorted(identities):
        line=db.get(OrderLedgerLine,identity)
        if line is not None and enabled(line.factory_id):
            db.add(QcDossierOutbox(id=uuid4().hex,factory=line.factory_id,source_id=identity,
                payload=snapshot(db,line),created_at=now(),delivered_at='',attempts=0,last_error=''))
    db.flush()


def clear(db, transaction):
    if transaction.parent is None:db.info.pop(KEY,None)


def install():
    for name,callback in [('before_flush',collect),('before_commit',enqueue),('after_transaction_end',clear)]:
        if not event.contains(Session,name,callback):event.listen(Session,name,callback)

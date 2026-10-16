"""Period fences run under the existing cutting -> fabric transaction lock order."""
from calendar import monthrange
from contextlib import nullcontext
from sqlalchemy import inspect, select, text
from app.models.cutting_period import CuttingPeriodEvent as Event
from app.services import cutting_ops as c


def schema_ready(bind):
    inspector = inspect(bind)
    if Event.__tablename__ not in inspector.get_table_names():
        return False
    if not {col.name for col in Event.__table__.columns} <= {col['name'] for col in inspector.get_columns(Event.__tablename__)}:
        return False
    with (bind.connect() if hasattr(bind, 'connect') else nullcontext(bind)) as connection:
        if connection.dialect.name == 'sqlite':
            names = set(connection.execute(text("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='cutting_ops_period_events'")).scalars())
            return {'cutting_period_no_update', 'cutting_period_no_delete'} <= names
        if connection.dialect.name == 'postgresql':
            return bool(connection.execute(text("SELECT 1 FROM pg_trigger WHERE tgrelid=to_regclass('cutting_ops_period_events') AND tgname='cutting_period_immutable' AND tgenabled IN ('O','A')")).scalar())
    return False


def ensure_schema(db):
    c.require(schema_ready(db.connection()), '内部月结需先完成0163显式迁移及证据保护', 503)


def history(db, *, optional=False):
    if optional and Event.__tablename__ not in inspect(db.connection()).get_table_names():
        return []
    ensure_schema(db)
    return list(db.scalars(select(Event).where(Event.factory_id == c.FACTORY).order_by(Event.version)))


def latest(history):
    return {e.month: e for e in history}


def locked(db):
    return {month: e for month, e in latest(history(db, optional=True)).items() if e.action == 'lock'}


def end_day(month):
    year, number = map(int, month.split('-'))
    return f'{month}-{monthrange(year, number)[1]:02d}'


def guard_days(db, *days):
    periods = locked(db)
    if periods:
        last = max(periods)
        c.require(not any(day and str(day) <= end_day(last) for day in days),
                  f'裁床内部已锁至 {last}，该操作影响已冻结月份或期初，请先按顺序反结')


def guard_price(db, root_batch_id):
    affected = [month for month, event in locked(db).items()
                if root_batch_id in event.data['snapshot'].get('price_roots', [])]
    c.require(not affected, '原批次成本已被锁月引用，请先反结相关月份：' + '、'.join(sorted(affected)))


def guard_warehouse(db, entries, body, request):
    if not request:
        return
    if body['kind'] in {'ISSUE', 'RETURN', 'CUTTING_RECEIPT', 'CUTTING_RECEIPT_VOID', 'CORRECTION'}:
        days = [body['business_date']]
        if body['kind'] in {'CUTTING_RECEIPT_VOID', 'CORRECTION'}:
            original = entries.get(body.get('original_id'))
            if original:
                days.append(original['business_date'])
        guard_days(db, *days)

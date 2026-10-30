"""Authorized native quote projections without view logs or lazy reference writes.

These are domain readers, not model-safe projections: consumers still have to
whitelist operational fields and gate financial projections independently.
"""
from fastapi import HTTPException
from sqlalchemy import select
from app.models.internal_quote import InternalQuote
from app.services import internal_quote as native
from app.services.business_authz import has_permission_for_departments


def authorize(user, factory_id, permission='internal_quote:read'):
    # Same decision predicate as the native ensure helper, without its commit
    # of a denied-access audit into the caller's read transaction. Native HTTP
    # auditing is unchanged; assistant runs keep their own failure evidence.
    if not has_permission_for_departments(user, permission, factory_id, native.ALL_QUOTE_DEPARTMENTS):
        raise HTTPException(403, "无授权范围内操作权限")


def record(db, user, factory_id, quote_id):
    with db.no_autoflush:
        authorize(user, factory_id)
        quote = db.scalar(select(InternalQuote).where(InternalQuote.factory_id == factory_id, InternalQuote.id == quote_id))
    if quote is None:
        raise HTTPException(404, "内部报价不存在或不属于当前厂区")
    return quote


def documents(db, user, factory_id, *, status='', keyword='', customer=''):
    """Full matching logical documents, in exactly the native page order."""
    with db.no_autoflush:
        authorize(user, factory_id)
        statement = native.quote_page_statement(factory_id, status=status, keyword=keyword, customer=customer)
        return list(db.scalars(statement.order_by(InternalQuote.updated_at.desc(), InternalQuote.id.desc())).all())


def detail(db, user, factory_id, quote_id):
    with db.no_autoflush:
        quote = record(db, user, factory_id, quote_id)
        return native.quote_to_out(db, quote)


def summary(db, user, factory_id, quote_id):
    with db.no_autoflush:
        authorize(user, factory_id, 'internal_quote:summary_read')
        quote = record(db, user, factory_id, quote_id)
        return native.get_quote_summary(db, quote.id, user, read_only=True)


def comparison(db, user, factory_id, target_quote_id, base_quote_id):
    from app.services.internal_quote_release import compare_quote_versions
    with db.no_autoflush:
        authorize(user, factory_id, 'internal_quote:summary_read')
        target = record(db, user, factory_id, target_quote_id)
        base = record(db, user, factory_id, base_quote_id)
        return compare_quote_versions(db, target.id, base.id, user)

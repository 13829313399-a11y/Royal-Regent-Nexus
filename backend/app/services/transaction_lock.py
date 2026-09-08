"""Database-owned, transaction-scoped serialization without schema changes."""
import hashlib

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session


def lock_transaction(db: Session, namespace: str, identity: str) -> None:
    connection = db.connection()
    transaction = db.get_transaction()
    state = db.info.get("business_transaction_locks")
    if state is None or state[0] is not transaction:
        state = (transaction, set())
        db.info["business_transaction_locks"] = state
    key = (namespace, identity)
    if key in state[1]:
        return
    try:
        if connection.dialect.name == "postgresql":
            lock_id = int.from_bytes(
                hashlib.sha256(f"{namespace}:{identity}".encode()).digest()[:8],
                "big", signed=True,
            )
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
        elif connection.dialect.name == "sqlite":
            # SQLAlchemy may have a logical transaction while sqlite has only
            # performed SELECTs. Reserve the writer before reading business state.
            if not connection.connection.driver_connection.in_transaction:
                connection.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            raise RuntimeError("Business transaction locking requires PostgreSQL or SQLite")
    except OperationalError as error:
        db.rollback()
        if "locked" in str(error).lower() or "busy" in str(error).lower():
            raise HTTPException(409, "其他操作正在保存，请稍后重新读取并重试") from error
        raise
    state[1].add(key)
    # Callers acquire this before modifying objects. Discard values loaded by
    # authentication/read queries while another transaction owned the lock.
    db.expire_all()

"""Fair local admission to cutting's existing SQLite writer transaction.

The database lock remains authoritative across engines/processes and warehouse
writes. Admission is only for a new cutting-master reservation; never wait for
this queue while already owning a SQLite transaction.
"""
from collections import deque
from threading import Condition, Lock
from time import monotonic
from weakref import WeakKeyDictionary

from sqlalchemy import event
from sqlalchemy.orm import Session

_engines = WeakKeyDictionary()
_engines_lock = Lock()
_LEASE = 'cutting_sqlite_admission'


class _Gate:
    def __init__(self):
        self.condition = Condition()
        self.queue = deque()

    def acquire(self, timeout):
        token = object()
        deadline = monotonic()+timeout
        with self.condition:
            self.queue.append(token)
            try:
                while self.queue[0] is not token:
                    remaining = deadline-monotonic()
                    if remaining <= 0:
                        raise TimeoutError('Cutting SQLite admission timed out')
                    self.condition.wait(remaining)
            except BaseException:
                self.queue.remove(token)
                self.condition.notify_all()
                raise
        return token

    def release(self, token):
        with self.condition:
            self.queue.remove(token)
            self.condition.notify_all()


def reserve(db, transaction, connection):
    """Lease until root transaction completion, including close/error rollback."""
    existing = db.info.get(_LEASE)
    if existing:
        if existing[0] is not transaction:
            raise RuntimeError('Stale cutting SQLite admission lease')
        return
    with _engines_lock:
        gate = _engines.get(connection.engine)
        if gate is None:
            gate = _engines[connection.engine] = _Gate()
    # Bound local admission by this connection's unchanged SQLite busy budget.
    timeout = connection.exec_driver_sql('PRAGMA busy_timeout').scalar_one()/1000
    token = gate.acquire(timeout)
    db.info[_LEASE] = (transaction, gate, token)


@event.listens_for(Session, 'after_transaction_end')
def _release(db, transaction):
    lease = db.info.get(_LEASE)
    if lease and lease[0] is transaction:
        db.info.pop(_LEASE)
        lease[1].release(lease[2])

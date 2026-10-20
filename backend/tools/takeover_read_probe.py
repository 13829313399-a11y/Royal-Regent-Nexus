"""Read-only ORM and authorization comparison for private takeover copies.

No initialization, login, HTTP lifespan or workers. Reports counts/digests only.
"""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import pkgutil
import socket
import sqlite3
import sys

# Direct CLI invocation must import the repository backend, not an installed app.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    def no_network(*args, **kwargs):
        raise RuntimeError('Network disabled in read-only takeover probe')
    socket.create_connection = socket.socket.connect = socket.socket.connect_ex = no_network
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from app.db import Base
    import app.models
    for module in pkgutil.iter_modules(app.models.__path__):
        importlib.import_module('app.models.' + module.name)
    from app.models.auth import AuthUser
    from app.services.auth import build_auth_context

    def engine_for(path):
        uri = Path(path).resolve(strict=True).as_uri() + '?mode=ro'
        def connect():
            connection = sqlite3.connect(uri, uri=True)
            connection.execute('PRAGMA query_only=ON')
            return connection
        return create_engine('sqlite://', creator=connect)

    def normalize(value):
        if isinstance(value, dict):
            return {str(k): normalize(v) for k, v in sorted(value.items())}
        if isinstance(value, (set, frozenset)):
            return sorted(normalize(v) for v in value)
        if isinstance(value, (tuple, list)):
            return [normalize(v) for v in value]
        return value

    instant = datetime.now(timezone.utc)
    def contexts(engine):
        with Session(engine) as db:
            return [normalize(asdict(build_auth_context(db, u, at=instant)))
                    for u in db.scalars(select(AuthUser).order_by(AuthUser.id)).all()]

    original, candidate = engine_for(sys.argv[1]), engine_for(sys.argv[2])
    try:
        before, after = contexts(original), contexts(candidate)
        if before != after:
            raise RuntimeError('Effective authorization context changed')
        read_tables = {}
        json_fields_checked = 0
        invalid_json = {}
        with Session(candidate) as db:
            for mapper in sorted(Base.registry.mappers, key=lambda m: m.local_table.name):
                # Decode every mapped row, including JSON/datetime/boolean types.
                rows = db.scalars(select(mapper.class_)).all()
                read_tables[mapper.local_table.name] = len(rows)
                for column in mapper.columns:
                    if not column.name.endswith('_json'):
                        continue
                    for row in rows:
                        value = getattr(row, column.key)
                        if not isinstance(value, str) or not value.strip():
                            continue
                        json_fields_checked += 1
                        try:
                            json.loads(value)
                        except ValueError:
                            key = mapper.local_table.name + '.' + column.name
                            invalid_json[key] = invalid_json.get(key, 0) + 1
        payload = json.dumps(before, ensure_ascii=False, sort_keys=True, default=str)
        report = {'effective_authorization_equal': True, 'users_checked': len(before),
                  'context_digest': hashlib.sha256(payload.encode()).hexdigest(),
                  'checked_at': instant.isoformat(), 'orm_tables': read_tables,
                  'orm_rows': sum(read_tables.values()), 'read_only': True,
                  'json_fields_checked': json_fields_checked, 'invalid_json': invalid_json,
                  'scope': 'existing accounts at one fixed instant; not formal employee acceptance'}
        Path(sys.argv[3]).write_text(json.dumps(report, indent=2), encoding='utf-8')
        if invalid_json:
            raise RuntimeError('Invalid JSON requires explicit historical-data review')
    finally:
        original.dispose()
        candidate.dispose()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

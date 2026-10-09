"""Outbox + sequence + source cursor share one durable transaction."""
from contextlib import contextmanager
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
from uuid import uuid4
import apsw


class Backpressure(Exception):
    pass


class Outbox:
    def __init__(self, path, *, queue_limit=1_000_000, min_free_bytes=100*1024*1024):
        path = Path(path).resolve()
        if str(path).startswith("\\\\"):
            raise ValueError("Outbox must be on a local disk")
        version = tuple(map(int, apsw.sqlitelibversion().split(".")))
        if not (version >= (3,51,3) or (3,50,7) <= version < (3,51,0) or (3,44,6) <= version < (3,45,0)):
            raise RuntimeError("SQLite WAL-reset fix required: 3.51.3+, 3.50.7 or 3.44.6")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path, self.queue_limit, self.min_free_bytes = path, queue_limit, min_free_bytes
        self.db = apsw.Connection(str(path))
        self.db.set_busy_timeout(5000)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("CREATE TABLE IF NOT EXISTS identity(singleton INTEGER PRIMARY KEY CHECK(singleton=1), stream_id TEXT NOT NULL, next_sequence INTEGER NOT NULL)")
        self.db.execute("INSERT OR IGNORE INTO identity VALUES(1,?,1)", (uuid4().hex,))
        self.db.execute("CREATE TABLE IF NOT EXISTS outbox(event_id TEXT PRIMARY KEY, stream_id TEXT NOT NULL, sequence INTEGER NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued', created_at TEXT NOT NULL, rejection TEXT, UNIQUE(stream_id,sequence))")
        self.db.execute('CREATE INDEX IF NOT EXISTS ix_outbox_pending ON outbox(state,sequence)')
        self.db.execute("CREATE TABLE IF NOT EXISTS cursors(source_id TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS local_quarantine(id TEXT PRIMARY KEY, source_id TEXT NOT NULL, evidence TEXT NOT NULL, created_at TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS acknowledgment(stream_id TEXT NOT NULL, sequence INTEGER NOT NULL, PRIMARY KEY(stream_id,sequence))")
        self.db.execute("CREATE TABLE IF NOT EXISTS ack_watermark(stream_id TEXT PRIMARY KEY, contiguous INTEGER NOT NULL)")

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def cursor(self, source_id):
        row = self.db.execute("SELECT value FROM cursors WHERE source_id=?", (source_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def append(self, source_id, events, cursor, rejected=()):
        if shutil.disk_usage(self.path.parent).free < self.min_free_bytes:
            raise Backpressure("low_disk_space")
        with self.transaction():
            size = self.db.execute("SELECT count(*) FROM outbox").fetchone()[0]
            if size+len(events) > self.queue_limit:
                raise Backpressure("queue_capacity")
            stream, sequence = self.db.execute("SELECT stream_id,next_sequence FROM identity WHERE singleton=1").fetchone()
            for event in events:
                event = dict(event, event_id=uuid4().hex, stream_id=stream, sequence=sequence)
                self.db.execute("INSERT INTO outbox(event_id,stream_id,sequence,payload,created_at) VALUES(?,?,?,?,?)", (event["event_id"], stream, sequence, json.dumps(event, ensure_ascii=False), datetime.now(UTC).isoformat()))
                sequence += 1
            for evidence in rejected:
                self.db.execute("INSERT INTO local_quarantine VALUES(?,?,?,?)", (uuid4().hex, source_id, json.dumps(evidence, ensure_ascii=False), datetime.now(UTC).isoformat()))
            self.db.execute("UPDATE identity SET next_sequence=? WHERE singleton=1", (sequence,))
            self.db.execute("INSERT INTO cursors VALUES(?,?) ON CONFLICT(source_id) DO UPDATE SET value=excluded.value", (source_id, json.dumps(cursor)))

    def pending(self, limit=100):
        return [json.loads(row[0]) for row in self.db.execute("SELECT payload FROM outbox WHERE state='queued' ORDER BY sequence LIMIT ?", (limit,))]

    def acknowledge(self, results):
        with self.transaction():
            for result in results:
                row = self.db.execute("SELECT stream_id,sequence FROM outbox WHERE event_id=?", (result.get("event_id"),)).fetchone()
                if not row:
                    continue
                if result.get("status") in {"persisted", "duplicate"}:
                    self.db.execute("INSERT OR IGNORE INTO acknowledgment VALUES(?,?)", row)
                    self.db.execute("DELETE FROM outbox WHERE event_id=?", (result["event_id"],))
                    self.db.execute("INSERT OR IGNORE INTO ack_watermark VALUES(?,0)", (row[0],))
                    watermark = self.db.execute("SELECT contiguous FROM ack_watermark WHERE stream_id=?", (row[0],)).fetchone()[0]
                    while self.db.execute("SELECT 1 FROM acknowledgment WHERE stream_id=? AND sequence=?", (row[0], watermark+1)).fetchone():
                        watermark += 1
                        self.db.execute("DELETE FROM acknowledgment WHERE stream_id=? AND sequence=?", (row[0], watermark))
                    self.db.execute("UPDATE ack_watermark SET contiguous=? WHERE stream_id=?", (watermark, row[0]))
                elif result.get("status") == "rejected" and not result.get("retryable",False):
                    self.db.execute("UPDATE outbox SET state='quarantine',rejection=? WHERE event_id=?", (str(result.get("code", "rejected"))[:100], result["event_id"]))

    def diagnostics(self):
        count, oldest = self.db.execute("SELECT count(*),min(created_at) FROM outbox WHERE state='queued'").fetchone()
        quarantine = self.db.execute("SELECT count(*) FROM outbox WHERE state='quarantine'").fetchone()[0]+self.db.execute("SELECT count(*) FROM local_quarantine").fetchone()[0]
        return dict(sqlite_version=apsw.sqlitelibversion(), queue_count=count, oldest_age_seconds=(datetime.now(UTC)-datetime.fromisoformat(oldest)).total_seconds() if oldest else 0, free_disk_bytes=shutil.disk_usage(self.path.parent).free, quarantine_count=quarantine)

    def close(self):
        self.db.close()

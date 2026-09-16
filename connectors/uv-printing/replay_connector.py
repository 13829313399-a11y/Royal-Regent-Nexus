"""Synthetic JSONL read-only reference adapter. Python standard library only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Connector redirects are disabled")


class Queue:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS sources (
                generation TEXT NOT NULL, path TEXT NOT NULL, identity TEXT NOT NULL,
                offset INTEGER NOT NULL, prefix_hash TEXT NOT NULL, machine_id TEXT NOT NULL,
                PRIMARY KEY(generation, path));
            CREATE TABLE IF NOT EXISTS pending (
                generation TEXT NOT NULL, event_id TEXT NOT NULL,
                payload TEXT NOT NULL, PRIMARY KEY(generation, event_id));
        """)

    def close(self):
        self.db.close()

    def pending(self, limit=100):
        return [json.loads(r[0]) for r in self.db.execute("SELECT payload FROM pending ORDER BY rowid LIMIT ?", (limit,))]

    def read_file(self, path, generation, machine_id):
        """Checkpoint and enqueue atomically; changing consumed bytes requires new generation."""
        if not generation or len(generation) > 128:
            raise ValueError("An explicit stable generation (1-128 chars) is required")
        path = Path(path).resolve(strict=True)
        added = 0
        with path.open("rb") as source:
            stat = os.fstat(source.fileno())
            identity = f"{stat.st_dev}:{stat.st_ino}"
            saved = self.db.execute("SELECT identity, offset, prefix_hash, machine_id FROM sources WHERE generation=? AND path=?", (generation, str(path))).fetchone()
            if saved and saved[3] != machine_id:
                raise ValueError("Source generation is already bound to a different machine")
            offset = saved[1] if saved else 0
            prefix = hashlib.sha256()
            remaining = offset
            while remaining:
                chunk = source.read(min(remaining, 1024 * 1024))
                if not chunk:
                    raise ValueError("Source truncated: choose a new generation")
                prefix.update(chunk)
                remaining -= len(chunk)
            if saved and (saved[0] != identity or saved[2] != prefix.hexdigest()):
                raise ValueError("Source rotated or rewritten: choose a new generation")
            while True:
                start = source.tell()
                line = source.readline(65537)
                if not line:
                    break
                if len(line) > 65536:
                    raise ValueError("JSONL record exceeds 64 KiB")
                if not line.endswith(b"\n"):
                    break  # A writer's partial last record is never consumed.
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    raise ValueError("JSONL records must be objects")
                if any(key in raw for key in ("connector_id", "factory_id", "generation", "machine_id", "source_event_id")):
                    raise ValueError("JSONL may not override connector scope or event identity")
                event_id = hashlib.sha256(f"{generation}|{identity}|{start}".encode()).hexdigest()
                event = {**raw, "generation": generation, "machine_id": machine_id, "source_event_id": event_id}
                event.setdefault("seq", start)
                if event.get("kind", "job") == "job":
                    # An ID-free row is one independent observation, never fuzzy-grouped by name.
                    event.setdefault("source_job_id", f"offset-{event_id}")
                payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                prefix.update(line)
                with self.db:
                    self.db.execute("INSERT INTO pending(generation,event_id,payload) VALUES(?,?,?)", (generation, event_id, payload))
                    self.db.execute("INSERT INTO sources VALUES(?,?,?,?,?,?) ON CONFLICT(generation,path) DO UPDATE SET offset=excluded.offset,prefix_hash=excluded.prefix_hash", (generation, str(path), identity, source.tell(), prefix.hexdigest(), machine_id))
                added += 1
        return added

    def flush(self, endpoint, token, factory_id="huakang-a", sender=None):
        """Explicit caller action only. Failures/rejections retain pending records."""
        parsed = urlsplit(endpoint)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Configure a direct HTTPS ingest endpoint without credentials/query/fragment")
        if factory_id != "huakang-a" or not token:
            raise ValueError("Scoped factory and connector token required")
        events = self.pending()
        if not events:
            return {"sent": 0, "removed": 0, "results": []}
        body = json.dumps({"factory_id": factory_id, "events": events}, ensure_ascii=False, allow_nan=False).encode()
        if sender is None:
            def sender(url, body, token):
                request = Request(url, body, {"Content-Type": "application/json", "Authorization": "Bearer " + token}, method="POST")
                # Disable environment proxies: credentials only go to configured target.
                from urllib.request import ProxyHandler
                with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=30) as response:
                    return json.loads(response.read(1024 * 1024))
        response = sender(endpoint, body, token)
        results = response.get("results") if isinstance(response, dict) else None
        if not isinstance(response, dict) or response.get("factory_id") != factory_id or not isinstance(results, list) or len(results) != len(events):
            raise ValueError("Incomplete or invalid ACK; queue retained")
        acknowledged = []
        seen = set()
        for result in results:
            if not isinstance(result, dict):
                raise ValueError("Invalid ACK record; queue retained")
            index = result.get("index")
            if type(index) is not int or index < 0 or index >= len(events) or index in seen:
                raise ValueError("Invalid ACK index; queue retained")
            seen.add(index)
            event = events[index]
            if result.get("source_event_id") != event["source_event_id"] or result.get("generation") != event["generation"]:
                raise ValueError("ACK identity mismatch; queue retained")
            if result.get("status") in ("accepted", "duplicate"):
                if not result.get("receipt_id"):
                    raise ValueError("ACK missing durable receipt; queue retained")
                acknowledged.append((event["generation"], event["source_event_id"]))
            elif result.get("status") != "rejected":
                raise ValueError("Unknown ACK status; queue retained")
        with self.db:
            self.db.executemany("DELETE FROM pending WHERE generation=? AND event_id=?", acknowledged)
        return {"sent": len(events), "removed": len(acknowledged), "results": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("read")
    ingest.add_argument("--file", required=True)
    ingest.add_argument("--generation", required=True)
    ingest.add_argument("--machine-id", required=True)
    sub.add_parser("status")
    flush = sub.add_parser("flush")
    flush.add_argument("--endpoint", required=True)
    args = parser.parse_args()
    queue = Queue(args.queue)
    try:
        if args.command == "read":
            print(json.dumps({"queued": queue.read_file(args.file, args.generation, args.machine_id)}))
        elif args.command == "status":
            print(json.dumps({"pending": queue.db.execute("SELECT count(*) FROM pending").fetchone()[0]}))
        else:
            print(json.dumps(queue.flush(args.endpoint, os.environ.get("UV_CONNECTOR_TOKEN", ""))))
    finally:
        queue.close()


if __name__ == "__main__":
    main()

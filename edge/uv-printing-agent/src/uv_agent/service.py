import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import threading
import tomllib
from uuid import uuid4
from . import __version__, identity
from .outbox import Outbox, Backpressure
from .transport import Transport
from .adapters.generic_csv_log import GenericCsvLog
from .adapters.simulator import Simulator


class Agent:
    def __init__(self, config):
        self.config = config
        self.state = Path(config["state_dir"]).resolve()
        self.identity = identity.load(self.state / "identity.dpapi")
        if self.identity.get("server_url", "").rstrip("/") != config["server_url"].rstrip("/"):
            raise ValueError("identity_server_mismatch")
        self.transport = Transport(config["server_url"], self.identity["token"], allow_loopback_http=config.get("allow_loopback_http", False))
        self.outbox = Outbox(self.state / "outbox.sqlite3", queue_limit=config.get("queue_limit", 1000000), min_free_bytes=config.get("min_free_bytes", 100*1024*1024))
        self.sources = {}
        for source in config.get("sources", []):
            kind = source["adapter"]
            if kind == "simulator":
                adapter = Simulator()
            elif kind == "generic_csv_log":
                adapter = GenericCsvLog(source["path"], encoding=source.get("encoding", "utf-8-sig"), format_version=source.get("format_version", "synthetic-csv-v1"))
            else:
                raise ValueError("unsupported_adapter")
            self.sources[source["source_id"]] = adapter
        cached = self.state / "binding-cache.json"
        self.bindings = json.loads(cached.read_text()) if cached.exists() else []
        self.last_error = None
        logger = logging.getLogger("uv_agent")
        logger.setLevel(logging.INFO)
        handler = RotatingFileHandler(self.state / "agent.log", maxBytes=2*1024*1024, backupCount=3, encoding="utf-8")
        logger.addHandler(handler)
        self.logger, self.handler = logger, handler

    def tick(self):
        self.last_error = None
        try:
            response = self.transport.request("/api/internal/uv-agent/config")
            self.bindings = response["bindings"]
            temporary = self.state / "binding-cache.tmp"
            temporary.write_text(json.dumps(self.bindings), encoding="utf-8")
            temporary.replace(self.state / "binding-cache.json")
        except Exception as error:
            self.last_error = "cloud_config_unreachable"
        # A cached binding permits offline capture, never a guessed/new binding.
        for binding in self.bindings:
            adapter = self.sources.get(binding["source_id"])
            if adapter is None:
                self.last_error = "local_source_unconfigured"
                continue
            # The read cut point belongs to the local source, not its current
            # cloud binding. Queued events keep the binding captured at read time.
            key = binding['source_id']
            try:
                result = adapter.read_events_since(self.outbox.cursor(key))
                events = [dict(event, machine_id=binding["machine_id"], source_id=binding["source_id"], binding_version=binding["binding_version"]) for event in result.events]
                self.outbox.append(key, events, result.cursor, result.rejected)
            except Backpressure as error:
                self.last_error = str(error)
            except Exception:
                self.last_error = "collector_error"
        try:
            events = self.outbox.pending()
            if events:
                response = self.transport.request("/api/internal/uv-agent/events/batch", dict(schema_version=1, batch_id=uuid4().hex, events=events))
                if not isinstance(response.get("results"), list):
                    raise ValueError("ack_missing")
                self.outbox.acknowledge(response["results"])
            self.transport.request("/api/internal/uv-agent/heartbeat", dict(agent_version=__version__, **self.outbox.diagnostics(), collector_health="degraded" if self.last_error else "ready", last_error_code=self.last_error))
        except Exception:
            self.last_error = self.last_error or "cloud_transport_unreachable"
        if self.last_error:
            self.logger.warning("collector_status=%s", self.last_error)

    def run(self, stop):
        try:
            while not stop.is_set():
                self.tick()
                stop.wait(max(1, min(60, self.config.get("poll_seconds", 5))))
        finally:
            self.outbox.close()
            self.logger.removeHandler(self.handler)
            self.handler.close()


def load_config(path):
    with Path(path).open("rb") as source:
        return tomllib.load(source)


def main():
    parser = argparse.ArgumentParser(description="RR UV read-only outbound agent")
    parser.add_argument("--config", required=True)
    parser.add_argument("action", choices=["run", "enroll", "diagnostics"])
    args = parser.parse_args()
    config = load_config(args.config)
    if args.action == "enroll":
        from getpass import getpass
        transport = Transport(config["server_url"], allow_loopback_http=config.get("allow_loopback_http", False))
        result = identity.enroll(transport, Path(config["state_dir"])/"identity.dpapi", getpass("One-time pairing code: "))
        print(json.dumps(result))
    elif args.action == "diagnostics":
        outbox = Outbox(Path(config["state_dir"])/"outbox.sqlite3")
        print(json.dumps(dict(agent_version=__version__, **outbox.diagnostics())))
        outbox.close()
    else:
        agent = Agent(config)
        try:
            agent.run(threading.Event())
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

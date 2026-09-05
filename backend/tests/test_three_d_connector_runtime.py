import importlib
import os
import shutil
import socket
import subprocess
import threading
import time
from datetime import timedelta
from pathlib import Path

from fastapi import Request
from sqlalchemy import select
from test_three_d_connector import TOKEN
from test_three_d_connector import environment as environment_fixture

environment = environment_fixture


def test_two_real_workers_eleven_tls_printers_api_reconcile_and_sse(
    environment, monkeypatch
):
    import uvicorn

    env = environment
    app = env[0].app
    healthy = [True]
    offset = [0]
    from datetime import UTC, datetime

    monkeypatch.setattr(
        env[3],
        "database_now",
        lambda _db: datetime.now(UTC) + timedelta(seconds=offset[0]),
    )
    network = importlib.import_module("app.services.three_d_network_health")
    original = network.network_health_snapshot

    def health(db):
        value = original(db)
        return {**value, "status": "healthy" if healthy[0] else "unreachable"}

    monkeypatch.setattr(network, "network_health_snapshot", health)
    monkeypatch.setattr(env[3], "network_health_snapshot", health)

    @app.post("/_test/configure")
    async def configure(request: Request):
        body = await request.json()
        with env[1].SessionLocal() as db:
            for index, printer_id in enumerate(env[5], 1):
                row = db.get(env[2].ThreeDPrintingPrinterConnection, printer_id)
                if row is None:
                    row = env[2].ThreeDPrintingPrinterConnection(
                        printer_id=printer_id,
                        factory_id="huakang-a",
                        site_id=env[3].SITE,
                        lan_host=f"10.33.30.{100 + index}",
                        mqtt_port=8883,
                        credential_ref=f"printer-{index:02d}",
                        connection_enabled=True,
                        connection_owner=env[3].OWNER,
                    )
                    db.add(row)
                row.certificate_fingerprint = body["fingerprint"]
            db.commit()
        return {"configured": True}

    @app.post("/_test/advance")
    async def advance(request: Request):
        body = await request.json()
        offset[0] += body["seconds"]
        healthy[0] = body["healthy"]
        return {"advanced": True}

    @app.get("/_test/snapshot")
    def snapshot():
        business = importlib.import_module("app.services.three_d_printing")
        with env[1].SessionLocal() as db:
            return {
                "events": len(
                    list(db.scalars(select(env[2].ThreeDPrintingPrinterStateEvent.id)))
                ),
                "runs": [
                    business.production_record_out(r)
                    for r in db.scalars(select(env[2].ThreeDPrintingProductionRecord))
                ],
                "commands": [
                    business.command_out(c)
                    for c in db.scalars(select(env[2].ThreeDPrintingPrinterCommand))
                ],
                "printers": [
                    {
                        "connected": p.connected and healthy[0],
                        "state": p.state if healthy[0] else "STALE",
                    }
                    for p in db.scalars(select(env[2].ThreeDPrintingPrinter))
                ],
            }

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [sock]}, daemon=True
    )
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.01)
    node = shutil.which("node") or str(
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe"
    )
    try:
        process = subprocess.run(
            [node, "services/three-d-printer-connector/test/runtime.integration.mjs"],
            cwd=Path(__file__).resolve().parents[2],
            env={
                **os.environ,
                "THREE_D_TEST_API": f"http://127.0.0.1:{port}",
                "THREE_D_TEST_TOKEN": TOKEN,
                "THREE_D_TEST_COOKIE": "; ".join(
                    f"{k}={v}" for k, v in env[0].cookies.items()
                ),
            },
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=90,
        )
        assert process.returncode == 0, process.stdout + process.stderr
        print(process.stdout)
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()

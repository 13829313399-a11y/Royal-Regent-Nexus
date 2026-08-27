import importlib
import logging
import re
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings

BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture(scope="module")
def production_main(tmp_path_factory):
    """Load the production middleware without consulting backend/.env."""

    patcher = pytest.MonkeyPatch()
    database_path = tmp_path_factory.mktemp("request-timing") / "test.db"
    patcher.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    original_init = BaseSettings.__init__

    def init_without_dotenv(self, **values):
        values.setdefault("_env_file", None)
        original_init(self, **values)

    patcher.setattr(BaseSettings, "__init__", init_without_dotenv)

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    main = importlib.import_module("app.main")
    yield main
    patcher.undo()


@pytest.fixture(scope="module")
def request_timing_middleware(production_main):
    return production_main.record_request_timing


@pytest.fixture
def request_id_client(request_timing_middleware):
    app = FastAPI()
    app.middleware("http")(request_timing_middleware)

    @app.get("/request-id-probe")
    async def request_id_probe(request: Request):
        return {"request_id": request.state.request_id}

    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize(
    ("supplied_request_id", "should_be_preserved"),
    [
        ("client-request_2026.08-11", True),
        (None, False),
        ("invalid/request-id", False),
        ("A" * 129, False),
    ],
    ids=["valid", "missing", "invalid", "overlong"],
)
def test_request_id_is_shared_by_state_response_header_and_log(
    request_id_client,
    caplog,
    supplied_request_id,
    should_be_preserved,
):
    headers = (
        {"X-Request-ID": supplied_request_id}
        if supplied_request_id is not None
        else {}
    )

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        response = request_id_client.get("/request-id-probe", headers=headers)

    assert response.status_code == 200
    state_request_id = response.json()["request_id"]
    assert response.headers["X-Request-ID"] == state_request_id

    if should_be_preserved:
        assert state_request_id == supplied_request_id
    else:
        assert re.fullmatch(r"[0-9a-f]{32}", state_request_id)
        if supplied_request_id is not None:
            assert state_request_id != supplied_request_id

    timing_logs = [
        record.getMessage()
        for record in caplog.records
        if record.name == "uvicorn.error"
        and record.getMessage().startswith("request_timing ")
    ]
    assert len(timing_logs) == 1
    assert f"request_id={state_request_id}" in timing_logs[0]
    if supplied_request_id is not None and not should_be_preserved:
        assert supplied_request_id not in timing_logs[0]

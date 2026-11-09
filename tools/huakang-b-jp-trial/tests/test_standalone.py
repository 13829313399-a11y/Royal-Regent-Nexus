"""Standalone trial acceptance with disposable data and real file workers."""
import asyncio
from datetime import date
from email.message import EmailMessage
from hashlib import sha256
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from threading import BoundedSemaphore
import time

import openpyxl
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


PACKAGE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("jp_trial_builder", PACKAGE / "prepare_backend.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
STAGE = tempfile.TemporaryDirectory(prefix="jp-trial-test-backend-")
MANIFEST = builder.prepare(STAGE.name)
sys.path.insert(0, STAGE.name)

from app.main import create_app
from app.db import TABLES
from app.services import customer_order_jobs as jobs
from app.services.huakang_b_jp import intake

ORIGIN = "http://127.0.0.1:18765"
BASE = "/api/huakang-b-jp"
SCOPE = {"factory_id": "huakang-b"}
HEADERS = {"X-JP-Intake": "1", "Origin": ORIGIN}


def workbook(kind):
    book = openpyxl.Workbook()
    sheet = book.active
    if kind == "schedule":
        sheet.title = "华康B"
        sheet.append([]); sheet.append([]); sheet.append(["订单编号"] * 15)
        sheet.append(["0126-21614", "OTHER", "0000000001", "", "", "67053", "67053 WB0", "67053", "Test toy", "3L", 100, "", 3, "美国", ""])
    elif kind == "price":
        sheet.append(["货号编码", "产品货号", "客货价(HK$)", "货运类别", "长货号", "货价日期", "外箱-装箱数"])
        sheet.append(["CODE", "67053", 12.5, "柜货", "67053-000-2B-003-WB0", date(2026, 1, 1), 3])
        sheet.append(["CODE2", "67053", 10, "出厂价", "67053-000-2B-003-WB0", date(2026, 1, 1), 3])
    else:
        sheet.append(["货号", "邮件长货号", "货运类别", "装箱数", "货币", "候选客货价(HK$)", "确认价格", "确认币种"])
        sheet.append(["67053", "67053-000-2B-003-WB0", "柜货", 3, "USD", 23.4, 3, "USD"])
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def mail(po="0117978388"):
    message = EmailMessage()
    message["Subject"] = "WMUS order inquiry"
    message["Date"] = "Mon, 09 Nov 2026 10:00:00 +0800"
    message.set_content("Synthetic trial test")
    message.add_alternative(f"<p>S/D 12/31/2026</p><table><tr><th>Item</th><th>Qty</th><th>Customer PO</th></tr>"
        f"<tr><td>67053-000-2B-003-WB0</td><td>648</td><td>{po}</td></tr></table>", subtype="html")
    return message.as_bytes()


def client_for(data, static=None):
    return TestClient(create_app(data, static, port=18765), base_url=ORIGIN, headers=HEADERS)


def install(client):
    for kind in ("schedule", "price"):
        result = client.post(BASE + "/references/" + kind, data={**SCOPE, "expected_revision": 0},
            files={"file": (kind + ".xlsx", workbook(kind))})
        assert result.status_code == 200, result.text


def parsed(client, raw=None):
    raw = raw or mail()
    data = {**SCOPE, "received_date": "2026-11-09", "merchandiser": "试用跟单"}
    response = client.post(BASE + "/preview", data=data, files={"files": ("synthetic.eml", raw)})
    assert response.status_code == 200, response.text
    preview = response.json()
    assert len(preview["rows"]) == 1
    return raw, data, preview


def exported(client, raw, data, preview, **changes):
    rows = preview["rows"]
    overrides = [{"id": r["id"], "field": field, "value": r[field]} for r in rows
        if r.get("price_confirm") for field in ("price_t", "factory_price_t")]
    payload = {**data, "fingerprint": preview["fingerprint"], "selected": json.dumps([r["id"] for r in rows]),
        "confirmed": "true", "reason": "试用原件已核对", "overrides": json.dumps(overrides), **changes}
    return client.post(BASE + "/export", data=payload, files={"files": ("synthetic.eml", raw)})


def test_unchanged_source_manifest_and_only_six_tables(tmp_path):
    for source in MANIFEST["unchanged_business_sources"]:
        assert sha256((Path(STAGE.name) / source["target"]).read_bytes()).hexdigest() == source["sha256"]
    with client_for(tmp_path) as client:
        assert client.get("/api/health").json()["service"] == "huakang-b-jp-trial"
        assert client.get(BASE + "/capabilities", params=SCOPE).json()["available"]
        with sqlite3.connect(tmp_path / "jp-trial.sqlite3") as connection:
            assert {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")} == TABLES
            assert connection.execute("PRAGMA application_id").fetchone()[0] == 0x4A505452


def test_real_worker_import_export_download_and_restart(tmp_path):
    data = tmp_path / "中文 空格 数据"
    with client_for(data) as client:
        install(client)
        raw, form, preview = parsed(client)
        response = exported(client, raw, form, preview)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["row_count"] == 1 and result["first_number"] == 21615
        repeated = exported(client, raw, form, preview)
        assert repeated.status_code == 200 and repeated.json() == result
        content = client.get(BASE + f"/exports/{result['id']}/download", params=SCOPE).content
        book = openpyxl.load_workbook(BytesIO(content))
        sheet = book.active
        assert sheet.max_column == 44 and sheet.max_row == 2
        assert sheet.cell(2, 1).value.endswith("-21615")
        assert sheet.cell(2, 3).value == "0117978388" and sheet.cell(2, 3).data_type == "s"
        assert sheet.cell(2, 13).value == 648 and sheet.cell(2, 21).value == 12.5
        assert sheet.cell(2, 40).value == "试用跟单" and sheet.cell(2, 41).value == "本机试用"
        book.close()
        assert list((data / "tmp").iterdir()) == []
    with client_for(data) as restarted:
        history = restarted.get(BASE + "/exports", params=SCOPE).json()
        assert history["total"] == 1 and history["items"][0]["id"] == result["id"]
        assert restarted.get(BASE + f"/exports/{result['id']}/download", params=SCOPE).content == content
        raw, form, preview = parsed(restarted, mail("0117978389"))
        next_result = exported(restarted, raw, form, preview)
        assert next_result.status_code == 200 and next_result.json()["first_number"] == 21616


def test_distributable_synthetic_demo_uses_all_three_refs_and_exports_44_columns(tmp_path):
    demo_spec = importlib.util.spec_from_file_location("jp_trial_demo", PACKAGE / "create_demo.py")
    demo = importlib.util.module_from_spec(demo_spec)
    demo_spec.loader.exec_module(demo)
    demo_dir = tmp_path / "纯合成 演示资料"
    manifest = demo.create_demo(demo_dir)
    assert manifest["synthetic_only"] and len(list(demo_dir.glob("*.xlsx"))) == 3
    with client_for(tmp_path / "隔离试用数据") as client:
        for kind in ("schedule", "price"):
            path = demo_dir / manifest["files"][kind]
            response = client.post(BASE + "/references/" + kind,
                data={**SCOPE, "expected_revision": 0}, files={"file": (path.name, path.read_bytes())})
            assert response.status_code == 200, response.text
        mail_path = demo_dir / manifest["files"]["mail"]
        raw, form, candidate = parsed(client, mail_path.read_bytes())
        assert candidate["rows"][0]["price_confirm"]
        path = demo_dir / manifest["files"]["confirmed"]
        response = client.post(BASE + "/references/confirmed", data={**SCOPE, "expected_revision": 0, "currency": "USD"},
            files={"file": (path.name, path.read_bytes())})
        assert response.status_code == 200, response.text
        raw, form, preview = parsed(client, raw)
        form["merchandiser"] = "演示跟单"
        # Follow the user flow: changing the operator requires fresh preview controls.
        response = client.post(BASE + "/preview", data=form, files={"files": ("synthetic.eml", raw)})
        assert response.status_code == 200, response.text
        preview = response.json()
        row = preview["rows"][0]
        assert not row["price_confirm"]
        assert row["price_t"] == "23.4" and row["factory_price_t"] == "15.6"
        result = exported(client, raw, form, preview)
        assert result.status_code == 200, result.text
        assert result.json()["row_count"] == 1 and result.json()["first_number"] == 10
        content = client.get(BASE + f"/exports/{result.json()['id']}/download", params=SCOPE).content
        book = openpyxl.load_workbook(BytesIO(content))
        sheet = book.active
        assert sheet.max_column == 44 and sheet.max_row == 2
        assert sheet.cell(2, 3).value == "0000999001" and sheet.cell(2, 13).value == 12
        assert sheet.cell(2, 21).value == 23.4
        assert sheet.cell(2, 40).value == "演示跟单"
        book.close()
        assert exported(client, raw, form, preview).json() == result.json()
    for filename, expected in manifest["sha256"].items():
        assert sha256((demo_dir / filename).read_bytes()).hexdigest() == expected
    with pytest.raises(FileExistsError):
        demo.create_demo(demo_dir)


@pytest.mark.parametrize("change", ["fingerprint", "selected", "quantity", "merchandiser"])
def test_invalid_export_controls_never_allocate_numbers(tmp_path, change):
    with client_for(tmp_path) as client:
        install(client)
        raw, form, preview = parsed(client)
        changes = {"fingerprint": {"fingerprint": "old-fingerprint"}, "selected": {"selected": '["unknown"]'},
            "quantity": {"overrides": json.dumps([{"id": preview["rows"][0]["id"], "field": "qty", "value": "-1"}])},
            "merchandiser": {"merchandiser": ""}}[change]
        response = exported(client, raw, form, preview, **changes)
        assert response.status_code in {400, 409}, response.text
        assert client.get(BASE + "/exports", params=SCOPE).json()["total"] == 0
        with sqlite3.connect(tmp_path / "jp-trial.sqlite3") as connection:
            assert connection.execute("SELECT count(*) FROM jp_intake_counters").fetchone()[0] == 0


def test_reference_versions_currency_and_immutable_evidence(tmp_path):
    with client_for(tmp_path) as client:
        install(client)
        previous = client.get(BASE + "/references", params=SCOPE).json()
        bad = client.post(BASE + "/references/schedule", data={**SCOPE, "expected_revision": 1}, files={"file": ("bad.xlsx", b"invalid")})
        assert bad.status_code == 400
        assert client.get(BASE + "/references", params=SCOPE).json() == previous
        stale = client.post(BASE + "/references/schedule", data={**SCOPE, "expected_revision": 0}, files={"file": ("schedule.xlsx", workbook("schedule"))})
        assert stale.status_code == 409
        confirmed = client.post(BASE + "/references/confirmed", data={**SCOPE, "expected_revision": 0, "currency": "USD"},
            files={"file": ("confirmed.xlsx", workbook("confirmed"))})
        assert confirmed.status_code == 200, confirmed.text
        cleared = client.post(BASE + "/references/confirmed/clear", data={**SCOPE, "expected_revision": 1})
        assert cleared.status_code == 200 and cleared.json()["confirmed"]["revision"] == 2
        raw, form, preview = parsed(client)
        assert exported(client, raw, form, preview).status_code == 200
        with sqlite3.connect(tmp_path / "jp-trial.sqlite3") as connection:
            for table in ("order_ledger_sources", "jp_intake_reference_events", "jp_intake_exports", "jp_intake_export_identities"):
                with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                    connection.execute(f"DELETE FROM {table}")
                connection.rollback()
                with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                    connection.execute(f"UPDATE {table} SET factory_id=factory_id")
                connection.rollback()


def test_local_origin_host_factory_and_upload_guards(tmp_path):
    with client_for(tmp_path) as client:
        assert client.get("/api/health", headers={"Host": "evil.invalid"}).status_code == 403
        assert client.get("/api/health", headers={"Origin": "https://evil.invalid"}).status_code == 403
        assert client.options(BASE + "/preview").status_code == 403
        assert client.get(BASE + "/capabilities", params={"factory_id": "huaxing"}).status_code == 400
        missing_header = client.post(BASE + "/references/confirmed/clear", headers={"X-JP-Intake": ""}, data={**SCOPE, "expected_revision": 0})
        assert missing_header.status_code == 403
        oversized = client.post(BASE + "/preview", headers={"Content-Length": str(56 * 1024**2)}, content=b"test")
        assert oversized.status_code == 413
        assert "access-control-allow-origin" not in client.get("/api/health").headers
    with pytest.raises(ValueError, match="127.0.0.1"):
        create_app(tmp_path / "remote", host="0.0.0.0")


def test_non_trial_database_is_refused_without_changing_it(tmp_path):
    path = tmp_path / "jp-trial.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE real_business(value TEXT)")
        connection.execute("INSERT INTO real_business VALUES ('preserve')")
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="不是此版本"):
        create_app(tmp_path)
    assert path.read_bytes() == before


def test_static_mount_cannot_expose_local_data(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html>trial-only</html>")
    with client_for(tmp_path / "data", web) as client:
        assert "trial-only" in client.get("/").text
        assert client.get("/data/jp-trial.sqlite3").status_code == 404
        assert client.get("/%2e%2e/data/jp-trial.sqlite3").status_code == 404


def test_worker_deadline_cancellation_and_single_admission(tmp_path):
    async def exercise():
        slot = BoundedSemaphore(1)
        expired = jobs.JobBudget(tmp_path, slot, deadline=time.monotonic() - 1)
        with pytest.raises(HTTPException) as failure:
            await jobs._execute("_jp_validate_reference", ("schedule", workbook("schedule")), {}, expired)
        assert failure.value.status_code == 504
        cancelled = jobs.JobBudget(tmp_path, slot)
        cancelled.cancelled.set()
        with pytest.raises(HTTPException) as failure:
            await jobs._execute("_jp_validate_reference", (), {}, cancelled)
        assert failure.value.status_code == 499
        with slot:
            with pytest.raises(HTTPException) as failure:
                await jobs._execute("_jp_validate_reference", (), {}, jobs.JobBudget(tmp_path, slot))
            assert failure.value.status_code == 429
        # A tiny running budget must reap its child and remove the private IPC directory.
        budget = jobs.JobBudget(tmp_path, slot, deadline=time.monotonic() + 0.08)
        with pytest.raises(HTTPException) as failure:
            await jobs._execute("_jp_validate_reference", ("schedule", workbook("schedule")), {}, budget)
        assert failure.value.status_code == 504
        assert list(tmp_path.iterdir()) == []
        assert slot.acquire(blocking=False)
        slot.release()
    asyncio.run(exercise())


def test_worker_file_lock_rejects_other_app_instance(tmp_path):
    from app.worker import job_slot
    directory = tmp_path / "tmp"
    directory.mkdir()

    async def exercise():
        with job_slot(tmp_path / "jp-worker.lock"):
            with pytest.raises(HTTPException) as failure:
                await jobs._execute("_jp_validate_reference", ("schedule", workbook("schedule")), {},
                    jobs.JobBudget(directory, BoundedSemaphore(1)))
            assert failure.value.status_code == 429
        result = await jobs._execute("_jp_validate_reference", ("schedule", workbook("schedule")), {},
            jobs.JobBudget(directory, BoundedSemaphore(1)))
        assert result["max_seq"] == 21614
        assert list(directory.iterdir()) == []
    asyncio.run(exercise())


@pytest.mark.parametrize("disconnect", [False, True])
def test_running_worker_is_reaped_when_caller_cancels_or_disconnects(tmp_path, monkeypatch, disconnect):
    async def exercise():
        from types import SimpleNamespace
        started = asyncio.Event()
        disconnected = asyncio.Event()
        processes = []
        launch = asyncio.create_subprocess_exec

        async def capture(*args, **kwargs):
            process = await launch(*args, **kwargs)
            processes.append(process)
            started.set()
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", capture)
        state = SimpleNamespace(job_directory=tmp_path, job_slot=BoundedSemaphore(1))

        class Request:
            app = SimpleNamespace(state=state)
            async def is_disconnected(self):
                return disconnected.is_set()

        dependency = jobs.order_job_request(Request())
        await anext(dependency)
        try:
            task = asyncio.create_task(jobs.run_order_job(intake._jp_validate_reference,
                "schedule", workbook("schedule")))
            await started.wait()
            if disconnect:
                disconnected.set()
                with pytest.raises(HTTPException) as failure:
                    await task
                assert failure.value.status_code == 499
            else:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
        finally:
            await dependency.aclose()
        assert processes and all(process.returncode is not None for process in processes)
        assert list(tmp_path.iterdir()) == []
        assert state.job_slot.acquire(blocking=False)
        state.job_slot.release()
    asyncio.run(exercise())

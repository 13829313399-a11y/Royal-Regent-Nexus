"""Save reuses the writer's authoritative preview without weakening import controls."""
from copy import deepcopy
import json

from fastapi import HTTPException
import pytest
from sqlalchemy import func, select

from app.api import customer_order_ledger as api
from app.models.customer_order_ledger import OrderLedgerLine as Line, OrderLedgerSource as Source, OrderLedgerVersion as Version
from app.services import customer_order_carton_schedule as handoff
from app.services import customer_order_dickie as dickie
from app.services import customer_order_unified as unified
from test_customer_order_ledger import client, db, engine, user


def confirmed_upload(monkeypatch, variant="dickie"):
    from test_customer_order_dickie import STANDARD_PAGES, build_dickie_schedule
    from test_customer_order_disney_factory import arguments, disney_po
    from test_customer_order_huaxing_unified import data, template

    if variant == "disney":
        args = arguments("huaxing", disney_po())
        create = api.mapping._create_mapped_customer_preview
    else:
        # OCR extraction is isolated here; use the real Dickie parser and writer.
        monkeypatch.setattr(dickie, "_extract_pdf_ocr_pages", lambda _: STANDARD_PAGES)
        workbook = template("dickie")
        sheet = workbook["ITEM表"]
        sheet["H4"], sheet["I4"], sheet["E4"] = "20 330 2028", "小消防车", "OLD"
        sheet["K4"], sheet["L4"] = 120, 24
        args = dict(customer_code="dickie", factory_id="huaxing", received_date="2026-03-18",
            po_files=[("po.pdf", b"%PDF-test-ocr-fixture")], schedule_file_name="schedule.xlsx",
            schedule_content=build_dickie_schedule() if variant == "dickie-legacy" else data(workbook))
        create = api.mapping._create_special_batch_preview
    preview = create(**args)
    api.mapping._finalize_preview(preview, received_date=args["received_date"],
        current_user=user(["read", "write"]), factory_id="huaxing")
    keys = [issue["skip_key"] for row in preview["rows"] for issue in row["issues"] if issue.get("can_skip")]
    form = dict(factory_id="huaxing", received_date=args["received_date"], confirmed="true",
        preview_fingerprint=preview["preview_fingerprint"], skipped_issue_keys=json.dumps(keys),
        confirmation_reason="已核对原单资料")
    files = [("po_files", (name, content, "application/pdf")) for name, content in args["po_files"]]
    files.append(("schedule_file", (args["schedule_file_name"], args["schedule_content"],
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")))
    return args, preview, form, files


def inline_jobs(monkeypatch):
    calls = []

    async def run(function, *args, db=None, **kwargs):
        calls.append(function.__name__)
        # Keep the real worker's no-pending-writes / released-connection contract.
        assert not (db.new or db.dirty or db.deleted)
        db.rollback()
        return function(*args, **kwargs)

    monkeypatch.setattr(api, "run_order_job", run)
    return calls


@pytest.mark.parametrize("variant", ["dickie", "dickie-legacy", "disney"])
def test_save_parses_once_and_preserves_writer_payload(client, db, monkeypatch, variant):
    args, preview, form, files = confirmed_upload(monkeypatch, variant)
    original_files = deepcopy(files)
    if variant == "dickie":
        row = preview["rows"][0]
        issue = next(issue for issue in row["issues"] if issue.get("edit_field") == "date_code")
        form["manual_overrides"] = json.dumps([dict(row_id=row["id"], issue_key=issue["skip_key"],
            field="date_code", value="00123APR27")])
    calls = inline_jobs(monkeypatch)
    parse_calls = []
    parser_module = dickie if variant == "dickie-legacy" else unified
    parser_name = "create_dickie_batch_preview" if variant == "dickie-legacy" else "create_unified_customer_preview"
    original_parser = getattr(parser_module, parser_name)

    def counted_preview(**kwargs):
        parse_calls.append(kwargs["po_files"])
        return original_parser(**kwargs)

    monkeypatch.setattr(parser_module, parser_name, counted_preview)
    response = client.post(f"/api/customer-order-ledger/imports/{args['customer_code']}", data=form, files=files)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["created_count"] == 1 and result["existing_count"] == 0
    expected_writer = "_export_mapped_customer_schedule" if variant == "disney" else "_export_special_batch_schedule"
    assert calls == [expected_writer]
    assert len(parse_calls) == 1
    stored = result["items"][0]["data"]
    assert stored["product_no"] == preview["rows"][0]["product_no"]
    assert stored["quantity"] == preview["rows"][0]["quantity"]
    if variant == "dickie":
        assert stored["date_code"] == "00123APR27"
        assert stored["import_controls"]["manual_overrides"] == json.loads(form["manual_overrides"])
    assert files == original_files
    assert db.scalar(select(func.count()).select_from(Line)) == 1


@pytest.mark.parametrize("tamper", ["fingerprint", "unknown-issue", "wrong-field", "unknown-row"])
def test_invalid_save_controls_write_no_ledger_evidence(client, db, monkeypatch, tamper):
    _, preview, form, files = confirmed_upload(monkeypatch)
    inline_jobs(monkeypatch)
    if tamper == "fingerprint":
        form["preview_fingerprint"] = "incorrect"
    elif tamper == "unknown-issue":
        form["skipped_issue_keys"] = json.dumps(["unknown-row|missing_date_code|date_code"])
    else:
        row = preview["rows"][0]
        issue = next(issue for issue in row["issues"] if issue.get("edit_field") == "date_code")
        form["manual_overrides"] = json.dumps([dict(
            row_id="unknown-row" if tamper == "unknown-row" else row["id"],
            issue_key=issue["skip_key"], field="quantity" if tamper == "wrong-field" else "date_code", value="900")])
    response = client.post("/api/customer-order-ledger/imports/dickie", data=form, files=files)
    assert response.status_code in {400, 409}, response.text
    for model in (Line, Source, Version):
        assert db.scalar(select(func.count()).select_from(model)) == 0


def test_warehouse_timeout_does_not_hide_committed_save_or_duplicate_retry(client, db, monkeypatch):
    _, _, form, files = confirmed_upload(monkeypatch)
    calls = inline_jobs(monkeypatch)
    sync_calls = []

    async def timeout_after_commit(*args, **kwargs):
        assert not db.in_transaction()
        sync_calls.append(True)
        raise HTTPException(504, "订单处理超时，任务已停止。")

    # Exercise the real sync_report error boundary, not a fabricated save result.
    monkeypatch.setattr(handoff, "synchronize", timeout_after_commit)
    first = client.post("/api/customer-order-ledger/imports/dickie", data=form, files=files)
    assert first.status_code == 200, first.text
    assert first.json()["created_count"] == 1
    assert first.json()["warehouse_sync"] == {"status": "ERROR", "message": "订单处理超时，任务已停止。"}
    again = client.post("/api/customer-order-ledger/imports/dickie", data=form, files=files)
    assert again.status_code == 200, again.text
    assert again.json()["created_count"] == 0 and again.json()["existing_count"] == 1
    assert again.json()["items"][0]["id"] == first.json()["items"][0]["id"]
    assert len(sync_calls) == 2 and calls == ["_export_special_batch_schedule"] * 2
    for model, expected in ((Line, 1), (Source, 2), (Version, 1)):
        assert db.scalar(select(func.count()).select_from(model)) == expected

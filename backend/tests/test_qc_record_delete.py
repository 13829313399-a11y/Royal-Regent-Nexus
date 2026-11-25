"""Comprehensive tests for QC_test admin account and QC record deletion boundaries."""
import base64
from datetime import datetime
import importlib
from io import BytesIO
import json
from uuid import uuid4

import httpx
from openpyxl import Workbook
import pytest

from test_molding_sample_api import make_client, login_as


ALL_FACTORIES = ("huakang-a", "huakang-b", "huakang-c", "huakang-d", "huadeng", "huaxing")


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch, tmp_path):
    monkeypatch.setenv("QC_DEPARTMENT_DATA_DIR", str(tmp_path / "qc-companies"))
    monkeypatch.setenv("QC_DOSSIER_ENABLED", "false")
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, "TEST_TMP_DIR", tmp_path / "main-test-db")


def install_stateful_upstream(monkeypatch, *, records=None, defect_lib=None, partners=None):
    module = importlib.import_module("app.api.qc_department")
    state = {
        "records": list(records or []),
        "defectLib": list(defect_lib or []),
        "partners": list(partners or []),
        "deleted_calls": [],
    }

    async def fake(method, path, params, body):
        if path == "api/health":
            return httpx.Response(200, json={"ok": True})
        if path == "api/bootstrap":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "records": list(state["records"]),
                    "nextId": max([r["id"] for r in state["records"]], default=0) + 1,
                    "partners": list(state["partners"]),
                    "defectLib": list(state["defectLib"]),
                },
            )
        if path == "api/records/delete":
            payload = json.loads(body) if body else {}
            ids = set(payload.get("ids") or [])
            state["deleted_calls"].append(sorted(ids))
            state["records"] = [r for r in state["records"] if r.get("id") not in ids]
            return httpx.Response(200, json={"ok": True, "deleted": len(ids)})
        if path == "api/defects":
            payload = json.loads(body) if body else {}
            state["defectLib"] = list(payload.get("defectLib") or [])
            return httpx.Response(200, json={"ok": True})
        if path == "api/partners":
            payload = json.loads(body) if body else {}
            state["partners"] = list(payload.get("partners") or [])
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(module, "upstream", fake)
    return state


def make_history_xlsx(year=2025, count=3):
    from app.services import qc_workbook_xml as xml

    wb = Workbook()
    ws = wb.active
    ws.title = "ZURU行验货"
    ws.append([datetime(year, 3, 15)])
    ws.append(xml.HEAD1)
    for idx in range(count):
        ws.append(["ZURU", f"PO-HIST-{idx + 1:03d}", "USA", f"SKU-H-{idx + 1:03d}", "History Item", 100, 10, 10, "PASS", "hist"])
    buf = BytesIO()
    wb.save(buf)
    return base64.b64encode(buf.getvalue()).decode()


def login_qc_test(client):
    res = client.post("/api/auth/login", json={"username": "QC_test", "password": "ok"})
    assert res.status_code == 200, res.text
    return res.json()


def frame_base(client, factory="huaxing"):
    res = client.get(f"/api/qc-department/{factory}/api/health")
    assert res.status_code == 200, res.text
    return res.json()["frame_url"]


def read_ui_context(client, base):
    res = client.get(base + "nexus-context.js")
    assert res.status_code == 200
    return json.loads(res.text.removeprefix("window.__QC_NEXUS = ").removesuffix(";"))


def manual_row(customer="DRAFT-CUST", po_no="PO-DRAFT-1", product_no="SKU-DRAFT-1", date_from="2026-11-26"):
    return {
        "requestKey": str(uuid4()),
        "row": {
            "dateFrom": date_from,
            "dateTo": date_from,
            "customer": customer,
            "poNo": po_no,
            "country": "USA",
            "productNo": product_no,
            "productName": "测试产品",
            "quantity": "100",
            "unitsPerCarton": "10",
            "cartonCount": "10",
            "production": "一车间",
            "agency": "行验",
            "customerPo": "",
            "remark": "",
        },
    }


@pytest.mark.parametrize("authz_mode", ["legacy", "enforce"])
def test_qc_test_seeded_without_default_accounts_across_all_six_factories(monkeypatch, authz_mode):
    monkeypatch.setenv("SEED_DEFAULT_ACCOUNTS", "false")
    monkeypatch.setenv("AUTHZ_MODE", authz_mode)
    from test_auth_api import make_client as make_auth_client

    with make_auth_client(monkeypatch, SEED_DEFAULT_ACCOUNTS="false", AUTHZ_MODE=authz_mode) as client:
        install_stateful_upstream(monkeypatch)
        profile = login_qc_test(client)
        assert profile["username"] == "QC_test"
        assert profile["force_password_change"] is False
        assert "qc_inspection:record_delete" in profile["permissions"]
        assert set(profile["factory_scopes"]) == set(ALL_FACTORIES)
        # Strictly QC-only permissions: no admin, sales, molding, warehouse permissions.
        assert all(code.startswith("qc_inspection:") for code in profile["permissions"])
        assert client.get("/api/system/users").status_code == 403
        assert client.get("/api/customer-order-ledger/lines?factory_id=huaxing").status_code == 403

        for factory in ALL_FACTORIES:
            base = frame_base(client, factory)
            ctx = read_ui_context(client, base)
            assert ctx["deleteAllowed"] is True
            assert ctx["workflow"]["delete"] is True
            assert ctx["user"]["perms"]["records"]["m"] == 1
            assert ctx["user"]["perms"]["review"]["m"] == 1
            assert ctx["user"]["perms"]["import"]["m"] == 1


def test_ordinary_qc_accounts_have_no_delete_permission_and_get_403(monkeypatch):
    with make_client(monkeypatch) as client:
        install_stateful_upstream(
            monkeypatch,
            records=[{"id": 10, "orderNo": "PO-10", "productNo": "SKU-10", "result": "PASS", "defect": ""}],
            defect_lib=[{"name": "刮花", "category": "外观/质量", "defaultLevel": "MAJ 1.0", "keywords": [], "enabled": True}],
            partners=[{"type": "supplier", "name": "天一"}],
        )
        for account in ("qc_inspector", "qc_supervisor"):
            login_as(client, account)
            base = frame_base(client, "huaxing")
            ctx = read_ui_context(client, base)
            assert ctx["deleteAllowed"] is False
            assert ctx["workflow"]["delete"] is False
            assert ctx["user"]["perms"]["records"]["m"] == 0
            assert ctx["user"]["perms"]["review"]["m"] == 0
            assert ctx["user"]["perms"]["import"]["m"] == 0
            if account == "qc_supervisor":
                # Ordinary supervisor retains non-delete daily capabilities.
                assert ctx["user"]["perms"]["defectlib"]["m"] == 1
                assert ctx["user"]["perms"]["suppliers"]["e"] == 1
                assert ctx["user"]["perms"]["import"]["v"] == 1
                assert ctx["workflow"]["review"] is True

            req = {"requestKey": uuid4().hex, "entries": [{"id": "deadbeef" * 4, "revision": 0}], "reason": ""}
            assert client.post(base + "api/inspection-sheet/entries/delete", json=req).status_code == 403
            assert client.post(base + "api/inspection-sheet/review/delete", json=req).status_code == 403
            assert client.get(base + "api/inspection-summary/history/batches").status_code == 403
            assert client.post(base + f"api/inspection-summary/records/{'a'*32}/delete", json={"requestKey": uuid4().hex}).status_code == 403
            assert client.post(base + f"api/inspection-summary/history/{'b'*32}/rollback", json={"requestKey": uuid4().hex}).status_code == 403
            assert client.post(base + "api/records/delete", json={"ids": [10]}).status_code == 403
            assert client.post(base + "api/records/replace", json={"records": []}).status_code == 403
            assert client.post(base + "api/reference-data/clear", json={}).status_code == 403
            assert client.post(base + "api/records", json={"records": [], "deletedIds": [10]}).status_code == 403

            if account == "qc_supervisor":
                # Supervisor can edit/toggle/add defects and add partners, but CANNOT delete them.
                assert client.post(
                    base + "api/defects",
                    json={"defectLib": [
                        {"name": "刮花", "category": "外观/质量", "defaultLevel": "MAJ 1.0", "keywords": ["划伤"], "enabled": False},
                        {"name": "缩水", "category": "外观/质量", "defaultLevel": "MAJ 1.0", "keywords": [], "enabled": True},
                    ]},
                ).status_code == 200
                assert client.post(
                    base + "api/defects",
                    json={"defectLib": [{"name": "刮花", "category": "外观/质量", "defaultLevel": "MAJ 1.0", "keywords": [], "enabled": False}]},
                ).status_code == 403
                assert client.post(
                    base + "api/partners",
                    json={"partners": [{"type": "supplier", "name": "天一"}, {"type": "supplier", "name": "顺景"}]},
                ).status_code == 200
                assert client.post(
                    base + "api/partners",
                    json={"partners": [{"type": "supplier", "name": "天一"}]},
                ).status_code == 403


def test_workbench_delete_covers_blank_draft_workflow_and_legacy_without_touching_sales_order(monkeypatch):
    with make_client(monkeypatch) as client:
        upstream_state = install_stateful_upstream(
            monkeypatch,
            records=[{"id": 101, "client": "LEGACY-CUST", "orderNo": "PO-LEG-1", "productNo": "SKU-LEG-1", "qty": 20, "result": ""}],
        )
        # Seed a real Sales OrderLedgerLine to verify 客排期 source safety and fallback to 未推送.
        db_module = importlib.import_module("app.db")
        from app.models.customer_order_ledger import OrderLedgerLine

        with db_module.SessionLocal() as db:
            line = OrderLedgerLine(
                id="sales-line-delete-test",
                factory_id="huaxing",
                customer_code="ZURU",
                customer_name="ZURU",
                identity_key="id-sales-line-delete-test",
                reference_no="PO-SALES-1",
                product_no="SKU-SALES-1",
                quantity=500,
                shipped_quantity=0,
                status="active",
                version=1,
                revision=1,
                data={
                    "customer_name": "ZURU",
                    "po_no": "PO-SALES-1",
                    "product_no": "SKU-SALES-1",
                    "product_name_zh": "测试玩具",
                    "quantity": 500,
                    "planned_inspection_date": "2026-11-26",
                    "planned_inspection_date_to": "2026-11-26",
                    "inspection_agency": "行验",
                },
                created_at="2026-11-25T00:00:00Z",
                updated_at="2026-11-25T00:00:00Z",
            )
            db.add(line)
            db.commit()

        login_qc_test(client)
        base = frame_base(client, "huaxing")

        # 1) Create a blank manual workbench draft (result is empty "").
        manual_res = client.post(
            base + "api/inspection-sheet/intake/manual",
            json=manual_row("DRAFT-CUST", "PO-DRAFT-1", "SKU-DRAFT-1"),
        )
        assert manual_res.status_code == 200, manual_res.text

        # 2) Push the Sales OrderLedgerLine into QC workflow.
        push_item = {
            "sourceId": "sales-line-delete-test",
            "sourceRevision": 1,
            "method": "internal",
            "batch": "第一批",
            "plannedDate": "2026-11-26",
            "plannedQuantity": 500,
        }
        push_res = client.post(
            base + "api/workflow/tasks",
            json={"requestKey": uuid4().hex, "items": [push_item]},
        )
        assert push_res.status_code == 200, push_res.text

        entries = client.get(base + "api/inspection-sheet/entries").json()["items"]
        by_po = {e["poNo"]: e for e in entries}
        assert {"PO-DRAFT-1", "PO-SALES-1", "PO-LEG-1"} <= set(by_po)

        # Delete all three (blank draft + workflow task + legacy record) in one batch.
        req_key = uuid4().hex
        del_payload = {
            "requestKey": req_key,
            "entries": [
                {"id": by_po["PO-DRAFT-1"]["id"], "revision": by_po["PO-DRAFT-1"]["revision"]},
                {"id": by_po["PO-SALES-1"]["id"], "revision": by_po["PO-SALES-1"]["revision"]},
                {"id": by_po["PO-LEG-1"]["id"], "revision": by_po["PO-LEG-1"]["revision"]},
            ],
            "reason": "清理测试草稿与误推记录",
        }
        del_res = client.post(base + "api/inspection-sheet/entries/delete", json=del_payload)
        assert del_res.status_code == 200, del_res.text
        data = del_res.json()
        assert data["succeeded"] == 3 and data["failed"] == 0

        # Idempotent replay with same requestKey succeeds cleanly.
        replay = client.post(base + "api/inspection-sheet/entries/delete", json=del_payload)
        assert replay.status_code == 200
        assert all(item["ok"] and item["replayed"] for item in replay.json()["results"])

        # Legacy delete was forwarded to upstream sidecar.
        assert [101] in upstream_state["deleted_calls"]
        # Even if upstream hypothetically returned record 101 again, tombstone prevents resurrection.
        upstream_state["records"].append({"id": 101, "client": "LEGACY-CUST", "orderNo": "PO-LEG-1", "productNo": "SKU-LEG-1", "qty": 20, "result": ""})
        after_entries = client.get(base + "api/inspection-sheet/entries").json()["items"]
        assert not ({"PO-DRAFT-1", "PO-SALES-1", "PO-LEG-1"} & {e["poNo"] for e in after_entries})

        # Audit snapshot retained in inspections.sqlite3 changes table; deleted_tasks archived in workflow.sqlite3.
        sheet_mod = importlib.import_module("app.services.qc_inspection_sheet")
        wf_mod = importlib.import_module("app.services.qc_workflow")
        with sheet_mod.store() as conn:
            audit_rows = conn.execute("SELECT action, diff FROM changes WHERE action='delete'").fetchall()
            assert len(audit_rows) == 3
            assert json.loads(audit_rows[0]["diff"])["reason"] == "清理测试草稿与误推记录"
        with wf_mod.store() as conn:
            assert conn.execute("SELECT count(*) FROM deleted_tasks WHERE factory='huaxing'").fetchone()[0] == 1
            assert conn.execute("SELECT count(*) FROM tasks WHERE factory='huaxing'").fetchone()[0] == 0

        # Sales OrderLedgerLine is completely untouched AND schedule falls back to unpushed & can be re-pushed!
        with db_module.SessionLocal() as db:
            persisted = db.get(OrderLedgerLine, "sales-line-delete-test")
            assert persisted is not None and persisted.status == "active"
            src = wf_mod.sources(db, "huaxing")["items"]
            sales_src = next(item for item in src if item["id"] == "sales-line-delete-test")
            assert sales_src["tasks"] == []

        repush = client.post(
            base + "api/workflow/tasks",
            json={"requestKey": uuid4().hex, "items": [push_item]},
        )
        assert repush.status_code == 200, repush.text
        repushed_entries = client.get(base + "api/inspection-sheet/entries").json()["items"]
        assert any(e["poNo"] == "PO-SALES-1" for e in repushed_entries)


def test_review_delete_enforces_revoke_first_and_keeps_summary_and_stats_consistent(monkeypatch):
    with make_client(monkeypatch) as client:
        install_stateful_upstream(monkeypatch)
        login_qc_test(client)
        base = frame_base(client, "huaxing")

        # Create two workbench drafts, save results, submit both to pending review.
        for po in ("PO-REV-1", "PO-REV-2"):
            assert client.post(
                base + "api/inspection-sheet/intake/manual",
                json=manual_row("ZURU", po, "SKU-" + po),
            ).status_code == 200
        items = {e["poNo"]: e for e in client.get(base + "api/inspection-sheet/entries").json()["items"]}
        for po in ("PO-REV-1", "PO-REV-2"):
            e = items[po]
            saved = client.post(
                base + f"api/inspection-sheet/entries/{e['id']}/save",
                json={"revision": e["revision"], "result": "PASS", "remark": "ok"},
            )
            assert saved.status_code == 200, saved.text
            rev = saved.json()["revision"]
            assert client.post(base + f"api/inspection-sheet/entries/{e['id']}/submit", json={"revision": rev}).status_code == 200

        review_items = {e["poNo"]: e for e in client.get(base + "api/inspection-sheet/review/entries").json()["items"]}
        # Workbench delete MUST reject pending review entries with 409.
        wb_reject = client.post(
            base + "api/inspection-sheet/entries/delete",
            json={"requestKey": uuid4().hex, "entries": [{"id": review_items["PO-REV-1"]["id"], "revision": review_items["PO-REV-1"]["revision"]}]},
        ).json()
        assert wb_reject["failed"] == 1 and wb_reject["results"][0]["status"] == 409

        # Pending delete removes PO-REV-1 cleanly without entering summary.
        del_pending = client.post(
            base + "api/inspection-sheet/review/delete",
            json={"requestKey": uuid4().hex, "entries": [{"id": review_items["PO-REV-1"]["id"], "revision": review_items["PO-REV-1"]["revision"]}], "reason": "误提待审"},
        ).json()
        assert del_pending["succeeded"] == 1

        # Confirm PO-REV-2 to approved (writes into 验货汇总).
        rev2 = review_items["PO-REV-2"]
        confirm_res = client.post(
            base + "api/inspection-sheet/review/confirm",
            json={"requestKey": uuid4().hex, "entries": [{"id": rev2["id"], "revision": rev2["revision"]}]},
        ).json()
        assert confirm_res["succeeded"] == 1
        approved_rev2 = confirm_res["results"][0]["item"]

        # Summary now contains PO-REV-2 (sourceKind='review').
        summary_rows = client.get(base + "api/inspection-summary/records").json()["items"]
        assert len(summary_rows) == 1 and summary_rows[0]["poNo"] == "PO-REV-2"
        summary_id = summary_rows[0]["id"]

        # Direct delete on approved record in review center MUST fail with 409.
        direct_approved = client.post(
            base + "api/inspection-sheet/review/delete",
            json={"requestKey": uuid4().hex, "entries": [{"id": approved_rev2["id"], "revision": approved_rev2["revision"]}]},
        ).json()
        assert direct_approved["failed"] == 1 and direct_approved["results"][0]["status"] == 409
        assert "反审核" in direct_approved["results"][0]["message"]

        # Direct delete on review-synced record in summary MUST fail with 409.
        direct_summary = client.post(
            base + f"api/inspection-summary/records/{summary_id}/delete",
            json={"requestKey": uuid4().hex},
        )
        assert direct_summary.status_code == 409
        assert "反审核" in direct_summary.json()["detail"]

        # Revoke PO-REV-2 back to pending, then delete in pending!
        revoke_res = client.post(
            base + "api/inspection-sheet/review/revoke",
            json={"requestKey": uuid4().hex, "entries": [{"id": approved_rev2["id"], "revision": approved_rev2["revision"]}], "reason": "准备删除"},
        ).json()
        assert revoke_res["succeeded"] == 1
        revoked_rev2 = revoke_res["results"][0]["item"]

        del_after_revoke = client.post(
            base + "api/inspection-sheet/review/delete",
            json={"requestKey": uuid4().hex, "entries": [{"id": revoked_rev2["id"], "revision": revoked_rev2["revision"]}], "reason": "反审核后删除"},
        ).json()
        assert del_after_revoke["succeeded"] == 1

        # Summary stays empty after reconcile, review queue is empty, and statistics endpoint works cleanly.
        assert client.get(base + "api/inspection-summary/records").json()["total"] == 0
        assert client.get(base + "api/inspection-sheet/review/entries").json()["items"] == []
        stats = client.get(base + "api/approved-statistics/dashboard")
        assert stats.status_code == 200


def test_summary_history_record_delete_and_batch_rollback(monkeypatch):
    with make_client(monkeypatch) as client:
        install_stateful_upstream(monkeypatch)
        login_qc_test(client)
        base = frame_base(client, "huaxing")

        # Preview and commit a 3-row historical Excel import.
        prev = client.post(
            base + "api/inspection-summary/history/preview",
            json={"filename": "2025历史汇总.xlsx", "mime": "", "content": make_history_xlsx(2025, 3)},
        )
        assert prev.status_code == 200, prev.text
        batch_id = prev.json()["id"]
        commit = client.post(base + f"api/inspection-summary/history/{batch_id}/commit", json={})
        assert commit.status_code == 200 and commit.json()["count"] == 3

        batches = client.get(base + "api/inspection-summary/history/batches").json()["items"]
        assert len(batches) == 1
        assert batches[0]["id"] == batch_id and batches[0]["activeCount"] == 3 and batches[0]["status"] == "committed"

        # Dossier endpoint exposes sourceKind='history' and historyBatchId for UI rendering.
        records = client.get(base + "api/inspection-summary/records").json()["items"]
        assert len(records) == 3
        first_id = records[0]["id"]
        dossier = client.get(base + f"api/inspection-dossier/records/{first_id}").json()
        assert dossier["qc"]["sourceKind"] == "history"
        assert dossier["qc"]["historyBatchId"] == batch_id
        assert dossier["qc"]["sourceFilename"] == "2025历史汇总.xlsx"

        # Delete single history record (+ idempotent replay).
        req = {"requestKey": uuid4().hex, "reason": "单条错行"}
        del_one = client.post(base + f"api/inspection-summary/records/{first_id}/delete", json=req)
        assert del_one.status_code == 200 and del_one.json()["status"] == "deleted"
        replay_one = client.post(base + f"api/inspection-summary/records/{first_id}/delete", json=req)
        assert replay_one.status_code == 200 and replay_one.json()["replayed"] is True
        assert client.get(base + "api/inspection-summary/records").json()["total"] == 2

        # Rollback the remaining 2 rows in that batch.
        rb = client.post(
            base + f"api/inspection-summary/history/{batch_id}/rollback",
            json={"requestKey": uuid4().hex, "reason": "整批版本有误"},
        )
        assert rb.status_code == 200 and rb.json()["rolledBackCount"] == 2 and rb.json()["status"] == "rolled_back"
        assert client.get(base + "api/inspection-summary/records").json()["total"] == 0
        batches_after = client.get(base + "api/inspection-summary/history/batches").json()["items"]
        assert batches_after[0]["status"] == "rolled_back" and batches_after[0]["activeCount"] == 0


def test_defect_reference_protection_partner_delete_and_mobile_boundary(monkeypatch):
    with make_client(monkeypatch) as client:
        install_stateful_upstream(
            monkeypatch,
            records=[{"id": 1, "orderNo": "PO-1", "productNo": "SKU-1", "result": "REJ", "defect": "缩水，刮花", "defects": [{"desc": "缩水", "qty": 2}]}],
            defect_lib=[
                {"name": "缩水", "category": "外观/质量", "defaultLevel": "MAJ 1.0", "keywords": [], "enabled": True},
                {"name": "未用词条", "category": "外观/质量", "defaultLevel": "MIN 2.5", "keywords": [], "enabled": True},
            ],
            partners=[{"type": "supplier", "name": "天一"}, {"type": "supplier", "name": "临时厂"}],
        )
        login_qc_test(client)
        base = frame_base(client, "huaxing")

        # Deleting a referenced defect is blocked with 409 instructing to disable it.
        blocked = client.post(
            base + "api/defects",
            json={"defectLib": [{"name": "未用词条", "category": "外观/质量", "defaultLevel": "MIN 2.5", "keywords": [], "enabled": True}]},
        )
        assert blocked.status_code == 409
        assert "停用" in blocked.json()["detail"]

        # Deleting an unreferenced defect succeeds for QC_test.
        allowed = client.post(
            base + "api/defects",
            json={"defectLib": [{"name": "缩水", "category": "外观/质量", "defaultLevel": "MAJ 1.0", "keywords": [], "enabled": True}]},
        )
        assert allowed.status_code == 200

        # Deleting a partner succeeds for QC_test.
        del_partner = client.post(base + "api/partners", json={"partners": [{"type": "supplier", "name": "天一"}]})
        assert del_partner.status_code == 200

        # Mobile gateway strictly rejects delete paths (404) even with a valid paired QC_test mobile session.
        mobile_mod = importlib.import_module("app.api.qc_mobile")
        monkeypatch.setattr(mobile_mod, "configured_origin", lambda: ("http://127.0.0.1:8000", mobile_mod.urlsplit("http://127.0.0.1:8000")))
        async def _noop(*args, **kwargs):
            return None
        monkeypatch.setattr(mobile_mod, "check_lan_entry", _noop)
        pair = client.post("/api/qc-mobile/pairings", json={"factory": "huaxing"})
        assert pair.status_code == 200, pair.text
        ticket = pair.json()["url"].split("#pair=")[1]
        redeem = client.post("/api/qc-mobile/exchange", json={"ticket": ticket})
        assert redeem.status_code == 200, redeem.text
        assert client.post(
            "/api/qc-mobile/sheet/entries/delete",
            json={"requestKey": uuid4().hex, "entries": [{"id": "a" * 32, "revision": 0}]},
        ).status_code == 404
        assert client.post(
            "/api/qc-mobile/sheet/review/delete",
            json={"requestKey": uuid4().hex, "entries": [{"id": "a" * 32, "revision": 0}]},
        ).status_code == 404

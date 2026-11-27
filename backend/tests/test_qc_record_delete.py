"""Comprehensive tests for QC_test admin account and QC record deletion boundaries."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import importlib
from io import BytesIO
import json
from threading import Event
from uuid import uuid4

import httpx
from openpyxl import Workbook
import pytest

from test_molding_sample_api import make_client, login_as


ALL_FACTORIES = ("huakang-a", "huakang-b", "huakang-c", "huakang-d", "huadeng", "huaxing")


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch, tmp_path):
    monkeypatch.setenv("QC_RECORD_ADMIN_BOOTSTRAP_SECRET", "QcFixtureOnly-2026")
    monkeypatch.setenv("QC_DEPARTMENT_DATA_DIR", str(tmp_path / "qc-companies"))
    monkeypatch.setenv("QC_DOSSIER_ENABLED", "false")
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, "TEST_TMP_DIR", tmp_path / "main-test-db")


def install_stateful_upstream(monkeypatch, *, records=None, defect_lib=None, partners=None):
    module = importlib.import_module("app.api.qc_department")
    records = list(records or [])
    state = {
        "records": records,
        "versions": {str(row["id"]): uuid4().hex for row in records},
        "generations": {str(row["id"]): uuid4().hex for row in records},
        "generation_starts": {},
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
                    "recordVersions": state["versions"],
                    "recordGenerations": state["generations"],
                    "recordGenerationStarts": state["generation_starts"],
                    "nextId": max([r["id"] for r in state["records"]], default=0) + 1,
                    "partners": list(state["partners"]),
                    "defectLib": list(state["defectLib"]),
                },
            )
        if path == "api/records/archive-sheet":
            payload = json.loads(body) if body else {}
            ids = {item["id"] for item in payload["items"] if state["versions"].get(str(item["id"])) == item["version"]}
            if ids:
                state["deleted_calls"].append(sorted(ids))
            outcome = ["archived" if item["id"] in ids else
                       "retained" if str(item["id"]) in state["versions"] else "absent" for item in payload["items"]]
            state["records"] = [r for r in state["records"] if r.get("id") not in ids]
            for record_id in ids:
                state["versions"].pop(str(record_id), None)
                state["generations"].pop(str(record_id), None)
            return httpx.Response(200, json={"ok": True, "results": outcome})
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
    res = client.post("/api/auth/login", json={"username": "QC_test", "password": "QcFixtureOnly-2026"})
    assert res.status_code == 200, res.text
    return res.json()


def frame_base(client, factory="huaxing"):
    res = client.get(f"/api/qc-department/{factory}/api/health")
    assert res.status_code == 200, res.text
    return res.json()["frame_url"]


@pytest.mark.parametrize("status", [None, "", " "])
def test_blank_legacy_state_is_locked_and_can_be_returned(monkeypatch, status):
    with make_client(monkeypatch) as client:
        original = {"id": 10, "status": status, "qc": "原检验员", "updatedAt": None, "remark": "原内容"}
        state = install_stateful_upstream(monkeypatch, records=[original])
        login_as(client, "qc_supervisor")
        base = frame_base(client)
        modified = {**original, "remark": "不应保存"}
        assert client.post(base + "api/records", json={"records": [modified]}).status_code == 409
        assert state["records"] == [original]
        target = base + "api/workflow/legacy-review"
        request = {"recordId": 10, "updatedAt": "", "action": "return", "reason": "补充照片"}
        assert client.post(target, json={**request, "action": "approve"}).status_code == 409
        result = client.post(target, json=request)
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "rejected"
        assert result.json()["qc"] == "原检验员"


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

    with make_auth_client(monkeypatch, SEED_DEFAULT_ACCOUNTS="false", AUTHZ_MODE=authz_mode,
                          IAM_IDENTITY_WRITES_ENABLED=str(authz_mode == "enforce").lower()) as client:
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


def test_upgrade_repairs_missing_binding_and_revokes_old_admin_frame(monkeypatch):
    from test_auth_api import make_client as make_auth_client
    with make_auth_client(monkeypatch, AUTHZ_MODE="enforce", IAM_IDENTITY_WRITES_ENABLED="true") as client:
        from app import db as database
        from app.models import auth as models
        from app.services import auth
        install_stateful_upstream(monkeypatch)
        login_as(client, "admin")
        old_url = frame_base(client)
        qc_id = auth.QC_RECORD_ADMIN_USER_ID
        binding_id = f"{qc_id}:qc_record_admin:huaxing:qc"
        with database.SessionLocal() as db:
            old_revision = db.get(models.AuthUserAuthorizationRevision, "user-admin").revision
            db.delete(db.get(models.AuthRoleBindingMetadata, binding_id))
            db.delete(db.get(models.AuthUserRole, binding_id))
            db.get(models.EmployeeProfile, qc_id).identity_mode = "v2"
            db.add(models.AuthRolePermission(id="admin:perm-qc_inspection-record_delete",
                role_id="admin", permission_id="perm-qc_inspection-record_delete"))
            db.commit()
        monkeypatch.setattr(auth.settings, "seed_default_accounts", False)
        database.init_db()
        assert client.get(old_url + "nexus-context.js").status_code == 409
        assert read_ui_context(client, frame_base(client))["deleteAllowed"] is False
        login_qc_test(client)
        for factory in ALL_FACTORIES:
            assert read_ui_context(client, frame_base(client, factory))["deleteAllowed"] is True
        with database.SessionLocal() as db:
            assert db.get(models.AuthUserAuthorizationRevision, "user-admin").revision == old_revision + 1
            qc = db.get(models.AuthUser, qc_id)
            qc.status = "suspended"
            qc.password_salt, qc.password_hash = auth.make_password_hash("changed-in-IAM")
            saved_hash = qc.password_hash
            db.commit()
        database.init_db()
        with database.SessionLocal() as db:
            assert db.get(models.AuthUserAuthorizationRevision, "user-admin").revision == old_revision + 1
            qc = db.get(models.AuthUser, qc_id)
            assert qc.password_hash == saved_hash and qc.status == "suspended"


def test_ordinary_qc_accounts_have_no_delete_permission_and_get_403(monkeypatch):
    with make_client(monkeypatch) as client:
        install_stateful_upstream(
            monkeypatch,
            records=[{"id": 10, "orderNo": "PO-10", "productNo": "SKU-10", "result": "PASS", "defect": ""}],
            defect_lib=[{"name": "刮花", "category": "外观/质量", "defaultLevel": "MAJ 1.0", "keywords": [], "enabled": True}],
            partners=[{"type": "supplier", "name": "天一"}],
        )
        for account in ("qc_inspector", "qc_supervisor", "admin"):
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
            assert client.post(base + "api/inspection-sheet/review/approved/delete", json=req).status_code == 403
            assert client.get(base + "api/inspection-summary/history/batches").status_code == 403
            assert client.post(base + f"api/inspection-summary/records/{'a'*32}/delete", json={"requestKey": uuid4().hex}).status_code == 403
            assert client.post(base + f"api/inspection-summary/history/{'b'*32}/rollback", json={"requestKey": uuid4().hex}).status_code == 403
            assert client.post(base + "api/records/delete", json={"ids": [10]}).status_code == 403
            assert client.post(base + "api/records/replace", json={"records": []}).status_code == 403
            assert client.post(base + "api/reference-data/clear", json={}).status_code == 403
            assert client.post(base + "api/records", json={"records": [], "deletedIds": [10]}).status_code == 403
            assert client.post(base + "api/defects", json={"defectLib": []}).status_code == 403
            assert client.post(base + "api/partners", json={"partners": []}).status_code == 403

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


@pytest.mark.parametrize("mode", ["legacy", "shadow", "enforce"])
def test_delete_is_not_delegable_even_with_grants_and_overrides(monkeypatch, mode):
    with make_client(monkeypatch) as client:
        from dataclasses import replace
        from app import db as database
        from app.models.auth import AuthUser
        from app.services import auth
        monkeypatch.setattr(auth.settings, "authz_mode", mode)
        with database.SessionLocal() as db:
            qc = auth.build_auth_context(db, db.get(AuthUser, auth.QC_RECORD_ADMIN_USER_ID))
            admin = auth.build_auth_context(db, db.get(AuthUser, "user-admin"))
        code = auth.QC_RECORD_DELETE
        override = auth.AuthOverrideContext(id="test", permission_code=code, factory_id="*",
                                            department="*", effect="allow", valid_from="", valid_until="", source_type="test")
        for other in (replace(qc, id="another-account"), replace(qc, username="other-name"),
                      replace(admin, grants=admin.grants + qc.grants, overrides=(override,)),
                      replace(qc, grants=admin.grants, overrides=(override,))):
            assert not auth.can(other, code, "huaxing", "qc")
            assert not auth.has_permission_in_scope(other, code, "huaxing", "qc")
        assert not auth.can(qc, code, "*", "qc")
        assert not auth.can(qc, code, "huaxing", "sales")


def seed_sales_order():
    from app.db import SessionLocal
    from app.models.customer_order_ledger import OrderLedgerLine

    with SessionLocal() as db:
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
        return {column.name: getattr(line, column.name) for column in OrderLedgerLine.__table__.columns}


def test_workbench_delete_covers_blank_draft_workflow_and_legacy_without_touching_sales_order(monkeypatch):
    with make_client(monkeypatch) as client:
        upstream_state = install_stateful_upstream(
            monkeypatch,
            records=[{"id": 101, "client": "LEGACY-CUST", "orderNo": "PO-LEG-1", "productNo": "SKU-LEG-1", "qty": 20, "result": "", "status": "draft"}],
        )
        db_module = importlib.import_module("app.db")
        from app.models.customer_order_ledger import OrderLedgerLine

        seed_sales_order()

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


@pytest.mark.parametrize("dossier_enabled", [False, True])
def test_direct_review_delete_preserves_audit_and_withdraws_summary_reports_and_workflow(monkeypatch, dossier_enabled):
    monkeypatch.setenv("QC_DOSSIER_ENABLED", str(dossier_enabled).lower())
    test_client = make_client(monkeypatch)
    from app import db as database
    from app.models.customer_order_ledger import OrderLedgerLine
    from app.models.qc_dossier import QcDossierOutbox
    from app.services import qc_dossier, qc_inspection_sheet as sheet, qc_inspection_summary as summary, qc_workflow as workflow

    if dossier_enabled:
        database.init_db()
        QcDossierOutbox.__table__.create(database.engine)
        qc_dossier.migrate()

    with test_client as client:
        install_stateful_upstream(monkeypatch)
        sales_before = seed_sales_order()
        login_qc_test(client)
        base = frame_base(client, "huaxing")

        push_item = {"sourceId": "sales-line-delete-test", "sourceRevision": 1, "method": "internal",
                     "batch": "第一批", "plannedDate": "2026-11-26", "plannedQuantity": 500}
        assert client.post(base + "api/workflow/tasks", json={"requestKey": uuid4().hex, "items": [push_item]}).status_code == 200
        assert client.post(base + "api/inspection-sheet/intake/manual", json=manual_row("ZURU", "PO-REV-1", "SKU-PENDING")).status_code == 200
        items = {e["poNo"]: e for e in client.get(base + "api/inspection-sheet/entries").json()["items"]}
        for po in ("PO-REV-1", "PO-SALES-1"):
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
        approved_path = base + "api/inspection-sheet/review/approved/delete"
        pending = review_items["PO-REV-1"]
        wrong_tab = client.post(approved_path, json={"requestKey": uuid4().hex, "entries": [
            {"id": pending["id"], "revision": pending["revision"]},
        ]}).json()
        assert wrong_tab["results"][0]["status"] == 409

        # Pending delete removes PO-REV-1 cleanly without entering summary.
        del_pending = client.post(
            base + "api/inspection-sheet/review/delete",
            json={"requestKey": uuid4().hex, "entries": [{"id": review_items["PO-REV-1"]["id"], "revision": review_items["PO-REV-1"]["revision"]}], "reason": "误提待审"},
        ).json()
        assert del_pending["succeeded"] == 1

        # Confirm the pushed task (writes into 验货汇总).
        rev2 = review_items["PO-SALES-1"]
        confirm_res = client.post(
            base + "api/inspection-sheet/review/confirm",
            json={"requestKey": uuid4().hex, "entries": [{"id": rev2["id"], "revision": rev2["revision"]}]},
        ).json()
        assert confirm_res["succeeded"] == 1
        approved_rev2 = confirm_res["results"][0]["item"]

        # Verify all report counts start at one before deletion.
        def report_totals():
            daily = [client.get(base + "api/daily-report", params={"date": "2026-11-26", "period": p}) for p in ("daily", "weekly", "monthly")]
            yearly = client.get(base + "api/approved-statistics/report", params={"year": "2026", "result": "ALL"})
            assert all(r.status_code == 200 for r in [*daily, yearly])
            return [r.json()["total"] for r in daily] + [yearly.json()["totals"]["total"]]

        assert report_totals() == [1, 1, 1, 1]
        summary_rows = client.get(base + "api/inspection-summary/records").json()["items"]
        assert len(summary_rows) == 1 and summary_rows[0]["poNo"] == "PO-SALES-1"
        summary_id = summary_rows[0]["id"]

        # The pending route still rejects approved records.
        wrong_tab = client.post(
            base + "api/inspection-sheet/review/delete",
            json={"requestKey": uuid4().hex, "entries": [{"id": approved_rev2["id"], "revision": approved_rev2["revision"]}]},
        ).json()
        assert wrong_tab["failed"] == 1 and wrong_tab["results"][0]["status"] == 409

        # The history-only summary endpoint directs reviewed records to the new action.
        direct_summary = client.post(
            base + f"api/inspection-summary/records/{summary_id}/delete",
            json={"requestKey": uuid4().hex},
        )
        assert direct_summary.status_code == 409
        assert "已审核" in direct_summary.json()["detail"]

        request = {"requestKey": uuid4().hex, "entries": [{"id": approved_rev2["id"], "revision": approved_rev2["revision"]}], "reason": "清理已审核验收记录"}
        del_res = client.post(approved_path, json=request)
        assert del_res.status_code == 200 and del_res.json()["succeeded"] == 1, del_res.text
        replay = client.post(approved_path, json=request)
        assert replay.status_code == 200 and replay.json()["results"][0]["replayed"] is True

        assert client.get(base + "api/inspection-sheet/entries").json()["items"] == []
        assert client.get(base + "api/inspection-summary/records").json()["total"] == 0
        assert client.get(base + "api/inspection-sheet/review/entries").json()["items"] == []
        assert report_totals() == [0, 0, 0, 0]
        with sheet.store() as conn:
            event = conn.execute("SELECT * FROM changes WHERE entry_id=? AND action='delete'", (approved_rev2["id"],)).fetchall()
            assert len(event) == 1 and event[0]["location"] == "审核中心 · 已审核"
            assert json.loads(event[0]["snapshot"]) == approved_rev2
            diff = json.loads(event[0]["diff"])
            assert (diff["scope"], diff["previousReviewState"], diff["wasApproved"]) == ("approved", "approved", True)
        with summary.store() as conn:
            record = conn.execute("SELECT * FROM records WHERE id=?", (summary_id,)).fetchone()
            assert (record["active"], record["status"]) == (0, "withdrawn")
            previous = conn.execute("SELECT payload FROM changes WHERE record_id=? ORDER BY id DESC", (summary_id,)).fetchone()
            assert previous["payload"] == record["payload"]
        with workflow.store() as conn:
            assert conn.execute("SELECT 1 FROM deleted_tasks WHERE id=?", (approved_rev2["workflowId"],)).fetchone()
            assert not conn.execute("SELECT 1 FROM tasks WHERE id=?", (approved_rev2["workflowId"],)).fetchone()
        with database.SessionLocal() as db:
            order = db.get(OrderLedgerLine, "sales-line-delete-test")
            assert {col: getattr(order, col) for col in sales_before} == sales_before
            assert workflow.sources(db, "huaxing")["items"][0]["tasks"] == []
        repush = client.post(base + "api/workflow/tasks", json={"requestKey": uuid4().hex, "items": [push_item]})
        assert repush.status_code == 200 and repush.json()["items"][0]["id"] != approved_rev2["workflowId"]


@pytest.mark.parametrize("status", ["approved", None, "", " "])
def test_approved_delete_with_legacy_completed_projection_and_cleanup_resume(monkeypatch, status):
    with make_client(monkeypatch) as client:
        legacy = {"id": 201, "client": "LEGACY", "orderNo": "PO-LEG-APPROVED", "result": "PASS", "status": status}
        state = install_stateful_upstream(monkeypatch, records=[legacy])
        from app.services import qc_inspection_sheet as sheet, qc_inspection_summary as summary

        # A record mirrored before the fix had flow v2 even if the legacy state was blank.
        previous = sheet.candidates("huaxing", [legacy], [], [], legacy_versions=state["versions"],
                                    legacy_generations=state["generations"])
        previous[0][1]["legacyReviewState"] = status
        sheet.sync("huaxing", previous)
        login_qc_test(client)
        base = frame_base(client)
        assert client.get(base + "api/inspection-sheet/entries").json()["items"] == []
        items = client.get(base + "api/inspection-sheet/review/entries").json()["items"]
        row = next(item for item in items if item["poNo"] == legacy["orderNo"])
        assert row["legacyCompleted"]

        with summary.store(True) as conn:
            identity = summary.upsert(conn, "huaxing", "entry:" + row["id"], {
                "entryId": row["id"], "sourceKind": "submission", "result": "PASS", "status": "completed",
            })

        gateway = importlib.import_module("app.api.qc_department")
        upstream = gateway.upstream

        async def temporarily_unavailable(method, path, params, data):
            if path == "api/records/archive-sheet":
                return httpx.Response(503)
            return await upstream(method, path, params, data)

        path = base + "api/inspection-sheet/review/approved/delete"
        req = {"requestKey": uuid4().hex, "entries": [{"id": row["id"], "revision": row["revision"]}]}
        wrong_view = client.post(base + "api/inspection-sheet/entries/delete", json=req).json()
        assert wrong_view["results"][0]["status"] == 409
        monkeypatch.setattr(gateway, "upstream", temporarily_unavailable)
        partial = client.post(path, json=req)
        assert partial.status_code == 200 and partial.json()["results"][0]["legacyArchive"] == "pending"
        assert state["records"] == [legacy]
        assert client.get(base + "api/inspection-sheet/review/entries").json()["items"] == []
        with summary.store() as conn:
            assert tuple(conn.execute("SELECT active,status FROM records WHERE id=?", (identity,)).fetchone()) == (0, "withdrawn")
            assert conn.execute("SELECT 1 FROM changes WHERE record_id=?", (identity,)).fetchone()
        monkeypatch.setattr(gateway, "upstream", upstream)
        # Reloading the list completes the durable cleanup without the original request key.
        assert client.get(base + "api/inspection-sheet/review/entries").json()["items"] == []
        assert state["deleted_calls"] == [[201]] and state["records"] == []
        assert sheet.pending_legacy_deletes("huaxing") == []
        replacement = {**legacy, "orderNo": "NEW-LEGACY"}
        state["records"].append(replacement)
        state["versions"]["201"] = uuid4().hex
        state["generations"]["201"] = uuid4().hex
        replayed = client.post(path, json=req).json()["results"][0]
        assert replayed["replayed"] is True and replayed["legacyArchive"] == "archived"
        assert state["deleted_calls"] == [[201]] and state["records"] == [replacement]
        restored = client.get(base + "api/inspection-sheet/review/entries").json()["items"]
        assert len(restored) == 1 and restored[0]["poNo"] == "NEW-LEGACY" and restored[0]["id"] != row["id"]


@pytest.mark.parametrize("restoration", ("in-place", "before-submit", "after-approval"))
def test_tokenless_approved_mirror_withdraws_but_retains_a_newer_legacy_source(monkeypatch, restoration):
    with make_client(monkeypatch) as client:
        from app.services import qc_inspection_sheet as sheet

        factory = "huaxing"
        actor = {"id": "user-qc-test", "name": "QC 数据管理员"}
        legacy = {"id": 301, "status": "rejected", "result": "PASS", "client": "LEGACY", "orderNo": "TOKENLESS",
                  "productNo": "SKU-301", "inspDate": "2026-11-26"}
        old = sheet.sync(factory, sheet.candidates(factory, [legacy], [], []))["items"][0]
        newer = {**legacy, "result": "FAIL"}
        if restoration != "in-place":
            newer.update(status="approved", orderNo="RESTORED")
        state = install_stateful_upstream(monkeypatch, records=[newer])
        if restoration == "before-submit":
            state["generation_starts"]["301"] = sheet.wf.now()
        submitted = sheet.submit(factory, old["id"], {"revision": old["revision"]}, actor)
        approved = sheet.review_batch(factory, "confirm", {
            "entries": [{"id": old["id"], "revision": submitted["revision"]}], "requestKey": uuid4().hex,
        }, actor)["results"][0]["item"]
        if restoration == "after-approval":
            state["generation_starts"]["301"] = sheet.wf.now()
        login_qc_test(client)
        base = frame_base(client)
        rows = client.get(base + "api/inspection-sheet/review/entries").json()["items"]
        original = next(row for row in rows if row["id"] == approved["id"])
        assert original["result"] == "PASS"
        assert client.get(base + "api/inspection-summary/records").json()["total"] == 1
        for period in ("daily", "weekly", "monthly"):
            report = client.get(base + "api/daily-report", params={"date": "2026-11-26", "period": period})
            assert report.status_code == 200 and report.json()["total"] == 1, report.text
        assert client.get(base + "api/approved-statistics/report?year=2026&result=ALL").json()["totals"]["total"] == 1
        request = {
            "entries": [{"id": old["id"], "revision": original["revision"]}], "requestKey": uuid4().hex,
        }
        route = base + "api/inspection-sheet/review/approved/delete"
        deleted = client.post(route, json=request).json()["results"][0]
        assert deleted["ok"] and deleted["legacyArchive"] == "retained"
        assert client.get(base + "api/inspection-sheet/entries").json()["items"] == []
        remaining = client.get(base + "api/inspection-sheet/review/entries").json()["items"]
        assert [row["poNo"] for row in remaining] == ([] if restoration == "in-place" else ["RESTORED"])
        assert client.get(base + "api/inspection-summary/records").json()["total"] == 0
        for period in ("daily", "weekly", "monthly"):
            report = client.get(base + "api/daily-report", params={"date": "2026-11-26", "period": period})
            assert report.status_code == 200 and report.json()["total"] == 0, report.text
        assert client.get(base + "api/approved-statistics/report?year=2026&result=ALL").json()["totals"]["total"] == 0
        assert sheet.pending_legacy_deletes(factory) == []
        assert state["deleted_calls"] == [] and state["records"] == [newer]
        with sheet.store() as conn:
            event = conn.execute("SELECT diff,snapshot FROM changes WHERE entry_id=? AND action='delete'", (old["id"],)).fetchone()
            assert json.loads(event["diff"])["legacyArchive"] == "retained"
            assert json.loads(event["snapshot"])["result"] == "PASS"
            # Simulate a pre-upgrade receipt: old deployments never persisted a queue row.
            conn.execute("DELETE FROM legacy_delete_queue WHERE entry_id=?", (old["id"],))
        replay = client.post(route, json=request).json()["results"][0]
        assert replay["replayed"] and replay["legacyArchive"] == "retained"
        assert state["deleted_calls"] == [] and state["records"] == [newer]


@pytest.mark.parametrize("restore_before_first_read", (False, True))
def test_preupgrade_tombstone_isolates_original_but_restored_generation_is_visible(monkeypatch, restore_before_first_read):
    with make_client(monkeypatch) as client:
        from app.services import qc_inspection_sheet as sheet

        actor = {"id": "user-qc-test", "name": "QC 数据管理员"}
        legacy = {"id": 401, "status": "rejected", "result": "", "client": "OLD", "orderNo": "OLD", "productNo": "OLD"}
        state = install_stateful_upstream(monkeypatch, records=[legacy])
        old = sheet.sync("huaxing", sheet.candidates("huaxing", [legacy], [], []))["items"][0]
        request = {"entries": [{"id": old["id"], "revision": old["revision"]}], "requestKey": uuid4().hex}
        assert sheet.delete_batch("huaxing", "workbench", request, actor)["succeeded"] == 1
        with sheet.store(True) as conn:
            conn.execute("DELETE FROM legacy_delete_queue WHERE entry_id=?", (old["id"],))
        login_qc_test(client)
        base = frame_base(client)
        entries = base + "api/inspection-sheet/entries"
        if not restore_before_first_read:
            assert client.get(entries).json()["items"] == []
        state["records"] = [{**legacy, "orderNo": "RESTORED"}]
        state["versions"]["401"] = uuid4().hex
        state["generations"]["401"] = uuid4().hex
        state["generation_starts"]["401"] = sheet.wf.now()
        assert client.post(entries + "/delete", json=request).json()["results"][0]["legacyArchive"] == "retained"
        current = client.get(entries).json()["items"]
        assert len(current) == 1 and current[0]["poNo"] == "RESTORED" and current[0]["id"] != old["id"]
        assert state["deleted_calls"] == []


def test_withdrawn_linked_legacy_record_does_not_reappear_as_standalone(monkeypatch):
    with make_client(monkeypatch) as client:
        from app.services import qc_workflow

        legacy = {"id": 402, "status": "rejected", "result": "PASS", "client": "OLD",
                  "orderNo": "LINKED", "productNo": "SKU", "inspDate": "2026-11-26"}
        actor = {"id": "user-qc-test", "name": "QC 数据管理员"}
        qc_workflow.create_entry("huaxing", {"recordId": 402}, actor, legacy)
        state = install_stateful_upstream(monkeypatch, records=[legacy])
        login_qc_test(client)
        entries = frame_base(client) + "api/inspection-sheet/entries"
        review = frame_base(client) + "api/inspection-sheet/review"
        item, = client.get(review + "/entries").json()["items"]
        assert item["workflowId"] and item["reviewState"] == "pending"
        deleted = client.post(review + "/delete", json={
            "entries": [{"id": item["id"], "revision": item["revision"]}], "requestKey": uuid4().hex,
        }).json()["results"][0]
        assert deleted["ok"] and deleted["legacyArchive"] == "retained"
        assert client.get(entries).json()["items"] == []
        assert client.get(review + "/entries").json()["items"] == []
        link_route = frame_base(client) + "api/workflow/legacy"
        blocked = client.post(link_route, json={"recordId": 402})
        assert blocked.status_code == 409 and "保留待核对" in blocked.json()["detail"]
        state["records"] = [{**legacy, "orderNo": "REPLACEMENT"}]
        state["versions"]["402"] = uuid4().hex
        state["generations"]["402"] = uuid4().hex
        restored, = client.get(entries).json()["items"]
        assert restored["poNo"] == "REPLACEMENT" and not restored.get("workflowId")
        link = client.post(link_route, json={"recordId": 402})
        assert link.status_code == 200, link.text
        linked, = client.get(entries).json()["items"]
        assert linked["poNo"] == "REPLACEMENT" and linked["workflowId"] == link.json()["id"]
        assert state["deleted_calls"] == []


def test_replacement_cannot_be_bound_to_a_legacy_workflow_on_its_first_sheet_read(monkeypatch):
    with make_client(monkeypatch) as client:
        from app.services import qc_workflow

        legacy = {"id": 403, "status": "rejected", "result": "PASS", "client": "OLD",
                  "orderNo": "FIRST-LINK", "productNo": "SKU"}
        actor = {"id": "user-qc-test", "name": "QC 数据管理员"}
        task = qc_workflow.create_entry("huaxing", {"recordId": 403}, actor, legacy)
        newer = {**legacy, "status": "approved", "orderNo": "FIRST-RESTORATION", "result": "FAIL"}
        state = install_stateful_upstream(monkeypatch, records=[newer])
        state["generation_starts"]["403"] = qc_workflow.now()
        login_qc_test(client)
        review = frame_base(client) + "api/inspection-sheet/review"
        rows = client.get(review + "/entries").json()["items"]
        assert {row["poNo"] for row in rows} == {"FIRST-LINK", "FIRST-RESTORATION"}
        old = next(row for row in rows if row.get("workflowId") == task["id"])
        deleted = client.post(review + "/delete", json={
            "entries": [{"id": old["id"], "revision": old["revision"]}], "requestKey": uuid4().hex,
        }).json()["results"][0]
        assert deleted["ok"] and deleted["legacyArchive"] == "retained"
        current, = client.get(review + "/entries").json()["items"]
        assert current["poNo"] == "FIRST-RESTORATION" and not current.get("workflowId")
        assert state["deleted_calls"] == [] and state["records"] == [newer]


def test_linking_a_visible_legacy_row_invalidates_its_stale_delete(monkeypatch):
    with make_client(monkeypatch) as client:
        from app.services import qc_inspection_sheet, qc_workflow

        legacy = {"id": 404, "status": "rejected", "result": "PASS", "client": "OLD",
                  "orderNo": "LINK-FIRST", "productNo": "SKU"}
        state = install_stateful_upstream(monkeypatch, records=[legacy])
        login_qc_test(client)
        base = frame_base(client)
        entries = base + "api/inspection-sheet/entries"
        old, = client.get(entries).json()["items"]
        candidates_read, release = Event(), Event()
        sync = qc_inspection_sheet.sync

        def delayed_sync(*args):
            candidates_read.set()
            assert release.wait(10)
            return sync(*args)

        with monkeypatch.context() as delayed:
            delayed.setattr(qc_inspection_sheet, "sync", delayed_sync)
            with ThreadPoolExecutor(max_workers=1) as executor:
                in_flight = executor.submit(client.get, entries)
                try:
                    assert candidates_read.wait(10)
                    linked = client.post(base + "api/workflow/legacy", json={"recordId": 404})
                finally:
                    release.set()
                refreshed, = in_flight.result(timeout=10).json()["items"]
        assert linked.status_code == 200, linked.text
        stale = client.post(entries + "/delete", json={
            "entries": [{"id": old["id"], "revision": old["revision"]}], "requestKey": uuid4().hex,
        }).json()["results"][0]
        assert stale["status"] == 409 and state["records"] == [legacy]
        task_id = linked.json()["id"]
        assert refreshed["id"] == old["id"] and refreshed["workflowId"] == task_id
        deleted = client.post(entries + "/delete", json={
            "entries": [{"id": refreshed["id"], "revision": refreshed["revision"]}], "requestKey": uuid4().hex,
        }).json()["results"][0]
        assert deleted["ok"] and deleted["legacyArchive"] == "archived"
        assert state["records"] == [] and state["deleted_calls"] == [[404]]
        with qc_workflow.store() as conn:
            assert conn.execute("SELECT 1 FROM deleted_tasks WHERE id=?", (task_id,)).fetchone()
            assert not conn.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone()


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

"""Follow-up is procurement evidence, never a substitute for warehouse receipt."""
import importlib
import json

from sqlalchemy import select, func
from test_fabric_procurement import BASE, row, book, upload, commit, stored
from test_molding_sample_api import login_as, make_client


def save(client, content, scope="TRACKING"):
    preview = upload(client, content, scope=scope)
    assert preview.status_code == 200, preview.text
    saved = commit(client, content, preview.json(), scope=scope)
    assert saved.status_code == 200, saved.text
    return saved.json()


def undo_preview(client, batch):
    return client.get(f"{BASE}/imports/{batch['id']}/withdraw-preview", params={"factory_id": "huakang-c"})


def undo(client, batch, preview, **overrides):
    return client.post(f"{BASE}/imports/{batch['id']}/withdraw", json={"factory_id": "huakang-c", "preview_token": preview["preview_token"], "reason": "选错文件", "confirmed": True, **overrides})


def test_tracking_excludes_new_history_but_follows_existing_lines_into_returned(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        initial = book([row()], [row(订单号="OLD", 交货明细="100", 入库数量=100)])
        default_preview = client.post(BASE + "/imports/preview", data={"factory_id": "huakang-c"}, files={"file": ("来源.xlsx", initial)})
        assert default_preview.status_code == 200 and default_preview.json()["counts"]["new"] == 1
        preview = upload(client, initial, scope="TRACKING").json()
        assert preview["excluded_history"] == 1
        assert preview["counts"]["new"] == 1
        save(client, initial)
        line_id = stored(client)["items"][0]["id"]
        changed = book([], [row(交货明细="100", 入库数量=100), row(订单号="OLD", 交货明细="100", 入库数量=100)])
        preview = upload(client, changed, scope="TRACKING").json()
        assert preview["counts"]["updated"] == 1 and preview["counts"]["new"] == 0
        assert "status" in preview["items"][0]["changes"]
        save(client, changed)
        assert stored(client, view="OUTSTANDING")["total"] == 0
        arrival = stored(client, view="ARRIVAL_REVIEW")
        assert arrival["total"] == 1 and arrival["items"][0]["id"] == line_id
        assert arrival["items"][0]["reported_outstanding_quantity"] == "0"
        assert stored(client, view="CHANGED")["total"] == 1
        save(client, changed)
        assert stored(client, view="CHANGED")["items"][0]["unreviewed_changes"] == 1
        dbm = importlib.import_module("app.db")
        carton = importlib.import_module("app.models.carton_procurement")
        with dbm.SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(carton.CartonInventoryMovement)) == 0


def test_outstanding_filter_does_not_assume_unknown_is_zero_and_pages_after_filter(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        save(client, book([row(订单号="UNKNOWN", 入库数量="#VALUE!", 交货明细=""), row(订单号="ZERO", 入库数量=0, 交货明细="0"),
                           row(订单号="PARTIAL"), row(订单号="FULL", 入库数量=100, 交货明细="100"), row(订单号="OVER", 入库数量=101, 交货明细="101")]))
        outstanding = stored(client, view="OUTSTANDING", limit=1)
        assert outstanding["total"] == 3 and len(outstanding["items"]) == 1
        assert outstanding["summary"] == {"outstanding": 3, "not_arrived": 2, "partial": 1, "arrival_review": 2, "changed": 0,
                                          "overdue": 0, "due_today": 0, "awaiting_date": 3, "quantity_review": 2}
        assert stored(client, view="PARTIAL")["items"][0]["reported_outstanding_quantity"] == "50"
        unknown = stored(client, view="NOT_ARRIVED", search="UNKNOWN")["items"][0]
        assert unknown["facts"]["reported_received_quantity"] is None
        assert unknown["reported_outstanding_quantity"] is None
        assert stored(client, view="NOT_ARRIVED", offset=2)["items"] == []


def test_read_change_is_version_bound_and_never_clears_arrival_followup(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        save(client, book([row()]))
        initial = stored(client)["items"][0]
        arrived_batch = save(client, book([], [row(交货明细="100", 入库数量=100)]))
        stale_withdraw = undo_preview(client, arrived_batch).json()
        line = stored(client, view="ARRIVAL_REVIEW")["items"][0]
        path = f"{BASE}/lines/{line['id']}/review-changes"
        assert client.post(path, json={"factory_id": "huakang-c", "expected_revision": initial["revision"]}).status_code == 409
        response = client.post(path, json={"factory_id": "huakang-c", "expected_revision": line["revision"]})
        assert response.status_code == 200 and response.json()["stock_posted"] is False
        assert stored(client, view="CHANGED")["total"] == 0
        assert stored(client, view="ARRIVAL_REVIEW")["total"] == 1
        assert undo(client, arrived_batch, stale_withdraw).status_code == 409
        save(client, book([], [row(交货明细="100", 入库数量=100, 订单数量=120)]))
        assert stored(client, view="CHANGED")["total"] == 1
        # A missing source row never cancels the tracked purchase.
        save(client, book([row(订单号="OTHER")]))
        assert stored(client, view="ARRIVAL_REVIEW")["total"] == 1


def test_withdraw_restores_updates_hides_new_preserves_evidence_and_can_reimport(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        first = save(client, book([row()]))
        original = stored(client)["items"][0]
        second_content = book([row(订单数量=120), row(订单号="NEW")])
        second = save(client, second_content)
        ids = {line["facts"]["order_no"]: line["id"] for line in stored(client)["items"]}
        assert undo_preview(client, first).status_code == 409
        review = undo_preview(client, second).json()
        assert review["remove_count"] == 1 and review["restore_count"] == 1
        assert undo(client, second, review, reason=" ").status_code == 422
        assert undo(client, second, review, confirmed=False).status_code == 422
        response = undo(client, second, review)
        assert response.status_code == 200 and response.json()["withdrawal"]["reason"] == "选错文件"
        assert undo(client, second, review).json() == response.json()
        line = stored(client)["items"][0]
        assert stored(client)["total"] == 1 and line["id"] == original["id"]
        assert line["facts"]["ordered_quantity"] == "100"
        assert stored(client, view="CHANGED")["total"] == 0
        detail = client.get(f"{BASE}/lines/{line['id']}", params={"factory_id": "huakang-c"}).json()
        assert len(detail["evidence"]) == 2 and any(event["withdrawal"] for event in detail["evidence"])
        third = save(client, second_content)
        assert ids == {line["facts"]["order_no"]: line["id"] for line in stored(client)["items"]}
        assert undo(client, third, undo_preview(client, third).json()).status_code == 200
        assert undo(client, first, undo_preview(client, first).json()).status_code == 200
        assert stored(client)["total"] == 0
        assert stored(client, view="ARRIVAL_REVIEW")["total"] == 0
        save(client, book([row()]))
        assert stored(client)["items"][0]["id"] == original["id"]


def test_retry_of_withdrawn_import_cannot_report_success_or_reactivate_sources(monkeypatch):
    from uuid import uuid4
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        content = book([row()]); preview = upload(client, content).json(); request = str(uuid4())
        result = commit(client, content, preview, request).json()
        assert undo(client, result, undo_preview(client, result).json()).status_code == 200
        retry = commit(client, content, preview, request)
        assert retry.status_code == 409 and "已撤销" in retry.text
        assert stored(client)["total"] == 0


def test_withdraw_and_import_previews_invalidate_each_other_including_unchanged_batches(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        content = book([row()])
        first = save(client, content)
        withdrawal = undo_preview(client, first).json()
        second = save(client, content)
        assert undo(client, first, withdrawal).status_code == 409
        import_preview = upload(client, content, scope="TRACKING").json()
        assert undo(client, second, undo_preview(client, second).json()).status_code == 200
        assert commit(client, content, import_preview, scope="TRACKING").status_code == 409
        assert undo(client, first, withdrawal).status_code == 409
        assert undo(client, first, undo_preview(client, first).json()).status_code == 200


def test_review_and_withdraw_require_same_factory_and_import_authority(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        batch = save(client, book([row()]))
        review = undo_preview(client, batch).json()
        line = stored(client)["items"][0]
        assert undo(client, batch, review, factory_id="huakang-a").status_code == 422
        login_as(client, "engineer")
        assert undo_preview(client, batch).status_code == 403
        assert undo(client, batch, review).status_code == 403
        assert client.post(f"{BASE}/lines/{line['id']}/review-changes", json={"factory_id": "huakang-c", "expected_revision": line["revision"]}).status_code == 403


def test_legacy_same_time_imports_block_unsafe_rollback(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        first = save(client, book([row()]))
        second = save(client, book([row(订单数量=120)]))
        dbm = importlib.import_module("app.db")
        models = importlib.import_module("app.models.fabric_procurement")
        with dbm.SessionLocal() as db:
            for batch in db.scalars(select(models.FabricProcurementImport)):
                payload = json.loads(batch.result_json); payload.pop("sequence")
                batch.result_json = json.dumps(payload)
                batch.occurred_at = "2026-10-06T10:00:00+08:00"
            db.commit()
        assert undo_preview(client, first).status_code == 409
        assert undo_preview(client, second).status_code == 409


def test_tracking_does_not_guess_when_pending_and_returned_rows_share_identity(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        save(client, book([row()]))
        content = book([row()], [row(入库数量=100, 交货明细="100")])
        preview = upload(client, content, scope="TRACKING").json()
        assert preview["counts"]["blocked"] == 2 and preview["counts"]["updated"] == 0
        assert stored(client, view="OUTSTANDING")["total"] == 1
        assert stored(client, view="ARRIVAL_REVIEW")["total"] == 0


def test_reordered_multiline_reimport_after_withdraw_keeps_exact_history_owners(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        values = [row(订单数量=80), row(订单数量=100)]
        first = save(client, book(values))
        original = {line["facts"]["ordered_quantity"]: line["id"] for line in stored(client)["items"]}
        assert undo(client, first, undo_preview(client, first).json()).status_code == 200
        second = save(client, book(list(reversed(values))))
        assert original == {line["facts"]["ordered_quantity"]: line["id"] for line in stored(client)["items"]}
        assert undo(client, second, undo_preview(client, second).json()).status_code == 200
        save(client, book([row(订单数量=90), row(订单数量=100)]))
        current = {line["facts"]["ordered_quantity"]: line["id"] for line in stored(client)["items"]}
        assert current["100"] == original["100"] and current["90"] not in original.values()

"""Independent P2 journey, using only a disposable fixture database."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal as D
from uuid import uuid4

import pytest

from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import BASE as PORTAL, setup_portal, supplier_login, accept_all, ship_payload
from test_carton_partial_shipment_receiving import payload, post
from test_carton_settlement_collaboration import workspace, save, review
from test_carton_supplier_settlement_api import action
from test_carton_transaction_guards_api import outbound, ledger

BASE = "/api/carton-procurement"
UNIFIED = "/api/carton-unified-deliveries"


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, "TEST_TMP_DIR", tmp_path)


def test_confirmed_month_reopen_shortfall_actual_return_and_next_month_receipt(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        from app.services import carton_procurement as core
        monkeypatch.setattr(core, "business_now", lambda: datetime(2026, 11, 5, 12))
        order = accept_all(client)
        dispatch = ship_payload(order)
        for line in dispatch["lines"]:
            line["unit_price"] = "2"
        sent = client.post(PORTAL + "/shipments", json=dispatch)
        assert sent.status_code == 201, sent.text
        shipment = sent.json()
        login_as(client, "warehouse_keeper")
        received = post(client, shipment, payload(client, shipment, 8, "2026-09-30", "CLOSE"))
        login_as(client, "carton_supervisor")
        initial_ledger = ledger(client)
        initial_total = sum(D(row["quantity"]) for row in initial_ledger)
        september = workspace(client)
        draft = save(client, september)
        supplier_login(client)
        approved = review(client, draft)
        assert approved.status_code == 200, approved.text
        login_as(client, "carton_supervisor")
        confirmed = action(client, approved.json())
        assert confirmed.status_code == 200, confirmed.text
        frozen = deepcopy(confirmed.json())

        reopening = dict(factory_id="huaxing", request_id=uuid4().hex, reason="核实原单尚有一件待送，纠正误关闭",
            formal=dict(expected_revision=received["revision"], lines=[
                dict(shipment_line_id=line["id"], quantity="1") for line in received["lines"]]))
        url = UNIFIED + "/FORMAL:" + shipment["id"] + "/reopen-shortfall"
        blocked = client.post(url, json=reopening)
        assert blocked.status_code == 409, blocked.text
        return_data = outbound(order, 1, issue_kind="RETURN", return_date="2026-09-30", reason="实际月底交接退供应商")
        blocked = client.post(BASE + "/inventory/movements", json=return_data)
        assert blocked.status_code == 409, blocked.text
        supplier_login(client)
        late_note = dict(dispatch, request_id=uuid4().hex, delivery_note_no="LATE-P2-" + uuid4().hex[:8])
        blocked = client.post(PORTAL + "/shipments", json=late_note)
        assert blocked.status_code == 409 and "月份已确认" in blocked.text, blocked.text
        # Original successful requests remain retryable after the period closes.
        retry = client.post(PORTAL + "/shipments", json=dispatch)
        assert retry.status_code == 201 and retry.json()["id"] == shipment["id"], retry.text
        login_as(client, "carton_supervisor")
        assert ledger(client) == initial_ledger
        assert not workspace(client)["documents"][0]["stale"]

        reopened_month = action(client, frozen, "reopen", reason="核实跨月原单短送及实际退货依据")
        assert reopened_month.status_code == 200, reopened_month.text
        assert "supplier_review" not in reopened_month.json()["result"]
        reopened = client.post(url, json=reopening)
        assert reopened.status_code == 200, reopened.text
        assert client.post(url, json=reopening).json() == reopened.json()
        assert ledger(client) == initial_ledger  # A shortfall correction cannot invent a stock movement.
        for line in reopened.json()["lines"]:
            assert D(line["closed_quantity"]) == 1
            assert D(line["remaining_quantity"]) == 1
        returned = client.post(BASE + "/inventory/movements", json=return_data)
        assert returned.status_code == 201, returned.text
        assert client.post(BASE + "/inventory/movements", json=return_data).json() == returned.json()
        current_september = workspace(client)
        returns = [row for row in current_september["sources"] if row["kind"] == "RETURN"]
        assert len(returns) == 1
        assert returns[0]["acceptance_date"] == "2026-09-30"
        assert returns[0]["posting_date"] == "2026-11-05"
        assert D(returns[0]["quantity"]) == 1  # RETURN kind supplies the deduction sign in settlement comparison.
        assert not any(row["kind"] == "RETURN" for row in workspace(client, "2026-11")["sources"])

        current = client.get(PORTAL + "/internal/workspace", params={"factory_id": "huaxing"}).json()
        current_shipment = next(row for row in current["shipments"] if row["id"] == shipment["id"])
        second = post(client, current_shipment, payload(client, current_shipment, 1, "2026-10-01"))
        assert all(D(line["received_quantity"]) == 9 and D(line["closed_quantity"]) == 1 for line in second["lines"])
        october = workspace(client, "2026-10")
        assert all(D(row["quantity"]) == 1 for row in october["sources"])
        assert len(october["sources"]) == len(shipment["lines"])
        assert sum(D(row["quantity"]) for row in ledger(client)) == initial_total - 1 + len(shipment["lines"])
        old_version = next(row for row in workspace(client)["documents"] if row["id"] == frozen["id"])
        assert old_version["status"] == "SUPERSEDED"
        for key in ("sources", "statement", "result", "source_fingerprint"):
            assert old_version[key] == frozen[key]

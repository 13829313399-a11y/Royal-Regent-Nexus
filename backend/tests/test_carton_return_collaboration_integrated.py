"""Independent return-to-credit-to-cash journey, using disposable API fixtures."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal as D
from uuid import uuid4

import pytest

from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import supplier_login
from test_carton_settlement_collaboration import received, workspace, save, review
from test_carton_supplier_settlement_api import action
from test_carton_transaction_guards_api import BASE, outbound, ledger


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, "TEST_TMP_DIR", tmp_path)


def return_detail(client, movement_id, *, external=False):
    base = "/api/carton-supplier" if external else BASE
    response = client.get(base + f"/returns/{movement_id}", params={"factory_id": "huaxing"})
    assert response.status_code == 200, response.text
    return response.json()


def return_action(client, row, name, *, external=False, **values):
    base = "/api/carton-supplier" if external else BASE
    body = {"factory_id": "huaxing", "request_id": uuid4().hex,
            "expected_revision": row["revision"], "source_fingerprint": row["source_fingerprint"],
            "action": name, "reason": "双方核实原退货和回款凭证", **values}
    response = client.post(base + f"/returns/{row['movement_id']}/actions", json=body)
    assert response.status_code == 200, response.text
    return response.json(), body


def finish_month(client, period):
    login_as(client, "carton_supervisor")
    work = workspace(client, period)
    document = save(client, work)
    assert not document["result"]["issues"], document["result"]
    supplier_login(client)
    signed = review(client, document)
    assert signed.status_code == 200, signed.text
    login_as(client, "carton_supervisor")
    confirmed = action(client, signed.json())
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()


def stock_facts(client):
    return [{key: row[key] for key in ("id", "quantity", "unit_price", "occurred_at", "movement_type")}
            for row in ledger(client)]


def test_cross_month_cash_and_corrected_return_date_preserve_both_ledgers(monkeypatch):
    with make_client(monkeypatch) as client:
        received(client, monkeypatch)
        from app.services import carton_procurement as core
        monkeypatch.setattr(core, "business_now", lambda: datetime(2026, 12, 5, 12))
        order = client.get(BASE + "/orders", params={"factory_id": "huaxing"}).json()["items"][0]
        made = client.post(BASE + "/inventory/movements", json=outbound(order, 2,
            issue_kind="RETURN", return_date="2026-09-28", document_no="RETURN-ROOT-JOURNEY"))
        assert made.status_code == 201, made.text
        movement_id = made.json()["id"]
        original_stock = stock_facts(client)

        supplier_login(client)
        row = return_detail(client, movement_id, external=True)
        assert row["enabled"] and D(row["received_quantity"]) == 0
        row, _ = return_action(client, row, "RECEIVE", external=True, quantity="1",
            receipt_date="2026-09-29", document_no="RETURN-SIGN-1")
        assert D(row["received_quantity"]) == 1 and D(row["remaining_quantity"]) == 1
        assert "PROPOSE_CREDIT" not in row["allowed_actions"]
        row, _ = return_action(client, row, "RECEIVE", external=True, quantity="1",
            receipt_date="2026-09-30", document_no="RETURN-SIGN-2")
        row, _ = return_action(client, row, "PROPOSE_CREDIT", external=True,
            unit_price="3", credit_date="2026-09-30", document_no="RETURN-CREDIT-6")
        login_as(client, "carton_supervisor")
        row = return_detail(client, movement_id)
        row, _ = return_action(client, row, "CONFIRM_CREDIT", target_event_id=row["credit"]["id"])
        september = deepcopy(finish_month(client, "2026-09"))
        assert D(september["result"]["return_amount"]) == 6
        assert D(september["result"]["net_amount"]) == D(september["result"]["inbound_amount"]) - 6

        cash_commands = []
        for day, amount, number in [("2026-10-15", "2", "REFUND-OCT"), ("2026-11-15", "4", "REFUND-NOV")]:
            supplier_login(client)
            row = return_detail(client, movement_id, external=True)
            row, _ = return_action(client, row, "DECLARE_REFUND", external=True,
                kind="CASH", amount=amount, refund_date=day, document_no=number)
            login_as(client, "carton_supervisor")
            row = return_detail(client, movement_id)
            row, command = return_action(client, row, "CONFIRM_REFUND",
                target_event_id=row["refunds"][-1]["id"], confirmation_reference="银行流水-" + number)
            cash_commands.append(command)
            # A later refund must not change already-reconciled credit or cash months.
            old = next(doc for doc in workspace(client, "2026-09")["documents"] if doc["id"] == september["id"])
            assert old["stale"] is False and old["sources"] == september["sources"]
            if day.startswith("2026-10"):
                october = deepcopy(finish_month(client, "2026-10"))
                assert len(october["sources"]) == 1 and october["sources"][0]["kind"] == "RETURN_REFUND"
                assert D(october["result"]["net_amount"]) == 2
            else:
                old_cash = next(doc for doc in workspace(client, "2026-10")["documents"] if doc["id"] == october["id"])
                assert old_cash["stale"] is False and old_cash["sources"] == october["sources"]
        november = deepcopy(finish_month(client, "2026-11"))
        assert D(november["result"]["net_amount"]) == 4
        assert stock_facts(client) == original_stock

        blocked = client.post(BASE + f"/inventory/movements/{movement_id}/reverse",
            json={"factory_id": "huaxing", "reason": "不得以冲销掩盖已签收和实际回款"})
        assert blocked.status_code == 409, blocked.text
        row = return_detail(client, movement_id)
        evidence = row["date_evidence"]
        correction = {"factory_id": "huaxing", "request_id": uuid4().hex,
            "expected_evidence_revision": evidence["revision"], "expected_evidence_fingerprint": evidence["fingerprint"],
            "return_date": "2026-08-31", "reason": "核实原交接单发现退货月份填错"}
        url = BASE + f"/inventory/movements/{movement_id}/return-date/corrections"
        assert client.post(url, json=correction).status_code == 409
        reopened = action(client, september, "reopen", reason="依据原交接单更正实际退货月份")
        assert reopened.status_code == 200, reopened.text
        corrected = client.post(url, json=correction)
        assert corrected.status_code == 200, corrected.text
        assert client.post(url, json=correction).json() == corrected.json()
        row = return_detail(client, movement_id)
        assert row["date_reconfirmation_required"] and D(row["cash_confirmed_amount"]) == 6
        assert stock_facts(client) == original_stock
        for period, document in [("2026-10", october), ("2026-11", november)]:
            frozen = next(doc for doc in workspace(client, period)["documents"] if doc["id"] == document["id"])
            assert frozen["stale"] is False and frozen["sources"] == document["sources"]
        pending = save(client, workspace(client, "2026-08"))
        assert pending["result"]["issues"]  # A date correction never silently reuses old acknowledgements.
        supplier_login(client)
        row = return_detail(client, movement_id, external=True)
        row, _ = return_action(client, row, "RECONFIRM_DATE", external=True)
        login_as(client, "carton_supervisor")
        row = return_detail(client, movement_id)
        row, _ = return_action(client, row, "CONFIRM_DATE")
        assert not row["date_reconfirmation_required"] and D(row["cash_confirmed_amount"]) == 6
        refreshed = workspace(client, "2026-08")
        document = save(client, refreshed, doc=pending)
        assert not document["result"]["issues"], document["result"]
        assert D(document["result"]["return_amount"]) == 6 and D(document["result"]["net_amount"]) == -6
        assert stock_facts(client) == original_stock

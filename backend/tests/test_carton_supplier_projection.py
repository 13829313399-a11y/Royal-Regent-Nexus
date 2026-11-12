"""Compare complete read output to the unchanged single-order calculation path."""
import importlib
import json
import pkgutil
from decimal import Decimal
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("count", [1, 35, 205])
def test_supplier_batch_matches_legacy_and_bounds_queries(count):
    import app.models
    for module in pkgutil.iter_modules(app.models.__path__):
        importlib.import_module("app.models." + module.name)
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import Session
    from app.db import Base
    from app.models.carton_procurement import CartonOrder, CartonOrderLine, CartonPurchaseOrderIssue
    from app.models.carton_supplier_portal import SupplierCommitment
    from app.services import carton_procurement as core, carton_supplier_portal as portal
    from app.services import carton_supplier_changes as changes
    from app.services.carton_supplier_projection import order_page_out
    from app.services.carton_supplier_read_inputs import BATCH_SIZE, order_inputs
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    queries = []
    event.listen(engine, "before_cursor_execute", lambda *args: queries.append(args[2]))
    with Session(engine) as db:
        orders = []
        for i in range(count):
            order = CartonOrder(id=f"O{i}", factory_id="huaxing", order_no=f"CT{i:04}",
                customer_code="TEST", customer_name="Synthetic", supplier_id="S", supplier_name_snapshot="Synthetic",
                contract_no=f"SC-{i}", item_no=f"ITEM-{i}", quantity_basis="EXPLICIT", product_order_quantity=None,
                order_date="2026-11-01", due_date="2026-11-30", status="PENDING_SUPPLIER",
                created_by="test", updated_by="test", created_at="2026-11-01", updated_at="2026-11-01")
            db.add(order); db.flush()
            lines = [CartonOrderLine(id=f"L{i}-{n}", factory_id="huaxing", order_id=order.id, line_no=n + 1,
                customer_code="TEST", contract_no=order.contract_no, item_no=order.item_no, packaging_type="BOX",
                paper_quality="A", specification="30*20*10", required_quantity=Decimal("100.1250") + n,
                unit="PCS", unit_price=Decimal("1.234567"), currency="CNY") for n in range(2)]
            db.add_all(lines); db.flush()
            snapshot = core._purchase_order_pending_change(order, lines, None)[3]
            issue = CartonPurchaseOrderIssue(id=f"I{i}", factory_id="huaxing", order_id=order.id, order_no=order.order_no,
                document_no=f"CT{i:04}-P00", document_type="INITIAL", issue_sequence=0, source_order_revision=order.revision,
                snapshot_json=json.dumps(snapshot, default=str), generated_by="test", generated_at="2026-11-01")
            db.add(issue)
            if i % 3:
                db.add(SupplierCommitment(order_line_id=lines[0].id, factory_id="huaxing", issue_id=issue.id,
                    promised_date="2026-11-29", accepted_by="test", accepted_at="2026-11-02"))
            orders.append(order)
        db.commit()
        for internal in (False, True):
            expected = [portal.order_out(db, order, internal=internal) for order in orders]
            queries.clear()
            actual = order_page_out(db, orders, internal=internal)
            assert actual == expected
            assert len(queries) <= 35 * ((count + 199) // 200) + 20, len(queries)
            assert all(query.lstrip().upper().startswith("SELECT") for query in queries)
        own = order_inputs(db, orders[:35])
        for order in orders[:35]:
            version = portal.latest_issue(db, order)
            before = changes._task(db, SimpleNamespace(), order, version, "REGULAR", internal=True)
            after = changes._task(db, SimpleNamespace(), order, version, "REGULAR", internal=True, projection=own[order.id])
            assert after == before
            # Historical presentation must not mutate the shared current state.
            assert changes._task(db, SimpleNamespace(), order, version, "REGULAR", internal=True, projection=own[order.id]) == before
        other = SimpleNamespace(id="foreign", factory_id="huadeng")
        queries.clear()
        with pytest.raises(ValueError, match="one factory"):
            order_inputs(db, [orders[0], other])
        if count > BATCH_SIZE:
            with pytest.raises(ValueError, match="at most 200 orders"):
                order_inputs(db, orders)
        assert not queries


def test_supplier_projection_keeps_partial_receipt_quantities(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, "TEST_TMP_DIR", tmp_path)
    from test_carton_supplier_portal import setup_portal, accept_all, ship_payload, receive_payload, BASE
    from test_molding_sample_api import make_client, login_as
    with make_client(monkeypatch) as client:
        from app.services import carton_supplier_projection as projection, carton_supplier_portal as portal
        original = projection.order_page_out
        compared = []
        def compare(db, orders, *, internal=False):
            expected = [item for row in orders if (item := portal.order_out(db, row, internal=internal)) is not None]
            actual = original(db, orders, internal=internal)
            assert actual == expected
            compared.append(len(actual))
            return actual
        monkeypatch.setattr(projection, "order_page_out", compare)
        setup_portal(client)
        order = accept_all(client)
        sent = client.post(BASE + "/shipments", json=ship_payload(order))
        assert sent.status_code == 201, sent.text
        assert client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).status_code == 200
        login_as(client, "warehouse_keeper")
        shipment = sent.json()
        received = client.post(BASE + f"/internal/shipments/{shipment['id']}/receive", json=receive_payload(client, shipment))
        assert received.status_code == 200, received.text
        response = client.get(BASE + "/internal/workspace", params={"factory_id": "huaxing"})
        assert response.status_code == 200, response.text
        assert len(compared) >= 3

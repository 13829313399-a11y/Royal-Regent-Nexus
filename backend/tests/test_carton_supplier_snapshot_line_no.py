import json

import pytest
from fastapi import HTTPException

from test_molding_sample_api import make_client
from test_carton_supplier_portal import BASE, setup_portal


@pytest.mark.parametrize("value,expected", [(1, 1), ("1", 1), ("02", 2), (" 12 ", 12)])
def test_legacy_snapshot_numeric_line_number_is_read_compatibly(value, expected):
    from app.services.carton_supplier_portal import _snapshot_line_no
    assert _snapshot_line_no(value, "ORDER-1") == expected


@pytest.mark.parametrize("value", [None, "", "1.5", "one", 0, -1, True, 1.5])
def test_invalid_snapshot_line_number_has_explicit_conflict(value):
    from app.services.carton_supplier_portal import _snapshot_line_no
    with pytest.raises(HTTPException) as error:
        _snapshot_line_no(value, "ORDER-1")
    assert error.value.status_code == 409 and "ORDER-1" in error.value.detail


def test_supplier_workspace_reads_numeric_string_snapshot_without_modifying_evidence(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        from sqlalchemy import select
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonPurchaseOrderIssue
        with SessionLocal() as db:
            issue = db.scalar(select(CartonPurchaseOrderIssue).where(CartonPurchaseOrderIssue.order_id == order["id"]))
            issue_id = issue.id
            data = json.loads(issue.snapshot_json)
            for line in data["lines"]:
                line["line_no"] = str(line["line_no"])
            evidence = json.dumps(data, ensure_ascii=False)
            issue.snapshot_json = evidence
            db.commit()
        result = client.get(BASE + "/workspace", params={"factory_id": "huaxing"})
        assert result.status_code == 200, result.text
        paper = result.json()["orders"][0]["lines"][0]
        assert paper["line_no"] == 1 and paper["child_no"].endswith("/01")
        with SessionLocal() as db:
            issue = db.get(CartonPurchaseOrderIssue, issue_id)
            assert issue.snapshot_json == evidence
            data["lines"][0]["line_no"] = "invalid"
            issue.snapshot_json = json.dumps(data)
            db.commit()
        result = client.get(BASE + "/workspace", params={"factory_id": "huaxing"})
        assert result.status_code == 409, result.text

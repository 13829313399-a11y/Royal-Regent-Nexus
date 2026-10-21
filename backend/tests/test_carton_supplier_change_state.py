"""Audit-backed confirmation projection keeps viewing and supplier decisions separate."""
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_exact_version_factory_kind_and_latest_decision_are_independent_from_reading(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    from app.models.carton_procurement import CartonAuditEvent
    from app.services.carton_supplier_changes import response_state
    engine = create_engine("sqlite://")
    CartonAuditEvent.__table__.create(engine)
    with Session(engine) as db:
        def event(identifier, factory, kind, event_type, status=None):
            detail = {"source_kind": kind}
            if status: detail.update(status=status, reason="具体异议" if status == "DISPUTED" else "")
            db.add(CartonAuditEvent(id=identifier, factory_id=factory, event_type=event_type,
                entity_type="carton_supplier_change", entity_id="ISSUE", actor_user_id="supplier", actor_name="供应商",
                created_at=identifier, detail_json=json.dumps(detail)))
            db.flush()
        event("01", "huaxing", "REGULAR", "SUPPLIER_CHANGE_READ")
        read = response_state(db, "huaxing", "REGULAR", "ISSUE")
        assert read["read"] and read["read_at"] == "01" and read["status"] == "PENDING"
        event("02", "huakang-b", "REGULAR", "SUPPLIER_CHANGE_RESPONSE", "ACCEPTED")
        event("03", "huaxing", "REPLENISHMENT", "SUPPLIER_CHANGE_RESPONSE", "ACCEPTED")
        assert response_state(db, "huaxing", "REGULAR", "ISSUE")["status"] == "PENDING"
        event("04", "huaxing", "REGULAR", "SUPPLIER_CHANGE_RESPONSE", "ACCEPTED")
        event("05", "huaxing", "REGULAR", "SUPPLIER_CHANGE_RESPONSE", "DISPUTED")
        state = response_state(db, "huaxing", "REGULAR", "ISSUE")
        assert state["status"] == "DISPUTED" and state["reason"] == "具体异议" and state["read_at"] == "01"
        assert response_state(db, "huaxing", "REGULAR", "OTHER")["status"] == "PENDING"
        event("06", "huaxing", "REGULAR", "SUPPLIER_CHANGE_RESPONSE", "ACCEPTED")
        assert response_state(db, "huaxing", "REGULAR", "ISSUE")["status"] == "ACCEPTED"
    engine.dispose()

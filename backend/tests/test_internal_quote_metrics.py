from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


@pytest.fixture
def data():
    from app.models import internal_quote as models
    from app.services.internal_quote_metrics import first_output_metrics
    engine = create_engine("sqlite://")
    for cls in (models.InternalQuote, models.InternalQuoteFamily, models.InternalQuoteAlternative, models.InternalQuoteExportFile):
        cls.__table__.create(engine)
    with Session(engine) as db:
        def quote(key, **overrides):
            values = dict(id=key, factory_id="huaxing", workshop_code="test", workshop_name="测试",
                          quote_no=key, product_name=key, customer="华登", qty=1000, version_label=key,
                          status="drafting", created_by="tester", created_by_name="测试",
                          created_at="2026-09-30 00:00:00", updated_at="2026-10-15 00:00:00")
            values.update(overrides)
            row = models.InternalQuote(**values); db.add(row); db.flush(); return row
        def alternative(key, root, **overrides):
            if not db.get(models.InternalQuoteFamily, root):
                db.add(models.InternalQuoteFamily(id=root, factory_id="huaxing")); db.flush()
            row = models.InternalQuoteAlternative(quote_id=key, family_id=root, scenario_id=key,
                scenario_name=key, version_number=1, **overrides)
            db.add(row); db.flush(); return row
        def export(key, quote_id, stamp, **overrides):
            values = dict(id=key, quote_id=quote_id, factory_id="huaxing", sha256=key, content=b"frozen original",
                          release_stage="p4_direct_issued", exported_at=stamp)
            values.update(overrides); db.add(models.InternalQuoteExportFile(**values)); db.flush()
        def parse(value):
            try: return datetime.fromisoformat(value)
            except (ValueError, TypeError): return None
        def metrics():
            return first_output_metrics(db, "huaxing", datetime(2026, 10, 1), datetime(2026, 10, 15), parse)
        yield SimpleNamespace(db=db, models=models, quote=quote, alternative=alternative, export=export, metrics=metrics)
    engine.dispose()


def test_first_output_uses_earliest_formal_file_across_versions_and_output_period(data):
    d = data
    d.quote("root")
    d.quote("window", created_at="2026-10-02 00:00:00")
    d.alternative("root", "root"); d.alternative("window", "root", archived=True)
    d.export("preview", "root", "2026-09-30 01:00:00", release_stage="p4_draft")
    d.export("first", "window", "2026-10-02 00:00:00", status="superseded")
    d.export("retry", "window", "2026-10-08 00:00:00")
    d.export("other", "root", "2026-10-12 00:00:00")
    before = d.db.execute(select(d.models.InternalQuoteExportFile.id, d.models.InternalQuoteExportFile.content)).all()
    result = d.metrics()
    assert result["customer_speed"] == [dict(customer="华登", completed_count=1, median_hours=48,
        average_hours=48, average_days=2, fastest_hours=48, slowest_hours=48)]
    assert result["pending_first_output"]["count"] == 0
    assert d.db.execute(select(d.models.InternalQuoteExportFile.id, d.models.InternalQuoteExportFile.content)).all() == before
    assert not d.db.dirty
    # A later re-export in this period cannot turn last month's first output into a new sample.
    d.export("earlier", "root", "2026-09-30 12:00:00")
    assert d.metrics()["customer_speed"] == []


def test_pending_covers_all_active_products_deduplicates_and_excludes_other_factory_and_archives(data):
    d = data
    d.quote("old", created_at="2026-01-01 00:00:00")
    d.quote("version"); d.alternative("old", "old"); d.alternative("version", "old")
    d.quote("recent", created_at="2026-10-14 00:00:00", batch_position=2)  # second product is counted
    d.quote("boundary", created_at="2026-10-12 00:00:00")
    d.quote("approved", final_release_status="approved", final_reviewed_at="2026-10-01 00:00:00")
    d.quote("closed", status="archived", batch_id="closed-batch")
    d.quote("closed-product", batch_id="closed-batch", batch_position=2)
    d.quote("closed-version"); d.alternative("closed-version", "closed-product")
    d.quote("archived-alternative"); d.alternative("archived-alternative", "archived-alternative", archived=True)
    d.quote("elsewhere", factory_id="huadeng")
    result = d.metrics()
    assert result["pending_first_output"]["count"] == 4
    assert result["pending_first_output"]["over_three_days"] == 2
    assert result["pending_first_output"]["items"][0]["quote_id"] == "old"
    assert result["customer_speed"] == []


def test_missing_output_times_are_not_fabricated_from_updates_or_approval(data):
    d = data
    d.quote("missing", status="exported", final_reviewed_at="2026-10-02 00:00:00")
    d.quote("invalid"); d.export("invalid-export", "invalid", "invalid")
    d.quote("before-created"); d.export("bad", "before-created", "2025-01-01 00:00:00")
    d.quote("known-alternative"); d.alternative("known-alternative", "known-alternative", issued_at="2026-10-03 00:00:00")
    result = d.metrics()
    assert result["first_output_missing_time_count"] == 4
    assert result["customer_speed"] == []
    assert result["pending_first_output"]["count"] == 0


def test_customer_median_resists_outlier_and_pending_list_keeps_total(data):
    d = data
    for index, hours in enumerate((24, 48, 240)):
        d.quote(f"issued-{index}", created_at=f"2026-10-{12-hours//24:02d} 00:00:00")
        d.export(f"file-{index}", f"issued-{index}", "2026-10-12 00:00:00")
    for index in range(12):
        d.quote(f"pending-{index}")
    result = d.metrics()
    assert result["customer_speed"][0]["median_hours"] == 48
    assert result["customer_speed"][0]["average_hours"] == 104
    assert result["customer_speed"][0]["completed_count"] == 3
    assert result["pending_first_output"]["count"] == 12
    assert len(result["pending_first_output"]["items"]) == 10


def test_readiness_uses_saved_current_calculations_not_approval_and_keeps_frozen_history():
    from app.services.internal_quote import quote_readiness, FORMULA_VERSION
    quote = SimpleNamespace(status="drafting", final_release_status="", module_version="v4", reference_snapshot_id="ref")
    def section(code, **overrides):
        values = dict(department=code, department_name=code, is_required=True, status="draft",
                      payload_json='{"lines": [1]}', filled_at="2026-10-15", calculation_status="valid",
                      dependency_status="current", calculation_formula_version=FORMULA_VERSION,
                      calculation_reference_snapshot_id="ref", calculation_json='{"warnings": [{"severity": "warning"}]}')
        values.update(overrides); return SimpleNamespace(**values)
    sections = [section("engineering"), section("assembly", status="approved", calculation_status="blocked"),
                section("sales", dependency_status="stale"), section("painting", filled_at=""),
                section("hair", is_required=False), section("sewing", status="not_applicable")]
    ready = quote_readiness(None, quote, sections)
    assert (ready["ready_sections"], ready["required_sections"]) == (1, 4)
    assert [b["state"] for b in ready["blockers"]] == ["incomplete", "stale", "empty"]
    sections[0].calculation_formula_version = "old"
    assert quote_readiness(None, quote, sections)["ready_sections"] == 0
    quote.status = "exported"
    frozen = quote_readiness(None, quote, sections)
    assert frozen["state"] == "issued" and frozen["blockers"] == []
    assert sections[0].calculation_formula_version == "old"


def test_readiness_projection_never_dirties_persistent_sections(data, monkeypatch):
    from app.services import internal_quote as service
    data.models.InternalQuoteSection.__table__.create(data.db.bind)
    quote = data.quote("projection", module_version="v4", reference_snapshot_id="ref")
    section = data.models.InternalQuoteSection(id="projection-molding", quote_id=quote.id, department="molding",
        department_name="啤机部", status="draft", is_required=True, payload_json='{"injection_lines": [1]}',
        filled_at="2026-10-01", calculation_status="valid", dependency_status="current", updated_at="2026-10-01",
        calculation_formula_version=service.FORMULA_VERSION, calculation_reference_snapshot_id="ref")
    data.db.add(section); data.db.commit()
    monkeypatch.setattr(service, "_can_project_molding_read", lambda *args: True)
    monkeypatch.setattr(service, "molding_projection_pending", lambda *args: True)
    result = service.quote_readiness(data.db, quote, [section])
    assert result["ready_sections"] == 0 and result["blockers"][0]["state"] == "stale"
    assert not data.db.dirty
    assert section.calculation_status == "valid" and section.dependency_status == "current"


def test_archived_formal_output_keeps_frozen_readiness(data):
    from app.services.internal_quote import quote_readiness
    quote = data.quote("archived-output", status="archived")
    data.export("old-output", quote.id, "2026-10-01 00:00:00", status="superseded")
    result = quote_readiness(data.db, quote, [])
    assert result["state"] == "issued" and result["blockers"] == []

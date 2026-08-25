import importlib
import json

import pytest
from fastapi import HTTPException

from test_molding_sample_api import make_client


def _check_result(schema, status: str):
    issue_count = 0 if status == "核对通过" else 1
    comparison_status = "pass" if status == "核对通过" else "changed"
    return schema.CartonMarkDocumentCheckResponse(
        excel_file_name="contract.xlsx",
        pdf_file_name="print.pdf",
        summary=schema.CartonMarkDocumentCheckSummary(
            overall_status=status,
            pass_count=1 if status == "核对通过" else 0,
            changed_count=issue_count,
            missing_count=0,
            unexpected_count=0,
            review_count=0,
        ),
        excel_items=[
            schema.CartonMarkDocumentTextItem(text="ABC", location="箱唛!A1")
        ],
        pdf_items=[
            schema.CartonMarkDocumentTextItem(text="ABC", location="第 1 页 · 第 1 行")
        ],
        comparisons=[
            schema.CartonMarkDocumentComparisonItem(
                status=comparison_status,
                expected="ABC",
                actual="ABC" if comparison_status == "pass" else "ABD",
            )
        ],
        extraction=[
            schema.CartonMarkExtractionStatus(
                source="source_excel", ok=True, engine="test"
            ),
            schema.CartonMarkExtractionStatus(
                source="print_pdf", ok=True, engine="test"
            ),
        ],
    )


def test_library_assigns_versions_stores_all_outcomes_and_rejects_duplicate_hashes(
    monkeypatch,
):
    with make_client(monkeypatch):
        db_module = importlib.import_module("app.db")
        auth = importlib.import_module("app.services.auth")
        schema = importlib.import_module("app.schemas.carton_mark")
        library = importlib.import_module("app.services.carton_mark_library")
        models = importlib.import_module("app.models.carton_mark")
        carton_models = importlib.import_module("app.models.carton_procurement")
        user = auth.AuthContext(
            id="user-carton-test",
            username="carton-test",
            display_name="纸箱测试员",
            roles=("纸箱仓管",),
            role_codes=("carton_warehouse_keeper",),
            permissions=frozenset({"carton_mark:read", "carton_mark:template_upload"}),
            factory_scopes=("huaxing",),
            department_scopes=("pmc-warehouse",),
        )

        with db_module.SessionLocal() as db:
            db.add_all(
                [
                    models.CartonMarkCustomer(
                        id="CMC-SERVICE-A",
                        factory_id="huaxing",
                        name="客人 A",
                        normalized_name="客人 a",
                        revision=1,
                        created_by="seed",
                        created_by_name="测试初始化",
                        created_at="2026-08-19T09:00:00+08:00",
                        updated_by="seed",
                        updated_by_name="测试初始化",
                        updated_at="2026-08-19T09:00:00+08:00",
                    ),
                    models.CartonMarkCustomer(
                        id="CMC-SERVICE-B",
                        factory_id="huaxing",
                        name="另一个名字也不能绕过文档去重",
                        normalized_name="另一个名字也不能绕过文档去重",
                        revision=1,
                        created_by="seed",
                        created_by_name="测试初始化",
                        created_at="2026-08-19T09:00:00+08:00",
                        updated_by="seed",
                        updated_by_name="测试初始化",
                        updated_at="2026-08-19T09:00:00+08:00",
                    ),
                ]
            )
            db.commit()
            first = library.create_carton_mark_template(
                db,
                user,
                factory_id="huaxing",
                customer_name="客人 A",
                po="PO-1",
                item="ITEM-1",
                contract_number="C-1",
                excel_file_name="contract.xlsx",
                excel_bytes=b"excel-v1",
                pdf_file_name="print.pdf",
                pdf_bytes=b"pdf-v1",
                check_result=_check_result(schema, "核对通过"),
            )
            second = library.create_carton_mark_template(
                db,
                user,
                factory_id="huaxing",
                customer_name="客人 A",
                po="PO-1",
                item="ITEM-1",
                contract_number="C-1",
                excel_file_name="contract.xlsx",
                excel_bytes=b"excel-v2",
                pdf_file_name="print.pdf",
                pdf_bytes=b"pdf-v2",
                check_result=_check_result(schema, "发现差异"),
            )
            assert (first.version, first.qc_ready) == (1, True)
            assert (second.version, second.qc_ready) == (2, False)
            assert second.check_result.summary.changed_count == 1

            with pytest.raises(HTTPException) as duplicate:
                library.create_carton_mark_template(
                    db,
                    user,
                    factory_id="huaxing",
                    customer_name="另一个名字也不能绕过文档去重",
                    po="PO-2",
                    item="ITEM-2",
                    contract_number="C-2",
                    excel_file_name="contract.xlsx",
                    excel_bytes=b"excel-v2",
                    pdf_file_name="print.pdf",
                    pdf_bytes=b"pdf-v2",
                    check_result=_check_result(schema, "发现差异"),
                )
            assert duplicate.value.status_code == 409
            assert db.query(models.CartonMarkTemplate).count() == 2
            assert db.query(models.CartonMarkDocument).count() == 4
            assert db.query(carton_models.CartonAuditEvent).filter_by(
                entity_type="carton_mark_template"
            ).count() == 2


def test_manual_release_preserves_automatic_result_and_recheck_revokes_it(monkeypatch):
    with make_client(monkeypatch):
        db_module = importlib.import_module("app.db")
        auth = importlib.import_module("app.services.auth")
        schema = importlib.import_module("app.schemas.carton_mark")
        library = importlib.import_module("app.services.carton_mark_library")
        models = importlib.import_module("app.models.carton_mark")
        carton_models = importlib.import_module("app.models.carton_procurement")
        supervisor = auth.AuthContext(
            id="user-carton-supervisor-test",
            username="carton-supervisor-test",
            display_name="纸箱主管测试员",
            roles=("纸箱主管",),
            role_codes=("position_carton_supervisor",),
            permissions=frozenset(
                {
                    "carton_mark:read",
                    "carton_mark:template_upload",
                    "carton_mark:template_release",
                }
            ),
            factory_scopes=("huaxing",),
            department_scopes=("carton",),
        )

        with db_module.SessionLocal() as db:
            db.add(
                models.CartonMarkCustomer(
                    id="CMC-MANUAL-RELEASE",
                    factory_id="huaxing",
                    name="人工放行客户",
                    normalized_name="人工放行客户",
                    revision=1,
                    created_by="seed",
                    created_by_name="测试初始化",
                    created_at="2026-08-25T09:00:00+08:00",
                    updated_by="seed",
                    updated_by_name="测试初始化",
                    updated_at="2026-08-25T09:00:00+08:00",
                )
            )
            db.commit()
            created = library.create_carton_mark_template(
                db,
                supervisor,
                factory_id="huaxing",
                customer_name="人工放行客户",
                po="PO-MANUAL",
                item="ITEM-MANUAL",
                contract_number="C-MANUAL",
                excel_file_name="contract.xlsx",
                excel_bytes=b"manual-excel",
                pdf_file_name="print.pdf",
                pdf_bytes=b"manual-pdf",
                check_result=_check_result(schema, "发现差异"),
            )
            assert created.qc_ready is False

            released = library.manually_release_carton_mark_template(
                db,
                supervisor,
                factory_id="huaxing",
                template_id=created.id,
                reason="客户已书面确认该处差异可以接受",
            )
            assert released.check_status == "发现差异"
            assert released.check_result.summary.overall_status == "发现差异"
            assert released.qc_ready is True
            assert released.manual_released is True
            assert released.manual_release_source_status == "发现差异"
            assert released.manual_released_by_name == "纸箱主管测试员"

            refreshed = library.update_carton_mark_document_check_result(
                db,
                supervisor,
                factory_id="huaxing",
                template_id=created.id,
                check_result=_check_result(schema, "发现差异"),
            )
            assert refreshed.qc_ready is False
            assert refreshed.manual_released is False
            assert refreshed.manual_release_reason == ""
            events = db.query(carton_models.CartonAuditEvent).filter_by(
                entity_type="carton_mark_template",
                entity_id=created.id,
            ).order_by(carton_models.CartonAuditEvent.created_at.asc()).all()
            assert [event.event_type for event in events] == [
                "CARTON_MARK_TEMPLATE_CREATED",
                "CARTON_MARK_TEMPLATE_MANUALLY_RELEASED",
                "CARTON_MARK_TEMPLATE_RECHECKED",
            ]
            assert json.loads(events[-1].detail_json)["manual_release_revoked"] is True

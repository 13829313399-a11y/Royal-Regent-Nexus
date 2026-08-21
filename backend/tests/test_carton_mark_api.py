import importlib
import sys
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
from pypdf import PdfWriter

from test_molding_sample_api import login_as, make_client


BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _workbook_bytes(value: str = "PO NO: AB-123") -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "箱唛"
    sheet["A1"] = value
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _seed_carton_mark_customer(
    db,
    model,
    *,
    customer_id: str,
    factory_id: str = "huaxing",
    name: str = "客人 A",
):
    db.add(
        model.CartonMarkCustomer(
            id=customer_id,
            factory_id=factory_id,
            name=name,
            normalized_name=" ".join(name.split()).casefold(),
            revision=1,
            created_by="seed",
            created_by_name="测试初始化",
            created_at="2026-08-19T09:00:00+08:00",
            updated_by="seed",
            updated_by_name="测试初始化",
            updated_at="2026-08-19T09:00:00+08:00",
        )
    )


def test_customer_options_read_independent_carton_mark_names_for_the_authorized_factory(monkeypatch):
    with make_client(monkeypatch) as client:
        db_module = importlib.import_module("app.db")
        model = importlib.import_module("app.models.carton_mark")
        internal_quote_model = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            _seed_carton_mark_customer(
                db,
                model,
                customer_id="CMC-HUAXING-ZURU",
                name="ZURU",
            )
            _seed_carton_mark_customer(
                db,
                model,
                customer_id="CMC-HUAXING-DICKIE",
                name="Dickie",
            )
            _seed_carton_mark_customer(
                db,
                model,
                customer_id="CMC-HUAKANG-OTHER",
                factory_id="huakang-c",
                name="外厂客户",
            )
            db.add(
                internal_quote_model.InternalQuoteCustomer(
                    id="IQC-DECOY",
                    factory_id="huaxing",
                    name="内部报价独有客户",
                    normalized_name="内部报价独有客户",
                    revision=1,
                    created_by="sales-user",
                    created_by_name="业务员",
                    created_at="2026-08-14T09:00:00+08:00",
                    updated_by="sales-user",
                    updated_by_name="业务员",
                    updated_at="2026-08-14T09:00:00+08:00",
                )
            )
            db.commit()

        login_as(client, "carton_warehouse")
        response = client.get(
            "/api/carton-mark/customer-options",
            params={"factory_id": "huaxing"},
        )
        assert response.status_code == 200, response.text
        assert response.json() == [
            {"id": "CMC-HUAXING-DICKIE", "name": "Dickie"},
            {"id": "CMC-HUAXING-ZURU", "name": "ZURU"},
        ]

        wrong_factory = client.get(
            "/api/carton-mark/customer-options",
            params={"factory_id": "huakang-c"},
        )
        assert wrong_factory.status_code == 403

        login_as(client, "qc_inspector")
        forbidden = client.get(
            "/api/carton-mark/customer-options",
            params={"factory_id": "huaxing"},
        )
        assert forbidden.status_code == 403


def test_carton_mark_customer_crud_requires_supervisor_permission(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "carton_warehouse")
        forbidden = client.post(
            "/api/carton-mark/customers",
            params={"factory_id": "huaxing"},
            json={"name": "ZURU"},
        )
        assert forbidden.status_code == 403

        login_as(client, "admin")
        created = client.post(
            "/api/carton-mark/customers",
            params={"factory_id": "huaxing"},
            json={"name": "  ZURU  "},
        )
        assert created.status_code == 201, created.text
        customer = created.json()
        assert customer["name"] == "ZURU"
        assert customer["factory_id"] == "huaxing"
        assert customer["revision"] == 1

        duplicate = client.post(
            "/api/carton-mark/customers",
            params={"factory_id": "huaxing"},
            json={"name": "zuru"},
        )
        assert duplicate.status_code == 409

        updated = client.put(
            f"/api/carton-mark/customers/{customer['id']}",
            params={"factory_id": "huaxing"},
            json={"name": "ZURU Toys", "revision": 1},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["revision"] == 2
        assert updated.json()["name"] == "ZURU Toys"

        listed = client.get(
            "/api/carton-mark/customers",
            params={"factory_id": "huaxing"},
        )
        assert listed.status_code == 200
        assert [item["name"] for item in listed.json()] == ["ZURU Toys"]

        deleted = client.delete(
            f"/api/carton-mark/customers/{customer['id']}",
            params={"factory_id": "huaxing", "revision": 2},
        )
        assert deleted.status_code == 204
        assert client.get(
            "/api/carton-mark/customers",
            params={"factory_id": "huaxing"},
        ).json() == []


def test_document_content_check_requires_template_upload_and_returns_stable_schema(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "qc_inspector")
        forbidden = client.post(
            "/api/carton-mark/document-content-check",
            files={
                "excel_contract": ("contract.xlsx", _workbook_bytes()),
                "print_pdf": ("print.pdf", _pdf_bytes(), "application/pdf"),
            },
        )
        assert forbidden.status_code == 403

        login_as(client, "carton_warehouse")
        service = importlib.import_module("app.services.carton_mark")
        schema = importlib.import_module("app.schemas.carton_mark")
        api = importlib.import_module("app.api.carton_mark")
        original_run_in_threadpool = api.run_in_threadpool
        threadpool_calls: list[object] = []

        async def run_in_threadpool_spy(func, *args, **kwargs):
            threadpool_calls.append(func)
            return await original_run_in_threadpool(func, *args, **kwargs)

        monkeypatch.setattr(api, "run_in_threadpool", run_in_threadpool_spy)
        monkeypatch.setattr(
            service,
            "extract_pdf_document_items",
            lambda _content: service.DocumentExtraction(
                items=[schema.CartonMarkDocumentTextItem(
                    text="po no: ab-123",
                    location="第 1 页 · 第 1 行",
                )],
                status=schema.CartonMarkExtractionStatus(
                    source="print_pdf", ok=True, engine="test", raw_text=""
                ),
                reviews=[],
            ),
        )
        response = client.post(
            "/api/carton-mark/document-content-check",
            files={
                "excel_contract": (
                    "contract.xlsx",
                    _workbook_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "print_pdf": ("print.pdf", _pdf_bytes(), "application/pdf"),
            },
        )

        assert response.status_code == 200, response.text
        result = response.json()
        assert result["excel_file_name"] == "contract.xlsx"
        assert result["pdf_file_name"] == "print.pdf"
        assert result["summary"] == {
            "overall_status": "核对通过",
            "pass_count": 1,
            "changed_count": 0,
            "missing_count": 0,
            "unexpected_count": 0,
            "review_count": 0,
        }
        assert result["excel_items"][0] == {
            "text": "PO NO: AB-123",
            "location": "箱唛!A1",
            "field_key": "po",
        }
        assert result["comparisons"][0]["status"] == "pass"
        assert threadpool_calls == [api.build_carton_mark_document_check]


def test_document_content_check_rejects_oversized_and_spoofed_uploads(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "carton_warehouse")
        api = importlib.import_module("app.api.carton_mark")
        monkeypatch.setattr(api, "MAX_DOCUMENT_FILE_BYTES", 16)
        oversized = client.post(
            "/api/carton-mark/document-content-check",
            files={
                "excel_contract": ("contract.xlsx", b"x" * 17),
                "print_pdf": ("print.pdf", _pdf_bytes(), "application/pdf"),
            },
        )
        assert oversized.status_code == 413
        assert oversized.json()["detail"] == "客户 Excel不能超过 20 MB"

        monkeypatch.setattr(api, "MAX_DOCUMENT_FILE_BYTES", 20 * 1024 * 1024)
        spoofed = client.post(
            "/api/carton-mark/document-content-check",
            files={
                "excel_contract": ("contract.xlsx", b"not an xlsx"),
                "print_pdf": ("print.pdf", _pdf_bytes(), "application/pdf"),
            },
        )
        assert spoofed.status_code == 422
        assert "OOXML" in spoofed.json()["detail"]


def test_document_content_check_maps_server_parser_configuration_to_503(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "carton_warehouse")
        api = importlib.import_module("app.api.carton_mark")
        service = importlib.import_module("app.services.carton_mark")

        def raise_configuration_error(**_kwargs):
            raise service.CartonMarkDocumentConfigurationError(
                "服务器未配置 PDF 文字读取组件"
            )

        monkeypatch.setattr(
            api,
            "build_carton_mark_document_check",
            raise_configuration_error,
        )
        response = client.post(
            "/api/carton-mark/document-content-check",
            files={
                "excel_contract": ("contract.xlsx", _workbook_bytes()),
                "print_pdf": ("print.pdf", _pdf_bytes(), "application/pdf"),
            },
        )

        assert response.status_code == 503
        assert response.json()["detail"] == "服务器未配置 PDF 文字读取组件"


def test_persisted_templates_support_qc_read_download_duplicate_and_soft_archive(
    monkeypatch,
):
    with make_client(monkeypatch) as client:
        login_as(client, "carton_warehouse")
        api = importlib.import_module("app.api.carton_mark")
        schema = importlib.import_module("app.schemas.carton_mark")
        db_module = importlib.import_module("app.db")
        customer_model = importlib.import_module("app.models.carton_mark")
        with db_module.SessionLocal() as db:
            _seed_carton_mark_customer(
                db,
                customer_model,
                customer_id="CMC-TEMPLATE-CUSTOMER-A",
                name="客人 A",
            )
            db.commit()

        def checked_result(**kwargs):
            return schema.CartonMarkDocumentCheckResponse(
                excel_file_name=kwargs["excel_file_name"],
                pdf_file_name=kwargs["pdf_file_name"],
                summary=schema.CartonMarkDocumentCheckSummary(
                    overall_status="核对通过",
                    pass_count=1,
                    changed_count=0,
                    missing_count=0,
                    unexpected_count=0,
                    review_count=0,
                ),
                excel_items=[
                    schema.CartonMarkDocumentTextItem(
                        text="PO NO: AB-123",
                        location="箱唛!A1",
                    )
                ],
                pdf_items=[
                    schema.CartonMarkDocumentTextItem(
                        text="PO NO: AB-123",
                        location="第 1 页 · 第 1 行",
                    )
                ],
                comparisons=[
                    schema.CartonMarkDocumentComparisonItem(
                        status="pass",
                        expected="PO NO: AB-123",
                        actual="PO NO: AB-123",
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

        monkeypatch.setattr(api, "build_carton_mark_document_check", checked_result)
        excel_bytes = _workbook_bytes()
        pdf_bytes = _pdf_bytes()
        create_payload = {
            "data": {
                "factory_id": "huaxing",
                "customer_name": "客人 A",
                "po": "PO-100",
                "item": "ITEM-200",
                "contract_number": "C-300",
            },
            "files": {
                "excel_contract": (
                    "customer-contract.xlsx",
                    excel_bytes,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "print_pdf": ("print-ready.pdf", pdf_bytes, "application/pdf"),
            },
        }
        created = client.post("/api/carton-mark/templates", **create_payload)
        assert created.status_code == 201, created.text
        record = created.json()
        template_id = record["id"]
        assert record["version"] == 1
        assert record["check_status"] == "核对通过"
        assert record["qc_ready"] is True
        assert record["check_result"]["summary"]["overall_status"] == "核对通过"
        assert record["updated_at"] == record["created_at"]

        duplicate = client.post("/api/carton-mark/templates", **create_payload)
        assert duplicate.status_code == 409

        login_as(client, "qc_inspector")
        listed = client.get("/api/carton-mark/templates", params={"factory_id": "huaxing"})
        assert listed.status_code == 200, listed.text
        assert [item["id"] for item in listed.json()] == [template_id]
        detail = client.get(
            f"/api/carton-mark/templates/{template_id}",
            params={"factory_id": "huaxing"},
        )
        assert detail.status_code == 200
        assert detail.json()["excel_file_name"] == "customer-contract.xlsx"

        downloaded = client.get(
            f"/api/carton-mark/templates/{template_id}/documents/print_pdf",
            params={"factory_id": "huaxing"},
        )
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content == pdf_bytes
        assert downloaded.headers["content-type"] == "application/pdf"
        assert "print-ready.pdf" in downloaded.headers["content-disposition"]
        assert downloaded.headers["x-content-sha256"]
        assert downloaded.headers["x-content-type-options"] == "nosniff"

        wrong_factory = client.get(
            "/api/carton-mark/templates",
            params={"factory_id": "huakang-c"},
        )
        assert wrong_factory.status_code == 403
        forbidden_archive = client.delete(
            f"/api/carton-mark/templates/{template_id}",
            params={"factory_id": "huaxing"},
        )
        assert forbidden_archive.status_code == 403
        forbidden_recheck = client.post(
            f"/api/carton-mark/templates/{template_id}/recheck",
            params={"factory_id": "huaxing"},
        )
        assert forbidden_recheck.status_code == 403

        login_as(client, "carton_warehouse")
        rechecked = client.post(
            f"/api/carton-mark/templates/{template_id}/recheck",
            params={"factory_id": "huaxing"},
        )
        assert rechecked.status_code == 200, rechecked.text
        assert rechecked.json()["check_status"] == "核对通过"
        assert rechecked.json()["check_result"]["summary"]["unexpected_count"] == 0
        archived = client.delete(
            f"/api/carton-mark/templates/{template_id}",
            params={"factory_id": "huaxing"},
        )
        assert archived.status_code == 204
        assert archived.content == b""
        assert client.get(
            "/api/carton-mark/templates",
            params={"factory_id": "huaxing"},
        ).json() == []

        login_as(client, "qc_inspector")
        archived_download = client.get(
            f"/api/carton-mark/templates/{template_id}/documents/source_excel",
            params={"factory_id": "huaxing"},
        )
        assert archived_download.status_code == 404

        db_module = importlib.import_module("app.db")
        model = importlib.import_module("app.models.carton_procurement")
        with db_module.SessionLocal() as db:
            events = db.query(model.CartonAuditEvent).filter_by(
                entity_type="carton_mark_template",
                entity_id=template_id,
            ).all()
        assert [event.event_type for event in events] == [
            "CARTON_MARK_TEMPLATE_CREATED",
            "CARTON_MARK_TEMPLATE_RECHECKED",
            "CARTON_MARK_TEMPLATE_ARCHIVED",
        ]
        assert "PO NO" not in "".join(event.detail_json for event in events)

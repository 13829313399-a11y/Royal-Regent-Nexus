import hashlib
import importlib
from io import BytesIO

from openpyxl import Workbook, load_workbook

from test_internal_quote_api import ALL_SECTION_CODES, create_payload, login, logout, make_client


def workbook_bytes(rows: list[list[object]], title: str = "报价明细") -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_p3_import_preview_is_non_mutating_and_confirm_is_revision_locked(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_p3_creator", "sales_customer_owner", "sales-business")
        created = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="P3-IMPORT", participating_sections=ALL_SECTION_CODES),
        ).json()
        quote_id = created["id"]
        source = workbook_bytes(
            [
                ["模号", "产品名称", "材质", "克重", "套数", "模价", "机型", "目标数"],
                ["M-300", "主体模", "ABS", 100, 1, 7750, "4A", 5000],
            ]
        )

        forbidden = client.post(
            f"/api/internal-quotes/{quote_id}/imports/mold/preview",
            files={"file": ("模具报价.xlsx", source, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert forbidden.status_code == 403

        logout(client)
        login(client, "iq_p3_engineer", "engineer", "engineering")
        preview_response = client.post(
            f"/api/internal-quotes/{quote_id}/imports/mold/preview",
            files={"file": ("模具报价.xlsx", source, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert preview_response.status_code == 201, preview_response.text
        preview = preview_response.json()
        assert preview["status"] == "previewed"
        assert preview["target_department"] == "engineering"
        assert preview["target_revision"] == 1
        assert preview["row_count"] == 1
        assert preview["diff_summary"] == {
            "target_revision": 1,
            "existing_rows": 0,
            "imported_rows": 1,
            "replace_result_rows": 1,
            "append_result_rows": 1,
        }
        assert preview["source_sha256"] == hashlib.sha256(source).hexdigest()

        detail_before = client.get(f"/api/internal-quotes/{quote_id}").json()
        engineering_before = next(
            item for item in detail_before["sections"] if item["department"] == "engineering"
        )
        assert engineering_before["revision"] == 1
        assert engineering_before["payload"] == {}

        confirm_response = client.post(
            f"/api/internal-quotes/{quote_id}/imports/{preview['batch_id']}/confirm",
            json={"revision": 1, "mode": "replace"},
        )
        assert confirm_response.status_code == 200, confirm_response.text
        confirmed = confirm_response.json()
        assert confirmed["batch"]["status"] == "confirmed"
        assert confirmed["batch"]["confirm_mode"] == "replace"
        assert confirmed["section"]["revision"] == 2
        assert confirmed["section"]["calculation_status"] == "valid"
        assert confirmed["section"]["payload"]["molds"][0]["mold_no"] == "M-300"
        assert confirmed["section"]["calculation"]["totals"]["mold_total_rmb"] == "7750.0000"

        duplicate = client.post(
            f"/api/internal-quotes/{quote_id}/imports/{preview['batch_id']}/confirm",
            json={"revision": 2, "mode": "append"},
        )
        assert duplicate.status_code == 409

        batches = client.get(f"/api/internal-quotes/{quote_id}/imports")
        assert batches.status_code == 200
        assert batches.json()[0]["confirmed_revision"] == 2


def test_hardware_template_preview_maps_only_shared_material_fields_and_replace_keeps_auxiliary(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_p3_hardware_creator", "sales_customer_owner", "sales-business")
        created = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="P3-HARDWARE", participating_sections=ALL_SECTION_CODES),
        ).json()
        quote_id = created["id"]

        logout(client)
        login(client, "iq_p3_hardware_engineer", "engineer", "engineering")
        saved = client.put(
            f"/api/internal-quotes/{quote_id}/sections/engineering",
            json={
                "revision": 1,
                "payload": {
                    "materials": [
                        {"item": "旧五金", "category": "hardware", "quantity": 1, "unit_price_rmb": 1},
                        {"item": "胶水", "category": "auxiliary", "quantity": 2, "unit_price_rmb": 3},
                    ],
                    "molds": [],
                    "amortization_qty": 0,
                    "customer_mold_subsidy_usd": 0,
                },
            },
        )
        assert saved.status_code == 200, saved.text

        source = workbook_bytes(
            [
                ["(五金电子部分)"],
                ["货号", "HW-01"],
                ["产品名称", "测试产品"],
                [],
                [],
                ["零件名称", "配件用处", "规格", "用量", "单位", "单价RMB", "总价", "质料", "表面处理", "供应商", "联系人/电话", "备注", "图片"],
                [],
                ["螺丝", "尿兜", "2.6*8PB", 3, "pcs", 0.0044, 0.0132, "铁", "镀镍", "港正", "张/13800000000", "样板", ""],
                ["合计", "", "", "", "", "", 0.0132],
                ["附：五金尺寸标准表（其它配件及包装物料请参照客签板）"],
            ],
            title="外购",
        )
        preview_response = client.post(
            f"/api/internal-quotes/{quote_id}/imports/hardware/preview",
            files={"file": ("五金1.xlsx", source, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert preview_response.status_code == 201, preview_response.text
        preview = preview_response.json()
        assert preview["header_row"] == 6
        assert preview["row_count"] == 1
        assert preview["diff_summary"]["existing_rows"] == 1
        imported = preview["payload_fragment"]["materials"][0]
        assert imported == {
            "item": "螺丝",
            "category": "hardware",
            "specification": "2.6*8PB",
            "quantity": "3.0000",
            "unit_price_rmb": "0.0044",
            "auxiliary_category": "其他外购",
            "tax_rate_percent": "0.0000",
            "remark": "样板",
            "source_row": 8,
        }
        assert not {"purpose", "unit", "material", "surface_treatment", "supplier", "contact"}.intersection(imported)
        assert any("模板其他列不写入报价字段" in warning for warning in preview["warnings"])

        confirmed = client.post(
            f"/api/internal-quotes/{quote_id}/imports/{preview['batch_id']}/confirm",
            json={"revision": 2, "mode": "replace"},
        )
        assert confirmed.status_code == 200, confirmed.text
        section = confirmed.json()["section"]
        materials = section["payload"]["materials"]
        assert [row["item"] for row in materials] == ["胶水", "螺丝"]
        assert section["calculation"]["totals"]["hardware_hkd"] == "0.0155"
        hardware_line = next(row for row in section["calculation"]["line_breakdown"] if row["category"] == "hardware")
        assert hardware_line["unit_price_hkd"] == "0.0052"
        assert "冻结 RMB→HKD 汇率" in hardware_line["formula"]


def test_p3_attachment_validates_magic_deduplicates_and_downloads(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_p3_attachment_creator", "sales_customer_owner", "sales-business")
        quote = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="P3-ATTACHMENT", participating_sections=ALL_SECTION_CODES),
        ).json()
        quote_id = quote["id"]

        logout(client)
        login(client, "iq_p3_attachment_engineer", "engineer", "engineering")
        image = b"\x89PNG\r\n\x1a\n" + b"internal-quote-image"
        uploaded = client.post(
            f"/api/internal-quotes/{quote_id}/attachments",
            data={"department": "engineering"},
            files={"file": ("模具图.png", image, "image/png")},
        )
        assert uploaded.status_code == 201, uploaded.text
        attachment = uploaded.json()
        assert attachment["sha256"] == hashlib.sha256(image).hexdigest()
        assert attachment["content_type"] == "image/png"

        duplicate = client.post(
            f"/api/internal-quotes/{quote_id}/attachments",
            data={"department": "engineering"},
            files={"file": ("另一名称.png", image, "image/png")},
        )
        assert duplicate.status_code == 409

        invalid = client.post(
            f"/api/internal-quotes/{quote_id}/attachments",
            data={"department": "engineering"},
            files={"file": ("伪造图片.png", b"not-a-png", "image/png")},
        )
        assert invalid.status_code == 400

        listed = client.get(
            f"/api/internal-quotes/{quote_id}/attachments?department=engineering"
        )
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [attachment["id"]]

        downloaded = client.get(
            f"/api/internal-quotes/{quote_id}/attachments/{attachment['id']}/download"
        )
        assert downloaded.status_code == 200
        assert downloaded.content == image
        assert downloaded.headers["x-content-sha256"] == attachment["sha256"]


def test_p3_controlled_export_is_retained_reproducible_and_superseded(monkeypatch):
    with make_client(monkeypatch) as client:
        profile = login(
            client,
            "iq_p3_exporter",
            "sales_customer_supervisor",
            "sales-business",
        )
        assert "internal_quote:export" in profile["permissions"]
        quote = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="P3-EXPORT", participating_sections=ALL_SECTION_CODES),
        ).json()
        quote_id = quote["id"]

        blocked = client.post(f"/api/internal-quotes/{quote_id}/exports")
        assert blocked.status_code == 409
        assert set(blocked.json()["detail"]["incomplete_sections"]) == {
            "sales",
            "engineering",
            "electronic",
            "molding",
            "painting",
            "slush",
            "sewing",
            "assembly",
        }

        db_module = importlib.import_module("app.db")
        quote_models = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            sections = db.query(quote_models.InternalQuoteSection).filter_by(quote_id=quote_id).all()
            for section in sections:
                section.status = "not_applicable"
                section.calculation_status = "not_applicable"
                section.dependency_status = "current"
            db.commit()

        first_response = client.post(f"/api/internal-quotes/{quote_id}/exports")
        assert first_response.status_code == 201, first_response.text
        first = first_response.json()
        assert first["status"] == "current"
        assert first["template_version"] == "internal-quote-p3-v1"
        assert first["release_stage"] == "p3_section_approved"
        assert first["export_manifest"]["p4_final_release_required"] is True

        download = client.get(
            f"/api/internal-quotes/{quote_id}/exports/{first['id']}/download"
        )
        assert download.status_code == 200
        assert download.content.startswith(b"PK")
        assert hashlib.sha256(download.content).hexdigest() == first["sha256"]
        workbook = load_workbook(BytesIO(download.content), data_only=False, read_only=True)
        assert workbook.sheetnames == ["报价明细", "电子明细", "车缝明细", "装配明细", "审批与版本"]
        assert workbook["审批与版本"]["B5"].value == "最终业务放行与客价交接在 P4 实施"
        workbook.close()

        second_response = client.post(f"/api/internal-quotes/{quote_id}/exports")
        assert second_response.status_code == 201
        second = second_response.json()
        history = client.get(f"/api/internal-quotes/{quote_id}/exports")
        assert history.status_code == 200
        by_id = {item["id"]: item for item in history.json()}
        assert by_id[first["id"]]["status"] == "superseded"
        assert by_id[second["id"]]["status"] == "current"

        with db_module.SessionLocal() as db:
            engineering = db.query(quote_models.InternalQuoteSection).filter_by(
                quote_id=quote_id,
                department="engineering",
            ).one()
            engineering.revision += 1
            db.commit()
        refreshed = client.get(f"/api/internal-quotes/{quote_id}/exports").json()
        assert all(item["status"] == "superseded" for item in refreshed)

        logout(client)
        login(client, "iq_p3_export_forbidden", "engineer", "engineering")
        history_only = client.get(f"/api/internal-quotes/{quote_id}/exports")
        assert history_only.status_code == 200
        assert len(history_only.json()) == 2
        forbidden_download = client.get(
            f"/api/internal-quotes/{quote_id}/exports/{second['id']}/download"
        )
        assert forbidden_download.status_code == 403

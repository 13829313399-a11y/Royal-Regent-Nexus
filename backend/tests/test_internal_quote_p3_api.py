import hashlib
import importlib
from io import BytesIO

from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as WorksheetImage
from PIL import Image as PillowImage

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


def workbook_bytes_with_image(rows: list[list[object]], anchor: str, title: str = "报价明细") -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title
    for row in rows:
        sheet.append(row)
    image_bytes = BytesIO()
    PillowImage.new("RGB", (4, 4), color=(16, 118, 110)).save(image_bytes, format="PNG")
    image_bytes.seek(0)
    image = WorksheetImage(image_bytes)
    image.anchor = anchor
    sheet.add_image(image)
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
        source = workbook_bytes_with_image(
            [
                ["模号", "产品名称", "材质", "克重", "套数", "模价", "机型", "目标数"],
                ["M-300", "主体模", "ABS", 100, 1, 7750, "4A", 5000],
            ],
            "U2",
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
        assert preview["payload_fragment"]["molds"][0]["image_reference"] == "模具图片-U2-1.png"
        assert "embedded_images" not in preview

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
        attachment_ids = confirmed["section"]["payload"]["molds"][0]["image_attachment_ids"]
        assert len(attachment_ids) == 1
        assert confirmed["section"]["calculation"]["totals"]["mold_total_rmb"] == "7750.0000"

        attachments = client.get(
            f"/api/internal-quotes/{quote_id}/attachments?department=engineering"
        ).json()
        assert [item["id"] for item in attachments] == attachment_ids
        image_preview = client.get(
            f"/api/internal-quotes/{quote_id}/attachments/{attachment_ids[0]}/preview"
        )
        assert image_preview.status_code == 200
        assert image_preview.headers["content-type"] == "image/png"
        assert image_preview.headers["content-disposition"].startswith("inline;")
        assert image_preview.content.startswith(b"\x89PNG\r\n\x1a\n")

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
            "auxiliary_category": "五金",
            "tax_rate_percent": "13.0000",
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
        assert hardware_line["auxiliary_category"] == "五金"
        assert hardware_line["tax_rate_percent"] == "13.0000"
        assert "冻结 RMB→HKD 汇率" in hardware_line["formula"]


def test_molding_quote_preview_and_confirm_recalculate_from_frozen_reference(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_p3_molding_creator", "sales_customer_owner", "sales-business")
        created = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="P3-MOLDING", participating_sections=ALL_SECTION_CODES),
        ).json()
        quote_id = created["id"]

        logout(client)
        login(client, "iq_p3_molding_clerk", "molding_clerk", "molding")
        source = workbook_bytes(
            [
                ["模具名称", "模号", "材质", "料型", "颜色", "啤净重(g)", "料损耗 3%", "料价 HK$/g", "原料单价 HK$", "机台", "啤价(HK$/啤)", "出模数", "套数", "机型", "目标数", "周期(秒)", "成品金额 HK$"],
                ["主体模", "M-01", "ABS", "750SW", "黑色", 100, 103, 999, 999, "80T", 999, "2", 1, "5A", 5000, 24, 999],
                [],
                ["货名", "日产量/22H", "用料", "预估料重 g", "料价 HK$/lb", "产品料价", "吹工", "披锋", "小计", "利润 ×", "合计 HK$", "出数", "模价 (¥)"],
                ["吹气瓶", "12000", "ABS 750SW", 45, 999, 999, 0.2, 0.1, 999, 1.05, 999, "1出2", 5000],
            ],
            title="啤机报价",
        )
        preview_response = client.post(
            f"/api/internal-quotes/{quote_id}/imports/molding/preview",
            files={"file": ("啤机报价.xlsx", source, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert preview_response.status_code == 201, preview_response.text
        preview = preview_response.json()
        assert preview["target_department"] == "molding"
        assert preview["row_count"] == 2
        assert preview["diff_summary"]["existing_rows"] == 0
        assert any("不直接写入" in warning for warning in preview["warnings"])

        confirmed = client.post(
            f"/api/internal-quotes/{quote_id}/imports/{preview['batch_id']}/confirm",
            json={"revision": 1, "mode": "replace"},
        )
        assert confirmed.status_code == 200, confirmed.text
        section = confirmed.json()["section"]
        assert section["revision"] == 2
        assert section["calculation_status"] == "valid"
        assert section["payload"]["injection_lines"][0]["mold_no"] == "M-01"
        assert section["payload"]["blow_lines"][0]["daily_capacity"] == "12000"
        injection = section["calculation"]["line_breakdown"][0]
        assert injection["material_price_hkd_lb"] == "8.5000"
        assert injection["machine_shift_price_hkd"] == "940.0000"
        assert injection["unit_amount_hkd"] != "999.0000"


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

        saved = client.put(
            f"/api/internal-quotes/{quote_id}/sections/engineering",
            json={
                "revision": 1,
                "payload": {
                    "materials": [
                        {"item": "五金件", "category": "hardware", "quantity": "2", "unit_price_rmb": "8.5"}
                    ],
                    "molds": [],
                    "production_mold_fees": [],
                },
            },
        )
        assert saved.status_code == 200, saved.text
        submitted = client.post(
            f"/api/internal-quotes/{quote_id}/sections/engineering/submit",
            json={"revision": 2},
        )
        assert submitted.status_code == 200, submitted.text
        late_upload = client.post(
            f"/api/internal-quotes/{quote_id}/attachments",
            data={"department": "engineering"},
            files={"file": ("提交后新增.png", image + b"late", "image/png")},
        )
        assert late_upload.status_code == 409
        assert "重开" in late_upload.json()["detail"]


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
        quote_sheet = workbook["报价明细"]
        assert quote_sheet.sheet_state == "visible"
        assert quote_sheet["A8"].value == "内部报价测试产品报价"
        packaging_labels = [quote_sheet.cell(row, 10).value for row in range(1, quote_sheet.max_row + 1)]
        assert "彩盒尺寸 (in)" in packaging_labels
        assert "产品尺寸 (in)" in packaging_labels
        assert [quote_sheet.cell(9, column).value for column in range(3, 14)] == [
            "名称", "料型", "料重(G)", "料价(G)", "机型", "1出几套", "目标数", "啤工", "料金额", None, "报客价",
        ]
        assert quote_sheet["C41"].value == "报客价："
        assert quote_sheet["D41"].value == "=D38*D39/D40"
        assert quote_sheet["D42"].value == 3.5
        assert quote_sheet["D43"].value == '=IF(D42="","",D41-D42)'
        assert quote_sheet["D44"].value == '=IF(OR(D42="",D42=0),"",D43/D42)'
        assert quote_sheet["C46"].value == "旺季价"
        assert all(workbook[name].sheet_state == "veryHidden" for name in workbook.sheetnames[1:])
        electronic_sheet = workbook["电子明细"]
        assert [electronic_sheet.cell(3, column).value for column in range(1, 11)] == [
            "父项", "零件名称", "规格", "用量", "单价RMB", "单价HKD", "金额HKD", "税点%", "备注", "来源",
        ]
        assert [electronic_sheet.cell(5, column).value for column in range(1, 5)] == ["电子成本汇总", "RMB", "HKD", "公式口径"]
        assert [workbook["车缝明细"].cell(3, column).value for column in range(1, 15)] == [
            "产品组", "类型", "#", "布料名称", "部位", "工艺", "裁片数", "用量/码",
            "物料价(RMB)", "价钱(RMB)", "码点", "总价钱(RMB)", "备注", "来源行",
        ]
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

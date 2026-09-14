from decimal import Decimal

from test_internal_quote_api import create_payload, login, make_client
from test_internal_quote_import import workbook_bytes


def test_two_imports_persist_sum_replace_and_delete_independently(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "electronic_groups_sales", "sales_customer_owner", "sales-business")
        created = client.post("/api/internal-quotes", json=create_payload(suffix="ELECTRONIC-GROUPS", participating_sections=["sales", "engineering", "assembly", "electronic"]))
        assert created.status_code == 201, created.text
        base = f"/api/internal-quotes/{created.json()['id']}"

        def section():
            return next(item for item in client.get(base).json()["sections"] if item["department"] == "electronic")

        def preview(name, price):
            content = workbook_bytes([["零件名称", "规格", "用量", "单价RMB", "备注"], [name, "规格", 1, price, ""], ["人工", None, None, 2, ""]])
            response = client.post(f"{base}/imports/electronic/preview", files={"file": (f"{name}.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
            assert response.status_code == 201, response.text
            return response.json()

        def confirm(batch, target, revision=None):
            return client.post(f"{base}/imports/{batch['batch_id']}/confirm", json={"revision": revision or section()["revision"], "electronic_quote_target": target})

        first = preview("主板", 10)
        response = confirm(first, "new")
        assert response.status_code == 200, response.text
        one = section()
        second = preview("副板", 4)
        response = confirm(second, "new")
        assert response.status_code == 200, response.text
        two = section()
        assert len(two["payload"]["quote_groups"]) == 2
        assert two["payload"]["quote_groups"][0] == one["payload"]["quote_groups"][0]
        assert Decimal(two["calculation"]["totals"]["total_hkd"]) > Decimal(one["calculation"]["totals"]["total_hkd"])
        downgrade = client.put(f"{base}/sections/electronic", json={"revision": two["revision"], "payload": {"components": []}})
        assert downgrade.status_code == 409
        assert section()["payload"] == two["payload"]
        update = preview("副板更新", 8)
        stale = confirm(update, two["payload"]["quote_groups"][1]["id"], revision=one["revision"])
        assert stale.status_code == 409
        response = confirm(update, two["payload"]["quote_groups"][1]["id"])
        assert response.status_code == 200, response.text
        replaced = section()
        assert replaced["payload"]["quote_groups"][0] == one["payload"]["quote_groups"][0]
        assert len(replaced["payload"]["quote_groups"]) == 2
        # Removing the superseded second workbook cannot erase its replacement.
        attachments = client.get(f"{base}/attachments", params={"department": "electronic"}).json()
        attachment_id = next(item["id"] for item in attachments if item["file_name"] == "副板.xlsx")
        response = client.delete(f"{base}/attachments/{attachment_id}", params={"revision": replaced["revision"]})
        assert response.status_code == 204, response.text
        assert section()["payload"]["quote_groups"] == replaced["payload"]["quote_groups"]
        # Exercise the real final workbook builder, including sheet visibility.
        import importlib
        import json
        from io import BytesIO
        from openpyxl import load_workbook
        from sqlalchemy import select
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.internal_quote")
        service = importlib.import_module("app.services.internal_quote")
        excel = importlib.import_module("app.services.internal_quote_excel")
        with db_module.SessionLocal() as db:
            quote = db.get(models.InternalQuote, created.json()["id"])
            sections = list(db.scalars(select(models.InternalQuoteSection).where(models.InternalQuoteSection.quote_id == quote.id)))
            reference = db.get(models.InternalQuoteReferenceSet, quote.reference_snapshot_id)
            snapshot = json.loads(reference.snapshot_json)
            context = service._cost_context(db, quote)
            summary = service._rr2_cost_summary(sections, context, snapshot, factory_id=quote.factory_id)
            content = excel.build_internal_quote_workbook(quote, sections, {}, snapshot, summary, context)
        book = load_workbook(BytesIO(content))
        assert [s.title for s in book if s.sheet_state == "visible"] == ["报价明细", "电子明细1", "电子明细2"]
        assert book["电子明细1"]["B4"].value == "主板"
        assert book["电子明细2"]["B4"].value == "副板更新"


def test_history_of_two_quotes_across_21_components_stays_two_quotes(monkeypatch):
    from test_internal_quote_history import create, put_source, catalog, source_ref, parts
    with make_client(monkeypatch) as client:
        login(client, "electronic_groups_history", "sales_customer_owner", "sales-business", "huakang-b")
        names = [f"配件{i}" for i in range(1, 22)]
        original = create(client, "EG-HISTORY-OLD", jp=True, products=[{"product_name": "21配件", "qty": 100, "pricing_components": names}])
        groups = [{"id": f"board{n}", "name": f"报价{n}", "pricing_currency": "RMB", "labor_rmb": 21,
                   "components": [{"item": f"板{n}配件{i}", "quantity": 1, "unit_price_rmb": n,
                                   "pricing_component_id": f"component-{i:02d}"} for i in range(1, 22)]} for n in (1, 2)]
        put_source(original["id"], {"electronic": {"quote_groups": groups}})
        row = next(row for row in catalog(client) if row["quote_id"] == original["id"])
        copied = create(client, "EG-HISTORY-NEW", jp=True, products=[{"product_name": "复制21配件", "qty": 100, "pricing_components": names,
            "history_source": source_ref(row), "component_sources": [source_ref(row, f"component-{i:02d}") for i in range(1, 22)]}])
        result = parts(copied, "electronic")["quote_groups"]
        assert len(result) == 2
        assert [len(group["components"]) for group in result] == [21, 21]
        assert all(abs(Decimal(group["labor_rmb"]) - 21) < Decimal("0.0001") for group in result)

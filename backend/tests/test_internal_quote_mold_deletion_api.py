import importlib
import json

import pytest

from test_internal_quote_api import create_payload, login, make_client
from test_internal_quote_p2_api import ENGINEERING_PAYLOAD, MOLDING_PAYLOAD


@pytest.mark.parametrize("whole_product", [False, True])
def test_deleted_molds_remove_persisted_injection_rows_and_stale_save_rows(monkeypatch, whole_product):
    with make_client(monkeypatch) as client:
        login(client, "mold_delete", "sales_customer_owner", "sales-business")
        response = client.post("/api/internal-quotes", json=create_payload(
            suffix="MOLD-DELETE", participating_sections=["engineering", "molding", "sales", "assembly"],
        ))
        assert response.status_code == 201, response.text
        quote_id = response.json()["id"]
        url = f"/api/internal-quotes/{quote_id}"

        def sections():
            return {row["department"]: row for row in client.get(url).json()["sections"]}

        def save(code, payload):
            result = client.put(f"{url}/sections/{code}", json={
                "revision": sections()[code]["revision"], "payload": payload,
            })
            assert result.status_code == 200, result.text
            return result.json()

        molds = [
            {"item": "主壳", "mold_no": "M01", "cost_rmb": "1000"},
            {"item": "3. Payment", "source_row": 22},
            {"item": "4. Validity", "source_row": 23},
        ]
        save("engineering", {**ENGINEERING_PAYLOAD, "molds": molds})
        projected = sections()["molding"]["payload"]
        projected["injection_lines"][0].update(MOLDING_PAYLOAD["injection_lines"][0])
        manual = {**MOLDING_PAYLOAD["injection_lines"][0], "item": "手工行", "remark": "保留"}
        projected["injection_lines"].append(manual)
        save("molding", projected)
        before = sections()
        stale_payload = before["molding"]["payload"]
        engineering = {**ENGINEERING_PAYLOAD, "molds": molds[:1]}

        if whole_product:
            result = client.put(f"{url}/sections/save-all", json={"sections": [
                {"section_code": "engineering", "revision": before["engineering"]["revision"], "payload": engineering},
                {"section_code": "molding", "revision": before["molding"]["revision"], "payload": stale_payload},
            ]})
            assert result.status_code == 200, result.text
            saved = next(row for row in result.json()["sections"] if row["department"] == "molding")
        else:
            # Consecutive deletions must still clean storage when already stale.
            save("engineering", {**ENGINEERING_PAYLOAD, "molds": molds[:2]})
            revision_after_first = sections()["molding"]["revision"]
            save("engineering", engineering)
            assert sections()["molding"]["revision"] > revision_after_first
            db_module = importlib.import_module("app.db")
            models = importlib.import_module("app.models.internal_quote")
            with db_module.SessionLocal() as db:
                row = db.query(models.InternalQuoteSection).filter_by(quote_id=quote_id, department="molding").one()
                assert len(json.loads(row.payload_json)["injection_lines"]) == 2
            # A caller holding an old draft cannot put deleted sources back.
            saved = save("molding", stale_payload)

        rows = saved["payload"]["injection_lines"]
        assert [row["item"] for row in rows] == ["主壳", "手工行"]
        assert rows[0]["grade"] == "750SW"
        assert rows[1] == manual
        assert saved["calculation_status"] == "valid"
        assert sections()["molding"]["payload"]["injection_lines"] == rows
        save("engineering", {**ENGINEERING_PAYLOAD, "molds": []})
        assert sections()["molding"]["payload"]["injection_lines"] == [manual]

"""Selected replacements must not turn into append or erase sibling suppliers."""
from decimal import Decimal

import pytest

from test_internal_quote_api import make_client, login, create_payload
from test_internal_quote_import import workbook_bytes
from test_internal_quote_meeting_changes import section


@pytest.mark.parametrize("kind,department", [("mold", "engineering"), ("electronic", "electronic")])
def test_replacement_keeps_other_sources_and_replaces_owned_rows(monkeypatch, kind, department):
    with make_client(monkeypatch) as client:
        login(client, "replace-supplier", "admin", "*", "*")
        payload = create_payload(suffix=f"SOURCE-{kind}", participating_sections=["engineering", "assembly", "sales", "electronic"])
        payload["workflow_mode"] = "direct_output"
        created = client.post("/api/internal-quotes", json=payload)
        assert created.status_code == 201, created.text
        root = f"/api/internal-quotes/{created.json()['id']}"

        def import_source(name, price, replacement=None):
            rows = ([["模号", "产品名称", "材质", "克重", "套数", "模价", "机型", "目标数"],
                     [name, name, "ABS", 20, 2, price, "4A", 3000]] if kind == "mold" else
                    [["零件名称", "规格", "用量", "单价RMB"], [name, "供应商规格", 2, price]])
            preview = client.post(root + f"/imports/{kind}/preview",
                data={"replace_attachment_id": replacement} if replacement else {},
                files={"file": (name + ".xlsx", workbook_bytes(rows), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
            assert preview.status_code == 201, preview.text
            request = {"revision": preview.json()["target_revision"], "mode": "append"}
            if kind == "electronic" and not replacement:
                request["electronic_quote_target"] = "new"
            confirmed = client.post(root + f"/imports/{preview.json()['batch_id']}/confirm", json=request)
            assert confirmed.status_code == 200, confirmed.text
            return next(a for a in client.get(root + "/attachments").json() if a["file_name"] == name + ".xlsx")

        old = import_source("旧供应商", 100)
        other = None
        if kind == "mold":
            # Ordinary mold imports replace their whole mapped region. Retain
            # a separately entered mold rather than assuming append is supported.
            current = section(client, root, department)
            current["payload"]["molds"].append({"item": "其他供应商", "mold_no": "手动模具",
                "material": "ABS", "net_weight_g": 20, "quantity": 1, "cost_rmb": 20,
                "machine_code": "4A", "target_output": 3000})
            saved = client.put(root + "/sections/engineering", json={"revision": current["revision"], "payload": current["payload"]})
            assert saved.status_code == 200, saved.text
        else:
            other = import_source("其他供应商", 20)
        before = section(client, root, department)["payload"]
        new = import_source("新供应商", 60, old["id"])
        after = section(client, root, department)["payload"]
        if kind == "mold":
            assert {r["item"] for r in after["molds"]} == {"其他供应商", "新供应商"}
            assert next(r for r in after["molds"] if r["item"] == "其他供应商") == next(r for r in before["molds"] if r["item"] == "其他供应商")
            assert Decimal(after["production_mold_costs"][0]["cost_rmb"]) == 80
        else:
            assert len(after["quote_groups"]) == 2
            before_other = next(g for g in before["quote_groups"] if any(r["item"] == "其他供应商" for r in g["components"]))
            assert next(g for g in after["quote_groups"] if g["id"] == before_other["id"]) == before_other
            assert {r["item"] for g in after["quote_groups"] for r in g["components"]} == {"其他供应商", "新供应商"}
        attachments = client.get(root + "/attachments").json()
        assert {a["id"] for a in attachments} == ({other["id"], new["id"]} if other else {new["id"]})

from test_molding_sample_api import make_client, login_as
from test_carton_history_wide import workbook, row, MINIMAL_HEADERS
from test_carton_history_identity_api import _customer, _orders

BASE="/api/carton-procurement"


def test_eight_column_import_saves_three_demand_lines_without_fabricating_inventory(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client,"admin");_customer(client,"迪奇")
        content=workbook([row(内箱需求数量=200,卡纸需求数量=300)],MINIMAL_HEADERS)
        response=upload(client,content);assert response.status_code==200,response.text
        preview=response.json();assert preview["errors"]==[]
        assert preview["incomplete_count"]==1 and preview["line_count"]==3
        assert _orders(client)==[]
        response=upload(client,content,preview=False,fingerprint=preview["source_fingerprint"])
        assert response.status_code==201,response.text
        order=_orders(client)[0]
        assert order["status"]=="CONFIRMED" and order["product_order_quantity"] is None
        assert {line["packaging_type"]:float(line["required_quantity"]) for line in order["lines"]}=={"内箱":200,"外箱":100,"卡纸":300}
        assert all(line["usage_quantity"] is None and float(line["received_quantity"])==0 for line in order["lines"])
        response=client.post(f"{BASE}/orders/{order['order_no']}/submit-supplier",json={"factory_id":"huaxing","expected_revision":order["revision"]})
        assert response.status_code==422,response.text
        assert client.get(f"{BASE}/inventory/movements",params={"factory_id":"huaxing"}).json()["total"]==0


def upload(client, content, *, preview=True, fingerprint=None, factory="huaxing"):
    return client.post(BASE+("/history-orders/preview" if preview else "/orders/history-imports"),
        params={"factory_id":factory},files={"file":("history.xlsx",content,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"expected_preview_fingerprint":fingerprint} if fingerprint else {})


def test_preview_is_read_only_confirmation_keeps_explicit_papers_and_no_inventory(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client,"admin");_customer(client,"迪奇")
        content=workbook([row(装箱数="0/12",历史订单号="H1"),row(历史订单号="H2",外箱需求数量=35)])
        response=upload(client,content);assert response.status_code==200,response.text
        preview=response.json();assert preview["errors"]==[]
        assert preview["ready_count"]==2
        assert _orders(client)==[]
        assert preview["orders"][0]["product_order_quantity"] is None
        assert preview["orders"][0]["supplier_id"]==preview["supplier_id"]
        assert upload(client,content,preview=False).status_code==409
        response=upload(client,content,preview=False,fingerprint=preview["source_fingerprint"])
        assert response.status_code==201,response.text
        assert response.json()["imported_count"]==2
        orders=_orders(client)
        assert {o["order_no"] for o in orders}=={"H1","H2"}
        assert all(o["quantity_basis"]=="EXPLICIT" for o in orders)
        assert all(o["status"]=="CONFIRMED" and o["product_order_quantity"] is None for o in orders)
        assert all(o["supplier_id"]==preview["supplier_id"] for o in orders)
        assert all(float(o["lines"][0]["received_quantity"])==0 for o in orders)
        movements=client.get(f"{BASE}/inventory/movements",params={"factory_id":"huaxing"})
        assert movements.status_code==200,movements.text
        assert movements.json()["total"]==0
        stale=upload(client,content,preview=False,fingerprint=preview["source_fingerprint"])
        assert stale.status_code==409
        again=upload(client,content).json()
        assert again["skipped_count"]==2


def test_unknown_customer_and_incomplete_material_are_explicit_not_guessed(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client,"admin")
        content=workbook([row(外箱纸质=None,外箱规格=None)])
        response=upload(client,content);assert response.status_code==200,response.text
        assert "不存在" in response.json()["errors"][0]
        assert _orders(client)==[]
        _customer(client,"迪奇")
        preview=upload(client,content).json()
        assert preview["errors"]==[]
        assert preview["incomplete_count"]==1
        assert not preview["orders"][0]["ready"]
        response=upload(client,content,preview=False,fingerprint=preview["source_fingerprint"])
        assert response.status_code==201,response.text
        order=_orders(client)[0]
        assert order["lines"][0]["paper_quality"]==""
        response=client.post(f"{BASE}/orders/{order['order_no']}/submit-supplier",json={"factory_id":"huaxing","expected_revision":order["revision"]})
        assert response.status_code==422,response.text


def test_preview_rejects_file_or_customer_state_change_atomically(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client,"admin");_customer(client,"迪奇")
        content=workbook([row()]);preview=upload(client,content).json()
        altered=workbook([row(外箱需求数量=101)])
        response=upload(client,altered,preview=False,fingerprint=preview["source_fingerprint"])
        assert response.status_code==409,response.text
        _customer(client,"Another")
        response=upload(client,content,preview=False,fingerprint=preview["source_fingerprint"])
        assert response.status_code==409,response.text
        assert _orders(client)==[]


def test_unique_master_lookup_is_visible_and_changed_or_ambiguous_configuration_requires_repreview(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client,"admin");_customer(client,"迪奇")
        content=workbook([row(外箱纸质=None,外箱规格=None)])
        def config(quality):
            response=client.post(f"{BASE}/master-data",json={"factory_id":"huaxing","kind":"CONFIG","code":"92120TQ1-S001-NB",
                "data":{"product_name":"历史产品","lines":[{"packaging_type":"外箱","paper_quality":quality,"specification":"30*20*10",
                    "dimension_unit":"cm","unit":"个","usage_quantity":"12"}]},"reason":"维护历史包装"})
            assert response.status_code==201,response.text
        config("A33")
        preview=upload(client,content).json()
        assert preview["ready_count"]==1
        assert preview["orders"][0]["lines"][0]["paper_quality"]=="A33"
        assert preview["orders"][0]["lines"][0]["usage_quantity"] is None
        assert any("基础资料" in msg for msg in preview["orders"][0]["warnings"])
        config("B33")
        response=upload(client,content,preview=False,fingerprint=preview["source_fingerprint"])
        assert response.status_code==409,response.text
        refreshed=upload(client,content).json()
        assert refreshed["incomplete_count"]==1
        assert refreshed["orders"][0]["lines"][0]["paper_quality"]==""
        assert _orders(client)==[]
        stopped=client.post(f"{BASE}/master-data",json={"factory_id":"huaxing","kind":"CONTRACT","customer_code":"迪奇",
            "code":"4500219760-10","status":"INACTIVE","data":{},"reason":"停用旧合同号"})
        assert stopped.status_code==201,stopped.text
        blocked=upload(client,content).json()
        assert "合同已停用" in blocked["errors"][0]

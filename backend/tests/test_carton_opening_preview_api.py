import json
from uuid import uuid4
from decimal import Decimal

from test_molding_sample_api import make_client,login_as
from test_carton_history_identity_api import _customer
from test_carton_opening_preview import workbook,OPTIONS,HEADERS
from test_carton_procurement_api import _freeze_carton_time,_history_inventory_workbook_bytes

BASE="/api/carton-procurement"
BATCH={**OPTIONS,"snapshot_date":"2026-08-01"}


def setup(client,monkeypatch):
    login_as(client,"admin");_freeze_carton_time(monkeypatch);_customer(client,"迪奇")
    response=client.post(f"{BASE}/inventory/locations",json={"factory_id":"huaxing","warehouse":"A","bin_code":"A1"})
    assert response.status_code==201,response.text
    return response.json()


def upload(client,content,*,preview=True,options=BATCH,token=None):
    data={}
    if options is not None: data["options"]=json.dumps(options)
    if token: data["expected_preview_fingerprint"]=token
    return client.post(f"{BASE}/inventory/history-imports"+("/preview" if preview else ""),params={"factory_id":"huaxing"},
        files={"file":("stock.xlsx",content,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},data=data)


def balances(client): return client.get(f"{BASE}/inventory/positions",params={"factory_id":"huaxing"}).json()


def test_original_stock_preview_confirm_outbound_and_supplier_exclusion_are_idempotent(monkeypatch):
    with make_client(monkeypatch) as client:
        loc=setup(client,monkeypatch)
        data=[["PO","0001","A33+B外箱",30,20,15,"A1",100,2.5],
              ["PO","0001","B3B内箱",15,10,5,"A1",200,None],
              ["PO","0001","H5A平卡",30,20,0,"A1",50,.3],
              ["PO","EMPTY","A33外箱",30,20,15,"A1",0,None]]
        content=workbook(data)
        response=upload(client,content);assert response.status_code==200,response.text
        preview=response.json();assert preview["errors"]==[]
        assert preview["missing_price_count"]==1 and preview["skipped_count"]==1
        assert balances(client)==[]
        assert upload(client,content,preview=False).status_code==409
        response=upload(client,content,preview=False,token=preview["source_fingerprint"])
        assert response.status_code==201,response.text
        assert response.json()["imported_count"]==3
        current=balances(client)
        assert len(current)==3 and all(item["location_id"]==loc["id"] for item in current)
        outer=next(item for item in current if item["packaging_type"]=="外箱")
        assert outer["specification"].endswith("cm") and outer["order_line_id"] is None
        response=client.post(f"{BASE}/inventory/movements",json={"factory_id":"huaxing","request_id":uuid4().hex,
            "reference_movement_id":outer["latest_movement_id"],"location_id":loc["id"],"movement_type":"OUTBOUND",
            "quantity":"40","document_no":"OUT-OPENING","reason":"生产领料"})
        assert response.status_code==201,response.text
        assert Decimal(response.json()["balance"])==60
        supplier=client.get(f"{BASE}/supplier-settlements/workspace",params={"factory_id":"huaxing","period":"2026-08","currency":"CNY"})
        assert supplier.status_code==200,supplier.text
        assert supplier.json()["sources"]==[]
        retry=upload(client,content,preview=False,token=preview["source_fingerprint"])
        assert retry.status_code==201,retry.text
        assert retry.json()["duplicate"] and retry.json()["imported_count"]==0
        reordered=upload(client,workbook(list(reversed(data)))).json()
        assert reordered["errors"]==[] and reordered["skipped_count"]==4
        changed=[*data[0]];changed[7]=101
        conflict=upload(client,workbook([changed])).json()
        assert conflict["errors"] and "不同基准日、数量或价格" in conflict["errors"][0]


def test_options_and_location_changes_invalidate_preview_and_locations_are_never_guessed(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client,monkeypatch)
        content=workbook([["PO","I","A33外箱",30,20,15,"A1",10,2]])
        preview=upload(client,content).json()
        changed=upload(client,content,preview=False,options={**BATCH,"dimension_unit":"in"},token=preview["source_fingerprint"])
        assert changed.status_code==409,changed.text
        client.post(f"{BASE}/inventory/locations",json={"factory_id":"huaxing","warehouse":"A","bin_code":"A2"})
        stale=upload(client,content,preview=False,token=preview["source_fingerprint"])
        assert stale.status_code==409,stale.text
        missing=upload(client,workbook([["PO","I","A33外箱",30,20,15,"NO-SUCH-BIN",10,2]])).json()
        assert "仓位未唯一匹配" in missing["errors"][0]
        assert balances(client)==[]


def test_same_physical_identity_with_conflicting_rows_blocks_entire_import(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client,monkeypatch)
        data=[["PO","I","A33外箱",30,20,15,"A1",10,2],["PO","I","A33外箱",30,20,15,"A1",12,2]]
        preview=upload(client,workbook(data)).json()
        assert "不同数量或单价" in preview["errors"][0]
        response=upload(client,workbook(data),preview=False,token=preview["source_fingerprint"])
        assert response.status_code==422,response.text
        assert balances(client)==[]


def test_old_full_template_same_source_changed_price_no_longer_silently_skips(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client,monkeypatch)
        client.post(f"{BASE}/inventory/locations",json={"factory_id":"huaxing","warehouse":"默认仓","bin_code":"OLD1"})
        row=["OLD-LINE","迪奇","","PO","I","外箱","A33","30*20*15","个",10,2,"CNY","OLD1","2026-08-01","OLD-DOC","",None]
        content=_history_inventory_workbook_bytes([row])
        preview=upload(client,content,options=None);assert preview.status_code==200,preview.text
        assert preview.json()["errors"]==[]
        result=upload(client,content,preview=False,options=None)
        assert result.status_code==201,result.text
        altered=[*row];altered[10]=3
        response=upload(client,_history_inventory_workbook_bytes([altered]),preview=False,options=None)
        assert response.status_code==409,response.text
        assert "不同数量、价格" in response.text


def test_dimensions_units_gate_order_matching_and_opening_never_changes_arrival_progress(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client,monkeypatch)
        for item,dimension_unit in [("IN-ITEM","in"),("CM-ITEM","cm")]:
            order=client.post(f"{BASE}/orders",json={"factory_id":"huaxing","customer_code":"迪奇","customer_name":"迪奇",
                "contract_no":"PO-UNITS","item_no":item,"quantity_basis":"EXPLICIT","product_order_quantity":None,
                "order_date":"2026-08-01","due_date":"2026-08-10","lines":[{"packaging_type":"外箱","paper_quality":"A33",
                    "specification":"30*20*15","dimension_unit":dimension_unit,"unit":"个","required_quantity":100,"usage_quantity":None,"unit_price":2}]}).json()
            assert order.get("order_no"),order
            content=workbook([["PO-UNITS",item,"A33外箱",30,20,15,"A1",10,2]])
            preview=upload(client,content).json()
            assert preview["errors"]==[]
            if dimension_unit=="in": assert preview["rows"][0]["order_line_id"] is None
            else: assert preview["rows"][0]["order_line_id"]==order["lines"][0]["id"]
            response=upload(client,content,preview=False,token=preview["source_fingerprint"])
            assert response.status_code==201,response.text
            refreshed=client.get(f"{BASE}/orders",params={"factory_id":"huaxing"}).json()["items"]
            saved=next(o for o in refreshed if o["order_no"]==order["order_no"])
            assert Decimal(saved["lines"][0]["received_quantity"])==0

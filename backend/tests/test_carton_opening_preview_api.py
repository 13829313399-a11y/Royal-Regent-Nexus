import json
import pytest
from uuid import uuid4
from decimal import Decimal

from test_molding_sample_api import make_client,login_as
from test_carton_history_identity_api import _customer
from test_carton_opening_preview import workbook,OPTIONS,HEADERS
from test_carton_procurement_api import _freeze_carton_time,_history_inventory_workbook_bytes

BASE="/api/carton-procurement"
BATCH={**OPTIONS,"snapshot_date":"2026-08-01"}
ROW_OPTIONS={key:value for key,value in BATCH.items() if key!="snapshot_date"}


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


def test_document_dates_post_into_separate_months_and_carry_forward_without_supplier_purchases(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client,monkeypatch)
        rows=[["PO-1","I1","A33外箱",30,20,15,"A1",10,2,"2026-07-31 10:30"],
              ["PO-2","I2","A33外箱",30,20,15,"A1",20,2,"2026-07-31T23:30:00Z"]]
        content=workbook(rows,HEADERS+["入库时间"])
        preview=upload(client,content,options=ROW_OPTIONS).json()
        assert preview["errors"]==[],preview
        assert [row["occurred_at"] for row in preview["rows"]]==["2026-07-31T10:30:00+08:00","2026-08-01T07:30:00+08:00"]
        posted=upload(client,content,preview=False,options=ROW_OPTIONS,token=preview["source_fingerprint"])
        assert posted.status_code==201,posted.text
        movements=client.get(f"{BASE}/inventory/movements",params={"factory_id":"huaxing"}).json()["items"]
        assert {row["occurred_at"] for row in movements}=={row["occurred_at"] for row in preview["rows"]}
        for period,opening,adjustment,ending in [("2026-07",0,10,10),("2026-08",10,20,30)]:
            res=client.post(f"{BASE}/closings/generate",json={"factory_id":"huaxing","period":period})
            assert res.status_code==200,res.text
            closing=res.json()[0]
            quantity=closing["quantities_by_unit"][0]
            assert [Decimal(quantity[key]) for key in ("opening_quantity","adjustment_quantity","ending_quantity")]==[opening,adjustment,ending]
            assert Decimal(quantity["inbound_quantity"])==0
            assert Decimal(closing["ending_amount"])==ending*2
            supplier=client.get(f"{BASE}/supplier-settlements/workspace",params={"factory_id":"huaxing","period":period,"currency":"CNY"}).json()
            assert supplier["sources"]==[]
        rows[1][-1]="2026-08-01 07:30"
        equivalent=upload(client,workbook(rows,HEADERS+["原入库时间"]),options=ROW_OPTIONS).json()
        assert equivalent["errors"]==[] and equivalent["skipped_count"]==2
        rows[1][-1]="2026-08-01 07:31"
        conflict=upload(client,workbook(rows,HEADERS+["入库时间"]),options=ROW_OPTIONS).json()
        assert "不同入库时间" in conflict["errors"][0]


@pytest.mark.parametrize("bad_time", ["", "8月1日", "2026-08-06", "2026-08-05 23:59", "2026-02-30", "2026-08-01 24:70"])
def test_invalid_or_future_document_date_rejects_entire_batch(monkeypatch,bad_time):
    with make_client(monkeypatch) as client:
        setup(client,monkeypatch)
        rows=[["PO-1","I1","A33外箱",30,20,15,"A1",10,2,"2026-08-01"],
              ["PO-2","I2","A33外箱",30,20,15,"A1",20,2,bad_time]]
        content=workbook(rows,HEADERS+["入库时间"])
        preview=upload(client,content,options=ROW_OPTIONS).json()
        assert preview["errors"] and "第 4 行" in preview["errors"][0]
        post=upload(client,content,preview=False,options=ROW_OPTIONS,token=preview["source_fingerprint"])
        assert post.status_code==422,post.text
        assert balances(client)==[]


def test_same_stock_different_times_within_file_is_not_silently_dropped(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client,monkeypatch)
        rows=[["PO","I","A33外箱",30,20,15,"A1",10,2,"2026-08-01 09:00"],
              ["PO","I","A33外箱",30,20,15,"A1",10,2,"2026-08-01 10:00"]]
        preview=upload(client,workbook(rows,HEADERS+["入库时间"]),options=ROW_OPTIONS).json()
        assert "入库时间" in preview["errors"][0] and balances(client)==[]


def test_row_date_cannot_modify_locked_or_earlier_period_and_whole_batch_rolls_back(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client,monkeypatch)
        content=workbook([["PO","I","A33外箱",30,20,15,"A1",10,2,"2026-07-01"]],HEADERS+["入库时间"])
        preview=upload(client,content,options=ROW_OPTIONS).json()
        assert upload(client,content,preview=False,options=ROW_OPTIONS,token=preview["source_fingerprint"]).status_code==201
        closing=client.post(f"{BASE}/closings/generate",json={"factory_id":"huaxing","period":"2026-07"}).json()[0]
        for status in ("PENDING","CONFIRMED","LOCKED"):
            result=client.post(f"{BASE}/closings/{closing['id']}/status",json={"factory_id":"huaxing","expected_revision":closing["revision"],"status":status})
            assert result.status_code==200,result.text
            closing=result.json()
        for date in ("2026-06-30","2026-07-31"):
            data=workbook([["PO-A","NEW","A33外箱",30,20,15,"A1",10,2,"2026-08-01"],
                           ["PO-B","OLD","A33外箱",30,20,15,"A1",10,2,date]],HEADERS+["入库时间"])
            checked=upload(client,data,options=ROW_OPTIONS).json()
            assert "锁账" in checked["errors"][0]
            rejected=upload(client,data,preview=False,options=ROW_OPTIONS,token=checked["source_fingerprint"])
            assert rejected.status_code==422 and len(balances(client))==1


def test_unassigned_opening_stock_can_issue_and_close_without_customer_master(monkeypatch):
    with make_client(monkeypatch) as client:
        loc=setup(client,monkeypatch)
        content=workbook([["PO-UNKNOWN","I","A535B外箱",30,20,15,"A1",10,2,"2026-07-20 09:30","A"]],HEADERS+["原入库时间","仓库"])
        options={**BATCH,"customer_name":""}
        preview=upload(client,content,options=options).json()
        assert preview["errors"]==[],preview
        assert preview["rows"][0]["customer_name"]=="未指定客户"
        assert preview["rows"][0]["original_inbound_at"]=="2026-07-20T09:30:00+08:00"
        posted=upload(client,content,preview=False,options=options,token=preview["source_fingerprint"])
        assert posted.status_code==201,posted.text
        audit=client.get(f"{BASE}/audit-events",params={"factory_id":"huaxing"})
        assert audit.status_code==200 and "2026-07-20T09:30:00+08:00" in audit.text
        movements=client.get(f"{BASE}/inventory/movements",params={"factory_id":"huaxing"})
        assert "2026-07-20T09:30:00" in movements.text
        current=balances(client)[0]
        assert current["latest_inbound_at"]=="2026-07-20T09:30:00+08:00"
        assert current["order_line_id"] is None
        assert current["customer_code"]=="__OPENING_UNASSIGNED__"
        attempted_return=client.post(f"{BASE}/inventory/movements",json={"factory_id":"huaxing","request_id":uuid4().hex,
            "reference_movement_id":current["latest_movement_id"],"location_id":loc["id"],"movement_type":"OUTBOUND",
            "quantity":"3","document_no":"RETURN-UNASSIGNED","reason":"供应商退货","issue_kind":"RETURN"})
        assert attempted_return.status_code==409 and "无法确定供应商" in attempted_return.text
        assert Decimal(balances(client)[0]["balance"])==10
        outbound=client.post(f"{BASE}/inventory/movements",json={"factory_id":"huaxing","request_id":uuid4().hex,
            "reference_movement_id":current["latest_movement_id"],"location_id":loc["id"],"movement_type":"OUTBOUND",
            "quantity":"3","document_no":"OUT-UNASSIGNED","reason":"生产领料"})
        assert outbound.status_code==201,outbound.text
        assert Decimal(balances(client)[0]["balance"])==7
        assert balances(client)[0]["latest_inbound_at"]=="2026-07-20T09:30:00+08:00"
        retry=upload(client,content,preview=False,options=options,token=preview["source_fingerprint"])
        assert retry.status_code==201 and retry.json()["imported_count"]==0,retry.text
        closing=client.post(f"{BASE}/closings/generate",json={"factory_id":"huaxing","period":"2026-08"})
        assert closing.status_code in (200,201),closing.text
        assert "未指定客户" in closing.text
        supplier=client.get(f"{BASE}/supplier-settlements/workspace",params={"factory_id":"huaxing","period":"2026-08","currency":"CNY"})
        assert supplier.json()["sources"]==[]


def test_multi_customer_warehouse_rows_override_optional_defaults(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client,monkeypatch)
        _customer(client,"360")
        other=client.post(f"{BASE}/inventory/locations",json={"factory_id":"huaxing","warehouse":"B","bin_code":"A1"})
        assert other.status_code==201,other.text
        rows=[["PO-A","I","A33外箱",30,20,15,"A1",10,2,"迪奇","A"],
              ["PO-B","I","A33外箱",30,20,15,"A1",20,2,"360","B"]]
        content=workbook(rows,HEADERS+["客户","仓库"])
        options={**BATCH,"customer_name":"","warehouse":""}
        preview=upload(client,content,options=options).json()
        assert preview["errors"]==[],preview
        assert {r["customer_name"] for r in preview["rows"]}=={"迪奇","360"}
        # Defaults never override explicit row identities.
        assert upload(client,content).json()["errors"]==[]
        posted=upload(client,content,preview=False,options=options,token=preview["source_fingerprint"])
        assert posted.status_code==201,posted.text
        assert posted.json()["imported_count"]==2
        assert {r["customer_name"] for r in balances(client)}=={"迪奇","360"}
        assert len({r["location_id"] for r in balances(client)})==2
        ambiguous=workbook([["PO-X","I","A33外箱",30,20,15,"A1",10,2,"迪奇",""]],HEADERS+["客户","仓库"])
        assert "未唯一匹配" in upload(client,ambiguous,options=options).json()["errors"][0]
        missing=workbook([["PO-X","I","A33外箱",30,20,15,"A1",10,2,"","A"]],HEADERS+["客户","仓库"])
        assert upload(client,missing,options=options).json()["rows"][0]["customer_name"] == "未指定客户"


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
        assert conflict["errors"] and "不同入库时间、数量或价格" in conflict["errors"][0]


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
        message=preview["errors"][0]
        assert '第 4 行' in message and '与“期初库存导入”第 3 行' in message
        assert 'A33外箱' in message and '数量：前行 10，本行 12' in message
        assert '不同纸质可分行导入' in message
        response=upload(client,workbook(data),preview=False,token=preview["source_fingerprint"])
        assert response.status_code==422,response.text
        assert balances(client)==[]


def test_same_contract_item_different_paper_quality_keeps_quantity_and_price_separate(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client,monkeypatch)
        data=[["PO","I","A33外箱",30,20,15,"A1",10,2],
              ["PO","I","A535B外箱",30,20,15,"A1",12,3]]
        content=workbook(data)
        preview=upload(client,content).json()
        assert preview["errors"]==[] and preview["skipped_count"]==0,preview
        assert {r["paper_quality"] for r in preview["rows"]}=={"A33","A535B"}
        assert len({r["source_line_id"] for r in preview["rows"]})==2
        posted=upload(client,content,preview=False,token=preview["source_fingerprint"])
        assert posted.status_code==201 and posted.json()["imported_count"]==2,posted.text
        current={r["paper_quality"]:r for r in balances(client)}
        assert set(current)=={"A33","A535B"}
        for quality,quantity,price in [("A33",10,2),("A535B",12,3)]:
            assert Decimal(current[quality]["balance"])==quantity
            assert Decimal(current[quality]["cost_amount"])==quantity*price
            assert Decimal(current[quality]["cost_unit_price"])==price
        movements=client.get(f"{BASE}/inventory/movements",params={"factory_id":"huaxing"}).json()["items"]
        assert {r["paper_quality"]:Decimal(r["unit_price"]) for r in movements}=={"A33":Decimal(2),"A535B":Decimal(3)}
        retry=upload(client,workbook(list(reversed(data)))).json()
        assert retry["errors"]==[] and retry["skipped_count"]==2,retry
        repeated=upload(client,content,preview=False,token=preview["source_fingerprint"])
        assert repeated.status_code==201 and repeated.json()["imported_count"]==0
        assert len(balances(client))==2


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

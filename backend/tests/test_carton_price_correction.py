"""Owner API contracts: preserved evidence, guarded old endpoint and safe supplier view."""
from uuid import uuid4
from decimal import Decimal as D
import pytest
from test_molding_sample_api import make_client,login_as
from test_carton_settlement_collaboration import received
from test_carton_supplier_portal import supplier_login

BASE="/api/carton-procurement/price-corrections"
SUP="/api/carton-supplier/price-corrections"


@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api,"TEST_TMP_DIR",tmp_path)


def get(client,identifier,external=False):
    response=client.get((SUP if external else BASE)+"/"+identifier,params={"factory_id":"huaxing"})
    assert response.status_code==200,response.text
    return response.json()


def command(client,row,name,external=False,**values):
    data=dict(factory_id="huaxing",request_id=uuid4().hex,expected_revision=row["revision"],source_fingerprint=row["source_fingerprint"],action=name,reason="仓管核对供应商原始更正凭证")
    data.update(values)
    response=client.post((SUP if external else BASE)+"/"+row["receipt_line_id"]+"/actions",json=data)
    assert response.status_code==200,response.text
    return response.json(),data


def test_effective_price_atomicity_old_route_fence_and_supplier_recursive_privacy(monkeypatch):
    with make_client(monkeypatch) as client:
        received(client,monkeypatch)
        login_as(client,"warehouse_keeper")
        work=client.get(BASE+"/workspace",params={"factory_id":"huaxing","status":"ALL"})
        assert work.status_code==200,work.text
        row=work.json()["items"][0]; identifier=row["receipt_line_id"]
        assert row["raw_unit_price"]=="2.000000" and D(row["current_cost_unit_price"])==2
        old_review=next(item for item in client.get("/api/carton-price-reviews/internal",params={"factory_id":"huaxing"}).json()["items"] if item["receipt_line_id"]==identifier)
        cleared=client.post("/api/carton-price-reviews/internal/"+old_review["id"]+"/propose",json=dict(factory_id="huaxing",request_id=uuid4().hex,
            expected_revision=old_review["revision"],proposed_unit_price=None,reason="旧入口不应清空已确认有效应付价"))
        assert cleared.status_code==409,cleared.text
        proposed,_=command(client,row,"PROPOSE",proposed_unit_price="3",document_no="PRICE-OWNER",document_date="2026-09-30")
        supplier_login(client)
        signed,_=command(client,get(client,identifier,True),"SUPPLIER_CONFIRM",True)
        assert "current_cost_unit_price" not in signed and "raw_unit_price" not in signed
        login_as(client,"carton_supervisor")
        row=get(client,identifier)
        preview=client.post(BASE+"/"+identifier+"/preview",json=dict(factory_id="huaxing",expected_revision=row["revision"],source_fingerprint=row["source_fingerprint"]))
        assert preview.status_code==200,preview.text
        impact=preview.json()["impact"]
        assert impact["can_apply"] and D(impact["summary"]["bridge_difference"])==0
        assert D(impact["summary"]["source_cost_difference"])==D(row["quantity"])
        applied,request=command(client,row,"FINAL_CONFIRM",impact_fingerprint=impact["impact_fingerprint"],reason="主管内部成本核对专用理由不得外发")
        assert applied["status"]=="APPLIED" and D(applied["current_unit_price"])==3 and D(applied["current_cost_unit_price"])==3
        assert applied["raw_unit_price"]=="2.000000"
        replay=client.post(BASE+"/"+identifier+"/actions",json=request)
        assert replay.status_code==200 and replay.json()["replayed"]
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonReceiptLine,CartonInventoryMovement
        from app.models.carton_price_review import CartonPriceReview
        from sqlalchemy import select
        with SessionLocal() as db:
            paper=db.get(CartonReceiptLine,identifier); movement=db.get(CartonInventoryMovement,row["movement_id"])
            assert paper.unit_price==movement.unit_price==2
            review=db.scalar(select(CartonPriceReview).where(CartonPriceReview.receipt_line_id==identifier))
            review_id,revision=review.id,review.revision
        login_as(client,"warehouse_keeper")
        old=client.post("/api/carton-price-reviews/internal/"+review_id+"/propose",json=dict(factory_id="huaxing",request_id=uuid4().hex,expected_revision=revision,proposed_unit_price="3",reason="同价重走旧入口不应覆盖生效版本"))
        assert old.status_code==409,old.text
        supplier_login(client)
        visible=get(client,identifier,True)
        serialized=str(visible)
        assert "主管内部成本核对专用理由" not in serialized
        def safe(value):
            if isinstance(value,dict):
                assert not ({"applied_by","impact","current_cost_unit_price","raw_unit_price","impact_fingerprint","old_cost_amount","new_cost_amount","cost_difference"}&set(value))
                for item in value.values(): safe(item)
            elif isinstance(value,list):
                for item in value:safe(item)
        safe(visible)
        old_supplier=client.get("/api/carton-price-reviews/supplier",params={"factory_id":"huaxing"})
        assert old_supplier.status_code==200 and "主管内部成本核对专用理由" not in old_supplier.text


def test_other_currency_bill_does_not_block_exact_source_price_correction(monkeypatch):
    with make_client(monkeypatch) as client:
        received(client,monkeypatch)
        from app.db import SessionLocal
        from app.models.carton_supplier_settlement import CartonSupplierSettlement
        from app.services import carton_procurement as core
        from app.services import carton_price_correction as service
        row=client.get(BASE+"/workspace",params={"factory_id":"huaxing","status":"ALL"}).json()["items"][0]
        with SessionLocal() as db:
            db.add(CartonSupplierSettlement(id="CSS-OTHER-CURRENCY",factory_id="huaxing",supplier_id=row["supplier_id"],period="2026-09",currency="HKD",version=1,revision=1,status="CONFIRMED",
                source_fingerprint="f"*64,sources_json="[]",statement_json='{"statement_no":"HKD-ONLY"}',result_json='{"net_amount":"12"}',created_at=core.now_text(),updated_at=core.now_text(),created_by="synthetic",confirmed_at=core.now_text(),confirmed_by="synthetic",reopen_reason=""))
            db.commit()
            current=service.source(db,"huaxing",row["receipt_line_id"])
            result=service.impact(db,current,D(3))
        assert result["can_apply"],result["blockers"]
        assert not any(item["code"]=="CONFIRMED_SUPPLIER_MONTH" for item in result["blockers"])
        with SessionLocal() as db:
            current=service.source(db,"huaxing",row["receipt_line_id"])
            current["receipt"].acceptance_date=None
            db.commit()
        undated=get(client,row["receipt_line_id"])
        assert not undated["can_propose"] and any("实际验收日期待核实" in item["message"] for item in undated["blockers"])
        response=client.post(BASE+"/"+row["receipt_line_id"]+"/actions",json=dict(factory_id="huaxing",request_id=uuid4().hex,expected_revision=undated["revision"],
            source_fingerprint=undated["source_fingerprint"],action="PROPOSE",reason="未知日期不能猜月份改价",proposed_unit_price="3",document_no="UNDATED-BLOCK",document_date="2026-09-30"))
        assert response.status_code==409,response.text


def test_legacy_special_gift_without_price_review_cannot_become_chargeable(monkeypatch):
    from test_carton_special_requests import setup,create_body,ok,ship,receive,SUP as SPECIAL_SUP
    with make_client(monkeypatch) as client:
        place=setup(client)
        supplier_login(client)
        gift=ok(client.post(SPECIAL_SUP+"/gifts",json=create_body("SUPPLIER_GIFT")),201)
        gift=ship(client,gift)
        receive(client,gift,place,"10")
        from app.db import SessionLocal
        from app.models.carton_special_requests import SpecialReceiptLink
        from app.models.carton_procurement import CartonReceiptLine,CartonInventoryMovement
        from app.models.carton_price_review import CartonPriceReview
        from sqlalchemy import select,delete
        from app.services import carton_procurement as core
        from types import SimpleNamespace
        with SessionLocal() as db:
            line=db.scalar(select(CartonReceiptLine).join(SpecialReceiptLink,SpecialReceiptLink.receipt_line_id==CartonReceiptLine.id))
            identifier=line.id
            movement=db.scalar(select(CartonInventoryMovement).where(CartonInventoryMovement.source_type=="RECEIPT",CartonInventoryMovement.source_line_id==identifier))
            db.execute(delete(CartonPriceReview).where(CartonPriceReview.receipt_line_id==identifier))
            # Old erroneous known-price evidence must not convert the explicit gift contract.
            core._audit(db,SimpleNamespace(id="synthetic",display_name="历史隔离凭证"),"huaxing","INVENTORY_PRICE_CONFIRMED","carton_inventory_movement",movement.id,{"unit_price":"2","reason":"旧已知价隔离夹具"})
            db.commit()
        login_as(client,"warehouse_keeper")
        row=get(client,identifier)
        assert not row["can_propose"] and any("赠送" in item["message"] for item in row["blockers"])
        response=client.post(BASE+"/"+identifier+"/actions",json=dict(factory_id="huaxing",request_id=uuid4().hex,expected_revision=row["revision"],
            source_fingerprint=row["source_fingerprint"],action="PROPOSE",reason="不能将原免费赠送变采购",proposed_unit_price="3",document_no="INVALID-GIFT-CHARGE",document_date="2026-10-18"))
        assert response.status_code==409,response.text


def test_unrelated_correction_does_not_reclassify_legacy_ambiguous_b_cost_pool():
    from types import SimpleNamespace as S
    import json
    from app.services.carton_inventory_valuation import value_movements,cost_key
    def row(identifier,line,quantity,price,day):
        return S(id=identifier,factory_id="huaxing",customer_code="C",order_line_id=line,contract_no="SC",item_no="I",packaging_type="外箱",paper_quality="A",specification="1*2",unit="个",currency="CNY",
            source_type="RECEIPT",source_id="R-"+identifier,source_line_id="L-"+identifier,quantity=D(quantity),unit_price=D(price),occurred_at=f"2026-10-0{day}T12:00:00+08:00",reversal_of_movement_id=None)
    a,b,legacy=row("A","A",10,2,1),row("B","B",10,4,2),row("B-FREE","B",2,4,3)
    def event(identifier,kind,sequence,data): return S(id="E-"+str(sequence),entity_id=identifier,event_type=kind,sequence=sequence,detail_json=json.dumps(data))
    link=event("L-B-FREE","RECEIPT_REPLENISHMENT_LINKED",3,{"responsibility":"SUPPLIER","replenishment_issue_id":"MISSING-LEGACY-ISSUE"})
    original=value_movements([a,b,legacy],[link])
    unrelated=value_movements([a,b,legacy],[link,event("A","INVENTORY_PRICE_CORRECTED",4,{"unit_price":"3"})])
    assert not unrelated.errors and unrelated.balances[cost_key(b)].amount==original.balances[cost_key(b)].amount==48
    affected=value_movements([a,b,legacy],[link,event("B","INVENTORY_PRICE_CORRECTED",4,{"unit_price":"5"})])
    assert any("免费补货缺少" in message for _,message in affected.errors)

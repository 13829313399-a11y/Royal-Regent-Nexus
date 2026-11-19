from copy import deepcopy
from fastapi import HTTPException
import pytest
from test_customer_order_ledger import engine, db, preview, ingest
from app.services import customer_order_ledger as s
from app.schemas.customer_order_ledger import RestoreIn


def payload():
    v=preview(factory='huadeng');v['customer_code']='jakks';r=v['rows'][0]
    r.update(contract_no='809714', reference_no='66973-1', product_no='13083J-V1',
             confirmation_no='66973',source_line_no='1')
    return v


def test_cancel_notice_is_separate_not_reconcilable_or_restorable(db):
    v=payload();original=ingest(db,v);cancel=deepcopy(v);cancel['rows'][0].update(document_kind='cancellation',order_type='取消单')
    notice=ingest(db,cancel)
    assert notice.id != original.id and notice.status=='cancelled' and original.status=='active'
    assert ingest(db,cancel).id==notice.id
    assert s.line_out(db,notice)['remaining_quantity']=='0'
    with pytest.raises(HTTPException) as e:
        s.import_preview(db,preview=cancel,files=[],source_kind='formal',actor='a',reason='测试关联行为',controls={},reconcile_line=original,expected_revision=original.revision)
    assert '不能' in str(e.value.detail)
    with pytest.raises(HTTPException) as e:
        s.restore(db,notice,RestoreIn(expected_revision=notice.revision,reason='测试恢复行为',confirmed=True,notify_recipients=False),'a')
    assert '归档凭证' in str(e.value.detail)
    assert original.version==1 and notice.status=='cancelled'


def test_new_source_metadata_does_not_duplicate_proven_suffixed_order(db):
    v=payload();old=deepcopy(v);old['rows'][0].pop('confirmation_no');old['rows'][0].pop('source_line_no')
    existing=ingest(db,old);assert ingest(db,v).id==existing.id


def test_sup_formal_preserves_line_quantity_versions_and_retry(db):
    v=payload();v['rows'][0].update(order_type='补充合同',po_no='236753',requested_ship_date='2026-12-11',unit_price_usd='',amount_usd='')
    v['rows'][0]['packaging']='原人工包装'
    original=ingest(db,v);formal=deepcopy(v);formal['rows'][0].update(order_type='正单',unit_price_usd='2',amount_usd='200',packaging='')
    line=ingest(db,formal)
    assert line.id==original.id and line.version==2 and line.data['unit_price_usd']=='2'
    assert ingest(db,formal).id==line.id and ingest(db,v).id==line.id
    assert line.version==2
    from sqlalchemy import select,func
    assert db.scalar(select(func.count()).select_from(s.Line))==1


def test_sup_formal_changes_do_not_overwrite_shipment_or_distinct_batch(db):
    v=payload();v['rows'][0].update(order_type='补充合同',po_no='236753',requested_ship_date='2026-12-11')
    original=ingest(db,v);original.shipped_quantity=1;db.flush()
    formal=deepcopy(v);formal['rows'][0].update(order_type='正单',unit_price_usd='2')
    assert ingest(db,formal).id!=original.id
    assert original.data['order_type']=='补充合同' and original.shipped_quantity==1


@pytest.mark.parametrize('state', ['cancelled','shipped'])
def test_original_sup_and_formal_retry_after_lifecycle_changes(db,state):
    v=payload();v['rows'][0].update(order_type='补充合同',po_no='236753',requested_ship_date='2026-12-11',packaging='人工包装')
    original=ingest(db,v);formal=deepcopy(v);formal['rows'][0].update(order_type='正单',packaging='',unit_price_usd='2')
    line=ingest(db,formal);assert line.id==original.id
    if state=='cancelled': line.status='cancelled'
    else: line.shipped_quantity=line.quantity
    db.flush()
    assert ingest(db,v).id==line.id and ingest(db,formal).id==line.id
    from sqlalchemy import select,func
    assert db.scalar(select(func.count()).select_from(s.Line))==1

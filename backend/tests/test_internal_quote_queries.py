"""Strict quote readers match native projections without recording or repairing."""
import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select
from test_assistant_api import env
from test_work_center_api import actor

F='huakang-a'
STAMP='2026-10-23T10:00:00+08:00'


def setup(env):
    from app.models.internal_quote import InternalQuote, InternalQuoteFamily, InternalQuoteAlternative
    from app.services import internal_quote as native, auth
    from app.core.config import settings
    client, dbm, calls, patch=env
    patch.setattr(settings,'authz_mode','enforce')
    user=actor('quote-reader',factory=F,department='sales-business',permissions=('internal_quote:read','internal_quote:summary_read','internal_quote:reference_manage'))
    client.app.dependency_overrides[auth.get_current_user]=lambda:user
    with dbm.SessionLocal() as db:
        for i in range(12):
            quote=InternalQuote(id=f'Q{i}',factory_id=F,workshop_code='A',workshop_name='合成车间',quote_no=f'QUO-{i}',
                product_name=f'产品{i}',customer='客户一' if i%2==0 else '客户二',qty=100+i,version_label='V1',status='drafting',
                module_version='v4',batch_id=f'Q{i}',batch_quote_no=f'QUO-{i}',batch_size=2 if i==0 else 1,
                created_by=user.id,created_by_name='合成创建人',business_owner_name='合成负责人',created_at=STAMP,updated_at=STAMP)
            db.add(quote);db.flush()
            if i==0:
                native._create_reference_set(db,quote,user,source_type='synthetic_test')
                native._create_sections(db,quote,user,{'engineering','assembly','sales'})
        for ident,factory,no,version,name in [('CHILD',F,'QUO-0-2','V1','第二产品'),('ALT',F,'QUO-0','A-V2','版本独有关键词'),('FOREIGN','huakang-b','OTHER','V1','外厂')]:
            quote=InternalQuote(id=ident,factory_id=factory,workshop_code='A',workshop_name='合成车间',quote_no=no,
                product_name=name,customer='客户一',qty=200,version_label=version,status='drafting',module_version='v4',
                batch_id='Q0' if ident=='CHILD' else ident,batch_position=2 if ident=='CHILD' else 1,batch_size=2 if ident=='CHILD' else 1,
                cloned_from_quote_id='Q0' if ident=='ALT' else '',created_by=user.id,created_by_name='合成创建人',created_at=STAMP,updated_at=STAMP)
            db.add(quote);db.flush()
            if ident=='ALT':
                native._create_reference_set(db,quote,user,source_type='synthetic_test')
                native._create_sections(db,quote,user,{'engineering','assembly','sales'})
        db.add(InternalQuoteFamily(id='Q0',factory_id=F,revision=1,selected_quote_id=''));db.flush()
        for ident,version in [('Q0',1),('ALT',2)]:
            db.add(InternalQuoteAlternative(quote_id=ident,family_id='Q0',scenario_id='A',scenario_name='原方案',version_number=version,source_quote_id='Q0' if ident=='ALT' else ''))
        db.commit()
    return client,dbm,calls,user


def capture(dbm):
    statements=[]
    def listener(conn,cursor,statement,*args): statements.append(statement)
    event.listen(dbm.engine,'before_cursor_execute',listener)
    return statements,lambda:event.remove(dbm.engine,'before_cursor_execute',listener)


def no_writes(statements):
    assert not any(s.lstrip().upper().startswith(('INSERT','UPDATE','DELETE','REPLACE')) for s in statements)


def test_full_document_reader_matches_native_filtered_pages_including_member_matches(env):
    from app.services import internal_quote_queries as queries
    client,dbm,calls,user=setup(env)
    statements,stop=capture(dbm)
    try:
        for filters in ({},{'customer':'客户一'},{'keyword':'合成负责人'},{'keyword':'第二产品'},{'keyword':'版本独有关键词'},{'status':'archived'}):
            with dbm.SessionLocal() as db:
                rows=queries.documents(db,user,F,**filters)
                ids=[row.id for row in rows]
            response=client.get('/api/internal-quotes',params=dict(factory_id=F,page=1,page_size=10,**filters))
            assert response.status_code==200,response.text
            native=response.json()
            assert len(ids)==native['total']
            assert ids[:10]==[row['id'] for row in native['items']]
            if not filters: assert len(ids)==12 and 'ALT' not in ids and 'CHILD' not in ids
            if filters.get('keyword') in {'第二产品','版本独有关键词'}: assert ids==['Q0']
    finally:stop()
    no_writes(statements);assert not calls


def test_detail_matches_native_without_adding_view_log(env):
    from app.services import internal_quote_queries as queries
    from app.models.internal_quote import InternalQuoteAuditLog
    client,dbm,calls,user=setup(env)
    statements,stop=capture(dbm)
    try:
        with dbm.SessionLocal() as db:
            before=db.scalar(select(func.count()).select_from(InternalQuoteAuditLog))
            detail=queries.detail(db,user,F,'Q0').model_dump(mode='json')
            assert db.scalar(select(func.count()).select_from(InternalQuoteAuditLog))==before
    finally:stop()
    no_writes(statements)
    response=client.get('/api/internal-quotes/Q0');assert response.status_code==200,response.text
    assert detail==response.json()
    with dbm.SessionLocal() as db: assert db.scalar(select(func.count()).select_from(InternalQuoteAuditLog))==before+1
    assert not calls


def test_summary_and_version_comparison_reuse_native_calculations_and_never_initialize(env):
    from app.services import internal_quote_queries as queries
    from app.models.internal_quote import InternalQuote,InternalQuoteReferenceSet
    client,dbm,calls,user=setup(env)
    statements,stop=capture(dbm)
    try:
        with dbm.SessionLocal() as db:
            summary=queries.summary(db,user,F,'Q0')
            compare=queries.comparison(db,user,F,'ALT','Q0').model_dump(mode='json')
            count=db.scalar(select(func.count()).select_from(InternalQuoteReferenceSet))
            with pytest.raises(HTTPException) as missing: queries.summary(db,user,F,'Q1')
            assert missing.value.status_code==409
            assert db.get(InternalQuote,'Q1').reference_snapshot_id==''
            assert db.scalar(select(func.count()).select_from(InternalQuoteReferenceSet))==count
        response=client.get('/api/internal-quotes/Q0/summary');assert response.status_code==200,response.text
        assert summary==response.json()
        response=client.get('/api/internal-quotes/ALT/compare/Q0');assert response.status_code==200,response.text
        assert compare==response.json()
    finally:stop()
    no_writes(statements)
    assert summary['pricing_complete'] is False and summary['authoritative_factory_quote_hkd'] is None
    assert summary['current_formula_version']=='rr2-2026-v11' and not calls


def test_scope_and_financial_permissions_are_independent_and_checked_before_read(env):
    from app.services import internal_quote_queries as queries
    _,dbm,_,_=setup(env)
    reader=actor('quote-reader',factory=F,department='sales-business',permissions=('internal_quote:read',))
    statements,stop=capture(dbm)
    try:
        with dbm.SessionLocal() as db:
            assert queries.detail(db,reader,F,'Q0').id=='Q0'
            for read in (lambda:queries.summary(db,reader,F,'Q0'),lambda:queries.comparison(db,reader,F,'ALT','Q0'),
                         lambda:queries.documents(db,reader,'huakang-b')):
                with pytest.raises(HTTPException) as forbidden:read()
                assert forbidden.value.status_code==403
            for ident in ('FOREIGN','missing'):
                with pytest.raises(HTTPException) as missing:queries.detail(db,reader,F,ident)
                assert missing.value.status_code==404
    finally:stop()
    no_writes(statements)


def test_pending_molding_summary_projection_does_not_dirty_or_rewrite_saved_section(env):
    from app.services import internal_quote as native, internal_quote_queries as queries
    from app.models.internal_quote import InternalQuoteSection
    _,dbm,_,user=setup(env)
    env[3].setattr(native,'_can_project_molding_read',lambda *args:True)
    env[3].setattr(native,'molding_projection_pending',lambda *args:True)
    with dbm.SessionLocal() as db:
        molding=db.get(InternalQuoteSection,'Q0-molding')
        molding.is_required=True
        molding.calculation_status='valid'
        molding.dependency_status='current'
        molding.calculation_json='{"status":"valid","totals":{"total_hkd":"15"}}'
        db.commit()
    statements,stop=capture(dbm)
    try:
        for read_only in (True,False):
            with dbm.SessionLocal() as db:
                result=queries.summary(db,user,F,'Q0') if read_only else native.get_quote_summary(db,'Q0',user)
                row=next(s for s in result['sections'] if s['section_code']=='molding')
                assert row['calculation_status']==row['dependency_status']=='stale'
                assert not db.dirty
                db.commit()
                saved=db.get(InternalQuoteSection,'Q0-molding')
                assert saved.calculation_status=='valid' and saved.dependency_status=='current'
                assert saved.calculation_json=='{"status":"valid","totals":{"total_hkd":"15"}}'
    finally:stop()
    no_writes(statements)

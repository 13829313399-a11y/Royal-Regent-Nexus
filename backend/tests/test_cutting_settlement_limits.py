from copy import deepcopy
from datetime import date
from uuid import uuid4
import pytest
from fastapi import HTTPException
from app.services import cutting_settlement as service, cutting_planning as planning
from app.services.cutting_settlement_schemas import Save
from test_cutting_ops import client, command
from test_cutting_orders import flow
from test_cutting_planning import planned
from test_cutting_reporting import production, ok
from test_cutting_settlement import fees, basis, price, save, save_body, decision, accountant, record, URL


@pytest.mark.parametrize('field,value', [('vendor','other-vendor'),('currency','USD')])
def test_one_statement_cannot_mix_vendors_or_currencies(fees,field,value):
    p=fees;price(p)
    first=basis(p)['rows'][0];second=deepcopy(first)
    second['acceptance_id']='second-acceptance';second['task_id']='other-task'
    if field=='vendor':second['context']['resource_id']=value
    else:second['price']['currency']=value
    first['prior_priced_sets']=second['prior_priced_sets']=0
    body=save_body(p)
    body['selections'].append(dict(line_id='line-1',acceptance_id='second-acceptance',sets=1))
    with pytest.raises(HTTPException) as error:
        service.calculate(Save.model_validate(body),[first,second],'2026-10-16')
    assert error.value.status_code==409


def test_later_month_uses_unsettled_acceptance_without_recounting(fees,monkeypatch):
    p=fees;price(p,value='1.25');did=save(p,sets=5);ok(decision(p,did,'submit'));accountant(p);ok(decision(p,did,'confirm'))
    monkeypatch.setattr(planning,'business_today',lambda:date(2026,11,16))
    value=ok(p.get(URL+'/2026-11/basis',params={'factory_id':'huakang-c'}))
    row=value['rows'][0]
    assert row['reserved_sets']==5 and row['available_sets']==15
    from test_cutting_ops import user
    from test_cutting_settlement import ACTIONS
    p.cutting_auth['user']=user(*ACTIONS)
    body=command(expected_version=value['revision'],document_id=uuid4().hex,month='2026-11',basis_token=value['basis_token'],
        selections=[dict(line_id='line-1',acceptance_id=p.acceptance,sets=3)],vendor_evidence='十一月补结余量确认')
    ok(p.post(URL+'/save',json=body))
    snapshot=ok(p.get(URL+'/2026-11',params={'factory_id':'huakang-c','document_id':body['document_id']}))['data']['snapshot']
    assert snapshot['sets']==3 and snapshot['total']=='3.75'
    assert snapshot['rows'][0]['prior_priced_sets']==5
    assert p.get(URL+'/2026-10',params={'factory_id':'huakang-c','document_id':body['document_id']}).status_code==404

"""Real cookie sessions and current IAM grants, independent of workflow tests."""
from sqlalchemy import delete
from sqlalchemy.orm import Session
from app.models.auth import AuthRolePermission, AuthUserPermissionOverride
from test_cutting_ops import client, command, BASE
from test_cutting_orders import flow
from test_cutting_session_auth import session_flow, login


def test_real_sessions_separate_financial_roles_and_revocation(session_flow, monkeypatch):
    from app.api import cutting_operations as api
    monkeypatch.setattr(api.settlement, 'execute', lambda *args: {'state':'permission-verified'})
    p=session_flow
    # Keep one set of actual accounts; every request still re-evaluates current IAM.
    cases=[('production','submit',200),('production','confirm',403),('accounting','confirm',200),
           ('accounting','reopen',200),('accounting','submit',403),('procurement','confirm',403),
           ('foreign','confirm',403),('reader','submit',403)]
    for name,action,status in cases:
        login(p,name)
        response=p.post(BASE+'/settlements/'+action,json=command(document_id='test-document-0001'))
        assert response.status_code==status,response.text
    login(p,'accounting')
    with Session(p.engine) as db:
        db.add(AuthUserPermissionOverride(id='deny-settlement',user_id='accounting',permission_id='cutting_ops:settlement_confirm',effect='deny',factory_id='huakang-c',department='accounting'))
        db.commit()
    assert p.post(BASE+'/settlements/confirm',json=command(document_id='test-document-0001')).status_code==403
    with Session(p.engine) as db:
        db.execute(delete(AuthRolePermission).where(AuthRolePermission.id=='accounting:settlement_read'))
        db.commit()
    assert p.post(BASE+'/settlements/reopen',json=command(document_id='test-document-0001')).status_code==403

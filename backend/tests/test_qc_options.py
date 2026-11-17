import json
from pathlib import Path
import pytest
from fastapi import HTTPException
from app.services import qc_options as options


def test_config_is_factory_scoped_and_preserves_verified_current_actor(tmp_path,monkeypatch):
 monkeypatch.setattr(options.settings,'qc_department_data_dir',str(tmp_path))
 actor={'id':'current','name':'当前登录人员'}
 assert options.choices('huaxing',actor)==dict(inspectors=[actor],institutions=[],hongKongContacts=[])
 (tmp_path/'options.json').write_text(json.dumps({'huaxing':{'inspectors':[{'id':'old','name':'旧人员','active':False}],'institutions':[{'id':'agency-a','name':'机构甲'}]},'huadeng':{'institutions':[{'id':'agency-b','name':'机构乙'}]}}))
 assert options.selection('huaxing',actor,'institutions','agency-a')=='机构甲'
 for identity in ['agency-b','unknown']:
  with pytest.raises(HTTPException):options.selection('huaxing',actor,'institutions',identity)
 assert options.choices('huaxing',actor)['inspectors']==[actor]
 (tmp_path/'options.json').write_text('{bad')
 with pytest.raises(HTTPException) as err:options.choices('huaxing',actor)
 assert err.value.status_code==503

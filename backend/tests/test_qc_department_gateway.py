"""Exercise the bridge with real Nexus sessions and scoped permissions."""
import importlib
import httpx
import pytest

from test_molding_sample_api import make_client, login_as, grant_permission_override


@pytest.fixture(autouse=True)
def isolated_example_store(monkeypatch, tmp_path):
    monkeypatch.setenv('QC_DEPARTMENT_DATA_DIR', str(tmp_path / 'qc-companies'))
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path / 'main-test-db')


def install_upstream(monkeypatch):
    module = importlib.import_module("app.api.qc_department")
    calls = []

    async def fake(method, path, params, body):
        calls.append((method, path, params, body))
        return httpx.Response(200, json={"ok": True, "records": [], "nextId": 1,
            "users": [{"username": "private-account", "password": "must-not-leak"}],
            "partners": [], "defectLib": []})

    monkeypatch.setattr(module, "upstream", fake)
    return calls


def test_session_factory_boundary_and_no_local_accounts(monkeypatch):
    with make_client(monkeypatch) as client:
        calls = install_upstream(monkeypatch)
        base = "/api/qc-department/huaxing/"
        assert client.get(base).status_code == 401
        login_as(client, "qc_inspector")
        base = client.get(base + "api/health").json()["frame_url"]
        calls.clear()
        assert client.get(base).status_code == 200
        assert client.get(base + "nexus-context.js").status_code == 200
        asset = client.get(base + "qc-schedule.js")
        assert asset.status_code == 200
        assert "root.renderSalesSchedule=refresh" in asset.text
        assert asset.headers["cache-control"] == "no-store"
        assert client.post(base + "qc-schedule.js").status_code == 404
        data = client.get(base + "api/bootstrap").json()
        assert data["users"][0]["username"].startswith("nexus:")
        assert data["users"][0]["password"] is None
        assert "must-not-leak" not in str(data)
        assert calls[-1][2] == [("company", "hy-huaxing")]
        before = len(calls)
        assert client.get(base + "api/bootstrap?company=hy-huakang-a").status_code == 403
        assert client.get(base + "api/bootstrap?company=hy-huaxing&company=hy-huakang-a").status_code == 403
        assert client.get("/api/qc-department/huakang-a/api/bootstrap").status_code == 403
        assert client.get("/api/qc-department/group/api/bootstrap").status_code == 422
        assert client.get(base + "vendor/%2e%2e%2fserver%2fserver.js").status_code == 404
        assert client.get(base + "server/seed.json").status_code == 404
        assert client.get(base + "server/data/hy-huaxing/qc.db").status_code == 404
        assert client.post(base + "api/users", json={"users": []}).status_code == 404
        assert client.post(base + "api/sso-verify", json={}).status_code == 404
        assert len(calls) == before


def test_schedule_reads_formal_source_without_importing_or_using_examples(monkeypatch):
    with make_client(monkeypatch) as client:
        calls = install_upstream(monkeypatch)
        login_as(client, "qc_inspector")
        endpoint = client.get("/api/qc-department/huaxing/api/health").json()["frame_url"] + "api/schedule-source"
        calls.clear()
        response = client.get(endpoint)
        assert response.status_code == 200
        data = response.json()
        assert data["contract_version"] == "2" and data["status"] == "ready"
        assert data["mapping_version"] == "qc-task-v1" and data["source_available"] is True
        assert data["factory_id"] == "huaxing" and data["items"] == []
        assert data["import_enabled"] is False
        assert client.post(endpoint, json={"items": [{"id": 1}]}).status_code == 404
        assert calls == []


def test_writes_require_permissions_and_deletes_cannot_hide_in_sync(monkeypatch):
    with make_client(monkeypatch) as client:
        calls = install_upstream(monkeypatch)
        login_as(client, "qc_inspector")
        base = client.get("/api/qc-department/huaxing/api/health").json()["frame_url"]
        calls.clear()
        assert client.post(base + "api/records", json={"records": []}).status_code == 200
        for path, body in [("api/records", {"records": [], "deletedIds": [1]}),
                           ("api/records/delete", {"ids": [1]}),
                           ("api/reference-data/clear", {}),
                           ("api/records/replace", {"records": []}),
                           ("api/partners", {"partners": []})]:
            assert client.post(base + path, json=body).status_code == 403
        assert client.post(base + "api/records", content='{}', headers={"Content-Type": "text/plain"}).status_code == 415
        assert client.post(base + "api/records", json={}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
        assert len(calls) == 1
        login_as(client, "engineer")
        assert client.get(base + "api/bootstrap").status_code == 403
        assert client.post(base + "api/records", json={"records": []}).status_code == 403


def test_upstream_failure_is_visible(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "qc_inspector")
        module = importlib.import_module("app.api.qc_department")
        original = module.upstream
        install_upstream(monkeypatch)
        base = client.get("/api/qc-department/huaxing/api/health").json()["frame_url"]
        monkeypatch.setattr(module, "upstream", original)
        from pydantic import SecretStr
        monkeypatch.setattr(module.settings, "qc_department_gateway_token", SecretStr(""))
        response = client.get(base + "api/bootstrap")
        assert response.status_code == 503
        assert "records" not in response.json()


def test_old_actor_url_cannot_write_after_account_change(monkeypatch):
    with make_client(monkeypatch) as client:
        calls = install_upstream(monkeypatch)
        login_as(client, "qc_inspector")
        old_url = client.get("/api/qc-department/huaxing/api/health").json()["frame_url"]
        login_as(client, "qc_supervisor")
        calls.clear()
        assert client.get(old_url + "api/bootstrap").status_code == 409
        assert client.post(old_url + "api/records", json={"records": []}).status_code == 409
        assert calls == []


def test_denied_order_write_cannot_create_through_record_sync(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    with make_client(monkeypatch) as client:
        calls = install_upstream(monkeypatch)
        login_as(client, "qc_inspector")
        grant_permission_override("qc_inspector", "qc_inspection:order_write", effect="deny", factory_id="huaxing", department="qc")
        base = client.get("/api/qc-department/huaxing/api/health").json()["frame_url"]
        calls.clear()
        assert client.post(base + "api/records", json={"records": [{"id": 1}]}).status_code == 403
        assert client.post(base + "api/reference-data/clear", json={}).status_code == 403
        assert calls == []


def test_real_node_service_roundtrip_and_private_port(monkeypatch, tmp_path):
    import os
    import secrets
    import shutil
    import socket
    import subprocess
    import time
    from pathlib import Path
    from pydantic import SecretStr

    token = secrets.token_hex(32)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    root = Path(__file__).resolve().parents[2]
    child = subprocess.Popen([shutil.which("node"), str(root / "services/qc-department/server/server.js")],
        env={**os.environ, "HOST": "127.0.0.1", "PORT": str(port), "DATA_PATH": str(tmp_path),
             "QC_DEPARTMENT_GATEWAY_TOKEN": token}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                if httpx.get(url + "/api/health", trust_env=False).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.05)
        else:
            raise AssertionError("Test sidecar did not start")
        assert httpx.get(url + "/api/bootstrap?company=hy-huaxing", trust_env=False).status_code == 403
        with make_client(monkeypatch) as client:
            module = importlib.import_module("app.api.qc_department")
            monkeypatch.setattr(module.settings, "qc_department_url", url)
            monkeypatch.setattr(module.settings, "qc_department_gateway_token", SecretStr(token))
            login_as(client, "qc_inspector")
            base = client.get("/api/qc-department/huaxing/api/health").json()["frame_url"]
            assert client.get(base).status_code == 200
            assert client.get(base + "app.js").status_code == 200
            assert client.get(base + "vendor/tesseract/core/tesseract-core-simd-lstm.wasm").status_code == 200
            assert client.get(base + "api/bootstrap").json()["records"] == []
            record = {"id": 1, "orderNo": "0000123", "productNo": "0000456", "result": "PASS", "qty": 10,
                      "updatedAt": "2026-10-26T01:00:00Z"}
            response = client.post(base + "api/records", json={"records": [record]})
            assert response.status_code == 200
            stored = client.get(base + "api/bootstrap").json()["records"]
            assert len(stored) == 1 and stored[0]["orderNo"] == "0000123"
            exported = client.get(base + "api/export/records.csv")
            assert exported.status_code == 200 and "0000123" in exported.text
            wf=importlib.import_module('app.services.qc_workflow')
            execution=wf.record_execution({'supplier':'验货供应商','client':'ZURU','productNo':'NEW-001','productName':'新验货产品','orderNo':'PO-NEW-001','qty':20,'sampleQty':5,'result':'','qc':'QC'})
            created=client.post(base+'api/workflow/manual',json={'requestKey':'manual-export-check','method':'internal','execution':execution})
            assert created.status_code==200,created.text
            for export_name in ['records.csv','factory-excel.xls']:
                export=client.get(base+'api/export/'+export_name)
                assert export.status_code==200 and 'PO-NEW-001' in export.text and '0000123' in export.text
                assert export.text.count('NEW-001')==2
                filtered=client.get(base+'api/export/'+export_name+'?search=NO-MATCH')
                assert 'PO-NEW-001' not in filtered.text
            assert client.get(base+'api/bootstrap').json()['records']==stored
            login_as(client, "admin")
            admin_base = client.get("/api/qc-department/huaxing/api/health").json()["frame_url"]
            cleared = client.post(admin_base + "api/reference-data/clear", json={})
            assert cleared.status_code == 200 and cleared.json()["deleted"] == 0
            assert len(client.get(admin_base + "api/bootstrap").json()["records"]) == 1
            other = client.get("/api/qc-department/huakang-a/api/health").json()["frame_url"]
            assert client.get(other + "api/bootstrap").json()["records"] == []
    finally:
        child.terminate()
        child.wait(timeout=10)


def test_schedule_example_is_readonly_authorized_and_huaxing_only(monkeypatch):
    with make_client(monkeypatch) as client:
        calls = install_upstream(monkeypatch)
        assert client.get('/api/qc-department/huaxing/api/schedule-example').status_code == 401
        login_as(client, 'qc_inspector')
        base = client.get('/api/qc-department/huaxing/api/health').json()['frame_url']
        calls.clear()
        response = client.get(base + 'api/schedule-example')
        assert response.status_code == 200
        data = response.json()
        assert data['example'] is True and data['factory_id'] == 'huaxing'
        assert data['source']['sheet'] == '各客验货排期 (3)'
        assert len(data['items']) == 47
        assert sum(row['quantity'] for row in data['items']) == 53826
        assert response.headers['cache-control'] == 'no-store'
        assert client.post(base + 'api/schedule-example', json={}).status_code == 404
        assert client.get(base + 'fixtures/qc-schedule-example.json').status_code == 404
        assert client.get('/api/qc-department/huakang-a/api/schedule-example').status_code == 403
        assert calls == []
        login_as(client, 'admin')
        other = client.get('/api/qc-department/huakang-a/api/health').json()['frame_url']
        calls.clear()
        assert client.get(other + 'api/schedule-example').status_code == 404
        assert calls == []


def test_example_feedback_persists_separately_and_checks_revision(monkeypatch):
    with make_client(monkeypatch) as client:
        calls = install_upstream(monkeypatch)
        login_as(client, 'qc_inspector')
        base = client.get('/api/qc-department/huaxing/api/health').json()['frame_url']
        original = client.get(base + 'api/schedule-example').json()
        row = original['items'][0]
        body = dict(id=row['id'], sourceSha256=original['source']['sha256'], completion='已完成', remark='划痕3件', revision=0)
        calls.clear()
        endpoint = base + 'api/schedule-example/feedback'
        response = client.post(endpoint, json=body)
        assert response.status_code == 200, response.text
        assert response.json()['feedbackRevision'] == 1
        updated = client.get(base + 'api/schedule-example').json()
        assert updated['items'][0]['completion'] == '已完成'
        assert updated['items'][0]['remark'] == '划痕3件'
        assert updated['items'][1:] == original['items'][1:]
        assert client.post(endpoint, json=body).status_code == 409
        assert client.post(endpoint, json={**body, 'revision':1,'completion':'','remark':''}).status_code == 200
        assert client.get(base + 'api/schedule-example').json()['items'][0]['completion'] == ''
        service = importlib.import_module('app.services.qc_schedule_example_feedback')
        assert service.store_path().name == 'feedback.sqlite3'
        assert service.store_path().parent.name == '_schedule_examples'
        gateway = importlib.import_module('app.api.qc_department')
        assert gateway.schedule_example('huaxing')['items'][0]['completion'] == ''
        for bad in [{**body,'id':'inspection-1'}, {**body,'sourceSha256':'old'}, {**body,'quantity':99},
                    {**body,'revision':True}, {**body,'completion':123}, {**body,'remark':'x'*4001}]:
            assert client.post(endpoint,json=bad).status_code in {404,409,422}
        assert client.post(endpoint,content='{}',headers={'Content-Type':'text/plain'}).status_code == 415
        assert client.post(endpoint,json=body,headers={'Sec-Fetch-Site':'cross-site'}).status_code == 403
        assert calls == []
        login_as(client,'admin')
        other=client.get('/api/qc-department/huakang-a/api/health').json()['frame_url']
        calls.clear()
        assert client.post(other+'api/schedule-example/feedback',json=body).status_code == 404
        assert client.post(endpoint,json=body).status_code == 409  # previous actor
        assert calls == []


def test_example_feedback_enforces_write_permission(monkeypatch):
    monkeypatch.setenv('AUTHZ_MODE','enforce')
    with make_client(monkeypatch) as client:
        calls=install_upstream(monkeypatch)
        login_as(client,'qc_inspector')
        grant_permission_override('qc_inspector','qc_inspection:order_write',effect='deny',factory_id='huaxing',department='qc')
        base=client.get('/api/qc-department/huaxing/api/health').json()['frame_url']
        calls.clear()
        assert client.get(base+'api/schedule-example').status_code == 200
        assert client.post(base+'api/schedule-example/feedback',json={}).status_code == 403
        assert '"scheduleExampleWriteAllowed": false' in client.get(base+'nexus-context.js').text
        assert calls == []
        service=importlib.import_module('app.services.qc_schedule_example_feedback')
        assert not service.store_path().exists()


def workbook_bytes():
    import io
    import zipfile
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as archive:
        archive.writestr('[Content_Types].xml', '<Types/>')
        archive.writestr('xl/workbook.xml', '<workbook/>')
    return out.getvalue()


def test_schedule_http_download_scoping_and_exact_bytes(monkeypatch):
    from pydantic import SecretStr
    from urllib.parse import quote
    with make_client(monkeypatch) as client:
        calls = install_upstream(monkeypatch)
        module = importlib.import_module('app.api.qc_department')
        helper = importlib.import_module('app.services.qc_schedule_downloads')
        monkeypatch.setattr(module.settings, 'qc_department_gateway_token', SecretStr('test-download-secret'))
        login_as(client, 'qc_inspector')
        base = client.get('/api/qc-department/huaxing/api/health').json()['frame_url']
        calls.clear()
        content = workbook_bytes()
        result = client.post(base+'api/schedule-export?mode=example',content=content,headers={'Content-Type':helper.MIME})
        assert result.status_code == 200, result.text
        url = base + result.json()['url']
        downloaded = client.get(url)
        assert downloaded.status_code == 200
        assert downloaded.content == content
        assert downloaded.headers['content-type'] == helper.MIME
        assert downloaded.headers['cache-control'] == 'no-store'
        assert quote('QC客排期_示例数据.xlsx') in downloaded.headers['content-disposition']
        head = client.head(url)
        assert head.status_code == 200 and head.content == b''
        assert int(head.headers['content-length']) == len(content)
        assert client.get(url[:-1]+('0' if url[-1]!='0' else '1')).status_code == 404
        assert client.get(url.replace('/huaxing/','/huakang-a/')).status_code == 403
        assert not list(helper.folder().parent.rglob('qc.db'))
        assert calls == []
        login_as(client,'qc_supervisor')
        assert client.get(url).status_code == 409


def test_schedule_http_download_validation_and_expiry(monkeypatch):
    from pydantic import SecretStr
    with make_client(monkeypatch) as client:
        install_upstream(monkeypatch)
        helper = importlib.import_module('app.services.qc_schedule_downloads')
        monkeypatch.setattr(helper.settings,'qc_department_gateway_token',SecretStr('test-download-secret'))
        login_as(client,'qc_inspector')
        base = client.get('/api/qc-department/huaxing/api/health').json()['frame_url']
        endpoint = base+'api/schedule-export?mode=example'
        headers = {'Content-Type':helper.MIME}
        content=workbook_bytes()
        assert client.post(endpoint,content=content).status_code == 415
        assert client.post(endpoint,content=content,headers={**headers,'Sec-Fetch-Site':'cross-site'}).status_code == 403
        assert client.post(endpoint,content=b'invalid',headers=headers).status_code == 422
        assert client.post(base+'api/schedule-export?mode=other',content=content,headers=headers).status_code == 422
        monkeypatch.setattr(helper,'MAX_BYTES',len(content)-1)
        assert client.post(endpoint,content=content,headers=headers).status_code == 413
        monkeypatch.setattr(helper,'MAX_BYTES',8*1024*1024)
        ticket=client.post(endpoint,content=content,headers=headers).json()
        token=ticket['url'].rsplit('/',1)[1]
        owner=base.split('/')[3]+':'+base.split('/')[4][2:]
        assert helper.download(token,owner)[0]==content
        with pytest.raises(Exception) as denied:
            helper.download(token,'another-actor')
        assert denied.value.status_code==404
        monkeypatch.setattr(helper,'time',type('Clock',(),{'time':staticmethod(lambda:int(token.split('.')[1])+1)})())
        assert client.get(base+ticket['url']).status_code==410


def test_schedule_http_download_rechecks_export_permission(monkeypatch):
    from pydantic import SecretStr
    monkeypatch.setenv('AUTHZ_MODE','enforce')
    with make_client(monkeypatch) as client:
        install_upstream(monkeypatch)
        helper=importlib.import_module('app.services.qc_schedule_downloads')
        monkeypatch.setattr(helper.settings,'qc_department_gateway_token',SecretStr('test-download-secret'))
        login_as(client,'qc_inspector')
        base=client.get('/api/qc-department/huaxing/api/health').json()['frame_url']
        headers={'Content-Type':helper.MIME}
        result=client.post(base+'api/schedule-export?mode=template',content=workbook_bytes(),headers=headers)
        assert result.status_code==200
        grant_permission_override('qc_inspector','qc_inspection:report_export',effect='deny',factory_id='huaxing',department='qc')
        newbase=client.get('/api/qc-department/huaxing/api/health').json()['frame_url']
        assert client.get(newbase+result.json()['url']).status_code==403
        assert client.post(newbase+'api/schedule-export?mode=template',content=workbook_bytes(),headers=headers).status_code==403


def test_real_sessions_inspector_submit_supervisor_review_complete_workflow(monkeypatch):
    from decimal import Decimal
    import base64
    from io import BytesIO
    import zipfile
    with make_client(monkeypatch) as client:
        install_upstream(monkeypatch)
        module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.customer_order_ledger")
        with module.SessionLocal() as db:
            db.add(models.OrderLedgerLine(id="workflow-test-order", factory_id="huaxing", customer_code="buzzbee",
                customer_name="测试客户", identity_key="workflow-isolated-key", reference_no="00001", product_no="00002",
                quantity=Decimal("100"), shipped_quantity=Decimal("0"), status="active", version=1, revision=1,
                data={"po_no":"00123", "product_name_zh":"隔离测试产品", "requested_ship_date":"2026-10-30"},
                created_at="2026-10-26T00:00:00Z", updated_at="2026-10-26T00:00:00Z"))
            db.commit()
        login_as(client,"qc_inspector")
        base=client.get("/api/qc-department/huaxing/api/health").json()["frame_url"]
        context=client.get(base+"nexus-context.js").text
        assert '"review": false' in context
        t=client.post(base+"api/workflow/tasks",json={"requestKey":"seeded-role-journey", "items":[{
            "sourceId":"workflow-test-order", "sourceRevision":1, "method":"external", "batch":"首验",
            "plannedDate":"2026-10-26", "plannedQuantity":"100"}]}).json()["items"][0]
        path=base+"api/workflow/tasks/"+t["id"]
        e=t["execution"];e.update(actualDate="2026-10-26",actualQuantity="100",sampleQuantity="10",inspector="机构验货员",
            institution="测试第三方",reportNo="TEST-001",result="REJ",remark="依据机构原报告")
        t=client.post(path+"/save",json={"revision":t["revision"],"execution":e}).json()
        t=client.post(path+"/attach",json={"revision":t["revision"],"name":"第三方报告.pdf","caption":"机构原件",
            "content":base64.b64encode(b"%PDF-1.4 isolated-test").decode()}).json()
        attachment=t["attachments"][0]
        t=client.post(path+"/submit",json={"revision":t["revision"]}).json()
        assert t["state"]=="pending"
        assert client.post(path+"/approve",json={"revision":t["revision"],"reason":""}).status_code==403
        assert client.post(path+"/save",json={"revision":t["revision"],"execution":e}).status_code==409
        login_as(client,"qc_supervisor")
        reviewer=client.get("/api/qc-department/huaxing/api/health").json()["frame_url"]
        path=reviewer+"api/workflow/tasks/"+t["id"]
        details=client.get(path).json()
        assert details["execution"]=={**e,"inspector":"华兴QC检验员"} and details["attachments"][0]["id"]==attachment["id"]
        assert client.get(path+"/files/"+attachment["id"]).content==b"%PDF-1.4 isolated-test"
        t=client.post(path+"/return",json={"revision":t["revision"],"reason":"补充具体问题"}).json()
        assert t["state"]=="returned"
        login_as(client,"qc_inspector")
        base=client.get("/api/qc-department/huaxing/api/health").json()["frame_url"];path=base+"api/workflow/tasks/"+t["id"]
        e["remark"]="机构原报告：箱唛错误，附报告原件"
        t=client.post(path+"/save",json={"revision":t["revision"],"execution":e}).json()
        t=client.post(path+"/submit",json={"revision":t["revision"]}).json()
        login_as(client,"qc_supervisor")
        base=client.get("/api/qc-department/huaxing/api/health").json()["frame_url"];path=base+"api/workflow/tasks/"+t["id"]
        response=client.post(path+"/approve",json={"revision":t["revision"],"reason":"已核对原报告"})
        assert response.status_code==200 and response.json()["state"]=="approved"
        assert response.json()["execution"]["result"]=="REJ"
        assert len(client.get(base+"api/workflow/projections").json()["items"])==1
        exported=client.post(base+"api/workflow/export",json={"ids":[t["id"]],"formal":True})
        assert exported.status_code==200
        with zipfile.ZipFile(BytesIO(exported.content)) as archive:
            assert any(name.endswith("第三方报告.pdf") for name in archive.namelist())
        ticket = client.post(base+"api/workflow/export-prepare",json={"ids":[t["id"]],"formal":True})
        assert ticket.status_code == 200, ticket.text
        download = client.get(base+ticket.json()["url"])
        assert download.status_code == 200 and download.content.startswith(b"PK")
        assert client.get(base+"api/bootstrap").json()["records"]==[]


def test_historical_return_uses_new_form_with_full_permission_lock_and_attachments(monkeypatch):
    from copy import deepcopy
    import json, base64
    from io import BytesIO
    from PIL import Image
    with make_client(monkeypatch) as client:
        gateway=importlib.import_module('app.api.qc_department')
        original={'id':22,'status':'approved','supplier':'名发','client':'ZURU','date':'2026-04-20','inspDate':'2026-04-20','qty':600,'sampleQty':80,'pass':72,'fail':8,'defectRate':'10.00%','result':'REJ','productNo':'15755','productName':'粉色熊','deliveryNo':'0005501','qc':'原检验员','remark':'原备注','defects':[],'measurements':[],'updatedAt':'old'}
        rows=[deepcopy(original)]
        async def fake(method,path,params,body):
            if path!='api/health': assert params==[('company','hy-huaxing')]
            if method=='POST':
                for r in json.loads(body).get('records',[]):rows[0]=r
            return httpx.Response(200,json={'records':deepcopy(rows),'nextId':23,'referenceData':{'ids':[22],'count':1},'users':[]})
        monkeypatch.setattr(gateway,'upstream',fake)
        login_as(client,'qc_inspector');base=client.get('/api/qc-department/huaxing/api/health').json()['frame_url']
        review={'recordId':22,'updatedAt':'old','action':'return','reason':'请补照片'}
        assert client.post(base+'api/workflow/legacy-review',json=review).status_code==403
        assert client.post(base+'api/workflow/legacy',json={'recordId':22}).status_code==409
        login_as(client,'qc_supervisor');base=client.get('/api/qc-department/huaxing/api/health').json()['frame_url']
        assert client.post(base+'api/workflow/legacy-review',json=review).status_code==200
        baseline=deepcopy(rows[0]);assert baseline['status']=='rejected'
        login_as(client,'qc_inspector');base=client.get('/api/qc-department/huaxing/api/health').json()['frame_url']
        response=client.post(base+'api/workflow/legacy',json={'recordId':22});assert response.status_code==200,response.text
        t=response.json();path=base+'api/workflow/tasks/'+t['id'];e=t['execution'];e['remark']='补充现场照片'
        t=client.post(path+'/save',json={'revision':t['revision'],'execution':e,'method':'internal'}).json()
        photo=BytesIO();Image.new('RGB',(2,2),'red').save(photo,format='PNG')
        t=client.post(path+'/attach',json={'revision':t['revision'],'name':'验货照片.png','caption':'问题位置','content':base64.b64encode(photo.getvalue()).decode()}).json()
        t=client.post(path+'/submit',json={'revision':t['revision']}).json();assert t['state']=='pending'
        assert client.post(path+'/save',json={'revision':t['revision'],'execution':e}).status_code==409
        assert client.post(path+'/approve',json={'revision':t['revision'],'reason':''}).status_code==403
        login_as(client,'qc_supervisor');base=client.get('/api/qc-department/huaxing/api/health').json()['frame_url'];path=base+'api/workflow/tasks/'+t['id']
        full=client.get(path).json();assert full['execution']['remark']=='补充现场照片' and full['attachments']
        t=client.post(path+'/approve',json={'revision':full['revision'],'reason':''}).json();assert t['state']=='approved'
        assert rows[0]==baseline and t['legacyOriginal']==baseline
        projected=client.get(base+'api/workflow/projections').json()['items'][0]
        assert projected['deliveryNo']=='0005501' and projected['reference'] and projected['result']=='REJ'


def test_inspection_plan_join_is_readonly_scoped_and_requires_verified_origin(monkeypatch):
    import copy
    module = importlib.import_module("app.api.qc_department")
    row = module.schedule_example('huaxing')['items'][0]
    record = {'id':31, 'client':row['customer'], 'orderNo':row['poNo'], 'productNo':row['productNo'],
              'date':'', 'inspDate':'', 'remark':'来源：测试；'+row['id']+'\n计划日期：2099-01-01'}
    original=copy.deepcopy(record)
    monkeypatch.setattr(module.qc_workflow,'test_entry_allowed',lambda factory,r:factory=='huaxing' and r==original)
    expected={'31':{'from':row['dateFrom'],'to':row['dateTo'] or row['dateFrom']}}
    assert module.inspection_plan_dates('huaxing',[record]) == expected
    assert record == original
    assert module.inspection_plan_dates('huakang-a',[record]) == {}
    assert module.inspection_plan_dates('huaxing',[{**record,'client':'other'}]) == {}
    assert module.inspection_plan_dates('huaxing',[{**record,'remark':'计划日期：2099-01-01'}],[31]) == {}
    assert module.inspection_plan_dates('huaxing',[{**record,'orderNo':'other'}],[31]) == {}

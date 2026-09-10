import importlib.util
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import pytest

TOOLS=Path(__file__).resolve().parents[2]/'deploy/three-d-printing/network'
sys.path.insert(0,str(TOOLS))
import doctor
import tailscale_doctor


def site_report():
    return {'tailscale':{'ip':['100.80.0.2']},'printers':[
        {'machine_no':n,'ip':f'192.168.110.{n}','tcp':'ok','tls':'observed','observed_cert_sha256':'a'*64}
        for n in range(1,12)]}


def test_windows_report_builds_cloud_config_without_linux_interfaces():
    value=tailscale_doctor.from_site_report(site_report())
    assert value['gateway_ip']=='100.80.0.2'
    assert len(value['printers'])==11
    assert value['printers'][0]['credential_ref']=='printer-01'
    bad=site_report(); bad['printers'][0]['tls']='failed'
    with pytest.raises(ValueError): tailscale_doctor.from_site_report(bad)
    bad=site_report(); bad['printers'][1]['ip']=bad['printers'][0]['ip']
    with pytest.raises(ValueError): tailscale_doctor.from_site_report(bad)


def test_cloud_probe_uses_tailscale_source_and_preserves_failed_checks(monkeypatch):
    monkeypatch.setattr(doctor,'run_json',lambda _: {'BackendState':'Running','TailscaleIPs':['100.80.0.1']})
    captured=[]
    def measured(config,*args,**kwargs):
        assert kwargs['timeout'] == 10
        assert kwargs['authenticate'] is False
        captured.append(config)
        return {'tunnel':'failed','exposure':'unknown','printers':[]}
    monkeypatch.setattr(doctor,'report',measured)
    assert tailscale_doctor.probe(tailscale_doctor.from_site_report(site_report()))['tunnel']=='failed'
    assert captured[0]['vpn']['connector_ip']=='100.80.0.1'
    assert captured[0]['vpn']['gateway_ip']=='100.80.0.2'


def test_health_upload_can_use_same_host_http(tmp_path):
    received=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append((self.path,self.headers.get('X-Three-D-Network-Token'),json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            self.send_response(200); self.end_headers()
        def log_message(self,*args): pass
    server=HTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    token=tmp_path/'token'; token.write_text('test-token-'+'x'*40)
    try:
        doctor.upload({'tunnel':'failed'},f'http://127.0.0.1:{server.server_port}/api/three-d-printing/network/health',token)
        assert received==[('/api/three-d-printing/network/health',token.read_text(),{'tunnel':'failed'})]
    finally:
        server.shutdown(); server.server_close(); thread.join()

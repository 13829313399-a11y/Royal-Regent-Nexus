"""Actual OS allocations and actual parser subprocesses, never parent limits."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zlib
import pytest
from test_assistant_api import env,session
from test_assistant_v2 import migrate,ready

ROOT=Path(__file__).parents[1]/'app/services/assistant'
pytestmark=pytest.mark.skipif(sys.platform!='win32' and not sys.platform.startswith('linux'),reason='Supported parser platforms')


def test_os_refuses_an_allocation_over_the_child_memory_limit():
    code="import sys;sys.path.insert(0,sys.argv[1]);from document_limits import apply_memory_limit;apply_memory_limit(128)\ntry: value=bytearray(256*1024*1024)\nexcept MemoryError: print('allocation-refused')\nelse: raise AssertionError('Allocation escaped the OS limit')"
    result=subprocess.run([sys.executable,'-c',code,str(ROOT)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='allocation-refused'


def run_worker(worker, source, output, extension='.txt'):
    child=subprocess.Popen([sys.executable,str(worker),str(source),str(output),extension,'100','200000','10','128'],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        assert child.wait(timeout=15)==0,child.stderr.read().decode(errors='replace')
        return json.loads(output.read_text(encoding='utf8'))
    finally:
        if child.poll() is None:child.kill();child.wait()
        child.stdin.close();child.stderr.close()


def test_worker_reports_memory_exhaustion_without_readable_output_and_next_worker_succeeds(tmp_path):
    worker=tmp_path/'document_worker.py'
    shutil.copy2(ROOT/'document_worker.py',worker);shutil.copy2(ROOT/'document_limits.py',tmp_path/'document_limits.py')
    (tmp_path/'document_parser.py').write_text("class DocumentParseError(Exception):pass\ndef extract(*args):\n value=bytearray(256*1024*1024)\n return []\n",encoding='utf8')
    source=tmp_path/'source';source.write_bytes(b'synthetic')
    assert run_worker(worker,source,tmp_path/'failed.json')==dict(error='parse_memory_limit')
    # A failed child does not lower the supervisor or the next child's limits.
    result=run_worker(ROOT/'document_worker.py',source,tmp_path/'ready.json')
    assert result['segments'][0]['text']=='synthetic'


def test_worker_refuses_to_parse_when_the_os_limit_cannot_be_installed(tmp_path):
    worker=tmp_path/'document_worker.py';shutil.copy2(ROOT/'document_worker.py',worker)
    (tmp_path/'document_limits.py').write_text("def apply_memory_limit(*args):raise OSError('synthetic OS failure')\n",encoding='utf8')
    (tmp_path/'document_parser.py').write_text("class DocumentParseError(Exception):pass\ndef extract(*args):raise AssertionError('Unbounded parsing must not run')\n",encoding='utf8')
    source=tmp_path/'source';source.write_bytes(b'synthetic')
    assert run_worker(worker,source,tmp_path/'failed.json')==dict(error='parse_resource_unavailable')


def compressed_pdf():
    compressor=zlib.compressobj();chunk=b'%'+b'x'*(1024*1024-2)+b'\n'
    packed=b''.join(compressor.compress(chunk) for _ in range(256))+compressor.flush()
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
        b'<< /Filter /FlateDecode /Length '+str(len(packed)).encode()+b' >>\nstream\n'+packed+b'\nendstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    raw=b'%PDF-1.4\n';offsets=[]
    for i,obj in enumerate(objects,1):
        offsets.append(len(raw));raw+=str(i).encode()+b' 0 obj\n'+obj+b'\nendobj\n'
    start=len(raw);raw+=b'xref\n0 6\n0000000000 65535 f \n'+b''.join(f'{offset:010} 00000 n \n'.encode() for offset in offsets)
    raw+=f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()
    assert len(raw)<1024*1024
    return raw


def test_compressed_pdf_expansion_is_rejected_in_the_bounded_real_worker(tmp_path):
    raw=compressed_pdf()
    source=tmp_path/'expanded.pdf';source.write_bytes(raw)
    result=run_worker(ROOT/'document_worker.py',source,tmp_path/'result.json','.pdf')
    assert result.get('error') in ('parse_memory_limit','pdf_invalid') and 'segments' not in result


def test_failed_large_pdf_releases_the_only_slot_for_a_normal_upload(env):
    import time
    client,dbm,_,monkeypatch=env
    from app.services.assistant import files
    migrate(dbm);sid=session(client)
    monkeypatch.setattr(files.settings,'assistant_file_parse_memory_mb',128)
    monkeypatch.setattr(files.settings,'assistant_file_parse_concurrency',1)
    monkeypatch.setattr(files.settings,'assistant_file_parse_queue_limit',1)
    upload=client.post(f'/api/assistant/sessions/{sid}/files',files={'file':('expansion.pdf',compressed_pdf())})
    assert upload.status_code==200
    failed=ready(client,upload.json()['id'])
    assert failed['parse_status']=='failed' and failed['error_code'] in ('parse_memory_limit','pdf_invalid')
    for _ in range(100):
        with files.JOB_LOCK: busy=bool(files.JOBS)
        if not busy:break
        time.sleep(.02)
    assert not busy
    upload=client.post(f'/api/assistant/sessions/{sid}/files',files={'file':('normal.txt',b'small synthetic file')})
    assert upload.status_code==200
    assert ready(client,upload.json()['id'])['parse_status']=='ready'

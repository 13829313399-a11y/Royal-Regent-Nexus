import io
import json
import subprocess
import time
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, NumberObject, RectangleObject

from app.core.config import settings
from app.services.document_tools import image_translation as engine, pipeline, job_service as jobs
from app.services.document_tools.document_ir import Cancelled, ToolError
from app.services.document_tools import translation_engine
from test_document_tools_jobs import runtime, upload


def picture(format="PNG", size=(300, 180)):
    data = io.BytesIO()
    Image.new("RGB", size, "white").save(data, format=format)
    return data.getvalue()


@pytest.fixture
def image_runtime(monkeypatch):
    monkeypatch.setattr(engine, "runtime_status", lambda: {"available": True, "reason": ""})
    monkeypatch.setattr(translation_engine.local, "document_translation_status", lambda _: {"available": True})

    def process(pages, options, work, progress, cancelled):
        values = []
        for index, page in enumerate(pages):
            if cancelled():
                raise Cancelled()
            with Image.open(page["input"]) as source:
                result = source.convert("RGB")
            ImageDraw.Draw(result).rectangle((0, 0, min(30, result.width - 1), min(30, result.height - 1)), fill="red")
            result.save(page["output"])
            values.append({"event": "page", "index": index, "status": "completed", "record": {"translations": [{"sourceText": "Hello 123", "translatedText": "你好 123"}]}})
        return values
    monkeypatch.setattr(engine, "run_node", process)


def translated(runtime, name="source.png", data=None):
    client, sessions, _ = runtime
    source = upload(client, name, data or picture())
    pipeline.run_one(sessions)
    assert client.get(f'/api/tools/sources/{source["source_id"]}').json()["inspection_status"] == "succeeded"
    created = client.post('/api/tools/jobs', json={"source_id": source["source_id"], "operation": "image_translate",
        "options": {"translation_direction": "en_to_zh"}, "client_request_id": jobs.uid()})
    assert created.status_code == 202, created.text
    pipeline.run_one(sessions)
    job = client.get('/api/tools/jobs/' + created.json()["job_id"]).json()
    assert job["execution_status"] == "succeeded", job
    return source, job


@pytest.mark.parametrize("extension,format", [("png", "PNG"), ("jpg", "JPEG"), ("jpeg", "JPEG"), ("webp", "WEBP")])
def test_image_upload_and_lossless_pdf_download(runtime, image_runtime, extension, format):
    client, _, _ = runtime
    source, job = translated(runtime, f"example.{extension}", picture(format))
    assert job["options"]["translation_direction"] == "en_to_zh"
    output = next(a for a in job["artifacts"] if a["role"] == "result")
    response = client.get(f'/api/tools/artifacts/{output["id"]}/download')
    pdf = PdfReader(io.BytesIO(response.content))
    assert len(pdf.pages) == 1
    assert tuple(map(float, pdf.pages[0].mediabox)) == (0, 0, 300, 180)
    assert pdf.pages[0]["/Resources"]["/XObject"]["/Im0"]["/Filter"] == "/FlateDecode"
    assert any(a["role"] == "source_page" for a in job["artifacts"])
    assert client.get('/api/tools/jobs?operation=image_translate').json()["total"] == 1


def test_all_image_endpoints_are_owner_scoped(runtime, image_runtime):
    client, _, account = runtime
    source, job = translated(runtime)
    account.id = "bob"
    for path in (f'/sources/{source["source_id"]}', f'/jobs/{job["id"]}', f'/jobs/{job["id"]}/result'):
        assert client.get('/api/tools' + path).status_code == 404
    for suffix in ('cancel', 'retry'):
        assert client.post(f'/api/tools/jobs/{job["id"]}/{suffix}').status_code == 404
    assert client.post(f'/api/tools/jobs/{job["id"]}/revise', json={"base_revision": 1, "region": {"page_index": 0, "bbox_pt": [20, 20, 90, 90]}}).status_code == 404
    for artifact in job["artifacts"]:
        for suffix in ('download', 'content'):
            assert client.get(f'/api/tools/artifacts/{artifact["id"]}/{suffix}').status_code == 404
    output = next(a for a in job["artifacts"] if a["role"] == "result")
    assert client.post('/api/tools/packages', json={"artifact_ids": [output["id"]], "format": "pdf", "client_request_id": "stolen"}).status_code == 404
    assert client.get('/api/tools/jobs?operation=image_translate').json()["total"] == 0


def test_region_patch_is_new_version_and_preserves_outside_pixels(runtime, image_runtime):
    client, sessions, _ = runtime
    _, original = translated(runtime)
    prior = next(a for a in original['artifacts'] if a['role'] == 'result_page')
    before = client.get(f'/api/tools/artifacts/{prior["id"]}/content').content
    region = {"page_index": 0, "bbox_pt": [100, 60, 200, 140]}
    for invalid in ({**region, "bbox_pt": [100, 60, 400, 140]}, {**region, "page_index": 5}):
        assert client.post(f'/api/tools/jobs/{original["id"]}/revise', json={"base_revision": 1, "region": invalid}).status_code == 422
    assert client.post(f'/api/tools/jobs/{original["id"]}/revise', json={"base_revision": 4, "region": region}).status_code == 409
    response = client.post(f'/api/tools/jobs/{original["id"]}/revise', json={"base_revision": 1, "region": region})
    assert response.status_code == 202
    pipeline.run_one(sessions)
    revised = client.get('/api/tools/jobs/' + response.json()['job_id']).json()
    assert revised['execution_status'] == 'succeeded', revised
    assert revised['revision'] == 2
    output = next(a for a in revised['artifacts'] if a['role'] == 'result_page')
    after = Image.open(io.BytesIO(client.get(f'/api/tools/artifacts/{output["id"]}/content').content))
    assert after.getpixel((110, 70)) == (255, 0, 0)
    assert after.getpixel((50, 50)) == (255, 255, 255)
    assert after.getpixel((5, 5)) == (255, 0, 0)
    assert client.get(f'/api/tools/artifacts/{prior["id"]}/content').content == before


def test_pdf_rotation_page_selection_and_aggregation(runtime, image_runtime):
    client, sessions, _ = runtime
    writer = PdfWriter()
    writer.add_blank_page(200, 300).rotate(90)
    second = writer.add_blank_page(600, 400)
    second.cropbox = RectangleObject([50, 60, 550, 360])
    second[NameObject('/UserUnit')] = NumberObject(2)
    stream = io.BytesIO(); writer.write(stream)
    _, job = translated(runtime, 'two.pdf', stream.getvalue())
    artifact = next(a for a in job['artifacts'] if a['role'] == 'result')
    reader = PdfReader(io.BytesIO(client.get(f'/api/tools/artifacts/{artifact["id"]}/content').content))
    assert [(float(p.mediabox.width), float(p.mediabox.height)) for p in reader.pages] == [(300, 200), (1000, 600)]
    _, other = translated(runtime, 'image.png')
    other_file = next(a for a in other['artifacts'] if a['role'] == 'result')
    created = client.post('/api/tools/packages', json={"artifact_ids": [other_file['id'], artifact['id']], "format": "pdf", "client_request_id": "aggregate"})
    assert created.status_code == 202
    pipeline.run_one(sessions)
    package = client.get('/api/tools/jobs/' + created.json()['job_id']).json()
    assert package['execution_status'] == 'succeeded', package
    combined = next(a for a in package['artifacts'] if a['role'] == 'package')
    result = PdfReader(io.BytesIO(client.get(f'/api/tools/artifacts/{combined["id"]}/download').content))
    assert [(float(p.mediabox.width), float(p.mediabox.height)) for p in result.pages] == [(300, 180), (300, 200), (1000, 600)]


def test_region_patch_retains_other_pages_review_issues(tmp_path, image_runtime, monkeypatch):
    from app.services.document_tools.document_ir import Issue, SourceAnchor
    monkeypatch.setattr(settings,'document_tools_storage_dir',str(tmp_path))
    source=tmp_path/'two.pdf'
    writer=PdfWriter(); writer.add_blank_page(200,300); writer.add_blank_page(200,300); writer.write(source)
    parent=engine.convert_image_translation(source,{},tmp_path/'parent',lambda *a:None,lambda:False)
    parent.ir.issues.append(Issue(id='empty-1',code='NO_TEXT',message='保留原图',source=SourceAnchor(page_index=1)))
    process=engine.run_node
    def no_text(*args):
        result=process(*args)
        result[0]['status']='no-translatable-text'
        return result
    monkeypatch.setattr(engine,'run_node',no_text)
    result=engine.convert_image_translation(source,{'_recognize_region':{'page_index':0,'bbox_pt':[20,20,80,80]}},
        tmp_path/'child',lambda *a:None,lambda:False,parent_ir=parent.ir)
    assert any(i.code=='NO_TEXT' and i.source.page_index==1 for i in result.ir.issues)
    assert any(i.code=='NO_TEXT' and i.source.page_index==0 and '选区' in i.message for i in result.ir.issues)
    assert len({i.id for i in result.ir.issues})==len(result.ir.issues)


@pytest.mark.parametrize('payload,code', [(b'not an image', 'INVALID_IMAGE'), (picture('JPEG'), 'INVALID_IMAGE')])
def test_invalid_image_never_becomes_ready(runtime, payload, code):
    client, sessions, _ = runtime
    source = upload(client, 'spoofed.png', payload)
    pipeline.run_one(sessions)
    job = client.get('/api/tools/jobs/' + source['inspection_job_id']).json()
    assert job['execution_status'] == 'failed'
    assert job['error_code'] == code


def test_image_pixel_limit_and_runtime_not_ready(runtime, monkeypatch):
    client, sessions, _ = runtime
    monkeypatch.setattr(settings, 'image_translation_max_pixels', 100)
    source = upload(client, 'oversize.png', picture())
    pipeline.run_one(sessions)
    assert client.get('/api/tools/jobs/' + source['inspection_job_id']).json()['error_code'] == 'IMAGE_PIXEL_LIMIT'
    monkeypatch.setattr(settings, 'image_translation_max_pixels', 16_000_000)
    source = upload(client, 'image.png', picture())
    pipeline.run_one(sessions)
    monkeypatch.setattr(engine, 'runtime_status', lambda: {'available': False, 'reason': '请联系管理员'})
    response = client.post('/api/tools/jobs', json={'source_id': source['source_id'], 'operation': 'image_translate', 'client_request_id': 'missing'})
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'IMAGE_RUNTIME_UNAVAILABLE'


def test_total_pdf_pixels_rejected_before_rasterization(tmp_path, image_runtime, monkeypatch):
    file = tmp_path / 'large.pdf'
    writer = PdfWriter(); writer.add_blank_page(1000, 1000); writer.write(file)
    monkeypatch.setattr(settings, 'image_translation_max_total_pixels', 1_000_000)
    with pytest.raises(ToolError) as error:
        engine.convert_image_translation(file, {}, tmp_path / 'work', lambda *a: None, lambda: False)
    assert error.value.code == 'IMAGE_TOTAL_PIXEL_LIMIT'
    assert not list((tmp_path / 'work').glob('source-*.png'))


def test_pdf_selected_page_and_password_are_preserved(runtime, image_runtime):
    client, sessions, _ = runtime
    writer = PdfWriter(); writer.add_blank_page(200, 300); writer.add_blank_page(500, 400)
    writer.encrypt('private-pass')
    data = io.BytesIO(); writer.write(data)
    source = upload(client, 'locked.pdf', data.getvalue())
    pipeline.run_one(sessions)
    assert client.get('/api/tools/sources/' + source['source_id']).json()['inspection_status'] == 'awaiting_input'
    assert client.post('/api/tools/sources/' + source['source_id'] + '/password', json={'password': 'private-pass'}).status_code == 202
    pipeline.run_one(sessions)
    value = client.post('/api/tools/jobs', json={'source_id': source['source_id'], 'operation': 'image_translate', 'options': {'page_selection': '2'}, 'client_request_id': 'selected'})
    assert value.status_code == 202, value.text
    pipeline.run_one(sessions)
    job = client.get('/api/tools/jobs/' + value.json()['job_id']).json()
    assert job['execution_status'] == 'succeeded', job
    artifact = next(a for a in job['artifacts'] if a['role'] == 'result')
    pdf = PdfReader(io.BytesIO(client.get('/api/tools/artifacts/' + artifact['id'] + '/content').content))
    assert len(pdf.pages) == 1 and float(pdf.pages[0].mediabox.width) == 500


def test_cancelled_image_attempt_cannot_publish(runtime, image_runtime, monkeypatch):
    client, sessions, _ = runtime
    source = upload(client, 'image.png', picture())
    pipeline.run_one(sessions)
    value = client.post('/api/tools/jobs', json={'source_id': source['source_id'], 'operation': 'image_translate', 'client_request_id': 'cancelled'})
    job_id = value.json()['job_id']
    fake = engine.run_node
    def cancel(*args):
        assert client.post('/api/tools/jobs/' + job_id + '/cancel').status_code == 200
        return fake(*args)
    monkeypatch.setattr(engine, 'run_node', cancel)
    pipeline.run_one(sessions)
    job = client.get('/api/tools/jobs/' + job_id).json()
    assert job['execution_status'] == 'cancelled' and job['artifacts'] == []


@pytest.mark.parametrize('mode', ['cancel', 'timeout', 'protocol'])
def test_silent_child_is_reaped_and_failures_are_safe(tmp_path, monkeypatch, mode):
    runner = tmp_path / 'worker.mjs'
    runner.write_text("setInterval(()=>{},1000);" if mode != 'protocol' else "process.stdout.write('secret path is not JSON\\n');setInterval(()=>{},1000);", encoding='utf-8')
    monkeypatch.setattr(settings, 'image_translation_runner', str(runner))
    monkeypatch.setattr(settings, 'image_translation_timeout_seconds', .4 if mode == 'timeout' else 10)
    created = []
    original = subprocess.Popen
    def launch(*args, **kwargs):
        process = original(*args, **kwargs)
        created.append(process)
        return process
    monkeypatch.setattr(engine.subprocess, 'Popen', launch)
    start = time.monotonic()
    with pytest.raises(ToolError) as error:
        engine.run_node([], {}, tmp_path, lambda *a: None, lambda: mode == 'cancel' and time.monotonic() - start > .3)
    assert error.value.code == {'cancel': 'CANCELLED', 'timeout': 'IMAGE_TIMEOUT', 'protocol': 'IMAGE_PROCESSING_FAILED'}[mode]
    assert 'secret' not in error.value.message and str(tmp_path) not in error.value.message
    assert created and created[0].poll() is not None
    assert time.monotonic() - start < 5

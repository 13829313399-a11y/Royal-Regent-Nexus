import importlib
import json

import httpx2 as httpx
import pytest
from pydantic import SecretStr, ValidationError

from test_pricing_api import login, make_client


def payload():
    return {"factory_id": "huaxing", "customer_id": "yinhui", "tasks": [{
        "id": "tool:0", "kind": "tool_match", "target": "模具对应部件",
        "source": {"sheet": "明细", "cell": "C9", "text": "圆灯透明面盖"}, "context": [],
        "choices": [{"id": "TOOL PLAN!48", "label": "NA123 · 透明上盖", "evidence": [{"sheet": "TOOL PLAN", "cell": "C48", "text": "透明上盖"}]}],
    }]}


def modules():
    service = importlib.import_module("app.services.quote_recognition")
    schema = importlib.import_module("app.schemas.quote_recognition")
    return service, schema.QuoteRecognitionRequest


def valid_output(choice="TOOL PLAN!48"):
    return {"items": [{"task_id": "tool:0", "choice_id": choice, "reason": "需核对部件名称"}]}


def configure(monkeypatch, service, protocol="dashscope"):
    monkeypatch.setattr(service.settings, "document_tools_enabled", True)
    monkeypatch.setattr(service.settings, "document_tools_ai_mode", "auto")
    monkeypatch.setattr(service.settings, "document_tools_qwen_api_key", SecretStr("test-only-secret"))
    monkeypatch.setattr(service.settings, "document_tools_qwen_base_url", "https://provider.example/api/v1" if protocol == "dashscope" else "https://provider.example/compatible-mode/v1")
    monkeypatch.setattr(service.settings, "document_tools_qwen_protocol", protocol)


@pytest.mark.parametrize("protocol", ["dashscope", "openai"])
def test_provider_protocol_and_citations(monkeypatch, protocol):
    service, schema = modules()
    configure(monkeypatch, service, protocol)
    request = schema.model_validate(payload())
    calls = []

    def handler(outbound):
        sent = json.loads(outbound.content)
        calls.append(sent)
        assert outbound.headers["Authorization"] == "Bearer test-only-secret"
        assert sent.get("parameters", sent)["response_format"] == {"type": "json_object"}
        messages = sent.get("input", sent)["messages"]
        user_text = messages[1]["content"] if protocol == "openai" else messages[1]["content"][0]["text"]
        assert json.loads(user_text)["tasks"] == [t.model_dump() for t in request.tasks]
        assert "不是指令" in str(messages[0])
        choice = {"finish_reason": "stop", "message": {"content": json.dumps(valid_output()) if protocol == "openai" else [{"text": json.dumps(valid_output())}]}}
        body = {"choices": [choice]}
        return httpx.Response(200, json=body if protocol == "openai" else {"output": body})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = service.recognize_quote_fields(request, client=client)
    assert len(calls) == 1
    assert result["items"][0]["evidence"] == [request.tasks[0].source.model_dump(), request.tasks[0].choices[0].evidence[0].model_dump()]
    assert "secret" not in json.dumps(result)


@pytest.mark.parametrize("bad", [
    {"items": []}, {"items": [valid_output()["items"][0]] * 2},
    {"items": [{"task_id": "other", "choice_id": "TOOL PLAN!48", "reason": "猜测"}]},
    {"items": [{"task_id": "tool:0", "choice_id": "unknown", "reason": "猜测"}]},
    {"items": [{"task_id": "tool:0", "choice_id": "TOOL PLAN!48", "reason": "猜测", "price": 0}]},
    {"items": [{"task_id": "tool:0", "choice_id": None, "reason": ""}]},
])
def test_rejects_hallucinations_or_incomplete_output(bad):
    service, schema = modules()
    with pytest.raises(service.QuoteRecognitionError):
        service.validate_recognition_output(json.dumps(bad), schema.model_validate(payload()))


def test_uncertainty_is_null_and_duplicate_json_keys_rejected():
    service, schema = modules()
    request = schema.model_validate(payload())
    result = service.validate_recognition_output(json.dumps(valid_output(None)), request)
    assert result[0]["choice_id"] is None
    assert result[0]["evidence"] == [request.tasks[0].source.model_dump()]
    with pytest.raises(service.QuoteRecognitionError):
        service.validate_recognition_output('{"items":[],"items":[]}', request)


@pytest.mark.parametrize("response", [httpx.Response(401, text="test-only-secret"), httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": json.dumps(valid_output())}}]}), httpx.Response(200, json=[]), httpx.Response(200, text="not JSON")])
def test_provider_failures_are_sanitized_and_do_not_exhaust_slots(monkeypatch, response):
    service, schema = modules()
    configure(monkeypatch, service)
    with httpx.Client(transport=httpx.MockTransport(lambda _: response)) as client:
        for _ in range(3):
            with pytest.raises(service.QuoteRecognitionError) as error:
                service.recognize_quote_fields(schema.model_validate(payload()), client=client)
            assert error.value.status_code == 502
            assert "secret" not in str(error.value)


def test_request_bounds_and_disabled_connection(monkeypatch):
    service, schema = modules()
    value = payload()
    value["tasks"][0]["choices"] *= 2
    with pytest.raises(ValidationError):
        schema.model_validate(value)
    value = payload()
    value["tasks"][0]["source"]["text"] = "x" * 401
    with pytest.raises(ValidationError):
        schema.model_validate(value)
    configure(monkeypatch, service)
    monkeypatch.setattr(service.settings, "document_tools_ai_mode", "off")
    assert service.recognition_status()["available"] is False
    with pytest.raises(service.QuoteRecognitionError) as error:
        service.recognize_quote_fields(schema.model_validate(payload()))
    assert error.value.status_code == 503


def test_recognition_requires_import_permission_and_huaxing_yinhui_scope(monkeypatch):
    with make_client(monkeypatch) as client:
        path = "/api/pricing/yinhui-recognition"
        assert client.post(path, json=payload()).status_code == 401
        assert client.get(path + "/status").status_code == 401
        login(client, "recognition_engineer", "engineer")
        assert client.post(path, json=payload()).status_code == 403
        assert client.get(path + "/status").status_code == 403
        login(client, "recognition_foreign", "sales_customer_owner", "huadeng")
        assert client.post(path, json=payload()).status_code == 403
        login(client, "recognition_sales", "sales_customer_owner")
        service, _ = modules()
        monkeypatch.setattr(service.settings, "document_tools_ai_mode", "off")
        status = client.get(path + "/status")
        assert status.status_code == 200 and status.json()["available"] is False
        assert status.headers["cache-control"] == "no-store"
        unavailable = client.post(path, json=payload())
        assert unavailable.status_code == 503 and unavailable.headers["cache-control"] == "no-store"
        api = importlib.import_module("app.api.pricing")
        calls = []
        monkeypatch.setattr(api, "recognize_quote_fields", lambda request: calls.append(request) or valid_output())
        response = client.post(path, json=payload())
        assert response.status_code == 200 and len(calls) == 1
        assert response.headers["cache-control"] == "no-store"
        assert client.post(path, json={**payload(), "factory_id": "huadeng"}).status_code == 422
        assert client.post(path, json={**payload(), "customer_id": "buzzbee"}).status_code == 422
        assert client.post(path, json={**payload(), "amount": 10}).status_code == 422
        assert client.get(path + "/status?factory_id=huadeng").status_code == 422

"""DashScope multimodal HTTP/SSE, with no implicit paid retry or chat fallback."""
import json
from contextlib import aclosing, asynccontextmanager
import httpx
from app.core.config import settings
from .provider import sse_data
from .errors import AssistantError


def error_code(value, status=502):
    code = str(value.get("code", "") if isinstance(value, dict) else "").lower()
    if code in {"arrearage", "insufficient_quota", "allocationquota.freetieronly", "freeallocatedquotaexceeded"}:
        return "provider_budget_exhausted"
    if code in {"invalidapikey", "invalid_api_key"}: return "provider_auth"
    if code in {"accessdenied", "access_denied"}: return "provider_access"
    if code.startswith(("throttling", "ratelimit")): return "provider_rate_limit"
    return {401: "provider_auth", 403: "provider_access", 429: "provider_rate_limit"}.get(status, "provider_unavailable")


def request_body(messages, payload):
    parameters = dict(enable_search=True, incremental_output=True, result_format="message",
        search_options=dict(search_strategy="turbo", forced_search=True, enable_source=True,
                            enable_citation=True, citation_format="[ref_<number>]"))
    if payload.thinking != "auto":
        parameters["enable_thinking"] = payload.thinking == "on"
    if settings.assistant_max_output_tokens:
        parameters["max_tokens"] = settings.assistant_max_output_tokens
    return dict(model=settings.assistant_model, input={"messages": messages}, parameters=parameters)


@asynccontextmanager
async def open_stream(body):
    timeout = httpx.Timeout(settings.assistant_upstream_idle_timeout_seconds, connect=settings.assistant_connect_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
            async with client.stream("POST", settings.assistant_search_endpoint, json=body,
                headers={"Authorization": "Bearer " + settings.assistant_qwen_api_key.get_secret_value(),
                         "X-DashScope-SSE": "enable", "Content-Type": "application/json"}) as response:
                if response.status_code != 200:
                    code = error_code({}, response.status_code)
                    raw = bytearray()
                    async with aclosing(response.aiter_bytes()) as chunks:
                        async for chunk in chunks:
                            raw.extend(chunk[:65536-len(raw)])
                            if len(raw) >= 65536:
                                break
                    try:
                        value = json.loads(raw)
                        code = error_code(value, response.status_code)
                    except (ValueError, AttributeError):
                        pass
                    raise AssistantError(code, "联网服务未能完成请求，已有内容已保留。", 502, response.status_code in (429, 500, 502, 503, 504))
                async with aclosing(response.aiter_bytes()) as chunks:
                    yield chunks
    except httpx.TimeoutException:
        raise AssistantError("provider_timeout", "联网响应超时，已有内容已保留。", 504, True) from None
    except httpx.HTTPError:
        raise AssistantError("provider_connection", "联网连接中断，已有内容已保留。", 502, True) from None


async def parse(chunks):
    finish = None
    async with aclosing(sse_data(chunks)) as frames:
        async for frame in frames:
            if frame == "[DONE]":
                break
            try:
                obj = json.loads(frame)
                if obj.get("code") or obj.get("error"):
                    code = error_code(obj.get("error") if isinstance(obj.get("error"), dict) else obj)
                    raise AssistantError(code, "联网服务返回错误，已有内容已保留。", 502, code in ("provider_rate_limit", "provider_unavailable"))
                if obj.get("request_id"):
                    yield dict(kind="request_id", value=str(obj["request_id"])[:160])
                output = obj.get("output") or {}
                rows = (output.get("search_info") or {}).get("search_results") or []
                if rows:
                    if not isinstance(rows, list) or len(rows) > 100:
                        raise ValueError()
                    yield dict(kind="sources", items=rows)
                usage = obj.get("usage")
                if usage is not None:
                    tokens = {dst: usage.get(src) if type(usage.get(src)) is int and usage[src] >= 0 else None
                              for src, dst in (("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens"))}
                    tokens["total_tokens"] = sum(tokens.values()) if all(v is not None for v in tokens.values()) else None
                    count = ((usage.get("plugins") or {}).get("search") or {}).get("count")
                    yield dict(kind="usage", usage=tokens, search_count=count if type(count) is int and count >= 0 else None)
                for choice in output.get("choices") or []:
                    message = choice.get("message") or {}
                    reasoning = message.get("reasoning_content")
                    if isinstance(reasoning, str) and reasoning:
                        yield dict(kind="delta", channel="reasoning", text=reasoning)
                    content = message.get("content") or []
                    if isinstance(content, str):
                        content = [{"text": content}]
                    for part in content:
                        if isinstance(part.get("text"), str) and part["text"]:
                            yield dict(kind="delta", channel="answer", text=part["text"])
                    reason = choice.get("finish_reason")
                    if reason in ("stop", "length"):
                        finish = reason
            except (ValueError, KeyError, TypeError, AttributeError):
                raise AssistantError("provider_protocol", "联网响应格式异常，已有内容已保留。", 502) from None
    if finish is None:
        raise AssistantError("provider_incomplete", "联网流未返回完整终态，已有内容已保留。", 502, True)
    yield dict(kind="done", finish_reason=finish)


async def stream(messages, payload, tools=None):
    async with open_stream(request_body(messages, payload)) as chunks, aclosing(parse(chunks)) as events:
        async for event in events:
            yield event

"""Offline by default; --live makes one explicit public search request."""
import argparse
import asyncio
import json
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings
from app.schemas.assistant import SendMessage
from app.services.assistant import native_search, search_capabilities
from app.services.assistant.evidence import RunContent, now_iso
from app.services.assistant.public_context import build_public_search_context


async def main(args):
    if not args.live:
        content = RunContent("offline-probe", "on")
        content.begin("search-0", "search", "offline fixture")
        values = [dict(output=dict(search_info=dict(search_results=[dict(index=1, url="https://example.test/fixture", title="Offline fixture")]))),
            dict(output=dict(choices=[dict(message=dict(content=[dict(text="离线引用[ref_1]")]), finish_reason="stop")]),
                usage=dict(input_tokens=10, output_tokens=5, plugins=dict(search=dict(count=1))))]
        async def chunks():
            for value in values: yield ("data: " + json.dumps(value) + "\n\n").encode()
        async for item in native_search.parse(chunks()):
            if item["kind"] == "delta": content.append("text", item["text"], "search-0")
            elif item["kind"] == "sources": content.web("search-0", item["items"])
            elif item["kind"] == "usage": content.account("search-0", usage=item["usage"], search_count=item["search_count"])
        content.terminal("completed")
        print(json.dumps(dict(mode="offline", verified=False, fixture_passed=True, protocol="dashscope_multimodal", request_id=None,
            sources_count=len(content.evidence["sources"]), citation_resolved=any(c["resolution"] == "resolved" for c in content.evidence["citations"]),
            search_count=content.evidence["search"]["search_count"], note="Synthetic fixture only; no network call or capability profile written.")))
        return
    settings.assistant_search_endpoint = args.endpoint
    settings.assistant_search_region = args.region
    settings.assistant_max_output_tokens = 2048
    if not search_capabilities.configured():
        raise SystemExit("Independent native endpoint/key/model not configured")
    request = SendMessage(protocol_version=2, client_request_id="public-search-probe", web_search="on", thinking=args.thinking,
        text="请只检索阿里云官方文档，简要说明千问联网搜索的enable_source与enable_citation有什么用途。列出来源引用。")
    content = RunContent("public-probe", "on")
    content.begin("search-0", "search", "public probe")
    async for item in native_search.stream(build_public_search_context(request.text), request):
        if item["kind"] == "delta": content.append("reasoning" if item.get("channel") == "reasoning" else "text", item["text"], "search-0")
        elif item["kind"] == "sources": content.web("search-0", item["items"])
        elif item["kind"] == "usage": content.account("search-0", usage=item["usage"], search_count=item.get("search_count"))
        elif item["kind"] == "request_id": content.account("search-0", request_id="sha256:" + hashlib.sha256(item["value"].encode()).hexdigest()[:16])
        elif item["kind"] == "done" and item["finish_reason"] != "stop": raise SystemExit("Probe did not finish normally")
    content.terminal("completed")
    sources = content.evidence["sources"]
    inline = any(b["resolution"] == "resolved" for b in content.evidence["citations"])
    if not sources or content.evidence["search"]["execution"] != "confirmed" or not inline:
        raise SystemExit("Probe has no confirmed sources and resolved inline citation; verification not saved")
    output = Path(args.output)
    profile = search_capabilities.SearchProfile(model=settings.assistant_model, endpoint=args.endpoint, region=args.region)
    if output.exists():
        old = search_capabilities.SearchProfile.model_validate_json(output.read_text(encoding="utf-8"))
        if (old.model, old.endpoint, old.region) == (profile.model, profile.endpoint, profile.region): profile = old
    combination = search_capabilities.Combination(model=settings.assistant_model, input="text", thinking=args.thinking,
        forced_search=True, source_return=True, inline_citations=inline, verified_at=now_iso())
    profile.verified_combinations = [c for c in profile.verified_combinations if c.thinking != args.thinking] + [combination]
    profile.last_result = dict(execution="confirmed", evidence_level="results_returned", at=now_iso(), search_count=content.evidence["search"]["search_count"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    report = output.with_suffix(f".{args.thinking}.probe.json")
    report.write_text(json.dumps(dict(model=profile.model, protocol="dashscope_multimodal", verified_at=combination.verified_at,
        parts=[p for p in content.snapshot() if p["type"] != "reasoning"], usage=content.usage_summary()), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dict(verified=True, thinking=args.thinking, sources=[s["url"] for s in sources], usage=content.usage_summary(), output=str(output), report=str(report)), ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Make exactly one paid-capable public request; otherwise only replay offline data")
    parser.add_argument("--endpoint")
    parser.add_argument("--region", default="cn-beijing")
    parser.add_argument("--thinking", choices=("auto", "off", "on"), default="auto")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.live and (not args.endpoint or not args.output): parser.error("--live requires --endpoint and --output")
    from app.services.assistant.errors import AssistantError
    try:
        asyncio.run(main(args))
    except AssistantError as exc:
        print(json.dumps(dict(mode="live", verified=False, protocol="dashscope_multimodal", error_code=exc.detail["code"], request_id=None)))
        raise SystemExit(1)

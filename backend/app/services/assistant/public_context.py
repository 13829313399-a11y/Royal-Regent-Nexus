"""A deliberately narrow input boundary. This module never accepts model history."""
import re
from .errors import AssistantError


def wants_search(payload):
    if payload.web_search == "off":
        return False
    if payload.web_search == "on":
        return True
    return payload.intent == "research" or bool(re.search(r"联网|查证|最新|当前.*(?:官方|规格|版本)|今天.*(?:新闻|天气)|搜索", payload.text))


def build_public_search_context(public_query: str):
    query = public_query.strip()
    if not query or len(query) > 4000:
        raise AssistantError("public_query_required", "请填写不含内部记录的公开检索问题（4000字以内）。")
    return [{"role": "user", "content": [{"text": query}]}]

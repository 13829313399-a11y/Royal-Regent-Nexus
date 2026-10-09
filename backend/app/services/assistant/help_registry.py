"""Server-only, audience-filtered source-backed help. Never scrapes business DOM."""
import hashlib
import json
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.core.config import BACKEND_DIR
from .errors import AssistantError

ROOT = BACKEND_DIR.parent
HELP_DIR = ROOT / "shared" / "assistant-help"
if not HELP_DIR.exists():
    HELP_DIR = BACKEND_DIR / "shared" / "assistant-help"


class Source(BaseModel):
    path: str
    symbol: str
    sha256: str


class Step(BaseModel):
    title: str
    description: str
    anchor_id: str
    precondition: str = "当前页面可见且目标已注册"
    completion: str = "目标已显示；业务操作由你确认"


class Article(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    module_id: str
    title: str
    kind: Literal["overview", "field", "workflow", "state"]
    audience: Literal["internal", "supplier", "all"]
    route_names: list[str]
    factory_ids: list[str] = Field(default_factory=list)
    anchor_id: str
    field_keys: list[str] = Field(default_factory=list)
    summary: str
    content: str
    steps: list[Step] = Field(default_factory=list)
    source_refs: list[Source]
    knowledge_version: str
    verified_commit: str
    status: Literal["verified", "partial", "unavailable", "needs_review"]


def supplier_only(user):
    codes = user.permissions
    return bool(any(p.startswith("carton_supplier:") for p in codes)
                and not any(p != "*" and not p.startswith("carton_supplier:") for p in codes)
                and "*" not in codes)


def articles():
    result = []
    for path in sorted((HELP_DIR / "modules").glob("*.json")):
        for item in json.loads(path.read_text(encoding="utf-8")):
            article = Article.model_validate(item)
            for source in article.source_refs:
                path = ROOT / source.path
                if not path.is_file() or hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != source.sha256:
                    article.status = "needs_review"
            result.append(article)
    if len({a.id for a in result}) != len(result):
        raise AssistantError("help_invalid", "本页说明需要维护。", 503)
    return result


def visible(user):
    supplier = supplier_only(user)
    return [a for a in articles() if a.audience == "all" or a.audience == ("supplier" if supplier else "internal")]


def public(article):
    data = article.model_dump(exclude={"source_refs", "verified_commit"})
    data["source_label"] = f"系统操作说明 · {article.knowledge_version}"
    return data


def get(user, help_id):
    article = next((a for a in visible(user) if a.id == help_id), None)
    if article is None:
        raise AssistantError("help_not_found", "这里还没有可用的精确说明。", 404)
    return article


def context(user, page):
    candidates = [a for a in visible(user) if a.module_id == page.module_id and page.route_name in a.route_names]
    if not candidates:
        raise AssistantError("context_unavailable", "本页说明尚未接入或当前身份不可查看。", 422)
    candidates = [a for a in candidates if not a.factory_ids or page.factory_id in a.factory_ids]
    if not candidates:
        raise AssistantError("factory_unavailable", "当前厂区没有这个模块的已验证业务入口。", 422)
    if page.help_id:
        candidates = [a for a in candidates if a.id == page.help_id]
        if not candidates:
            raise AssistantError("help_not_found", "目标说明与当前页面不匹配。", 422)
    return candidates


TOOLS = [{"type": "function", "function": {"name": name, "description": description,
    "parameters": {"type": "object", "properties": {key: {"type": "string", "maxLength": 200}}, "required": [key], "additionalProperties": False}}}
    for name, key, description in (
        ("help_search", "query", "搜索当前身份可见的系统说明，不查询实际业务数据"),
        ("help_describe_element", "help_id", "读取注册元素的规则说明"),
        ("help_get_walkthrough", "help_id", "读取只读操作引导；不执行业务操作"))]


def tool(user, name, arguments):
    keys = {"help_search": "query", "help_describe_element": "help_id", "help_get_walkthrough": "help_id"}
    key = keys.get(name)
    if not key or not isinstance(arguments, dict) or set(arguments) != {key} or not isinstance(arguments[key], str) or len(arguments[key]) > 200:
        raise AssistantError("tool_invalid", "模型请求了不可用的操作。")
    if name == "help_search":
        q = arguments[key].strip().lower()
        found = [a for a in visible(user) if q in (a.title + a.summary + a.content).lower()][:6]
    else:
        found = [get(user, arguments[key])]
    return [public(a) for a in found]

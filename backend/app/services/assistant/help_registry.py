"""Server-only, audience-filtered source-backed help. Never scrapes business DOM."""
import hashlib
import json
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr
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
    _source_checks: list[dict] = PrivateAttr(default_factory=list)
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
            if not article.source_refs:
                article.status = "needs_review"
            for source in article.source_refs:
                current_hash = None
                symbol_found = False
                try:
                    target = (ROOT / source.path).resolve()
                    if target.is_relative_to(ROOT.resolve()) and target.is_file():
                        content = target.read_bytes().replace(b"\r\n", b"\n")
                        current_hash = hashlib.sha256(content).hexdigest()
                        symbol_found = source.symbol.encode("utf-8") in content
                except OSError:
                    pass  # Unreadable source cannot establish a verified guide.
                matches = current_hash == source.sha256 and symbol_found
                article._source_checks.append(dict(path=source.path, symbol=source.symbol,
                    expected_sha256=source.sha256, current_sha256=current_hash, matches=matches))
                if not matches:
                    article.status = "needs_review"
            result.append(article)
    if len({a.id for a in result}) != len(result):
        raise AssistantError("help_invalid", "本页说明需要维护。", 503)
    return result


def visible(user):
    supplier = supplier_only(user)
    return [a for a in articles() if a.audience == "all" or a.audience == ("supplier" if supplier else "internal")]


def fingerprint(article):
    return hashlib.sha256(json.dumps(article.model_dump(), ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def public(article, *, verification=False):
    data = article.model_dump(exclude={"source_refs", "verified_commit"})
    data["source_label"] = f"系统操作说明 · {article.knowledge_version}"
    data["source_fingerprint"] = fingerprint(article)
    if not verification:
        return data
    # Bind content, steps, routes and expected source versions, not just a manually
    # maintained version label. Current source hashes remain separately inspectable.
    data["verification"] = dict(fingerprint=data["source_fingerprint"], verified_commit=article.verified_commit,
                              sources=article._source_checks)
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


def model_context(user, page, *, strict=False):
    candidates = [a for a in context(user, page) if a.status == "verified"]
    if strict and not candidates:
        raise AssistantError("help_needs_review", "这份系统说明需要重新核对，暂不能作为当前规则。你仍可自由提问。", 409)
    return candidates


def citation(article):
    data = public(article) if isinstance(article, Article) else article
    return dict(id=data['id'], version=data['knowledge_version'], source_fingerprint=data['source_fingerprint'])


def matches(article, reference):
    # Old records remain readable at their recorded version, but are explicitly
    # version-only: never invent the missing historical content fingerprint.
    return (article.status == 'verified'
        and article.knowledge_version == reference.get('version', reference.get('knowledge_version'))
        and (reference.get('source_fingerprint') is None
             or reference['source_fingerprint'] == fingerprint(article)))


def references_current(user, references):
    if not references:
        return True
    known = {a.id:a for a in visible(user)}
    return all((a := known.get(ref.get('id', ref.get('help_id')))) is not None and matches(a, ref)
               for ref in references)


def require_references(user, references):
    if not references_current(user, references):
        raise AssistantError('help_changed', '回答所依据的系统说明已变化或不再可用，请重新读取说明后提问。', 409)


def source(article, run_id):
    from .evidence import stable_id
    return dict(kind='help', source_id=stable_id(run_id,'help',article['id'],article.get('source_fingerprint') or article['knowledge_version']),
        run_id=run_id, title=article['title'], help_id=article['id'], knowledge_version=article['knowledge_version'],
        source_fingerprint=article.get('source_fingerprint'), route_name=article['route_names'][0], anchor_id=article['anchor_id'])


def source_from_reference(user, reference, run_id):
    article = get(user, reference['id'])
    if not matches(article, reference):
        raise AssistantError('help_changed', '这份历史说明的版本已失效。', 409)
    data = public(article)
    data['source_fingerprint'] = reference.get('source_fingerprint')
    return source(data, run_id)


def highlight_action(article):
    return dict(type='highlight', help_id=article['id'], label='定位：'+article['title'],
                knowledge_version=article['knowledge_version'], source_fingerprint=article['source_fingerprint'])


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
        found = [a for a in visible(user) if a.status == 'verified' and q in (a.title + a.summary + a.content).lower()][:6]
    else:
        found = [get(user, arguments[key])]
        if found[0].status != 'verified':
            raise AssistantError('help_needs_review', '这份说明可能已过时，请等待重新核对；不能把旧规则作为当前依据。', 409)
    return [public(a) for a in found]

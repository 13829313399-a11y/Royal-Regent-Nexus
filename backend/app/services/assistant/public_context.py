"""Public planning accepts an already-public topic, never a private transcript."""
import re
from .errors import AssistantError

_OPT_OUT = re.compile(r"不要(?:再)?(?:联网|搜索)|不(?:用|要)?联网|离线回答|do\s+not\s+(?:search|browse)|don['’]?t\s+(?:search|browse)|without\s+(?:web|internet|browsing)|no\s+web\s+search", re.I)
_CURRENT = re.compile(r"联网|查证|最新|当前.*(?:官方|规格|版本)|今天.*(?:新闻|天气)|搜索|https?://|\b(?:latest|current|today|news|weather|search|browse|official\s+(?:guidance|specifications?|version|documentation))\b", re.I)
_FOLLOWUP = re.compile(r"它|这个|这些|上述|前者|后者|相比|继续|\b(?:it|its|they|their|those|that|compare|comparison|versus)\b", re.I)
_PRIVATE_HINT = re.compile(r"内部(?:订单|资料|文件|报价|记录)|订单号|客户名称|员工姓名|工号|\b(?:SYN|ORD|INV)[-_][A-Z0-9_-]+|\b(?:internal|private)\s+(?:order|record|file|customer)\b", re.I)


def direct_urls(query):
    # Only user-supplied public terms; never URLs discovered inside fetched text.
    return list(dict.fromkeys(u.rstrip(".,;!?，。；！？、") for u in re.findall(r"https?://[^\s<>\"'）)\]】]+", query)))[:3]


def wants_search(payload, public_topic=""):
    if payload.web_search == "off" or _OPT_OUT.search(payload.text):
        return False
    if payload.web_search == "on":
        return True
    return payload.intent == "research" or bool(_CURRENT.search(payload.text)) or bool(public_topic and _FOLLOWUP.search(payload.text))


def plan(payload, *, private_history=False, public_topic=""):
    if not wants_search(payload, public_topic):
        return dict(search=False, query=None, public_topic=None, reason="explicit_off" if payload.web_search == "off" or _OPT_OUT.search(payload.text) else "not_needed")
    selection = payload.context_selection
    explicit = selection.filters.get("public_query") if selection else None
    private = private_history or payload.document_ids or payload.attachment_ids or payload.intent == "my_work" or bool(selection and (selection.resources or set(selection.filters) - {"public_query"})) or _PRIVATE_HINT.search(payload.text)
    if private and (not isinstance(explicit, str) or not explicit.strip()):
        raise AssistantError("public_query_required", "本轮含私有工作或资料。请单独填写公开检索词，或关闭联网继续分析。")
    query = explicit.strip() if isinstance(explicit, str) and explicit.strip() else payload.text.strip()
    if _PRIVATE_HINT.search(query):
        raise AssistantError("public_query_required", "公开检索词仍含内部记录标识，请移除订单、客户或文件标识后再提交。")
    topic = query
    if not explicit and public_topic and _FOLLOWUP.search(query):
        topic = public_topic
        query = f"已确认的公开主题：{public_topic}\n本次追问：{query}"
    build_public_search_context(query)  # One bound shared by planning and transport.
    return dict(search=True, query=query, public_topic=topic, urls=direct_urls(query), reason="explicit_on" if payload.web_search == "on" else "public_topic")


def previous_topic(db, user, sid, rid):
    from sqlalchemy import select
    from app.models.assistant import AssistantRun as Run, AssistantMessage as Message
    from . import service
    service.owned(db, user, sid)
    rows = db.scalars(select(Run).where(Run.session_id == sid, Run.id != rid, Run.state == "completed").order_by(Run.started_at.desc()).limit(20))
    for row in rows:
        execution = (row.context_window or {}).get("execution_v3") or {}
        topic = execution.get("public_topic")
        if not isinstance(topic, str) or not topic or len(topic) > 4000:
            continue
        answer = db.scalar(select(Message).where(Message.run_id == row.id, Message.role == "assistant"))
        if answer and not service.message_out(answer, user).get("unavailable"):
            return topic
    return ""


def build_public_search_context(public_query: str):
    query = public_query.strip()
    if not query or len(query) > 4000:
        raise AssistantError("public_query_required", "请填写不含内部记录的公开检索问题（4000字以内）。")
    return [{"role": "user", "content": [{"text": query}]}]

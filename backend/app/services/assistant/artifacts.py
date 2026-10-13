"""Private immutable revisions. Source deletion/revocation invalidates every version."""
import csv
from io import StringIO
import re
import time
from uuid import uuid4
from sqlalchemy import select, or_, and_
from app.models.assistant import AssistantArtifact as Artifact, AssistantArtifactVersion as Version, AssistantMessage as Message, AssistantRun as Run, AssistantFavorite as Favorite
from . import service, visibility, files
from .errors import AssistantError
from app import db as database


def visible(db, user, row):
    try:
        service.owned(db, user, row.session_id)
        return visibility.allowed(user, row.source_refs, db)
    except AssistantError:
        return False


def owned(db, user, ident):
    row = db.get(Artifact, ident)
    if not row or row.owner_user_id != user.id or row.employment_epoch != service.epoch(user):
        raise AssistantError("not_found", "成果不存在。", 404)
    if not visible(db, user, row):
        raise AssistantError("source_unavailable", "成果所依赖的会话、文件或权限已失效，所有版本停止读取和导出。", 410)
    return row


def source_lines(refs):
    lines = []
    for i, source in enumerate(refs, 1):
        title = source.get("title", "资料")
        if source["kind"] == "web":
            lines.append(f"{i}. {title} — {source['url']}；检索时间 {source['retrieved_at']}；{source['evidence_level']}")
        elif source["kind"] == "file":
            loc = source["locator"]
            position = f"第{loc['page']}页" if loc["kind"] == "page" else f"第{loc['start']}–{loc['end']}行" if loc["kind"] == "lines" else str(loc)
            lines.append(f"{i}. {title} — {position}；文件 {source['file_ref']['id']}")
        elif source["kind"] == "business":
            lines.append(f"{i}. {title} — {source['scope']['scope_label']}；截至 {source['as_of']}；{source['data_mode']}")
        else:
            lines.append(f"{i}. {title} — 系统说明 {source['help_id']} / {source['knowledge_version']}")
    return "\n".join(lines)


def formats(kind):
    return ["md", "txt", "csv"] if kind in ("checklist", "table") else ["md", "txt"]


def out(db, row, revision=None):
    version = db.get(Version, (row.id, revision or row.current_revision))
    if not version:
        raise AssistantError("not_found", "成果版本不存在。", 404)
    return dict(id=row.id, title=row.title, kind=row.kind, current_revision=row.current_revision, revision=version.revision,
                content=version.content, source_refs=row.source_refs, source_run_id=row.source_run_id,
                export_formats=formats(row.kind), updated_at=row.updated_at)


def create(user, sid, payload):
    files.require_schema()
    with service.transaction() as db:
        service.owned(db, user, sid)
        run = db.get(Run, payload.source_run_id)
        if not run or run.session_id != sid or run.state in service.ACTIVE:
            raise AssistantError("source_unavailable", "请等待回答结束后保存成果。", 409)
        message = db.scalar(select(Message).where(Message.run_id == run.id, Message.role == "assistant"))
        safe = service.message_out(message, user)
        if safe.get("unavailable"):
            raise AssistantError("source_unavailable", "回答所依赖的来源已失效。", 410)
        now = time.time()
        row = Artifact(id=uuid4().hex, owner_user_id=user.id, employment_epoch=service.epoch(user), session_id=sid,
            source_run_id=run.id, kind=payload.kind, title=payload.title.strip(), current_revision=1,
            source_refs=visibility.sources(safe["content_parts"]), created_at=now, updated_at=now)
        db.add(row)
        db.flush()
        db.add(Version(artifact_id=row.id, revision=1, content=payload.content, created_at=now))
        db.flush()
        return out(db, row)


def get(user, ident, revision=None):
    files.require_schema()
    with database.SessionLocal() as db:
        return out(db, owned(db, user, ident), revision)


def revise(user, ident, payload):
    files.require_schema()
    with service.transaction() as db:
        row = owned(db, user, ident)
        if row.current_revision != payload.base_revision:
            raise AssistantError("revision_conflict", "另一窗口已保存新版本。请读取最新版本后合并，不会覆盖你的编辑。", 409)
        row.current_revision += 1
        row.updated_at = time.time()
        db.add(Version(artifact_id=row.id, revision=row.current_revision, content=payload.content, created_at=row.updated_at))
        db.flush()
        return out(db, row)


def listing(user, q="", cursor="", limit=30):
    files.require_schema()
    with database.SessionLocal() as db:
        stmt = select(Artifact).where(Artifact.owner_user_id == user.id, Artifact.employment_epoch == service.epoch(user))
        from .pagination import matching_page
        def render(row):
            if not visible(db, user, row):
                return None
            version = db.get(Version, (row.id, row.current_revision)) if q else None
            if not q or q.casefold() in (row.title + "\n" + (version.content if version else "")).casefold():
                return dict(id=row.id, title=row.title, kind=row.kind, current_revision=row.current_revision, updated_at=row.updated_at)
            return None
        return matching_page(db, Artifact, stmt, cursor, limit, render)


def csv_cell(value):
    value = str(value).strip()
    if value.startswith(("=", "+", "-", "@")) and not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value):
        return "'" + value
    return value


def render(content, kind, title, refs, format):
    if format not in formats(kind):
        raise AssistantError("format_unavailable", "这类成果只支持Markdown和纯文本。")
    sources = source_lines(refs)
    if format == "csv":
        out = StringIO(newline="")
        writer = csv.writer(out)
        if kind == "checklist":
            writer.writerow(["完成", "事项"])
            for line in content.splitlines():
                match = re.match(r"^\s*[-*]\s+\[([ xX])\]\s*(.*)", line)
                if match:
                    writer.writerow(["是" if match[1].lower() == "x" else "否", csv_cell(match[2])])
        else:
            for line in content.splitlines():
                if "|" in line and not re.fullmatch(r"[\s|:\-]+", line):
                    writer.writerow([csv_cell(c) for c in line.strip().strip("|").split("|")])
        writer.writerow([])
        writer.writerow(["来源"])
        for line in sources.splitlines():
            writer.writerow([csv_cell(line)])
        return "\ufeff" + out.getvalue(), "text/csv"
    return f"# {title}\n\n{content}\n\n## 依据\n\n{sources}\n", "text/markdown" if format == "md" else "text/plain"


def export(user, ident, format, revision=None):
    value = get(user, ident, revision)
    return render(value["content"], value["kind"], value["title"], value["source_refs"], format)


def favorite(user, sid, enabled):
    files.require_schema()
    with service.transaction() as db:
        service.owned(db, user, sid)
        row = db.get(Favorite, sid)
        if enabled and not row:
            db.add(Favorite(session_id=sid, owner_user_id=user.id, employment_epoch=service.epoch(user), created_at=time.time()))
        elif not enabled and row:
            db.delete(row)
    return dict(favorite=enabled)

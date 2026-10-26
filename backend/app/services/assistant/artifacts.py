"""Private immutable revisions. Source deletion/revocation invalidates every version."""
import csv
from io import StringIO
import re
import time
from uuid import uuid4
from sqlalchemy import select, or_, and_
from app.models.assistant import AssistantArtifact as Artifact, AssistantArtifactVersion as Version, AssistantMessage as Message, AssistantRun as Run, AssistantFavorite as Favorite
from . import service, visibility, files, help_registry
from .errors import AssistantError
from app import db as database


def visible(db, user, row):
    try:
        service.owned(db, user, row.session_id)
        message = db.scalar(select(Message).where(Message.run_id == row.source_run_id, Message.role == 'assistant'))
        if message is None or service.message_out(message, user).get('unavailable'):
            return False
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
    for i, source in enumerate((s for s in refs if s.get('citation_eligible',True)), 1):
        title = source.get("title", "资料")
        if source["kind"] == "web":
            lines.append(f"{i}. {title} — {source['url']}；检索时间 {source['retrieved_at']}；{source['evidence_level']}")
            if source.get("origin"):
                lines.append("   沿用历史来源，保留原获取时间。")
            if source.get("read_status") == "failed":
                lines.append("   正文读取失败：" + source.get("read_error", "page_read_failed") + "；保留检索条目。")
            elif source["evidence_level"] != "page_content":
                lines.append("   尚未取得正文，不能据此声称已读全文。")
            else:
                lines.append("   正文摘录；跳转后地址：" + source.get("final_url", source["url"]))
                lines.append("   内容指纹：" + source.get("content_hash", "未记录"))
                if source.get("excerpt"):
                    lines.append("   摘录（不代表全文）：\n" + "\n".join("   > " + line for line in source["excerpt"].splitlines()))
        elif source["kind"] == "file":
            loc = source["locator"]
            position = f"第{loc['page']}页" if loc["kind"] == "page" else f"第{loc['start']}–{loc['end']}行" if loc["kind"] == "lines" else f"第{loc['paragraph']}段" if loc['kind'] == 'paragraph' else f"{loc['sheet']}!{loc['cells']}" if loc['kind'] == 'sheet' else str(loc)
            if loc['kind'] == 'ocr_region':
                position = f"第{loc['page']}页 · 识别区域{loc['region']}"
            lines.append(f"{i}. {title} — {position}；文件 {source['file_ref']['id']}")
            if loc['kind'] == 'ocr_region':
                lines.append('   图像识别候选，必须对照原页核实；识别评分不是正确率，模糊字符与数值不得推定。')
        elif source["kind"] == "business":
            lines.append(f"{i}. {title} — {source['scope']['scope_label']}；截至 {source['as_of']}；{source['data_mode']}")
        else:
            lines.append(f"{i}. {title} — 系统说明 {source['help_id']} / {source['knowledge_version']}")
            lines.append('   说明指纹：' + (source.get('source_fingerprint') or '旧记录未保存；仅有历史版本号，不能据此确认当前规则。'))
    for source in refs:
        if source.get('citation_eligible') is False:
            report=source.get('retrieval',{})
            lines.append(f"检索范围：{source.get('title','文件')}；召回 {report.get('selected_chunks',0)}/{report.get('total_chunks',0)} 片段；仅召回片段进入上下文，未命中不代表不存在。")
    return "\n".join(lines)


def evidence_summary(evidence):
    search = evidence.get("search", {})
    sources = [s for s in evidence.get("sources", []) if s["kind"] == "web"]
    if not sources and not search.get("attempted"):
        return ""
    current = [s for s in sources if not s.get("origin")]
    read = sum(s["evidence_level"] == "page_content" for s in current)
    failed = sum(s["evidence_level"] != "page_content" and s.get("read_status") == "failed" for s in current)
    notice = {"unconfirmed": "本次未取得可核验的联网证据。", "failed": "检索未完成，已有资料保留。", "pending": "正在查找公开资料。"}.get(search.get("execution"), "")
    return (notice + f"本轮公开来源 {len(current)} 项：已取得正文摘录 {read} 项，读取失败 {failed} 项，未尝试读取 {len(current)-read-failed} 项。"
            f"沿用历史公开来源 {len(sources)-len(current)} 项。引用表示资料关联，不代表内容已核实。")


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
        refs = visibility.sources(safe['content_parts'])
        existing_help = {(s['help_id'],s.get('source_fingerprint')) for s in refs if s['kind']=='help'}
        for citation in safe['help_citations']:
            if (citation['id'],citation.get('source_fingerprint')) not in existing_help:
                refs.append(help_registry.source_from_reference(user,citation,run.id))
        row = Artifact(id=uuid4().hex, owner_user_id=user.id, employment_epoch=service.epoch(user), session_id=sid,
            source_run_id=run.id, kind=payload.kind, title=payload.title.strip(), current_revision=1,
            source_refs=refs, created_at=now, updated_at=now)
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


def table_cells(line):
    """Split GFM table rows without treating escaped pipes as delimiters."""
    cells, current, trailing_delimiter = [], [], False
    i = 0
    line = line.strip()
    while i < len(line):
        char = line[i]
        if char == "\\" and i + 1 < len(line) and line[i + 1] in ("\\", "|"):
            current.append(line[i + 1]); trailing_delimiter = False; i += 2; continue
        if char == "|":
            cells.append("".join(current).strip()); current = []; trailing_delimiter = True
        else:
            current.append(char); trailing_delimiter = False
        i += 1
    cells.append("".join(current).strip())
    if line.startswith("|"): cells.pop(0)
    if trailing_delimiter: cells.pop()
    return cells


def table_rows(content):
    """Export actual Markdown table blocks, excluding prose and fenced code."""
    lines = content.splitlines()
    rows, fence, i = [], None, 0
    while i < len(lines):
        line = lines[i].strip()
        marker = re.match(r"^(`{3,}|~{3,})", line)
        if marker:
            value = marker[1]
            if fence is None: fence = value
            elif value[0] == fence[0] and len(value) >= len(fence): fence = None
            i += 1; continue
        if fence is not None or i + 1 >= len(lines) or "|" not in line:
            i += 1; continue
        header, separator = table_cells(line), table_cells(lines[i + 1])
        if not header or len(header) != len(separator) or not all(re.fullmatch(r":?-+:?", cell) for cell in separator):
            i += 1; continue
        if rows: rows.append([])
        rows.append(header); i += 2
        while i < len(lines) and lines[i].strip() and "|" in lines[i] and not re.match(r"^\s*(`{3,}|~{3,})", lines[i]):
            cells = table_cells(lines[i])
            rows.append((cells + [""] * len(header))[:len(header)]); i += 1
    if not rows:
        raise AssistantError("format_unavailable", "未找到可导出的表格，请使用Markdown或纯文本。")
    return rows


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
            for row in table_rows(content):
                writer.writerow([csv_cell(c) for c in row])
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

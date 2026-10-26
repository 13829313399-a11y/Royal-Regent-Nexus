"""Bounded private parsing processes with cancellation and real wall-time limits."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO, StringIO
from pathlib import Path
from threading import Event, Lock
from uuid import uuid4
from datetime import datetime, timezone
import csv
import json
import hashlib
import base64
import re
import time
import subprocess
import sys
import logging
from sqlalchemy import inspect, select
from app import db as database
from app.core.config import settings
from app.models.assistant import AssistantFile as Document
from . import service
from .errors import AssistantError
from .evidence import now_iso, stable_id

PROCESS = uuid4().hex
POOL = None
JOBS = {}
JOB_LOCK = Lock()
logger = logging.getLogger(__name__)
MEDIA = {".txt": "text/plain", ".md": "text/markdown", ".csv": "text/csv", ".pdf": "application/pdf",
         '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
         ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def require_schema():
    if not inspect(database.engine).has_table(Document.__tablename__):
        raise AssistantError("materials_schema_pending", "文件与成果数据迁移待完成；普通聊天仍可使用。", 503)


def path_for(key, extracted=False):
    if not re.fullmatch(r"[a-f0-9]{32}\.bin", key):
        raise AssistantError("storage_invalid", "文件记录无效。", 503)
    root = (Path(settings.assistant_storage_dir) / "documents").resolve()
    target = (root / (key + ".json" if extracted else key)).resolve()
    if target.parent != root:
        raise AssistantError("storage_invalid", "文件位置无效。", 503)
    return target


def owned(db, user, ident, ready=False, *, include_superseded=False):
    row = db.get(Document, ident)
    if not row or row.owner_user_id != user.id or row.employment_epoch != service.epoch(user):
        raise AssistantError("not_found", "文件不存在或当前身份不可查看。", 404)
    service.owned(db, user, row.session_id)
    if row.parse_status == "deleted":
        raise AssistantError("source_unavailable", "文件已删除，相关回答与成果不再可用。", 410)
    if row.parse_status == 'superseded' and not include_superseded:
        raise AssistantError('source_unavailable', '文件已被替换，旧索引及相关回答与成果不再可用。', 410)
    with JOB_LOCK:
        running = row.id in JOBS
    if row.parse_status in ("queued", "parsing") and (row.parse_owner != PROCESS or not running):
        row.parse_status, row.error_code, row.updated_at = "failed", "parse_interrupted", time.time()
    if ready and row.parse_status != "ready":
        raise AssistantError("file_not_ready", "文件尚未解析完成或解析失败，请查看资料状态。", 409)
    return row


def out(row):
    return {k: getattr(row, k) for k in ("id", "session_id", "name", "media_type", "byte_size", "parse_status", "parse_index", "error_code", "created_at", "updated_at")}


def extract(raw, extension):
    from .document_parser import extract as parse, DocumentParseError
    try:
        return parse(raw, extension, settings.assistant_max_document_pages, settings.assistant_max_document_characters)
    except DocumentParseError as exc:
        raise AssistantError(exc.code, exc.message) from None


def worker_path(key, owner=PROCESS):
    if not re.fullmatch(r"[a-f0-9]{32}", owner or ""):
        return None
    return path_for(key).with_suffix(f".parse-{owner}.json")


def launch_parser(key, extension, output):
    return subprocess.Popen([sys.executable, str(Path(__file__).with_name("document_worker.py")), str(path_for(key)),
        str(output), extension, str(settings.assistant_max_document_pages), str(settings.assistant_max_document_characters),
        str(settings.assistant_file_parse_timeout_seconds), str(settings.assistant_file_parse_memory_mb)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)


def cleanup_path(path):
    try:
        path.unlink(missing_ok=True)
    except OSError:
        # The DB row retains ownership; retry during recovery without consuming a slot.
        logger.warning("assistant_file_cleanup_pending key=%s", path.name)


def preview_path(key, page):
    if not isinstance(page, int) or not 1 <= page <= 500:
        raise AssistantError('not_found', '原页预览不存在。', 404)
    return path_for(key).with_suffix(f'.page-{page}.png')


def cleanup_previews(key):
    original = path_for(key)
    for path in original.parent.glob(original.stem + '.page-*.png'):
        cleanup_path(path)


def parse_job(ident, extension, cancelled):
    child, key, output = None, None, None
    try:
        with service.transaction() as db:
            row = db.get(Document, ident)
            if not row or row.parse_status != "queued":
                return
            row.parse_status, row.updated_at = "parsing", time.time()
            key = row.storage_key
        if cancelled.is_set():
            raise AssistantError("parse_interrupted", "文件解析已取消。")
        output = worker_path(key)
        child = launch_parser(key, extension, output)
        deadline = time.monotonic() + settings.assistant_file_parse_timeout_seconds
        while child.poll() is None:
            if cancelled.wait(.05):
                raise AssistantError("parse_interrupted", "文件解析已取消。")
            if time.monotonic() >= deadline:
                raise AssistantError("parse_timeout", "文件解析超时，请拆分后上传。")
        if cancelled.is_set():
            raise AssistantError("parse_interrupted", "文件解析已取消。")
        if child.returncode != 0 or not output.is_file():
            raise AssistantError("parse_failed", "文件解析进程未能完成。")
        result = json.loads(output.read_text(encoding="utf-8"))
        if result.get("error"):
            raise AssistantError(result["error"], "文件解析未完成，请查看资料状态。")
        segments = result["segments"]
        with service.transaction() as db:
            row = db.get(Document, ident)
            if not row or row.parse_status != "parsing":
                return
            for page, encoded in result.get('previews', {}).items():
                preview_path(key, int(page)).write_bytes(base64.b64decode(encoded, validate=True))
            path_for(key, True).write_text(json.dumps(segments, ensure_ascii=False), encoding="utf-8")
            row.parse_index = [s["locator"] for s in segments]
            row.parse_status, row.updated_at = "ready", time.time()
    except Exception as exc:
        try:
            with service.transaction() as db:
                row = db.get(Document, ident)
                if row and row.parse_status != "deleted":
                    row.parse_status, row.updated_at = "failed", time.time()
                    row.error_code = exc.detail["code"] if isinstance(exc, AssistantError) else "parse_failed"
        except Exception:
            logger.warning("assistant_file_state_recovery_pending id=%s", ident)
    finally:
        try:
            try:
                if child and child.poll() is None:
                    child.kill()
                    child.wait(timeout=3)
            finally:
                if child and child.stdin: child.stdin.close()
        except Exception:
            logger.warning("assistant_file_child_cleanup_pending id=%s", ident)
        try:
            if output: cleanup_path(output)
            if key:
                with database.SessionLocal() as db:
                    row = db.get(Document, ident)
                    if not row or row.parse_status == "deleted":
                        for extracted in (False, True): cleanup_path(path_for(key, extracted))
                    if not row or row.parse_status != 'ready':
                        cleanup_previews(key)
        except Exception:
            logger.warning("assistant_file_cleanup_retry_pending id=%s", ident)
        finally:
            with JOB_LOCK: JOBS.pop(ident, None)


def recover_jobs():
    if not inspect(database.engine).has_table(Document.__tablename__): return
    with service.transaction() as db:
        for row in db.scalars(select(Document)):
            with JOB_LOCK:
                if row.id in JOBS: continue
            temporary = worker_path(row.storage_key, row.parse_owner)
            if temporary: cleanup_path(temporary)
            if row.parse_status in ('deleted','superseded'):
                for extracted in (False, True): cleanup_path(path_for(row.storage_key, extracted))
                cleanup_previews(row.storage_key)
            elif row.parse_status in ("queued", "parsing"):
                row.parse_status, row.error_code, row.updated_at = "failed", "parse_interrupted", time.time()
                cleanup_previews(row.storage_key)
            elif row.parse_status == 'failed':
                cleanup_previews(row.storage_key)


def shutdown():
    global POOL
    with JOB_LOCK:
        pool, POOL = POOL, None
        for cancelled in JOBS.values(): cancelled.set()
    if pool: pool.shutdown(wait=True)


def save(user, sid, raw, filename, media_type=None):
    global POOL
    require_schema()
    name = Path((filename or "").replace("\\", "/")).name[:240]
    extension = Path(name).suffix.lower()
    if extension not in MEDIA:
        raise AssistantError("file_type", "支持TXT、Markdown、CSV、PDF、DOCX、XLSX、PNG和JPEG；不接收宏文件。")
    if extension in ('.docx', '.xlsx') and media_type not in (None, '', 'application/octet-stream', MEDIA[extension]):
        raise AssistantError('file_type', '文件类型与扩展名不一致，请重新导出标准DOCX或XLSX。')
    if extension in ('.png', '.jpg', '.jpeg') and media_type not in (None, '', 'application/octet-stream', MEDIA[extension]):
        raise AssistantError('file_type', '图片内容类型与扩展名不一致，请重新导出PNG或JPEG。')
    if not raw or len(raw) > settings.assistant_max_file_bytes:
        raise AssistantError("file_size", "文件为空或超过大小限制。", 413)
    ident, now = uuid4().hex, time.time()
    cancelled = Event()
    with JOB_LOCK:
        if len(JOBS) >= settings.assistant_file_parse_queue_limit:
            raise AssistantError("parse_busy", "文件解析队列繁忙，请稍后重试。", 429, True)
        JOBS[ident] = cancelled
    key = ident + ".bin"
    try:
        with service.transaction() as db:
            service.owned(db, user, sid)
            row = Document(id=ident, session_id=sid, owner_user_id=user.id, employment_epoch=service.epoch(user), name=name,
                storage_key=key, media_type=MEDIA[extension], byte_size=len(raw), parse_status="queued", parse_owner=PROCESS,
                parse_index=[], created_at=now, updated_at=now)
            db.add(row)
        with service.transaction() as db:
            service.owned(db, user, sid)
            path = path_for(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        with JOB_LOCK:
            if POOL is None:
                POOL = ThreadPoolExecutor(max_workers=settings.assistant_file_parse_concurrency, thread_name_prefix="assistant-files")
            POOL.submit(parse_job, ident, extension, cancelled)
    except BaseException:
        with JOB_LOCK: JOBS.pop(ident, None)
        path_for(key).unlink(missing_ok=True)
        with service.transaction() as db:
            row = db.get(Document, ident)
            if row and row.parse_status != "deleted":
                row.parse_status, row.error_code = "failed", "parse_failed"
        raise
    return dict(id=ident, name=name, parse_status="queued")


def metadata(user, ident):
    require_schema()
    with service.transaction() as db:
        row=owned(db,user,ident,include_superseded=True)
        value=out(row)
        if row.parse_status=='ready':
            document=snapshot(db,user,ident)
            value.update(document_version=document['version'],indexed_segments=len(document['segments']))
        return value


def content(user, ident, extracted=False, version=None):
    require_schema()
    with service.transaction() as db:
        row = owned(db, user, ident, ready=extracted)
        if extracted or version:
            document=snapshot(db,user,ident,expected_version=version)
            if extracted:
                return json.dumps(document['segments'],ensure_ascii=False).encode(), 'application/json'
        path = path_for(row.storage_key, extracted)
        if not path.is_file():
            raise AssistantError("source_unavailable", "文件内容当前不可用。", 410)
        return path.read_bytes(), "application/json" if extracted else row.media_type


def page_preview(user, ident, page, version=None):
    require_schema()
    with service.transaction() as db:
        row = owned(db, user, ident, ready=True)
        snapshot(db,user,ident,expected_version=version)
        if not any(loc.get('kind') == 'ocr_region' and loc.get('page') == page for loc in row.parse_index):
            raise AssistantError('not_found', '该页没有识别预览。', 404)
        path = preview_path(row.storage_key, page)
        if not path.is_file():
            raise AssistantError('source_unavailable', '原页预览当前不可用，请重新上传文件。', 410)
        return path.read_bytes()


def erase(db, row):
    with JOB_LOCK:
        if cancelled := JOBS.get(row.id): cancelled.set()
    row.parse_status, row.parse_index, row.error_code = "deleted", [], None
    row.name, row.updated_at = "已删除文件", time.time()
    cleanup_previews(row.storage_key)
    for extracted in (False, True):
        try: path_for(row.storage_key, extracted).unlink(missing_ok=True)
        except PermissionError:
            # A terminating worker may briefly hold the source on Windows.
            if row.id not in JOBS: raise


def remove(user, ident):
    require_schema()
    with service.transaction() as db:
        erase(db, owned(db, user, ident,include_superseded=True))


def replace(user, ident, replacement_id, expected_version, replacement_version):
    """Activate an independently parsed upload; failures never retire the original."""
    require_schema()
    from app.models.assistant import AssistantRun
    with service.transaction() as db:
        old=owned(db,user,ident,ready=True)
        if ident==replacement_id:
            raise AssistantError('file_replacement_invalid','请选择另一份已解析文件。')
        snapshot(db,user,ident,expected_version=expected_version)
        replacement=snapshot(db,user,replacement_id,old.session_id,replacement_version)
        if db.scalar(select(AssistantRun.id).where(AssistantRun.session_id==old.session_id,
                       AssistantRun.state.in_(service.ACTIVE),AssistantRun.lease_expires_at>=time.time()).limit(1)):
            raise AssistantError('file_in_use','请先停止生成或等待回答结束，再替换文件。',409)
        # Status is the transactional invalidation boundary. Never overwrite
        # source bytes or redirect a historical citation to the replacement.
        old.parse_status,old.parse_index,old.updated_at='superseded',[],time.time()
        key=old.storage_key
        value=out(db.get(Document,replacement_id))
        value.update(document_version=replacement['version'],indexed_segments=len(replacement['segments']))
    # Recovery retries failed cleanup; access already fails closed after commit.
    for extracted in (False,True): cleanup_path(path_for(key,extracted))
    cleanup_previews(key)
    return dict(replaced_file_id=ident,file=value)


def materials(db, user, sid, ids, run_id):
    result, sources = [], []
    if ids:
        require_schema()
    if len(set(ids)) != len(ids):
        raise AssistantError("file_duplicate", "资料重复。")
    budget = min(settings.assistant_max_document_characters, settings.assistant_context_character_budget // 2)
    used = 0
    for ident in ids:
        row = owned(db, user, ident, ready=True)
        if row.session_id != sid:
            raise AssistantError("source_unavailable", "文件不属于当前会话。", 404)
        try:
            segments = json.loads(path_for(row.storage_key, True).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise AssistantError("source_unavailable", "解析内容不可用，请重新上传。", 410) from None
        for index, segment in enumerate(segments):
            metadata = segment.get('metadata')
            used += len(segment["text"]) + (len(json.dumps(metadata, ensure_ascii=False)) if metadata else 0)
            if used > budget:
                raise AssistantError("file_context_limit", "本次资料超过上下文预算，请减少文件或拆分材料。")
            source = dict(kind="file", source_id=stable_id(run_id, ident, index), run_id=run_id, title=row.name,
                file_ref=dict(kind="document", id=ident), extracted_at=datetime.fromtimestamp(row.updated_at, timezone.utc).isoformat(), locator=segment["locator"])
            from .document_retrieval import segment_hash
            source['content_hash'] = segment_hash(segment)
            if segment.get('metadata', {}).get('format') == 'ocr':
                source['ocr'] = {k: segment['metadata'][k] for k in ('signal_score', 'uncertain', 'uncertainty_reasons', 'engine')}
            sources.append(source)
            result.append(dict(source_id=source["source_id"], name=row.name, locator=segment["locator"], text=segment["text"],
                               **(dict(metadata=segment['metadata']) if segment.get('metadata') else {})))
    return result, sources


def snapshot(db, user, ident, sid=None, expected_version=None):
    """Filter before ranking; bind current original bytes and extraction together."""
    from .document_retrieval import version_segments
    row = owned(db, user, ident, ready=True)
    if sid is not None and row.session_id != sid:
        raise AssistantError('source_unavailable', '文件不属于当前会话。', 404)
    original, index = path_for(row.storage_key), path_for(row.storage_key, True)
    try:
        if original.stat().st_size != row.byte_size or index.stat().st_size > 16*1024*1024:
            raise ValueError('changed document size')
        with original.open('rb') as stream:
            raw_hash = hashlib.file_digest(stream,'sha256').hexdigest()
        segments = json.loads(index.read_text(encoding='utf-8'))
        if not isinstance(segments,list) or not segments or any(
            not isinstance(s,dict) or not isinstance(s.get('text'),str) or
            not isinstance(s.get('locator'),dict) or not isinstance(s.get('metadata',{}),dict) for s in segments):
            raise ValueError('invalid document index')
        version = version_segments(raw_hash, segments)
        if any(s.get('original_hash',raw_hash)!=raw_hash or s.get('document_version',version)!=version for s in segments):
            raise ValueError('changed original or index')
        if expected_version and version != expected_version:
            raise ValueError('changed document version')
    except (OSError, ValueError, TypeError, KeyError):
        raise AssistantError('file_version_changed', '文件或解析版本已变化，请重新选择或上传资料。', 409) from None
    return dict(id=row.id,name=row.name,version=version,segments=segments,updated_at=row.updated_at,session_id=row.session_id)


def search_documents(db, user, sid, ids, query, run_id, expected_versions=None, budget=None):
    """One production path for question context, inspection and recall tests."""
    from .document_retrieval import retrieve
    if len(ids)>8 or len(set(ids))!=len(ids):
        raise AssistantError('file_duplicate', '每次最多选择8份不同资料。')
    documents=[snapshot(db,user,ident,sid,(expected_versions or {}).get(ident)) for ident in ids]
    limit=min(8000,settings.assistant_context_character_budget//3,
              settings.assistant_max_document_characters)
    if budget is not None: limit=min(limit,budget)
    try:
        chunks,report=retrieve(documents,query,limit)
    except ValueError:
        raise AssistantError('retrieval_query_limit','资料查询过长，请缩短编号或关键词后重试。') from None
    if report['coverage']=='budget_exhausted':
        raise AssistantError('file_context_limit','资料片段及定位超过本轮预算，请缩小查询范围。')
    materials,refs=[],[]
    by_id={d['id']:d for d in documents}
    for chunk in chunks:
        document=by_id[chunk['file_id']]
        source=dict(kind='file',source_id=stable_id(run_id,document['id'],document['version'],chunk['segment_index'],chunk['excerpt_range']['start']),
            run_id=run_id,title=document['name'],file_ref=dict(kind='document',id=document['id']),
            extracted_at=datetime.fromtimestamp(document['updated_at'],timezone.utc).isoformat(),
            locator=chunk['locator'],document_version=document['version'],content_hash=chunk['segment_hash'],
            chunk_hash=chunk['chunk_hash'],excerpt_range=chunk['excerpt_range'],segment_index=chunk['segment_index'])
        if chunk['metadata'].get('format')=='ocr':
            source['ocr']={k:chunk['metadata'][k] for k in ('signal_score','uncertain','uncertainty_reasons','engine')}
        refs.append(source)
        materials.append(dict(source_id=source['source_id'],name=document['name'],text=chunk['text'],
            locator=chunk['locator'],document_version=document['version'],excerpt_range=chunk['excerpt_range'],
            **(dict(metadata=chunk['metadata']) if chunk['metadata'] else {})))
    # A no-match answer still depends on the selected file/version. These scope
    # records invalidate derived content but are not eligible text citations.
    for document in documents:
        refs.append(dict(kind='file',source_id=stable_id(run_id,document['id'],document['version'],'scope'),run_id=run_id,
            title=document['name'],file_ref=dict(kind='document',id=document['id']),locator=dict(kind='document'),
            extracted_at=datetime.fromtimestamp(document['updated_at'],timezone.utc).isoformat(),
            document_version=document['version'],citation_eligible=False,
            retrieval={**report['documents'][document['id']], 'strategy':report['strategy'],
                       'query_hash':report['query_hash'], 'notice':report['notice'],
                       'coverage':('complete' if report['documents'][document['id']]['selected_chunks']==report['documents'][document['id']]['total_chunks']
                                   else 'partial' if report['documents'][document['id']]['selected_chunks'] else 'no_match')}))
    return dict(materials=materials,sources=refs,report=report)


def source_matches(document, source):
    from .document_retrieval import segment_hash
    if source.get('document_version') and source['document_version']!=document['version']:
        return False
    if source['locator']['kind']=='document':
        return source.get('citation_eligible') is False
    parts=[p for p in document['segments'] if p['locator']==source['locator']]
    if not parts:
        return False
    part=next((p for p in parts if not source.get('content_hash') or segment_hash(p)==source['content_hash']),None)
    if part is None:
        return False
    if span:=source.get('excerpt_range'):
        if not 0<=span['start']<span['end']<=len(part['text']) or span['total']!=len(part['text']):
            return False
        return hashlib.sha256(part['text'][span['start']:span['end']].encode()).hexdigest()==source.get('chunk_hash')
    return True

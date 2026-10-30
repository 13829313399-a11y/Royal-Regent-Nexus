"""Explicit colleague document ACLs and durable save callbacks."""
from datetime import datetime, timezone
from io import BytesIO
import hashlib
import json
import os
import time
from uuid import uuid4
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import select, update, case

from app.core.config import settings
from app.models.auth import AuthSession, AuthUser, EmployeeProfile
from app.models.identity import IamOrgUnit
from app.models.online_documents import OnlineDocument as Document, OnlineDocumentRevision as Revision
from app.models.online_documents import OnlineDocumentPlacement as Placement
from app.services import auth, collaborative_sheets, internal_members
from app.services.document_tools import storage
from app.services import online_document_protocol as protocol
from app.services.identity_policy import lock_mutation
from app.services.identity_resolver import identity_columns
from app.services.identity_catalog import DEPARTMENTS


def uid():
    return uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def epoch(user):
    return int((user.identity or {}).get("employment_epoch", 1))


def enabled():
    if not settings.document_tools_enabled or not settings.online_documents_enabled:
        raise HTTPException(503, "在线文档尚未启用")
    protocol.secret()
    if not settings.onlyoffice_public_url.startswith(("http://", "https://")):
        raise HTTPException(503, "在线文档尚未配置")


def scope(user, factory_id):
    if not user.account_available:
        raise HTTPException(403, "账号不可用")
    if factory_id == "group":
        return  # Ownership does not require an employee profile; sharing is explicit.
    collaborative_sheets.scope(user, factory_id)


def access(doc, user):
    if doc.owner_id == user.id and doc.owner_epoch == epoch(user):
        return "owner"
    if doc.factory_id == "group" and not group_member(user):
        return ""
    return next((g["access"] for g in doc.grants if g["user_id"] == user.id and g["epoch"] == epoch(user)), "")


def group_member(user):
    # The directory tolerates legacy empty identities for display. Document
    # sharing requires affirmative internal identity, not merely an active login.
    return internal_members.is_internal(user) and bool(
        (user.profile and user.profile.confirmation_status == "confirmed") or user.permissions or
        any(a.get("org_unit_id") and a["org_unit_id"] != "group"
            for a in (user.identity or {}).get("active_assignments_summary", [])))


def require_group_member(user):
    if not group_member(user):
        raise HTTPException(403, "请确认公司内部员工身份后再使用共享")


def group_recipient_ids(db):
    eligible = internal_members.eligible_member_ids(db)
    rows = db.execute(select(AuthUser.id, EmployeeProfile.confirmation_status)
                      .outerjoin(EmployeeProfile, EmployeeProfile.user_id == AuthUser.id)
                      .where(AuthUser.id.in_(eligible))).all()
    # Confirmed employees are already evaluated by the bulk internal-member
    # rule. Resolve only legacy/unconfirmed exceptions such as administrators.
    return {uid for uid, confirmation in rows if confirmation == "confirmed" or
            group_member(auth.build_auth_context(db, db.get(AuthUser, uid)))}


def get(db, user, factory_id, document_id, *, lock=False, owner=False, edit=False, include_deleted=False):
    scope(user, factory_id)
    if lock:
        # Acquires a write lock before reading on SQLite as well as PostgreSQL.
        db.execute(update(Document).where(Document.id == document_id).values(id=document_id))
    doc = db.scalar(select(Document).where(Document.id == document_id, Document.factory_id == factory_id).execution_options(populate_existing=True))
    mode = access(doc, user) if doc else ""
    if not mode or (doc.deleted_at and (not include_deleted or mode != "owner")):
        raise HTTPException(404, "文档不存在或未向您共享")
    if (owner and mode != "owner") or (edit and mode == "view"):
        raise HTTPException(403, "您没有此操作权限")
    return doc


def summary(doc, user):
    result = {key: getattr(doc, key) for key in ("id", "title", "format", "owner_name", "revision", "byte_size", "created_at", "updated_at", "pending_save", "saved_request", "save_error")}
    result.update(access=access(doc, user), editing=bool(doc.editor_key), deleted_at=doc.deleted_at,
                  state_version=doc.state_version, protected=bool(doc.protection))
    if result["access"] == "owner":
        result["grants"] = [{k: g[k] for k in ("user_id", "name", "access", "epoch")} for g in doc.grants]
        result["share_version"] = share_version(doc)
    return result


def share_version(doc):
    return hashlib.sha256(json.dumps(doc.grants, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def listing(db, user, factory_id, deleted=False, folder_id=None, sort='updated', recent_ids=()):
    scope(user, factory_id)
    query = select(Document, Placement.folder_id, Placement.version).outerjoin(Placement, Placement.document_id == Document.id).where(Document.factory_id == factory_id)
    if folder_id is not None:
        from app.services import online_document_folders as folders
        if folder_id != "uncategorized":
            folders.get(db, user, factory_id, folder_id)
        query = query.where(Document.owner_id == user.id, Document.owner_epoch == epoch(user),
                            Placement.folder_id.is_(None) if folder_id == "uncategorized" else Placement.folder_id == folder_id)
    if sort == 'recent':
        if not recent_ids:
            return {"items": []}
        query = query.where(Document.id.in_(recent_ids)).order_by(case({value: index for index, value in enumerate(recent_ids)}, value=Document.id))
    elif sort == 'name':
        query = query.order_by(Document.title.asc())
    elif sort == 'name_desc':
        query = query.order_by(Document.title.desc())
    rows = db.execute(query.order_by(Document.updated_at.desc(), Document.id).execution_options(yield_per=100))
    result = []
    for doc, placement_folder, placement_version in rows:
        mode = access(doc, user)
        if mode and bool(doc.deleted_at) == deleted and (not deleted or mode == "owner"):
            item = summary(doc, user)
            if mode == "owner":
                item.update(folder_id=placement_folder, placement_version=placement_version or 0)
            result.append(item)
            if len(result) >= 200:
                break
    return {"items": result}


def write_blob(document_id, data):
    key = f"online-documents/{document_id}/{uid()}.bin"
    path = storage.resolve(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    return key, hashlib.sha256(data).hexdigest()


def valid_title(title, extension):
    title = title.strip()
    if title.lower().endswith("." + extension):
        title = title[:-(len(extension) + 1)].strip()
    if not title or storage.safe_name(title) != title:
        raise HTTPException(422, r'请输入有效文件名，不要包含 \ / : * ? " < > | 或末尾句点')
    return title


def rename(db, doc, user, title, expected_title, expected_version):
    title = valid_title(title, doc.format)
    if doc.title != expected_title and doc.title != title:
        raise HTTPException(409, "文件名已在其他窗口修改，请取消后刷新列表再重命名")
    if doc.title != title:
        if doc.state_version != expected_version:
            raise HTTPException(409, "文档状态已在其他窗口修改，请取消后重新发起改名")
        previous = doc.title
        doc.title = title
        doc.updated_at = now()
        doc.state_version += 1
        from app.services.online_document_management import audit
        audit(db, doc, user, "rename", {"from": previous, "to": title})
    # Renaming changes metadata only: keep format, grants, blobs and revisions.
    db.commit()
    # Serialize title notifications with later mutations and use the latest DB
    # title. A transport failure must not roll back an already durable rename.
    lock_mutation(db)
    db.refresh(doc)
    result = summary(doc, user)
    if doc.editor_key and not doc.deleted_at:
        try:
            response = protocol.command({"c": "meta", "key": doc.editor_key, "meta": {"title": doc.title + "." + doc.format}})
            if response.get("error") != 0:
                raise ValueError("meta command unconfirmed")
        except Exception:
            result["title_sync_pending"] = True
            result["operation_notice"] = "名称已保存，编辑器标题同步尚未确认，请重试同步名称"
    db.rollback()  # Release the notification lock; no content/session mutation.
    return result


def revision(db, doc, actor):
    db.add(Revision(id=uid(), document_id=doc.id, revision=doc.revision, storage_key=doc.storage_key,
                    sha256=doc.sha256, byte_size=doc.byte_size, actor_id=actor, created_at=now(), protection=doc.protection or {}))


def create(db, user, factory_id, title, extension, data=None, *, folder_id=None):
    scope(user, factory_id)
    if folder_id:
        from app.services.online_document_folders import get as get_folder
        get_folder(db, user, factory_id, folder_id)
    title = storage.safe_name(title or ("新建表格" if extension == "xlsx" else "新建文档"))[:190]
    if title.lower().endswith("." + extension):
        title = title[:-(len(extension) + 1)]
    if data is None:
        stream = BytesIO()
        if extension == "xlsx":
            from openpyxl import Workbook
            Workbook().save(stream)
        elif extension == "docx":
            from docx import Document as Word
            Word().save(stream)
        else:
            raise HTTPException(422, "仅支持 DOCX / XLSX")
        data = stream.getvalue()
    protocol.validate(data, extension)
    document_id = uid()
    key, digest = write_blob(document_id, data)
    doc = Document(id=document_id, factory_id=factory_id, owner_id=user.id, owner_epoch=epoch(user),
                   owner_name=user.display_name, title=title, format=extension, storage_key=key,
                   sha256=digest, byte_size=len(data), revision=1, grants=[], participants={},
                   created_at=now(), updated_at=now())
    db.add(doc)
    db.flush()
    if folder_id:
        db.add(Placement(document_id=doc.id, folder_id=folder_id, version=1))
    revision(db, doc, user.id)
    from app.services.online_document_management import audit
    audit(db, doc, user, "create", {"title": title})
    db.commit()
    return summary(doc, user)


def recipients(db, user, factory_id):
    scope(user, factory_id)
    if factory_id != "group":
        result = collaborative_sheets.recipients(db, user, factory_id)
        epochs = dict(db.execute(select(EmployeeProfile.user_id, EmployeeProfile.employment_epoch)
                                .where(EmployeeProfile.user_id.in_([p["id"] for p in result["users"]]))).all())
        return {**result, "users": [{**p, "epoch": epochs.get(p["id"], 1)} for p in result["users"]]}
    require_group_member(user)
    _, department, _, org = identity_columns(include_org=True)
    rows = db.execute(
        select(AuthUser.id, AuthUser.display_name, EmployeeProfile.employment_epoch.label("epoch"), department.label("department"),
               select(IamOrgUnit.name).where(IamOrgUnit.id == org).scalar_subquery().label("organization"))
        .outerjoin(EmployeeProfile, EmployeeProfile.user_id == AuthUser.id)
        .where(AuthUser.id.in_(group_recipient_ids(db)), AuthUser.id != user.id)
        .order_by(org, AuthUser.display_name, AuthUser.id)
    ).all()
    return {"users": [{"id": row.id, "display_name": row.display_name,
                       "epoch": row.epoch or 1, "department": DEPARTMENTS.get(row.department, row.department or ""), "organization": row.organization or ""}
                      for row in rows], "departments": []}


def validate_sharing(db, doc, user, grants, version):
    if doc.factory_id == "group":
        require_group_member(user)
    if version != share_version(doc):
        raise HTTPException(409, "共享设置已在其他窗口变更，请关闭并重新打开共享设置")
    if len(grants) > 50 or len({g.user_id for g in grants}) != len(grants):
        raise HTTPException(422, "最多共享给 50 人，且不能重复")
    allowed = (group_recipient_ids(db) if doc.factory_id == "group" else
               {item["id"] for item in collaborative_sheets._eligible_accounts(db, doc.factory_id)})
    result = []
    for grant in grants:
        if grant.user_id not in allowed or grant.user_id == doc.owner_id:
            raise HTTPException(422, "请选择其他有效的公司内部同事" if doc.factory_id == "group" else "请选择其他已确认的本厂账号")
        target = auth.build_auth_context(db, db.get(AuthUser, grant.user_id))
        scope(target, doc.factory_id)
        if doc.factory_id == "group":
            require_group_member(target)
        if grant.epoch != epoch(target):
            raise HTTPException(409, "同事的任职身份已变化，请关闭并重新打开共享设置，再移除该同事并重新添加")
        result.append({"user_id": target.id, "name": target.display_name, "epoch": epoch(target), "access": grant.access})
    return result


SHARING_STATE = "__sharing__"


def sharing_fingerprint(grants):
    fields = [{k: g[k] for k in ("user_id", "epoch", "access")} for g in grants]
    return hashlib.sha256(json.dumps(sorted(fields, key=lambda g: g["user_id"]), sort_keys=True).encode()).hexdigest()


def sharing_state(doc, result, version):
    state = doc.participants.get(SHARING_STATE, {})
    if (state.get("expires", 0) > time.time() and state.get("key") == doc.editor_key and state.get("version") == version and
            state.get("fingerprint") == sharing_fingerprint(result)):
        return state
    return {}


def set_sharing_state(doc, state):
    doc.participants = {**doc.participants, SHARING_STATE: state}


def prepare_sharing(db, doc, user, grants, version, session_id):
    """Disconnect only reduced grants; checkpoint without closing other editors."""
    result = validate_sharing(db, doc, user, grants, version)
    document_id, factory, key = doc.id, doc.factory_id, doc.editor_key
    actor_id, actor_epoch = user.id, epoch(user)
    if not key:
        return {"ready": True}

    def current_owner():
        lock_mutation(db)
        account = db.get(AuthUser, actor_id, populate_existing=True)
        session = db.get(AuthSession, session_id, populate_existing=True)
        expiry = auth.parse_time(session.expires_at) if session else None
        if (not account or account.status != "active" or account.force_password_change or
                not session or session.status != "active" or session.user_id != actor_id or
                not expiry or expiry <= datetime.now()):
            raise HTTPException(401, "登录状态已变化，请重新登录")
        actor = auth.build_auth_context(db, account)
        if epoch(actor) != actor_epoch:
            raise HTTPException(403, "任职身份已变化，请重新打开文档")
        current = get(db, actor, factory, document_id, owner=True, lock=True)
        validate_sharing(db, current, actor, grants, version)
        return current

    state = sharing_state(doc, result, version)
    if state.get("phase") == "ready":
        return {"ready": True}
    if state.get("phase") in {"waiting", "saving"}:
        if doc.save_error:
            raise HTTPException(409, "内容保存尚未确认，共享设置尚未修改，请恢复文档保存后重试")
        if doc.pending_save:
            return {"ready": False}
        if state.get("phase") == "saving":
            if doc.saved_request != state["request_id"]:
                raise HTTPException(409, "共享前的保存尚未确认，请重试原共享设置")
            set_sharing_state(doc, {**state, "phase": "ready"})
            db.commit()
            return {"ready": True}
        request_id = uid()
        set_sharing_state(doc, {**state, "phase": "saving", "request_id": request_id})
        # start_save commits the receipt and nonce before the remote command.
        start_save(db, doc, request_id=request_id)
        doc = current_owner()
        if doc.editor_key != key:
            return {"ready": not bool(doc.editor_key)}
        latest = sharing_state(doc, result, version)
        if latest.get("operation") != state["operation"]:
            raise HTTPException(409, "共享准备已过期或被替换，请重试原设置")
        state = latest
        if doc.saved_request == request_id and not doc.pending_save and not doc.save_error:
            set_sharing_state(doc, {**state, "phase": "ready"})
            db.commit()
            return {"ready": True}
        return {"ready": state.get("phase") == "ready"}

    old_state = doc.participants.get(SHARING_STATE, {})
    if old_state.get("expires", 0) > time.time() and not state and old_state.get("phase") != "ready":
        raise HTTPException(409, "另一组共享修改尚未完成，请先重试原共享设置")
    desired = {(g["user_id"], g["epoch"]): g["access"] for g in result}
    targets = [f'{g["user_id"]}_{g["epoch"]}' for g in doc.grants
               if (g["user_id"], g["epoch"]) not in desired or
               (g["access"] == "edit" and desired[(g["user_id"], g["epoch"])] != "edit")]
    state = state or {"key": key, "version": version, "fingerprint": sharing_fingerprint(result),
                     "targets": targets, "phase": "drop", "operation": uid(), "expires": time.time() + 120}
    set_sharing_state(doc, state)
    db.commit()  # Callbacks must be free to acquire IAM/document locks.
    try:
        response = protocol.command({"c": "info", "key": key})
    except Exception:
        raise HTTPException(502, "暂时无法核实编辑连接，共享设置尚未修改，请稍后重试") from None
    doc = current_owner()
    if doc.editor_key != key:
        return {"ready": not bool(doc.editor_key)}
    latest = sharing_state(doc, result, version)
    if latest.get("operation") != state["operation"]:
        raise HTTPException(409, "共享准备已过期或被替换，请重试原设置")
    if latest.get("phase") != "drop":
        return {"ready": latest.get("phase") == "ready"}
    if response.get("error") == 1:
        if doc.pending_save or doc.save_error:
            raise HTTPException(409, "编辑连接已离线，但还有未确认的保存，共享设置尚未修改，请先恢复文档保存")
        doc.editor_key, doc.participants = "", {}
        db.commit()
        return {"ready": True}
    if response.get("error") != 0:
        raise HTTPException(502, "暂时无法核实编辑连接，共享设置尚未修改，请稍后重试")
    if not targets:
        set_sharing_state(doc, {**state, "phase": "ready"})
        db.commit()
        return {"ready": True}
    db.commit()
    try:
        # Never omit users or send an empty target list: that would drop everyone.
        response = protocol.command({"c": "drop", "key": key, "users": targets})
    except Exception:
        raise HTTPException(502, "目标同事连接的处理结果尚未确认，共享设置尚未修改，请重试原设置") from None
    doc = current_owner()
    if response.get("error") != 0:
        raise HTTPException(502, "目标同事连接尚未结束，共享设置尚未修改，请稍后重试")
    if doc.editor_key != key:
        return {"ready": not bool(doc.editor_key)}
    latest = sharing_state(doc, result, version)
    if latest.get("operation") != state["operation"]:
        raise HTTPException(409, "共享准备已过期或被替换，请重试原设置")
    if latest.get("phase") != "drop":
        return {"ready": latest.get("phase") == "ready"}
    set_sharing_state(doc, {**state, "phase": "waiting"})
    db.commit()
    # One non-closing checkpoint preserves edits already received from targets.
    doc = current_owner()
    return prepare_sharing(db, doc, user, grants, version, session_id)


def share(db, doc, user, grants, version):
    result = validate_sharing(db, doc, user, grants, version)
    prepared = sharing_state(doc, result, version)
    if doc.editor_key and prepared.get("phase") != "ready":
        raise HTTPException(409, "请先完成目标同事连接处理和保存确认，再保存共享设置")
    previous = doc.grants
    if doc.editor_key:
        targets = set(prepared.get("targets", []))
        doc.participants = {pid: ({**p, "revoked": True} if pid in targets else p)
                            for pid, p in doc.participants.items() if pid != SHARING_STATE}
    doc.grants = result
    doc.updated_at = now()
    doc.state_version += 1
    if not doc.editor_key:
        doc.access_generation += 1
    from app.services.online_document_management import audit
    audit(db, doc, user, "share", {"before": previous, "after": result})
    db.commit()
    return summary(doc, user)


def editor(db, doc, user, session_id):
    mode = access(doc, user)
    editor_id = f"{user.id}_{epoch(user)}"
    state = doc.participants.get(SHARING_STATE, {})
    if state.get("expires", 0) > time.time() and editor_id in state.get("targets", []):
        raise HTTPException(409, "拥有者正在调整您的共享权限，请稍后重新打开")
    if mode == "view":
        source = protocol.sign({"purpose": "source-view", "document": doc.id, "revision": doc.revision,
                                "generation": doc.access_generation,
                                "user_id": user.id, "epoch": epoch(user), "session_id": session_id, "exp": int(time.time()) + 900})
        base = settings.onlyoffice_callback_base.rstrip("/") + "/api/tools/online-documents"
        config = {"documentType": "cell" if doc.format == "xlsx" else "word", "type": "desktop", "height": "100%", "width": "100%",
                  "document": {"fileType": doc.format, "key": f"view-{doc.id}-{doc.revision}", "title": doc.title + "." + doc.format,
                               "url": f"{base}/{doc.id}/source?token={quote(source)}", "permissions": {"edit": False, "download": False, "chat": False}},
                  "editorConfig": {"mode": "view", "lang": "zh-CN", "user": {"id": f"{user.id}_{epoch(user)}", "name": user.display_name},
                                   "customization": {"plugins": False, "macros": False, "ai": {"disabled": True}}}, "exp": int(time.time()) + 900}
        config["token"] = protocol.sign(config)
        db.commit()
        return {"config": config, "script_url": settings.onlyoffice_public_url.rstrip("/") + "/web-apps/apps/api/documents/api.js", "document": summary(doc, user)}
    if doc.editor_key and time.time() - doc.editor_started > 86400:
        raise HTTPException(409, "编辑会话已超过一天，请先关闭所有编辑窗口，等待保存完成后再打开")
    if not doc.editor_key:
        doc.editor_key = uid()
        doc.editor_source = doc.storage_key
        doc.editor_started = int(time.time())
        doc.participants = {}
        doc.pending_save = ""
        doc.save_error = ""
    editor_id = f"{user.id}_{epoch(user)}"
    doc.participants = {**doc.participants, editor_id: {"user_id": user.id, "epoch": epoch(user), "session_id": session_id, "edit": mode != "view"}}
    source = protocol.sign({"purpose": "source", "document": doc.id, "key": doc.editor_key,
                            "generation": doc.access_generation,
                            "user_id": user.id, "epoch": epoch(user), "session_id": session_id, "exp": doc.editor_started + 86400})
    base = settings.onlyoffice_callback_base.rstrip("/") + "/api/tools/online-documents"
    config = {
        "documentType": "cell" if doc.format == "xlsx" else "word",
        "document": {"fileType": doc.format, "key": doc.editor_key, "title": doc.title + "." + doc.format,
                     "url": f"{base}/{doc.id}/source?token={quote(source)}",
                     "permissions": {"edit": mode != "view", "download": False, "print": True, "chat": False}},
        "editorConfig": {"mode": "view" if mode == "view" else "edit", "lang": "zh-CN",
                         "callbackUrl": f"{base}/{doc.id}/callback",
                         "user": {"id": editor_id, "name": user.display_name},
                         "customization": {"autosave": True, "forcesave": False, "compactToolbar": True,
                                           "plugins": False, "macros": False, "help": False,
                                           "ai": {"disabled": True}, "feedback": False}},
        "height": "100%", "width": "100%", "type": "desktop",
        "exp": int(time.time()) + 86400,
    }
    config["token"] = protocol.sign(config)
    db.commit()
    return {"config": config, "script_url": settings.onlyoffice_public_url.rstrip("/") + "/web-apps/apps/api/documents/api.js", "document": summary(doc, user)}


def start_save(db, doc, *, request_id=None):
    if not doc.editor_key:
        return {"request_id": "", "revision": doc.revision}
    if doc.pending_save and not doc.save_error and time.time() - doc.pending_since < 90:
        return {"request_id": doc.pending_save, "revision": doc.revision}
    uncertain = bool(doc.pending_save or doc.save_error)
    # Preserve an unacknowledged request across retries: the document server may
    # have assembled the file even when its callback or command response failed.
    request_id, key = doc.pending_save or request_id or uid(), doc.editor_key
    doc.pending_save, doc.pending_since, doc.save_error = request_id, int(time.time()), ""
    db.commit()  # The callback can arrive before the command HTTP response.
    try:
        result = protocol.command({"c": "forcesave", "key": key, "userdata": request_id})
        error = int(result.get("error", -1))
    except Exception:
        error = -1
    if error:
        unchanged = error == 4 and not uncertain
        db.execute(update(Document).where(Document.id == doc.id, Document.editor_key == key, Document.pending_save == request_id)
                   .values(pending_save="" if unchanged else request_id,
                           saved_request=request_id if unchanged else doc.saved_request,
                           save_error="" if unchanged else "尚未收到文件保存确认，请保持编辑窗口打开并重试"))
        db.commit()
        if not unchanged:
            raise HTTPException(502, "尚未收到文件保存确认，请保持编辑窗口打开并重试")
    return {"request_id": request_id, "revision": doc.revision}


def release_unopened(db, doc):
    if doc.pending_save or doc.save_error:
        return {"released": False}
    key = doc.editor_key
    db.commit()
    if key:
        try:
            result = protocol.command({"c": "info", "key": key})
        except Exception:
            return {"released": False}
        # Error 1 means this key never reached (or no longer exists on) the
        # document server. Never discard a live or potentially unsaved session.
        if result.get("error") == 1:
            db.execute(update(Document).where(Document.id == doc.id, Document.editor_key == key)
                       .values(editor_key="", participants={}, pending_save=""))
            db.commit()
            return {"released": True}
    return {"released": False}


def callback_actor(db, doc, payload, *, duplicate_only=False):
    if doc.deleted_at:
        raise HTTPException(403, "文档已移入回收站")
    users = payload.get("users")
    if not isinstance(users, list) or not users:
        raise HTTPException(403, "保存回调缺少编辑人")
    # ONLYOFFICE sends the last editing user for status 2 and 6.
    participant = doc.participants.get(users[0])
    if not participant or not participant["edit"]:
        raise HTTPException(403, "编辑人未获授权")
    session = db.get(AuthSession, participant["session_id"])
    expiry = auth.parse_time(session.expires_at) if session else None
    account = db.get(AuthUser, participant["user_id"])
    if (not session or session.status != "active" or session.user_id != participant["user_id"] or
            not expiry or expiry <= datetime.now() or not account or account.status != "active" or account.force_password_change):
        raise HTTPException(403, "编辑会话已失效")
    user = auth.build_auth_context(db, account)
    scope(user, doc.factory_id)
    if epoch(user) != participant["epoch"]:
        raise HTTPException(403, "编辑权限已失效")
    if access(doc, user) not in {"owner", "edit"}:
        if duplicate_only and participant.get("revoked"):
            return None  # May acknowledge identical bytes, never write a revision.
        raise HTTPException(403, "编辑权限已失效")
    return user.id


def callback(db, document_id, payload):
    status = payload.get("status")
    protection_state, protection_error = None, ""
    if status in {2, 6}:
        preliminary = db.get(Document, document_id)
        if not preliminary or not preliminary.editor_key or preliminary.editor_key != payload.get("key"):
            db.rollback()
            return {"error": 0}
        if status == 6 and (payload.get("forcesavetype") != 0 or not preliminary.pending_save or payload.get("userdata") != preliminary.pending_save):
            db.rollback()
            return {"error": 0}
        callback_actor(db, preliminary, payload, duplicate_only=True)
        extension = preliminary.format
        protection_state = preliminary.protection
        baseline = None
        if protection_state:
            from app.services import online_document_management as management
            baseline_row = db.scalar(select(Revision).where(Revision.document_id == document_id, Revision.revision == protection_state["baseline_revision"]))
            if not baseline_row or baseline_row.sha256 != protection_state["sha256"]:
                raise HTTPException(409, "公式保护基线异常，请联系管理员")
            baseline = management.read_asset(baseline_row)
        db.rollback()
        # Remote I/O must not hold the shared IAM mutation lock.
        data = protocol.fetch_saved(payload.get("url"))
        protocol.validate(data, extension)
        if baseline is not None:
            from app.services.online_document_protection import validate_saved
            try:
                validate_saved(baseline, data, protection_state["rules"])
            except HTTPException as error:
                protection_error = str(error.detail)[:200]
        lock_mutation(db)
    db.execute(update(Document).where(Document.id == document_id).values(id=document_id))
    doc = db.get(Document, document_id, populate_existing=True)
    key, status = payload.get("key"), payload.get("status")
    if not doc or not isinstance(key, str) or not key:
        raise HTTPException(403, "保存会话无效")
    if doc.deleted_at:
        raise HTTPException(403, "文档已移入回收站")
    if doc.editor_key != key:
        # Acknowledge a retried closed session without allowing another write.
        db.rollback()
        return {"error": 0}
    if status in {3, 7}:
        if status == 7 and (payload.get("forcesavetype") != 0 or not doc.pending_save or payload.get("userdata") != doc.pending_save):
            db.rollback()
            return {"error": 0}
        doc.save_error = "编辑器报告保存失败，请保持窗口打开并重试"
        db.commit()
        return {"error": 0}
    if status == 4:
        if doc.pending_save or doc.save_error:
            db.rollback()
            return {"error": 1}
        doc.editor_key, doc.participants = "", {}
        doc.pending_save = ""
        db.commit()
        return {"error": 0}
    if status == 1:
        db.rollback()
        return {"error": 0}
    if status not in {2, 6}:
        raise HTTPException(422, "未知文档回调")
    if status == 6 and (payload.get("forcesavetype") != 0 or not doc.pending_save or payload.get("userdata") != doc.pending_save):
        db.rollback()
        return {"error": 0}
    actor = callback_actor(db, doc, payload, duplicate_only=True)
    digest = hashlib.sha256(data).hexdigest()
    if actor is None and digest != doc.sha256:
        raise HTTPException(403, "已撤销权限的旧编辑人不能写入新内容")
    if doc.protection != protection_state:
        raise HTTPException(409, "公式保护设置已变化，已停止旧会话保存")
    if protection_error:
        doc.save_error = protection_error
        db.commit()
        return {"error": 1}
    if digest != doc.sha256:
        doc.storage_key, doc.sha256 = write_blob(doc.id, data)
        doc.byte_size, doc.revision, doc.updated_at = len(data), doc.revision + 1, now()
        revision(db, doc, actor)
        doc.state_version += 1
        from app.services.online_document_management import audit
        account = db.get(AuthUser, actor)
        user = auth.build_auth_context(db, account)
        audit(db, doc, user, "save", {"attribution": "last_editor", "participants": [pid for pid in doc.participants if pid != SHARING_STATE]})
    state = doc.participants.get(SHARING_STATE, {})
    if status == 6 and state.get("phase") == "saving" and state.get("request_id") == doc.pending_save:
        set_sharing_state(doc, {**state, "phase": "ready"})
    doc.saved_request, doc.pending_save, doc.save_error = doc.pending_save, "", ""
    if status == 2:
        doc.editor_key, doc.participants = "", {}
    db.commit()
    return {"error": 0}

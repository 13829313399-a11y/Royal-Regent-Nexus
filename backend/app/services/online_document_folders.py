"""Owner-private folders, atomic moves and replay-safe classification."""
import hashlib
import json
import unicodedata

from fastapi import HTTPException
from sqlalchemy import select
from app.models.online_documents import (OnlineDocument as Document, OnlineDocumentFolder as Folder,
    OnlineDocumentPlacement as Placement, OnlineDocumentEvent as Event)
from app.services import online_documents as service
from app.services.online_document_management import audit
from app.services.identity_policy import lock_mutation


def owned(user, factory):
    service.scope(user, factory)
    return (Folder.factory_id == factory, Folder.owner_id == user.id, Folder.owner_epoch == service.epoch(user))


def get(db, user, factory, folder_id, *, include_deleted=False):
    folder = db.scalar(select(Folder).where(Folder.id == folder_id, *owned(user, factory)))
    if not folder or (folder.deleted_at and not include_deleted):
        raise HTTPException(404, "文件夹不存在")
    return folder


def listing(db, user, factory):
    folders = db.scalars(select(Folder).where(*owned(user, factory), Folder.deleted_at == "").order_by(Folder.name_key, Folder.id)).all()
    return {"items": [{"id": f.id, "name": f.name, "version": f.version} for f in folders]}


def name_value(value):
    name = unicodedata.normalize("NFC", value.strip())
    if not name or len(name) > 100 or service.storage.safe_name(name) != name:
        raise HTTPException(422, "请输入 1–100 字的有效文件夹名称")
    return name, name.casefold()


def create(db, user, factory, folder_id, name):
    lock_mutation(db)
    conditions = owned(user, factory)
    name, key = name_value(name)
    previous = db.get(Folder, folder_id)
    if previous:
        if (previous.factory_id, previous.owner_id, previous.owner_epoch, previous.name) != (factory, user.id, service.epoch(user), name):
            raise HTTPException(409, "操作编号已使用，请刷新后重试")
        if previous.deleted_at:
            raise HTTPException(409, "原文件夹创建成功后已被删除，请刷新后重新新建")
        return {"id": previous.id, "name": previous.name, "version": previous.version}
    if db.scalar(select(Folder.id).where(*conditions, Folder.name_key == key)):
        raise HTTPException(409, "已有同名文件夹，请使用其他名称")
    folder = Folder(id=folder_id, factory_id=factory, owner_id=user.id, owner_epoch=service.epoch(user),
                    name=name, name_key=key, created_at=service.now())
    db.add(folder); db.commit()
    return {"id": folder.id, "name": folder.name, "version": folder.version}


def remove(db, user, factory, folder_id):
    lock_mutation(db)
    folder = get(db, user, factory, folder_id, include_deleted=True)
    if folder.deleted_at:
        return {"removed": True}
    if db.scalar(select(Placement.document_id).where(Placement.folder_id == folder.id).limit(1)):
        raise HTTPException(409, "请先移出文件夹内的文档；回收站中的文档需先恢复再移出")
    # Retain the creation receipt so a delayed retry cannot resurrect a deletion.
    folder.deleted_at = service.now(); folder.name_key = "deleted:" + folder.id
    db.commit()
    return {"removed": True}


def rename(db, user, factory, folder_id, name, expected_name, expected_version):
    lock_mutation(db)
    folder = get(db, user, factory, folder_id)
    name, key = name_value(name)
    if folder.name == name:
        return {"id": folder.id, "name": folder.name, "version": folder.version}
    if folder.version != expected_version:
        raise HTTPException(409, "文件夹名称已在其他窗口修改，请刷新后重试")
    if folder.name not in (expected_name, name):
        raise HTTPException(409, "文件夹名称已在其他窗口修改，请刷新后重试")
    if db.scalar(select(Folder.id).where(*owned(user, factory), Folder.name_key == key, Folder.id != folder.id)):
        raise HTTPException(409, "已有同名文件夹，请使用其他名称")
    folder.name, folder.name_key = name, key
    folder.version += 1
    db.commit()
    return {"id": folder.id, "name": folder.name, "version": folder.version}


def move(db, user, factory, payload):
    lock_mutation(db)
    service.scope(user, factory)
    items = payload["documents"]
    if len({item["id"] for item in items}) != len(items):
        raise HTTPException(422, "请选择不重复的文档")
    # Authorize the entire batch before inspecting receipts or changing placement.
    docs = [service.get(db, user, factory, item["id"], owner=True, include_deleted=True) for item in items]
    fingerprint = hashlib.sha256(json.dumps({"kind": "move", "factory": factory, "payload": payload}, sort_keys=True).encode()).hexdigest()
    receipts = db.scalars(select(Event).where(Event.document_id.in_([d.id for d in docs]), Event.command_id == payload["request_id"])).all()
    if receipts:
        if len(receipts) != len(docs) or any(e.fingerprint != fingerprint or e.actor_id != user.id or e.actor_epoch != service.epoch(user) for e in receipts):
            raise HTTPException(409, "该操作编号已用于其他请求，请刷新后重试")
        return {"moved": len(docs)}
    target = payload["folder_id"]
    if target:
        get(db, user, factory, target)
    placements = []
    for doc, item in zip(docs, items):
        if doc.deleted_at:
            raise HTTPException(409, "文档已移入回收站，请刷新列表")
        placement = db.get(Placement, doc.id)
        if (placement.version if placement else 0) != item["expected_version"]:
            raise HTTPException(409, "文档分类已在其他窗口变更，请刷新后重新选择")
        placements.append(placement)
    for doc, placement in zip(docs, placements):
        previous = placement.folder_id if placement else None
        if placement:
            placement.folder_id = target; placement.version += 1
        else:
            db.add(Placement(document_id=doc.id, folder_id=target, version=1))
        audit(db, doc, user, "move", {"from_folder": previous, "to_folder": target},
              command_id=payload["request_id"], fingerprint=fingerprint)
    db.commit()
    return {"moved": len(docs)}

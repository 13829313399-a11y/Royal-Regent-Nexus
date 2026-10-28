"""Copy one durable revision to a private document with an immutable receipt."""
from copy import deepcopy
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select

from app.models.online_documents import OnlineDocument as Document, OnlineDocumentEvent as Event, OnlineDocumentPlacement as Placement
from app.services import online_documents as service, online_document_folders as folders
from app.services.online_document_management import audit, read_asset
from app.services.identity_policy import lock_mutation


def duplicate(db, user, factory, source_id, payload):
    lock_mutation(db)
    source = service.get(db, user, factory, source_id, owner=True, include_deleted=True)
    fingerprint = hashlib.sha256(json.dumps({"kind": "copy", "factory": factory, "payload": payload}, sort_keys=True).encode()).hexdigest()
    receipt = db.scalar(select(Event).where(Event.document_id == source.id, Event.command_id == payload["request_id"]))
    if receipt:
        if receipt.fingerprint != fingerprint or receipt.actor_id != user.id or receipt.actor_epoch != service.epoch(user):
            raise HTTPException(409, "操作编号已用于其他请求，请刷新后重试")
        # A retry acknowledges the original copy, even if it was subsequently moved/trashed.
        result = service.get(db, user, factory, receipt.details["copy_id"], owner=True, include_deleted=True)
        return service.summary(result, user)
    if source.deleted_at:
        raise HTTPException(409, "原文档已移入回收站，请先恢复")
    if source.revision != payload["expected_revision"]:
        raise HTTPException(409, "原文档已保存了新版本，请重新选择复制以确认版本")
    target = payload["folder_id"]
    if target:
        folders.get(db, user, factory, target)
    title = service.valid_title(payload["title"], source.format)
    data = read_asset(source)
    document_id = service.uid()
    key, digest = service.write_blob(document_id, data)
    policy = {"rules": deepcopy(source.protection["rules"]), "baseline_revision": 1, "sha256": digest} if source.protection else {}
    doc = Document(id=document_id, factory_id=factory, owner_id=user.id, owner_epoch=service.epoch(user),
                   owner_name=user.display_name, title=title, format=source.format, storage_key=key,
                   sha256=digest, byte_size=len(data), revision=1, grants=[], participants={}, protection=policy,
                   created_at=service.now(), updated_at=service.now())
    db.add(doc); db.flush()
    if target:
        db.add(Placement(document_id=doc.id, folder_id=target, version=1))
    service.revision(db, doc, user.id)
    audit(db, doc, user, "create", {"title": title, "source_id": source.id, "source_revision": source.revision})
    audit(db, source, user, "copy", {"copy_id": doc.id, "title": title, "source_revision": source.revision},
          command_id=payload["request_id"], fingerprint=fingerprint)
    db.commit()
    return service.summary(doc, user)

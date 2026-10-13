from __future__ import annotations
import base64
import hashlib
import json
from uuid import uuid4
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select, func, and_, or_
from app.models.auth import AuthUser, EmployeeProfile
from app.models.collaboration import (MemberProfile, MemberPreferences, MemberContact,
    DirectConversation, ConversationMember, Message, UserStream, UserEvent, Draft, Attachment, Appreciation)
from app.services.identity_resolver import stamp, utc_now, instant
from app.services.transaction_lock import lock_transaction
from app.services.internal_members import require_internal, is_internal
from app.services.auth import build_auth_context

DEFAULT_PREFERENCES = dict(motion="rich", density="comfortable", sound_enabled=False,
    read_receipts_enabled=False, dnd_until=None, send_key="enter", module_shortcuts=[])


def fail(code, message, status=409):
    raise HTTPException(status, {"code": code, "message": message})


def identity(user):
    return user.id, int((user.identity or {}).get("employment_epoch", 1))


def owner(user):
    uid, epoch = identity(user)
    return {"user_id": uid, "employment_epoch": epoch}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def new_id():
    return uuid4().hex


def lock_streams(db, owners, conversation_id=None, assets=()):
    # API writes acquired the shared IAM mutation lock before re-authentication.
    for uid, epoch in sorted(set(owners)):
        lock_transaction(db, "collab-stream", f"{uid}:{epoch}")
    if conversation_id:
        lock_transaction(db, "collab-conversation", conversation_id)
    for aid in sorted(set(assets)):
        lock_transaction(db, "collab-asset", aid)


def emit(db, who, event_type, entity_id="", version=1, conversation_id="", actor_id=""):
    stream = db.get(UserStream, who)
    if stream is None:
        stream = UserStream(user_id=who[0], epoch=who[1], last_event_seq=0, minimum_valid_cursor=0)
        db.add(stream)
    stream.last_event_seq += 1
    event = UserEvent(user_id=who[0], epoch=who[1], event_seq=stream.last_event_seq,
        event_type=event_type, entity_id=entity_id, entity_version=version,
        conversation_id=conversation_id, actor_id=actor_id, created_at=stamp())
    db.add(event)
    db.flush()


def peer_context(db, peer_id):
    row = db.get(AuthUser, peer_id)
    if row is None or row.status != "active":
        fail("MEMBER_UNAVAILABLE", "该成员当前不可联系", 404)
    ctx = build_auth_context(db, row)
    if not is_internal(ctx):
        fail("MEMBER_UNAVAILABLE", "该成员当前不可联系", 404)
    return ctx


def profile_out(row):
    data = dict(bio="", help_topics="", skill_tags=[], theme="celadon", availability="available",
                status_text="", status_expires_at=None, version=0)
    if row:
        data.update({key: getattr(row, key) for key in data})
    if data["status_expires_at"] and instant(data["status_expires_at"]) <= utc_now():
        data.update(availability="available", status_text="", status_expires_at=None)
    return data


def get_profile(db, user):
    return profile_out(db.get(MemberProfile, identity(user)))


def patch_profile(db, user, payload):
    who = identity(user)
    lock_streams(db, [who])
    row = db.get(MemberProfile, who)
    if (row.version if row else 0) != payload.expected_version:
        fail("PROFILE_CONFLICT", "名片已在另一处更新，请重新读取")
    if row is None:
        row = MemberProfile(user_id=who[0], epoch=who[1], version=0)
        db.add(row)
    for key, value in payload.model_dump(exclude={"expected_version"}).items():
        setattr(row, key, value)
    row.version += 1
    emit(db, who, "profile.changed", user.id, row.version)
    db.commit()
    return profile_out(row)


def preferences(db, who):
    row = db.get(MemberPreferences, who)
    return {**DEFAULT_PREFERENCES, **(row.values if row else {}), "version": row.version if row else 0}


def patch_preferences(db, user, payload):
    who = identity(user)
    previous = preferences(db, who)
    affected = list(db.scalars(select(DirectConversation).join(ConversationMember).where(
        ConversationMember.user_id == who[0], ConversationMember.epoch == who[1]))) if previous["read_receipts_enabled"] != payload.read_receipts_enabled else []
    lock_streams(db, [who] + [peer_identity(conv, who) for conv in affected])
    row = db.get(MemberPreferences, who)
    if (row.version if row else 0) != payload.expected_version:
        fail("PREFERENCES_CONFLICT", "偏好已更新，请重新读取")
    if row is None:
        row = MemberPreferences(user_id=who[0], epoch=who[1], version=0)
        db.add(row)
    row.values = payload.model_dump(exclude={"expected_version"})
    row.version += 1
    emit(db, who, "preferences.updated", user.id, row.version)
    for conv in affected:
        # Invalidate an already public projection without disclosing private preferences.
        emit(db, peer_identity(conv, who), "conversation.projection_invalidated", conv.id, conv.revision, conv.id)
    db.commit()
    return preferences(db, who)


def contact(db, user, target_id, add):
    who = identity(user)
    lock_streams(db, [who])
    if add:
        target = identity(peer_context(db, target_id))
        if who[0] == target_id:
            fail("SELF_CONTACT", "无需将自己设为常联系人", 422)
        row = db.get(MemberContact, (*who, *target))
        if row is None:
            db.add(MemberContact(user_id=who[0], epoch=who[1], target_id=target[0], target_epoch=target[1]))
    else:
        for row in db.scalars(select(MemberContact).where(MemberContact.user_id == who[0], MemberContact.epoch == who[1], MemberContact.target_id == target_id)):
            db.delete(row)
    emit(db, who, "contacts.updated", target_id)
    db.commit()
    return {"ok": True}


def conversation(db, user, cid):
    who = identity(user)
    member = db.get(ConversationMember, (cid, *who))
    conv = db.get(DirectConversation, cid) if member else None
    if conv is None:
        fail("CONVERSATION_NOT_FOUND", "会话不存在或不可查看", 404)
    return conv, member


def endpoints(conv):
    return [(conv.low_user_id, conv.low_epoch), (conv.high_user_id, conv.high_epoch)]


def peer_identity(conv, who):
    return next(item for item in endpoints(conv) if item != who)


def direct(db, user, peer_id):
    if peer_id == user.id:
        fail("SELF_CONVERSATION", "请选择其他成员", 422)
    peer = peer_context(db, peer_id)
    lo, hi = sorted([identity(user), identity(peer)])
    lock_streams(db, [lo, hi])
    conv = db.scalar(select(DirectConversation).where(DirectConversation.low_user_id == lo[0],
        DirectConversation.low_epoch == lo[1], DirectConversation.high_user_id == hi[0], DirectConversation.high_epoch == hi[1]))
    if conv is None:
        conv = DirectConversation(id=new_id(), low_user_id=lo[0], low_epoch=lo[1], high_user_id=hi[0], high_epoch=hi[1],
                                  last_message_seq=0, revision=1, created_at=stamp(), updated_at=stamp())
        db.add(conv)
        db.flush()
        for uid, epoch in (lo, hi):
            db.add(ConversationMember(conversation_id=conv.id, user_id=uid, epoch=epoch))
        db.flush()
        for who in (lo, hi):
            emit(db, who, "conversation.updated", conv.id, conv.revision, conv.id)
        db.commit()
    return conversation_out(db, user, conv)


def unread(db, cid, who, through):
    return db.scalar(select(func.count()).select_from(Message).where(Message.conversation_id == cid,
        Message.sender_user_id != who[0], Message.retracted_at.is_(None), Message.message_seq > through)) or 0


def conversation_out(db, user, conv):
    return conversation_batch(db, user, [conv])[0]


def conversation_batch(db, user, rows):
    if not rows:
        return []
    who = identity(user)
    ids = [c.id for c in rows]
    peer_ids = {peer_identity(c, who)[0] for c in rows}
    members = {(m.conversation_id, m.user_id, m.epoch): m for m in db.scalars(select(ConversationMember).where(ConversationMember.conversation_id.in_(ids)))}
    people = {p.id: p for p in db.scalars(select(AuthUser).where(AuthUser.id.in_(peer_ids)))}
    profiles = {p.user_id: p for p in db.scalars(select(EmployeeProfile).where(EmployeeProfile.user_id.in_(peer_ids)))}
    prefs = {(p.user_id, p.epoch): p.values for p in db.scalars(select(MemberPreferences).where(MemberPreferences.user_id.in_(peer_ids)))}
    latest = {m.conversation_id: m for m in db.scalars(select(Message).join(DirectConversation,
        and_(DirectConversation.id == Message.conversation_id, DirectConversation.last_message_seq == Message.message_seq)).where(Message.conversation_id.in_(ids)))}
    unread_counts = dict(db.execute(select(Message.conversation_id, func.count()).join(ConversationMember,
        ConversationMember.conversation_id == Message.conversation_id).where(Message.conversation_id.in_(ids),
        ConversationMember.user_id == who[0], ConversationMember.epoch == who[1], Message.sender_user_id != who[0],
        Message.retracted_at.is_(None), Message.message_seq > ConversationMember.last_read_seq).group_by(Message.conversation_id)).all())
    context = message_context(db, list(latest.values()))
    result = []
    for conv in rows:
        member = members[(conv.id, *who)]
        peer_id, peer_epoch = peer_identity(conv, who)
        person, profile = people.get(peer_id), profiles.get(peer_id)
        available = bool(person and person.status == "active" and (profile.employment_epoch if profile else 1) == peer_epoch and (not profile or profile.employment_status != "left"))
        peer_member = members[(conv.id, peer_id, peer_epoch)]
        receipt = prefs.get((peer_id, peer_epoch), {}).get("read_receipts_enabled", DEFAULT_PREFERENCES["read_receipts_enabled"])
        result.append(dict(id=conv.id, peer=dict(id=peer_id, display_name=person.display_name if person else "成员不可用", available=available),
            last_message_seq=conv.last_message_seq, revision=conv.revision, updated_at=conv.updated_at,
            last_read_seq=member.last_read_seq, unread=unread_counts.get(conv.id, 0), mute_until=member.mute_until,
            pin_order=member.pin_order, archived_at=member.archived_at, version=member.version,
            peer_read_seq=peer_member.last_read_seq if receipt else None,
            last_message=message_out(db, user, latest[conv.id], context) if conv.id in latest else None))
    return result


def conversations(db, user, before=None, limit=30, include_archived=False):
    who = identity(user)
    query = select(DirectConversation).join(ConversationMember).where(ConversationMember.user_id == who[0], ConversationMember.epoch == who[1])
    if not include_archived:
        query = query.where(ConversationMember.archived_at.is_(None))
    if before:
        pin, updated, cid = page_position(before, 3)
        query = query.where(or_(ConversationMember.pin_order < pin,
            and_(ConversationMember.pin_order == pin, DirectConversation.updated_at < updated),
            and_(ConversationMember.pin_order == pin, DirectConversation.updated_at == updated, DirectConversation.id < cid)))
    rows = list(db.scalars(query.order_by(ConversationMember.pin_order.desc(), DirectConversation.updated_at.desc(), DirectConversation.id.desc()).limit(limit + 1)))
    items = conversation_batch(db, user, rows[:limit])
    return {"items": items,
            "next_cursor": page_cursor([items[-1]["pin_order"], rows[limit-1].updated_at, rows[limit-1].id]) if len(rows) > limit else None}


def page_cursor(parts):
    return base64.urlsafe_b64encode(json.dumps(parts).encode()).decode().rstrip("=")


def page_position(value, size):
    try:
        parts = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
        if not isinstance(parts, list) or len(parts) != size or any(not isinstance(p, (str, int)) for p in parts):
            raise ValueError()
        if size == 3 and type(parts[0]) is not int:
            raise ValueError()
        return parts
    except (ValueError, TypeError, UnicodeError):
        fail("INVALID_PAGE_CURSOR", "分页位置无效", 422)


def attachment_out(row):
    return dict(id=row.id, filename=row.filename, mime=row.mime, size=row.size, state=row.state,
                url=f"/api/collaboration/attachments/{row.id}/content")


def message_context(db, rows):
    from .references import preload
    reply_ids = {m.reply_to_id for m in rows if m.reply_to_id and not m.retracted_at}
    replies = {m.id: m for m in db.scalars(select(Message).where(Message.id.in_(reply_ids)))} if reply_ids else {}
    asset_ids = [m.id for m in rows if m.kind == "attachment" and not m.retracted_at]
    assets = {}
    if asset_ids:
        for asset in db.scalars(select(Attachment).where(Attachment.message_id.in_(asset_ids), Attachment.state == "attached")):
            assets.setdefault(asset.message_id, []).append(asset)
    return replies, assets, preload(db, [m.reference for m in rows if m.reference and not m.retracted_at])


def message_out(db, user, row, context=None):
    result = dict(id=row.id, conversation_id=row.conversation_id, message_seq=row.message_seq,
        sender_user_id=row.sender_user_id, kind=row.kind, body="" if row.retracted_at else row.body,
        client_message_id=row.client_message_id if row.sender_user_id == user.id else None,
        created_at=row.created_at, retracted_at=row.retracted_at, version=row.version,
        reply_to_id=row.reply_to_id, reply=None, attachments=[], reference=None)
    if row.retracted_at:
        return result
    if row.reply_to_id:
        original = context[0].get(row.reply_to_id) if context is not None else db.get(Message, row.reply_to_id)
        if original:
            result["reply"] = dict(id=original.id, message_seq=original.message_seq,
                body="消息已撤回" if original.retracted_at else original.body[:160], retracted=bool(original.retracted_at))
    result["attachments"] = [attachment_out(a) for a in (context[1].get(row.id, []) if context is not None else db.scalars(select(Attachment).where(Attachment.message_id == row.id, Attachment.state == "attached")))]
    if row.reference:
        from .references import project
        result["reference"] = project(db, user, row.reference, context[2] if context is not None else None)
    return result


def messages(db, user, cid, before_seq=None, after_seq=None, limit=50, q=""):
    conv, member = conversation(db, user, cid)
    query = select(Message).where(Message.conversation_id == cid)
    if before_seq is not None:
        query = query.where(Message.message_seq < before_seq)
    if after_seq is not None:
        query = query.where(Message.message_seq > after_seq)
    if q:
        query = query.where(Message.retracted_at.is_(None), Message.body.contains(q, autoescape=True))
    rows = list(db.scalars(query.order_by(Message.message_seq.asc() if after_seq is not None else Message.message_seq.desc()).limit(limit + 1)))
    page = sorted(rows[:limit], key=lambda m: m.message_seq)
    return dict(items=[message_out(db, user, row) for row in page], has_more=len(rows) > limit,
        last_read_seq=member.last_read_seq, last_message_seq=conv.last_message_seq)


def submitted(db, user, client_id):
    who = identity(user)
    row = db.scalar(select(Message).where(Message.sender_user_id == who[0], Message.sender_epoch == who[1], Message.client_message_id == client_id))
    if row is None:
        fail("MESSAGE_NOT_FOUND", "尚未找到这次发送", 404)
    conversation(db, user, row.conversation_id)
    return message_out(db, user, row)


def send(db, user, cid, payload):
    conv, _ = conversation(db, user, cid)
    who = identity(user)
    lock_streams(db, endpoints(conv), cid, payload.attachment_ids)
    conv, _ = conversation(db, user, cid)
    content = payload.model_dump(exclude={"client_message_id", "draft_version"})
    content["attachment_ids"] = sorted(content["attachment_ids"])
    request_hash = digest({"conversation_id": cid, **content})
    old = db.scalar(select(Message).where(Message.sender_user_id == who[0], Message.sender_epoch == who[1], Message.client_message_id == payload.client_message_id))
    if old:
        if old.request_hash != request_hash:
            fail("MESSAGE_ID_CONFLICT", "同一发送标识对应不同内容")
        return message_out(db, user, old)
    peer = peer_identity(conv, who)
    if identity(peer_context(db, peer[0])) != peer:
        fail("MEMBER_CHANGED", "对方任职身份已变化，请从目录重新联系", 403)
    if payload.reply_to_id:
        reply = db.get(Message, payload.reply_to_id)
        if reply is None or reply.conversation_id != cid:
            fail("INVALID_REPLY", "引用不属于当前会话", 422)
    assets = []
    for aid in payload.attachment_ids:
        item = db.get(Attachment, aid)
        if item is None or (item.owner_id, item.epoch) != who or item.conversation_id != cid or item.state != "pending" or instant(item.created_at) < utc_now() - timedelta(hours=24):
            fail("ATTACHMENT_UNAVAILABLE", "附件不可用，请重新选择", 404)
        assets.append(item)
    if sum(a.size for a in assets) > 75 * 1024 * 1024:
        fail("ATTACHMENTS_TOO_LARGE", "单条附件总量最多 75 MiB", 413)
    if payload.reference:
        from .references import project
        if not project(db, user, payload.reference.model_dump())["available"]:
            fail("REFERENCE_UNAVAILABLE", "该业务记录当前不可分享", 404)
    conv.last_message_seq += 1
    conv.revision += 1
    conv.updated_at = stamp()
    row = Message(id=new_id(), conversation_id=cid, message_seq=conv.last_message_seq,
        sender_user_id=who[0], sender_epoch=who[1], client_message_id=payload.client_message_id,
        request_hash=request_hash, kind=payload.kind, body=payload.body, reply_to_id=payload.reply_to_id,
        reference=payload.reference.model_dump() if payload.reference else None, created_at=stamp(), version=1)
    db.add(row)
    db.flush()
    for item in assets:
        item.state, item.message_id = "attached", row.id
    for participant in endpoints(conv):
        member = db.get(ConversationMember, (cid, *participant))
        if member.archived_at:
            member.archived_at = None
            member.version += 1
        emit(db, participant, "message.created", row.id, row.version, cid)
    draft = db.get(Draft, (cid, *who))
    if draft and payload.draft_version == draft.version:
        draft.text, draft.reply_to_id, draft.attachment_ids = "", None, []
        draft.version += 1
        draft.updated_at = stamp()
        emit(db, who, "draft.updated", cid, draft.version, cid)
    db.commit()
    return message_out(db, user, row)


def retract(db, user, mid):
    row = db.get(Message, mid)
    if not row:
        fail("MESSAGE_NOT_FOUND", "消息不可查看", 404)
    conv, _ = conversation(db, user, row.conversation_id)
    lock_streams(db, endpoints(conv), conv.id)
    row = db.get(Message, mid)
    if (row.sender_user_id, row.sender_epoch) != identity(user):
        fail("MESSAGE_NOT_FOUND", "消息不可撤回", 404)
    if row.retracted_at:
        return message_out(db, user, row)
    if utc_now() - instant(row.created_at) > timedelta(seconds=120):
        fail("RETRACT_EXPIRED", "已超过 120 秒撤回时限")
    row.retracted_at, row.body = stamp(), ""
    row.reference = None
    row.version += 1
    conv.revision += 1
    for participant in endpoints(conv):
        emit(db, participant, "message.retracted", row.id, row.version, conv.id)
    db.commit()
    return message_out(db, user, row)


def mark_read(db, user, cid, seq):
    conv, _ = conversation(db, user, cid)
    who = identity(user)
    share = preferences(db, who)["read_receipts_enabled"]
    lock_streams(db, endpoints(conv) if share else [who], cid)
    conv, member = conversation(db, user, cid)
    if seq > conv.last_message_seq:
        fail("READ_AHEAD", "已读位置超过已提交消息", 422)
    if seq > member.last_read_seq:
        member.last_read_seq = seq
        member.version += 1
        emit(db, who, "read.updated", cid, member.version, cid, user.id)
        if share:
            emit(db, peer_identity(conv, who), "read.updated", cid, member.version, cid, user.id)
        db.commit()
    return conversation_out(db, user, conv)


def conversation_preferences(db, user, cid, payload):
    who = identity(user)
    lock_streams(db, [who], cid)
    conv, member = conversation(db, user, cid)
    if member.version != payload.expected_version:
        fail("CONVERSATION_CONFLICT", "会话偏好已更新，请重新读取")
    member.mute_until, member.pin_order = payload.mute_until, payload.pin_order
    member.archived_at = stamp() if payload.archived else None
    member.version += 1
    emit(db, who, "conversation.updated", cid, member.version, cid)
    db.commit()
    return conversation_out(db, user, conv)


def get_draft(db, user, cid):
    conversation(db, user, cid)
    row = db.get(Draft, (cid, *identity(user)))
    result = dict(text=row.text, reply_to_id=row.reply_to_id, attachment_ids=row.attachment_ids, version=row.version) if row else dict(text="", reply_to_id=None, attachment_ids=[], version=0)
    unavailable = []
    for aid in result["attachment_ids"]:
        asset = db.get(Attachment, aid)
        if not asset or asset.state != "pending" or instant(asset.created_at) <= utc_now() - timedelta(hours=24):
            unavailable.append(aid)
    if unavailable:
        result["unavailable_attachment_ids"] = unavailable
    return result


def patch_draft(db, user, cid, payload):
    who = identity(user)
    lock_streams(db, [who], cid)
    conversation(db, user, cid)
    row = db.get(Draft, (cid, *who))
    if (row.version if row else 0) != payload.expected_version:
        fail("DRAFT_CONFLICT", "另一台设备已更新草稿，本机输入已保留")
    if payload.reply_to_id:
        reply = db.get(Message, payload.reply_to_id)
        if reply is None or reply.conversation_id != cid:
            fail("INVALID_REPLY", "引用不属于当前会话", 422)
    for aid in payload.attachment_ids:
        a = db.get(Attachment, aid)
        if not a or (a.owner_id, a.epoch) != who or a.conversation_id != cid or a.state != "pending":
            fail("ATTACHMENT_UNAVAILABLE", "暂存附件不可用", 404)
    if row is None:
        row = Draft(conversation_id=cid, user_id=who[0], epoch=who[1], version=0)
        db.add(row)
    row.text, row.reply_to_id, row.attachment_ids = payload.text, payload.reply_to_id, payload.attachment_ids
    row.version += 1
    row.updated_at = stamp()
    emit(db, who, "draft.updated", cid, row.version, cid)
    db.commit()
    return get_draft(db, user, cid)


def cursor(who, seq):
    return base64.urlsafe_b64encode(json.dumps([1, *who, seq], separators=(",", ":")).encode()).decode().rstrip("=")


def parse_cursor(value, who, stream):
    try:
        version, uid, epoch, seq = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
        if version != 1 or (uid, epoch) != who or type(seq) is not int:
            raise ValueError()
    except (ValueError, TypeError, UnicodeError):
        fail("INVALID_CURSOR", "同步位置与当前身份不一致", 422)
    head, floor = (stream.last_event_seq, stream.minimum_valid_cursor) if stream else (0, 0)
    if seq < floor or seq > head:
        fail("RESET_REQUIRED", "同步位置已过期，请重新加载")
    return seq


def total_unread(db, user):
    who = identity(user)
    return db.scalar(select(func.count()).select_from(Message).join(ConversationMember,
        ConversationMember.conversation_id == Message.conversation_id).where(
        ConversationMember.user_id == who[0], ConversationMember.epoch == who[1],
        Message.message_seq > ConversationMember.last_read_seq, Message.sender_user_id != who[0], Message.retracted_at.is_(None))) or 0


def bootstrap(db, user):
    who = identity(user)
    stream = db.get(UserStream, who)
    return dict(owner=owner(user), conversations=conversations(db, user, include_archived=True), unread=total_unread(db, user),
        preferences=preferences(db, who), cursor=cursor(who, stream.last_event_seq if stream else 0), server_now=stamp())


def sync(db, user, value, limit=100):
    who = identity(user)
    stream = db.get(UserStream, who)
    seq = parse_cursor(value, who, stream)
    rows = list(db.scalars(select(UserEvent).where(UserEvent.user_id == who[0], UserEvent.epoch == who[1],
        UserEvent.event_seq > seq).order_by(UserEvent.event_seq).limit(limit + 1)))
    events = []
    for row in rows[:limit]:
        item = dict(event_seq=row.event_seq, type=row.event_type, entity_id=row.entity_id,
                    entity_version=row.entity_version, conversation_id=row.conversation_id)
        if row.event_type == "read.updated" and row.actor_id != user.id:
            conv, _ = conversation(db, user, row.conversation_id)
            actor_who = next(w for w in endpoints(conv) if w[0] == row.actor_id)
            if not preferences(db, actor_who)["read_receipts_enabled"]:
                item = dict(event_seq=row.event_seq, type="checkpoint")
        if row.event_type.startswith("message."):
            message = db.get(Message, row.entity_id)
            conversation(db, user, message.conversation_id)
            item["message"] = message_out(db, user, message)
        if row.event_type == "appreciation.created":
            appreciation = db.get(Appreciation, row.entity_id)
            item["notify_receiver"] = bool(appreciation and (appreciation.receiver_id, appreciation.receiver_epoch) == who)
        events.append(item)
    consumed = rows[min(len(rows), limit) - 1].event_seq if rows else seq
    return dict(owner=owner(user), events=events, cursor=cursor(who, consumed), has_more=len(rows) > limit,
                unread=total_unread(db, user), server_now=stamp())


def appreciate(db, user, payload):
    who = identity(user)
    if user.id == payload.receiver_id:
        fail("SELF_APPRECIATION", "请选择帮助你的同事", 422)
    # Resolve idempotency before checking whether the original receiver left.
    old = db.scalar(select(Appreciation).where(Appreciation.sender_id == who[0], Appreciation.sender_epoch == who[1], Appreciation.client_request_id == payload.client_request_id))
    request_hash = digest(payload.model_dump(exclude={"client_request_id"}))
    if old:
        if old.request_hash != request_hash:
            fail("APPRECIATION_ID_CONFLICT", "感谢标识对应不同内容")
        return appreciation_out(db, user, old)
    peer = identity(peer_context(db, payload.receiver_id))
    lock_streams(db, [who, peer])
    row = Appreciation(id=new_id(), sender_id=who[0], sender_epoch=who[1], receiver_id=peer[0], receiver_epoch=peer[1],
        client_request_id=payload.client_request_id, request_hash=request_hash, category=payload.category, text=payload.text,
        created_at=stamp(), version=1, private_pin_order=0)
    db.add(row)
    for participant in [who, peer]:
        emit(db, participant, "appreciation.created", row.id, row.version)
    db.commit()
    return appreciation_out(db, user, row)


def appreciation_out(db, user, row):
    who = identity(user)
    received = who == (row.receiver_id, row.receiver_epoch)
    if not received and who != (row.sender_id, row.sender_epoch):
        fail("APPRECIATION_NOT_FOUND", "感谢卡不可查看", 404)
    sender, receiver = db.get(AuthUser, row.sender_id), db.get(AuthUser, row.receiver_id)
    return dict(id=row.id, sender_id=row.sender_id, receiver_id=row.receiver_id,
        sender_name=sender.display_name if sender else "成员", receiver_name=receiver.display_name if receiver else "成员",
        category=row.category, text=row.text, created_at=row.created_at, version=row.version if received else None,
        receiver_seen_at=row.receiver_seen_at if received else None, private_pin_order=row.private_pin_order if received else 0,
        hidden_at=row.hidden_at if received else None)


def appreciations(db, user, sent=False, before=None, limit=30):
    who = identity(user)
    query = select(Appreciation).where(and_(Appreciation.sender_id == who[0], Appreciation.sender_epoch == who[1]) if sent
        else and_(Appreciation.receiver_id == who[0], Appreciation.receiver_epoch == who[1]))
    if before:
        position = page_position(before, 2 if sent else 3)
        created, aid = position[-2:]
        older = or_(Appreciation.created_at < created, and_(Appreciation.created_at == created, Appreciation.id < aid))
        query = query.where(older if sent else or_(Appreciation.private_pin_order < position[0],
            and_(Appreciation.private_pin_order == position[0], older)))
    order = [] if sent else [Appreciation.private_pin_order.desc()]
    rows = list(db.scalars(query.order_by(*order, Appreciation.created_at.desc(), Appreciation.id.desc()).limit(limit + 1)))
    # Retain the loaded users while assembling this page; no per-card lookup.
    people = list(db.scalars(select(AuthUser).where(AuthUser.id.in_({uid for r in rows for uid in (r.sender_id, r.receiver_id)}))))
    unseen = db.scalar(select(func.count()).select_from(Appreciation).where(Appreciation.receiver_id == who[0], Appreciation.receiver_epoch == who[1],
        Appreciation.receiver_seen_at.is_(None), Appreciation.hidden_at.is_(None))) or 0
    return dict(items=[appreciation_out(db, user, r) for r in rows[:limit]], unseen=unseen,
                next_cursor=page_cursor(([] if sent else [rows[limit-1].private_pin_order]) + [rows[limit-1].created_at, rows[limit-1].id]) if len(rows) > limit else None)


def patch_appreciation(db, user, aid, payload):
    who = identity(user)
    lock_streams(db, [who])
    row = db.get(Appreciation, aid)
    if not row or (row.receiver_id, row.receiver_epoch) != who:
        fail("APPRECIATION_NOT_FOUND", "感谢卡不可查看", 404)
    if row.version != payload.expected_version:
        fail("APPRECIATION_CONFLICT", "感谢卡已更新，请刷新")
    if payload.private_pin_order:
        count = db.scalar(select(func.count()).select_from(Appreciation).where(Appreciation.receiver_id == who[0], Appreciation.receiver_epoch == who[1],
            Appreciation.private_pin_order > 0, Appreciation.id != aid)) or 0
        if count >= 3:
            fail("PIN_LIMIT", "最多置顶三张感谢卡", 422)
    row.private_pin_order = payload.private_pin_order
    row.hidden_at = stamp() if payload.hidden else None
    if payload.seen and not row.receiver_seen_at:
        row.receiver_seen_at = stamp()
    row.version += 1
    emit(db, who, "appreciation.updated", row.id, row.version)
    db.commit()
    return appreciation_out(db, user, row)

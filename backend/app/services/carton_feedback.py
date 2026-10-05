import hashlib
import json
from io import BytesIO
from uuid import uuid4
from PIL import Image, UnidentifiedImageError
from fastapi import HTTPException
from sqlalchemy import select, update, func, or_
from sqlalchemy.exc import IntegrityError
from app.models.carton_feedback import CartonFeedback, CartonFeedbackImage, CartonFeedbackReply, CartonFeatureUpdate
from app.services.auth import authorization_decision
from app.services.carton_procurement import CARTON_DEPARTMENTS, require_carton_factory, now_text, _audit

MANAGE = "system:feedback_manage"
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def can_manage(user, factory):
    return authorization_decision(user, MANAGE, factory, "*")[0]


def scope(user, factory):
    factory = require_carton_factory(factory)
    if not any(authorization_decision(user, "carton_procurement:read", factory, department)[0] for department in CARTON_DEPARTMENTS):
        raise HTTPException(403, "没有此厂区的纸箱模块访问权限")
    return factory


def require_manager(user, factory):
    if not can_manage(user, factory):
        raise HTTPException(403, "只有有权限的管理员可以处理反馈和发布更新")


def feedback_row(db, user, factory, key):
    row = db.scalar(select(CartonFeedback).where(CartonFeedback.id == key, CartonFeedback.factory_id == factory))
    if row is None or (row.author_id != user.id and not can_manage(user, factory)):
        raise HTTPException(404, "未找到可查看的反馈")
    return row


def feedback_out(row):
    return dict(id=row.id, factory_id=row.factory_id, author_id=row.author_id, author_name=row.author_name,
        title=row.title, description=row.description, context_path=row.context_path, status=row.status,
        revision=row.revision, created_at=row.created_at, updated_at=row.updated_at)


def detail(db, user, factory, key):
    row = feedback_row(db, user, factory, key)
    result = feedback_out(row)
    result["images"] = list(db.scalars(select(CartonFeedbackImage.id).where(CartonFeedbackImage.feedback_id == key,
        CartonFeedbackImage.factory_id == factory).order_by(CartonFeedbackImage.ordinal)))
    replies = list(db.scalars(select(CartonFeedbackReply).where(CartonFeedbackReply.feedback_id == key,
        CartonFeedbackReply.factory_id == factory).order_by(CartonFeedbackReply.revision.desc()).limit(100)))
    result["replies"] = [dict(id=r.id, author_name=r.author_name, body=r.body, status=r.status, created_at=r.created_at)
        for r in reversed(replies)]
    return result


def workspace(db, user, factory, all_feedback=False, *, search="", status="", date_from="", date_to="", sort="DESC", limit=100, offset=0, updates_offset=0):
    from app.services.carton_query import date_bounds, literal_pattern
    first, after = date_bounds(date_from, date_to)
    if all_feedback:
        require_manager(user, factory)
    statement = select(CartonFeedback).where(CartonFeedback.factory_id == factory)
    if not all_feedback:
        statement = statement.where(CartonFeedback.author_id == user.id)
    updates = select(CartonFeatureUpdate).where(CartonFeatureUpdate.factory_id == factory)
    if status:
        statement = statement.where(CartonFeedback.status == status)
    if search:
        pattern = literal_pattern(search)
        statement = statement.where(or_(*(column.ilike(pattern, escape="!") for column in
            (CartonFeedback.title, CartonFeedback.description, CartonFeedback.author_name))))
        updates = updates.where(or_(*(column.ilike(pattern, escape="!") for column in
            (CartonFeatureUpdate.title, CartonFeatureUpdate.body, CartonFeatureUpdate.author_name))))
    if first:
        statement = statement.where(CartonFeedback.created_at >= first)
        updates = updates.where(CartonFeatureUpdate.created_at >= first)
    if after:
        statement = statement.where(CartonFeedback.created_at < after)
        updates = updates.where(CartonFeatureUpdate.created_at < after)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    updates_total = db.scalar(select(func.count()).select_from(updates.subquery())) or 0
    ascending = sort == "ASC"
    rows = db.scalars(statement.order_by(CartonFeedback.updated_at.asc() if ascending else CartonFeedback.updated_at.desc(), CartonFeedback.id).limit(limit).offset(offset))
    return dict(can_manage=can_manage(user, factory), feedbacks=[feedback_out(r) for r in rows],
        updates=[dict(id=r.id, title=r.title, body=r.body, author_name=r.author_name, created_at=r.created_at)
            for r in db.scalars(updates.order_by(CartonFeatureUpdate.created_at.asc() if ascending else CartonFeatureUpdate.created_at.desc(), CartonFeatureUpdate.id).limit(limit).offset(updates_offset))],
        total=total, updates_total=updates_total, limit=limit, offset=offset, updates_offset=updates_offset)


def normalize_image(content):
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "截图单张最多 5 MB")
    try:
        with Image.open(BytesIO(content)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"} or image.width * image.height > 16_000_000:
                raise HTTPException(422, "截图仅支持 PNG、JPG、WebP，像素总数不能超过 1600 万")
            image.load()
            normalized = image.convert("RGBA")
            output_image = Image.new("RGBA", normalized.size, "white")
            output_image.alpha_composite(normalized)
            buffer = BytesIO()
            output_image.convert("RGB").save(buffer, "PNG")
            result = buffer.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(422, "截图文件损坏或不是支持的图片")
    if len(result) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "截图处理后超过 5 MB，请缩小图片")
    return result


def create(db, user, factory, title, description, context_path, request_key, images):
    title, description = title.strip(), description.strip()
    if not title or not description or len(title) > 120 or len(description) > 6000:
        raise HTTPException(422, "请填写问题标题和说明；标题最多 120 字，说明最多 6000 字")
    if not request_key or len(request_key) > 64:
        raise HTTPException(422, "提交标识无效，请重新打开反馈表单")
    # Store only a module path, never credentials, page text or arbitrary URL queries.
    if context_path not in {"/modules/pmc-warehouse/carton-procurement", "/carton-supplier"}:
        context_path = "/modules/pmc-warehouse/carton-procurement"
    payload = json.dumps([title, description, context_path, [hashlib.sha256(i).hexdigest() for i in images]], ensure_ascii=False)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    def existing():
        row = db.scalar(select(CartonFeedback).where(CartonFeedback.factory_id == factory,
            CartonFeedback.author_id == user.id, CartonFeedback.request_key == request_key))
        if row and row.payload_sha256 != digest:
            raise HTTPException(409, "此提交已保存且内容不同，请先查看我的反馈再重新提交")
        return row
    if row := existing():
        return detail(db, user, factory, row.id)
    key, now = f"CF-{uuid4().hex}", now_text()
    row = CartonFeedback(id=key, factory_id=factory, author_id=user.id, author_name=user.display_name,
        title=title, description=description, context_path=context_path, request_key=request_key, payload_sha256=digest,
        status="OPEN", revision=1, created_at=now, updated_at=now)
    try:
        db.add(row)
        db.flush()
        for ordinal, image in enumerate(images):
            db.add(CartonFeedbackImage(id=f"CFI-{uuid4().hex}", factory_id=factory, feedback_id=key, content=image, ordinal=ordinal, created_at=now))
        _audit(db, user, factory, "FEEDBACK_CREATED", "carton_feedback", key, {"image_count": len(images)})
        db.commit()
    except IntegrityError:
        db.rollback()
        if row := existing():
            return detail(db, user, factory, row.id)
        raise
    return detail(db, user, factory, key)


def reply(db, user, factory, key, payload):
    require_manager(user, factory)
    feedback_row(db, user, factory, key)
    now = now_text()
    changed = db.execute(update(CartonFeedback).where(CartonFeedback.id == key,
        CartonFeedback.factory_id == factory, CartonFeedback.revision == payload.revision)
        .values(status=payload.status, revision=payload.revision + 1, updated_at=now))
    if changed.rowcount != 1:
        raise HTTPException(409, "反馈已被更新，请刷新后重新回复")
    db.add(CartonFeedbackReply(id=f"CFR-{uuid4().hex}", feedback_id=key, factory_id=factory,
        author_id=user.id, author_name=user.display_name, body=payload.body, status=payload.status, revision=payload.revision + 1, created_at=now))
    _audit(db, user, factory, "FEEDBACK_REPLIED", "carton_feedback", key, {"status": payload.status, "revision": payload.revision + 1})
    db.commit()
    return detail(db, user, factory, key)


def publish(db, user, factory, payload):
    require_manager(user, factory)
    def existing():
        row = db.scalar(select(CartonFeatureUpdate).where(CartonFeatureUpdate.factory_id == factory,
            CartonFeatureUpdate.author_id == user.id, CartonFeatureUpdate.request_key == payload.request_key))
        if row and (row.title != payload.title or row.body != payload.body):
            raise HTTPException(409, "此更新说明已发布且内容不同，请刷新核对后重新发布")
        return row
    if row := existing():
        return {"id": row.id}
    now, key = now_text(), f"CFU-{uuid4().hex}"
    db.add(CartonFeatureUpdate(id=key, factory_id=factory, title=payload.title, body=payload.body,
        author_id=user.id, author_name=user.display_name, request_key=payload.request_key, created_at=now))
    _audit(db, user, factory, "FEATURE_UPDATE_PUBLISHED", "carton_feature_update", key, {})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if row := existing():
            return {"id": row.id}
        raise
    return {"id": key}

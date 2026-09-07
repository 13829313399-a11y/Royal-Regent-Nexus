from hashlib import sha256
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import inspect

from app.api.three_d_printing import MigrationDb, MigrationUser, _ensure_permission
from app.core.config import settings
from app.schemas.three_d_operations import Action, SaveResource
from app.services import three_d_operations as service

router = APIRouter(
    prefix="/api/three-d-printing/operations", tags=["three-d-operations"]
)


def guard(db, user, factory_id, permission="read"):
    _ensure_permission(db, user, "three_d_printing:" + permission, factory_id)
    if not inspect(db.get_bind()).has_table(service.MODEL.__tablename__):
        raise HTTPException(503, "生产协同需要先备份并升级数据库至 20260904_0099")


@router.get("/resources/{kind}")
def resources(
    kind: str,
    db: MigrationDb,
    user: MigrationUser,
    factory_id: str = "huakang-a",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    guard(db, user, factory_id)
    return service.resources(db, kind, page, page_size)


@router.post("/resources/{kind}")
def save(kind: str, payload: SaveResource, db: MigrationDb, user: MigrationUser):
    guard(db, user, payload.factory_id, "operate")
    if kind == "file":
        raise HTTPException(422, "请使用附件上传接口")
    return service.out(service.save(db, kind=kind, payload=payload, user=user))


@router.post("/resources/{item_id}/actions")
def action(item_id: str, payload: Action, db: MigrationDb, user: MigrationUser):
    guard(db, user, payload.factory_id, "operate")
    return service.out(service.act(db, item_id=item_id, payload=payload, user=user))


@router.post("/runs/{record_id}/match")
def match(record_id: str, payload: Action, db: MigrationDb, user: MigrationUser):
    guard(db, user, payload.factory_id, "operate")
    return service.business.production_record_out(
        service.match_run(db, record_id=record_id, payload=payload, user=user)
    )


@router.get("/recommendations")
def recommendations(
    db: MigrationDb, user: MigrationUser, factory_id: str = "huakang-a"
):
    guard(db, user, factory_id)
    return service.recommendations(db)


@router.get("/analytics")
def analytics(
    db: MigrationDb,
    user: MigrationUser,
    factory_id: str = "huakang-a",
    days: int = Query(30, ge=1, le=366),
):
    guard(db, user, factory_id)
    return service.analytics(db, days)


@router.get("/thread/{record_id}")
def thread(
    record_id: str, db: MigrationDb, user: MigrationUser, factory_id: str = "huakang-a"
):
    guard(db, user, factory_id)
    return service.digital_thread(db, record_id)


@router.post("/files")
async def upload(
    db: MigrationDb,
    user: MigrationUser,
    file: Annotated[UploadFile, File()],
    factory_id: str = "huakang-a",
):
    guard(db, user, factory_id, "operate")
    name = Path((file.filename or "").replace("\\", "/")).name[:255]
    extension = Path(name).suffix.lower()
    if extension not in {".3mf", ".stl", ".gcode", ".pdf", ".png", ".jpg"}:
        raise HTTPException(422, "支持 3MF/STL/Gcode/PDF/PNG/JPG 附件")
    content = await file.read(10485761)
    await file.close()
    if not content or len(content) > 10485760:
        raise HTTPException(413, "附件须为 1 字节至 10MB")
    digest = sha256(content).hexdigest()
    directory = Path(settings.three_d_asset_dir) / "operations"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / digest
    # Immutable content addressed storage; metadata is committed separately.
    try:
        with destination.open("xb") as handle:
            handle.write(content)
    except FileExistsError:
        if sha256(destination.read_bytes()).hexdigest() != digest:
            raise HTTPException(409, "附件校验失败")
    payload = SaveResource(
        resource_key=uuid4().hex,
        idempotency_key=uuid4().hex,
        reason="上传版本附件",
        data={
            "name": name,
            "extension": extension,
            "sha256": digest,
            "size": len(content),
        },
    )
    return service.out(service.save(db, kind="file", payload=payload, user=user))


@router.get("/files/{item_id}")
def download(
    item_id: str, db: MigrationDb, user: MigrationUser, factory_id: str = "huakang-a"
):
    guard(db, user, factory_id)
    row = db.get(service.MODEL, item_id)
    if (
        not row
        or row.factory_id != factory_id
        or row.kind != "file"
        or row.status != "active"
    ):
        raise HTTPException(404)
    data = service.out(row)["data"]
    from app.schemas.three_d_operations import FileMetadata

    data = FileMetadata.model_validate(data)
    path = Path(settings.three_d_asset_dir) / "operations" / data.sha256
    if not path.is_file():
        raise HTTPException(404, "附件文件缺失")
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=data.name,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )

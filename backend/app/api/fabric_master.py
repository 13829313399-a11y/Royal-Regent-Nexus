from typing import Literal
from fastapi import APIRouter, Depends, Query, File, UploadFile, Form, Response
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import AuthContext, can, get_current_user
from app.api.fabric_procurement import authorize
from app.services import fabric_master as service
from app.schemas.fabric_master import MasterKind, SaveMasterRequest, LocationPreviewRequest, LocationApplyRequest, WarehouseRenameRequest
from app.services import fabric_master_locations as locations

router = APIRouter(prefix="/api/fabric-warehouse/master", tags=["fabric-warehouse"])


@router.get("")
def records(factory_id: str, kind: MasterKind, search: str = Query("", max_length=128), status: Literal["ALL", "ACTIVE", "DRAFT", "INACTIVE"] = "ALL",
            sort: Literal["CODE", "NAME", "UPDATED"] = "CODE", db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, factory_id, "read")
    return {**service.list_records(db, kind, search, status, sort), "can_manage": can(actor, "fabric_warehouse:import", factory_id, "pmc-warehouse")}


@router.get("/candidates")
def candidates(factory_id: str, kind: MasterKind, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, factory_id, "read")
    return service.candidates(db, kind)


@router.post("")
def save(payload: SaveMasterRequest, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, payload.factory_id, "import")
    return service.save(db, actor, payload)


@router.get("/locations/template")
def location_template(factory_id: str, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, factory_id, "read")
    return Response(locations.template(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=fabric-locations.xlsx"})


@router.post("/locations/file-preview")
async def location_file_preview(factory_id: str = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, factory_id, "import")
    rows = locations.file_rows(await file.read(5 * 1024 * 1024 + 1), file.filename or "")
    payload = LocationPreviewRequest(factory_id=factory_id, rows=rows)
    return {**locations.preview(db, actor, payload), "rows": [row.model_dump() for row in rows]}


@router.post("/locations/preview")
def location_preview(payload: LocationPreviewRequest, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, payload.factory_id, "import")
    return locations.preview(db, actor, payload)


@router.post("/locations/apply")
def location_apply(payload: LocationApplyRequest, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, payload.factory_id, "import")
    return locations.apply(db, actor, payload)


@router.post("/locations/rename-warehouse")
def warehouse_rename(payload: WarehouseRenameRequest, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, payload.factory_id, "import")
    return locations.rename(db, actor, payload)


@router.get("/{record_id}/history")
def history(record_id: str, factory_id: str, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, factory_id, "read")
    return service.history(db, record_id)

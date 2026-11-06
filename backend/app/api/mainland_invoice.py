"""Online generation only: private templates, no invoice uploads or ledger writes."""
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.services.auth import AuthContext, can, get_current_user

router = APIRouter(prefix="/api/mainland-invoices", tags=["mainland-invoices"])
Factory = Literal["huakang-a", "huakang-b", "huakang-d"]
PERMISSION = "mainland_invoice:generate"
NO_STORE = {"Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff"}

# The legacy engine paths are identifiers, never public static URLs.
TEMPLATES = {
    "huakang-a": {
        "a-zuru": ("hka-tpl", "华康A-zuru.xlsx"),
        "a-headstart": ("hka-tpl", "华康A-Headstart.xlsx"),
        "a-360": ("hka-tpl", "华康A-360.xlsx"),
        "a-green-toys": ("hka-tpl", "华康A-GT.xlsx"),
        "a-magic-time": ("hka-tpl", "华康A-适时达.xlsx"),
        "a-strottman": ("hka-tpl", "华康A-建文.xlsx"),
    },
    "huakang-b": {
        "b-trade": ("hkb-tpl", "华康B贸易.xlsx"),
        "b-international": ("hkb-tpl", "华康B国际.xlsx"),
    },
    "huakang-d": {
        "d-zuru": ("hkd-tpl", "华康D-ZURU.xlsx"),
        "d-jazwares": ("hkd-tpl", "华康D-Jazwares.xlsx"),
        "d-strottman": ("hkd-tpl", "华康D-建文.xlsx"),
        "d-maxx": ("hkd-tpl", "华康D-MAXX.xlsx"),
        "d-index": ("hkd-tpl", "华康D-Index.xlsx"),
        "d-seasons-huijie": ("hkd-tpl", "华康D-思信（辉捷）.xlsx"),
        "d-seasons-kangyi": ("hkd-tpl", "华康D-思信（康宜）.xlsx"),
        "d-seasons-indonesia": ("hkd-tpl", "华康D-思信印尼（辉捷RRI）.xlsx"),
    },
}


def require_access(db: Session, user: AuthContext, factory_id: Factory) -> None:
    # New financial module always honors canonical denies/catalog/account state,
    # even if the host keeps legacy/shadow mode for existing modules.
    if not can(user, PERMISSION, factory_id, "sales-business"):
        raise HTTPException(403, "无本厂区业务部大陆发票权限", headers=NO_STORE)
    if not settings.mainland_invoice_enabled:
        raise HTTPException(503, "大陆发票模块尚未启用", headers=NO_STORE)


def template_file(factory_id: Factory, template_id: str) -> Path:
    entry = TEMPLATES[factory_id].get(template_id)
    if entry is None:
        raise HTTPException(404, "模板不存在", headers=NO_STORE)
    root = Path(settings.mainland_invoice_template_dir)
    file = root / factory_id / entry[1]
    # Read-only private mount managed by the administrator. No path supplied by
    # the browser is joined to the filesystem; reject symlinks at every level.
    if not root.is_absolute() or any(p.is_symlink() for p in (file, *file.parents)):
        raise HTTPException(503, "私有模板目录配置无效", headers=NO_STORE)
    if not file.is_file():
        raise HTTPException(503, "当前厂区模板尚未安装完整", headers=NO_STORE)
    return file


@router.get("/context")
def context(
    response: Response,
    factory_id: Factory,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    require_access(db, current_user, factory_id)
    for key in TEMPLATES[factory_id]:
        template_file(factory_id, key)
    response.headers.update(NO_STORE)
    return {
        "factory_id": factory_id,
        "user_id": current_user.id,
        "employment_epoch": int((current_user.identity or {}).get("employment_epoch", 1)),
        "mode": "generate-download-only",
        "templates": {
            "/" + folder + "/" + name: key
            for key, (folder, name) in TEMPLATES[factory_id].items()
        },
    }


@router.get("/templates/{template_id}")
def read_template(
    template_id: str,
    factory_id: Factory,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    require_access(db, current_user, factory_id)
    path = template_file(factory_id, template_id)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
        headers=NO_STORE,
    )

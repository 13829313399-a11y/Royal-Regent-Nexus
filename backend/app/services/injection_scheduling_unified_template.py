from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import HTTPException

TEMPLATE_VERSION = "RR-ISP-1.0"
TEMPLATE_SHA256 = "e6128bddc6e93e66016bf72f56cc2be20c8a14731e72e3e6ba408c486c877b7a"
TEMPLATE_RESOURCE = (
    Path(__file__).resolve().parents[1]
    / "resources"
    / "injection_scheduling"
    / "unified_injection_plan_v1.xlsx"
)
FACTORY_FILE_NAMES = {
    "huaxing": "华兴",
    "huakang-a": "华康A",
    "huakang-b": "华康B",
}


def unified_template_download(factory_id: str) -> tuple[Path, str]:
    factory_name = FACTORY_FILE_NAMES.get(factory_id)
    if factory_name is None:
        raise HTTPException(status_code=422, detail="当前厂区不适用统一注塑排产模板")
    if not TEMPLATE_RESOURCE.is_file():
        raise HTTPException(status_code=503, detail="统一注塑排产模板资源尚未部署")
    digest = hashlib.sha256(TEMPLATE_RESOURCE.read_bytes()).hexdigest()
    if digest != TEMPLATE_SHA256:
        raise HTTPException(status_code=503, detail="统一注塑排产模板资源校验失败")
    return (
        TEMPLATE_RESOURCE,
        f"{factory_name}_统一注塑排产导入模板_{TEMPLATE_VERSION}.xlsx",
    )

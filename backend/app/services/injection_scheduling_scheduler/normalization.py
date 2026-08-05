from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.core.time import BUSINESS_TIME_ZONE, parse_business_timestamp


def load_json(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def as_business_datetime(value: str) -> datetime:
    parsed = parse_business_timestamp(value)
    if parsed is None:
        raise ValueError(f"无效排期时间：{value}")
    return parsed.astimezone(BUSINESS_TIME_ZONE)


def iso_seconds(value: datetime) -> str:
    return value.astimezone(BUSINESS_TIME_ZONE).isoformat(timespec="seconds")


def color_rank(value: str, configured_scale: list[str] | None = None) -> int:
    normalized = value.strip().lower()
    scale = [item.strip().lower() for item in configured_scale or []]
    if normalized and normalized in scale:
        return scale.index(normalized)
    keywords = (
        (0, ("白", "透明", "clear", "white")),
        (1, ("浅", "淡", "light")),
        (2, ("黄", "米", "yellow")),
        (3, ("红", "橙", "pink", "red", "orange")),
        (4, ("绿", "蓝", "green", "blue")),
        (5, ("灰", "紫", "grey", "gray", "purple")),
        (6, ("黑", "深", "black", "dark")),
    )
    for rank, markers in keywords:
        if any(marker in normalized for marker in markers):
            return rank
    return 3

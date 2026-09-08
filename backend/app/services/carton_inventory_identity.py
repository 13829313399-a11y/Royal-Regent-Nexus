"""Stable, bounded inventory identities with explicit legacy compatibility."""
import hashlib
import json
from collections import defaultdict
from fastapi import HTTPException

FIELDS = ("customer_code", "contract_no", "item_no", "packaging_type", "paper_quality", "specification", "unit")


def inventory_key(row):
    if row.order_line_id:
        return row.order_line_id
    payload = json.dumps([getattr(row, name) for name in FIELDS], ensure_ascii=False, separators=(",", ":"))
    return "STK2:" + hashlib.sha256(payload.encode()).hexdigest()


def legacy_key(row):
    return row.order_line_id or "|".join(getattr(row, name) for name in FIELDS)


def aliases_for(rows):
    aliases = defaultdict(set)
    for row in rows:
        key = inventory_key(row)
        aliases[key].add(key)
        aliases[legacy_key(row)].add(key)
    return aliases


def resolve_key(key, aliases):
    matches = aliases.get(key, set())
    if len(matches) != 1:
        raise HTTPException(409, "旧库存身份存在歧义或缺少来源，请核对原始收发及调仓记录；旧盘点可先取消，不能按合并数量继续过账")
    return next(iter(matches))

"""One-time, reviewed equipment registration; plan imports never call this module."""

import re

from fastapi import HTTPException
from sqlalchemy import select

from app.models.injection_scheduling import CalendarEvent, Machine

from .calculations import now
from .common import begin_write, finish_write, record
from .master_data import write_master
from .requirement_parser import normalize_code
from .sparse_xlsx import read_sheet

PROFILES = {
    "huakang-a-equipment-v1": {
        "factory": "huakang-a",
        "sheet": "8月",
        "spec": "F",
        "description": "G",
        "note": "H",
        "headers": {
            "A": "机位",
            "B": "机位",
            "D": "货号",
            "E": "安机",
            "F": "工模",
            "H": "单号",
            "K": "订单数",
        },
    },
    "huakang-b-equipment-v1": {
        "factory": "huakang-b",
        "sheet": "计划表",
        "spec": "G",
        "description": "H",
        "note": "I",
        "headers": {
            "A": "机位",
            "B": "机位",
            "E": "货号",
            "F": "安机",
            "G": "工模",
            "I": "单号",
            "L": "订单数",
        },
    },
}


def inspect_register(content, profile_id):
    profile = PROFILES[profile_id]
    source = read_sheet(content, profile["sheet"])
    rows = source["rows"]

    def value(r, col):
        return rows.get(r, {}).get(col, {}).get("cached_value")

    for col, label in profile["headers"].items():
        if value(3, col) != label:
            raise ValueError(f"设备取证格式不符：{col}3 应为 {label}")
    machines, conflicts, pending, seen = [], [], [], set()
    group = None
    for r in sorted(n for n in rows if n > 3):
        marker = value(r, "A")
        spec = str(value(r, profile["spec"]) or "")
        explicit = value(r, "B")
        if marker is not None and str(marker).strip():
            code = str(marker).strip()
            if not re.fullmatch(r"[A-Za-z]*\d+", code):
                raise ValueError(f"第 {r} 行机号需人工核对：{code}")
            if normalize_code(explicit) != normalize_code(code):
                raise ValueError(f"第 {r} 行设备分组的 A/B 机位不一致")
            if rows[r]["A"].get("formula_expanded"):
                raise ValueError(f"第 {r} 行机号必须是固定文本")
            if normalize_code(code) in seen:
                raise ValueError(f"设备分组重复：{code}")
            seen.add(normalize_code(code))
            group = code
            a = re.search(r"(\d+(?:\.\d+)?)\s*A", normalize_code(spec))
            ton = re.search(r"(\d+(?:\.\d+)?)\s*T", normalize_code(spec))
            if not a:
                raise ValueError(f"第 {r} 行缺少明确机台 A，不能从订单推测")
            description = str(value(r, profile["description"]) or "")
            extra = str(value(r, profile["note"]) or "")
            raw_status = str(value(r, "C") or "")
            text = normalize_code(description + " " + extra)
            arm = re.search(
                r"(?:双臂\s*[35五三]?\s*轴?|单臂\s*[35五三]?\s*轴?|五轴双臂|普通双臂|普通机械手|机器人)",
                text,
            )
            forbidden = re.search(
                r"(?:不能|禁止|不可)(?:啤|排)\s*([A-Z]+(?:/[A-Z]+)*)", text
            )
            restrictions = (
                {"forbidden_resins": forbidden.group(1).split("/")} if forbidden else {}
            )
            # Only explicit exclusive material statements become constraints.
            only = re.search(r"只能啤\s*([A-Z]+)", text)
            if only:
                restrictions["only_resin"] = only.group(1)
            status = (
                "FAULT"
                if raw_status == "机故"
                else "DISABLED"
                if raw_status == "暂停"
                else "IDLE"
            )
            notes = f"原表设备：{spec}；{description}"
            if extra:
                notes += f"；原表备注：{extra}"
            if raw_status:
                notes += f"；原表状态：{raw_status}"
            notes += "；来源计划表设备分组，当前状态请现场核对"
            machines.append(
                {
                    "source_row": r,
                    "data": {
                        "code": code,
                        "workshop": "",
                        "machine_a": float(a.group(1)),
                        "clamp_ton": float(ton.group(1)) if ton else None,
                        "machine_family": "VERTICAL"
                        if "立式" in text
                        else "TWO_COLOR"
                        if "双色" in text
                        else "HORIZONTAL",
                        "speed_class": "HIGH_SPEED"
                        if "高速" in text
                        else "ELECTRIC"
                        if "全电" in text
                        else "NORMAL",
                        "manipulator": arm.group(0).replace(" ", "") if arm else "",
                        "capabilities": {},
                        "restrictions": restrictions,
                        "notes": notes,
                    },
                    "operating_status": status,
                    "evidence": {
                        "profile": profile_id,
                        "sha256": source["sha256"],
                        "sheet": profile["sheet"],
                        "row": r,
                        "cells": {
                            c: rows[r][c]
                            for c in (
                                "A",
                                "B",
                                "C",
                                profile["spec"],
                                profile["description"],
                                profile["note"],
                            )
                            if c in rows[r]
                        },
                        "defaults_not_source_verified": [
                            k
                            for k, known in (
                                (
                                    "machine_family",
                                    any(v in text for v in ("立式", "双色", "卧式")),
                                ),
                                (
                                    "speed_class",
                                    any(v in text for v in ("高速", "全电", "普通")),
                                ),
                            )
                            if not known
                        ],
                    },
                }
            )
        elif spec:
            if explicit is None or str(explicit).strip() == "":
                pending.append(r)
            elif normalize_code(explicit) != normalize_code(group):
                conflicts.append(
                    {
                        "source_row": r,
                        "group_machine": group,
                        "row_machine": str(explicit),
                        "mold_code": spec,
                    }
                )
    if not machines:
        raise ValueError("没有可注册的设备分组")
    return {
        "factory_id": profile["factory"],
        "profile": profile_id,
        "sha256": source["sha256"],
        "sheet": profile["sheet"],
        "machines": machines,
        "assignment_conflicts": conflicts,
        "unassigned_source_rows": pending,
    }


def apply_register(db, report, payload, actor):
    """Add reviewed machine records atomically; never overwrite existing equipment."""
    factory = report["factory_id"]
    if (
        payload["factory_id"] != factory
        or payload.get("source_sha256") != report["sha256"]
    ):
        raise HTTPException(422, "设备取证来源或厂区发生变化")
    prior, context = begin_write(db, payload, actor, "machine.register.source")
    if prior is not None:
        return prior
    existing = {
        normalize_code(m.code): m
        for m in db.scalars(select(Machine).where(Machine.factory_id == factory))
    }
    created, skipped = [], []
    for item in report["machines"]:
        other = existing.get(normalize_code(item["data"]["code"]))
        if other:
            previous = other.raw_header_cells or {}
            if (
                previous.get("sha256") != report["sha256"]
                or previous.get("row") != item["source_row"]
            ):
                raise HTTPException(
                    409, f"本厂已有 {other.code}，请在基础资料核对；不会覆盖"
                )
            skipped.append(other.code)
            continue
        machine = write_master(db, "machines", factory, item["data"], actor)
        machine.raw_header_cells = item["evidence"]
        machine.operating_status = item["operating_status"]
        if machine.operating_status != "IDLE":
            db.add(
                CalendarEvent(
                    factory_id=factory,
                    resource_type="MACHINE",
                    resource_id=machine.id,
                    start_at=now(),
                    kind="STATUS_STOP",
                    notes=machine.notes,
                )
            )
        created.append(record(machine))
    db.flush()
    return finish_write(
        db,
        context,
        {
            "created_count": len(created),
            "skipped_codes": skipped,
            "created": created,
            "source_sha256": report["sha256"],
            "assignment_conflicts": report["assignment_conflicts"],
        },
    )

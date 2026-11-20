"""Huaxing-shaped four-factory workbook, with no user-maintained technical IDs."""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from .calculations import decimal
from .field_registry import FACTORIES, FIELDS, column_name
from .requirement_parser import machine_requirement, normalize_code
from .unified_plan import CONTRACT, read_unified, text
from .unified_plan import VERSION as FLAT_VERSION

VERSION = "RR_INJECTION_HUAXING_V2"
TEMPLATE_PATH = Path(__file__).with_name("templates") / "injection-plan-huaxing-v2.xlsx"
HEADERS = [
    None,
    "机号",
    None,
    "是否全自动",
    "备注",
    "机型",
    "工模",
    "名称",
    "单号",
    "货号",
    "数量(套)",
    "订单数",
    "已啤数",
    "欠数",
    "计划目标",
    "水口比例",
    "颜色",
    "色粉",
    "用料",
    "净重",
    "毛重",
    "用料重（KG）",
    "单价/啤",
    "外发单价",
    "比例",
    "下单期",
    "开始\n交货期",
    "交货\n完成期",
    "转模\n参考时间",
    "转色参考时间",
    "转模/色\n时间",
    "机/模故\n时间",
    "计划生产期",
    "计划完成期",
    "计划完成月",
    "入库期",
    "交期差",
    "是否喷油",
    "啤货天数",
    "每班结束时间",
    "时间",
    "每班计划啤数",
    "机型",
    "仓库",
    "备注",
    "走货期",
    "单双臂",
    "夹具",
    "白班",
    "夜班",
]
FIRST_MACHINE_ROW = 4
BLOCK_SIZE = 6
MACHINE_SLOTS = 3  # Authored prototype; download expands bands to the factory's fleet.
PENDING_ROW = FIRST_MACHINE_ROW + BLOCK_SIZE * MACHINE_SLOTS
LAST_ROW = PENDING_ROW + 30
# Hidden dictionary occupies DZ:EL. It is a download-time snapshot, never master input.
LOOKUP_FIRST_COLUMN = 130
LOOKUP_LIMIT = 10000


def read_huaxing_template(source):
    rows = source["rows"]

    def cell(row, col):
        return rows.get(row, {}).get(col, {})

    def val(row, col):
        return cell(row, col).get("cached_value")

    marker = text(val(1, "AY"))
    if not marker.startswith("RR_INJECTION_HUAXING"):
        if text(val(2, "E")) == "厂区" and text(val(2, "AY")) == "统一厂区计划":
            raise ValueError("华兴格式统一模板标识已修改，请重新下载模板")
        return None
    if marker != VERSION or cell(1, "AY").get("formula_expanded"):
        raise ValueError("华兴格式统一模板版本不支持，请重新下载模板")
    bound_factory = text(val(1, "EN"))
    factory_names = {normalize_code(k).replace(" ", ""): k for k in FACTORIES}
    factory_names.update(
        {normalize_code(v).replace(" ", ""): k for k, v in FACTORIES.items()}
    )
    if bound_factory and factory_names.get(
        normalize_code(bound_factory).replace(" ", "")
    ) != factory_names.get(normalize_code(val(2, "F")).replace(" ", "")):
        raise ValueError("F2 厂区与下载模板所属厂区不一致，请在目标厂区重新下载模板")
    for n, expected in enumerate(HEADERS, 1):
        if expected and text(val(3, column_name(n))).replace(
            "\n", ""
        ) != expected.replace("\n", ""):
            raise ValueError(
                f"原样模板第 3 行表头不符：{column_name(n)} 列应为“{expected}”"
            )

    # Reuse the validated quantity/date contract and the existing atomic import path.
    converted = {
        2: {"A": {"cached_value": FLAT_VERSION}},
        3: {"B": cell(2, "F"), "E": cell(2, "I")},
    }
    converted[6] = {
        column_name(i): {"cached_value": label}
        for i, (_, label, _) in enumerate(CONTRACT["columns"], 1)
    }
    originals, errors, positions, identities = [], {}, Counter(), set()
    context = None
    in_pending = False
    machine_groups = set()
    for r in sorted(n for n in rows if n >= 4):
        mold = text(val(r, "G"))
        marker = text(val(r, "A"))
        if mold in {"待排区", "待排订单", "未排订单", "需求池"} or marker == "待排区":
            context, in_pending = None, True
            continue
        # A is the original visible machine-band marker; B remains a hidden helper.
        specification = bool(
            re.fullmatch(
                r"\d+(?:\.\d+)?\s*A(?:\s*\d+(?:\.\d+)?\s*T)?", mold, re.IGNORECASE
            )
        )
        if (
            cell(r, "B").get("formula_expanded") == f"A{r}"
            or marker
            and (specification or mold in {"", "机台规格", "立式", "立式机", "双色机"})
        ):
            # An emptied machine band still ends the previous queue.
            context = None if marker in {"", "填写机号"} else marker
            in_pending = False
            if context:
                normalized = normalize_code(context)
                if normalized in machine_groups:
                    raise ValueError(
                        f"第 {r} 行机台分组重复：{context}。请把同一机台的任务放在同一组内"
                    )
                machine_groups.add(normalized)
            continue
        if not mold:
            if val(r, "I") or val(r, "J") or val(r, "L") not in (None, ""):
                raise ValueError(f"第 {r} 行有订单数据但未填写工模")
            continue
        if mold in {"工模", "模号"}:
            continue
        n = len(originals) + 7
        mapped, issues = {}, []
        explicit = text(val(r, "B"))
        if cell(r, "B").get("formula_expanded"):
            explicit = (
                ""  # The group marker is authoritative, not a stale helper cache.
            )
        machine = explicit or context or ""
        if in_pending and explicit:
            issues.append("待排区存在机号，请移到该机台分组或清空机号")
        if context and explicit and normalize_code(context) != normalize_code(explicit):
            issues.append(
                f"第 {r} 行机号“{explicit}”与上方机台分组“{context}”不一致；请把整行移到正确机台组，再复制同组机号公式"
            )
        if not in_pending and not machine:
            issues.append("机台分组尚未填写机号；未排机任务请放到待排区")
        identity_values = [
            normalize_code(val(r, c)) for c in ("G", "I", "J", "Q", "R", "S")
        ]
        identity = (
            "HX2-"
            + hashlib.sha256(
                json.dumps(identity_values, ensure_ascii=False).encode()
            ).hexdigest()[:40]
        )
        if identity in identities:
            issues.append(
                "相同工模、单号、货号、颜色、色粉和用料出现多行，请合并为一条需求；拆批在系统内处理"
            )
        identities.add(identity)
        positions[normalize_code(machine)] += 1
        values = {
            "source_line_id": identity,
            "machine_code": machine,
            "queue_order": positions[normalize_code(machine)] if machine else None,
        }
        for i, (key, _, kind) in enumerate(CONTRACT["columns"], 1):
            if key in values:
                evidence = {"cached_value": values[key]}
            else:
                col = FIELDS[key].legacy_column if key in FIELDS else None
                evidence = dict(cell(r, col)) if col else {}
            if key == "required_machine_a":
                raw = evidence.get("cached_value")
                number = decimal(raw)
                evidence["cached_value"] = (
                    float(number)
                    if number is not None
                    else machine_requirement(raw)["required_machine_a"]
                )
                if raw not in (None, "") and evidence["cached_value"] is None:
                    issues.append("机型列未包含有效机安 A，请核对公共模具参数")
            # Blank auto-lookup results are intentionally supplied by the live master.
            if (
                key
                in {
                    "required_machine_a",
                    "part_name",
                    "target_shots_per_day",
                    "net_weight_g",
                    "gross_weight_g",
                    "price_per_shot",
                    "manipulator_requirement",
                    "fixture_requirement",
                    "automation_requirement",
                }
                and evidence.get("cached_value") in (None, "")
                and evidence.get("type") != "e"
            ):
                evidence = {"cached_value": None}
            mapped[column_name(i)] = evidence
        for col, evidence in rows[r].items():
            # Only actual numeric shift inputs are relevant; hidden dictionaries are not.
            from .sparse_xlsx import column_number

            index = column_number(col)
            if 49 <= index <= 50 or 53 <= index < LOOKUP_FIRST_COLUMN:
                raw = evidence.get("cached_value")
                qty = decimal(raw)
                if (
                    evidence.get("type") == "e"
                    or raw not in (None, "")
                    and (qty is None or qty < 0)
                ):
                    issues.append(f"{col} 列班次产量必须为非负数字")
        converted[n] = mapped
        originals.append(r)
        errors[r] = issues
    try:
        parsed = read_unified({**source, "rows": converted})
    except ValueError as exc:
        message = (
            str(exc)
            .replace("B3", "F2")
            .replace("E3", "I2")
            .replace("第 7 行", "机台分组下的空白任务行")
        )
        raise ValueError(message) from exc
    for row, original in zip(parsed["demands"], originals, strict=True):
        row["source_row"] = original
        from .sparse_xlsx import column_number

        row["source_cells"] = {
            c: v
            for c, v in rows[original].items()
            if column_number(c) < LOOKUP_FIRST_COLUMN
        }
        row["issues"].extend(
            {"code": "HUAXING_TEMPLATE_ROW", "message": message}
            for message in errors[original]
        )
    parsed["unified"]["version"] = VERSION
    parsed["unified"]["layout"] = "huaxing"
    return parsed

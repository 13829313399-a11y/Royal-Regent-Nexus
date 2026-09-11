"""Atomic template imports with stable source IDs and explicit machine bindings."""

from fastapi import HTTPException
from sqlalchemy import select

from app.models.injection_scheduling import (
    Demand,
    ImportRow,
    Machine,
    MoldAsset,
    MoldMaster,
    Run,
    RunDemand,
)

from .calculations import timestamp
from .common import jsonable, record, touch
from .enrichment import enrich, update_quantities
from .field_registry import FIELDS
from .requirement_parser import normalize_code
from .scheduler import REASONS, fit, ready_reason
from .unified_plan import CONTRACT, process_fields

INPUT_KEYS = [key for key, _, kind in CONTRACT["columns"] if kind != "calculated"]
DEMAND_KEYS = [key for key in INPUT_KEYS if key in FIELDS and FIELDS[key].editable] + [
    "dispatch_state",
    "resin",
    "material_grade",
]


def source_fields(row):
    return {key: row["fields"].get(key) for key in INPUT_KEYS}


def current_state(db, demand):
    values = record(demand)
    runs = list(
        db.scalars(select(Run).join(RunDemand).where(RunDemand.demand_id == demand.id))
    )
    return {
        "fields": {
            key: values.get(key)
            for key in [
                *DEMAND_KEYS,
                "opening_shots",
                "adjustment_shots",
                "target_basis_hours",
                "allowance_rate",
                "allocation_mode",
                "requirements_snapshot",
            ]
        },
        "runs": sorted(
            [
                {
                    "id": run.id,
                    "machine_id": run.machine_id,
                    "sequence": run.sequence,
                    "status": run.status,
                    "pinned": run.pinned,
                    "physical_shots": float(run.physical_shots),
                    "actual_start_at": jsonable(run.actual_start_at),
                }
                for run in runs
                if run.status != "CANCELLED"
            ],
            key=lambda run: run["id"],
        ),
    }


def inspect_rows(db, factory, parsed):
    """Read-only binding, also repeated inside the serialized apply transaction."""
    from app.models.injection_scheduling import FactorySettings

    from .import_service import candidate_index, identity_key

    machines = {}
    for machine in db.scalars(select(Machine).where(Machine.factory_id == factory)):
        machines.setdefault(normalize_code(machine.code), []).append(machine)
    masters = {}
    for master in db.scalars(select(MoldMaster)):
        for code in {
            master.normalized_code,
            *(normalize_code(alias) for alias in master.alias_codes),
        }:
            masters.setdefault(code, []).append(master)
    assets = {}
    for asset in db.scalars(
        select(MoldAsset).where(
            MoldAsset.current_factory_id == factory, MoldAsset.status == "AVAILABLE"
        )
    ):
        assets.setdefault(asset.master_id, []).append(asset)
    known = {}
    for demand in db.scalars(
        select(Demand).where(
            Demand.factory_id == factory, Demand.source_system == "UNIFIED_PLAN"
        )
    ):
        known.setdefault(demand.source_line_id, []).append(demand)
    existing = candidate_index(db, factory)
    settings = db.get(FactorySettings, factory).parameters
    results, used_positions = [], set()
    for row in parsed["demands"]:
        fields = row["fields"]
        issues = list(row["issues"])

        def problem(message, code="UNIFIED_BINDING", issues=issues, row=row):
            issues.append(
                {"code": code, "message": message, "source_row": row["source_row"]}
            )

        matches = known.get(fields["source_line_id"], [])
        demand = matches[0] if len(matches) == 1 else None
        if len(matches) > 1:
            problem("此需求编号在本厂匹配到多条记录，请核对", "UNIFIED_ID_CONFLICT")
        if not matches and any(
            d.source_system != "UNIFIED_PLAN"
            for d in existing.get(identity_key(fields), [])
        ):
            problem(
                "本厂已有相同业务需求；请使用系统导出的标准交换表更新，避免重复导入",
                "UNIFIED_EXISTING_DEMAND",
            )
        baseline = (demand.extras or {}).get("unified_baseline", {}) if demand else {}
        unchanged = bool(
            demand
            and baseline.get("source") == source_fields(row)
            and baseline.get("as_of") == parsed["unified"]["as_of"]
        )
        master_matches = masters.get(normalize_code(fields["mold_code"]), [])
        master = master_matches[0] if len(master_matches) == 1 else None
        machine, asset = None, None
        if fields.get("machine_code") and not unchanged:
            choices = machines.get(normalize_code(fields["machine_code"]), [])
            if len(choices) != 1:
                problem(
                    "机号在本厂设备库不存在或有歧义，请先维护本厂设备；不会自动新建设备",
                    "UNIFIED_MACHINE_NOT_FOUND",
                )
            else:
                machine = choices[0]
            if master is None:
                problem(
                    "公共模具库未找到唯一模号，请先维护公共模具资料",
                    "UNIFIED_MOLD_NOT_FOUND",
                )
            elif not assets.get(master.id):
                problem(
                    "本厂没有该模号的可用实物模具，请核对实物位置和状态",
                    "UNIFIED_ASSET_NOT_FOUND",
                )
            else:
                # Multiple physical copies are deliberately resolved by the operator.
                if len(assets[master.id]) > 1:
                    problem(
                        "同模号有多副可用实物模具，请先导入为未排机，再在系统选择实物排产",
                        "UNIFIED_AMBIGUOUS_ASSET",
                    )
                else:
                    asset = assets[master.id][0]
            if machine and master:
                effective = {
                    "factory_id": factory,
                    "dispatch_state": "READY",
                    "allocation_mode": "SEQUENTIAL_SHOTS",
                    "target_basis_hours": 24,
                    **master.defaults,
                    "required_machine_a": master.required_machine_a,
                    **{k: v for k, v in fields.items() if v is not None and v != ""},
                    "requirements_snapshot": master.requirements,
                }
                effective.update(process_fields(effective))
                reason = ready_reason(effective) or fit(
                    effective, record(machine), settings, manual_oversize=True
                )
                if reason and fields.get("remaining_shots") != 0:
                    problem(REASONS.get(reason, reason), reason)
        if fields.get("machine_code"):
            position = (
                normalize_code(fields["machine_code"]),
                fields.get("queue_order"),
            )
            if position in used_positions:
                problem(
                    "同一机号的机内顺序重复（包含大小写或全角写法）",
                    "UNIFIED_DUPLICATE_POSITION",
                )
            used_positions.add(position)
        results.append(
            {
                "row": row,
                "demand": demand,
                "unchanged": unchanged,
                "machine": machine,
                "asset": asset,
                "issues": issues,
            }
        )
    return results


def preview_summary(db, factory, parsed):
    inspected = inspect_rows(db, factory, parsed)
    for item in inspected:
        item["row"]["preview_issues"] = item["issues"]
    return {
        **parsed["statistics"],
        "template_version": parsed["unified"]["version"],
        "creates": sum(item["demand"] is None for item in inspected),
        "updates": sum(
            item["demand"] is not None and not item["unchanged"] for item in inspected
        ),
        "unchanged_count": sum(item["unchanged"] for item in inspected),
        "conflicts": [
            {"source_row": item["row"]["source_row"], **issue}
            for item in inspected
            for issue in item["issues"]
        ],
        "assignment_policy": "按本厂机号及机内顺序记录待开工计划；未列入表格的现有队列保留在前。时间结合班历与换模换色计算。",
    }


def apply_unified(db, batch, actor, skip_rows):
    from .planning import import_original_assignments

    parsed = batch.evidence
    selected = {row["source_row"] for row in parsed["demands"]} - set(skip_rows)
    inspected = [
        item
        for item in inspect_rows(db, batch.factory_id, parsed)
        if item["row"]["source_row"] in selected
    ]
    problems = [
        f"第 {item['row']['source_row']} 行：{issue['message']}"
        for item in inspected
        for issue in item["issues"]
    ]
    if problems:
        raise HTTPException(422, "；".join(problems[:30]))
    changed = [item for item in inspected if not item["unchanged"]]
    if changed:
        # Any source update must preserve independent changes and production history.
        for item in inspected:
            demand = item["demand"]
            if demand is None:
                continue
            state = current_state(db, demand)
            baseline = demand.extras.get("unified_baseline", {})
            if state != baseline.get("server") or any(
                run["status"] != "PLANNED" for run in state["runs"]
            ):
                raise HTTPException(
                    409,
                    f"第 {item['row']['source_row']} 行已在系统调整或有生产记录；请用系统导出的标准交换表更新，原记录未覆盖",
                )
        # Rebind unchanged members as well when an imported queue is being replaced.
        for item in inspected:
            if item["unchanged"]:
                row = item["row"]
                if row["fields"].get("remaining_shots") == 0:
                    continue  # Finished source rows retain evidence, without queue occupancy.
                machine = db.scalar(
                    select(Machine).where(
                        Machine.factory_id == batch.factory_id,
                        Machine.code == item["demand"].machine_code,
                    )
                )
                run_id = item["demand"].extras.get("active_run_id")
                run = db.get(Run, run_id) if run_id else None
                if row["fields"].get("machine_code") and (not machine or not run):
                    raise HTTPException(
                        409, f"第 {row['source_row']} 行原排程已变化，请重新核对"
                    )
                item["machine"] = machine
                item["asset"] = db.get(MoldAsset, run.mold_asset_id) if run else None
        original, replacements = [], []
        for item in inspected:
            row, demand = item["row"], item["demand"]
            fields = row["fields"]
            if demand is None:
                demand = Demand(
                    factory_id=batch.factory_id,
                    mold_code=fields["mold_code"],
                    source_system="UNIFIED_PLAN",
                    source_line_id=fields["source_line_id"],
                    stable_sequence=row["source_row"],
                    extras={},
                    field_sources={},
                )
                db.add(demand)
                item["demand"] = demand
            if not item["unchanged"]:
                for key in DEMAND_KEYS:
                    value = fields.get(key)
                    if FIELDS[key].value_type == "datetime":
                        value = timestamp(value)
                    setattr(demand, key, value if value != "" else None)
                demand.opening_shots = fields["completed_shots"]
                demand.target_basis_hours = 24
                demand.allowance_rate = 0.01
                demand.requirements_snapshot = {}
                demand.field_sources = {
                    key: {
                        "kind": "UNIFIED_PLAN",
                        "batch_id": batch.id,
                        "source_row": row["source_row"],
                    }
                    for key in DEMAND_KEYS
                    if fields.get(key) not in (None, "")
                }
                demand.source_document = batch.file_name
                demand.source_row = row["source_row"]
                demand.import_batch_id = batch.id
                enrich(db, demand)
                for key, value in process_fields(record(demand)).items():
                    setattr(demand, key, value)
                db.flush()
                update_quantities(demand)
                demand.extras = {
                    **demand.extras,
                    **{
                        key: fields.get(key)
                        for key in (
                            "automation_requirement",
                            "fixture_requirement",
                            "manipulator_requirement",
                        )
                    },
                }
                touch(demand, actor)
            db.flush()
            replacements.append(demand.id)
            if item["machine"]:
                original.append(
                    {
                        "demand_id": demand.id,
                        "machine_id": item["machine"].id,
                        "mold_asset_id": item["asset"].id,
                        "source_row": row["source_row"],
                        "queue_order": fields["queue_order"],
                        "legacy_start": parsed["unified"]["as_of"],
                    }
                )
        result = import_original_assignments(
            db,
            batch.factory_id,
            sorted(original, key=lambda a: (a["machine_id"], a["queue_order"])),
            actor,
            replace_demand_ids=replacements,
            strict=True,
            as_of=parsed["unified"]["as_of"],
        )
        for item in inspected:
            demand = item["demand"]
            demand.extras = {
                **demand.extras,
                "unified_baseline": {
                    "source": source_fields(item["row"]),
                    "as_of": parsed["unified"]["as_of"],
                    "server": current_state(db, demand),
                },
            }
    else:
        result = {"changed_runs": [], "unplaced": []}
    for item in inspected:
        db.add(
            ImportRow(
                batch_id=batch.id,
                source_row=item["row"]["source_row"],
                row_role="demand",
                demand_id=item["demand"].id,
                evidence=item["row"],
                issues=[],
            )
        )
    batch.status = "APPLIED"
    batch.summary = {
        **batch.summary,
        "applied_count": len(changed),
        "unchanged_count": len(inspected) - len(changed),
        "skipped_rows": sorted(skip_rows),
        "conflicts": [],
    }
    touch(batch, actor)
    db.flush()
    return {
        "batch_id": batch.id,
        "summary": batch.summary,
        "recalculate_required": False,
        "unified_import": True,
        "restored_assignment_count": sum(
            bool(item["demand"].machine_code)
            and item["row"]["fields"].get("remaining_shots", 0) > 0
            for item in inspected
        )
        if changed
        else 0,
        **result,
    }

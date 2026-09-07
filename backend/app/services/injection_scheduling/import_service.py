from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select

from app.models.injection_scheduling import (
    Demand,
    HistoricalOutput,
    ImportBatch,
    ImportRow,
    Machine,
    MoldAsset,
    MoldMaster,
    Run,
    RunDemand,
)

from .calculations import decimal, now, timestamp
from .common import jsonable, record, touch
from .enrichment import apply_demand_fields, enrich, match_mold, update_quantities
from .field_registry import FIELDS
from .import_plan import PARSER_VERSION, parse_plan
from .requirement_parser import normalize_code

MATCH_KEYS = (
    "order_no",
    "item_no",
    "mold_code",
    "color_name",
    "colorant_code",
    "material_raw",
    "delivery_due_at",
)


def identity_key(data):
    return tuple(
        timestamp(data[k]).isoformat()
        if k == "delivery_due_at" and data.get(k)
        else str(data.get(k) or "").strip()
        for k in MATCH_KEYS
    )


def legacy_baseline(db, demand):
    saved = (demand.extras or {}).get("legacy_import_baseline")
    if saved:
        return saved
    evidence = db.scalar(
        select(ImportRow).where(
            ImportRow.demand_id == demand.id,
            ImportRow.batch_id == demand.import_batch_id,
        )
    )
    if not evidence:
        return None
    row = evidence.evidence
    if "raw_fields" not in row:
        return None
    return {
        "source_fields": row["fields"],
        "server_fields": row["fields"],
        "history": {
            f"{h['date']}|{h['shift_code']}": h["raw_quantity"]
            for h in row.get("history", [])
        },
        "opening_shots": float(demand.opening_shots),
        "source_row": demand.source_row,
    }


def candidate_index(db, factory):
    result = {}
    for demand in db.scalars(select(Demand).where(Demand.factory_id == factory)):
        baseline = legacy_baseline(db, demand)
        keys = {identity_key(record(demand))}
        if baseline:
            keys.add(identity_key(baseline["source_fields"]))
        for key in keys:
            result.setdefault(key, []).append(demand)
    return result


def row_candidates(index, row):
    candidates = index.get(identity_key(row["fields"]), [])
    # Identical business identities may still be two legitimate source-line splits.
    same_line = [
        d
        for d in candidates
        if d.source_system == "LEGACY_PLAN" and d.source_row == row["source_row"]
    ]
    return same_line if len(same_line) == 1 else candidates


def update_legacy_row(db, batch, row, demand, evidence, actor):
    """Advance accepted source facts without replacing independent server work."""
    from app.models.injection_scheduling import FactorySettings

    from .exchange import same_value
    from .reports import shift_window

    baseline = legacy_baseline(db, demand)
    conflicts = []
    changed = False

    def conflict(code, field=None, **detail):
        item = {
            "source_row": row["source_row"],
            "demand_id": demand.id,
            "code": code,
            **detail,
        }
        if field:
            item["field"] = field
        conflicts.append(item)

    if not baseline:
        conflict(
            "MISSING_LEGACY_BASELINE",
            message="此需求没有可核对的旧表基线，请使用系统交换表更新。",
        )
        return False, conflicts
    source = dict(baseline["source_fields"])
    saved = dict(baseline["server_fields"])
    history_baseline = dict(baseline["history"])
    current = record(demand)
    executions = list(
        db.scalars(
            select(Run)
            .join(RunDemand, RunDemand.run_id == Run.id)
            .where(RunDemand.demand_id == demand.id, Run.actual_start_at.is_not(None))
        )
    )
    active = any(run.status in {"RUNNING", "PAUSED"} for run in executions)
    errors = {
        i.get("field")
        for i in row["issues"]
        if i.get("code")
        in {"SOURCE_CELL_ERROR", "FORMULA_CACHE_MISSING", "INVALID_LEGACY_DATE"}
    }
    for key, incoming in row["fields"].items():
        if key not in FIELDS or not FIELDS[key].editable or key not in source:
            continue
        if same_value(key, incoming, source[key]):
            continue
        if key in errors:
            conflict("SOURCE_VALUE_UNAVAILABLE", key)
            continue
        if same_value(key, incoming, current.get(key)):
            source[key] = incoming
            saved[key] = current.get(key)
            continue
        if not same_value(key, current.get(key), saved.get(key)):
            conflict(
                "FIELD_CONFLICT",
                key,
                baseline=saved.get(key),
                server=current.get(key),
                incoming=incoming,
            )
            continue
        if active and key not in {
            "planned_shots",
            "adjustment_shots",
            "required_units",
            "order_note",
            "production_note",
            "warehouse_note",
            "delivery_due_at",
            "priority_level",
        }:
            conflict("RUNNING_SNAPSHOT", key)
            continue
        try:
            with db.begin_nested():
                apply_demand_fields(db, demand, {key: incoming}, actor)
            source[key] = incoming
            saved[key] = record(demand).get(key)
            changed = True
        except HTTPException as exc:
            conflict("INVALID_FIELD", key, message=str(exc.detail))
    histories = {
        f"{h.production_date.isoformat()}|{h.shift_code}": h
        for h in db.scalars(
            select(HistoricalOutput).where(
                HistoricalOutput.demand_id == demand.id,
                HistoricalOutput.source_key == "legacy",
            )
        )
    }
    parameters = db.get(FactorySettings, batch.factory_id).parameters
    full = (
        row["fields"].get("planned_shots") is not None
        and row["fields"].get("completed_shots") is not None
    )
    full = full and decimal(row["fields"]["completed_shots"]) >= decimal(
        row["numeric_shift_sum"]
    )
    for item in row["history"]:
        key = f"{item['date']}|{item['shift_code']}"
        incoming = decimal(item["raw_quantity"])
        existing = histories.get(key)
        old = history_baseline.get(key)
        if same_value(key, incoming, old):
            continue
        if incoming < 0:
            conflict("INVALID_HISTORY_QUANTITY", key)
            continue
        if not full and existing and existing.counts_toward_demand:
            conflict(
                "HISTORY_QUANTITY_UNRECONCILED",
                key,
                message="文件累计缺失或小于班次数量，不能替换已计入累计的历史。",
            )
            continue
        if existing and same_value(key, incoming, existing.quantity):
            history_baseline[key] = float(incoming)
            continue
        if existing and not same_value(key, existing.quantity, old):
            conflict(
                "HISTORY_CONFLICT",
                key,
                baseline=old,
                server=float(existing.quantity),
                incoming=float(incoming),
            )
            continue
        start, end = shift_window(item["date"], item["shift_code"], parameters)
        if any(
            timestamp(run.actual_start_at) < end
            and (not run.actual_end_at or timestamp(run.actual_end_at) > start)
            for run in executions
        ):
            conflict(
                "HISTORY_OVERLAPS_EXECUTION",
                key,
                message="该班次已有实际批次；保留服务器报工，请按物理批次在班次报工面更正。",
            )
            continue
        if existing is None:
            existing = HistoricalOutput(
                demand_id=demand.id,
                import_row_id=evidence.id,
                production_date=date.fromisoformat(item["date"]),
                shift_code=item["shift_code"],
                source_key="legacy",
                quantity=incoming,
                counts_toward_demand=full,
                allocation_mode="LEGACY_UNRESOLVED",
            )
            db.add(existing)
            histories[key] = existing
        else:
            existing.quantity = incoming
            existing.import_row_id = evidence.id
        history_baseline[key] = float(incoming)
        changed = True
    # Cumulative M is a reconciliation snapshot, never a replacement for reports.
    # When no physical execution exists, retain histories outside a later file's
    # window and calculate only the truly unrepresented opening amount.
    old_m = source.get("completed_shots")
    incoming_m = row["fields"].get("completed_shots")
    if (
        full
        and not executions
        and not any(
            c["code"] in {"HISTORY_CONFLICT", "INVALID_HISTORY_QUANTITY"}
            for c in conflicts
        )
    ):
        proposed = decimal(incoming_m) - sum(
            (h.quantity for h in histories.values()), decimal(0)
        )
        if proposed < 0:
            conflict(
                "CUMULATIVE_BELOW_RETAINED_HISTORY",
                "completed_shots",
                incoming=incoming_m,
            )
        elif decimal(demand.opening_shots) != decimal(baseline["opening_shots"]):
            if not same_value("completed_shots", incoming_m, old_m):
                conflict("OPENING_CONFLICT", "completed_shots")
        else:
            if demand.opening_shots != proposed:
                demand.opening_shots = proposed
                changed = True
            for historical in histories.values():
                if not historical.counts_toward_demand:
                    historical.counts_toward_demand = True
                    changed = True
            baseline = {**baseline, "opening_shots": float(proposed)}
            source["completed_shots"] = incoming_m
    elif executions and not same_value("completed_shots", incoming_m, old_m):
        conflict(
            "CUMULATIVE_SNAPSHOT_PRESERVED",
            "completed_shots",
            message="累计由已接受历史及服务器报工计算；文件累计不覆盖物理生产事实。",
        )
    if histories and not executions:
        demand.opening_cutoff_at = max(
            shift_window(h.production_date, h.shift_code, parameters)[1]
            for h in histories.values()
        )
    demand.extras = {
        **(demand.extras or {}),
        "legacy_import_baseline": {
            **baseline,
            "source_fields": source,
            "server_fields": saved,
            "history": history_baseline,
            "source_row": row["source_row"],
        },
    }
    if changed:
        touch(demand, actor)
    return changed, conflicts


def preview(db, factory, content, file_name, sheet, actor, mapping=None):
    parsed = parse_plan(content, sheet, mapping)
    if parsed.get("exchange") and parsed["exchange"].get("factory_id") != factory:
        raise HTTPException(422, "交换表厂区与当前厂区不一致")
    existing = db.scalar(
        select(ImportBatch).where(
            ImportBatch.factory_id == factory,
            ImportBatch.file_sha256 == parsed["sha256"],
            ImportBatch.sheet_name == sheet,
            ImportBatch.parser_version == PARSER_VERSION,
        )
    )
    if existing:
        return existing
    old = {} if parsed.get("exchange") else candidate_index(db, factory)
    conflicts, updates, creates = [], 0, 0
    for row in parsed["demands"]:
        if parsed.get("exchange"):
            stable = db.get(Demand, row["fields"].get("id"))
            matches = [stable] if stable and stable.factory_id == factory else []
            if not matches:
                row["match_candidates"] = []
                conflicts.append(
                    {"source_row": row["source_row"], "code": "UNKNOWN_SCOPED_DEMAND"}
                )
                continue
        else:
            matches = row_candidates(old, row)
        row["match_candidates"] = [
            {"id": d.id, "source_row": d.source_row, "revision": d.revision}
            for d in matches
        ]
        if len(matches) > 1:
            conflicts.append(
                {
                    "source_row": row["source_row"],
                    "code": "AMBIGUOUS_DEMAND",
                    "candidates": row["match_candidates"],
                }
            )
        elif matches:
            updates += 1
        else:
            creates += 1
    summary = {
        **parsed["statistics"],
        "creates": creates,
        "updates": updates,
        "conflicts": conflicts,
        "asset_assumption": "首次出现的唯一模号推定单副在本厂；已有异厂资产不自动复制。",
        "history_quantity_basis": "历史单元格原数合计，未经同啤关系去重，不等同机台物理啤数",
    }
    batch = ImportBatch(
        factory_id=factory,
        file_name=file_name,
        file_sha256=parsed["sha256"],
        sheet_name=sheet,
        parser_version=PARSER_VERSION,
        summary=jsonable(summary),
        evidence=jsonable(parsed),
        status="PREVIEW",
    )
    touch(batch, actor)
    db.add(batch)
    db.flush()
    return batch


def apply_batch(db, batch, actor, choices=None, skip_rows=()):
    if batch.status == "APPLIED":
        return {
            "batch_id": batch.id,
            "summary": batch.summary,
            "already_applied": True,
            "recalculate_required": False,
            "changed_runs": [],
        }
    if batch.evidence.get("exchange"):
        from .exchange import apply_exchange

        return apply_exchange(db, batch, actor)
    choices = choices or {}
    parsed = batch.evidence
    factory = batch.factory_id
    machines = {
        m.code: m
        for m in db.scalars(select(Machine).where(Machine.factory_id == factory))
    }
    created_machine_ids = []
    for item in parsed["machines"]:
        if item["code"] not in machines:
            data = {
                k: v
                for k, v in item.items()
                if k in {c.key for c in Machine.__table__.columns}
                and k not in {"id", "factory_id"}
            }
            obj = Machine(factory_id=factory, **data)
            touch(obj, actor)
            db.add(obj)
            db.flush()
            machines[obj.code] = obj
            created_machine_ids.append(obj.id)
    existing = candidate_index(db, factory)
    applied, skipped, conflicts, original, unchanged = [], [], [], [], []
    # Retain title/header/machine evidence as well as every incomplete demand.
    for row in parsed["structure_rows"]:
        db.add(
            ImportRow(
                batch_id=batch.id,
                source_row=row["source_row"],
                row_role=row["row_role"],
                evidence=row,
                issues=[],
            )
        )
    for row in parsed["demands"]:
        source_row = row["source_row"]
        if source_row in skip_rows:
            skipped.append(source_row)
            db.add(
                ImportRow(
                    batch_id=batch.id,
                    source_row=source_row,
                    row_role=row["row_role"],
                    evidence=row,
                    issues=[{"code": "USER_SKIPPED"}],
                )
            )
            continue
        fields = row["fields"]
        candidates = row_candidates(existing, row)
        chosen = choices.get(str(source_row))
        if chosen:
            obj = db.get(Demand, chosen)
            if not obj or obj.factory_id != factory or obj not in candidates:
                raise HTTPException(422, "选择的合并需求不属于本行候选")
        elif len(candidates) == 1:
            obj = candidates[0]
        elif candidates:
            conflicts.append(
                {
                    "source_row": source_row,
                    "code": "AMBIGUOUS_DEMAND",
                    "candidates": [d.id for d in candidates],
                }
            )
            db.add(
                ImportRow(
                    batch_id=batch.id,
                    source_row=source_row,
                    row_role=row["row_role"],
                    evidence=row,
                    issues=[conflicts[-1]],
                )
            )
            continue
        else:
            obj = None
        if obj:
            evidence = ImportRow(
                batch_id=batch.id,
                source_row=source_row,
                row_role=row["row_role"],
                demand_id=obj.id,
                evidence=row,
                issues=[],
            )
            db.add(evidence)
            db.flush()
            changed, issues = update_legacy_row(db, batch, row, obj, evidence, actor)
            evidence.issues = issues
            conflicts.extend(issues)
            (applied if changed else unchanged).append(obj.id)
            continue
        master = match_mold(db, fields["mold_code"])
        if not master:
            defaults = {
                k: fields[k]
                for k in (
                    "target_shots_per_day",
                    "net_weight_g",
                    "gross_weight_g",
                    "price_per_shot",
                )
                if fields.get(k) is not None
            }
            master = MoldMaster(
                mold_code=fields["mold_code"],
                normalized_code=normalize_code(fields["mold_code"]),
                part_name=fields.get("part_name") or "",
                required_machine_a=fields.get("required_machine_a"),
                requirement_raw=row["raw_fields"].get("required_machine_a") or "",
                requirements=fields["requirements_snapshot"],
                defaults=defaults,
                created_from_factory_id=factory,
                source={
                    "batch_id": batch.id,
                    "source_row": source_row,
                    "kind": "LEGACY_CACHE",
                },
            )
            touch(master, actor)
            db.add(master)
            db.flush()
        if (
            db.scalar(
                select(MoldAsset.id).where(MoldAsset.master_id == master.id).limit(1)
            )
            is None
        ):
            db.add(
                MoldAsset(
                    master_id=master.id,
                    asset_code=f"{master.mold_code} / 1",
                    current_factory_id=factory,
                    status="AVAILABLE",
                    location_source="由本厂导入计划推定单副",
                    updated_by=actor,
                    updated_at=now(),
                )
            )
            db.flush()
        model_keys = {c.key for c in Demand.__table__.columns}
        data = {
            k: timestamp(v)
            if FIELDS.get(k) and FIELDS[k].value_type == "datetime"
            else v
            for k, v in fields.items()
            if k in model_keys
            and k
            not in {
                "completed_shots",
                "remaining_shots",
                "machine_code",
                "planned_start_at",
                "planned_end_at",
                "expected_stock_ready_at",
                "delivery_slack_hours",
            }
        }
        extra = {k: v for k, v in fields.items() if k not in model_keys}
        extra["legacy_schedule"] = {
            "machine_code": row["inferred_machine_block"],
            "start": fields.get("planned_start_at"),
            "end": fields.get("planned_end_at"),
            "source_row": source_row,
        }
        extra["legacy_signed_remaining"] = row["raw_fields"].get("remaining_shots")
        extra["legacy_history_quantity"] = row["numeric_shift_sum"]
        extra["import_issues"] = row["issues"]
        complete = (
            fields.get("planned_shots") is not None
            and fields.get("completed_shots") is not None
        )
        history_total = decimal(row["numeric_shift_sum"], 0)
        cached = decimal(fields.get("completed_shots"), 0)
        # Path A: only the difference before the imported detail window is opening.
        opening = cached - history_total if complete else 0
        if opening < 0:
            complete = False
            opening = cached
            extra["import_issues"].append(
                {
                    "code": "HISTORY_EXCEEDS_CACHED_TOTAL",
                    "message": "历史作为只读证据；按截止快照计累计",
                }
            )
        obj = Demand(
            factory_id=factory,
            mold_master_id=master.id,
            opening_shots=opening,
            **data,
            extras=extra,
            field_sources={
                k: {
                    "kind": "LEGACY_CACHE",
                    "batch_id": batch.id,
                    "source_row": source_row,
                }
                for k in data
            },
            source_system="LEGACY_PLAN",
            source_document=batch.file_name,
            source_line_id=f"{batch.file_sha256}:{source_row}",
            source_row=source_row,
            stable_sequence=source_row,
            import_batch_id=batch.id,
        )
        if row["history"]:
            obj.opening_cutoff_at = timestamp(
                max(h["date"] for h in row["history"])
            ) + timedelta(days=1, hours=8)
        enrich(db, obj)
        obj.extras = {
            **obj.extras,
            "legacy_import_baseline": {
                "source_fields": fields,
                "server_fields": jsonable(record(obj)),
                "history": {
                    f"{h['date']}|{h['shift_code']}": h["raw_quantity"]
                    for h in row["history"]
                },
                "opening_shots": float(opening),
                "source_row": source_row,
            },
        }
        touch(obj, actor)
        db.add(obj)
        db.flush()
        evidence = ImportRow(
            batch_id=batch.id,
            source_row=source_row,
            row_role=row["row_role"],
            demand_id=obj.id,
            evidence=row,
            issues=row["issues"],
        )
        db.add(evidence)
        db.flush()
        for h in row["history"]:
            db.add(
                HistoricalOutput(
                    demand_id=obj.id,
                    import_row_id=evidence.id,
                    production_date=date.fromisoformat(h["date"]),
                    shift_code=h["shift_code"],
                    source_key="legacy",
                    quantity=h["raw_quantity"],
                    counts_toward_demand=complete,
                    allocation_mode="LEGACY_UNRESOLVED",
                )
            )
        update_quantities(obj, history_total if complete else 0)
        applied.append(obj.id)
        # Repeated rows in the same workbook are distinct source-line identities.
        # Candidate matching here only considers records that existed before this batch.
        if row["inferred_machine_block"]:
            original.append(
                {
                    "demand_id": obj.id,
                    "machine_id": machines[row["inferred_machine_block"]].id,
                    "source_row": source_row,
                    "legacy_start": fields.get("planned_start_at"),
                }
            )
    batch.status = "APPLIED"
    from .reports import reallocate_factory

    db.flush()
    if applied:
        reallocate_factory(db, factory)
    batch.summary = {
        **batch.summary,
        "applied_count": len(applied),
        "unchanged_count": len(unchanged),
        "skipped_rows": skipped,
        "conflicts": conflicts,
        "original_assignments": original,
        "created_machine_ids": created_machine_ids,
    }
    touch(batch, actor)
    db.flush()
    return {
        "batch_id": batch.id,
        "summary": batch.summary,
        "demand_ids": applied,
        "recalculate_required": bool(applied or created_machine_ids),
        "changed_runs": [],
    }

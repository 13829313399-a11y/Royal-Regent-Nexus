from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from hashlib import sha256
import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import BUSINESS_TIME_ZONE, parse_business_timestamp
from app.models.injection_schedule import (
    InjectionMachineMaster,
    InjectionMoldMaster,
    InjectionOrderMaster,
    InjectionScheduleRuleConfig,
    InjectionScheduleTask,
    InjectionScheduleVersion,
)
from app.schemas.injection_schedule import InjectionScheduleRuleConfigUpdateRequest
from app.services.auth import AuthContext
from app.services.injection_schedule_excel import canonical_json, normalize_key
from app.services.injection_schedule_import import (
    add_audit_event,
    json_object,
    now_text,
    revision_conflict,
    serialize_rule_config,
)
from app.services.injection_schedule_rules import (
    calculate_transition_setup,
    canonical_color_key,
    normalize_rule_config,
)
from app.services.injection_schedule_validation import (
    validate_capabilities,
    validate_delivery_due_date,
    validate_dimensions,
    validate_machine_class,
    validate_material,
    validate_robot_requirement,
    validate_shot_capacity,
    validate_text_requirement,
)


SCORE_LABELS: dict[str, str] = {
    "due_date": "货期紧迫度",
    "sequence_affinity": "同模/同料连续",
    "setup_efficiency": "换模/换色效率",
    "color_transition": "颜色转换",
    "load_balance": "机台负载",
    "downstream_priority": "下游交付影响",
    "exact_match": "机械手/夹具精确匹配",
    "split_penalty": "拆单惩罚",
    "special_handling_penalty": "人工特殊处理惩罚",
}
NATURAL_PART_PATTERN = re.compile(r"(\d+)")


def get_rule_config(db: Session, factory_id: str) -> dict[str, Any]:
    item = db.get(InjectionScheduleRuleConfig, factory_id)
    if item is None:
        return {
            "factory_id": factory_id,
            "config": normalize_rule_config({}),
            "revision": 0,
            "updated_by": "",
            "updated_at": "",
        }
    return serialize_rule_config(item)


def update_rule_config(
    db: Session,
    factory_id: str,
    payload: InjectionScheduleRuleConfigUpdateRequest,
    actor: AuthContext,
    *,
    request_id: str = "",
    ip_address: str = "",
) -> dict[str, Any]:
    document = payload.config.model_dump()
    _validate_window_machine_ids(db, factory_id, document["unavailable_windows"])
    timestamp = now_text()
    current = db.scalar(
        select(InjectionScheduleRuleConfig)
        .where(InjectionScheduleRuleConfig.factory_id == factory_id)
        .with_for_update()
    )
    if current is None:
        if payload.expected_revision != 0:
            raise revision_conflict(factory_id, payload.expected_revision, None)
        item = InjectionScheduleRuleConfig(
            factory_id=factory_id,
            config_json=canonical_json(document),
            revision=1,
            updated_by=actor.id,
            updated_at=timestamp,
        )
        db.add(item)
        add_audit_event(
            db,
            factory_id=factory_id,
            entity_type="rule_config",
            entity_id=factory_id,
            action="created",
            actor=actor,
            request_id=request_id,
            ip_address=ip_address,
            reason=payload.reason,
            old_revision=0,
            new_revision=1,
            before={"config": normalize_rule_config({})},
            after={"config": document},
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            concurrent = db.get(InjectionScheduleRuleConfig, factory_id)
            raise revision_conflict(
                factory_id,
                payload.expected_revision,
                concurrent.revision if concurrent is not None else None,
            )
        return serialize_rule_config(item)

    before = serialize_rule_config(current)
    result = db.execute(
        update(InjectionScheduleRuleConfig)
        .where(
            InjectionScheduleRuleConfig.factory_id == factory_id,
            InjectionScheduleRuleConfig.revision == payload.expected_revision,
        )
        .values(
            config_json=canonical_json(document),
            revision=InjectionScheduleRuleConfig.revision + 1,
            updated_by=actor.id,
            updated_at=timestamp,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        concurrent = db.get(InjectionScheduleRuleConfig, factory_id)
        raise revision_conflict(
            factory_id,
            payload.expected_revision,
            concurrent.revision if concurrent is not None else None,
        )
    new_revision = payload.expected_revision + 1
    add_audit_event(
        db,
        factory_id=factory_id,
        entity_type="rule_config",
        entity_id=factory_id,
        action="updated",
        actor=actor,
        request_id=request_id,
        ip_address=ip_address,
        reason=payload.reason,
        old_revision=payload.expected_revision,
        new_revision=new_revision,
        before=before,
        after={"factory_id": factory_id, "config": document, "revision": new_revision},
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.expire_all()
    return serialize_rule_config(
        db.get(InjectionScheduleRuleConfig, factory_id)
    )


def _index_unavailable_windows(
    rules: dict[str, Any],
    machines: list[InjectionMachineMaster],
) -> dict[str, list[tuple[datetime, datetime, str]]]:
    """Parse every configured window once for a recommendation request."""

    factory_windows: list[tuple[datetime, datetime, str]] = []
    machine_windows: dict[str, list[tuple[datetime, datetime, str]]] = defaultdict(
        list
    )
    for item in rules["unavailable_windows"]:
        start = parse_business_timestamp(str(item.get("start_at", "")))
        end = parse_business_timestamp(str(item.get("end_at", "")))
        if start is None or end is None or end <= start:
            continue
        parsed = (start, end, str(item.get("reason", "")))
        if item.get("scope") == "factory":
            factory_windows.append(parsed)
        elif item.get("scope") == "machine":
            machine_windows[str(item.get("machine_id", ""))].append(parsed)

    return {
        machine.id: sorted(
            [*factory_windows, *machine_windows.get(machine.id, [])],
            key=lambda item: (item[0], item[1], item[2]),
        )
        for machine in machines
    }


@dataclass
class AutoRecommendationBatch:
    """Preloaded, append-only recommendation state for Phase 4 auto drafts.

    The interactive Phase 3 API still evaluates every legal gap. Automatic
    drafts intentionally use the safe append position so existing work and
    execution barriers never move. All master/rule/task rows are loaded once;
    each scheduled task is then registered in memory for the next order.
    """

    factory_id: str
    version: InjectionScheduleVersion
    machines: list[InjectionMachineMaster]
    mold_by_code: dict[str, InjectionMoldMaster]
    lanes: dict[str, list[InjectionScheduleTask]]
    machine_load_hours: dict[str, float]
    existing_order_machine_ids: dict[str, set[str]]
    rules: dict[str, Any]
    rule_hash: str
    rule_config_revision: int
    plan_base: datetime
    parsed_windows_by_machine: dict[
        str,
        list[tuple[datetime, datetime, str]],
    ]
    calendar_horizon: datetime | None
    base_constraint_cache: dict[
        tuple[Any, ...],
        list[dict[str, Any]],
    ]
    lane_dependency_hashes: dict[str, str]
    max_transition_minutes: float
    max_color_minutes: float
    scoring_weights: dict[str, float]

    @classmethod
    def load(
        cls,
        db: Session,
        version: InjectionScheduleVersion,
    ) -> "AutoRecommendationBatch":
        machines = list(
            db.scalars(
                select(InjectionMachineMaster)
                .where(
                    InjectionMachineMaster.factory_id == version.factory_id
                )
                .order_by(InjectionMachineMaster.id)
            ).all()
        )
        molds = list(
            db.scalars(
                select(InjectionMoldMaster).where(
                    InjectionMoldMaster.factory_id == version.factory_id
                )
            ).all()
        )
        tasks = list(
            db.scalars(
                select(InjectionScheduleTask)
                .where(
                    InjectionScheduleTask.factory_id == version.factory_id,
                    InjectionScheduleTask.version_id == version.id,
                )
                .order_by(
                    InjectionScheduleTask.machine_id,
                    InjectionScheduleTask.sequence_no,
                    InjectionScheduleTask.id,
                )
            ).all()
        )
        lanes: dict[str, list[InjectionScheduleTask]] = defaultdict(list)
        machine_load_hours: dict[str, float] = defaultdict(float)
        existing_order_machine_ids: dict[str, set[str]] = defaultdict(set)
        for task in tasks:
            lanes[task.machine_id].append(task)
            if task.execution_status not in {"completed", "cancelled"}:
                machine_load_hours[task.machine_id] += max(
                    float(task.duration_hours),
                    0,
                )
                existing_order_machine_ids[task.order_id].add(task.machine_id)

        rules = normalize_rule_config(
            json_object(version.rules_snapshot_json)
        )
        rule_hash = sha256(canonical_json(rules).encode("utf-8")).hexdigest()
        plan_base = parse_business_timestamp(version.plan_base_at)
        if plan_base is None:
            plan_base = datetime.now(BUSINESS_TIME_ZONE).replace(
                second=0,
                microsecond=0,
            )
        lane_dependency_hashes = {
            machine.id: _lane_dependency_hash(
                lanes.get(machine.id, [])
            )
            for machine in machines
        }
        return cls(
            factory_id=version.factory_id,
            version=version,
            machines=machines,
            mold_by_code={
                item.normalized_mold_code: item for item in molds
            },
            lanes=lanes,
            machine_load_hours=machine_load_hours,
            existing_order_machine_ids=existing_order_machine_ids,
            rules=rules,
            rule_hash=rule_hash,
            rule_config_revision=max(
                int(version.rule_config_revision or 0),
                0,
            ),
            plan_base=plan_base,
            parsed_windows_by_machine=_index_unavailable_windows(
                rules,
                machines,
            ),
            calendar_horizon=parse_business_timestamp(
                str(
                    rules.get(
                        "availability_calendar_verified_through",
                        "",
                    )
                )
            ),
            base_constraint_cache={},
            lane_dependency_hashes=lane_dependency_hashes,
            max_transition_minutes=max(
                [
                    float(item["minutes"])
                    for key in (
                        "color_transition_matrix",
                        "material_transition_matrix",
                    )
                    for item in rules[key]
                ]
                + [
                    float(item["mold_change_minutes"])
                    for item in rules["setup_minutes"]
                ]
                + [1.0]
            ),
            max_color_minutes=max(
                [
                    float(item["minutes"])
                    for item in rules["color_transition_matrix"]
                ]
                + [1.0]
            ),
            scoring_weights={
                code: float(rules["scoring_weights"][code])
                for code in SCORE_LABELS
            },
        )

    def recommend(
        self,
        order: InjectionOrderMaster,
        planned_qty: float,
    ) -> dict[str, Any]:
        maximum_load = max(self.machine_load_hours.values(), default=0)
        candidates = [
            self._candidate(
                order,
                machine,
                planned_qty,
                maximum_load,
                include_context_hash=False,
            )
            for machine in self.machines
        ]
        _assign_candidate_ranks(candidates)
        ordered = sorted(candidates, key=_candidate_sort_key)
        return {
            "factory_id": self.factory_id,
            "version_id": self.version.id,
            "version_revision": self.version.revision,
            "order_id": order.id,
            "order_revision": order.revision,
            "planned_qty": round(planned_qty, 6),
            "rule_config_revision": self.rule_config_revision,
            "rule_config_hash": self.rule_hash,
            "uses_version_rule_snapshot": True,
            "generated_at": now_text(),
            "total_candidates": len(candidates),
            "eligible_count": sum(
                item["status"] == "eligible" for item in candidates
            ),
            "manual_review_count": sum(
                item["status"] == "manual_review" for item in candidates
            ),
            "blocked_count": sum(
                item["status"] == "blocked" for item in candidates
            ),
            "candidates": ordered,
        }

    def select_append_candidate(
        self,
        order: InjectionOrderMaster,
        planned_qty: float,
    ) -> dict[str, Any]:
        """Select one append candidate without materializing 76 explanations.

        Phase 4 may evaluate 1,500 orders against 76 machines.  The complete
        constraint evidence and score explanation are still generated for the
        selected machine, while non-selected machines use the same rules in a
        compact numeric pass.  This keeps the decision identical and avoids
        constructing more than one million short-lived explanation objects.
        """

        maximum_load = max(self.machine_load_hours.values(), default=0)
        counts = {
            "eligible": 0,
            "manual_review": 0,
            "blocked": 0,
        }
        best: tuple[tuple[Any, ...], InjectionMachineMaster, float] | None = None
        mold = self.mold_by_code.get(normalize_key(order.mold_code))
        for machine in self.machines:
            base_constraints = self._base_constraints(
                order,
                machine,
                mold,
            )
            compact = _compact_append_candidate(
                order=order,
                mold=mold,
                machine=machine,
                previous=(
                    self.lanes.get(machine.id, [])[-1]
                    if self.lanes.get(machine.id)
                    else None
                ),
                base_constraints=base_constraints,
                rules=self.rules,
                planned_qty=planned_qty,
                machine_load_hours=self.machine_load_hours.get(
                    machine.id,
                    0,
                ),
                maximum_load_hours=maximum_load,
                existing_order_machine_ids=self.existing_order_machine_ids.get(
                    order.id,
                    set(),
                ),
                plan_base=self.plan_base,
                machine_available_at=parse_business_timestamp(
                    machine.available_at
                ),
                parsed_windows=self.parsed_windows_by_machine.get(
                    machine.id,
                    [],
                ),
                calendar_horizon=self.calendar_horizon,
                max_transition_minutes=self.max_transition_minutes,
                max_color_minutes=self.max_color_minutes,
                scoring_weights=self.scoring_weights,
            )
            status = str(compact["status"])
            counts[status] += 1
            if status != "eligible":
                continue
            total = float(compact["score_total"])
            key = (
                -total,
                _natural_key(machine.machine_code),
                machine.id,
            )
            if best is None or key < best[0]:
                best = (key, machine, total)

        if best is None:
            return {
                "candidate": None,
                "eligible_count": counts["eligible"],
                "manual_review_count": counts["manual_review"],
                "blocked_count": counts["blocked"],
            }

        _, machine, compact_total = best
        candidate = self._candidate(
            order,
            machine,
            planned_qty,
            maximum_load,
            include_context_hash=False,
        )
        if candidate["status"] != "eligible":
            raise RuntimeError("compact automatic candidate status changed")
        if abs(float(candidate["score"]["total"]) - compact_total) > 1e-6:
            raise RuntimeError("compact automatic candidate score changed")
        candidate["rank"] = 1
        candidate["recommendation_context_hash"] = (
            self._append_candidate_trace_hash(
                order,
                machine,
                planned_qty,
                candidate,
            )
        )
        return {
            "candidate": candidate,
            "eligible_count": counts["eligible"],
            "manual_review_count": counts["manual_review"],
            "blocked_count": counts["blocked"],
        }

    def recommend_movable_suffix(
        self,
        order: InjectionOrderMaster,
        planned_qty: float,
    ) -> dict[str, Any]:
        """Evaluate the first safe insertion point after each lane's barriers.

        Urgent orders may push a movable suffix, but they must never jump ahead
        of a locked/running/completed/cancelled/protected task.  Unlike the
        batch auto planner's append-only candidates, these estimates include
        the real predecessor and successor at the exact insertion gap.
        """

        maximum_load = max(self.machine_load_hours.values(), default=0)
        candidates: list[dict[str, Any]] = []
        for machine in self.machines:
            lane = self.lanes.get(machine.id, [])
            target_index = (
                max(
                    (
                        index
                        for index, task in enumerate(lane)
                        if task.locked
                        or task.protected
                        or task.execution_status
                        in {"running", "completed", "cancelled"}
                    ),
                    default=-1,
                )
                + 1
            )
            candidates.append(
                self._candidate(
                    order,
                    machine,
                    planned_qty,
                    maximum_load,
                    include_context_hash=True,
                    target_index=target_index,
                    allow_downstream_shift=True,
                )
            )
        _assign_candidate_ranks(candidates)
        ordered = sorted(candidates, key=_candidate_sort_key)
        return {
            "factory_id": self.factory_id,
            "version_id": self.version.id,
            "version_revision": self.version.revision,
            "order_id": order.id,
            "order_revision": order.revision,
            "planned_qty": round(planned_qty, 6),
            "rule_config_revision": self.rule_config_revision,
            "rule_config_hash": self.rule_hash,
            "uses_version_rule_snapshot": True,
            "generated_at": now_text(),
            "total_candidates": len(candidates),
            "eligible_count": sum(
                item["status"] == "eligible" for item in candidates
            ),
            "manual_review_count": sum(
                item["status"] == "manual_review" for item in candidates
            ),
            "blocked_count": sum(
                item["status"] == "blocked" for item in candidates
            ),
            "candidates": ordered,
        }

    def finalize_candidate(
        self,
        order: InjectionOrderMaster,
        planned_qty: float,
        selected: dict[str, Any],
    ) -> dict[str, Any]:
        machine = next(
            (
                item
                for item in self.machines
                if item.id == selected["machine_id"]
            ),
            None,
        )
        if machine is None:
            raise RuntimeError("automatic candidate machine disappeared")
        maximum_load = max(self.machine_load_hours.values(), default=0)
        finalized = self._candidate(
            order,
            machine,
            planned_qty,
            maximum_load,
            include_context_hash=True,
        )
        if (
            finalized["status"] != "eligible"
            or finalized["target_index"] != selected["target_index"]
        ):
            raise RuntimeError("automatic candidate context changed")
        finalized["rank"] = selected.get("rank")
        finalized["advisory_rank"] = selected.get("advisory_rank")
        return finalized

    def register_task(self, task: InjectionScheduleTask) -> None:
        lane = self.lanes[task.machine_id]
        if task.sequence_no != len(lane):
            raise RuntimeError("automatic task is not an append operation")
        prior_digest = self.lane_dependency_hashes.get(
            task.machine_id,
            _lane_dependency_hash([]),
        )
        lane.append(task)
        self.lane_dependency_hashes[task.machine_id] = sha256(
            canonical_json(
                {
                    "previous_digest": prior_digest,
                    "appended_task": _task_dependency_snapshot(task),
                }
            ).encode("utf-8")
        ).hexdigest()
        self.machine_load_hours[task.machine_id] = (
            self.machine_load_hours.get(task.machine_id, 0.0)
            + max(float(task.duration_hours), 0)
        )
        self.existing_order_machine_ids.setdefault(
            task.order_id,
            set(),
        ).add(task.machine_id)

    def _append_candidate_trace_hash(
        self,
        order: InjectionOrderMaster,
        machine: InjectionMachineMaster,
        planned_qty: float,
        candidate: dict[str, Any],
    ) -> str:
        lane = self.lanes.get(machine.id, [])
        previous = lane[-1] if lane else None
        score = candidate.get("score") or {}
        estimated = score.get("estimated") or {}
        transition = score.get("transition") or {}
        result_hash = sha256(
            canonical_json(
                {
                    "hard_constraints": candidate.get(
                        "hard_constraints",
                        [],
                    ),
                    "score": score,
                }
            ).encode("utf-8")
        ).hexdigest()
        return sha256(
            canonical_json(
                {
                    "factory_id": self.factory_id,
                    "source_version_id": (
                        self.version.base_version_id or self.version.id
                    ),
                    "version_revision": self.version.revision,
                    "order_id": order.id,
                    "order_revision": order.revision,
                    "machine_id": machine.id,
                    "machine_revision": machine.revision,
                    "target_index": candidate["target_index"],
                    "planned_qty": round(planned_qty, 6),
                    "rule_hash": self.rule_hash,
                    "rule_config_revision": self.rule_config_revision,
                    "lane_dependency_hash": (
                        self.lane_dependency_hashes.get(
                            machine.id,
                            _lane_dependency_hash([]),
                        )
                    ),
                    "previous": {
                        "identity": (
                            _task_dependency_identity(previous)
                            if previous is not None
                            else ""
                        ),
                        "revision": (
                            previous.revision
                            if previous is not None
                            else 0
                        ),
                        "planned_finish_at": (
                            previous.planned_finish_at
                            if previous is not None
                            else ""
                        ),
                    },
                    "constraints": [
                        [item["code"], item["status"]]
                        for item in candidate.get("hard_constraints", [])
                    ],
                    "score_total": score.get("total"),
                    "production_start_at": estimated.get(
                        "production_start_at"
                    ),
                    "finish_at": estimated.get("finish_at"),
                    "setup_minutes_before": transition.get(
                        "setup_minutes_before"
                    ),
                    "result_hash": result_hash,
                }
            ).encode("utf-8")
        ).hexdigest()

    def _base_constraints(
        self,
        order: InjectionOrderMaster,
        machine: InjectionMachineMaster,
        mold: InjectionMoldMaster | None,
    ) -> list[dict[str, Any]]:
        base_key = (
            order.factory_id,
            order.status,
            bool(float(order.outstanding_qty) > 0),
            normalize_key(order.mold_code),
            canonical_color_key(order.pigment, order.color),
            normalize_key(order.material),
            normalize_key(order.machine_class),
            order.delivery_due_date,
            float(order.daily_target_qty or 0),
            mold.id if mold is not None else "",
            mold.revision if mold is not None else 0,
            machine.id,
            machine.revision,
            self.rule_hash,
        )
        base_constraints = self.base_constraint_cache.get(base_key)
        if base_constraints is None:
            base_constraints = _base_constraints(
                self.factory_id,
                order,
                mold,
                machine,
                self.rules,
            )
            self.base_constraint_cache[base_key] = base_constraints
        return base_constraints

    def _candidate(
        self,
        order: InjectionOrderMaster,
        machine: InjectionMachineMaster,
        planned_qty: float,
        maximum_load: float,
        *,
        include_context_hash: bool,
        target_index: int | None = None,
        allow_downstream_shift: bool = False,
    ) -> dict[str, Any]:
        lane = self.lanes.get(machine.id, [])
        mold = self.mold_by_code.get(normalize_key(order.mold_code))
        base_constraints = self._base_constraints(order, machine, mold)
        return _candidate_at_gap(
            factory_id=self.factory_id,
            version=self.version,
            context_version_revision=self.version.revision,
            order=order,
            mold=mold,
            machine=machine,
            lane=lane,
            target_index=(
                len(lane)
                if target_index is None
                else max(0, min(target_index, len(lane)))
            ),
            base_constraints=base_constraints,
            rules=self.rules,
            rule_hash=self.rule_hash,
            rule_config_revision=self.rule_config_revision,
            planned_qty=planned_qty,
            machine_load_hours=self.machine_load_hours.get(machine.id, 0),
            maximum_load_hours=maximum_load,
            existing_order_machine_ids=self.existing_order_machine_ids.get(
                order.id,
                set(),
            ),
            plan_base=self.plan_base,
            machine_available_at=parse_business_timestamp(
                machine.available_at
            ),
            parsed_windows=self.parsed_windows_by_machine.get(
                machine.id,
                [],
            ),
            calendar_horizon=self.calendar_horizon,
            include_context_hash=include_context_hash,
            allow_downstream_shift=allow_downstream_shift,
        )


def _task_dependency_identity(task: InjectionScheduleTask) -> str:
    """Return a stable identity across exact-clone preview transactions."""

    if task.parent_task_id:
        return task.parent_task_id
    return sha256(
        canonical_json(
            {
                "order_id": task.order_id,
                "machine_id": task.machine_id,
                "sequence_no": task.sequence_no,
                "source": task.source,
            }
        ).encode("utf-8")
    ).hexdigest()


def _task_dependency_snapshot(
    task: InjectionScheduleTask,
) -> dict[str, Any]:
    """Complete scheduling semantics used by the append lane digest."""

    return {
        "identity": _task_dependency_identity(task),
        "parent_task_id": task.parent_task_id,
        "source": task.source,
        "revision": task.revision,
        "sequence_no": task.sequence_no,
        "order_id": task.order_id,
        "machine_id": task.machine_id,
        "mold_id": task.mold_id,
        "planned_qty": task.planned_qty,
        "planned_start_at": task.planned_start_at,
        "planned_finish_at": task.planned_finish_at,
        "setup_hours": task.setup_hours,
        "duration_hours": task.duration_hours,
        "locked": bool(task.locked),
        "protected": bool(task.protected),
        "execution_status": task.execution_status,
        "mold_code": task.mold_code_snapshot,
        "color": task.color_snapshot,
        "color_rank": task.color_rank_snapshot,
        "material": task.material_snapshot,
        "product_code": task.product_code_snapshot,
        "order_revision_snapshot": task.order_revision_snapshot,
        "machine_revision_snapshot": task.machine_revision_snapshot,
        "mold_revision_snapshot": task.mold_revision_snapshot,
    }


def _lane_dependency_hash(
    lane: list[InjectionScheduleTask],
) -> str:
    digest = sha256(b"[]").hexdigest()
    for task in lane:
        digest = sha256(
            canonical_json(
                {
                    "previous_digest": digest,
                    "appended_task": _task_dependency_snapshot(task),
                }
            ).encode("utf-8")
        ).hexdigest()
    return digest


def recommend_order_machines(
    db: Session,
    factory_id: str,
    version_id: str,
    order_id: str,
    *,
    limit: int = 20,
    planned_qty: float | None = None,
    context_version_revision: int | None = None,
    for_update: bool = False,
) -> dict[str, Any]:
    version_statement = select(InjectionScheduleVersion).where(
        InjectionScheduleVersion.id == version_id,
        InjectionScheduleVersion.factory_id == factory_id,
    )
    if for_update:
        version_statement = version_statement.with_for_update()
    version = db.scalar(version_statement)
    if version is None:
        raise HTTPException(status_code=404, detail="未找到该厂区的排程版本")

    order_statement = select(InjectionOrderMaster).where(
        InjectionOrderMaster.id == order_id,
        InjectionOrderMaster.factory_id == factory_id,
    )
    if for_update:
        order_statement = order_statement.with_for_update()
    order = db.scalar(order_statement)
    if order is None:
        raise HTTPException(status_code=404, detail="未找到该厂区的订单")

    machine_statement = (
        select(InjectionMachineMaster)
        .where(InjectionMachineMaster.factory_id == factory_id)
        .order_by(InjectionMachineMaster.id)
    )
    if for_update:
        machine_statement = machine_statement.with_for_update()
    machines = list(db.scalars(machine_statement).all())

    mold_statement = select(InjectionMoldMaster).where(
        InjectionMoldMaster.factory_id == factory_id,
        InjectionMoldMaster.normalized_mold_code == normalize_key(order.mold_code),
    )
    if for_update:
        mold_statement = mold_statement.with_for_update()
    mold = db.scalar(mold_statement)

    task_statement = (
        select(InjectionScheduleTask)
        .where(
            InjectionScheduleTask.factory_id == factory_id,
            InjectionScheduleTask.version_id == version_id,
        )
        .order_by(
            InjectionScheduleTask.machine_id,
            InjectionScheduleTask.sequence_no,
            InjectionScheduleTask.id,
        )
    )
    if for_update:
        task_statement = task_statement.with_for_update()
    tasks = list(db.scalars(task_statement).all())

    current_config = db.get(InjectionScheduleRuleConfig, factory_id)
    snapshot_raw = json_object(version.rules_snapshot_json)
    snapshot_revision = max(int(version.rule_config_revision or 0), 0)
    rules = normalize_rule_config(snapshot_raw)
    rule_hash = sha256(canonical_json(rules).encode("utf-8")).hexdigest()
    current_revision = current_config.revision if current_config is not None else 0
    parsed_windows_by_machine = _index_unavailable_windows(rules, machines)
    calendar_horizon = parse_business_timestamp(
        str(rules.get("availability_calendar_verified_through", ""))
    )
    plan_base = parse_business_timestamp(version.plan_base_at)
    if plan_base is None:
        plan_base = datetime.now(BUSINESS_TIME_ZONE).replace(second=0, microsecond=0)

    allocated_qty = sum(
        item.planned_qty
        for item in tasks
        if item.order_id == order.id
        and item.execution_status not in {"completed", "cancelled"}
    )
    remaining_qty = max(order.outstanding_qty - allocated_qty, 0)
    requested_qty = remaining_qty if planned_qty is None else float(planned_qty)
    if requested_qty <= 0:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "order_fully_planned",
                "message": "该订单在所选版本中已无待排数量",
                "outstanding_qty": order.outstanding_qty,
                "already_planned_qty": allocated_qty,
            },
        )
    if requested_qty > remaining_qty + 1e-6:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "planned_qty_exceeds_unplanned",
                "message": "推荐数量超过所选版本中的剩余待排数量",
                "remaining_unplanned_qty": remaining_qty,
                "requested_qty": requested_qty,
            },
        )

    lanes: dict[str, list[InjectionScheduleTask]] = defaultdict(list)
    machine_load_hours: dict[str, float] = defaultdict(float)
    for task in tasks:
        lanes[task.machine_id].append(task)
        machine_load_hours[task.machine_id] += max(task.duration_hours, 0)
    maximum_load = max(machine_load_hours.values(), default=0)
    existing_order_machine_ids = {
        item.machine_id
        for item in tasks
        if item.order_id == order.id
        and item.execution_status not in {"completed", "cancelled"}
    }
    context_revision = context_version_revision or version.revision

    candidates = [
        _best_machine_candidate(
            factory_id=factory_id,
            version=version,
            context_version_revision=context_revision,
            order=order,
            mold=mold,
            machine=machine,
            lane=lanes.get(machine.id, []),
            rules=rules,
            rule_hash=rule_hash,
            rule_config_revision=snapshot_revision,
            planned_qty=requested_qty,
            machine_load_hours=machine_load_hours.get(machine.id, 0),
            maximum_load_hours=maximum_load,
            existing_order_machine_ids=existing_order_machine_ids,
            plan_base=plan_base,
            machine_available_at=parse_business_timestamp(machine.available_at),
            parsed_windows=parsed_windows_by_machine.get(machine.id, []),
            calendar_horizon=calendar_horizon,
        )
        for machine in machines
    ]
    _assign_candidate_ranks(candidates)
    ordered = sorted(candidates, key=_candidate_sort_key)
    bounded_limit = max(1, min(int(limit), 100))
    return {
        "factory_id": factory_id,
        "version_id": version.id,
        "version_revision": version.revision,
        "order_id": order.id,
        "order_revision": order.revision,
        "planned_qty": round(requested_qty, 6),
        "rule_config_revision": snapshot_revision,
        "current_rule_config_revision": current_revision,
        "rule_config_hash": rule_hash,
        "uses_version_rule_snapshot": True,
        "generated_at": now_text(),
        "total_candidates": len(candidates),
        "eligible_count": sum(item["status"] == "eligible" for item in candidates),
        "manual_review_count": sum(
            item["status"] == "manual_review" for item in candidates
        ),
        "blocked_count": sum(item["status"] == "blocked" for item in candidates),
        "candidates": ordered[:bounded_limit],
    }


def verify_recommendation_for_assignment(
    db: Session,
    *,
    factory_id: str,
    version_id: str,
    version_revision: int,
    order_id: str,
    machine_id: str,
    target_index: int,
    planned_qty: float,
    recommendation_context_hash: str,
) -> dict[str, Any]:
    response = recommend_order_machines(
        db,
        factory_id,
        version_id,
        order_id,
        limit=100,
        planned_qty=planned_qty,
        context_version_revision=version_revision,
        for_update=True,
    )
    candidate = next(
        (
            item
            for item in response["candidates"]
            if item["machine_id"] == machine_id
            and item["target_index"] == target_index
        ),
        None,
    )
    if candidate is None or candidate["recommendation_context_hash"] != (
        recommendation_context_hash
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "recommendation_stale",
                "message": "推荐依据已变化，请重新获取候选机台",
            },
        )
    if candidate["status"] == "blocked":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "recommendation_blocked",
                "message": "该机台存在已知硬约束冲突",
                "constraints": candidate["hard_constraints"],
            },
        )
    return candidate


def evaluate_phase3_master_constraints(
    factory_id: str,
    order: InjectionOrderMaster,
    mold: InjectionMoldMaster | None,
    machine: InjectionMachineMaster,
    rules: dict[str, Any],
) -> list[dict[str, Any]]:
    return _base_constraints(
        factory_id,
        order,
        mold,
        machine,
        normalize_rule_config(rules),
    )


def evaluate_scheduled_task_time_window(
    task: InjectionScheduleTask,
    machine: InjectionMachineMaster,
    rules: dict[str, Any],
) -> dict[str, Any]:
    normalized = normalize_rule_config(rules)
    start = parse_business_timestamp(task.planned_start_at)
    finish = parse_business_timestamp(task.planned_finish_at)
    if start is None or finish is None or finish <= start:
        return _constraint(
            "phase3_time_window",
            "fail",
            "任务计划开始/结束时间无效。",
            {
                "planned_start_at": task.planned_start_at,
                "planned_finish_at": task.planned_finish_at,
            },
        )
    occupied_start = start - timedelta(hours=max(task.setup_hours, 0))
    matching_windows = [
        item
        for item in normalized["unavailable_windows"]
        if item.get("scope") == "factory"
        or (
            item.get("scope") == "machine"
            and item.get("machine_id") == machine.id
        )
    ]
    overlaps = []
    for window in matching_windows:
        window_start = parse_business_timestamp(str(window.get("start_at", "")))
        window_end = parse_business_timestamp(str(window.get("end_at", "")))
        if (
            window_start is not None
            and window_end is not None
            and occupied_start < window_end
            and finish > window_start
        ):
            overlaps.append(
                {
                    "start_at": _datetime_text(window_start),
                    "end_at": _datetime_text(window_end),
                    "reason": str(window.get("reason", "")),
                }
            )
    if overlaps:
        return _constraint(
            "phase3_time_window",
            "fail",
            "任务换型或生产占用了厂区/机台停机窗口。",
            {
                "occupied_start_at": _datetime_text(occupied_start),
                "overlaps": overlaps,
            },
        )
    horizon = parse_business_timestamp(
        str(normalized.get("availability_calendar_verified_through", ""))
    )
    if horizon is None:
        return _constraint(
            "phase3_time_window",
            "unknown",
            "未配置已核验的停机日历覆盖截止时间。",
            {},
        )
    if finish > horizon:
        return _constraint(
            "phase3_time_window",
            "unknown",
            "任务完成时间超出已核验停机日历范围。",
            {
                "finish_at": _datetime_text(finish),
                "calendar_verified_through": _datetime_text(horizon),
            },
        )
    return _constraint(
        "phase3_time_window",
        "pass",
        "任务未占用停机窗口且位于已核验日历范围。",
        {
            "occupied_start_at": _datetime_text(occupied_start),
            "calendar_verified_through": _datetime_text(horizon),
        },
    )


def _validate_window_machine_ids(
    db: Session,
    factory_id: str,
    windows: list[dict[str, Any]],
) -> None:
    requested = {
        str(item.get("machine_id", ""))
        for item in windows
        if item.get("scope") == "machine"
    }
    if not requested:
        return
    existing = set(
        db.scalars(
            select(InjectionMachineMaster.id).where(
                InjectionMachineMaster.factory_id == factory_id,
                InjectionMachineMaster.id.in_(sorted(requested)),
            )
        ).all()
    )
    if existing != requested:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_unavailable_window_machine",
                "message": "停机窗口包含本厂区不存在的机台",
            },
        )


def _best_machine_candidate(
    *,
    factory_id: str,
    version: InjectionScheduleVersion,
    context_version_revision: int,
    order: InjectionOrderMaster,
    mold: InjectionMoldMaster | None,
    machine: InjectionMachineMaster,
    lane: list[InjectionScheduleTask],
    rules: dict[str, Any],
    rule_hash: str,
    rule_config_revision: int,
    planned_qty: float,
    machine_load_hours: float,
    maximum_load_hours: float,
    existing_order_machine_ids: set[str],
    plan_base: datetime,
    machine_available_at: datetime | None,
    parsed_windows: list[tuple[datetime, datetime, str]],
    calendar_horizon: datetime | None,
) -> dict[str, Any]:
    base_constraints = _base_constraints(
        factory_id,
        order,
        mold,
        machine,
        rules,
    )
    if any(item["status"] == "fail" for item in base_constraints):
        target_indexes = [len(lane)]
    else:
        target_indexes = list(range(len(lane) + 1))

    return min(
        (
            _candidate_at_gap(
            factory_id=factory_id,
            version=version,
            context_version_revision=context_version_revision,
            order=order,
            mold=mold,
            machine=machine,
            lane=lane,
            target_index=target_index,
            base_constraints=base_constraints,
            rules=rules,
            rule_hash=rule_hash,
            rule_config_revision=rule_config_revision,
            planned_qty=planned_qty,
            machine_load_hours=machine_load_hours,
            maximum_load_hours=maximum_load_hours,
            existing_order_machine_ids=existing_order_machine_ids,
            plan_base=plan_base,
            machine_available_at=machine_available_at,
            parsed_windows=parsed_windows,
            calendar_horizon=calendar_horizon,
        )
            for target_index in target_indexes
        ),
        key=_gap_choice_key,
    )


def _base_constraints(
    factory_id: str,
    order: InjectionOrderMaster,
    mold: InjectionMoldMaster | None,
    machine: InjectionMachineMaster,
    rules: dict[str, Any],
) -> list[dict[str, Any]]:
    constraints = [
        _constraint(
            "factory_scope",
            "pass"
            if order.factory_id == machine.factory_id == factory_id
            else "fail",
            "订单、机台与请求厂区一致。"
            if order.factory_id == machine.factory_id == factory_id
            else "订单或机台不属于请求厂区。",
            {
                "request_factory_id": factory_id,
                "order_factory_id": order.factory_id,
                "machine_factory_id": machine.factory_id,
            },
        ),
        _constraint(
            "order_status",
            "pass" if order.status == "open" and order.outstanding_qty > 0 else "fail",
            "订单处于可排产状态。"
            if order.status == "open" and order.outstanding_qty > 0
            else f"订单状态为 {order.status}，不能排产。"
            if order.status != "open"
            else "订单已无欠数，不能继续排产。",
            {"status": order.status, "outstanding_qty": order.outstanding_qty},
        ),
        _constraint(
            "machine_status",
            "pass" if machine.status == "available" else "fail",
            "机台状态可用。"
            if machine.status == "available"
            else f"机台状态为 {machine.status}。",
            {"status": machine.status, "available_at": machine.available_at},
        ),
    ]
    canonical_color = canonical_color_key(order.pigment, order.color)
    missing_transition_fields = [
        field_name
        for field_name, value in (
            ("mold_code", order.mold_code),
            ("color", canonical_color),
            ("material", order.material),
        )
        if not _known_transition_value(value)
    ]
    constraints.append(
        _constraint(
            "transition_data",
            "unknown" if missing_transition_fields else "pass",
            "缺少换模/换色/换料计算资料。"
            if missing_transition_fields
            else "换模、颜色与材料资料齐全。",
            {"missing_fields": missing_transition_fields},
        )
    )
    delivery = validate_delivery_due_date("", order.delivery_due_date)
    constraints.append(_from_validation(delivery))
    if order.daily_target_qty:
        constraints.append(
            _constraint(
                "production_rate",
                "pass",
                "订单日产量可用于估算生产时长。",
                {"daily_target_qty": order.daily_target_qty},
            )
        )
    else:
        constraints.append(
            _constraint(
                "production_rate",
                "unknown",
                "缺少订单日产量，预计完成时间仅为保守占位。",
                {},
            )
        )
    if mold is None:
        constraints.append(
            _constraint(
                "mold_master",
                "unknown",
                "缺少模具主数据，无法完成安全适配校验。",
                {"mold_code": order.mold_code},
            )
        )
        for code, message in (
            ("machine_class", "缺少模具主数据，无法校验机型。"),
            ("shot_capacity", "缺少模具主数据，无法校验射胶量。"),
            ("mold_dimensions", "缺少模具主数据，无法校验柱距。"),
            ("mold_thickness", "缺少模具主数据，无法校验模厚。"),
            ("opening_stroke", "缺少模具主数据，无法校验开模行程。"),
            ("robot_type", "缺少模具主数据，无法校验机械手。"),
            ("fixture_type", "缺少模具主数据，无法校验夹具。"),
            ("capabilities", "缺少模具主数据，无法校验工艺能力。"),
            ("screw_compatibility", "缺少模具主数据，无法校验螺杆。"),
        ):
            constraints.append(_constraint(code, "unknown", message, {}))
    else:
        constraints.append(
            _constraint(
                "mold_master",
                "pass",
                "已找到同厂区模具主数据。",
                {"mold_id": mold.id, "mold_revision": mold.revision},
            )
        )
        constraints.extend(
            [
                _from_validation(validate_machine_class("", machine, mold, order)),
                _from_validation(
                    validate_shot_capacity(
                        "",
                        machine,
                        mold,
                        float(rules["shot_safety_factor"]),
                    )
                ),
                _from_validation(validate_dimensions("", machine, mold)),
                _validate_mold_thickness(machine, mold),
                _validate_opening_stroke(machine, mold),
                _from_validation(
                    validate_robot_requirement("", mold.robot_type, machine.robot_type)
                ),
                _from_validation(
                    validate_text_requirement(
                        "",
                        "fixture_type",
                        mold.fixture_type,
                        machine.fixture_type,
                        "夹具",
                    )
                ),
                _from_validation(validate_capabilities("", machine, mold)),
                _validate_screw(machine, mold, order),
            ]
        )
    constraints.append(
        _from_validation(validate_material("", machine, mold, order))
    )
    return constraints


def _candidate_at_gap(
    *,
    factory_id: str,
    version: InjectionScheduleVersion,
    context_version_revision: int,
    order: InjectionOrderMaster,
    mold: InjectionMoldMaster | None,
    machine: InjectionMachineMaster,
    lane: list[InjectionScheduleTask],
    target_index: int,
    base_constraints: list[dict[str, Any]],
    rules: dict[str, Any],
    rule_hash: str,
    rule_config_revision: int,
    planned_qty: float,
    machine_load_hours: float,
    maximum_load_hours: float,
    existing_order_machine_ids: set[str],
    plan_base: datetime,
    machine_available_at: datetime | None,
    parsed_windows: list[tuple[datetime, datetime, str]],
    calendar_horizon: datetime | None,
    include_context_hash: bool = True,
    allow_downstream_shift: bool = False,
) -> dict[str, Any]:
    previous = lane[target_index - 1] if target_index > 0 else None
    next_task = lane[target_index] if target_index < len(lane) else None
    transition = _transition_snapshot(previous, next_task, order, machine, rules)
    time_constraint, estimate = _time_window_constraint(
        version,
        order,
        machine,
        previous,
        next_task,
        planned_qty,
        transition,
        rules,
        plan_base=plan_base,
        machine_available_at=machine_available_at,
        parsed_windows=parsed_windows,
        calendar_horizon=calendar_horizon,
        allow_downstream_shift=allow_downstream_shift,
    )
    constraints = [
        dict(item)
        for item in base_constraints
        if item["code"] != "transition_data"
    ]
    constraints.extend(
        [
            _gap_transition_data_constraint(order, previous, next_task),
            time_constraint,
        ]
    )
    if (
        any(item["status"] == "unknown" for item in constraints)
        and not bool(
            rules.get("allow_missing_data_in_draft_with_manual_confirmation")
        )
    ):
        constraints.append(
            _constraint(
                "missing_data_policy",
                "fail",
                "当前版本规则禁止将未知硬约束保存到草稿。",
                {
                    "allow_missing_data_in_draft_with_manual_confirmation": False,
                },
            )
        )
    statuses = {item["status"] for item in constraints}
    status = (
        "blocked"
        if "fail" in statuses
        else "manual_review"
        if "unknown" in statuses
        else "eligible"
    )
    score = (
        None
        if status == "blocked"
        else _score_candidate(
            status=status,
            order=order,
            mold=mold,
            machine=machine,
            previous=previous,
            next_task=next_task,
            transition=transition,
            estimate=estimate,
            rules=rules,
            machine_load_hours=machine_load_hours,
            maximum_load_hours=maximum_load_hours,
            existing_order_machine_ids=existing_order_machine_ids,
        )
    )
    context_hash = (
        _candidate_context_hash(
            factory_id=factory_id,
            version=version,
            context_version_revision=context_version_revision,
            order=order,
            mold=mold,
            machine=machine,
            lane=lane,
            target_index=target_index,
            planned_qty=planned_qty,
            rule_hash=rule_hash,
            rule_config_revision=rule_config_revision,
            constraints=constraints,
            score=score,
        )
        if include_context_hash
        else ""
    )
    return {
        "rank": None,
        "advisory_rank": None,
        "machine_id": machine.id,
        "machine_code": machine.machine_code,
        "machine_name": machine.machine_name,
        "target_index": target_index,
        "status": status,
        "eligible": status == "eligible",
        "requires_manual_confirmation": status == "manual_review",
        "auto_publish_allowed": status == "eligible",
        "hard_constraints": constraints,
        "score": score,
        "recommendation_context_hash": context_hash,
    }


def _gap_transition_data_constraint(
    order: InjectionOrderMaster,
    previous: InjectionScheduleTask | None,
    next_task: InjectionScheduleTask | None,
) -> dict[str, Any]:
    missing: list[dict[str, str]] = []
    for field_name, value in (
        ("mold_code", order.mold_code),
        ("color", canonical_color_key(order.pigment, order.color)),
        ("material", order.material),
    ):
        if not _known_transition_value(value):
            missing.append(
                {
                    "role": "target",
                    "task_id": "",
                    "field": field_name,
                }
            )
    for role, task in (("previous", previous), ("next", next_task)):
        if task is None:
            continue
        for field_name, value in (
            ("mold_code_snapshot", task.mold_code_snapshot),
            ("color_snapshot", task.color_snapshot),
            ("material_snapshot", task.material_snapshot),
        ):
            if not _known_transition_value(value):
                missing.append(
                    {
                        "role": role,
                        "task_id": task.id,
                        "field": field_name,
                    }
                )
    return _constraint(
        "transition_data",
        "unknown" if missing else "pass",
        "参与相邻换型计算的任务快照存在缺失，不能自动采用该候选。"
        if missing
        else "当前订单及前后相邻任务的换模、颜色与材料快照齐全。",
        {"missing": missing},
    )


def _validate_mold_thickness(
    machine: InjectionMachineMaster,
    mold: InjectionMoldMaster,
) -> dict[str, Any]:
    if (
        mold.mold_thickness_mm is None
        or machine.mold_thickness_min_mm is None
        or machine.mold_thickness_max_mm is None
    ):
        return _constraint(
            "mold_thickness",
            "unknown",
            "缺少模厚或机台模厚范围资料。",
            {
                "mold_thickness_mm": mold.mold_thickness_mm,
                "machine_min_mm": machine.mold_thickness_min_mm,
                "machine_max_mm": machine.mold_thickness_max_mm,
            },
        )
    fits = (
        machine.mold_thickness_min_mm
        <= mold.mold_thickness_mm
        <= machine.mold_thickness_max_mm
    )
    return _constraint(
        "mold_thickness",
        "pass" if fits else "fail",
        "模厚在机台允许范围内。" if fits else "模厚超出机台允许范围。",
        {
            "mold_thickness_mm": mold.mold_thickness_mm,
            "machine_min_mm": machine.mold_thickness_min_mm,
            "machine_max_mm": machine.mold_thickness_max_mm,
        },
    )


def _validate_opening_stroke(
    machine: InjectionMachineMaster,
    mold: InjectionMoldMaster,
) -> dict[str, Any]:
    if (
        mold.required_opening_stroke_mm is None
        or machine.opening_stroke_mm is None
    ):
        return _constraint(
            "opening_stroke",
            "unknown",
            "缺少模具所需或机台可用开模行程。",
            {
                "required_mm": mold.required_opening_stroke_mm,
                "machine_mm": machine.opening_stroke_mm,
            },
        )
    fits = mold.required_opening_stroke_mm <= machine.opening_stroke_mm
    return _constraint(
        "opening_stroke",
        "pass" if fits else "fail",
        "机台开模行程满足要求。" if fits else "机台开模行程不足。",
        {
            "required_mm": mold.required_opening_stroke_mm,
            "machine_mm": machine.opening_stroke_mm,
        },
    )


def _validate_screw(
    machine: InjectionMachineMaster,
    mold: InjectionMoldMaster,
    order: InjectionOrderMaster,
) -> dict[str, Any]:
    required = normalize_key(mold.required_screw_type)
    material = normalize_key(order.material)
    if not material:
        return _constraint(
            "screw_compatibility",
            "unknown",
            "订单缺少材料资料，无法判断螺杆要求。",
            {"machine_screw_type": machine.screw_type},
        )
    if not required:
        if any(token in material for token in ("PVC", "PC", "合金")):
            return _constraint(
                "screw_compatibility",
                "unknown",
                "特殊材料未声明所需螺杆类型。",
                {"material": order.material, "machine_screw_type": machine.screw_type},
            )
        return _constraint(
            "screw_compatibility",
            "pass",
            "模具未声明特殊螺杆要求。",
            {"material": order.material},
        )
    actual = normalize_key(machine.screw_type)
    if not actual:
        return _constraint(
            "screw_compatibility",
            "unknown",
            "机台缺少螺杆类型资料。",
            {"required": mold.required_screw_type},
        )
    fits = required in actual or actual in required
    return _constraint(
        "screw_compatibility",
        "pass" if fits else "fail",
        "机台螺杆满足材料要求。" if fits else "机台螺杆不满足材料要求。",
        {"required": mold.required_screw_type, "actual": machine.screw_type},
    )


def _transition_snapshot(
    previous: InjectionScheduleTask | None,
    next_task: InjectionScheduleTask | None,
    order: InjectionOrderMaster,
    machine: InjectionMachineMaster,
    rules: dict[str, Any],
) -> dict[str, Any]:
    target_color_key = canonical_color_key(order.pigment, order.color)
    before = (
        calculate_transition_setup(
            from_mold_code=previous.mold_code_snapshot,
            from_color=previous.color_snapshot,
            from_color_rank=previous.color_rank_snapshot,
            from_material=previous.material_snapshot,
            to_mold_code=order.mold_code,
            to_color=target_color_key,
            to_color_rank=order.color_rank,
            to_material=order.material,
            machine_class=machine.machine_class,
            rules=rules,
        )
        if previous is not None
        else _empty_transition_edge("first_task")
    )
    after = (
        calculate_transition_setup(
            from_mold_code=order.mold_code,
            from_color=target_color_key,
            from_color_rank=order.color_rank,
            from_material=order.material,
            to_mold_code=next_task.mold_code_snapshot,
            to_color=next_task.color_snapshot,
            to_color_rank=next_task.color_rank_snapshot,
            to_material=next_task.material_snapshot,
            machine_class=machine.machine_class,
            rules=rules,
        )
        if next_task is not None
        else _empty_transition_edge("last_task")
    )
    replaced = (
        calculate_transition_setup(
            from_mold_code=previous.mold_code_snapshot,
            from_color=previous.color_snapshot,
            from_color_rank=previous.color_rank_snapshot,
            from_material=previous.material_snapshot,
            to_mold_code=next_task.mold_code_snapshot,
            to_color=next_task.color_snapshot,
            to_color_rank=next_task.color_rank_snapshot,
            to_material=next_task.material_snapshot,
            machine_class=machine.machine_class,
            rules=rules,
        )
        if previous is not None and next_task is not None
        else _empty_transition_edge("none")
    )
    return {
        "previous_task_id": previous.id if previous is not None else "",
        "next_task_id": next_task.id if next_task is not None else "",
        "previous_mold_code": previous.mold_code_snapshot
        if previous is not None
        else "",
        "next_mold_code": next_task.mold_code_snapshot
        if next_task is not None
        else "",
        "previous_color": previous.color_snapshot if previous is not None else "",
        "previous_color_rank": (
            previous.color_rank_snapshot if previous is not None else None
        ),
        "target_color": target_color_key,
        "target_color_rank": order.color_rank,
        "next_color": next_task.color_snapshot if next_task is not None else "",
        "next_color_rank": (
            next_task.color_rank_snapshot if next_task is not None else None
        ),
        "previous_material": previous.material_snapshot if previous is not None else "",
        "next_material": next_task.material_snapshot if next_task is not None else "",
        "same_mold": bool(before["same_mold"] or after["same_mold"]),
        "color_minutes": before["color_minutes"],
        "material_minutes": before["material_minutes"],
        "after_color_minutes": after["color_minutes"],
        "after_material_minutes": after["material_minutes"],
        "replaced_color_minutes": replaced["color_minutes"],
        "replaced_material_minutes": replaced["material_minutes"],
        "setup_minutes_before": before["setup_minutes"],
        "setup_minutes_after": after["setup_minutes"],
        "replaced_setup_minutes": replaced["setup_minutes"],
        "setup_minutes_delta": round(
            before["setup_minutes"]
            + after["setup_minutes"]
            - replaced["setup_minutes"],
            3,
        ),
        "color_matrix_match": before["color_matrix_match"],
        "material_matrix_match": before["material_matrix_match"],
        "after_color_matrix_match": after["color_matrix_match"],
        "after_material_matrix_match": after["material_matrix_match"],
        "replaced_color_matrix_match": replaced["color_matrix_match"],
        "replaced_material_matrix_match": replaced["material_matrix_match"],
    }


def _empty_transition_edge(match: str) -> dict[str, Any]:
    return {
        "same_mold": False,
        "mold_minutes": 0.0,
        "color_minutes": 0.0,
        "material_minutes": 0.0,
        "setup_minutes": 0.0,
        "color_matrix_match": match,
        "material_matrix_match": match,
    }


def _time_window_constraint(
    version: InjectionScheduleVersion,
    order: InjectionOrderMaster,
    machine: InjectionMachineMaster,
    previous: InjectionScheduleTask | None,
    next_task: InjectionScheduleTask | None,
    planned_qty: float,
    transition: dict[str, Any],
    rules: dict[str, Any],
    *,
    plan_base: datetime,
    machine_available_at: datetime | None,
    parsed_windows: list[tuple[datetime, datetime, str]],
    calendar_horizon: datetime | None,
    allow_downstream_shift: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cursor = plan_base
    unknown_reasons: list[str] = []
    if machine.available_at and machine_available_at is None:
        unknown_reasons.append("机台可用时间格式无效")
    elif machine_available_at is not None:
        cursor = max(cursor, machine_available_at)
    if previous is not None:
        previous_finish = parse_business_timestamp(previous.planned_finish_at)
        if previous_finish is None:
            unknown_reasons.append("相邻前序任务缺少完成时间")
        else:
            cursor = max(cursor, previous_finish)

    duration_hours = (
        planned_qty / order.daily_target_qty * 24
        if order.daily_target_qty
        else max(float(rules["minimum_task_hours"]), 24.0)
    )
    setup_before = float(transition["setup_minutes_before"])
    skipped: list[dict[str, str]] = []
    skipped_count = 0
    while True:
        production_start = cursor + timedelta(minutes=setup_before)
        finish = production_start + timedelta(hours=duration_hours)
        overlap = next(
            (
                item
                for item in parsed_windows
                if cursor < item[1] and finish > item[0]
            ),
            None,
        )
        if overlap is None:
            break
        cursor = overlap[1]
        skipped_count += 1
        if len(skipped) < 50:
            skipped.append(
                {
                    "start_at": _datetime_text(overlap[0]),
                    "end_at": _datetime_text(overlap[1]),
                    "reason": overlap[2],
                }
            )

    downstream_shift_minutes = 0.0
    fail_reason = ""
    downstream_setup_start: datetime | None = None
    downstream_setup_end: datetime | None = None
    downstream_setup_windows: list[dict[str, str]] = []
    downstream_setup_window_count = 0
    if next_task is not None:
        next_start = parse_business_timestamp(next_task.planned_start_at)
        required_next_start = finish + timedelta(
            minutes=float(transition["setup_minutes_after"])
        )
        if next_start is None:
            unknown_reasons.append("相邻后序任务缺少开始时间")
        elif required_next_start > next_start:
            downstream_shift_minutes = (
                required_next_start - next_start
            ).total_seconds() / 60
            if not allow_downstream_shift:
                fail_reason = (
                    "推荐空档不足，提交后会移动既有后序任务；该能力留待 Phase 4"
                )
        else:
            downstream_setup_start = next_start - timedelta(
                minutes=float(transition["setup_minutes_after"])
            )
            if downstream_setup_start < next_start:
                downstream_setup_end = next_start
                matching_downstream_windows = [
                    (window_start, window_end, reason)
                    for window_start, window_end, reason in parsed_windows
                    if downstream_setup_start < window_end
                    and next_start > window_start
                ]
                downstream_setup_window_count = len(
                    matching_downstream_windows
                )
                downstream_setup_windows = [
                    {
                        "start_at": _datetime_text(window_start),
                        "end_at": _datetime_text(window_end),
                        "reason": reason,
                    }
                    for window_start, window_end, reason
                    in matching_downstream_windows[:50]
                ]
                if downstream_setup_windows:
                    fail_reason = (
                        "插入后当前任务到后序任务的换型占机时间命中停机窗口"
                    )

    if calendar_horizon is None:
        unknown_reasons.append("未配置已核验的停机日历覆盖截止时间")
    elif max(finish, downstream_setup_end or finish) > calendar_horizon:
        unknown_reasons.append(
            "预计生产或后序换型占机时间超出已核验停机日历范围"
        )

    delivery_slack = _delivery_slack_hours(order, finish)
    estimate = {
        "slot_start_at": _datetime_text(cursor),
        "production_start_at": _datetime_text(production_start),
        "finish_at": _datetime_text(finish),
        "duration_hours": round(duration_hours, 3),
        "delivery_slack_hours": round(delivery_slack, 3)
        if delivery_slack is not None
        else None,
        "downstream_shift_minutes": round(downstream_shift_minutes, 3),
        "skipped_unavailable_windows": skipped,
        "skipped_unavailable_window_count": skipped_count,
    }
    details = {
        **estimate,
        "calendar_verified_through": str(
            rules.get("availability_calendar_verified_through", "")
        ),
        "downstream_setup_start_at": (
            _datetime_text(downstream_setup_start)
            if downstream_setup_start is not None
            else ""
        ),
        "downstream_setup_end_at": (
            _datetime_text(downstream_setup_end)
            if downstream_setup_end is not None
            else ""
        ),
        "downstream_setup_unavailable_windows": downstream_setup_windows,
        "downstream_setup_unavailable_window_count": (
            downstream_setup_window_count
        ),
    }
    if fail_reason:
        return _constraint("time_window", "fail", fail_reason, details), estimate
    if unknown_reasons:
        return (
            _constraint(
                "time_window",
                "unknown",
                "；".join(dict.fromkeys(unknown_reasons)),
                details,
            ),
            estimate,
        )
    return (
        _constraint(
            "time_window",
            "pass",
            (
                "候选时段位于已核验日历范围内；其后仅移动无执行屏障的任务后缀。"
                if allow_downstream_shift and downstream_shift_minutes > 0
                else "候选时段位于已核验日历范围内且不占用锁定任务。"
            ),
            details,
        ),
        estimate,
    )


def _compact_append_candidate(
    *,
    order: InjectionOrderMaster,
    mold: InjectionMoldMaster | None,
    machine: InjectionMachineMaster,
    previous: InjectionScheduleTask | None,
    base_constraints: list[dict[str, Any]],
    rules: dict[str, Any],
    planned_qty: float,
    machine_load_hours: float,
    maximum_load_hours: float,
    existing_order_machine_ids: set[str],
    plan_base: datetime,
    machine_available_at: datetime | None,
    parsed_windows: list[tuple[datetime, datetime, str]],
    calendar_horizon: datetime | None,
    max_transition_minutes: float,
    max_color_minutes: float,
    scoring_weights: dict[str, float],
) -> dict[str, Any]:
    """Compact equivalent of an append-only Phase 3 candidate evaluation."""

    statuses = {
        str(item["status"])
        for item in base_constraints
        if item["code"] != "transition_data"
    }
    transition_values = (
        order.mold_code,
        canonical_color_key(order.pigment, order.color),
        order.material,
        previous.mold_code_snapshot if previous is not None else "first",
        previous.color_snapshot if previous is not None else "first",
        previous.material_snapshot if previous is not None else "first",
    )
    if not all(_known_transition_value(value) for value in transition_values):
        statuses.add("unknown")

    cursor = plan_base
    time_unknown = False
    if machine.available_at and machine_available_at is None:
        time_unknown = True
    elif machine_available_at is not None:
        cursor = max(cursor, machine_available_at)
    if previous is not None:
        previous_finish = parse_business_timestamp(
            previous.planned_finish_at
        )
        if previous_finish is None:
            time_unknown = True
        else:
            cursor = max(cursor, previous_finish)

    edge = (
        calculate_transition_setup(
            from_mold_code=previous.mold_code_snapshot,
            from_color=previous.color_snapshot,
            from_color_rank=previous.color_rank_snapshot,
            from_material=previous.material_snapshot,
            to_mold_code=order.mold_code,
            to_color=canonical_color_key(order.pigment, order.color),
            to_color_rank=order.color_rank,
            to_material=order.material,
            machine_class=machine.machine_class,
            rules=rules,
        )
        if previous is not None
        else _empty_transition_edge("first_task")
    )
    duration_hours = (
        planned_qty / order.daily_target_qty * 24
        if order.daily_target_qty
        else max(float(rules["minimum_task_hours"]), 24.0)
    )
    setup_minutes = float(edge["setup_minutes"])
    while True:
        production_start = cursor + timedelta(minutes=setup_minutes)
        finish = production_start + timedelta(hours=duration_hours)
        overlap = next(
            (
                item
                for item in parsed_windows
                if cursor < item[1] and finish > item[0]
            ),
            None,
        )
        if overlap is None:
            break
        cursor = overlap[1]
    if calendar_horizon is None or finish > calendar_horizon:
        time_unknown = True
    if time_unknown:
        statuses.add("unknown")
    if (
        "unknown" in statuses
        and not bool(
            rules.get("allow_missing_data_in_draft_with_manual_confirmation")
        )
    ):
        statuses.add("fail")
    status = (
        "blocked"
        if "fail" in statuses
        else "manual_review"
        if "unknown" in statuses
        else "eligible"
    )
    if status == "blocked":
        return {"status": status, "score_total": float("-inf")}

    slack = _delivery_slack_hours(order, finish)
    due_score = (
        0.0
        if slack is None
        else 1.0
        if slack <= 0
        else _clamp(1 - float(slack) / (30 * 24))
    )
    affinity_score = (
        (
            0.6
            if _known_equal(
                previous.mold_code_snapshot,
                order.mold_code,
            )
            else 0
        )
        + (
            0.25
            if _known_equal(
                previous.material_snapshot,
                order.material,
            )
            else 0
        )
        + (
            0.15
            if _known_equal(
                previous.product_code_snapshot,
                order.product_code,
            )
            else 0
        )
        if previous is not None
        else 0.0
    )
    setup_score = _clamp(
        1
        - max(setup_minutes, 0)
        / (max_transition_minutes * 3)
    )
    color_score = _clamp(
        1
        - float(edge["color_minutes"] or 0)
        / max_color_minutes
    )
    load_score = (
        1.0
        if maximum_load_hours <= 0
        else _clamp(1 - machine_load_hours / maximum_load_hours)
    )
    downstream_score = (
        float(order.downstream_urgency)
        if order.downstream_urgency is not None
        else 1.0
        if normalize_key(order.priority_flag)
        in {"URGENT", "RUSH", "加急", "急", "超期"}
        else 0.0
    )
    exact_parts: list[float] = []
    if mold is not None:
        for required, actual in (
            (mold.machine_class, machine.machine_class),
            (mold.robot_type, machine.robot_type),
            (mold.fixture_type, machine.fixture_type),
        ):
            if required and actual:
                exact_parts.append(
                    1.0
                    if normalize_key(required) == normalize_key(actual)
                    else 0.5
                )
    exact_score = (
        sum(exact_parts) / len(exact_parts)
        if exact_parts
        else 0.0
    )
    split_penalty = (
        1.0
        if existing_order_machine_ids
        and machine.id not in existing_order_machine_ids
        else 0.0
    )
    special_penalty = (
        1.0 if order.special_handling_reason.strip() else 0.0
    )
    raw_scores = {
        "due_date": due_score,
        "sequence_affinity": affinity_score,
        "setup_efficiency": setup_score,
        "color_transition": color_score,
        "load_balance": load_score,
        "downstream_priority": downstream_score,
        "exact_match": exact_score,
        "split_penalty": split_penalty,
        "special_handling_penalty": special_penalty,
    }
    total = sum(
        (
            -scoring_weights[code] * raw_scores[code]
            if code.endswith("_penalty")
            else scoring_weights[code] * raw_scores[code]
        )
        for code in SCORE_LABELS
    )
    return {
        "status": status,
        "score_total": round(total, 3),
    }


def _score_candidate(
    *,
    status: str,
    order: InjectionOrderMaster,
    mold: InjectionMoldMaster | None,
    machine: InjectionMachineMaster,
    previous: InjectionScheduleTask | None,
    next_task: InjectionScheduleTask | None,
    transition: dict[str, Any],
    estimate: dict[str, Any],
    rules: dict[str, Any],
    machine_load_hours: float,
    maximum_load_hours: float,
    existing_order_machine_ids: set[str],
) -> dict[str, Any]:
    weights = rules["scoring_weights"]
    slack = estimate["delivery_slack_hours"]
    due_score = (
        0.0
        if slack is None
        else 1.0
        if slack <= 0
        else _clamp(1 - float(slack) / (30 * 24))
    )
    neighbor_scores = []
    for neighbor in (previous, next_task):
        if neighbor is None:
            continue
        neighbor_scores.append(
            (0.6 if _known_equal(neighbor.mold_code_snapshot, order.mold_code) else 0)
            + (0.25 if _known_equal(neighbor.material_snapshot, order.material) else 0)
            + (0.15 if _known_equal(neighbor.product_code_snapshot, order.product_code) else 0)
        )
    affinity_score = max(neighbor_scores, default=0.0)
    max_transition = max(
        [
            float(item["minutes"])
            for key in ("color_transition_matrix", "material_transition_matrix")
            for item in rules[key]
        ]
        + [
            float(item["mold_change_minutes"])
            for item in rules["setup_minutes"]
        ]
        + [1.0]
    )
    setup_score = _clamp(
        1
        - max(float(transition["setup_minutes_delta"]), 0)
        / (max_transition * 3)
    )
    max_color = max(
        [float(item["minutes"]) for item in rules["color_transition_matrix"]]
        + [1.0]
    )
    color_score = _clamp(
        1 - float(transition["color_minutes"] or 0) / max_color
    )
    load_score = (
        1.0
        if maximum_load_hours <= 0
        else _clamp(1 - machine_load_hours / maximum_load_hours)
    )
    downstream_score = (
        float(order.downstream_urgency)
        if order.downstream_urgency is not None
        else 1.0
        if normalize_key(order.priority_flag)
        in {"URGENT", "RUSH", "加急", "急", "超期"}
        else 0.0
    )
    exact_parts = []
    if mold is not None:
        for required, actual in (
            (mold.machine_class, machine.machine_class),
            (mold.robot_type, machine.robot_type),
            (mold.fixture_type, machine.fixture_type),
        ):
            if required and actual:
                exact_parts.append(
                    1.0 if normalize_key(required) == normalize_key(actual) else 0.5
                )
    exact_score = sum(exact_parts) / len(exact_parts) if exact_parts else 0.0
    split_penalty = (
        1.0
        if existing_order_machine_ids
        and machine.id not in existing_order_machine_ids
        else 0.0
    )
    special_penalty = 1.0 if order.special_handling_reason.strip() else 0.0
    factors = {
        "due_date": (
            due_score,
            f"交期余量 {slack:.1f} 小时。" if slack is not None else "缺少有效交期。",
            False,
        ),
        "sequence_affinity": (
            affinity_score,
            "根据候选空档两侧真实相邻任务的模具、材料和产品计算。",
            False,
        ),
        "setup_efficiency": (
            setup_score,
            f"插入空档的净换型时间变化为 {transition['setup_minutes_delta']:.1f} 分钟。",
            False,
        ),
        "color_transition": (
            color_score,
            f"有向颜色矩阵命中 {transition['color_matrix_match']}，耗时 {transition['color_minutes']} 分钟。",
            False,
        ),
        "load_balance": (
            load_score,
            f"机台已排负载 {machine_load_hours:.1f} 小时。",
            False,
        ),
        "downstream_priority": (
            downstream_score,
            "使用订单下游紧急度快照；缺失时不加分。",
            False,
        ),
        "exact_match": (
            exact_score,
            "比较机型、机械手与夹具的结构化精确程度。",
            False,
        ),
        "split_penalty": (
            split_penalty,
            "订单已在其他机台有任务。" if split_penalty else "不会新增跨机拆单。",
            True,
        ),
        "special_handling_penalty": (
            special_penalty,
            order.special_handling_reason.strip()
            or "订单未标记人工特殊处理。",
            True,
        ),
    }
    breakdown = []
    total = 0.0
    for code in SCORE_LABELS:
        raw, explanation, penalty = factors[code]
        weight = float(weights[code])
        weighted = -weight * raw if penalty else weight * raw
        total += weighted
        breakdown.append(
            {
                "code": code,
                "label": SCORE_LABELS[code],
                "weight": round(weight, 3),
                "raw_score": round(raw, 6),
                "weighted_score": round(weighted, 3),
                "explanation": explanation,
            }
        )
    max_total = sum(
        float(weights[code])
        for code in SCORE_LABELS
        if not code.endswith("_penalty")
    )
    return {
        "total": round(total, 3),
        "max_total": round(max_total, 3),
        "advisory": status == "manual_review",
        "breakdown": breakdown,
        "transition": transition,
        "estimated": estimate,
    }


def _candidate_context_hash(
    *,
    factory_id: str,
    version: InjectionScheduleVersion,
    context_version_revision: int,
    order: InjectionOrderMaster,
    mold: InjectionMoldMaster | None,
    machine: InjectionMachineMaster,
    lane: list[InjectionScheduleTask],
    target_index: int,
    planned_qty: float,
    rule_hash: str,
    rule_config_revision: int,
    constraints: list[dict[str, Any]],
    score: dict[str, Any] | None,
) -> str:
    basis = {
        "factory_id": factory_id,
        "version_id": version.id,
        "version_revision": context_version_revision,
        "order_id": order.id,
        "order_revision": order.revision,
        "mold_id": mold.id if mold is not None else "",
        "mold_revision": mold.revision if mold is not None else 0,
        "machine_id": machine.id,
        "machine_revision": machine.revision,
        "target_index": target_index,
        "planned_qty": round(planned_qty, 6),
        "rule_hash": rule_hash,
        "rule_config_revision": rule_config_revision,
        "lane": [
            {
                "id": task.id,
                "revision": task.revision,
                "sequence_no": task.sequence_no,
                "planned_start_at": task.planned_start_at,
                "planned_finish_at": task.planned_finish_at,
                "locked": bool(task.locked),
                "mold_code": task.mold_code_snapshot,
                "color": task.color_snapshot,
                "color_rank": task.color_rank_snapshot,
                "material": task.material_snapshot,
            }
            for task in lane
        ],
        "constraints": constraints,
        "score": score,
    }
    return sha256(canonical_json(basis).encode("utf-8")).hexdigest()


def _assign_candidate_ranks(candidates: list[dict[str, Any]]) -> None:
    eligible = sorted(
        (item for item in candidates if item["status"] == "eligible"),
        key=lambda item: (
            -float(item["score"]["total"]),
            _natural_key(item["machine_code"]),
            item["machine_id"],
        ),
    )
    for rank, item in enumerate(eligible, 1):
        item["rank"] = rank
    review = sorted(
        (item for item in candidates if item["status"] == "manual_review"),
        key=lambda item: (
            -float(item["score"]["total"]),
            _natural_key(item["machine_code"]),
            item["machine_id"],
        ),
    )
    for rank, item in enumerate(review, 1):
        item["advisory_rank"] = rank


def _candidate_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    status_order = {"eligible": 0, "manual_review": 1, "blocked": 2}
    score = item["score"]["total"] if item["score"] is not None else float("-inf")
    return (
        status_order[item["status"]],
        -float(score),
        _natural_key(item["machine_code"]),
        item["machine_id"],
    )


def _gap_choice_key(item: dict[str, Any]) -> tuple[Any, ...]:
    status_order = {"eligible": 0, "manual_review": 1, "blocked": 2}
    score = item["score"]["total"] if item["score"] is not None else float("-inf")
    return (
        status_order[item["status"]],
        -float(score),
        item["target_index"],
    )


def _natural_key(value: str) -> tuple[Any, ...]:
    return tuple(
        int(part) if part.isdigit() else part.casefold()
        for part in NATURAL_PART_PATTERN.split(value or "")
    )


def _constraint(
    code: str,
    status: str,
    message: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "code": code,
        "status": status,
        "blocking": status != "pass",
        "message": message,
        "details": details,
    }


def _from_validation(value: dict[str, Any]) -> dict[str, Any]:
    return _constraint(
        str(value["constraint_code"]),
        str(value["status"]),
        str(value["message"]),
        json_object(value.get("details_json")),
    )


def _delivery_slack_hours(
    order: InjectionOrderMaster,
    finish: datetime,
) -> float | None:
    try:
        due_date = date.fromisoformat(order.delivery_due_date)
    except (TypeError, ValueError):
        return None
    due = datetime.combine(due_date, time.max, tzinfo=BUSINESS_TIME_ZONE)
    return (
        due
        - finish
        - timedelta(
            hours=order.warehouse_buffer_hours + order.downstream_buffer_hours
        )
    ).total_seconds() / 3600


def _datetime_text(value: datetime) -> str:
    return value.astimezone(BUSINESS_TIME_ZONE).strftime("%Y-%m-%d %H:%M:%S")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _positive_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _known_equal(left: str, right: str) -> bool:
    left_key = normalize_key(left)
    right_key = normalize_key(right)
    return bool(
        _known_transition_value(left)
        and _known_transition_value(right)
        and left_key == right_key
    )


def _known_transition_value(value: str) -> bool:
    return normalize_key(value) not in {"", "UNKNOWN", "未知", "待确认"}

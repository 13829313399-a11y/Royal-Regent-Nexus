import json
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.injection_schedule import (
    InjectionScheduleImportBatch,
    InjectionScheduleImportIssue,
    InjectionScheduleMachine,
    InjectionScheduleTask,
)
from app.schemas.injection_schedule import (
    InjectionScheduleImportIssueOut,
    InjectionScheduleImportPreviewResponse,
    InjectionScheduleImportSummary,
    InjectionScheduleMachineOut,
    InjectionScheduleTaskOut,
)
from app.services.auth import now_text
from app.services.injection_schedule_excel import ParsedDailyScheduleImport, parse_daily_schedule_workbook


def create_daily_schedule_import(
    db: Session,
    content: bytes,
    source_file_name: str,
    factory_id: str,
    created_by: str,
) -> InjectionScheduleImportPreviewResponse:
    parsed = parse_daily_schedule_workbook(content, source_file_name)
    batch_id = f"isb-{uuid4().hex[:12]}"
    batch = InjectionScheduleImportBatch(
        id=batch_id,
        factory_id=factory_id,
        import_type="daily_schedule",
        source_file_name=source_file_name,
        business_date=parsed.summary.business_date,
        status="imported",
        summary_json=json.dumps(parsed.summary_dict(), ensure_ascii=False),
        created_by=created_by,
        created_at=now_text(),
    )
    db.add(batch)

    for index, machine in enumerate(parsed.machines, start=1):
        db.add(
            InjectionScheduleMachine(
                id=f"{batch_id}:machine:{index}",
                batch_id=batch_id,
                factory_id=factory_id,
                machine_code=machine.machine_code,
                workshop=machine.workshop,
                machine_spec_label=machine.machine_spec_label,
                machine_process_type=machine.machine_process_type,
                robot_type=machine.robot_type,
                status=machine.status,
                constraints_json=json.dumps(machine.constraints, ensure_ascii=False),
                source_row=machine.source_row,
            )
        )

    for index, task in enumerate(parsed.tasks, start=1):
        db.add(
            InjectionScheduleTask(
                id=f"{batch_id}:task:{index}",
                batch_id=batch_id,
                factory_id=factory_id,
                source_row=task.source_row,
                assigned_machine_code=task.assigned_machine_code,
                task_bucket=task.task_bucket,
                mold_code=task.mold_code,
                product_name=task.product_name,
                order_no=task.order_no,
                product_code=task.product_code,
                machine_model=task.machine_model,
                color=task.color,
                pigment=task.pigment,
                material=task.material,
                order_qty=task.order_qty,
                produced_qty=task.produced_qty,
                shortage_qty=task.shortage_qty,
                daily_target_qty=task.daily_target_qty,
                delivery_due_date=task.delivery_due_date,
                plan_start_at=task.plan_start_at,
                plan_finish_at=task.plan_finish_at,
                warehouse_due_at=task.warehouse_due_at,
                delivery_gap_days=task.delivery_gap_days,
                priority_flag=task.priority_flag,
                remark=task.remark,
                source_values_json=json.dumps(task.source_values, ensure_ascii=False),
            )
        )

    persist_import_issues(db, batch_id, parsed)
    db.commit()
    return get_import_preview(db, batch_id)


def persist_import_issues(db: Session, batch_id: str, parsed: ParsedDailyScheduleImport) -> None:
    for index, issue in enumerate(parsed.issues, start=1):
        db.add(
            InjectionScheduleImportIssue(
                id=f"{batch_id}:issue:{index}",
                batch_id=batch_id,
                source_row=issue.source_row,
                severity=issue.severity,
                issue_type=issue.issue_type,
                field_name=issue.field_name,
                raw_value=issue.raw_value,
                message=issue.message,
            )
        )


def get_import_preview(db: Session, batch_id: str) -> InjectionScheduleImportPreviewResponse:
    batch = load_batch(db, batch_id)
    machines = list(
        db.scalars(
            select(InjectionScheduleMachine)
            .where(InjectionScheduleMachine.batch_id == batch_id)
            .order_by(InjectionScheduleMachine.source_row)
        ).all()
    )
    tasks = list(
        db.scalars(
            select(InjectionScheduleTask)
            .where(InjectionScheduleTask.batch_id == batch_id)
            .order_by(InjectionScheduleTask.source_row)
        ).all()
    )
    issues = list(
        db.scalars(
            select(InjectionScheduleImportIssue)
            .where(InjectionScheduleImportIssue.batch_id == batch_id)
            .order_by(InjectionScheduleImportIssue.source_row, InjectionScheduleImportIssue.id)
        ).all()
    )

    return InjectionScheduleImportPreviewResponse(
        batch_id=batch.id,
        factory_id=batch.factory_id,
        source_file_name=batch.source_file_name,
        business_date=batch.business_date,
        status=batch.status,
        summary=summary_from_json(batch.summary_json),
        machines=[machine_to_out(machine) for machine in machines],
        tasks=[task_to_out(task) for task in tasks],
        issues=[issue_to_out(issue) for issue in issues],
    )


def get_machine_status(db: Session, batch_id: str) -> list[InjectionScheduleMachineOut]:
    load_batch(db, batch_id)
    machines = db.scalars(
        select(InjectionScheduleMachine)
        .where(InjectionScheduleMachine.batch_id == batch_id)
        .order_by(InjectionScheduleMachine.source_row)
    ).all()
    return [machine_to_out(machine) for machine in machines]


def load_batch(db: Session, batch_id: str) -> InjectionScheduleImportBatch:
    batch = db.get(InjectionScheduleImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="未找到注塑排产导入批次")
    return batch


def summary_from_json(raw_summary: str) -> InjectionScheduleImportSummary:
    try:
        payload = json.loads(raw_summary or "{}")
    except json.JSONDecodeError:
        payload = {}
    return InjectionScheduleImportSummary(**payload)


def machine_to_out(machine: InjectionScheduleMachine) -> InjectionScheduleMachineOut:
    return InjectionScheduleMachineOut(
        id=machine.id,
        batch_id=machine.batch_id,
        factory_id=machine.factory_id,
        machine_code=machine.machine_code,
        workshop=machine.workshop,
        machine_spec_label=machine.machine_spec_label,
        machine_process_type=machine.machine_process_type,
        robot_type=machine.robot_type,
        status=machine.status,
        constraints=parse_json_object(machine.constraints_json),
        source_row=machine.source_row,
    )


def task_to_out(task: InjectionScheduleTask) -> InjectionScheduleTaskOut:
    return InjectionScheduleTaskOut(
        id=task.id,
        batch_id=task.batch_id,
        factory_id=task.factory_id,
        source_row=task.source_row,
        assigned_machine_code=task.assigned_machine_code,
        task_bucket=task.task_bucket,
        mold_code=task.mold_code,
        product_name=task.product_name,
        order_no=task.order_no,
        product_code=task.product_code,
        machine_model=task.machine_model,
        color=task.color,
        pigment=task.pigment,
        material=task.material,
        order_qty=task.order_qty,
        produced_qty=task.produced_qty,
        shortage_qty=task.shortage_qty,
        daily_target_qty=task.daily_target_qty,
        delivery_due_date=task.delivery_due_date,
        plan_start_at=task.plan_start_at,
        plan_finish_at=task.plan_finish_at,
        warehouse_due_at=task.warehouse_due_at,
        delivery_gap_days=task.delivery_gap_days,
        priority_flag=task.priority_flag,
        remark=task.remark,
        source_values=parse_json_object(task.source_values_json),
    )


def issue_to_out(issue: InjectionScheduleImportIssue) -> InjectionScheduleImportIssueOut:
    return InjectionScheduleImportIssueOut(
        id=issue.id,
        batch_id=issue.batch_id,
        source_row=issue.source_row,
        severity=issue.severity,
        issue_type=issue.issue_type,
        field_name=issue.field_name,
        raw_value=issue.raw_value,
        message=issue.message,
    )


def parse_json_object(raw_value: str) -> dict[str, object]:
    try:
        payload = json.loads(raw_value or "{}")
    except json.JSONDecodeError:
        return {}

    return payload if isinstance(payload, dict) else {}

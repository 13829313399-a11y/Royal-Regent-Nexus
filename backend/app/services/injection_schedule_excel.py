import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from io import BytesIO
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.utils.datetime import from_excel


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
OLD_WORKSHOP_PATTERN = re.compile(r"^(旧|老)")
NEW_WORKSHOP_PATTERN = re.compile(r"^新")
HUGE_NEGATIVE_GAP_DAYS = -365


@dataclass(frozen=True)
class ParsedImportSummary:
    machine_count: int
    old_machine_count: int
    new_machine_count: int
    task_count: int
    scheduled_task_count: int
    pending_task_count: int
    relative_task_count: int
    no_plan_task_count: int
    total_shortage_qty: float
    overdue_count: int
    missing_due_count: int
    negative_or_zero_shortage_count: int
    huge_negative_gap_count: int
    external_formula_risk_count: int
    date_axis_days: int
    date_axis_shift_columns: int
    business_date: str


@dataclass(frozen=True)
class ParsedMachine:
    machine_code: str
    workshop: str
    machine_spec_label: str
    machine_process_type: str
    robot_type: str
    status: str
    constraints: dict[str, Any]
    source_row: int


@dataclass(frozen=True)
class ParsedTask:
    source_row: int
    assigned_machine_code: str
    task_bucket: str
    mold_code: str
    product_name: str
    order_no: str
    product_code: str
    machine_model: str
    color: str
    pigment: str
    material: str
    order_qty: float | None
    produced_qty: float | None
    shortage_qty: float | None
    daily_target_qty: float | None
    delivery_due_date: str
    plan_start_at: str
    plan_finish_at: str
    warehouse_due_at: str
    delivery_gap_days: float | None
    priority_flag: str
    remark: str
    source_values: dict[str, Any]


@dataclass(frozen=True)
class ParsedIssue:
    source_row: int
    severity: str
    issue_type: str
    field_name: str
    raw_value: str
    message: str


@dataclass(frozen=True)
class ParsedDailyScheduleImport:
    source_file_name: str
    summary: ParsedImportSummary
    machines: list[ParsedMachine]
    tasks: list[ParsedTask]
    issues: list[ParsedIssue]

    def summary_dict(self) -> dict[str, Any]:
        return asdict(self.summary)


def parse_daily_schedule_workbook(content: bytes, source_file_name: str) -> ParsedDailyScheduleImport:
    workbook = load_workbook(BytesIO(content), data_only=True, read_only=False)
    sheet = workbook["Sheet1"] if "Sheet1" in workbook.sheetnames else workbook.active

    machines: list[ParsedMachine] = []
    tasks: list[ParsedTask] = []
    issues: list[ParsedIssue] = []
    current_machine_code = ""

    max_row = sheet.max_row or 0
    for row_index in range(4, max_row + 1):
        if is_secondary_header(sheet, row_index):
            continue

        if is_empty_data_row(sheet, row_index):
            continue

        if is_machine_row(sheet, row_index):
            machine = parse_machine(sheet, row_index)
            current_machine_code = machine.machine_code
            machines.append(machine)
            continue

        if not is_task_row(sheet, row_index):
            continue

        task = parse_task(sheet, row_index, current_machine_code)
        tasks.append(task)
        issues.extend(build_task_issues(task))

    formula_issues = scan_external_formula_risks(content, max_row)
    issues.extend(formula_issues)

    date_axis_days, date_axis_shift_columns, business_date = summarize_date_axis(sheet)
    scheduled_task_count = sum(1 for task in tasks if task.task_bucket == "scheduled")
    relative_task_count = sum(1 for task in tasks if task.task_bucket == "pending")
    no_plan_task_count = sum(1 for task in tasks if task.task_bucket == "unplanned")
    total_shortage_qty = sum(task.shortage_qty or 0 for task in tasks)
    overdue_count = sum(1 for task in tasks if (task.delivery_gap_days is not None and task.delivery_gap_days < 0))
    negative_or_zero_shortage_count = sum(1 for task in tasks if (task.shortage_qty is not None and task.shortage_qty <= 0))
    huge_negative_gap_count = sum(
        1 for task in tasks if (task.delivery_gap_days is not None and task.delivery_gap_days <= HUGE_NEGATIVE_GAP_DAYS)
    )
    missing_due_count = sum(1 for task in tasks if not task.delivery_due_date)

    summary = ParsedImportSummary(
        machine_count=len(machines),
        old_machine_count=sum(1 for machine in machines if machine.workshop == "old"),
        new_machine_count=sum(1 for machine in machines if machine.workshop == "new"),
        task_count=len(tasks),
        scheduled_task_count=scheduled_task_count,
        pending_task_count=relative_task_count + no_plan_task_count,
        relative_task_count=relative_task_count,
        no_plan_task_count=no_plan_task_count,
        total_shortage_qty=total_shortage_qty,
        overdue_count=overdue_count,
        missing_due_count=missing_due_count,
        negative_or_zero_shortage_count=negative_or_zero_shortage_count,
        huge_negative_gap_count=huge_negative_gap_count,
        external_formula_risk_count=len(formula_issues),
        date_axis_days=date_axis_days,
        date_axis_shift_columns=date_axis_shift_columns,
        business_date=business_date,
    )

    return ParsedDailyScheduleImport(
        source_file_name=source_file_name,
        summary=summary,
        machines=machines,
        tasks=tasks,
        issues=issues,
    )


def is_empty_data_row(sheet, row_index: int) -> bool:
    return all(is_blank(sheet.cell(row_index, column_index).value) for column_index in range(2, 16))


def is_secondary_header(sheet, row_index: int) -> bool:
    return text(sheet.cell(row_index, 7).value) == "工模" and text(sheet.cell(row_index, 8).value) == "名称"


def is_machine_row(sheet, row_index: int) -> bool:
    machine_code = text(sheet.cell(row_index, 2).value) or text(sheet.cell(row_index, 1).value)
    spec = text(sheet.cell(row_index, 7).value)
    process_type = text(sheet.cell(row_index, 8).value)
    robot_type = text(sheet.cell(row_index, 9).value)
    quantity_values = [sheet.cell(row_index, column_index).value for column_index in range(11, 16)]

    return bool(machine_code and spec and process_type and robot_type and all(coerce_number(value) is None for value in quantity_values))


def parse_machine(sheet, row_index: int) -> ParsedMachine:
    machine_code = text(sheet.cell(row_index, 2).value) or text(sheet.cell(row_index, 1).value)
    remark = text(sheet.cell(row_index, 10).value)
    return ParsedMachine(
        machine_code=machine_code,
        workshop=classify_workshop(machine_code),
        machine_spec_label=text(sheet.cell(row_index, 7).value),
        machine_process_type=text(sheet.cell(row_index, 8).value),
        robot_type=text(sheet.cell(row_index, 9).value),
        status="available",
        constraints={"remark": remark} if remark else {},
        source_row=row_index,
    )


def classify_workshop(machine_code: str) -> str:
    if OLD_WORKSHOP_PATTERN.search(machine_code):
        return "old"
    if NEW_WORKSHOP_PATTERN.search(machine_code):
        return "new"
    return "unknown"


def is_task_row(sheet, row_index: int) -> bool:
    core_values = [sheet.cell(row_index, column_index).value for column_index in range(7, 11)]
    quantity_values = [sheet.cell(row_index, column_index).value for column_index in range(11, 16)]
    has_core = sum(0 if is_blank(value) else 1 for value in core_values) >= 3
    has_quantity = any(coerce_number(value) is not None for value in quantity_values)
    return has_core and has_quantity


def parse_task(sheet, row_index: int, current_machine_code: str) -> ParsedTask:
    assigned_machine_code = text(sheet.cell(row_index, 2).value) or current_machine_code
    plan_start_value = sheet.cell(row_index, 33).value
    plan_finish_value = sheet.cell(row_index, 34).value
    task_bucket = classify_task_bucket(plan_start_value, plan_finish_value)
    shortage_qty = coerce_number(sheet.cell(row_index, 14).value)
    delivery_gap_days = coerce_number(sheet.cell(row_index, 37).value)
    priority_flag = text(sheet.cell(row_index, 5).value)
    remark = text(sheet.cell(row_index, 49).value)

    return ParsedTask(
        source_row=row_index,
        assigned_machine_code=assigned_machine_code,
        task_bucket=task_bucket,
        mold_code=text(sheet.cell(row_index, 7).value),
        product_name=text(sheet.cell(row_index, 8).value),
        order_no=text(sheet.cell(row_index, 9).value),
        product_code=text(sheet.cell(row_index, 10).value),
        machine_model=text(sheet.cell(row_index, 6).value),
        color=text(sheet.cell(row_index, 17).value),
        pigment=text(sheet.cell(row_index, 18).value),
        material=text(sheet.cell(row_index, 19).value),
        order_qty=coerce_number(sheet.cell(row_index, 12).value),
        produced_qty=coerce_number(sheet.cell(row_index, 13).value),
        shortage_qty=shortage_qty,
        daily_target_qty=coerce_number(sheet.cell(row_index, 15).value),
        delivery_due_date=stringify_date_value(sheet.cell(row_index, 28).value),
        plan_start_at=stringify_date_value(plan_start_value),
        plan_finish_at=stringify_date_value(plan_finish_value),
        warehouse_due_at=stringify_date_value(sheet.cell(row_index, 36).value),
        delivery_gap_days=delivery_gap_days,
        priority_flag=priority_flag,
        remark=remark,
        source_values={
            "quantity_set": coerce_number(sheet.cell(row_index, 11).value),
            "transfer_mold_reference": stringify_date_value(sheet.cell(row_index, 29).value),
            "priority_flag": priority_flag,
        },
    )


def classify_task_bucket(plan_start_value: Any, plan_finish_value: Any) -> str:
    plan_values = [value for value in [plan_start_value, plan_finish_value] if not is_blank(value)]
    if not plan_values:
        return "unplanned"
    if any(is_real_plan_value(value) for value in plan_values):
        return "scheduled"
    if any(is_relative_plan_datetime_value(value) for value in plan_values):
        return "pending"
    return "unplanned"


def is_real_plan_value(value: Any) -> bool:
    normalized = normalize_datetime_value(value)
    return isinstance(normalized, datetime) and normalized.year >= 2025


def is_relative_plan_datetime_value(value: Any) -> bool:
    normalized = normalize_datetime_value(value)
    if not isinstance(normalized, datetime):
        return False
    return normalized.year < 2025


def normalize_datetime_value(value: Any) -> datetime | time | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        try:
            return from_excel(value)
        except (TypeError, ValueError):
            return None
    return None


def build_task_issues(task: ParsedTask) -> list[ParsedIssue]:
    issues: list[ParsedIssue] = []
    if task.task_bucket == "pending":
        issues.append(
            ParsedIssue(
                source_row=task.source_row,
                severity="info",
                issue_type="relative_plan_time",
                field_name="AG/AH",
                raw_value=f"{task.plan_start_at} / {task.plan_finish_at}",
                message="计划生产期为 1900 相对时间或纯时间，先进入待排池，不按真实日期发布。",
            )
        )
    if task.task_bucket == "unplanned":
        issues.append(
            ParsedIssue(
                source_row=task.source_row,
                severity="warning",
                issue_type="no_plan_time",
                field_name="AG/AH",
                raw_value="",
                message="计划生产期为空，先进入待排池。",
            )
        )
    if not task.delivery_due_date:
        issues.append(
            ParsedIssue(
                source_row=task.source_row,
                severity="error",
                issue_type="missing_due_date",
                field_name="AB",
                raw_value="",
                message="缺少交货完成期，不能自动发布到正式排期。",
            )
        )
    if task.shortage_qty is not None and task.shortage_qty <= 0:
        issues.append(
            ParsedIssue(
                source_row=task.source_row,
                severity="info",
                issue_type="negative_or_zero_shortage",
                field_name="N",
                raw_value=format_number(task.shortage_qty),
                message="欠数小于或等于 0，需要确认是否已经完工或数据回写未清理。",
            )
        )
    if task.delivery_gap_days is not None and task.delivery_gap_days <= HUGE_NEGATIVE_GAP_DAYS:
        issues.append(
            ParsedIssue(
                source_row=task.source_row,
                severity="warning",
                issue_type="huge_negative_delivery_gap",
                field_name="AK",
                raw_value=format_number(task.delivery_gap_days),
                message="交期差为巨大负数，需人工核对日期公式或交期来源。",
            )
        )

    return issues


def scan_external_formula_risks(content: bytes, max_row: int) -> list[ParsedIssue]:
    workbook = load_workbook(BytesIO(content), data_only=False, read_only=False)
    sheet = workbook["Sheet1"] if "Sheet1" in workbook.sheetnames else workbook.active
    issues: list[ParsedIssue] = []
    scan_row_count = min(max_row or 0, sheet.max_row or 0)

    for row_index in range(1, scan_row_count + 1):
        for column_index in range(1, 51):
            value = sheet.cell(row_index, column_index).value
            if not (isinstance(value, str) and value.startswith("=")):
                continue
            if "[" not in value and ".xls" not in value.lower():
                continue

            issues.append(
                ParsedIssue(
                    source_row=row_index,
                    severity="warning",
                    issue_type="external_formula_reference",
                    field_name=get_column_letter(column_index),
                    raw_value=value[:200],
                    message="检测到外部工作簿公式引用，导入值需要以 Excel 当前缓存值为准并人工复核。",
                )
            )
            if len(issues) >= 50:
                return issues

    return issues


def summarize_date_axis(sheet) -> tuple[int, int, str]:
    start_column = column_index_from_string("BA")
    end_column = column_index_from_string("GOP")
    unique_dates: list[str] = []
    shift_columns = 0

    for column_index in range(start_column, end_column + 1):
        date_value = stringify_date_value(sheet.cell(2, column_index).value)
        shift_value = text(sheet.cell(3, column_index).value)
        if date_value and date_value not in unique_dates:
            unique_dates.append(date_value)
        if shift_value:
            shift_columns += 1

    return len(unique_dates), shift_columns, unique_dates[0] if unique_dates else ""


def stringify_date_value(value: Any) -> str:
    if is_blank(value):
        return ""
    if isinstance(value, datetime):
        if value.time() == time.min:
            return value.date().isoformat()
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        normalized = normalize_datetime_value(value)
        if isinstance(normalized, time):
            return normalized.strftime("%H:%M:%S")
        if isinstance(normalized, datetime):
            if normalized.time() == time.min:
                return normalized.date().isoformat()
            return normalized.strftime("%Y-%m-%d %H:%M:%S")
    return text(value)


def coerce_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def format_number(value: float) -> str:
    return str(int(value)) if value == int(value) else str(value)


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value).strip()

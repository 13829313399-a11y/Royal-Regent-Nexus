from datetime import datetime, time
from io import BytesIO

from openpyxl import Workbook


def build_daily_schedule_workbook() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"

    headers = {
        "B": "机号",
        "G": "工模",
        "H": "名称",
        "I": "单号",
        "J": "货号",
        "K": "数量(套)",
        "L": "订单数",
        "M": "已啤数",
        "N": "欠数",
        "O": "计划目标",
        "AB": "交货\n完成期",
        "AG": "计划生产期",
        "AH": "计划完成期",
        "AJ": "入库期",
        "AK": "交期差",
    }
    for column, label in headers.items():
        sheet[f"{column}3"] = label

    sheet["BA2"] = datetime(2026, 6, 30)
    sheet["BB2"] = datetime(2026, 6, 30)
    sheet["BA3"] = "白班"
    sheet["BB3"] = "夜班"

    sheet["B4"] = "旧1"
    sheet["G4"] = "50A 400T"
    sheet["H4"] = "普通"
    sheet["I4"] = "双臂五轴"

    sheet["G5"] = "SE-20230217-01"
    sheet["H5"] = "脚骨左右上下盖"
    sheet["I5"] = "FBE202500189"
    sheet["J5"] = "W86255"
    sheet["K5"] = 2200
    sheet["L5"] = 2200
    sheet["M5"] = 2280
    sheet["N5"] = -80
    sheet["O5"] = 2500
    sheet["AB5"] = datetime(2026, 7, 1)
    sheet["AG5"] = datetime(2026, 6, 30, 8, 30)
    sheet["AH5"] = datetime(2026, 6, 30, 17, 30)
    sheet["AJ5"] = datetime(2026, 7, 4)
    sheet["AK5"] = 5

    sheet["B6"] = "新1"
    sheet["G6"] = "60A 500T"
    sheet["H6"] = "高速"
    sheet["I6"] = "双臂五轴"

    sheet["G7"] = "20 375 7002-009"
    sheet["H7"] = "皮卡车车窗/引擎座"
    sheet["I7"] = "BJB251160"
    sheet["J7"] = "20 375 7005"
    sheet["K7"] = 4000
    sheet["L7"] = 4000
    sheet["M7"] = 0
    sheet["N7"] = 4000
    sheet["O7"] = 2800
    sheet["AB7"] = datetime(2026, 7, 10)
    sheet["AG7"] = time(4, 42, 39)
    sheet["AH7"] = datetime(1900, 1, 1, 4, 42, 39)
    sheet["AK7"] = -12

    sheet["A111"] = "机位"
    sheet["B111"] = "机号"
    sheet["G111"] = "工模"
    sheet["H111"] = "名称"
    sheet["I111"] = "单号"
    sheet["J111"] = "货号"
    sheet["K111"] = "数量(套)"

    sheet["G112"] = "BBT 36100-01"
    sheet["H112"] = "枪身"
    sheet["I112"] = "BJB251262"
    sheet["J112"] = "36100"
    sheet["K112"] = 1500
    sheet["L112"] = 1500
    sheet["M112"] = 0
    sheet["N112"] = 1500
    sheet["O112"] = 700
    sheet["AB112"] = None
    sheet["AG112"] = None
    sheet["AH112"] = None
    sheet["AK112"] = -12345

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_parse_daily_schedule_workbook_classifies_real_relative_and_unplanned_tasks():
    from app.services.injection_schedule_excel import parse_daily_schedule_workbook

    parsed = parse_daily_schedule_workbook(build_daily_schedule_workbook(), "fixture.xlsx")

    assert parsed.summary.machine_count == 2
    assert parsed.summary.old_machine_count == 1
    assert parsed.summary.new_machine_count == 1
    assert parsed.summary.task_count == 3
    assert parsed.summary.scheduled_task_count == 1
    assert parsed.summary.relative_task_count == 1
    assert parsed.summary.no_plan_task_count == 1
    assert parsed.summary.pending_task_count == 2
    assert parsed.summary.total_shortage_qty == 5420
    assert parsed.summary.overdue_count == 2
    assert parsed.summary.missing_due_count == 1
    assert parsed.summary.negative_or_zero_shortage_count == 1
    assert parsed.summary.huge_negative_gap_count == 1
    assert parsed.summary.date_axis_days == 1
    assert parsed.summary.date_axis_shift_columns == 2

    assert [machine.machine_code for machine in parsed.machines] == ["旧1", "新1"]
    assert parsed.tasks[0].assigned_machine_code == "旧1"
    assert parsed.tasks[1].task_bucket == "pending"
    assert parsed.tasks[2].task_bucket == "unplanned"
    assert any(issue.issue_type == "relative_plan_time" for issue in parsed.issues)
    assert any(issue.issue_type == "missing_due_date" for issue in parsed.issues)

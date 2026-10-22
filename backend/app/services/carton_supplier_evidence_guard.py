"""Freeze confirmed supplier evidence periods independently of payable dates.

Callers hold the shared factory lock and check successful request replays first.
Reopening keeps the old confirmed version and permits a new bilateral review;
this guard never moves stock, recalculates money or changes a settlement.
"""
from datetime import date
import re
from fastapi import HTTPException


def _period(value):
    text = value.isoformat() if isinstance(value, date) else value
    try:
        if not isinstance(text, str):
            raise ValueError()
        if re.fullmatch(r"\d{4}-\d{2}", text):
            day = date.fromisoformat(text + "-01")
        else:
            day = date.fromisoformat(text)
            if day.isoformat() != text:
                raise ValueError()
        return f"{day.year:04d}-{day.month:02d}"
    except (ValueError, TypeError):
        raise HTTPException(422, "原送货或验收日期缺失、无效，无法核实已确认月份；请先核实原凭证")


def ensure_evidence_open(db, factory, supplier, *dates):
    from app.services.carton_supplier_settlement import ensure_open

    if not dates:
        raise HTTPException(422, "缺少原送货或验收日期，无法核实已确认月份")
    for period in sorted({_period(value) for value in dates}):
        try:
            ensure_open(db, factory, supplier, period)
        except HTTPException as error:
            if error.status_code != 409:
                raise
            raise HTTPException(409, f"该供应商 {period} 月份已确认对账；补录或更正原送货、验收证据前，"
                "请由内部填写原因重开该月，补证后由供应商和内部重新确认；不会自动调整金额") from error

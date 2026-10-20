"""Date-only placement rules for Huakang A 360; never shipment/completion events."""
from datetime import date, datetime, timedelta, timezone
import re


def shanghai_today() -> date:
    # Fixed UTC+8 also works in the bundled Windows runtime without a tzdata install.
    return datetime.now(timezone(timedelta(hours=8))).date()


def parse_inspection_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None  # Excel serials need the workbook's own date epoch.
    text = value.strip()
    match = re.fullmatch(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    try:
        if match:
            return date(*(int(part) for part in match.groups()))
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?", text):
            return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    return None


def inspection_date_from_data(data: dict) -> tuple[date | None, str]:
    # Existing migration and PO representations of the same inspection date.
    # FCD/requested_ship_date are deliberately absent: no shipping-date fallback.
    values = [data.get(key) for key in ("inspection_date", "line_q", "planned_inspection_date", "customer_q")]
    values = [value for value in values if value is not None and str(value).strip()]
    dates = [parse_inspection_date(value) for value in values]
    if any(value is None for value in dates):
        return None, "验货日期不明确，保留在未完成中待核对"
    unique = set(dates)
    if len(unique) > 1:
        return None, "已有验货日期不一致，保留在未完成中待核对"
    return (next(iter(unique)), "") if unique else (None, "验货日期为空，保留在未完成中")


def natural_key(value: str):
    return tuple((1, int(part)) if part.isdigit() else (0, part.casefold())
                 for part in re.split(r"(\d+)", value or ""))

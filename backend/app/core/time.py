from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo


BUSINESS_TIME_ZONE_NAME = "Asia/Shanghai"
BUSINESS_TIME_ZONE = ZoneInfo(BUSINESS_TIME_ZONE_NAME)


def business_now() -> datetime:
    """Return the authoritative current business time."""

    return datetime.now(BUSINESS_TIME_ZONE)


def business_today() -> str:
    return business_now().date().isoformat()


def parse_business_timestamp(value: str | None) -> datetime | None:
    """Parse a persisted timestamp and normalize it to the business timezone.

    Legacy timestamps without an offset were written as local wall-clock values,
    so they remain interpreted as Asia/Shanghai. Explicit ``Z``/offset values are
    treated as instants and converted to Asia/Shanghai.
    """

    text = str(value or "").strip()
    if not text:
        return None

    normalized = f"{text[:-1]}+00:00" if text.endswith(("Z", "z")) else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BUSINESS_TIME_ZONE)
    return parsed.astimezone(BUSINESS_TIME_ZONE)


def business_date_from_timestamp(value: str | None) -> str | None:
    parsed = parse_business_timestamp(value)
    return parsed.date().isoformat() if parsed is not None else None


def serialize_process_local_timestamp(
    value: str | None,
    *,
    source_timezone: tzinfo | None = None,
) -> str:
    """Attach the producing process timezone to a legacy wall-clock value.

    Auth/system timestamps are persisted as timezone-less strings. Keeping the
    stored value unchanged avoids invalidating sessions, while adding the
    process offset at the API boundary lets browsers convert the instant to the
    fixed business timezone correctly. Explicit offsets are preserved.
    """

    text = str(value or "").strip()
    if not text:
        return ""

    normalized = f"{text[:-1]}+00:00" if text.endswith(("Z", "z")) else text.replace(" ", "T", 1)
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return text

    if parsed.tzinfo is None:
        local_timezone = source_timezone or datetime.now().astimezone().tzinfo or timezone.utc
        parsed = parsed.replace(tzinfo=local_timezone)

    return parsed.isoformat(timespec="microseconds" if parsed.microsecond else "seconds")

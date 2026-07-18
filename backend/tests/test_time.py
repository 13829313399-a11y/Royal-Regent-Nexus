from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.time import (
    business_date_from_timestamp,
    parse_business_timestamp,
    serialize_process_local_timestamp,
)


def test_business_timestamp_normalizes_explicit_utc_and_preserves_legacy_business_time():
    explicit_utc = parse_business_timestamp("2026-07-18T16:30:00Z")
    legacy_business = parse_business_timestamp("2026-07-19 00:30:00")

    assert explicit_utc is not None
    assert legacy_business is not None
    assert explicit_utc == legacy_business
    assert business_date_from_timestamp("2026-07-18T16:30:00Z") == "2026-07-19"


def test_process_local_timestamp_adds_source_offset_without_changing_wall_clock():
    source_timezone = timezone(timedelta(hours=-5))
    serialized = serialize_process_local_timestamp(
        "2026-07-18 08:03:04.123456",
        source_timezone=source_timezone,
    )
    parsed = datetime.fromisoformat(serialized)

    assert serialized == "2026-07-18T08:03:04.123456-05:00"
    assert parsed.utcoffset() == timedelta(hours=-5)


def test_process_local_timestamp_preserves_explicit_offset_and_invalid_legacy_value():
    assert serialize_process_local_timestamp("2026-07-18T08:03:04Z") == "2026-07-18T08:03:04+00:00"
    assert serialize_process_local_timestamp("not-a-date") == "not-a-date"
    assert serialize_process_local_timestamp("") == ""

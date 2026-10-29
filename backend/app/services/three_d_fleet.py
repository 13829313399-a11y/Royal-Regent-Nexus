"""Machine numbers configured for this factory, including a partially prepared fleet."""

from datetime import datetime, time

from sqlalchemy import select

from app.core.config import settings
from app.core.time import BUSINESS_TIME_ZONE

from app.models import three_d_printing as m


def machine_numbers(db):
    setting = db.get(m.ThreeDPrintingSetting, "huakang-a")
    numbers = set(range(1, setting.machine_count + 1)) if setting else set()
    numbers.update(db.scalars(select(m.ThreeDPrintingPrinter.machine_no).where(
        m.ThreeDPrintingPrinter.factory_id == "huakang-a",
    )))
    return sorted(numbers)


def numbering_start():
    cutoff = settings.three_d_record_numbering_since
    return datetime.combine(cutoff, time.min, tzinfo=BUSINESS_TIME_ZONE) if cutoff else None

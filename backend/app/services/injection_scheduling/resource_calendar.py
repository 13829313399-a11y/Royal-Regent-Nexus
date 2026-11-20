"""Half-open resource intervals; production splits, setup is continuous by default."""

from datetime import datetime, time, timedelta

from .calculations import TZ, timestamp


def merge_blocks(blocks):
    result = []
    for start, end in sorted(
        (timestamp(a), timestamp(b)) for a, b in blocks if a and b
    ):
        if end <= start:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(end, result[-1][1]))
        else:
            result.append((start, end))
    return result


def calendar_blocks(as_of, settings, events, machine_id=None, asset_id=None, days=730):
    start = timestamp(as_of).replace(hour=0, minute=0, second=0, microsecond=0)
    blocks = []
    for event in events:
        resource = event.get("resource_type", "FACTORY")
        if (
            resource == "FACTORY"
            or resource == "MACHINE"
            and event.get("resource_id") == machine_id
            or resource == "MOLD"
            and event.get("resource_id") == asset_id
        ):
            # An unknown recovery is unavailable throughout the entire planning horizon.
            blocks.append(
                (
                    event["start_at"],
                    event.get("end_at") or timestamp(as_of) + timedelta(days=days + 1),
                )
            )
    working = settings.get("working_days", list(range(7)))
    breaks = settings.get("daily_breaks", [])
    if len(working) < 7 or breaks:
        for n in range(days):
            day = start + timedelta(days=n)
            if day.weekday() not in working:
                blocks.append((day, day + timedelta(days=1)))
                continue
            for period in breaks:
                a = datetime.combine(
                    day.date(), time.fromisoformat(period["start"]), TZ
                )
                b = datetime.combine(day.date(), time.fromisoformat(period["end"]), TZ)
                if b <= a:
                    b += timedelta(days=1)
                blocks.append((a, b))
    return merge_blocks(blocks)


def consume(start, minutes, blocks=(), *, continuous=False):
    cursor = timestamp(start)
    seconds = float(minutes) * 60
    if seconds < 0:
        raise ValueError("生产时长不能为负数")
    if seconds == 0:
        return cursor, []
    limit = cursor + timedelta(days=730)
    segments = []
    for block_start, block_end in blocks:
        a, b = timestamp(block_start), timestamp(block_end)
        if b <= cursor:
            continue
        if cursor < a:
            available = (a - cursor).total_seconds()
            if seconds <= available:
                end = cursor + timedelta(seconds=seconds)
                return end, [*segments, (cursor, end)]
            if not continuous:
                segments.append((cursor, a))
                seconds -= available
        cursor = max(cursor, b)
        if cursor >= limit:
            raise ValueError("日历在两年内没有足够可用时间")
    end = cursor + timedelta(seconds=seconds)
    if end > limit:
        raise ValueError("生产时间超过两年范围，请核对日目标")
    return end, [*segments, (cursor, end)]


def overlaps(a, b):
    return timestamp(a[0]) < timestamp(b[1]) and timestamp(b[0]) < timestamp(a[1])

"""Half-open, timezone-explicit machine interval unions and gang attribution."""
from collections import defaultdict
from datetime import datetime, date, timedelta, UTC
from decimal import Decimal
from zoneinfo import ZoneInfo
from app.models import uv_operations as m
from . import common as c
from .payroll import split_money

ZONE=ZoneInfo('Asia/Shanghai')


def union_seconds(intervals):
    merged=[]
    for start,end in sorted(intervals):
        if end<=start:
            continue
        if merged and start<=merged[-1][1]:
            merged[-1]=(merged[-1][0],max(merged[-1][1],end))
        else:
            merged.append((start,end))
    return sum((Decimal(str((end-start).total_seconds())) for start,end in merged),Decimal(0))


def report(db,start_date,end_date):
    start,end=date.fromisoformat(start_date),date.fromisoformat(end_date)
    c.require(start<=end and (end-start).days<=366,'report_window','请选择不超过 366 天的日期区间',422)
    lower=datetime.combine(start,datetime.min.time(),ZONE).astimezone(UTC)
    upper=datetime.combine(end+timedelta(days=1),datetime.min.time(),ZONE).astimezone(UTC)
    buckets=defaultdict(list)
    attributed=[]
    incomplete=[]
    runs=list(db.scalars(c.query(m.UvOpsRun).where(m.UvOpsRun.started_at<c.ts(upper),(m.UvOpsRun.ended_at.is_(None))|(m.UvOpsRun.ended_at>c.ts(lower)))))
    shifts=list(db.scalars(c.query(m.UvOpsShift).where(m.UvOpsShift.start_at<c.ts(upper),m.UvOpsShift.end_at>c.ts(lower))))
    shift_buckets=defaultdict(list)
    for run in runs:
        if not run.ended_at:
            incomplete.append(run.id)
            continue
        a=max(datetime.fromisoformat(run.started_at),lower)
        b=min(datetime.fromisoformat(run.ended_at),upper)
        allocations=list(db.scalars(c.query(m.UvOpsRunAllocation).where(m.UvOpsRunAllocation.run_id==run.id)))
        cursor=a
        while cursor<b:
            midnight=datetime.combine(cursor.astimezone(ZONE).date()+timedelta(days=1),datetime.min.time(),ZONE).astimezone(UTC)
            stop=min(b,midnight)
            day=cursor.astimezone(ZONE).date().isoformat()
            buckets[(run.machine_id,day)].append((cursor,stop))
            if allocations:
                # Reuse deterministic minor-unit allocation at microsecond scale.
                seconds=Decimal(str((stop-cursor).total_seconds()))
                shares=split_money(seconds*10000,{row.id:row.share for row in allocations})
                attributed.extend(dict(run_id=run.id,task_id=row.task_id,allocation_id=row.id,business_date=day,allocated_machine_seconds=shares[row.id]/10000,share=row.share) for row in allocations)
            cursor=stop
        for shift in shifts:
            x,y=max(a,datetime.fromisoformat(shift.start_at)),min(b,datetime.fromisoformat(shift.end_at))
            if x<y:
                shift_buckets[(run.machine_id,shift.id)].append((x,y))
    return c.json_value(dict(by_day=[dict(machine_id=machine,business_date=day,machine_seconds=union_seconds(parts)) for (machine,day),parts in sorted(buckets.items())],by_shift=[dict(machine_id=machine,shift_id=shift,machine_seconds=union_seconds(parts)) for (machine,shift),parts in sorted(shift_buckets.items())],task_allocations=attributed,incomplete_runs=incomplete,policy='Asia/Shanghai natural-day machine interval union; quantity/wages use explicit shift business date; gang shares apply to machine seconds, never multiply human hours'))

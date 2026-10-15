"""Read-only reporting over logical products and immutable formal exports."""
from collections import defaultdict
from statistics import median

from sqlalchemy import select

from app.models.internal_quote import InternalQuote, InternalQuoteAlternative, InternalQuoteExportFile

FORMAL_STAGES = {"p4_direct_issued", "p4_final_approved"}


def first_output_metrics(db, factory_id, start, end, parse_timestamp):
    # Do not load workbook blobs, regenerate files, or use mutable updated_at.
    quotes = list(db.scalars(select(InternalQuote).where(InternalQuote.factory_id == factory_id)))
    by_id = {q.id: q for q in quotes}
    alternatives = list(db.scalars(select(InternalQuoteAlternative).where(
        InternalQuoteAlternative.quote_id.in_(by_id)))) if by_id else []
    entries = {a.quote_id: a for a in alternatives}
    versions = defaultdict(list)
    for q in quotes:
        root_id = entries[q.id].family_id if q.id in entries else q.id
        if root_id in by_id:
            versions[root_id].append(q)
    exports = defaultdict(list)
    if by_id:
        for quote_id, stamp in db.execute(select(InternalQuoteExportFile.quote_id, InternalQuoteExportFile.exported_at).where(
            InternalQuoteExportFile.factory_id == factory_id,
            InternalQuoteExportFile.quote_id.in_(by_id),
            InternalQuoteExportFile.release_stage.in_(FORMAL_STAGES),
        )):
            exports[quote_id].append(stamp)
    archived_batches = {q.batch_id or q.id for q in quotes if q.id in versions and q.status == "archived"}
    samples = defaultdict(list)
    pending = []
    overdue = 0
    missing = 0
    for root_id, members in versions.items():
        root = by_id[root_id]
        created = parse_timestamp(root.created_at)
        stamps = [parse_timestamp(stamp) for q in members for stamp in exports[q.id]]
        known_output = bool(stamps) or any(
            q.status == "exported" or q.final_release_status == "issued"
            or (q.id in entries and (entries[q.id].issued_at or entries[q.id].reported_at)) for q in members)
        if known_output:
            if not created or not stamps or any(t is None or t < created or t > end for t in stamps):
                missing += 1
                continue
            first = min(stamps)
            if start <= first <= end:
                samples[(root.customer or "未填写客户").strip() or "未填写客户"].append((first - created).total_seconds() / 3600)
            continue
        if (root.batch_id or root.id) in archived_batches or not any(
            q.status != "archived" and not (q.id in entries and entries[q.id].archived) for q in members
        ):
            continue
        if created and created > end:
            continue
        hours = (end - created).total_seconds() / 3600 if created else None
        overdue += hours is not None and hours > 72
        pending.append(dict(quote_id=root.id, quote_no=root.quote_no, product_name=root.product_name,
                            customer=root.customer, created_at=root.created_at,
                            waiting_hours=round(hours, 2) if hours is not None else None))
    pending.sort(key=lambda row: (row["waiting_hours"] is not None, row["waiting_hours"] or 0), reverse=True)
    speed = [dict(customer=customer, completed_count=len(values), median_hours=round(median(values), 2),
                  average_hours=round(sum(values) / len(values), 2), average_days=round(sum(values) / len(values) / 24, 2),
                  fastest_hours=round(min(values), 2), slowest_hours=round(max(values), 2))
             for customer, values in samples.items()]
    speed.sort(key=lambda row: (row["median_hours"], row["customer"]))
    return dict(customer_speed=speed, first_output_missing_time_count=missing,
                pending_first_output=dict(count=len(pending),
                    over_three_days=overdue,
                    oldest_hours=max((row["waiting_hours"] for row in pending if row["waiting_hours"] is not None), default=None),
                    items=pending[:10]))

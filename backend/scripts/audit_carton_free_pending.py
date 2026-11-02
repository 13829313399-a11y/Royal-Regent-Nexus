"""Read-only SQLite report of explicit-free receipts left pending; never repairs data."""
import argparse
import json
import sqlite3
from pathlib import Path


def candidates(database):
    database = Path(database).resolve(strict=True)
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        result = []
        rows = db.execute("""SELECT p.*, r.receipt_no, r.delivery_note_no, r.acceptance_date,
            r.confirmed_at, r.status AS receipt_status, l.currency, l.item_no, l.customer_code
            FROM carton_price_reviews p
            JOIN carton_receipt_lines l ON l.id=p.receipt_line_id AND l.factory_id=p.factory_id
            JOIN carton_receipts r ON r.id=l.receipt_id AND r.factory_id=p.factory_id
            WHERE p.status='PENDING' ORDER BY p.factory_id, p.id""").fetchall()
        for row in rows:
            source_tables = ("carton_supplier_shipment_lines", "carton_supplier_unmatched_lines") if row["source_kind"] == "REGULAR" else ("carton_special_shipment_lines",)
            snapshots = []
            for table in source_tables:
                source = db.execute(f"SELECT snapshot_json FROM {table} WHERE id=? AND factory_id=?",
                                    (row["shipment_line_id"], row["factory_id"])).fetchone()
                if source:
                    snapshots.append(json.loads(source[0]))
            events = db.execute("SELECT event_type,detail_json FROM carton_audit_events WHERE factory_id=? AND entity_type='carton_price_review' AND entity_id=? ORDER BY sequence",
                                (row["factory_id"], row["id"])).fetchall()
            recorded_free = any(event[0] == "PRICE_REVIEW_CREATED" and json.loads(event[1]).get("original_free_confirmed") is True for event in events)
            source_free = any(item.get("free_confirmed") is True or item.get("pricing_kind") == "FREE" for item in snapshots)
            if not recorded_free and not source_free:
                continue  # Zero alone never proves free.
            period = (row["acceptance_date"] or row["confirmed_at"][:10])[:7]
            protected = bool(db.execute("SELECT 1 FROM carton_supplier_settlements WHERE factory_id=? AND supplier_id=? AND period=? AND status='CONFIRMED' LIMIT 1",
                            (row["factory_id"], row["supplier_id"], period)).fetchone())
            protected = protected or bool(db.execute("SELECT 1 FROM carton_closings WHERE factory_id=? AND customer_code=? AND period=? AND currency=? AND status IN ('CONFIRMED','LOCKED') LIMIT 1",
                            (row["factory_id"], row["customer_code"], period, row["currency"])).fetchone())
            result.append({"review_id": row["id"], "factory_id": row["factory_id"], "receipt_no": row["receipt_no"],
                "delivery_note_no": row["delivery_note_no"], "item_no": row["item_no"], "period": period,
                "receipt_status": row["receipt_status"], "recorded_free_at_receipt": recorded_free,
                "source_currently_free": source_free, "protected_period": protected,
                "has_later_review_actions": row["revision"] > 1 or any(event[0] != "PRICE_REVIEW_CREATED" for event in events),
                "decision": "仅列为人工核对候选；须核对争议、历史更正及结算原证据，禁止自动修改"})
        return {"database": str(database), "read_only": True, "pending_checked": len(rows), "candidate_count": len(result), "candidates": result}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.resolve() == args.database.resolve():
        parser.error("报告路径不能覆盖数据库")
    report = candidates(args.database)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "candidates"}, ensure_ascii=False))

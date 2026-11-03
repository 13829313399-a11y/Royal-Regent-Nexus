"""Administrative, read-only snapshot for the approved feedback triage job.

Use only inside the authenticated production administration environment. This is
not an HTTP endpoint or a substitute for the employee-facing authorization API.
Attachments remain private; the report contains metadata, never their bytes.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.models.module_feedback import FeedbackAttachment, FeedbackMessage, FeedbackTicket


def collect_report(db, *, offset=0, limit=100):
    if offset < 0 or not 1 <= limit <= 200:
        raise ValueError("Invalid report pagination")
    scope = FeedbackTicket.module == "internal-quote"
    total = db.scalar(select(func.count()).select_from(FeedbackTicket).where(scope))
    tickets = db.scalars(select(FeedbackTicket).where(scope).order_by(FeedbackTicket.id).offset(offset).limit(limit)).all()
    items = []
    for ticket in tickets:
        item = {key: getattr(ticket, key) for key in (
            "id", "factory_id", "module", "title", "category", "status", "author_name", "context",
            "requested_materials", "provided_materials", "release_note", "revision", "created_at", "updated_at")}
        item["messages"] = []
        messages = db.scalars(select(FeedbackMessage).where(FeedbackMessage.ticket_id == ticket.id,
            FeedbackMessage.revision <= ticket.revision).order_by(FeedbackMessage.revision)).all()
        for message in messages:
            row = {key: getattr(message, key) for key in (
                "id", "actor_name", "actor_kind", "body", "action", "revision", "created_at",
                "requested_materials", "provided_materials", "release_note")}
            # Select columns explicitly to ensure no attachment content is loaded.
            row["attachments"] = [dict(attachment._mapping) for attachment in db.execute(select(
                FeedbackAttachment.id, FeedbackAttachment.file_name, FeedbackAttachment.content_type,
                FeedbackAttachment.size, FeedbackAttachment.sha256).where(FeedbackAttachment.message_id == message.id))]
            item["messages"].append(row)
        items.append(item)
    return {"module": "internal-quote", "collected_at": datetime.now(timezone.utc).isoformat(),
            "total": total, "offset": offset, "next_offset": offset + len(items) if offset + len(items) < total else None,
            "items": items}

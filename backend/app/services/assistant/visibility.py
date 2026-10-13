"""Fail closed for the whole derived response, not only its citation buttons."""
from fastapi import HTTPException
from app import db as database


def sources(parts):
    return [s for p in parts if p.get("type") == "evidence" for s in p.get("sources", [])]


def allowed(user, refs, db=None):
    if db is None:
        with database.SessionLocal() as session:
            return allowed(user, refs, session)
    try:
        for source in refs:
            if source["kind"] == "business":
                from .business import visible
                if not visible(db, user, source):
                    return False
            elif source["kind"] == "file":
                if source["file_ref"]["kind"] == "document":
                    from .files import owned
                    owned(db, user, source["file_ref"]["id"], ready=True)
                else:
                    from .storage import validate_attachments
                    from app.models.assistant import AssistantAttachment
                    row = db.get(AssistantAttachment, source["file_ref"]["id"])
                    if row is None:
                        return False
                    validate_attachments(db, user, row.session_id, [row.id])
            elif source["kind"] == "help":
                from .help_registry import get
                get(user, source["help_id"])
        return True
    except (HTTPException, KeyError, ValueError):
        return False

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
        snapshots = {}
        for source in refs:
            if source["kind"] == "business":
                from .business import visible
                if not visible(db, user, source):
                    return False
            elif source["kind"] == "file":
                if source["file_ref"]["kind"] == "document":
                    from .files import snapshot, source_matches
                    ident = source['file_ref']['id']
                    if ident not in snapshots:
                        snapshots[ident] = snapshot(db,user,ident)
                    if not source_matches(snapshots[ident],source):
                        return False
                else:
                    from .storage import validate_attachments
                    from app.models.assistant import AssistantAttachment
                    row = db.get(AssistantAttachment, source["file_ref"]["id"])
                    if row is None:
                        return False
                    validate_attachments(db, user, row.session_id, [row.id])
            elif source["kind"] == "help":
                from .help_registry import get, matches
                if not matches(get(user, source["help_id"]), source):
                    return False
        return True
    except (HTTPException, KeyError, ValueError, TypeError):
        return False

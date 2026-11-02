"""Read V3 security dependencies without requiring V3 ORM models.

This small reader is also shipped in the reviewed prior-code rollback patch.
None means the newer run cannot be safely projected by this reader.
"""
from copy import deepcopy
import json
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

TABLE='nexus_assistant_executions'
KINDS=frozenset(('business','file','help','web'))


def decode_refs(raw):
    try:
        value=json.loads(raw) if isinstance(raw,str) else raw
    except (ValueError,TypeError):
        return None
    if not isinstance(value,list):return None
    if any(not isinstance(s,dict) or not isinstance(s.get('source_id'),str) or not s['source_id']
           or not isinstance(s.get('kind'),str) or s['kind'] not in KINDS for s in value):
        return None
    return deepcopy(value)


def source_refs(db,run):
    if run is None or not isinstance(run.request_input,dict):return None
    version=run.request_input.get('protocol_version',1)
    if type(version) is not int or version<1:return None
    if version<=2:return []
    if version!=3:return None
    try:
        inspector=inspect(db.connection())
        if not inspector.has_table(TABLE):return None
        if not {'run_id','source_refs'} <= {c['name'] for c in inspector.get_columns(TABLE)}:return None
        raw=db.execute(text('SELECT source_refs FROM nexus_assistant_executions WHERE run_id=:rid'),{'rid':run.id}).scalar_one_or_none()
    except SQLAlchemyError:
        # No SQL parameters, source values or response content enter a log.
        return None
    return decode_refs(raw)

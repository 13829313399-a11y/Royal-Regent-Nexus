"""Keyset pages contain authorized matches, not pre-filtered candidate slots."""
import math
from sqlalchemy import and_, or_
from .errors import AssistantError


def matching_page(db, model, statement, cursor, limit, render):
    after = None
    if cursor:
        try:
            stamp, ident = cursor.split(":", 1)
            stamp = float(stamp)
            if not math.isfinite(stamp) or not 0 <= stamp < 1e12 or not ident or len(ident) > 64: raise ValueError()
            after = (stamp, ident)
        except ValueError:
            raise AssistantError("cursor_invalid", "分页位置无效，请重新搜索。") from None
    found = []
    batch_size = max(50, limit + 1)
    while len(found) <= limit:
        query = statement
        if after:
            stamp, ident = after
            query = query.where(or_(model.updated_at < stamp, and_(model.updated_at == stamp, model.id < ident)))
        rows = db.scalars(query.order_by(model.updated_at.desc(), model.id.desc()).limit(batch_size)).all()
        for row in rows:
            item = render(row)
            after = (row.updated_at, row.id)
            if item is not None:
                found.append((item, after))
                if len(found) > limit: break
        if len(rows) < batch_size: break
    more = len(found) > limit
    last = found[limit-1][1] if more else None
    return dict(items=[item for item, _ in found[:limit]], next_cursor=f"{last[0]}:{last[1]}" if last else None)

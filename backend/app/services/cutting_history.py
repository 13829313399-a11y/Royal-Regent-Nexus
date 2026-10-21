"""Bound presentation history only; effective facts are always replayed in full."""
from hashlib import sha256
import json

from app.services import cutting_ops as c

PAGE_SIZE = 20


def window(groups, page, focus=''):
    total = sum(len(d['history']) for documents in groups for d in documents)
    if focus:
        offset = 0
        for documents in groups:
            for document in documents:
                if document['document_id'] == focus:
                    page = offset // PAGE_SIZE + 1
                    break
                offset += len(document['history'])
            else:
                continue
            break
    page = min(page, max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE))
    start, stop, offset = (page - 1) * PAGE_SIZE, page * PAGE_SIZE, 0
    output = []
    for documents in groups:
        selected = []
        for document in documents:
            history = document['history']
            lo, hi = max(0, start - offset), min(len(history), stop - offset)
            if lo < hi:
                selected.append(dict(document, history=history[lo:hi]))
            offset += len(history)
        output.append(selected)
    return output, dict(page=page, page_size=PAGE_SIZE, total=total)


def production(value, page=1, expected_version=None, focus=''):
    c.require(expected_version is None or value['version'] == expected_version,
              '生产记录已变化，请刷新后重新查看历史，原输入可保留。', 409)
    groups, pagination = window([value['documents']], page, focus)
    return dict(value, documents=groups[0], history_pagination=pagination)


def closing(value, page=1, scope='all', expected_token=None):
    keys = ('production_documents', 'usage_documents', 'warehouse_documents')
    token = sha256(json.dumps([value['line_id'], value['month'], value['through'],
                              value['basis']['order_version'], *[value[k] for k in keys]],
                             sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    c.require(expected_token is None or expected_token == token,
              '月度核对依据已变化，请刷新所选订单后重新查看历史。', 409)
    def matches(d):
        return scope == 'all' or d.get('scope', {}).get(
            'earlier_history' if scope == 'opening' else 'period_history', False)
    warehouse = [dict(document_id=d['id'], history=[d]) for d in value[keys[2]]
                 if scope == 'all' or d.get('scope') == scope]
    groups, pagination = window([[d for d in value[k] if matches(d)] for k in keys[:2]] + [warehouse], page)
    return dict(value, production_documents=groups[0], usage_documents=groups[1],
                warehouse_documents=[d['history'][0] for d in groups[2]],
                history_pagination=dict(pagination, scope=scope, token=token))

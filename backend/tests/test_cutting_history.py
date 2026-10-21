from copy import deepcopy
import pytest
from fastapi import HTTPException
from app.services.cutting_history import production, closing


def test_pages_cover_every_event_once_preserving_effective_document_and_summary():
    docs = [dict(document_id=str(i), posted={'id':f'{i}-latest'},
                 history=[dict(id=f'{i}-{j}') for j in range(n)])
            for i, n in enumerate([23, 5, 17])]
    value = dict(version=8, documents=docs, summary=dict(completed=7))
    original = deepcopy(value)
    pages = [production(value, p, 8) for p in range(1, 4)]
    ids = [e['id'] for page in pages for d in page['documents'] for e in d['history']]
    assert ids == [e['id'] for d in docs for e in d['history']]
    assert len(set(ids)) == 45
    assert all(p['summary']['completed'] == 7 for p in pages)
    assert pages[1]['documents'][0]['posted'] == docs[0]['posted']
    assert production(value, focus='2')['history_pagination']['page'] == 2
    assert production(value, 999)['history_pagination']['page'] == 3
    assert value == original
    with pytest.raises(HTTPException) as error:
        production(value, 2, 7)
    assert error.value.status_code == 409


def test_closing_pages_filter_before_paging_and_keep_complete_totals():
    docs = [dict(document_id=str(i), scope=dict(earlier_history=i<22, period_history=i>=22),
                 history=[dict(id=str(i))]) for i in range(44)]
    value = dict(line_id='one', month='2026-09', through='2026-09-30', basis={'order_version':9},
                 production_documents=docs, usage_documents=[], warehouse_documents=[],
                 production=[dict(completed=55)])
    old = deepcopy(value)
    first = closing(value, scope='period')
    assert first['history_pagination']['total'] == 22
    token = first['history_pagination']['token']
    value['basis']['usage_revision'] = 900
    value['basis']['warehouse_revision'] = 901
    second = closing(value, 2, 'period', token)
    assert [d['document_id'] for d in second['production_documents']] == ['42', '43']
    assert second['production'] == value['production']
    old['basis'].update(usage_revision=900, warehouse_revision=901)
    assert value == old
    value['production_documents'][0]['history'][0]['reason'] = 'correction'
    with pytest.raises(HTTPException) as error:
        closing(value, 2, 'period', token)
    assert error.value.status_code == 409

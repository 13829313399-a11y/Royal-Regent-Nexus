from app.services.carton_schedule_order_matching import solve


def row(key, so, po, **extra):
    return dict(schedule_identity=key, schedule_customer_code='C', contract_no='K', item_no='I',
                source_reference=so, customer_po=po, factory_id='F', **extra)


def order(key, po, **extra):
    return dict(id=key, customer_code='C', contract_no='K', item_no='I', customer_po=po,
                factory_id='F', status='CONFIRMED', **extra)


def run(rows, orders, links=None):
    return solve(rows, orders, links or {}, factory_id='F')


def test_explicit_links_take_precedence_and_other_so_can_have_same_po():
    rows = [row('a', 'SO-A', 'PO-X'), row('b', 'SO-B', 'PO-X')]
    assert run(rows, [order('one', 'PO-X')], {'a': ['one']}) == {
        'matches': {'a': ['one']}, 'ambiguous': {}}
    assert run(rows, [order('one', 'PO-X'), order('two', 'PO-X')], {'a': ['one'], 'b': ['two']}) == {
        'matches': {'a': ['one'], 'b': ['two']}, 'ambiguous': {}}


def test_same_po_without_source_evidence_or_multiple_orders_requires_review():
    rows = [row('a', 'SO-A', 'PO-X'), row('b', 'SO-B', 'PO-X')]
    assert run(rows, [order('one', 'PO-X')]) == {'matches': {}, 'ambiguous': {'a': ['one'], 'b': ['one']}}
    assert run(rows[:1], [order('one', 'PO-X'), order('two', 'PO-X')]) == {
        'matches': {}, 'ambiguous': {'a': ['one', 'two']}}


def test_legacy_so_only_if_unique_and_does_not_steal_other_real_po():
    assert run([row('a', 'SO-A', 'PO-X')], [order('old', 'SO-A')])['matches'] == {'a': ['old']}
    result = run([row('a', 'SO-A', 'PO-X'), row('b', 'SO-B', 'SO-A')], [order('old', 'SO-A')])
    assert result == {'matches': {}, 'ambiguous': {'b': ['old'], 'a': ['old']}}
    assert run([row('a', 'SO-A', '')], [order('old', 'SO-A')])['matches'] == {'a': ['old']}
    assert run([row('a', '', '')], [order('blank', '')]) == {'matches': {}, 'ambiguous': {}}


def test_duplicate_identity_conflicting_links_and_scope_fail_closed():
    same = row('a', 'SO-A', 'PO-X')
    assert run([same, dict(same)], [order('one', 'PO-X')]) == {'matches': {}, 'ambiguous': {'a': ['one']}}
    rows = [same, row('b', 'SO-B', 'PO-X')]
    assert run(rows, [order('one', 'PO-X')], {'a': ['one'], 'b': ['one']}) == {
        'matches': {}, 'ambiguous': {'a': ['one'], 'b': ['one']}}
    foreign = {**order('foreign', 'PO-X'), 'factory_id': 'OTHER'}
    assert run([same], [foreign], {'a': ['foreign']}) == {'matches': {}, 'ambiguous': {}}
    other_customer = {**order('other', 'PO-X'), 'customer_code': 'OTHER'}
    assert run([same], [other_customer], {'a': ['other']}) == {'matches': {}, 'ambiguous': {}}


def test_ambiguous_actual_po_is_not_claimed_by_legacy_so():
    rows = [row('a', 'SO-A', 'PO-X'), row('b', 'SO-B', 'PO-X'), row('c', 'PO-X', 'PO-C')]
    result = run(rows, [order('one', 'PO-X')])
    assert result['matches'] == {}
    assert result['ambiguous'] == {'a': ['one'], 'b': ['one'], 'c': ['one']}


def test_new_link_requires_current_real_po_but_old_link_accepts_so():
    source = row('a', 'SO-A', 'NEW-PO')
    legacy = order('old', 'SO-A')
    assert run([source], [legacy], {'a': ['old']})['matches'] == {'a': ['old']}
    current = {**legacy, 'source_po_semantics': 'SOURCE_PO'}
    assert run([source], [current], {'a': ['old']}) == {'matches': {}, 'ambiguous': {'a': ['old']}}
    assert run([source], [current]) == {'matches': {}, 'ambiguous': {'a': ['old']}}


def test_link_for_absent_source_reserves_order():
    assert run([row('b', 'SO-B', 'PO-X')], [order('one', 'PO-X')], {'a': ['one']}) == {'matches': {}, 'ambiguous': {}}


def test_both_source_identifiers_blank_only_create_review_quantity_evidence():
    from app.services.carton_schedule_quantity_matching import solve as quantity_solve
    source = row('a', '', '', template='unified-item', order_type='正单', schedule_section='PENDING', quantity=104, carton_rule='4')
    purchase = order('one', '', quantity_basis='CALCULATED', product_order_quantity=104,
        lines=[dict(packaging_type='外箱', usage_quantity=4, quantity_rule={'mode': 'PACKING'})])
    result = quantity_solve([source], [purchase], factory_id='F')
    assert result['one'][0]['ambiguous'] is True
    assert quantity_solve([source], [{**purchase, 'customer_code': 'OTHER'}], factory_id='F') == {}
    assert quantity_solve([source], [{**purchase, 'factory_id': 'OTHER'}], factory_id='F') == {}
    assert quantity_solve([{**source, 'carton_rule': ''}], [purchase], factory_id='F') == {}

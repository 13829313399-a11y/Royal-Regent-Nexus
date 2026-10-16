"""Read-only comparison of immutable preparation versions, with decimal deltas."""
from decimal import Decimal, localcontext


QUANTITIES = ('opening_normal_quantity', 'ending_normal_quantity', 'opening_completed_quantity',
              'completed_quantity', 'opening_wip_quantity', 'ending_wip_quantity',
              'opening_loss_quantity', 'ending_loss_quantity', 'opening_custody', 'ending_custody')


def comparison(events, selected):
    if not selected:
        return None
    same_input = selected.data['input']['operation_id']
    earlier = [event for event in events if event.action == 'save' and event.version < selected.version
               and event.id != same_input]
    if not earlier:
        return None
    previous = earlier[-1]
    old, new = previous.data['snapshot'], selected.data['snapshot']
    before = {row['issue_id']: row for row in old['allocations']}
    after = {row['issue_id']: row for row in new['allocations']}
    changes, costs = [], {}
    with localcontext() as precision:
        precision.prec = 60
        for identifier in sorted(before.keys() | after.keys()):
            a, b = before.get(identifier), after.get(identifier)
            if a == b:
                continue
            quantities = {key: format(Decimal((b or {}).get(key, '0')) - Decimal((a or {}).get(key, '0')), 'f')
                          for key in QUANTITIES}
            # Missing prices and currency changes are not zero-valued row costs.
            amounts = None
            if a and b and a.get('amounts') and b.get('amounts') and a['currency'] == b['currency']:
                amounts = {key: format(Decimal(b['amounts'][key]) - Decimal(a['amounts'][key]), '.2f')
                           for key in b['amounts']}
            changes.append(dict(issue_id=identifier, line_id=(b or a)['line_id'], before=a, after=b,
                                quantity_delta=quantities, amount_delta=amounts))
        for currency in sorted(old['costs'].keys() | new['costs'].keys()):
            a, b = old['costs'].get(currency, {}), new['costs'].get(currency, {})
            costs[currency] = {key: format(Decimal(b.get(key, '0')) - Decimal(a.get(key, '0')), '.2f')
                               for key in a.keys() | b.keys()}
    return dict(previous_id=previous.id, previous_version=previous.version, previous_actor=previous.actor_name,
                previous_date=previous.created_at, previous_reason=previous.reason,
                evidence_changed=selected.data['basis_token'] != previous.data['basis_token'],
                partial_pricing=any(not row.get('price') for row in [*before.values(), *after.values()]),
                orders=[dict(line_id=order['line_id'], order_snapshot=order.get('order_snapshot', {})) for order in old['orders']],
                rows=changes, costs=costs)

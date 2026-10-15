import type { RouteLocationRaw } from 'vue-router'
import type { WorkEntry } from './types'
import { positionWorkbenchEnabled, consolidatedIamEnabled } from '@/components/iam/workspace/iam-navigation'

/** Fixed routes, validated identifiers; the API never supplies executable URLs. */
export function entryRoute(entry: WorkEntry, positionUi = positionWorkbenchEnabled, consolidated = consolidatedIamEnabled): RouteLocationRaw | null {
  const target = entry.actions.find(action => action.enabled)?.target
  if (!target) return null
  const id = target.params.id ?? ''
  if (!id || id.length > 128 || /[\\/?#\u0000-\u001f]/.test(id)) return null
  if (target.route_key === 'identity_approval') return consolidated
    ? { name: 'system-users', query: { view: 'todo', task: `identity-change:${id}` } }
    : { path: '/system/iam/requests', query: { change: id } }
  if (consolidated && ['account_requests', 'position_workbench'].includes(target.route_key)) {
    const kind = target.route_key === 'position_workbench' ? 'position' : target.query.stage?.startsWith('password_reset') ? 'password-reset' : 'registration'
    return { name: 'system-users', query: { view: 'todo', task: `${kind}:${id}` } }
  }
  // Account administration is a global workspace. Its source organization may
  // be '*' or group-management, neither is a production-factory route scope.
  if (target.route_key === 'account_requests') return target.query.stage?.startsWith('password_reset')
    ? { name: 'system-registration', query: { tab: 'password-reset', request_id: id } }
    : positionUi
      ? { name: 'position-workbench-compatible', query: { tab: 'pending', item: `registration:${id}` } }
      : { name: 'system-registration', query: { tab: 'pending', request_id: id } }
  if (target.route_key === 'position_workbench') return { name: 'position-workbench-compatible', query: { tab: 'pending', item: `position:${id}` } }
  if (target.route_key === 'my_position') return { name: 'account-position' }
  const factory = target.query.factory ?? ''
  if (factory && !['huakang-a', 'huakang-b', 'huakang-c', 'huakang-d', 'huadeng', 'huaxing'].includes(factory)) return null
  switch (target.route_key) {
    case 'quote': return { name: 'internal-quote-collaboration', params: { quoteId: id }, query: { factory, section: target.query.stage?.split(':')[1] } }
    case 'molding_engineering': return { name: 'molding-sample', query: { factory, order_id: id } }
    case 'molding_production': return { name: 'molding-sample-production-tasks', query: { factory, order_id: id } }
    case 'shipment': return { name: 'carton-supplier-management', query: { factory, shipment: id } }
    default: return null
  }
}

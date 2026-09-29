import type { RouteLocationRaw } from 'vue-router'
import type { WorkEntry } from './types'

/** Fixed routes, validated identifiers; the API never supplies executable URLs. */
export function entryRoute(entry: WorkEntry): RouteLocationRaw | null {
  const target = entry.actions.find(action => action.enabled)?.target
  if (!target) return null
  const id = target.params.id ?? ''
  if (!id || id.length > 128 || /[\\/?#\u0000-\u001f]/.test(id)) return null
  const factory = target.query.factory ?? ''
  if (factory && !['huakang-a', 'huakang-b', 'huakang-c', 'huakang-d', 'huadeng', 'huaxing'].includes(factory)) return null
  switch (target.route_key) {
    case 'quote': return { name: 'internal-quote-collaboration', params: { quoteId: id }, query: { factory, section: target.query.stage?.split(':')[1] } }
    case 'molding_engineering': return { name: 'molding-sample', query: { factory, order_id: id } }
    case 'molding_production': return { name: 'molding-sample-production-tasks', query: { factory, order_id: id } }
    case 'shipment': return { name: 'carton-supplier-management', query: { factory, shipment: id } }
    case 'account_requests': return { name: 'system-registration', query: { tab: target.query.stage?.startsWith('password_reset') ? 'password-reset' : 'pending', request_id: id } }
    default: return null
  }
}

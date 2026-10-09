import type { AuthMeResponse } from '@/api/auth'
import type { PageContext } from './types'
export const moduleRoutes: Record<string, string[]> = {
  portal: ['dashboard', 'modules-department'],
  'work-center': ['notification-center'],
  'injection-scheduling': ['injection-scheduling'],
  'three-d-printing': ['three-d-printing-management'],
  'internal-quote': ['internal-quote-desk-home', 'internal-quote-collaboration', 'internal-quote-summary', 'internal-quote-export-summary'],
  'identity-management': ['system-user-access', 'system-users', 'iam-role-templates'],
  'carton-supplier': ['carton-supplier', 'carton-supplier-carton-mark'],
  'molding-sample': ['molding-sample', 'molding-sample-production-tasks'],
  'customer-orders': ['customer-order-center'],
  'carton-procurement': ['carton-procurement'],
  'carton-mark': ['carton-mark-template', 'carton-mark-check', 'qc-carton-mark-check'],
  'qc-inspection': ['qc-inspection-schedule', 'qc-inspection-order-records', 'qc-inspection-order-detail', 'qc-inspection-problems', 'qc-inspection-reports'],
  'document-tools': ['shared-tool-center'],
  'uv-operations': ['uv-live', 'uv-planning', 'uv-shifts', 'uv-materials', 'uv-analytics', 'uv-settings', 'uv-imports'],
  'spray-production': ['spray-overview', 'spray-planning', 'spray-demands', 'spray-execution', 'spray-handover', 'spray-materials', 'spray-finance', 'spray-settlements', 'spray-imports', 'spray-activity'],
}
export function identityKey(user: AuthMeResponse | null) { return user ? `${user.id}:${user.identity?.employment_epoch ?? 1}` : '' }
export function pageContext(routeName: unknown, factory: string, queryFactory?: unknown): PageContext | null {
  if (typeof routeName !== 'string') return null
  const entry = Object.entries(moduleRoutes).find(([, routes]) => routes.includes(routeName))
  if (!entry) return null
  const scopedQuery = ['injection-scheduling','three-d-printing','spray-production'].includes(entry[0]) && typeof queryFactory === 'string'
  return { module_id: entry[0], route_name: routeName, factory_id: ['uv-operations','three-d-printing'].includes(entry[0]) ? 'huakang-a' : scopedQuery ? queryFactory : factory }
}
export function eligible(user: AuthMeResponse | null, routeName: unknown) {
  return !!user && !user.force_password_change && !['login', 'register', 'reset-password', 'change-password', 'forbidden'].includes(String(routeName))
}

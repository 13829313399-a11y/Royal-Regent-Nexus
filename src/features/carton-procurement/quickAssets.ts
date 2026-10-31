import type { AssetDepartment, QuickTarget, QuickTargetRef } from '@/api/cartonQuickAssets'
import { grantAllowsPermission, type useAuthStore } from '@/stores/auth'
import { getAuthenticationGeneration } from '@/lib/authenticationGeneration'

export type QuickAudience = 'sales' | 'warehouse' | 'supplier'
type Auth = ReturnType<typeof useAuthStore>
export const internalDepartments: AssetDepartment[] = ['sales-business', 'pmc-warehouse', 'carton']
export const departmentLabel: Record<AssetDepartment, string> = { 'sales-business': '业务部', 'pmc-warehouse': '仓库', carton: '纸箱部', supplier: '东康' }
export const quickStatusLabel: Record<string, string> = { DRAFT: '初稿', PENDING: '待确认', READY: '已确认', HISTORY: '历史版本', UNCLASSIFIED: '初稿' }
const explicitSources = ['override', 'user_override', 'inactive_permission', 'inactive_account']
const matches = (granted: string, requested: string) => granted === '*' || granted === requested

/** UI affordance only. Server canonical authorization remains authoritative. */
export function canQuickAsset(auth: Auth, factory: string, department: AssetDepartment, action: 'read' | 'manage' | 'confirm') {
  if (!factory || factory === 'ALL' || !auth.currentUser) return false
  if (department === 'supplier' && action === 'confirm') return false
  const code = 'carton_asset:' + action
  const access = (auth.effectiveAccess ?? []).filter(x => x.permission_code === code)
  const matching = access.filter(x => matches(x.factory_id, factory) && matches(x.department, department))
  if (matching.some(x => (x.effect === 'deny' || x.allowed === false) && explicitSources.includes(x.source_type))) return false
  if (!auth.hasEffectiveAccessSnapshot || !access.length) return false
  if (department === 'supplier' && !auth.can(action === 'manage' ? 'carton_supplier:edit' : 'carton_supplier:read', factory, '*')) return false
  const admin = (auth.grants ?? []).some(g => (g.role_code === 'admin' || g.role_id === 'admin') && g.factory_id === '*' && ['*', 'system'].includes(g.department) && (!g.factory_ceiling || g.factory_ceiling.includes(factory)))
  if (admin) return auth.can(code, factory, department)
  // As on the server, supplier global overrides cannot establish an internal
  // department. Nor may a position's function bundle impersonate other depts.
  if (matching.some(x => x.effect === 'allow' && x.allowed !== false && ['override', 'user_override'].includes(x.source_type)
    && (department === 'supplier' || x.department === department))) return true
  return auth.can(code, factory, department) && (auth.grants ?? []).some(g => (
    g.department === '*' || g.department === department || department === 'pmc-warehouse' && g.department === 'warehouse'
  ) && grantAllowsPermission(g, code, factory, department))
}
export function uploadDepartments(auth: Auth, factory: string, audience: QuickAudience) {
  return (audience === 'supplier' ? ['supplier' as const] : internalDepartments).filter(d => canQuickAsset(auth, factory, d, 'manage'))
}
export function viewerKey(auth: Auth) {
  return JSON.stringify([auth.currentUser?.id, auth.currentUser?.identity?.employment_epoch, auth.authorizationVersion, getAuthenticationGeneration()])
}
export function targetRef(target: QuickTarget): QuickTargetRef {
  return { kind: target.kind, id: target.id, sheet: target.sheet, row: target.row, fingerprint: target.fingerprint }
}
export function targetLabel(target: Pick<QuickTarget, 'kind' | 'contract_no' | 'item_no' | 'customer_name' | 'sheet' | 'row'>) {
  const type = { REGULAR: '采购单（已建单）', SCHEDULE: '业务排期（采购前可关联）', SAMPLE: '样板', MISC: '杂单' }[target.kind]
  return [type, target.contract_no, target.customer_name, target.item_no, target.kind === 'SCHEDULE' ? `${target.sheet} 第${target.row}行` : ''].filter(Boolean).join(' · ')
}
export function suggestedContract(value: string, filename = false) {
  const text = value.normalize('NFKC')
  const explicit = [...text.matchAll(/(?:合同(?:编号|号)?|CONTRACT\s*(?:NO\.?|NUMBER|#)?)\s*[:：#]?\s*([A-Za-z0-9][A-Za-z0-9./_-]{3,127})/gi)].map(x => x[1]!)
  if (filename) {
    const stem = text.replace(/\.[^.]+$/, '').replace(/(?:[_\s-]*(?:箱唛|初稿|待确认|已确认|正唛|侧唛|照片|图片|shipping[ _-]*mark|front|side)(?:[_\s-]*\d+)?)$/i, '')
    const token = stem.match(/^(?:\d{6,20}|[A-Za-z]{1,12}[-/][A-Za-z0-9][A-Za-z0-9./_-]{2,80})$/)?.[0]
    if (token) explicit.push(token)
  }
  const unique = [...new Map(explicit.map(x => [x.toUpperCase(), x])).values()]
  return unique.length === 1 ? unique[0]! : ''
}
export function responseStatus(cause: unknown): number | undefined {
  return (cause as { response?: { status?: number } } | null)?.response?.status
}

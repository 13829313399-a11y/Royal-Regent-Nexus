import { CUTTING_BASE, CUTTING_FACTORY, CUTTING_WORKSPACES } from './navigation'

export const ACCEPTANCE_GROUPS = ['生产与物料', '月结与财务', '操作追溯'] as const
const roleLabels = { readers:'已授权裁床岗位', clerk:'裁床文员', supervisor:'裁床主管', engineering:'工程岗位', procurement:'采购岗位', warehouse:'布料仓岗位', registrar:'登记会计', reviewer:'复核会计' }
const readablePermissions = ['read', 'cost_read', 'settlement_read', 'payment_read']

// Local acceptance metadata is navigation only; every destination retains its own authorization.
export function acceptanceSamples(value: unknown, release: string) {
  if (!value || typeof value !== 'object') throw new Error('样本导航格式不完整')
  const data = value as Record<string, unknown>
  if (data.release !== release || !Array.isArray(data.links) || data.links.length > 30) throw new Error('样本导航与发布版本不一致')
  return data.links.map((item: unknown) => {
    if (!item || typeof item !== 'object') throw new Error('样本导航格式不完整')
    const row = item as Record<string, unknown>
    if (typeof row.label !== 'string' || !row.label.trim() || row.label.length > 120 || !CUTTING_WORKSPACES.some(w => w.path === row.workspace)) throw new Error('样本导航目标无效')
    const group = row.group ?? (row.workspace === 'closing' ? '月结与财务' : row.workspace === 'activity' ? '操作追溯' : '生产与物料')
    const roles = row.roles ?? ['readers'], required = row.required_permissions ?? ['read']
    const expected = row.expected ?? '核对页面实际状态；需要办理时，由已授权岗位按原流程操作。'
    if (!ACCEPTANCE_GROUPS.some(g => g === group) || !Array.isArray(roles) || !roles.length || roles.length > 8 || !roles.every(role => typeof role === 'string' && Object.hasOwn(roleLabels, role))) throw new Error('样本岗位说明无效')
    if (!Array.isArray(required) || !required.length || required.length > 4 || !required.every(p => typeof p === 'string' && readablePermissions.includes(p))) throw new Error('样本查询授权说明无效')
    if (typeof expected !== 'string' || !expected.trim() || expected.length > 300) throw new Error('样本预期说明无效')
    const query: Record<string, string> = { factory: CUTTING_FACTORY }
    for (const key of ['day', 'month', 'line_id', 'view', 'document_id', 'event_id', 'focus_kind', 'focus_id', 'reporting_view', 'cost_view']) {
      const entry = row[key]
      if (entry === undefined) continue
      if (typeof entry !== 'string' || !entry || entry.length > 160) throw new Error('样本定位参数无效')
      if (key === 'month' && !/^\d{4}-(0[1-9]|1[0-2])$/.test(entry)) throw new Error('样本月份无效')
      if (key === 'day' && (!/^\d{4}-\d{2}-\d{2}$/.test(entry) || !Number.isFinite(Date.parse(entry)) || new Date(entry).toISOString().slice(0, 10) !== entry)) throw new Error('样本日期无效')
      query[key] = entry
    }
    return { label: row.label, group: group as typeof ACCEPTANCE_GROUPS[number], roles: roles.map(role => roleLabels[role as keyof typeof roleLabels]), expected, required: required as string[], to: { path: `${CUTTING_BASE}/${row.workspace}`, query } }
  })
}

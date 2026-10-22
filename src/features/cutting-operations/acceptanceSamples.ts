import { CUTTING_BASE, CUTTING_FACTORY, CUTTING_WORKSPACES } from './navigation'

// Local acceptance metadata is navigation only; every destination retains its own authorization.
export function acceptanceSamples(value: unknown, release: string) {
  if (!value || typeof value !== 'object') throw new Error('样本导航格式不完整')
  const data = value as Record<string, unknown>
  if (data.release !== release || !Array.isArray(data.links) || data.links.length > 30) throw new Error('样本导航与发布版本不一致')
  return data.links.map((item: unknown) => {
    if (!item || typeof item !== 'object') throw new Error('样本导航格式不完整')
    const row = item as Record<string, unknown>
    if (typeof row.label !== 'string' || !row.label.trim() || row.label.length > 120 || !CUTTING_WORKSPACES.some(w => w.path === row.workspace)) throw new Error('样本导航目标无效')
    const query: Record<string, string> = { factory: CUTTING_FACTORY }
    for (const key of ['day', 'month', 'line_id', 'view', 'document_id', 'event_id', 'focus_kind', 'focus_id', 'reporting_view', 'cost_view']) {
      const entry = row[key]
      if (entry === undefined) continue
      if (typeof entry !== 'string' || !entry || entry.length > 160) throw new Error('样本定位参数无效')
      if (key === 'month' && !/^\d{4}-(0[1-9]|1[0-2])$/.test(entry)) throw new Error('样本月份无效')
      if (key === 'day' && (!/^\d{4}-\d{2}-\d{2}$/.test(entry) || !Number.isFinite(Date.parse(entry)) || new Date(entry).toISOString().slice(0, 10) !== entry)) throw new Error('样本日期无效')
      query[key] = entry
    }
    return { label: row.label, to: { path: `${CUTTING_BASE}/${row.workspace}`, query } }
  })
}

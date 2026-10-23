import type { WorkSnapshot, WorkView } from './types'

const sourceLabels: Record<string, string> = {
  molding: '啤办', internal_quote: '内部报价', account_requests: '账户申请',
  carton_supplier: '供应商送货', identity: '任职知会', business_results: '业务结果通知',
  legacy_history: '历史记录', integrity: '来源检查', position_reviews: '任职审核',
}
const sourceLabel = (module: string) => sourceLabels[module] || '其他业务来源'

export const verificationCount = (snapshot?: WorkSnapshot | null) => (snapshot?.health.issues ?? [])
  .filter(issue => issue.reason === 'source_inconsistent').reduce((sum, issue) => sum + issue.count, 0)

export function workEmptyState(snapshot: WorkSnapshot | null | undefined, view: WorkView) {
  if (!snapshot) return { title: '正在读取事项', description: '' }
  if (workHealth(snapshot)?.retryable) return { title: '暂时无法读取完整列表', description: '请重试同步，当前计数可能不完整。' }
  if (view === 'info') return { title: '暂无知会消息', description: '知会用于告知进展，不计入可处理待办。' }
  if (view === 'verification') return { title: '暂无需要核对的业务事项', description: '历史提醒的来源记录可在上方说明中查看。' }
  if (['todo', 'assigned', 'team'].includes(view) && verificationCount(snapshot)) return {
    title: '暂无可直接处理的待办', description: '另有业务事项待核对，请通过上方入口查看；知会消息仍可正常查看。',
  }
  return { title: view === 'todo' ? '已接入业务范围内暂无待办' : '当前视图暂无事项', description: '可查看知会与历史，或调整筛选范围。' }
}

export function workHealth(snapshot?: WorkSnapshot | null) {
  if (!snapshot || snapshot.health.status === 'fresh') return null
  const { health, summary } = snapshot
  const issues = health.issues ?? []
  const missing = issues.filter(issue => issue.reason === 'source_missing').reduce((sum, issue) => sum + issue.count, 0)
  const inconsistent = issues.filter(issue => issue.reason === 'source_inconsistent').reduce((sum, issue) => sum + issue.count, 0)
  const unavailable = health.unavailable_sources.map(sourceLabel)
  const details = issues.map(issue => `${sourceLabel(issue.module)}：${issue.count} ${issue.reason === 'source_missing' ? '条历史提醒未找到原单据' : '项业务状态需要核对'}`)
  const historicalOnly = health.status === 'partial' && !unavailable.length && missing > 0 && !inconsistent && missing === summary.verification_required_total
  if (historicalOnly) return {
    warning: false, retryable: false, verificationCount: 0, title: `当前待办已同步 · ${missing} 条历史提醒待核对`,
    description: '这些历史提醒未找到对应原单据，已保留记录并排除在待办计数之外，不影响当前已核实事项的处理。', details,
  }
  return {
    warning: true,
    retryable: health.status === 'stale' || unavailable.length > 0 || missing + inconsistent !== summary.verification_required_total || !inconsistent,
    verificationCount: inconsistent,
    title: health.status === 'stale' ? '同步未完成，当前显示上次结果'
      : unavailable.length ? `${unavailable.join('、')}暂时无法同步`
        : inconsistent ? `${inconsistent} 项业务状态需要核对` : '部分事项仍需核验',
    description: health.status === 'stale' ? '待办数量可能已变化，请重试同步后再处理。'
      : unavailable.length ? '当前计数可能不完整，已读取的事项仍可查看。请重试同步；若持续失败，请联系管理员检查对应业务服务。'
        : inconsistent ? '同步已完成，相关事项因业务版本或状态待核对，未计入可处理待办。查看对应事项后前往源单据核对；其他待办与知会可正常使用。'
          : '已核实事项仍可查看，来源检查尚未完成。请重试同步获取具体原因。',
    details,
  }
}

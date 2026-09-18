import type { QcInspectionOrder, QcScheduleChange } from '@/api/qcInspection'

export type ScheduleDateField = 'planned_inspection_date' | 'shipment_date' | 'actual_inspection_date'
export interface ScheduleFilters {
  customer: string
  search: string
  status: string
  dateField: ScheduleDateField
  from: string
  to: string
  agency: string
}

// Keep the customer-specified value separate so a later shipment change still applies to fallback schedules.
export function effectiveInspectionDate(order: { planned_inspection_date?: string | null; shipment_date?: string | null }) {
  return order.planned_inspection_date || order.shipment_date || ''
}

export function inspectionToday() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
}

export function groupInspectionDays(orders: QcInspectionOrder[]) {
  const groups = new Map<string, QcInspectionOrder[]>()
  for (const order of sortInspectionSchedule(orders)) {
    const date = effectiveInspectionDate(order)
    if (!groups.has(date)) groups.set(date, [])
    groups.get(date)!.push(order)
  }
  return [...groups].map(([date, items]) => ({ date, orders: items }))
}

export function sortInspectionSchedule(orders: QcInspectionOrder[]) {
  return [...orders].sort((left, right) => {
    const a = effectiveInspectionDate(left) || '9999-12-31'
    const b = effectiveInspectionDate(right) || '9999-12-31'
    return a.localeCompare(b) || String(left.inspection_no || left.id).localeCompare(String(right.inspection_no || right.id))
  })
}

export function scheduleStatus(order: QcInspectionOrder) {
  if (order.status === 'CANCELLED' || order.inspection_result === 'CANCELLED') return 'cancelled'
  if (order.status === 'COMPLETED' || (order.inspection_result && order.inspection_result !== 'PENDING')) return 'completed'
  return effectiveInspectionDate(order) ? 'pending' : 'unplanned'
}

export function isImportedPendingInspection(order: QcInspectionOrder) {
  return order.source_type === 'SCHEDULE_IMPORT'
    && ['pending', 'unplanned'].includes(scheduleStatus(order))
}

export function filterSchedule(orders: QcInspectionOrder[], filters: ScheduleFilters) {
  const query = filters.search.trim().toLocaleLowerCase()
  return orders.filter((order) => {
    const date = filters.dateField === 'planned_inspection_date' ? effectiveInspectionDate(order) : order[filters.dateField] || ''
    return (!filters.customer || order.customer_name === filters.customer)
      && (!filters.agency || order.inspection_agency === filters.agency)
      && (!filters.status || (filters.status === 'problem' ? order.has_problem : scheduleStatus(order) === filters.status))
      && (!filters.from || (date && date >= filters.from))
      && (!filters.to || (date && date <= filters.to))
      && (!query || [order.inspection_no, order.customer_name, order.sales_contract_no, order.customer_po_no,
        order.customer_item_no, order.product_name].some((value) => String(value || '').toLocaleLowerCase().includes(query)))
  })
}

export type ImportDecisionAction = 'CREATE' | 'UPDATE' | 'KEEP' | 'SKIP'
export function importAction(row: QcScheduleChange, target?: string, requested?: ImportDecisionAction) {
  if (row.decision_status !== 'PENDING') return null
  const action = requested || (row.match_status === 'NEW' ? 'CREATE' : 'UPDATE')
  const allowed: Record<string, ImportDecisionAction[]> = { NEW: ['CREATE', 'SKIP'], EXACT: ['UPDATE', 'KEEP'], MULTIPLE_MATCHES: ['UPDATE', 'KEEP', 'SKIP'], INVALID: ['SKIP'] }
  if (!allowed[row.match_status]?.includes(action)) return null
  if (row.validation_errors.length && action !== 'SKIP') return null
  if (row.match_status === 'MULTIPLE_MATCHES' && action !== 'SKIP' && (!target || !row.candidate_order_ids.includes(target))) return null
  return action
}

export function selectedImportDecisions(rows: QcScheduleChange[], selected: string[], targets: Record<string, string>, actions: Record<string, ImportDecisionAction> = {}) {
  const ids = new Set(selected)
  return rows.filter((row) => ids.has(row.id)).flatMap((row) => {
    const action = importAction(row, targets[row.id], actions[row.id])
    return action ? [{ row_id: row.id, action, target_order_id: action === 'SKIP' ? undefined : targets[row.id] || undefined }] : []
  })
}

export const scheduleStatusLabels: Record<string, string> = {
  unplanned: '待安排', pending: '待验货', completed: '已验货', cancelled: '已取消',
}

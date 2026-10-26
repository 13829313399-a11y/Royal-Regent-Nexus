import type { CartonImportPreviewRow, CartonScheduleDemandSnapshot, CartonScheduleOrderMark } from '@/api/cartonProcurement'

const normalized = (value?: string) => (value || '').normalize('NFKC').trim().toLowerCase()
export const effectiveSchedulePo = (row: CartonImportPreviewRow) => normalized(row.source_reference) || normalized(row.customer_po)

export function scheduleDemandSnapshot(row: CartonImportPreviewRow): CartonScheduleDemandSnapshot {
  let packing = normalized(row.carton_rule).replace(/\s+/g, '')
  if (/^\d+(?:\.\d+)?(?:\/\d+(?:\.\d+)?)?$/.test(packing)) packing = packing.split('/').map(value => String(Number(value))).join('/')
  return { quantity: row.quantity == null ? '' : String(Number(row.quantity)), carton_rule: packing,
    inspection_window: normalized(row.inspection_window || row.source_inspection_window),
    customer_due_date: normalized(row.customer_due_date || row.source_customer_due_date) }
}

export function scheduleMarkChanges(row: CartonImportPreviewRow, mark?: Partial<CartonScheduleOrderMark>): string[] {
  if (mark?.review_required) return ['原下单依据待核实']
  if (!(mark?.marked ?? row.manual_ordered)) return []
  const frozen = mark?.demand_snapshot
  if (!frozen || Object.keys(frozen).length !== 4) return ['原下单依据待核实']
  const labels: Record<keyof CartonScheduleDemandSnapshot, string> = { quantity: '数量', carton_rule: '装箱', inspection_window: '验货日期', customer_due_date: '客户交期' }
  const current = scheduleDemandSnapshot(row)
  return (Object.keys(labels) as Array<keyof CartonScheduleDemandSnapshot>).filter(key => frozen[key] !== current[key]).map(key => labels[key])
}

export function scheduleMarkState(row: CartonImportPreviewRow, marks: Record<string, Partial<CartonScheduleOrderMark>>) {
  const current = marks[row.schedule_identity || '']
  if (current) return current
  if (row.schedule_identity_aliases?.some(key => marks[key]?.marked || marks[key]?.review_required))
    return { marked: false, review_required: true, demand_snapshot: null }
  return { marked: row.manual_ordered ?? false }
}

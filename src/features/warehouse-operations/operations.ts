import type { WarehouseDocument, WarehouseDomain, WarehouseOperationKind, WarehouseQuality } from '@/api/warehouseOperations'

export const operationLabels: Record<WarehouseOperationKind, string> = {
  RECEIPT: '登记实收', REQUEST: '登记领料申请', ISSUE: '登记出库', RETURN: '登记退料', TRANSFER: '登记调仓',
  LOCATION_BIND: '核实仓位', QUALITY: '登记质检结论', CORRECTION: '冲销录错单据', TASK: '登记加工任务', PROCESS_SEND: '登记加工发出',
  PROCESS_RETURN: '登记加工回货', PACK_SEND: '登记包装发出', PACK_RECEIVE: '代录包装接收回执',
}
export const qualityLabels: Record<WarehouseQuality, string> = { PENDING_INSPECTION: '待检', QUALIFIED: '合格', REJECTED: '不合格', HOLD: '暂停' }
export function sumQuantities(values: string[]): string {
  const scale = Math.max(0, ...values.map(value => (value.split('.')[1] ?? '').length))
  const sum = values.reduce((total, value) => { const [whole, fraction = ''] = value.split('.'); return total + BigInt(`${whole}${fraction.padEnd(scale, '0')}`) }, 0n)
  const digits = sum.toString().padStart(scale + 1, '0')
  return scale ? `${digits.slice(0, -scale)}.${digits.slice(-scale)}`.replace(/\.?0+$/, '') : digits
}
export function operationsView(domain: WarehouseDomain, section: string, view: string): { stock: boolean; kinds: WarehouseOperationKind[]; actions: WarehouseOperationKind[] } | undefined {
  if (section === 'overview') return { stock: false, kinds: [], actions: domain === 'fabric' ? ['RECEIPT', 'REQUEST'] : ['TASK', 'RECEIPT'] }
  if (section === 'activity') return { stock: false, kinds: [], actions: [] }
  if (section === 'exceptions' && view !== 'missing') return { stock: view === 'holds', kinds: view === 'holds' ? [] : ['CORRECTION', 'RETURN'], actions: ['CORRECTION'] }
  if (domain === 'semi' && section === 'orders' && view === 'tasks') return { stock: false, kinds: ['TASK'], actions: ['TASK'] }
  if (domain === 'semi' && section === 'receipts' && view !== 'import-review') return {
    stock: false, kinds: view === 'pending' ? ['TASK'] : view === 'processing-returns' ? ['PROCESS_RETURN'] : ['RECEIPT', 'PROCESS_RETURN', 'RETURN'],
    actions: view === 'processing-returns' ? ['PROCESS_RETURN'] : ['RECEIPT'],
  }
  if (section !== 'inventory') return undefined
  const map: Record<string, { stock: boolean; kinds: WarehouseOperationKind[]; actions: WarehouseOperationKind[] }> = {
    stock: { stock: true, kinds: [], actions: ['ISSUE', 'TRANSFER'] },
    'pending-issues': { stock: false, kinds: ['REQUEST'], actions: ['REQUEST', 'ISSUE'] },
    issues: { stock: false, kinds: ['ISSUE'], actions: ['ISSUE'] },
    returns: { stock: false, kinds: ['RETURN'], actions: ['RETURN'] },
    transfers: { stock: false, kinds: ['TRANSFER'], actions: ['TRANSFER'] },
    movements: { stock: false, kinds: [], actions: [] },
    processing: { stock: false, kinds: ['PROCESS_SEND'], actions: ['PROCESS_SEND', 'PROCESS_RETURN'] },
    packaging: { stock: false, kinds: ['PACK_SEND', 'PACK_RECEIVE'], actions: ['PACK_SEND', 'PACK_RECEIVE'] },
  }
  return map[view]
}
export function referenceKinds(kind: WarehouseOperationKind): WarehouseOperationKind[] {
  if (kind === 'ISSUE') return ['REQUEST']
  if (kind === 'RETURN') return ['ISSUE', 'PACK_SEND']
  if (kind === 'PROCESS_RETURN') return ['PROCESS_SEND']
  if (kind === 'PACK_RECEIVE') return ['PACK_SEND']
  if (kind === 'CORRECTION') return ['RECEIPT', 'ISSUE', 'TRANSFER', 'PROCESS_SEND', 'PACK_SEND']
  return []
}
// Display-only exact decimal subtraction. Posting quantities are validated by the server.
export function remaining(total: string, used = '0'): string {
  const parts = [total, used].map(value => value.split('.'))
  const scale = Math.max(...parts.map(part => (part[1] ?? '').length))
  const values = parts.map(part => BigInt(`${part[0] || '0'}${(part[1] ?? '').padEnd(scale, '0')}`))
  const difference = values[0]! - values[1]!
  const sign = difference < 0n ? '-' : ''
  const digits = (difference < 0n ? -difference : difference).toString().padStart(scale + 1, '0')
  return scale ? `${sign}${digits.slice(0, -scale)}.${digits.slice(-scale)}` : `${sign}${digits}`
}
export function documentProgress(row: WarehouseDocument): string {
  if (row.reversed) return '已冲销，原单保留'
  if (row.kind === 'CORRECTION') return `冲销${row.data.reversed_kind === 'RECEIPT' ? '入库，扣回' : row.data.reversed_kind === 'TRANSFER' ? '移库，退回原仓位' : '发出，恢复库存'} ${row.data.quantity} ${row.data.unit}`
  if (row.kind === 'REQUEST') return `申请 ${row.data.quantity} · 已发 ${row.issued_quantity ?? '0'} · 待发 ${remaining(row.data.quantity, row.issued_quantity)} ${row.data.unit}`
  if (row.kind === 'TASK') return `计划产出 ${row.data.quantity} · 已回 ${row.received_quantity ?? '0'} ${row.data.unit}`
  if (row.kind === 'PROCESS_SEND') return `待核销 ${remaining(row.data.quantity, row.consumed_quantity)} ${row.batch_snapshot?.unit ?? ''} · 已回 ${row.returned_quantity ?? '0'}（产出单位见任务）`
  if (row.kind === 'PACK_SEND') return `实发 ${row.data.quantity} · 接收 ${row.received_quantity ?? '0'} · 退回 ${row.returned_quantity ?? '0'} ${row.batch_snapshot?.unit ?? ''}`
  return row.kind === 'QUALITY' ? qualityLabels[row.data.quality_status] : '已登记'
}

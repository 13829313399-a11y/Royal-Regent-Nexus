import type { WarehouseDocument, WarehouseDomain, WarehouseOperationKind, WarehouseQuality } from '@/api/warehouseOperations'
import type { Batch, SubOrder } from '@/api/fabricSubcontract'

export const operationLabels: Record<WarehouseOperationKind, string> = {
  CUTTING_REQUEST_REUSE: '确认领料申请续用', REQUEST_CLOSE: '关闭申请余量', CUTTING_RECEIPT: '裁床物料签收', CUTTING_RECEIPT_VOID: '撤销裁床签收',
  OPENING: '期初库存', STOCKTAKE: '盘点差异', SEMI_RELEASE: '登记放产明细',
  RECEIPT: '登记实收', REQUEST: '登记领料申请', ISSUE: '登记出库', RETURN: '登记退料', TRANSFER: '登记调仓',
  LOCATION_BIND: '核实仓位', QUALITY: '登记质检结论', CORRECTION: '冲销录错单据', TASK: '登记加工任务', PROCESS_SEND: '登记加工发出',
  PROCESS_RETURN: '登记加工回货', PACK_SEND: '登记包装发出', PACK_RECEIVE: '代录包装接收回执',
}
export const qualityLabels: Record<WarehouseQuality, string> = { PENDING_INSPECTION: '待检', QUALIFIED: '合格', REJECTED: '不合格', HOLD: '暂停' }
export function fabricOperationLabel(kind: WarehouseOperationKind) {
  return kind === 'RECEIPT' ? '入库' : operationLabels[kind]
}
export function sumQuantities(values: string[]): string {
  const scale = Math.max(0, ...values.map(value => (value.split('.')[1] ?? '').length))
  const sum = values.reduce((total, value) => { const [whole, fraction = ''] = value.split('.'); return total + BigInt(`${whole}${fraction.padEnd(scale, '0')}`) }, 0n)
  const digits = sum.toString().padStart(scale + 1, '0')
  return scale ? `${digits.slice(0, -scale)}.${digits.slice(-scale)}`.replace(/\.?0+$/, '') : digits
}
export function operationsView(domain: WarehouseDomain, section: string, view: string): { stock: boolean; kinds: WarehouseOperationKind[]; actions: WarehouseOperationKind[]; progress?: boolean } | undefined {
  if (section === 'overview') return { stock: false, kinds: [], actions: domain === 'fabric' ? ['REQUEST'] : ['TASK', 'RECEIPT'] }
  if (section === 'activity') return { stock: false, kinds: [], actions: [] }
  if (section === 'exceptions' && view !== 'missing') return { stock: view === 'holds', kinds: view === 'holds' ? [] : domain === 'fabric' ? ['CORRECTION'] : ['CORRECTION', 'RETURN'], actions: domain === 'fabric' ? [] : ['CORRECTION'] }
  if (domain === 'semi' && section === 'orders' && view === 'progress') return { stock: false, kinds: ['SEMI_RELEASE'], actions: ['SEMI_RELEASE'], progress: true }
  if (domain === 'semi' && section === 'orders' && view === 'tasks') return { stock: false, kinds: ['TASK'], actions: ['TASK'] }
  if (domain === 'semi' && section === 'receipts' && view === 'pending') return { stock: false, kinds: ['SEMI_RELEASE'], actions: ['RECEIPT'], progress: true }
  if (domain === 'semi' && section === 'receipts' && view !== 'import-review') return {
    stock: false, kinds: view === 'processing-returns' ? ['PROCESS_RETURN'] : ['RECEIPT', 'PROCESS_RETURN', 'RETURN'],
    actions: view === 'processing-returns' ? ['PROCESS_RETURN'] : ['RECEIPT'],
  }
  if (section !== 'inventory') return undefined
  const map: Record<string, { stock: boolean; kinds: WarehouseOperationKind[]; actions: WarehouseOperationKind[] }> = {
    stock: { stock: true, kinds: [], actions: ['ISSUE', 'TRANSFER'] },
    'pending-issues': { stock: false, kinds: ['REQUEST'], actions: domain === 'fabric' ? [] : ['REQUEST', 'ISSUE'] },
    issues: { stock: false, kinds: ['ISSUE'], actions: domain === 'fabric' ? [] : ['ISSUE'] },
    returns: { stock: false, kinds: ['RETURN'], actions: domain === 'fabric' ? [] : ['RETURN'] },
    transfers: { stock: false, kinds: ['TRANSFER'], actions: domain === 'fabric' ? [] : ['TRANSFER'] },
    movements: { stock: false, kinds: [], actions: [] },
    processing: { stock: false, kinds: ['PROCESS_SEND'], actions: ['PROCESS_SEND', 'PROCESS_RETURN'] },
    packaging: { stock: false, kinds: ['PACK_SEND', 'PACK_RECEIVE'], actions: ['PACK_SEND', 'PACK_RECEIVE'] },
  }
  return map[view]
}
export function referenceKinds(kind: WarehouseOperationKind): WarehouseOperationKind[] {
  if (kind === 'REQUEST_CLOSE') return ['REQUEST']
  if (kind === 'ISSUE') return ['REQUEST']
  if (kind === 'RETURN') return ['ISSUE', 'PACK_SEND']
  if (kind === 'PROCESS_RETURN') return ['PROCESS_SEND']
  if (kind === 'PACK_RECEIVE') return ['PACK_SEND']
  if (kind === 'CORRECTION') return ['RECEIPT', 'ISSUE', 'RETURN', 'TRANSFER', 'PROCESS_SEND', 'PACK_SEND', 'SEMI_RELEASE', 'TASK']
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

export function pendingHandoffQuantity(row: WarehouseDocument): string | undefined {
  if (row.reversed) return undefined
  let pending: string
  if (row.kind === 'PROCESS_SEND') pending = remaining(row.data.quantity, row.consumed_quantity)
  else if (row.kind === 'PACK_SEND') pending = remaining(remaining(row.data.quantity, row.received_quantity), row.returned_quantity)
  else return undefined
  return Number(pending) > 0 ? pending : undefined
}

export function sendableSubcontractInputs(inputs: SubOrder['inputs'], stock: Batch[]) {
  const currentStock = new Map(stock.map(batch => [batch.id, batch]))
  return inputs.flatMap(input => {
    const batch = currentStock.get(input.id)
    const plannedRemainder = remaining(input.planned, input.sent)
    if (!batch?.available || Number(batch.available) <= 0 || Number(plannedRemainder) <= 0) return []
    const max = remaining(plannedRemainder, batch.available).startsWith('-') ? plannedRemainder : batch.available
    return [{ batch, max }]
  })
}
export function hasUnissuedRemainder(row: WarehouseDocument): boolean {
  return row.kind === 'REQUEST' && !row.reversed && !row.closed && Number(remaining(row.data.quantity, row.issued_quantity)) > 0
}
export function documentProgress(row: WarehouseDocument, outputUnit?: string): string {
  if (row.reversed) return '已冲销，原单保留'
  if (row.kind === 'CORRECTION') {
    if (row.data.reversed_kind === 'SEMI_RELEASE') return '已冲销放产明细，原记录保留'
    if (row.data.reversed_kind === 'TASK') return '已冲销加工任务，原记录保留'
    const direction = row.data.reversed_kind === 'RETURN' ? '退料入库，扣回库存'
      : row.data.reversed_kind === 'RECEIPT' ? '入库，扣回库存'
      : row.data.reversed_kind === 'TRANSFER' ? '移库，退回原仓位' : '发出，恢复库存'
    return `冲销${direction} ${row.data.quantity} ${row.data.unit}`
  }
  if (row.kind === 'REQUEST' && row.closed) return `已关闭未发余量；已发 ${row.issued_quantity ?? '0'} ${row.data.unit} · ${row.close_reason ?? ''}`
  if (row.kind === 'REQUEST') return `申请 ${row.data.quantity} · 已发 ${row.issued_quantity ?? '0'} · 待发 ${remaining(row.data.quantity, row.issued_quantity)} ${row.data.unit}`
  if (row.kind === 'TASK') return `计划产出 ${row.data.quantity} · 已回 ${row.received_quantity ?? '0'} ${row.data.unit}`
  if (row.kind === 'PROCESS_SEND') return `待核销 ${remaining(row.data.quantity, row.consumed_quantity)} ${row.batch_snapshot?.unit ?? ''} · 已回 ${row.returned_quantity ?? '0'}${outputUnit ? ` ${outputUnit}` : '（产出单位见任务）'}`
  if (row.kind === 'PACK_SEND') return `实发 ${row.data.quantity} · 接收 ${row.received_quantity ?? '0'} · 退回 ${row.returned_quantity ?? '0'} ${row.batch_snapshot?.unit ?? ''}`
  return row.kind === 'QUALITY' ? qualityLabels[row.data.quality_status] : '已登记'
}

import type { PortalOrder, PortalShipment } from '@/api/cartonSupplierPortal'
import type { SpecialRequest } from '@/api/cartonSpecialRequests'

export function specialSupplierOrigin(order: SpecialRequest) {
  return order.origin === 'SUPPLIER_EXTRA' || order.kind === 'SUPPLIER_GIFT' || order.supplier_confirmation?.status === 'SUPPLIER_ORIGIN'
}
export function specialSupplierActive(order: SpecialRequest) {
  return !order.deleted && ['SENT', 'QUOTED', 'READY', 'PARTIALLY_RECEIVED'].includes(order.status)
    && order.lines.some(line => Number(line.quantity) > 0)
}
export function specialSupplierAccepted(order: SpecialRequest) {
  return specialSupplierOrigin(order) || Boolean(order.current_version_id && order.supplier_confirmation?.version_id === order.current_version_id
    && order.supplier_confirmation.status === 'ACCEPTED')
}
export function specialSupplierNeedsAcceptance(order: SpecialRequest) {
  return specialSupplierActive(order) && !specialSupplierAccepted(order)
}
export function specialSupplierCanPromise(order: SpecialRequest) {
  return specialSupplierActive(order) && Boolean(order.current_version_id) && !specialSupplierOrigin(order)
}
export function specialSupplierPromise(order: SpecialRequest) {
  return specialSupplierAccepted(order) ? order.supplier_confirmation?.promised_date || order.promised_date || '' : ''
}
export function specialSupplierStage(order: SpecialRequest) {
  if (order.status === 'COMPLETED' || order.status === 'CANCELLED') return order.status
  if (!specialSupplierActive(order) || !order.current_version_id) return 'PENDING_ISSUE'
  if (order.shipments.some(shipment => shipment.lines.some(line => Number(line.remaining_quantity) > 0))) return 'RECEIPT_PENDING'
  if (specialSupplierOrigin(order)) return 'WAITING_SHIPMENT'
  if (specialSupplierNeedsAcceptance(order)) return 'PENDING_ACCEPTANCE'
  if (order.status === 'PARTIALLY_RECEIVED' && order.lines.some(line => Number(line.remaining_to_ship ?? line.remaining_quantity ?? line.quantity) > 0)) return 'WAITING_SHIPMENT'
  return 'ACCEPTED'
}

export function awaitsWarehouseReceipt(shipment: PortalShipment) {
  return Boolean(shipment.requires_correction || shipment.receipt_status === 'REVERSED'
    || shipment.status === 'SENT')
}

export function supplierWorkCounts(orders: PortalOrder[], shipments: PortalShipment[], special: SpecialRequest[] = []) {
  const active = orders.filter(order => !order.awaiting_issue && ['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED'].includes(order.status))
  return {
    acceptance: active.filter(order => order.lines.some(line => Number(line.required_quantity) > 0 && !line.accepted)).length + special.filter(specialSupplierNeedsAcceptance).length,
    shipment: active.filter(order => order.lines.filter(line => Number(line.required_quantity) > 0).every(line => line.accepted)
      && order.lines.some(line => Number(line.remaining_to_ship) > 0 && !line.shipping_blocked_reason)).length
      + special.filter(order => specialSupplierActive(order) && specialSupplierAccepted(order) && order.lines.some(line => Number(line.remaining_to_ship ?? line.remaining_quantity ?? line.quantity) > 0)).length,
    receipt: shipments.filter(awaitsWarehouseReceipt).length,
  }
}

export function specialSupplierStatusLabel(row: SpecialRequest) {
  const stage = specialSupplierStage(row)
  if (stage === 'COMPLETED') return '已完成'
  if (stage === 'CANCELLED') return '已取消'
  if (row.supplier_confirmation?.version_id === row.current_version_id && row.supplier_confirmation?.status === 'DISPUTED') return '有异议 · 待接单'
  if (stage === 'PENDING_ACCEPTANCE') return '待接单'
  if (stage === 'PENDING_ISSUE') return '变更待生成'
  const delivery = stage === 'RECEIPT_PENDING' ? '待仓库验收' : stage === 'WAITING_SHIPMENT' ? '待送货' : '已确认接单'
  if (row.status === 'PARTIALLY_RECEIVED') return `部分收料 · ${delivery}`
  return delivery
}

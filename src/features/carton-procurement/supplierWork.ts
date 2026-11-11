import type { PortalOrder, PortalShipment } from '@/api/cartonSupplierPortal'
import type { SpecialRequest } from '@/api/cartonSpecialRequests'
import { shipmentNeedsReceipt } from './receiptDisplay'

function regularSupplierActive(order: PortalOrder) {
  return !order.awaiting_issue && ['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED'].includes(order.status)
}

export function regularSupplierCanShip(order: PortalOrder) {
  if (!order.issue_id || !regularSupplierActive(order)) return false
  const papers = order.lines.filter(line => Number(line.required_quantity) > 0)
  return papers.every(line => line.accepted)
    && papers.some(line => Number(line.remaining_to_ship) > 0 && !line.shipping_blocked_reason)
}

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

export function specialSupplierCanShip(order: SpecialRequest) {
  return Boolean(order.current_version_id) && specialSupplierActive(order) && specialSupplierAccepted(order)
    && order.lines.some(line => Number(line.quantity) > 0 && Number(line.remaining_to_ship ?? line.remaining_quantity ?? line.quantity) > 0)
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
  if (specialSupplierNeedsAcceptance(order)) return 'PENDING_ACCEPTANCE'
  if ((specialSupplierOrigin(order) || order.status === 'PARTIALLY_RECEIVED') && specialSupplierCanShip(order)) return 'WAITING_SHIPMENT'
  return 'ACCEPTED'
}

export function supplierWorkCounts(orders: PortalOrder[], shipments: PortalShipment[], special: SpecialRequest[] = []) {
  const active = orders.filter(regularSupplierActive)
  return {
    acceptance: active.filter(order => order.lines.some(line => Number(line.required_quantity) > 0 && !line.accepted)).length + special.filter(specialSupplierNeedsAcceptance).length,
    shipment: orders.filter(regularSupplierCanShip).length + special.filter(specialSupplierCanShip).length,
    receipt: shipments.filter(shipmentNeedsReceipt).length,
  }
}

export function specialSupplierStatusLabel(row: SpecialRequest) {
  const stage = specialSupplierStage(row)
  if (stage === 'COMPLETED') return '已完成'
  if (stage === 'CANCELLED') return '已取消'
  if (row.supplier_confirmation?.version_id === row.current_version_id && row.supplier_confirmation?.status === 'DISPUTED') return '有异议 · 待接单'
  if (stage === 'PENDING_ACCEPTANCE') return '待接单'
  if (stage === 'PENDING_ISSUE') return '变更待生成'
  const delivery = stage === 'RECEIPT_PENDING' ? '待仓库验收' : stage === 'WAITING_SHIPMENT' ? '待发货' : '已确认接单'
  if (row.status === 'PARTIALLY_RECEIVED') return `部分收料 · ${delivery}`
  return delivery
}

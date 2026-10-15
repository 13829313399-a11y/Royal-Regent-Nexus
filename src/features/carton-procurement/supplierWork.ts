import type { PortalOrder, PortalShipment } from '@/api/cartonSupplierPortal'

export function awaitsWarehouseReceipt(shipment: PortalShipment) {
  return Boolean(shipment.requires_correction || shipment.receipt_status === 'REVERSED'
    || shipment.status === 'SENT')
}

export function supplierWorkCounts(orders: PortalOrder[], shipments: PortalShipment[]) {
  const active = orders.filter(order => !order.awaiting_issue && ['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED'].includes(order.status))
  return {
    acceptance: active.filter(order => order.lines.some(line => Number(line.required_quantity) > 0 && !line.accepted)).length,
    shipment: active.filter(order => order.lines.filter(line => Number(line.required_quantity) > 0).every(line => line.accepted)
      && order.lines.some(line => Number(line.remaining_to_ship) > 0 && !line.shipping_blocked_reason)).length,
    receipt: shipments.filter(awaitsWarehouseReceipt).length,
  }
}

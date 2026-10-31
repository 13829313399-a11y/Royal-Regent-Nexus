import type { PortalShipment } from '@/api/cartonSupplierPortal'
import type { Tone } from '@/data/enterpriseMock'

export function shipmentNeedsReceipt(shipment: PortalShipment) {
  return ['SENT', 'RECEIPT_REVERSED'].includes(shipment.status) || Boolean(shipment.requires_correction || shipment.receipt_status === 'REVERSED')
}

/** Display only: processed notes may include closures or rejected goods. */
export function shipmentReceiptDisplay(shipment: PortalShipment): { label: string; tone: Tone } {
  if (shipment.requires_correction || shipment.status === 'RECEIPT_REVERSED' || shipment.receipt_status === 'REVERSED') return { label: '待更正', tone: 'amber' }
  const arrived = shipment.lines.some(line => Number(line.received_quantity) > 0)
  if (shipmentNeedsReceipt(shipment)) return arrived || shipment.partially_received
    ? { label: '部分已收', tone: 'amber' } : { label: '未收货', tone: 'blue' }
  if (shipment.status === 'NOT_RECEIVED') return { label: '零到货关闭', tone: 'slate' }
  if (shipment.lines.length && shipment.lines.every(line => Number(line.quantity) > 0 && Number(line.rejected_quantity) >= Number(line.quantity))) return { label: '已拒收退回', tone: 'red' }
  if (shipment.lines.some(line => Number(line.closed_quantity) > 0)) return { label: arrived ? '短送结束' : '零到货关闭', tone: 'slate' }
  if (shipment.status === 'RECEIVED' && shipment.lines.length && shipment.lines.every(line => Number(line.quantity) > 0 && Number(line.received_quantity) >= Number(line.quantity))) return { label: '已收齐', tone: 'green' }
  return { label: '已处理', tone: 'slate' }
}

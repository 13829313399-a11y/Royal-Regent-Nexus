import { describe, expect, it } from 'vitest'
import { supplierWorkCounts } from '../supplierWork'
import { emptyShipmentFilters, filterShipments } from '../queryFilters'
import type { PortalOrder, PortalShipment } from '@/api/cartonSupplierPortal'

describe('supplier work queues', () => {
  it('counts unmatched notes and reversals, while partial dispatch may also leave work to ship', () => {
    const orders = [
      { status: 'PENDING_SUPPLIER', lines: [{ required_quantity: '100', remaining_to_ship: '40', accepted: true, in_transit_quantity: '60' }] },
      { status: 'PENDING_SUPPLIER', lines: [{ required_quantity: '100', remaining_to_ship: '100', accepted: false }] },
      { status: 'CANCELLED', lines: [{ required_quantity: '100', remaining_to_ship: '100', accepted: false }] },
    ] as PortalOrder[]
    const shipments = [
      { id: 'unmatched', status: 'SENT', lines: [{ order_line_id: null }] },
      { id: 'normal', status: 'SENT', lines: [] },
      { id: 'partial', status: 'SENT', receipt_status: 'POSTED', partially_received: true, lines: [] },
      { id: 'reversal', status: 'RECEIVED', receipt_status: 'REVERSED', lines: [] },
      { id: 'posted', status: 'RECEIVED', receipt_status: 'POSTED', lines: [] },
      { id: 'not-delivered', status: 'NOT_RECEIVED', lines: [] },
    ].map(row => ({ created_at: '', delivery_date: '2026-10-15', ...row })) as PortalShipment[]
    expect(supplierWorkCounts(orders, shipments)).toEqual({ acceptance: 1, shipment: 1, receipt: 4 })
    expect(filterShipments(shipments, { ...emptyShipmentFilters(), status: 'PENDING_RECEIPT' }).map(row => row.id).sort()).toEqual(['normal', 'partial', 'reversal', 'unmatched'])
  })
})

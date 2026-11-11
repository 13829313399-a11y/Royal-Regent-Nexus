import { describe, expect, it } from 'vitest'
import { supplierWorkCounts, specialSupplierAccepted, specialSupplierNeedsAcceptance, specialSupplierCanPromise, specialSupplierPromise, specialSupplierStage } from '../supplierWork'
import { emptyShipmentFilters, filterShipments } from '../queryFilters'
import type { PortalOrder, PortalShipment } from '@/api/cartonSupplierPortal'
import type { SpecialRequest } from '@/api/cartonSpecialRequests'

const special = (patch: Partial<SpecialRequest> = {}): SpecialRequest => ({
  id: 'S1', request_no: 'SP-1', factory_id: 'huaxing', kind: 'SAMPLE', status: 'SENT', revision: 3, current_version_id: 'V3', promised_date: '2026-10-24',
  required_date: '2026-10-25', lines: [{ quantity: '10', remaining_to_ship: '10', unit: '个' }], shipments: [], ...patch,
} as SpecialRequest)

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
  it.each(['SENT', 'QUOTED', 'READY'])('requires current-version confirmation rather than inferring acceptance from %s', status => {
    const row = special({ status })
    expect(specialSupplierNeedsAcceptance(row)).toBe(true)
    expect(specialSupplierPromise(row)).toBe('')
    expect(supplierWorkCounts([], [], [row])).toMatchObject({ acceptance: 1, shipment: 0 })
    expect(specialSupplierStage(row)).toBe('PENDING_ACCEPTANCE')
  })
  it('accepts the backend legacy confirmation only when it identifies the current requirement', () => {
    const row = special({ supplier_confirmation: { version_id: 'V3', status: 'ACCEPTED', promised_date: '2026-10-28', responded_at: '', responded_by: '', reason: '' } })
    expect(specialSupplierAccepted(row)).toBe(true)
    expect(specialSupplierPromise(row)).toBe('2026-10-28')
    expect(supplierWorkCounts([], [], [row])).toMatchObject({ acceptance: 0, shipment: 1 })
    row.current_version_id = 'V4'
    expect(specialSupplierAccepted(row)).toBe(false)
    expect(specialSupplierPromise(row)).toBe('')
  })
  it('keeps disputes pending and active partial orders eligible for a whole-version promise', () => {
    const row = special({ status: 'PARTIALLY_RECEIVED', supplier_confirmation: { version_id: 'V3', status: 'DISPUTED', promised_date: '2026-10-28', responded_at: '', responded_by: '', reason: '需核实' } })
    expect(specialSupplierCanPromise(row)).toBe(true)
    expect(specialSupplierStage(row)).toBe('PENDING_ACCEPTANCE')
    expect(supplierWorkCounts([], [], [row])).toMatchObject({ acceptance: 1, shipment: 0 })
    row.supplier_confirmation!.status = 'ACCEPTED'
    expect(specialSupplierStage(row)).toBe('WAITING_SHIPMENT')
  })
  it.each(['COMPLETED', 'CANCELLED'])('keeps %s sources out of acceptance and promise maintenance', status => {
    const row = special({ status })
    expect(specialSupplierCanPromise(row)).toBe(false)
    expect(supplierWorkCounts([], [], [row])).toMatchObject({ acceptance: 0, shipment: 0 })
  })
  it('exempts supplier-origin goods and gifts without inventing an internal acceptance', () => {
    const rows = [special({ origin: 'SUPPLIER_EXTRA' }), special({ kind: 'SUPPLIER_GIFT' })]
    for (const row of rows) {
      expect(specialSupplierNeedsAcceptance(row)).toBe(false)
      expect(specialSupplierCanPromise(row)).toBe(false)
      expect(specialSupplierStage(row)).toBe('WAITING_SHIPMENT')
    }
    expect(supplierWorkCounts([], [], rows)).toMatchObject({ acceptance: 0, shipment: 2 })
  })
  it('does not offer acceptance for zero-demand special sources', () => {
    const row = special({ lines: [{ ...special().lines[0]!, quantity: '0' }] })
    expect(specialSupplierCanPromise(row)).toBe(false)
    expect(specialSupplierNeedsAcceptance(row)).toBe(false)
  })
})

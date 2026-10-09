import { describe, expect, it } from 'vitest'
import { emptyShipmentFilters, filterShipments, matchesSettlementLine, settlementStage } from '../queryFilters'
import type { PortalShipment } from '@/api/cartonSupplierPortal'
import type { SettlementDocument, StatementLine, SupplierSource } from '@/api/cartonSupplierSettlement'

const shipment = (id: string, date: string, acceptance: string | null, customer = '东康客户'): PortalShipment => ({ id, delivery_note_no: id, delivery_date: date, acceptance_date: acceptance, status: 'RECEIVED', revision: 1, created_at: date, confirmed_at: '', acceptance_lines: [], lines: [{ id: id + '-line', order_line_id: 'line', order_no: 'CT-1', contract_no: 'SC-1', customer_po: 'PO-1', item_no: 'ITEM-1', customer_name: customer, child_no: '', packaging_type: '外箱', paper_quality: 'A33', specification: '1*1', unit: '个', quantity: '10' }] })
describe('carton read-only query projections', () => {
  it('uses the selected date basis inclusively and puts unrecorded dates last in both directions', () => {
    const rows = [shipment('early', '2026-09-01', '2026-10-01'), shipment('late', '2026-10-02', '2026-10-02'), shipment('undated', '2026-10-03', null)]
    const query = { ...emptyShipmentFilters(), dateField: 'ACCEPTANCE' as const, from: '2026-10-01', to: '2026-10-01' }
    expect(filterShipments(rows, query).map(row => row.id)).toEqual(['early'])
    expect(filterShipments(rows, { ...query, dateField: 'DELIVERY' })).toEqual([])
    expect(filterShipments(rows, { ...query, from: '', to: '' }).map(row => row.id)).toEqual(['late', 'early', 'undated'])
    expect(filterShipments(rows, { ...query, from: '', to: '', sort: 'ASC' }).map(row => row.id)).toEqual(['early', 'late', 'undated'])
  })
  it('combines customer, correction status, unmatched-order and literal identity queries without mutating the source', () => {
    const correct = { ...shipment('DN-%', '2026-10-01', null), status: 'RECEIPT_REVERSED' }
    correct.lines[0]!.order_line_id = null
    const rows = [shipment('other', '2026-10-01', null, '其他客户'), correct]
    const query = { ...emptyShipmentFilters(), search: '%', customer: '东康客户', status: 'RECEIPT_REVERSED', association: 'UNMATCHED' }
    expect(filterShipments(rows, query).map(row => row.id)).toEqual(['DN-%'])
    expect(rows.map(row => row.id)).toEqual(['other', 'DN-%'])
    expect(filterShipments(rows, { ...query, search: 'PO-1', association: 'MATCHED' })).toEqual([])
  })
  it('finds settlement notes, unmatched sources and exact difference evidence without changing amounts', () => {
    const line = { id: 'L1', source_key: 'S1', document_no: 'DN-1', note: '退货依据', quantity: '2', unit_price: '1', amount: '2' } as StatementLine
    const source = { source_key: 'S1', kind: 'RECEIPT', contract_no: 'SC1', item_no: 'I1', issues: [] } as unknown as SupplierSource
    expect(matchesSettlementLine(line, source, undefined, '退货依据', 'UNMATCHED')).toBe(true)
    expect(matchesSettlementLine(line, source, { id: 'L1', source_key: 'S1', issues: [], quantity_difference: '0.0000', price_difference: '0.000001', amount_difference: '0' }, '', 'DIFFERENCE')).toBe(true)
    expect(matchesSettlementLine(line, source, { id: 'L1', source_key: 'S1', issues: [], quantity_difference: '0', price_difference: '0', amount_difference: '0' }, '', 'DIFFERENCE')).toBe(false)
    expect(line.amount).toBe('2')
  })
  it('keeps stale or superseded acknowledgements distinct from effective supplier confirmation', () => {
    const doc = { status: 'DRAFT', stale: false, result: { supplier_review: { decision: 'CONFIRMED' } } } as SettlementDocument
    expect(settlementStage(doc)).toBe('INTERNAL_PENDING')
    expect(settlementStage({ ...doc, stale: true })).toBe('STALE')
    expect(settlementStage({ ...doc, stale: true, status: 'SUPERSEDED' })).toBe('HISTORY')
    expect(settlementStage({ ...doc, result: { ...doc.result, supplier_review: { ...doc.result.supplier_review!, decision: 'DISPUTED' } } })).toBe('DISPUTED')
  })
})

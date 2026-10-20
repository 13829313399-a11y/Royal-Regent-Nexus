import { describe, expect, it } from 'vitest'
import { toPortalShipment, unifiedDeliveryLineKind, type UnifiedDelivery, type UnifiedDeliveryLine } from '../cartonUnifiedDeliveries'
import type { SpecialRequest } from '../cartonSpecialRequests'

const paper = (id: string, request: string): UnifiedDeliveryLine => ({
  id, special_request_id: request, source_kind: 'SPECIAL', order_line_id: null,
  order_no: '', contract_no: '', customer_po: '', item_no: '', customer_name: '', child_no: '',
  packaging_type: '外箱', paper_quality: '', specification: '', unit: '个', quantity: '1',
})
const request = (id: string, kind: SpecialRequest['kind'], origin = 'INTERNAL') => ({
  id, kind, origin, shipments: [{ receipts: [] }],
}) as unknown as SpecialRequest
function group(): UnifiedDelivery {
  return { id: 'G', factory_id: 'huaxing', delivery_note_no: 'DN', delivery_date: '2026-10-20', created_at: '', formal: null,
    special: [request('S', 'SAMPLE'), request('M', 'WORKSHOP_MISC'), request('X', 'WORKSHOP_MISC', 'SUPPLIER_EXTRA'), request('G', 'SUPPLIER_GIFT')],
    lines: [paper('S1', 'S'), paper('M1', 'M'), { ...paper('X1', 'X'), origin: 'SUPPLIER_EXTRA' }, paper('G1', 'G')],
    receipts: [], status: 'SENT', revision: 1, requires_correction: false, can_operate: true }
}
describe('unified delivery business type projection', () => {
  it('uses explicit request identity and leaves unreviewed extras and old gifts unclassified', () => {
    const source = group()
    expect(toPortalShipment(source).lines.map(line => line.business_kind)).toEqual(['SAMPLE', 'MISC', 'UNKNOWN', 'UNKNOWN'])
    expect(source.lines.every(line => line.business_kind === undefined)).toBe(true)
    expect(toPortalShipment(source).lines).toHaveLength(4)
  })
  it('uses the warehouse-confirmed use of extra papers, including after reversal', () => {
    const source = group(), extra = source.special[2]!
    extra.kind = 'SAMPLE'
    extra.shipments[0]!.receipts.push({ id: 'R', status: 'REVERSED' })
    expect(unifiedDeliveryLineKind(source, source.lines[2]!)).toBe('SAMPLE')
  })
  it('retains legacy unmatched status even when a historical review has a linked internal line', () => {
    const source = group(), line = { ...paper('F1', ''), source_kind: 'FORMAL' as const, order_line_id: 'legacy', source_type: 'AD_HOC_REVIEW' }
    expect(unifiedDeliveryLineKind(source, line)).toBe('UNKNOWN')
    expect(unifiedDeliveryLineKind(source, { ...line, source_type: 'FORMAL_ORDER' })).toBe('REGULAR')
  })
})

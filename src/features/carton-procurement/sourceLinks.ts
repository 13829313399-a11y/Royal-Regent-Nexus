export interface CartonSourceRequest {
  id: string; request_no: string; kind: string; line_id?: string; shipment_id?: string; delivery_id?: string
}
export const sourceKindLabel = (kind: string) => ({ PURCHASE: '正单', SAMPLE: '样板单', WORKSHOP_MISC: '杂单', SUPPLIER_GIFT: '历史赠送', LEGACY: '其他历史' })[kind] || kind
export function sourceRequestRoute(factory: string, source: CartonSourceRequest, supplier = false, marks = false) {
  return { path: supplier ? '/carton-supplier' : '/modules/pmc-warehouse/carton-procurement',
    query: { factory, tab: marks ? 'carton-marks' : 'orders', ...(marks ? { mark_request: source.id, mark_line: source.line_id } : { special_request: source.id }) } }
}
export function sourceDeliveryRoute(factory: string, id: string) {
  return { path: '/modules/pmc-warehouse/carton-procurement', query: { factory, tab: 'receipts', receipt_page: 'supplier', shipment: id } }
}

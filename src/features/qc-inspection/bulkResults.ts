import type { QcInspectionEvent, QcInspectionEventPayload, QcInspectionOrder } from '@/api/qcInspection'

export const inspectionResults: Record<string, string> = { PASS: 'PASS · 通过', FAIL: 'FAIL · 不通过', CONDITIONAL_PASS: '有条件通过', REJECTED: '拒收', CANCELLED: '取消' }
export const inspectionTypes = { CUSTOMER: '客验', THIRD_PARTY: '第三方', LINE: '巡线', SELF: '自检', REINSPECTION: '复验', SAMPLE: '抽检' }
export interface BulkResultForm { date: string; result: string; inspector: string; note: string; eventType: keyof typeof inspectionTypes | '' }

export function bulkResultPayload(order: QcInspectionOrder, form: BulkResultForm, latest?: QcInspectionEvent): QcInspectionEventPayload {
  if (latest && latest.inspection_result !== 'PENDING') throw new Error('已有验货结果，请打开订单详情核对。')
  let payload: QcInspectionEventPayload
  if (latest) {
    const { id: _id, revision: _revision, attempt_no: _attempt, created_at: _created, updated_at: _updated,
      created_by: _creator, created_by_name: _creatorName, updated_by: _editor, updated_by_name: _editorName, ...values } = latest
    payload = structuredClone(values)
  } else {
    if (!form.eventType) throw new Error('请选择新记录的验货类型。')
    payload = {
      factory_id: order.factory_id, inspection_order_id: order.id, event_type: form.eventType, actual_inspection_date: '',
      inspector_name: '', inspection_agency: order.inspection_agency || '', inspection_location: '',
      sampling_standard: '', inspection_level: '', aql_critical: '', aql_major: '', aql_minor: '',
      lot_size: 0, sample_size: 0, critical_defect_count: 0, major_defect_count: 0, minor_defect_count: 0,
      inspection_result: 'PENDING', document_status: 'DRAFT', manual_has_problem: Boolean(order.manual_has_problem), report_number: '', note: '',
      lines: [{ customer_po_no: order.customer_po_no, customer_item_no: order.customer_item_no, product_name: order.product_name,
        order_quantity: order.quantity, inspected_quantity: null, packing: order.packing || '', carton_count: order.carton_count || '',
        release_no: '', internal_item_no: '', batch_no: '', date_code: '', upc_ean: '' }], defects: [], tests: [], dispositions: [],
    }
  }
  return { ...payload, expected_pending_order_revision: order.revision, actual_inspection_date: form.date,
    inspection_result: form.result, inspector_name: form.inspector.trim() || payload.inspector_name,
    note: [payload.note, form.note.trim()].filter(Boolean).join('\n') }
}

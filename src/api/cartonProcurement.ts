import { http } from '@/lib/http'
import { postCartonInventoryRequest } from './cartonInventoryRequest'
import type { SplitRecord } from './cartonOrderSplits'

export interface CartonCustomerResponse {
  id: string
  factory_id: string
  customer_code: string
  customer_name: string
  country_region: string
  contact_name: string
  contact_phone: string
  note: string
  status: 'ACTIVE' | 'INACTIVE'
  revision: number
  created_by: string
  created_by_name: string
  updated_by: string
  updated_by_name: string
  created_at: string
  updated_at: string
}

export interface CartonCustomerSaveRequest {
  factory_id: string
  customer_code: string
  customer_name: string
  country_region: string
  contact_name: string
  contact_phone: string
  note: string
  status: 'ACTIVE' | 'INACTIVE'
}

export interface CartonReplenishmentOption { replenishment_issue_id: string; document_no: string; responsibility: 'OWN' | 'SUPPLIER'; remaining_quantity: string }
export interface CartonOrderLineResponse {
  replenishment_review_required?: boolean
  replenishment_options?: CartonReplenishmentOption[]
  replenished_quantity?: string
  id: string
  line_no: number
  packaging_type: string
  paper_quality: string
  specification: string
  dimension_unit: string
  usage_quantity: string | null
  required_quantity: string
  received_quantity: string
  remaining_quantity: string
  pending_received_quantity?: string
  maximum_reducible_quantity?: string
  unit: string
  unit_price: string
  currency: string
  price_source: string
  note: string
}

export interface CartonSupplierAcceptanceResponse {
  status: 'NOT_ISSUED' | 'PENDING' | 'PARTIAL' | 'ACCEPTED' | 'PENDING_CHANGE' | 'NOT_REQUIRED' | 'CANCELLED'
  label: string
  issue_id: string
  document_no: string
  total_line_count: number
  accepted_line_count: number
  accepted_at: string
}

export interface CartonOrderResponse {
  supplier_acceptance?: CartonSupplierAcceptanceResponse
  split_records?: SplitRecord[]
  can_delete?: boolean
  deletion_block_reason?: string
  can_delete_history?: boolean
  customer_po?: string
  usage_status?: string
  usage_status_label?: string
  id: string
  factory_id: string
  order_no: string
  customer_code: string
  customer_name: string
  supplier_id: string
  supplier_name: string
  contract_no: string
  item_no: string
  product_name: string
  quantity_basis?: 'CALCULATED' | 'EXPLICIT'
  product_order_quantity: string | null
  order_date: string
  customer_due_date?: string | null
  safety_lead_days?: number
  due_date: string
  status: string
  note: string
  revision: number
  created_by: string
  created_by_name: string
  updated_by: string
  updated_by_name: string
  created_at: string
  updated_at: string
  maximum_reducible_quantity?: string | null
  lines: CartonOrderLineResponse[]
}

export type CartonPurchaseOrderDocumentType = 'LEGACY_BASELINE' | 'INITIAL' | 'APPEND' | 'REDUCE' | 'ADJUSTMENT'

export interface CartonPurchaseOrderIssueResponse {
  is_replenishment?: boolean
  id: string
  factory_id: string
  order_no: string
  document_no: string
  document_type: CartonPurchaseOrderDocumentType
  issue_sequence: number
  source_order_revision: number
  before_product_quantity: string | null
  after_product_quantity: string | null
  product_quantity_delta: string | null
  generated_by: string
  generated_by_name: string
  generated_at: string
}

export interface CartonPurchaseOrderContextResponse {
  factory_id: string
  order_no: string
  order_revision: number
  pending_type: 'NONE' | 'INITIAL' | 'APPEND' | 'REDUCE' | 'ADJUSTMENT'
  pending_product_quantity: string | null
  pending_line_count: number
  can_generate: boolean
  latest_document_no: string
  historical_baseline: boolean
  issues: CartonPurchaseOrderIssueResponse[]
}

export interface CartonOrderCreateRequest {
  schedule_source?: { batch_id: string; source_sheet: string; source_row: number }
  customer_po?: string
  master_config_id?: string
  master_config_revision?: number
  factory_id: string
  customer_code: string
  customer_name: string
  supplier_id?: string
  contract_no: string
  item_no: string
  product_name?: string
  quantity_basis?: 'CALCULATED' | 'EXPLICIT'
  product_order_quantity: number | null
  order_date: string
  customer_due_date?: string | null
  due_date: string
  status: 'CONFIRMED'
  note: string
  lines: Array<{
    packaging_type: string
    paper_quality: string
    specification: string
    dimension_unit: string
    usage_quantity: number | null
    required_quantity?: number
    unit: string
    unit_price?: number
    currency?: string
    price_source?: string
    note?: string
  }>
}

export type CartonOrderUpdateRequest = Omit<CartonOrderCreateRequest, 'status' | 'schedule_source'> & {
  reason: string
}

export interface CartonHistoryOrderImportResponse {
  factory_id: string
  original_filename: string
  row_count: number
  group_count: number
  imported_count: number
  imported_line_count: number
  skipped_count: number
  imported_orders: string[]
  skipped_orders: string[]
  warnings: string[]
}

export interface CartonOrderHistorySuggestionResponse {
  item_no: string
  customer_code: string
  customer_name: string
  product_name: string
  latest_order_no: string
  latest_contract_no: string
  latest_order_date: string
  latest_product_order_quantity: string | null
  order_count: number
  match_type: 'EXACT' | 'PREFIX' | 'CONTAINS' | 'SIMILAR'
  match_score: number
  lines: Array<{
    line_no: number
    packaging_type: string
    paper_quality: string
    specification: string
    dimension_unit: string
    usage_quantity: string | null
    unit: string
    unit_price: string
    currency: string
    price_source: string
    note: string
  }>
}

export interface CartonHistoryInventoryImportResponse {
  factory_id: string
  original_filename: string
  row_count: number
  imported_count: number
  skipped_count: number
  matched_order_line_count: number
  standalone_count: number
  total_quantity: string
  duplicate: boolean
  movement_ids: string[]
  warnings: string[]
}

export interface OpeningInventoryOptions {
  customer_name: string
  warehouse: string
  snapshot_date?: string
  dimension_unit: 'cm' | 'in'
  currency: string
}
export interface OpeningInventoryPreview {
  factory_id: string; original_filename: string; source_fingerprint: string
  row_count: number; skipped_count: number; missing_price_count: number
  warnings: string[]; errors: string[]
  rows: Array<{ source: string; customer_name: string; contract_no: string; item_no: string
    packaging_type: string; paper_quality: string; specification: string; unit: string
    opening_quantity: string; unit_price: string | null; amount: string | null
    currency: string; location: string; warehouse?: string; original_inbound_at?: string; occurred_at?: string; status: 'READY' | 'DUPLICATE' | 'ZERO'; warnings: string[] }>
  totals: Array<{ unit: string; currency: string; quantity: string; amount: string | null; missing_price_count: number }>
}

export interface CartonInventoryMovementResponse {
  cost_status?: string
  cost_currency?: string
  cost_amount?: string | null
  cost_unit_price?: string | null
  workshop_id?: string
  workshop_name?: string
  id: string
  factory_id: string
  order_line_id: string | null
  customer_code: string
  customer_name: string
  contract_no: string
  item_no: string
  packaging_type: string
  paper_quality: string
  specification: string
  movement_type: 'INBOUND' | 'OUTBOUND' | 'ADJUSTMENT' | 'REVERSAL'
  quantity: string
  balance: string
  unit: string
  unit_price: string
  currency: string
  location: string
  document_no: string
  source_type: string
  source_id: string
  source_line_id: string
  reversal_of_movement_id: string | null
  reason: string
  actor_user_id: string
  actor_name: string
  occurred_at: string
}

export interface CartonInventoryBalanceResponse {
  inbound_quantity?: string | null
  outbound_quantity?: string | null
  opening_quantity?: string | null
  transfer_quantity?: string | null
  adjustment_quantity?: string | null
  cost_status?: string
  cost_currency?: string
  cost_amount?: string | null
  cost_unit_price?: string | null
  position_key?: string
  inventory_key?: string
  location_id?: string
  warehouse?: string
  bin_code?: string
  position_revision?: number
  factory_id: string
  customer_code: string
  customer_name: string
  contract_no: string
  item_no: string
  order_line_id: string | null
  packaging_type: string
  paper_quality: string
  specification: string
  unit: string
  balance: string
  latest_location: string
  latest_movement_id: string
  latest_document_no: string
  latest_movement_at: string
  latest_inbound_at?: string | null
  location_revision?: number
}

export interface CartonInventoryMovementCreateRequest {
  workshop_id?: string
  location_id?: string
  issue_kind?: string
  factory_id: string
  order_line_id: string | null
  reference_movement_id: string | null
  movement_type: 'OUTBOUND' | 'ADJUSTMENT'
  quantity: number
  location: string
  document_no: string
  reason: string
}

export interface CartonInventoryFlowSummaryResponse {
  business_date: string
  customer_code: string
  customer_name: string
  movement_type: 'INBOUND' | 'OUTBOUND'
  document_count: number
  line_count: number
  quantity: string
}

export interface CartonAuditEventResponse {
  sequence: number
  id: string
  factory_id: string
  event_type: string
  entity_type: string
  entity_id: string
  detail: Record<string, unknown>
  actor_user_id: string
  actor_name: string
  created_at: string
}

export interface CartonPricingIssue {
  movement_id: string
  document_no: string
  item_no: string
  packaging_type: string
  occurred_at: string
  unit: string
  currency: string
  message: string
  can_price: boolean
}

export interface CartonClosingUnitQuantities {
  unit: string
  opening_quantity: string
  inbound_quantity: string
  outbound_quantity: string
  adjustment_quantity: string
  ending_quantity: string
}

export interface CartonClosingResponse {
  id: string
  factory_id: string
  period: string
  customer_code: string
  customer_name: string
  opening_quantity: string
  inbound_quantity: string
  outbound_quantity: string
  adjustment_quantity: string
  ending_quantity: string
  ending_amount: string
  pricing_issues?: CartonPricingIssue[]
  snapshot_stale?: boolean
  quantities_by_unit?: CartonClosingUnitQuantities[]
  quantity_snapshot_missing?: boolean
  currency: string
  status: 'DRAFT' | 'PENDING' | 'CONFIRMED' | 'LOCKED'
  revision: number
}

export interface CartonImportBatchResponse {
  id: string
  factory_id: string
  import_type: 'DELIVERY_NOTE' | 'WEEKLY_SCHEDULE' | 'INSPECTION_SCHEDULE'
  original_filename: string
  source_sha256: string
  import_profile: string
  content_type: string
  source_size_bytes: number
  status: 'REQUIRES_REVIEW' | 'CONFIRMED' | 'REJECTED'
  imported_by: string
  imported_by_name: string
  created_at: string
  parse_summary: {
    message?: string
    engine?: string
    row_count?: number
    matched_count?: number
    issue_count?: number
    reminder_count?: number
    overdue_count?: number
    due_soon_count?: number
    ready_count?: number
    advance_days?: number | null
    parser_version?: string | null
    warnings?: string[]
    review_count?: number
    field_mappings?: Array<{ sheet: string; header_row: number; fields: Record<string, string> }>
    change_counts?: Record<string, number>
    schedule_customer?: { customer_code: string; customer_name: string }
    document?: { delivery_note_no?: string; delivery_date?: string; raw_text_excerpt?: string }
    rows?: CartonImportPreviewRow[]
  }
  duplicate: boolean
}

export interface CartonImportPreviewRow {
  source_material?: { packaging_type: string; paper_quality: string; specification: string; dimension_unit?: string }
  material_candidates?: { order_no: string; order_line_id: string; packaging_type: string; paper_quality: string; specification: string; dimension_unit?: string; conflicts: string[] }[]
  schedule_customer_code?: string
  schedule_customer_name?: string
  template?: string
  order_type?: string
  source_reference?: string
  source_customer_name?: string
  schedule_section?: 'PENDING' | 'CANCELLED' | 'SHIPPED'
  schedule_change?: 'BASELINE' | 'UNCHANGED' | 'NEW' | 'CANCELLED' | 'CANCELLED_AFTER_ORDER' | 'SHIPPED' | 'REOPENED' | 'REVIEW_REQUIRED' | 'NOT_TRACKED'
  schedule_identity?: string
  manual_ordered?: boolean
  source_inspection_window?: string
  source_customer_due_date?: string
  date_review_required?: boolean
  production_no?: string
  customer_due_date?: string
  procurement_state?: 'NEEDS_ORDER' | 'ORDERED' | 'COMPLETED' | 'REVIEW'
  customer_po?: string
  source_sheet?: string
  source_row?: number
  destination?: string
  destination_factory_id?: string
  delivery_note_no?: string
  delivery_date?: string
  reference?: string
  contract_no?: string
  po_numbers?: string
  customer_code?: string
  customer_name?: string
  item_no?: string
  product_name?: string
  packaging_type?: string
  paper_quality?: string
  specification?: string
  delivered_quantity?: number
  quantity?: number | null
  unit_price?: number
  order_unit_price?: number | null
  order_currency?: string
  location?: string
  unit?: string
  carton_rule?: string
  inspection_window?: string
  match_status?: 'MATCHED' | 'MISSING_ORDER' | 'QUANTITY_MISMATCH' | 'AMBIGUOUS' | 'REVIEW_REQUIRED' | 'DATE_MISMATCH'
  order_status?: 'DRAFT' | 'PENDING_SUPPLIER' | 'CONFIRMED' | 'PARTIALLY_RECEIVED' | 'COMPLETED' | 'CANCELLED'
  inspection_start_date?: string
  required_delivery_date?: string
  advance_days?: number
  days_until_delivery?: number | null
  reminder_status?: 'READY' | 'UPCOMING' | 'DUE_SOON' | 'OVERDUE' | 'MISSING_ORDER' | 'AMBIGUOUS' | 'INVALID_DATE' | 'REVIEW_REQUIRED'
  match_basis?: string
  suggestion?: string
  order_id?: string
  order_line_id?: string
  order_no?: string
}

export interface CartonReceiptResponse {
  id: string
  factory_id: string
  receipt_no: string
  delivery_note_no: string
  delivery_date: string
  acceptance_date?: string | null
  supplier_id: string
  supplier_name: string
  import_batch_id: string | null
  status: 'DRAFT' | 'PENDING_CONFIRMATION' | 'POSTED' | 'REVERSED'
  note: string
  revision: number
  created_by: string
  created_by_name: string
  confirmed_by: string
  confirmed_by_name: string
  created_at: string
  updated_at: string
  confirmed_at: string
  lines: Array<{
    id: string
    line_no: number
    source_type: 'FORMAL_ORDER' | 'AD_HOC'
    replenishment_issue_id?: string | null
    document_no?: string | null
    responsibility?: 'OWN' | 'SUPPLIER' | null
    settlement_unit_price?: string | null
    order_line_id: string | null
    customer_code: string
    customer_name: string
    contract_no: string
    item_no: string
    packaging_type: string
    paper_quality: string
    specification: string
    delivered_quantity: string
    received_quantity: string
    damaged_quantity: string
    rejected_quantity: string
    unusable_quantity: string
    effective_quantity: string
    unit: string
    unit_price: string
    currency: string
    location: string
    location_allocations?: Array<{ location_id: string; quantity: string | number; label?: string }>
  feedback_note: string
  }>
}

export interface CartonExceptionResponse {
  id: string
  factory_id: string
  exception_no: string
  source_type: string
  source_id: string
  category: string
  severity: 'LOW' | 'MEDIUM' | 'HIGH'
  customer_code: string
  customer_name: string
  contract_no: string
  item_no: string
  title: string
  description: string
  owner_department: string
  status: 'OPEN' | 'IN_PROGRESS' | 'RESOLVED' | 'CLOSED'
  resolution_note: string
  revision: number
  created_at: string
  updated_at: string
}

export interface CartonDashboardResponse {
  factory_id: string
  open_order_count: number
  partial_order_count: number
  pending_receipt_count: number
  inventory_balance: string
  unlocked_closing_count: number
  open_exception_count: number
}

export const cartonProcurementApi = {
  async confirmInventoryPrice(movementId: string, payload: {
    factory_id: string; unit_price: string; zero_price_confirmed: boolean; reason: string
  }) {
    await http.post(`/carton-procurement/inventory/movements/${encodeURIComponent(movementId)}/price-confirmation`, payload)
  },
  async listCustomers(factoryId: string, includeInactive = true) {
    const response = await http.get<{ items: CartonCustomerResponse[] }>('/carton-procurement/customers', {
      params: { factory_id: factoryId, include_inactive: includeInactive },
    })
    return response.data.items
  },
  async createCustomer(payload: CartonCustomerSaveRequest) {
    const response = await http.post<CartonCustomerResponse>('/carton-procurement/customers', payload)
    return response.data
  },
  async updateCustomer(customer: CartonCustomerResponse, payload: CartonCustomerSaveRequest) {
    const response = await http.patch<CartonCustomerResponse>(`/carton-procurement/customers/${customer.id}`, {
      ...payload,
      expected_revision: customer.revision,
    })
    return response.data
  },
  async deleteCustomer(factoryId: string, customerId: string) {
    await http.delete(`/carton-procurement/customers/${customerId}`, {
      params: { factory_id: factoryId },
    })
  },
  async dashboard(factoryId: string) {
    const response = await http.get<CartonDashboardResponse>('/carton-procurement/dashboard', {
      params: { factory_id: factoryId },
    })
    return response.data
  },
  async listOrders(factoryId: string, filters: {
    status?: string
    dueFrom?: string
    dueTo?: string
    search?: string
  } = {}) {
    const items: CartonOrderResponse[] = []
    while (true) {
      const response = await http.get<{ items: CartonOrderResponse[]; total: number }>('/carton-procurement/orders', {
        params: { factory_id: factoryId, status_filter: filters.status ?? '', due_from: filters.dueFrom ?? '',
          due_to: filters.dueTo ?? '', search: filters.search ?? '', limit: 200, offset: items.length },
      })
      items.push(...response.data.items)
      if (!response.data.items.length || items.length >= response.data.total) return items
    }
  },
  async createOrder(payload: CartonOrderCreateRequest) {
    const response = await http.post<CartonOrderResponse>('/carton-procurement/orders', payload)
    return response.data
  },
  async updateOrder(order: CartonOrderResponse, payload: CartonOrderUpdateRequest) {
    const response = await http.patch<CartonOrderResponse>(
      `/carton-procurement/orders/${encodeURIComponent(order.order_no)}`,
      { ...payload, expected_revision: order.revision },
    )
    return response.data
  },
  async submitOrderToSupplier(factoryId: string, order: CartonOrderResponse) {
    const response = await http.post<CartonOrderResponse>(
      `/carton-procurement/orders/${encodeURIComponent(order.order_no)}/submit-supplier`,
      {
        factory_id: factoryId,
        expected_revision: order.revision,
      },
    )
    return response.data
  },
  async bulkSubmitOrdersToSupplier(factoryId: string, orders: CartonOrderResponse[]) {
    const response = await http.post<CartonOrderResponse[]>(
      '/carton-procurement/orders/bulk-submit-supplier',
      {
        factory_id: factoryId,
        items: orders.map((order) => ({
          order_no: order.order_no,
          expected_revision: order.revision,
        })),
      },
    )
    return response.data
  },
  async replenishOrder(factoryId: string, order: CartonOrderResponse, responsibility: 'OWN' | 'SUPPLIER', reason: string, lines: { order_line_id: string; location_id: string; quantity: number }[]) {
    return postCartonInventoryRequest<{ order: CartonOrderResponse; issue: CartonPurchaseOrderIssueResponse }>(
      `/carton-procurement/orders/${encodeURIComponent(order.order_no)}/replenish`,
      { factory_id: factoryId, expected_revision: order.revision, responsibility, reason, lines },
    )
  },
  async deleteHistoryOrder(factoryId: string, order: CartonOrderResponse, reason: string) {
    await http.post(`/carton-procurement/orders/${encodeURIComponent(order.order_no)}/delete-history`, {
      factory_id: factoryId, expected_revision: order.revision, reason,
    })
  },
  async deleteOrder(factoryId: string, order: CartonOrderResponse, reason: string) {
    await http.post(`/carton-procurement/orders/${encodeURIComponent(order.order_no)}/delete`, {
      factory_id: factoryId, expected_revision: order.revision, reason,
    })
  },
  async bulkDeleteOrders(factoryId: string, orders: CartonOrderResponse[], reason: string) {
    await http.post('/carton-procurement/orders/bulk-delete', {
      factory_id: factoryId, reason,
      items: orders.map(order => ({ order_no: order.order_no, expected_revision: order.revision })),
    })
  },
  async bulkDeleteHistoryOrders(factoryId: string, orders: CartonOrderResponse[], reason: string) {
    await http.post('/carton-procurement/orders/bulk-delete-history', {
      factory_id: factoryId, reason,
      items: orders.map(order => ({ order_no: order.order_no, expected_revision: order.revision })),
    })
  },
  async undoScheduleImport(factoryId: string, batchId: string, reason: string) {
    const response = await http.post<CartonImportBatchResponse>(`/carton-procurement/imports/${encodeURIComponent(batchId)}/undo`, {
      factory_id: factoryId, reason,
    })
    return response.data
  },
  async cancelOrder(factoryId: string, order: CartonOrderResponse, reason: string) {
    const response = await http.post<CartonOrderResponse>(
      `/carton-procurement/orders/${encodeURIComponent(order.order_no)}/cancel`,
      {
        factory_id: factoryId,
        expected_revision: order.revision,
        reason,
      },
    )
    return response.data
  },
  async appendOrder(
    factoryId: string,
    order: CartonOrderResponse,
    additionalQuantity: number | null,
    reason: string,
    dueDate?: string,
    customerDueDate?: string,
    lineQuantities?: Array<{ order_line_id: string; required_quantity: number }>,
  ) {
    const response = await http.post<CartonOrderResponse>(
      `/carton-procurement/orders/${encodeURIComponent(order.order_no)}/append`,
      {
        factory_id: factoryId,
        expected_revision: order.revision,
        additional_quantity: additionalQuantity,
        ...(lineQuantities ? { line_quantities: lineQuantities } : {}),
        reason,
        customer_due_date: customerDueDate || null,
        due_date: dueDate || null,
      },
    )
    return response.data
  },
  async reduceOrder(
    factoryId: string,
    order: CartonOrderResponse,
    reductionQuantity: number | null,
    reason: string,
    lineQuantities?: Array<{ order_line_id: string; required_quantity: number }>,
  ) {
    const response = await http.post<CartonOrderResponse>(
      `/carton-procurement/orders/${encodeURIComponent(order.order_no)}/reduce`,
      {
        factory_id: factoryId,
        expected_revision: order.revision,
        reduction_quantity: reductionQuantity,
        ...(lineQuantities ? { line_quantities: lineQuantities } : {}),
        reason,
      },
    )
    return response.data
  },
  async returnOrder(factoryId: string, order: CartonOrderResponse, reason: string) {
    const response = await http.post<CartonOrderResponse>(
      `/carton-procurement/orders/${encodeURIComponent(order.order_no)}/return`,
      {
        factory_id: factoryId,
        expected_revision: order.revision,
        reason,
      },
    )
    return response.data
  },
  async bulkCancelOrders(factoryId: string, orders: CartonOrderResponse[], reason: string) {
    const response = await http.post<CartonOrderResponse[]>('/carton-procurement/orders/bulk-cancel', {
      factory_id: factoryId,
      reason,
      items: orders.map((order) => ({
        order_no: order.order_no,
        expected_revision: order.revision,
      })),
    })
    return response.data
  },
  async previewHistoryOrders(factoryId: string, file: File) {
    const form = new FormData()
    form.append('file', file)
    return (await http.post<CartonHistoryOrderPreview>('/carton-procurement/history-orders/preview', form, { params: { factory_id: factoryId }, headers: { 'Content-Type': 'multipart/form-data' } })).data
  },
  async uploadHistoryOrders(factoryId: string, file: File, fingerprint?: string) {
    const form = new FormData()
    form.append('file', file)
    if (fingerprint) form.append('expected_preview_fingerprint', fingerprint)
    const response = await http.post<CartonHistoryOrderImportResponse>(
      '/carton-procurement/orders/history-imports',
      form,
      { params: { factory_id: factoryId }, headers: { 'Content-Type': 'multipart/form-data' } },
    )
    return response.data
  },
  async searchOrderHistoryItems(
    factoryId: string,
    itemNo: string,
    customerCode = '',
    limit = 8,
  ) {
    const response = await http.get<{ items: CartonOrderHistorySuggestionResponse[] }>(
      '/carton-procurement/order-history/item-suggestions',
      {
        params: {
          factory_id: factoryId,
          item_no: itemNo,
          customer_code: customerCode,
          limit,
        },
      },
    )
    return response.data.items
  },
  async exportPurchaseOrder(factoryId: string, orderNo: string) {
    const response = await http.get<Blob>(
      `/carton-procurement/orders/${encodeURIComponent(orderNo)}/purchase-order.xlsx`,
      { params: { factory_id: factoryId }, responseType: 'blob', timeout: 30_000 },
    )
    return response.data
  },
  async getPurchaseOrderContext(factoryId: string, orderNo: string) {
    const response = await http.get<CartonPurchaseOrderContextResponse>(
      `/carton-procurement/orders/${encodeURIComponent(orderNo)}/purchase-order-context`,
      { params: { factory_id: factoryId } },
    )
    return response.data
  },
  async issuePurchaseOrder(factoryId: string, order: CartonOrderResponse) {
    const response = await http.post<Blob>(
      `/carton-procurement/orders/${encodeURIComponent(order.order_no)}/purchase-order-issues.xlsx`,
      {
        factory_id: factoryId,
        expected_revision: order.revision,
      },
      { responseType: 'blob', timeout: 30_000 },
    )
    return {
      blob: response.data,
      documentNo: String(response.headers['x-purchase-order-document-no'] || order.order_no),
    }
  },
  async downloadPurchaseOrderIssue(factoryId: string, orderNo: string, issueId: string) {
    const response = await http.get<Blob>(
      `/carton-procurement/orders/${encodeURIComponent(orderNo)}/purchase-order-issues/${encodeURIComponent(issueId)}.xlsx`,
      { params: { factory_id: factoryId }, responseType: 'blob', timeout: 30_000 },
    )
    return response.data
  },
  async issuePurchaseOrders(factoryId: string, orders: CartonOrderResponse[]) {
    const response = await http.post<Blob>(
      '/carton-procurement/orders/purchase-order-issues.xlsx',
      {
        factory_id: factoryId,
        items: orders.map((order) => ({
          order_no: order.order_no,
          expected_revision: order.revision,
        })),
      },
      { responseType: 'blob', timeout: 60_000 },
    )
    return {
      blob: response.data,
      issueCount: Number(response.headers['x-purchase-order-issue-count'] || 0),
    }
  },
  async exportPurchaseOrders(factoryId: string, orderNos: string[]) {
    const response = await http.post<Blob>(
      '/carton-procurement/orders/purchase-orders.xlsx',
      { factory_id: factoryId, order_nos: orderNos },
      { responseType: 'blob', timeout: 60_000 },
    )
    return response.data
  },
  async listMovements(factoryId: string) {
    const response = await http.get<{ items: CartonInventoryMovementResponse[] }>(
      '/carton-procurement/inventory/movements',
      { params: { factory_id: factoryId, limit: 500 } },
    )
    return response.data.items
  },
  async listInventoryBalances(factoryId: string) {
    const response = await http.get<CartonInventoryBalanceResponse[]>(
      '/carton-procurement/inventory/positions',
      { params: { factory_id: factoryId } },
    )
    return response.data
  },
  async createInventoryMovement(payload: CartonInventoryMovementCreateRequest) {
    return postCartonInventoryRequest<CartonInventoryMovementResponse>(
      '/carton-procurement/inventory/movements',
      payload,
    )
  },
  async relocateInventory(payload: {
    factory_id: string
    reference_movement_id: string
    expected_location_revision: number
    location: string
    note: string
  }) {
    const response = await http.post<CartonInventoryBalanceResponse>(
      '/carton-procurement/inventory/relocations', payload,
    )
    return response.data
  },
  async createInventoryMovementsBulk(payload: {
    workshop_id?: string
    issue_kind?: string
    factory_id: string
    document_no: string
    reason: string
    items: Array<{
      workshop_id?: string
      order_line_id: string | null
      reference_movement_id: string | null
      quantity: number
      location: string
      location_id?: string
    }>
  }) {
    return postCartonInventoryRequest<CartonInventoryMovementResponse[]>(
      '/carton-procurement/inventory/movements/bulk',
      { ...payload, items: [...payload.items].sort((a, b) =>
        (a.order_line_id || a.reference_movement_id || '').localeCompare(b.order_line_id || b.reference_movement_id || '')) },
    )
  },
  async listInventorySummary(factoryId: string, dateFrom = '', dateTo = '') {
    const response = await http.get<CartonInventoryFlowSummaryResponse[]>(
      '/carton-procurement/inventory/summary',
      { params: { factory_id: factoryId, date_from: dateFrom, date_to: dateTo } },
    )
    return response.data
  },
  async reverseInventoryMovement(factoryId: string, movementId: string, reason: string) {
    const response = await http.post<CartonInventoryMovementResponse>(
      `/carton-procurement/inventory/movements/${encodeURIComponent(movementId)}/reverse`,
      { factory_id: factoryId, reason },
    )
    return response.data
  },
  async previewHistoryInventory(factoryId: string, file: File, options: OpeningInventoryOptions) {
    const form = new FormData()
    form.append('file', file)
    form.append('options', JSON.stringify(options))
    return (await http.post<OpeningInventoryPreview>('/carton-procurement/inventory/history-imports/preview', form, { params: { factory_id: factoryId }, headers: { 'Content-Type': 'multipart/form-data' } })).data
  },
  async uploadHistoryInventory(factoryId: string, file: File, options?: OpeningInventoryOptions, fingerprint?: string) {
    const form = new FormData()
    form.append('file', file)
    if (options) form.append('options', JSON.stringify(options))
    if (fingerprint) form.append('expected_preview_fingerprint', fingerprint)
    const response = await http.post<CartonHistoryInventoryImportResponse>(
      '/carton-procurement/inventory/history-imports',
      form,
      { params: { factory_id: factoryId }, headers: { 'Content-Type': 'multipart/form-data' } },
    )
    return response.data
  },
  async listClosings(factoryId: string) {
    const response = await http.get<CartonClosingResponse[]>('/carton-procurement/closings', {
      params: { factory_id: factoryId },
    })
    return response.data
  },
  async uploadReceipt(factoryId: string, file: File) {
    const form = new FormData()
    form.append('file', file)
    const response = await http.post<CartonImportBatchResponse>(
      '/carton-procurement/receipt-imports',
      form,
      { params: { factory_id: factoryId }, headers: { 'Content-Type': 'multipart/form-data' } },
    )
    return response.data
  },
  async latestReceiptImport(factoryId: string) {
    const response = await http.get<CartonImportBatchResponse | null>('/carton-procurement/receipt-imports/latest', {
      params: { factory_id: factoryId },
    })
    return response.data
  },
  async deleteReceiptImport(factoryId: string, batchId: string) {
    await http.delete(`/carton-procurement/receipt-imports/${batchId}`, {
      params: { factory_id: factoryId },
    })
  },
  async uploadWeeklySchedule(factoryId: string, file: File, customerCode: string) {
    const form = new FormData()
    form.append('file', file)
    form.append('customer_code', customerCode)
    const response = await http.post<CartonImportBatchResponse>(
      '/carton-procurement/weekly-imports',
      form,
      { params: { factory_id: factoryId }, headers: { 'Content-Type': 'multipart/form-data' } },
    )
    return response.data
  },
  async listScheduleOrderMarks(factoryId: string) {
    const response = await http.get<Record<string, { marked: boolean; actor: string; updated_at: string; order_ids?: string[] }>>(
      '/carton-procurement/schedule-order-marks', { params: { factory_id: factoryId } },
    )
    return response.data
  },
  async setScheduleOrderMark(factoryId: string, batchId: string, sourceSheet: string, sourceRow: number, marked: boolean) {
    const response = await http.post<{ identity: string; marked: boolean }>(
      '/carton-procurement/schedule-order-marks',
      { factory_id: factoryId, batch_id: batchId, source_sheet: sourceSheet, source_row: sourceRow, marked },
    )
    return response.data
  },
  async setScheduleOrderMarks(factoryId: string, batchId: string, rows: Array<{ source_sheet: string; source_row: number }>, marked: boolean) {
    const response = await http.post<{ items: Array<{ identity: string; marked: boolean }>; changed_count: number }>(
      '/carton-procurement/schedule-order-marks/bulk',
      { factory_id: factoryId, batch_id: batchId, rows, marked },
    )
    return response.data
  },
  async listImports(
    factoryId: string,
    importType: 'DELIVERY_NOTE' | 'WEEKLY_SCHEDULE' | 'INSPECTION_SCHEDULE',
  ) {
    const response = await http.get<{ items: CartonImportBatchResponse[] }>('/carton-procurement/imports', {
      params: { factory_id: factoryId, import_type: importType, limit: 50 },
    })
    return response.data.items
  },
  async uploadInspectionSchedule(factoryId: string, file: File, advanceDays: number) {
    const form = new FormData()
    form.append('file', file)
    const response = await http.post<CartonImportBatchResponse>(
      '/carton-procurement/inspection-imports',
      form,
      {
        params: { factory_id: factoryId, advance_days: advanceDays },
        headers: { 'Content-Type': 'multipart/form-data' },
      },
    )
    return response.data
  },
  async listReceipts(factoryId: string) {
    const items: CartonReceiptResponse[] = []
    while (true) {
      const response = await http.get<{ items: CartonReceiptResponse[]; total: number }>('/carton-procurement/receipts', {
        params: { factory_id: factoryId, limit: 200, offset: items.length },
      })
      items.push(...response.data.items)
      if (!response.data.items.length || items.length >= response.data.total) return items
    }
  },
  async reverseReceipt(factoryId: string, receiptId: string, expectedRevision: number, reason: string) {
    const response = await http.post<CartonReceiptResponse>(`/carton-procurement/receipts/${encodeURIComponent(receiptId)}/reverse`, {
      factory_id: factoryId, expected_revision: expectedRevision, reason,
    })
    return response.data
  },
  async createReceipt(payload: {
    post_immediately?: boolean
    split_confirmation?: string
    factory_id: string
    delivery_note_no: string
    delivery_date: string
    acceptance_date?: string
    import_batch_id: string | null
    note: string
    lines: Array<{
      source_type: 'FORMAL_ORDER' | 'AD_HOC'
      replenishment_issue_id?: string | null
      order_line_id: string | null
      customer_code: string
      contract_no: string
      item_no: string
      packaging_type: string
      paper_quality: string
      specification: string
      unit: string
      currency: string
      delivered_quantity: number
      received_quantity: number
      damaged_quantity: number
      rejected_quantity: number
      unusable_quantity: number
      unit_price?: number
      location: string
      location_allocations?: Array<{ location_id: string; quantity: string | number; label?: string }>
  feedback_note: string
    }>
  }) {
    if (payload.post_immediately) {
      return postCartonInventoryRequest<CartonReceiptResponse>('/carton-procurement/receipts', payload)
    }
    const response = await http.post<CartonReceiptResponse>('/carton-procurement/receipts', payload)
    return response.data
  },
  async confirmReceipt(factoryId: string, receiptId: string, expectedRevision: number, splitConfirmation = '') {
    const response = await http.post<CartonReceiptResponse>(`/carton-procurement/receipts/${receiptId}/confirm`, {
      factory_id: factoryId,
      expected_revision: expectedRevision,
      split_confirmation: splitConfirmation,
    })
    return response.data
  },
  async generateClosings(factoryId: string, period: string) {
    const response = await http.post<CartonClosingResponse[]>('/carton-procurement/closings/generate', {
      factory_id: factoryId,
      period,
    })
    return response.data
  },
  async unlockClosing(factoryId: string, closing: CartonClosingResponse, reason: string) {
    const response = await http.post<CartonClosingResponse>(`/carton-procurement/closings/${encodeURIComponent(closing.id)}/unlock`, {
      factory_id: factoryId, expected_revision: closing.revision, reason,
    })
    return response.data
  },
  async updateClosingStatus(factoryId: string, closing: CartonClosingResponse, status: 'PENDING' | 'CONFIRMED' | 'LOCKED') {
    const response = await http.post<CartonClosingResponse>(`/carton-procurement/closings/${closing.id}/status`, {
      factory_id: factoryId,
      expected_revision: closing.revision,
      status,
    })
    return response.data
  },
  async listExceptions(factoryId: string) {
    const items: CartonExceptionResponse[] = []
    while (true) {
      const response = await http.get<{ items: CartonExceptionResponse[]; total: number }>('/carton-procurement/exceptions', {
        params: { factory_id: factoryId, limit: 500, offset: items.length },
      })
      items.push(...response.data.items)
      if (!response.data.items.length || items.length >= response.data.total || response.data.items.length < 500) return items
    }
  },
  async bulkUpdateExceptions(factoryId: string, exceptions: CartonExceptionResponse[], status: CartonExceptionResponse['status'], resolutionNote: string) {
    const response = await http.post<CartonExceptionResponse[]>('/carton-procurement/exceptions/bulk-update', {
      factory_id: factoryId, items: exceptions.map(row => ({ id: row.id, expected_revision: row.revision })),
      status, resolution_note: resolutionNote,
    })
    return response.data
  },
  async updateException(factoryId: string, exception: CartonExceptionResponse, status: CartonExceptionResponse['status'], resolutionNote = '') {
    const response = await http.patch<CartonExceptionResponse>(`/carton-procurement/exceptions/${exception.id}`, {
      factory_id: factoryId,
      expected_revision: exception.revision,
      status,
      owner_department: exception.owner_department,
      resolution_note: resolutionNote,
    })
    return response.data
  },
  async listAuditEvents(factoryId: string, filters: {
    search?: string
    eventType?: string
    actorUserId?: string
    dateFrom?: string
    dateTo?: string
  } = {}) {
    const response = await http.get<{ items: CartonAuditEventResponse[] }>('/carton-procurement/audit-events', {
      params: {
        factory_id: factoryId,
        search: filters.search ?? '',
        event_type: filters.eventType ?? '',
        actor_user_id: filters.actorUserId ?? '',
        date_from: filters.dateFrom ?? '',
        date_to: filters.dateTo ?? '',
        limit: 500,
      },
    })
    return response.data.items
  },
}

export interface CartonHistoryOrderPreview {
  supplier_id?: string; supplier_name?: string;
  factory_id: string; original_filename: string; source_fingerprint: string;
  row_count: number; group_count: number; line_count: number; ready_count: number; draft_count: number; skipped_count: number;
  warnings: string[]; errors: string[];
  orders: Array<{ customer_po?: string; source_rows: string[]; order_no: string; customer_name: string; contract_no: string; item_no: string;
    product_name: string; product_order_quantity: string | null; order_date: string; due_date: string | null; customer_due_date: string | null;
    status: string; quantity_basis: string; duplicate: boolean; ready: boolean; warnings: string[];
    lines: Array<{ packaging_type: string; paper_quality: string; specification: string; dimension_unit: string;
      usage_quantity: string | null; required_quantity: string; unit: string; unit_price: string; currency: string; note: string }> }>
}

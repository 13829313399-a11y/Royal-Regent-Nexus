import { http } from '@/lib/http'

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

export interface CartonOrderLineResponse {
  id: string
  line_no: number
  packaging_type: string
  paper_quality: string
  specification: string
  dimension_unit: string
  usage_quantity: string
  required_quantity: string
  received_quantity: string
  remaining_quantity: string
  unit: string
  unit_price: string
  currency: string
  price_source: string
  note: string
}

export interface CartonOrderResponse {
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
  product_order_quantity: string
  order_date: string
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
  lines: CartonOrderLineResponse[]
}

export interface CartonOrderCreateRequest {
  factory_id: string
  customer_code: string
  customer_name: string
  supplier_id?: string
  contract_no: string
  item_no: string
  product_name?: string
  product_order_quantity: number
  order_date: string
  due_date: string
  status: 'CONFIRMED'
  note: string
  lines: Array<{
    packaging_type: string
    paper_quality: string
    specification: string
    dimension_unit: string
    usage_quantity: number
    unit: string
    unit_price?: number
    currency?: string
    price_source?: string
    note?: string
  }>
}

export type CartonOrderUpdateRequest = Omit<CartonOrderCreateRequest, 'status'> & {
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

export interface CartonInventoryMovementResponse {
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
  latest_movement_at: string
}

export interface CartonInventoryMovementCreateRequest {
  factory_id: string
  order_line_id: string | null
  reference_movement_id: string | null
  movement_type: 'OUTBOUND' | 'ADJUSTMENT'
  quantity: number
  location: string
  document_no: string
  reason: string
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
    warnings?: string[]
    document?: { delivery_note_no?: string; delivery_date?: string; raw_text_excerpt?: string }
    rows?: CartonImportPreviewRow[]
  }
  duplicate: boolean
}

export interface CartonImportPreviewRow {
  source_sheet?: string
  source_row?: number
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
  quantity?: number
  unit_price?: number
  location?: string
  unit?: string
  carton_rule?: string
  inspection_window?: string
  match_status?: 'MATCHED' | 'MISSING_ORDER' | 'QUANTITY_MISMATCH' | 'AMBIGUOUS'
  order_status?: 'DRAFT' | 'PENDING_SUPPLIER' | 'CONFIRMED' | 'PARTIALLY_RECEIVED' | 'COMPLETED' | 'CANCELLED'
  inspection_start_date?: string
  required_delivery_date?: string
  advance_days?: number
  days_until_delivery?: number | null
  reminder_status?: 'READY' | 'UPCOMING' | 'DUE_SOON' | 'OVERDUE' | 'MISSING_ORDER' | 'AMBIGUOUS' | 'INVALID_DATE'
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
    order_line_id: string
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
  async listOrders(factoryId: string) {
    const response = await http.get<{ items: CartonOrderResponse[] }>('/carton-procurement/orders', {
      params: { factory_id: factoryId, limit: 200 },
    })
    return response.data.items
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
  async uploadHistoryOrders(factoryId: string, file: File) {
    const form = new FormData()
    form.append('file', file)
    const response = await http.post<CartonHistoryOrderImportResponse>(
      '/carton-procurement/orders/history-imports',
      form,
      { params: { factory_id: factoryId }, headers: { 'Content-Type': 'multipart/form-data' } },
    )
    return response.data
  },
  async exportPurchaseOrder(factoryId: string, orderNo: string) {
    const response = await http.get<Blob>(
      `/carton-procurement/orders/${encodeURIComponent(orderNo)}/purchase-order.xlsx`,
      { params: { factory_id: factoryId }, responseType: 'blob', timeout: 30_000 },
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
      '/carton-procurement/inventory/balances',
      { params: { factory_id: factoryId } },
    )
    return response.data
  },
  async createInventoryMovement(payload: CartonInventoryMovementCreateRequest) {
    const response = await http.post<CartonInventoryMovementResponse>(
      '/carton-procurement/inventory/movements',
      payload,
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
  async uploadHistoryInventory(factoryId: string, file: File) {
    const form = new FormData()
    form.append('file', file)
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
  async uploadWeeklySchedule(factoryId: string, file: File) {
    const form = new FormData()
    form.append('file', file)
    const response = await http.post<CartonImportBatchResponse>(
      '/carton-procurement/weekly-imports',
      form,
      { params: { factory_id: factoryId }, headers: { 'Content-Type': 'multipart/form-data' } },
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
    const response = await http.get<{ items: CartonReceiptResponse[] }>('/carton-procurement/receipts', {
      params: { factory_id: factoryId, limit: 200 },
    })
    return response.data.items
  },
  async createReceipt(payload: {
    factory_id: string
    delivery_note_no: string
    delivery_date: string
    import_batch_id: string | null
    note: string
    lines: Array<{
      order_line_id: string
      delivered_quantity: number
      received_quantity: number
      damaged_quantity: number
      rejected_quantity: number
      unusable_quantity: number
      unit_price: number
      location: string
      feedback_note: string
    }>
  }) {
    const response = await http.post<CartonReceiptResponse>('/carton-procurement/receipts', payload)
    return response.data
  },
  async confirmReceipt(factoryId: string, receiptId: string, expectedRevision: number) {
    const response = await http.post<CartonReceiptResponse>(`/carton-procurement/receipts/${receiptId}/confirm`, {
      factory_id: factoryId,
      expected_revision: expectedRevision,
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
  async updateClosingStatus(factoryId: string, closing: CartonClosingResponse, status: 'PENDING' | 'CONFIRMED' | 'LOCKED') {
    const response = await http.post<CartonClosingResponse>(`/carton-procurement/closings/${closing.id}/status`, {
      factory_id: factoryId,
      expected_revision: closing.revision,
      status,
    })
    return response.data
  },
  async listExceptions(factoryId: string) {
    const response = await http.get<{ items: CartonExceptionResponse[] }>('/carton-procurement/exceptions', {
      params: { factory_id: factoryId, limit: 500 },
    })
    return response.data.items
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
}

export interface CustomerOrderIssue {
  severity: 'warning' | 'blocked' | string
  code: string
  field: string
  message: string
  can_skip: boolean
  skip_key: string
  skip_label: string
}

export interface CustomerOrderPreviewRow {
  id: string
  status: 'valid' | 'warning' | 'blocked'
  status_label: string
  row_role?: 'parent' | 'detail'
  parent_product_no?: string
  received_date: string
  po_no: string
  contract_no: string
  customer_country: string
  customer_name: string
  country: string
  product_no: string
  product_name_zh: string
  product_name_en: string
  quantity: string
  units_per_carton: string
  carton_count: string
  standard: string
  unit_price_hkd: string
  amount_hkd: string
  packaging: string
  line_q: string
  customer_q: string
  requested_ship_date: string
  input_template: string
  target_template: string
  item_sheet_name: string
  source_po_file_name: string
  lineage: Record<string, string>
  issues: CustomerOrderIssue[]
}

export interface CustomerOrderImportPreview {
  preview_schema_version: string
  customer_code: string
  factory_id: string
  po_file_name: string
  po_file_names: string[]
  po_file_count: number
  schedule_file_name: string
  source_po_sha256: string
  source_po_sha256s: string[]
  source_schedule_sha256: string
  input_template: string
  target_template: string
  output_file_name: string
  summary: {
    total: number
    valid: number
    warning: number
    blocked: number
  }
  rows: CustomerOrderPreviewRow[]
  warnings: string[]
}

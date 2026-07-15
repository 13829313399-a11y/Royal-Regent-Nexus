import { http } from '../lib/http.js'

export const INDONESIA_INVOICE_RECONCILIATION_TIMEOUT_MS = 60000

export interface RriInvoiceDocument {
  input_slot: string
  invoice_no: string
  po_no: string
  date: string
  line_count: number
  declared_total_hkd: number | null
}

export interface RriInvoiceHeaderCheck {
  field: string
  customer_value: string
  supplier_value: string
  status: 'matched' | 'mismatch' | string
  note: string
}

export interface RriInvoiceLineCheck {
  customer_sku: string
  supplier_sku: string
  description: string
  quantity: number
  customer_unit_price_hkd: number
  expected_supplier_unit_price_hkd: number
  supplier_unit_price_hkd: number | null
  customer_amount_hkd: number
  expected_supplier_amount_hkd: number
  supplier_amount_hkd: number | null
  price_status: 'matched' | 'mismatch' | 'not_available' | string
  amount_status: 'matched' | 'mismatch' | 'not_available' | string
  status: 'matched' | 'mismatch' | 'missing_supplier_line' | string
  note: string
}

export interface RriInvoiceReconciliationResponse {
  customer_profile_code: string
  customer_name: string
  factor: number
  rounding_rule: string
  customer_invoice: RriInvoiceDocument
  supplier_invoice: RriInvoiceDocument
  header_checks: RriInvoiceHeaderCheck[]
  line_checks: RriInvoiceLineCheck[]
  summary: {
    customer_line_count: number
    supplier_line_count: number
    matched_line_count: number
    mismatch_line_count: number
    missing_supplier_line_count: number
    unexpected_supplier_line_count: number
    expected_supplier_total_hkd: number
    supplier_declared_total_hkd: number | null
    supplier_total_difference_hkd: number | null
    status: 'matched' | 'review_required' | string
  }
}

export interface RriInvoiceReconciliationRequest {
  invoiceA: Blob
  invoiceB: Blob
}

export function createIndonesiaInvoiceApi(client = http) {
  return {
    async reconcileRri(payload: RriInvoiceReconciliationRequest) {
      const formData = new FormData()
      formData.set('invoice_a', payload.invoiceA)
      formData.set('invoice_b', payload.invoiceB)

      const response = await client.post<RriInvoiceReconciliationResponse>(
        '/indonesia-invoices/rri/reconcile',
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: INDONESIA_INVOICE_RECONCILIATION_TIMEOUT_MS,
        },
      )
      return response.data
    },
  }
}

export const indonesiaInvoiceApi = createIndonesiaInvoiceApi()

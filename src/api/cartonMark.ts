import { http } from '../lib/http.js'

export const CARTON_MARK_AUTO_CHECK_TIMEOUT_MS = 120000

export interface CartonMarkExtractedField {
  key: string
  label: string
  value: string
  confidence: number
  source: string
}

export interface CartonMarkComparisonItem {
  side: 'front' | 'side' | string
  field_key: string
  label: string
  comparison_scope: 'left_label' | 'right_value' | string
  expected: string
  actual: string
  status: 'pass' | 'mismatch' | 'missing_expected' | 'missing_actual' | 'review' | string
  confidence: number
  note: string
}

export interface CartonMarkExtractionStatus {
  source: string
  ok: boolean
  engine: string
  message: string
  raw_text: string
  matched_page?: number | null
  page_count?: number | null
  match_confidence?: number | null
  requires_review?: boolean
  review_reason?: string
}

export interface CartonMarkAutoCheckResponse {
  summary: {
    overall_status: string
    pass_count: number
    mismatch_count: number
    missing_count: number
    review_count: number
  }
  template_fields: CartonMarkExtractedField[]
  front_template_fields: CartonMarkExtractedField[]
  side_template_fields: CartonMarkExtractedField[]
  front_photo_fields: CartonMarkExtractedField[]
  side_photo_fields: CartonMarkExtractedField[]
  comparisons: CartonMarkComparisonItem[]
  extraction: CartonMarkExtractionStatus[]
}

export interface CartonMarkDocumentContentItem {
  text: string
  location: string
  field_key?: string
  is_graphic_text?: boolean
}

export interface CartonMarkDocumentContentComparison {
  status: 'pass' | 'changed' | 'missing' | 'unexpected' | 'review'
  expected: string
  actual: string
  expected_location: string
  actual_location: string
  note: string
}

export interface CartonMarkDocumentContentCheckResponse {
  excel_file_name: string
  pdf_file_name: string
  summary: {
    overall_status: string
    pass_count: number
    changed_count: number
    missing_count: number
    unexpected_count: number
    review_count: number
  }
  excel_items: CartonMarkDocumentContentItem[]
  pdf_items: CartonMarkDocumentContentItem[]
  comparisons: CartonMarkDocumentContentComparison[]
  extraction: CartonMarkExtractionStatus[]
}

export interface CartonMarkAutoCheckRequest {
  customerName: string
  po: string
  item: string
  pdfTemplate: Blob
  frontPhoto: Blob
  sidePhoto: Blob
}

export interface CartonMarkBatchCheckItem {
  side: 'front' | 'side' | string
  file_name: string
  file_index: number
  result: CartonMarkAutoCheckResponse
}

export interface CartonMarkBatchCheckResponse {
  summary: CartonMarkAutoCheckResponse['summary']
  items: CartonMarkBatchCheckItem[]
}

export interface CartonMarkBatchCheckRequest {
  customerName: string
  po: string
  item: string
  pdfTemplate: Blob
  frontPhotos: Blob[]
  sidePhotos: Blob[]
}

export interface CartonMarkDocumentContentCheckRequest {
  excelContract: Blob
  printPdf: Blob
}

export interface CartonMarkCustomerOption {
  id: string
  name: string
}

export interface CartonMarkCustomer extends CartonMarkCustomerOption {
  factory_id: string
  revision: number
  created_by: string
  created_by_name: string
  created_at: string
  updated_by: string
  updated_by_name: string
  updated_at: string
}

export interface CartonMarkTemplateRecordResponse {
  id: string
  factory_id: string
  customer_name: string
  po: string
  item: string
  contract_number: string
  version: number
  check_status: string
  check_result: CartonMarkDocumentContentCheckResponse
  excel_file_name: string
  excel_file_size: number
  pdf_file_name: string
  pdf_file_size: number
  created_at: string
  updated_at: string
  created_by_name: string
  qc_ready: boolean
  manual_released: boolean
  manual_release_reason: string
  manual_release_source_status: string
  manual_released_by_name: string
  manual_released_at: string
}

export interface CartonMarkTemplateCreateRequest {
  factoryId: string
  customerName: string
  po?: string
  item: string
  contractNumber: string
  excelContract: Blob
  printPdf: Blob
  signal?: AbortSignal
}

export type CartonMarkTemplateDocumentKind = 'source_excel' | 'print_pdf'

export function createCartonMarkApi(client = http) {
  return {
    async listCustomerOptions(factoryId: string, signal?: AbortSignal) {
      const response = await client.get<CartonMarkCustomerOption[]>('/carton-mark/customer-options', {
        params: { factory_id: factoryId },
        signal,
      })
      return response.data
    },

    async listCustomers(factoryId: string, signal?: AbortSignal) {
      const response = await client.get<CartonMarkCustomer[]>('/carton-mark/customers', {
        params: { factory_id: factoryId },
        signal,
      })
      return response.data
    },

    async createCustomer(factoryId: string, name: string) {
      const response = await client.post<CartonMarkCustomer>('/carton-mark/customers', { name }, {
        params: { factory_id: factoryId },
      })
      return response.data
    },

    async updateCustomer(factoryId: string, customerId: string, name: string, revision: number) {
      const response = await client.put<CartonMarkCustomer>(`/carton-mark/customers/${customerId}`, {
        name,
        revision,
      }, {
        params: { factory_id: factoryId },
      })
      return response.data
    },

    async deleteCustomer(factoryId: string, customerId: string, revision: number) {
      await client.delete(`/carton-mark/customers/${customerId}`, {
        params: { factory_id: factoryId, revision },
      })
    },

    async createTemplate(payload: CartonMarkTemplateCreateRequest) {
      const formData = new FormData()
      formData.set('factory_id', payload.factoryId)
      formData.set('customer_name', payload.customerName)
      if (payload.po?.trim()) formData.set('po', payload.po.trim())
      formData.set('item', payload.item)
      formData.set('contract_number', payload.contractNumber)
      formData.set('excel_contract', payload.excelContract)
      formData.set('print_pdf', payload.printPdf)

      const response = await client.post<CartonMarkTemplateRecordResponse>('/carton-mark/templates', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: CARTON_MARK_AUTO_CHECK_TIMEOUT_MS,
        signal: payload.signal,
      })
      return response.data
    },

    async listTemplates(factoryId: string, signal?: AbortSignal) {
      const response = await client.get<CartonMarkTemplateRecordResponse[]>('/carton-mark/templates', {
        params: { factory_id: factoryId },
        signal,
      })
      return response.data
    },

    async getTemplate(templateId: string, factoryId: string, signal?: AbortSignal) {
      const response = await client.get<CartonMarkTemplateRecordResponse>(`/carton-mark/templates/${templateId}`, {
        params: { factory_id: factoryId },
        signal,
      })
      return response.data
    },

    async recheckTemplate(templateId: string, factoryId: string, signal?: AbortSignal) {
      const response = await client.post<CartonMarkTemplateRecordResponse>(`/carton-mark/templates/${templateId}/recheck`, undefined, {
        params: { factory_id: factoryId },
        timeout: CARTON_MARK_AUTO_CHECK_TIMEOUT_MS,
        signal,
      })
      return response.data
    },

    async manualReleaseTemplate(templateId: string, factoryId: string, reason: string, signal?: AbortSignal) {
      const response = await client.post<CartonMarkTemplateRecordResponse>(`/carton-mark/templates/${templateId}/manual-release`, {
        reason,
      }, {
        params: { factory_id: factoryId },
        signal,
      })
      return response.data
    },

    async downloadTemplateDocument(templateId: string, kind: CartonMarkTemplateDocumentKind, factoryId: string, signal?: AbortSignal) {
      const response = await client.get<Blob>(`/carton-mark/templates/${templateId}/documents/${kind}`, {
        params: { factory_id: factoryId },
        responseType: 'blob',
        signal,
      })
      return response.data
    },

    async deleteTemplate(templateId: string, factoryId: string, signal?: AbortSignal) {
      await client.delete(`/carton-mark/templates/${templateId}`, {
        params: { factory_id: factoryId },
        signal,
      })
    },

    async documentContentCheck(payload: CartonMarkDocumentContentCheckRequest) {
      const formData = new FormData()
      formData.set('excel_contract', payload.excelContract)
      formData.set('print_pdf', payload.printPdf)

      const response = await client.post<CartonMarkDocumentContentCheckResponse>('/carton-mark/document-content-check', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: CARTON_MARK_AUTO_CHECK_TIMEOUT_MS,
      })
      return response.data
    },

    async autoCheck(payload: CartonMarkAutoCheckRequest) {
      const formData = new FormData()
      formData.set('customer_name', payload.customerName)
      formData.set('po', payload.po)
      formData.set('item', payload.item)
      formData.set('pdf_template', payload.pdfTemplate)
      formData.set('front_photo', payload.frontPhoto)
      formData.set('side_photo', payload.sidePhoto)

      const response = await client.post<CartonMarkAutoCheckResponse>('/carton-mark/auto-check', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: CARTON_MARK_AUTO_CHECK_TIMEOUT_MS,
      })
      return response.data
    },

    async batchAutoCheck(payload: CartonMarkBatchCheckRequest) {
      const formData = new FormData()
      formData.set('customer_name', payload.customerName)
      formData.set('po', payload.po)
      formData.set('item', payload.item)
      formData.set('pdf_template', payload.pdfTemplate)
      payload.frontPhotos.forEach((photo) => formData.append('front_photos', photo))
      payload.sidePhotos.forEach((photo) => formData.append('side_photos', photo))

      const response = await client.post<CartonMarkBatchCheckResponse>('/carton-mark/batch-auto-check', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: CARTON_MARK_AUTO_CHECK_TIMEOUT_MS,
      })
      return response.data
    },
  }
}

export const cartonMarkApi = createCartonMarkApi()

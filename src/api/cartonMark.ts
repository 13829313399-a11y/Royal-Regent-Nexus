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

export interface CartonMarkAutoCheckRequest {
  customerName: string
  po: string
  item: string
  pdfTemplate: Blob
  frontPhoto: Blob
  sidePhoto: Blob
}

export function createCartonMarkApi(client = http) {
  return {
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
  }
}

export const cartonMarkApi = createCartonMarkApi()

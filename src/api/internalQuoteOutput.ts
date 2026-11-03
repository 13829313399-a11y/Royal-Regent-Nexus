import { http } from '@/lib/http'
import type { ApiInternalQuoteWholeProductSave, InternalQuoteHttpClient } from './internalQuote'

export interface OutputField {
  annotation?: { text: string; image_attachment_ids: string[]; author?: string; updated_at?: string; price_at_note?: string } | null
  id: string
  label: string
  kind: 'name' | 'price'
  currency: string
  value: string | number | null
  nullable: boolean
}
export interface OutputGroup {
  id: string
  section: string
  section_name: string
  label: string
  category: string
  editable: boolean
  fields: OutputField[]
}
export interface OutputCell {
  comment?: string
  address: string
  column: number
  text: string
  rowspan: number
  colspan: number
  style: Record<string, string>
  unavailable: boolean
  binding: { group?: string; groups?: string[]; kind: 'name' | 'price' | 'source' } | null
}
export interface OutputLayout {
  import_sources?: Array<{ id: string; file_name: string; department: string; import_type: import('./internalQuote').ApiInternalQuoteImportPreview['import_type']; editable: boolean; revision: number }>
  quote_id: string
  version_label: string
  base_token: string
  sheets: Array<{ name: string; source?: { file_name: string; department: string }; widths: number[]; rows: Array<{ index: number; height: number; cells: OutputCell[] }>; images?: Array<{ src: string; left: number; top: number; width: number; height: number }> }>
  groups: OutputGroup[]
  formula_errors: string[]
  factory_price_hkd: string
  quote_price_hkd?: string | null
  preview: boolean
  read_only: boolean
  warnings: Array<{ message?: string }>
}
export interface OutputEdits {
  base_token: string
  edits: Array<{ field_id: string; value: string | number | null; annotation?: { text: string; image_attachment_ids: string[]; new_images: string[] } }>
}

export function createInternalQuoteOutputApi(client: InternalQuoteHttpClient = http) {
  return {
    async get(quoteId: string) {
      return (await client.get<OutputLayout>(`/internal-quotes/${quoteId}/output-layout`)).data
    },
    async preview(quoteId: string, edits: OutputEdits) {
      return (await client.post<OutputLayout>(`/internal-quotes/${quoteId}/output-layout/preview`, edits)).data
    },
    async save(quoteId: string, edits: OutputEdits) {
      return (await client.put<ApiInternalQuoteWholeProductSave>(`/internal-quotes/${quoteId}/output-layout`, edits)).data
    },
  }
}
export const internalQuoteOutputApi = createInternalQuoteOutputApi()

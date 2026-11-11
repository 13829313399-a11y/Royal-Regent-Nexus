import { http } from '@/lib/http'
import type { ApiInternalQuoteWholeProductSave, InternalQuoteHttpClient } from './internalQuote'

export interface OutputField {
  adjustment?: {
    mode: 'formula' | 'per_piece' | 'per_carton'; status: 'formula' | 'adopted' | 'pending'
    original_per_piece_hkd: string; original_per_carton_hkd: string | null
    qty_per_carton: string | null; effective_per_piece_hkd: string; amount_hkd: string
    allowed_modes: Array<'per_piece' | 'per_carton'>; history_count: number
  }
  adjustment_history?: Array<{ action: string; amount_hkd: string | null; author: string; updated_at: string; original_per_piece_hkd: string }>
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
  source_workbooks_pending?: boolean
  import_sources?: Array<{ id: string; file_name: string; department: string; import_type: import('./internalQuote').ApiInternalQuoteImportPreview['import_type']; editable: boolean; revision: number }>
  quote_id: string
  version_label: string
  base_token: string
  sheets: Array<{ name: string; source?: { file_name: string; department: string }; widths: number[]; rows: Array<{ index: number; height: number; cells: OutputCell[] }>; images?: Array<{ src: string; left: number; top: number; width: number; height: number }> }>
  groups: OutputGroup[]
  formula_errors: string[]
  factory_price_hkd: string
  quote_price_hkd?: string | null
  target_customer_price?: string
  exchange_rates?: { rmb_hkd?: string; hkd_usd?: string }
  removed_adjustments?: Array<{ name: string; section_name: string; amount_hkd: string; reason: string }>
  preview: boolean
  read_only: boolean
  warnings: Array<{ message?: string; code?: string; section_code?: string; section_name?: string }>
}
export interface OutputEdits {
  base_token: string
  edits: Array<{ field_id: string; value: string | number | null; adjustment_mode?: 'formula' | 'per_piece' | 'per_carton'; annotation?: { text: string; image_attachment_ids: string[]; new_images: string[] } }>
}

export function createInternalQuoteOutputApi(client: InternalQuoteHttpClient = http) {
  return {
    async get(quoteId: string, includeSourceWorkbooks = true) {
      return (await client.get<OutputLayout>(`/internal-quotes/${quoteId}/output-layout`,
        { params: { include_source_workbooks: includeSourceWorkbooks } })).data
    },
    async preview(quoteId: string, edits: OutputEdits, includeSourceWorkbooks = true) {
      return (await client.post<OutputLayout>(`/internal-quotes/${quoteId}/output-layout/preview`, edits,
        { params: { include_source_workbooks: includeSourceWorkbooks } })).data
    },
    async save(quoteId: string, edits: OutputEdits) {
      return (await client.put<ApiInternalQuoteWholeProductSave>(`/internal-quotes/${quoteId}/output-layout`, edits)).data
    },
  }
}
export const internalQuoteOutputApi = createInternalQuoteOutputApi()

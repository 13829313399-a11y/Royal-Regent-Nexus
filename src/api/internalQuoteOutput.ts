import { http } from '@/lib/http'
import type { ApiInternalQuoteWholeProductSave, InternalQuoteHttpClient } from './internalQuote'

export interface OutputField {
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
  quote_id: string
  version_label: string
  base_token: string
  sheets: Array<{ name: string; widths: number[]; rows: Array<{ index: number; height: number; cells: OutputCell[] }>; images?: Array<{ src: string; left: number; top: number; width: number; height: number }> }>
  groups: OutputGroup[]
  formula_errors: string[]
  factory_price_hkd: string
  preview: boolean
  read_only: boolean
  warnings: Array<{ message?: string }>
}
export interface OutputEdits {
  base_token: string
  edits: Array<{ field_id: string; value: string | number | null }>
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

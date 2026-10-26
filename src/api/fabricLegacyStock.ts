import { http } from '@/lib/http'

export interface LegacyStockUnit {
  raw_unit: string; unit: string; unit_basis: string; conversion_only: boolean
}
export interface LegacyStockRow extends LegacyStockUnit {
  row_number: number; quantity: string | null; raw_quantity: string; duplicate_of: number | null
  new_item_code: string; item_code: string; item_name: string; location: string; supplier: string
}
export interface LegacyStockProblem extends LegacyStockUnit {
  row_number: number; raw: Record<string, string>; values: Record<string, string>; quantity: string | null
  formula_fields: string[]; unresolved_formulas: string[]; issues: string[]; suggestions: string[]
  matches: Record<'material' | 'supplier' | 'location', string[]>; duplicate_of: number | null
}
export interface LegacyStockPreview {
  filename: string; sheet: string; header_row: number; sheet_rows: number; quantity_column: string; quantity_key: string
  field_mapping: Record<string, { header: string; column: string }>
  summary: { total_rows: number; valid_rows: number; zero_rows: number; missing_qty: number; invalid_qty: number; missing_unit: number; duplicate_rows: number; duplicate_groups: number; conversion_only_rows: number }
  matching: Record<'material' | 'supplier' | 'location', { matched: number; unmatched: number; ambiguous: number }>
  rows: LegacyStockRow[]
  unit_aliases: { raw: string; canonical: string; rows: number; conversion_only: boolean }[]
  conversion_totals: Record<string, string>; unique_totals: Record<string, string>; matched_unique_totals: Record<string, string>
  duplicate_groups: { key: string; rows: LegacyStockRow[]; count: number; rows_truncated: boolean }[]
  duplicate_groups_truncated: boolean
  totals: Record<string, string>; issue_counts: Record<string, number>; problems: LegacyStockProblem[]
  problem_count: number; problems_truncated: boolean; posted: false; read_only: true; quantity_basis: string; totals_basis: string
  unique_totals_basis: string; matched_unique_totals_basis: string; conversion_totals_basis: string
}
export const fabricLegacyStockApi = {
  async preview(file: File, signal?: AbortSignal): Promise<LegacyStockPreview> {
    const input = new FormData()
    input.set('factory_id', 'huakang-c'); input.set('file', file)
    return (await http.post<LegacyStockPreview>('/warehouse-operations/fabric/legacy-stock/preview', input, { signal })).data
  },
}

import { http } from '@/lib/http'
import type { CartonLocation } from './cartonPositions'
import { matchesNumberTemplate } from '@/lib/cartonNumberPatterns'

export interface MasterPaper { packaging_type: string; paper_quality: string; specification: string; dimension_unit: string; unit: string; usage_quantity: string | number }
export interface NumberRule { mode: 'AUTO' | 'OFF' | 'WARN' | 'BLOCK'; prefix: string; min_length: number; max_length: number; characters: 'ANY' | 'DIGITS' | 'ALNUM_DASH'; templates?: string[]; frozen?: boolean; reset?: boolean; sample_text?: string; source?: 'NONE' | 'MANUAL' | 'HISTORY'; sample_count?: number; user_configured?: boolean }
export type PaperHistory = Partial<Record<'packaging_type' | 'paper_quality' | 'specification', string[]>>
export interface MasterData { hidden_paper_types?: string[]; hidden_paper_qualities?: string[]; hidden_specifications?: string[]; paper_types?: string[]; paper_qualities?: string[]; specifications?: string[]; product_name: string; packing_name: string; lines: MasterPaper[]; item_nos: string[]; note: string; lead_days: number | null; production_days: number | null; customer_days: number | null; customer_days_disabled: boolean; customer_po_rule: NumberRule; contract_rule: NumberRule; item_rule: NumberRule; warehouses: string[] }
export interface MasterRecord { id: string; kind: 'CONFIG' | 'CONTRACT' | 'RULE' | 'WORKSHOP' | 'ACCESS'; customer_code: string; code: string; data: Partial<MasterData>; status: 'ACTIVE' | 'INACTIVE'; preferred: boolean; revision: number; maintained: boolean; updated_at: string; sources: { order_no: string; order_date: string; customer_po?: string; contract_no: string; item_no: string; customer_code?: string; configuration: Partial<MasterData> }[] }
export interface MasterWorkspace { paper_history?: PaperHistory; can_manage: boolean; warehouses: string[]; records: MasterRecord[]; locations: CartonLocation[]; users: { id: string; name: string }[] }
export type MasterImportKind = 'paper-options' | 'configurations' | 'locations'
export interface MasterImportResult { factory_id: string; kind: MasterImportKind; fingerprint: string; master_revision: string; preview_token: string; added: number; skipped: number; errors: string[]; details: string[] }
export const emptyMaster = (): MasterWorkspace => ({ can_manage: false, warehouses: [], records: [], locations: [], users: [] })
export const defaultNumberRule = (mode: NumberRule['mode'] = 'AUTO'): NumberRule => ({ mode, prefix: '', min_length: 0, max_length: 128, characters: 'ANY', templates: [], frozen: false, sample_text: '', source: 'NONE', sample_count: 0, user_configured: false })
export function effectiveItemRule(rule?: NumberRule): NumberRule {
  const result = { ...defaultNumberRule('OFF'), ...rule }
  const unrestricted = !result.prefix && result.min_length === 0 && result.max_length === 128 && result.characters === 'ANY'
  if (unrestricted && automaticNumberRule(result) && !result.user_configured && result.source !== 'MANUAL') result.mode = 'OFF'
  return result
}
export const automaticNumberRule = (rule: NumberRule) => rule.mode === 'AUTO' ||
  (rule.mode === 'WARN' && !rule.templates?.length && !rule.prefix && rule.min_length === 0 && rule.max_length === 128 && rule.characters === 'ANY')
export function historicalNumberSamples(records: MasterRecord[], customer: string, key: 'contract_rule' | 'item_rule' | 'customer_po_rule') {
  const values = records.filter(r => r.kind === 'CONTRACT' || r.kind === 'CONFIG')
    .flatMap(r => r.sources.filter(source => (source.customer_code || r.customer_code) === customer).map(source => key === 'customer_po_rule' ? source.customer_po || '' : key === 'contract_rule' ? source.contract_no : source.item_no))
  return [...new Set(values.filter(Boolean))]
}
export const defaultMasterData = (): MasterData => ({ product_name: '', packing_name: '', lines: [], item_nos: [], note: '', lead_days: null, production_days: null, customer_days: null, customer_days_disabled: false, customer_po_rule: defaultNumberRule(), contract_rule: defaultNumberRule(), item_rule: defaultNumberRule('OFF'), warehouses: [] })
export function masterDueRules(records: MasterRecord[], customer: string) {
  const result = { lead_days: 3, production_days: 7, customer_days: null as number | null, customer_po_rule: defaultNumberRule(), contract_rule: defaultNumberRule(), item_rule: defaultNumberRule('OFF') }
  for (const code of ['', customer].filter((x, i, a) => a.indexOf(x) === i)) {
    const row = records.find(r => r.kind === 'RULE' && r.customer_code === code && r.status === 'ACTIVE')
    if (!row) continue
    if (row.data.lead_days != null) result.lead_days = row.data.lead_days
    if (row.data.production_days != null) result.production_days = row.data.production_days
    if (row.data.customer_days != null) result.customer_days = row.data.customer_days
    if (row.data.customer_days_disabled) result.customer_days = null
    if (code) {
      result.customer_po_rule = row.data.customer_po_rule || defaultNumberRule()
      result.contract_rule = row.data.contract_rule || defaultNumberRule()
      result.item_rule = effectiveItemRule(row.data.item_rule)
    }
  }
  return result
}
export function numberWarning(rule: NumberRule, value: string) {
  if (!value || rule.mode === 'OFF') return false
  if (rule.frozen && rule.templates?.length) return !rule.templates.some(t => matchesNumberTemplate(t, value))
  if (rule.mode === 'AUTO') return false
  return !value.startsWith(rule.prefix) || value.length < rule.min_length || value.length > rule.max_length ||
    (rule.characters === 'DIGITS' && !/^\d+$/.test(value)) || (rule.characters === 'ALNUM_DASH' && !/^[A-Za-z0-9_-]+$/.test(value))
}
export const cartonMasterApi = {
  async template(factory_id: string, kind: MasterImportKind) {
    return (await http.get<Blob>(`/carton-procurement/master-data/import/${kind}/template`, { params: { factory_id }, responseType: 'blob' })).data
  },
  async importPreview(factory_id: string, kind: MasterImportKind, file: File) {
    const form = new FormData(); form.append('factory_id', factory_id); form.append('file', file)
    return (await http.post<MasterImportResult>(`/carton-procurement/master-data/import/${kind}/preview`, form, { headers: { 'Content-Type': 'multipart/form-data' } })).data
  },
  async importApply(factory_id: string, kind: MasterImportKind, file: File, preview_token: string) {
    const form = new FormData(); form.append('factory_id', factory_id); form.append('file', file); form.append('preview_token', preview_token)
    return (await http.post<MasterImportResult>(`/carton-procurement/master-data/import/${kind}/apply`, form, { headers: { 'Content-Type': 'multipart/form-data' } })).data
  },
  async deleteWarehouse(factory_id: string, warehouse: string, expected_locations: Record<string, number>, reason: string) {
    return (await http.post<{ deleted: boolean }>('/carton-procurement/inventory/warehouses/delete', { factory_id, warehouse, expected_locations, reason })).data
  },
  async createWarehouse(factory_id: string, warehouse: string, bin_code: string, reason: string) {
    return (await http.post<CartonLocation[]>('/carton-procurement/inventory/warehouses', { factory_id, warehouse, bin_code, reason })).data
  },
  async renameWarehouse(factory_id: string, warehouse: string, new_name: string, expected_locations: Record<string, number>, reason: string) {
    return (await http.patch<CartonLocation[]>('/carton-procurement/inventory/warehouses', { factory_id, warehouse, new_name, expected_locations, reason })).data
  },
  async get(factory_id: string) { return (await http.get<MasterWorkspace>('/carton-procurement/master-data', { params: { factory_id } })).data },
  async save(factory_id: string, row: Pick<MasterRecord, 'kind' | 'customer_code' | 'code' | 'status' | 'preferred'> & { data: MasterData; expected_revision: number; reason: string }, id = '') {
    return (await (id ? http.patch<MasterRecord>(`/carton-procurement/master-data/${id}`, { factory_id, ...row }) : http.post<MasterRecord>('/carton-procurement/master-data', { factory_id, ...row }))).data
  },
  async location(factory_id: string, id: string, data: { warehouse: string; bin_code: string; status: string; expected_revision: number; reason: string }) {
    return (await http.patch<CartonLocation>(`/carton-procurement/inventory/locations/${id}`, { factory_id, ...data })).data
  },
}

export function masterPaperOptions(records: MasterRecord[], field: 'packaging_type' | 'paper_quality' | 'specification', history: PaperHistory = {}) {
  const key = { packaging_type: 'paper_types', paper_quality: 'paper_qualities', specification: 'specifications' }[field] as 'paper_types' | 'paper_qualities' | 'specifications'
  const defaults = records.find(row => row.kind === 'RULE' && !row.customer_code)
  const hidden = new Set(defaults?.data[`hidden_${key}`] || [])
  return [...new Set([...(defaults?.data[key] || []), ...(history[field] || []), ...records.filter(row => row.kind === 'CONFIG' && row.status === 'ACTIVE').flatMap(row => (row.data.lines || []).map(line => line[field]))].map(value => value.trim()).filter(value => value && !hidden.has(value)))]
}

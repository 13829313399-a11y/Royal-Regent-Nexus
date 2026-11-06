import { http } from '@/lib/http'
import type { BomData, Material } from '@/features/engineering-bom/api'

export interface FrozenBom { id: string; version: number; data: BomData; materials: Record<string, Material> }
export type MaterialAttribute = '外购' | '自制' | '委外' | '客供'
export interface OrderReference { line_id: string; revision: number }
export interface OrderBasis extends OrderReference { factory_id: string; version: number; customer_code: string; customer_name: string; reference_no: string; product_no: string; quantity: string; shipped_quantity: string; status: string }
export interface TrialInput { title: string; bom_id: string; bom_version: number; quantity: string; loss_percent: string; loss_exemptions: Record<string, boolean>; material_attributes: Record<string, MaterialAttribute>; reference: string; order?: OrderReference | null }
export interface Amount { value: string; numerator: string; denominator: string; approximate: boolean }
export interface Usage { material_id: string; material_version: number; code: string; name: string; unit: string; attribute: string; base: Amount; loss: Amount; gross: Amount }
export interface TrialResult {
  lines: Array<Usage & { key: string; parent: string; process: string; exempt_loss: boolean; engineering_exempt_loss: boolean; engineering_attribute?: string }>
  totals: Array<Usage & { processes: string[]; keys: string[] }>
  finished_quantity: Amount; finished_unit: string; supply_status: string; net_purchase_quantity: null; pending: string[]; algorithm: string
  order_basis?: OrderBasis | null
  release_gate?: { can_release: false; blockers: string[] }
}
export interface WorkflowActor { id: string; name: string; at: string }
export interface TrialDraft { id: string; version: number; owner_id: string; owner_name: string; status: string; inputs: TrialInput; bom: FrozenBom; result: TrialResult; occurred_at: string; reason: string; process_dates?: Record<string, string>; date_actor?: WorkflowActor; reviewed_by?: WorkflowActor }
export interface Access { enabled: boolean; schema_ready: boolean; can_write: boolean; can_read_orders?: boolean; order_schema_ready?: boolean; can_submit?: boolean; can_self_review?: boolean }
export interface DateDemand { id: string; version: number; status: string; owner_name: string; item_no: string; quantity: string; unit: string; lines: TrialResult['lines']; processes: string[]; process_dates: Record<string, string>; date_actor?: WorkflowActor; occurred_at: string }
const statuses: Record<string, string> = { DRAFT_DATA_PENDING: '草稿待资料', AWAITING_PROCESS_DATES: '待采购填期', AWAITING_SELF_REVIEW: '待业务自审', SELF_REVIEWED_DATA_PENDING: '业务已自审，待供给资料' }
export const statusText = (status: string) => statuses[status] || status
const base = '/material-planning', params = { factory_id: 'huakang-c' }
export const trialApi = {
  async access(): Promise<Access> { return (await http.get(`${base}/access`, { params })).data },
  async workspace(): Promise<{ boms: FrozenBom[]; drafts: TrialDraft[] }> { return (await http.get(`${base}/workspace`, { params })).data },
  async preview(body: unknown): Promise<TrialResult> { return (await http.post(`${base}/preview`, body)).data },
  async save(path: string, body: unknown): Promise<TrialDraft> { return (await http.post(base + path, body)).data },
  async history(id: string): Promise<{ items: TrialDraft[] }> { return (await http.get(`${base}/drafts/${encodeURIComponent(id)}/history`, { params })).data },
  async orders(q: string): Promise<{ items: OrderBasis[]; has_more: boolean }> { return (await http.get(`${base}/orders`, { params: { ...params, q } })).data },
  async dateAccess(): Promise<Access> { return (await http.get(`${base}/procurement/access`, { params })).data },
  async dateWorkspace(): Promise<{ items: DateDemand[] }> { return (await http.get(`${base}/procurement/workspace`, { params })).data },
  async saveDates(id: string, body: unknown): Promise<DateDemand> { return (await http.post(`${base}/drafts/${encodeURIComponent(id)}/dates`, body)).data },
}
export const blankTrial = (): TrialInput => ({ title: '', bom_id: '', bom_version: 0, quantity: '1', loss_percent: '0', loss_exemptions: {}, material_attributes: {}, reference: '' })
export const quantityText = (amount: Amount) => `${amount.approximate ? '≈ ' : ''}${amount.value}`

export function defaultAttributes(bom: FrozenBom): Record<string, MaterialAttribute> {
  return Object.fromEntries(bom.data.nodes.filter(n => n.parent).flatMap(n => {
    const attribute = bom.materials[`${n.material_id}:${n.material_version}`]?.data.engineering?.attribute
    return attribute && ['外购', '自制', '委外', '客供'].includes(attribute) ? [[n.key, attribute as MaterialAttribute]] : []
  }))
}

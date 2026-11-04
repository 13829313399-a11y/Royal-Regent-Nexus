import { ref, shallowReactive } from 'vue'
import type { CartonImportPreviewRow } from '@/api/cartonProcurement'
import type { MasterRecord } from '@/api/cartonMaster'
import type { ScheduleBatchBody, ScheduleBatchLineOverride } from '@/api/cartonScheduleBatch'
import { paperDemands } from './paperQuantity'

export type BatchPaper = ScheduleBatchBody['lines'][number]
export interface ScheduleBatchPreview { source: CartonImportPreviewRow; batchId: string }
export interface ScheduleBatchAttempt { body: ScheduleBatchBody; preview: ScheduleBatchPreview[]; uncertain: boolean }
export type BatchOverrides = Record<string, ScheduleBatchLineOverride[]>
export interface ScheduleBatchDraft {
  preview: ScheduleBatchPreview[]; papers: BatchPaper[]; planned: string; configId: string; configRevision: number
  note: string; rush: boolean; rushReason: string; overrides: BatchOverrides; attempt?: ScheduleBatchAttempt
}
export const pendingScheduleBatches = shallowReactive(new Map<string, ScheduleBatchAttempt>())
export const scheduleBatchDraftVersion = ref(0)
export const scheduleSourceKey = (row: ScheduleBatchPreview) => JSON.stringify([row.batchId, row.source.source_sheet, row.source.source_row])
export const scheduleBatchDraftKey = (identityKey: string, factoryId: string) => `carton-schedule-batch:v1:${encodeURIComponent(identityKey)}:${encodeURIComponent(factoryId)}`
const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value)
const validPreview = (value: unknown) => Array.isArray(value) && value.length > 0 && value.length <= 100 && value.every(row => record(row) && typeof row.batchId === 'string' && record(row.source) && typeof row.source.source_sheet === 'string' && Number.isInteger(row.source.source_row))
const validPapers = (value: unknown) => Array.isArray(value) && value.length > 0 && value.length <= 50 && value.every(row => record(row) && ['packaging_type', 'paper_quality', 'specification', 'dimension_unit', 'unit'].every(key => typeof row[key] === 'string'))
export function readScheduleBatchDraft(storage: Pick<Storage, 'getItem'>, identityKey: string, factoryId: string): ScheduleBatchDraft | null {
  try {
    const raw = storage.getItem(scheduleBatchDraftKey(identityKey, factoryId))
    if (!raw || raw.length > 2_000_000) return null
    const value: unknown = JSON.parse(raw)
    if (!record(value) || value.identityKey !== identityKey || value.factoryId !== factoryId || !record(value.draft)) return null
    const draft = value.draft
    if (!validPreview(draft.preview) || !validPapers(draft.papers) || !['planned', 'configId', 'note', 'rushReason'].every(key => typeof draft[key] === 'string') || typeof draft.rush !== 'boolean' || !Number.isInteger(draft.configRevision) || !record(draft.overrides)) return null
    if (!Object.values(draft.overrides).every(lines => Array.isArray(lines) && lines.length <= 50 && lines.every(line => record(line) && Number.isInteger(line.line_no) && Number(line.line_no) > 0 && ['manual_quantity', 'net_weight_kg', 'gross_weight_kg'].every(key => line[key] === undefined || line[key] === null || typeof line[key] === 'number' && Number.isFinite(line[key]))))) return null
    if (draft.attempt !== undefined) {
      const attempt = draft.attempt
      if (!record(attempt) || !record(attempt.body) || attempt.body.factory_id !== factoryId || typeof attempt.body.request_id !== 'string' || !validPapers(attempt.body.lines) || !validPreview(attempt.preview) || !Array.isArray(attempt.body.sources) || attempt.body.sources.length !== (attempt.preview as unknown[]).length || typeof attempt.body.planned_due_date !== 'string') return null
    }
    return draft as unknown as ScheduleBatchDraft
  } catch { return null }
}
export function writeScheduleBatchDraft(storage: Pick<Storage, 'setItem'>, identityKey: string, factoryId: string, draft: ScheduleBatchDraft) {
  const raw = JSON.stringify({ identityKey, factoryId, draft })
  if (raw.length > 2_000_000) throw new Error('批量草稿过大，请减少本次选择')
  storage.setItem(scheduleBatchDraftKey(identityKey, factoryId), raw); scheduleBatchDraftVersion.value++
}
export function clearScheduleBatchDraft(storage: Pick<Storage, 'removeItem'>, identityKey: string, factoryId: string) {
  storage.removeItem(scheduleBatchDraftKey(identityKey, factoryId)); scheduleBatchDraftVersion.value++
}
const identifier = (value?: string) => (value || '').normalize('NFKC').trim().toLocaleLowerCase()
export function schedulePacking(row: CartonImportPreviewRow): Record<string, number> | null {
  const match = (row.carton_rule || '').trim().match(/^(\d+(?:\.\d+)?)(?:\s*[/／]\s*(\d+(?:\.\d+)?))?$/)
  if (!match) return null
  const inner = match[2] === undefined ? 0 : Number(match[1]), outer = Number(match[2] ?? match[1])
  if (!(outer > 0) || inner < 0 || inner > outer) return null
  return inner > 0 ? { 内箱: inner, 外箱: outer } : { 外箱: outer }
}
export function sameScheduleItem(left: CartonImportPreviewRow, right: CartonImportPreviewRow) {
  return !!left.customer_code && left.customer_code === right.customer_code && !!identifier(left.item_no) && identifier(left.item_no) === identifier(right.item_no)
}
export function batchSourceError(row: CartonImportPreviewRow) {
  if (!row.customer_code || !row.item_no || !row.contract_no || !row.source_sheet || !row.source_row) return '缺少客户、合同或来源资料'
  if (row.can_operate_source === false || row.manual_ordered || row.order_no || row.schedule_section !== 'PENDING') return '已下单或当前来源不可下单'
  if (row.schedule_identity_duplicate || row.legacy_match_stale || row.date_review_required || row.schedule_change === 'REVIEW_REQUIRED' || row.match_status === 'AMBIGUOUS') return '来源资料需要先核对'
  if (!row.customer_due_date || !/^\d{4}-\d{2}-\d{2}$/.test(row.customer_due_date)) return '缺少完整客户交期'
  if (!(Number(row.quantity) > 0) || !schedulePacking(row)) return '数量或内外箱装箱数需要先核对'
  return ''
}
export function scheduleBatchConfigurations(records: MasterRecord[], source: CartonImportPreviewRow) {
  return records.filter(record => record.kind === 'CONFIG' && record.status === 'ACTIVE'
    && identifier(record.code) === identifier(source.item_no))
}
export function emptyBatchPapers(rows: ScheduleBatchPreview[], dimension = 'cm'): BatchPaper[] {
  const types = new Set(rows.flatMap(({ source }) => Object.keys(schedulePacking(source) || {})))
  return [...types].map(packaging_type => ({ packaging_type, paper_quality: '', specification: '', dimension_unit: dimension, unit: '个', usage_quantity: null }))
}
export function batchPaperPreview(source: CartonImportPreviewRow, papers: BatchPaper[], overrides: ScheduleBatchLineOverride[] = []) {
  const packing = schedulePacking(source) || {}
  const lines = papers.map((line, index) => ({ ...line, usage_quantity: isScheduleBox(line.packaging_type) ? packing[['普通箱', '半翼箱'].includes(line.packaging_type) ? '外箱' : line.packaging_type] ?? null : line.usage_quantity,
    quantity_rule: { mode: 'PACKING' as const, ...line.quantity_rule, manual_quantity: overrides.find(item => item.line_no === index + 1)?.manual_quantity ?? null } }))
  return paperDemands(source.quantity ?? null, lines).map((demand, index) => ({ ...demand, type: papers[index]!.packaging_type, unit: papers[index]!.unit }))
}
export const isScheduleBox = (type: string) => ['内箱', '外箱', '普通箱', '半翼箱'].includes(type)
export function effectiveBatchWeights(paper: BatchPaper, override?: ScheduleBatchLineOverride) {
  return { net_weight_kg: override?.net_weight_kg !== undefined ? override.net_weight_kg : paper.net_weight_kg,
    gross_weight_kg: override?.gross_weight_kg !== undefined ? override.gross_weight_kg : paper.gross_weight_kg }
}
export function batchWeightError(weights: { net_weight_kg?: number | null; gross_weight_kg?: number | null }) {
  if ([weights.net_weight_kg, weights.gross_weight_kg].some(value => value != null && (!Number.isFinite(value) || value < 0 || !/^\d+(?:\.\d{1,4})?$/.test(String(value))))) return '每箱重量须为非负数，最多四位小数'
  return weights.net_weight_kg != null && weights.gross_weight_kg != null && weights.gross_weight_kg < weights.net_weight_kg ? '每箱毛重不能小于净重' : ''
}
export function batchPaperError(source: CartonImportPreviewRow, papers: BatchPaper[]) {
  const packing = schedulePacking(source)
  if (!packing) return '排期装箱数需要先核对'
  const boxes = papers.filter(line => line.quantity_rule?.mode !== 'PER_CARTON' && isScheduleBox(line.packaging_type)).map(line => ['普通箱', '半翼箱'].includes(line.packaging_type) ? '外箱' : line.packaging_type)
  if (new Set(boxes).size !== boxes.length || Object.keys(packing).some(type => !boxes.includes(type)) || boxes.some(type => !packing[type])) return '纸品配置与排期内外箱不一致'
  return batchPaperPreview(source, papers).find(paper => paper.error)?.error || ''
}

import { http } from '@/lib/http'
import { CUTTING_FACTORY } from './navigation'
import type { Command, Part } from './api'

export type ReportAction = 'save' | 'post' | 'void' | 'review' | 'discard'
export type ReportKind = 'daily' | 'match' | 'return' | 'accept' | 'handover'
export interface PieceInput { code: string; good: number; rejected: number; scrap: number }
export interface ProductionInput {
  task_id: string; plan_version: number; day: string; mode: 'sets' | 'parts'; kind: ReportKind
  sets: number; rejected: number; scrap: number; parts: PieceInput[]; evidence: string; exception_reason: string
}
export interface ProductionContext { plan_version: number; dispatch_id: string; bom_id: string; bom_version: number; parts: Part[]; task_name: string; task_target: number; resource_id: string; resource_name: string; execution: 'internal' | 'outsourced'; actual_review_pending: boolean }
export interface ReportEvent { id: string; version: number; document_id: string; action: ReportAction; data: { entry: ProductionInput; context: ProductionContext }; actor_id: string; created_at: string; reason: string }
export interface ReportDocument { document_id: string; posted: ReportEvent | null; draft: ReportEvent | null; review: ReportEvent | null; voided: boolean; history: ReportEvent[]; first_version: number }
export interface Balance { produced: number; completed: number; claimed: number; returned: number; accepted: number; rejected: number; handed: number; daily_rejected: number; daily_scrap: number; loose: Record<string,number>; matchable: number; part_rejected: Record<string,number>; part_scrap: Record<string,number> }
export interface ReportTask { task_id: string; name: string; execution: 'internal' | 'outsourced'; mode: 'sets' | 'parts' | null; plan_version: number; target_sets: number; parts: Part[]; historical: boolean; balance: Balance | null; settlement_context?: ProductionContext | null }
export interface ProductionView {
  line_id: string; version: number; as_of: string; tasks: ReportTask[]; documents: ReportDocument[]
  summary: { order_sets: number | null; completed: number; handed: number; actual_delivery: number; remaining: number | null; planned: number; plan_difference: number; completed_unhanded: number; day_completed: number; day_handed: number; months: Record<string,{planned:number;completed:number;handed:number}> }
}
export type ReportCommand = Command & { document_id: string; entry?: ProductionInput }
const url = (id: string) => `/cutting-operations/orders/${encodeURIComponent(id)}`
export const reportingApi = {
  async read(id: string, asOf?: string): Promise<ProductionView> { return (await http.get(`${url(id)}/reports`, { params: { factory_id: CUTTING_FACTORY, ...(asOf ? { as_of: asOf } : {}) } })).data },
  async command(id: string, action: ReportAction, body: ReportCommand): Promise<ProductionView> { return (await http.post(`${url(id)}/reports/${action}`, body)).data },
  async recover(id: string, action: ReportAction, command: ReportCommand): Promise<{state:'committed';result:ProductionView} | {state:'abandoned'}> { return (await http.post(`${url(id)}/report-operations/recover`, { action, command })).data },
}
export const reportLabels: Record<ReportKind,string> = { daily:'每日报数', match:'裁片核套', return:'外发收回', accept:'外发验收', handover:'交接下道' }
export const reportPermission = (kind: ReportKind) => kind === 'handover' ? 'handover_write' : kind === 'return' || kind === 'accept' ? 'acceptance_write' : 'report_write'

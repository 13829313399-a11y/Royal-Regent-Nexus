import { formatBusinessDate } from '@/lib/dateTime'
import { http } from '@/lib/http'
import type { CartonImportPreviewRow } from './cartonProcurement'

export type ScheduleScopeMode = 'FULL' | 'INCREMENTAL' | 'UNDECLARED'
export type ScheduleMissingDecision = 'KEEP_REQUIRED' | 'SOURCE_OMISSION' | 'NO_LONGER_REQUIRED' | 'REOPEN'
export type ScheduleMissingStatus = Exclude<ScheduleMissingDecision, 'REOPEN'> | 'PENDING' | 'RETURNED' | 'INVALIDATED' | 'SUPERSEDED'
export const scheduleMissingStatusLabels: Record<ScheduleMissingStatus, string> = { PENDING: '待核实', KEEP_REQUIRED: '已核实仍需采购', SOURCE_OMISSION: '业务漏列，继续跟进', NO_LONGER_REQUIRED: '已核实不再需要（订单另行变更）', RETURNED: '来源已重新出现', INVALIDATED: '原批次或比较依据已失效', SUPERSEDED: '已有新版核实项（历史只读）' }
export const scheduleMissingStatusLabel = (value: string) => scheduleMissingStatusLabels[value as ScheduleMissingStatus] || '待核对最新状态'
export interface ScheduleCoverageSummary {
  batch_id: string; filename: string; created_at: string; scope_mode: ScheduleScopeMode;
  as_of_date: string | null; coverage_start: string | null; coverage_end: string | null;
  date_basis: 'CUSTOMER_DUE_DATE'; excluded_count: number; missing_count: number;
}
export interface ScheduleCoverageCustomer {
  customer_code: string; customer_name: string; status: string;
  latest_import: ScheduleCoverageSummary | null; full_coverage: ScheduleCoverageSummary | null;
  pending_count: number; excluded_count: number;
}
export interface ScheduleCoverageExclusion { batch_id?: string; source_sheet: string; source_row: number; contract_no: string; item_no: string; source_customer_due_date?: string; reason: string }
export interface ScheduleCoverageEvidence {
  version: 1; scope_mode: ScheduleScopeMode; as_of_date: string | null; coverage_start: string | null; coverage_end: string | null;
  date_basis: 'CUSTOMER_DUE_DATE'; full_scope_confirmed: boolean; identity_profile?: Record<string, unknown>;
  excluded_rows?: ScheduleCoverageExclusion[]; missing_rows?: unknown[]; excluded_count?: number; missing_count?: number;
}
export interface ScheduleMissingHistory { id: string; decision: ScheduleMissingDecision; reason: string; actor_name: string; created_at: string; revision: number }
export interface ScheduleMissingCase {
  id: string; customer_code: string; customer_name: string; batch_id: string; as_of_date: string;
  coverage_start: string; coverage_end: string; date_basis: 'CUSTOMER_DUE_DATE'; identity: string;
  contract_no: string; item_no: string; customer_po: string; source_reference: string;
  source_rows: (CartonImportPreviewRow & { batch_id: string })[];
  status: ScheduleMissingStatus; revision: number; source_fingerprint: string;
  can_review: boolean; can_operate_source: boolean; history: ScheduleMissingHistory[];
  basis_changed?: boolean; effective_source_rows?: (CartonImportPreviewRow & { batch_id: string })[];
  current_order_ids?: string[]; current_manual_marked?: boolean;
  current_sources?: { batch_id: string; source_sheet: string; source_row: number; current_order_ids: string[]; current_manual_marked: boolean; manual_review_required: boolean }[];
  current_state_basis?: 'EXPLICIT_SOURCE_LINKS_AND_MANUAL_MARKS';
  excluded_rows?: ScheduleCoverageExclusion[];
}
export interface ScheduleCoverageWorkspace {
  factory_id: string; customers: ScheduleCoverageCustomer[];
  missing: { items: ScheduleMissingCase[]; total: number; limit: number; offset: number; pending_count: number };
}
const base = '/carton-procurement/schedule-coverage'
export const cartonScheduleCoverageApi = {
  async workspace(factory: string, query: { customer_code?: string; status: 'PENDING' | 'ALL'; keyword?: string; limit: number; offset: number }, signal?: AbortSignal) {
    return (await http.get<ScheduleCoverageWorkspace>(base + '/workspace', { params: { factory_id: factory, ...query }, signal })).data
  },
  async detail(factory: string, id: string, signal?: AbortSignal) {
    return (await http.get<ScheduleMissingCase>(`${base}/missing/${encodeURIComponent(id)}`, { params: { factory_id: factory }, signal })).data
  },
  async review(id: string, body: { factory_id: string; request_id: string; expected_revision: number; source_fingerprint: string; decision: ScheduleMissingDecision; reason: string }, signal?: AbortSignal) {
    return (await http.post<ScheduleMissingCase>(`${base}/missing/${encodeURIComponent(id)}/review`, body, { signal })).data
  },
}

export interface CartonScheduleImportScope {
  scope_mode: 'FULL' | 'INCREMENTAL'
  as_of_date: string
  coverage_start: string
  coverage_end: string
  full_scope_confirmed: boolean
}
export const emptyScheduleImportScope = (): CartonScheduleImportScope => ({ scope_mode: 'INCREMENTAL', as_of_date: formatBusinessDate(new Date().toISOString()), coverage_start: '', coverage_end: '', full_scope_confirmed: false })
export function scheduleScopeErrors(scope: CartonScheduleImportScope, today = formatBusinessDate(new Date().toISOString())): string[] {
  const errors: string[] = []
  const date = (value: string) => /^(?!0000)\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value + 'T00:00:00Z')) && new Date(value + 'T00:00:00Z').toISOString().slice(0, 10) === value
  if (!date(scope.as_of_date)) errors.push('请填写完整的业务排期日期。')
  else if (scope.as_of_date > today) errors.push('业务排期日期不能晚于上海今天。')
  if (scope.coverage_start || scope.coverage_end || scope.scope_mode === 'FULL') {
    if (!date(scope.coverage_start) || !date(scope.coverage_end)) errors.push('客户交期覆盖范围须填写完整的起止日期。')
    else if (scope.coverage_start > scope.coverage_end) errors.push('覆盖结束日期不能早于开始日期。')
  }
  if (scope.scope_mode === 'FULL' && !scope.full_scope_confirmed) errors.push('全量导入须明确确认该客户交期段的完整性。')
  return errors
}

import type { Tone } from '@/data/enterpriseMock'
import type {
  UvAdminStatus,
  UvCoverage,
  UvFreshness,
  UvHandoverState,
  UvJobState,
  UvPayrollState,
  UvPricingState,
  UvQualityStatus,
  UvRawUnit,
  UvReconciliation,
  UvReportStatus,
  UvRuntimeStatus,
  UvSourceKind,
} from '../contracts'

/**
 * 状态一律用业务语言输出，不直接展示枚举；颜色不能是唯一状态信号。
 * 同一列表中的同一状态必须保持同一色调。
 */

export interface StatusView {
  label: string
  tone: Tone
}

export const ADMIN_STATUS: Record<UvAdminStatus, StatusView> = {
  normal: { label: '正常', tone: 'green' },
  maintenance: { label: '维修中', tone: 'amber' },
  disabled: { label: '已停用', tone: 'slate' },
}

export const RUNTIME_STATUS: Record<UvRuntimeStatus, StatusView> = {
  printing: { label: '打印中', tone: 'teal' },
  idle: { label: '待机', tone: 'slate' },
  offline: { label: '离线', tone: 'red' },
  error: { label: '设备报错', tone: 'red' },
  unknown: { label: '状态未知', tone: 'slate' },
}

export const FRESHNESS: Record<UvFreshness, StatusView> = {
  fresh: { label: '心跳正常', tone: 'green' },
  stale: { label: '心跳过期', tone: 'amber' },
  never_seen: { label: '从未连接', tone: 'slate' },
}

export const JOB_STATE: Record<UvJobState, StatusView> = {
  observed: { label: '观察到', tone: 'slate' },
  running: { label: '进行中', tone: 'teal' },
  completed: { label: '已完成', tone: 'green' },
  cancelled: { label: '已取消', tone: 'slate' },
  uncertain: { label: '完工不确定', tone: 'amber' },
}

export const RECONCILIATION: Record<UvReconciliation, StatusView> = {
  unmatched: { label: '产品未匹配', tone: 'amber' },
  needs_unit: { label: '数量单位待确认', tone: 'amber' },
  ready: { label: '可分配', tone: 'blue' },
  partially_allocated: { label: '部分已分配', tone: 'blue' },
  allocated: { label: '已分配完', tone: 'green' },
  ignored: { label: '已忽略', tone: 'slate' },
}

export const RAW_UNIT: Record<UvRawUnit, string> = {
  piece: '件',
  board: '板',
  cycle: '次',
  unknown: '单位未知',
}

export const REPORT_STATUS: Record<UvReportStatus, StatusView> = {
  draft: { label: '草稿', tone: 'slate' },
  confirmed: { label: '已确认', tone: 'green' },
  corrected: { label: '已更正', tone: 'blue' },
  voided: { label: '已作废', tone: 'red' },
}

export const QUALITY_STATUS: Record<UvQualityStatus, StatusView> = {
  pending: { label: '质量待判定', tone: 'amber' },
  partial: { label: '质量部分判定', tone: 'amber' },
  complete: { label: '质量已判清', tone: 'green' },
}

export const PAYROLL_STATE: Record<UvPayrollState, StatusView> = {
  unpriced: { label: '未定价', tone: 'amber' },
  provisional: { label: '暂算待核', tone: 'amber' },
  confirmed: { label: '已确认', tone: 'green' },
}

export const PRICING_STATE: Record<UvPricingState, StatusView> = {
  priced: { label: '已定价', tone: 'green' },
  unpriced: { label: '未定价', tone: 'amber' },
}

export const SOURCE_KIND: Record<UvSourceKind, StatusView> = {
  manual: { label: '人工确认', tone: 'blue' },
  device: { label: '设备记录', tone: 'teal' },
  import: { label: '导入归档', tone: 'slate' },
  mixed: { label: '人工 + 设备', tone: 'blue' },
}

export const HANDOVER_STATE: Record<UvHandoverState, StatusView> = {
  reconciled: { label: '已核对一致', tone: 'green' },
  difference: { label: '有差异待处理', tone: 'amber' },
  pending: { label: '待接收核对', tone: 'slate' },
}

export const COVERAGE: Record<UvCoverage, StatusView> = {
  complete: { label: '数据完整', tone: 'green' },
  partial: { label: '部分覆盖·暂算', tone: 'amber' },
  no_data: { label: '无数据', tone: 'slate' },
}

export const TIME_EVIDENCE_LABEL: Record<'observed' | 'inferred' | 'unknown', string> = {
  observed: '设备时间',
  inferred: '推断时间',
  unknown: '时间待确认',
}

export const CAPABILITY_LABELS: Record<string, string> = {
  progress: '准确进度',
  exact_completion: '可信完工信号',
  ink_by_color: '分色耗墨',
  stable_job_id: '稳定作业 ID',
}

export const EXPENSE_CATEGORY_LABELS: Record<string, string> = {
  equipment: '设备投资',
  tooling: '工具费用',
  material: '材料',
  sundry: '杂费',
  maintenance: '维修',
  ink: '油墨',
  processing: '加工费',
  rent: '房租',
  utilities: '水电',
  management_wage: '管理人员工资',
  night_subsidy: '夜班补贴',
  recoverable_wage: '可回收工资',
  recoverable_paint: '可回收油漆',
}

export const WORKER_ROLE_LABELS: Record<string, string> = {
  operator: '操作员',
  foreman: '管工',
  master: '师傅',
  assistant: '助理',
}

export const EMPLOY_STATE_LABELS: Record<string, string> = {
  active: '在职',
  left: '已离职',
}

export const RATE_KIND_LABELS: Record<string, string> = {
  commercial: '商业执行单价',
  piece_wage: '计件工价',
  area: '面积费率',
}

export const INK_MATERIAL_LABELS: Record<string, string> = {
  hard: '硬墨',
  soft: '软墨',
  other: '其他材质',
}

export const INK_MOVEMENT_LABELS: Record<string, string> = {
  opening: '期初',
  purchase_in: '采购入库',
  issue_out: '领用出库',
  return_in: '退回入库',
  stocktake: '盘点调整',
  reversal: '冲销',
}

export const DRILL_KIND_LABELS: Record<string, string> = {
  reports: '业务报工',
  jobs: '采集作业',
  ink_movements: '墨水流水',
  expenses: '费用记录',
  payroll: '工资明细',
  handovers: '入库核数',
  unpriced_reports: '未定价报工',
}

export function statusOrUnknown<T extends string>(
  map: Record<T, StatusView>,
  key: T | null | undefined,
): StatusView {
  if (key && key in map) return map[key]
  return { label: '未知', tone: 'slate' }
}

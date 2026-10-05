export const SPRAY_BASE = '/modules/production/spray-production'
export const SPRAY_FACTORIES = ['huaxing', 'huadeng', 'huakang-a', 'huakang-b'] as const
export type SprayFactory = typeof SPRAY_FACTORIES[number]
export const FACTORY_NAMES: Record<SprayFactory, string> = { huaxing: '华兴', huadeng: '华登', 'huakang-a': '华康A', 'huakang-b': '华康B' }
export const SPRAY_NAV = [
  { path: 'overview', label: '工作总览', short: '总览', icon: 'LayoutDashboard' },
  { path: 'planning', label: '计划调度', short: '计划', icon: 'CalendarRange' },
  { path: 'execution', label: '现场执行', short: '执行', icon: 'ClipboardCheck' },
  { path: 'handover', label: '胶件与交收', short: '交收', icon: 'PackageCheck' },
  { path: 'materials', label: '油漆与采购', short: '油漆', icon: 'PaintBucket' },
  { path: 'finance', label: '经营与月结', short: '经营', icon: 'ChartNoAxesCombined' },
  { path: 'master', label: '基础资料', short: '基础', icon: 'SlidersHorizontal' },
] as const
export const sprayEnabled = () => import.meta.env.VITE_SPRAY_OPS_ENABLED === 'true'
export const isSprayFactory = (value: unknown): value is SprayFactory => typeof value === 'string' && (SPRAY_FACTORIES as readonly string[]).includes(value)

export interface Envelope<T> {
  meta: { factory_id: SprayFactory; as_of: string; factory_revision: number; data_mode: 'live'; warnings: { code: string; message: string; entity_id?: string }[]; coverage?: Record<string, 'complete' | 'partial' | 'unknown'> }
  data: T
  pagination?: { page: number; page_size: number; total: number }
}
export interface Entity { id: string; factory_id: SprayFactory; version: number; created_at: string; updated_at: string; [key: string]: unknown }
export interface Capability extends Entity { capability: string; hourly_capacity: string | null; evidence: string }
export interface CalendarWindow extends Entity { start_at: string; end_at: string; kind: string; reason: string }
export interface Resource extends Entity { code: string; name: string; kind: string; capacity: number; enabled: boolean; capabilities: Capability[]; calendar: CalendarWindow[] }
export interface Step extends Entity { route_id: string; code: string; name: string; capability: string; predecessors: string[]; prep_required: boolean; input_unit: string; output_unit: string; output_ratio: string; drying_minutes: number }
export interface RouteVersion extends Entity { code: string; label: string; revision: number; status: string; steps: Step[]; evidence: string }
export interface DemandLine extends Entity { demand_id: string; item_no: string; part: string; color: string; quantity: string; unit: string; due_date: string; expected_arrival: string | null; route_id: string | null; priority: number; split_allowed: boolean; received: string; opening_balance?: string; balances: Record<string, string>; balances_by_unit?: Record<string, Record<string, string>>; commercial_price?: string | null; currency: string }
export interface Demand extends Entity { document_no: string; counterparty: string; source_factory: string | null; status: string; business_date: string; source_ref: string; note: string; lines: DemandLine[]; journey?: {line_id:string;step_id:string;processed:string;good:string;rework_processed:string;input_unit:string;output_unit:string}[] }
export interface Stock extends Entity { batch_id: string; line_id: string | null; state: string; quantity: string; reserved: string; unit: string; ready_at: string; pending_step_id: string | null }
export interface Batch extends Entity { document_no: string; line_id: string | null; item_no: string; part: string; quantity: string; accepted: string; held: string; rejected: string; unit: string; business_date: string }
export interface Allocation extends Entity { task_id: string; stock_id: string; line_id: string; quantity: string; consumed: string }
export interface Task extends Entity { scenario_id: string; step_id: string; resource_id: string; start_at: string; end_at: string; actual_start: string | null; actual_end: string | null; quantity: string; reported: string; status: string; note: string; allocations: Allocation[] }
export interface TaskDraft { step_id: string; resource_id: string; start_at: string; end_at: string; allocations: { stock_id: string; quantity: string }[]; note?: string }
export interface Scenario extends Entity { label: string; base_revision: number; status: string; snapshot: { tasks: TaskDraft[]; original: Task[]; replace_task_ids: string[]; unplanned: { line_id: string; code: string; message: string }[]; start_at: string; end_at: string } }
export interface Employee extends Entity { code: string; name: string; enabled: boolean }
export interface DeliveryLine extends Entity { delivery_id: string; stock_id: string; quantity: string; accepted: string; rejected: string; returned: string; settled: string; price?: string | null; currency: string; accepted_date: string | null; unit: string; acceptances: { business_date: string; quantity: string }[] }
export interface Delivery extends Entity { document_no: string; counterparty: string; business_date: string; status: string; warehouse_ref: string; lines: DeliveryLine[] }
export interface Rule extends Entity { code: string; label: string; kind: string; revision: number; status: string; parameters?: Record<string, string | null>; effective_from: string; evidence?: string }
export interface Settlement extends Entity { document_no: string; counterparty: string; month: string; currency: string; total_amount?: string; status: string; lines: (Entity & { delivery_line_id: string; delivery_document_no: string; delivery_date: string; demand_id: string; order_document_no: string; item_part: string; unit: string; quantity: string; price: string; amount: string })[] }
export const stateLabel: Record<string, string> = { cost_confirmation:'原批成本确认',cost_adjustment:'耗用成本补确认',wage:'员工工资', unit:'单位换算', exchange:'币种折算', operation_price:'工序产值', team_piece:'班组计件', personal_piece:'个人计件', hourly:'按实际工时', fixed_shift:'每日固定', historical_normalized:'历史时长折算', processed:'加工数量', good:'合格数量', expense:'费用', recovery:'回收冲减', investment:'投入', memo:'参考备忘', issue:'领用', consume:'耗用', return:'退回', paused: '已暂停', conditional: '待条件兑现', converted: '已兑现', reversed: '已冲销', opening: '期初结余', draft: '草稿', confirmed: '已确认', planned: '已排待开', started: '正在执行', completed: '已完成', cancelled: '已取消', white: '白件', wip: '在制', hold: '待判', finished: '合格成品', dispatched: '在途', partial_accepted: '部分验收', accepted: '已验收', trial: '试算待核', review: '待核对', partial: '部分完成', unknown: '资料缺失', complete: '已齐备', ordered: '待到货', closed: '已锁月', open: '可登记' }
export const number = (value: unknown) => value === null || value === undefined || value === '' ? '待确认' : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 6 })
export const dateTime = (value: unknown) => typeof value === 'string' && value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) : '待确认'
export const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
export const utc = (local: string) => new Date(local.length === 16 ? local + ':00+08:00' : local).toISOString()
export const documentNo = (prefix: string) => `${prefix}-${today().replaceAll('-', '')}-${crypto.randomUUID().slice(0, 6).toUpperCase()}`

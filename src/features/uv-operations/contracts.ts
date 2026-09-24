export const UV_BASE = '/modules/production/uv-printing'
export const UV_FACTORY = 'huakang-a'
export interface Entity { id: string; version: number; [key: string]: unknown }
export interface Meta {
  factory_id: string; as_of: string; data_mode: 'live' | 'synthetic'; authorization_version: number; view_revision: number
  coverage: { state: string; unmatched_runs: number | null; unconfirmed_output: number | null; missing_cost_records: number | null }
  warnings: string[]
}
export interface Envelope<T> { data: T; meta: Meta; pagination?: { total: number; next_cursor: string | null; has_more: boolean } }
export interface WorkspaceSnapshot { machines: Entity[]; tasks: Entity[]; schedule: Entity[]; shifts: Entity[]; batches: Entity[]; runs: Entity[]; collection_totals: Record<string, number> }
export function str(row: Entity | Record<string, unknown> | undefined, key: string, fallback = '—'): string {
  const value = row?.[key]
  return value === null || value === undefined || value === '' ? fallback : String(value)
}
export const num = (row: Entity | undefined, key: string) => Number(row?.[key] ?? 0)
export const object = (value: unknown) => (value && typeof value === 'object' && !Array.isArray(value) ? value : {}) as Entity
export const entities = (value: unknown) => Array.isArray(value) ? value as Entity[] : []
export function displayTime(value: unknown) {
  if (!value) return '尚未采集'
  const parsed = new Date(String(value))
  return Number.isNaN(parsed.valueOf()) ? '未知时间' : new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(parsed)
}
export const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
export const utcInput = (value: string) => /Z$|[+-]\d{2}:\d{2}$/.test(value) ? value : value + ':00+08:00'
export const stateLabels: Record<string, string> = {
  ready:'已就绪', planned:'已排程', in_progress:'执行中', completed:'已完成', open:'进行中', closed:'已关闭',
  pending:'待签收', partial:'部分完成', settled:'已结清', fresh:'采集正常', stale:'采集延迟', offline:'连接中断', unconfigured:'尚未配置',
  unknown:'未知', idle:'空闲', running:'运行中', paused:'暂停', fault:'故障', failed:'失败', cancelled:'已取消',
  simulator:'合成模拟器', generic_csv_log:'日志采集 · 待现场验证', queued:'排队中', preview:'待确认', committed:'已导入',
  receipt:'入库', consume:'耗用', transfer:'转移', return:'退回', reverse:'冲销', stocktake_in:'盘盈', stocktake_out:'盘亏',
}
export const label = (value: unknown) => stateLabels[String(value)] ?? String(value ?? '—')

/** A late response from a different identity/context can never write into cache. */
export class ContextFence {
  generation = 0
  private controllers = new Set<AbortController>()
  begin() { const controller = new AbortController(); this.controllers.add(controller); return { generation:this.generation, controller } }
  current(ticket: {generation:number}) { return ticket.generation === this.generation }
  finish(ticket: {controller:AbortController}) { this.controllers.delete(ticket.controller) }
  clear() { this.generation++; this.controllers.forEach(controller=>controller.abort()); this.controllers.clear() }
}

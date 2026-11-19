export type FactoryId = 'huaxing' | 'huadeng' | 'huakang-a' | 'huakang-b'
export const factories: Record<FactoryId, string> = {
  huaxing: '华兴',
  huadeng: '华登',
  'huakang-a': '华康 A',
  'huakang-b': '华康 B',
}
export interface DataRow {
  id: string
  revision: number
  [key: string]: any
}
export interface FieldSpec {
  key: string
  label: string
  value_type: string
  editable: boolean
  group: string
  legacy_column: string | null
  unit: string | null
  filter_ops: string[]
}
export interface FilterNode {
  logic?: 'AND' | 'OR'
  children?: FilterNode[]
  field?: string
  op?: string
  value?: unknown
}
export interface SearchSpec {
  field: string
  mode: string
  text: string
}
export interface QuerySpec {
  factory_id: FactoryId
  filter?: FilterNode | null
  search?: SearchSpec
  sort?: { field: string; direction: string }[]
  columns?: string[]
  page_size: number
  cursor?: number | null
}
export interface QueryResult {
  rows: DataRow[]
  total_count: number
  filtered_summary: Record<string, number>
  revision: number
  shared_revision: number
  next_cursor: number | null
}
export const dateText = (value: unknown) =>
  value ? String(value).replace('T', ' ').slice(0, 16) : '—'
export const numberText = (value: unknown) =>
  value == null
    ? '—'
    : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
export function displayValue(value: unknown, field?: FieldSpec): string {
  if (value == null || value === '') return '—'
  if (field?.value_type === 'datetime') return dateText(value)
  if (typeof value === 'object') return JSON.stringify(value)
  if (field && ['number', 'integer'].includes(field.value_type))
    return numberText(value)
  return String(value)
}
export function parseValue(text: string, field: FieldSpec): unknown {
  if (text.trim() === '') return null
  if (['number', 'integer'].includes(field.value_type)) {
    const n = Number(text.replaceAll(',', ''))
    if (
      !Number.isFinite(n) ||
      (field.value_type === 'integer' && !Number.isInteger(n))
    )
      throw new Error(
        `${field.label}需要${field.value_type === 'integer' ? '整数' : '数字'}`,
      )
    return n
  }
  if (field.value_type === 'datetime') {
    const value = new Date(text)
    if (Number.isNaN(value.getTime())) throw new Error(`${field.label}日期无效`)
    return value.toISOString()
  }
  if (field.value_type === 'json') return JSON.parse(text)
  if (field.value_type === 'boolean') return ['true', '是', '1'].includes(text)
  return text
}
export const statusText: Record<string, string> = {
  PLANNED: '计划待开工',
  RUNNING: '在产',
  PAUSED: '暂停',
  FINISHED: '已结束',
  AVAILABLE: '可用',
  MAINTENANCE: '检修',
  STOPPED: '停机',
  READY: '可排',
  HOLD: '暂停排产',
  CANCELLED: '已取消',
  IDLE: '待开工',
  FAULT: '故障',
  DISABLED: '停用',
  TRANSFERRED: '已转机',
  UNAVAILABLE: '暂不可用',
  WAIT_NOTICE: '待通知',
  WAIT_MATERIAL: '待料',
  MOLD_REPAIR: '修模',
}
export function productionShift(
  settings: Record<string, any>,
  now = new Date(),
) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: settings.business_timezone || 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(now)
  const part = (key: string) => parts.find((p) => p.type === key)!.value
  const localDay = `${part('year')}-${part('month')}-${part('day')}`
  const minutes = (value: string) => {
    const [h, m] = value.split(':').map(Number)
    return h! * 60 + m!
  }
  const time = minutes(`${part('hour')}:${part('minute')}`),
    day = minutes(settings.day_start || '08:00'),
    night = minutes(settings.night_start || '20:00')
  const offset = (time - day + 1440) % 1440,
    duration = (night - day + 1440) % 1440
  const base = new Date(localDay + 'T12:00:00Z')
  if (time < day) base.setUTCDate(base.getUTCDate() - 1)
  return {
    date: base.toISOString().slice(0, 10),
    shift: offset < duration ? 'DAY' : 'NIGHT',
  }
}

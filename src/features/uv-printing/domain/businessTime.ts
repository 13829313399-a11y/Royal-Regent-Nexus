import type { BusinessDate, IsoInstant, ShiftCode, ShiftScope } from '../contracts'

/**
 * 业务时间口径（docs/uv-printing/UV_PRINT_SHARED_SPEC.md 5.3）。
 *
 * - 业务时间固定 Asia/Shanghai，事件时间入库为明确 UTC 时间戳；
 * - 业务日期是「班次开始的当地日期」，不随客户端电脑时区改变；
 * - 时间区间左闭右开；
 * - 默认班次模板可版本化，白班 07:40–21:00、夜班 21:00–次日 07:40。
 */

export const UV_TIME_ZONE = 'Asia/Shanghai'

export interface ShiftTemplateSpec {
  shift: ShiftCode
  label: string
  /** 当地开始时刻 HH:mm */
  startLocal: string
  /** 当地结束时刻 HH:mm，夜班跨到次日 */
  endLocal: string
  breakMinutes: number
  versionId: string
}

export const DEFAULT_SHIFT_TEMPLATES: Record<ShiftCode, ShiftTemplateSpec> = {
  day: {
    shift: 'day',
    label: '白班',
    startLocal: '07:40',
    endLocal: '21:00',
    breakMinutes: 0,
    versionId: 'shift-template-v1-day',
  },
  night: {
    shift: 'night',
    label: '夜班',
    startLocal: '21:00',
    endLocal: '07:40',
    breakMinutes: 0,
    versionId: 'shift-template-v1-night',
  },
}

export const SHIFT_LABELS: Record<ShiftScope, string> = {
  day: '白班',
  night: '夜班',
  all: '全天',
}

interface ZonedParts {
  year: number
  month: number
  day: number
  hour: number
  minute: number
  second: number
}

const partsFormatter = new Intl.DateTimeFormat('en-CA', {
  timeZone: UV_TIME_ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

export function shanghaiParts(instant: IsoInstant | Date): ZonedParts {
  const date = instant instanceof Date ? instant : new Date(instant)
  const parts = partsFormatter.formatToParts(date)
  const lookup = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((part) => part.type === type)?.value ?? '0')
  const hour = lookup('hour')
  return {
    year: lookup('year'),
    month: lookup('month'),
    day: lookup('day'),
    hour: hour === 24 ? 0 : hour,
    minute: lookup('minute'),
    second: lookup('second'),
  }
}

function pad(value: number, size = 2) {
  return String(value).padStart(size, '0')
}

export function shanghaiDateString(instant: IsoInstant | Date): BusinessDate {
  const parts = shanghaiParts(instant)
  return `${parts.year}-${pad(parts.month)}-${pad(parts.day)}`
}

export function shanghaiTimeString(instant: IsoInstant | Date): string {
  const parts = shanghaiParts(instant)
  return `${pad(parts.hour)}:${pad(parts.minute)}`
}

export function shanghaiDateTimeString(instant: IsoInstant | Date): string {
  return `${shanghaiDateString(instant)} ${shanghaiTimeString(instant)}`
}

export function minutesOfDay(instant: IsoInstant | Date): number {
  const parts = shanghaiParts(instant)
  return parts.hour * 60 + parts.minute
}

function parseLocalMinutes(value: string): number {
  const [hour = '0', minute = '0'] = value.split(':')
  return Number(hour) * 60 + Number(minute)
}

/** 上海时区某个当地时刻对应的 UTC 瞬间。 */
export function shanghaiInstant(businessDate: BusinessDate, localTime: string): IsoInstant {
  const [year, month, day] = businessDate.split('-').map(Number)
  const [hour, minute] = localTime.split(':').map(Number)
  const guess = Date.UTC(year, (month ?? 1) - 1, day ?? 1, hour ?? 0, minute ?? 0, 0)
  const offset = shanghaiOffsetMinutes(new Date(guess))
  return new Date(guess - offset * 60_000).toISOString()
}

/** Asia/Shanghai 当时是否处于夏令时（历史上曾用过，当前恒为 +08:00）。 */
export function shanghaiOffsetMinutes(date: Date): number {
  const parts = shanghaiParts(date)
  const asUtc = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute, parts.second)
  return Math.round((asUtc - Math.floor(date.getTime() / 1000) * 1000) / 60_000)
}

export interface ShiftMembership {
  business_date: BusinessDate
  shift: ShiftCode
  /** 该班次的开始与结束瞬间，左闭右开。 */
  start_at: IsoInstant
  end_at: IsoInstant
  template_version_id: string
}

/**
 * 严格按 5.3 节归属：07:39:59 属于前一日夜班，07:40:00 起属于当日白班，
 * 21:00:00 起属于当日夜班；夜班跨月时业务日期仍是班次开始日。
 */
export function shiftMembership(instant: IsoInstant | Date, templates = DEFAULT_SHIFT_TEMPLATES): ShiftMembership {
  const localDate = shanghaiDateString(instant)
  const minutes = minutesOfDay(instant)
  const dayStart = parseLocalMinutes(templates.day.startLocal)
  const nightStart = parseLocalMinutes(templates.night.startLocal)

  if (minutes >= dayStart && minutes < nightStart) {
    const template = templates.day
    return {
      business_date: localDate,
      shift: 'day',
      start_at: shanghaiInstant(localDate, template.startLocal),
      end_at: shanghaiInstant(localDate, template.endLocal),
      template_version_id: template.versionId,
    }
  }

  const nightTemplate = templates.night
  const businessDate = minutes < dayStart ? addDays(localDate, -1) : localDate
  return {
    business_date: businessDate,
    shift: 'night',
    start_at: shanghaiInstant(businessDate, nightTemplate.startLocal),
    end_at: shanghaiInstant(addDays(businessDate, 1), nightTemplate.endLocal),
    template_version_id: nightTemplate.versionId,
  }
}

export function addDays(businessDate: BusinessDate, days: number): BusinessDate {
  const [year, month, day] = businessDate.split('-').map(Number)
  const next = new Date(Date.UTC(year, (month ?? 1) - 1, day ?? 1))
  next.setUTCDate(next.getUTCDate() + days)
  return `${next.getUTCFullYear()}-${pad(next.getUTCMonth() + 1)}-${pad(next.getUTCDate())}`
}

export function monthOf(businessDate: BusinessDate): string {
  return businessDate.slice(0, 7)
}

export function daysInMonth(month: string): BusinessDate[] {
  const [year, monthNumber] = month.split('-').map(Number)
  const total = new Date(Date.UTC(year, monthNumber ?? 1, 0)).getUTCDate()
  return Array.from({ length: total }, (_, index) => `${month}-${pad(index + 1)}`)
}

export function weekdayLabel(businessDate: BusinessDate): string {
  const [year, month, day] = businessDate.split('-').map(Number)
  const date = new Date(Date.UTC(year, (month ?? 1) - 1, day ?? 1))
  return ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][date.getUTCDay()] ?? ''
}

export function isSunday(businessDate: BusinessDate): boolean {
  const [year, month, day] = businessDate.split('-').map(Number)
  return new Date(Date.UTC(year, (month ?? 1) - 1, day ?? 1)).getUTCDay() === 0
}

/**
 * 把一段运行时间按班次区间拆分，用于利用率；同一份产量不会在两天重复计。
 * 返回按业务日/班次聚合的分钟数（左闭右开）。
 */
export function splitByShift(
  startAt: IsoInstant,
  endAt: IsoInstant,
  templates = DEFAULT_SHIFT_TEMPLATES,
): Array<{ business_date: BusinessDate; shift: ShiftCode; minutes: number }> {
  const result = new Map<string, { business_date: BusinessDate; shift: ShiftCode; minutes: number }>()
  let cursor = new Date(startAt).getTime()
  const end = new Date(endAt).getTime()
  if (!Number.isFinite(cursor) || !Number.isFinite(end) || end <= cursor) return []

  let guard = 0
  while (cursor < end && guard < 400) {
    guard += 1
    const membership = shiftMembership(new Date(cursor), templates)
    const boundary = new Date(membership.end_at).getTime()
    const sliceEnd = Math.min(boundary, end)
    const minutes = Math.max(0, Math.round((sliceEnd - cursor) / 60_000))
    const key = `${membership.business_date}:${membership.shift}`
    const existing = result.get(key)
    if (existing) existing.minutes += minutes
    else result.set(key, { business_date: membership.business_date, shift: membership.shift, minutes })
    cursor = sliceEnd
    if (sliceEnd <= new Date(membership.start_at).getTime()) break
  }

  return [...result.values()].sort((a, b) =>
    a.business_date === b.business_date
      ? a.shift.localeCompare(b.shift)
      : a.business_date.localeCompare(b.business_date),
  )
}

export function minutesBetween(startAt: IsoInstant | null, endAt: IsoInstant | null): number | null {
  if (!startAt || !endAt) return null
  const start = new Date(startAt).getTime()
  const end = new Date(endAt).getTime()
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null
  return Math.round((end - start) / 60_000)
}

export function formatDuration(minutes: number | null): string {
  if (minutes === null) return '—'
  if (minutes < 60) return `${minutes} 分钟`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest === 0 ? `${hours} 小时` : `${hours} 小时 ${rest} 分`
}

/** 心跳新鲜度阈值默认 5 分钟，与旧系统一致，可按实际心跳周期配置。 */
export const FRESHNESS_THRESHOLD_MINUTES = 5

export type FreshnessBucket = 'fresh' | 'stale' | 'never_seen'

export function freshnessOf(
  lastHeartbeatAt: IsoInstant | null,
  asOf: IsoInstant,
  thresholdMinutes = FRESHNESS_THRESHOLD_MINUTES,
): { freshness: FreshnessBucket; ageMinutes: number | null } {
  if (!lastHeartbeatAt) return { freshness: 'never_seen', ageMinutes: null }
  const minutes = minutesBetween(lastHeartbeatAt, asOf)
  if (minutes === null) return { freshness: 'never_seen', ageMinutes: null }
  return { freshness: minutes <= thresholdMinutes ? 'fresh' : 'stale', ageMinutes: minutes }
}

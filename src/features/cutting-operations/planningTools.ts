import type { WorkCalendarData } from './api'
import type { PlanTaskInput } from './planning'

const DAY = 86400000
function timestamp(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value < '2000-01-01' || value > '2100-12-31') throw new Error('请选择有效日期（2000～2100年）')
  const stamp = Date.parse(`${value}T00:00:00Z`)
  if (!Number.isFinite(stamp) || new Date(stamp).toISOString().slice(0, 10) !== value) throw new Error('日期无效')
  return stamp
}
export function generateDailyPlan(start: string, end: string, sets: number, remaining: number, calendar: WorkCalendarData | null, occupied: string[] = []) {
  const first = timestamp(start), last = timestamp(end)
  if (last < first || (last - first) / DAY >= 730) throw new Error('日期区间须按先后顺序，且最多730天')
  if (!Number.isSafeInteger(sets) || sets < 1 || sets > 1e9 || !Number.isSafeInteger(remaining) || remaining < 1 || remaining > 1e9) throw new Error('每日套数与剩余目标须为有效正整数')
  const weekdays = calendar?.weekdays ?? [1, 2, 3, 4, 5, 6]
  if (!weekdays.length) throw new Error('工作周不可为空')
  const exceptions = new Map(calendar?.exceptions.map(e => [e.day, e.working]) ?? [])
  const used = new Set(occupied), result: PlanTaskInput['days'] = []
  let left = remaining
  for (let stamp = first; stamp <= last && left; stamp += DAY) {
    const date = new Date(stamp), day = date.toISOString().slice(0, 10)
    const working = exceptions.get(day) ?? weekdays.includes(date.getUTCDay() || 7)
    if (working && !used.has(day)) {
      const quantity = Math.min(sets, left)
      result.push({ day, sets: quantity }); left -= quantity
    }
  }
  if (!result.length) throw new Error('区间内没有可新增的工作日，请核对日历与已有日期')
  return result
}

export function copyDailyPlan(days: PlanTaskInput['days'], start: string, remaining: number, calendar: WorkCalendarData | null, occupied: string[] = []) {
  if (!days.length) throw new Error('没有可复制的日计划')
  const first = timestamp(start)
  if (!Number.isSafeInteger(remaining) || remaining < 1 || remaining > 1e9) throw new Error('没有可编排的有效剩余套数')
  // Copy quantities in date order while skipping rest/occupied days in the destination.
  const sorted = [...days].sort((a, b) => a.day.localeCompare(b.day))
  const result: PlanTaskInput['days'] = [], used = [...occupied]
  let cursor = first, left = remaining
  for (const day of sorted) {
    if (!left) break
    const end = Math.min(timestamp('2100-12-31'), cursor + 729 * DAY)
    const next = generateDailyPlan(new Date(cursor).toISOString().slice(0, 10), new Date(end).toISOString().slice(0, 10), day.sets, Math.min(day.sets, left), calendar, used)[0]!
    result.push(next); used.push(next.day); left -= next.sets; cursor = timestamp(next.day) + DAY
  }
  return result
}

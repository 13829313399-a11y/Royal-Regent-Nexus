import { formatBusinessDate, formatBusinessDateTime, parseBusinessTimestamp } from '@/lib/dateTime'
import type { WorkEntry } from './types'

const hour = 3_600_000
const day = 24 * hour

export function aging(entry: WorkEntry, serverTime?: string) {
  const now = parseBusinessTimestamp(serverTime)
  const due = parseBusinessTimestamp(entry.due_at)
  const opened = parseBusinessTimestamp(entry.opened_at)
  const absolute = entry.due_at || entry.opened_at
  const exact = absolute
    ? formatBusinessDateTime(absolute) +
      (entry.due_at ? ' 到期' : entry.module === 'account_requests' ? ' 提交' : ' 发起')
    : ''
  if (now === null) return { text: exact, exact, tone: 'calm' }
  if (due !== null) {
    const distance = due - now
    const amount = Math.abs(distance)
    const units =
      amount < day
        ? Math.max(1, Math.ceil(amount / hour)) + ' 小时'
        : Math.max(1, Math.floor(amount / day)) + ' 天'
    if (distance < 0 && entry.can_act_now) return { text: '已逾期 ' + units, exact, tone: 'overdue' }
    if (distance >= 0)
      return {
        text: distance < day ? '剩 ' + units + '到期' : units + '后到期',
        exact,
        tone: distance < day ? 'warning' : 'calm',
      }
    return { text: exact, exact, tone: 'calm' }
  }
  if (opened === null) return { text: '', exact, tone: 'calm' }
  if (entry.kind === 'info' || !['open', 'in_progress'].includes(entry.lifecycle ?? ''))
    return { text: exact, exact, tone: 'calm' }
  const elapsed = Math.max(0, now - opened)
  const text =
    elapsed < hour
      ? '刚刚发起'
      : '已等待 ' + (elapsed < day ? Math.floor(elapsed / hour) + ' 小时' : Math.floor(elapsed / day) + ' 天')
  return { text, exact, tone: elapsed >= 3 * day ? 'aging' : 'calm' }
}

export function snoozePresets(serverTime?: string) {
  const now = parseBusinessTimestamp(serverTime)
  if (now === null) return []
  const midnight = Date.parse(formatBusinessDate(serverTime) + 'T00:00:00+08:00')
  const afternoon = now < midnight + 13.5 * hour
  return [
    { label: '1 小时后', at: now + hour },
    { label: afternoon ? '今天下午 14:00' : '今天傍晚 17:30', at: midnight + (afternoon ? 14 : 17.5) * hour },
    { label: '明天上午 09:00', at: midnight + day + 9 * hour },
  ].map((item) => ({ label: item.label, until: new Date(item.at).toISOString(), disabled: item.at <= now }))
}

export function customSnooze(value: string, serverTime?: string) {
  const now = parseBusinessTimestamp(serverTime)
  if (now === null || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return null
  const iso = value + ':00+08:00'
  const at = parseBusinessTimestamp(iso)
  return at !== null && at > now && formatBusinessDateTime(iso) === value.replace('T', ' ')
    ? new Date(at).toISOString()
    : null
}

export function isSnoozed(entry: WorkEntry, serverTime?: string) {
  const until = parseBusinessTimestamp(entry.personal.snoozed_until)
  const now = parseBusinessTimestamp(serverTime)
  return entry.can_act_now && now !== null && until !== null && until > now
}

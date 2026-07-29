import type { ProductionCalendar, ProductionWindow } from '@/types/injectionScheduling'

function toMs(value: string) {
  return new Date(value).getTime()
}

function intersectHours(start: number, end: number, window: ProductionWindow) {
  const overlapStart = Math.max(start, toMs(window.startAt))
  const overlapEnd = Math.min(end, toMs(window.endAt))
  return Math.max(0, overlapEnd - overlapStart) / 3_600_000
}

export function addProductionHours(
  anchorAt: string,
  requiredHours: number,
  calendar: ProductionCalendar,
): string {
  let remaining = Math.max(0, requiredHours)
  let cursor = toMs(anchorAt)

  const windows = [...calendar.availabilityWindows]
    .sort((left, right) => toMs(left.startAt) - toMs(right.startAt))

  for (const window of windows) {
    const windowStart = Math.max(cursor, toMs(window.startAt))
    const windowEnd = toMs(window.endAt)
    if (windowEnd <= windowStart) continue

    const downtimeHours = calendar.downtimeWindows.reduce(
      (total, downtime) => total + intersectHours(windowStart, windowEnd, downtime),
      0,
    )
    const availableHours = Math.max(0, (windowEnd - windowStart) / 3_600_000 - downtimeHours)
    if (remaining <= availableHours) {
      let result = windowStart + remaining * 3_600_000
      for (const downtime of calendar.downtimeWindows) {
        const downtimeStart = toMs(downtime.startAt)
        const downtimeEnd = toMs(downtime.endAt)
        if (downtimeStart >= windowStart && downtimeStart < result) {
          result += Math.max(0, downtimeEnd - downtimeStart)
        }
      }
      return new Date(result).toISOString()
    }
    remaining -= availableHours
    cursor = windowEnd
  }

  return new Date(cursor + remaining * 3_600_000).toISOString()
}

export function addCalendarHours(anchorAt: string, hours: number) {
  return new Date(toMs(anchorAt) + hours * 3_600_000).toISOString()
}

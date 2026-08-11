import type { SchedulingColumnDefinition } from '../types'

export interface SchedulingGroupHeaderSegment {
  id: string
  group: string
  frozen: boolean
  columnKeys: string[]
  width: number
  left?: number
}

export function buildSchedulingGroupHeaderSegments(
  columns: readonly SchedulingColumnDefinition[],
  columnSizes: Readonly<Record<string, number>>,
) {
  const segments: SchedulingGroupHeaderSegment[] = []
  let frozenLeft = 0

  for (const column of columns) {
    const key = String(column.key)
    const width = columnSizes[key] ?? column.width
    const frozen = Boolean(column.frozen)
    const previous = segments.at(-1)

    if (previous && previous.group === column.group && previous.frozen === frozen) {
      previous.columnKeys.push(key)
      previous.width += width
    } else {
      segments.push({
        id: `${frozen ? 'frozen' : 'scroll'}:${column.group}:${key}`,
        group: column.group,
        frozen,
        columnKeys: [key],
        width,
        ...(frozen ? { left: frozenLeft } : {}),
      })
    }

    if (frozen) frozenLeft += width
  }

  return segments
}

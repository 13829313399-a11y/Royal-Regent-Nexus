export const schedulingDensity = {
  comfortable: {
    machineRow: 48,
    taskRow: 44,
    bodyFont: 13,
    headerFont: 12,
    groupFont: 11,
    chipFont: 11,
  },
  compact: {
    machineRow: 44,
    taskRow: 38,
    bodyFont: 12,
    headerFont: 11,
    groupFont: 10,
    chipFont: 10,
  },
} as const

export type SchedulingDensityMode = keyof typeof schedulingDensity
export const defaultSchedulingDensity: SchedulingDensityMode = 'comfortable'

type SchedulingRowGeometry = { rowType: 'machine' | 'task' }

function rowHeight(row: SchedulingRowGeometry, density: SchedulingDensityMode) {
  return row.rowType === 'machine' ? schedulingDensity[density].machineRow : schedulingDensity[density].taskRow
}

export function translateSchedulingScrollOffset(
  rows: readonly SchedulingRowGeometry[],
  fromDensity: SchedulingDensityMode,
  toDensity: SchedulingDensityMode,
  offset: number,
) {
  if (offset <= 0 || fromDensity === toDensity) return Math.max(0, offset)
  let fromCursor = 0
  let toCursor = 0
  for (const row of rows) {
    const fromHeight = rowHeight(row, fromDensity)
    const toHeight = rowHeight(row, toDensity)
    if (offset < fromCursor + fromHeight) {
      return toCursor + (offset - fromCursor) / fromHeight * toHeight
    }
    fromCursor += fromHeight
    toCursor += toHeight
  }
  return toCursor + Math.max(0, offset - fromCursor)
}

export function schedulingDensityCssVariables(density: SchedulingDensityMode) {
  const layout = schedulingDensity[density]
  return {
    '--scheduling-machine-row': `${layout.machineRow}px`,
    '--scheduling-task-row': `${layout.taskRow}px`,
    '--scheduling-body-font': `${layout.bodyFont}px`,
    '--scheduling-header-font': `${layout.headerFont}px`,
    '--scheduling-group-font': `${layout.groupFont}px`,
    '--scheduling-chip-font': `${layout.chipFont}px`,
  }
}

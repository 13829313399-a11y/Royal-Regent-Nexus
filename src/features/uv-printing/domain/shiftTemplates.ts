import type { BusinessDate, ShiftCode, UvShiftTemplate } from '../contracts'

/** Select the actual server template ID effective for the reporting shift/date. */
export function effectiveShiftTemplateFor(
  templates: UvShiftTemplate[],
  shift: ShiftCode,
  businessDate: BusinessDate,
): UvShiftTemplate | null {
  return templates
    .filter((template) => template.shift === shift
      && template.effective_from <= businessDate
      && (template.effective_to === null || businessDate <= template.effective_to))
    .sort((a, b) => b.effective_from.localeCompare(a.effective_from) || b.version - a.version)[0] ?? null
}

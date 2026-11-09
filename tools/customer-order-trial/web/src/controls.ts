import type { CustomerOrderImportPreview, CustomerOrderIssue, CustomerOrderManualOverride } from '@/types/customerOrder'

// Same server-owned controls as CustomerOrderCenterWorkspace. No guessed edit fields.
export function isResolved(issue: CustomerOrderIssue, skipped: string[], values: Record<string, string>) {
  return Boolean(issue.skip_key && ((issue.can_edit && issue.edit_field && values[issue.skip_key]?.trim())
    || (issue.can_skip && skipped.includes(issue.skip_key))))
}

export function exportControls(preview: CustomerOrderImportPreview | null, skipped: string[], values: Record<string, string>) {
  const overrides: CustomerOrderManualOverride[] = []
  const allowedSkips = new Set<string>()
  const unresolved: Array<{ rowId: string; message: string }> = []
  for (const row of preview?.rows ?? []) {
    if (!['valid', 'warning', 'blocked'].includes(row.status)) unresolved.push({ rowId: row.id, message: '该行状态未识别，请重新解析或反馈原件。' })
    if (row.status === 'blocked' && !row.issues.length) unresolved.push({ rowId: row.id, message: '该行仍被阻断，请核对原件后重新解析。' })
    for (const issue of row.issues) {
      if (issue.can_skip && issue.skip_key && skipped.includes(issue.skip_key)) allowedSkips.add(issue.skip_key)
      const value = values[issue.skip_key]?.trim()
      if (value && issue.can_edit && issue.edit_field && issue.skip_key) {
        overrides.push({ row_id: row.id, issue_key: issue.skip_key, field: issue.edit_field, value })
      }
      if (!['warning', 'blocked', 'confirmation'].includes(issue.severity)) unresolved.push({ rowId: row.id, message: issue.message || '核对项状态未识别。' })
      if (['blocked', 'confirmation'].includes(issue.severity) && !isResolved(issue, skipped, values)) {
        unresolved.push({ rowId: row.id, message: issue.message })
      }
    }
  }
  return { overrides, keys: [...new Set([...allowedSkips, ...overrides.map(value => value.issue_key)])], unresolved }
}

export function manualInputType(issue: CustomerOrderIssue) {
  return ['date', 'number'].includes(issue.edit_input_type ?? '') ? issue.edit_input_type : 'text'
}

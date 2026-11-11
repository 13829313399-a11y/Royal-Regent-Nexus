import { describe, expect, it } from 'vitest'
import type { CustomerOrderImportPreview, CustomerOrderIssue } from '@/types/customerOrder'
import { exportControls } from './controls'
function preview(issues: CustomerOrderIssue[], status = 'blocked') {
  return { rows: [{ id: 'row-1', status, issues }] } as CustomerOrderImportPreview
}
const blocked = { severity: 'blocked', code: 'missing_price', field: '单价', message: '单价待核对', can_skip: false, skip_key: 'price-1', skip_label: '', can_edit: true, edit_field: 'po_unit_prices' }
describe('server-owned manual controls', () => {
  it('rejects guessed edit fields or skips and keeps hard blockers unresolved', () => {
    const issue = { ...blocked, can_edit: false }
    const result = exportControls(preview([issue]), ['price-1', 'invented'], { 'price-1': 'PO001=7.15', invented: '9' })
    expect(result.keys).toEqual([])
    expect(result.overrides).toEqual([])
    expect(result.unresolved).toHaveLength(1)
  })
  it('keeps exact PO prices and full issue keys without numeric conversion', () => {
    const result = exportControls(preview([blocked]), [], { 'price-1': '  00001=007.15000\n00002=0.0100  ' })
    expect(result.overrides).toEqual([{ row_id: 'row-1', issue_key: 'price-1', field: 'po_unit_prices', value: '00001=007.15000\n00002=0.0100' }])
    expect(result.keys).toEqual(['price-1'])
    expect(result.unresolved).toEqual([])
  })
  it('requires explicit allowed confirmation while warning-only rows remain usable', () => {
    const issue = { ...blocked, severity: 'confirmation', can_edit: false, can_skip: true, code: 'existing_order_line' }
    expect(exportControls(preview([issue]), [], {}).unresolved).toHaveLength(1)
    expect(exportControls(preview([issue]), [issue.skip_key], {}).unresolved).toHaveLength(0)
    expect(exportControls(preview([{ ...blocked, severity: 'warning' }], 'warning'), [], {}).unresolved).toHaveLength(0)
  })
  it('does not release a blocked row with no explanatory issues', () => {
    expect(exportControls(preview([]), [], {}).unresolved).toHaveLength(1)
  })
})

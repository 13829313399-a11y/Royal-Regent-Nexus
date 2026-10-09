import { describe, expect, it } from 'vitest'
import type { FillTaskDetail } from '@/api/collaborativeSheets'
import { blockedTrialCommand, mutationChanges, stageFillChanges, TRIAL_SHEET_ID, trialWorkbook, VALUE_MUTATION } from './univerAdapter'

function example(): FillTaskDetail {
  return {
    id: 'task', title: '原表', original_name: '原表.xls', format: 'xls', factory_id: 'huaxing',
    owner_user_id: 'owner', owner_name: '上传人', status: 'open', revision: 1, is_owner: true,
    created_at: '', updated_at: '', grants: [], submissions: [], activity: [],
    editable_ranges: [{ sheet: 0, range: 'B2:D3' }], workbook: { warnings: [], sheets: [{
      index: 0, name: '数据', rows: 3, columns: 4, merges: ['A1:D1', 'C3:D3'], row_heights: { '0': 40 }, column_widths: { '1': 160 },
      cells: [
        { address: 'A1', row: 0, column: 0, value: '产品', display: '产品', formula: false, style: { fontWeight: 'bold', backgroundColor: '#ffee00', fontSize: '14pt', borderBottom: '1px solid #123456' }, image: 'data:image/png;base64,original' },
        { address: 'B2', row: 1, column: 1, value: 0.125, display: '12.50%', number_format: '0.00%', formula: false, style: {} },
        { address: 'C2', row: 1, column: 2, value: 2.5, display: '2.50', formula: true, style: {} },
      ],
    }] },
  }
}

describe('Univer trial adapter', () => {
  it('maps original styles, dimensions, merges and scalar drafts without mutating source or importing formulas', () => {
    const task = example(), before = JSON.stringify(task)
    const data = trialWorkbook(task, task.workbook.sheets[0]!, [{ sheet: 0, address: 'B3', value: '00123' }])
    const sheet = data.sheets![TRIAL_SHEET_ID]!
    expect(sheet.rowCount).toBe(3); expect(sheet.columnCount).toBe(4)
    expect(sheet.rowData?.[0]?.h).toBe(40); expect(sheet.columnData?.[1]?.w).toBe(160)
    expect(sheet.mergeData).toContainEqual({ startRow: 0, startColumn: 0, endRow: 0, endColumn: 3 })
    expect(sheet.cellData?.[0]?.[0]?.s).toMatchObject({ bl: 1, fs: 14, bg: { rgb: '#ffee00' }, bd: { b: { cl: { rgb: '#123456' } } } })
    expect(sheet.cellData?.[1]?.[1]).toMatchObject({ v: 0.125, t: 2, s: { n: { pattern: '0.00%' } } })
    expect(sheet.cellData?.[1]?.[2]).toMatchObject({ v: '2.50', t: 1, f: null })
    expect(sheet.cellData?.[2]?.[1]).toMatchObject({ v: '00123', t: 1 })
    expect(JSON.stringify(task)).toBe(before)
  })
  it('stages, replaces and undoes to the original scalar without altering other sheets', () => {
    const task = example(), pending = [{ sheet: 4, address: 'A1', value: 42 }]
    const next = stageFillChanges(task, pending, [{ sheet: 0, address: 'B2', value: 0.25 }])
    expect(next).toHaveLength(2)
    expect(stageFillChanges(task, next, [{ sheet: 0, address: 'B2', value: 0.125 }])).toEqual(pending)
    expect(pending).toHaveLength(1)
  })
  it.each(['A1', 'C2', 'D3', 'E2'])('rejects readonly or out-of-bounds %s atomically', address => {
    const task = example(), pending = [{ sheet: 0, address: 'B3', value: '保留' }]
    expect(() => stageFillChanges(task, pending, [{ sheet: 0, address: 'B2', value: 99 }, { sheet: 0, address, value: '禁止' }])).toThrow('本次修改未写入')
    expect(pending).toEqual([{ sheet: 0, address: 'B3', value: '保留' }])
  })
  it('does not give owners a permission bypass and rejects closed tasks', () => {
    const task = example(); task.editable_ranges = []
    expect(() => stageFillChanges(task, [], [{ sheet: 0, address: 'B2', value: 1 }])).toThrow()
    task.editable_ranges = [{ sheet: 0, range: 'B2' }]; task.status = 'closed'
    expect(() => stageFillChanges(task, [], [{ sheet: 0, address: 'B2', value: 1 }])).toThrow()
  })
  it.each(['=SUM(A1)', '  =1+1', 'x'.repeat(2001), '\u0000'])('rejects unsafe scalar input', value => {
    expect(() => stageFillChanges(example(), [], [{ sheet: 0, address: 'B2', value }])).toThrow()
  })
  it('enforces the pending 500-cell budget across worksheets without partial writes', () => {
    const pending = Array.from({ length: 500 }, (_, i) => ({ sheet: 4, address: `A${i + 1}`, value: 1 }))
    expect(() => stageFillChanges(example(), pending, [{ sheet: 0, address: 'B2', value: 5 }])).toThrow('500')
    expect(pending).toHaveLength(500)
    expect(() => stageFillChanges(example(), [], Array.from({ length: 501 }, () => ({ sheet: 0, address: 'B2', value: 1 })))).toThrow('500')
  })
  it('normalizes booleans, blank cells and rich plain text; rejects native formula payloads', () => {
    const sheet = example().workbook.sheets[0]!
    expect(mutationChanges(sheet, { 1: { 1: { v: 1, t: 3 }, 3: null }, 2: { 1: { p: { id: 'text', documentStyle: {}, body: { dataStream: '第一行\n第二行\r\n' } } } } })).toEqual([
      { sheet: 0, address: 'B2', value: true }, { sheet: 0, address: 'D2', value: null }, { sheet: 0, address: 'B3', value: '第一行\n第二行' },
    ])
    expect(() => mutationChanges(sheet, { 1: { 1: { f: '=1+1' } } })).toThrow('公式')
  })
  it('blocks structure, formatting, autofill and style mutations while allowing selection and scalar mutations', () => {
    for (const id of ['sheet.command.insert-row-before', 'sheet.command.set-range-bold', 'sheet.command.auto-fill', 'sheet.mutation.move-range', 'sheet.mutation.set.numfmt']) expect(blockedTrialCommand(id)).toBe(true)
    for (const id of [VALUE_MUTATION, 'sheet.command.set-range-values', 'sheet.command.move-selection', 'sheet.command.clear-selection-content']) expect(blockedTrialCommand(id)).toBe(false)
  })
})

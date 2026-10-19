import { describe, expect, it } from 'vitest'
import { columnLabel, extractMergeTable, sameNameMapping, validateSpreadsheetFile } from '../mergeHelpers'

describe('spreadsheet merge source preparation', () => {
  it('uses the selected header row without replacing missing product names', () => {
    expect(extractMergeTable('尺寸表', [['说明'], ['货号', '产品名称'], ['00123', null]], 2)).toEqual({
      name: '尺寸表', header_row: 2, headers: ['货号', '产品名称'], rows: [['00123', null]],
    })
    expect(extractMergeTable('尺寸表', [], 1)).toBeNull()
    expect(extractMergeTable('尺寸表', [['货号']], 0)).toBeNull()
  })
  it('maps only unique same-name fields and keeps ambiguous fields explicit', () => {
    expect(sameNameMapping(['货号', '产品名称', '重复', '重复'], [' 货号 ', '产品名称', '重复', '其他'])).toEqual([0, 1, -1, -1])
    expect(sameNameMapping(['货号'], ['货号', '货号'])).toEqual([-1, -1])
    expect(sameNameMapping(['未命名列 1'], ['未命名列 1'])).toEqual([-1])
  })
  it('preserves trailing data columns even with blank headers', () => {
    expect(extractMergeTable('表', [['货号'], ['001', '内容']], 1)?.headers).toEqual(['货号', '未命名列 2'])
    expect(columnLabel(26)).toBe('AA')
  })
  it('accepts only nonempty XLSX/CSV within 64 MiB', () => {
    expect(validateSpreadsheetFile(new File(['data'], '客户.csv'))).toBe('')
    expect(validateSpreadsheetFile(new File(['data'], '客户.xls'))).toContain('XLSX 或 CSV')
    expect(validateSpreadsheetFile(new File([], '客户.xlsx'))).toContain('不能为空')
    const file = new File(['data'], '客户.xlsx')
    Object.defineProperty(file, 'size', { value: 64 * 1024 * 1024 + 1 })
    expect(validateSpreadsheetFile(file)).toContain('64 MiB')
  })
})

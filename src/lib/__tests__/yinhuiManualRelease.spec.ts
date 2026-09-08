import { describe, expect, it } from 'vitest'
import { convertYinhuiInternalQuote, validateYinhuiExport, yinhuiTotals } from '@/lib/customerPriceConverters/yinhui'
import { createXlsxWorkbook, type XlsxCellInput } from '@/lib/customerPriceConverters/xlsxLite'

function buffer(bytes: Uint8Array) { return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer }
function mismatchedToolPlan() {
  const rows: XlsxCellInput[][] = []
  const row = (r: number, values: Record<number, XlsxCellInput>) => { rows[r - 1] ||= []; for (const [c, value] of Object.entries(values)) rows[r - 1]![Number(c)] = value }
  row(10, { 0: '#00012 Sample Robot (Window Box) 银辉' }); row(11, { 2: '名称', 3: '料型', 4: '料重(G)' })
  row(12, { 2: 'Body', 3: 'ABS', 4: 100, 7: 1, 9: 2, 11: 2.2 })
  row(25, { 3: '出厂价' }); row(26, { 1: '料价', 2: '料', 3: 1, 10: '彩盒（CM）：', 11: 10, 12: 20, 13: 30 })
  row(27, { 1: '啤工', 2: '啤工', 3: 1, 10: '裝箱尺碼：', 11: 20, 12: 21, 13: 22 })
  row(28, { 1: '五金', 2: 'Screw (1PC)', 3: 1, 4: 1.1, 10: '装箱：', 11: 4 })
  row(29, { 1: '纸箱', 2: 'Outer Carton', 3: 2, 4: 2.2, 10: 'MOQ:', 11: 5000 })
  row(30, { 2: '×', 3: 1.1 }); row(31, { 2: '÷', 3: 1 })
  row(33, { 2: '报关费用/文件费/操作费用：', 3: .1 }); row(34, { 4: 'FCL', 5: 'LCL' }); row(35, { 4: 1.2, 5: 2.3 }); row(36, { 2: '出厂价', 3: 10 })
  const plan: XlsxCellInput[][] = [[], [], [], ['M99', 'Unrelated Cover', 'P99', 'ABS', '', 1, 1, 70, 30, 30, 2000, 2000, 70]]
  return buffer(createXlsxWorkbook([{ name: '明细', rows }, { name: 'Tool PLan', rows: plan }]))
}

function mixedFormatToolPlan() {
  const rows: XlsxCellInput[][] = []
  const row = (r: number, values: Record<number, XlsxCellInput>) => { rows[r - 1] ||= []; for (const [c, value] of Object.entries(values)) rows[r - 1]![Number(c)] = value }
  row(10, { 0: '#00012 Sample Robot (Window Box) 银辉' }); row(11, { 2: '名称', 3: '料型', 4: '料重(G)' })
  row(12, { 2: 'Body', 3: 'ABS', 4: 100, 7: 1, 9: 2, 11: 2.2 })
  row(25, { 3: '出厂价' }); row(26, { 1: '料价', 2: '料', 3: 1, 10: '彩盒（CM）：', 11: 10, 12: 20, 13: 30 })
  row(27, { 1: '啤工', 2: '啤工', 3: 1, 10: '裝箱尺碼：', 11: 20, 12: 21, 13: 22 })
  row(28, { 1: '五金', 2: 'Screw (1PC)', 3: 1, 4: 1.1, 10: '装箱：', 11: 4 })
  row(29, { 1: '纸箱', 2: 'Outer Carton', 3: 2, 4: 2.2, 10: 'MOQ:', 11: 5000 })
  row(30, { 2: '×', 3: 1.1 }); row(31, { 2: '÷', 3: 1 })
  row(33, { 2: '报关费用/文件费/操作费用：', 3: .1 }); row(34, { 4: 'FCL', 5: 'LCL' }); row(35, { 4: 1.2, 5: 2.3 }); row(36, { 2: '出厂价', 3: 10 })
  const plan: XlsxCellInput[][] = [[], [], [],
    ['M01', 'Body', 'P01', 'ABS', '', 1, 1, 80, 30, 30, 2000, 2000, 80],
    ['', 'Cover', '', '', '', '2', '2', 20, 30, 30, 2000, 2000, '20'],
    ['', '', 'P03', '', '', 1, 1, 10, 30, 30, 2000, 2000, 10],
    ['MOLD-A', 'Alias Cover', 'P04', '', '', 1, 0, 10, 30, 30, 2000, 2000, 10],
    ['', '#VALUE!', 'P05', '', '', 1, 0, 10, 30, 30, 2000, 2000, 10],
    ['M02'],
    ['', 'Detached Part', 'P06', 'ABS', '', 1, 1, 10, 30, 30, 2000, 2000, 10],
  ]
  return buffer(createXlsxWorkbook([{ name: '明细', rows }, { name: 'Tool PLan', rows: plan }]))
}

describe('Silverlit Tool Plan manual release', () => {
  it('imports a mismatched Tool Plan as a warning and preserves main-detail molding amounts', () => {
    const result = convertYinhuiInternalQuote(mismatchedToolPlan(), '银辉00012.xlsx')
    expect(result.manualReviewReasons?.join(' ')).toMatch(/无法与 Tool Plan 唯一匹配/)
    expect(result.manualReviewReasons?.join(' ')).toMatch(/未与主明细匹配/)
    expect(result.quoteData.tools).toMatchObject([{moldNo:'',partNo:'',description:'Body',usage:1,cavity:1,weightG:100,material:'ABS',laborHkd:2.2,toolingHkd:0}])
    expect(yinhuiTotals(result.quoteData)).toMatchObject({plastic:1.565,injection:2.2})
    expect(() => validateYinhuiExport(result.quoteData)).not.toThrow()
  })
  it('keeps text-formatted numbers and a blank part number visible for manual review', () => {
    const result = convertYinhuiInternalQuote(mixedFormatToolPlan(), '银辉00012.xlsx')
    expect(result.manualReviewReasons?.join(' ')).toMatch(/Cover.*未填写零件号/)
    expect(result.manualReviewReasons?.join(' ')).toMatch(/零件描述为空/)
    expect(result.manualReviewReasons?.join(' ')).toMatch(/MOLD-A.*无法确定是新模具还是零件别名/)
    expect(result.manualReviewReasons?.join(' ')).toMatch(/公式错误.*#VALUE!/)
    expect(result.manualReviewReasons?.join(' ')).toMatch(/仅填写模号“M02”.*新模具分组/)
    expect(result.quoteData.tools.slice(0, 2)).toMatchObject([
      {moldNo:'M01',partNo:'P01',description:'Body',usage:1,cavity:1,weightG:100},
      {moldNo:'',partNo:'',description:'Cover',usage:2,cavity:2,weightG:0},
    ])
  })
  it('blocks a Chinese fallback Tool Plan name until it is translated or manually corrected', () => {
    const result = convertYinhuiInternalQuote(mismatchedToolPlan(), '银辉00012.xlsx')
    result.quoteData.tools[0]!.description = '透明面盖'
    expect(() => validateYinhuiExport(result.quoteData)).toThrow(/补全英文物料名称.*透明面盖/)
    result.quoteData.tools[0]!.description = 'Clear Cover'
    expect(() => validateYinhuiExport(result.quoteData)).not.toThrow()
  })
})

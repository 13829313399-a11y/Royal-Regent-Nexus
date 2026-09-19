import { createXlsxWorkbook, type XlsxCellInput } from '../../customerPriceConverters/xlsxLite'
export function draftSource(broken = true) {
  const rows: XlsxCellInput[][] = []
  const row = (r: number, values: Record<number, XlsxCellInput>) => { rows[r - 1] ||= []; for (const [c, value] of Object.entries(values)) rows[r - 1]![Number(c)] = value }
  row(7, { 0: '#81209 Round Light 银辉' }); row(8, { 2: '名称', 3: '料型', 4: '料重(G)' })
  row(9, { 2: 'Cover', 3: 'ABS', 4: 9.12, 7: 1, 9: 1 })
  row(15, { 3: '出厂价' })
  row(16, { 1: '料价', 2: '料', 3: 1, 10: '彩盒（CM）：', 11: 10, 12: 20, 13: 30 })
  row(17, { 1: '啤工', 2: '啤工', 3: 1, 10: '裝箱尺碼：', 11: 20, 12: 21, 13: 22 })
  row(18, { 1: '五金', 2: 'Screw', 3: broken ? null : 1, 4: 1.1, 10: '装箱：', 11: 4 })
  row(19, { 1: '纸箱', 2: 'Outer Carton', 3: 2, 4: broken ? 8 : 2.2, 10: 'MOQ:', 11: broken ? '' : '5K' })
  row(20, { 2: '×', 3: 1.1 }); row(21, { 2: '÷', 3: 1 })
  row(23, { 2: '报关费用/文件费/操作费用：', 3: .1 }); row(24, { 4: 'FCL', 5: 'LCL' }); row(25, { 4: 1.2, 5: 2.3 }); row(26, { 2: '出厂价', 3: 10 })
  const plan: XlsxCellInput[][] = []
  plan[46] = ['模号', '图片', '名称', '出模数', '模具材料', '产品材料']
  plan[47] = ['NA123', '', 'Cover', 48, 'Steel', 'ABS']
  const bytes = createXlsxWorkbook([{ name: '明细', rows }, { name: 'TOOL PLAN', rows: plan }])
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

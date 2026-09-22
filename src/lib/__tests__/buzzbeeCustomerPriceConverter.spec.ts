import { existsSync, readFileSync } from 'node:fs'
import { strFromU8, unzipSync } from 'fflate'
import { describe, expect, it } from 'vitest'
import {
  buildBuzzBeeCustomerQuoteFileName,
  convertBuzzBeeInternalQuote,
  createBuzzBeeCustomerQuoteWorkbook,
} from '@/lib/customerPriceConverters/buzzbee'
import {
  createXlsxWorkbook,
  parseXlsxWorkbook,
  type XlsxCellInput,
} from '@/lib/customerPriceConverters/xlsxLite'

const samplePath = 'D:/360安全云盘同步版/成果文件/李悦/内部转报客网页/露营火堆套装枪报价2026-3-15（内部价钱）.xlsx'

function asArrayBuffer(bytes: Uint8Array) {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

function readFileAsArrayBuffer(path: string) {
  const bytes = readFileSync(path)
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

function readGeneratedXml(bytes: Uint8Array, path: string) {
  const zip = unzipSync(bytes)
  return strFromU8(zip[path])
}

function getCellStyle(xml: string, reference: string) {
  const matched = xml.match(new RegExp(`<c r="${reference}"(?:[^>]*) s="(\\d+)"`))
  return matched?.[1] ?? ''
}

function getCellFormula(xml: string, reference: string) {
  const matched = xml.match(new RegExp(`<c r="${reference}"[^>]*><f>([^<]+)</f>`))
  return matched?.[1] ?? ''
}

function createMinimalBuzzBeeWorkbook() {
  const rows: XlsxCellInput[][] = Array.from({ length: 48 }, () => [])

  rows[6][0] = '露营火堆套装（按图报价）'
  rows[7][2] = '名称'
  rows[7][3] = '料型'
  rows[7][4] = '料重(G)'
  rows[7][6] = '机型'
  rows[7][7] = '1出几套'
  rows[7][8] = '目标数'
  rows[7][9] = '啤工'
  rows[7][10] = '料金额'
  rows[7][11] = '报客啤工'
  rows[8][2] = '下---大身面壳+底壳'
  rows[8][3] = 'ABS料'
  rows[8][4] = 135
  rows[8][6] = 18
  rows[8][7] = 1
  rows[8][8] = 2800
  rows[8][9] = 0.675
  rows[8][10] = 2.14
  rows[8][11] = 0.77625
  rows[9][4] = 135
  rows[11][1] = '料价'
  rows[11][2] = '料价'
  rows[11][3] = 2.14
  rows[11][8] = '外箱:'
  rows[11][9] = 14
  rows[11][10] = 9.25
  rows[11][11] = 23.875
  rows[12][1] = '啤工'
  rows[12][2] = '啤工'
  rows[12][3] = 0.675
  rows[13][1] = '装配工'
  rows[13][2] = '装工'
  rows[13][3] = 1.25
  rows[14][1] = '吹气'
  rows[14][2] = '吹气树支PP（2PCS)'
  rows[14][3] = 0.9
  rows[14][4] = 0.99
  rows[15][8] = '装箱：'
  rows[15][9] = 2
  rows[16][8] = '合计'
  rows[16][9] = 2.326471875
  rows[17][8] = 'CUFT:'
  rows[17][9] = 1.78924334490741
  rows[20][8] = '报客彩盒'
  rows[21][8] = 3.46
  rows[21][9] = 14.21
  rows[21][10] = 'MOQ500'
  rows[22][8] = 2.48
  rows[22][9] = 10.24
  rows[22][10] = 'MOQ1k'

  return asArrayBuffer(createXlsxWorkbook([{ name: '明细', rows }]))
}

function createUnifiedV6BuzzBeeWorkbook() {
  const rows: XlsxCellInput[][] = Array.from({ length: 72 }, () => [])

  rows[7][0] = '露营火堆套装报价'
  rows[8][2] = '名称'
  rows[8][3] = '料型'
  rows[8][4] = '料重(G)'
  rows[8][6] = '机型'
  rows[8][7] = '1出几套'
  rows[8][8] = '目标数'
  rows[8][9] = '啤工'
  rows[8][10] = '料金额'
  rows[8][11] = '报客啤工'
  rows[9][2] = '下---大身面壳+底壳'
  rows[9][3] = 'ABS料'
  rows[9][4] = 135
  rows[9][6] = 18
  rows[9][7] = 1
  rows[9][8] = 2800
  rows[9][9] = 0.675
  rows[9][10] = 2.14
  rows[9][11] = 0.77625
  rows[15][2] = '模具合计'

  rows[18][0] = '¥13%'
  rows[18][1] = '料价'
  rows[18][2] = '料价'
  rows[18][3] = 2.14
  rows[18][13] = '外箱 (inch):'
  rows[18][14] = 14
  rows[18][15] = 9.25
  rows[18][16] = 23.875
  rows[19][1] = '啤工'
  rows[19][2] = '啤工'
  rows[19][3] = 0.675
  rows[20][1] = '装配工'
  rows[20][2] = '装工'
  rows[20][3] = 1.25
  rows[21][1] = '吹气'
  rows[21][2] = '吹气树支PP（2PCS)'
  rows[21][3] = 0.9
  rows[21][4] = 0.99
  rows[22][1] = '纸箱'
  rows[22][2] = '纸箱'
  rows[22][3] = 2.326471875
  rows[22][13] = 'CUFT:'
  rows[22][14] = 1.78924334490741
  rows[23][1] = '杂项'
  rows[23][2] = '杂项'
  rows[23][3] = 0
  rows[24][1] = '运费'
  rows[24][2] = '运费'
  rows[24][4] = 2.06
  rows[24][5] = 3.85
  rows[25][1] = '吊柜费'
  rows[25][2] = '吊柜费'
  rows[25][4] = 3.71
  rows[25][5] = 3.76
  rows[26][2] = '×'
  rows[26][3] = 1.18
  rows[27][2] = '÷'
  rows[27][3] = 0.98
  rows[28][1] = '报价（MOQ3K）'
  rows[28][3] = 60.14
  rows[30][1] = '包含测试费用（US）：'
  rows[30][3] = 8.3

  rows[24][13] = '装箱：'
  rows[24][14] = 2
  rows[25][13] = '合计'
  rows[25][14] = 2.326471875
  rows[27][13] = '功能介绍：'
  // The v6 layout deliberately keeps one complete blank row before 彩盒价格.
  rows[36][13] = '彩盒价格'
  rows[37][13] = '报客彩盒'
  rows[37][14] = '报客彩盒FSC'
  rows[37][15] = 'MOQ数量'
  rows[38][13] = 3.46
  rows[38][14] = 3.56
  rows[38][15] = 'MOQ500'
  rows[39][13] = 2.48
  rows[39][14] = 2.55
  rows[39][15] = 'MOQ1k'
  rows[42][13] = '测试费用'
  rows[42][14] = 1500
  rows[43][13] = 3000
  rows[43][14] = 0.5

  const attachmentRows: XlsxCellInput[][] = [
    ['电子部报价导入模板'],
    ['零件名称', '单价 RMB', '单价 HKD', '税点%', '备注'],
  ]

  return asArrayBuffer(createXlsxWorkbook([
    { name: '报价明细', rows },
    { name: '上传附件-电子部报价', rows: attachmentRows },
  ]))
}

describe('BuzzBee customer price converter', () => {
  it('converts a BuzzBee-style internal workbook and exports a customer quote workbook', () => {
    const result = convertBuzzBeeInternalQuote(createMinimalBuzzBeeWorkbook(), 'buzzbee-minimal.xlsx')

    expect(result.sheets).toHaveLength(1)
    expect(result.sheets[0].name).toBe('露营火堆套装')
    expect(result.sheets[0].details.length).toBeGreaterThan(3)
    expect(result.sheets[0].totalCustomerHkd).toBeGreaterThan(5)

    const output = createBuzzBeeCustomerQuoteWorkbook(result)
    const parsed = parseXlsxWorkbook(asArrayBuffer(output))
    const sheet = parsed.sheets[0]

    expect(sheet.rows[0][0]).toBe('COST BREAKDOWN SHEET (ROYAL REGENT)')
    expect(sheet.rows[3][0]).toBe('ltem:露营火堆套装')
    expect(sheet.rows[4][0]).toBe('INJECTION')
    expect(sheet.rows[6][0]).toBe('下---大身面壳+底壳')
    expect(sheet.rows[6][1]).toBe('ABS')
    expect(sheet.rows[6][3]).toBe(16.5)
    expect(sheet.rows[6][6]).toBe(0.675)
    expect(sheet.rows[54][5]).toBe(1.73)
    expect(sheet.rows[54][6]).toBe(1.7819)
    expect(sheet.rows[55][5]).toBe(1.24)
    expect(sheet.rows[55][6]).toBe(1.2772)
    expect(sheet.rows[57][1]).toBe(2)

    const worksheetXml = readGeneratedXml(output, 'xl/worksheets/sheet1.xml')
    const stylesXml = readGeneratedXml(output, 'xl/styles.xml')

    expect(getCellStyle(worksheetXml, 'A4')).toBe('13')
    expect(getCellStyle(worksheetXml, 'C7')).toBe('11')
    expect(getCellStyle(worksheetXml, 'D7')).toBe('12')
    expect(getCellStyle(worksheetXml, 'F7')).toBe('11')
    expect(getCellStyle(worksheetXml, 'B28')).toBe('11')
    expect(getCellStyle(worksheetXml, 'B58')).toBe('11')
    expect(getCellFormula(worksheetXml, 'F55')).toBe('3.46/2')
    expect(getCellFormula(worksheetXml, 'G55')).toBe('F55*1.03')
    expect(getCellFormula(worksheetXml, 'F56')).toBe('2.48/2')
    expect(getCellFormula(worksheetXml, 'G56')).toBe('F56*1.03')
    expect(stylesXml).toContain('formatCode="0"')
    expect(stylesXml).toContain('formatCode="0.0"')
    expect(stylesXml).toContain('horizontal="center" vertical="top"')
    expect(buildBuzzBeeCustomerQuoteFileName(result, new Date(2026, 2, 18))).toBe('R0 RR ITEM 露营火堆套装（2026-3-18）.xlsx')
  })

  it('accepts the unified v6 internal layout without mapping internal-only freight, lifting, MOQ, or testing blocks', () => {
    const result = convertBuzzBeeInternalQuote(
      createUnifiedV6BuzzBeeWorkbook(),
      'buzzbee-unified-v6.xlsx',
    )

    expect(result.sheets).toHaveLength(1)
    expect(result.sheets[0].name).toBe('露营火堆套装')
    expect(result.sheets[0].details.map((row) => row.description)).not.toEqual(expect.arrayContaining([
      '运费',
      '吊柜费',
      '报价（MOQ3K）',
      '包含测试费用（US）：',
    ]))
    expect(result.sheets[0].details.map((row) => row.description)).toEqual(expect.arrayContaining([
      '吹气树支PP',
      '纸箱',
    ]))

    const output = createBuzzBeeCustomerQuoteWorkbook(result)
    const parsed = parseXlsxWorkbook(asArrayBuffer(output))
    expect(parsed.sheets).toHaveLength(1)
    expect(parsed.sheets[0].rows[0][0]).toBe('COST BREAKDOWN SHEET (ROYAL REGENT)')
  })

  it('reads the real BuzzBee sample workbook when it is available locally', () => {
    if (!existsSync(samplePath)) {
      return
    }

    const result = convertBuzzBeeInternalQuote(readFileAsArrayBuffer(samplePath), '露营火堆套装枪报价2026-3-15（内部价钱）.xlsx')

    expect(result.sheets).toHaveLength(1)
    expect(result.sheets[0].name).toBe('露营火堆套装')
    expect(result.sheets[0].rowCount).toBeGreaterThan(20)
    expect(result.sheets[0].totalCustomerHkd).toBeGreaterThan(50)

    const output = createBuzzBeeCustomerQuoteWorkbook(result)
    const parsed = parseXlsxWorkbook(asArrayBuffer(output))

    expect(parsed.sheets[0].rows[0][0]).toBe('COST BREAKDOWN SHEET (ROYAL REGENT)')
    expect(parsed.sheets[0].rows[23][0]).toBe('SUB TOTAL')
    expect(parsed.sheets[0].rows[25][0]).toBe('PURCHASE')
  })
})

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
  rows[21][8] = 6.7
  rows[21][9] = 6.901
  rows[21][10] = 'MOQ3000'

  return asArrayBuffer(createXlsxWorkbook([{ name: '明细', rows }]))
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
    expect(sheet.rows[6][6]).toBe(0.7763)
    expect(sheet.rows[54][5]).toBe(3.35)
    expect(sheet.rows[54][6]).toBe(6.901)
    expect(sheet.rows[57][1]).toBe(2)

    const worksheetXml = readGeneratedXml(output, 'xl/worksheets/sheet1.xml')
    const stylesXml = readGeneratedXml(output, 'xl/styles.xml')

    expect(getCellStyle(worksheetXml, 'A4')).toBe('13')
    expect(getCellStyle(worksheetXml, 'C7')).toBe('11')
    expect(getCellStyle(worksheetXml, 'D7')).toBe('12')
    expect(getCellStyle(worksheetXml, 'F7')).toBe('11')
    expect(getCellStyle(worksheetXml, 'B28')).toBe('11')
    expect(getCellStyle(worksheetXml, 'B58')).toBe('11')
    expect(getCellFormula(worksheetXml, 'F55')).toBe('6.7/2')
    expect(stylesXml).toContain('formatCode="0"')
    expect(stylesXml).toContain('formatCode="0.0"')
    expect(stylesXml).toContain('horizontal="center" vertical="top"')
    expect(buildBuzzBeeCustomerQuoteFileName(result, new Date(2026, 2, 18))).toBe('R0 RR ITEM 露营火堆套装（2026-3-18）.xlsx')
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

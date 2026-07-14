import { existsSync, readFileSync } from 'node:fs'
import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'
import { describe, expect, it } from 'vitest'
import {
  buildDisneyCustomerQuoteFileName,
  convertDisneyInternalQuote,
  createDisneyCustomerQuoteWorkbook,
} from '@/lib/customerPriceConverters/disney'
import {
  createXlsxWorkbook,
  parseXlsxWorkbook,
  type XlsxCellInput,
} from '@/lib/customerPriceConverters/xlsxLite'

const samplePath = 'C:/Users/Aalyaan/Desktop/迪士尼报客(2)/迪士尼报客/本厂 -1000142435  印第安纳・琼斯 回力玩具车 Indiana Jones Pul-back Ride Vehicle报价20260603（内部报价）.xlsx'
const disneyTemplatePath = 'public/templates/disney-customer-quote-template.bin'

function asArrayBuffer(bytes: Uint8Array) {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

function readFileAsArrayBuffer(path: string) {
  const bytes = readFileSync(path)
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

function readDisneyTemplate() {
  return readFileSync(disneyTemplatePath)
}

function getSheetXml(bytes: Uint8Array) {
  return strFromU8(unzipSync(bytes)['xl/worksheets/sheet1.xml'])
}

function getCellStyle(sheetXml: string, ref: string) {
  const match = sheetXml.match(new RegExp(`<c\\b[^>]*\\br="${ref}"[^>]*`))
  return match?.[0].match(/\bs="([^"]+)"/)?.[1] ?? ''
}

function columnName(columnIndex: number) {
  let index = columnIndex + 1
  let name = ''

  while (index > 0) {
    const remainder = (index - 1) % 26
    name = String.fromCharCode(65 + remainder) + name
    index = Math.floor((index - 1) / 26)
  }

  return name
}

function findStyleMismatches(
  templateXml: string,
  outputXml: string,
  ranges: Array<[number, number, number, number]>,
) {
  const mismatches: string[] = []

  ranges.forEach(([startRow, endRow, startColumn, endColumn]) => {
    for (let row = startRow; row <= endRow; row += 1) {
      for (let column = startColumn; column <= endColumn; column += 1) {
        const ref = `${columnName(column)}${row}`
        const templateStyle = getCellStyle(templateXml, ref)
        if (!templateStyle) {
          continue
        }

        const outputStyle = getCellStyle(outputXml, ref)
        if (outputStyle !== templateStyle) {
          mismatches.push(`${ref}:${templateStyle}->${outputStyle || 'none'}`)
        }
      }
    }
  })

  return mismatches
}

function getCellBody(sheetXml: string, ref: string) {
  const cellPattern = /<c\b([^>]*)\/>|<c\b([^>]*)>([\s\S]*?)<\/c>/g
  for (const match of sheetXml.matchAll(cellPattern)) {
    const attrs = match[1] ?? match[2] ?? ''
    if (attrs.match(new RegExp(`\\br="${ref}"`))) {
      return match[3] ?? ''
    }
  }

  return ''
}

function getCellXml(sheetXml: string, ref: string) {
  const cellPattern = /<c\b([^>]*)\/>|<c\b([^>]*)>([\s\S]*?)<\/c>/g
  for (const match of sheetXml.matchAll(cellPattern)) {
    const attrs = match[1] ?? match[2] ?? ''
    if (attrs.match(new RegExp(`\\br="${ref}"`))) {
      return match[0]
    }
  }

  return ''
}

function getCellFormula(sheetXml: string, ref: string) {
  return getCellBody(sheetXml, ref).match(/<f(?:\s[^>]*)?>([\s\S]*?)<\/f>/)?.[1] ?? ''
}

function applyMoqHighlightFills(workbook: ArrayBuffer, refs: string[]) {
  const zip = unzipSync(new Uint8Array(workbook))
  const styles = strFromU8(zip['xl/styles.xml'])
  zip['xl/styles.xml'] = strToU8(styles
    .replace('<fills count="2">', '<fills count="3">')
    .replace('</fills><borders', '<fill><patternFill patternType="solid"><fgColor rgb="FFFFFF00"/></patternFill></fill></fills><borders')
    .replace('<cellXfs count="14">', '<cellXfs count="15">')
    .replace('</cellXfs><cellStyles', '<xf numFmtId="166" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyNumberFormat="1"/></cellXfs><cellStyles'))

  let sheetXml = strFromU8(zip['xl/worksheets/sheet1.xml'])
  refs.forEach((ref) => {
    const cellOpenTag = new RegExp(`<c\\b([^>]*\\br="${ref}"[^>]*)>`)
    sheetXml = sheetXml.replace(cellOpenTag, (_full, attributes: string) => `<c${attributes.replace(/\s+s="[^"]*"/, '')} s="14">`)
  })
  zip['xl/worksheets/sheet1.xml'] = strToU8(sheetXml)

  return asArrayBuffer(zipSync(zip))
}

function lineNumbers(rows: ReturnType<typeof parseXlsxWorkbook>['sheets'][number]['rows'], startRow: number, count = 10) {
  return Array.from({ length: count }, (_, index) => rows[startRow - 1 + index]?.[0])
}

function createMinimalDisneyWorkbook() {
  const detailRows: XlsxCellInput[][] = Array.from({ length: 66 }, () => [])

  detailRows[0][2] = '料型'
  detailRows[0][3] = 'ABS料'
  detailRows[1][2] = '单价/P'
  detailRows[1][3] = 7.5
  detailRows[2][3] = 2.16
  detailRows[6][2] = '机型'
  detailRows[6][3] = '14A'
  detailRows[7][2] = '单价/元'
  detailRows[7][3] = 1490
  detailRows[8][3] = 8.12
  detailRows[9][0] = '#1000142435 Indiana Jones Pul-back Ride Vehicle 报价（图纸评估报价）'
  detailRows[10][2] = '名称'
  detailRows[10][3] = '料型（Part Material）'
  detailRows[10][4] = '料重(G)'
  detailRows[10][6] = '机型(A)'
  detailRows[10][7] = '1出幾套'
  detailRows[10][8] = '啤數'
  detailRows[10][9] = '啤工'
  detailRows[10][10] = '料金额'
  detailRows[10][12] = '周期（Cycle Time (s)'
  detailRows[10][14] = 'Press size (TON)'
  detailRows[11][1] = 1
  detailRows[11][2] = '车面'
  detailRows[11][3] = 'ABS'
  detailRows[11][4] = 28
  detailRows[11][5] = 0.01652
  detailRows[11][6] = '14A'
  detailRows[11][7] = 1
  detailRows[11][8] = 2200
  detailRows[11][9] = 0.677
  detailRows[11][10] = 0.462
  detailRows[11][12] = 39
  detailRows[11][13] = 0.0605
  detailRows[11][14] = 999
  for (const [rowIndex, lineNo, description, machine] of [
    [12, 2, '档风玻璃', '18A'],
    [13, 3, '车轮', '7A'],
    [14, 4, '公子/公子鼻子', '7A'],
  ] as const) {
    detailRows[rowIndex][1] = lineNo
    detailRows[rowIndex][2] = description
    detailRows[rowIndex][3] = 'ABS'
    detailRows[rowIndex][4] = 28
    detailRows[rowIndex][5] = 0.01652
    detailRows[rowIndex][6] = machine
    detailRows[rowIndex][7] = 1
    detailRows[rowIndex][8] = 2200
    detailRows[rowIndex][9] = 0.677
    detailRows[rowIndex][10] = 0.462
    detailRows[rowIndex][12] = 39
    detailRows[rowIndex][13] = 0.0605
    detailRows[rowIndex][14] = 999
  }
  detailRows[24][10] = '裝箱尺碼：'
  detailRows[24][11] = 12.56
  detailRows[24][12] = 10.2
  detailRows[24][13] = 3.76
  detailRows[29][9] = '装箱数'
  detailRows[29][10] = 6
  detailRows[30][1] = '五金'
  detailRows[30][2] = '螺丝M2.6*8PB（6Pcs)'
  detailRows[30][5] = 0.008
  detailRows[31][1] = '其他外购'
  detailRows[31][2] = '回力牙箱（1PCS)'
  detailRows[31][5] = 0.077
  detailRows[32][1] = '纸箱'
  detailRows[32][2] = '外箱 （B=B）'
  detailRows[32][5] = 0.05
  detailRows[33][1] = '其他外购'
  detailRows[33][2] = '封箱胶纸/胶水/雪梨纸'
  detailRows[33][5] = 0.013
  detailRows[34][1] = '装配工'
  detailRows[34][2] = '半成品（23人/11H/2000)'
  detailRows[34][5] = 0.12
  detailRows[35][1] = '装配工'
  detailRows[35][2] = '包装装配工（22人/11H/3000）'
  detailRows[35][5] = 0.1
  detailRows[36][1] = '彩盒/内咭'
  detailRows[36][2] = 'PDQ'
  detailRows[36][3] = 0.47
  detailRows[36][5] = 0.061
  detailRows[37][1] = '其他外购'
  detailRows[37][2] = '车面贴纸'
  detailRows[37][3] = 0.57
  detailRows[37][5] = 0.075
  detailRows[38][1] = '彩盒/内咭'
  detailRows[38][2] = '吊牌'
  detailRows[38][3] = 0.32
  detailRows[38][5] = 0.042
  detailRows[39][1] = '其他外购'
  detailRows[39][2] = '胶膜（防碰花）'
  detailRows[39][3] = 0.1
  detailRows[39][5] = 0.013
  detailRows[40][1] = '彩盒/内咭'
  detailRows[40][2] = '吊牌'
  detailRows[40][5] = 11794.845
  detailRows[40][6] = 83705.35
  detailRows[40][7] = 129362.81
  detailRows[44][2] = '3K报价：'
  detailRows[46][2] = '包含测试费用（US)：'
  detailRows[46][3] = 3.04
  detailRows[46][4] = 3.11
  detailRows[46][5] = 3.08
  detailRows[46][6] = 3.07
  detailRows[46][7] = 3.07
  detailRows[46][8] = 3.06
  detailRows[46][9] = 3.06
  detailRows[47][5] = 0.027
  detailRows[51][2] = '5K报价：'
  detailRows[53][2] = '包含测试费用（US)：'
  detailRows[53][3] = 2.81
  detailRows[53][4] = 2.87
  detailRows[53][5] = 2.84
  detailRows[53][6] = 2.84
  detailRows[53][7] = 2.84
  detailRows[53][8] = 2.83
  detailRows[53][9] = 2.83
  detailRows[58][2] = '10K报价：'
  detailRows[60][2] = '包含测试费用（US)：'
  detailRows[60][3] = 2.62
  detailRows[60][4] = 2.69
  detailRows[60][5] = 2.66
  detailRows[60][6] = 2.66
  detailRows[60][7] = 2.65
  detailRows[60][8] = 2.65
  detailRows[60][9] = 2.64
  detailRows[62][9] = 'MOQ:'
  detailRows[62][10] = 3000

  const moldRows: XlsxCellInput[][] = Array.from({ length: 4 }, () => [])
  moldRows[0][1] = 'Mold #'
  moldRows[0][2] = 'Parts (膠件)'
  moldRows[0][5] = 'Resin'
  moldRows[0][6] = 'Cav.'
  moldRows[0][7] = 'Up'
  moldRows[0][11] = 'USD'
  moldRows[1][1] = 'M01'
  moldRows[1][2] = '车面'
  moldRows[1][5] = 'ABS'
  moldRows[1][6] = 1
  moldRows[1][7] = 1
  moldRows[1][10] = 1111
  moldRows[1][11] = 8900

  const sprayRows: XlsxCellInput[][] = Array.from({ length: 30 }, () => [])
  sprayRows[28][8] = 34
  sprayRows[28][10] = 0.0171

  const modelRows: XlsxCellInput[][] = Array.from({ length: 16 }, () => [])
  modelRows[12][3] = '画图'
  modelRows[12][9] = 1500
  modelRows[13][3] = '功能色板'
  modelRows[13][9] = 3800
  modelRows[14][3] = '开模板'
  modelRows[14][9] = 2400

  return applyMoqHighlightFills(asArrayBuffer(createXlsxWorkbook([
    { name: '明细', rows: detailRows },
    { name: '喷油报价', rows: sprayRows },
    { name: '模具报价', rows: moldRows },
    { name: '手办报价', rows: modelRows },
  ])), ['F47', 'G54', 'J61'])
}

describe('Disney customer price converter', () => {
  it('converts a Disney-style internal workbook and exports the Disney quote format', () => {
    const result = convertDisneyInternalQuote(
      createMinimalDisneyWorkbook(),
      '本厂 -1000142435 Indiana Jones Pul-back Ride Vehicle报价20260603（内部报价）.xlsx',
    )

    expect(result.sheets).toHaveLength(1)
    expect(result.sheets[0].name).toBe('Indiana Jones Pul-back Ride Vehicle')
    expect(result.sheets[0].details.length).toBeGreaterThan(8)
    expect(result.sheets[0].totalCustomerHkd).toBeGreaterThan(10000)
    expect(result.sheets[0].quoteData.plastics[0].laborRateUsdHr).toBe(8.12)
    expect(result.sheets[0].quoteData.plastics[0].moldingLaborCostUsd).toBeGreaterThan(0)
    expect(result.sheets[0].quoteData.plastics.map((part) => part.partDescription)).toEqual([
      'Car Body',
      'Windshield',
      'Wheel',
      'Doll / Doll Nose',
    ])
    expect(result.sheets[0].quoteData.plastics.map((part) => part.pressSizeTon)).toEqual([
      180,
      200,
      120,
      120,
    ])
    expect(result.sheets[0].quoteData.purchasedPackageParts.map((part) => part.description))
      .toEqual([
        'Carton Box 0/6 (12.56"x10.2"x3.76")',
        'Tissue paper and packing materials',
        'PDQ',
        'Car Body Sticker',
        'Hang tag',
        'Protective film',
      ])

    const output = createDisneyCustomerQuoteWorkbook(result, readDisneyTemplate())
    const parsed = parseXlsxWorkbook(asArrayBuffer(output))

    expect(parsed.sheets.map((sheet) => sheet.name)).toEqual([
      'Tier 1 MOQ 3K',
      'PLM Upload format - Tier 1',
      'Constant Tables',
    ])

    const tier = parsed.sheets[0]
    expect(tier.rows[7][2]).toBe('Indiana Jones Pul-back Ride Vehicle')
    expect(tier.rows[8][2]).toBe(1000142435)
    expect(tier.rows[18][1]).toBe('1000142435-01')
    expect(tier.rows[18][2]).toBe(8900)
    expect(tier.rows[18][3]).toBe('Car Body')
    expect(tier.rows[19][3]).toBe('Windshield')
    expect(tier.rows[20][3]).toBe('Wheel')
    expect(tier.rows[21][3]).toBe('Doll / Doll Nose')
    expect([18, 19, 20, 21].map((rowIndex) => tier.rows[rowIndex][15])).toEqual([
      180,
      200,
      120,
      120,
    ])
    expect(tier.rows[18][5]).toBe('ABS')
    expect(tier.rows[18][7]).toBe(2.16)
    expect(tier.rows[18][18]).toBeGreaterThan(0)
    expect(tier.rows[18][19]).toBeGreaterThan(0)
    expect(tier.rows[61][1]).toBe('Screw M2.6 x 8 (6pcs)')
    expect(tier.rows.slice(118, 124).map((row) => row[1])).toEqual([
      'Carton Box 0/6 (12.56"x10.2"x3.76")',
      'Tissue paper and packing materials',
      'PDQ',
      'Car Body Sticker',
      'Hang tag',
      'Protective film',
    ])
    expect(tier.rows[163][1]).toBe('Assembly vehicle')
    expect(tier.rows[178][1]).toBe('Whole Item')
    expect(tier.rows[193][1]).toBe('Transportation')
    expect(tier.rows[234][2]).toBe(3.08)
    expect(tier.rows[236][2]).toBe(8900)
    expect(tier.rows[235][5]).toBe(3.08)
    expect(tier.rows[236][5]).toBe(2.84)
    expect(tier.rows[237][5]).toBe(2.64)
    expect(tier.rows[239][2]).toBe(6200)
    expect(tier.rows[240][2]).toBe(1500)
    expect(lineNumbers(tier.rows, 47)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    expect(lineNumbers(tier.rows, 89)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    expect(lineNumbers(tier.rows, 104)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    expect(lineNumbers(tier.rows, 134)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    expect(lineNumbers(tier.rows, 149)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    expect(buildDisneyCustomerQuoteFileName(result)).toBe('Quotation of 1000142435 Indiana Jones Pul-back Ride Vehicle - Royal Regent (R0) (20260603).xlsx')
  })

  it('reads the real Disney sample workbook when it is available locally', () => {
    if (!existsSync(samplePath)) {
      return
    }

    const result = convertDisneyInternalQuote(readFileAsArrayBuffer(samplePath), '本厂 -1000142435  印第安纳・琼斯 回力玩具车 Indiana Jones Pul-back Ride Vehicle报价20260603（内部报价）.xlsx')

    expect(result.sheets).toHaveLength(1)
    expect(result.sheets[0].name).toBe('Indiana Jones Pul-back Ride Vehicle')
    expect(result.sheets[0].details.length).toBeGreaterThan(20)

    const template = readDisneyTemplate()
    const output = createDisneyCustomerQuoteWorkbook(result, template)
    const parsed = parseXlsxWorkbook(asArrayBuffer(output))
    const tier = parsed.sheets[0]

    expect(tier.rows[18][1]).toBe('1000142435-01')
    expect(tier.rows[18][2]).toBe(6100)
    expect(tier.rows[18][5]).toBe('PVC')
    expect(tier.rows[8][2]).toBe(1000142435)
    expect(tier.rows[18][3]).toBe('Doll upper body/doll head/doll hands and fee')
    expect(tier.rows[18][6]).toBe('')
    expect(tier.rows[18][18]).toBe(6.32)
    expect(tier.rows[18][19]).toBe(0.0948)
    expect(tier.rows[19][17]).toBe(39)
    expect(tier.rows[20][17]).toBe(25)
    expect(tier.rows[20][3]).toBe('vehicle bottom')
    expect(tier.rows[21][3]).toBe('seat')
    expect(tier.rows[23][3]).toBe('wheel boss')
    expect(tier.rows[24][3]).toBe('Accessories (red + gray)')
    expect(result.sheets[0].quoteData.purchasedPackageParts.some((part) => part.description === 'Hang tag')).toBe(false)
    expect(tier.rows[41][2]).toBe(32400)
    expect(tier.rows[41][11]).toBeCloseTo(0.35876, 12)
    expect(tier.rows[41][20]).toBeCloseTo(0.353234173280423, 12)
    expect(tier.rows[41][22]).toBeCloseTo(0.751412777777778, 12)
    expect(tier.rows[208][2]).toBeCloseTo(0.35876, 12)
    expect(tier.rows[209][2]).toBeCloseTo(0.138, 12)
    expect(tier.rows[128][3]).toBe(6)
    expect(tier.rows[213][2]).toBeCloseTo(2.23405277777778, 12)
    expect(tier.rows[216][2]).toBeCloseTo(2.92081277777778, 12)
    expect(tier.rows[234][2]).toBe(3.42)
    expect(tier.rows[239][2]).toBe(6200)
    expect(tier.rows[240][2]).toBe(1500)

    const templateXml = getSheetXml(template)
    const outputXml = getSheetXml(output)
    expect(getCellStyle(outputXml, 'B19')).toBe(getCellStyle(templateXml, 'B19'))
    expect(getCellStyle(outputXml, 'C19')).toBe(getCellStyle(templateXml, 'C19'))
    expect(getCellStyle(outputXml, 'A47')).toBe(getCellStyle(templateXml, 'A47'))
    expect(getCellStyle(outputXml, 'A89')).toBe(getCellStyle(templateXml, 'A89'))
    expect(outputXml).toContain('<mergeCell ref="A235:B235"')
    expect(outputXml).toContain('<mergeCell ref="A243:B243"')
    expect(findStyleMismatches(templateXml, outputXml, [
      [25, 41, 0, 23],
      [47, 56, 0, 25],
      [65, 83, 0, 6],
      [89, 98, 0, 25],
      [104, 113, 0, 25],
      [122, 128, 0, 6],
      [134, 143, 0, 25],
      [149, 158, 0, 7],
      [166, 173, 0, 7],
      [180, 188, 0, 7],
      [195, 203, 0, 2],
      [209, 217, 0, 2],
      [221, 232, 0, 3],
    ])).toEqual([])
  })

  it('preserves template formulas, blanks, and text cell types in Disney cost sections', () => {
    if (!existsSync(samplePath)) {
      return
    }

    const result = convertDisneyInternalQuote(readFileAsArrayBuffer(samplePath), '本厂 -1000142435  印第安纳・琼斯 回力玩具车 Indiana Jones Pul-back Ride Vehicle报价20260603（内部报价）.xlsx')
    const outputXml = getSheetXml(createDisneyCustomerQuoteWorkbook(result, readDisneyTemplate()))

    expect(getCellFormula(outputXml, 'G26')).toBe('')
    expect(getCellFormula(outputXml, 'F188')).toBe('V19')
    expect(getCellFormula(outputXml, 'C230')).toBe('G189-E189')
    expect(getCellFormula(outputXml, 'D230')).toBe('C230/E189')
    expect(getCellFormula(outputXml, 'N26')).toBe('')
    expect(getCellFormula(outputXml, 'T26')).toBe('')
    expect(getCellFormula(outputXml, 'U26')).toBe('')
    expect(getCellFormula(outputXml, 'W26')).toBe('')
    expect(getCellFormula(outputXml, 'X26')).toBe('')

    expect(getCellFormula(outputXml, 'J19')).toBe('G19*I19')
    expect(getCellFormula(outputXml, 'J26')).toBe('')
    expect(getCellFormula(outputXml, 'L41')).toBe('H41*I41*K41/1000')
    expect(getCellFormula(outputXml, 'V20')).toBe('V19')
    expect(getCellFormula(outputXml, 'V21')).toBe('V19')
    expect(getCellFormula(outputXml, 'V22')).toBe('V19')
    expect(getCellFormula(outputXml, 'V23')).toBe('V19')
    expect(getCellFormula(outputXml, 'V24')).toBe('V20')
    expect(getCellFormula(outputXml, 'V25')).toBe('V21')

    for (let rowNumber = 62; rowNumber <= 83; rowNumber += 1) {
      expect(getCellFormula(outputXml, `E${rowNumber}`)).toBe(`C${rowNumber}*D${rowNumber}`)
      expect(getCellFormula(outputXml, `F${rowNumber}`)).toBe('V19')
      expect(getCellFormula(outputXml, `G${rowNumber}`)).toBe(`E${rowNumber}*(1+F${rowNumber})`)
    }

    for (let rowNumber = 119; rowNumber <= 128; rowNumber += 1) {
      expect(getCellFormula(outputXml, `E${rowNumber}`)).toBe(`C${rowNumber}*D${rowNumber}`)
      expect(getCellFormula(outputXml, `F${rowNumber}`)).toBe('V19')
      expect(getCellFormula(outputXml, `G${rowNumber}`)).toBe(`E${rowNumber}*(1+F${rowNumber})`)
    }

    for (let rowNumber = 164; rowNumber <= 173; rowNumber += 1) {
      expect(getCellFormula(outputXml, `E${rowNumber}`)).toBe(`C${rowNumber}*D${rowNumber}/60`)
      expect(getCellFormula(outputXml, `F${rowNumber}`)).toBe('V19')
      expect(getCellFormula(outputXml, `G${rowNumber}`)).toBe(`E${rowNumber}*(1+F${rowNumber})`)
    }

    for (let rowNumber = 179; rowNumber <= 188; rowNumber += 1) {
      expect(getCellFormula(outputXml, `E${rowNumber}`)).toBe(`C${rowNumber}*D${rowNumber}`)
      expect(getCellFormula(outputXml, `F${rowNumber}`)).toBe('V19')
      expect(getCellFormula(outputXml, `G${rowNumber}`)).toBe(`E${rowNumber}*(1+F${rowNumber})`)
    }

    expect(getCellFormula(outputXml, 'E122')).toBe('C122*D122')
    expect(getCellFormula(outputXml, 'G122')).toBe('E122*(1+F122)')
    expect(getCellFormula(outputXml, 'G188')).toBe('E188*(1+F188)')
    expect(getCellFormula(outputXml, 'G189')).toBe('SUM(G179:G188)')
    expect(getCellFormula(outputXml, 'A190')).toBe('IFERROR(G189,0)')
    expect(getCellFormula(outputXml, 'C214')).toBe('A175+T42+A190')
    expect(getCellFormula(outputXml, 'C217')).toBe('SUM(C205:C216)')
    expect(getCellFormula(outputXml, 'C221')).toBe('')
    expect(getCellFormula(outputXml, 'D221')).toBe('C221/U42')
    expect(getCellFormula(outputXml, 'C223')).toBe('G84-E84')
    expect(getCellFormula(outputXml, 'D223')).toBe('C223/E84')
    expect(getCellFormula(outputXml, 'C226')).toBe('G129-E129')
    expect(getCellFormula(outputXml, 'D226')).toBe('C226/E129')
    expect(getCellFormula(outputXml, 'C228')).toBe('G159-E159')
    expect(getCellFormula(outputXml, 'D228')).toBe('C228/E159')
    expect(getCellFormula(outputXml, 'C229')).toBe('G174-E174')
    expect(getCellFormula(outputXml, 'D229')).toBe('C229/E174')
    expect(getCellFormula(outputXml, 'A233')).toBe('IFERROR(C232,0)')
    expect(getCellFormula(outputXml, 'C235')).toBe('F236')
    expect(getCellFormula(outputXml, 'B235')).toBe('')
    expect(getCellFormula(outputXml, 'F236')).toBe('')
    expect(getCellFormula(outputXml, 'C243')).toBe('SUM(C237:C242)')
    expect(getCellBody(outputXml, 'C222')).not.toContain('<v>')
    expect(getCellBody(outputXml, 'C224')).not.toContain('<v>')
    expect(getCellBody(outputXml, 'C225')).not.toContain('<v>')
    expect(getCellBody(outputXml, 'C227')).not.toContain('<v>')
    expect(getCellBody(outputXml, 'C231')).not.toContain('<v>')
    expect(getCellBody(outputXml, 'C22')).not.toContain('<v>')
    expect(getCellBody(outputXml, 'C24')).not.toContain('<v>')
    for (const ref of ['M19', 'M20', 'M21', 'M22', 'M23', 'M24']) {
      expect(getCellXml(outputXml, ref)).toContain('t="inlineStr"')
    }
    expect(getCellBody(outputXml, 'D228')).toContain('<v>#DIV/0!</v>')
    expect(outputXml).toMatch(/<c r="D228" t="e"[^>]*>/)
    expect(outputXml).toMatch(/<c r="A233" t="str"[^>]*><f>IFERROR\(C232,0\)<\/f><v><\/v><\/c>/)
  })
})

import { existsSync, readFileSync } from 'node:fs'
import { strFromU8, unzipSync } from 'fflate'
import { describe, expect, it } from 'vitest'
import {
  buildCaixingCustomerQuoteFileName,
  convertCaixingInternalQuote,
  createCaixingCustomerQuoteWorkbook,
} from '@/lib/customerPriceConverters/caixing'
import {
  createXlsxWorkbook,
  parseXlsxWorkbook,
  type XlsxCellInput,
} from '@/lib/customerPriceConverters/xlsxLite'

const plasticSamplePath = 'C:/Users/Aalyaan/Desktop/彩星/塑胶/68963发声亮灯剑报价（按图报价）－2026-6-27.xlsx'
const plushSamplePath = 'C:/Users/Aalyaan/Desktop/彩星/毛绒/40636－1款5寸公仔套装报价（按图报价）－2026-6－2（内部）.xlsx'

const plasticTemplatePath = 'public/templates/caixing-plastic-customer-quote-template.bin'
const plushTemplatePath = 'public/templates/caixing-plush-customer-quote-template.bin'

function asArrayBuffer(bytes: Uint8Array) {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

function createMinimalCaixingWorkbook() {
  const rows: XlsxCellInput[][] = Array.from({ length: 90 }, () => [])

  rows[9][0] = '68963发声亮灯剑报价（按图报价）'
  rows[10][2] = '名称'
  rows[10][3] = '料型'
  rows[10][4] = '料重(G)'
  rows[10][6] = '机型(A)'
  rows[10][7] = '1出几套'
  rows[10][8] = '1出几件'
  rows[10][9] = '目标数'
  rows[10][10] = '啤工'
  rows[10][11] = '料金额'
  rows[10][13] = '周期'
  rows[10][14] = '模价'
  rows[10][15] = '报客模费'
  rows[12][1] = '1'
  rows[12][2] = '剑柄上盖'
  rows[12][3] = 'ABS'
  rows[12][4] = 120
  rows[12][6] = 14
  rows[12][7] = 2
  rows[12][8] = 2
  rows[12][9] = 3600
  rows[12][10] = 0.2
  rows[12][11] = 1.94
  rows[12][13] = 24
  rows[12][14] = 5000
  rows[12][15] = 5300
  rows[13][2] = '剑柄下盖'
  rows[13][8] = 2
  rows[14][9] = '合计：'
  rows[14][10] = 0.2
  rows[14][11] = 1.94
  rows[34][1] = '料价'
  rows[34][2] = '料'
  rows[34][3] = 1.94
  rows[35][1] = '啤工'
  rows[35][2] = '啤工'
  rows[35][3] = 0.2
  rows[36][1] = '装配工'
  rows[36][2] = '装配人工'
  rows[36][3] = 0.6
  rows[37][1] = '彩盒/内咭'
  rows[37][2] = '彩盒'
  rows[37][3] = 1.2
  rows[38][1] = '五金'
  rows[38][2] = '螺丝'
  rows[38][3] = 0.08
  rows[39][1] = '车衣'
  rows[39][2] = '衣服'
  rows[39][3] = 1.5
  rows[40][1] = '车发'
  rows[40][2] = '车发人工'
  rows[40][3] = 0.4
  rows[41][12] = '外箱外尺码：'
  rows[41][13] = 13
  rows[41][14] = 11
  rows[41][15] = 9.5
  rows[42][12] = 'CU.FT：'
  rows[42][13] = 0.786
  rows[43][12] = '纸箱价：'
  rows[43][13] = 3.9
  rows[43][14] = 4

  return asArrayBuffer(createXlsxWorkbook([{ name: '68963', rows }]))
}

function createPlasticWorkbookWithProcessDetails() {
  const rows = parseXlsxWorkbook(createMinimalCaixingWorkbook()).sheets[0].rows
    .map((row) => [...row]) as XlsxCellInput[][]

  rows[50] ??= []
  rows[51] ??= []
  rows[52] ??= []
  rows[53] ??= []
  rows[50][1] = '吹气'
  rows[50][2] = '剑身'
  rows[50][3] = 1.4
  rows[51][1] = '搪胶'
  rows[51][2] = '软胶把手'
  rows[51][3] = 0.5
  rows[52][1] = '油漆'
  rows[52][2] = '喷油油漆'
  rows[52][3] = 0.3
  rows[53][1] = '喷油工'
  rows[53][2] = '喷油人工'
  rows[53][3] = 1.38

  return asArrayBuffer(createXlsxWorkbook([
    { name: '68963', rows },
    {
      name: '喷油',
      rows: [
        ['图片', '客户', '货号', '位置', '夹模', '边模', '移印', '油漆', '人工', '备注'],
        [null, '彩星', 68963, '剑身', 1, null, null, 0.3, 1.38, null],
        [null, null, null, null, null, null, null, 1.7, null, null],
      ],
    },
  ]))
}

function readFileAsArrayBuffer(path: string) {
  const bytes = readFileSync(path)
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

function readCellStyle(zip: Record<string, Uint8Array>, sheetPath: string, ref: string) {
  const xml = strFromU8(zip[sheetPath])
  const cellPattern = /<c\b([^>]*)\/>|<c\b([^>]*)>[\s\S]*?<\/c>/g

  for (const match of xml.matchAll(cellPattern)) {
    const attrs = match[1] ?? match[2] ?? ''
    if (attrs.includes(`r="${ref}"`)) {
      return attrs.match(/\bs="([^"]*)"/)?.[1] ?? ''
    }
  }

  return ''
}

function readXmlAttr(attrs: string, name: string) {
  return attrs.match(new RegExp(`\\b${name}="([^"]*)"`))?.[1] ?? ''
}

function decodeXmlAttr(value: string) {
  return value
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
}

function normalizeWorksheetTarget(target: string) {
  const normalized = target.replace(/\\/g, '/').replace(/^\/+/, '')
  return normalized.startsWith('xl/') ? normalized : `xl/${normalized}`
}

function resolvePartPath(basePartPath: string, target: string) {
  if (target.startsWith('/')) {
    return target.replace(/^\/+/, '')
  }

  const resolved: string[] = []
  ;[...basePartPath.split('/').slice(0, -1), ...target.split('/')].forEach((part) => {
    if (!part || part === '.') {
      return
    }

    if (part === '..') {
      resolved.pop()
      return
    }

    resolved.push(part)
  })

  return resolved.join('/')
}

function partRelsPath(partPath: string) {
  const parts = partPath.split('/')
  const fileName = parts.pop()
  return `${parts.join('/')}/_rels/${fileName}.rels`
}

function findSheetPath(zip: Record<string, Uint8Array>, sheetName: string) {
  const workbookXml = strFromU8(zip['xl/workbook.xml'])
  const relationsXml = strFromU8(zip['xl/_rels/workbook.xml.rels'])
  const relationMap = new Map<string, string>()

  for (const match of relationsXml.matchAll(/<Relationship\b([^>]*)\/>/g)) {
    relationMap.set(readXmlAttr(match[1], 'Id'), readXmlAttr(match[1], 'Target'))
  }

  for (const match of workbookXml.matchAll(/<sheet\b([^>]*)\/>/g)) {
    const attrs = match[1]
    if (decodeXmlAttr(readXmlAttr(attrs, 'name')) === sheetName) {
      return normalizeWorksheetTarget(relationMap.get(readXmlAttr(attrs, 'r:id')) ?? '')
    }
  }

  return ''
}

function readSheetPictureCount(zip: Record<string, Uint8Array>, sheetName: string) {
  const sheetPath = findSheetPath(zip, sheetName)
  const sheetXml = sheetPath && zip[sheetPath] ? strFromU8(zip[sheetPath]) : ''
  const sheetRelsXml = sheetPath && zip[partRelsPath(sheetPath)] ? strFromU8(zip[partRelsPath(sheetPath)]) : ''
  let pictureCount = 0

  for (const drawingMatch of sheetXml.matchAll(/<drawing\b([^>]*)\/>/g)) {
    const drawingRelationId = readXmlAttr(drawingMatch[1], 'r:id')

    for (const relationMatch of sheetRelsXml.matchAll(/<Relationship\b([^>]*)\/>/g)) {
      const relationAttrs = relationMatch[1]
      if (readXmlAttr(relationAttrs, 'Id') !== drawingRelationId || !readXmlAttr(relationAttrs, 'Type').includes('/drawing')) {
        continue
      }

      const drawingPath = resolvePartPath(sheetPath, readXmlAttr(relationAttrs, 'Target'))
      const drawingXml = drawingPath && zip[drawingPath] ? strFromU8(zip[drawingPath]) : ''
      pictureCount += drawingXml.match(/<xdr:pic\b/g)?.length ?? 0
    }
  }

  return pictureCount
}

describe('Caixing customer price converter', () => {
  it('converts plastic and exports the plastic quote workbook structure', () => {
    const result = convertCaixingInternalQuote(
      createMinimalCaixingWorkbook(),
      '68963发声亮灯剑报价（按图报价）－2026-6-27.xlsx',
      'plastic',
    )

    expect(result.productType).toBe('plastic')
    expect(result.sheets[0].name).toContain('塑胶')
    expect(result.sheets[0].details.length).toBeGreaterThan(4)
    expect(result.sheets[0].totalCustomerHkd).toBeGreaterThan(0)
    expect(buildCaixingCustomerQuoteFileName(result)).toContain('塑胶')

    const output = createCaixingCustomerQuoteWorkbook(result)
    const parsed = parseXlsxWorkbook(asArrayBuffer(output))

    expect(parsed.sheets.map((sheet) => sheet.name)).toEqual([
      'Summary',
      'Tool Plan',
      'Elect',
      'Purchase',
      'Packing',
      'Fabric',
    ])
    expect(parsed.sheets[0].rows[0][0]).toBe('VENDOR QUOTATION')
    expect(parsed.sheets[0].rows[3][6]).toBe('塑胶')
  })

  it('fills the plastic customer quote template while preserving template styles', () => {
    const result = convertCaixingInternalQuote(
      createMinimalCaixingWorkbook(),
      '68963 quote 2026-6-27.xlsx',
      'plastic',
    )
    const template = readFileSync(plasticTemplatePath)
    const output = createCaixingCustomerQuoteWorkbook(result, readFileAsArrayBuffer(plasticTemplatePath))
    const parsed = parseXlsxWorkbook(asArrayBuffer(output))

    expect(parsed.sheets.slice(0, 7).map((sheet) => sheet.name)).toEqual([
      'Deco List & Product Image',
      'Summary',
      'Tool Plan',
      'Elect',
      'purchase',
      'Packing',
      'Fabric',
    ])
    expect(parsed.sheets.find((sheet) => sheet.name === 'Summary')?.rows[2][1]).toBe('68963')
    expect(parsed.sheets.find((sheet) => sheet.name === 'Tool Plan')?.rows[14][0]).toBe(1)

    const templateZip = unzipSync(template)
    const outputZip = unzipSync(output)
    expect(readCellStyle(outputZip, 'xl/worksheets/sheet2.xml', 'A1')).toBe(readCellStyle(templateZip, 'xl/worksheets/sheet2.xml', 'A1'))
    expect(readCellStyle(outputZip, 'xl/worksheets/sheet2.xml', 'B3')).toBe(readCellStyle(templateZip, 'xl/worksheets/sheet2.xml', 'B3'))
    expect(readCellStyle(outputZip, 'xl/worksheets/sheet3.xml', 'A15')).toBe(readCellStyle(templateZip, 'xl/worksheets/sheet3.xml', 'A15'))
    expect(readSheetPictureCount(templateZip, 'Deco List & Product Image')).toBeGreaterThan(0)
    expect(readSheetPictureCount(templateZip, 'Summary')).toBeGreaterThan(0)
    expect(readSheetPictureCount(outputZip, 'Deco List & Product Image')).toBe(0)
    expect(readSheetPictureCount(outputZip, 'Summary')).toBe(1)
    expect(outputZip['xl/media/image1.png']).toBeUndefined()
    const decoXml = strFromU8(outputZip['xl/worksheets/sheet1.xml'])
    expect(decoXml).not.toContain('[1]Summary!')
    expect(decoXml).toContain('<f>Summary!A3</f>')
    expect(parsed.sheets.find((sheet) => sheet.name === 'Deco List & Product Image')?.rows[0][6]).toBe('68963')
    expect(readCellStyle(outputZip, 'xl/worksheets/sheet3.xml', 'E15')).toBe('508')
  })

  it('uses plastic process detail sheets and applies the required 2% scrap to purchase and packing rows', () => {
    const result = convertCaixingInternalQuote(
      createPlasticWorkbookWithProcessDetails(),
      '68963 quote 2026-6-27.xlsx',
      'plastic',
    )
    const output = createCaixingCustomerQuoteWorkbook(result, readFileAsArrayBuffer(plasticTemplatePath))
    const workbook = parseXlsxWorkbook(asArrayBuffer(output))
    const summary = workbook.sheets.find((sheet) => sheet.name === 'Summary')
    const toolPlan = workbook.sheets.find((sheet) => sheet.name === 'Tool Plan')
    const purchase = workbook.sheets.find((sheet) => sheet.name === 'purchase')
    const packing = workbook.sheets.find((sheet) => sheet.name === 'Packing')
    const templatePacking = parseXlsxWorkbook(readFileAsArrayBuffer(plasticTemplatePath))
      .sheets.find((sheet) => sheet.name === 'Packing')

    expect(summary?.rows[18][4]).toBeCloseTo(0.7, 6)
    expect(summary?.rows[19][4]).toBeCloseTo(1.4, 6)
    expect(summary?.rows[20][4]).toBeCloseTo(1.7, 6)
    expect(toolPlan?.rows[15][1]).toBe('BL')
    expect(toolPlan?.rows[15][5]).toBe('剑身')
    expect(toolPlan?.rows[15][16]).toBeCloseTo(1.4, 6)
    expect(toolPlan?.rows[16][1]).toBe('RC')
    expect(toolPlan?.rows[16][5]).toBe('软胶把手')
    expect(toolPlan?.rows[16][16]).toBeCloseTo(0.5, 6)
    expect(toolPlan?.rows[68][16]).toBeCloseTo(2.1, 6)
    expect(purchase?.rows[7][7]).toBeCloseTo(0.02, 6)
    expect(purchase?.rows[7][8]).toBeCloseTo(0.0816, 6)
    expect(packing?.rows.slice(6, 52).map((row) => row?.[1])).toEqual(
      templatePacking?.rows.slice(6, 52).map((row) => row?.[1]),
    )
    expect(packing?.rows[12][1]).toBe('Box - Open')
    expect(packing?.rows[12][2]).toBe('彩盒')
    expect(packing?.rows[12][12]).toBeCloseTo(0.02, 6)
    expect(packing?.rows[12][13]).toBeCloseTo(1.224, 6)
    expect(packing?.rows[24][12]).toBeCloseTo(0.02, 6)
    expect(packing?.rows[24][13]).toBeCloseTo(0.9945, 6)
    expect(summary?.rows[13][4]).toBeCloseTo(0.0816, 6)
    expect(summary?.rows[14][4]).toBeCloseTo(2.2185, 6)
  })

  it('converts plush and exports the plush-first quote workbook structure', () => {
    const result = convertCaixingInternalQuote(
      createMinimalCaixingWorkbook(),
      '40636－1款5寸公仔套装报价（按图报价）－2026-6－2（内部）.xlsx',
      'plush',
    )

    expect(result.productType).toBe('plush')
    expect(result.sheets[0].name).toContain('毛绒')
    expect(buildCaixingCustomerQuoteFileName(result)).toContain('毛绒')

    const output = createCaixingCustomerQuoteWorkbook(result)
    const parsed = parseXlsxWorkbook(asArrayBuffer(output))

    expect(parsed.sheets.map((sheet) => sheet.name)).toEqual([
      'Summary',
      'Tool Plan',
      'Purchase',
      'Fabric',
      'Packing',
      'Elect',
    ])
    expect(parsed.sheets[0].rows[3][6]).toBe('毛绒')
    expect(parsed.sheets[0].rows[23][0]).toBe('Hair Rooting')
  })

  it('fills the plush customer quote template while preserving template styles', () => {
    const result = convertCaixingInternalQuote(
      createMinimalCaixingWorkbook(),
      '40636 quote 2026-6-2.xlsx',
      'plush',
    )
    const template = readFileSync(plushTemplatePath)
    const output = createCaixingCustomerQuoteWorkbook(result, readFileAsArrayBuffer(plushTemplatePath))
    const parsed = parseXlsxWorkbook(asArrayBuffer(output))

    expect(parsed.sheets.slice(0, 7).map((sheet) => sheet.name)).toEqual([
      'Deco List & Product Image',
      'Summary',
      'Tool Plan',
      'Elect',
      'Purchase',
      'Fabric',
      'Packing',
    ])
    expect(parsed.sheets.find((sheet) => sheet.name === 'Summary')?.rows[2][1]).toBe('68963')
    expect(parsed.sheets.find((sheet) => sheet.name === 'Tool Plan')?.rows[14][0]).toBe(1)

    const templateZip = unzipSync(template)
    const outputZip = unzipSync(output)
    expect(readCellStyle(outputZip, 'xl/worksheets/sheet2.xml', 'A1')).toBe(readCellStyle(templateZip, 'xl/worksheets/sheet2.xml', 'A1'))
    expect(readCellStyle(outputZip, 'xl/worksheets/sheet2.xml', 'B3')).toBe(readCellStyle(templateZip, 'xl/worksheets/sheet2.xml', 'B3'))
    expect(readCellStyle(outputZip, 'xl/worksheets/sheet3.xml', 'A15')).toBe(readCellStyle(templateZip, 'xl/worksheets/sheet3.xml', 'A15'))
    expect(readCellStyle(outputZip, 'xl/worksheets/sheet6.xml', 'B8')).toBe(readCellStyle(templateZip, 'xl/worksheets/sheet6.xml', 'B8'))
    expect(readCellStyle(outputZip, 'xl/worksheets/sheet7.xml', 'A24')).toBe(readCellStyle(templateZip, 'xl/worksheets/sheet7.xml', 'A24'))
    expect(readSheetPictureCount(templateZip, 'Deco List & Product Image')).toBeGreaterThan(0)
    expect(readSheetPictureCount(templateZip, 'Summary')).toBeGreaterThan(0)
    expect(readSheetPictureCount(outputZip, 'Deco List & Product Image')).toBe(0)
    expect(readSheetPictureCount(outputZip, 'Summary')).toBe(2)
    expect(outputZip['xl/media/image1.png']).toBeUndefined()
    expect(readCellStyle(outputZip, 'xl/worksheets/sheet3.xml', 'E15')).toBe('533')
  })

  it('reads the real Caixing sample workbooks when they are available locally', () => {
    if (!existsSync(plasticSamplePath) || !existsSync(plushSamplePath)) {
      return
    }

    const plastic = convertCaixingInternalQuote(
      readFileAsArrayBuffer(plasticSamplePath),
      '68963发声亮灯剑报价（按图报价）－2026-6-27.xlsx',
      'plastic',
    )
    const plush = convertCaixingInternalQuote(
      readFileAsArrayBuffer(plushSamplePath),
      '40636－1款5寸公仔套装报价（按图报价）－2026-6－2（内部）.xlsx',
      'plush',
    )

    expect(plastic.sheets[0].details.length).toBeGreaterThan(20)
    expect(plastic.sheets[0].totalCustomerHkd).toBeGreaterThan(10)
    expect(plush.sheets[0].details.length).toBeGreaterThan(40)
    expect(plush.sheets[0].totalCustomerHkd).toBeGreaterThan(10)

    expect(parseXlsxWorkbook(asArrayBuffer(createCaixingCustomerQuoteWorkbook(plastic))).sheets[0].rows[3][6]).toBe('塑胶')
    expect(parseXlsxWorkbook(asArrayBuffer(createCaixingCustomerQuoteWorkbook(plush))).sheets[0].rows[3][6]).toBe('毛绒')
  }, 60_000)

  it('flags a material row that cites another material price without creating a customer multiplier', () => {
    const rows = parseXlsxWorkbook(createMinimalCaixingWorkbook()).sheets[0].rows
      .map((row) => [...row]) as XlsxCellInput[][]
    for (const index of [0, 1, 3, 4]) rows[index] ??= []
    rows[0][4] = 'ABS料'
    rows[1][4] = 7.2
    rows[3][4] = '特价PVC'
    rows[4][4] = 6.8
    rows[12][5] = { value: 6.8 / 454, formula: 'E5/454' }
    const mismatched = convertCaixingInternalQuote(
      asArrayBuffer(createXlsxWorkbook([{ name: '68963', rows }])), 'mismatch.xlsx', 'plastic',
    )
    expect(mismatched.warnings).toEqual([expect.stringContaining('第 13 行料型为 ABS，料价公式却引用 E5（PVC）')])
    rows[12][5] = { value: 7.2 / 454, formula: 'E2/454' }
    const corrected = convertCaixingInternalQuote(
      asArrayBuffer(createXlsxWorkbook([{ name: '68963', rows }])), 'corrected.xlsx', 'plastic',
    )
    expect(corrected.warnings).toEqual([])
  })

  it('reports the supplied 68972 source formula mismatch as a review warning', () => {
    const path = 'C:/Users/Aalyaan/Desktop/自动报客/华兴-彩星/塑胶/68972、68974两款机器人按图报价2026－9－4.xlsx'
    if (!existsSync(path)) return
    const result = convertCaixingInternalQuote(readFileAsArrayBuffer(path), '68972、68974两款机器人按图报价2026－9－4.xlsx', 'plastic')
    expect(result.warnings?.some((warning) => warning.includes('第 59 行') && warning.includes('ABS') && warning.includes('PVC'))).toBe(true)
  }, 60_000)

  it('extends the plastic Tool Plan for both legacy parts and extra blow/slush processes', () => {
    const result = convertCaixingInternalQuote(
      createPlasticWorkbookWithProcessDetails(), '68963-legacy.xlsx', 'plastic',
    )
    const quote = result.sheets[0].quoteData
    const first = quote.injectionRows[0]
    for (let index = quote.injectionRows.length + 1; index <= 61; index += 1) {
      quote.injectionRows.push({ ...first, lineNo: String(index), name: `补充零件 ${index}`,
        materialCostHkd: 0, moldingCostHkd: 0, moldCostHkd: 0, customerMoldCostHkd: 0 })
    }
    const output = createCaixingCustomerQuoteWorkbook(result, readFileSync(plasticTemplatePath))
    const workbook = parseXlsxWorkbook(asArrayBuffer(output), { includeFormulas: true })
    const tool = workbook.sheets.find((sheet) => sheet.name === 'Tool Plan')!
    const summary = workbook.sheets.find((sheet) => sheet.name === 'Summary')!
    const blowIndex = tool.rows.findIndex((row) => row?.[5] === '剑身')
    const slushIndex = tool.rows.findIndex((row) => row?.[5] === '软胶把手')
    expect(blowIndex).toBe(76)
    expect(slushIndex).toBe(77)
    expect(tool.rows[blowIndex]?.[16]).toBe(1.4)
    expect(tool.rows[slushIndex]?.[16]).toBe(.5)
    expect(tool.cellFormulas?.Q79).toBe('SUM(Q60:Q78)')
    expect(tool.cellFormulas?.Q80).toBe('Q58+Q79')
    expect(summary.cellFormulas?.E19).toContain("'Tool Plan'!Q60:Q78")
  }, 30_000)
})

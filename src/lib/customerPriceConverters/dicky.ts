import { parseXlsxWorkbook, type XlsxCellValue } from './xlsxLite'
import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'

type DetailCompareStatus = '上调' | '下调' | '持平'

interface DickyWorkbookSheetRef {
  name: string
  path: string
  relationId: string
  sheetId: number
}

interface DickyWorksheetCell {
  ref: string
  attrs: string
  body: string
  full: string
  start: number
  end: number
}

interface DickyCellPatch {
  ref: string
  value: XlsxCellValue
  formula?: string
  style?: number
  styleRef?: string
}

export interface DickyQuoteDetailRow {
  id: string
  sheetId: string
  sheetName: string
  itemNo: string
  description: string
  internalPriceHkd: number
  customerPriceHkd: number
  previousCustomerPriceHkd: number
  differenceHkd: number
  marginBand: string
  compareStatus: DetailCompareStatus
}

export interface DickyConvertedSheet {
  id: string
  name: string
  sourceFileName: string
  rowCount: number
  totalInternalHkd: number
  totalCustomerHkd: number
  details: DickyQuoteDetailRow[]
}

export interface DickyConversionResult {
  sourceFileName: string
  sourceBuffer: ArrayBuffer
  summarySheetName: string
  clientName: string
  quoteDate: Date
  sheets: DickyConvertedSheet[]
}

export const DICKY_CUSTOMER_QUOTE_TEMPLATE_URL = '/templates/dicky-customer-quote-template.bin'

const SUMMARY_SHEET_NAME = '总表'
const QUOTATION_SHEET_NAMES = ['Quotation', 'Quatation']
const XML_HEADER = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
const WORKSHEET_REL_TYPE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet'
const WORKSHEET_CONTENT_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'

const PRODUCT_TRANSLATIONS: Array<[RegExp, string]> = [
  [/史迪仔/i, 'Stitch Cable Buggy'],
  [/米妮/i, 'Minnie Cable'],
  [/胡迪/i, 'Woody Cable Buggy'],
  [/雪宝/i, 'Olaf Cable Sledge'],
]

const PART_TRANSLATIONS = new Map<string, string>([
  ['车灯', 'Car Light'],
  ['车底', 'Car Bottom'],
  ['车面', 'Car Body'],
  ['车身', 'Car Body'],
  ['车胎', 'Car Tire'],
  ['车铃', 'Car Bell'],
  ['齿轮*8', 'Gear * 8'],
  ['牙箱盖、齿轮盖，前小轮压盖，配件', 'Gearbox Cover, Gear Cover, Front Small Wheel Cap, Accessories'],
  ['公仔头前壳/后壳,身体前壳/后壳', 'Doll Head Front Shell / Rear Shell, Body Front Shell / Rear Shell'],
  ['公仔头前壳/后壳+身体前壳/后壳', 'Doll Head Front Shell / Rear Shell, Body Front Shell / Rear Shell'],
  ['座椅配件/车底压盖/包装扣*2/车尾配件', 'Seat Accessory / Bottom Cover / Packing Buckle * 2 / Car Rear Accessory'],
  ['耳朵/手/遥控器配件', 'Ears / Hand / Remote Control Accessory'],
  ['遥控器面壳/底壳/电池盖', 'Remote Control Front Shell / Bottom Shell / Battery Cover'],
  ['前进按制，后退按制', 'Forward Button, Reverse Button'],
  ['车头配件/座椅配件/车底压盖/包装扣*2/车尾配件', 'Car Front Accessory / Seat Accessory / Bottom Cover / Packing Buckle * 2 / Car Rear Accessory'],
  ['耳朵/遥控器配件+左手/右手', 'Ears / Remote Control Accessory + Left Hand / Right Hand'],
  ['车窗', 'Car Window'],
  ['前泵把/避震*2', 'Front Bumper / Shock Absorber * 2'],
  ['柱子', 'Pillar'],
  ['定风翼', 'Spoiler / Rear Wing'],
  ['黄色侧面装饰件', 'Yellow Side Decoration / Side Trim'],
  ['公仔头前壳/后壳', 'Doll Head Front Shell / Rear Shell'],
])

const MOLD_REMARK_TRANSLATIONS = new Map<string, string>([
  ['米妮/史迪仔/胡迪/雪宝/(共用模具）', 'Minnie / Stitch / Woody / Olaf (Common Mold)'],
  ['米妮/史迪仔/胡迪/雪宝/(共用模具)', 'Minnie / Stitch / Woody / Olaf (Common Mold)'],
  ['米妮/史迪仔/胡迪/雪宝(共用模具）', 'Minnie / Stitch / Woody / Olaf (Common Mold)'],
  ['米妮/史迪仔/胡迪/雪宝(共用模具)', 'Minnie / Stitch / Woody / Olaf (Common Mold)'],
  ['4边行位', '4 Side Sliders'],
  ['转水口', 'Sub Gate'],
  ['大水转潜水', 'Sprue to Sub Gate'],
  ['细水口', 'Pin Gate'],
  ['细水/（吹气出模）', 'Pin Gate / (Air Blow Ejection)'],
  ['细水/(吹气出模)', 'Pin Gate / (Air Blow Ejection)'],
])

const FIXED_REMARK_PATCHES: Array<[string, XlsxCellValue, string?]> = [
  ['A21', 'Remark（备注）：'],
  ['A22', 1],
  ['B22', 'Estimate based on the picture. If there are any changes, the quotation needs to be updated.'],
  ['A23', 2],
  ['B23', 'Color Box Material:  250gsm + B9+, 4C Printer, UV.'],
  ['A24', 3],
  ['B24', 'The above products include 2xAA alkaline batteries, a by-wire vehicle with lights and no sound, and Try me function.'],
  ['A25', 4],
  ['B25', 'Production following RoHS & Non-Phthalates,Cadmium,ASTM,EN71,EN62115,FCC.'],
  ['A26', 5],
  ['B26', 'This is not included any CFS and THC Cost.'],
  ['A27', 6],
  ['B27', 'Plastic Quotation(HK$/LB):'],
  ['B28', 'Type'],
  ['C28', 'Cost'],
  ['E28', 'Type'],
  ['F28', 'Cost'],
  ['B31', 'If the Material cost increased more than 5% and the exchange rate of RMB more than 2%,this quote will be revised.'],
  ['A32', 7],
  ['B32', 'Client has their own responsibility about the patent, design concept and legal issue of their products.'],
  ['A33', 8],
  ['B33', 'Except client has already paid all the amount of tooling cost, '],
  ['B34', 'product cost and relevant inventory material cost,we (Royal Regent) has the right of use and own the product.', 'B33'],
]

function toText(value: XlsxCellValue) {
  return String(value ?? '').trim()
}

function toNumber(value: XlsxCellValue) {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : 0
  }

  const parsed = Number(String(value ?? '').replace(/[$,HKD]/gi, '').trim())
  return Number.isFinite(parsed) ? parsed : 0
}

function round(value: number, precision = 3) {
  if (!Number.isFinite(value)) {
    return 0
  }

  const factor = 10 ** precision
  return Math.round(value * factor) / factor
}

function compareStatus(difference: number): DetailCompareStatus {
  if (difference > 0.01) return '上调'
  if (difference < -0.01) return '下调'
  return '持平'
}

function marginBand(internalPriceHkd: number, customerPriceHkd: number) {
  if (!internalPriceHkd) {
    return '-'
  }

  return `${(((customerPriceHkd - internalPriceHkd) / internalPriceHkd) * 100).toFixed(1)}%`
}

function sanitizeFileNamePart(value: string) {
  return value.replace(/[\\/:*?"<>|]/g, '_').replace(/\s+/g, ' ').trim()
}

function normalizeDickieSpelling(value: string) {
  return value.replace(/\bDicky\b/g, 'Dickie')
}

function normalizeDickieCellValue(value: XlsxCellValue): XlsxCellValue {
  return typeof value === 'string' ? normalizeDickieSpelling(value) : value
}

function formatFileDate(date = new Date()) {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}${month}${day}`
}

function excelSerialToDate(serial: number) {
  const epoch = Date.UTC(1899, 11, 30)
  return new Date(epoch + serial * 86400000)
}

function maybeDate(value: XlsxCellValue) {
  if (typeof value === 'number' && value > 20000 && value < 80000) {
    return excelSerialToDate(value)
  }

  return new Date()
}

function normalizeText(value: string) {
  return value.replace(/\s+/g, ' ').replace(/[，]/g, ',').trim()
}

function translateProductName(value: string) {
  let translated = value

  PRODUCT_TRANSLATIONS.forEach(([pattern, replacement]) => {
    translated = translated.replace(pattern, replacement)
  })

  translated = translated
    .replace(/（\s*包含\s*2xAA-?LR6\s*电池\s*）/gi, '(2xAA-LR6 INCLUDED)')
    .replace(/（\s*不包含\s*2xAA-?LR6\s*电池\s*）/gi, '(2xAA-LR6 EXCLUDED)')
    .replace(/包含2xAA-?LR6电池/gi, '2xAA-LR6 INCLUDED')
    .replace(/不包含2xAA-?LR6电池/gi, '2xAA-LR6 EXCLUDED')

  return translated
}

function translatePartDescription(value: string) {
  const normalized = normalizeTranslationKey(value)

  const exactTranslation = PART_TRANSLATIONS.get(normalized)
  if (exactTranslation) {
    return exactTranslation
  }

  if (normalized.includes('牙箱盖') && normalized.includes('齿轮盖')) {
    return 'Gearbox Cover, Gear Cover, Front Small Wheel Cap, Accessories'
  }

  if (normalized.includes('公仔头前壳') && normalized.includes('后壳') && normalized.includes('身体前壳')) {
    return 'Doll Head Front Shell / Rear Shell, Body Front Shell / Rear Shell'
  }

  if (normalized.includes('座椅配件') && normalized.includes('车底压盖') && normalized.includes('车尾配件')) {
    return 'Seat Accessory / Bottom Cover / Packing Buckle * 2 / Car Rear Accessory'
  }

  if (normalized.includes('耳朵') && normalized.includes('遥控器配件') && normalized.includes('左手')) {
    return 'Ears / Remote Control Accessory + Left Hand / Right Hand'
  }

  return value
}

function normalizeTranslationKey(value: string) {
  return normalizeText(value)
    .replace(/\s*\/\s*/g, '/')
    .replace(/\s*\+\s*/g, '+')
    .replace(/\s*\*\s*/g, '*')
    .replace(/\s+([（(])/g, '$1')
}

function translateMoldRemark(value: string) {
  const normalized = normalizeTranslationKey(value).replace(/\s+/g, ' ')
  return MOLD_REMARK_TRANSLATIONS.get(normalized) ?? ''
}

function detailRow(
  sheetId: string,
  sheetName: string,
  itemNo: string,
  description: string,
  internalPriceHkd: number,
  customerPriceHkd: number,
): DickyQuoteDetailRow {
  const roundedInternal = round(internalPriceHkd)
  const roundedCustomer = round(customerPriceHkd)
  const differenceHkd = 0

  return {
    id: `${sheetId}-${itemNo}`,
    sheetId,
    sheetName,
    itemNo,
    description,
    internalPriceHkd: roundedInternal,
    customerPriceHkd: roundedCustomer,
    previousCustomerPriceHkd: roundedCustomer,
    differenceHkd,
    marginBand: marginBand(roundedInternal, roundedCustomer),
    compareStatus: compareStatus(differenceHkd),
  }
}

function findSummarySheet(workbook: ReturnType<typeof parseXlsxWorkbook>) {
  const sheet = workbook.sheets.find((item) => item.name === SUMMARY_SHEET_NAME)
    ?? workbook.sheets.find((item) => item.name.includes(SUMMARY_SHEET_NAME))

  if (!sheet) {
    throw new Error('未找到 Dickie 内部报价工作表：总表')
  }

  return sheet
}

function buildDetailRows(rows: XlsxCellValue[][], sheetId: string, sheetName: string) {
  const details: DickyQuoteDetailRow[] = []

  for (let rowIndex = 11; rowIndex <= 18; rowIndex += 1) {
    const row = rows[rowIndex] ?? []
    const rawItem = toText(row[1])
    if (!rawItem) {
      continue
    }

    const firstLine = rawItem.split(/\r?\n/).map((line) => line.trim()).find(Boolean) ?? `${rowIndex - 10}`
    const itemNo = firstLine.match(/\d[\d\s]+/)?.[0]?.replace(/\s+/g, ' ').trim() || String(row[0] ?? rowIndex - 10)
    const customerPriceHkd = toNumber(row[7]) || toNumber(row[8]) || toNumber(row[9])
    details.push(detailRow(sheetId, sheetName, itemNo, translateProductName(rawItem), 0, customerPriceHkd))
  }

  for (let rowIndex = 47; rowIndex < rows.length; rowIndex += 1) {
    const row = rows[rowIndex] ?? []
    const moldNo = toText(row[1])
    if (/TOTAL:HK\$/i.test(moldNo)) {
      break
    }

    if (!/^M\d+/i.test(moldNo)) {
      continue
    }

    const description = translatePartDescription(toText(row[2]))
    const customerPriceHkd = toNumber(row[9])
    details.push(detailRow(sheetId, sheetName, moldNo, description || moldNo, 0, customerPriceHkd))
  }

  return details
}

export function convertDickyInternalQuote(buffer: ArrayBuffer, sourceFileName: string): DickyConversionResult {
  const workbook = parseXlsxWorkbook(buffer)
  const summarySheet = findSummarySheet(workbook)
  const sheetId = 'dicky-summary'
  const details = buildDetailRows(summarySheet.rows, sheetId, 'Quotation')
  const totalCustomerHkd = round(details.reduce((sum, row) => sum + row.customerPriceHkd, 0))
  const clientName = normalizeDickieSpelling(toText(summarySheet.rows[6]?.[2]) || 'Dickie')
  const quoteDate = maybeDate(summarySheet.rows[6]?.[10])

  return {
    sourceFileName,
    sourceBuffer: buffer.slice(0),
    summarySheetName: summarySheet.name,
    clientName,
    quoteDate,
    sheets: [{
      id: sheetId,
      name: 'Quotation',
      sourceFileName,
      rowCount: details.length,
      totalInternalHkd: 0,
      totalCustomerHkd,
      details,
    }],
  }
}

function readXmlAttr(attrs: string, name: string) {
  return attrs.match(new RegExp(`\\b${name}="([^"]*)"`))?.[1] ?? ''
}

function escapeXml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function escapeAttr(value: string) {
  return escapeXml(value).replace(/"/g, '&quot;')
}

function decodeXml(value: string) {
  return value
    .replace(/&#x([0-9a-f]+);/gi, (_full, value: string) => {
      const codePoint = Number.parseInt(value, 16)
      return Number.isFinite(codePoint) ? String.fromCodePoint(codePoint) : ''
    })
    .replace(/&#(\d+);/g, (_full, value: string) => {
      const codePoint = Number(value)
      return Number.isFinite(codePoint) ? String.fromCodePoint(codePoint) : ''
    })
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, '\'')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
}

function getZipText(zip: Record<string, Uint8Array>, path: string) {
  const file = zip[path]
  return file ? strFromU8(file) : ''
}

function normalizeWorksheetTarget(target: string) {
  const normalized = target.replace(/\\/g, '/').replace(/^\/+/, '')
  return normalized.startsWith('xl/') ? normalized : `xl/${normalized}`
}

function resolveWorksheetRefs(zip: Record<string, Uint8Array>) {
  const workbookXml = getZipText(zip, 'xl/workbook.xml')
  const relationsXml = getZipText(zip, 'xl/_rels/workbook.xml.rels')
  const relationMap = new Map<string, string>()

  for (const match of relationsXml.matchAll(/<Relationship\b([^>]*)\/>/g)) {
    relationMap.set(readXmlAttr(match[1], 'Id'), readXmlAttr(match[1], 'Target'))
  }

  return Array.from(workbookXml.matchAll(/<sheet\b([^>]*)\/>/g)).map((match, index): DickyWorkbookSheetRef => {
    const attrs = match[1]
    const relationId = readXmlAttr(attrs, 'r:id')
    const target = relationMap.get(relationId) ?? `worksheets/sheet${index + 1}.xml`

    return {
      name: decodeXml(readXmlAttr(attrs, 'name')),
      path: normalizeWorksheetTarget(target),
      relationId,
      sheetId: Number(readXmlAttr(attrs, 'sheetId') || index + 1),
    }
  })
}

function readSharedStrings(zip: Record<string, Uint8Array>) {
  const xml = getZipText(zip, 'xl/sharedStrings.xml')
  if (!xml) {
    return [] as string[]
  }

  return Array.from(xml.matchAll(/<si>([\s\S]*?)<\/si>/g)).map((match) => {
    return decodeXml(Array.from(match[1].matchAll(/<t[^>]*>([\s\S]*?)<\/t>/g)).map((textMatch) => textMatch[1]).join(''))
  })
}

function columnNameToIndex(columnName: string) {
  return columnName.split('').reduce((total, char) => total * 26 + char.charCodeAt(0) - 64, 0) - 1
}

function columnIndexToName(columnIndex: number) {
  let index = columnIndex + 1
  let name = ''

  while (index > 0) {
    const remainder = (index - 1) % 26
    name = String.fromCharCode(65 + remainder) + name
    index = Math.floor((index - 1) / 26)
  }

  return name
}

function parseCellRef(ref: string) {
  const columnName = ref.match(/[A-Z]+/)?.[0] ?? 'A'
  const rowNumber = Number(ref.match(/\d+/)?.[0] ?? 1)

  return {
    columnName,
    columnIndex: columnNameToIndex(columnName),
    rowNumber,
  }
}

function createCellMap(sheetXml: string) {
  const cellMap = new Map<string, DickyWorksheetCell>()
  const cellPattern = /<c\b([^>]*)\/>|<c\b([^>]*)>([\s\S]*?)<\/c>/g

  for (const match of sheetXml.matchAll(cellPattern)) {
    const attrs = match[1] ?? match[2] ?? ''
    const ref = readXmlAttr(attrs, 'r')
    if (!ref || match.index === undefined) {
      continue
    }

    cellMap.set(ref, {
      ref,
      attrs,
      body: match[3] ?? '',
      full: match[0],
      start: match.index,
      end: match.index + match[0].length,
    })
  }

  return cellMap
}

function getElementText(body: string) {
  return decodeXml(Array.from(body.matchAll(/<t[^>]*>([\s\S]*?)<\/t>/g)).map((match) => match[1]).join(''))
}

function readCellFormula(body: string) {
  return decodeXml(body.match(/<f(?:\s[^>]*)?>([\s\S]*?)<\/f>/)?.[1] ?? '')
}

function readCellValue(cell: DickyWorksheetCell | undefined, sharedStrings: string[]): XlsxCellValue {
  if (!cell) {
    return ''
  }

  const type = readXmlAttr(cell.attrs, 't')

  if (type === 'inlineStr') {
    return getElementText(cell.body)
  }

  const rawValue = decodeXml(cell.body.match(/<v>([\s\S]*?)<\/v>/)?.[1] ?? '')

  if (type === 's') {
    return sharedStrings[Number(rawValue)] ?? ''
  }

  if (type === 'b') {
    return rawValue === '1'
  }

  if (type === 'str') {
    return rawValue
  }

  if (/^-?\d+(?:\.\d+)?(?:e[+-]?\d+)?$/i.test(rawValue.trim())) {
    return Number(rawValue)
  }

  return rawValue
}

function readCellText(cell: DickyWorksheetCell | undefined, sharedStrings: string[]) {
  const value = toText(readCellValue(cell, sharedStrings))
  if (value || !cell) {
    return value
  }

  return toText(getElementText(cell.full))
}

function parseSimpleCellFormula(formula: string) {
  const normalizedFormula = formula.trim().replace(/^=/, '')
  const quotedMatch = normalizedFormula.match(/^'((?:[^']|'')+)'!\$?([A-Z]{1,3})\$?(\d+)$/)
  if (quotedMatch) {
    return {
      sheetName: quotedMatch[1].replace(/''/g, '\''),
      cellRef: `${quotedMatch[2]}${quotedMatch[3]}`,
    }
  }

  const unquotedMatch = normalizedFormula.match(/^([^!]+)!\$?([A-Z]{1,3})\$?(\d+)$/)
  if (unquotedMatch) {
    return {
      sheetName: unquotedMatch[1],
      cellRef: `${unquotedMatch[2]}${unquotedMatch[3]}`,
    }
  }

  return null
}

function resolveCellText(
  cell: DickyWorksheetCell | undefined,
  sharedStrings: string[],
  workbookCells: Map<string, Map<string, DickyWorksheetCell>>,
  depth = 0,
): string {
  if (!cell || depth > 8) {
    return ''
  }

  const directValue = readCellText(cell, sharedStrings)
  if (directValue) {
    return directValue
  }

  const parsedFormula = parseSimpleCellFormula(readCellFormula(cell.body))
  if (!parsedFormula) {
    return ''
  }

  return resolveCellText(
    workbookCells.get(parsedFormula.sheetName)?.get(parsedFormula.cellRef),
    sharedStrings,
    workbookCells,
    depth + 1,
  )
}

function formatNumber(value: number) {
  if (!Number.isFinite(value)) {
    return '0'
  }

  return String(Number(value.toFixed(12)))
}

function buildCellXml(patch: DickyCellPatch, existing?: DickyWorksheetCell, styleSource?: DickyWorksheetCell) {
  const existingStyle = existing ? Number(readXmlAttr(existing.attrs, 's')) : Number.NaN
  const sourceStyle = styleSource ? Number(readXmlAttr(styleSource.attrs, 's')) : Number.NaN
  const style = Number.isFinite(existingStyle) ? existingStyle : Number.isFinite(sourceStyle) ? sourceStyle : patch.style
  const styleAttr = typeof style === 'number' ? ` s="${style}"` : ''
  const formula = patch.formula ?? ''

  if (patch.value === null || patch.value === undefined || patch.value === '') {
    if (formula) {
      return `<c r="${patch.ref}"${styleAttr}><f>${escapeXml(formula)}</f></c>`
    }

    return `<c r="${patch.ref}"${styleAttr}/>`
  }

  if (formula) {
    if (typeof patch.value === 'number') {
      return `<c r="${patch.ref}"${styleAttr}><f>${escapeXml(formula)}</f><v>${formatNumber(patch.value)}</v></c>`
    }

    return `<c r="${patch.ref}" t="str"${styleAttr}><f>${escapeXml(formula)}</f><v>${escapeXml(String(patch.value))}</v></c>`
  }

  if (typeof patch.value === 'number') {
    return `<c r="${patch.ref}"${styleAttr}><v>${formatNumber(patch.value)}</v></c>`
  }

  if (typeof patch.value === 'boolean') {
    return `<c r="${patch.ref}" t="b"${styleAttr}><v>${patch.value ? 1 : 0}</v></c>`
  }

  const text = String(patch.value)
  const spaceAttr = /^\s|\s$/.test(text) ? ' xml:space="preserve"' : ''
  return `<c r="${patch.ref}" t="inlineStr"${styleAttr}><is><t${spaceAttr}>${escapeXml(text)}</t></is></c>`
}

function insertCell(sheetXml: string, patch: DickyCellPatch, cellMap: Map<string, DickyWorksheetCell>) {
  if ((patch.value === null || patch.value === undefined || patch.value === '') && !patch.formula) {
    return sheetXml
  }

  const { rowNumber, columnIndex } = parseCellRef(patch.ref)
  const rowPattern = new RegExp(`<row\\b[^>]*\\br="${rowNumber}"[^>]*>[\\s\\S]*?<\\/row>`)
  const rowMatch = sheetXml.match(rowPattern)
  const styleSource = patch.styleRef ? cellMap.get(patch.styleRef) : undefined
  const cellXml = buildCellXml(patch, undefined, styleSource)

  if (!rowMatch || rowMatch.index === undefined) {
    const nextRowPattern = /<row\b[^>]*\br="(\d+)"[^>]*>/g
    let insertIndex = sheetXml.indexOf('</sheetData>')

    for (const match of sheetXml.matchAll(nextRowPattern)) {
      if (match.index !== undefined && Number(match[1]) > rowNumber) {
        insertIndex = match.index
        break
      }
    }

    const rowXml = `<row r="${rowNumber}">${cellXml}</row>`
    return `${sheetXml.slice(0, insertIndex)}${rowXml}${sheetXml.slice(insertIndex)}`
  }

  const rowXml = rowMatch[0]
  const rowStart = rowMatch.index
  const rowEndOffset = rowXml.lastIndexOf('</row>')
  const cellPattern = /<c\b([^>]*)\/>|<c\b([^>]*)>([\s\S]*?)<\/c>/g
  let insertOffset = rowEndOffset

  for (const match of rowXml.matchAll(cellPattern)) {
    const attrs = match[1] ?? match[2] ?? ''
    const ref = readXmlAttr(attrs, 'r')
    const existingColumn = ref.match(/[A-Z]+/)?.[0]
    if (match.index !== undefined && existingColumn && columnNameToIndex(existingColumn) > columnIndex) {
      insertOffset = match.index
      break
    }
  }

  const insertIndex = rowStart + insertOffset
  return `${sheetXml.slice(0, insertIndex)}${cellXml}${sheetXml.slice(insertIndex)}`
}

function applyCellPatches(sheetXml: string, patches: DickyCellPatch[]) {
  const cellMap = createCellMap(sheetXml)
  const uniquePatches = new Map<string, DickyCellPatch>()
  const replacements: Array<{ start: number, end: number, xml: string }> = []
  const missingPatches: DickyCellPatch[] = []

  patches.forEach((patch) => uniquePatches.set(patch.ref, patch))

  Array.from(uniquePatches.values()).forEach((patch) => {
    const existing = cellMap.get(patch.ref)

    if (!existing) {
      missingPatches.push(patch)
      return
    }

    replacements.push({
      start: existing.start,
      end: existing.end,
      xml: buildCellXml(patch, existing, patch.styleRef ? cellMap.get(patch.styleRef) : undefined),
    })
  })

  let updatedXml = sheetXml
  replacements
    .sort((a, b) => b.start - a.start)
    .forEach((replacement) => {
      updatedXml = `${updatedXml.slice(0, replacement.start)}${replacement.xml}${updatedXml.slice(replacement.end)}`
    })

  return missingPatches.reduce((xml, patch) => insertCell(xml, patch, createCellMap(xml)), updatedXml)
}

function maxRowInCells(cellMap: Map<string, DickyWorksheetCell>) {
  return Math.max(1, ...Array.from(cellMap.keys()).map((ref) => parseCellRef(ref).rowNumber))
}

function refreshDimension(sheetXml: string) {
  const cellMap = createCellMap(sheetXml)
  let maxRow = 1
  let maxColumn = 0

  Array.from(cellMap.keys()).forEach((ref) => {
    const parsed = parseCellRef(ref)
    maxRow = Math.max(maxRow, parsed.rowNumber)
    maxColumn = Math.max(maxColumn, parsed.columnIndex)
  })

  const dimension = `A1:${columnIndexToName(maxColumn)}${maxRow}`
  if (/<dimension\b[^>]*\/>/.test(sheetXml)) {
    return sheetXml.replace(/<dimension\b[^>]*\/>/, `<dimension ref="${dimension}"/>`)
  }

  return sheetXml.replace(/<worksheet\b[^>]*>/, (match) => `${match}<dimension ref="${dimension}"/>`)
}

function findRowByColumnText(
  cellMap: Map<string, DickyWorksheetCell>,
  sharedStrings: string[],
  columnName: string,
  startRow: number,
  pattern: RegExp,
) {
  for (let rowNumber = startRow; rowNumber <= maxRowInCells(cellMap); rowNumber += 1) {
    if (pattern.test(readCellText(cellMap.get(`${columnName}${rowNumber}`), sharedStrings))) {
      return rowNumber
    }
  }

  return 0
}

function findQuotationSheet(sheets: DickyWorkbookSheetRef[]) {
  return sheets.find((sheet) => QUOTATION_SHEET_NAMES.some((name) => sheet.name.toLowerCase() === name.toLowerCase()))
}

function findSummarySheetRef(sheets: DickyWorkbookSheetRef[]) {
  const sheet = sheets.find((item) => item.name === SUMMARY_SHEET_NAME)
    ?? sheets.find((item) => item.name.includes(SUMMARY_SHEET_NAME))

  if (!sheet) {
    throw new Error('未找到 Dickie 内部报价工作表：总表')
  }

  return sheet
}

function getNextRelationshipId(relsXml: string) {
  const maxId = Array.from(relsXml.matchAll(/\bId="rId(\d+)"/g))
    .reduce((max, match) => Math.max(max, Number(match[1])), 0)
  return `rId${maxId + 1}`
}

function getNextSheetId(sheets: DickyWorkbookSheetRef[]) {
  return Math.max(0, ...sheets.map((sheet) => sheet.sheetId)) + 1
}

function getNextWorksheetPath(zip: Record<string, Uint8Array>) {
  let index = 1
  while (zip[`xl/worksheets/sheet${index}.xml`]) {
    index += 1
  }

  return `xl/worksheets/sheet${index}.xml`
}

function addContentTypeOverride(contentTypesXml: string, worksheetPath: string) {
  const partName = `/${worksheetPath}`
  if (contentTypesXml.includes(`PartName="${partName}"`)) {
    return contentTypesXml
  }

  return contentTypesXml.replace(
    '</Types>',
    `<Override PartName="${partName}" ContentType="${WORKSHEET_CONTENT_TYPE}"/></Types>`,
  )
}

function forceWorkbookRecalculation(workbookXml: string) {
  const calcPr = '<calcPr calcMode="auto" fullCalcOnLoad="1" forceFullCalc="1"/>'

  if (/<calcPr\b[\s\S]*?\/>/.test(workbookXml)) {
    return workbookXml.replace(/<calcPr\b[\s\S]*?\/>/, calcPr)
  }

  if (/<calcPr\b[\s\S]*?<\/calcPr>/.test(workbookXml)) {
    return workbookXml.replace(/<calcPr\b[\s\S]*?<\/calcPr>/, calcPr)
  }

  return workbookXml.replace('</workbook>', `${calcPr}</workbook>`)
}

function partRelsPath(partPath: string) {
  const slashIndex = partPath.lastIndexOf('/')
  const dir = slashIndex >= 0 ? partPath.slice(0, slashIndex + 1) : ''
  const file = partPath.slice(slashIndex + 1)
  return `${dir}_rels/${file}.rels`
}

function copyWorksheetRels(zip: Record<string, Uint8Array>, fromPath: string, toPath: string) {
  const sourceRelsPath = partRelsPath(fromPath)
  const targetRelsPath = partRelsPath(toPath)
  if (!zip[sourceRelsPath]) {
    delete zip[targetRelsPath]
    return
  }

  zip[targetRelsPath] = zip[sourceRelsPath]
}

function copyWorksheetContent(zip: Record<string, Uint8Array>, fromPath: string, toPath: string) {
  zip[toPath] = strToU8(getZipText(zip, fromPath))
  copyWorksheetRels(zip, fromPath, toPath)
}

function createWorkbookCellMaps(zip: Record<string, Uint8Array>, sheets: DickyWorkbookSheetRef[]) {
  return new Map(sheets.map((sheet) => [sheet.name, createCellMap(getZipText(zip, sheet.path))]))
}

function addQuotationWorksheet(
  zip: Record<string, Uint8Array>,
  sheets: DickyWorkbookSheetRef[],
  sourceSheet: DickyWorkbookSheetRef,
) {
  const workbookPath = 'xl/workbook.xml'
  const relsPath = 'xl/_rels/workbook.xml.rels'
  const contentTypesPath = '[Content_Types].xml'
  const worksheetPath = getNextWorksheetPath(zip)
  const relationshipId = getNextRelationshipId(getZipText(zip, relsPath))
  const sheetId = getNextSheetId(sheets)

  zip[worksheetPath] = strToU8(getZipText(zip, sourceSheet.path))
  copyWorksheetRels(zip, sourceSheet.path, worksheetPath)

  zip[workbookPath] = strToU8(getZipText(zip, workbookPath).replace(
    '</sheets>',
    `<sheet name="${escapeAttr(QUOTATION_SHEET_NAMES[0])}" sheetId="${sheetId}" r:id="${relationshipId}"/></sheets>`,
  ))
  zip[relsPath] = strToU8(getZipText(zip, relsPath).replace(
    '</Relationships>',
    `<Relationship Id="${relationshipId}" Type="${WORKSHEET_REL_TYPE}" Target="${worksheetPath.replace(/^xl\//, '')}"/></Relationships>`,
  ))
  zip[contentTypesPath] = strToU8(addContentTypeOverride(getZipText(zip, contentTypesPath), worksheetPath))

  return {
    name: QUOTATION_SHEET_NAMES[0],
    path: worksheetPath,
    relationId: relationshipId,
    sheetId,
  }
}

function shiftLocalFormulaRows(formula: string, rowOffset: number) {
  if (!formula || rowOffset === 0 || formula.includes('!')) {
    return formula
  }

  return formula.replace(/(\$?[A-Z]{1,3})(\$?)(\d+)/g, (_full, columnName: string, absoluteRow: string, rowNumber: string) => {
    const shiftedRow = Math.max(1, Number(rowNumber) + rowOffset)
    return `${columnName}${absoluteRow}${shiftedRow}`
  })
}

function sourcePatch(
  ref: string,
  sourceCell: DickyWorksheetCell | undefined,
  sharedStrings: string[],
  rowOffset = 0,
): DickyCellPatch {
  return {
    ref,
    value: normalizeDickieCellValue(readCellValue(sourceCell, sharedStrings)),
    formula: shiftLocalFormulaRows(readCellFormula(sourceCell?.body ?? ''), rowOffset) || undefined,
  }
}

function buildQuotationPatches(
  summaryXml: string,
  quotationXml: string,
  sharedStrings: string[],
  workbookCells: Map<string, Map<string, DickyWorksheetCell>>,
) {
  const summaryCells = createCellMap(summaryXml)
  const quotationCells = createCellMap(quotationXml)
  const patches: DickyCellPatch[] = []
  const copy = (sourceRef: string, targetRef = sourceRef) => {
    const sourceCell = summaryCells.get(sourceRef)
    if (sourceCell) {
      patches.push(sourcePatch(targetRef, sourceCell, sharedStrings, parseCellRef(targetRef).rowNumber - parseCellRef(sourceRef).rowNumber))
    }
  }
  const patchText = (ref: string, value: XlsxCellValue, styleRef?: string) => patches.push({
    ref,
    value: normalizeDickieCellValue(value),
    styleRef,
  })
  const textAt = (ref: string) => resolveCellText(summaryCells.get(ref), sharedStrings, workbookCells)
  const ref = (columnName: string, rowNumber: number) => `${columnName}${rowNumber}`

  ;['C7', 'K7', 'C8', 'K8', 'C9'].forEach((cellRef) => copy(cellRef))

  for (let rowNumber = 12; rowNumber <= 19; rowNumber += 1) {
    ;['A', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J'].forEach((columnName) => copy(ref(columnName, rowNumber)))
    patchText(ref('B', rowNumber), translateProductName(textAt(ref('B', rowNumber))))
  }

  FIXED_REMARK_PATCHES.forEach(([cellRef, value, styleRef]) => patchText(cellRef, value, styleRef))

  const sourceQuotationRow = findRowByColumnText(summaryCells, sharedStrings, 'A', 35, /^Quotation/i)
  const targetQuotationRowByTitle = findRowByColumnText(quotationCells, sharedStrings, 'A', 35, /^Quotation/i)
  const sourceMoldHeaderRow = findRowByColumnText(summaryCells, sharedStrings, 'B', sourceQuotationRow, /^Mold\s*#/i)
  const targetMoldHeaderRow = findRowByColumnText(quotationCells, sharedStrings, 'B', targetQuotationRowByTitle || 35, /^Mold\s*#/i)
  const offset = sourceMoldHeaderRow && targetMoldHeaderRow
    ? targetMoldHeaderRow - sourceMoldHeaderRow
    : (targetQuotationRowByTitle || sourceQuotationRow) - sourceQuotationRow
  const targetQuotationRow = targetQuotationRowByTitle || sourceQuotationRow + offset
  const finishRow = findRowByColumnText(summaryCells, sharedStrings, 'B', sourceQuotationRow, /^Finish time/i)
    || maxRowInCells(summaryCells)
  const targetFinishRow = findRowByColumnText(quotationCells, sharedStrings, 'B', targetQuotationRow, /^Finish time/i)
    || finishRow + offset

  for (let rowNumber = targetQuotationRow; rowNumber <= targetFinishRow; rowNumber += 1) {
    ;['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K'].forEach((columnName) => {
      patchText(ref(columnName, rowNumber), null)
    })
  }

  for (let rowNumber = sourceQuotationRow; rowNumber <= finishRow; rowNumber += 1) {
    const targetRow = rowNumber + offset
    const moldNo = textAt(ref('B', rowNumber))
    const isMoldDetailRow = /^M\d+/i.test(moldNo)

    if (!isMoldDetailRow) {
      ;['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K'].forEach((columnName) => {
        copy(ref(columnName, rowNumber), ref(columnName, targetRow))
      })
      continue
    }

    ;['B', 'E', 'F', 'G', 'H', 'I', 'J', 'K'].forEach((columnName) => {
      copy(ref(columnName, rowNumber), ref(columnName, targetRow))
    })

    patchText(ref('A', targetRow), translateProductName(textAt(ref('A', rowNumber))))

    const partText = textAt(ref('C', rowNumber))
    const translatedPartText = translatePartDescription(partText)
    if (translatedPartText) {
      patchText(ref('C', targetRow), translatedPartText)
    } else {
      copy(ref('C', rowNumber), ref('C', targetRow))
    }

    const translatedRemarkText = translateMoldRemark(textAt(ref('K', rowNumber)))
    if (translatedRemarkText) {
      patchText(ref('K', targetRow), translatedRemarkText)
    }
  }

  return patches
}

export function createDickyCustomerQuoteWorkbook(
  result: DickyConversionResult,
  _templateBuffer?: ArrayBuffer | Uint8Array,
) {
  const zip = unzipSync(new Uint8Array(result.sourceBuffer))
  const sheets = resolveWorksheetRefs(zip)
  const summarySheet = findSummarySheetRef(sheets)
  const quotationSheet = findQuotationSheet(sheets) ?? addQuotationWorksheet(zip, sheets, summarySheet)

  copyWorksheetContent(zip, summarySheet.path, quotationSheet.path)

  const sharedStrings = readSharedStrings(zip)
  const workbookCells = createWorkbookCellMaps(zip, sheets)
  const summaryXml = getZipText(zip, summarySheet.path)
  const quotationXml = getZipText(zip, quotationSheet.path)

  if (!summaryXml) {
    throw new Error('Dickie 内部报价缺少总表内容')
  }

  if (!quotationXml) {
    throw new Error('Dickie 报客价工作表创建失败')
  }

  zip[quotationSheet.path] = strToU8(refreshDimension(applyCellPatches(
    quotationXml,
    buildQuotationPatches(summaryXml, quotationXml, sharedStrings, workbookCells),
  )))

  if (zip['xl/workbook.xml']) {
    zip['xl/workbook.xml'] = strToU8(forceWorkbookRecalculation(getZipText(zip, 'xl/workbook.xml')))
  }

  delete zip['xl/calcChain.xml']
  if (zip['xl/_rels/workbook.xml.rels']) {
    zip['xl/_rels/workbook.xml.rels'] = strToU8(getZipText(zip, 'xl/_rels/workbook.xml.rels').replace(
      /<Relationship\b[^>]*(?:Type="http:\/\/schemas\.openxmlformats\.org\/officeDocument\/2006\/relationships\/calcChain"|Target="calcChain\.xml")[^>]*\/>/g,
      '',
    ))
  }
  if (zip['[Content_Types].xml']) {
    zip['[Content_Types].xml'] = strToU8(getZipText(zip, '[Content_Types].xml').replace(
      /<Override\b[^>]*PartName="\/xl\/calcChain\.xml"[^>]*\/>/g,
      '',
    ))
  }

  return zipSync(zip)
}

export function buildDickyCustomerQuoteFileName(result: DickyConversionResult) {
  const sheet = result.sheets[0]
  const sourceName = normalizeDickieSpelling(sheet?.sourceFileName.replace(/\.[^.]+$/, '') ?? 'Dickie')

  return `Quotation of ${sanitizeFileNamePart(result.clientName)} - Royal Regent (R0) (${formatFileDate(result.quoteDate)})-${sanitizeFileNamePart(sourceName)}.xlsx`
}

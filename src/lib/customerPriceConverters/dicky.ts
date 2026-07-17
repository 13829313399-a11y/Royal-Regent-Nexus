import { parseXlsxWorkbook, type XlsxCellValue } from './xlsxLite'
import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'
import type { P4InternalQuoteArtifact } from './p4Artifact'

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
  forceStyleRef?: boolean
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

export interface DickyP4ProductQuoteRow {
  lineNo: number
  itemTextEn: string
  unitsPerCarton: string
  cartonCbm: number
  colorBoxSizeCm: string
  cartonSizeCm: string
  productionMoq: string
  price40hHkd: number
  price20hHkd: number
  priceLclHkd: number
}

export interface DickyP4RemarkLine { lineNo: number; textEn: string }
export interface DickyP4MaterialPrice { material: string; priceHkdLb: number }
export interface DickyP4MoldRow { projectNameEn: string; moldNo: string; partsEn: string; resin: string; moldSize: string; moldMaterial: string; cavities: number; partsPerShot: number; moldCostHkd: number; remarkEn: string }
export interface DickyP4QuoteData { clientName: string; quoteDate: string; attention: string; revision: string; fromName: string; projectNameEn: string; firstShotTime: string; finishTime: string; productRows: DickyP4ProductQuoteRow[]; remarkLines: DickyP4RemarkLine[]; materialPricesHkd: DickyP4MaterialPrice[]; moldRows: DickyP4MoldRow[] }

export interface DickyConversionResult {
  sourceFileName: string
  sourceBuffer: ArrayBuffer
  summarySheetName: string
  clientName: string
  quoteDate: Date
  sheets: DickyConvertedSheet[]
  p4QuoteData?: DickyP4QuoteData
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

const PART_TRANSLATION_ENTRIES: Array<[string, string]> = [
  ['车灯', 'Car Light'],
  ['车底', 'Car Bottom'],
  ['车面', 'Car Body'],
  ['车身', 'Car Body'],
  ['车胎', 'Car Tire'],
  ['车铃', 'Car Bell'],
  ['后车胎*2/前小轮', 'Rear Tires * 2 / Front Small Wheels'],
  ['前车胎*2', 'Front Tires * 2'],
  ['齿轮', 'Gear'],
  ['齿轮*8', 'Gear * 8'],
  ['牙箱盖、齿轮盖，前小轮压盖，配件', 'Gearbox Cover, Gear Cover, Front Small Wheel Cap, Accessories'],
  ['牙箱盖、前小轮压盖', 'Gearbox Cover / Front Small Wheel Cap'],
  ['公仔头前壳/后壳,身体前壳/后壳', 'Doll Head Front Shell / Rear Shell, Body Front Shell / Rear Shell'],
  ['公仔头前壳/后壳+身体前壳/后壳', 'Doll Head Front Shell / Rear Shell, Body Front Shell / Rear Shell'],
  ['座椅配件/车底压盖/包装扣*2/车尾配件', 'Seat Accessory / Bottom Cover / Packing Buckle * 2 / Car Rear Accessory'],
  ['耳朵/手/遥控器配件', 'Ears / Hand / Remote Control Accessory'],
  ['遥控器面壳/底壳/电池盖', 'Remote Control Front Shell / Bottom Shell / Battery Cover'],
  ['遥控器面壳/底壳/电池盖/包装扣*2/螺母压件', 'Remote Control Front Shell / Bottom Shell / Battery Cover / Packing Buckle * 2 / Nut Retainer'],
  ['前进按制，后退按制', 'Forward Button, Reverse Button'],
  ['车头配件/座椅配件/车底压盖/包装扣*2/车尾配件', 'Car Front Accessory / Seat Accessory / Bottom Cover / Packing Buckle * 2 / Car Rear Accessory'],
  ['耳朵/遥控器配件+左手/右手', 'Ears / Remote Control Accessory + Left Hand / Right Hand'],
  ['车窗', 'Car Window'],
  ['前泵把/避震*2', 'Front Bumper / Shock Absorber * 2'],
  ['柱子', 'Pillar'],
  ['定风翼', 'Spoiler / Rear Wing'],
  ['黄色侧面装饰件', 'Yellow Side Decoration / Side Trim'],
  ['公仔头前壳/后壳', 'Doll Head Front Shell / Rear Shell'],
  ['车底/座椅', 'Car Bottom / Seat'],
  ['座椅', 'Seat'],
  ['3000米妮车灯/3001史迪仔车灯', '3000 Minnie Car Light / 3001 Stitch Car Light'],
  ['3000米妮前玻璃/3005胡迪玻璃', '3000 Minnie Front Windshield / 3005 Woody Windshield'],
  ['米妮公仔头/史迪仔公仔头', 'Minnie Doll Head / Stitch Doll Head'],
  ['米妮公仔身/蝴蝶结/左右手/遥控器蝴蝶结', 'Minnie Doll Body / Bow / Left Hand / Right Hand / Remote Control Bow'],
  ['史迪仔耳朵/手/遥控器耳朵', 'Stitch Ears / Hands / Remote Control Ears'],
  ['左右车身/车底', 'Left and Right Car Bodies / Car Bottom'],
  ['3002雪宝车灯/3005胡迪车灯', '3002 Olaf Car Light / 3005 Woody Car Light'],
  ['雪宝公仔前身后身/胡迪公仔身体前壳，身体前壳后壳', 'Olaf Doll Front and Rear Body / Woody Doll Body Front Shell / Rear Shell'],
  ['雪宝头发/手/鼻子/遥控器配件', 'Olaf Hair / Hands / Nose / Remote Control Accessories'],
  ['尾翼', 'Rear Wing'],
  ['帽子/手/天线', 'Hat / Hands / Antenna'],
]

const PART_TRANSLATIONS = new Map<string, string>(
  PART_TRANSLATION_ENTRIES.map(([source, translation]) => [normalizeTranslationKey(source), translation]),
)

const MOLD_REMARK_TRANSLATION_ENTRIES: Array<[string, string]> = [
  ['米妮/史迪仔/胡迪/雪宝/(共用模具）', 'Minnie / Stitch / Woody / Olaf (Common Mold)'],
  ['米妮/史迪仔/胡迪/雪宝/(共用模具)', 'Minnie / Stitch / Woody / Olaf (Common Mold)'],
  ['米妮/史迪仔/胡迪/雪宝(共用模具）', 'Minnie / Stitch / Woody / Olaf (Common Mold)'],
  ['米妮/史迪仔/胡迪/雪宝(共用模具)', 'Minnie / Stitch / Woody / Olaf (Common Mold)'],
  ['米妮/史迪仔/胡迪/雪人(共用模具）', 'Minnie / Stitch / Woody / Olaf (Common Mold)'],
  ['米妮/史迪仔/胡迪/雪人(共用模具)', 'Minnie / Stitch / Woody / Olaf (Common Mold)'],
  ['米妮/史迪仔/胡迪(共用模具）', 'Minnie / Stitch / Woody (Common Mold)'],
  ['米妮/史迪仔/胡迪(共用模具)', 'Minnie / Stitch / Woody (Common Mold)'],
  ['米妮', 'Minnie'],
  ['史迪仔', 'Stitch'],
  ['雪宝', 'Olaf'],
  ['雪人', 'Olaf'],
  ['胡迪', 'Woody'],
  ['行位*1', '1 Side Slider'],
  ['4边行位', '4 Side Sliders'],
  ['转水口', 'Sub Gate'],
  ['转水口/喷油', 'Sub Gate / Spray Painting'],
  ['大水转潜水', 'Sprue to Sub Gate'],
  ['细水口', 'Pin Gate'],
  ['细水/（吹气出模）', 'Pin Gate / (Air Blow Ejection)'],
  ['细水/(吹气出模)', 'Pin Gate / (Air Blow Ejection)'],
]

const MOLD_REMARK_TRANSLATIONS = new Map<string, string>(
  MOLD_REMARK_TRANSLATION_ENTRIES.map(([source, translation]) => [normalizeTranslationKey(source), translation]),
)

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

function normalizeDickieSpelling(value: string) {
  return value.replace(/\bDicky\b/g, 'Dickie')
}

function normalizeDickieCellValue(value: XlsxCellValue): XlsxCellValue {
  return typeof value === 'string' ? normalizeDickieSpelling(value) : value
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

function translateRemarkText(value: string) {
  const normalized = normalizeTranslationKey(value)
  if (!normalized) {
    return ''
  }

  if (normalized === '料型') {
    return 'Type'
  }

  if (normalized === '料价') {
    return 'Cost'
  }

  if (
    /(?:样办|样板|客样).*(?:报价|核价)|(?:报价|核价).*(?:样办|样板|客样)/.test(normalized)
  ) {
    return 'This quotation is based on the sample provided by the customer. The final price will be confirmed by the approved sample. Any changes will require a revised quotation.'
  }

  if (/图片估价|看图估价/.test(normalized)) {
    const plasticWeight = normalized.match(/胶件重量(?:预计)?(?:是)?\s*(\d+(?:\.\d+)?)\s*g/i)?.[1]
    const vinylWeight = normalized.match(/搪胶重量(?:预计)?(?:是)?\s*(\d+(?:\.\d+)?)\s*g/i)?.[1]

    if (plasticWeight && vinylWeight) {
      return `Picture estimate: plastic parts ${plasticWeight}g; rotocast vinyl ${vinylWeight}g. Requote if changed.`
    }

    return 'Estimate based on the picture. If there are any changes, the quotation needs to be updated.'
  }

  if (/公仔头.*手脚.*搪胶.*塑胶件/.test(normalized)) {
    return 'Head, hands and feet: rotocast vinyl; body and accessories: plastic.'
  }

  if (/彩盒材质/.test(normalized)) {
    return 'Color Box Material:  250gsm + B9+, 4C Printer, UV.'
  }

  if (/以上产品.*2xAA.*Try\s*me/i.test(normalized)) {
    return 'The above products include 2xAA alkaline batteries, a by-wire vehicle with lights and no sound, and Try me function.'
  }

  if (/产品可通过.*RoHS/i.test(normalized)) {
    return 'Production following RoHS & Non-Phthalates,Cadmium,ASTM,EN71,EN62115,FCC.'
  }

  if (/报价未含吊柜费.*入仓费/.test(normalized)) {
    return 'This is not included any CFS and THC Cost.'
  }

  if (/按.*料价报价.*HK\$\/LB/i.test(normalized)) {
    return 'Plastic Quotation(HK$/LB):'
  }

  if (/人民币.*汇率.*2%.*原材料.*5%/.test(normalized)) {
    return 'If the Material cost increased more than 5% and the exchange rate of RMB more than 2%,this quote will be revised.'
  }

  if (/法律责任.*知识产权/.test(normalized)) {
    return 'Client has their own responsibility about the patent, design concept and legal issue of their products.'
  }

  if (/价格全数清还.*拥有权/.test(normalized)) {
    return 'Except client has already paid all the amount of tooling cost, product cost and relevant inventory material cost,we (Royal Regent) has the right of use and own the product.'
  }

  return normalizeDickieSpelling(value)
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

function p4Object(value: unknown) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function p4Rows(value: unknown) {
  return Array.isArray(value) ? value.map(p4Object) : []
}

function p4Text(value: unknown) {
  return String(value ?? '').trim()
}

function p4Number(value: unknown) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function p4Positive(value: unknown, message: string) {
  const parsed = p4Number(value)
  if (parsed <= 0) throw new Error(`Dickie 直转被阻断：${message}`)
  return parsed
}

function p4RequiredText(value: unknown, message: string, englishOnly = false) {
  const text = p4Text(value)
  if (!text) throw new Error(`Dickie 直转被阻断：${message}`)
  if (englishOnly && /[\u3400-\u9fff]/u.test(text)) throw new Error(`Dickie 直转被阻断：${message}仍含中文`)
  return normalizeDickieSpelling(text)
}

export function convertDickyP4InternalQuote(
  artifact: P4InternalQuoteArtifact,
  sourceFileName: string,
): DickyConversionResult {
  const customerFields = p4Object(artifact.sections.sales.payload.customer_quote_fields)
  const dickie = p4Object(customerFields.dickie)
  const clientName = p4RequiredText(dickie.client_name, '缺少 Client')
  const quoteDateText = p4RequiredText(dickie.quote_date, '缺少 Quote Date')
  const quoteDate = new Date(`${quoteDateText}T00:00:00`)
  if (!Number.isFinite(quoteDate.getTime())) throw new Error('Dickie 直转被阻断：Quote Date 格式无效')
  const attention = p4RequiredText(dickie.attention, '缺少 Attn')
  const revision = p4Text(dickie.revision)
  const fromName = p4RequiredText(dickie.from_name, '缺少 From', true)
  const projectNameEn = p4RequiredText(dickie.project_name_en, '缺少 Project Name 英文字款', true)
  const firstShotTime = p4RequiredText(dickie.first_shot_time, '缺少 First Shot Time 英文字款', true)
  const finishTime = p4RequiredText(dickie.finish_time, '缺少 Finish Time 英文字款', true)

  const rawProducts = p4Rows(dickie.product_rows)
  if (rawProducts.length === 0 || rawProducts.length > 8) {
    throw new Error('Dickie 直转被阻断：总表产品行必须为 1–8 行')
  }
  const productRows = rawProducts.map<DickyP4ProductQuoteRow>((row, index) => ({
    lineNo: p4Positive(row.line_no, `总表产品第 ${index + 1} 行 NO. 必须大于 0`),
    itemTextEn: p4RequiredText(row.item_text_en, `总表产品第 ${index + 1} 行缺少 ITEM 英文字款`, true),
    unitsPerCarton: p4RequiredText(row.units_per_carton, `总表产品第 ${index + 1} 行缺少 Units per Carton`),
    cartonCbm: p4Positive(row.carton_cbm, `总表产品第 ${index + 1} 行 Carton CBM 必须大于 0`),
    colorBoxSizeCm: p4RequiredText(row.color_box_size_cm, `总表产品第 ${index + 1} 行缺少 Color Box Size`),
    cartonSizeCm: p4RequiredText(row.carton_size_cm, `总表产品第 ${index + 1} 行缺少 Carton Size`),
    productionMoq: p4RequiredText(row.production_moq, `总表产品第 ${index + 1} 行缺少 Production MOQ`),
    price40hHkd: p4Positive(row.price_40h_hkd, `总表产品第 ${index + 1} 行 40' 报价必须大于 0`),
    price20hHkd: p4Positive(row.price_20h_hkd, `总表产品第 ${index + 1} 行 20' 报价必须大于 0`),
    priceLclHkd: p4Positive(row.price_lcl_hkd, `总表产品第 ${index + 1} 行 LCL 报价必须大于 0`),
  }))

  const remarkLines = p4Rows(dickie.remark_lines).map<DickyP4RemarkLine>((row, index) => ({
    lineNo: Math.max(0, Math.trunc(p4Number(row.line_no))),
    textEn: p4RequiredText(row.text_en, `英文备注第 ${index + 1} 行为空`, true),
  }))
  const requiredRemarkNumbers = [1, 2, 3, 4, 5, 6, 7, 8]
  if (remarkLines.length > 12 || !remarkLines.some((row) => row.lineNo === 0) || requiredRemarkNumbers.some((lineNo) => !remarkLines.some((row) => row.lineNo === lineNo))) {
    throw new Error('Dickie 直转被阻断：英文备注必须完整包含 1–8 项及一项编号 0 的汇率/调价条款')
  }

  const rawMaterialPrices = p4Rows(dickie.material_prices_hkd)
  if (rawMaterialPrices.length !== 4) throw new Error('Dickie 直转被阻断：Plastic Quotation 必须完整填写 4 项材料价')
  const materialPricesHkd = rawMaterialPrices.map<DickyP4MaterialPrice>((row, index) => ({
    material: p4RequiredText(row.material, `材料价第 ${index + 1} 行缺少 Type`),
    priceHkdLb: p4Positive(row.price_hkd_lb, `材料价第 ${index + 1} 行 Cost 必须大于 0`),
  }))

  const rawMolds = p4Rows(artifact.sections.engineering.payload.molds)
  if (rawMolds.length === 0 || rawMolds.length > 38) throw new Error('Dickie 直转被阻断：工程模具必须为 1–38 行')
  const moldRows = rawMolds.map<DickyP4MoldRow>((row, index) => ({
    projectNameEn: p4RequiredText(row.dickie_project_name_en, `工程模具第 ${index + 1} 行缺少 Project Name 英文字款`, true),
    moldNo: p4RequiredText(row.dickie_mold_no, `工程模具第 ${index + 1} 行缺少 Mold #`),
    partsEn: p4RequiredText(row.dickie_parts_en, `工程模具第 ${index + 1} 行缺少 Parts 英文字款`, true),
    resin: p4RequiredText(row.dickie_resin, `工程模具第 ${index + 1} 行缺少 Resin`),
    moldSize: p4RequiredText(row.dickie_mold_size, `工程模具第 ${index + 1} 行缺少 Mold Size`),
    moldMaterial: p4RequiredText(row.dickie_mold_material, `工程模具第 ${index + 1} 行缺少 Mold Material`),
    cavities: p4Positive(row.dickie_cavities, `工程模具第 ${index + 1} 行 Cav. 必须大于 0`),
    partsPerShot: p4Positive(row.dickie_parts_per_shot, `工程模具第 ${index + 1} 行 Up 必须大于 0`),
    moldCostHkd: p4Positive(row.dickie_mold_cost_hkd, `工程模具第 ${index + 1} 行 Mold Cost 必须大于 0`),
    remarkEn: p4Text(row.dickie_remark_en) ? p4RequiredText(row.dickie_remark_en, `工程模具第 ${index + 1} 行 Remark`, true) : '',
  }))
  const moldNumbers = moldRows.map((row) => row.moldNo.toLowerCase())
  if (new Set(moldNumbers).size !== moldNumbers.length) throw new Error('Dickie 直转被阻断：Mold # 不得重复')

  const p4QuoteData: DickyP4QuoteData = {
    clientName,
    quoteDate: quoteDateText,
    attention,
    revision,
    fromName,
    projectNameEn,
    firstShotTime,
    finishTime,
    productRows,
    remarkLines,
    materialPricesHkd,
    moldRows,
  }
  const details = [
    ...productRows.map((row, index) => detailRow('dicky-p4', 'Quotation', `${row.lineNo}-${index + 1}`, row.itemTextEn, 0, row.price40hHkd)),
    ...moldRows.map((row) => detailRow('dicky-p4', 'Quotation', row.moldNo, row.partsEn, 0, row.moldCostHkd)),
  ]

  return {
    sourceFileName,
    sourceBuffer: new ArrayBuffer(0),
    summarySheetName: SUMMARY_SHEET_NAME,
    clientName,
    quoteDate,
    sheets: [{
      id: 'dicky-p4',
      name: 'Quotation',
      sourceFileName,
      rowCount: details.length,
      totalInternalHkd: 0,
      totalCustomerHkd: round(details.reduce((sum, row) => sum + row.customerPriceHkd, 0)),
      details,
    }],
    p4QuoteData,
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
  if (directValue && !/^#(?:REF!|NAME\?|VALUE!|N\/A|DIV\/0!|NUM!|NULL!)$/i.test(directValue)) {
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
  const style = patch.forceStyleRef && Number.isFinite(sourceStyle)
    ? sourceStyle
    : Number.isFinite(existingStyle) ? existingStyle : Number.isFinite(sourceStyle) ? sourceStyle : patch.style
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

function findStandardRemarkTextStyleRef(
  cellMap: Map<string, DickyWorksheetCell>,
  sharedStrings: string[],
  workbookCells: Map<string, Map<string, DickyWorksheetCell>>,
  remarkRow: number,
  remarkEndRow: number,
) {
  for (let rowNumber = remarkRow + 4; rowNumber <= remarkEndRow; rowNumber += 1) {
    const itemNumber = resolveCellText(cellMap.get(`A${rowNumber}`), sharedStrings, workbookCells)
    const text = resolveCellText(cellMap.get(`B${rowNumber}`), sharedStrings, workbookCells)

    if (/^\d+$/.test(itemNumber) && text) {
      return `B${rowNumber}`
    }
  }

  return ''
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
  const patchText = (ref: string, value: XlsxCellValue, styleRef?: string, forceStyleRef = false) => patches.push({
    ref,
    value: normalizeDickieCellValue(value),
    styleRef,
    forceStyleRef,
  })
  const textAt = (ref: string) => resolveCellText(summaryCells.get(ref), sharedStrings, workbookCells)
  const ref = (columnName: string, rowNumber: number) => `${columnName}${rowNumber}`
  const remarkRow = findRowByColumnText(summaryCells, sharedStrings, 'A', 12, /Remark|备注/i)

  ;['C7', 'K7', 'C8', 'K8', 'C9'].forEach((cellRef) => copy(cellRef))

  const productEndRow = remarkRow ? Math.min(19, remarkRow - 1) : 19
  for (let rowNumber = 12; rowNumber <= productEndRow; rowNumber += 1) {
    ;['A', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J'].forEach((columnName) => copy(ref(columnName, rowNumber)))
    patchText(ref('B', rowNumber), translateProductName(textAt(ref('B', rowNumber))))
  }

  if (remarkRow) {
    const nextQuotationRow = findRowByColumnText(summaryCells, sharedStrings, 'A', remarkRow + 1, /^Quotation/i)
    const remarkEndRow = nextQuotationRow ? nextQuotationRow - 1 : maxRowInCells(summaryCells)
    const standardRemarkTextStyleRef = findStandardRemarkTextStyleRef(
      summaryCells,
      sharedStrings,
      workbookCells,
      remarkRow,
      remarkEndRow,
    )

    for (let rowNumber = remarkRow + 1; rowNumber <= remarkEndRow; rowNumber += 1) {
      ;['B', 'C', 'E', 'F'].forEach((columnName) => {
        const cellRef = ref(columnName, rowNumber)
        const sourceText = textAt(cellRef)
        const translatedText = translateRemarkText(sourceText)
        if (translatedText && translatedText !== sourceText) {
          const shouldUseStandardRemarkStyle = columnName === 'B' && Boolean(standardRemarkTextStyleRef)
          patchText(
            cellRef,
            translatedText,
            shouldUseStandardRemarkStyle ? standardRemarkTextStyleRef : undefined,
            shouldUseStandardRemarkStyle,
          )
        }
      })
    }
  }

  const sourceQuotationRow = findRowByColumnText(summaryCells, sharedStrings, 'A', 35, /^Quotation/i)
  if (!sourceQuotationRow) {
    return patches
  }

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

function dateToExcelSerial(dateText: string) {
  const [year, month, day] = dateText.split('-').map(Number)
  return Math.round((Date.UTC(year, month - 1, day) - Date.UTC(1899, 11, 30)) / 86_400_000)
}

function toArrayBuffer(bytes: Uint8Array) {
  return new Uint8Array(bytes).buffer
}

function buildDickyP4SourceWorkbook(data: DickyP4QuoteData, templateBuffer: ArrayBuffer | Uint8Array) {
  const bytes = templateBuffer instanceof Uint8Array ? templateBuffer : new Uint8Array(templateBuffer)
  const zip = unzipSync(bytes)
  const sheets = resolveWorksheetRefs(zip)
  const summarySheet = findSummarySheetRef(sheets)
  const summaryXml = getZipText(zip, summarySheet.path)
  if (!summaryXml) throw new Error('Dickie 报客模板缺少“总表”内容')

  const patches: DickyCellPatch[] = []
  const patch = (ref: string, value: XlsxCellValue, formula?: string) => patches.push({ ref, value, formula })
  const clearRange = (columns: string[], startRow: number, endRow: number) => {
    for (let rowNumber = startRow; rowNumber <= endRow; rowNumber += 1) {
      columns.forEach((columnName) => patch(`${columnName}${rowNumber}`, null))
    }
  }
  const quoteDateSerial = dateToExcelSerial(data.quoteDate)

  patch('C7', data.clientName)
  patch('K7', quoteDateSerial)
  patch('C8', data.attention)
  patch('K8', data.revision)
  patch('C9', data.fromName)

  clearRange(['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J'], 12, 19)
  data.productRows.forEach((row, index) => {
    const rowNumber = 12 + index
    patch(`A${rowNumber}`, row.lineNo)
    patch(`B${rowNumber}`, row.itemTextEn)
    patch(`C${rowNumber}`, row.unitsPerCarton)
    patch(`D${rowNumber}`, row.cartonCbm)
    patch(`E${rowNumber}`, row.colorBoxSizeCm)
    patch(`F${rowNumber}`, row.cartonSizeCm)
    patch(`G${rowNumber}`, row.productionMoq)
    patch(`H${rowNumber}`, row.price40hHkd)
    patch(`I${rowNumber}`, row.price20hHkd)
    patch(`J${rowNumber}`, row.priceLclHkd)
  })

  clearRange(['A', 'B', 'C', 'D', 'E', 'F'], 22, 34)
  const remarksByNumber = new Map(data.remarkLines.map((row) => [row.lineNo, row.textEn]))
  for (let lineNo = 1; lineNo <= 6; lineNo += 1) {
    patch(`A${21 + lineNo}`, lineNo)
    patch(`B${21 + lineNo}`, remarksByNumber.get(lineNo) ?? '')
  }
  patch('B28', 'Type')
  patch('C28', 'Cost')
  patch('E28', 'Type')
  patch('F28', 'Cost')
  data.materialPricesHkd.forEach((row, index) => {
    const rowNumber = 29 + Math.floor(index / 2)
    const typeColumn = index % 2 === 0 ? 'B' : 'E'
    const costColumn = index % 2 === 0 ? 'C' : 'F'
    patch(`${typeColumn}${rowNumber}`, row.material)
    patch(`${costColumn}${rowNumber}`, row.priceHkdLb)
  })
  patch('B31', remarksByNumber.get(0) ?? '')
  patch('A32', 7)
  patch('B32', remarksByNumber.get(7) ?? '')
  patch('A33', 8)
  patch('B33', remarksByNumber.get(8) ?? '')

  patch('C42', data.clientName)
  patch('K42', quoteDateSerial)
  patch('C43', data.attention)
  patch('K43', data.revision)
  patch('C44', data.fromName)
  patch('C46', data.projectNameEn)

  clearRange(['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K'], 48, 85)
  data.moldRows.forEach((row, index) => {
    const rowNumber = 48 + index
    patch(`A${rowNumber}`, row.projectNameEn)
    patch(`B${rowNumber}`, row.moldNo)
    patch(`C${rowNumber}`, row.partsEn)
    patch(`E${rowNumber}`, row.resin)
    patch(`F${rowNumber}`, row.moldSize)
    patch(`G${rowNumber}`, row.moldMaterial)
    patch(`H${rowNumber}`, row.cavities)
    patch(`I${rowNumber}`, row.partsPerShot)
    patch(`J${rowNumber}`, row.moldCostHkd)
    patch(`K${rowNumber}`, row.remarkEn)
  })
  const totalMoldCost = round(data.moldRows.reduce((total, row) => total + row.moldCostHkd, 0))
  patch('B86', 'TOTAL:HK$')
  patch('J86', totalMoldCost, 'SUM(J48:J85)')
  patch('J87', data.firstShotTime)
  patch('J88', data.finishTime)

  zip[summarySheet.path] = strToU8(refreshDimension(applyCellPatches(summaryXml, patches)))
  if (zip['xl/workbook.xml']) {
    zip['xl/workbook.xml'] = strToU8(forceWorkbookRecalculation(getZipText(zip, 'xl/workbook.xml')))
  }
  delete zip['xl/calcChain.xml']

  return toArrayBuffer(zipSync(zip, { level: 0 }))
}

function createDickyCustomerQuoteFromSource(
  sourceBuffer: ArrayBuffer | Uint8Array,
  fastP4 = false,
) {
  const zip = unzipSync(new Uint8Array(sourceBuffer))
  const sheets = resolveWorksheetRefs(zip)
  const summarySheet = findSummarySheetRef(sheets)
  const quotationSheet = findQuotationSheet(sheets) ?? addQuotationWorksheet(zip, sheets, summarySheet)

  copyWorksheetContent(zip, summarySheet.path, quotationSheet.path)

  const sharedStrings = readSharedStrings(zip)
  const summaryXml = getZipText(zip, summarySheet.path)
  const quotationXml = getZipText(zip, quotationSheet.path)
  const workbookCells = fastP4
    ? new Map([
        [summarySheet.name, createCellMap(summaryXml)],
        [quotationSheet.name, createCellMap(quotationXml)],
      ])
    : createWorkbookCellMaps(zip, sheets)

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

  return zipSync(zip, { level: 0 })
}

export function createDickyCustomerQuoteWorkbook(
  result: DickyConversionResult,
  templateBuffer?: ArrayBuffer | Uint8Array,
) {
  if (result.p4QuoteData) {
    if (!templateBuffer) throw new Error('Dickie P4 直转缺少报客模板')
    return createDickyCustomerQuoteFromSource(
      buildDickyP4SourceWorkbook(result.p4QuoteData, templateBuffer),
      true,
    )
  }

  return createDickyCustomerQuoteFromSource(result.sourceBuffer)
}

export function buildDickyCustomerQuoteFileName(result: DickyConversionResult) {
  if (result.p4QuoteData) {
    const baseName = result.sourceFileName
      .trim()
      .replace(/\.xlsx$/i, '')
      .replace(/-P4-v2$/i, '')

    return `${baseName || 'Dickie'}-Customer-Quotation.xlsx`
  }

  return result.sourceFileName || 'Dickie.xlsx'
}

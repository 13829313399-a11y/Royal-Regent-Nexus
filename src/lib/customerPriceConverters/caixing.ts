import { pricingRate, assertPricingCustomer, type CustomerPricingSettings } from './pricingSettings'
import {
  XLSX_STYLE,
  createXlsxWorkbook,
  excelDateSerial,
  parseXlsxWorkbook,
  type XlsxCellInput,
  type XlsxCellValue,
  type XlsxOutputSheet,
} from './xlsxLite'
import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'
import type { P4InternalQuoteArtifact, P4SectionCode } from './p4Artifact'
import { extractYinhuiProductImage, type YinhuiProductImage } from './yinhuiTemplate'

export type CaixingProductType = 'plastic' | 'plush'

type DetailCompareStatus = '上调' | '下调' | '持平'

interface CaixingCartonProfile {
  length: number
  width: number
  height: number
  cube: number
  cbm: number
  pcsPerCarton: number
  cartonPrice: number
}

interface CaixingQuoteMetadata {
  itemNo: string
  itemName: string
  quoteDate: Date
  revision?: string
  markupRateOverride?: number
  sourceSheetName: string
  productType: CaixingProductType
  productTypeName: string
  carton: CaixingCartonProfile
}

interface CaixingInjectionRow {
  lineNo: string
  name: string
  material: string
  displayMaterial: string
  weightG: number
  machineTons: number
  setsPerShot: number
  partsPerShot: number
  targetYield: number
  moldingCostHkd: number
  materialCostHkd: number
  materialUnitPriceHkdKg?: number
  machineHourlyHkd?: number
  cycleSeconds: number
  moldCostHkd: number
  customerMoldCostHkd: number
  processType?: 'IN' | 'BL' | 'CP' | 'DC' | 'RC'
  toolNo?: string
  skuNo?: string
  cavities?: number
  up?: number
  materialCode?: number
  color?: string
}

export type CaixingCustomerCostGroup = 'special' | 'electronic' | 'purchase' | 'packing' | 'carton' | 'fabric' | 'spraying' | 'tampo' | 'assembly' | 'packout' | 'rooting' | 'sewing' | 'special_offer'

interface CaixingCostRow {
  taxTag: string
  category: string
  description: string
  baseCostHkd: number
  customerCostHkd: number
  customerGroup?: CaixingCustomerCostGroup
  costKind?: 'material' | 'labor'
}

interface CaixingMoldingProcessRow {
  processCode: 'BL' | 'RC'
  description: string
  costHkd: number
}

interface CaixingSummary {
  markupRate: number
  material: {
    plasticParts: number
    specialMaterial: number
    electronicMaterial: number
    purchasePart: number
    packagingMaterial: number
    fabric: number
    total: number
  }
  process: {
    moldingCasting: number
    spraying: number
    tampo: number
    assemblyLabor: number
    packoutLabor: number
    rootingHair: number
    sewingHandfinish: number
    specialOffer: number
    total: number
  }
  exFactoryHkd: number
  exFactoryUsd: number
  domesticTransportationHkd: number
  fobTransportationHkd: number
}

interface CaixingQuoteData {
  pricing?: CustomerPricingSettings
  image?: YinhuiProductImage
  metadata: CaixingQuoteMetadata
  injectionRows: CaixingInjectionRow[]
  costRows: CaixingCostRow[]
  summary: CaixingSummary
}

export interface CaixingQuoteDetailRow {
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

export interface CaixingConvertedSheet {
  id: string
  name: string
  productName: string
  sourceFileName: string
  rowCount: number
  totalInternalHkd: number
  totalCustomerHkd: number
  details: CaixingQuoteDetailRow[]
  quoteData: CaixingQuoteData
}

export interface CaixingConversionResult {
  pricing?: CustomerPricingSettings
  warnings?: string[]
  sourceFileName: string
  productType: CaixingProductType
  sheets: CaixingConvertedSheet[]
}

const PRODUCT_TYPE_LABELS: Record<CaixingProductType, string> = {
  plastic: '塑胶',
  plush: '毛绒',
}

export const CAIXING_PLASTIC_CUSTOMER_QUOTE_TEMPLATE_URL = '/templates/caixing-plastic-customer-quote-template.bin'
export const CAIXING_PLUSH_CUSTOMER_QUOTE_TEMPLATE_URL = '/templates/caixing-plush-customer-quote-template.bin'

const MATERIALS: Record<string, { display: string, price: number }> = {
  ABS: { display: 'ABS', price: 16.18 },
  PVC: { display: 'PVC', price: 15.28 },
  PP: { display: 'PP', price: 14.6 },
  POM: { display: 'POM', price: 40.44 },
  'C-ABS': { display: 'C-ABS', price: 30.33 },
  'C-PP': { display: 'C-PP', price: 15.73 },
  HIPS: { display: 'HIPS', price: 14.6 },
  PE: { display: 'PE', price: 14.15 },
  TPR: { display: 'TPR', price: 31 },
}

const CAIXING_PLASTIC_SCRAP_RATE = 0.02

function caixingOptionalRate(pricing: CustomerPricingSettings | undefined, key: string, legacy: number) {
  return pricing?.rates[key] === undefined ? legacy : pricingRate(pricing, key, legacy)
}

function caixingScrapRate(pricing: CustomerPricingSettings | undefined, productType: CaixingProductType, group: CaixingCustomerCostGroup, costKind?: CaixingCostRow['costKind']) {
  if (group === 'fabric') return costKind === 'labor'
    ? caixingOptionalRate(pricing, 'fabric_labor_scrap_rate', 0)
    : caixingOptionalRate(pricing, 'fabric_material_scrap_rate', 0.02)
  if (group === 'special') return caixingOptionalRate(pricing, 'special_material_scrap_rate', 0.02)
  if (group === 'electronic') return caixingOptionalRate(pricing, 'electronic_scrap_rate', 0.02)
  if (group === 'purchase' || group === 'packing' || group === 'carton') return productType === 'plastic'
    ? pricingRate(pricing, 'plastic_scrap_rate', CAIXING_PLASTIC_SCRAP_RATE)
    : caixingOptionalRate(pricing, 'plush_scrap_rate', 0.02)
  return 0
}

function caixingMarkupRate(pricing: CustomerPricingSettings | undefined, productType: CaixingProductType, group: 'special' | 'electronic' | 'standard', override?: number) {
  const standard = override ?? (productType === 'plush' ? pricingRate(pricing, 'plush_markup_rate', 0.17) : pricingRate(pricing, 'plastic_markup_rate', 0.16))
  if (productType !== 'plush') return standard
  if (group === 'special') return caixingOptionalRate(pricing, 'plush_special_markup_rate', 0)
  if (group === 'electronic') return caixingOptionalRate(pricing, 'plush_electronic_markup_rate', 0)
  return standard
}

function caixingMoqText(pricing?: CustomerPricingSettings) {
  const quantity = caixingOptionalRate(pricing, 'minimum_order_qty', 3000)
  if (!Number.isInteger(quantity) || quantity <= 0) throw new Error('彩星最低订量必须为正整数')
  return `Production MOQ ${quantity % 1000 === 0 ? `${quantity / 1000}K` : quantity} / style`
}

const CAIXING_DISTINCT_SAMPLE_LAYOUT_ITEMS = new Set(['68972', '68974', '40665', '57841', '40637'])

function caixingLayoutWarning(itemNo: string) {
  return CAIXING_DISTINCT_SAMPLE_LAYOUT_ITEMS.has(itemNo)
    ? [`${itemNo} 的报客样表具有独立行位与说明区；当前仅按彩星塑胶/车衣基准模板生成，正式报客前须核对并补齐该款原版版式。`]
    : []
}

function toText(value: XlsxCellValue) {
  return String(value ?? '').trim()
}

function toNumber(value: XlsxCellValue) {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : 0
  }

  const normalized = String(value ?? '')
    .replace(/[$,¥￥HKDUSD]/gi, '')
    .replace(/%$/, '')
    .trim()

  if (!normalized) {
    return 0
  }

  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : 0
}

function round(value: number, precision = 4) {
  if (!Number.isFinite(value)) {
    return 0
  }

  const factor = 10 ** precision
  return Math.round(value * factor) / factor
}

function roundMoney(value: number) {
  return round(value, 4)
}

function sumBy<T>(items: T[], getter: (item: T) => number) {
  return round(items.reduce((sum, item) => sum + getter(item), 0), 6)
}

function costRowAmount(row: CaixingCostRow) {
  return row.customerCostHkd || row.baseCostHkd
}

function sanitizeFileNamePart(value: string) {
  return value.replace(/[\\/:*?"<>|]/g, '_').replace(/\s+/g, ' ').trim()
}

function formatFileDate(date: Date) {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}${month}${day}`
}

function parseDateFromSource(sourceFileName: string) {
  const normalized = sourceFileName.replace(/[年月日._－—]/g, '-')
  const separated = normalized.match(/(20\d{2})-(\d{1,2})-(\d{1,2})/)
  if (separated) {
    return new Date(Number(separated[1]), Number(separated[2]) - 1, Number(separated[3]))
  }

  const compact = sourceFileName.match(/(20\d{2})(\d{2})(\d{2})/)
  if (compact) {
    return new Date(Number(compact[1]), Number(compact[2]) - 1, Number(compact[3]))
  }

  return new Date()
}

function normalizeMaterialName(material: string) {
  const cleaned = material
    .replace(/料型|料/g, '')
    .replace(/[（）()].*?[（）()]/g, '')
    .replace(/\s+/g, '')
    .toUpperCase()

  if (cleaned.includes('C-ABS') || cleaned.includes('透明ABS')) return 'C-ABS'
  if (cleaned.includes('C-PP') || cleaned.includes('PP透明') || cleaned.includes('透明PP')) return 'C-PP'
  if (cleaned.includes('ABS')) return 'ABS'
  if (cleaned.includes('PVC')) return 'PVC'
  if (cleaned.includes('POM')) return 'POM'
  if (cleaned.includes('HIPS')) return 'HIPS'
  if (cleaned.includes('TPR')) return 'TPR'
  if (cleaned.includes('PP')) return 'PP'
  if (cleaned.includes('PE')) return 'PE'

  return cleaned || material.trim()
}

function materialDisplay(material: string) {
  return MATERIALS[material]?.display ?? material
}

function materialUnitPrice(material: string) {
  return MATERIALS[material]?.price ?? 0
}

function findHeaderRow(rows: XlsxCellValue[][]) {
  return rows.findIndex((row) => toText(row?.[2]) === '名称' && toText(row?.[3]).includes('料型'))
}

function materialPriceReferenceWarnings(sheet: ReturnType<typeof parseXlsxWorkbook>['sheets'][number]) {
  const headerRow = findHeaderRow(sheet.rows)
  if (headerRow < 0 || !sheet.cellFormulas) return []
  const warnings: string[] = []
  for (const [cellRef, expression] of Object.entries(sheet.cellFormulas)) {
    const rowNumber = Number(cellRef.match(/\d+/)?.[0] ?? 0)
    if (!/^F\d+$/.test(cellRef) || rowNumber <= headerRow + 1) continue
    const material = normalizeMaterialName(toText(sheet.rows[rowNumber - 1]?.[3]))
    if (!material || !/^(?:C-ABS|C-PP|ABS|PVC|POM|HIPS|TPR|PP|PE|LDPE|PC|PA)$/i.test(material)) continue
    const referenced = expression.trim().match(/^\$?([A-Z]+)\$?(\d+)\s*\/\s*454(?:\b|$)/i)
    if (!referenced) continue
    const column = templateColumnNameToIndex(referenced[1].toUpperCase())
    const priceRow = Number(referenced[2])
    if (priceRow < 2 || priceRow > headerRow) continue
    const sourceLabel = toText(sheet.rows[priceRow - 2]?.[column])
    const sourceMaterial = normalizeMaterialName(sourceLabel)
    if (sourceMaterial && sourceMaterial !== material && /^(?:C-ABS|C-PP|ABS|PVC|POM|HIPS|TPR|PP|PE|LDPE|PC|PA)$/i.test(sourceMaterial)) {
      warnings.push(`内部明细第 ${rowNumber} 行料型为 ${material}，料价公式却引用 ${referenced[1]}${priceRow}（${sourceMaterial}）；请核对原表。`)
    }
  }
  return warnings
}

function findTitle(rows: XlsxCellValue[][], sheetName: string, sourceFileName: string) {
  const sourceTitle = sourceFileName.replace(/\.[^.]+$/, '')
  if (/\d{5,}/.test(sourceTitle) && sourceTitle.includes('报价')) {
    return sourceTitle
  }

  for (let rowIndex = 0; rowIndex < Math.min(rows.length, 15); rowIndex += 1) {
    const matched = (rows[rowIndex] ?? [])
      .map(toText)
      .find((cell) => /\d{5,}/.test(cell) && cell.includes('报价'))

    if (matched) {
      return matched
    }
  }

  for (let rowIndex = 0; rowIndex < Math.min(rows.length, 15); rowIndex += 1) {
    const matched = (rows[rowIndex] ?? [])
      .map(toText)
      .find((cell) => /\d{5,}/.test(cell) && (cell.includes('报价') || cell.length < 80))

    if (matched) {
      return matched
    }
  }

  return sheetName || sourceFileName.replace(/\.[^.]+$/, '')
}

function cleanItemName(title: string, itemNo: string, fallback: string) {
  const cleaned = title
    .replace(itemNo, '')
    .replace(/报价.*$/, '')
    .replace(/[（(].*?[）)]/g, '')
    .replace(/[－—_-]+$/g, '')
    .trim()

  return cleaned || fallback.replace(/\.[^.]+$/, '').replace(itemNo, '').trim() || itemNo
}

function parseMetadata(
  rows: XlsxCellValue[][],
  sheetName: string,
  sourceFileName: string,
  productType: CaixingProductType,
): CaixingQuoteMetadata {
  const title = findTitle(rows, sheetName, sourceFileName)
  const itemNo = title.match(/\d{5,}/)?.[0]
    ?? sourceFileName.match(/\d{5,}/)?.[0]
    ?? 'ITEM'

  const carton: CaixingCartonProfile = {
    length: 0,
    width: 0,
    height: 0,
    cube: 0,
    cbm: 0,
    pcsPerCarton: 0,
    cartonPrice: 0,
  }

  rows.forEach((row) => {
    row.forEach((cell, columnIndex) => {
      const text = toText(cell)
      if (text.includes('外箱外尺码')) {
        carton.length = toNumber(row[columnIndex + 1])
        carton.width = toNumber(row[columnIndex + 2])
        carton.height = toNumber(row[columnIndex + 3])
      }
      if (text.includes('CU.FT')) {
        carton.cube = toNumber(row[columnIndex + 1])
      }
      if (text.includes('CBM')) {
        carton.cbm = toNumber(row[columnIndex + 1])
      }
      if (text.includes('纸箱价')) {
        carton.cartonPrice = toNumber(row[columnIndex + 1])
        carton.pcsPerCarton = toNumber(row[columnIndex + 2])
      }
    })
  })

  return {
    itemNo,
    itemName: cleanItemName(title, itemNo, sourceFileName),
    quoteDate: parseDateFromSource(sourceFileName),
    sourceSheetName: sheetName,
    productType,
    productTypeName: PRODUCT_TYPE_LABELS[productType],
    carton,
  }
}

function parseInjectionRows(rows: XlsxCellValue[][], headerRow: number) {
  const totalRow = rows.findIndex((row, index) => index > headerRow && toText(row?.[9]).includes('合计'))
  const endRow = totalRow >= 0 ? totalRow : rows.length
  const injectionRows: CaixingInjectionRow[] = []
  let activeLineNo = ''

  for (let rowIndex = headerRow + 1; rowIndex < endRow; rowIndex += 1) {
    const row = rows[rowIndex] ?? []
    const name = toText(row[2])
    if (!name) {
      continue
    }

    const lineNo = toText(row[1])
    if (lineNo) {
      activeLineNo = lineNo
    }

    const rawMaterial = toText(row[3])
    const material = normalizeMaterialName(rawMaterial)
    const weightG = toNumber(row[4])
    const materialCostHkd = toNumber(row[11])
    const moldingCostHkd = toNumber(row[10])

    injectionRows.push({
      lineNo: lineNo || activeLineNo || String(injectionRows.length + 1),
      name,
      material: rawMaterial ? material : '',
      displayMaterial: rawMaterial ? materialDisplay(material) : '',
      weightG,
      machineTons: toNumber(row[6]),
      setsPerShot: toNumber(row[7]) || 1,
      partsPerShot: toNumber(row[8]) || 1,
      targetYield: toNumber(row[9]),
      moldingCostHkd,
      materialCostHkd,
      cycleSeconds: toNumber(row[13]),
      moldCostHkd: toNumber(row[14]),
      customerMoldCostHkd: toNumber(row[15]),
    })
  }

  const total = totalRow >= 0
    ? {
        rowIndex: totalRow,
        weightG: toNumber(rows[totalRow]?.[4]),
        moldingCostHkd: toNumber(rows[totalRow]?.[10]),
        materialCostHkd: toNumber(rows[totalRow]?.[11]),
        customerMoldCostHkd: toNumber(rows[totalRow]?.[15]),
      }
    : null

  return { injectionRows, total }
}

function parseCostRows(rows: XlsxCellValue[][], startRow: number) {
  const costRows: CaixingCostRow[] = []

  for (let rowIndex = startRow; rowIndex < rows.length; rowIndex += 1) {
    const row = rows[rowIndex] ?? []
    const category = toText(row[1])
    const description = toText(row[2])

    if (!category || !description) {
      continue
    }

    if (/目标价|报客价|差价|旺季|淡季|毛利|利润|总成本|人民币外购|码数|找数|汇率/.test(category + description)) {
      continue
    }

    const baseCostHkd = toNumber(row[3]) || toNumber(row[4]) || toNumber(row[5]) || toNumber(row[6])
    const customerCostHkd = toNumber(row[6]) || baseCostHkd
    if (!baseCostHkd && !customerCostHkd) {
      continue
    }

    costRows.push({
      taxTag: toText(row[0]),
      category,
      description,
      baseCostHkd: roundMoney(baseCostHkd),
      customerCostHkd: roundMoney(customerCostHkd),
    })
  }

  return costRows
}

function effectiveCustomerGroup(row: CaixingCostRow): CaixingCustomerCostGroup | null {
  const haystack = `${row.category} ${row.description}`

  if (/\bIC\b/i.test(haystack)) {
    return 'special'
  }
  if (/电池|battery/i.test(haystack)) {
    return 'purchase'
  }
  if (/利宝|说明书|锡线|胶针|胶纸|instruction\s*sheet|label/i.test(haystack)) {
    return 'packing'
  }
  if (/油漆|喷油/i.test(haystack)) {
    return 'tampo'
  }
  if (row.customerGroup) {
    return row.customerGroup
  }
  if (/外箱|纸箱|carton/i.test(haystack)) {
    return 'carton'
  }
  if (/彩盒|内咭|内卡|吸塑|blister|polybag|胶袋/i.test(haystack)) {
    return 'packing'
  }
  if (/电子|electronic/i.test(haystack)) {
    return 'electronic'
  }
  if (/车衣|fabric/i.test(haystack)) {
    return 'fabric'
  }
  if (/包装人工|packout/i.test(haystack)) {
    return 'packout'
  }
  if (/装配工|assembly/i.test(haystack)) {
    return 'assembly'
  }
  if (/车发|rooting/i.test(haystack)) {
    return 'rooting'
  }
  if (/车缝|手缝|sewing|handfinish/i.test(haystack)) {
    return 'sewing'
  }
  if (/special\s*material/i.test(haystack)) {
    return 'special'
  }
  if (/五金|其它外购|其他外购|马达|purchase/i.test(haystack)) {
    return 'purchase'
  }

  return null
}

function filterCustomerGroup(costRows: CaixingCostRow[], group: CaixingCustomerCostGroup) {
  return costRows.filter((row) => effectiveCustomerGroup(row) === group)
}

function sumCustomerGroup(costRows: CaixingCostRow[], group: CaixingCustomerCostGroup) {
  return sumBy(filterCustomerGroup(costRows, group), costRowAmount)
}

function isCartonCostRow(row: CaixingCostRow) {
  return /外箱|纸箱|Carton/i.test(`${row.category} ${row.description}`)
}

function getMoldingProcessRows(costRows: CaixingCostRow[]): CaixingMoldingProcessRow[] {
  const processRows: CaixingMoldingProcessRow[] = []

  costRows.forEach((row) => {
    const haystack = `${row.category} ${row.description}`
    const costHkd = costRowAmount(row)

    if (!costHkd) {
      return
    }

    if (haystack.includes('吹气')) {
      processRows.push({ processCode: 'BL', description: row.description || '吹气', costHkd })
      return
    }

    if (haystack.includes('搪胶')) {
      processRows.push({ processCode: 'RC', description: row.description || '搪胶', costHkd })
    }
  })

  return processRows
}

function templateMoldingProcessRows(data: CaixingQuoteData) {
  return data.injectionRows.some((row) => row.processType) ? [] : getMoldingProcessRows(data.costRows)
}

function templateToolPlanRowCount(data: CaixingQuoteData) {
  return data.injectionRows.length + templateMoldingProcessRows(data).length
}

function buildSummary(
  productType: CaixingProductType,
  injectionRows: CaixingInjectionRow[],
  injectionTotal: ReturnType<typeof parseInjectionRows>['total'],
  costRows: CaixingCostRow[],
  carton: CaixingCartonProfile,
  sprayingDetailTotal?: number | null,
  pricing?: CustomerPricingSettings,
  markupRateOverride?: number,
): CaixingSummary {
  const injectionMaterial = injectionTotal?.materialCostHkd || sumBy(injectionRows, (row) => row.materialCostHkd)
  const hasExplicitToolProcesses = injectionRows.some((row) => row.processType)
  const legacyMoldingProcessRows = hasExplicitToolProcesses ? [] : getMoldingProcessRows(costRows)
  const injectionMolding = injectionTotal?.moldingCostHkd
    || sumBy(injectionRows.filter((row) => row.processType !== 'BL'), (row) => row.moldingCostHkd)
  const blowMolding = sumBy(
    injectionRows.filter((row) => row.processType === 'BL'),
    (row) => row.moldingCostHkd,
  ) + sumBy(
    legacyMoldingProcessRows.filter((row) => row.processCode === 'BL'),
    (row) => row.costHkd,
  )
  const legacyNonBlowMolding = sumBy(
    legacyMoldingProcessRows.filter((row) => row.processCode !== 'BL'),
    (row) => row.costHkd,
  )
  const pricedGroup = (group: CaixingCustomerCostGroup) => sumBy(filterCustomerGroup(costRows, group), (row) =>
    costRowAmount(row) * (1 + caixingScrapRate(pricing, productType, group, row.costKind)))
  const electronicMaterial = roundMoney(pricedGroup('electronic'))
  const packingMultiplier = 1 + caixingScrapRate(pricing, productType, 'packing')
  const packagingMaterial = roundMoney(
    pricedGroup('packing')
    + (carton.cartonPrice && carton.pcsPerCarton
      ? carton.cartonPrice / carton.pcsPerCarton * packingMultiplier
      : 0),
  )
  const fabric = roundMoney(pricedGroup('fabric'))
  const purchasePart = roundMoney(pricedGroup('purchase'))
  const specialMaterial = roundMoney(pricedGroup('special') + (productType === 'plush'
    ? sumBy(
        costRows.filter((row) => !row.customerGroup && /搪胶/.test(`${row.category} ${row.description}`)),
        costRowAmount,
      )
    : 0))
  const moldingCasting = roundMoney(injectionMolding + legacyNonBlowMolding)
  const spraying = roundMoney(blowMolding + sumCustomerGroup(costRows, 'spraying'))
  const tampo = sprayingDetailTotal === null || sprayingDetailTotal === undefined
    ? sumCustomerGroup(costRows, 'tampo')
    : roundMoney(sprayingDetailTotal)
  const assemblyLabor = sumCustomerGroup(costRows, 'assembly')
  const packoutLabor = sumCustomerGroup(costRows, 'packout')
  const rootingHair = sumCustomerGroup(costRows, 'rooting')
  const sewingHandfinish = sumCustomerGroup(costRows, 'sewing')
  const specialOffer = sumCustomerGroup(costRows, 'special_offer')
  const markupRate = caixingMarkupRate(pricing, productType, 'standard', markupRateOverride)
  const materialTotal = roundMoney(injectionMaterial + specialMaterial + electronicMaterial + purchasePart + packagingMaterial + fabric)
  const processTotal = roundMoney(moldingCasting + spraying + tampo + assemblyLabor + packoutLabor + rootingHair + sewingHandfinish + specialOffer)
  const exFactoryHkd = round(
    (injectionMaterial + purchasePart + packagingMaterial + fabric + processTotal) * (1 + markupRate)
      + specialMaterial * (1 + caixingMarkupRate(pricing, productType, 'special', markupRateOverride))
      + electronicMaterial * (1 + caixingMarkupRate(pricing, productType, 'electronic', markupRateOverride)),
    2,
  )

  return {
    markupRate,
    material: {
      plasticParts: roundMoney(injectionMaterial),
      specialMaterial: roundMoney(specialMaterial),
      electronicMaterial: roundMoney(electronicMaterial),
      purchasePart: roundMoney(purchasePart),
      packagingMaterial: roundMoney(packagingMaterial),
      fabric: roundMoney(fabric),
      total: materialTotal,
    },
    process: {
      moldingCasting,
      spraying: roundMoney(spraying),
      tampo,
      assemblyLabor: roundMoney(assemblyLabor),
      packoutLabor: roundMoney(packoutLabor),
      rootingHair: roundMoney(rootingHair),
      sewingHandfinish,
      specialOffer,
      total: processTotal,
    },
    exFactoryHkd,
    exFactoryUsd: round(exFactoryHkd / pricingRate(pricing, 'hkd_usd', 7.8), 3),
    domesticTransportationHkd: roundMoney((carton.cube || 0) * pricingRate(pricing, 'domestic_freight_rate', 2.11) / Math.max(carton.pcsPerCarton || 1, 1)),
    fobTransportationHkd: roundMoney((carton.cube || 0) * pricingRate(pricing, 'fob_freight_rate', 5.93) / Math.max(carton.pcsPerCarton || 1, 1)),
  }
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

function detailRow(
  sheetId: string,
  sheetName: string,
  itemNo: string,
  description: string,
  internalPriceHkd: number,
  customerPriceHkd: number,
): CaixingQuoteDetailRow {
  const roundedInternal = round(internalPriceHkd, 4)
  const roundedCustomer = round(customerPriceHkd, 4)
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

function buildDetailRows(sheetId: string, data: CaixingQuoteData) {
  const rows: CaixingQuoteDetailRow[] = []
  const markup = 1 + data.summary.markupRate

  data.injectionRows.forEach((row, index) => {
    const internal = row.materialCostHkd + row.moldingCostHkd
    rows.push(detailRow(
      sheetId,
      'Tool Plan',
      `MOLD-${String(index + 1).padStart(3, '0')}`,
      `${row.name}${row.displayMaterial ? ` / ${row.displayMaterial}` : ''}`,
      internal,
      internal * markup,
    ))
  })

  data.costRows.forEach((row, index) => {
    const group = effectiveCustomerGroup(row)
    const markupGroup = group === 'special' || group === 'electronic' ? group : 'standard'
    const customer = costRowAmount(row)
      * (1 + (group ? caixingScrapRate(data.pricing, data.metadata.productType, group, row.costKind) : 0))
      * (1 + caixingMarkupRate(data.pricing, data.metadata.productType, markupGroup, data.metadata.markupRateOverride))
    rows.push(detailRow(
      sheetId,
      row.category,
      `COST-${String(index + 1).padStart(3, '0')}`,
      row.description,
      row.baseCostHkd,
      customer,
    ))
  })

  rows.push(detailRow(sheetId, 'Summary', 'EXF-001', 'EX-FACTORY COST', data.summary.material.total + data.summary.process.total, data.summary.exFactoryHkd))

  return rows
}

function parseSprayingDetailTotal(rows: XlsxCellValue[][]) {
  const headerRowIndex = rows.findIndex((row) => row.some((cell) => toText(cell) === '油漆') && row.some((cell) => toText(cell) === '人工'))
  if (headerRowIndex < 0) {
    return null
  }

  const headerRow = rows[headerRowIndex] ?? []
  const oilColumnIndex = headerRow.findIndex((cell) => toText(cell) === '油漆')
  const laborColumnIndex = headerRow.findIndex((cell) => toText(cell) === '人工')
  if (oilColumnIndex < 0 || laborColumnIndex < 0) {
    return null
  }

  for (let rowIndex = rows.length - 1; rowIndex > headerRowIndex; rowIndex -= 1) {
    const row = rows[rowIndex] ?? []
    const totalCandidates = [toNumber(row[oilColumnIndex]), toNumber(row[laborColumnIndex])].filter((value) => value > 0)
    const hasOtherValues = row.some((cell, columnIndex) => {
      if (columnIndex === oilColumnIndex || columnIndex === laborColumnIndex) {
        return false
      }

      return toText(cell) !== ''
    })

    if (!hasOtherValues && totalCandidates.length === 1) {
      return roundMoney(totalCandidates[0])
    }
  }

  for (let rowIndex = headerRowIndex + 1; rowIndex < rows.length; rowIndex += 1) {
    const row = rows[rowIndex] ?? []
    if (!row.some((cell) => toText(cell).includes('合计'))) {
      continue
    }

    const total = toNumber(row[oilColumnIndex]) + toNumber(row[laborColumnIndex])
    if (total > 0) {
      return roundMoney(total)
    }
  }

  return null
}

function findSprayingDetailTotal(workbook: ReturnType<typeof parseXlsxWorkbook>) {
  const sprayingSheet = workbook.sheets.find((sheet) => sheet.name.includes('喷油'))
  return sprayingSheet ? parseSprayingDetailTotal(sprayingSheet.rows) : null
}

function parseCaixingSheet(
  rows: XlsxCellValue[][],
  sheetName: string,
  sourceFileName: string,
  productType: CaixingProductType,
  sprayingDetailTotal?: number | null,
  pricing?: CustomerPricingSettings,
): CaixingQuoteData {
  const headerRow = findHeaderRow(rows)
  if (headerRow < 0) {
    throw new Error('未找到彩星内部报价明细表头：C列需为“名称”，D列需为“料型”')
  }

  const metadata = parseMetadata(rows, sheetName, sourceFileName, productType)
  const { injectionRows, total } = parseInjectionRows(rows, headerRow)
  const costRows = parseCostRows(rows, (total?.rowIndex ?? headerRow) + 1)
  const summary = buildSummary(productType, injectionRows, total, costRows, metadata.carton, sprayingDetailTotal, pricing)

  return {
    pricing,
    metadata,
    injectionRows,
    costRows,
    summary,
  }
}

function convertSheet(quoteData: CaixingQuoteData, sourceFileName: string, index: number): CaixingConvertedSheet {
  const sheetId = `caixing-${quoteData.metadata.productType}-${index + 1}-${quoteData.metadata.itemNo}`
  const details = buildDetailRows(sheetId, quoteData)
  const totalInternalHkd = round(details.reduce((sum, row) => sum + row.internalPriceHkd, 0), 4)

  return {
    id: sheetId,
    name: `${quoteData.metadata.itemNo} ${quoteData.metadata.productTypeName}`,
    productName: quoteData.metadata.itemName,
    sourceFileName,
    rowCount: details.length,
    totalInternalHkd,
    totalCustomerHkd: quoteData.summary.exFactoryHkd,
    details,
    quoteData,
  }
}

function findConvertibleSheet(workbook: ReturnType<typeof parseXlsxWorkbook>) {
  const matched = workbook.sheets.find((sheet) => findHeaderRow(sheet.rows) >= 0 && /\d{5,}/.test(sheet.name))
    ?? workbook.sheets.find((sheet) => findHeaderRow(sheet.rows) >= 0)

  if (!matched) {
    throw new Error('未找到彩星有效 Sheet：Sheet 名称或标题需包含货号，且明细表头为 C列“名称”/D列“料型”')
  }

  return matched
}

const CAIXING_PLASTIC_TEMPLATE_SHEETS = {
  deco: 'Deco List & Product Image',
  summary: 'Summary',
  toolPlan: 'Tool Plan',
  elect: 'Elect',
  purchase: 'purchase',
  packing: 'Packing',
  fabric: 'Fabric',
} as const

const CAIXING_PLUSH_TEMPLATE_SHEETS = {
  deco: 'Deco List & Product Image',
  summary: 'Summary',
  toolPlan: 'Tool Plan',
  elect: 'Elect',
  purchase: 'Purchase',
  packing: 'Packing',
  fabric: 'Fabric',
} as const

const CAIXING_PLASTIC_TEMPLATE_MATERIAL_CODES: Record<string, number> = {
  ABS: 1,
  PVC: 2,
  HIPS: 3,
  PE: 4,
  PP: 5,
  POM: 7,
  'C-ABS': 9,
  'C-PP': 5,
  LDPE: 11,
}

const CAIXING_PLUSH_TEMPLATE_MATERIAL_CODES: Record<string, number> = {
  ABS: 1,
  PVC: 2,
  'C-ABS': 3,
  TPR: 4,
  PP: 5,
  'C-PP': 6,
  POM: 7,
  PE: 8,
}

interface CaixingGroupedCostRows {
  specialRows: CaixingCostRow[]
  electronicRows: CaixingCostRow[]
  packingRows: CaixingCostRow[]
  fabricRows: CaixingCostRow[]
  purchaseRows: CaixingCostRow[]
}

type CaixingPackingTemplateKey =
  | 'blister_tray'
  | 'blister_card'
  | 'blister_insert'
  | 'blister_outer'
  | 'blister_inner'
  | 'box_closed'
  | 'box_open'
  | 'box_window'
  | 'box_insert'
  | 'insert'
  | 'cable_tie'
  | 'certificate'
  | 'collector'
  | 'greeting_card'
  | 'card_insert'
  | 'carton_inner'
  | 'carton_insert'
  | 'chip_insert'
  | 'clamshell'
  | 'instruction_sheet'
  | 'label_product'
  | 'label_warning'
  | 'plastic_nail'
  | 'polybag'
  | 'reinforce_plate'
  | 'tissue_paper'
  | 'pp_tape'
  | 'j_hook'
  | 'dennison'
  | 'hot_melt_glue'
  | 'packing_material'
  | 'blank'

interface CaixingPackingTemplateSlot {
  rowNumber: number
  key: CaixingPackingTemplateKey
}

const CAIXING_PLASTIC_PACKING_SLOTS: CaixingPackingTemplateSlot[] = [
  { rowNumber: 7, key: 'blister_tray' },
  { rowNumber: 8, key: 'blister_insert' },
  { rowNumber: 9, key: 'blister_insert' },
  { rowNumber: 10, key: 'blister_insert' },
  { rowNumber: 11, key: 'blister_outer' },
  { rowNumber: 12, key: 'blister_inner' },
  { rowNumber: 13, key: 'box_open' },
  { rowNumber: 14, key: 'box_window' },
  { rowNumber: 15, key: 'insert' },
  { rowNumber: 16, key: 'cable_tie' },
  { rowNumber: 17, key: 'cable_tie' },
  { rowNumber: 18, key: 'certificate' },
  { rowNumber: 19, key: 'collector' },
  { rowNumber: 20, key: 'card_insert' },
  { rowNumber: 21, key: 'card_insert' },
  { rowNumber: 22, key: 'card_insert' },
  { rowNumber: 23, key: 'carton_inner' },
  { rowNumber: 24, key: 'carton_insert' },
  { rowNumber: 26, key: 'chip_insert' },
  { rowNumber: 27, key: 'chip_insert' },
  { rowNumber: 28, key: 'clamshell' },
  { rowNumber: 29, key: 'clamshell' },
  { rowNumber: 30, key: 'instruction_sheet' },
  { rowNumber: 31, key: 'label_product' },
  { rowNumber: 32, key: 'label_product' },
  { rowNumber: 33, key: 'label_warning' },
  { rowNumber: 34, key: 'plastic_nail' },
  { rowNumber: 35, key: 'polybag' },
  { rowNumber: 36, key: 'polybag' },
  { rowNumber: 37, key: 'polybag' },
  { rowNumber: 38, key: 'reinforce_plate' },
  { rowNumber: 39, key: 'tissue_paper' },
  { rowNumber: 40, key: 'pp_tape' },
  { rowNumber: 41, key: 'j_hook' },
  { rowNumber: 42, key: 'dennison' },
  { rowNumber: 43, key: 'packing_material' },
  ...Array.from({ length: 9 }, (_, index) => ({ rowNumber: 44 + index, key: 'blank' as const })),
]

const CAIXING_PLUSH_PACKING_SLOTS: CaixingPackingTemplateSlot[] = [
  { rowNumber: 7, key: 'blister_card' },
  { rowNumber: 8, key: 'blister_insert' },
  { rowNumber: 9, key: 'blister_insert' },
  { rowNumber: 10, key: 'blister_outer' },
  { rowNumber: 11, key: 'blister_inner' },
  { rowNumber: 12, key: 'box_closed' },
  { rowNumber: 13, key: 'box_open' },
  { rowNumber: 14, key: 'box_window' },
  { rowNumber: 15, key: 'box_insert' },
  { rowNumber: 16, key: 'cable_tie' },
  { rowNumber: 17, key: 'certificate' },
  { rowNumber: 18, key: 'greeting_card' },
  { rowNumber: 19, key: 'card_insert' },
  { rowNumber: 20, key: 'card_insert' },
  { rowNumber: 21, key: 'card_insert' },
  { rowNumber: 22, key: 'carton_inner' },
  { rowNumber: 23, key: 'carton_insert' },
  { rowNumber: 25, key: 'chip_insert' },
  { rowNumber: 26, key: 'chip_insert' },
  { rowNumber: 27, key: 'clamshell' },
  { rowNumber: 28, key: 'clamshell' },
  { rowNumber: 29, key: 'instruction_sheet' },
  { rowNumber: 30, key: 'label_product' },
  { rowNumber: 31, key: 'label_product' },
  { rowNumber: 32, key: 'label_product' },
  { rowNumber: 33, key: 'label_warning' },
  { rowNumber: 34, key: 'plastic_nail' },
  { rowNumber: 35, key: 'polybag' },
  { rowNumber: 36, key: 'polybag' },
  { rowNumber: 37, key: 'polybag' },
  { rowNumber: 38, key: 'reinforce_plate' },
  { rowNumber: 39, key: 'tissue_paper' },
  { rowNumber: 40, key: 'pp_tape' },
  { rowNumber: 41, key: 'dennison' },
  { rowNumber: 42, key: 'hot_melt_glue' },
  { rowNumber: 43, key: 'packing_material' },
  ...Array.from({ length: 10 }, (_, index) => ({ rowNumber: 44 + index, key: 'blank' as const })),
]

interface CaixingTemplateCellPatch {
  ref: string
  value: XlsxCellValue
  formula?: string
  style?: number
}

interface CaixingTemplateCellMatch {
  ref: string
  attrs: string
  full: string
  start: number
  end: number
}

function getCaixingGroupedCostRows(data: CaixingQuoteData): CaixingGroupedCostRows {
  const specialRows = [
    ...filterCustomerGroup(data.costRows, 'special'),
    ...(data.metadata.productType === 'plush'
      ? data.costRows.filter((row) => !row.customerGroup && /搪胶/.test(`${row.category} ${row.description}`))
      : []),
  ]
  const electronicRows = filterCustomerGroup(data.costRows, 'electronic')
  const packingRows = filterCustomerGroup(data.costRows, 'packing')
  const fabricRows = filterCustomerGroup(data.costRows, 'fabric')
  const purchaseRows = filterCustomerGroup(data.costRows, 'purchase')

  return {
    specialRows,
    electronicRows,
    packingRows,
    fabricRows,
    purchaseRows,
  }
}

function getPackingTemplateCandidates(row: CaixingCostRow): CaixingPackingTemplateKey[] {
  const category = row.category
  const description = row.description
  const haystack = `${category} ${description}`

  if (/说明书|instruction\s*sheet/i.test(description)) return ['instruction_sheet', 'packing_material', 'blank']
  if (/利宝|label/i.test(description)) return ['label_product', 'label_warning', 'packing_material', 'blank']
  if (/开窗|window/i.test(description)) return ['box_window', 'box_open', 'packing_material', 'blank']
  if (/闭口|closed/i.test(description)) return ['box_closed', 'box_open', 'packing_material', 'blank']
  if (/彩盒|box/i.test(description)) return ['box_open', 'box_closed', 'box_window', 'packing_material', 'blank']
  if (/胶针|plastic\s*nail/i.test(haystack)) return ['plastic_nail', 'dennison', 'packing_material', 'blank']
  if (/胶纸|tape/i.test(haystack)) return ['pp_tape', 'packing_material', 'blank']
  if (/锡线/i.test(haystack)) return ['packing_material', 'blank']
  if (/热熔胶|hot\s*melt/i.test(haystack)) return ['hot_melt_glue', 'packing_material', 'blank']
  if (/纸巾|tissue/i.test(haystack)) return ['tissue_paper', 'packing_material', 'blank']
  if (/胶袋|polybag/i.test(haystack)) return ['polybag', 'packing_material', 'blank']
  if (/扎带|cable\s*tie/i.test(haystack)) return ['cable_tie', 'packing_material', 'blank']
  if (/警告|warning/i.test(haystack)) return ['label_warning', 'label_product', 'packing_material', 'blank']
  if (/证书|certificate/i.test(haystack)) return ['certificate', 'card_insert', 'packing_material', 'blank']
  if (/贺卡|greeting/i.test(haystack)) return ['greeting_card', 'card_insert', 'packing_material', 'blank']
  if (/收藏卡|collector/i.test(haystack)) return ['collector', 'card_insert', 'packing_material', 'blank']
  if (/内咭|内卡|插咭|插卡|card\s*insert/i.test(haystack)) return ['card_insert', 'insert', 'packing_material', 'blank']
  if (/内箱/i.test(haystack)) return ['carton_inner', 'carton_insert', 'packing_material', 'blank']
  if (/纸板|carton\s*insert/i.test(haystack)) return ['carton_insert', 'reinforce_plate', 'packing_material', 'blank']
  if (/开窗|window/i.test(haystack)) return ['box_window', 'box_open', 'packing_material', 'blank']
  if (/闭口|closed/i.test(haystack)) return ['box_closed', 'box_open', 'packing_material', 'blank']
  if (/彩盒|box/i.test(haystack)) return ['box_open', 'box_closed', 'box_window', 'packing_material', 'blank']
  if (/吸塑咭|吸塑卡|blister\s*card/i.test(haystack)) return ['blister_card', 'blister_tray', 'blister_insert', 'packing_material', 'blank']
  if (/吸塑.*外|blister\s*outer/i.test(haystack)) return ['blister_outer', 'blister_tray', 'packing_material', 'blank']
  if (/吸塑.*内|blister\s*inner/i.test(haystack)) return ['blister_inner', 'blister_tray', 'packing_material', 'blank']
  if (/吸塑托|blister\s*tray/i.test(haystack)) return ['blister_tray', 'blister_inner', 'blister_outer', 'packing_material', 'blank']
  if (/吸塑|blister/i.test(haystack)) return ['blister_tray', 'blister_card', 'blister_insert', 'packing_material', 'blank']
  if (/利宝|label/i.test(category)) return ['label_product', 'label_warning', 'packing_material', 'blank']
  if (/说明书/i.test(category)) return ['instruction_sheet', 'packing_material', 'blank']

  return ['packing_material', 'blank']
}

function assignPackingTemplateRows(
  rows: CaixingCostRow[],
  slots: CaixingPackingTemplateSlot[],
) {
  const available = [...slots]

  return rows.flatMap((item) => {
    const candidates = getPackingTemplateCandidates(item)
    let slotIndex = candidates
      .map((candidate) => available.findIndex((slot) => slot.key === candidate))
      .find((index) => index >= 0) ?? -1

    if (slotIndex < 0) {
      slotIndex = available.findIndex((slot) => slot.key === 'blank')
    }
    if (slotIndex < 0) {
      throw new Error(`彩星 Packing 明细超过模板容量，未能安置：${item.description}`)
    }

    const [slot] = available.splice(slotIndex, 1)
    return [{ item, rowNumber: slot.rowNumber }]
  })
}

function templateColumnNameToIndex(columnName: string) {
  return columnName.split('').reduce((total, char) => total * 26 + char.charCodeAt(0) - 64, 0) - 1
}

function templateColumnIndexToName(columnIndex: number) {
  let index = columnIndex + 1
  let name = ''

  while (index > 0) {
    const remainder = (index - 1) % 26
    name = String.fromCharCode(65 + remainder) + name
    index = Math.floor((index - 1) / 26)
  }

  return name
}

function parseTemplateCellRef(ref: string) {
  const columnName = ref.match(/[A-Z]+/)?.[0] ?? 'A'
  const rowNumber = Number(ref.match(/\d+/)?.[0] ?? 1)

  return {
    columnIndex: templateColumnNameToIndex(columnName),
    rowNumber,
  }
}

function escapeTemplateXml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function decodeTemplateAttr(value: string) {
  return value
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
}

function formatTemplateNumber(value: number) {
  if (!Number.isFinite(value)) {
    return '0'
  }

  return String(Number(value.toFixed(12)))
}

function readTemplateAttr(attrs: string, name: string) {
  return attrs.match(new RegExp(`\\b${name}="([^"]*)"`))?.[1] ?? ''
}

function createTemplateCellMap(sheetXml: string) {
  const cellMap = new Map<string, CaixingTemplateCellMatch>()
  const cellPattern = /<c\b([^>]*)\/>|<c\b([^>]*)>([\s\S]*?)<\/c>/g

  for (const match of sheetXml.matchAll(cellPattern)) {
    const attrs = match[1] ?? match[2] ?? ''
    const ref = readTemplateAttr(attrs, 'r')
    if (!ref || match.index === undefined) {
      continue
    }

    cellMap.set(ref, {
      ref,
      attrs,
      full: match[0],
      start: match.index,
      end: match.index + match[0].length,
    })
  }

  return cellMap
}

function buildTemplateCellXml(patch: CaixingTemplateCellPatch, existing?: CaixingTemplateCellMatch) {
  const existingStyle = existing ? Number(readTemplateAttr(existing.attrs, 's')) : Number.NaN
  const style = typeof patch.style === 'number'
    ? patch.style
    : Number.isFinite(existingStyle) ? existingStyle : undefined
  const styleAttr = typeof style === 'number' ? ` s="${style}"` : ''
  const formula = patch.formula ?? ''

  if (patch.value === null || patch.value === undefined || patch.value === '') {
    if (formula) {
      return `<c r="${patch.ref}"${styleAttr}><f>${escapeTemplateXml(formula)}</f></c>`
    }

    return `<c r="${patch.ref}"${styleAttr}/>`
  }

  if (formula) {
    const value = typeof patch.value === 'number'
      ? formatTemplateNumber(patch.value)
      : escapeTemplateXml(String(patch.value))
    const typeAttr = typeof patch.value === 'number' ? '' : ' t="str"'

    return `<c r="${patch.ref}"${typeAttr}${styleAttr}><f>${escapeTemplateXml(formula)}</f><v>${value}</v></c>`
  }

  if (typeof patch.value === 'number') {
    return `<c r="${patch.ref}"${styleAttr}><v>${formatTemplateNumber(patch.value)}</v></c>`
  }

  if (typeof patch.value === 'boolean') {
    return `<c r="${patch.ref}" t="b"${styleAttr}><v>${patch.value ? 1 : 0}</v></c>`
  }

  const text = String(patch.value)
  const spaceAttr = /^\s|\s$/.test(text) ? ' xml:space="preserve"' : ''
  return `<c r="${patch.ref}" t="inlineStr"${styleAttr}><is><t${spaceAttr}>${escapeTemplateXml(text)}</t></is></c>`
}

function insertTemplateCell(sheetXml: string, patch: CaixingTemplateCellPatch) {
  if ((patch.value === null || patch.value === undefined || patch.value === '') && !patch.formula) {
    return sheetXml
  }

  const { rowNumber, columnIndex } = parseTemplateCellRef(patch.ref)
  const rowPattern = new RegExp(`<row\\b[^>]*\\br="${rowNumber}"[^>]*>[\\s\\S]*?<\\/row>`)
  const rowMatch = sheetXml.match(rowPattern)
  const cellXml = buildTemplateCellXml(patch)

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
    const ref = readTemplateAttr(attrs, 'r')
    const existingColumn = ref.match(/[A-Z]+/)?.[0]
    if (match.index !== undefined && existingColumn && templateColumnNameToIndex(existingColumn) > columnIndex) {
      insertOffset = match.index
      break
    }
  }

  const insertIndex = rowStart + insertOffset
  return `${sheetXml.slice(0, insertIndex)}${cellXml}${sheetXml.slice(insertIndex)}`
}

function applyTemplateCellPatches(sheetXml: string, patches: CaixingTemplateCellPatch[]) {
  const cellMap = createTemplateCellMap(sheetXml)
  const uniquePatches = new Map<string, CaixingTemplateCellPatch>()
  const replacements: Array<{ start: number, end: number, xml: string }> = []
  const missingPatches: CaixingTemplateCellPatch[] = []

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
      xml: buildTemplateCellXml(patch, existing),
    })
  })

  let updatedXml = sheetXml
  replacements
    .sort((a, b) => b.start - a.start)
    .forEach((replacement) => {
      updatedXml = `${updatedXml.slice(0, replacement.start)}${replacement.xml}${updatedXml.slice(replacement.end)}`
    })

  return missingPatches.reduce((xml, patch) => insertTemplateCell(xml, patch), updatedXml)
}

function normalizeTemplateWorksheetTarget(target: string) {
  const normalized = target.replace(/\\/g, '/').replace(/^\/+/, '')
  return normalized.startsWith('xl/') ? normalized : `xl/${normalized}`
}

function resolveTemplateWorksheetTargets(zip: Record<string, Uint8Array>) {
  const workbookXml = zip['xl/workbook.xml'] ? strFromU8(zip['xl/workbook.xml']) : ''
  const relationsXml = zip['xl/_rels/workbook.xml.rels'] ? strFromU8(zip['xl/_rels/workbook.xml.rels']) : ''
  const relationMap = new Map<string, string>()

  for (const match of relationsXml.matchAll(/<Relationship\b([^>]*)\/>/g)) {
    const id = readTemplateAttr(match[1], 'Id')
    const target = readTemplateAttr(match[1], 'Target')
    if (id && target) {
      relationMap.set(id, target)
    }
  }

  return Array.from(workbookXml.matchAll(/<sheet\b([^>]*)\/>/g)).map((match, index) => {
    const attrs = match[1]
    const relationId = readTemplateAttr(attrs, 'r:id')
    const target = relationMap.get(relationId) ?? `worksheets/sheet${index + 1}.xml`

    return {
      name: decodeTemplateAttr(readTemplateAttr(attrs, 'name') || `Sheet${index + 1}`),
      path: normalizeTemplateWorksheetTarget(target),
    }
  })
}

function getTemplateSheetPath(zip: Record<string, Uint8Array>, sheetName: string) {
  return resolveTemplateWorksheetTargets(zip).find((sheet) => sheet.name === sheetName)?.path ?? ''
}

function getTemplatePartRelsPath(partPath: string) {
  const parts = partPath.split('/')
  const fileName = parts.pop() ?? ''
  return `${parts.join('/')}/_rels/${fileName}.rels`
}

function resolveTemplatePartPath(basePartPath: string, target: string) {
  if (target.startsWith('/')) {
    return target.replace(/^\/+/, '')
  }

  const baseParts = basePartPath.split('/').slice(0, -1)
  const resolved: string[] = []

  ;[...baseParts, ...target.split('/')].forEach((part) => {
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

function stripTemplatePictureAnchors(drawingXml: string, relationIds: Set<string>) {
  return (['twoCellAnchor', 'oneCellAnchor', 'absoluteAnchor'] as const).reduce((xml, anchorName) => {
    const anchorPattern = new RegExp(`<xdr:${anchorName}\\b[\\s\\S]*?<\\/xdr:${anchorName}>`, 'g')
    return xml.replace(anchorPattern, (anchorXml) => [...relationIds].some((id) => anchorXml.includes(`r:embed="${id}"`)) ? '' : anchorXml)
  }, drawingXml)
}

function replaceTemplateSheetProductPictures(zip: Record<string, Uint8Array>, sheetName: string, image?: YinhuiProductImage) {
  const sheetPath = getTemplateSheetPath(zip, sheetName)
  const sheetXml = sheetPath && zip[sheetPath] ? strFromU8(zip[sheetPath]) : ''
  if (!sheetXml) {
    return
  }

  const sheetRelsPath = getTemplatePartRelsPath(sheetPath)
  const sheetRelsXml = zip[sheetRelsPath] ? strFromU8(zip[sheetRelsPath]) : ''
  if (!sheetRelsXml) {
    return
  }

  for (const drawingMatch of sheetXml.matchAll(/<drawing\b([^>]*)\/>/g)) {
    const drawingRelationId = readTemplateAttr(drawingMatch[1], 'r:id')
    if (!drawingRelationId) {
      continue
    }

    for (const relationMatch of sheetRelsXml.matchAll(/<Relationship\b([^>]*)\/>/g)) {
      const relationAttrs = relationMatch[1]
      if (readTemplateAttr(relationAttrs, 'Id') !== drawingRelationId) {
        continue
      }

      if (!readTemplateAttr(relationAttrs, 'Type').includes('/drawing')) {
        continue
      }

      const drawingPath = resolveTemplatePartPath(sheetPath, readTemplateAttr(relationAttrs, 'Target'))
      const drawingXml = drawingPath && zip[drawingPath] ? strFromU8(zip[drawingPath]) : ''
      if (!drawingXml) {
        continue
      }

      const drawingRelsPath = getTemplatePartRelsPath(drawingPath)
      let drawingRelsXml = zip[drawingRelsPath] ? strFromU8(zip[drawingRelsPath]) : ''
      const productRelationIds = new Set<string>()
      drawingRelsXml = drawingRelsXml.replace(/<Relationship\b([^>]*)\/>/g, (relationXml, attrs: string) => {
        const target = readTemplateAttr(attrs, 'Target')
        if (!/\/image[123]\.png$/i.test(target)) return relationXml
        const id = readTemplateAttr(attrs, 'Id')
        productRelationIds.add(id)
        if (!image) return ''
        return relationXml.replace(/Target="[^"]*"/, `Target="../media/caixing-product.${image.extension}"`)
      })
      if (!productRelationIds.size) continue
      zip[drawingRelsPath] = strToU8(drawingRelsXml)
      if (!image) zip[drawingPath] = strToU8(stripTemplatePictureAnchors(drawingXml, productRelationIds))
    }
  }
}

function forceTemplateRecalculation(workbookXml: string) {
  const calcPr = '<calcPr calcMode="auto" fullCalcOnLoad="1" forceFullCalc="1"/>'

  if (/<calcPr\b[\s\S]*?\/>/.test(workbookXml)) {
    return workbookXml.replace(/<calcPr\b[\s\S]*?\/>/, calcPr)
  }

  if (/<calcPr\b[\s\S]*?<\/calcPr>/.test(workbookXml)) {
    return workbookXml.replace(/<calcPr\b[\s\S]*?<\/calcPr>/, calcPr)
  }

  return workbookXml.replace('</workbook>', `${calcPr}</workbook>`)
}

function extendPlasticToolPlanTemplate(zip: Record<string, Uint8Array>, extraRows: number) {
  if (!extraRows) return
  if (!Number.isInteger(extraRows) || extraRows < 0 || extraRows > 48) throw new Error('彩星塑胶 Tool Plan 扩展行数无效')
  const path = getTemplateSheetPath(zip, CAIXING_PLASTIC_TEMPLATE_SHEETS.toolPlan)
  const xml = path && zip[path] ? strFromU8(zip[path]) : ''
  const sampleRow = xml.match(/<row\b[^>]*\br="67"[^>]*>[\s\S]*?<\/row>/)?.[0]
  if (!sampleRow || !/<row\b[^>]*\br="68"/.test(xml) || !/<row\b[^>]*\br="69"/.test(xml)) {
    throw new Error('彩星塑胶 Tool Plan 模板缺少可安全扩展的明细与合计行')
  }
  const shifted = xml.replace(/<row\b[^>]*\br="(\d+)"[^>]*>[\s\S]*?<\/row>/g, (rowXml, numberText: string) => {
    const number = Number(numberText)
    if (number < 68) return rowXml
    const next = number + extraRows
    return rowXml.replace(/(<row\b[^>]*\br=")\d+("[^>]*>)/, `$1${next}$2`)
      .replace(/(<c\b[^>]*\br="[A-Z]+)\d+("[^>]*>)/g, `$1${next}$2`)
      .replace(/(<c\b[^>]*\br="[A-Z]+)\d+("[^>]*\/>)/g, `$1${next}$2`)
  })
  const extra = Array.from({ length: extraRows }, (_, index) => {
    const number = 68 + index
    return sampleRow.replace(/(<row\b[^>]*\br=")67("[^>]*>)/, `$1${number}$2`)
      .replace(/(\$?[A-Z]{1,3}\$?)67\b/g, `$1${number}`)
  }).join('')
  const inserted = shifted.replace(/(<row\b[^>]*\br="67"[^>]*>[\s\S]*?<\/row>)/, `$1${extra}`)
    .replace(/(<dimension\b[^>]*\bref="[A-Z]+\d+:[A-Z]+)\d+("[^>]*\/>)/, (_match, start: string, end: string) => `${start}${71 + extraRows}${end}`)
  zip[path] = strToU8(inserted)
  if (zip['xl/workbook.xml']) {
    zip['xl/workbook.xml'] = strToU8(strFromU8(zip['xl/workbook.xml']).replace(/('Tool Plan'!\$A\$1:\$Q\$)69\b/g, `$1${69 + extraRows}`))
  }
}

function appendTemplateGeneralNumberStyles(stylesXml: string, sourceStyleIndexes: number[]) {
  const cellXfsMatch = stylesXml.match(/<cellXfs\b([^>]*)>([\s\S]*?)<\/cellXfs>/)
  if (!cellXfsMatch) {
    throw new Error('彩星报客价模板缺少 cellXfs 样式定义')
  }
  const stylePattern = /<xf\b[^>]*\/>|<xf\b[^>]*>[\s\S]*?<\/xf>/g
  const styles = Array.from(cellXfsMatch[2].matchAll(stylePattern), (match) => match[0])
  const clonedStyles = sourceStyleIndexes.map((sourceIndex) => {
    const source = styles[sourceIndex]
    if (!source) {
      throw new Error(`彩星报客价模板缺少样式索引：${sourceIndex}`)
    }
    return source
      .replace(/\bnumFmtId="\d+"/, 'numFmtId="0"')
      .replace(/\sapplyNumberFormat="1"/, '')
  })
  const indexes = clonedStyles.map((_, index) => styles.length + index)
  const attrs = cellXfsMatch[1].match(/\bcount="\d+"/)
    ? cellXfsMatch[1].replace(/\bcount="\d+"/, `count="${styles.length + clonedStyles.length}"`)
    : `${cellXfsMatch[1]} count="${styles.length + clonedStyles.length}"`
  const replacement = `<cellXfs${attrs}>${cellXfsMatch[2]}${clonedStyles.join('')}</cellXfs>`
  return {
    indexes,
    stylesXml: stylesXml.replace(cellXfsMatch[0], replacement),
  }
}

function toTemplateUint8Array(templateBuffer: ArrayBuffer | Uint8Array) {
  return templateBuffer instanceof Uint8Array ? templateBuffer : new Uint8Array(templateBuffer)
}

function getTemplateMaterialCode(material: string, productType: CaixingProductType = 'plastic') {
  const codes = productType === 'plush'
    ? CAIXING_PLUSH_TEMPLATE_MATERIAL_CODES
    : CAIXING_PLASTIC_TEMPLATE_MATERIAL_CODES

  return codes[normalizeMaterialName(material)] ?? 1
}

function patchCaixingToolRates(data: CaixingQuoteData, patch: (sheet: string, ref: string, value: XlsxCellValue) => void, summarySheet: string) {
  const plush = data.metadata.productType === 'plush'
  const p4 = data.metadata.sourceSheetName === 'P4 v2'
  const firstMaterialRow = plush ? 44 : 40
  const machineRows = plush
    ? ['2', '4', '7', '10', '14', '18', '28', '30', '35', '40', 'BL', 'CP', 'DC', 'RC']
    : ['2', '4', '7', '12', '14', '20', '25', '28', '35', '40', 'BL', 'CP', 'DC', 'RC']
  const materialPrices = new Map<number, number>()
  const materialNames = new Map<number, string>()
  const machinePrices = new Map<string, number>()
  const usedMachines = new Set(data.injectionRows.map((row) => row.processType && row.processType !== 'IN' ? row.processType : String(row.machineTons)))
  if (p4) {
    usedMachines.forEach((size) => {
      if (machineRows.includes(size)) return
      if (['BL', 'CP', 'DC', 'RC'].includes(size)) throw new Error(`彩星啤机工艺 ${size} 不在模板范围内`)
      const replaceAt = machineRows.findIndex((name, index) => index < 10 && !usedMachines.has(name))
      if (replaceAt < 0) throw new Error('彩星本单啤机规格超过模板可容纳的 10 种')
      machineRows[replaceAt] = size
    })
  }
  const scrap = caixingOptionalRate(data.pricing, 'tool_material_scrap_rate', 0.02)
  data.injectionRows.forEach((row) => {
    if (p4 && row.materialCode && row.material) {
      const code = row.materialCode
      if (code < 1 || code > 14) throw new Error(`彩星 Tool Plan ${row.lineNo} 的材料编号不在模板范围内`)
      const name = normalizeMaterialName(row.material)
      const previousName = materialNames.get(code)
      if (previousName && previousName !== name) {
        throw new Error(`彩星材料编号 ${code} 对应了不同料型，请核对 Tool Plan 的料型与引用料价`)
      }
      materialNames.set(code, name)
    }
    const materialPrice = row.materialUnitPriceHkdKg ?? (p4 && row.materialCostHkd > 0 && row.weightG > 0
      ? row.materialCostHkd / (row.weightG / 1000 * (1 + scrap)) : undefined)
    if (materialPrice !== undefined) {
      const code = row.materialCode ?? 0
      if (code < 1 || code > 14) throw new Error(`彩星 Tool Plan ${row.lineNo} 的材料编号不在模板范围内`)
      const previous = materialPrices.get(code)
      if (previous !== undefined && Math.abs(previous - materialPrice) > (p4 ? Math.max(0.1, previous * 0.005) : 0.001)) {
        throw new Error(`彩星同一材料编号 ${code} 有不同客户公斤价，请在本单统一材料单价后重试`)
      }
      if (previous === undefined || row.materialUnitPriceHkdKg !== undefined) materialPrices.set(code, materialPrice)
    }
    const machinePrice = row.machineHourlyHkd ?? (p4 && row.moldingCostHkd > 0 && row.cycleSeconds > 0
      ? row.moldingCostHkd * 3600 * row.setsPerShot / row.cycleSeconds : undefined)
    if (machinePrice !== undefined) {
      const size = row.processType && row.processType !== 'IN' ? row.processType : String(row.machineTons)
      if (!machineRows.includes(size)) throw new Error(`彩星 Tool Plan ${row.lineNo} 的啤机规格 ${size} 不在客户模板范围内`)
      const previous = machinePrices.get(size)
      if (previous !== undefined && Math.abs(previous - machinePrice) > (p4 ? Math.max(1, previous * 0.005) : 0.001)) {
        throw new Error(`彩星同一啤机规格 ${size} 有不同客户小时价，请在本单统一啤机日价后重试`)
      }
      if (previous === undefined || row.machineHourlyHkd !== undefined) machinePrices.set(size, machinePrice)
    }
  })
  if (p4) data.injectionRows.forEach((row) => {
    const code = row.materialCode ?? 0
    const materialPrice = materialPrices.get(code)
    if (materialPrice !== undefined && roundMoney(row.weightG / 1000 * (1 + scrap) * round(materialPrice, 6)) !== roundMoney(row.materialCostHkd)) {
      throw new Error(`彩星 Tool Plan ${row.lineNo} 的料金额与材料编号 ${code} 共用单价重算不一致，请核对料价`)
    }
    const size = row.processType && row.processType !== 'IN' ? row.processType : String(row.machineTons)
    const machinePrice = machinePrices.get(size)
    if (machinePrice !== undefined && roundMoney(row.cycleSeconds / 3600 * round(machinePrice, 6) / row.setsPerShot) !== roundMoney(row.moldingCostHkd)) {
      throw new Error(`彩星 Tool Plan ${row.lineNo} 的啤工与机型 ${size} 共用小时价重算不一致，请核对啤机日价`)
    }
  })
  materialNames.forEach((name, code) => patch(summarySheet, `D${firstMaterialRow + code - 1}`, name))
  materialPrices.forEach((value, code) => {
    const row = firstMaterialRow + code - 1
    patch(summarySheet, `E${row}`, scrap)
    patch(summarySheet, `F${row}`, round(value, 6))
  })
  if (p4) machineRows.forEach((size, index) => patch(summarySheet, `G${firstMaterialRow + index}`, /^\d+$/.test(size) ? Number(size) : size))
  machinePrices.forEach((value, size) => patch(summarySheet, `H${firstMaterialRow + machineRows.indexOf(size)}`, round(value, 6)))
}

function caixingToolMaterialFormula(row: number, firstRateRow: number) {
  const range = `Summary!$C$${firstRateRow}:$F$${firstRateRow + 13}`
  return `IF(D${row}=0,IF(G${row}=$E$4,IF(OR(J${row}=0,K${row}=0),"",(J${row}/1000)*(1+VLOOKUP(K${row},${range},3))*VLOOKUP(K${row},${range},4)),""),"Dup Tool")`
}

function caixingToolProcessFormula(row: number, firstRateRow: number) {
  return `IF(D${row}=0,IF(A${row}=0,"",IF(OR(B${row}="IN",B${row}="BL",B${row}="CP",B${row}="DC",B${row}="RC"),((P${row}/3600)*(IF(B${row}="IN",VLOOKUP(O${row},Summary!$G$${firstRateRow}:$H$${firstRateRow + 9},2,FALSE)/I${row},VLOOKUP(B${row},Summary!$G$${firstRateRow + 10}:$H$${firstRateRow + 13},2,FALSE)/I${row}))),"Typ ??")),"Dup.Tool")`
}

function buildPlasticTemplatePatches(data: CaixingQuoteData, pricing?: CustomerPricingSettings) {
  const requiredToolRows = templateToolPlanRowCount(data)
  if (requiredToolRows > 100) throw new Error('彩星塑胶 Tool Plan 含附加工序超过安全扩展容量 100 行')
  const extraToolRows = Math.max(0, requiredToolRows - 52)
  const secondToolLastRow = 67 + extraToolRows
  const secondToolSubtotalRow = 68 + extraToolRows
  const toolTotalRow = 69 + extraToolRows
  const patchesBySheet: Record<string, CaixingTemplateCellPatch[]> = {
    [CAIXING_PLASTIC_TEMPLATE_SHEETS.deco]: [],
    [CAIXING_PLASTIC_TEMPLATE_SHEETS.summary]: [],
    [CAIXING_PLASTIC_TEMPLATE_SHEETS.toolPlan]: [],
    [CAIXING_PLASTIC_TEMPLATE_SHEETS.elect]: [],
    [CAIXING_PLASTIC_TEMPLATE_SHEETS.purchase]: [],
    [CAIXING_PLASTIC_TEMPLATE_SHEETS.packing]: [],
    [CAIXING_PLASTIC_TEMPLATE_SHEETS.fabric]: [],
  }
  const patch = (sheetName: string, ref: string, value: XlsxCellValue, style?: number) => {
    patchesBySheet[sheetName].push({ ref, value, style })
  }
  const formula = (sheetName: string, ref: string, value: XlsxCellValue, formulaText: string, style?: number) => {
    patchesBySheet[sheetName].push({ ref, value, formula: formulaText, style })
  }
  const ref = (columnIndex: number, rowNumber: number) => `${templateColumnIndexToName(columnIndex)}${rowNumber}`
  const clear = (sheetName: string, rowNumber: number, columnIndexes: number[]) => {
    columnIndexes.forEach((columnIndex) => patch(sheetName, ref(columnIndex, rowNumber), null))
  }
  const { metadata, summary } = data
  const { specialRows, electronicRows, packingRows, fabricRows, purchaseRows } = getCaixingGroupedCostRows(data)
  const summarySheet = CAIXING_PLASTIC_TEMPLATE_SHEETS.summary
  const toolSheet = CAIXING_PLASTIC_TEMPLATE_SHEETS.toolPlan
  const electSheet = CAIXING_PLASTIC_TEMPLATE_SHEETS.elect
  const purchaseSheet = CAIXING_PLASTIC_TEMPLATE_SHEETS.purchase
  const packingSheet = CAIXING_PLASTIC_TEMPLATE_SHEETS.packing
  const fabricSheet = CAIXING_PLASTIC_TEMPLATE_SHEETS.fabric
  const decoSheet = CAIXING_PLASTIC_TEMPLATE_SHEETS.deco
  const quoteDateSerial = excelDateSerial(metadata.quoteDate)
  const finalCost = (value: number, group: 'special' | 'electronic' | 'standard' = 'standard') => roundMoney(value * (1 + caixingMarkupRate(pricing, 'plastic', group, metadata.markupRateOverride)))
  const materialFinalTotal = roundMoney(summary.material.total * (1 + summary.markupRate))
  const pct = (value: number) => summary.exFactoryHkd ? round(value / summary.exFactoryHkd, 6) : 0

  patchCaixingToolRates(data, patch, summarySheet)

  patch(summarySheet, 'B3', metadata.itemNo)
  patch(summarySheet, 'B4', metadata.itemNo)
  patch(summarySheet, 'B5', metadata.itemName)
  formula(summarySheet, 'B6', metadata.carton.cube, 'IF(Packing!J25=0,"",Packing!G25*Packing!H25*Packing!I25/1728)')
  formula(summarySheet, 'B7', metadata.carton.pcsPerCarton, 'IF(Packing!J25=0,"",1/Packing!J25)')
  patch(summarySheet, 'G5', quoteDateSerial)
  patch(summarySheet, 'H56', pricingRate(pricing, 'hkd_usd', 7.8))
  patch(summarySheet, 'H57', caixingOptionalRate(pricing, 'hkd_cny', 1.199))
  patch(summarySheet, 'A58', caixingMoqText(pricing))
  patch(summarySheet, 'F32', pricingRate(pricing, 'domestic_freight_rate', 2.11))
  patch(summarySheet, 'F34', pricingRate(pricing, 'fob_freight_rate', 5.93))

  ;[
    ['E11', summary.material.plasticParts, `'Tool Plan'!N${toolTotalRow}`],
    ['E12', summary.material.specialMaterial, 'Elect!I19'],
    ['E13', summary.material.electronicMaterial, 'Elect!I89'],
    ['E14', summary.material.purchasePart, 'purchase!I26'],
    ['E15', summary.material.packagingMaterial, 'Packing!$N$53'],
    ['E16', summary.material.fabric, 'Fabric!I31'],
  ].forEach(([cellRef, value, formulaText]) => {
    formula(summarySheet, cellRef as string, value as number, formulaText as string)
  })

  for (let rowNumber = 11; rowNumber <= 16; rowNumber += 1) {
    const base = toNumber(rowNumber === 11 ? summary.material.plasticParts
      : rowNumber === 12 ? summary.material.specialMaterial
        : rowNumber === 13 ? summary.material.electronicMaterial
          : rowNumber === 14 ? summary.material.purchasePart
            : rowNumber === 15 ? summary.material.packagingMaterial
              : summary.material.fabric)
    const group = rowNumber === 12 ? 'special' : rowNumber === 13 ? 'electronic' : 'standard'
    patch(summarySheet, `F${rowNumber}`, caixingMarkupRate(pricing, 'plastic', group, metadata.markupRateOverride))
    formula(summarySheet, `G${rowNumber}`, finalCost(base), `E${rowNumber}*(1+F${rowNumber})`)
    formula(summarySheet, `H${rowNumber}`, pct(finalCost(base)), `IF(G$29=0,"",G${rowNumber}/G$29)`)
  }

  formula(summarySheet, 'E17', summary.material.total, 'SUM(E11:E16)')
  formula(summarySheet, 'G17', materialFinalTotal, 'SUM(G11:G16)')
  formula(summarySheet, 'H17', pct(materialFinalTotal), 'IF(G$29=0,"",G17/G$29)')
  formula(
    summarySheet,
    'E19',
    summary.process.moldingCasting,
    `SUMIF('Tool Plan'!B14:B57,"<>BL",'Tool Plan'!Q14:Q57)+SUMIF('Tool Plan'!B60:B${secondToolLastRow},"<>BL",'Tool Plan'!Q60:Q${secondToolLastRow})`,
  )
  for (let rowNumber = 19; rowNumber <= 26; rowNumber += 1) {
    const base = toNumber(rowNumber === 19 ? summary.process.moldingCasting
      : rowNumber === 20 ? summary.process.spraying
        : rowNumber === 21 ? summary.process.tampo
          : rowNumber === 22 ? summary.process.assemblyLabor
            : rowNumber === 23 ? summary.process.packoutLabor
              : rowNumber === 24 ? summary.process.rootingHair
                : rowNumber === 25 ? summary.process.sewingHandfinish
                  : summary.process.specialOffer)
    if (rowNumber > 19) {
      patch(summarySheet, `C${rowNumber}`, base ? 1 : null)
      patch(summarySheet, `D${rowNumber}`, base || null)
      formula(summarySheet, `E${rowNumber}`, base, `C${rowNumber}*D${rowNumber}`)
    }
    patch(summarySheet, `F${rowNumber}`, summary.markupRate)
    formula(summarySheet, `G${rowNumber}`, finalCost(base), `E${rowNumber}*(1+F${rowNumber})`)
    formula(summarySheet, `H${rowNumber}`, pct(finalCost(base)), `IF(G$29=0,"",G${rowNumber}/G$29)`)
  }

  formula(summarySheet, 'E27', summary.process.total, 'SUM(E18:E26)')
  formula(summarySheet, 'G27', finalCost(summary.process.total), 'SUM(G18:G26)')
  formula(summarySheet, 'H27', pct(finalCost(summary.process.total)), 'IF(G$29=0,"",G27/G$29)')
  formula(summarySheet, 'E29', summary.material.total + summary.process.total, 'E17+E27')
  formula(summarySheet, 'G29', summary.exFactoryHkd, 'ROUND(G17+G27,2)')
  formula(summarySheet, 'G30', summary.exFactoryUsd, 'ROUND(G29/$H$56,3)')
  formula(summarySheet, 'G32', summary.domesticTransportationHkd, 'IF(B6=""," ",F32*B6/B7)')
  formula(summarySheet, 'G34', summary.fobTransportationHkd, 'IF(B6=""," ",F34*B6/B7)')

  // The supplied plastic template contains five stale external-workbook links
  // ("[1]Summary"). Rebind them to this workbook so Excel and preview tools do
  // not show #NAME? after the controlled template is generated.
  formula(decoSheet, 'E1', 'ITEM No : ', 'Summary!A3')
  formula(decoSheet, 'N1', 'Vendor : ', 'Summary!F3')
  formula(decoSheet, 'O1', 'Royal Regent Products (H.K.) Limited', 'Summary!G3')
  formula(decoSheet, 'E2', 'Item Description : ', 'Summary!A5')
  formula(decoSheet, 'N2', 'Date : ', 'Summary!F5')
  patch(decoSheet, 'G1', metadata.itemNo)
  patch(decoSheet, 'G2', metadata.itemName)
  patch(decoSheet, 'O2', quoteDateSerial)
  patch(decoSheet, 'C17', metadata.carton.length)
  patch(decoSheet, 'C18', metadata.carton.width)
  patch(decoSheet, 'C19', metadata.carton.height)
  patch(decoSheet, 'C21', metadata.carton.pcsPerCarton)

  const toolRows = [
    ...Array.from({ length: 44 }, (_, index) => 14 + index),
    ...Array.from({ length: 8 + extraToolRows }, (_, index) => 60 + index),
  ]
  const toolInjectionRows = data.injectionRows
  const toolProcessRows = templateMoldingProcessRows(data)
  const toolMoldingCosts = [
    ...toolInjectionRows.map((item) => item.moldingCostHkd),
    ...toolProcessRows.map((item) => item.costHkd),
  ]
  const materialCostTotal = sumBy(data.injectionRows, (item) => item.materialCostHkd)
  const moldingCostTotal = sumBy(toolMoldingCosts, (item) => item)

  toolRows.forEach((rowNumber) => {
    clear(toolSheet, rowNumber, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 15, 17])
    formula(toolSheet, `L${rowNumber}`, null, `IF(OR(K${rowNumber}=0,K${rowNumber}>14),"",VLOOKUP(K${rowNumber},Summary!$C$40:$D$53,2))`)
    formula(toolSheet, `N${rowNumber}`, 0, caixingToolMaterialFormula(rowNumber, 40))
    formula(toolSheet, `Q${rowNumber}`, 0, caixingToolProcessFormula(rowNumber, 40))
  })

  toolInjectionRows.forEach((item, index) => {
    const rowNumber = toolRows[index]
    const lineNo = /^\d+$/.test(item.lineNo) ? Number(item.lineNo) : item.lineNo || index + 1
    patch(toolSheet, `A${rowNumber}`, lineNo)
    patch(toolSheet, `B${rowNumber}`, item.processType ?? 'IN')
    patch(toolSheet, `C${rowNumber}`, item.toolNo || null)
    patch(toolSheet, `E${rowNumber}`, item.customerMoldCostHkd || item.moldCostHkd || null, 508)
    patch(toolSheet, `F${rowNumber}`, item.name)
    patch(toolSheet, `G${rowNumber}`, item.skuNo || metadata.itemNo)
    patch(toolSheet, `H${rowNumber}`, item.cavities || item.partsPerShot || 1)
    patch(toolSheet, `I${rowNumber}`, item.up || item.setsPerShot || 1)
    patch(toolSheet, `J${rowNumber}`, item.weightG || null)
    patch(toolSheet, `K${rowNumber}`, item.materialCode || (item.material ? getTemplateMaterialCode(item.material) : null))
    patch(toolSheet, `L${rowNumber}`, item.displayMaterial || null)
    patch(toolSheet, `M${rowNumber}`, item.color || null)
    if (metadata.sourceSheetName === 'P4 v2') formula(toolSheet, `N${rowNumber}`, item.materialCostHkd, caixingToolMaterialFormula(rowNumber, 40))
    else patch(toolSheet, `N${rowNumber}`, item.materialCostHkd)
    patch(toolSheet, `O${rowNumber}`, item.processType && item.processType !== 'IN' ? item.processType : item.machineTons || null)
    patch(toolSheet, `P${rowNumber}`, item.cycleSeconds || null)
    if (metadata.sourceSheetName === 'P4 v2') formula(toolSheet, `Q${rowNumber}`, item.moldingCostHkd, caixingToolProcessFormula(rowNumber, 40))
    else patch(toolSheet, `Q${rowNumber}`, item.moldingCostHkd)
  })

  toolProcessRows.forEach((item, index) => {
    const rowNumber = toolRows[toolInjectionRows.length + index]
    patch(toolSheet, `A${rowNumber}`, toolInjectionRows.length + index + 1)
    patch(toolSheet, `B${rowNumber}`, item.processCode)
    patch(toolSheet, `F${rowNumber}`, item.description)
    patch(toolSheet, `G${rowNumber}`, metadata.itemNo)
    patch(toolSheet, `H${rowNumber}`, 1)
    patch(toolSheet, `I${rowNumber}`, 1)
    patch(toolSheet, `Q${rowNumber}`, item.costHkd)
  })

  formula(toolSheet, 'J58', sumBy(toolInjectionRows.slice(0, 44), (item) => item.weightG), 'SUM(J14:J57)')
  formula(toolSheet, 'N58', sumBy(toolInjectionRows.slice(0, 44), (item) => item.materialCostHkd), 'SUM(N14:N57)')
  formula(toolSheet, 'Q58', sumBy(toolMoldingCosts.slice(0, 44), (item) => item), 'SUM(Q14:Q57)')
  formula(toolSheet, `J${secondToolSubtotalRow}`, sumBy(toolInjectionRows.slice(44), (item) => item.weightG), `SUM(J60:J${secondToolLastRow})`)
  formula(toolSheet, `N${secondToolSubtotalRow}`, sumBy(toolInjectionRows.slice(44), (item) => item.materialCostHkd), `SUM(N60:N${secondToolLastRow})`)
  formula(toolSheet, `Q${secondToolSubtotalRow}`, sumBy(toolMoldingCosts.slice(44), (item) => item), `SUM(Q60:Q${secondToolLastRow})`)
  formula(toolSheet, `N${toolTotalRow}`, materialCostTotal, `N58+N${secondToolSubtotalRow}`)
  formula(toolSheet, `Q${toolTotalRow}`, moldingCostTotal, `Q58+Q${secondToolSubtotalRow}`)

  const patchPurchasedSection = (
    sheetName: string,
    startRow: number,
    endRow: number,
    totalCell: string,
    totalFormula: string,
    rows: CaixingCostRow[],
    scrapRate: number | ((row: CaixingCostRow) => number) = 0,
  ) => {
    if (rows.length > endRow - startRow + 1) throw new Error(`彩星${sheetName}明细超过模板容量，请拆分报价`)
    for (let rowNumber = startRow; rowNumber <= endRow; rowNumber += 1) {
      patch(sheetName, `A${rowNumber}`, rowNumber - startRow + 1)
      clear(sheetName, rowNumber, [1, 2, 3, 4, 6, 7])
      patch(sheetName, `F${rowNumber}`, 'Pc')
      patch(sheetName, `H${rowNumber}`, typeof scrapRate === 'number' ? scrapRate : 0)
      formula(sheetName, `I${rowNumber}`, 0, `E${rowNumber}*G${rowNumber}*(1+H${rowNumber})`)
    }

    rows.slice(0, endRow - startRow + 1).forEach((item, index) => {
      const rowNumber = startRow + index
      const cost = item.customerCostHkd || item.baseCostHkd
      const rowScrap = typeof scrapRate === 'number' ? scrapRate : scrapRate(item)
      patch(sheetName, `A${rowNumber}`, index + 1)
      patch(sheetName, `B${rowNumber}`, item.description)
      patch(sheetName, `E${rowNumber}`, 1)
      patch(sheetName, `F${rowNumber}`, 'Pc')
      patch(sheetName, `G${rowNumber}`, cost)
      patch(sheetName, `H${rowNumber}`, rowScrap)
      formula(sheetName, `I${rowNumber}`, roundMoney(cost * (1 + rowScrap)), `E${rowNumber}*G${rowNumber}*(1+H${rowNumber})`)
    })

    formula(sheetName, totalCell, sumBy(rows, (item) => costRowAmount(item) * (1 + (typeof scrapRate === 'number' ? scrapRate : scrapRate(item)))), totalFormula)
  }

  patchPurchasedSection(electSheet, 8, 18, 'I19', 'SUM(I8:I18)', specialRows, caixingScrapRate(pricing, 'plastic', 'special'))
  patchPurchasedSection(electSheet, 21, 88, 'I89', 'SUM(I21:I88)', electronicRows, caixingScrapRate(pricing, 'plastic', 'electronic'))
  patchPurchasedSection(purchaseSheet, 8, 25, 'I26', 'SUM(I8:I25)', purchaseRows, pricingRate(pricing, 'plastic_scrap_rate', CAIXING_PLASTIC_SCRAP_RATE))
  patchPurchasedSection(fabricSheet, 8, 30, 'I31', 'SUM(I8:I30)', fabricRows, (row) => caixingScrapRate(pricing, 'plastic', 'fabric', row.costKind))

  const nonCartonPackingRows = packingRows.filter((row) => !isCartonCostRow(row))
  const packingDataRows = CAIXING_PLASTIC_PACKING_SLOTS.map((slot) => slot.rowNumber)

  packingDataRows.forEach((rowNumber) => {
    clear(packingSheet, rowNumber, [2, 3, 4, 5, 6, 7, 8, 9, 11, 12])
    patch(packingSheet, `K${rowNumber}`, 'Pc')
    patch(packingSheet, `M${rowNumber}`, pricingRate(pricing, 'plastic_scrap_rate', CAIXING_PLASTIC_SCRAP_RATE))
    formula(packingSheet, `N${rowNumber}`, 0, `L${rowNumber}*J${rowNumber}*(1+M${rowNumber})`)
  })

  assignPackingTemplateRows(nonCartonPackingRows, CAIXING_PLASTIC_PACKING_SLOTS).forEach(({ item, rowNumber }) => {
    const cost = item.customerCostHkd || item.baseCostHkd
    patch(packingSheet, `C${rowNumber}`, item.description)
    patch(packingSheet, `J${rowNumber}`, 1)
    patch(packingSheet, `K${rowNumber}`, 'Pc')
    patch(packingSheet, `L${rowNumber}`, cost)
    patch(packingSheet, `M${rowNumber}`, pricingRate(pricing, 'plastic_scrap_rate', CAIXING_PLASTIC_SCRAP_RATE))
    formula(packingSheet, `N${rowNumber}`, roundMoney(cost * (1 + pricingRate(pricing, 'plastic_scrap_rate', CAIXING_PLASTIC_SCRAP_RATE))), `L${rowNumber}*J${rowNumber}*(1+M${rowNumber})`)
  })

  patch(packingSheet, 'C25', null)
  patch(packingSheet, 'G25', metadata.carton.height || null)
  patch(packingSheet, 'H25', metadata.carton.length || null)
  patch(packingSheet, 'I25', metadata.carton.width || null)
  patch(packingSheet, 'J25', metadata.carton.pcsPerCarton ? 1 / metadata.carton.pcsPerCarton : null)
  patch(packingSheet, 'K25', 'Pc')
  patch(packingSheet, 'L25', metadata.carton.cartonPrice || null)
  patch(packingSheet, 'M25', pricingRate(pricing, 'plastic_scrap_rate', CAIXING_PLASTIC_SCRAP_RATE))
  formula(
    packingSheet,
    'N25',
    metadata.carton.pcsPerCarton ? roundMoney(metadata.carton.cartonPrice / metadata.carton.pcsPerCarton * (1 + pricingRate(pricing, 'plastic_scrap_rate', CAIXING_PLASTIC_SCRAP_RATE))) : 0,
    'L25*J25*(1+M25)',
  )
  formula(packingSheet, 'N53', summary.material.packagingMaterial, 'SUM(N7:N52)')

  return patchesBySheet
}

function buildPlushTemplatePatches(data: CaixingQuoteData, decoNumberStyles?: number[], pricing?: CustomerPricingSettings) {
  if (templateToolPlanRowCount(data) > 51) throw new Error('彩星车衣 Tool Plan 含附加工序超过当前模板的 51 行容量')
  const patchesBySheet: Record<string, CaixingTemplateCellPatch[]> = {
    [CAIXING_PLUSH_TEMPLATE_SHEETS.deco]: [],
    [CAIXING_PLUSH_TEMPLATE_SHEETS.summary]: [],
    [CAIXING_PLUSH_TEMPLATE_SHEETS.toolPlan]: [],
    [CAIXING_PLUSH_TEMPLATE_SHEETS.elect]: [],
    [CAIXING_PLUSH_TEMPLATE_SHEETS.purchase]: [],
    [CAIXING_PLUSH_TEMPLATE_SHEETS.fabric]: [],
    [CAIXING_PLUSH_TEMPLATE_SHEETS.packing]: [],
  }
  const patch = (sheetName: string, ref: string, value: XlsxCellValue, style?: number) => {
    patchesBySheet[sheetName].push({ ref, value, style })
  }
  const formula = (sheetName: string, ref: string, value: XlsxCellValue, formulaText: string, style?: number) => {
    patchesBySheet[sheetName].push({ ref, value, formula: formulaText, style })
  }
  const ref = (columnIndex: number, rowNumber: number) => `${templateColumnIndexToName(columnIndex)}${rowNumber}`
  const clear = (sheetName: string, rowNumber: number, columnIndexes: number[]) => {
    columnIndexes.forEach((columnIndex) => patch(sheetName, ref(columnIndex, rowNumber), null))
  }
  const { metadata, summary } = data
  const { specialRows, electronicRows, packingRows, fabricRows, purchaseRows } = getCaixingGroupedCostRows(data)
  const summarySheet = CAIXING_PLUSH_TEMPLATE_SHEETS.summary
  const toolSheet = CAIXING_PLUSH_TEMPLATE_SHEETS.toolPlan
  const electSheet = CAIXING_PLUSH_TEMPLATE_SHEETS.elect
  const purchaseSheet = CAIXING_PLUSH_TEMPLATE_SHEETS.purchase
  const packingSheet = CAIXING_PLUSH_TEMPLATE_SHEETS.packing
  const fabricSheet = CAIXING_PLUSH_TEMPLATE_SHEETS.fabric
  const decoSheet = CAIXING_PLUSH_TEMPLATE_SHEETS.deco
  const quoteDateSerial = excelDateSerial(metadata.quoteDate)
  const finalCost = (value: number, group: 'special' | 'electronic' | 'standard' = 'standard') => roundMoney(value * (1 + caixingMarkupRate(pricing, 'plush', group, metadata.markupRateOverride)))
  const materialFinalTotal = roundMoney(
    (summary.material.plasticParts + summary.material.purchasePart + summary.material.packagingMaterial + summary.material.fabric) * (1 + summary.markupRate)
      + summary.material.specialMaterial * (1 + caixingMarkupRate(pricing, 'plush', 'special', metadata.markupRateOverride))
      + summary.material.electronicMaterial * (1 + caixingMarkupRate(pricing, 'plush', 'electronic', metadata.markupRateOverride)),
  )
  const pct = (value: number) => summary.exFactoryHkd ? round(value / summary.exFactoryHkd, 6) : 0

  patchCaixingToolRates(data, patch, summarySheet)

  patch(summarySheet, 'B3', metadata.itemNo)
  patch(summarySheet, 'B4', metadata.itemNo)
  patch(summarySheet, 'B5', metadata.itemName)
  formula(summarySheet, 'B6', metadata.carton.cube, 'IF(Packing!J24=0,"",Packing!G24*Packing!H24*Packing!I24/1728)')
  formula(summarySheet, 'B7', metadata.carton.pcsPerCarton, 'IF(Packing!J24=0,"",1/Packing!J24)')
  patch(summarySheet, 'G5', quoteDateSerial)
  patch(summarySheet, 'H60', pricingRate(pricing, 'hkd_usd', 7.8))
  patch(summarySheet, 'H61', caixingOptionalRate(pricing, 'hkd_cny', 1.199))
  patch(summarySheet, 'A62', caixingMoqText(pricing))
  patch(summarySheet, 'F36', pricingRate(pricing, 'domestic_freight_rate', 2.11))
  patch(summarySheet, 'F38', pricingRate(pricing, 'fob_freight_rate', 5.93))

  ;[
    ['E11', summary.material.plasticParts, "'Tool Plan'!N67"],
    ['E12', summary.material.specialMaterial, 'Elect!I19'],
    ['E13', summary.material.electronicMaterial, 'Elect!I89'],
    ['E14', summary.material.purchasePart, 'Purchase!I32'],
    ['E15', summary.material.packagingMaterial, 'Packing!$N$54'],
    ['E16', summary.material.fabric, 'Fabric!I41'],
  ].forEach(([cellRef, value, formulaText]) => {
    formula(summarySheet, cellRef as string, value as number, formulaText as string)
  })

  for (let rowNumber = 11; rowNumber <= 16; rowNumber += 1) {
    const base = toNumber(rowNumber === 11 ? summary.material.plasticParts
      : rowNumber === 12 ? summary.material.specialMaterial
        : rowNumber === 13 ? summary.material.electronicMaterial
          : rowNumber === 14 ? summary.material.purchasePart
            : rowNumber === 15 ? summary.material.packagingMaterial
              : summary.material.fabric)
    const group = rowNumber === 12 ? 'special' : rowNumber === 13 ? 'electronic' : 'standard'
    patch(summarySheet, `F${rowNumber}`, caixingMarkupRate(pricing, 'plush', group, metadata.markupRateOverride))
    formula(summarySheet, `G${rowNumber}`, finalCost(base, group), `E${rowNumber}*(1+F${rowNumber})`)
    formula(summarySheet, `H${rowNumber}`, pct(finalCost(base, group)), `IF(G$33=0,"",G${rowNumber}/G$33)`)
  }

  formula(summarySheet, 'E17', summary.material.total, 'SUM(E11:E16)')
  formula(summarySheet, 'G17', materialFinalTotal, 'SUM(G11:G16)')
  formula(summarySheet, 'H17', pct(materialFinalTotal), 'IF(G$33=0,"",G17/G$33)')
  formula(
    summarySheet,
    'E19',
    summary.process.moldingCasting,
    `SUMIF('Tool Plan'!B14:B58,"<>BL",'Tool Plan'!Q14:Q58)+SUMIF('Tool Plan'!B60:B65,"<>BL",'Tool Plan'!Q60:Q65)`,
  )
  const processBaseByRow = new Map<number, number>([
    [19, summary.process.moldingCasting],
    [20, summary.process.spraying],
    [21, summary.process.tampo],
    [22, summary.process.specialOffer],
    [23, summary.process.assemblyLabor],
    [24, 0],
    [25, 0],
    [26, 0],
    [27, summary.process.packoutLabor],
    [28, 0],
    [29, summary.process.rootingHair],
    [30, summary.process.sewingHandfinish],
  ])

  for (let rowNumber = 20; rowNumber <= 30; rowNumber += 1) {
    const base = processBaseByRow.get(rowNumber) ?? 0
    patch(summarySheet, `C${rowNumber}`, base ? 1 : null)
    patch(summarySheet, `D${rowNumber}`, base || null)
    formula(summarySheet, `E${rowNumber}`, base, `C${rowNumber}*D${rowNumber}`)
  }

  for (let rowNumber = 19; rowNumber <= 30; rowNumber += 1) {
    const base = processBaseByRow.get(rowNumber) ?? 0
    patch(summarySheet, `F${rowNumber}`, summary.markupRate)
    formula(summarySheet, `G${rowNumber}`, finalCost(base), `E${rowNumber}*(1+F${rowNumber})`)
    formula(summarySheet, `H${rowNumber}`, pct(finalCost(base)), `IF(G$33=0,"",G${rowNumber}/G$33)`)
  }

  formula(summarySheet, 'E31', summary.process.total, 'SUM(E18:E30)')
  formula(summarySheet, 'G31', finalCost(summary.process.total), 'SUM(G18:G30)')
  formula(summarySheet, 'H31', pct(finalCost(summary.process.total)), 'IF(G$33=0,"",G31/G$33)')
  formula(summarySheet, 'E33', summary.material.total + summary.process.total, 'E17+E31')
  formula(summarySheet, 'G33', summary.exFactoryHkd, 'ROUND(G17+G31,2)')
  formula(summarySheet, 'G34', summary.exFactoryUsd, 'ROUND(G33/$H$60,3)')
  formula(summarySheet, 'G36', summary.domesticTransportationHkd, 'IF(B6=""," ",F36*B6/B7)')
  formula(summarySheet, 'H36', pct(summary.domesticTransportationHkd), 'IF(B6="","",G36/G$33)')
  formula(summarySheet, 'G38', summary.fobTransportationHkd, 'IF(B6=""," ",F38*B6/B7)')
  formula(summarySheet, 'H38', pct(summary.fobTransportationHkd), 'IF(B6="","",G38/G$33)')

  patch(decoSheet, 'C17', metadata.carton.length, decoNumberStyles?.[0])
  patch(decoSheet, 'C18', metadata.carton.width, decoNumberStyles?.[1])
  patch(decoSheet, 'C19', metadata.carton.height, decoNumberStyles?.[2])
  patch(decoSheet, 'C21', metadata.carton.pcsPerCarton, decoNumberStyles?.[3])

  const toolRows = [
    ...Array.from({ length: 45 }, (_, index) => 14 + index),
    ...Array.from({ length: 6 }, (_, index) => 60 + index),
  ]
  const toolInjectionRows = data.injectionRows
  const toolProcessRows = templateMoldingProcessRows(data)
  const toolMoldingCosts = [
    ...toolInjectionRows.map((item) => item.moldingCostHkd),
    ...toolProcessRows.map((item) => item.costHkd),
  ]
  const materialCostTotal = sumBy(data.injectionRows, (item) => item.materialCostHkd)
  const moldingCostTotal = sumBy(toolMoldingCosts, (item) => item)

  toolRows.forEach((rowNumber) => {
    clear(toolSheet, rowNumber, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 15, 17])
    formula(toolSheet, `L${rowNumber}`, null, `IF(OR(K${rowNumber}=0,K${rowNumber}>14),"",VLOOKUP(K${rowNumber},Summary!$C$44:$D$57,2))`)
    formula(toolSheet, `N${rowNumber}`, 0, caixingToolMaterialFormula(rowNumber, 44))
    formula(toolSheet, `Q${rowNumber}`, 0, caixingToolProcessFormula(rowNumber, 44))
  })

  toolInjectionRows.forEach((item, index) => {
    const rowNumber = toolRows[index]
    const lineNo = /^\d+$/.test(item.lineNo) ? Number(item.lineNo) : item.lineNo || index + 1
    patch(toolSheet, `A${rowNumber}`, lineNo)
    patch(toolSheet, `B${rowNumber}`, item.processType ?? 'IN')
    patch(toolSheet, `C${rowNumber}`, item.toolNo || null)
    patch(toolSheet, `E${rowNumber}`, item.customerMoldCostHkd || item.moldCostHkd || null, 533)
    patch(toolSheet, `F${rowNumber}`, item.name)
    patch(toolSheet, `G${rowNumber}`, item.skuNo || metadata.itemNo)
    patch(toolSheet, `H${rowNumber}`, item.cavities || item.partsPerShot || 1)
    patch(toolSheet, `I${rowNumber}`, item.up || item.setsPerShot || 1)
    patch(toolSheet, `J${rowNumber}`, item.weightG || null)
    patch(toolSheet, `K${rowNumber}`, item.materialCode || (item.material ? getTemplateMaterialCode(item.material, 'plush') : null))
    patch(toolSheet, `L${rowNumber}`, item.displayMaterial || null)
    patch(toolSheet, `M${rowNumber}`, item.color || null)
    if (metadata.sourceSheetName === 'P4 v2') formula(toolSheet, `N${rowNumber}`, item.materialCostHkd, caixingToolMaterialFormula(rowNumber, 44))
    else patch(toolSheet, `N${rowNumber}`, item.materialCostHkd)
    patch(toolSheet, `O${rowNumber}`, item.processType && item.processType !== 'IN' ? item.processType : item.machineTons || null)
    patch(toolSheet, `P${rowNumber}`, item.cycleSeconds || null)
    if (metadata.sourceSheetName === 'P4 v2') formula(toolSheet, `Q${rowNumber}`, item.moldingCostHkd, caixingToolProcessFormula(rowNumber, 44))
    else patch(toolSheet, `Q${rowNumber}`, item.moldingCostHkd)
  })

  toolProcessRows.forEach((item, index) => {
    const rowNumber = toolRows[toolInjectionRows.length + index]
    patch(toolSheet, `A${rowNumber}`, toolInjectionRows.length + index + 1)
    patch(toolSheet, `B${rowNumber}`, item.processCode)
    patch(toolSheet, `F${rowNumber}`, item.description)
    patch(toolSheet, `G${rowNumber}`, metadata.itemNo)
    patch(toolSheet, `H${rowNumber}`, 1)
    patch(toolSheet, `I${rowNumber}`, 1)
    patch(toolSheet, `Q${rowNumber}`, item.costHkd)
  })

  formula(toolSheet, 'J59', sumBy(toolInjectionRows.slice(0, 45), (item) => item.weightG), 'SUM(J14:J58)')
  formula(toolSheet, 'N59', sumBy(toolInjectionRows.slice(0, 45), (item) => item.materialCostHkd), 'SUM(N14:N58)')
  formula(toolSheet, 'Q59', sumBy(toolMoldingCosts.slice(0, 45), (item) => item), 'SUM(Q14:Q58)')
  formula(toolSheet, 'J66', sumBy(toolInjectionRows.slice(45, 51), (item) => item.weightG), 'SUM(J60:J65)')
  formula(toolSheet, 'N66', sumBy(toolInjectionRows.slice(45, 51), (item) => item.materialCostHkd), 'SUM(N60:N65)')
  formula(toolSheet, 'Q66', sumBy(toolMoldingCosts.slice(45, 51), (item) => item), 'SUM(Q60:Q65)')
  formula(toolSheet, 'N67', materialCostTotal, 'N59+N66')
  formula(toolSheet, 'Q67', moldingCostTotal, 'Q59+Q66')

  const patchPurchasedSection = (
    sheetName: string,
    startRow: number,
    endRow: number,
    totalCell: string,
    totalFormula: string,
    rows: CaixingCostRow[],
    scrapRate: number | ((row: CaixingCostRow) => number) = 0,
  ) => {
    if (rows.length > endRow - startRow + 1) throw new Error(`彩星${sheetName}明细超过模板容量，请拆分报价`)
    for (let rowNumber = startRow; rowNumber <= endRow; rowNumber += 1) {
      patch(sheetName, `A${rowNumber}`, rowNumber - startRow + 1)
      clear(sheetName, rowNumber, [1, 2, 3, 4, 6, 7])
      patch(sheetName, `F${rowNumber}`, 'Pc')
      formula(sheetName, `I${rowNumber}`, 0, `E${rowNumber}*G${rowNumber}*(1+H${rowNumber})`)
    }

    rows.slice(0, endRow - startRow + 1).forEach((item, index) => {
      const rowNumber = startRow + index
      const cost = item.customerCostHkd || item.baseCostHkd
      const rowScrap = typeof scrapRate === 'number' ? scrapRate : scrapRate(item)
      patch(sheetName, `A${rowNumber}`, index + 1)
      patch(sheetName, `B${rowNumber}`, item.description)
      patch(sheetName, `E${rowNumber}`, 1)
      patch(sheetName, `F${rowNumber}`, 'Pc')
      patch(sheetName, `G${rowNumber}`, cost)
      patch(sheetName, `H${rowNumber}`, rowScrap)
      formula(sheetName, `I${rowNumber}`, roundMoney(cost * (1 + rowScrap)), `E${rowNumber}*G${rowNumber}*(1+H${rowNumber})`)
    })

    formula(sheetName, totalCell, sumBy(rows, (item) => costRowAmount(item) * (1 + (typeof scrapRate === 'number' ? scrapRate : scrapRate(item)))), totalFormula)
  }

  patchPurchasedSection(electSheet, 8, 18, 'I19', 'SUM(I8:I18)', specialRows, caixingScrapRate(pricing, 'plush', 'special'))
  patchPurchasedSection(electSheet, 21, 88, 'I89', 'SUM(I21:I88)', electronicRows, caixingScrapRate(pricing, 'plush', 'electronic'))
  patchPurchasedSection(purchaseSheet, 8, 31, 'I32', 'SUM(I8:I31)', purchaseRows, caixingScrapRate(pricing, 'plush', 'purchase'))
  patchPurchasedSection(fabricSheet, 8, 40, 'I41', 'SUM(I8:I40)', fabricRows, (row) => caixingScrapRate(pricing, 'plush', 'fabric', row.costKind))

  const cartonDescription = (row: CaixingCostRow) => /外箱|纸箱|Carton/i.test(`${row.category} ${row.description}`)
  const nonCartonPackingRows = packingRows.filter((row) => !cartonDescription(row))
  const packingDataRows = CAIXING_PLUSH_PACKING_SLOTS.map((slot) => slot.rowNumber)

  packingDataRows.forEach((rowNumber) => {
    clear(packingSheet, rowNumber, [2, 3, 4, 5, 6, 7, 8, 9, 11, 12])
    patch(packingSheet, `K${rowNumber}`, 'Pc')
    formula(packingSheet, `N${rowNumber}`, 0, `L${rowNumber}*J${rowNumber}*(1+M${rowNumber})`)
  })

  assignPackingTemplateRows(nonCartonPackingRows, CAIXING_PLUSH_PACKING_SLOTS).forEach(({ item, rowNumber }) => {
    const cost = item.customerCostHkd || item.baseCostHkd
    patch(packingSheet, `C${rowNumber}`, item.description)
    patch(packingSheet, `J${rowNumber}`, 1)
    patch(packingSheet, `K${rowNumber}`, 'Pc')
    patch(packingSheet, `L${rowNumber}`, cost)
    const scrapRate = caixingScrapRate(pricing, 'plush', 'packing')
    patch(packingSheet, `M${rowNumber}`, scrapRate)
    formula(packingSheet, `N${rowNumber}`, roundMoney(cost * (1 + scrapRate)), `L${rowNumber}*J${rowNumber}*(1+M${rowNumber})`)
  })

  patch(packingSheet, 'C24', null)
  patch(packingSheet, 'G24', metadata.carton.height || null)
  patch(packingSheet, 'H24', metadata.carton.length || null)
  patch(packingSheet, 'I24', metadata.carton.width || null)
  patch(packingSheet, 'J24', metadata.carton.pcsPerCarton ? 1 / metadata.carton.pcsPerCarton : null)
  patch(packingSheet, 'K24', 'Pc')
  patch(packingSheet, 'L24', metadata.carton.cartonPrice || null)
  patch(packingSheet, 'M24', caixingScrapRate(pricing, 'plush', 'carton'))
  formula(
    packingSheet,
    'N24',
    metadata.carton.pcsPerCarton ? roundMoney(metadata.carton.cartonPrice / metadata.carton.pcsPerCarton * (1 + caixingScrapRate(pricing, 'plush', 'carton'))) : 0,
    'L24*J24*(1+M24)',
  )
  formula(packingSheet, 'N54', summary.material.packagingMaterial, 'SUM(N7:N53)')

  return patchesBySheet
}

function cell(value: XlsxCellValue, style: number = XLSX_STYLE.border): XlsxCellInput {
  return { value, style }
}

function ensureRow(rows: XlsxCellInput[][], rowNumber: number) {
  const rowIndex = rowNumber - 1
  rows[rowIndex] = rows[rowIndex] ?? []
  return rows[rowIndex]
}

function setCell(rows: XlsxCellInput[][], rowNumber: number, columnIndex: number, value: XlsxCellValue, style: number = XLSX_STYLE.border) {
  ensureRow(rows, rowNumber)[columnIndex] = cell(value, style)
}

function setNumber(rows: XlsxCellInput[][], rowNumber: number, columnIndex: number, value: number, style: number = XLSX_STYLE.number3) {
  setCell(rows, rowNumber, columnIndex, roundMoney(value), style)
}

interface SummaryLine {
  label: string
  note?: string
  count?: XlsxCellValue
  rate?: XlsxCellValue
  basic: number
}

function setSummaryLine(rows: XlsxCellInput[][], rowNumber: number, line: SummaryLine, markupRate: number, finalTotal: number) {
  const finalCost = roundMoney(line.basic * (1 + markupRate))
  setCell(rows, rowNumber, 0, line.label)
  setCell(rows, rowNumber, 2, line.note ?? 'Refer to attached breakdown')
  if (line.count !== undefined) setCell(rows, rowNumber, 2, line.count)
  if (line.rate !== undefined) setCell(rows, rowNumber, 3, line.rate)
  setNumber(rows, rowNumber, 4, line.basic)
  setNumber(rows, rowNumber, 5, markupRate)
  setNumber(rows, rowNumber, 6, finalCost)
  setNumber(rows, rowNumber, 7, finalTotal ? finalCost / finalTotal : 0)
}

function buildSummarySheet(data: CaixingQuoteData, pricing?: CustomerPricingSettings): XlsxOutputSheet {
  const rows: XlsxCellInput[][] = []
  const { metadata, summary } = data
  const materialLines: SummaryLine[] = [
    { label: 'Plastic Parts ', basic: summary.material.plasticParts },
    { label: 'Special Material', basic: summary.material.specialMaterial },
    { label: 'Electronic Material', basic: summary.material.electronicMaterial },
    { label: 'Purchase Part', basic: summary.material.purchasePart },
    { label: 'Packaging Material', basic: summary.material.packagingMaterial },
    { label: 'Fabric', basic: summary.material.fabric },
  ]
  const processLines: SummaryLine[] = data.metadata.productType === 'plush'
    ? [
        { label: 'Molding & Casting', basic: summary.process.moldingCasting },
        { label: 'Spraying', basic: summary.process.spraying },
        { label: 'Tampo', basic: summary.process.tampo },
        { label: 'Assembly labor', basic: summary.process.assemblyLabor },
        { label: 'Packout Labor', basic: summary.process.packoutLabor },
        { label: 'Hair Rooting', basic: summary.process.rootingHair },
        { label: 'Sewing / Handfinish', basic: summary.process.sewingHandfinish },
        { label: 'Special offer', basic: summary.process.specialOffer },
      ]
    : [
        { label: 'Molding & Casting', basic: summary.process.moldingCasting },
        { label: 'Spraying', basic: summary.process.spraying },
        { label: 'Tampo Printing', basic: summary.process.tampo },
        { label: 'Assembly labor', basic: summary.process.assemblyLabor },
        { label: 'Packout Labor', basic: summary.process.packoutLabor },
        { label: 'Rooting Hair', basic: summary.process.rootingHair },
        { label: 'Sewing / Handfinish', basic: summary.process.sewingHandfinish },
        { label: 'Special offer', basic: summary.process.specialOffer },
      ]
  const finalTotal = roundMoney((summary.material.total + summary.process.total) * (1 + summary.markupRate))

  setCell(rows, 1, 0, 'VENDOR QUOTATION', XLSX_STYLE.title)
  setCell(rows, 3, 0, 'ITEM No : ')
  setCell(rows, 3, 1, metadata.itemNo)
  setCell(rows, 3, 5, 'Vendor : ')
  setCell(rows, 3, 6, 'Royal Regent Products (H.K.) Limited')
  setCell(rows, 4, 0, 'Product Line : ')
  setCell(rows, 4, 1, metadata.itemNo)
  setCell(rows, 4, 5, 'Product Type : ')
  setCell(rows, 4, 6, metadata.productTypeName)
  setCell(rows, 5, 0, 'Item Description : ')
  setCell(rows, 5, 1, metadata.itemName)
  setCell(rows, 5, 5, 'Date : ')
  setCell(rows, 5, 6, excelDateSerial(metadata.quoteDate), XLSX_STYLE.date)
  setCell(rows, 6, 0, 'Cu.Ft. / Shipper : ')
  setNumber(rows, 6, 1, metadata.carton.cube)
  setCell(rows, 6, 2, 'base on packaging')
  setCell(rows, 6, 5, 'Mfg Location : ')
  setCell(rows, 6, 6, 'Heyuan city, Guangdong province, China')
  setCell(rows, 7, 0, 'Pcs / Shipper : ')
  setNumber(rows, 7, 1, metadata.carton.pcsPerCarton || 0, XLSX_STYLE.number0)
  setCell(rows, 7, 5, 'Quoted by : ')

  ;['Costing Item', '', 'No. of part per Toy', 'Rate (HK$)', 'Basic Cost (HK$)', 'Fty OH & M/U (%)', 'Final Cost (HK$)', 'Pct of Ex-Fty (%)'].forEach((label, index) => {
    setCell(rows, 9, index, label, XLSX_STYLE.boldBorder)
  })

  materialLines.forEach((line, index) => setSummaryLine(rows, 11 + index, line, summary.markupRate, finalTotal))
  setCell(rows, 17, 3, 'TOTAL MATERIAL COST : ', XLSX_STYLE.boldBorder)
  setNumber(rows, 17, 4, summary.material.total, XLSX_STYLE.number3Bold)
  setNumber(rows, 17, 6, summary.material.total * (1 + summary.markupRate), XLSX_STYLE.number3Bold)

  const processStart = 19
  processLines.forEach((line, index) => setSummaryLine(rows, processStart + index, line, summary.markupRate, finalTotal))

  const totalProcessRow = processStart + processLines.length + 1
  setCell(rows, totalProcessRow, 3, 'TOTAL PROCESS COST : ', XLSX_STYLE.boldBorder)
  setNumber(rows, totalProcessRow, 4, summary.process.total, XLSX_STYLE.number3Bold)
  setNumber(rows, totalProcessRow, 6, summary.process.total * (1 + summary.markupRate), XLSX_STYLE.number3Bold)

  const exFactoryRow = totalProcessRow + 2
  setCell(rows, exFactoryRow, 3, 'EX-FACTORY COST : ', XLSX_STYLE.boldBorder)
  setNumber(rows, exFactoryRow, 4, summary.material.total + summary.process.total, XLSX_STYLE.number3Bold)
  setNumber(rows, exFactoryRow, 6, summary.exFactoryHkd, XLSX_STYLE.number3Bold)
  setCell(rows, exFactoryRow + 1, 3, 'EX-FACTORY COST US$ : ', XLSX_STYLE.boldBorder)
  setNumber(rows, exFactoryRow + 1, 6, summary.exFactoryUsd, XLSX_STYLE.number3Bold)

  setCell(rows, exFactoryRow + 3, 0, 'FOR PLAYMATES TOYS REFERENCE ONLY :', XLSX_STYLE.bold)
  setCell(rows, exFactoryRow + 4, 4, 'Domestic Transportation Cost to Port @ Rate (HK$/Cu.Ft.) :')
  setNumber(rows, exFactoryRow + 4, 5, pricingRate(pricing, 'domestic_freight_rate', 2.11))
  setNumber(rows, exFactoryRow + 4, 6, summary.domesticTransportationHkd)
  setCell(rows, exFactoryRow + 5, 4, 'FOB Transportation Cost to Port @ Rate (HK$/Cu.Ft.) :')
  setNumber(rows, exFactoryRow + 5, 5, pricingRate(pricing, 'fob_freight_rate', 5.93))
  setNumber(rows, exFactoryRow + 5, 6, summary.fobTransportationHkd)

  return {
    name: 'Summary',
    rows,
    cols: [24, 16, 24, 14, 14, 14, 14, 14],
    merges: ['A1:H1'],
  }
}

function buildToolPlanSheet(data: CaixingQuoteData): XlsxOutputSheet {
  const rows: XlsxCellInput[][] = []
  setCell(rows, 1, 0, 'TOOL PLAN / PLASTIC PARTS COST', XLSX_STYLE.title)
  setCell(rows, 3, 0, 'Item No')
  setCell(rows, 3, 1, data.metadata.itemNo)
  setCell(rows, 3, 3, 'Description')
  setCell(rows, 3, 4, data.metadata.itemName)

  ;['Ref No.', 'Part Description', 'Material', 'Shot Weight (g)', 'Parts / Toy', 'M/C Size', 'Cycle (sec)', 'Material Cost', 'Molding Cost', 'Tool Cost'].forEach((label, index) => {
    setCell(rows, 5, index, label, XLSX_STYLE.boldBorder)
  })

  data.injectionRows.forEach((item, index) => {
    const rowNumber = 6 + index
    setCell(rows, rowNumber, 0, item.lineNo)
    setCell(rows, rowNumber, 1, item.name)
    setCell(rows, rowNumber, 2, item.displayMaterial)
    setNumber(rows, rowNumber, 3, item.weightG)
    setNumber(rows, rowNumber, 4, item.partsPerShot, XLSX_STYLE.number0)
    setNumber(rows, rowNumber, 5, item.machineTons, XLSX_STYLE.number0)
    setNumber(rows, rowNumber, 6, item.cycleSeconds)
    setNumber(rows, rowNumber, 7, item.materialCostHkd)
    setNumber(rows, rowNumber, 8, item.moldingCostHkd)
    setNumber(rows, rowNumber, 9, item.customerMoldCostHkd || item.moldCostHkd)
  })

  const totalRow = 6 + data.injectionRows.length + 1
  setCell(rows, totalRow, 1, 'TOTAL COST PER TOY :', XLSX_STYLE.boldBorder)
  setNumber(rows, totalRow, 7, sumBy(data.injectionRows, (item) => item.materialCostHkd), XLSX_STYLE.number3Bold)
  setNumber(rows, totalRow, 8, sumBy(data.injectionRows, (item) => item.moldingCostHkd), XLSX_STYLE.number3Bold)

  return {
    name: 'Tool Plan',
    rows,
    cols: [12, 28, 12, 14, 12, 12, 12, 14, 14, 14],
    merges: ['A1:J1'],
  }
}

function buildCostSheet(name: string, title: string, rowsData: CaixingCostRow[], markupRate: number): XlsxOutputSheet {
  const rows: XlsxCellInput[][] = []
  setCell(rows, 1, 0, title, XLSX_STYLE.title)
  ;['Ref No.', 'Description', 'Internal Category', 'Qty per Toy', 'U/M', 'Unit Cost', 'Scrap Allow', 'Cost per Toy'].forEach((label, index) => {
    setCell(rows, 4, index, label, XLSX_STYLE.boldBorder)
  })

  rowsData.forEach((item, index) => {
    const rowNumber = 5 + index
    setNumber(rows, rowNumber, 0, index + 1, XLSX_STYLE.number0)
    setCell(rows, rowNumber, 1, item.description)
    setCell(rows, rowNumber, 2, item.category)
    setNumber(rows, rowNumber, 3, 1, XLSX_STYLE.number0)
    setCell(rows, rowNumber, 4, 'Pc')
    setNumber(rows, rowNumber, 5, item.baseCostHkd)
    setNumber(rows, rowNumber, 6, markupRate)
    setNumber(rows, rowNumber, 7, item.customerCostHkd * (1 + markupRate))
  })

  const totalRow = 5 + rowsData.length + 1
  setCell(rows, totalRow, 6, 'TOTAL COST PER TOY :', XLSX_STYLE.boldBorder)
  setNumber(rows, totalRow, 7, sumBy(rowsData, (item) => item.customerCostHkd * (1 + markupRate)), XLSX_STYLE.number3Bold)

  return {
    name,
    rows,
    cols: [10, 34, 18, 12, 10, 12, 12, 14],
    merges: ['A1:H1'],
  }
}

function buildPackingSheet(data: CaixingQuoteData, rowsData: CaixingCostRow[]): XlsxOutputSheet {
  const sheet = buildCostSheet('Packing', 'PACKING MATERIAL COST', rowsData, data.summary.markupRate)
  const rows = sheet.rows
  const start = rows.length + 3
  setCell(rows, start, 0, 'Carton Info', XLSX_STYLE.boldBorder)
  setCell(rows, start + 1, 0, 'L" (W")')
  setNumber(rows, start + 1, 1, data.metadata.carton.length)
  setCell(rows, start + 2, 0, 'W" (D")')
  setNumber(rows, start + 2, 1, data.metadata.carton.width)
  setCell(rows, start + 3, 0, 'H"')
  setNumber(rows, start + 3, 1, data.metadata.carton.height)
  setCell(rows, start + 4, 0, 'Case Pack')
  setNumber(rows, start + 4, 1, data.metadata.carton.pcsPerCarton, XLSX_STYLE.number0)
  setCell(rows, start + 5, 0, 'CU.FT')
  setNumber(rows, start + 5, 1, data.metadata.carton.cube)

  return sheet
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

function p4RequiredText(value: unknown, message: string) {
  const text = p4Text(value)
  if (!text) throw new Error(`彩星直转被阻断：${message}`)
  return text
}

function p4Positive(value: unknown, message: string) {
  const parsed = p4Number(value)
  if (parsed <= 0) throw new Error(`彩星直转被阻断：${message}`)
  return parsed
}

function p4NonNegative(value: unknown, message: string) {
  const parsed = p4Number(value)
  if (parsed < 0) throw new Error(`彩星直转被阻断：${message}`)
  return parsed
}

function p4Date(value: unknown) {
  const text = p4RequiredText(value, '缺少报价日期')
  const matched = text.match(/^(20\d{2})-(\d{2})-(\d{2})$/)
  if (!matched) throw new Error('彩星直转被阻断：报价日期必须使用 YYYY-MM-DD')
  const result = new Date(Number(matched[1]), Number(matched[2]) - 1, Number(matched[3]))
  if (result.getFullYear() !== Number(matched[1]) || result.getMonth() !== Number(matched[2]) - 1 || result.getDate() !== Number(matched[3])) {
    throw new Error('彩星直转被阻断：报价日期不是有效日期')
  }
  return result
}

function p4SectionCalculationRows(artifact: P4InternalQuoteArtifact, code: P4SectionCode) {
  return p4Rows(artifact.sections[code]?.calculation?.line_breakdown)
}

function p4SectionTotals(artifact: P4InternalQuoteArtifact, code: P4SectionCode) {
  return p4Object(artifact.sections[code]?.calculation?.totals)
}

function p4TaxTag(row: Record<string, unknown>) {
  const rate = p4Number(row.tax_rate_percent)
  if (rate <= 0) return ''
  return `±${Number.isInteger(rate) ? rate : round(rate, 2)}%`
}

function p4CostDescription(row: Record<string, unknown>, fallback: string) {
  const item = p4Text(row.item || row.name || row.process || row.group)
  const specification = p4Text(row.specification || row.position || row.part || row.craft)
  if (item && specification && !item.includes(specification)) return `${item} ${specification}`
  return item || specification || fallback
}

function p4DerivedCostRow(
  row: Record<string, unknown>,
  customerGroup: CaixingCustomerCostGroup | undefined,
  category: string,
  fallbackDescription: string,
  amountField: 'amount_hkd' | 'amount_hkd_pcs' = 'amount_hkd',
) {
  const amount = p4Number(row[amountField])
  if (amount <= 0) return null
  return {
    taxTag: p4TaxTag(row),
    category,
    description: p4CostDescription(row, fallbackDescription),
    baseCostHkd: roundMoney(amount),
    customerCostHkd: roundMoney(amount),
    ...(customerGroup ? { customerGroup } : {}),
  } satisfies CaixingCostRow
}

function p4PrimaryCarton(artifact: P4InternalQuoteArtifact): CaixingCartonProfile {
  const salesPayload = artifact.sections.sales.payload
  const cartonRow = p4Rows(salesPayload.cartons)[0]
  if (!cartonRow) {
    throw new Error('彩星直转被阻断：业务部缺少基础纸箱')
  }
  const length = p4Positive(cartonRow.length_in, '基础纸箱长度必须大于 0')
  const width = p4Positive(cartonRow.width_in, '基础纸箱宽度必须大于 0')
  const height = p4Positive(cartonRow.height_in, '基础纸箱高度必须大于 0')
  const pcsPerCarton = p4Positive(cartonRow.qty_per_carton, '基础纸箱每箱数量必须大于 0')
  const calculatedCarton = p4SectionCalculationRows(artifact, 'sales')
    .find((row) => p4Text(row.kind) === 'carton')
  const cube = p4Number(calculatedCarton?.cuft) || length * width * height / 1728
  const paperPriceFactor = p4Number(salesPayload.paper_price_factor)
    || p4Number(artifact.referenceSnapshot.paper_price_factor)
    || 2.75
  const cartonPrice = p4Number(calculatedCarton?.carton_price_hkd)
    || (length + width + 2) * (width + height + 1) * 2 * paperPriceFactor / 1000

  return {
    length,
    width,
    height,
    cube: p4Positive(cube, '基础纸箱 CU.FT 必须大于 0'),
    cbm: round(length * width * height * 0.000016387064, 4),
    pcsPerCarton,
    cartonPrice: p4Positive(cartonPrice, '基础纸箱价格必须大于 0'),
  }
}

const P4_SALES_PACKAGING_LABELS: Record<string, string> = {
  blister: '吸塑',
  color_box_inner_card: '彩盒/内卡',
  leaflet_manual: '利宝/说明书',
  other_purchase: '其他外购',
}

function p4EngineeringCostRows(artifact: P4InternalQuoteArtifact) {
  return p4SectionCalculationRows(artifact, 'engineering').flatMap((row) => {
    if (p4Text(row.kind) !== 'material' || row.reference_only === true) return []
    const category = p4Text(row.auxiliary_category)
      || (p4Text(row.category) === 'hardware' ? '五金' : '其他外购')
    const costRow = p4DerivedCostRow(
      row,
      p4Text(row.category) === 'packaging' ? 'packing' : undefined,
      category,
      '外购物料',
    )
    return costRow ? [costRow] : []
  })
}

function p4SalesPackagingCostRows(artifact: P4InternalQuoteArtifact) {
  return p4SectionCalculationRows(artifact, 'sales').flatMap((row) => {
    if (p4Text(row.kind) !== 'packaging_material') return []
    const category = P4_SALES_PACKAGING_LABELS[p4Text(row.category)] || p4Text(row.category) || '包装材料'
    const costRow = p4DerivedCostRow(row, 'packing', category, '包装材料')
    return costRow ? [costRow] : []
  })
}

function p4ElectronicCostRows(artifact: P4InternalQuoteArtifact) {
  const componentRows = p4SectionCalculationRows(artifact, 'electronic')
    .filter((row) => p4Text(row.kind) === 'electronic_component' && p4Number(row.amount_hkd) > 0)
  const rawTotal = sumBy(componentRows, (row) => p4Number(row.amount_hkd))
  const authoritativeTotal = p4Number(p4SectionTotals(artifact, 'electronic').total_hkd) || rawTotal
  if (authoritativeTotal <= 0) return []
  if (rawTotal <= 0) {
    return [{
      taxTag: '',
      category: '电子',
      description: '电子报价合计',
      baseCostHkd: roundMoney(authoritativeTotal),
      customerCostHkd: roundMoney(authoritativeTotal),
      customerGroup: 'electronic',
    } satisfies CaixingCostRow]
  }

  let allocated = 0
  return componentRows.map<CaixingCostRow>((row, index) => {
    const baseCostHkd = roundMoney(p4Number(row.amount_hkd))
    const customerCostHkd = index === componentRows.length - 1
      ? roundMoney(authoritativeTotal - allocated)
      : roundMoney(authoritativeTotal * baseCostHkd / rawTotal)
    allocated = roundMoney(allocated + customerCostHkd)
    const description = p4CostDescription(row, '电子零件')
    const isIc = /\bIC\b/i.test(description)
    return {
      taxTag: p4TaxTag(row),
      category: isIc ? 'IC' : '电子',
      description,
      baseCostHkd,
      customerCostHkd,
      customerGroup: isIc ? 'special' : 'electronic',
    }
  })
}

function p4PaintingCostRows(artifact: P4InternalQuoteArtifact) {
  return p4SectionCalculationRows(artifact, 'painting').flatMap((row) => {
    const kind = p4Text(row.kind)
    if (!['painting', 'painting_quick_labor', 'painting_quick_paint', 'painting_quick_paint_tax'].includes(kind)) return []
    const category = kind === 'painting_quick_labor'
      ? '喷油工'
      : kind.includes('paint') ? '油漆' : '喷油'
    const costRow = p4DerivedCostRow(row, 'tampo', category, category)
    return costRow ? [costRow] : []
  })
}

function p4SlushCostRows(artifact: P4InternalQuoteArtifact, productType: CaixingProductType) {
  return p4SectionCalculationRows(artifact, 'slush').flatMap((row) => {
    if (p4Text(row.kind) !== 'slush') return []
    const costRow = p4DerivedCostRow(
      row,
      productType === 'plush' ? 'special' : 'special_offer',
      '搪胶',
      '搪胶',
    )
    return costRow ? [costRow] : []
  })
}

function p4SewingCostRows(artifact: P4InternalQuoteArtifact) {
  const totals = p4SectionTotals(artifact, 'sewing')
  const clothesHkd = p4Number(totals.clothes_hkd)
  const legacyHairHkd = p4Number(totals.hair_hkd)
  const clothesLines = [
    ...p4SectionCalculationRows(artifact, 'sewing'),
    ...p4Rows(artifact.sections.sewing.calculation?.pricing_breakdown),
  ].filter((row) => ['sewing_material', 'sewing_labor', 'sewing_quick'].includes(p4Text(row.kind))
    && (!p4Text(row.category) || p4Text(row.category) === 'clothes'))
  if (clothesLines.some((row) => p4Text(row.kind) === 'sewing_quick' && p4Number(row.amount_hkd) > 0)) {
    throw new Error('彩星直转被阻断：车衣快捷总价缺少材料与人工明细，请改用逐项车缝报价')
  }
  if (clothesHkd > 0 && !clothesLines.length) {
    throw new Error('彩星直转被阻断：车衣合计缺少逐项材料与人工明细')
  }
  const itemized = clothesLines.flatMap((row) => {
    const costRow = p4DerivedCostRow(row, 'fabric', '车衣', '车衣材料')
    return costRow ? [{ ...costRow, costKind: p4Text(row.cost_kind) === 'labor' || p4Text(row.kind) !== 'sewing_material' ? 'labor' as const : 'material' as const }] : []
  })
  const itemizedTotal = sumBy(itemized, (row) => row.customerCostHkd)
  if (Math.abs(itemizedTotal - clothesHkd) > 0.01) throw new Error('彩星直转被阻断：车衣明细金额与已审批车衣合计不一致')
  return [
    ...itemized,
    ...(legacyHairHkd > 0 ? [{
      taxTag: '',
      category: '车发',
      description: '历史车发报价合计',
      baseCostHkd: roundMoney(legacyHairHkd),
      customerCostHkd: roundMoney(legacyHairHkd),
      customerGroup: 'rooting' as const,
    }] : []),
  ]
}

function p4HairCostRows(artifact: P4InternalQuoteArtifact) {
  return p4SectionCalculationRows(artifact, 'hair').flatMap((row) => {
    if (p4Text(row.kind) !== 'hair') return []
    const costRow = p4DerivedCostRow(row, 'rooting', '车发', '车发')
    return costRow ? [costRow] : []
  })
}

function p4AssemblyCostRows(artifact: P4InternalQuoteArtifact) {
  return p4SectionCalculationRows(artifact, 'assembly').flatMap((row) => {
    if (p4Text(row.kind) !== 'assembly_process') return []
    const isPackout = p4Text(row.category) === 'packaging'
    const category = isPackout ? '包装人工' : '装配工'
    const costRow = p4DerivedCostRow(
      row,
      isPackout ? 'packout' : 'assembly',
      category,
      category,
      'amount_hkd_pcs',
    )
    return costRow ? [costRow] : []
  })
}

function p4DerivedCostRows(artifact: P4InternalQuoteArtifact, productType: CaixingProductType) {
  return [
    ...p4EngineeringCostRows(artifact),
    ...p4ElectronicCostRows(artifact),
    ...p4SalesPackagingCostRows(artifact),
    ...p4PaintingCostRows(artifact),
    ...p4SlushCostRows(artifact, productType),
    ...p4SewingCostRows(artifact),
    ...p4HairCostRows(artifact),
    ...p4AssemblyCostRows(artifact),
  ]
}

function p4ToolSourcePrice(row: Record<string, unknown>, processType: string, artifact: P4InternalQuoteArtifact) {
  if (processType !== 'IN' && processType !== 'BL') return undefined
  const sources = p4SectionCalculationRows(artifact, 'molding').filter((source) =>
    p4Text(source.kind) === (processType === 'BL' ? 'blow' : 'injection')
      && p4Number(source.material_price_hkd_lb) > 0
      && normalizeMaterialName(p4Text(source.material)) === normalizeMaterialName(p4Text(row.material)))
  const toolNo = p4Text(row.tool_no).toUpperCase()
  const byTool = toolNo ? sources.filter((source) => p4Text(source.mold_no).toUpperCase() === toolNo) : []
  const name = p4Text(row.description).toUpperCase().replace(/\s+/g, '')
  const byName = name ? (byTool.length ? byTool : sources).filter((source) => p4Text(source.item).toUpperCase().replace(/\s+/g, '') === name) : []
  const weight = p4Number(row.net_weight_g)
  const byWeight = weight > 0 ? (byTool.length ? byTool : sources).filter((source) => Math.abs(p4Number(source.net_weight_g || source.estimated_weight_g) - weight) < 0.001) : []
  return [byName, byTool, byWeight].find((group) => group.length === 1)?.[0]
}

export function convertCaixingP4InternalQuote(
  artifact: P4InternalQuoteArtifact,
  sourceFileName: string,
  pricing?: CustomerPricingSettings,
): CaixingConversionResult {
  assertPricingCustomer(pricing, 'caixing')
  const customerFields = p4Object(artifact.sections.sales.payload.customer_quote_fields)
  const caixing = p4Object(customerFields.caixing)
  const productTypeText = p4RequiredText(caixing.product_type, '缺少塑胶/毛绒产品类型')
  if (productTypeText !== 'plastic' && productTypeText !== 'plush') {
    throw new Error('彩星直转被阻断：产品类型必须是 plastic 或 plush')
  }
  const productType = productTypeText as CaixingProductType
  const itemNo = p4RequiredText(caixing.item_number, '缺少 Item No.')
  const itemName = p4RequiredText(caixing.item_name, '缺少 Item Description')
  const quoteDate = p4Date(caixing.quote_date)
  const overrideValue = caixing.markup_rate_override
  const markupRateOverride = overrideValue === null || overrideValue === undefined || overrideValue === ''
    ? undefined : Number(overrideValue)
  if (markupRateOverride !== undefined && (!Number.isFinite(markupRateOverride) || markupRateOverride < 0 || markupRateOverride > 1)) {
    throw new Error('彩星直转被阻断：本单加价比例必须在 0 到 1 之间')
  }
  const carton = p4PrimaryCarton(artifact)

  const rawToolRows = p4Rows(artifact.sections.molding.payload.caixing_tool_plan_rows)
  if (rawToolRows.length === 0 || rawToolRows.length > (productType === 'plastic' ? 100 : 51)) {
    throw new Error(`彩星直转被阻断：${productType === 'plastic' ? '塑胶 Tool Plan 须在 1–100 行' : '车衣 Tool Plan 须在 1–51 行'}`)
  }
  const processTypes = new Set(['IN', 'BL', 'CP', 'DC', 'RC'])
  const refs = new Set<string>()
  const reviewWarnings: string[] = []
  const hasApprovedMoldingPrices = p4SectionCalculationRows(artifact, 'molding').some((row) =>
    ['injection', 'blow'].includes(p4Text(row.kind)) && p4Number(row.material_price_hkd_lb) > 0)
  const moldByRef = new Map<string, Record<string, unknown>>()
  p4Rows(artifact.sections.engineering.payload.molds).forEach((row, index) => {
    const ref = p4Text(row.caixing_tool_plan_ref)
    if (!ref) return
    if (moldByRef.has(ref)) throw new Error(`彩星直转被阻断：工程模具 Tool Plan Ref ${ref} 重复`)
    p4NonNegative(row.caixing_mold_cost_hkd, `工程模具第 ${index + 1} 行内部模价不得小于 0`)
    p4Positive(row.caixing_customer_mold_cost_hkd, `工程模具第 ${index + 1} 行客户模价必须大于 0`)
    moldByRef.set(ref, row)
  })

  const injectionRows = rawToolRows.map<CaixingInjectionRow>((row, index) => {
    const ref = p4RequiredText(row.ref_no, `Tool Plan 第 ${index + 1} 行缺少 Ref No.`)
    if (refs.has(ref)) throw new Error(`彩星直转被阻断：Tool Plan Ref No. ${ref} 重复`)
    refs.add(ref)
    const processType = p4RequiredText(row.process_type, `Tool Plan ${ref} 缺少 Type`)
    if (!processTypes.has(processType)) throw new Error(`彩星直转被阻断：Tool Plan ${ref} Type 必须是 IN/BL/CP/DC/RC`)
    const customerMoldCostHkd = p4NonNegative(row.tooling_cost_hkd, `Tool Plan ${ref} Tooling Cost 不得小于 0`)
    const mold = moldByRef.get(ref)
    if (customerMoldCostHkd > 0) {
      if (!mold) throw new Error(`彩星直转被阻断：Tool Plan ${ref} 的客户模价未匹配工程模具`)
      const mapped = p4Positive(mold.caixing_customer_mold_cost_hkd, `工程模具 ${ref} 缺少客户模价`)
      if (Math.abs(mapped - customerMoldCostHkd) > 0.01) {
        throw new Error(`彩星直转被阻断：Tool Plan ${ref} 与工程模具客户模价不一致`)
      }
    } else if (mold) {
      throw new Error(`彩星直转被阻断：工程模具 ${ref} 已填写客户模价，但 Tool Plan 对应行为空`)
    }
    const machineSize = p4RequiredText(row.machine_size, `Tool Plan ${ref} 缺少 M/C Size`)
    if (processType === 'IN' && p4Number(machineSize) <= 0) {
      throw new Error(`彩星直转被阻断：Tool Plan ${ref} 注塑 M/C Size 必须是大于 0 的吨位`)
    }
    const weightG = p4Positive(row.net_weight_g, `Tool Plan ${ref} Net Wt. 必须大于 0`)
    const materialCode = p4Positive(row.material_code, `Tool Plan ${ref} Material Code 必须大于 0`)
    if (!Number.isInteger(materialCode) || materialCode > 14) {
      throw new Error(`彩星直转被阻断：Tool Plan ${ref} Material Code 必须是 1 至 14 的整数`)
    }
    const skuNo = p4RequiredText(row.sku_no, `Tool Plan ${ref} 缺少 SKU No.`)
    if (skuNo !== itemNo) throw new Error(`彩星直转被阻断：Tool Plan ${ref} 的 SKU No. 与本单 Item No. 不一致`)
    const up = p4Positive(row.up, `Tool Plan ${ref} Up 必须大于 0`)
    const cycleSeconds = p4Positive(row.cycle_time_seconds, `Tool Plan ${ref} Cycle Time 必须大于 0`)
    const matchedSource = p4ToolSourcePrice(row, processType, artifact)
    if (!matchedSource && hasApprovedMoldingPrices && row.material_price_hkd_lb == null && row.machine_daily_hkd == null) {
      reviewWarnings.push(`Tool Plan ${ref} 未唯一匹配内部啤机明细，沿用本单已填客户料金额及啤工，请核对。`)
    }
    const materialPriceInput = row.material_price_hkd_lb === null || row.material_price_hkd_lb === undefined || row.material_price_hkd_lb === ''
      ? matchedSource?.material_price_hkd_lb : row.material_price_hkd_lb
    const machinePriceInput = row.machine_daily_hkd === null || row.machine_daily_hkd === undefined || row.machine_daily_hkd === ''
      ? matchedSource?.machine_shift_price_hkd : row.machine_daily_hkd
    const hasRawMaterialPrice = materialPriceInput !== null && materialPriceInput !== undefined && materialPriceInput !== ''
    const hasRawMachinePrice = machinePriceInput !== null && machinePriceInput !== undefined && machinePriceInput !== ''
    if (!hasRawMaterialPrice && (caixingOptionalRate(pricing, 'material_price_uplift_rate', 0.02) !== 0.02
      || caixingOptionalRate(pricing, 'tool_material_scrap_rate', 0.02) !== 0.02)) {
      throw new Error(`彩星直转被阻断：Tool Plan ${ref} 缺少内部材料磅价，无法应用已调整的料价或料重损耗参数`)
    }
    if (!hasRawMachinePrice && (caixingOptionalRate(pricing, 'machine_hours_per_day', 24) !== 24
      || caixingOptionalRate(pricing, 'machine_utilization_factor', 0.98) !== 0.98)) {
      throw new Error(`彩星直转被阻断：Tool Plan ${ref} 缺少内部啤机日价，无法应用已调整的啤机工时参数`)
    }
    const materialUnitPriceHkdKg = hasRawMaterialPrice
      ? p4Positive(materialPriceInput, `Tool Plan ${ref} 内部材料磅价必须大于 0`) / 454 * 1000 * (1 + caixingOptionalRate(pricing, 'material_price_uplift_rate', 0.02))
      : undefined
    const machineHourlyHkd = hasRawMachinePrice
      ? p4Positive(machinePriceInput, `Tool Plan ${ref} 内部啤机日价必须大于 0`)
        / p4Positive(caixingOptionalRate(pricing, 'machine_hours_per_day', 24), '每日计价小时必须大于 0')
        / p4Positive(caixingOptionalRate(pricing, 'machine_utilization_factor', 0.98), '啤机有效工时系数必须大于 0')
      : undefined
    return {
      lineNo: ref,
      name: p4RequiredText(row.description, `Tool Plan ${ref} 缺少 Description`),
      material: p4RequiredText(row.material, `Tool Plan ${ref} 缺少 Material`),
      displayMaterial: p4RequiredText(row.material, `Tool Plan ${ref} 缺少 Material`),
      weightG,
      machineTons: processType === 'IN' ? p4Positive(machineSize, `Tool Plan ${ref} M/C Size 必须大于 0`) : 0,
      setsPerShot: up,
      partsPerShot: p4Positive(row.cavities, `Tool Plan ${ref} Cav. 必须大于 0`),
      targetYield: 0,
      moldingCostHkd: machineHourlyHkd === undefined
        ? p4Positive(row.process_cost_hkd, `Tool Plan ${ref} Process Cost 必须大于 0`)
        : roundMoney(cycleSeconds / 3600 * machineHourlyHkd / up),
      materialCostHkd: materialUnitPriceHkdKg === undefined
        ? p4Positive(row.material_cost_hkd, `Tool Plan ${ref} Material Cost 必须大于 0`)
        : roundMoney(weightG / 1000 * materialUnitPriceHkdKg * (1 + caixingOptionalRate(pricing, 'tool_material_scrap_rate', 0.02))),
      materialUnitPriceHkdKg,
      machineHourlyHkd,
      cycleSeconds,
      moldCostHkd: mold ? p4NonNegative(mold.caixing_mold_cost_hkd, `工程模具 ${ref} 内部模价不得小于 0`) : 0,
      customerMoldCostHkd,
      processType: processType as CaixingInjectionRow['processType'],
      toolNo: p4Text(row.tool_no),
      skuNo,
      cavities: p4Positive(row.cavities, `Tool Plan ${ref} Cav. 必须大于 0`),
      up: p4Positive(row.up, `Tool Plan ${ref} Up 必须大于 0`),
      materialCode,
      color: p4Text(row.color),
    }
  })
  for (const ref of moldByRef.keys()) {
    if (!refs.has(ref)) throw new Error(`彩星直转被阻断：工程模具 ${ref} 未匹配 Tool Plan 行`)
  }

  const costRows = p4DerivedCostRows(artifact, productType)

  const metadata: CaixingQuoteMetadata = {
    itemNo,
    itemName,
    quoteDate,
    revision: p4Text(artifact.versionLabel) || 'R0',
    markupRateOverride,
    sourceSheetName: 'P4 v2',
    productType,
    productTypeName: PRODUCT_TYPE_LABELS[productType],
    carton,
  }
  const quoteData: CaixingQuoteData = {
    pricing,
    metadata,
    injectionRows,
    costRows,
    summary: buildSummary(productType, injectionRows, null, costRows, carton, undefined, pricing, markupRateOverride),
  }
  return {
    pricing,
    warnings: caixingLayoutWarning(itemNo).concat(reviewWarnings.slice(0, 10), reviewWarnings.length > 10 ? [`另有 ${reviewWarnings.length - 10} 行需要核对。`] : []),
    sourceFileName,
    productType,
    sheets: [convertSheet(quoteData, sourceFileName, 0)],
  }
}

export function convertCaixingInternalQuote(
  buffer: ArrayBuffer,
  sourceFileName: string,
  productType: CaixingProductType,
  pricing?: CustomerPricingSettings,
): CaixingConversionResult {
  assertPricingCustomer(pricing, 'caixing')
  const workbook = parseXlsxWorkbook(buffer, { includeFormulas: true })
  const sheet = findConvertibleSheet(workbook)
  const quoteData = parseCaixingSheet(
    sheet.rows,
    sheet.name,
    sourceFileName,
    productType,
    findSprayingDetailTotal(workbook),
    pricing,
  )
  quoteData.image = extractYinhuiProductImage(buffer, sheet.name)

  return {
    pricing,
    warnings: materialPriceReferenceWarnings(sheet).concat(caixingLayoutWarning(quoteData.metadata.itemNo)),
    sourceFileName,
    productType,
    sheets: [convertSheet(quoteData, sourceFileName, 0)],
  }
}

export function buildCaixingCustomerQuoteFileName(result: CaixingConversionResult) {
  const firstSheet = result.sheets[0]
  const metadata = firstSheet?.quoteData.metadata
  const itemNo = metadata?.itemNo ?? 'ITEM'
  const itemName = metadata?.itemName ?? firstSheet?.productName ?? 'Caixing Quote'
  const quoteDate = metadata?.quoteDate ?? new Date()
  const productTypeName = PRODUCT_TYPE_LABELS[result.productType]

  return `RR ${sanitizeFileNamePart(itemNo)}_${sanitizeFileNamePart(itemName)}_${productTypeName}_${sanitizeFileNamePart(metadata?.revision || 'R0')}_${formatFileDate(quoteDate)}.xlsx`
}

export function createCaixingCustomerQuoteWorkbookFromTemplate(
  result: CaixingConversionResult,
  templateBuffer: ArrayBuffer | Uint8Array,
): Uint8Array {
  const pricing = result.pricing

  const firstSheet = result.sheets[0]
  if (!firstSheet) {
    throw new Error('没有可输出的彩星报客数据')
  }

  if (result.productType !== 'plastic' && result.productType !== 'plush') {
    return createCaixingCustomerQuoteWorkbook(result)
  }

  const zip = unzipSync(toTemplateUint8Array(templateBuffer))
  if (result.productType === 'plastic') {
    const rowCount = templateToolPlanRowCount(firstSheet.quoteData)
    if (rowCount > 100) throw new Error('彩星塑胶 Tool Plan 含附加工序超过安全扩展容量 100 行')
    extendPlasticToolPlanTemplate(zip, Math.max(0, rowCount - 52))
  }
  let plushDecoNumberStyles: number[] | undefined
  if (result.productType === 'plush' && zip['xl/styles.xml']) {
    const appended = appendTemplateGeneralNumberStyles(
      strFromU8(zip['xl/styles.xml']),
      [920, 923, 925, 929],
    )
    zip['xl/styles.xml'] = strToU8(appended.stylesXml)
    plushDecoNumberStyles = appended.indexes
  }
  const patchesBySheet = result.productType === 'plush'
    ? buildPlushTemplatePatches(firstSheet.quoteData, plushDecoNumberStyles, pricing)
    : buildPlasticTemplatePatches(firstSheet.quoteData, pricing)
  const templateSheets = result.productType === 'plush'
    ? CAIXING_PLUSH_TEMPLATE_SHEETS
    : CAIXING_PLASTIC_TEMPLATE_SHEETS

  Object.entries(patchesBySheet).forEach(([sheetName, patches]) => {
    const sheetPath = getTemplateSheetPath(zip, sheetName)
    const sheetXml = sheetPath && zip[sheetPath] ? strFromU8(zip[sheetPath]) : ''

    if (!sheetXml) {
      throw new Error(`彩星${PRODUCT_TYPE_LABELS[result.productType]}报客价模板缺少工作表：${sheetName}`)
    }

    zip[sheetPath] = strToU8(applyTemplateCellPatches(sheetXml, patches))
  })

  const productImage = firstSheet.quoteData.image
  replaceTemplateSheetProductPictures(zip, templateSheets.deco, productImage)
  replaceTemplateSheetProductPictures(zip, templateSheets.summary, productImage)
  delete zip['xl/media/image1.png']
  delete zip['xl/media/image2.png']
  delete zip['xl/media/image3.png']
  if (productImage) {
    zip[`xl/media/caixing-product.${productImage.extension}`] = new Uint8Array(productImage.bytes)
    if (productImage.extension === 'jpg' && zip['[Content_Types].xml']) {
      const contentTypes = strFromU8(zip['[Content_Types].xml'])
      if (!/<Default\b[^>]*Extension="jpg"/.test(contentTypes)) {
        zip['[Content_Types].xml'] = strToU8(contentTypes.replace('</Types>', '<Default Extension="jpg" ContentType="image/jpeg"/></Types>'))
      }
    }
  }

  if (zip['xl/workbook.xml']) {
    zip['xl/workbook.xml'] = strToU8(forceTemplateRecalculation(strFromU8(zip['xl/workbook.xml'])))
  }

  return zipSync(zip)
}

export function createCaixingCustomerQuoteWorkbook(result: CaixingConversionResult, templateBuffer?: ArrayBuffer | Uint8Array): Uint8Array {
  const pricing = result.pricing

  const firstSheet = result.sheets[0]
  if (!firstSheet) {
    throw new Error('没有可输出的彩星报客数据')
  }

  if (templateBuffer && (result.productType === 'plastic' || result.productType === 'plush')) {
    return createCaixingCustomerQuoteWorkbookFromTemplate(result, templateBuffer)
  }

  const data = firstSheet.quoteData
  const {
    specialRows,
    electronicRows,
    packingRows,
    fabricRows,
    purchaseRows,
  } = getCaixingGroupedCostRows(data)
  const electRows = [...specialRows, ...electronicRows]

  const sheets: XlsxOutputSheet[] = [
    buildSummarySheet(data, pricing),
    buildToolPlanSheet(data),
  ]

  if (data.metadata.productType === 'plastic') {
    sheets.push(
      buildCostSheet('Elect', 'SPECIAL / ELECTRONIC MATERIAL COST', electRows, data.summary.markupRate),
      buildCostSheet('Purchase', 'PURCHASED PARTS COST', purchaseRows, data.summary.markupRate),
      buildPackingSheet(data, packingRows),
      buildCostSheet('Fabric', 'FABRIC COST', fabricRows, data.summary.markupRate),
    )
  } else {
    sheets.push(
      buildCostSheet('Purchase', 'PURCHASED PARTS COST', purchaseRows, data.summary.markupRate),
      buildCostSheet('Fabric', 'FABRIC / PLUSH COST', fabricRows, data.summary.markupRate),
      buildPackingSheet(data, packingRows),
      buildCostSheet('Elect', 'SPECIAL / ELECTRONIC MATERIAL COST', electRows, data.summary.markupRate),
    )
  }

  return createXlsxWorkbook(sheets)
}

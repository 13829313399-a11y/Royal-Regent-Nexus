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
import type { P4InternalQuoteArtifact } from './p4Artifact'

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

function includesAny(value: string, keywords: string[]) {
  return keywords.some((keyword) => value.includes(keyword))
}

function sumCostRows(costRows: CaixingCostRow[], keywords: string[], exclude: string[] = []) {
  return sumBy(costRows, (row) => {
    const haystack = `${row.category} ${row.description}`
    if (!includesAny(haystack, keywords) || includesAny(haystack, exclude)) {
      return 0
    }

    return row.customerCostHkd || row.baseCostHkd
  })
}

function filterCostRows(costRows: CaixingCostRow[], keywords: string[], exclude: string[] = []) {
  return costRows.filter((row) => {
    const haystack = `${row.category} ${row.description}`
    return includesAny(haystack, keywords) && !includesAny(haystack, exclude)
  })
}

function filterCustomerGroup(costRows: CaixingCostRow[], group: CaixingCustomerCostGroup) {
  return costRows.filter((row) => row.customerGroup === group)
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

function getPlasticPackingTotal(costRows: CaixingCostRow[], carton: CaixingCartonProfile) {
  const packingRows = filterCostRows(costRows, ['彩盒', '内咭', '纸箱', '吸塑'])
  const componentTotal = sumBy(
    packingRows.filter((row) => !isCartonCostRow(row)),
    (row) => costRowAmount(row) * (1 + CAIXING_PLASTIC_SCRAP_RATE),
  )
  const cartonPerToy = carton.cartonPrice && carton.pcsPerCarton
    ? carton.cartonPrice / carton.pcsPerCarton
    : 0

  return roundMoney(componentTotal + cartonPerToy * (1 + CAIXING_PLASTIC_SCRAP_RATE))
}

function buildSummary(
  productType: CaixingProductType,
  injectionRows: CaixingInjectionRow[],
  injectionTotal: ReturnType<typeof parseInjectionRows>['total'],
  costRows: CaixingCostRow[],
  carton: CaixingCartonProfile,
  sprayingDetailTotal?: number | null,
): CaixingSummary {
  const hasExplicitGroups = costRows.some((row) => row.customerGroup)
  const injectionMaterial = injectionTotal?.materialCostHkd || sumBy(injectionRows, (row) => row.materialCostHkd)
  const injectionMolding = injectionTotal?.moldingCostHkd || sumBy(injectionRows, (row) => row.moldingCostHkd)
  const electronicMaterial = hasExplicitGroups
    ? sumCustomerGroup(costRows, 'electronic')
    : sumCostRows(costRows, ['电子', 'IC', '电池'])
  const packagingMaterial = hasExplicitGroups
    ? roundMoney(
        sumCustomerGroup(costRows, 'packing') * (productType === 'plastic' ? 1 + CAIXING_PLASTIC_SCRAP_RATE : 1)
        + (carton.cartonPrice && carton.pcsPerCarton
          ? carton.cartonPrice / carton.pcsPerCarton * (productType === 'plastic' ? 1 + CAIXING_PLASTIC_SCRAP_RATE : 1)
          : 0),
      )
    : productType === 'plastic'
      ? getPlasticPackingTotal(costRows, carton)
      : sumCostRows(costRows, ['彩盒', '内咭', '纸箱', '吸塑'])
  const fabric = hasExplicitGroups ? sumCustomerGroup(costRows, 'fabric') : sumCostRows(costRows, ['车衣'])
  const purchasePartBase = sumCostRows(
    costRows,
    ['五金', '其它外购', '其他外购', '利宝', '说明书', '马达'],
    ['彩盒', '内咭', '纸箱', '吸塑', '电子', 'IC', '电池'],
  )
  const explicitPurchasePart = sumCustomerGroup(costRows, 'purchase')
  const purchasePart = productType === 'plastic'
    ? roundMoney((hasExplicitGroups ? explicitPurchasePart : purchasePartBase) * (1 + CAIXING_PLASTIC_SCRAP_RATE))
    : hasExplicitGroups ? explicitPurchasePart : purchasePartBase
  const specialMaterial = hasExplicitGroups
    ? sumCustomerGroup(costRows, 'special')
    : productType === 'plush' ? sumCostRows(costRows, ['搪胶']) : 0
  const moldingCasting = hasExplicitGroups
    ? roundMoney(injectionMolding)
    : roundMoney(injectionMolding + sumBy(getMoldingProcessRows(costRows), (row) => row.costHkd))
  const spraying = sprayingDetailTotal === null || sprayingDetailTotal === undefined
    ? hasExplicitGroups ? sumCustomerGroup(costRows, 'spraying') : sumCostRows(costRows, ['油漆', '喷油'])
    : roundMoney(sprayingDetailTotal)
  const assemblyLabor = hasExplicitGroups ? sumCustomerGroup(costRows, 'assembly') : sumCostRows(costRows, ['装配工'], ['包装'])
  const packoutLabor = hasExplicitGroups ? sumCustomerGroup(costRows, 'packout') : sumCostRows(costRows, ['包装人工'])
  const rootingHair = hasExplicitGroups ? sumCustomerGroup(costRows, 'rooting') : productType === 'plush' ? sumCostRows(costRows, ['车发']) : 0
  const sewingHandfinish = hasExplicitGroups ? sumCustomerGroup(costRows, 'sewing') : 0
  const specialOffer = hasExplicitGroups ? sumCustomerGroup(costRows, 'special_offer') : 0
  const tampo = hasExplicitGroups ? sumCustomerGroup(costRows, 'tampo') : 0
  const markupRate = productType === 'plush' ? 0.17 : 0.16
  const materialTotal = roundMoney(injectionMaterial + specialMaterial + electronicMaterial + purchasePart + packagingMaterial + fabric)
  const processTotal = roundMoney(moldingCasting + spraying + tampo + assemblyLabor + packoutLabor + rootingHair + sewingHandfinish + specialOffer)
  const exFactoryHkd = round(materialTotal * (1 + markupRate) + processTotal * (1 + markupRate), 2)

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
    exFactoryUsd: round(exFactoryHkd / 7.8, 3),
    domesticTransportationHkd: roundMoney((carton.cube || 0) * 2.11 / Math.max(carton.pcsPerCarton || 1, 1)),
    fobTransportationHkd: roundMoney((carton.cube || 0) * 5.93 / Math.max(carton.pcsPerCarton || 1, 1)),
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
    rows.push(detailRow(
      sheetId,
      row.category,
      `COST-${String(index + 1).padStart(3, '0')}`,
      row.description,
      row.baseCostHkd,
      row.customerCostHkd * markup,
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
) {
  const headerRow = findHeaderRow(rows)
  if (headerRow < 0) {
    throw new Error('未找到彩星内部报价明细表头：C列需为“名称”，D列需为“料型”')
  }

  const metadata = parseMetadata(rows, sheetName, sourceFileName, productType)
  const { injectionRows, total } = parseInjectionRows(rows, headerRow)
  const costRows = parseCostRows(rows, (total?.rowIndex ?? headerRow) + 1)
  const summary = buildSummary(productType, injectionRows, total, costRows, metadata.carton, sprayingDetailTotal)

  return {
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
  const hasExplicitGroups = data.costRows.some((row) => row.customerGroup)
  const specialRows = hasExplicitGroups ? filterCustomerGroup(data.costRows, 'special') : filterCostRows(data.costRows, ['搪胶'])
  const electronicRows = hasExplicitGroups ? filterCustomerGroup(data.costRows, 'electronic') : filterCostRows(data.costRows, ['电子', 'IC', '电池'])
  const packingRows = hasExplicitGroups ? filterCustomerGroup(data.costRows, 'packing') : filterCostRows(data.costRows, ['彩盒', '内咭', '纸箱', '吸塑'])
  const fabricRows = hasExplicitGroups
    ? filterCustomerGroup(data.costRows, 'fabric')
    : data.metadata.productType === 'plush'
      ? filterCostRows(data.costRows, ['车衣', '车发'])
      : filterCostRows(data.costRows, ['车衣'])
  const purchaseRows = hasExplicitGroups ? filterCustomerGroup(data.costRows, 'purchase') : data.costRows.filter((row) => {
    const haystack = `${row.category} ${row.description}`
    return !includesAny(haystack, ['电子', 'IC', '电池', '彩盒', '内咭', '纸箱', '吸塑', '车衣', '车发', '装配工', '喷油', '油漆', '啤工', '料价', '吹气', '搪胶', '运费', '吊柜'])
  })

  return {
    specialRows,
    electronicRows,
    packingRows,
    fabricRows,
    purchaseRows,
  }
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

function stripTemplatePictureAnchors(drawingXml: string) {
  return (['twoCellAnchor', 'oneCellAnchor', 'absoluteAnchor'] as const).reduce((xml, anchorName) => {
    const anchorPattern = new RegExp(`<xdr:${anchorName}\\b[\\s\\S]*?<\\/xdr:${anchorName}>`, 'g')
    return xml.replace(anchorPattern, (anchorXml) => anchorXml.includes('<xdr:pic') ? '' : anchorXml)
  }, drawingXml)
}

function stripTemplateSheetPictures(zip: Record<string, Uint8Array>, sheetName: string) {
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

      zip[drawingPath] = strToU8(stripTemplatePictureAnchors(drawingXml))
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

function buildPlasticTemplatePatches(data: CaixingQuoteData) {
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
  const { electronicRows, packingRows, fabricRows, purchaseRows } = getCaixingGroupedCostRows(data)
  const summarySheet = CAIXING_PLASTIC_TEMPLATE_SHEETS.summary
  const toolSheet = CAIXING_PLASTIC_TEMPLATE_SHEETS.toolPlan
  const electSheet = CAIXING_PLASTIC_TEMPLATE_SHEETS.elect
  const purchaseSheet = CAIXING_PLASTIC_TEMPLATE_SHEETS.purchase
  const packingSheet = CAIXING_PLASTIC_TEMPLATE_SHEETS.packing
  const fabricSheet = CAIXING_PLASTIC_TEMPLATE_SHEETS.fabric
  const decoSheet = CAIXING_PLASTIC_TEMPLATE_SHEETS.deco
  const quoteDateSerial = excelDateSerial(metadata.quoteDate)
  const finalCost = (value: number) => roundMoney(value * (1 + summary.markupRate))
  const pct = (value: number) => summary.exFactoryHkd ? round(value / summary.exFactoryHkd, 6) : 0

  patch(summarySheet, 'B3', metadata.itemNo)
  patch(summarySheet, 'B4', metadata.itemNo)
  patch(summarySheet, 'B5', metadata.itemName)
  formula(summarySheet, 'B6', metadata.carton.cube, 'IF(Packing!J25=0,"",Packing!G25*Packing!H25*Packing!I25/1728)')
  formula(summarySheet, 'B7', metadata.carton.pcsPerCarton, 'IF(Packing!J25=0,"",1/Packing!J25)')
  patch(summarySheet, 'G5', quoteDateSerial)
  patch(summarySheet, 'H56', 7.8)

  ;[
    ['E11', summary.material.plasticParts, "'Tool Plan'!N69"],
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
    patch(summarySheet, `F${rowNumber}`, summary.markupRate)
    formula(summarySheet, `G${rowNumber}`, finalCost(base), `E${rowNumber}*(1+F${rowNumber})`)
    formula(summarySheet, `H${rowNumber}`, pct(finalCost(base)), `IF(G$29=0,"",G${rowNumber}/G$29)`)
  }

  formula(summarySheet, 'E17', summary.material.total, 'SUM(E11:E16)')
  formula(summarySheet, 'G17', finalCost(summary.material.total), 'SUM(G11:G16)')
  formula(summarySheet, 'H17', pct(finalCost(summary.material.total)), 'IF(G$29=0,"",G17/G$29)')
  formula(summarySheet, 'E19', summary.process.moldingCasting, "'Tool Plan'!Q69")
  patch(summarySheet, 'C20', null)
  patch(summarySheet, 'D20', null)
  patch(summarySheet, 'E20', summary.process.spraying)
  patch(summarySheet, 'C21', null)
  patch(summarySheet, 'D21', null)
  patch(summarySheet, 'E21', summary.process.tampo)
  patch(summarySheet, 'C22', null)
  patch(summarySheet, 'D22', null)
  patch(summarySheet, 'E22', summary.process.assemblyLabor)
  patch(summarySheet, 'C23', null)
  patch(summarySheet, 'D23', null)
  patch(summarySheet, 'E23', summary.process.packoutLabor)
  patch(summarySheet, 'E24', summary.process.rootingHair)
  patch(summarySheet, 'E25', summary.process.sewingHandfinish)
  patch(summarySheet, 'E26', summary.process.specialOffer)

  for (let rowNumber = 19; rowNumber <= 26; rowNumber += 1) {
    const base = toNumber(rowNumber === 19 ? summary.process.moldingCasting
      : rowNumber === 20 ? summary.process.spraying
        : rowNumber === 21 ? summary.process.tampo
          : rowNumber === 22 ? summary.process.assemblyLabor
            : rowNumber === 23 ? summary.process.packoutLabor
              : rowNumber === 24 ? summary.process.rootingHair
                : rowNumber === 25 ? summary.process.sewingHandfinish
                  : summary.process.specialOffer)
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
    ...Array.from({ length: 7 }, (_, index) => 60 + index),
  ]
  const moldingProcessRows = getMoldingProcessRows(data.costRows)
  const toolInjectionRows = data.injectionRows.slice(0, toolRows.length)
  const toolProcessRows = data.injectionRows.some((item) => item.processType)
    ? []
    : moldingProcessRows.slice(0, Math.max(toolRows.length - toolInjectionRows.length, 0))
  const toolMoldingCosts = [
    ...toolInjectionRows.map((item) => item.moldingCostHkd),
    ...toolProcessRows.map((item) => item.costHkd),
  ]
  const materialCostTotal = sumBy(data.injectionRows, (item) => item.materialCostHkd)
  const moldingCostTotal = summary.process.moldingCasting

  toolRows.forEach((rowNumber) => {
    clear(toolSheet, rowNumber, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 15, 17])
    formula(toolSheet, `L${rowNumber}`, null, `IF(OR(K${rowNumber}=0,K${rowNumber}>14),"",VLOOKUP(K${rowNumber},Summary!$C$40:$D$53,2))`)
    formula(toolSheet, `N${rowNumber}`, 0, `IF(D${rowNumber}=0,IF(G${rowNumber}=$E$4,IF(OR(J${rowNumber}=0,K${rowNumber}=0),"",(J${rowNumber}/1000)*(1+VLOOKUP(K${rowNumber},Summary!$C$40:$F$53,3))*VLOOKUP(K${rowNumber},Summary!$C$40:$F$53,4)),""),"Dup Tool")`)
    formula(toolSheet, `Q${rowNumber}`, 0, `IF(D${rowNumber}=0,IF(A${rowNumber}=0,"",IF(OR(B${rowNumber}="IN",B${rowNumber}="BL",B${rowNumber}="CP",B${rowNumber}="DC",B${rowNumber}="RC"),((P${rowNumber}/3600)*(IF(B${rowNumber}="IN",VLOOKUP(O${rowNumber},Summary!$G$40:$H$49,2)/I${rowNumber},VLOOKUP(B${rowNumber},Summary!$G$50:$H$53,2)/I${rowNumber}))),"Typ ??")),"Dup.Tool")`)
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
    patch(toolSheet, `N${rowNumber}`, item.materialCostHkd)
    patch(toolSheet, `O${rowNumber}`, item.processType && item.processType !== 'IN' ? item.processType : item.machineTons || null)
    patch(toolSheet, `P${rowNumber}`, item.cycleSeconds || null)
    patch(toolSheet, `Q${rowNumber}`, item.moldingCostHkd)
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
  formula(toolSheet, 'N68', sumBy(toolInjectionRows.slice(44, 51), (item) => item.materialCostHkd), 'SUM(N60:N66)')
  formula(toolSheet, 'Q68', sumBy(toolMoldingCosts.slice(44, 51), (item) => item), 'SUM(Q60:Q66)')
  formula(toolSheet, 'N69', materialCostTotal, 'N58+N68')
  formula(toolSheet, 'Q69', moldingCostTotal, 'Q58+Q68')

  const patchPurchasedSection = (
    sheetName: string,
    startRow: number,
    endRow: number,
    totalCell: string,
    totalFormula: string,
    rows: CaixingCostRow[],
    scrapRate = 0,
  ) => {
    for (let rowNumber = startRow; rowNumber <= endRow; rowNumber += 1) {
      patch(sheetName, `A${rowNumber}`, rowNumber - startRow + 1)
      clear(sheetName, rowNumber, [1, 2, 3, 4, 6, 7])
      patch(sheetName, `F${rowNumber}`, 'Pc')
      patch(sheetName, `H${rowNumber}`, scrapRate)
      formula(sheetName, `I${rowNumber}`, 0, `E${rowNumber}*G${rowNumber}*(1+H${rowNumber})`)
    }

    rows.slice(0, endRow - startRow + 1).forEach((item, index) => {
      const rowNumber = startRow + index
      const cost = item.customerCostHkd || item.baseCostHkd
      patch(sheetName, `A${rowNumber}`, index + 1)
      patch(sheetName, `B${rowNumber}`, item.description)
      patch(sheetName, `E${rowNumber}`, 1)
      patch(sheetName, `F${rowNumber}`, 'Pc')
      patch(sheetName, `G${rowNumber}`, cost)
      patch(sheetName, `H${rowNumber}`, scrapRate)
      formula(sheetName, `I${rowNumber}`, roundMoney(cost * (1 + scrapRate)), `E${rowNumber}*G${rowNumber}*(1+H${rowNumber})`)
    })

    formula(sheetName, totalCell, sumBy(rows, (item) => costRowAmount(item) * (1 + scrapRate)), totalFormula)
  }

  patchPurchasedSection(electSheet, 8, 18, 'I19', 'SUM(I8:I18)', [])
  patchPurchasedSection(electSheet, 21, 88, 'I89', 'SUM(I21:I88)', electronicRows)
  patchPurchasedSection(purchaseSheet, 8, 25, 'I26', 'SUM(I8:I25)', purchaseRows, CAIXING_PLASTIC_SCRAP_RATE)
  patchPurchasedSection(fabricSheet, 8, 30, 'I31', 'SUM(I8:I30)', fabricRows)

  const nonCartonPackingRows = packingRows.filter((row) => !isCartonCostRow(row))
  const packingDataRows = [
    ...Array.from({ length: 18 }, (_, index) => 7 + index),
    ...Array.from({ length: 27 }, (_, index) => 26 + index),
  ]

  packingDataRows.forEach((rowNumber, index) => {
    patch(packingSheet, `A${rowNumber}`, index + 1)
    clear(packingSheet, rowNumber, [1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12])
    patch(packingSheet, `K${rowNumber}`, 'Pc')
    patch(packingSheet, `M${rowNumber}`, CAIXING_PLASTIC_SCRAP_RATE)
    formula(packingSheet, `N${rowNumber}`, 0, `L${rowNumber}*J${rowNumber}*(1+M${rowNumber})`)
  })

  nonCartonPackingRows.slice(0, packingDataRows.length).forEach((item, index) => {
    const rowNumber = packingDataRows[index]
    const cost = item.customerCostHkd || item.baseCostHkd
    patch(packingSheet, `A${rowNumber}`, index + 1)
    patch(packingSheet, `B${rowNumber}`, item.category)
    patch(packingSheet, `C${rowNumber}`, item.description)
    patch(packingSheet, `J${rowNumber}`, 1)
    patch(packingSheet, `K${rowNumber}`, 'Pc')
    patch(packingSheet, `L${rowNumber}`, cost)
    patch(packingSheet, `M${rowNumber}`, CAIXING_PLASTIC_SCRAP_RATE)
    formula(packingSheet, `N${rowNumber}`, roundMoney(cost * (1 + CAIXING_PLASTIC_SCRAP_RATE)), `L${rowNumber}*J${rowNumber}*(1+M${rowNumber})`)
  })

  patch(packingSheet, 'A25', 19)
  patch(packingSheet, 'B25', 'Carton Shipper')
  patch(packingSheet, 'C25', null)
  patch(packingSheet, 'G25', metadata.carton.height || null)
  patch(packingSheet, 'H25', metadata.carton.length || null)
  patch(packingSheet, 'I25', metadata.carton.width || null)
  patch(packingSheet, 'J25', metadata.carton.pcsPerCarton ? 1 / metadata.carton.pcsPerCarton : null)
  patch(packingSheet, 'K25', 'Pc')
  patch(packingSheet, 'L25', metadata.carton.cartonPrice || null)
  patch(packingSheet, 'M25', CAIXING_PLASTIC_SCRAP_RATE)
  formula(
    packingSheet,
    'N25',
    metadata.carton.pcsPerCarton ? roundMoney(metadata.carton.cartonPrice / metadata.carton.pcsPerCarton * (1 + CAIXING_PLASTIC_SCRAP_RATE)) : 0,
    'L25*J25*(1+M25)',
  )
  formula(packingSheet, 'N53', summary.material.packagingMaterial, 'SUM(N7:N52)')

  return patchesBySheet
}

function buildPlushTemplatePatches(data: CaixingQuoteData, decoNumberStyles?: number[]) {
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
  const finalCost = (value: number) => roundMoney(value * (1 + summary.markupRate))
  const pct = (value: number) => summary.exFactoryHkd ? round(value / summary.exFactoryHkd, 6) : 0

  patch(summarySheet, 'B3', metadata.itemNo)
  patch(summarySheet, 'B4', metadata.itemNo)
  patch(summarySheet, 'B5', metadata.itemName)
  formula(summarySheet, 'B6', metadata.carton.cube, 'IF(Packing!J24=0,"",Packing!G24*Packing!H24*Packing!I24/1728)')
  formula(summarySheet, 'B7', metadata.carton.pcsPerCarton, 'IF(Packing!J24=0,"",1/Packing!J24)')
  patch(summarySheet, 'G5', quoteDateSerial)
  patch(summarySheet, 'H60', 7.8)

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
    patch(summarySheet, `F${rowNumber}`, summary.markupRate)
    formula(summarySheet, `G${rowNumber}`, finalCost(base), `E${rowNumber}*(1+F${rowNumber})`)
    formula(summarySheet, `H${rowNumber}`, pct(finalCost(base)), `IF(G$33=0,"",G${rowNumber}/G$33)`)
  }

  formula(summarySheet, 'E17', summary.material.total, 'SUM(E11:E16)')
  formula(summarySheet, 'G17', finalCost(summary.material.total), 'SUM(G11:G16)')
  formula(summarySheet, 'H17', pct(finalCost(summary.material.total)), 'IF(G$33=0,"",G17/G$33)')
  formula(summarySheet, 'E19', summary.process.moldingCasting, "'Tool Plan'!Q67")
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
    clear(summarySheet, rowNumber, [2, 3])
    patch(summarySheet, `E${rowNumber}`, processBaseByRow.get(rowNumber) ?? 0)
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
  const materialCostTotal = sumBy(data.injectionRows, (item) => item.materialCostHkd)
  const moldingCostTotal = sumBy(data.injectionRows, (item) => item.moldingCostHkd)

  toolRows.forEach((rowNumber) => {
    clear(toolSheet, rowNumber, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 15, 17])
    formula(toolSheet, `L${rowNumber}`, null, `IF(OR(K${rowNumber}=0,K${rowNumber}>14),"",VLOOKUP(K${rowNumber},Summary!$C$44:$D$57,2))`)
    formula(toolSheet, `N${rowNumber}`, 0, `IF(D${rowNumber}=0,IF(G${rowNumber}=$E$4,IF(OR(J${rowNumber}=0,K${rowNumber}=0),"",(J${rowNumber}/1000)*(1+VLOOKUP(K${rowNumber},Summary!$C$44:$F$57,3))*VLOOKUP(K${rowNumber},Summary!$C$44:$F$57,4)),""),"Dup Tool")`)
    formula(toolSheet, `Q${rowNumber}`, 0, `IF(D${rowNumber}=0,IF(A${rowNumber}=0,"",IF(OR(B${rowNumber}="IN",B${rowNumber}="BL",B${rowNumber}="CP",B${rowNumber}="DC",B${rowNumber}="RC"),((P${rowNumber}/3600)*(IF(B${rowNumber}="IN",VLOOKUP(O${rowNumber},Summary!$G$44:$H$53,2)/I${rowNumber},VLOOKUP(B${rowNumber},Summary!$G$54:$H$57,2)/I${rowNumber}))),"Typ ??")),"Dup.Tool")`)
  })

  data.injectionRows.slice(0, toolRows.length).forEach((item, index) => {
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
    patch(toolSheet, `N${rowNumber}`, item.materialCostHkd)
    patch(toolSheet, `O${rowNumber}`, item.processType && item.processType !== 'IN' ? item.processType : item.machineTons || null)
    patch(toolSheet, `P${rowNumber}`, item.cycleSeconds || null)
    patch(toolSheet, `Q${rowNumber}`, item.moldingCostHkd)
  })

  formula(toolSheet, 'J59', sumBy(data.injectionRows.slice(0, 45), (item) => item.weightG), 'SUM(J14:J58)')
  formula(toolSheet, 'N59', sumBy(data.injectionRows.slice(0, 45), (item) => item.materialCostHkd), 'SUM(N14:N58)')
  formula(toolSheet, 'Q59', sumBy(data.injectionRows.slice(0, 45), (item) => item.moldingCostHkd), 'SUM(Q14:Q58)')
  formula(toolSheet, 'J66', sumBy(data.injectionRows.slice(45, 51), (item) => item.weightG), 'SUM(J60:J65)')
  formula(toolSheet, 'N66', sumBy(data.injectionRows.slice(45, 51), (item) => item.materialCostHkd), 'SUM(N60:N65)')
  formula(toolSheet, 'Q66', sumBy(data.injectionRows.slice(45, 51), (item) => item.moldingCostHkd), 'SUM(Q60:Q65)')
  formula(toolSheet, 'N67', materialCostTotal, 'N59+N66')
  formula(toolSheet, 'Q67', moldingCostTotal, 'Q59+Q66')

  const patchPurchasedSection = (
    sheetName: string,
    startRow: number,
    endRow: number,
    totalCell: string,
    totalFormula: string,
    rows: CaixingCostRow[],
  ) => {
    for (let rowNumber = startRow; rowNumber <= endRow; rowNumber += 1) {
      patch(sheetName, `A${rowNumber}`, rowNumber - startRow + 1)
      clear(sheetName, rowNumber, [1, 2, 3, 4, 6, 7])
      patch(sheetName, `F${rowNumber}`, 'Pc')
      formula(sheetName, `I${rowNumber}`, 0, `E${rowNumber}*G${rowNumber}*(1+H${rowNumber})`)
    }

    rows.slice(0, endRow - startRow + 1).forEach((item, index) => {
      const rowNumber = startRow + index
      const cost = item.customerCostHkd || item.baseCostHkd
      patch(sheetName, `A${rowNumber}`, index + 1)
      patch(sheetName, `B${rowNumber}`, item.description)
      patch(sheetName, `E${rowNumber}`, 1)
      patch(sheetName, `F${rowNumber}`, 'Pc')
      patch(sheetName, `G${rowNumber}`, cost)
      patch(sheetName, `H${rowNumber}`, 0)
      formula(sheetName, `I${rowNumber}`, cost, `E${rowNumber}*G${rowNumber}*(1+H${rowNumber})`)
    })

    formula(sheetName, totalCell, sumBy(rows, (item) => item.customerCostHkd || item.baseCostHkd), totalFormula)
  }

  patchPurchasedSection(electSheet, 8, 18, 'I19', 'SUM(I8:I18)', specialRows)
  patchPurchasedSection(electSheet, 21, 88, 'I89', 'SUM(I21:I88)', electronicRows)
  patchPurchasedSection(purchaseSheet, 8, 31, 'I32', 'SUM(I8:I31)', purchaseRows)
  patchPurchasedSection(fabricSheet, 8, 40, 'I41', 'SUM(I8:I40)', fabricRows)

  const cartonDescription = (row: CaixingCostRow) => /外箱|纸箱|Carton/i.test(`${row.category} ${row.description}`)
  const nonCartonPackingRows = packingRows.filter((row) => !cartonDescription(row))
  const packingDataRows = [
    ...Array.from({ length: 17 }, (_, index) => 7 + index),
    ...Array.from({ length: 29 }, (_, index) => 25 + index),
  ]
  const packingLineNo = (rowNumber: number, index: number) => rowNumber < 24 ? index + 1 : index + 2

  packingDataRows.forEach((rowNumber, index) => {
    patch(packingSheet, `A${rowNumber}`, packingLineNo(rowNumber, index))
    clear(packingSheet, rowNumber, [1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12])
    patch(packingSheet, `K${rowNumber}`, 'Pc')
    formula(packingSheet, `N${rowNumber}`, 0, `L${rowNumber}*J${rowNumber}*(1+M${rowNumber})`)
  })

  nonCartonPackingRows.slice(0, packingDataRows.length).forEach((item, index) => {
    const rowNumber = packingDataRows[index]
    const cost = item.customerCostHkd || item.baseCostHkd
    patch(packingSheet, `A${rowNumber}`, packingLineNo(rowNumber, index))
    patch(packingSheet, `B${rowNumber}`, item.description)
    patch(packingSheet, `J${rowNumber}`, 1)
    patch(packingSheet, `K${rowNumber}`, 'Pc')
    patch(packingSheet, `L${rowNumber}`, cost)
    patch(packingSheet, `M${rowNumber}`, 0)
    formula(packingSheet, `N${rowNumber}`, cost, `L${rowNumber}*J${rowNumber}*(1+M${rowNumber})`)
  })

  patch(packingSheet, 'A24', 18)
  patch(packingSheet, 'B24', 'Carton Shipper')
  patch(packingSheet, 'C24', null)
  patch(packingSheet, 'G24', metadata.carton.height || null)
  patch(packingSheet, 'H24', metadata.carton.length || null)
  patch(packingSheet, 'I24', metadata.carton.width || null)
  patch(packingSheet, 'J24', metadata.carton.pcsPerCarton ? 1 / metadata.carton.pcsPerCarton : null)
  patch(packingSheet, 'K24', 'Pc')
  patch(packingSheet, 'L24', metadata.carton.cartonPrice || null)
  patch(packingSheet, 'M24', 0)
  formula(
    packingSheet,
    'N24',
    metadata.carton.pcsPerCarton ? metadata.carton.cartonPrice / metadata.carton.pcsPerCarton : 0,
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

function buildSummarySheet(data: CaixingQuoteData): XlsxOutputSheet {
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
  setNumber(rows, exFactoryRow + 4, 5, 2.11)
  setNumber(rows, exFactoryRow + 4, 6, summary.domesticTransportationHkd)
  setCell(rows, exFactoryRow + 5, 4, 'FOB Transportation Cost to Port @ Rate (HK$/Cu.Ft.) :')
  setNumber(rows, exFactoryRow + 5, 5, 5.93)
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

export function convertCaixingP4InternalQuote(
  artifact: P4InternalQuoteArtifact,
  sourceFileName: string,
): CaixingConversionResult {
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
  const carton: CaixingCartonProfile = {
    length: p4Positive(caixing.carton_length_in, '外箱长度必须大于 0'),
    width: p4Positive(caixing.carton_width_in, '外箱宽度必须大于 0'),
    height: p4Positive(caixing.carton_height_in, '外箱高度必须大于 0'),
    cube: p4Positive(caixing.carton_cuft, '外箱 CU.FT 必须大于 0'),
    cbm: p4Positive(caixing.carton_cbm, '外箱 CBM 必须大于 0'),
    pcsPerCarton: p4Positive(caixing.pcs_per_carton, 'Pcs / Shipper 必须大于 0'),
    cartonPrice: p4Positive(caixing.carton_price_hkd, 'Carton Shipper 单价必须大于 0'),
  }

  const rawToolRows = p4Rows(artifact.sections.molding.payload.caixing_tool_plan_rows)
  if (rawToolRows.length === 0 || rawToolRows.length > 51) {
    throw new Error('彩星直转被阻断：Tool Plan 必须完整填写 1–51 行')
  }
  const processTypes = new Set(['IN', 'BL', 'CP', 'DC', 'RC'])
  const refs = new Set<string>()
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
    return {
      lineNo: ref,
      name: p4RequiredText(row.description, `Tool Plan ${ref} 缺少 Description`),
      material: p4RequiredText(row.material, `Tool Plan ${ref} 缺少 Material`),
      displayMaterial: p4RequiredText(row.material, `Tool Plan ${ref} 缺少 Material`),
      weightG: p4Positive(row.net_weight_g, `Tool Plan ${ref} Net Wt. 必须大于 0`),
      machineTons: processType === 'IN' ? p4Positive(machineSize, `Tool Plan ${ref} M/C Size 必须大于 0`) : 0,
      setsPerShot: p4Positive(row.up, `Tool Plan ${ref} Up 必须大于 0`),
      partsPerShot: p4Positive(row.cavities, `Tool Plan ${ref} Cav. 必须大于 0`),
      targetYield: 0,
      moldingCostHkd: p4Positive(row.process_cost_hkd, `Tool Plan ${ref} Process Cost 必须大于 0`),
      materialCostHkd: p4Positive(row.material_cost_hkd, `Tool Plan ${ref} Material Cost 必须大于 0`),
      cycleSeconds: p4Positive(row.cycle_time_seconds, `Tool Plan ${ref} Cycle Time 必须大于 0`),
      moldCostHkd: mold ? p4NonNegative(mold.caixing_mold_cost_hkd, `工程模具 ${ref} 内部模价不得小于 0`) : 0,
      customerMoldCostHkd,
      processType: processType as CaixingInjectionRow['processType'],
      toolNo: p4Text(row.tool_no),
      skuNo: p4RequiredText(row.sku_no, `Tool Plan ${ref} 缺少 SKU No.`),
      cavities: p4Positive(row.cavities, `Tool Plan ${ref} Cav. 必须大于 0`),
      up: p4Positive(row.up, `Tool Plan ${ref} Up 必须大于 0`),
      materialCode: p4Positive(row.material_code, `Tool Plan ${ref} Material Code 必须大于 0`),
      color: p4Text(row.color),
    }
  })
  for (const ref of moldByRef.keys()) {
    if (!refs.has(ref)) throw new Error(`彩星直转被阻断：工程模具 ${ref} 未匹配 Tool Plan 行`)
  }

  const allowedGroups = new Set<CaixingCustomerCostGroup>(['special', 'electronic', 'purchase', 'packing', 'carton', 'fabric', 'spraying', 'tampo', 'assembly', 'packout', 'rooting', 'sewing', 'special_offer'])
  const rawCostRows = p4Rows(caixing.cost_rows)
  if (rawCostRows.length === 0) throw new Error('彩星直转被阻断：缺少塑胶/毛绒客户模板分组明细')
  const costRows = rawCostRows.map<CaixingCostRow>((row, index) => {
    const customerGroup = p4RequiredText(row.group, `客户分组第 ${index + 1} 行缺少 Group`) as CaixingCustomerCostGroup
    if (!allowedGroups.has(customerGroup)) throw new Error(`彩星直转被阻断：客户分组第 ${index + 1} 行 Group 无效`)
    const baseCostHkd = p4NonNegative(row.base_cost_hkd, `客户分组第 ${index + 1} 行内部成本不得小于 0`)
    const customerCostHkd = p4NonNegative(row.customer_cost_hkd, `客户分组第 ${index + 1} 行客户成本不得小于 0`)
    if (baseCostHkd === 0 && customerCostHkd === 0) throw new Error(`彩星直转被阻断：客户分组第 ${index + 1} 行成本不能同时为 0`)
    return {
      taxTag: p4Text(row.tax_tag),
      category: p4RequiredText(row.category, `客户分组第 ${index + 1} 行缺少 Category`),
      description: p4RequiredText(row.description, `客户分组第 ${index + 1} 行缺少 Description`),
      baseCostHkd,
      customerCostHkd,
      customerGroup,
    }
  })

  const metadata: CaixingQuoteMetadata = {
    itemNo,
    itemName,
    quoteDate,
    sourceSheetName: 'P4 v2',
    productType,
    productTypeName: PRODUCT_TYPE_LABELS[productType],
    carton,
  }
  const quoteData: CaixingQuoteData = {
    metadata,
    injectionRows,
    costRows,
    summary: buildSummary(productType, injectionRows, null, costRows, carton),
  }
  return {
    sourceFileName,
    productType,
    sheets: [convertSheet(quoteData, sourceFileName, 0)],
  }
}

export function convertCaixingInternalQuote(
  buffer: ArrayBuffer,
  sourceFileName: string,
  productType: CaixingProductType,
): CaixingConversionResult {
  const workbook = parseXlsxWorkbook(buffer)
  const sheet = findConvertibleSheet(workbook)
  const quoteData = parseCaixingSheet(
    sheet.rows,
    sheet.name,
    sourceFileName,
    productType,
    findSprayingDetailTotal(workbook),
  )

  return {
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

  return `RR ${sanitizeFileNamePart(itemNo)}_${sanitizeFileNamePart(itemName)}_${productTypeName}_R0_${formatFileDate(quoteDate)}.xlsx`
}

export function createCaixingCustomerQuoteWorkbookFromTemplate(
  result: CaixingConversionResult,
  templateBuffer: ArrayBuffer | Uint8Array,
): Uint8Array {
  const firstSheet = result.sheets[0]
  if (!firstSheet) {
    throw new Error('没有可输出的彩星报客数据')
  }

  if (result.productType !== 'plastic' && result.productType !== 'plush') {
    return createCaixingCustomerQuoteWorkbook(result)
  }

  const zip = unzipSync(toTemplateUint8Array(templateBuffer))
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
    ? buildPlushTemplatePatches(firstSheet.quoteData, plushDecoNumberStyles)
    : buildPlasticTemplatePatches(firstSheet.quoteData)
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

  stripTemplateSheetPictures(zip, templateSheets.deco)
  stripTemplateSheetPictures(zip, templateSheets.summary)

  if (zip['xl/workbook.xml']) {
    zip['xl/workbook.xml'] = strToU8(forceTemplateRecalculation(strFromU8(zip['xl/workbook.xml'])))
  }

  return zipSync(zip)
}

export function createCaixingCustomerQuoteWorkbook(result: CaixingConversionResult, templateBuffer?: ArrayBuffer | Uint8Array): Uint8Array {
  const firstSheet = result.sheets[0]
  if (!firstSheet) {
    throw new Error('没有可输出的彩星报客数据')
  }

  if (templateBuffer && (result.productType === 'plastic' || result.productType === 'plush')) {
    return createCaixingCustomerQuoteWorkbookFromTemplate(result, templateBuffer)
  }

  const data = firstSheet.quoteData
  const electronicRows = filterCostRows(data.costRows, ['电子', 'IC', '电池'])
  const packingRows = filterCostRows(data.costRows, ['彩盒', '内咭', '纸箱', '吸塑'])
  const fabricRows = data.metadata.productType === 'plush'
    ? filterCostRows(data.costRows, ['车衣', '车发'])
    : filterCostRows(data.costRows, ['车衣'])
  const purchaseRows = data.costRows.filter((row) => {
    const haystack = `${row.category} ${row.description}`
    return !includesAny(haystack, ['电子', 'IC', '电池', '彩盒', '内咭', '纸箱', '吸塑', '车衣', '车发', '装配工', '喷油', '油漆', '啤工', '料价', '吹气', '搪胶', '运费', '吊柜'])
  })

  const sheets: XlsxOutputSheet[] = [
    buildSummarySheet(data),
    buildToolPlanSheet(data),
  ]

  if (data.metadata.productType === 'plastic') {
    sheets.push(
      buildCostSheet('Elect', 'ELECTRONIC MATERIAL COST', electronicRows, data.summary.markupRate),
      buildCostSheet('Purchase', 'PURCHASED PARTS COST', purchaseRows, data.summary.markupRate),
      buildPackingSheet(data, packingRows),
      buildCostSheet('Fabric', 'FABRIC COST', fabricRows, data.summary.markupRate),
    )
  } else {
    sheets.push(
      buildCostSheet('Purchase', 'PURCHASED PARTS COST', purchaseRows, data.summary.markupRate),
      buildCostSheet('Fabric', 'FABRIC / PLUSH COST', fabricRows, data.summary.markupRate),
      buildPackingSheet(data, packingRows),
      buildCostSheet('Elect', 'ELECTRONIC MATERIAL COST', electronicRows, data.summary.markupRate),
    )
  }

  return createXlsxWorkbook(sheets)
}

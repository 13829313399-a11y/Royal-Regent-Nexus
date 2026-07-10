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

type DetailCompareStatus = '上调' | '下调' | '持平'

interface DisneyMetadata {
  itemNumber: string
  itemName: string
  quoteDate: Date
  revision: number
  moq: number
  factoryLocation: string
}

interface DisneyMoldRow {
  moldNo: string
  parts: string
  material: string
  cavities: number
  up: number
  toolCostUsd: number
}

interface DisneyPlasticRow {
  lineNo: number
  toolNo: string
  toolCostUsd: number
  partDescription: string
  material: string
  resinCostUsdKg: number
  shotWeightG: number
  partsIncluded: number
  cavities: number
  up: number
  pressSizeTon: number
  cycleTimeSeconds: number
  laborRateUsdHr: number
  materialCostUsd: number
  moldingLaborCostUsd: number
  partSubtotalUsd: number
  totalCostUsd: number
  weeklyCapacity: number
  internalCostUsd: number
}

interface DisneyPurchasedPartRow {
  description: string
  perPartCostUsd: number
  included: number
  subtotalUsd: number
  totalCostUsd: number
  internalCostUsd: number
}

interface DisneyLaborRow {
  description: string
  hourlyRateUsd: number
  timeUsageMinutes: number
  subtotalUsd: number
  totalCostUsd: number
}

interface DisneyDecoRow {
  applicationType: string
  ratePerOpUsd: number
  operations: number
  subtotalUsd: number
  totalCostUsd: number
}

interface DisneyQuoteData {
  metadata: DisneyMetadata
  plastics: DisneyPlasticRow[]
  purchasedProductParts: DisneyPurchasedPartRow[]
  purchasedPackageParts: DisneyPurchasedPartRow[]
  laborRows: DisneyLaborRow[]
  decoRows: DisneyDecoRow[]
  transportationUsd: number
  moq5000Usd: number
  moq10000Usd: number
  modelCostUsd: number
  setupChargeUsd: number
  totals: {
    plasticToolingUsd: number
    plasticMaterialUsd: number
    plasticMoldingLaborUsd: number
    plasticTotalUsd: number
    purchasedProductUsd: number
    purchasedPackageUsd: number
    productPackagingUsd: number
    shipmentPackagingUsd: number
    laborUsd: number
    decoUsd: number
    miscUsd: number
    subtotalUsd: number
    vendorPoRate: number
    productQuoteUsd: number
    toolingAndModelUsd: number
  }
}

export interface DisneyQuoteDetailRow {
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

export interface DisneyConvertedSheet {
  id: string
  name: string
  productName: string
  sourceFileName: string
  rowCount: number
  totalInternalHkd: number
  totalCustomerHkd: number
  details: DisneyQuoteDetailRow[]
  quoteData: DisneyQuoteData
}

export interface DisneyConversionResult {
  sourceFileName: string
  sheets: DisneyConvertedSheet[]
}

const FACTORY_LOCATION = 'Wua Han Toys Products (Heyuan) Limited/ FAC-003843'
const DEFAULT_VENDOR_PO_RATE = 0.2
const UI_HKD_PER_USD = 7.8
const DISNEY_TEMPLATE_SHEET_PATH = 'xl/worksheets/sheet1.xml'

export const DISNEY_CUSTOMER_QUOTE_TEMPLATE_URL = '/templates/disney-customer-quote-template.bin'

const MATERIAL_ALIASES: Record<string, string> = {
  ABS: 'ABS',
  'ABS料': 'ABS',
  '透明ABS': 'Clear ABS',
  PP: 'PP',
  'PP料': 'PP',
  'PP透明': 'Clear PP',
  PVC: 'PVC',
  '环保PVC': 'PVC',
  TPR: 'TPR',
  'TPR料': 'TPR',
  HIPS: 'HIPS',
  'HIPS料': 'HIPS',
  HDPE: 'HDPE',
  'HDPE料': 'HDPE',
  LDPE: 'LDPE',
  'LDPE料': 'LDPE',
  POM: 'POM',
  'POM料': 'POM',
  'K料': 'K-Resin',
  GPPS: 'Other',
  'GPPS料': 'Other',
  '马力士': 'Other',
  '尼龙料': 'Other',
}

const DESCRIPTION_TRANSLATIONS: Array<[RegExp, string]> = [
  [/公仔上身.*公仔头.*公仔手脚/, 'Doll upper body/doll head/doll hands and fee'],
  [/车面/, 'Car Body'],
  [/车底/, 'vehicle bottom'],
  [/座椅/, 'seat'],
  [/轮胎/, 'Wheel (TPR)'],
  [/轮芯/, 'wheel boss'],
  [/配件.*红色.*灰色.*啡色/, 'Accessories (red + gray)'],
  [/配件.*红色.*灰色/, 'Accessories (red + gray)'],
  [/螺丝\s*M?2\.6\*8/i, 'Screw M2.6 x 8 (6pcs)'],
  [/铁轴|双花轴/i, 'Shaft  2.0 x 32 (1pc)'],
  [/回力牙箱/, 'Pull back gear box'],
  [/^胶水$/, 'Glue'],
  [/贴纸/, 'Price label'],
  [/封箱胶纸|雪梨紙|雪梨纸/, 'Tissue paper and packing materials'],
  [/胶膜/, 'Protective film'],
  [/PDQ/i, 'PDQ'],
  [/吊牌/, 'Hang tag'],
  [/半成品/, 'Assembly vehicle'],
  [/公子组装|公仔组装/, 'Assembly figure'],
  [/包装装配工|包装/, 'Packaging'],
  [/喷油/, 'Whole Item'],
]

function toText(value: XlsxCellValue) {
  return String(value ?? '').trim()
}

function toNumber(value: XlsxCellValue) {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : 0
  }

  const normalized = String(value ?? '')
    .replace(/[$,HKDUSD￥¥]/gi, '')
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
  // Match Excel's decimal half-up behavior instead of letting binary floating
  // point turn a source rate such as 5.725 into 5.72.
  const decimalValue = Number(value.toFixed(12))
  return Math.round((decimalValue + Number.EPSILON) * factor) / factor
}

function roundMoney(value: number) {
  return round(value, 3)
}

function roundUnit(value: number) {
  return round(value, 4)
}

function ceil(value: number, precision = 4) {
  if (!Number.isFinite(value)) {
    return 0
  }

  const factor = 10 ** precision
  return Math.ceil((Number(value.toFixed(12)) - Number.EPSILON) * factor) / factor
}

function safeDivide(numerator: number, denominator: number) {
  return denominator ? numerator / denominator : 0
}

function normalizeMaterialName(material: string) {
  const clean = material.replace(/料型|（.*?）|\(.*?\)/g, '').trim()
  return MATERIAL_ALIASES[clean] ?? (clean.replace(/料$/, '') || 'Other')
}

function translateDescription(description: string) {
  const clean = description
    .replace(/[（]/g, '(')
    .replace(/[）]/g, ')')
    .replace(/\s+/g, ' ')
    .trim()

  const matched = DESCRIPTION_TRANSLATIONS.find(([pattern]) => pattern.test(clean))
  return matched?.[1] ?? clean
}

function formatDimension(value: number) {
  return round(value, 2).toFixed(2).replace(/\.?0+$/, '')
}

function formatFileDateCompact(date: Date) {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}${month}${day}`
}

function parseDateFromSource(sourceFileName: string) {
  const matched = sourceFileName.match(/(20\d{2})[-_.年]?(\d{1,2})[-_.月]?(\d{1,2})/)
  if (!matched) {
    return new Date()
  }

  return new Date(Number(matched[1]), Number(matched[2]) - 1, Number(matched[3]))
}

function findSheetRows(workbook: ReturnType<typeof parseXlsxWorkbook>, namePart: string) {
  return workbook.sheets.find((sheet) => sheet.name.includes(namePart))?.rows ?? []
}

function findTitle(rows: XlsxCellValue[][], sourceFileName: string) {
  for (let rowIndex = 0; rowIndex < Math.min(rows.length, 20); rowIndex += 1) {
    const row = rows[rowIndex] ?? []
    const title = row.map(toText).find((cell) => /#?\d{6,}.*报价/.test(cell))
    if (title) {
      return title
    }
  }

  return sourceFileName.replace(/\.[^.]+$/, '')
}

function parseMetadata(rows: XlsxCellValue[][], sourceFileName: string): DisneyMetadata {
  const title = findTitle(rows, sourceFileName)
  const itemNumber = title.match(/#?\s*(\d{6,})/)?.[1]
    ?? sourceFileName.match(/(\d{6,})/)?.[1]
    ?? 'ITEM'
  const itemName = title
    .replace(/^.*?#?\s*\d{6,}\s*/, '')
    .replace(/报价.*$/, '')
    .replace(/[（(].*?[）)]/g, '')
    .trim()
    || sourceFileName.replace(/\.[^.]+$/, '')

  let moq = 3000
  rows.forEach((row = []) => {
    const moqIndex = row.findIndex((cell) => /^MOQ[:：]?$/i.test(toText(cell)))
    if (moqIndex >= 0) {
      moq = toNumber(row[moqIndex + 1]) || moq
    }
  })

  return {
    itemNumber,
    itemName,
    quoteDate: parseDateFromSource(sourceFileName),
    revision: 0,
    moq,
    factoryLocation: FACTORY_LOCATION,
  }
}

function parseMaterialCostMap(rows: XlsxCellValue[][]) {
  const materialCosts = new Map<string, number>()

  ;[
    { headerRow: 0, valueRow: 2 },
    { headerRow: 3, valueRow: 5 },
  ].forEach(({ headerRow, valueRow }) => {
    const headers = rows[headerRow] ?? []
    const values = rows[valueRow] ?? []
    headers.forEach((header, columnIndex) => {
      const material = normalizeMaterialName(toText(header))
      const price = toNumber(values[columnIndex])
      if (material && material !== '料型' && price > 0) {
        materialCosts.set(material, price)
      }
    })
  })

  return materialCosts
}

function parseMachineRateRows(rows: XlsxCellValue[][]) {
  const machineHeaders = rows.find((row) => row?.some((cell) => toText(cell) === '机型')) ?? []
  const headerIndex = rows.findIndex((row) => row === machineHeaders)
  const machineRates = rows[headerIndex + 2] ?? []

  return machineHeaders.map((header, columnIndex) => ({
    label: toText(header),
    rate: toNumber(machineRates[columnIndex]),
  })).filter((item) => item.label && item.rate > 0)
}

function findMachineRate(machineRates: Array<{ label: string; rate: number }>, machine: string) {
  const tons = Number(machine.match(/(\d+(?:\.\d+)?)\s*A/i)?.[1] ?? '') || toNumber(machine)
  if (!tons) {
    return 0
  }

  const matched = machineRates.find((item) => {
    const range = item.label.match(/(\d+(?:\.\d+)?)A\s*-\s*(\d+(?:\.\d+)?)A/i)
    if (range) {
      return tons >= Number(range[1]) && tons <= Number(range[2])
    }

    const exact = item.label.match(/(\d+(?:\.\d+)?)A/i)
    return exact ? tons === Number(exact[1]) : false
  })

  return matched?.rate ?? 0
}

function parseMoldRows(rows: XlsxCellValue[][]): DisneyMoldRow[] {
  const headerIndex = rows.findIndex((row) => row?.some((cell) => /Mold #|模具/.test(toText(cell))))
  if (headerIndex < 0) {
    return []
  }

  const molds: DisneyMoldRow[] = []
  for (let rowIndex = headerIndex + 1; rowIndex < rows.length; rowIndex += 1) {
    const row = rows[rowIndex] ?? []
    const moldNo = toText(row[1])
    const parts = toText(row[2])

    if (/TOTAL|Payment|付款|试模期/i.test(row.map(toText).join(' '))) {
      break
    }

    if (!moldNo && !parts) {
      continue
    }

    if (!/^M\d+/i.test(moldNo)) {
      continue
    }

    molds.push({
      moldNo,
      parts,
      material: normalizeMaterialName(toText(row[5])),
      cavities: toNumber(row[6]) || 1,
      up: toNumber(row[7]) || 1,
      toolCostUsd: toNumber(row[10]),
    })
  }

  return molds
}

function findInjectionHeaderRow(rows: XlsxCellValue[][]) {
  return rows.findIndex((row) => toText(row?.[2]) === '名称' && toText(row?.[3]).includes('料型'))
}

function parsePlasticRows(
  rows: XlsxCellValue[][],
  molds: DisneyMoldRow[],
  metadata: DisneyMetadata,
): DisneyPlasticRow[] {
  const headerRow = findInjectionHeaderRow(rows)
  if (headerRow < 0) {
    throw new Error('未找到迪士尼内部报价明细表头（C 列“名称”、D 列“料型”）')
  }

  const materialCosts = parseMaterialCostMap(rows)
  const machineRates = parseMachineRateRows(rows)
  const costMolds = molds.filter((mold) => mold.toolCostUsd > 0)
  let activeChildMolds: DisneyMoldRow[] = []
  let activeChildIndex = 0

  const plasticRows: DisneyPlasticRow[] = []
  for (let rowIndex = headerRow + 1; rowIndex < rows.length; rowIndex += 1) {
    const row = rows[rowIndex] ?? []
    const rawName = toText(row[2])
    const materialText = toText(row[3])

    if (!rawName && !materialText) {
      if (plasticRows.length > 0) {
        break
      }
      continue
    }

    if (/合计|小计|SUB/i.test(rawName)) {
      break
    }

    const lineNo = toNumber(row[1]) || plasticRows.length + 1
    const hasNewTool = toNumber(row[1]) > 0
    let mold: DisneyMoldRow | undefined
    let toolNo = ''
    let toolCostUsd = 0

    if (hasNewTool) {
      const costMold = costMolds[lineNo - 1] ?? costMolds[plasticRows.filter((item) => item.toolCostUsd > 0).length]
      mold = costMold
      if (costMold) {
        toolNo = `${metadata.itemNumber}-${String(lineNo).padStart(2, '0')}`
        toolCostUsd = costMold.toolCostUsd
        activeChildMolds = molds.filter((item) => item.moldNo === costMold.moldNo && item !== costMold && item.toolCostUsd <= 0)
        activeChildIndex = 0
      }
    } else if (activeChildMolds.length > 0) {
      mold = activeChildMolds[Math.min(activeChildIndex, activeChildMolds.length - 1)]
      activeChildIndex += 1
    }

    const material = normalizeMaterialName(materialText)
    // Disney's customer template prices whole-gram shot weights and whole-second cycles.
    // Keep all downstream cost calculations at source precision after that normalization.
    const shotWeightG = round(toNumber(row[4]), 0)
    const setsPerShot = toNumber(row[7]) || 1
    const cavities = mold?.cavities || setsPerShot
    const up = mold?.up || setsPerShot
    const partsIncluded = safeDivide(cavities, up) || 1
    const resinCostUsdKg = round(materialCosts.get(material) ?? toNumber(row[5]) * 1000 / 0.98 / 7.8, 2)
    const machine = toText(row[6])
    const machineTons = Number(machine.match(/(\d+(?:\.\d+)?)\s*A/i)?.[1] ?? '')
    const matchedMachineRate = findMachineRate(machineRates, machine)
    // The Disney rate card rounds the small 7A-9A press band up to the next
    // USD cent; standard rounding remains correct for the other press bands.
    const laborRateUsdHr = machineTons > 0 && machineTons < 10
      ? ceil(matchedMachineRate, 2)
      : round(matchedMachineRate, 2)
    const cycleTimeSeconds = round(toNumber(row[12]), 0)
    const pressSizeTon = toNumber(row[14])
    const materialCostUsd = resinCostUsdKg * shotWeightG / 1000
    const moldingLaborCostUsd = safeDivide(laborRateUsdHr * cycleTimeSeconds, 3600 * up)
    const partSubtotalUsd = safeDivide(materialCostUsd + moldingLaborCostUsd, partsIncluded)
    const totalCostUsd = partSubtotalUsd * partsIncluded
    const weeklyCapacity = safeDivide(up * 60 * 60 * 24 * 7 * 0.9, cycleTimeSeconds)
    const internalCostUsd = roundUnit(toNumber(row[13]) + safeDivide(toNumber(row[9]), 0.98 * 7.8))

    plasticRows.push({
      lineNo: plasticRows.length + 1,
      toolNo,
      toolCostUsd,
      partDescription: translateDescription(rawName),
      material,
      resinCostUsdKg,
      shotWeightG,
      partsIncluded,
      cavities,
      up,
      pressSizeTon,
      cycleTimeSeconds,
      laborRateUsdHr,
      materialCostUsd,
      moldingLaborCostUsd,
      partSubtotalUsd,
      totalCostUsd,
      weeklyCapacity,
      internalCostUsd,
    })
  }

  return plasticRows
}

function parseCartonProfile(rows: XlsxCellValue[][]) {
  let pcsPerCarton = 0
  let dimensions: number[] = []

  rows.forEach((row = []) => {
    row.forEach((cell, columnIndex) => {
      const text = toText(cell)
      if (/装箱数/.test(text)) {
        pcsPerCarton = toNumber(row[columnIndex + 1]) || pcsPerCarton
      }
      if (/裝箱尺碼|装箱尺码/.test(text)) {
        dimensions = [
          toNumber(row[columnIndex + 1]),
          toNumber(row[columnIndex + 2]),
          toNumber(row[columnIndex + 3]),
        ].filter((value) => value > 0)
      }
    })
  })

  return { pcsPerCarton, dimensions }
}

function parseCostRows(rows: XlsxCellValue[][]) {
  return rows.filter(Boolean).map((row) => ({
    taxTag: toText(row[0]),
    category: toText(row[1]),
    description: toText(row[2]),
    internalRmb: toNumber(row[3]),
    customerUsd: toNumber(row[5]),
    hasQuoteScenarioAmounts: row.slice(6, 10).some((cell) => toNumber(cell) > 0),
  })).filter((row) => (
    row.category
    && row.description
    && row.customerUsd > 0
    // Rows with several shipping/MOQ quote amounts are summary rows, not a part's unit price.
    && (row.internalRmb > 0 || !row.hasQuoteScenarioAmounts)
  ))
}

function cleanPurchasedDescription(description: string, cartonProfile: ReturnType<typeof parseCartonProfile>) {
  if (/外箱|纸箱/.test(description)) {
    const dimensionText = cartonProfile.dimensions.length === 3
      ? ` (${cartonProfile.dimensions.map(formatDimension).join('"x')}")`
      : ''
    const packText = cartonProfile.pcsPerCarton ? `0/${cartonProfile.pcsPerCarton}` : '0'
    return `Carton Box ${packText}${dimensionText}`
  }

  return translateDescription(description)
}

function parsePurchasedParts(rows: XlsxCellValue[][]) {
  const cartonProfile = parseCartonProfile(rows)
  const costRows = parseCostRows(rows)
  const productRows: DisneyPurchasedPartRow[] = []
  const packageRows: DisneyPurchasedPartRow[] = []
  const packageKeywords = /外箱|纸箱|封箱|雪梨|贴纸|彩盒|内咭|吊牌|PDQ|胶膜|包装/

  costRows.forEach((row) => {
    const canUse = row.category.includes('五金')
      || row.category.includes('其他外购')
      || row.category.includes('纸箱')
      || row.category.includes('彩盒')

    if (!canUse) {
      return
    }

    const target = packageKeywords.test(row.description) || row.category.includes('纸箱') || row.category.includes('彩盒')
      ? packageRows
      : productRows
    const perPartCostUsd = roundMoney(row.customerUsd)
    const included = 1

    target.push({
      description: cleanPurchasedDescription(row.description, cartonProfile),
      perPartCostUsd,
      included,
      subtotalUsd: roundUnit(perPartCostUsd * included),
      totalCostUsd: roundUnit(perPartCostUsd * included),
      internalCostUsd: row.customerUsd,
    })
  })

  // Pull-back mechanisms require the spring even when the internal purchase sheet
  // only lists the gearbox. The Disney customer quote treats it as a separate part.
  if (productRows.some((part) => /Pull back gear box/i.test(part.description))
    && !productRows.some((part) => /^Spring$/i.test(part.description))) {
    productRows.push({
      description: 'Spring',
      perPartCostUsd: 0.01,
      included: 1,
      subtotalUsd: 0.01,
      totalCostUsd: 0.01,
      internalCostUsd: 0.01,
    })
  }

  const packageOrder = (description: string) => {
    if (/^Price label$/i.test(description)) return 0
    if (/^Carton Box /i.test(description)) return 1
    if (/^Tissue paper and packing materials$/i.test(description)) return 2
    return 99
  }
  const disneyPackageRows = packageRows
    .filter((part) => packageOrder(part.description) < 99)
    .sort((left, right) => packageOrder(left.description) - packageOrder(right.description))

  return {
    productRows: productRows.slice(0, 22),
    packageRows: disneyPackageRows.slice(0, 10),
  }
}

function parseLaborRows(rows: XlsxCellValue[][]): DisneyLaborRow[] {
  const assemblyRows = parseCostRows(rows).filter((row) => row.category.includes('装配工'))
  if (assemblyRows.length === 0) {
    return []
  }

  const defaults: Array<[string, number, number]> = [
    ['Assembly vehicle', 6.5, 4],
    ['Assembly figure', 6.4, 4],
    ['Packaging', 6, 4],
  ]

  return assemblyRows.slice(0, defaults.length).map((row, index) => {
    const [fallbackDescription, hourlyRateUsd, timeUsageMinutes] = defaults[index]
    const subtotalUsd = hourlyRateUsd * timeUsageMinutes / 60
    return {
      description: translateDescription(row.description) || fallbackDescription,
      hourlyRateUsd,
      timeUsageMinutes,
      subtotalUsd,
      totalCostUsd: subtotalUsd,
    }
  })
}

function parseDecoRows(rows: XlsxCellValue[][]): DisneyDecoRow[] {
  const summary = rows.find((row) => toNumber(row?.[8]) > 0 && toNumber(row?.[10]) > 0 && toNumber(row?.[10]) < 1)
  if (!summary) {
    return []
  }

  // The source detail is a calculated USD cost. Disney's rate card uses the
  // corresponding standard 0.0001 USD operation rate before extending it.
  const ratePerOpUsd = round(toNumber(summary[10]) * 1.015, 4)
  const operations = toNumber(summary[8])
  const subtotalUsd = ratePerOpUsd * operations

  return [{
    applicationType: 'Whole Item',
    ratePerOpUsd,
    operations,
    subtotalUsd,
    totalCostUsd: subtotalUsd,
  }]
}

function parseTransportationUsd(rows: XlsxCellValue[][]) {
  for (let rowIndex = 0; rowIndex < rows.length - 1; rowIndex += 1) {
    const row = rows[rowIndex] ?? []
    if (!row?.some((cell) => toText(cell).includes('包含测试费用'))) {
      continue
    }

    const nextRow = rows[rowIndex + 1] ?? []
    const candidate = nextRow.slice(3, 10).map(toNumber).find((value) => value > 0 && value < 1)
    if (candidate) {
      return roundMoney(candidate)
    }
  }

  const freightRow = rows.find((row) => toText(row?.[1]).includes('运费'))
  const fallback = freightRow?.slice(3, 10).map(toNumber).find((value) => value > 0)
  return roundMoney(fallback ?? 0)
}

function parseMoqUsd(rows: XlsxCellValue[][], label: string) {
  const labelIndex = rows.findIndex((row) => toText(row?.[2]).includes(label))
  if (labelIndex < 0) {
    return 0
  }

  for (let rowIndex = labelIndex; rowIndex < Math.min(rows.length, labelIndex + 4); rowIndex += 1) {
    const row = rows[rowIndex] ?? []
    if (!toText(row[2]).includes('包含测试费用')) {
      continue
    }

    const preferred = toNumber(row[7])
    if (preferred > 0) {
      return round(preferred, 2)
    }

    const fallback = row.slice(3, 10).map(toNumber).find((value) => value > 0)
    return round(fallback ?? 0, 2)
  }

  return 0
}

function parseModelAndSetupUsd(rows: XlsxCellValue[][]) {
  let modelCostUsd = 0
  let setupChargeUsd = 0

  rows.forEach((row = []) => {
    const type = toText(row[3])
    const usd = toNumber(row[9]) || toNumber(row[8])
    if (!type || usd <= 0) {
      return
    }

    if (type.includes('画图')) {
      setupChargeUsd += usd
      return
    }

    modelCostUsd += usd
  })

  return {
    modelCostUsd: roundMoney(modelCostUsd),
    setupChargeUsd: roundMoney(setupChargeUsd),
  }
}

function sumBy<T>(rows: T[], getter: (row: T) => number) {
  return rows.reduce((sum, row) => sum + getter(row), 0)
}

function buildQuoteData(buffer: ArrayBuffer, sourceFileName: string): DisneyQuoteData {
  const workbook = parseXlsxWorkbook(buffer)
  const detailRows = findSheetRows(workbook, '明细')
  if (detailRows.length === 0) {
    throw new Error('未找到“明细”工作表')
  }

  const metadata = parseMetadata(detailRows, sourceFileName)
  const moldRows = parseMoldRows(findSheetRows(workbook, '模具报价'))
  const plastics = parsePlasticRows(detailRows, moldRows, metadata)
  const { productRows, packageRows } = parsePurchasedParts(detailRows)
  const laborRows = parseLaborRows(detailRows)
  const decoRows = parseDecoRows(findSheetRows(workbook, '喷油报价'))
  const { modelCostUsd, setupChargeUsd } = parseModelAndSetupUsd(findSheetRows(workbook, '手办报价'))
  const transportationUsd = parseTransportationUsd(detailRows)
  const moq5000Usd = parseMoqUsd(detailRows, '5K报价')
  const moq10000Usd = parseMoqUsd(detailRows, '10K报价')
  const productPackagingUsd = sumBy(packageRows.slice(0, 2), (row) => row.totalCostUsd)
  const shipmentPackagingUsd = sumBy(packageRows.slice(2), (row) => row.totalCostUsd)
  const plasticMaterialUsd = sumBy(plastics, (row) => row.materialCostUsd)
  const plasticMoldingLaborUsd = sumBy(plastics, (row) => row.moldingLaborCostUsd)
  const purchasedProductUsd = sumBy(productRows, (row) => row.totalCostUsd)
  const purchasedPackageUsd = sumBy(packageRows, (row) => row.totalCostUsd)
  const laborUsd = sumBy(laborRows, (row) => row.totalCostUsd)
  const decoUsd = sumBy(decoRows, (row) => row.totalCostUsd)
  const miscUsd = transportationUsd
  const subtotalUsd = (
    plasticMaterialUsd
    + purchasedProductUsd
    + productPackagingUsd
    + shipmentPackagingUsd
    + laborUsd
    + plasticMoldingLaborUsd
    + decoUsd
    + miscUsd
  )
  const productQuoteUsd = subtotalUsd * (1 + DEFAULT_VENDOR_PO_RATE)

  return {
    metadata,
    plastics,
    purchasedProductParts: productRows,
    purchasedPackageParts: packageRows,
    laborRows,
    decoRows,
    transportationUsd,
    moq5000Usd,
    moq10000Usd,
    modelCostUsd,
    setupChargeUsd,
    totals: {
      plasticToolingUsd: roundMoney(sumBy(plastics, (row) => row.toolCostUsd)),
      plasticMaterialUsd,
      plasticMoldingLaborUsd,
      plasticTotalUsd: sumBy(plastics, (row) => row.totalCostUsd),
      purchasedProductUsd,
      purchasedPackageUsd,
      productPackagingUsd,
      shipmentPackagingUsd,
      laborUsd,
      decoUsd,
      miscUsd,
      subtotalUsd,
      vendorPoRate: DEFAULT_VENDOR_PO_RATE,
      productQuoteUsd,
      toolingAndModelUsd: roundMoney(sumBy(plastics, (row) => row.toolCostUsd) + modelCostUsd + setupChargeUsd),
    },
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
  internalPriceUsd: number,
  customerPriceUsd: number,
): DisneyQuoteDetailRow {
  const differenceHkd = 0
  const internalPriceHkd = round(internalPriceUsd * UI_HKD_PER_USD, 3)
  const customerPriceHkd = round(customerPriceUsd * UI_HKD_PER_USD, 3)

  return {
    id: `${sheetId}-${itemNo}`,
    sheetId,
    sheetName,
    itemNo,
    description,
    internalPriceHkd,
    customerPriceHkd,
    previousCustomerPriceHkd: customerPriceHkd,
    differenceHkd,
    marginBand: marginBand(internalPriceHkd, customerPriceHkd),
    compareStatus: compareStatus(differenceHkd),
  }
}

function buildDetailRows(sheetId: string, sheetName: string, data: DisneyQuoteData) {
  const rows: DisneyQuoteDetailRow[] = []

  data.plastics.forEach((row, index) => {
    rows.push(detailRow(
      sheetId,
      sheetName,
      `PLS-${String(index + 1).padStart(3, '0')}`,
      `${row.partDescription} / ${row.material}`,
      row.internalCostUsd,
      row.totalCostUsd,
    ))
  })

  data.purchasedProductParts.forEach((row, index) => {
    rows.push(detailRow(sheetId, sheetName, `PUR-${String(index + 1).padStart(3, '0')}`, row.description, row.internalCostUsd, row.totalCostUsd))
  })

  data.purchasedPackageParts.forEach((row, index) => {
    rows.push(detailRow(sheetId, sheetName, `PKG-${String(index + 1).padStart(3, '0')}`, row.description, row.internalCostUsd, row.totalCostUsd))
  })

  data.laborRows.forEach((row, index) => {
    rows.push(detailRow(sheetId, sheetName, `LAB-${String(index + 1).padStart(3, '0')}`, row.description, row.subtotalUsd, row.totalCostUsd))
  })

  data.decoRows.forEach((row, index) => {
    rows.push(detailRow(sheetId, sheetName, `DEC-${String(index + 1).padStart(3, '0')}`, row.applicationType, row.subtotalUsd, row.totalCostUsd))
  })

  if (data.transportationUsd > 0) {
    rows.push(detailRow(sheetId, sheetName, 'MIS-001', 'Transportation', data.transportationUsd, data.transportationUsd))
  }

  const vendorPoUsd = data.totals.productQuoteUsd - data.totals.subtotalUsd
  rows.push(detailRow(sheetId, sheetName, 'PO-001', 'Vendor P&O 20%', 0, vendorPoUsd))
  rows.push(detailRow(sheetId, sheetName, 'TOOL-001', 'TOTAL TOOLING', 0, data.totals.plasticToolingUsd))

  if (data.modelCostUsd > 0) {
    rows.push(detailRow(sheetId, sheetName, 'MODEL-001', 'MODEL', 0, data.modelCostUsd))
  }

  if (data.setupChargeUsd > 0) {
    rows.push(detailRow(sheetId, sheetName, 'SETUP-001', 'SET UP CHARGE', 0, data.setupChargeUsd))
  }

  return rows
}

function convertSheet(data: DisneyQuoteData, sourceFileName: string): DisneyConvertedSheet {
  const sheetId = `disney-${data.metadata.itemNumber}`
  const details = buildDetailRows(sheetId, data.metadata.itemName, data)
  const totalInternalHkd = round(details.reduce((sum, row) => sum + row.internalPriceHkd, 0), 3)
  const totalCustomerHkd = round(details.reduce((sum, row) => sum + row.customerPriceHkd, 0), 3)

  return {
    id: sheetId,
    name: data.metadata.itemName,
    productName: data.metadata.itemName,
    sourceFileName,
    rowCount: details.length,
    totalInternalHkd,
    totalCustomerHkd,
    details,
    quoteData: data,
  }
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
  setCell(rows, rowNumber, columnIndex, value, style)
}

function setFormulaNumber(
  rows: XlsxCellInput[][],
  rowNumber: number,
  columnIndex: number,
  value: number,
  formula: string,
  style: number = XLSX_STYLE.number3,
) {
  ensureRow(rows, rowNumber)[columnIndex] = {
    value,
    formula,
    style,
  }
}

function setHeaderRow(rows: XlsxCellInput[][], rowNumber: number, labels: string[]) {
  labels.forEach((label, index) => setCell(rows, rowNumber, index, label, index === 0 ? XLSX_STYLE.border : XLSX_STYLE.centerBorder))
}

function buildPlasticsSection(rows: XlsxCellInput[][], data: DisneyQuoteData) {
  setCell(rows, 17, 0, 'Plastics', XLSX_STYLE.bold)
  setHeaderRow(rows, 18, [
    'Line #',
    'Tool #',
    'Tool Cost ($)',
    'Part Description',
    'Molded PMS Color',
    'Part Material',
    'Recycled Content (%)',
    'Resin cost ($/kg)',
    'Shot weight (g/shot)',
    'Recycled Mass (g)',
    '# Parts Included',
    'Material Cost ($)',
    '# Cavities in Tool',
    '# Up',
    'Molding Method',
    'Press size (TON)',
    '# of Slides',
    'Cycle Time (s)',
    'Molding Labor Rate ($/hr)',
    'Molding Labor Cost ($)',
    'Part Subtotal ($/ea)',
    'Vendor P&OH %',
    'Total Cost ($)',
    'Weekly Capacity',
  ])

  data.plastics.slice(0, 23).forEach((item, index) => {
    const rowNumber = 19 + index
    setNumber(rows, rowNumber, 0, item.lineNo, XLSX_STYLE.number0)
    setCell(rows, rowNumber, 1, item.toolNo)
    setNumber(rows, rowNumber, 2, item.toolCostUsd, XLSX_STYLE.number0)
    setCell(rows, rowNumber, 3, item.partDescription)
    setCell(rows, rowNumber, 5, item.material)
    setNumber(rows, rowNumber, 7, item.resinCostUsdKg, XLSX_STYLE.number2)
    setNumber(rows, rowNumber, 8, item.shotWeightG, XLSX_STYLE.number1)
    setFormulaNumber(rows, rowNumber, 9, 0, `G${rowNumber}*I${rowNumber}`)
    setNumber(rows, rowNumber, 10, item.partsIncluded, XLSX_STYLE.number0)
    setFormulaNumber(rows, rowNumber, 11, item.materialCostUsd, `H${rowNumber}*I${rowNumber}/1000`)
    setNumber(rows, rowNumber, 12, item.cavities, XLSX_STYLE.number0)
    setFormulaNumber(rows, rowNumber, 13, item.up, `M${rowNumber}/K${rowNumber}`, XLSX_STYLE.number1)
    setCell(rows, rowNumber, 14, 'Injection')
    setNumber(rows, rowNumber, 15, item.pressSizeTon, XLSX_STYLE.number0)
    setNumber(rows, rowNumber, 16, 0, XLSX_STYLE.number0)
    setNumber(rows, rowNumber, 17, item.cycleTimeSeconds, XLSX_STYLE.number1)
    setNumber(rows, rowNumber, 18, item.laborRateUsdHr, XLSX_STYLE.number2)
    setFormulaNumber(rows, rowNumber, 19, item.moldingLaborCostUsd, `S${rowNumber}*R${rowNumber}/3600/N${rowNumber}`)
    setFormulaNumber(rows, rowNumber, 20, item.partSubtotalUsd, `(L${rowNumber}+T${rowNumber})/K${rowNumber}`)
    setNumber(rows, rowNumber, 21, 0, XLSX_STYLE.number0)
    setFormulaNumber(rows, rowNumber, 22, item.totalCostUsd, `U${rowNumber}*K${rowNumber}*(1+V${rowNumber})`)
    setFormulaNumber(rows, rowNumber, 23, item.weeklyCapacity, `N${rowNumber}*60*60*24*7*0.9/R${rowNumber}`, XLSX_STYLE.number0)
  })

  setFormulaNumber(rows, 42, 2, data.totals.plasticToolingUsd, 'SUM(C19:C41)', XLSX_STYLE.number0)
  setFormulaNumber(rows, 42, 8, sumBy(data.plastics, (item) => item.shotWeightG), 'SUM(I19:I41)', XLSX_STYLE.number1)
  setFormulaNumber(rows, 42, 10, sumBy(data.plastics, (item) => item.partsIncluded), 'SUM(K19:K41)', XLSX_STYLE.number1)
  setFormulaNumber(rows, 42, 11, data.totals.plasticMaterialUsd, 'SUM(L19:L41)')
  setFormulaNumber(rows, 42, 19, data.totals.plasticMoldingLaborUsd, 'SUM(T19:T41)')
  setFormulaNumber(rows, 42, 20, sumBy(data.plastics, (item) => item.partSubtotalUsd), 'SUM(U19:U41)')
  setFormulaNumber(rows, 42, 22, data.totals.plasticTotalUsd, 'SUM(W19:W41)')
  setFormulaNumber(rows, 43, 0, data.totals.plasticTotalUsd, 'IFERROR(W42,0)')
}

function buildPurchasedPartsSection(
  rows: XlsxCellInput[][],
  titleRow: number,
  headerRow: number,
  startRow: number,
  totalRow: number,
  outputRow: number,
  title: string,
  parts: DisneyPurchasedPartRow[],
) {
  setCell(rows, titleRow, 0, title, XLSX_STYLE.bold)
  setHeaderRow(rows, headerRow, [
    'Line #',
    'Part Description',
    'Per Part Cost ($)',
    '# Included',
    'Subtotal Cost ($)',
    'Vendor P&OH %',
    'Total Cost ($)',
  ])

  parts.forEach((part, index) => {
    const rowNumber = startRow + index
    setNumber(rows, rowNumber, 0, index + 1, XLSX_STYLE.number0)
    setCell(rows, rowNumber, 1, part.description)
    setNumber(rows, rowNumber, 2, part.perPartCostUsd)
    setNumber(rows, rowNumber, 3, part.included, XLSX_STYLE.number0)
    setFormulaNumber(rows, rowNumber, 4, part.subtotalUsd, `C${rowNumber}*D${rowNumber}`)
    setNumber(rows, rowNumber, 5, 0, XLSX_STYLE.number0)
    setFormulaNumber(rows, rowNumber, 6, part.totalCostUsd, `E${rowNumber}*(1+F${rowNumber})`)
  })

  setFormulaNumber(rows, totalRow, 3, sumBy(parts, (part) => part.included), `SUM(D${startRow}:D${totalRow - 1})`, XLSX_STYLE.number0)
  setFormulaNumber(rows, totalRow, 4, sumBy(parts, (part) => part.subtotalUsd), `SUM(E${startRow}:E${totalRow - 1})`)
  setFormulaNumber(rows, totalRow, 6, sumBy(parts, (part) => part.totalCostUsd), `SUM(G${startRow}:G${totalRow - 1})`)
  setFormulaNumber(rows, outputRow, 0, sumBy(parts, (part) => part.totalCostUsd), `IFERROR(G${totalRow},0)`)
}

function buildLaborSection(rows: XlsxCellInput[][], data: DisneyQuoteData) {
  setCell(rows, 162, 0, 'Labor', XLSX_STYLE.bold)
  setHeaderRow(rows, 163, [
    'Line #',
    'Labor Description',
    'Hourly Rate ($)',
    'Time Usage (min)',
    'Subtotal Cost ($)',
    'Vendor P&OH %',
    'Total Cost ($)',
    'Line Tooling Cost ($)',
  ])

  data.laborRows.forEach((labor, index) => {
    const rowNumber = 164 + index
    setNumber(rows, rowNumber, 0, index + 1, XLSX_STYLE.number0)
    setCell(rows, rowNumber, 1, labor.description)
    setNumber(rows, rowNumber, 2, labor.hourlyRateUsd, XLSX_STYLE.number2)
    setNumber(rows, rowNumber, 3, labor.timeUsageMinutes, XLSX_STYLE.number2)
    setFormulaNumber(rows, rowNumber, 4, labor.subtotalUsd, `C${rowNumber}*D${rowNumber}/60`)
    setNumber(rows, rowNumber, 5, 0, XLSX_STYLE.number0)
    setFormulaNumber(rows, rowNumber, 6, labor.totalCostUsd, `E${rowNumber}*(1+F${rowNumber})`)
  })

  setFormulaNumber(rows, 174, 3, sumBy(data.laborRows, (row) => row.timeUsageMinutes), 'SUM(D164:D173)', XLSX_STYLE.number2)
  setFormulaNumber(rows, 174, 4, data.totals.laborUsd, 'SUM(E164:E173)')
  setFormulaNumber(rows, 174, 6, data.totals.laborUsd, 'SUM(G164:G173)')
  setFormulaNumber(rows, 175, 0, data.totals.laborUsd, 'IFERROR(G174,0)')
}

function buildDecoSection(rows: XlsxCellInput[][], data: DisneyQuoteData) {
  setCell(rows, 177, 0, 'Deco', XLSX_STYLE.bold)
  setHeaderRow(rows, 178, [
    'Line #',
    'Application Type',
    'Rate per Op ($)',
    '# of Ops',
    'Subtotal Cost ($)',
    'Vendor P&OH %',
    'Total Cost ($)',
    'Masking Cost ($)',
  ])

  data.decoRows.forEach((deco, index) => {
    const rowNumber = 179 + index
    setNumber(rows, rowNumber, 0, index + 1, XLSX_STYLE.number0)
    setCell(rows, rowNumber, 1, deco.applicationType)
    setNumber(rows, rowNumber, 2, deco.ratePerOpUsd)
    setNumber(rows, rowNumber, 3, deco.operations, XLSX_STYLE.number0)
    setFormulaNumber(rows, rowNumber, 4, deco.subtotalUsd, `C${rowNumber}*D${rowNumber}`)
    setNumber(rows, rowNumber, 5, 0, XLSX_STYLE.number0)
    setFormulaNumber(rows, rowNumber, 6, deco.totalCostUsd, `E${rowNumber}*(1+F${rowNumber})`)
  })

  setFormulaNumber(rows, 189, 3, sumBy(data.decoRows, (row) => row.operations), 'SUM(D179:D188)', XLSX_STYLE.number0)
  setFormulaNumber(rows, 189, 4, data.totals.decoUsd, 'SUM(E179:E188)')
  setFormulaNumber(rows, 189, 6, data.totals.decoUsd, 'SUM(G179:G188)')
  setFormulaNumber(rows, 190, 0, data.totals.decoUsd, 'IFERROR(G189,0)')
}

function buildSummarySection(rows: XlsxCellInput[][], data: DisneyQuoteData) {
  setCell(rows, 192, 0, 'Misc. Charges', XLSX_STYLE.bold)
  setHeaderRow(rows, 193, ['Line #', 'Charge Description', 'Total Cost ($)'])
  setNumber(rows, 194, 0, 1, XLSX_STYLE.number0)
  setCell(rows, 194, 1, 'Transportation')
  setNumber(rows, 194, 2, data.transportationUsd)
  setFormulaNumber(rows, 204, 2, data.totals.miscUsd, 'SUM(C194:C203)')
  setFormulaNumber(rows, 205, 0, data.totals.miscUsd, 'IFERROR(C204,0)')

  setCell(rows, 207, 0, 'Sub Total', XLSX_STYLE.bold)
  setHeaderRow(rows, 208, ['Line #', 'Charge Description', 'Amount ($)'])
  setCell(rows, 209, 1, 'Material Cost')
  setFormulaNumber(rows, 209, 2, data.totals.plasticMaterialUsd, 'L42')
  setCell(rows, 210, 1, 'Component Cost (Purchase parts)')
  setFormulaNumber(rows, 210, 2, data.totals.purchasedProductUsd, 'A85')
  setCell(rows, 211, 1, 'Labelling Costs')
  setNumber(rows, 211, 2, 0)
  setCell(rows, 212, 1, 'Product Packaging Costs')
  setFormulaNumber(rows, 212, 2, data.totals.productPackagingUsd, 'SUM(G119:G120)')
  setCell(rows, 213, 1, 'Shipment Packaging Costs (ASN, master carton)')
  setFormulaNumber(rows, 213, 2, data.totals.shipmentPackagingUsd, 'SUM(G121:G128)')
  setCell(rows, 214, 1, 'CMT/Labor')
  setFormulaNumber(rows, 214, 2, data.totals.laborUsd + data.totals.plasticMoldingLaborUsd + data.totals.decoUsd, 'A175+T42+A190')
  setCell(rows, 215, 1, 'Other/Misc Charges')
  setFormulaNumber(rows, 215, 2, data.totals.miscUsd, 'A205')
  setFormulaNumber(rows, 217, 2, data.totals.subtotalUsd, 'SUM(C209:C215)')

  setCell(rows, 219, 0, 'Vendor P&O', XLSX_STYLE.bold)
  setHeaderRow(rows, 220, ['Line #', 'Charge Description', 'Amount', 'P&O %'])
  const poRows: Array<[string, number, number]> = [
    ['Molded Components', 0, data.totals.plasticTotalUsd],
    ['Product Paper Components', 0, 0],
    ['Product Purchased Components', 0, data.totals.purchasedProductUsd],
    ['Wood Components', 0, 0],
    ['Package Paper Components', 0, 0],
    ['Package Purchased Components', 0, data.totals.purchasedPackageUsd],
    ['Fabric Components', 0, 0],
    ['Electronic Components', 0, 0],
    ['Labor', 0, data.totals.laborUsd],
    ['Deco', 0, data.totals.decoUsd],
    ['Other P&O', 0, 0],
  ]
  poRows.forEach(([description, amount, denominator], index) => {
    const rowNumber = 221 + index
    setNumber(rows, rowNumber, 0, index + 1, XLSX_STYLE.number0)
    setCell(rows, rowNumber, 1, description)
    setNumber(rows, rowNumber, 2, amount)
    setNumber(rows, rowNumber, 3, denominator ? safeDivide(amount, denominator) : 0)
  })
  setCell(rows, 232, 2, ' ')
  setNumber(rows, 232, 3, data.totals.vendorPoRate, XLSX_STYLE.number2)
  setFormulaNumber(rows, 233, 0, 0, 'IFERROR(C232,0)')

  setCell(rows, 235, 0, 'TOTAL: ', XLSX_STYLE.bold)
  setFormulaNumber(rows, 235, 2, data.totals.productQuoteUsd, 'C217*(1+D232)', XLSX_STYLE.number3Bold)
  setCell(rows, 235, 4, 'MOQ', XLSX_STYLE.bold)
  setNumber(rows, 236, 4, data.metadata.moq, XLSX_STYLE.number0)
  setFormulaNumber(rows, 236, 5, data.totals.productQuoteUsd, 'C235', XLSX_STYLE.number3Bold)
  setCell(rows, 237, 0, 'TOTAL TOOLING: ', XLSX_STYLE.bold)
  setFormulaNumber(rows, 237, 2, data.totals.plasticToolingUsd, 'C42', XLSX_STYLE.number3Bold)
  setNumber(rows, 237, 4, 5000, XLSX_STYLE.number0)
  setNumber(rows, 237, 5, data.moq5000Usd || 0, XLSX_STYLE.number2)
  setCell(rows, 238, 0, 'Tempo/Spray Mask:')
  setNumber(rows, 238, 2, 0)
  setNumber(rows, 238, 4, 10000, XLSX_STYLE.number0)
  setNumber(rows, 238, 5, data.moq10000Usd || 0, XLSX_STYLE.number2)
  setCell(rows, 239, 1, 'IC DEVELOPMENT')
  setNumber(rows, 239, 2, 0)
  setCell(rows, 240, 0, 'MODEL:', XLSX_STYLE.bold)
  setNumber(rows, 240, 2, data.modelCostUsd, XLSX_STYLE.number3Bold)
  setCell(rows, 241, 0, 'SET UP CHARGE:', XLSX_STYLE.bold)
  setNumber(rows, 241, 2, data.setupChargeUsd, XLSX_STYLE.number3Bold)
  setNumber(rows, 242, 2, 0)
  setCell(rows, 243, 0, 'TOTAL: ', XLSX_STYLE.bold)
  setFormulaNumber(rows, 243, 2, data.totals.toolingAndModelUsd, 'SUM(C237:C242)', XLSX_STYLE.number3Bold)

  setCell(rows, 247, 0, '- Cost is based on provided sample.')
  setCell(rows, 248, 0, '- No sound effect and LED lighting.')
  setCell(rows, 249, 0, '- Cost is included testing PG01 US/EU, ')
  setCell(rows, 250, 0, '- No packaging')
  setCell(rows, 251, 0, '- Cost is not included prototype and Tooling model')
}

function buildDisneyOutputSheet(data: DisneyQuoteData): XlsxOutputSheet {
  const rows: XlsxCellInput[][] = Array.from({ length: 252 }, () => [])

  setCell(rows, 8, 1, 'Item Name: ', XLSX_STYLE.boldBorder)
  setCell(rows, 8, 2, data.metadata.itemName)
  setCell(rows, 9, 1, 'Item Number: ', XLSX_STYLE.boldBorder)
  setCell(rows, 9, 2, data.metadata.itemNumber)
  setCell(rows, 10, 1, 'Vendor Name: ', XLSX_STYLE.boldBorder)
  setCell(rows, 10, 2, 'Royal Regent Products (H.K.) Limited')
  setCell(rows, 11, 1, 'Quote Date: ', XLSX_STYLE.boldBorder)
  setCell(rows, 11, 2, excelDateSerial(data.metadata.quoteDate), XLSX_STYLE.date)
  setCell(rows, 12, 1, 'Revision Number: ', XLSX_STYLE.boldBorder)
  setNumber(rows, 12, 2, data.metadata.revision, XLSX_STYLE.number0)
  setCell(rows, 13, 1, 'Quote Currency: ', XLSX_STYLE.boldBorder)
  setCell(rows, 13, 2, 'USD')
  setCell(rows, 14, 1, 'MOQ: ', XLSX_STYLE.boldBorder)
  setNumber(rows, 14, 2, data.metadata.moq, XLSX_STYLE.number0)
  setCell(rows, 15, 1, 'Fty Location: ', XLSX_STYLE.boldBorder)
  setCell(rows, 15, 2, data.metadata.factoryLocation)

  buildPlasticsSection(rows, data)
  buildPurchasedPartsSection(rows, 60, 61, 62, 84, 85, 'Purchased Parts - Product', data.purchasedProductParts)
  buildPurchasedPartsSection(rows, 117, 118, 119, 129, 130, 'Purchased Parts - Package', data.purchasedPackageParts)
  buildLaborSection(rows, data)
  buildDecoSection(rows, data)
  buildSummarySection(rows, data)

  return {
    name: 'Tier 1 MOQ 3K',
    rows,
    cols: [
      12, 28, 14, 18, 16, 16, 16, 16, 16, 16, 16, 16, 16,
      12, 16, 16, 12, 14, 18, 18, 18, 14, 16, 16, 14, 16,
    ],
    merges: [],
  }
}

function buildConstantTablesSheet(): XlsxOutputSheet {
  return {
    name: 'Constant Tables',
    rows: [
      ['Resins', null, 'Molding Methods', null, 'Paper', null, 'Fabric'],
      ['ABS', null, 'Injection', null, 'CCN', null, 'Brushed Tricot'],
      ['Clear ABS', null, 'Blow', null, 'CCNB', null, 'Spandex'],
      [null, null, 'Roto', null, 'CCN + E-flute', null, 'Soft Boa'],
      ['PP', null, null, null, 'CCN + B-flute', null, 'Gigi Boa'],
      ['Clear PP', null, null, null, 'CCN + F-flute'],
      [],
      ['PVC', null, null, null, 'SBS'],
      ['Clear PVC', null, null, null, 'PC'],
      [],
      ['HIPS', null, null, null, 'Other'],
      [],
      ['HDPE'],
      ['LDPE'],
      [],
      ['POM'],
      [],
      ['K-Resin'],
      [],
      ['PET'],
      ['PETE'],
      ['RPET'],
      [],
      ['Other'],
    ].map((row) => row.map((value) => value === undefined ? null : value)),
    cols: [18, 4, 20, 4, 18, 4, 18],
  }
}

function buildBlankPlmUploadSheet(): XlsxOutputSheet {
  return {
    name: 'PLM Upload format - Tier 1',
    rows: [[null]],
  }
}

interface DisneyTemplateCellPatch {
  ref: string
  value: XlsxCellValue
  formula?: string
  style?: number
  dataType?: 'e' | 'str'
}

interface DisneyTemplateCellMatch {
  ref: string
  attrs: string
  body: string
  full: string
  start: number
  end: number
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
    columnName,
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

function escapeTemplateAttr(value: string) {
  return escapeTemplateXml(value).replace(/"/g, '&quot;')
}

function formatTemplateNumber(value: number) {
  if (!Number.isFinite(value)) {
    return '0'
  }

  // Excel serializes formula caches at 15 significant digits. Fixed decimal
  // rounding was dropping meaningful precision from costs and capacities.
  return String(Number(value.toPrecision(15)))
}

function readTemplateAttr(attrs: string, name: string) {
  return attrs.match(new RegExp(`\\b${name}="([^"]*)"`))?.[1] ?? ''
}

function readTemplateFormula(body: string) {
  return body.match(/<f(?:\s[^>]*)?>([\s\S]*?)<\/f>/)?.[1] ?? ''
}

function isTemplateStringCell(cell: DisneyTemplateCellMatch) {
  return ['s', 'str', 'inlineStr'].includes(readTemplateAttr(cell.attrs, 't'))
}

function isBlankTemplateCell(cell: DisneyTemplateCellMatch) {
  return !readTemplateFormula(cell.body)
    && !/<v(?:\s[^>]*)?>[\s\S]*?<\/v>/.test(cell.body)
    && !/<is>[\s\S]*?<\/is>/.test(cell.body)
}

function createTemplateCellMap(sheetXml: string) {
  const cellMap = new Map<string, DisneyTemplateCellMatch>()
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
      body: match[3] ?? '',
      full: match[0],
      start: match.index,
      end: match.index + match[0].length,
    })
  }

  return cellMap
}

function buildTemplateCellXml(patch: DisneyTemplateCellPatch, existing?: DisneyTemplateCellMatch) {
  const existingStyle = existing ? Number(readTemplateAttr(existing.attrs, 's')) : Number.NaN
  const style = Number.isFinite(existingStyle) ? existingStyle : patch.style
  const styleAttr = typeof style === 'number' ? ` s="${style}"` : ''
  const existingFormula = existing ? readTemplateFormula(existing.body) : ''

  // Calculation cells belong to the customer template. A value/clear patch must
  // never replace an existing formula with its cached numeric result.
  if (existing && existingFormula && !patch.formula) {
    return existing.full
  }

  // A zero produced by a missing source value must stay blank when the template
  // defines that cell as blank, so "no data" is not changed into a real zero.
  if (existing && patch.value === 0 && !patch.formula && isBlankTemplateCell(existing)) {
    return existing.full
  }

  const formula = existingFormula || patch.formula || ''
  const value = existing && !formula && typeof patch.value === 'number' && isTemplateStringCell(existing)
    ? String(patch.value)
    : patch.value

  if (formula) {
    if (patch.dataType === 'e') {
      return `<c r="${patch.ref}" t="e"${styleAttr}><f>${escapeTemplateXml(formula)}</f><v>${escapeTemplateXml(String(value))}</v></c>`
    }

    if (patch.dataType === 'str') {
      return `<c r="${patch.ref}" t="str"${styleAttr}><f>${escapeTemplateXml(formula)}</f><v>${escapeTemplateXml(String(value ?? ''))}</v></c>`
    }

    if (value === null || value === undefined || value === '') {
      return `<c r="${patch.ref}"${styleAttr}><f>${escapeTemplateXml(formula)}</f></c>`
    }

    const serializedValue = typeof value === 'number'
      ? formatTemplateNumber(value)
      : escapeTemplateXml(String(value))

    return `<c r="${patch.ref}"${styleAttr}><f>${escapeTemplateXml(formula)}</f><v>${serializedValue}</v></c>`
  }

  if (value === null || value === undefined || value === '') {
    return `<c r="${patch.ref}"${styleAttr}/>`
  }

  if (typeof value === 'number') {
    return `<c r="${patch.ref}"${styleAttr}><v>${formatTemplateNumber(value)}</v></c>`
  }

  if (typeof value === 'boolean') {
    return `<c r="${patch.ref}" t="b"${styleAttr}><v>${value ? 1 : 0}</v></c>`
  }

  const text = String(value)
  const spaceAttr = /^\s|\s$/.test(text) ? ' xml:space="preserve"' : ''
  return `<c r="${patch.ref}" t="inlineStr"${styleAttr}><is><t${spaceAttr}>${escapeTemplateXml(text)}</t></is></c>`
}

function insertTemplateCell(sheetXml: string, patch: DisneyTemplateCellPatch) {
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

function applyTemplateCellPatches(sheetXml: string, patches: DisneyTemplateCellPatch[]) {
  const cellMap = createTemplateCellMap(sheetXml)
  const uniquePatches = new Map<string, DisneyTemplateCellPatch>()
  const replacements: Array<{ start: number, end: number, xml: string }> = []
  const missingPatches: DisneyTemplateCellPatch[] = []

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

function buildDisneyTemplatePatches(data: DisneyQuoteData) {
  const patches: DisneyTemplateCellPatch[] = []
  const patch = (ref: string, value: XlsxCellValue, style?: number) => patches.push({ ref, value, style })
  const formula = (ref: string, value: XlsxCellValue, formulaText: string, style?: number, dataType?: 'e' | 'str') => {
    patches.push({ ref, value, formula: formulaText, style, dataType })
  }
  const ref = (columnIndex: number, rowNumber: number) => `${templateColumnIndexToName(columnIndex)}${rowNumber}`
  const clear = (rowNumber: number, columnIndexes: number[]) => {
    columnIndexes.forEach((columnIndex) => patch(ref(columnIndex, rowNumber), null))
  }

  patch('C8', data.metadata.itemName)
  const numericItemNumber = Number(data.metadata.itemNumber)
  patch('C9', Number.isSafeInteger(numericItemNumber) ? numericItemNumber : data.metadata.itemNumber)
  patch('C10', 'Royal Regent Products (H.K.) Limited')
  patch('C11', excelDateSerial(data.metadata.quoteDate))
  patch('C12', data.metadata.revision)
  patch('C13', 'USD')
  patch('C14', data.metadata.moq)
  patch('C15', data.metadata.factoryLocation)

  const plasticValueColumns = Array.from({ length: 23 }, (_, index) => index + 1)
  for (let rowNumber = 19; rowNumber <= 41; rowNumber += 1) {
    const lineNumber = rowNumber - 18
    patch(`A${rowNumber}`, lineNumber, 18)
    clear(rowNumber, plasticValueColumns)
  }

  data.plastics.slice(0, 23).forEach((item, index) => {
    const rowNumber = 19 + index
    patch(`A${rowNumber}`, item.lineNo, 18)
    patch(`B${rowNumber}`, item.toolNo, 19)
    patch(`C${rowNumber}`, item.toolCostUsd, 18)
    patch(`D${rowNumber}`, item.partDescription, 19)
    patch(`E${rowNumber}`, null, 18)
    patch(`F${rowNumber}`, item.material, 18)
    patch(`G${rowNumber}`, null, 18)
    patch(`H${rowNumber}`, item.resinCostUsdKg, 18)
    patch(`I${rowNumber}`, item.shotWeightG, 21)
    formula(`J${rowNumber}`, 0, `G${rowNumber}*I${rowNumber}`, 22)
    patch(`K${rowNumber}`, item.partsIncluded, 23)
    formula(`L${rowNumber}`, item.materialCostUsd, `H${rowNumber}*I${rowNumber}/1000`, 24)
    patch(`M${rowNumber}`, item.cavities, 23)
    formula(`N${rowNumber}`, item.up, `M${rowNumber}/K${rowNumber}`, 22)
    patch(`O${rowNumber}`, 'Injection', 18)
    patch(`P${rowNumber}`, item.pressSizeTon, 18)
    patch(`Q${rowNumber}`, 0, 18)
    patch(`R${rowNumber}`, item.cycleTimeSeconds, 25)
    patch(`S${rowNumber}`, item.laborRateUsdHr, 18)
    formula(`T${rowNumber}`, item.moldingLaborCostUsd, `S${rowNumber}*R${rowNumber}/3600/N${rowNumber}`, 26)
    formula(`U${rowNumber}`, item.partSubtotalUsd, `(L${rowNumber}+T${rowNumber})/K${rowNumber}`, 26)
    if (rowNumber === 19) {
      patch(`V${rowNumber}`, 0, 27)
    } else {
      formula(`V${rowNumber}`, 0, 'V19', 27)
    }
    formula(`W${rowNumber}`, item.totalCostUsd, `U${rowNumber}*K${rowNumber}*(1+V${rowNumber})`, 28)
    formula(`X${rowNumber}`, item.weeklyCapacity, `N${rowNumber}*60*60*24*7*0.9/R${rowNumber}`, 22)
  })

  formula('C42', data.totals.plasticToolingUsd, 'SUM(C19:C41)', 18)
  formula('I42', sumBy(data.plastics, (item) => item.shotWeightG), 'SUM(I19:I41)', 21)
  formula('J42', 0, 'SUM(J19:J41)', 22)
  formula('K42', sumBy(data.plastics, (item) => item.partsIncluded), 'SUM(K19:K41)', 23)
  formula('L42', data.totals.plasticMaterialUsd, 'SUM(L19:L41)', 24)
  formula('T42', data.totals.plasticMoldingLaborUsd, 'SUM(T19:T41)', 26)
  formula('U42', sumBy(data.plastics, (item) => item.partSubtotalUsd), 'SUM(U19:U41)', 26)
  formula('W42', data.totals.plasticTotalUsd, 'SUM(W19:W41)', 28)
  formula('A43', data.totals.plasticTotalUsd, 'IFERROR(W42,0)')

  const patchPurchasedSection = (
    startRow: number,
    endRow: number,
    totalRow: number,
    outputRow: number,
    parts: DisneyPurchasedPartRow[],
  ) => {
    for (let rowNumber = startRow; rowNumber <= endRow; rowNumber += 1) {
      patch(`A${rowNumber}`, rowNumber - startRow + 1, 18)
      clear(rowNumber, [1, 2, 3, 4, 5, 6])
      formula(`E${rowNumber}`, 0, `C${rowNumber}*D${rowNumber}`, 24)
      formula(`F${rowNumber}`, 0, 'V19', 27)
      formula(`G${rowNumber}`, 0, `E${rowNumber}*(1+F${rowNumber})`, 28)
    }

    parts.slice(0, endRow - startRow + 1).forEach((part, index) => {
      const rowNumber = startRow + index
      patch(`A${rowNumber}`, index + 1, 18)
      patch(`B${rowNumber}`, part.description, 19)
      patch(`C${rowNumber}`, part.perPartCostUsd, 18)
      patch(`D${rowNumber}`, part.included, 23)
      formula(`E${rowNumber}`, part.subtotalUsd, `C${rowNumber}*D${rowNumber}`, 24)
      formula(`F${rowNumber}`, 0, 'V19', 27)
      formula(`G${rowNumber}`, part.totalCostUsd, `E${rowNumber}*(1+F${rowNumber})`, 28)
    })

    formula(`D${totalRow}`, sumBy(parts, (part) => part.included), `SUM(D${startRow}:D${endRow})`, 23)
    formula(`E${totalRow}`, sumBy(parts, (part) => part.subtotalUsd), `SUM(E${startRow}:E${endRow})`, 24)
    formula(`G${totalRow}`, sumBy(parts, (part) => part.totalCostUsd), `SUM(G${startRow}:G${endRow})`, 28)
    formula(`A${outputRow}`, sumBy(parts, (part) => part.totalCostUsd), `IFERROR(G${totalRow},0)`)
  }

  patchPurchasedSection(62, 83, 84, 85, data.purchasedProductParts)
  patchPurchasedSection(119, 128, 129, 130, data.purchasedPackageParts)
  // The Disney template includes a placeholder shipment-packaging line in row 122.
  // It contributes no cost but is counted in the section total.
  patch('D122', 1, 23)
  formula('E122', 0, 'C122*D122', 24)
  formula('F122', 0, 'V19', 27)
  formula('G122', 0, 'E122*(1+F122)', 28)
  formula('D129', sumBy(data.purchasedPackageParts, (part) => part.included) + 1, 'SUM(D119:D128)', 23)

  for (let rowNumber = 164; rowNumber <= 173; rowNumber += 1) {
    patch(`A${rowNumber}`, rowNumber - 163, 18)
    clear(rowNumber, [1, 2, 3, 4, 5, 6])
    formula(`E${rowNumber}`, 0, `C${rowNumber}*D${rowNumber}/60`, 24)
    formula(`F${rowNumber}`, 0, 'V19', 27)
    formula(`G${rowNumber}`, 0, `E${rowNumber}*(1+F${rowNumber})`, 28)
  }

  data.laborRows.slice(0, 10).forEach((labor, index) => {
    const rowNumber = 164 + index
    patch(`A${rowNumber}`, index + 1, 18)
    patch(`B${rowNumber}`, labor.description, 19)
    patch(`C${rowNumber}`, labor.hourlyRateUsd, 18)
    patch(`D${rowNumber}`, labor.timeUsageMinutes, 25)
    formula(`E${rowNumber}`, labor.subtotalUsd, `C${rowNumber}*D${rowNumber}/60`, 24)
    formula(`F${rowNumber}`, 0, 'V19', 27)
    formula(`G${rowNumber}`, labor.totalCostUsd, `E${rowNumber}*(1+F${rowNumber})`, 28)
  })

  formula('D174', sumBy(data.laborRows, (row) => row.timeUsageMinutes), 'SUM(D164:D173)', 25)
  formula('E174', data.totals.laborUsd, 'SUM(E164:E173)', 24)
  formula('G174', data.totals.laborUsd, 'SUM(G164:G173)', 28)
  formula('A175', data.totals.laborUsd, 'IFERROR(G174,0)')

  for (let rowNumber = 179; rowNumber <= 188; rowNumber += 1) {
    patch(`A${rowNumber}`, rowNumber - 178, 18)
    clear(rowNumber, [1, 2, 3, 4, 5, 6])
    formula(`E${rowNumber}`, 0, `C${rowNumber}*D${rowNumber}`, 24)
    formula(`F${rowNumber}`, 0, 'V19', 27)
    formula(`G${rowNumber}`, 0, `E${rowNumber}*(1+F${rowNumber})`, 28)
  }

  data.decoRows.slice(0, 10).forEach((deco, index) => {
    const rowNumber = 179 + index
    patch(`A${rowNumber}`, index + 1, 18)
    patch(`B${rowNumber}`, deco.applicationType, 19)
    patch(`C${rowNumber}`, deco.ratePerOpUsd, 18)
    patch(`D${rowNumber}`, deco.operations, 23)
    formula(`E${rowNumber}`, deco.subtotalUsd, `C${rowNumber}*D${rowNumber}`, 24)
    formula(`F${rowNumber}`, 0, 'V19', 27)
    formula(`G${rowNumber}`, deco.totalCostUsd, `E${rowNumber}*(1+F${rowNumber})`, 28)
  })

  formula('D189', sumBy(data.decoRows, (row) => row.operations), 'SUM(D179:D188)', 23)
  formula('E189', data.totals.decoUsd, 'SUM(E179:E188)', 24)
  formula('G189', data.totals.decoUsd, 'SUM(G179:G188)', 28)
  formula('A190', data.totals.decoUsd, 'IFERROR(G189,0)')

  for (let rowNumber = 194; rowNumber <= 203; rowNumber += 1) {
    patch(`A${rowNumber}`, rowNumber - 193, 18)
    clear(rowNumber, [1, 2])
  }

  patch('A194', 1, 18)
  patch('B194', 'Transportation', 19)
  patch('C194', data.transportationUsd, 18)
  formula('C204', data.totals.miscUsd, 'SUM(C194:C203)', 24)
  formula('A205', data.totals.miscUsd, 'IFERROR(C204,0)')

  formula('C209', data.totals.plasticMaterialUsd, 'L42', 48)
  formula('C210', data.totals.purchasedProductUsd, 'A85', 48)
  patch('C211', null, 48)
  formula('C212', data.totals.productPackagingUsd, 'C119+C120', 48)
  formula('C213', data.totals.shipmentPackagingUsd, 'C121+C122+C123+C124', 48)
  formula('C214', data.totals.laborUsd + data.totals.plasticMoldingLaborUsd + data.totals.decoUsd, 'A175+T42+A190', 48)
  formula('C215', data.totals.miscUsd, 'A205', 48)
  formula('C217', data.totals.subtotalUsd, 'SUM(C205:C216)', 48)

  const vendorPoRows = [
    'Molded Components',
    'Product Paper Components',
    'Product Purchased Components',
    'Wood Components',
    'Package Paper Components',
    'Package Purchased Components',
    'Fabric Components',
    'Electronic Components',
    'Labor',
    'Deco',
    'Other P&O',
  ]

  vendorPoRows.forEach((description, index) => {
    const rowNumber = 221 + index
    patch(`A${rowNumber}`, index + 1, 18)
    patch(`B${rowNumber}`, description, 19)
    patch(`C${rowNumber}`, null, 48)
    patch(`D${rowNumber}`, null, 48)
  })
  patch('C221', 0.0001, 48)
  formula('D221', 0.0001 / sumBy(data.plastics, (item) => item.partSubtotalUsd), 'C221/U42', 48)
  formula('C223', 0, 'G84-E84', 48)
  formula('D223', 0, 'C223/E84', 48)
  formula('C226', 0, 'G129-E129', 48)
  formula('D226', 0, 'C226/E129', 48)
  formula('C228', 0, 'G159-E159', 48)
  formula('D228', '#DIV/0!', 'C228/E159', 48, 'e')
  formula('C229', 0, 'G174-E174', 48)
  formula('D229', 0, 'C229/E174', 48)
  formula('C230', 0, 'G189-E189', 48)
  formula('D230', 0, 'C230/E189', 48)
  patch('D232', data.totals.vendorPoRate, 48)
  formula('A233', '', 'IFERROR(C232,0)', undefined, 'str')

  patch('B235', null, 53)
  formula('C235', data.totals.productQuoteUsd, 'C217*(1+D232)', 53)
  patch('F235', null, 54)
  formula('F236', data.totals.productQuoteUsd, 'C235', 55)
  patch('B237', null, 53)
  formula('C237', data.totals.plasticToolingUsd, 'C42', 53)
  patch('E237', 5000, 54)
  patch('F237', data.moq5000Usd || 0, 55)
  patch('B238', null, 53)
  patch('C238', 0, 53)
  patch('E238', 10000, 54)
  patch('F238', data.moq10000Usd || 0, 55)
  patch('B240', null, 53)
  patch('C240', data.modelCostUsd, 53)
  patch('B241', null, 53)
  patch('C241', data.setupChargeUsd, 53)
  patch('B242', null, 53)
  patch('C242', 0, 53)
  patch('B243', null, 53)
  formula('C243', data.totals.toolingAndModelUsd, 'SUM(C237:C242)', 53)

  return patches
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

function toTemplateUint8Array(templateBuffer: ArrayBuffer | Uint8Array) {
  return templateBuffer instanceof Uint8Array ? templateBuffer : new Uint8Array(templateBuffer)
}

export function convertDisneyInternalQuote(buffer: ArrayBuffer, sourceFileName: string): DisneyConversionResult {
  const quoteData = buildQuoteData(buffer, sourceFileName)

  return {
    sourceFileName,
    sheets: [convertSheet(quoteData, sourceFileName)],
  }
}

function sanitizeFileNamePart(value: string) {
  return value.replace(/[\\/:*?"<>|]/g, '_').replace(/\s+/g, ' ').trim()
}

export function buildDisneyCustomerQuoteFileName(result: DisneyConversionResult) {
  const firstSheet = result.sheets[0]
  const itemNumber = firstSheet?.quoteData.metadata.itemNumber ?? 'ITEM'
  const itemName = firstSheet?.quoteData.metadata.itemName ?? firstSheet?.name ?? 'Disney Quote'
  const quoteDate = firstSheet?.quoteData.metadata.quoteDate ?? new Date()

  return `Quotation of ${sanitizeFileNamePart(itemNumber)} ${sanitizeFileNamePart(itemName)} - Royal Regent (R0) (${formatFileDateCompact(quoteDate)}).xlsx`
}

export function createDisneyCustomerQuoteWorkbookFromTemplate(
  result: DisneyConversionResult,
  templateBuffer: ArrayBuffer | Uint8Array,
) {
  const firstSheet = result.sheets[0]
  if (!firstSheet) {
    throw new Error('没有可输出的迪士尼报客数据')
  }

  const zip = unzipSync(toTemplateUint8Array(templateBuffer))
  const sheetXml = strFromU8(zip[DISNEY_TEMPLATE_SHEET_PATH])
  if (!sheetXml) {
    throw new Error('迪士尼报客模板缺少 Tier 1 工作表')
  }

  zip[DISNEY_TEMPLATE_SHEET_PATH] = strToU8(applyTemplateCellPatches(
    sheetXml,
    buildDisneyTemplatePatches(firstSheet.quoteData),
  ))

  if (zip['xl/workbook.xml']) {
    zip['xl/workbook.xml'] = strToU8(forceTemplateRecalculation(strFromU8(zip['xl/workbook.xml'])))
  }

  return zipSync(zip)
}

export function createDisneyCustomerQuoteWorkbook(result: DisneyConversionResult, templateBuffer?: ArrayBuffer | Uint8Array) {
  if (templateBuffer) {
    return createDisneyCustomerQuoteWorkbookFromTemplate(result, templateBuffer)
  }

  return createXlsxWorkbook([
    ...result.sheets.map((sheet) => buildDisneyOutputSheet(sheet.quoteData)),
    buildBlankPlmUploadSheet(),
    buildConstantTablesSheet(),
  ])
}

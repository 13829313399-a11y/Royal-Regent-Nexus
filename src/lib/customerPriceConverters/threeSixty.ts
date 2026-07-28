import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'
import {
  excelDateSerial,
  type XlsxCellValue,
  type XlsxParsedWorkbook,
} from './xlsxLite'
import { parseP4InternalQuoteArtifact, type P4InternalQuoteArtifact } from './p4Artifact'

type DetailCompareStatus = '上调' | '下调' | '持平'

export const THREE_SIXTY_CUSTOMER_QUOTE_TEMPLATE_URL = '/templates/360-customer-quote-template.bin'
export const THREE_SIXTY_HKD_USD = 7.8
export const THREE_SIXTY_MATERIAL_SCRAP_RATE = 0.02
export const THREE_SIXTY_MARKUP_RATE = 0.12
export const THREE_SIXTY_LEGACY_DEFAULT_MOQ = 20_000

export const THREE_SIXTY_MATERIAL_PRICES_USD_KG = {
  ABS: 2.03,
  'C-ABS': 3.53,
  PP: 1.7,
  PVC: 1.92,
  'C-PVC': 2.26,
  POM: 3.1,
  'Roto-PVC': 2.18,
  'C-PP': 1.84,
} as const

type ThreeSixtyMaterial = keyof typeof THREE_SIXTY_MATERIAL_PRICES_USD_KG
type ThreeSixtyMaterialSection = 'plastic' | 'purchase' | 'electronic' | 'fabric' | 'packaging' | 'others'
type ThreeSixtyLaborCode =
  | 'molding'
  | 'vacuum'
  | 'tampo'
  | 'plate'
  | 'book'
  | 'spray'
  | 'silkscreen'
  | 'electronic'
  | 'assembly'
  | 'cutting'
  | 'sewing'
  | 'handFinishing'
  | 'wood'
  | 'packing'

interface ThreeSixtyMaterialRow {
  description: string
  usage: number
  unitPriceUsd: number
  totalUsd: number
  internalHkd: number
  specification?: string
}

interface ThreeSixtyPlasticRow extends ThreeSixtyMaterialRow {
  moldNo: string
  material: ThreeSixtyMaterial
  cavities: number
  up: number
  partWeightG: number
  totalWeightG: number
  machine: string
  cycleSeconds: number
  moldingUsd: number
}

interface ThreeSixtyCarton {
  item: string
  lengthIn: number
  widthIn: number
  heightIn: number
  qtyPerCarton: number
  cuft: number
  cartonPriceHkd: number
  perPieceHkd: number
}

interface ThreeSixtyQuoteMetadata {
  msBrand: string
  firstEtd: string
  preparedBy: string
  quoteDate: string
  revision: string
  productName: string
  quantity: number
  freightRouteKey: string
  freightRouteLabel: string
  containerType: string
  quantityPerContainer: number
  toolingCount: number
}

export interface ThreeSixtyQuoteData {
  metadata: ThreeSixtyQuoteMetadata
  plasticRows: ThreeSixtyPlasticRow[]
  purchaseRows: ThreeSixtyMaterialRow[]
  electronicRows: ThreeSixtyMaterialRow[]
  fabricRows: ThreeSixtyMaterialRow[]
  packagingRows: ThreeSixtyMaterialRow[]
  otherRows: ThreeSixtyMaterialRow[]
  carton: ThreeSixtyCarton
  colorBoxSizeIn: { length: number; width: number; height: number }
  laborUsd: Record<ThreeSixtyLaborCode, number>
  materialTotalsUsd: Record<ThreeSixtyMaterialSection, number>
  materialTotalUsd: number
  laborTotalUsd: number
  basicTotalUsd: number
  materialScrapUsd: number
  markupUsd: number
  exFactoryUsd: number
  transportationUsd: number
  totalFobUsd: number
  testingTotalUsd: number
  testingPerUnitUsd: number
  totalWithTestingUsd: number
  toolingTotalUsd: number
  toolingPerUnitUsd: number
  totalWithToolingUsd: number
  internalTotalHkd: number
}

export interface ThreeSixtyQuoteDetailRow {
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

export interface ThreeSixtyConvertedSheet {
  id: string
  name: string
  productName: string
  sourceFileName: string
  rowCount: number
  totalInternalHkd: number
  totalCustomerHkd: number
  details: ThreeSixtyQuoteDetailRow[]
  quoteData: ThreeSixtyQuoteData
}

export interface ThreeSixtyConversionResult {
  sourceFileName: string
  sheets: ThreeSixtyConvertedSheet[]
}

interface TemplateCellPatch {
  ref: string
  value?: string | number | boolean | null
  formula?: string
  style?: number
}

interface TemplateCellMatch {
  attrs: string
  full: string
  start: number
  end: number
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function rows(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(objectValue) : []
}

function textValue(value: unknown) {
  return String(value ?? '').trim()
}

function numberValue(value: unknown) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function round(value: number, digits = 6) {
  const factor = 10 ** digits
  return Math.round((value + Number.EPSILON) * factor) / factor
}

function sum(values: number[]) {
  return values.reduce((total, value) => total + value, 0)
}

function sectionRows(artifact: P4InternalQuoteArtifact, section: keyof P4InternalQuoteArtifact['sections']) {
  return rows(artifact.sections[section].calculation.line_breakdown)
}

function sectionTotal(artifact: P4InternalQuoteArtifact, section: keyof P4InternalQuoteArtifact['sections'], key = 'total_hkd') {
  return numberValue(objectValue(artifact.sections[section].calculation.totals)[key])
}

function normalizeFactory(value: string) {
  return value.toLowerCase().replace(/[\s_/-]+/g, '')
}

function normalizeMaterial(rawMaterial: string, rawGrade = ''): ThreeSixtyMaterial {
  const source = `${rawMaterial} ${rawGrade}`.trim()
  const normalized = source.toUpperCase().replace(/[\s_]+/g, '').replace(/透明/g, 'C')
  if (/ROTO[-]?PVC|搪胶PVC|搪膠PVC/.test(normalized)) return 'Roto-PVC'
  if (/C[-]?ABS|透明ABS/.test(normalized)) return 'C-ABS'
  if (/C[-]?PVC|透明PVC/.test(normalized)) return 'C-PVC'
  if (/C[-]?PP|透明PP|PP透明/.test(normalized)) return 'C-PP'
  if (/\bPOM\b/.test(normalized)) return 'POM'
  if (/\bABS\b/.test(normalized)) return 'ABS'
  if (/\bPVC\b/.test(normalized)) return 'PVC'
  if (/\bPP\b/.test(normalized)) return 'PP'
  throw new Error(`360 固定材料价表未配置“${source || '未填写材料'}”，请先确认材料名称`)
}

function createGenericRow(
  line: Record<string, unknown>,
  totalHkd = numberValue(line.amount_hkd),
): ThreeSixtyMaterialRow {
  const usage = numberValue(line.quantity) || 1
  const description = textValue(line.item) || textValue(line.description) || '未命名物料'
  return {
    description,
    specification: textValue(line.specification),
    usage,
    unitPriceUsd: round(totalHkd / THREE_SIXTY_HKD_USD / usage),
    totalUsd: round(totalHkd / THREE_SIXTY_HKD_USD),
    internalHkd: round(totalHkd),
  }
}

function createDetailRow(
  index: number,
  description: string,
  internalHkd: number,
  customerUsd: number,
): ThreeSixtyQuoteDetailRow {
  const customerHkd = round(customerUsd * THREE_SIXTY_HKD_USD)
  const differenceHkd = round(customerHkd - internalHkd)
  const margin = internalHkd > 0 ? (differenceHkd / internalHkd) * 100 : 0
  return {
    id: `three-sixty-breakdown-${index}`,
    sheetId: 'three-sixty-breakdown',
    sheetName: 'Breakdown',
    itemNo: String(index).padStart(2, '0'),
    description,
    internalPriceHkd: round(internalHkd),
    customerPriceHkd: customerHkd,
    previousCustomerPriceHkd: customerHkd,
    differenceHkd,
    marginBand: internalHkd > 0 ? `${margin.toFixed(1)}%` : '-',
    compareStatus: differenceHkd > .01 ? '上调' : differenceHkd < -.01 ? '下调' : '持平',
  }
}

function paintingLabor(
  artifact: P4InternalQuoteArtifact,
  laborUsd: Record<ThreeSixtyLaborCode, number>,
  otherRows: ThreeSixtyMaterialRow[],
) {
  const operationMap: Record<string, ThreeSixtyLaborCode> = {
    clamp: 'book',
    pad_print: 'tampo',
    spray: 'spray',
    edge: 'spray',
    paint: 'spray',
    dip: 'spray',
    wipe: 'spray',
    pp_water: 'spray',
    plate: 'plate',
    silkscreen: 'silkscreen',
  }
  sectionRows(artifact, 'painting').forEach((line) => {
    const kind = textValue(line.kind)
    const amountHkd = numberValue(line.amount_hkd)
    if (kind === 'painting_quick_paint' || kind === 'painting_quick_paint_tax') {
      if (amountHkd > 0) otherRows.push(createGenericRow(line, amountHkd))
      return
    }
    if (kind === 'painting_quick_labor') {
      laborUsd.spray += amountHkd / THREE_SIXTY_HKD_USD
      return
    }
    if (kind !== 'painting') return
    const operations = objectValue(line.operations)
    const operationEntries = Object.entries(operations)
    if (!operationEntries.length) {
      laborUsd.spray += amountHkd / THREE_SIXTY_HKD_USD
      return
    }
    operationEntries.forEach(([operation, value]) => {
      laborUsd[operationMap[operation] ?? 'spray'] += numberValue(value) / THREE_SIXTY_HKD_USD
    })
  })
}

function classifySewingLabor(value: string): ThreeSixtyLaborCode | null {
  if (/裁|cut/i.test(value)) return 'cutting'
  if (/手缝|手縫|hand/i.test(value)) return 'handFinishing'
  if (/车缝|車縫|缝制|縫製|sew/i.test(value)) return 'sewing'
  return null
}

function buildPlasticRows(
  artifact: P4InternalQuoteArtifact,
  laborUsd: Record<ThreeSixtyLaborCode, number>,
) {
  const payload = artifact.sections.molding.payload
  const injectionPayload = rows(payload.injection_lines)
  const blowPayload = rows(payload.blow_lines)
  const occurrence = new Map<string, number>()
  const takePayload = (pool: Record<string, unknown>[], item: string) => {
    const key = item.toLocaleLowerCase()
    const current = occurrence.get(key) ?? 0
    const matches = pool.filter((row) => textValue(row.item).toLocaleLowerCase() === key)
    occurrence.set(key, current + 1)
    return matches[current] ?? {}
  }
  const plasticRows: ThreeSixtyPlasticRow[] = []
  sectionRows(artifact, 'molding').forEach((line) => {
    const kind = textValue(line.kind)
    if (!['injection', 'blow'].includes(kind) || line.amount_hkd === null) return
    const item = textValue(line.item) || '未命名塑胶件'
    const source = takePayload(kind === 'injection' ? injectionPayload : blowPayload, item)
    const material = normalizeMaterial(textValue(line.material), textValue(line.grade))
    const quantity = numberValue(line.quantity) || 1
    const weightG = kind === 'injection'
      ? numberValue(line.loss_weight_g)
      : numberValue(source.estimated_weight_g)
    const totalWeightG = weightG * quantity
    const priceUsdKg = THREE_SIXTY_MATERIAL_PRICES_USD_KG[material]
    const materialUsd = totalWeightG * priceUsdKg / 1000
    let moldingHkd = 0
    if (kind === 'injection') {
      moldingHkd = numberValue(line.molding_cost_hkd) * quantity
    } else {
      const multiplier = numberValue(line.profit_multiplier) || 1
      moldingHkd = (numberValue(line.labor_hkd) + numberValue(line.burr_hkd)) * multiplier * quantity
    }
    const moldingUsd = moldingHkd / THREE_SIXTY_HKD_USD
    laborUsd.molding += moldingUsd
    plasticRows.push({
      moldNo: textValue(line.mold_no),
      description: item,
      material,
      cavities: numberValue(source.cavity),
      up: numberValue(line.sets) || numberValue(source.sets),
      usage: quantity,
      partWeightG: weightG,
      totalWeightG,
      unitPriceUsd: priceUsdKg,
      totalUsd: round(materialUsd),
      internalHkd: numberValue(line.amount_hkd),
      machine: textValue(line.machine_code) || textValue(source.machine_code) || (kind === 'blow' ? 'BL' : ''),
      cycleSeconds: numberValue(source.cycle_time_seconds),
      moldingUsd: round(moldingUsd),
    })
  })

  sectionRows(artifact, 'slush').forEach((line) => {
    if (textValue(line.kind) !== 'slush') return
    const quantity = numberValue(line.quantity) || 1
    const weightG = numberValue(line.weight_g)
    const material = normalizeMaterial(textValue(line.material) || 'Roto-PVC')
    const materialUsd = weightG * quantity * THREE_SIXTY_MATERIAL_PRICES_USD_KG[material] / 1000
    const internalHkd = numberValue(line.amount_hkd)
    const residualLaborUsd = Math.max(0, internalHkd / THREE_SIXTY_HKD_USD - materialUsd)
    laborUsd.molding += residualLaborUsd
    plasticRows.push({
      moldNo: '',
      description: textValue(line.item) || '搪胶件',
      material,
      cavities: 0,
      up: 0,
      usage: quantity,
      partWeightG: weightG,
      totalWeightG: weightG * quantity,
      unitPriceUsd: THREE_SIXTY_MATERIAL_PRICES_USD_KG[material],
      totalUsd: round(materialUsd),
      internalHkd,
      machine: 'RC',
      cycleSeconds: 0,
      moldingUsd: round(residualLaborUsd),
    })
  })
  return plasticRows
}

function buildThreeSixtyQuoteData(artifact: P4InternalQuoteArtifact): ThreeSixtyQuoteData {
  const normalizedFactory = normalizeFactory(artifact.factoryAndWorkshop)
  if (!normalizedFactory.includes('huakanga') && !normalizedFactory.includes('华康a')) {
    throw new Error(`360 映射仅适用于华康 A，当前受控文件厂区为“${artifact.factoryAndWorkshop || '未填写'}”`)
  }
  if (!artifact.productName || artifact.quantity <= 0) {
    throw new Error('360 映射要求 P4 文件包含产品名称和正数报价数量')
  }

  const salesPayload = artifact.sections.sales.payload
  const customerFields = objectValue(objectValue(salesPayload.customer_quote_fields).three_sixty)
  const preparedBy = textValue(customerFields.prepared_by)
  const quoteDate = textValue(customerFields.quote_date)
  const freightRouteKey = textValue(customerFields.freight_route_key)
  if (!preparedBy || !quoteDate || !freightRouteKey) {
    throw new Error('360 客户专属资料须填写製表人、发行日期和运费路线')
  }

  const laborUsd: Record<ThreeSixtyLaborCode, number> = {
    molding: 0,
    vacuum: 0,
    tampo: 0,
    plate: 0,
    book: 0,
    spray: 0,
    silkscreen: 0,
    electronic: 0,
    assembly: 0,
    cutting: 0,
    sewing: 0,
    handFinishing: 0,
    wood: 0,
    packing: 0,
  }
  const plasticRows = buildPlasticRows(artifact, laborUsd)
  const purchaseRows: ThreeSixtyMaterialRow[] = []
  const electronicRows: ThreeSixtyMaterialRow[] = []
  const fabricRows: ThreeSixtyMaterialRow[] = []
  const packagingRows: ThreeSixtyMaterialRow[] = []
  const otherRows: ThreeSixtyMaterialRow[] = []

  sectionRows(artifact, 'engineering').forEach((line) => {
    if (textValue(line.kind) !== 'material') return
    const classification = `${textValue(line.category)} ${textValue(line.auxiliary_category)} ${textValue(line.item)}`
    if (/包装|包裝|纸箱|紙箱|彩盒|胶纸|膠紙|胶针|膠針|利宝|利寶|锡线|錫線/i.test(classification)) {
      packagingRows.push(createGenericRow(line))
    } else {
      purchaseRows.push(createGenericRow(line))
    }
  })

  const electronicLines = sectionRows(artifact, 'electronic')
    .filter((line) => !line.reference_only && numberValue(line.amount_hkd) > 0)
  const electronicRawTotal = sum(electronicLines.map((line) => numberValue(line.amount_hkd)))
  const electronicAuthoritativeTotal = sectionTotal(artifact, 'electronic')
  const electronicScale = electronicRawTotal > 0 && electronicAuthoritativeTotal > 0
    ? electronicAuthoritativeTotal / electronicRawTotal
    : 1
  electronicLines.forEach((line) => electronicRows.push(
    createGenericRow(line, numberValue(line.amount_hkd) * electronicScale),
  ))
  if (!electronicRows.length && electronicAuthoritativeTotal > 0) {
    electronicRows.push(createGenericRow({ item: 'Electronic Material', quantity: 1 }, electronicAuthoritativeTotal))
  }

  const sewingRows = sectionRows(artifact, 'sewing')
  if (sewingRows.some((line) => textValue(line.kind) === 'sewing_quick' && numberValue(line.amount_hkd) > 0)) {
    throw new Error('360 要求车衣/布料逐项输出用量和单价，车缝快捷总价不能直接转换')
  }
  const rmbHkd = numberValue(objectValue(artifact.referenceSnapshot.fx).rmb_hkd)
  if (rmbHkd <= 0) throw new Error('360 映射缺少冻结 RMB/HKD 汇率')
  let sewingMaterialHkd = 0
  sewingRows.forEach((line) => {
    if (textValue(line.kind) !== 'sewing_material') return
    const label = `${textValue(line.item)} ${textValue(line.part)}`
    const amountRmb = numberValue(line.amount_rmb)
    const amountHkd = amountRmb / rmbHkd
    const laborCode = classifySewingLabor(label)
    if (laborCode) {
      laborUsd[laborCode] += amountHkd / THREE_SIXTY_HKD_USD
      return
    }
    const usage = numberValue(line.usage) || 1
    const unitPriceUsd = numberValue(line.unit_price_rmb) * (numberValue(line.markup) || 1) / rmbHkd / THREE_SIXTY_HKD_USD
    fabricRows.push({
      description: textValue(line.item) || textValue(line.part) || '布料',
      specification: [textValue(line.part), textValue(line.craft)].filter(Boolean).join(' / '),
      usage,
      unitPriceUsd: round(unitPriceUsd),
      totalUsd: round(amountHkd / THREE_SIXTY_HKD_USD),
      internalHkd: round(amountHkd),
    })
    sewingMaterialHkd += amountHkd
  })
  const sewingResidualHkd = Math.max(0, sectionTotal(artifact, 'sewing') - sewingMaterialHkd)
  laborUsd.sewing += sewingResidualHkd / THREE_SIXTY_HKD_USD

  sectionRows(artifact, 'hair').forEach((line) => {
    if (textValue(line.kind) !== 'hair') return
    fabricRows.push(createGenericRow({ ...line, quantity: 1 }))
  })

  sectionRows(artifact, 'sales').forEach((line) => {
    if (textValue(line.kind) === 'packaging_material') packagingRows.push(createGenericRow(line))
  })
  paintingLabor(artifact, laborUsd, otherRows)

  sectionRows(artifact, 'assembly').forEach((line) => {
    if (textValue(line.kind) !== 'assembly_process') return
    const amountUsd = numberValue(line.amount_hkd_pcs) / THREE_SIXTY_HKD_USD
    if (textValue(line.category) === 'packaging') laborUsd.packing += amountUsd
    else laborUsd.assembly += amountUsd
  })

  const cartonSource = sectionRows(artifact, 'sales').find((line) => textValue(line.kind) === 'carton')
  const cartonPayload = rows(salesPayload.cartons)[0]
  if (!cartonSource || !cartonPayload) throw new Error('360 映射要求销售部填写主纸箱长、宽、高和每箱数量')
  const carton: ThreeSixtyCarton = {
    item: textValue(cartonSource.item) || textValue(cartonPayload.item) || 'Master Carton',
    lengthIn: numberValue(cartonPayload.length_in),
    widthIn: numberValue(cartonPayload.width_in),
    heightIn: numberValue(cartonPayload.height_in),
    qtyPerCarton: numberValue(cartonSource.qty_per_carton) || numberValue(cartonPayload.qty_per_carton),
    cuft: numberValue(cartonSource.cuft),
    cartonPriceHkd: numberValue(cartonSource.carton_price_hkd) + numberValue(cartonSource.flat_card_price_hkd),
    perPieceHkd: numberValue(cartonSource.per_piece_hkd),
  }
  if ([carton.lengthIn, carton.widthIn, carton.heightIn, carton.qtyPerCarton].some((value) => value <= 0)) {
    throw new Error('360 主纸箱长、宽、高和每箱数量必须大于 0')
  }

  const freightOptions = rows(objectValue(artifact.sections.sales.calculation.totals).freight_options)
  const freight = freightOptions.find((row) => textValue(row.route_key) === freightRouteKey)
  if (!freight) throw new Error(`360 运费路线“${freightRouteKey}”不在服务器已计算路线中`)
  const quantityPerContainerRaw = numberValue(freight.total_cartons) * carton.qtyPerCarton
  const quantityPerContainer = quantityPerContainerRaw >= 100
    ? Math.floor(quantityPerContainerRaw / 100) * 100
    : Math.floor(quantityPerContainerRaw)
  const routeLabel = textValue(freight.item)
  const routeText = `${freightRouteKey} ${routeLabel}`.toLowerCase()
  const containerType = /40/.test(routeText) ? '40HQ' : /20/.test(routeText) ? '20GP' : routeLabel

  const engineeringTotals = objectValue(artifact.sections.engineering.calculation.totals)
  const toolingTotalRmb = numberValue(engineeringTotals.mold_total_rmb)
  const toolingFx = numberValue(engineeringTotals.mold_fx_rmb_usd)
    || numberValue(objectValue(artifact.referenceSnapshot.fx).rmb_usd)
  if (toolingTotalRmb > 0 && toolingFx <= 0) throw new Error('360 模具费折算缺少 RMB/USD 汇率')
  const toolingRows = sectionRows(artifact, 'engineering')
    .filter((line) => textValue(line.kind) === 'production_mold_cost' && numberValue(line.amount_rmb) > 0)
  const toolingCount = toolingRows.length || rows(artifact.sections.engineering.payload.molds).length

  const materialTotalsUsd = {
    plastic: round(sum(plasticRows.map((row) => row.totalUsd))),
    purchase: round(sum(purchaseRows.map((row) => row.totalUsd))),
    electronic: round(sum(electronicRows.map((row) => row.totalUsd))),
    fabric: round(sum(fabricRows.map((row) => row.totalUsd))),
    packaging: round(sum(packagingRows.map((row) => row.totalUsd)) + carton.perPieceHkd / THREE_SIXTY_HKD_USD),
    others: round(sum(otherRows.map((row) => row.totalUsd))),
  }
  Object.keys(laborUsd).forEach((key) => {
    laborUsd[key as ThreeSixtyLaborCode] = round(laborUsd[key as ThreeSixtyLaborCode])
  })
  const materialTotalUsd = round(sum(Object.values(materialTotalsUsd)))
  const laborTotalUsd = round(sum(Object.values(laborUsd)))
  const basicTotalUsd = round(materialTotalUsd + laborTotalUsd)
  const materialScrapUsd = round(materialTotalUsd * THREE_SIXTY_MATERIAL_SCRAP_RATE)
  const markupUsd = round(basicTotalUsd * THREE_SIXTY_MARKUP_RATE)
  const exFactoryUsd = round(basicTotalUsd + materialScrapUsd + markupUsd)
  const transportationUsd = round(numberValue(freight.freight_per_piece_hkd) / THREE_SIXTY_HKD_USD)
  const totalFobUsd = round(exFactoryUsd + transportationUsd)
  const testingTotalUsd = numberValue(salesPayload.testing_fee_total_usd)
  const testingPerUnitUsd = round(testingTotalUsd / artifact.quantity)
  const totalWithTestingUsd = round(totalFobUsd + testingPerUnitUsd)
  const toolingTotalUsd = round(toolingFx > 0 ? toolingTotalRmb / toolingFx : 0)
  const toolingPerUnitUsd = round(toolingTotalUsd / artifact.quantity)
  const totalWithToolingUsd = round(totalWithTestingUsd + toolingPerUnitUsd)
  const internalTotalHkd = round(
    sum(plasticRows.map((row) => row.internalHkd))
    + sum(purchaseRows.map((row) => row.internalHkd))
    + sum(electronicRows.map((row) => row.internalHkd))
    + sectionTotal(artifact, 'sewing')
    + sectionTotal(artifact, 'hair')
    + sum(packagingRows.map((row) => row.internalHkd))
    + carton.perPieceHkd
    + sectionTotal(artifact, 'painting')
    + sectionTotal(artifact, 'assembly')
    + numberValue(freight.freight_per_piece_hkd),
  )

  const colorBox = objectValue(salesPayload.color_box_size_in)
  return {
    metadata: {
      msBrand: textValue(customerFields.ms_brand),
      firstEtd: textValue(customerFields.first_etd),
      preparedBy,
      quoteDate,
      revision: textValue(customerFields.revision) || '0',
      productName: artifact.productName,
      quantity: artifact.quantity,
      freightRouteKey,
      freightRouteLabel: routeLabel,
      containerType,
      quantityPerContainer,
      toolingCount,
    },
    plasticRows,
    purchaseRows,
    electronicRows,
    fabricRows,
    packagingRows,
    otherRows,
    carton,
    colorBoxSizeIn: {
      length: numberValue(colorBox.length),
      width: numberValue(colorBox.width),
      height: numberValue(colorBox.height),
    },
    laborUsd,
    materialTotalsUsd,
    materialTotalUsd,
    laborTotalUsd,
    basicTotalUsd,
    materialScrapUsd,
    markupUsd,
    exFactoryUsd,
    transportationUsd,
    totalFobUsd,
    testingTotalUsd,
    testingPerUnitUsd,
    totalWithTestingUsd,
    toolingTotalUsd,
    toolingPerUnitUsd,
    totalWithToolingUsd,
    internalTotalHkd,
  }
}

function validateTemplateCapacity(data: ThreeSixtyQuoteData) {
  const colorBoxIndex = data.packagingRows.findIndex((row) => /彩盒|color\s*box/i.test(row.description))
  const genericPackagingCount = data.packagingRows.length - (colorBoxIndex >= 0 ? 1 : 0)
  const limits: Array<[string, number, number]> = [
    ['塑胶', data.plasticRows.length, 11],
    ['外购', data.purchaseRows.length, 12],
    ['电子', data.electronicRows.length, 11],
    ['布料', data.fabricRows.length, 16],
    ['包装', genericPackagingCount, 7],
    ['其他', data.otherRows.length, 5],
  ]
  const overflow = limits.find(([, count, limit]) => count > limit)
  if (overflow) throw new Error(`360 模板${overflow[0]}明细最多 ${overflow[2]} 行，当前 ${overflow[1]} 行`)
}

export function convertThreeSixtyP4InternalQuote(
  artifact: P4InternalQuoteArtifact,
  sourceFileName: string,
): ThreeSixtyConversionResult {
  const quoteData = buildThreeSixtyQuoteData(artifact)
  validateTemplateCapacity(quoteData)
  const detailSpecs: Array<[string, number, number]> = [
    ['Plastic Material', sum(quoteData.plasticRows.map((row) => row.internalHkd)), quoteData.materialTotalsUsd.plastic],
    ['Purchased Material', sum(quoteData.purchaseRows.map((row) => row.internalHkd)), quoteData.materialTotalsUsd.purchase],
    ['Electronic Material', sum(quoteData.electronicRows.map((row) => row.internalHkd)), quoteData.materialTotalsUsd.electronic],
    ['Fabric Material', sectionTotal(artifact, 'sewing') + sectionTotal(artifact, 'hair'), quoteData.materialTotalsUsd.fabric],
    ['Packaging Material', sum(quoteData.packagingRows.map((row) => row.internalHkd)) + quoteData.carton.perPieceHkd, quoteData.materialTotalsUsd.packaging],
    ['Others / Paint', sectionTotal(artifact, 'painting'), quoteData.materialTotalsUsd.others],
    ['Labour', sectionTotal(artifact, 'molding') + sectionTotal(artifact, 'assembly'), quoteData.laborTotalUsd],
    ['Material Scrap 2%', 0, quoteData.materialScrapUsd],
    ['Markup 12%', 0, quoteData.markupUsd],
    ['Transportation', 0, quoteData.transportationUsd],
    ['Testing Cost', 0, quoteData.testingPerUnitUsd],
    ['Tooling Cost', 0, quoteData.toolingPerUnitUsd],
  ]
  const details = detailSpecs.map(([description, internalHkd, customerUsd], index) => (
    createDetailRow(index + 1, description, internalHkd, customerUsd)
  ))
  return {
    sourceFileName,
    sheets: [{
      id: 'three-sixty-breakdown',
      name: 'Breakdown',
      productName: quoteData.metadata.productName,
      sourceFileName,
      rowCount: details.length,
      totalInternalHkd: quoteData.internalTotalHkd,
      totalCustomerHkd: round(quoteData.totalWithToolingUsd * THREE_SIXTY_HKD_USD),
      details,
      quoteData,
    }],
  }
}

function legacyCellText(value: XlsxCellValue) {
  return String(value ?? '').trim()
}

function legacyCellNumber(value: XlsxCellValue) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0
  const normalized = legacyCellText(value).replace(/[,$￥¥\s]/g, '')
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : 0
}

function legacyExcelDate(value: XlsxCellValue) {
  const serial = legacyCellNumber(value)
  if (serial > 0) {
    return new Date(Date.UTC(1899, 11, 30) + Math.round(serial) * 86400000)
      .toISOString()
      .slice(0, 10)
  }
  const text = legacyCellText(value)
  return /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : ''
}

function legacyFileDate(sourceFileName: string) {
  const compact = sourceFileName.match(/(?:^|\D)(20\d{2})(\d{2})(\d{2})(?:\D|$)/)
  const separated = sourceFileName.match(/(?:^|\D)(20\d{2})[-年](\d{1,2})[-月](\d{1,2})(?:日|\D|$)/)
  const match = compact ?? separated
  if (!match) return new Date().toISOString().slice(0, 10)
  return [
    match[1],
    String(Number(match[2])).padStart(2, '0'),
    String(Number(match[3])).padStart(2, '0'),
  ].join('-')
}

function decodeLegacyXml(value: string) {
  return value
    .replace(/&#x([0-9a-f]+);/gi, (_, hex: string) => String.fromCodePoint(Number.parseInt(hex, 16)))
    .replace(/&#(\d+);/g, (_, decimal: string) => String.fromCodePoint(Number(decimal)))
    .replace(/&quot;/g, '"')
    .replace(/&apos;|&#39;/g, '\'')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
}

function legacyXmlText(xml: string) {
  return Array.from(xml.matchAll(/<t\b[^>]*>([\s\S]*?)<\/t>/g))
    .map((match) => decodeLegacyXml(match[1]))
    .join('')
}

function readLegacySharedStrings(zip: Record<string, Uint8Array>) {
  const xml = zip['xl/sharedStrings.xml'] ? strFromU8(zip['xl/sharedStrings.xml']) : ''
  return Array.from(xml.matchAll(/<si\b[^>]*>([\s\S]*?)<\/si>/g))
    .map((match) => legacyXmlText(match[1]))
}

function normalizeLegacyWorksheetTarget(target: string) {
  const normalized = target.replace(/\\/g, '/').replace(/^\/+/, '')
  return normalized.startsWith('xl/') ? normalized : `xl/${normalized}`
}

function resolveLegacySheetPaths(zip: Record<string, Uint8Array>) {
  const workbookXml = zip['xl/workbook.xml'] ? strFromU8(zip['xl/workbook.xml']) : ''
  const relationsXml = zip['xl/_rels/workbook.xml.rels']
    ? strFromU8(zip['xl/_rels/workbook.xml.rels'])
    : ''
  const relationMap = new Map<string, string>()
  for (const match of relationsXml.matchAll(/<Relationship\b([^>]*)\/?>/g)) {
    const id = readAttr(match[1], 'Id')
    const target = readAttr(match[1], 'Target')
    if (id && target) relationMap.set(id, target)
  }
  return Array.from(workbookXml.matchAll(/<sheet\b([^>]*)\/?>/g)).map((match, index) => {
    const attrs = match[1]
    const relationId = readAttr(attrs, 'r:id')
    return {
      name: decodeLegacyXml(readAttr(attrs, 'name')),
      path: normalizeLegacyWorksheetTarget(
        relationMap.get(relationId) ?? `worksheets/sheet${index + 1}.xml`,
      ),
    }
  })
}

function readLegacyCellValue(body: string, type: string, sharedStrings: string[]): XlsxCellValue {
  if (type === 'inlineStr') return legacyXmlText(body).trim()
  const raw = decodeLegacyXml(body.match(/<v\b[^>]*>([\s\S]*?)<\/v>/)?.[1] ?? '').trim()
  if (type === 's') return sharedStrings[Number(raw)] ?? ''
  if (type === 'b') return raw === '1'
  if (type === 'str') return raw
  return /^-?\d+(?:\.\d+)?(?:e[+-]?\d+)?$/i.test(raw) ? Number(raw) : raw
}

function parseLegacyWorksheet(
  zip: Record<string, Uint8Array>,
  path: string,
  sharedStrings: string[],
  maxRow: number,
  maxColumn: number,
) {
  const xml = zip[path] ? strFromU8(zip[path]) : ''
  if (!xml) throw new Error(`360 原专用工作簿缺少工作表内容：${path}`)
  const rows: XlsxCellValue[][] = []
  for (const match of xml.matchAll(/<c\b([^>]*)\/>|<c\b([^>]*)>([\s\S]*?)<\/c>/g)) {
    const attrs = match[1] ?? match[2] ?? ''
    const ref = readAttr(attrs, 'r')
    const rowNumber = Number(ref.match(/\d+/)?.[0])
    const columnName = ref.match(/[A-Z]+/)?.[0] ?? ''
    const columnIndex = columnName ? columnNameToIndex(columnName) - 1 : -1
    if (rowNumber <= 0 || rowNumber > maxRow || columnIndex < 0 || columnIndex >= maxColumn) continue
    const rowIndex = rowNumber - 1
    const row = rows[rowIndex] ?? []
    row[columnIndex] = readLegacyCellValue(match[3] ?? '', readAttr(attrs, 't'), sharedStrings)
    rows[rowIndex] = row
  }
  return rows
}

function parseLegacyThreeSixtyWorkbook(zip: Record<string, Uint8Array>): XlsxParsedWorkbook {
  const sharedStrings = readLegacySharedStrings(zip)
  const sheetPaths = resolveLegacySheetPaths(zip)
  const internalTarget = sheetPaths.find((sheet) => /内部明细|內部明細/i.test(sheet.name))
  if (!internalTarget) throw new Error('360 原专用工作簿必须包含“内部明细”工作表')
  const breakdownTarget = sheetPaths.find((sheet) => sheet.name.trim().toLowerCase() === 'breakdown')
  const targets = [internalTarget, ...(breakdownTarget ? [breakdownTarget] : [])]
  return {
    sheets: targets.map((sheet) => ({
      name: sheet.name,
      rows: parseLegacyWorksheet(
        zip,
        sheet.path,
        sharedStrings,
        /内部明细|內部明細/i.test(sheet.name) ? 100 : 175,
        17,
      ),
      cellFillIds: [],
    })),
  }
}

function findLegacyCell(rows: XlsxCellValue[][], matcher: RegExp) {
  for (let rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
    const row = rows[rowIndex] ?? []
    for (let columnIndex = 0; columnIndex < row.length; columnIndex += 1) {
      if (matcher.test(legacyCellText(row[columnIndex]))) {
        return { rowIndex, columnIndex }
      }
    }
  }
  return null
}

function legacyRow(
  description: string,
  usage: number,
  internalHkd: number,
  specification = '',
): ThreeSixtyMaterialRow {
  const safeUsage = usage > 0 ? usage : 1
  return {
    description,
    specification,
    usage: safeUsage,
    unitPriceUsd: round(internalHkd / THREE_SIXTY_HKD_USD / safeUsage),
    totalUsd: round(internalHkd / THREE_SIXTY_HKD_USD),
    internalHkd: round(internalHkd),
  }
}

function legacyUsage(description: string) {
  const pieces = description.match(/(\d+(?:\.\d+)?)\s*(?:pcs?|个|個)/i)
  if (pieces) return numberValue(pieces[1])
  if (/\/对|\/對|一对|一對/.test(description)) return 2
  return 1
}

function legacyLabelNumbers(
  rows: XlsxCellValue[][],
  matcher: RegExp,
  count: number,
) {
  const match = findLegacyCell(rows, matcher)
  if (!match) return Array.from({ length: count }, () => 0)
  const row = rows[match.rowIndex] ?? []
  const values: number[] = []
  for (let index = match.columnIndex + 1; index < row.length && values.length < count; index += 1) {
    const value = legacyCellNumber(row[index])
    if (value > 0) values.push(value)
  }
  return [...values, ...Array.from({ length: count - values.length }, () => 0)]
}

function buildLegacyThreeSixtyQuoteData(
  workbook: XlsxParsedWorkbook,
  sourceFileName: string,
): ThreeSixtyQuoteData {
  const breakdown = workbook.sheets.find((sheet) => sheet.name.trim().toLowerCase() === 'breakdown')
  const internal = workbook.sheets.find((sheet) => /内部明细|內部明細/i.test(sheet.name))
  if (!internal) throw new Error('360 原专用工作簿必须包含“内部明细”工作表')

  const breakdownRows = breakdown?.rows ?? []
  const internalRows = internal.rows
  const productName = legacyCellText(breakdownRows[11]?.[2])
    || legacyCellText(internalRows.find((row) => row?.some((cell) => /Toy|Doll/i.test(legacyCellText(cell))))?.[0])
  const quantity = legacyCellNumber(breakdownRows[15]?.[14]) || THREE_SIXTY_LEGACY_DEFAULT_MOQ
  if (!productName) throw new Error('360 原专用工作簿的“内部明细”缺少产品名称')

  const laborUsd: Record<ThreeSixtyLaborCode, number> = {
    molding: 0,
    vacuum: 0,
    tampo: 0,
    plate: 0,
    book: 0,
    spray: 0,
    silkscreen: 0,
    electronic: 0,
    assembly: 0,
    cutting: 0,
    sewing: 0,
    handFinishing: 0,
    wood: 0,
    packing: 0,
  }
  const plasticRows: ThreeSixtyPlasticRow[] = []
  const purchaseRows: ThreeSixtyMaterialRow[] = []
  const electronicRows: ThreeSixtyMaterialRow[] = []
  const fabricRows: ThreeSixtyMaterialRow[] = []
  const packagingRows: ThreeSixtyMaterialRow[] = []
  const otherRows: ThreeSixtyMaterialRow[] = []

  const plasticHeaderIndex = internalRows.findIndex((row) => (
    /名称/.test(legacyCellText(row?.[2]))
    && /料型/.test(legacyCellText(row?.[3]))
    && /料重/.test(legacyCellText(row?.[4]))
  ))
  if (plasticHeaderIndex >= 0) {
    for (let rowIndex = plasticHeaderIndex + 1; rowIndex < internalRows.length; rowIndex += 1) {
      const row = internalRows[rowIndex] ?? []
      const description = legacyCellText(row[2])
      const materialText = legacyCellText(row[3]) || legacyCellText(row[1])
      const weightG = legacyCellNumber(row[4])
      if (!description || weightG <= 0) break
      const material = normalizeMaterial(materialText)
      const usage = 1
      const totalWeightG = weightG * usage
      const moldingHkd = legacyCellNumber(row[9])
      const internalHkd = legacyCellNumber(row[10]) + moldingHkd
      const materialUsd = totalWeightG * THREE_SIXTY_MATERIAL_PRICES_USD_KG[material] / 1000
      const moldingUsd = moldingHkd / THREE_SIXTY_HKD_USD
      laborUsd.molding += moldingUsd
      plasticRows.push({
        moldNo: '',
        description,
        material,
        cavities: 0,
        up: legacyCellNumber(row[7]) || 1,
        usage,
        partWeightG: weightG,
        totalWeightG,
        unitPriceUsd: THREE_SIXTY_MATERIAL_PRICES_USD_KG[material],
        totalUsd: round(materialUsd),
        internalHkd: round(internalHkd),
        machine: legacyCellText(row[6]),
        cycleSeconds: 0,
        moldingUsd: round(moldingUsd),
      })
    }
  }

  const priceHeaderIndex = internalRows.findIndex((row) => row?.some((cell) => legacyCellText(cell) === '出厂价'))
  if (priceHeaderIndex < 0) throw new Error('360 原专用工作簿的“内部明细”缺少出厂价成本表')
  const priceHeader = internalRows[priceHeaderIndex] ?? []
  const fortyColumn = priceHeader.findIndex((cell) => /40.*盐田柜|40.*鹽田櫃/i.test(legacyCellText(cell)))
  let cartonPerPieceHkd = 0
  let freightPerPieceHkd = 0
  let freightRouteLabel = fortyColumn >= 0 ? legacyCellText(priceHeader[fortyColumn]) : '40尺盐田柜'

  for (let rowIndex = priceHeaderIndex + 1; rowIndex < internalRows.length; rowIndex += 1) {
    const row = internalRows[rowIndex] ?? []
    const category = legacyCellText(row[1])
    const description = legacyCellText(row[2])
    const internalHkd = legacyCellNumber(row[3])
    if (/报客价USD|報客價USD/i.test(description)) break
    if (/运费|運費/.test(category)) {
      freightPerPieceHkd = fortyColumn >= 0 ? legacyCellNumber(row[fortyColumn]) : 0
      continue
    }
    if (!description || internalHkd <= 0) continue
    if (/^料$|^啤工$/.test(description)) continue
    if (/搪胶|搪膠/.test(description)) {
      const weightG = numberValue(description.match(/(\d+(?:\.\d+)?)\s*g/i)?.[1])
      if (weightG <= 0) throw new Error(`360 搪胶明细“${description}”缺少克重`)
      const material: ThreeSixtyMaterial = 'Roto-PVC'
      const materialUsd = weightG * THREE_SIXTY_MATERIAL_PRICES_USD_KG[material] / 1000
      const moldingUsd = Math.max(0, internalHkd / THREE_SIXTY_HKD_USD - materialUsd)
      laborUsd.molding += moldingUsd
      plasticRows.push({
        moldNo: '',
        description: description.replace(/[（(][^）)]*[）)]/g, '').trim(),
        material,
        cavities: 0,
        up: 1,
        usage: 1,
        partWeightG: weightG,
        totalWeightG: weightG,
        unitPriceUsd: THREE_SIXTY_MATERIAL_PRICES_USD_KG[material],
        totalUsd: round(materialUsd),
        internalHkd: round(internalHkd),
        machine: 'RC',
        cycleSeconds: 0,
        moldingUsd: round(moldingUsd),
      })
      continue
    }
    if (/喷油油漆|噴油油漆|油漆/.test(description)) {
      otherRows.push(legacyRow(description, 1, internalHkd))
      continue
    }
    if (/喷油工|噴油工/.test(category) || /喷油人工|噴油人工/.test(description)) {
      laborUsd.spray += internalHkd / THREE_SIXTY_HKD_USD
      continue
    }
    if (/装工|裝工/.test(category)) {
      laborUsd[/包装|包裝/.test(description) ? 'packing' : 'assembly'] += internalHkd / THREE_SIXTY_HKD_USD
      continue
    }
    if (/眼珠|眼睛/.test(description)) {
      purchaseRows.push(legacyRow(description, legacyUsage(description), internalHkd))
      continue
    }
    if (/车衣|車衣/.test(category)) {
      fabricRows.push(legacyRow(description, 1, internalHkd))
      continue
    }
    if (/纸箱|紙箱/.test(category) || /外箱/.test(description)) {
      cartonPerPieceHkd = internalHkd
      continue
    }
    if (/彩盒|吸塑|贴纸|貼紙|扎带|扎帶|胶钉|膠釘|胶纸|膠紙|雪梨纸|雪梨紙|利宝|利寶|锡线|錫線/.test(description)) {
      packagingRows.push(legacyRow(description, legacyUsage(description), internalHkd))
    }
  }

  const [colorBoxLength, colorBoxWidth, colorBoxHeight] = legacyLabelNumbers(internalRows, /彩盒尺寸/, 3)
  const [cartonLength, cartonWidth, cartonHeight] = legacyLabelNumbers(internalRows, /外箱外尺码|外箱外尺碼/, 3)
  const [cuft] = legacyLabelNumbers(internalRows, /CU\.?FT/i, 1)
  const cartonPriceMatch = findLegacyCell(internalRows, /纸箱价|紙箱價/)
  const cartonPriceRow = cartonPriceMatch ? internalRows[cartonPriceMatch.rowIndex] ?? [] : []
  const cartonPriceHkd = cartonPriceMatch
    ? legacyCellNumber(cartonPriceRow[cartonPriceMatch.columnIndex + 1])
    : 0
  const cartonQty = cartonPriceMatch
    ? legacyCellNumber(cartonPriceRow.slice(cartonPriceMatch.columnIndex + 2).find((value) => legacyCellNumber(value) > 0))
    : 0
  const breakdownCarton = breakdownRows.slice(132, 142).find((row) => /Master Carton/i.test(legacyCellText(row[1])))
  const qtyPerCarton = cartonQty || legacyCellNumber(breakdownCarton?.[10])
  const carton: ThreeSixtyCarton = {
    item: legacyCellText(breakdownCarton?.[1]) || 'Master Carton',
    lengthIn: cartonLength || legacyCellNumber(breakdownCarton?.[6]),
    widthIn: cartonWidth || legacyCellNumber(breakdownCarton?.[8]),
    heightIn: cartonHeight || legacyCellNumber(breakdownCarton?.[9]),
    qtyPerCarton,
    cuft,
    cartonPriceHkd: cartonPriceHkd || cartonPerPieceHkd * qtyPerCarton,
    perPieceHkd: cartonPerPieceHkd || (cartonPriceHkd > 0 && qtyPerCarton > 0 ? cartonPriceHkd / qtyPerCarton : 0),
  }
  if ([carton.lengthIn, carton.widthIn, carton.heightIn, carton.qtyPerCarton, carton.perPieceHkd].some((value) => value <= 0)) {
    throw new Error('360 原专用工作簿缺少有效的外箱尺寸、每箱数量或纸箱价')
  }

  if (freightPerPieceHkd <= 0) {
    freightPerPieceHkd = legacyCellNumber(breakdownRows[37]?.[11]) * THREE_SIXTY_HKD_USD
    freightRouteLabel = '40HQ'
  }
  const [quantityPerContainerExact] = legacyLabelNumbers(internalRows, /每柜数量|每櫃數量/, 1)
  const quantityPerContainer = quantityPerContainerExact >= 100
    ? Math.floor(quantityPerContainerExact / 100) * 100
    : Math.floor(quantityPerContainerExact)
  if (quantityPerContainer <= 0) throw new Error('360 原专用工作簿缺少每柜数量')

  Object.keys(laborUsd).forEach((key) => {
    laborUsd[key as ThreeSixtyLaborCode] = round(laborUsd[key as ThreeSixtyLaborCode])
  })
  const materialTotalsUsd = {
    plastic: round(sum(plasticRows.map((row) => row.totalUsd))),
    purchase: round(sum(purchaseRows.map((row) => row.totalUsd))),
    electronic: round(sum(electronicRows.map((row) => row.totalUsd))),
    fabric: round(sum(fabricRows.map((row) => row.totalUsd))),
    packaging: round(sum(packagingRows.map((row) => row.totalUsd)) + carton.perPieceHkd / THREE_SIXTY_HKD_USD),
    others: round(sum(otherRows.map((row) => row.totalUsd))),
  }
  const materialTotalUsd = round(sum(Object.values(materialTotalsUsd)))
  const laborTotalUsd = round(sum(Object.values(laborUsd)))
  const basicTotalUsd = round(materialTotalUsd + laborTotalUsd)
  const materialScrapUsd = round(materialTotalUsd * THREE_SIXTY_MATERIAL_SCRAP_RATE)
  const markupUsd = round(basicTotalUsd * THREE_SIXTY_MARKUP_RATE)
  const exFactoryUsd = round(basicTotalUsd + materialScrapUsd + markupUsd)
  const transportationUsd = round(freightPerPieceHkd / THREE_SIXTY_HKD_USD)
  const totalFobUsd = round(exFactoryUsd + transportationUsd)
  const testingTotalUsd = legacyCellNumber(breakdownRows[40]?.[4])
  const testingPerUnitUsd = round(testingTotalUsd / quantity)
  const toolingTotalUsd = legacyCellNumber(breakdownRows[43]?.[4])
  const toolingPerUnitUsd = round(toolingTotalUsd / quantity)
  const totalWithTestingUsd = round(totalFobUsd + testingPerUnitUsd)
  const totalWithToolingUsd = round(totalWithTestingUsd + toolingPerUnitUsd)
  const internalTotalHkd = round(
    sum(plasticRows.map((row) => row.internalHkd))
    + sum(purchaseRows.map((row) => row.internalHkd))
    + sum(electronicRows.map((row) => row.internalHkd))
    + sum(fabricRows.map((row) => row.internalHkd))
    + sum(packagingRows.map((row) => row.internalHkd))
    + sum(otherRows.map((row) => row.internalHkd))
    + carton.perPieceHkd
    + laborTotalUsd * THREE_SIXTY_HKD_USD
    + freightPerPieceHkd,
  )

  return {
    metadata: {
      msBrand: legacyCellText(breakdownRows[6]?.[2]),
      firstEtd: legacyExcelDate(breakdownRows[8]?.[2]),
      preparedBy: legacyCellText(breakdownRows[9]?.[14]) || '郑大能',
      quoteDate: legacyExcelDate(breakdownRows[11]?.[14]) || legacyFileDate(sourceFileName),
      revision: legacyCellText(breakdownRows[13]?.[14]) || '0',
      productName,
      quantity,
      freightRouteKey: 'legacy-yt40',
      freightRouteLabel,
      containerType: '40HQ',
      quantityPerContainer,
      toolingCount: legacyCellNumber(breakdownRows[22]?.[14]),
    },
    plasticRows,
    purchaseRows,
    electronicRows,
    fabricRows,
    packagingRows,
    otherRows,
    carton,
    colorBoxSizeIn: {
      length: colorBoxLength,
      width: colorBoxWidth,
      height: colorBoxHeight,
    },
    laborUsd,
    materialTotalsUsd,
    materialTotalUsd,
    laborTotalUsd,
    basicTotalUsd,
    materialScrapUsd,
    markupUsd,
    exFactoryUsd,
    transportationUsd,
    totalFobUsd,
    testingTotalUsd,
    testingPerUnitUsd,
    totalWithTestingUsd,
    toolingTotalUsd,
    toolingPerUnitUsd,
    totalWithToolingUsd,
    internalTotalHkd,
  }
}

function convertLegacyThreeSixtyInternalQuote(
  workbook: XlsxParsedWorkbook,
  sourceFileName: string,
): ThreeSixtyConversionResult {
  const quoteData = buildLegacyThreeSixtyQuoteData(workbook, sourceFileName)
  validateTemplateCapacity(quoteData)
  const detailSpecs: Array<[string, number, number]> = [
    ['Plastic Material', sum(quoteData.plasticRows.map((row) => row.internalHkd)), quoteData.materialTotalsUsd.plastic],
    ['Purchased Material', sum(quoteData.purchaseRows.map((row) => row.internalHkd)), quoteData.materialTotalsUsd.purchase],
    ['Electronic Material', sum(quoteData.electronicRows.map((row) => row.internalHkd)), quoteData.materialTotalsUsd.electronic],
    ['Fabric Material', sum(quoteData.fabricRows.map((row) => row.internalHkd)), quoteData.materialTotalsUsd.fabric],
    ['Packaging Material', sum(quoteData.packagingRows.map((row) => row.internalHkd)) + quoteData.carton.perPieceHkd, quoteData.materialTotalsUsd.packaging],
    ['Others / Paint', sum(quoteData.otherRows.map((row) => row.internalHkd)), quoteData.materialTotalsUsd.others],
    ['Labour', quoteData.laborTotalUsd * THREE_SIXTY_HKD_USD, quoteData.laborTotalUsd],
    ['Material Scrap 2%', 0, quoteData.materialScrapUsd],
    ['Markup 12%', 0, quoteData.markupUsd],
    ['Transportation', quoteData.transportationUsd * THREE_SIXTY_HKD_USD, quoteData.transportationUsd],
    ['Testing Cost', 0, quoteData.testingPerUnitUsd],
    ['Tooling Cost', 0, quoteData.toolingPerUnitUsd],
  ]
  const details = detailSpecs.map(([description, internalHkd, customerUsd], index) => (
    createDetailRow(index + 1, description, internalHkd, customerUsd)
  ))
  return {
    sourceFileName,
    sheets: [{
      id: 'three-sixty-breakdown',
      name: 'Breakdown',
      productName: quoteData.metadata.productName,
      sourceFileName,
      rowCount: details.length,
      totalInternalHkd: quoteData.internalTotalHkd,
      totalCustomerHkd: round(quoteData.totalWithToolingUsd * THREE_SIXTY_HKD_USD),
      details,
      quoteData,
    }],
  }
}

export function convertThreeSixtyInternalQuote(buffer: ArrayBuffer, sourceFileName: string): ThreeSixtyConversionResult {
  const packageEntries = unzipSync(new Uint8Array(buffer))
  const workbookXml = packageEntries['xl/workbook.xml']
    ? strFromU8(packageEntries['xl/workbook.xml'])
    : ''
  const isP4Workbook = /name="(?:结构化数据|結構化數據)"/.test(workbookXml)
    && /name="(?:审批与版本|審批與版本)"/.test(workbookXml)
  if (isP4Workbook) {
    const artifact = parseP4InternalQuoteArtifact(buffer)
    return convertThreeSixtyP4InternalQuote(artifact, sourceFileName)
  }
  const workbook = parseLegacyThreeSixtyWorkbook(packageEntries)
  return convertLegacyThreeSixtyInternalQuote(workbook, sourceFileName)
}

function columnNameToIndex(column: string) {
  return column.split('').reduce((value, letter) => value * 26 + letter.charCodeAt(0) - 64, 0)
}

function parseCellRef(ref: string) {
  return {
    columnIndex: columnNameToIndex(ref.match(/[A-Z]+/)?.[0] ?? 'A'),
    rowNumber: Number(ref.match(/\d+/)?.[0] ?? 1),
  }
}

function escapeXml(value: string) {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function readAttr(attrs: string, name: string) {
  return attrs.match(new RegExp(`\\b${name}="([^"]*)"`))?.[1] ?? ''
}

function createCellMap(sheetXml: string) {
  const cellMap = new Map<string, TemplateCellMatch>()
  const pattern = /<c\b([^>]*)\/>|<c\b([^>]*)>([\s\S]*?)<\/c>/g
  for (const match of sheetXml.matchAll(pattern)) {
    const attrs = match[1] ?? match[2] ?? ''
    const ref = readAttr(attrs, 'r')
    if (!ref || match.index === undefined) continue
    cellMap.set(ref, {
      attrs,
      full: match[0],
      start: match.index,
      end: match.index + match[0].length,
    })
  }
  return cellMap
}

function formatNumber(value: number) {
  return String(Number((Number.isFinite(value) ? value : 0).toFixed(12)))
}

function buildCellXml(patch: TemplateCellPatch, existing?: TemplateCellMatch) {
  const existingStyle = existing ? Number(readAttr(existing.attrs, 's')) : Number.NaN
  const style = typeof patch.style === 'number'
    ? patch.style
    : Number.isFinite(existingStyle) ? existingStyle : undefined
  const styleAttr = typeof style === 'number' ? ` s="${style}"` : ''
  const formula = patch.formula ? `<f>${escapeXml(patch.formula)}</f>` : ''
  if (patch.value === null || patch.value === undefined || patch.value === '') {
    return formula ? `<c r="${patch.ref}"${styleAttr}>${formula}</c>` : `<c r="${patch.ref}"${styleAttr}/>`
  }
  if (typeof patch.value === 'number') {
    return `<c r="${patch.ref}"${styleAttr}>${formula}<v>${formatNumber(patch.value)}</v></c>`
  }
  if (typeof patch.value === 'boolean') {
    return `<c r="${patch.ref}" t="b"${styleAttr}>${formula}<v>${patch.value ? 1 : 0}</v></c>`
  }
  const value = String(patch.value)
  if (formula) return `<c r="${patch.ref}" t="str"${styleAttr}>${formula}<v>${escapeXml(value)}</v></c>`
  const space = /^\s|\s$/.test(value) ? ' xml:space="preserve"' : ''
  return `<c r="${patch.ref}" t="inlineStr"${styleAttr}><is><t${space}>${escapeXml(value)}</t></is></c>`
}

function applyPatches(sheetXml: string, patches: TemplateCellPatch[]) {
  const cellMap = createCellMap(sheetXml)
  const unique = new Map(patches.map((patch) => [patch.ref, patch]))
  const replacements: Array<{ start: number; end: number; xml: string }> = []
  const missing: TemplateCellPatch[] = []
  unique.forEach((patch) => {
    const existing = cellMap.get(patch.ref)
    if (!existing) {
      missing.push(patch)
      return
    }
    replacements.push({
      start: existing.start,
      end: existing.end,
      xml: buildCellXml(patch, existing),
    })
  })
  let updated = sheetXml
  replacements.sort((left, right) => right.start - left.start).forEach((replacement) => {
    updated = `${updated.slice(0, replacement.start)}${replacement.xml}${updated.slice(replacement.end)}`
  })
  const patchesByRow = new Map<number, TemplateCellPatch[]>()
  missing.forEach((patch) => {
    const row = parseCellRef(patch.ref).rowNumber
    patchesByRow.set(row, [...(patchesByRow.get(row) ?? []), patch])
  })
  Array.from(patchesByRow.entries())
    .sort(([left], [right]) => right - left)
    .forEach(([rowNumber, rowPatches]) => {
      const rowPattern = new RegExp(`<row\\b[^>]*\\br="${rowNumber}"[^>]*>[\\s\\S]*?<\\/row>`)
      const rowMatch = updated.match(rowPattern)
      if (!rowMatch || rowMatch.index === undefined) {
        const populated = rowPatches.filter((patch) => (
          !((patch.value === null || patch.value === undefined || patch.value === '') && !patch.formula)
        ))
        if (!populated.length) return
        const cells = populated
          .sort((left, right) => parseCellRef(left.ref).columnIndex - parseCellRef(right.ref).columnIndex)
          .map((patch) => buildCellXml(patch))
          .join('')
        const insertIndex = updated.indexOf('</sheetData>')
        updated = `${updated.slice(0, insertIndex)}<row r="${rowNumber}">${cells}</row>${updated.slice(insertIndex)}`
        return
      }
      let rowXml = rowMatch[0]
      rowPatches
        .filter((patch) => !((patch.value === null || patch.value === undefined || patch.value === '') && !patch.formula))
        .sort((left, right) => parseCellRef(left.ref).columnIndex - parseCellRef(right.ref).columnIndex)
        .forEach((patch) => {
          const targetColumn = parseCellRef(patch.ref).columnIndex
          let insertOffset = rowXml.lastIndexOf('</row>')
          for (const match of rowXml.matchAll(/<c\b([^>]*)\/>|<c\b([^>]*)>([\s\S]*?)<\/c>/g)) {
            const ref = readAttr(match[1] ?? match[2] ?? '', 'r')
            const column = ref.match(/[A-Z]+/)?.[0]
            if (match.index !== undefined && column && columnNameToIndex(column) > targetColumn) {
              insertOffset = match.index
              break
            }
          }
          rowXml = `${rowXml.slice(0, insertOffset)}${buildCellXml(patch)}${rowXml.slice(insertOffset)}`
        })
      updated = `${updated.slice(0, rowMatch.index)}${rowXml}${updated.slice(rowMatch.index + rowMatch[0].length)}`
    })
  return updated
}

function addGenericRows(patches: TemplateCellPatch[], input: ThreeSixtyMaterialRow[], startRows: number[]) {
  input.forEach((row, index) => {
    const target = startRows[index]
    if (!target) return
    patches.push(
      { ref: `A${target}`, value: index + 1 },
      { ref: `B${target}`, value: row.specification ? `${row.description} / ${row.specification}` : row.description },
      { ref: `L${target}`, value: row.usage },
      { ref: `O${target}`, value: row.unitPriceUsd },
      { ref: `P${target}`, value: row.totalUsd, formula: `L${target}*O${target}` },
    )
  })
}

function buildTemplatePatches(data: ThreeSixtyQuoteData): TemplateCellPatch[] {
  const patches: TemplateCellPatch[] = [
    { ref: 'C7', value: data.metadata.msBrand },
    { ref: 'C9', value: data.metadata.firstEtd },
    { ref: 'C12', value: data.metadata.productName },
    { ref: 'O10', value: data.metadata.preparedBy },
    { ref: 'O12', value: excelDateSerial(new Date(`${data.metadata.quoteDate}T00:00:00`)) },
    { ref: 'O14', value: data.metadata.revision },
    { ref: 'O16', value: data.metadata.quantity },
    { ref: 'O18', value: data.totalWithTestingUsd, formula: 'L42' },
    { ref: 'O20', value: THREE_SIXTY_HKD_USD },
    { ref: 'O22', value: data.toolingTotalUsd > 0 ? data.totalWithToolingUsd : 'NIL', formula: 'L45' },
    { ref: 'O23', value: data.metadata.toolingCount },
  ]
  const summaryRows: Array<[number, ThreeSixtyMaterialSection]> = [
    [26, 'plastic'],
    [27, 'purchase'],
    [28, 'electronic'],
    [29, 'fabric'],
    [30, 'packaging'],
    [31, 'others'],
  ]
  summaryRows.forEach(([row, key]) => {
    patches.push(
      { ref: `L${row}`, value: data.materialTotalsUsd[key] },
      { ref: `N${row}`, value: 0 },
      { ref: `O${row}`, value: data.materialTotalsUsd[key], formula: `L${row}+N${row}` },
    )
  })
  patches.push(
    { ref: 'L32', value: data.materialTotalUsd, formula: 'SUM(L26:L31)' },
    { ref: 'O32', value: data.materialTotalUsd, formula: 'SUM(O26:O31)' },
    { ref: 'L33', value: data.laborTotalUsd, formula: 'P175' },
    { ref: 'N33', value: 0 },
    { ref: 'O33', value: data.laborTotalUsd, formula: 'L33+N33' },
    { ref: 'L34', value: data.basicTotalUsd, formula: 'SUM(L32:L33)' },
    { ref: 'O34', value: data.basicTotalUsd, formula: 'SUM(O32:O33)' },
    { ref: 'L35', value: data.materialScrapUsd, formula: 'L32*M35' },
    { ref: 'M35', value: THREE_SIXTY_MATERIAL_SCRAP_RATE },
    { ref: 'N35', value: 0, formula: 'O35-L35' },
    { ref: 'O35', value: data.materialScrapUsd, formula: 'O32*P35' },
    { ref: 'P35', value: THREE_SIXTY_MATERIAL_SCRAP_RATE },
    { ref: 'L36', value: data.markupUsd, formula: 'L34*M36' },
    { ref: 'M36', value: THREE_SIXTY_MARKUP_RATE },
    { ref: 'N36', value: 0, formula: 'O36-L36' },
    { ref: 'O36', value: data.markupUsd, formula: 'O34*P36' },
    { ref: 'P36', value: THREE_SIXTY_MARKUP_RATE },
    { ref: 'L37', value: data.exFactoryUsd, formula: 'L34+L35+L36' },
    { ref: 'O37', value: data.exFactoryUsd, formula: 'O34+O35+O36' },
    { ref: 'L38', value: data.transportationUsd },
    { ref: 'N38', value: 0 },
    { ref: 'O38', value: data.transportationUsd, formula: 'L38+N38' },
    { ref: 'L39', value: 0 },
    { ref: 'N39', value: 0 },
    { ref: 'O39', value: 0 },
    { ref: 'L40', value: data.totalFobUsd, formula: 'SUM(L37:L39)' },
    { ref: 'N40', value: 0, formula: 'O40-L40' },
    { ref: 'O40', value: data.totalFobUsd, formula: 'SUM(O37:O39)' },
    { ref: 'E41', value: data.testingTotalUsd },
    { ref: 'H41', value: data.metadata.quantity },
    { ref: 'L41', value: data.testingPerUnitUsd, formula: 'IF(H41=0,0,E41/H41)' },
    { ref: 'L42', value: data.totalWithTestingUsd, formula: 'SUM(L40:L41)' },
    { ref: 'E44', value: data.toolingTotalUsd },
    { ref: 'H44', value: data.metadata.quantity },
    { ref: 'L44', value: data.toolingPerUnitUsd, formula: 'IF(H44=0,0,E44/H44)' },
    {
      ref: 'L45',
      value: data.toolingTotalUsd > 0 ? data.totalWithToolingUsd : 'NIL',
      formula: 'IF(SUM(L44:M44)=0,"NIL",SUM(L40,L41,L44))',
    },
    { ref: 'L47', value: data.carton.qtyPerCarton },
    { ref: 'L48', value: data.metadata.quantityPerContainer },
    { ref: 'L49', value: data.metadata.containerType },
    {
      ref: 'A54',
      value: `4>. MOQ:${data.metadata.quantity.toLocaleString('en-US')}. Estimate it will use ${Math.ceil(data.metadata.quantity / data.metadata.quantityPerContainer)} ${data.metadata.containerType} containers. Transportation cost is not included LCL cost. RR will charge back TSG the extra LCL cost. (预计约需 ${Math.ceil(data.metadata.quantity / data.metadata.quantityPerContainer)} 条 ${data.metadata.containerType} 柜，报价不包含散货运费，散货运费按实报实销)`,
    },
  )

  data.plasticRows.forEach((row, index) => {
    const target = 60 + index
    patches.push(
      { ref: `A${target}`, value: index + 1 },
      { ref: `B${target}`, value: row.description },
      { ref: `E${target}`, value: row.material },
      { ref: `F${target}`, value: row.cavities || null },
      { ref: `G${target}`, value: row.up || null },
      { ref: `H${target}`, value: row.usage },
      { ref: `I${target}`, value: row.partWeightG },
      { ref: `J${target}`, value: row.totalWeightG, formula: `H${target}*I${target}` },
      { ref: `K${target}`, value: row.unitPriceUsd },
      { ref: `L${target}`, value: row.totalUsd, formula: `J${target}*K${target}/1000` },
      { ref: `M${target}`, value: row.machine },
      { ref: `N${target}`, value: row.cycleSeconds || null },
      { ref: `P${target}`, value: row.moldingUsd },
    )
  })
  patches.push(
    { ref: 'H71', value: sum(data.plasticRows.map((row) => row.usage)), formula: 'SUM(H60:H70)' },
    { ref: 'I71', value: sum(data.plasticRows.map((row) => row.partWeightG)), formula: 'SUM(I60:I70)' },
    { ref: 'J71', value: sum(data.plasticRows.map((row) => row.totalWeightG)), formula: 'SUM(J60:J70)' },
    { ref: 'L71', value: data.materialTotalsUsd.plastic, formula: 'SUM(L60:L70)' },
    { ref: 'P71', value: data.laborUsd.molding, formula: 'SUM(P60:P70)' },
  )
  addGenericRows(patches, data.purchaseRows, Array.from({ length: 12 }, (_, index) => 77 + index))
  patches.push({ ref: 'P89', value: data.materialTotalsUsd.purchase, formula: 'SUM(P77:P88)' })
  addGenericRows(patches, data.electronicRows, Array.from({ length: 11 }, (_, index) => 94 + index))
  patches.push({ ref: 'P105', value: data.materialTotalsUsd.electronic, formula: 'SUM(P94:P104)' })
  addGenericRows(patches, data.fabricRows, Array.from({ length: 16 }, (_, index) => 112 + index))
  patches.push({ ref: 'P128', value: data.materialTotalsUsd.fabric, formula: 'SUM(P112:P127)' })

  const colorBoxIndex = data.packagingRows.findIndex((row) => /彩盒|color\s*box/i.test(row.description))
  const colorBox = colorBoxIndex >= 0 ? data.packagingRows[colorBoxIndex] : data.packagingRows[0]
  const otherPackaging = data.packagingRows.filter((_, index) => index !== (colorBoxIndex >= 0 ? colorBoxIndex : 0))
  if (colorBox) addGenericRows(patches, [colorBox], [133])
  patches.push(
    { ref: 'C134', value: data.colorBoxSizeIn.length || null },
    { ref: 'D134', value: data.colorBoxSizeIn.width || null },
    { ref: 'E134', value: data.colorBoxSizeIn.height || null },
  )
  const packagingTargets = [135, 136, 137, 139, 140, 141, 142]
  addGenericRows(patches, otherPackaging, packagingTargets)
  otherPackaging.forEach((_, index) => {
    const target = packagingTargets[index]
    if (target) patches.push({ ref: `A${target}`, value: index < 3 ? index + 2 : index + 3 })
  })
  const cartonSequence = Math.min(otherPackaging.length, 3) + 2
  patches.push(
    { ref: 'A138', value: cartonSequence },
    { ref: 'B138', value: data.carton.item || 'Master Carton' },
    { ref: 'G138', value: data.carton.lengthIn },
    { ref: 'I138', value: data.carton.widthIn },
    { ref: 'J138', value: data.carton.heightIn },
    { ref: 'K138', value: data.carton.qtyPerCarton },
    { ref: 'L138', value: 1 / data.carton.qtyPerCarton },
    { ref: 'O138', value: data.carton.cartonPriceHkd / THREE_SIXTY_HKD_USD },
    { ref: 'P138', value: data.carton.perPieceHkd / THREE_SIXTY_HKD_USD, formula: 'L138*O138' },
    { ref: 'P143', value: data.materialTotalsUsd.packaging, formula: 'SUM(P133:P142)' },
  )
  addGenericRows(patches, data.otherRows, Array.from({ length: 5 }, (_, index) => 148 + index))
  patches.push({ ref: 'P153', value: data.materialTotalsUsd.others, formula: 'SUM(P148:P152)' })

  const laborRows: Array<[number, ThreeSixtyLaborCode]> = [
    [158, 'molding'],
    [160, 'vacuum'],
    [161, 'tampo'],
    [162, 'plate'],
    [163, 'book'],
    [164, 'spray'],
    [165, 'silkscreen'],
    [166, 'electronic'],
    [167, 'assembly'],
    [168, 'cutting'],
    [169, 'sewing'],
    [170, 'handFinishing'],
    [171, 'wood'],
    [172, 'packing'],
  ]
  laborRows.forEach(([row, code]) => {
    const amount = data.laborUsd[code]
    patches.push(
      { ref: `M${row}`, value: amount > 0 ? 1 : 0 },
      { ref: `O${row}`, value: amount },
      { ref: `P${row}`, value: amount, formula: `M${row}*O${row}` },
    )
  })
  patches.push({ ref: 'P175', value: data.laborTotalUsd, formula: 'SUM(P158:P174)' })
  return patches
}

export function createThreeSixtyCustomerQuoteWorkbook(
  result: ThreeSixtyConversionResult,
  templateBuffer: ArrayBuffer | Uint8Array,
): Uint8Array {
  const firstSheet = result.sheets[0]
  if (!firstSheet) throw new Error('没有可输出的 360 报客数据')
  const bytes = templateBuffer instanceof Uint8Array ? templateBuffer : new Uint8Array(templateBuffer)
  const zip = unzipSync(bytes)
  const sheetPath = 'xl/worksheets/sheet1.xml'
  if (!zip[sheetPath]) throw new Error('360 客户模板缺少 Breakdown 工作表')
  zip[sheetPath] = strToU8(applyPatches(strFromU8(zip[sheetPath]), buildTemplatePatches(firstSheet.quoteData)))
  if (zip['xl/workbook.xml']) {
    let workbookXml = strFromU8(zip['xl/workbook.xml'])
    workbookXml = workbookXml.replace(
      /<calcPr\b[^>]*\/>/,
      '<calcPr calcId="0" calcMode="auto" fullCalcOnLoad="1" forceFullCalc="1"/>',
    )
    zip['xl/workbook.xml'] = strToU8(workbookXml)
  }
  return zipSync(zip, { level: 0 })
}

function safeFileName(value: string) {
  return value.replace(/[\\/:*?"<>|]+/g, '-').replace(/\s+/g, ' ').trim() || '360 Quote'
}

export function buildThreeSixtyCustomerQuoteFileName(result: ThreeSixtyConversionResult) {
  const data = result.sheets[0]?.quoteData
  if (!data) return 'RR_360_Customer_Quote.xlsx'
  const date = data.metadata.quoteDate.replace(/-/g, '')
  return `RR_${safeFileName(data.metadata.productName)}_360_${safeFileName(data.metadata.revision)}_${date}.xlsx`
}

import {
  XLSX_STYLE,
  createXlsxWorkbook,
  excelDateSerial,
  parseXlsxWorkbook,
  type XlsxCellInput,
  type XlsxCellValue,
  type XlsxOutputSheet,
} from './xlsxLite'
import type { P4InternalQuoteArtifact } from './p4Artifact'

type DetailCompareStatus = '上调' | '下调' | '持平'

interface BuzzBeeMaterialRule {
  name: string
  en: string
  price: number
}

interface BuzzBeeMachineRule {
  maxTons: number
  cost: number
}

interface BuzzBeeInternalInjectionItem {
  name: string
  materialZh: string
  weightG: number
  machineTons: number
  setsPerShot: number
  targetYield: number
  beerCostInternal: number
  materialAmountInternal: number
  customerBeerCostHint: number
}

interface BuzzBeeInternalCostRow {
  taxTag: string
  category: string
  description: string
  internalValue: number
  customerValueHint: number
}

interface BuzzBeeInternalBox {
  length: number
  width: number
  height: number
  pcsPerCarton: number
  cartonPriceInternal: number
  cube: number
}

interface BuzzBeeInternalColorBox {
  price1: number
  fsc1: number
  moq1: string
  price2: number
  fsc2: number
  moq2: string
}

interface BuzzBeeInternalSheet {
  sheetName: string
  title: string
  productName: string
  items: BuzzBeeInternalInjectionItem[]
  costRows: BuzzBeeInternalCostRow[]
  box: BuzzBeeInternalBox
  colorBox: BuzzBeeInternalColorBox
}

interface BuzzBeeQuoteInjectionRow {
  name: string
  material: string
  weight: number
  pricePerKg: number
  amount: number
  setsPerShot: number
  beer: number
  internalAmount: number
}

interface BuzzBeeQuotePurchaseRow {
  desc: string
  qty: number
  price: number
  amount: number
  internalAmount: number
  category: string
}

interface BuzzBeeQuoteData {
  sheetName: string
  productName: string
  injectionRows: BuzzBeeQuoteInjectionRow[]
  injectionWeight: number
  injectionAmount: number
  injectionBeer: number
  purchaseRows: BuzzBeeQuotePurchaseRow[]
  purchaseSubTotal: number
  additionalParts: BuzzBeeQuotePurchaseRow[]
  additionalTotal: number
  breakdown: {
    plastic: number
    injection: number
    purchase: number
    tran: number
    process: number
    paint: number
    spray: number
    sprayOnly: number
    assembly: number
    sub: number
    po: number
    total: number
  }
  exftyCost: number
  usd: number
  box: BuzzBeeInternalBox
  colorBox: BuzzBeeInternalColorBox
}

export interface BuzzBeeQuoteDetailRow {
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

export interface BuzzBeeConvertedSheet {
  id: string
  name: string
  productName: string
  sourceFileName: string
  rowCount: number
  totalInternalHkd: number
  totalCustomerHkd: number
  details: BuzzBeeQuoteDetailRow[]
  quoteData: BuzzBeeQuoteData
}

export interface BuzzBeeConversionResult {
  sourceFileName: string
  sheets: BuzzBeeConvertedSheet[]
}

const MATERIALS: BuzzBeeMaterialRule[] = [
  { name: 'PP料', en: 'PP', price: 12.1 },
  { name: 'ABS料', en: 'ABS', price: 16.5 },
  { name: 'PC料', en: 'PC', price: 18 },
  { name: 'K料', en: 'K', price: 22 },
  { name: 'GP料', en: 'GP', price: 11 },
  { name: 'PE料', en: 'PE', price: 14.5 },
  { name: 'POM料', en: 'POM', price: 28 },
  { name: '475料', en: '475', price: 12 },
  { name: 'C-ABS料', en: 'C-ABS', price: 31.3 },
  { name: 'EVA料', en: 'EVA', price: 13 },
  { name: '马力士', en: 'Mars', price: 14 },
  { name: '环保PVC', en: 'PVC', price: 14 },
  { name: '尼龙料', en: 'Nylon', price: 34 },
  { name: 'TPR料', en: 'TPR', price: 28 },
  { name: 'SAN料', en: 'SAN', price: 20 },
  { name: 'PP料明', en: 'PP(C)', price: 18 },
  { name: 'HI75%+GP25%', en: 'HI/GP', price: 12 },
  { name: 'HDPE料', en: 'HDPE', price: 13 },
]

const P4_MATERIAL_ALIASES: Record<string, string> = {
  '1#PP': 'PP料',
  '透明PP': 'PP料明',
  '透明ABS': 'C-ABS料',
  LDPE: 'PE料',
  PE: 'PE料',
  HDPE: 'HDPE料',
  PVC: '环保PVC',
}

const MACHINES: BuzzBeeMachineRule[] = [
  { maxTons: 6, cost: 1040 },
  { maxTons: 9, cost: 1160 },
  { maxTons: 12, cost: 1280 },
  { maxTons: 14, cost: 1650 },
  { maxTons: 18, cost: 1890 },
  { maxTons: 24, cost: 2130 },
  { maxTons: 34, cost: 2460 },
  { maxTons: 44, cost: 2700 },
  { maxTons: 49.9, cost: 2790 },
  { maxTons: 999, cost: 3090 },
]

const MARKUPS = {
  beer: 1.1,
  assembly: 1,
  paint: 1,
  spray: 1,
  carton: 1.03,
  carShell: 1.03,
  default: 1.05,
}

const ADDITIONAL_PART_KEYWORDS = /子弹|波波球|波波|加值件|附加件/
const SKIP_COST_DESCRIPTION = /^[×÷=*\/]$|报客价|目标价|相差|旺季价|按出厂|占货价|减税|料价成本|含税|不含人工|毛利|利润|总成本|外购件成本|未减税|减税后|人民币|港币|RMB|HKD|US\$|USD/i
const INTERNAL_ONLY_COST_BOUNDARY = /^(?:运费|吊柜费|报价[（(]|包含测试费用)/

function toText(value: XlsxCellValue) {
  return String(value ?? '').trim()
}

function toNumber(value: XlsxCellValue) {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : 0
  }

  const normalized = String(value ?? '').replace(/,/g, '').trim()
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
  return round(value, 3)
}

function findMaterial(materialZh: string) {
  const clean = materialZh.trim()
  const exact = MATERIALS.find((item) => item.name === clean)
  if (exact) {
    return exact
  }

  const simplified = clean.replace(/料$/, '')
  return MATERIALS.find((item) => item.name.replace(/料$/, '') === simplified)
}

function findMachineCost(tons: number) {
  return MACHINES.find((machine) => tons <= machine.maxTons)?.cost ?? MACHINES[MACHINES.length - 1].cost
}

function markupFor(category: string) {
  if (category.includes('啤工')) return MARKUPS.beer
  if (category.includes('装配工') || category.includes('装工')) return MARKUPS.assembly
  if (category.includes('油漆')) return MARKUPS.paint
  if (category.includes('喷油工')) return MARKUPS.spray
  if (category.includes('纸箱')) return MARKUPS.carton
  if (category.includes('车衣')) return MARKUPS.carShell
  return MARKUPS.default
}

function hasInjectionHeader(rows: XlsxCellValue[][]) {
  return rows.some((row) => toText(row?.[2]) === '名称' && toText(row?.[3]) === '料型')
}

function findInjectionHeaderRow(rows: XlsxCellValue[][]) {
  return rows.findIndex((row) => toText(row?.[2]) === '名称' && toText(row?.[3]) === '料型')
}

function cleanProductName(title: string, fallback: string) {
  const cleaned = title
    .replace(/[（(][^）)]*[）)]/g, '')
    .replace(/报价$/, '')
    .trim()
  return cleaned || fallback.replace(/明细$/, '').trim() || fallback || '报价'
}

function parseQtyFromDesc(description: string) {
  const matched = description.match(/[（(]\s*(\d+(?:\.\d+)?)\s*PCS?\s*[）)]/i)
  if (!matched) {
    return { qty: 1, desc: description.trim() }
  }

  return {
    qty: Number(matched[1]) || 1,
    desc: description.replace(matched[0], '').trim(),
  }
}

function cleanPurchaseDescription(description: string) {
  const { qty, desc } = parseQtyFromDesc(description)
  const cleaned = desc
    .replace(/^130马达/, '马达')
    .trim()

  return {
    qty,
    desc: cleaned || desc || description,
  }
}

function parseInternalSheet(rows: XlsxCellValue[][], sheetName: string): BuzzBeeInternalSheet {
  let title = ''
  for (let rowIndex = 0; rowIndex < Math.min(12, rows.length); rowIndex += 1) {
    const row = rows[rowIndex] ?? []
    const matched = row.find((cell) => {
      const text = toText(cell)
      return text.length > 2 && text.length < 60 && (text.includes('报价') || text.includes('套装') || text.includes('按图'))
    })

    if (matched) {
      title = toText(matched)
      break
    }
  }

  const productName = cleanProductName(title, sheetName)
  const headerRow = findInjectionHeaderRow(rows)
  if (headerRow < 0) {
    throw new Error(`${sheetName} 未找到注塑件明细表头（C 列“名称”、D 列“料型”）`)
  }

  const items: BuzzBeeInternalInjectionItem[] = []
  let rowIndex = headerRow + 1
  for (; rowIndex < rows.length; rowIndex += 1) {
    const row = rows[rowIndex] ?? []
    const name = toText(row[2])
    const materialZh = toText(row[3])

    if (!name && !materialZh) {
      if (toNumber(row[4]) > 0) {
        break
      }

      const hasData = row.some((cell) => toText(cell) !== '')
      if (!hasData) {
        continue
      }

      break
    }

    if (/合计|小计|SUB/i.test(name)) {
      break
    }

    items.push({
      name,
      materialZh,
      weightG: toNumber(row[4]),
      machineTons: toNumber(row[6]),
      setsPerShot: toNumber(row[7]) || 1,
      targetYield: toNumber(row[8]) || 1,
      beerCostInternal: toNumber(row[9]),
      materialAmountInternal: toNumber(row[10]),
      customerBeerCostHint: toNumber(row[11]),
    })
  }

  const costRows: BuzzBeeInternalCostRow[] = []
  const costStart = rows.findIndex((row, index) => index >= rowIndex && toText(row?.[1]) === '料价')
  let blankStreak = 0

  if (costStart >= 0) {
    for (let index = costStart; index < rows.length; index += 1) {
      const row = rows[index] ?? []
      const taxTag = toText(row[0])
      const category = toText(row[1])
      const description = toText(row[2])
      const internalValue = toNumber(row[3])
      const customerValueHint = toNumber(row[4])

      // The unified internal-quote layout appends route freight, lifting fees,
      // MOQ scenarios, and testing-fee summaries directly after the customer
      // cost details. BuzzBee's own workbook has no matching fields for those
      // internal-only blocks, and freight is the final ordered detail category.
      if (INTERNAL_ONLY_COST_BOUNDARY.test(category)) {
        break
      }

      const isBlank = !category && !description && !internalValue && !customerValueHint
      if (isBlank) {
        blankStreak += 1
        if (blankStreak >= 8 && costRows.length > 5) {
          break
        }
        continue
      }

      if (!category || SKIP_COST_DESCRIPTION.test(description)) {
        blankStreak += 1
        continue
      }

      blankStreak = 0
      costRows.push({
        taxTag,
        category,
        description,
        internalValue,
        customerValueHint,
      })
    }
  }

  const box: BuzzBeeInternalBox = {
    length: 0,
    width: 0,
    height: 0,
    pcsPerCarton: 1,
    cartonPriceInternal: 0,
    cube: 0,
  }

  rows.forEach((row) => {
    row.forEach((cell, columnIndex) => {
      const text = toText(cell)
      if (text === '外箱:' || text === '外箱：' || text === '外箱') {
        box.length = toNumber(row[columnIndex + 1])
        box.width = toNumber(row[columnIndex + 2])
        box.height = toNumber(row[columnIndex + 3])
      }

      if (text === '装箱:' || text === '装箱：' || text === '装箱') {
        box.pcsPerCarton = toNumber(row[columnIndex + 1]) || 1
      }

      if (text === '合计' && toNumber(row[columnIndex + 1]) > 0 && !box.cartonPriceInternal) {
        box.cartonPriceInternal = toNumber(row[columnIndex + 1])
      }

      if (text === 'CUFT:' || text === 'CUFT：' || text === 'CUFT') {
        box.cube = toNumber(row[columnIndex + 1])
      }
    })
  })

  if (!box.cube && box.length && box.width && box.height) {
    box.cube = round(box.length * box.width * box.height / 1728, 6)
  }

  let colorBox: BuzzBeeInternalColorBox = {
    price1: 0,
    fsc1: 0,
    moq1: '',
    price2: 0,
    fsc2: 0,
    moq2: '',
  }

  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index] ?? []
    const columnIndex = row.findIndex((cell) => toText(cell) === '报客彩盒')

    if (columnIndex >= 0) {
      const first = rows[index + 1] ?? []
      const second = rows[index + 2] ?? []
      const packCount = box.pcsPerCarton || 1
      colorBox = {
        price1: toNumber(first[columnIndex]),
        fsc1: 0,
        moq1: toText(first[columnIndex + 2]),
        price2: toNumber(second[columnIndex]),
        fsc2: 0,
        moq2: toText(second[columnIndex + 2]),
      }

      colorBox.fsc1 = round(colorBox.price1 / packCount * MARKUPS.carton, 4)
      colorBox.fsc2 = round(colorBox.price2 / packCount * MARKUPS.carton, 4)
      break
    }
  }

  return {
    sheetName,
    title: title || productName,
    productName,
    items,
    costRows,
    box,
    colorBox,
  }
}

function parseBuzzBeeInternalSheets(buffer: ArrayBuffer): BuzzBeeInternalSheet[] {
  const workbook = parseXlsxWorkbook(buffer)
  const preferred = workbook.sheets.filter((sheet) => sheet.name.includes('明细') && hasInjectionHeader(sheet.rows))
  const targets = preferred.length > 0
    ? preferred
    : workbook.sheets.filter((sheet) => hasInjectionHeader(sheet.rows)).slice(0, 1)

  if (targets.length === 0) {
    throw new Error('未找到含注塑件明细的 Sheet（C 列需为“名称”、D 列需为“料型”）')
  }

  return targets.map((sheet) => parseInternalSheet(sheet.rows, sheet.name))
}

function convertToClientData(parsed: BuzzBeeInternalSheet): BuzzBeeQuoteData {
  const injectionRows = parsed.items.map((item) => {
    const material = findMaterial(item.materialZh)
    const pricePerKg = material?.price ?? 0
    const materialName = material?.en ?? item.materialZh.replace(/料$/, '')
    const amount = round(item.weightG * pricePerKg / 1000, 4)
    const fallbackBeer = findMachineCost(item.machineTons) / item.targetYield / item.setsPerShot * MARKUPS.beer
    const beer = round(item.customerBeerCostHint || fallbackBeer, 4)

    return {
      name: item.name,
      material: materialName,
      weight: item.weightG,
      pricePerKg,
      amount,
      setsPerShot: item.setsPerShot,
      beer,
      internalAmount: round(item.materialAmountInternal + item.beerCostInternal, 4),
    }
  })

  const purchaseRows: BuzzBeeQuotePurchaseRow[] = []
  const additionalParts: BuzzBeeQuotePurchaseRow[] = []
  let paintTotal = 0
  let sprayTotal = 0
  let assemblyTotal = 0

  parsed.costRows.forEach((row) => {
    const category = row.category
    const internal = row.internalValue || 0
    const markup = markupFor(category)

    if (category === '料价' || category === '啤工') return
    if (category === '装配工' || category.includes('装工')) {
      assemblyTotal += internal * markup
      return
    }
    if (category === '油漆') {
      paintTotal += internal * markup
      return
    }
    if (category === '喷油工') {
      sprayTotal += internal * markup
      return
    }
    if (
      category === '纸箱'
      || category.includes('彩盒')
      || category === '杂项'
      || category.includes('运费')
      || category.includes('吊柜费')
    ) return

    const { qty, desc } = cleanPurchaseDescription(row.description)
    const customerAmount = row.customerValueHint || internal * markup
    if (customerAmount <= 0) {
      return
    }

    const price = roundMoney(customerAmount / Math.max(qty, 1))
    const amount = roundMoney(price * qty)
    const target = ADDITIONAL_PART_KEYWORDS.test(row.description) ? additionalParts : purchaseRows

    target.push({
      desc,
      qty,
      price,
      amount,
      internalAmount: internal,
      category,
    })
  })

  const cartonPrice = roundMoney(parsed.box.cartonPriceInternal * MARKUPS.carton)
  if (cartonPrice > 0) {
    purchaseRows.push({
      desc: '纸箱',
      qty: 1,
      price: cartonPrice,
      amount: cartonPrice,
      internalAmount: parsed.box.cartonPriceInternal,
      category: '纸箱',
    })
  }

  const injectionWeight = round(injectionRows.reduce((sum, row) => sum + row.weight, 0), 4)
  const injectionAmount = round(injectionRows.reduce((sum, row) => sum + row.amount, 0), 4)
  const injectionBeer = round(injectionRows.reduce((sum, row) => sum + row.beer, 0), 4)
  const purchaseSubTotal = round(purchaseRows.reduce((sum, row) => sum + row.amount, 0), 4)
  const process = round(paintTotal + sprayTotal + assemblyTotal, 4)
  const sub = round(injectionAmount + injectionBeer + purchaseSubTotal + process, 4)
  const po = round(sub * 0.1, 4)
  const total = round(sub + po, 4)
  const additionalTotal = round(additionalParts.reduce((sum, row) => sum + row.amount, 0), 4)
  const exftyCost = round(total + additionalTotal, 4)

  return {
    sheetName: parsed.sheetName,
    productName: parsed.productName,
    injectionRows,
    injectionWeight,
    injectionAmount,
    injectionBeer,
    purchaseRows,
    purchaseSubTotal,
    additionalParts,
    additionalTotal,
    breakdown: {
      plastic: injectionAmount,
      injection: injectionBeer,
      purchase: purchaseSubTotal,
      tran: 0,
      process,
      paint: round(paintTotal, 4),
      spray: round(paintTotal + sprayTotal, 4),
      sprayOnly: round(sprayTotal, 4),
      assembly: round(assemblyTotal, 4),
      sub,
      po,
      total,
    },
    exftyCost,
    usd: round(exftyCost / 7.75, 4),
    box: parsed.box,
    colorBox: parsed.colorBox,
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
): BuzzBeeQuoteDetailRow {
  const differenceHkd = 0

  return {
    id: `${sheetId}-${itemNo}`,
    sheetId,
    sheetName,
    itemNo,
    description,
    internalPriceHkd: round(internalPriceHkd, 3),
    customerPriceHkd: round(customerPriceHkd, 3),
    previousCustomerPriceHkd: round(customerPriceHkd, 3),
    differenceHkd,
    marginBand: marginBand(internalPriceHkd, customerPriceHkd),
    compareStatus: compareStatus(differenceHkd),
  }
}

function buildDetailRows(sheetId: string, sheetName: string, data: BuzzBeeQuoteData) {
  const rows: BuzzBeeQuoteDetailRow[] = []

  data.injectionRows.forEach((row, index) => {
    rows.push(detailRow(
      sheetId,
      sheetName,
      `INJ-${String(index + 1).padStart(3, '0')}`,
      `${row.name} / ${row.material}`,
      row.internalAmount,
      row.amount + row.beer,
    ))
  })

  data.purchaseRows.forEach((row, index) => {
    rows.push(detailRow(
      sheetId,
      sheetName,
      `PUR-${String(index + 1).padStart(3, '0')}`,
      row.desc,
      row.internalAmount,
      row.amount,
    ))
  })

  if (data.breakdown.process > 0) {
    rows.push(detailRow(sheetId, sheetName, 'PRO-001', 'PROCESS 工艺人工', data.breakdown.process, data.breakdown.process))
  }

  rows.push(detailRow(sheetId, sheetName, 'PO-001', 'P+O 10%', 0, data.breakdown.po))

  data.additionalParts.forEach((row, index) => {
    rows.push(detailRow(
      sheetId,
      sheetName,
      `ADD-${String(index + 1).padStart(3, '0')}`,
      `Additional Parts / ${row.desc}`,
      row.internalAmount,
      row.amount,
    ))
  })

  return rows
}

function convertSheet(parsed: BuzzBeeInternalSheet, sourceFileName: string, index: number): BuzzBeeConvertedSheet {
  const quoteData = convertToClientData(parsed)
  const sheetId = `buzzbee-${index + 1}-${parsed.productName.replace(/\s+/g, '') || 'quote'}`
  const details = buildDetailRows(sheetId, parsed.productName, quoteData)
  const totalInternalHkd = round(details.reduce((sum, row) => sum + row.internalPriceHkd, 0), 3)

  return {
    id: sheetId,
    name: parsed.productName,
    productName: parsed.productName,
    sourceFileName,
    rowCount: details.length,
    totalInternalHkd,
    totalCustomerHkd: quoteData.exftyCost,
    details,
    quoteData,
  }
}

function p4Object(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function p4Rows(value: unknown) {
  return Array.isArray(value) ? value.map(p4Object) : []
}

function p4Number(value: unknown) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function p4BuzzBeeMaterial(value: unknown) {
  const source = String(value ?? '').trim()
  return P4_MATERIAL_ALIASES[source] ?? `${source.replace(/料$/, '')}料`
}

function p4BuzzBeeColorBox(artifact: P4InternalQuoteArtifact, pcsPerCarton: number, hasInternalColorBoxCost: boolean): BuzzBeeInternalColorBox {
  const customerFields = p4Object(artifact.sections.sales.payload.customer_quote_fields)
  const buzzBeeFields = p4Object(customerFields.buzzbee)
  const tiers = p4Rows(buzzBeeFields.color_box_tiers)
  if (!hasInternalColorBoxCost && tiers.length === 0) {
    return { price1: 0, fsc1: 0, moq1: '', price2: 0, fsc2: 0, moq2: '' }
  }
  if (tiers.length !== 2) {
    throw new Error('BuzzBee 直转被阻断：彩盒必须完整填写两档报客价、FSC 与 MOQ')
  }
  const normalized = tiers.map((row, index) => {
    const quotePrice = p4Number(row.quote_price_hkd)
    const fscPrice = p4Number(row.fsc_price_hkd)
    const moq = String(row.moq ?? '').trim()
    if (!quotePrice || !fscPrice || !moq) {
      throw new Error(`BuzzBee 直转被阻断：彩盒第 ${index + 1} 档缺少报客价、FSC 或 MOQ`)
    }
    if (Math.abs(fscPrice - quotePrice * MARKUPS.carton) > 0.02) {
      throw new Error(`BuzzBee 直转被阻断：彩盒第 ${index + 1} 档 FSC 必须等于报客彩盒价 × 1.03`)
    }
    return { quotePrice, fscPrice, moq }
  })
  const packCount = pcsPerCarton || 1
  return {
    price1: normalized[0].quotePrice,
    fsc1: round(normalized[0].quotePrice / packCount * MARKUPS.carton, 4),
    moq1: normalized[0].moq,
    price2: normalized[1].quotePrice,
    fsc2: round(normalized[1].quotePrice / packCount * MARKUPS.carton, 4),
    moq2: normalized[1].moq,
  }
}

function p4MachineCodeValue(value: unknown) {
  const matches = Array.from(
    String(value ?? '').trim().matchAll(/(\d+(?:\.\d+)?)A/gi),
    (match) => Number(match[1]),
  ).filter((item) => Number.isFinite(item))
  return matches.length > 0 ? Math.max(...matches) : 0
}

function p4Total(artifact: P4InternalQuoteArtifact, sectionCode: keyof P4InternalQuoteArtifact['sections'], key = 'total_hkd') {
  const totals = p4Object(artifact.sections[sectionCode].calculation.totals)
  return p4Number(totals[key])
}

function p4CostRows(artifact: P4InternalQuoteArtifact): BuzzBeeInternalCostRow[] {
  const costRows: BuzzBeeInternalCostRow[] = []
  const engineering = artifact.sections.engineering
  const salesPackagingBreakdown = p4Rows(artifact.sections.sales.calculation.line_breakdown)
    .filter((row) => row.kind === 'packaging_material')
  const engineeringBreakdown = p4Rows(engineering.calculation.line_breakdown)
  engineeringBreakdown
    .filter((row) => row.kind === 'material')
    .filter((row) => !(salesPackagingBreakdown.length > 0 && row.category === 'packaging'))
    .forEach((row) => {
      const category = String(row.category ?? '')
      costRows.push({
        taxTag: '',
        category: category === 'hardware' ? '五金' : category === 'packaging' ? '包装材料' : '其它外购',
        description: String(row.item ?? ''),
        internalValue: p4Number(row.amount_hkd),
        customerValueHint: 0,
      })
    })

  const packagingCategoryLabels: Record<string, string> = {
    blister: '吸塑',
    color_box_inner_card: '彩盒/内卡',
    leaflet_manual: '利宝/说明书',
    other_purchase: '其他外购',
  }
  salesPackagingBreakdown.forEach((row) => {
    costRows.push({
      taxTag: p4Number(row.tax_rate_percent) > 0 ? `${p4Number(row.tax_rate_percent)}%` : '',
      category: packagingCategoryLabels[String(row.category ?? '')] ?? '包装材料',
      description: String(row.item ?? ''),
      internalValue: p4Number(row.amount_hkd),
      customerValueHint: 0,
    })
  })

  const electronicBreakdown = p4Rows(artifact.sections.electronic.calculation.line_breakdown)
    .filter((row) => row.kind === 'electronic_component')
  if (electronicBreakdown.length > 0) {
    electronicBreakdown.forEach((row, index) => {
      const internalValue = p4Number(row.line_hkd)
      if (internalValue <= 0) return
      costRows.push({
        taxTag: '',
        category: '电子',
        description: String(row.item ?? `电子材料${index + 1}`),
        internalValue,
        customerValueHint: 0,
      })
    })
  } else {
    const electronic = p4Total(artifact, 'electronic')
    if (electronic > 0) costRows.push({ taxTag: '', category: '电子', description: '电子材料及加工', internalValue: electronic, customerValueHint: 0 })
  }

  let paint = 0
  let spray = 0
  p4Rows(artifact.sections.painting.calculation.line_breakdown).forEach((row) => {
    const operations = p4Object(row.operations)
    paint += p4Number(operations.paint)
    spray += Object.entries(operations).reduce((sum, [code, value]) => sum + (code === 'paint' ? 0 : p4Number(value)), 0)
  })
  if (paint > 0) costRows.push({ taxTag: '', category: '油漆', description: '油色材料', internalValue: paint, customerValueHint: 0 })
  if (spray > 0) costRows.push({ taxTag: '', category: '喷油工', description: '喷油及表面工序', internalValue: spray, customerValueHint: 0 })

  const slush = p4Total(artifact, 'slush')
  if (slush > 0) costRows.push({ taxTag: '', category: '搪胶', description: '搪胶件', internalValue: slush, customerValueHint: 0 })
  const clothes = p4Total(artifact, 'sewing', 'clothes_hkd')
  const hair = p4Total(artifact, 'sewing', 'hair_hkd')
  if (clothes > 0) costRows.push({ taxTag: '', category: '车衣', description: '车衣材料及人工', internalValue: clothes, customerValueHint: 0 })
  if (hair > 0) costRows.push({ taxTag: '', category: '车发', description: '车发材料及人工', internalValue: hair, customerValueHint: 0 })
  const assembly = p4Total(artifact, 'assembly', 'assembly_hkd')
  const packaging = p4Total(artifact, 'assembly', 'packaging_hkd')
  if (assembly > 0) costRows.push({ taxTag: '', category: '装配工', description: '装配人工', internalValue: assembly, customerValueHint: 0 })
  if (packaging > 0) costRows.push({ taxTag: '', category: '装配工', description: '包装人工', internalValue: packaging, customerValueHint: 0 })

  p4Rows(artifact.sections.molding.calculation.line_breakdown)
    .filter((row) => row.kind === 'blow')
    .forEach((row) => costRows.push({
      taxTag: '',
      category: '吹气',
      description: String(row.item ?? '吹气件'),
      internalValue: p4Number(row.amount_hkd),
      customerValueHint: 0,
    }))
  return costRows
}

export function convertBuzzBeeP4InternalQuote(
  artifact: P4InternalQuoteArtifact,
  sourceFileName: string,
): BuzzBeeConversionResult {
  const moldingPayload = artifact.sections.molding.payload
  const injectionLines = p4Rows(moldingPayload.injection_lines)
  if (injectionLines.length === 0) {
    throw new Error('BuzzBee 直转要求啤机分段至少有一条注塑明细')
  }
  const injectionBreakdown = p4Rows(artifact.sections.molding.calculation.line_breakdown)
    .filter((row) => row.kind === 'injection')
  if (injectionBreakdown.length !== injectionLines.length) {
    throw new Error('BuzzBee 直转被阻断：注塑原始行与权威计算明细数量不一致')
  }

  const items = injectionLines.map((row, index): BuzzBeeInternalInjectionItem => {
    const materialZh = p4BuzzBeeMaterial(row.material)
    if (!findMaterial(materialZh)) {
      throw new Error(`BuzzBee 直转缺少客户材料价：第 ${index + 1} 行 ${String(row.material ?? '')}`)
    }
    const machineCode = p4MachineCodeValue(row.machine_code)
    const sets = p4Number(row.sets)
    const targetOutput = p4Number(row.target_output)
    if (!machineCode || !sets || !targetOutput) {
      throw new Error(`BuzzBee 直转缺少第 ${index + 1} 行机型 A 码、套数或目标数`)
    }
    const calculation = injectionBreakdown[index] as Record<string, unknown>
    const quantity = p4Number(row.quantity) || 1
    return {
      name: String(row.item ?? `注塑件${index + 1}`),
      materialZh,
      weightG: p4Number(row.net_weight_g),
      machineTons: machineCode,
      setsPerShot: sets,
      targetYield: targetOutput,
      beerCostInternal: p4Number(calculation.molding_cost_hkd) * quantity,
      materialAmountInternal: p4Number(calculation.material_cost_hkd) * quantity,
      customerBeerCostHint: 0,
    }
  })

  const engineeringPayload = artifact.sections.engineering.payload
  const salesPayload = artifact.sections.sales.payload
  const salesPackagingMaterials = p4Rows(salesPayload.packaging_materials)
  const packagingMaterials = salesPackagingMaterials.length > 0
    ? salesPackagingMaterials.filter((row) => row.category === 'color_box_inner_card' || /彩盒|color\s*box/i.test(String(row.item ?? '')))
    : p4Rows(engineeringPayload.materials)
      .filter((row) => row.category === 'packaging' && /彩盒|color\s*box/i.test(String(row.item ?? '')))
  const salesCartons = p4Rows(salesPayload.cartons)
  const cartons = salesCartons.length > 0 ? salesCartons : p4Rows(engineeringPayload.cartons)
  const cartonOwner = salesCartons.length > 0 ? artifact.sections.sales : artifact.sections.engineering
  const carton = cartons[0] ?? {}
  const cartonCalculation = p4Rows(cartonOwner.calculation.line_breakdown)
    .find((row) => row.kind === 'carton') ?? {}
  const pcsPerCarton = p4Number(carton.qty_per_carton) || 1
  const parsed: BuzzBeeInternalSheet = {
    sheetName: artifact.quoteNo,
    title: artifact.productName,
    productName: artifact.productName || artifact.quoteNo,
    items,
    costRows: p4CostRows(artifact),
    box: {
      length: p4Number(carton.length_in),
      width: p4Number(carton.width_in),
      height: p4Number(carton.height_in),
      pcsPerCarton,
      cartonPriceInternal: p4Number(cartonCalculation.per_piece_hkd),
      cube: p4Number(cartonCalculation.cuft),
    },
    colorBox: p4BuzzBeeColorBox(artifact, pcsPerCarton, packagingMaterials.length > 0),
  }
  return {
    sourceFileName,
    sheets: [convertSheet(parsed, sourceFileName, 0)],
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

function fillRect(rows: XlsxCellInput[][], startRow: number, endRow: number, startCol: number, endCol: number, style: number = XLSX_STYLE.border) {
  for (let rowNumber = startRow; rowNumber <= endRow; rowNumber += 1) {
    for (let columnIndex = startCol; columnIndex <= endCol; columnIndex += 1) {
      const row = ensureRow(rows, rowNumber)
      const existing = row[columnIndex]
      const normalized = existing && typeof existing === 'object' && !Array.isArray(existing)
        ? existing as { value?: XlsxCellValue; formula?: string; style?: number }
        : { value: existing as XlsxCellValue }
      row[columnIndex] = {
        ...normalized,
        style: normalized.style ?? style,
      }
    }
  }
}

function setNumber(rows: XlsxCellInput[][], rowNumber: number, columnIndex: number, value: number, style: number = XLSX_STYLE.number3) {
  setCell(rows, rowNumber, columnIndex, value, style)
}

function formatFormulaNumber(value: number) {
  return String(round(value, 4)).replace(/\.0+$/, '')
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

function buildQuoteOutputSheet(data: BuzzBeeQuoteData, date: Date): XlsxOutputSheet {
  const injectionSlots = Math.max(17, data.injectionRows.length)
  const purchaseSlots = Math.max(19, data.purchaseRows.length)
  const injectionStart = 7
  const injectionSubtotalRow = injectionStart + injectionSlots
  const purchaseLabelRow = injectionSubtotalRow + 2
  const purchaseHeaderRow = purchaseLabelRow + 1
  const purchaseStart = purchaseHeaderRow + 1
  const purchaseEnd = purchaseStart + purchaseSlots - 1
  const purchaseSubtotalRow = purchaseEnd + 3
  const cartonLabelRow = purchaseSubtotalRow + 3
  const gunRow = cartonLabelRow + 1
  const packingRow = cartonLabelRow + 2
  const cartonSizeRow = cartonLabelRow + 3
  const color2Row = cartonLabelRow + 4
  const packCubeHeaderRow = cartonLabelRow + 5
  const outterRow = cartonLabelRow + 6
  const additionalCount = Math.max(1, data.additionalParts.length)
  const addLabelRow = purchaseHeaderRow + 13
  const addHeaderRow = purchaseHeaderRow + 14
  const addStartRow = purchaseHeaderRow + 15
  const addEndRow = addStartRow + additionalCount - 1
  const totalExftyRow = addEndRow + 1
  const usdRow = totalExftyRow + 2
  const rows: XlsxCellInput[][] = []
  const packCount = data.box.pcsPerCarton || 1

  setCell(rows, 1, 0, 'COST BREAKDOWN SHEET (ROYAL REGENT)', XLSX_STYLE.title)
  setCell(rows, 1, 5, 'DATE')
  setCell(rows, 1, 6, excelDateSerial(date), XLSX_STYLE.date)
  setCell(rows, 2, 5, 'REVISED')
  setCell(rows, 2, 6, 0)
  setCell(rows, 4, 0, `ltem:${data.productName}`, XLSX_STYLE.itemTitle)
  setCell(rows, 5, 0, 'INJECTION', XLSX_STYLE.bold)

  ;['DESCRIPTION', "MAT'L", 'WEIGHT', 'PRICE/KG', 'AMOUNT', 'SET/SHOT', 'COST'].forEach((label, index) => {
    setCell(rows, 6, index, label, index === 0 ? XLSX_STYLE.border : XLSX_STYLE.centerBorder)
  })
  setCell(rows, 6, 8, 'Tooling', XLSX_STYLE.centerBorder)

  for (let index = 0; index < injectionSlots; index += 1) {
    const rowNumber = injectionStart + index
    const item = data.injectionRows[index]
    if (item) {
      setCell(rows, rowNumber, 0, item.name, XLSX_STYLE.borderCn)
      setCell(rows, rowNumber, 1, item.material)
      setNumber(rows, rowNumber, 2, item.weight, XLSX_STYLE.number0)
      setNumber(rows, rowNumber, 3, item.pricePerKg, XLSX_STYLE.number1)
      setNumber(rows, rowNumber, 4, item.amount)
      setNumber(rows, rowNumber, 5, item.setsPerShot, XLSX_STYLE.number0)
      setNumber(rows, rowNumber, 6, item.beer)
    } else {
      setNumber(rows, rowNumber, 4, 0)
    }
  }

  setCell(rows, injectionSubtotalRow, 0, 'SUB TOTAL', XLSX_STYLE.boldBorder)
  setNumber(rows, injectionSubtotalRow, 2, data.injectionWeight, XLSX_STYLE.number0)
  setNumber(rows, injectionSubtotalRow, 4, data.injectionAmount, XLSX_STYLE.number3Bold)
  setNumber(rows, injectionSubtotalRow, 6, data.injectionBeer, XLSX_STYLE.number3Bold)
  setNumber(rows, injectionSubtotalRow, 8, 0, XLSX_STYLE.number3Bold)

  setCell(rows, purchaseLabelRow, 0, 'PURCHASE', XLSX_STYLE.bold)
  setCell(rows, purchaseLabelRow, 5, 'TRANSPORTATION', XLSX_STYLE.boldBorder)
  setCell(rows, purchaseLabelRow, 8, 'BREAKDOWN', XLSX_STYLE.boldBorder)
  ;['DESCRIPTION', 'QTY', 'PRICE', 'AMOUNT'].forEach((label, index) => setCell(rows, purchaseHeaderRow, index, label, index === 0 ? XLSX_STYLE.border : XLSX_STYLE.centerBorder))
  setCell(rows, purchaseHeaderRow, 5, 'PARTS')
  setCell(rows, purchaseHeaderRow, 8, 'PLASTIC')
  setNumber(rows, purchaseHeaderRow, 9, data.breakdown.plastic)

  for (let index = 0; index < purchaseSlots; index += 1) {
    const rowNumber = purchaseStart + index
    const item = data.purchaseRows[index]
    if (item) {
      setCell(rows, rowNumber, 0, item.desc, XLSX_STYLE.borderCn)
      setNumber(rows, rowNumber, 1, item.qty, XLSX_STYLE.number0)
      setNumber(rows, rowNumber, 2, item.price)
      setNumber(rows, rowNumber, 3, item.amount)
    }
  }

  const breakdown = data.breakdown
  const rightRows: Array<[number, number, XlsxCellValue, number?]> = [
    [purchaseHeaderRow + 1, 5, 'SHIPPING'],
    [purchaseHeaderRow + 1, 8, 'INJECTION'],
    [purchaseHeaderRow + 1, 9, breakdown.injection, XLSX_STYLE.number3],
    [purchaseHeaderRow + 2, 5, 'KO LAD'],
    [purchaseHeaderRow + 2, 6, 0, XLSX_STYLE.number3],
    [purchaseHeaderRow + 2, 8, 'PURCHASE'],
    [purchaseHeaderRow + 2, 9, breakdown.purchase, XLSX_STYLE.number3],
    [purchaseHeaderRow + 3, 8, 'TRAN'],
    [purchaseHeaderRow + 3, 9, breakdown.tran, XLSX_STYLE.number3],
    [purchaseHeaderRow + 4, 5, 'SUB TOTAL'],
    [purchaseHeaderRow + 4, 6, 0, XLSX_STYLE.number3],
    [purchaseHeaderRow + 4, 8, 'PROCESS'],
    [purchaseHeaderRow + 4, 9, breakdown.process, XLSX_STYLE.number3],
    [purchaseHeaderRow + 6, 5, 'PROCESS'],
    [purchaseHeaderRow + 6, 8, 'SUB'],
    [purchaseHeaderRow + 6, 9, breakdown.sub, XLSX_STYLE.number3],
    [purchaseHeaderRow + 7, 5, 'SPRAY'],
    [purchaseHeaderRow + 7, 6, breakdown.spray, XLSX_STYLE.number3],
    [purchaseHeaderRow + 7, 8, 'P+O'],
    [purchaseHeaderRow + 7, 9, breakdown.po, XLSX_STYLE.number3],
    [purchaseHeaderRow + 8, 5, 'TAMPO'],
    [purchaseHeaderRow + 9, 5, 'ASSEMBLY'],
    [purchaseHeaderRow + 9, 6, breakdown.assembly, XLSX_STYLE.number3],
    [purchaseHeaderRow + 9, 8, 'TOTAL'],
    [purchaseHeaderRow + 9, 9, breakdown.total, XLSX_STYLE.number3],
    [purchaseHeaderRow + 10, 5, 'OTHER'],
    [purchaseHeaderRow + 11, 5, 'SUB TOTAL'],
    [purchaseHeaderRow + 11, 6, breakdown.process, XLSX_STYLE.number3],
  ]

  rightRows.forEach(([rowNumber, col, value, style]) => setCell(rows, rowNumber, col, value, style ?? XLSX_STYLE.border))

  setCell(rows, addLabelRow, 5, 'Additional Parts', XLSX_STYLE.boldBorder)
  setCell(rows, addHeaderRow, 5, 'DESCRIPTION')
  setCell(rows, addHeaderRow, 7, 'QTY')
  setCell(rows, addHeaderRow, 8, 'PRICE')

  if (data.additionalParts.length === 0) {
    setNumber(rows, addStartRow, 9, 0)
  } else {
    data.additionalParts.forEach((item, index) => {
      const rowNumber = addStartRow + index
      setCell(rows, rowNumber, 5, item.desc, XLSX_STYLE.borderCn)
      setNumber(rows, rowNumber, 7, item.qty, XLSX_STYLE.number0)
      setNumber(rows, rowNumber, 8, item.price)
      setNumber(rows, rowNumber, 9, item.amount)
    })
  }

  setCell(rows, totalExftyRow, 5, 'TOTAL Ex-fty cost', XLSX_STYLE.boldBorder)
  setNumber(rows, totalExftyRow, 9, data.exftyCost, XLSX_STYLE.number3Bold)
  setCell(rows, usdRow, 8, 'US$', XLSX_STYLE.boldBorder)
  setNumber(rows, usdRow, 9, data.usd, XLSX_STYLE.number3Bold)

  setNumber(rows, purchaseSubtotalRow - 1, 3, 0)
  setCell(rows, purchaseSubtotalRow, 0, 'SUB TOTAL', XLSX_STYLE.boldBorder)
  setNumber(rows, purchaseSubtotalRow, 3, data.purchaseSubTotal, XLSX_STYLE.number3Bold)

  setCell(rows, cartonLabelRow, 1, 'LENGHT', XLSX_STYLE.centerBorder)
  setCell(rows, cartonLabelRow, 2, 'WIDTH', XLSX_STYLE.centerBorder)
  setCell(rows, cartonLabelRow, 3, 'HEIGHT', XLSX_STYLE.centerBorder)
  setCell(rows, gunRow, 0, 'GUN', XLSX_STYLE.boldBorder)
  setCell(rows, gunRow, 5, '彩盒价格', XLSX_STYLE.boldBorder)
  setCell(rows, packingRow, 0, 'PACKAGING', XLSX_STYLE.boldBorder)
  setCell(rows, packingRow, 5, '报客彩盒', XLSX_STYLE.boldBorder)
  setCell(rows, packingRow, 6, '报客彩盒FSC', XLSX_STYLE.boldBorder)
  setCell(rows, cartonSizeRow, 0, 'CARTON SIZE', XLSX_STYLE.boldBorder)
  setNumber(rows, cartonSizeRow, 1, data.box.length)
  setNumber(rows, cartonSizeRow, 2, data.box.width)
  setNumber(rows, cartonSizeRow, 3, data.box.height)
  setFormulaNumber(
    rows,
    cartonSizeRow,
    5,
    data.colorBox.price1 / packCount,
    `${formatFormulaNumber(data.colorBox.price1)}/${formatFormulaNumber(packCount)}`,
    XLSX_STYLE.number2,
  )
  setFormulaNumber(
    rows,
    cartonSizeRow,
    6,
    data.colorBox.fsc1,
    `F${cartonSizeRow}*${formatFormulaNumber(MARKUPS.carton)}`,
    XLSX_STYLE.number2,
  )
  setCell(rows, cartonSizeRow, 7, data.colorBox.moq1)
  setFormulaNumber(
    rows,
    color2Row,
    5,
    data.colorBox.price2 / packCount,
    `${formatFormulaNumber(data.colorBox.price2)}/${formatFormulaNumber(packCount)}`,
    XLSX_STYLE.number2,
  )
  setFormulaNumber(
    rows,
    color2Row,
    6,
    data.colorBox.fsc2,
    `F${color2Row}*${formatFormulaNumber(MARKUPS.carton)}`,
    XLSX_STYLE.number2,
  )
  setCell(rows, color2Row, 7, data.colorBox.moq2)
  setCell(rows, packCubeHeaderRow, 1, 'PACK', XLSX_STYLE.boldBorder)
  setCell(rows, packCubeHeaderRow, 2, 'CUBE', XLSX_STYLE.boldBorder)
  setCell(rows, outterRow, 0, 'OUTTER', XLSX_STYLE.boldBorder)
  setNumber(rows, outterRow, 1, data.box.pcsPerCarton, XLSX_STYLE.number0)
  setNumber(rows, outterRow, 2, data.box.cube)

  fillRect(rows, 1, 2, 5, 6)
  fillRect(rows, 6, injectionSubtotalRow, 0, 6)
  fillRect(rows, 6, injectionSubtotalRow, 8, 8)
  fillRect(rows, purchaseHeaderRow, purchaseSubtotalRow, 0, 3)
  fillRect(rows, purchaseLabelRow, purchaseHeaderRow + 4, 5, 6)
  fillRect(rows, purchaseHeaderRow + 6, purchaseHeaderRow + 11, 5, 6)
  fillRect(rows, purchaseLabelRow, purchaseHeaderRow + 9, 8, 9)
  fillRect(rows, addLabelRow, totalExftyRow, 5, 9)
  fillRect(rows, usdRow, usdRow, 8, 9)
  fillRect(rows, cartonLabelRow, cartonLabelRow, 1, 3)
  fillRect(rows, gunRow, cartonSizeRow, 0, 3)
  fillRect(rows, gunRow, color2Row, 5, 7)
  fillRect(rows, packCubeHeaderRow, outterRow, 0, 2)

  return {
    name: data.productName,
    rows,
    cols: [30, 10, 10, 10, 12, 14, 10, 10, 12, 12],
    merges: [
      'A3:I3',
      'A4:J4',
      `F${purchaseLabelRow}:G${purchaseLabelRow}`,
      `I${purchaseLabelRow}:J${purchaseLabelRow}`,
      `F${purchaseHeaderRow + 6}:G${purchaseHeaderRow + 6}`,
      `F${addLabelRow}:I${addLabelRow}`,
      `F${addHeaderRow}:G${addHeaderRow}`,
      `F${totalExftyRow}:I${totalExftyRow}`,
      `F${gunRow}:G${gunRow}`,
    ],
  }
}

export function convertBuzzBeeInternalQuote(buffer: ArrayBuffer, sourceFileName: string): BuzzBeeConversionResult {
  const parsedSheets = parseBuzzBeeInternalSheets(buffer)
  const sheets = parsedSheets.map((sheet, index) => convertSheet(sheet, sourceFileName, index))

  return {
    sourceFileName,
    sheets,
  }
}

function sanitizeFileNamePart(value: string) {
  return value.replace(/[\\/:*?"<>|]/g, '_').replace(/\s+/g, ' ').trim()
}

function formatFileDate(date: Date) {
  return `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`
}

export function buildBuzzBeeCustomerQuoteFileName(result: BuzzBeeConversionResult, date = new Date()) {
  const firstProduct = result.sheets[0]?.productName || result.sheets[0]?.name || '报客价'
  const productName = result.sheets.length > 1
    ? `${firstProduct}等${result.sheets.length}款`
    : firstProduct

  return `R0 RR ITEM ${sanitizeFileNamePart(productName)}（${formatFileDate(date)}）.xlsx`
}

export function createBuzzBeeCustomerQuoteWorkbook(result: BuzzBeeConversionResult) {
  return createXlsxWorkbook(
    result.sheets.map((sheet) => buildQuoteOutputSheet(sheet.quoteData, new Date())),
  )
}

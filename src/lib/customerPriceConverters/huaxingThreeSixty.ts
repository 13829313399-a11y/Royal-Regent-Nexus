import { assertPricingCustomer, pricingMaterial, pricingRate, type CustomerPricingSettings } from './pricingSettings'
import { parseXlsxWorkbook, type XlsxParsedSheet } from './xlsxLite'
import { readHuaxing360SourceExtras, type H360Image } from './huaxingThreeSixtySource'

export const HUAXING_360_ID = 'three-sixty-huaxing'
export const HUAXING_360_MAPPING_VERSION = 'rzr-2026-v2'
export type H360Category = 'purchase' | 'electronic' | 'fabric' | 'packaging' | 'others' | 'labor'
export const H360_CATEGORIES: Record<H360Category, string> = { purchase: '采购/五金/马达/电池/油漆', electronic: '电子/线路板', fabric: '布料', packaging: '包装', others: '其他材料/木料', labor: '人工' }
export interface H360Cost {
  source: string; description: string; originalCategory: string; category: H360Category | ''; quantity: number
  sourceHkd: number | null; amountHkd: number | null; needsCategory: boolean
}
export interface H360Plastic { source: string; description: string; material: string; priceMaterial: string; weightG: number; moldingHkd: number; internalMaterialHkd: number; up: number; machine: string; moldNo: string }
export interface H360Fee { description: string; totalUsd: number | null; allocation: number | null; sourceAllocation: number | null; source: string; allocationKey: string }
export interface H360Review {
  productName: string; quoteDate: string; revision: string; preparedBy: string; brand: string; firstEtd: string; moq: number | null
  route: string; toolingCount: number | null; quantityPerContainer: number | null; confirmed: boolean
  fees: H360Fee[]
}
export interface Huaxing360Result {
  mappingVersion: string
  pricing: CustomerPricingSettings; sourceFileName: string; sourceSheet: string; plastic: H360Plastic[]; costs: H360Cost[]
  freight: Array<{ key: string; label: string; hkd: number; fees: H360Fee[] }>
  carton: { dimensions: number[]; quantity: number; priceHkd: number; cuft: number }; colorBox: number[]
  issues: string[]; notices: string[]; review: H360Review; image?: H360Image
}
const value = (s: XlsxParsedSheet, r: number, c: number) => s.rows[r - 1]?.[c - 1]
const text = (x: unknown) => String(x ?? '').trim()
const norm = (x: unknown) => text(x).replace(/\s/g, '').replace(/：/g, ':')
const valid = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x) && x >= 0
const numeric = (x: unknown): number | null => text(x) !== '' && Number.isFinite(Number(x)) && Number(x) >= 0 ? Number(x) : null
const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0)

function classify(category: string, description: string): H360Category | '' {
  if (/工$|人工|车缝|車縫/.test(category)) return 'labor'
  if (/电子|電子/.test(category)) return 'electronic'
  if (/马达|馬達|电池|電池|油漆/.test(category)) return 'purchase'
  // Product decals and USB accessory blisters follow the updated customer's purchased-material section.
  if (/USB.*吸塑/i.test(description) || (/利宝|利寶|贴纸|貼紙/.test(description) && /车面|車面|车灯|車燈|人仔|手制/.test(description))) return 'purchase'
  if (/纸箱|紙箱|彩盒|吸塑|利宝|利寶|包装|包裝/.test(category) || /说明书|說明書|服务卡|服務卡/.test(description)) return 'packaging'
  if (/五金|其他外购|其他外購|外购|外購/.test(category)) return 'purchase'
  if (/布料|布织|布織/.test(category)) return 'fabric'
  if (/木料/.test(category)) return 'others'
  return ''
}

/** Old A:L cost sheet only. No dependency on, or relaxation of, the P4 / Huakang A parser. */
export function convertHuaxing360InternalQuote(buffer: ArrayBuffer, sourceFileName: string, settings: CustomerPricingSettings): Huaxing360Result {
  assertPricingCustomer(settings, HUAXING_360_ID)
  const pricing: CustomerPricingSettings = JSON.parse(JSON.stringify(settings))
  const book = parseXlsxWorkbook(buffer, { includeFormulas: true, valuesOnly: true })
  if (book.sheets.some(s => /P4|__.*metadata|报价元数据|報價元數據|结构化数据|結構化數據|审批与版本|審批與版本/i.test(s.name))) throw new Error('华兴360临时路线只接受旧版 A:L 内部成本明细；内部报价台文件请使用对应正式路线')
  const candidates = book.sheets.map(s => ({ s, header: s.rows.findIndex(r => r && norm(r[2]) === '名称' && norm(r[3]) === '料型' && /料重/.test(text(r[4])) && /啤工/.test(text(r[9])) && /料金额/.test(text(r[10]))) + 1 })).filter(x => x.header > 0)
  if (candidates.length !== 1) throw new Error(candidates.length ? `发现多张内部成本明细，请分别导入：${candidates.map(x => x.s.name).join('、')}` : '未识别华兴360旧版内部成本明细（名称/料型/料重/啤工/料金额）；不能导入客表或内部报价台文件')
  const { s, header } = candidates[0]!
  const issues: string[] = []; const notices: string[] = []
  const extras = readHuaxing360SourceExtras(buffer, s.name)
  s.cellFormulas = { ...s.cellFormulas, ...extras.formulas }
  if (extras.notice) notices.push(extras.notice)
  notices.push('采用新版RZR客表格式；零件名称、料重、用量、原始费用和产品图以本次内部报价为准，不套用样表金额或合并不同来源行。', '马达、电池、油漆及产品贴纸列入采购；TX/RX按原线路板成本列示，不拆出原表未提供的电子元件价格。', '内部报价列出的测试、模具、手办/画图费均保留摊分；含全部费用的FOB为本单报客总价，不沿用样表“不含模具费”的说明。')
  const numberAt = (r: number, c: number, label: string) => {
    const result = numeric(value(s, r, c))
    if (result === null) issues.push(`${s.name}!${String.fromCharCode(64 + c)}${r} ${label}缺少有效非负数值；公式请在 Excel 重算并保存`)
    return result ?? 0
  }
  const detailHeader = s.rows.findIndex((r, i) => r && i > header && norm(r[2]) === '项目' && /出厂价/.test(text(r[3]))) + 1
  if (!detailHeader) throw new Error('未找到“项目 / 出厂价”成本区，无法确定原始费用范围')
  const plastic: H360Plastic[] = []
  const aliases = new Map((pricing.texts.material_aliases ?? '').split(/[;；\n]+/).filter(Boolean).map(line => {
    const pair = line.split('='); if (pair.length !== 2 || !pair[0]?.trim() || !pair[1]?.trim()) throw new Error('客户基础信息料型对应格式应为：原料型=报客料型')
    return [pair[0].trim().toUpperCase(), pair[1].trim()]
  }))
  let totalRow = 0
  for (let r = header + 1; r < detailHeader; r++) {
    if (/合计|小计|总共|总计/.test(text(value(s, r, 3)) + text(value(s, r, 9)))) { totalRow = r; break }
    const description = text(value(s, r, 3)); const material = text(value(s, r, 4))
    if (!description && !material && !text(value(s, r, 5))) continue
    if (!description || !material) { issues.push(`${s.name}!C${r}:D${r} 零件名称或料型缺失`); continue }
    const priceMaterial = aliases.get(material.toUpperCase()) ?? material
    if (priceMaterial !== material) notices.push(`${material} → ${priceMaterial}（客户基础信息明确对应）`)
    plastic.push({ source: `第${r}行`, description, material, priceMaterial, weightG: numberAt(r, 5, '整套料重'), moldingHkd: numberAt(r, 10, '啤工'), internalMaterialHkd: numberAt(r, 11, '原料金额'), up: numberAt(r, 8, '出模套数'), machine: text(value(s, r, 7)), moldNo: text(value(s, r, 2)) })
  }
  if (!plastic.length || !totalRow) throw new Error('塑胶明细或小计边界缺失')
  for (const [c, amount, label] of [[5, sum(plastic.map(p => p.weightG)), '总料重'], [10, sum(plastic.map(p => p.moldingHkd)), '总啤工'], [11, sum(plastic.map(p => p.internalMaterialHkd)), '总料金额']] as const) {
    if (Math.abs(numberAt(totalRow, c, label) - amount) > 0.005) issues.push(`第${totalRow}行${label}与逐行合计不一致，请重算来源文件`)
  }
  const freightRow = s.rows.findIndex((r, i) => r && i > detailHeader && norm(r[1]) === '运费' && norm(r[2]) === '运费') + 1
  if (!freightRow) throw new Error('缺少明确运费行，不能确定原始费用边界')
  const costs: H360Cost[] = []
  for (let r = detailHeader + 1; r < freightRow; r++) {
    const originalCategory = text(value(s, r, 2)); const description = text(value(s, r, 3)); const raw = value(s, r, 4)
    if (!originalCategory && !description && !text(raw)) continue
    if (originalCategory === '料价' || originalCategory === '啤工') {
      const expected = sum(plastic.map(p => originalCategory === '料价' ? p.internalMaterialHkd : p.moldingHkd))
      if (Math.abs(numberAt(r, 4, originalCategory) - expected) > 0.005) issues.push(`D${r} ${originalCategory}与塑胶明细合计不一致`)
      continue
    }
    if (!description) issues.push(`C${r} 存在费用但缺少项目名称`)
    const sourceHkd = numeric(raw)
    if (sourceHkd === null && (text(raw) || s.cellFormulas?.[`D${r}`])) issues.push(`D${r} 金额无效或公式无缓存，请修正原文件并重新导入`)
    const category = classify(originalCategory, description)
    // E is a quantity column for hardware/fabric only; elsewhere it may contain prices.
    const explicitQty = /五金|布料|布织|布織/.test(originalCategory) ? numeric(value(s, r, 5)) : null
    const suffixQty = description.match(/(?:\(|（)(\d+(?:\.\d+)?)\s*(?:PCS|件|码|碼|YDS)\s*(?:\)|）)\s*$/i) ?? description.match(/[*×]\s*(\d+(?:\.\d+)?)\s*(?:PCS|件)?\s*$/i)
    // Count tokens can precede a dimension note, e.g. 防割板2PCS(8*3寸); dimensions are not counts.
    const pieceCounts = [...description.matchAll(/(\d+(?:\.\d+)?)\s*PCS\b/gi)].map(m => Number(m[1]))
    const uniquePieces = [...new Set(pieceCounts)]
    const batteryCount = /电池|電池/.test(originalCategory) ? description.match(/(\d+|[一二两兩三四五六七八九十])\s*粒/)?.[1] : undefined
    const chineseCounts: Record<string, number> = { 一: 1, 二: 2, 两: 2, 兩: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9, 十: 10 }
    const namedQuantity = uniquePieces.length === 1 ? uniquePieces[0] : batteryCount ? (chineseCounts[batteryCount] ?? Number(batteryCount)) : undefined
    const quantity = explicitQty ?? (suffixQty ? Number(suffixQty[1]) : namedQuantity ?? 1)
    if (!(quantity > 0)) issues.push(`第${r}行用量须大于0`)
    costs.push({ source: `D${r}`, description, originalCategory, category, needsCategory: !category, quantity, sourceHkd, amountHkd: sourceHkd })
  }
  const subtotal = numeric(value(s, freightRow + 1, 4))
  const rawTotal = sum(plastic.map(p => p.internalMaterialHkd + p.moldingHkd)) + sum(costs.map(c => c.sourceHkd ?? 0))
  if (subtotal === null || Math.abs(subtotal - rawTotal) > .005) issues.push(`D${freightRow + 1} 原成本小计缺失或与逐行成本不一致，请重算来源文件`)
  const labelRow = (re: RegExp) => s.rows.findIndex(r => r && re.test(norm(r[13]))) + 1
  const cartonRow = labelRow(/装箱尺码|裝箱尺碼/); const colorRow = labelRow(/彩盒尺寸/); const cuftRow = labelRow(/CU\.?FT/i); const cartonPriceRow = labelRow(/箱价|箱價/)
  if (!cartonRow || !colorRow || !cuftRow || !cartonPriceRow) throw new Error('缺少装箱尺码、彩盒尺寸、CU.FT 或箱价')
  const carton = { dimensions: [15, 16, 17].map(c => numberAt(cartonRow, c, '外箱英寸尺寸')), quantity: numberAt(cuftRow, 16, '装箱数'), priceHkd: numberAt(cartonPriceRow, 15, '整箱价'), cuft: numberAt(cuftRow, 15, '箱体积') }
  if (carton.quantity <= 0 || carton.dimensions.some(n => n <= 0) || carton.cuft <= 0) issues.push('装箱数、外箱尺寸及体积必须大于0')
  const colorBox = [15, 16, 17].map(c => numberAt(colorRow, c, '彩盒英寸尺寸'))
  const feeRows = s.rows.map((r, i) => ({ r: i + 1, description: text(r[2]) })).filter(x => x.r > freightRow && /模具费|手办费|测试费/.test(x.description) && /摊|分|成本/.test(x.description) && !/含测试费/.test(x.description))
  const readFees = (column: number) => feeRows.map(f => {
    const ref = `${String.fromCharCode(64 + column)}${f.r}`
    const formula = s.cellFormulas?.[ref]?.replace(/^=/, '').replace(/\s/g, '')
    const match = formula?.match(/^\(?([\d.]+)\)?\/\(?([\d.]+)\)?$/)
    const totalUsd = match ? Number(match[1]) : null; const sourceAllocation = match ? Number(match[2]) : null
    if (match && totalUsd !== null && sourceAllocation !== null) {
      const cached = numeric(value(s, f.r, column))
      if (sourceAllocation <= 0 || cached === null || Math.abs(cached - totalUsd / sourceAllocation) > .00001) issues.push(`${ref} 费用摊分原公式与金额缓存不一致，请重算原文件`)
    }
    const allocationKey = /测试费/.test(f.description) ? 'testing_allocation_qty' : /模具费/.test(f.description) ? 'tooling_allocation_qty' : 'sample_allocation_qty'
    const allocation = pricingRate(pricing, allocationKey, 0)
    return { description: f.description, totalUsd, allocation, sourceAllocation, allocationKey, source: ref }
  })
  const freight = [5, 6, 7].flatMap(c => {
    const label = text(value(s, freightRow - 1, c)); if (!label && !text(value(s, freightRow, c))) return []
    return [{ key: String(c), label, hkd: numberAt(freightRow, c, '运费'), fees: readFees(c) }]
  })
  if (!freight.length) issues.push('没有可用运输路线')
  const moqText = s.rows.slice(freightRow).map(r => text(r[2])).find(t => /MOQ\s*[:：]\s*[\d,.]+\s*K?/i.test(t)) ?? ''
  const moqMatch = moqText.match(/MOQ\s*[:：]\s*([\d,.]+)\s*(K)?/i)
  const moq = moqMatch ? Number(moqMatch[1]!.replace(/,/g, '')) * (moqMatch[2] ? 1000 : 1) : null
  const toolingMatch = text(value(s, totalRow, 3)).match(/(?:总共|合计)(\d+)套/)
  notices.push('转换料价全部采用所附历史客表的USD/kg料价，并由跟客在各客基础资料维护；未知料型须先补齐料价。', '原表内部码数、找数及损耗除数不进入本次计算。', '测试/模具/手办费总额读取原式，摊分数量采用本次冻结的客户基础资料；测试费默认按历史客表100,000件，切换路线不改变摊分数量。', `原模具说明：${text(value(s, totalRow, 3))}`)
  return { mappingVersion: HUAXING_360_MAPPING_VERSION, pricing, image: extras.image, sourceFileName, sourceSheet: s.name, plastic, costs, freight, carton, colorBox, issues, notices: [...new Set(notices)], review: { productName: text(value(s, header - 1, 1)), quoteDate: '', revision: '', preparedBy: pricing.texts.prepared_by ?? '', brand: pricing.texts.brand ?? '', firstEtd: '', moq, route: freight[0]?.key ?? '', toolingCount: toolingMatch ? Number(toolingMatch[1]) : null, quantityPerContainer: null, confirmed: false, fees: JSON.parse(JSON.stringify(freight[0]?.fees ?? [])) } }
}

export function selectHuaxing360Route(result: Huaxing360Result, key: string) {
  const route = result.freight.find(r => r.key === key)
  if (!route) throw new Error('无效运输路线')
  result.review.route = key; result.review.fees = JSON.parse(JSON.stringify(route.fees)); result.review.confirmed = false
}

export function calculateHuaxing360(result: Huaxing360Result) {
  assertPricingCustomer(result.pricing, HUAXING_360_ID)
  const exchange = pricingRate(result.pricing, 'hkd_usd', 7.8)
  if (!(exchange > 0)) throw new Error('港元兑美元必须大于0')
  const missingPrices = [...new Set(result.plastic.filter(p => pricingMaterial(result.pricing, p.priceMaterial, 'USD', 'kg', null) === null).map(p => p.priceMaterial))]
  const plastic = result.plastic.map(p => ({ ...p, price: pricingMaterial(result.pricing, p.priceMaterial, 'USD', 'kg', null), totalUsd: p.weightG * (pricingMaterial(result.pricing, p.priceMaterial, 'USD', 'kg', null) ?? 0) / 1000, moldingUsd: p.moldingHkd / exchange }))
  const costs = result.costs.map(c => ({ ...c, totalUsd: (valid(c.amountHkd) ? c.amountHkd : 0) / exchange }))
  const materialUsd = sum(plastic.map(p => p.totalUsd)) + sum(costs.filter(c => c.category && c.category !== 'labor').map(c => c.totalUsd))
  const laborUsd = sum(plastic.map(p => p.moldingUsd)) + sum(costs.filter(c => c.category === 'labor').map(c => c.totalUsd))
  const basicUsd = materialUsd + laborUsd
  const scrapBasis = pricingRate(result.pricing, 'scrap_include_labor', 1)
  if (scrapBasis !== 0 && scrapBasis !== 1) throw new Error('损耗基数选择必须为0（材料）或1（材料加人工）')
  const scrapUsd = (materialUsd + laborUsd * scrapBasis) * pricingRate(result.pricing, 'scrap_rate', .02)
  const markupUsd = basicUsd * pricingRate(result.pricing, 'markup_rate', .12)
  const exFactoryUsd = basicUsd + scrapUsd + markupUsd
  const freightUsd = (result.freight.find(f => f.key === result.review.route)?.hkd ?? 0) / exchange
  const fees = result.review.fees.map(f => {
    const allocation = pricingRate(result.pricing, f.allocationKey, 0)
    return { ...f, allocation, perUnitUsd: valid(f.totalUsd) && allocation > 0 ? f.totalUsd / allocation : 0 }
  })
  const finalUsd = exFactoryUsd + freightUsd + sum(fees.map(f => f.perUnitUsd))
  return { plastic, costs, exchange, missingPrices, materialUsd, laborUsd, basicUsd, scrapUsd, markupUsd, exFactoryUsd, freightUsd, fees, finalUsd }
}

export function huaxing360Problems(result: Huaxing360Result): string[] {
  const errors = [...result.issues]; const r = result.review
  if (result.mappingVersion !== HUAXING_360_MAPPING_VERSION) errors.push('报客映射已更新，请重新导入内部报价并核对后输出')
  const calc = calculateHuaxing360(result)
  if (calc.missingPrices.length) errors.push(`客户基础信息缺少 USD/kg 料价：${calc.missingPrices.join('、')}；维护后重新导入`)
  result.costs.forEach(c => { if (!c.category) errors.push(`${c.source} ${c.description}：请选择费用类别`); if (!valid(c.amountHkd)) errors.push(`${c.source} ${c.description}：原金额未填写；补入金额，已含其他费用或不计须明确输入0`); if (!(c.quantity > 0)) errors.push(`${c.source} 用量须大于0`) })
  if (!r.productName.trim()) errors.push('请填写产品名称')
  const date = new Date(r.quoteDate)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(r.quoteDate) || Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== r.quoteDate) errors.push('请填写有效报价日期')
  if (!r.preparedBy.trim() || !r.revision.trim()) errors.push('请填写制表人和版本')
  if (!valid(r.moq) || r.moq <= 0 || !Number.isInteger(r.moq)) errors.push('MOQ须为正整数')
  if (!result.freight.some(f => f.key === r.route)) errors.push('请选择运输路线')
  if (r.toolingCount !== null && (!valid(r.toolingCount) || !Number.isInteger(r.toolingCount))) errors.push('模具数量须为非负整数或留空')
  if (r.quantityPerContainer !== null && (!valid(r.quantityPerContainer) || r.quantityPerContainer <= 0 || !Number.isInteger(r.quantityPerContainer))) errors.push('每柜数量须为正整数或留空')
  calc.fees.forEach(f => { if (!valid(f.totalUsd) || !valid(f.allocation) || f.allocation <= 0 || !Number.isInteger(f.allocation)) errors.push(`${f.source} ${f.description}：请核对费用USD及基础资料中的正整数摊分数量（不计费用填0）`) })
  return errors
}

export function validateHuaxing360Export(result: Huaxing360Result) {
  const errors = huaxing360Problems(result)
  if (errors.length) throw new Error(errors.join('；'))
  if (!result.review.confirmed) throw new Error('请先确认华兴360原始成本、运输路线和费用摊分')
}

export function huaxing360PreviewSheets(result: Huaxing360Result) {
  const calc = calculateHuaxing360(result)
  const internal = sum(result.plastic.map(p => p.internalMaterialHkd + p.moldingHkd)) + sum(result.costs.map(c => valid(c.amountHkd) ? c.amountHkd : 0))
  return [{ id: 'huaxing-360', name: result.sourceSheet, sourceFileName: result.sourceFileName, rowCount: result.plastic.length + result.costs.length, totalInternalHkd: internal, totalCustomerHkd: calc.finalUsd * calc.exchange, details: [{ id: 'huaxing-360-total', sheetId: 'huaxing-360', sheetName: result.sourceSheet, itemNo: '', description: result.review.productName, internalPriceHkd: internal, customerPriceHkd: calc.finalUsd * calc.exchange, previousCustomerPriceHkd: 0, differenceHkd: 0, marginBand: huaxing360Problems(result).length ? '不完整草稿' : '已计算，待核对', compareStatus: '持平' as const }] }]
}

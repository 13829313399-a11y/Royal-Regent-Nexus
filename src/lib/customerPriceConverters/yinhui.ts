import { parseXlsxWorkbook, type XlsxCellValue } from './xlsxLite'
import { parseP4InternalQuoteArtifact, type P4InternalQuoteArtifact, type P4SectionCode } from './p4Artifact'
import { extractYinhuiProductImage, type YinhuiProductImage } from './yinhuiTemplate'
import { YINHUI_PROFILES, YINHUI_MATERIAL_PRICES_HKD_KG, yinhuiProfileForModel, type YinhuiProfileId } from './yinhuiProfiles'

export const YINHUI_CUSTOMER_QUOTE_TEMPLATE_URL = '/templates/yinhui-customer-quote-template.bin'
export { YINHUI_MATERIAL_PRICES_HKD_KG } from './yinhuiProfiles'
export const YINHUI_HKD_USD = 7.8
// Keep source resin names even when the customer has not supplied a price yet.
type Material = string
export interface YinhuiCostRow {
  description: string
  source: string
  quantity: number
  amountHkd: number
  internalHkd: number
  isBattery?: boolean
}
export interface YinhuiToolRow {
  moldNo: string
  partNo: string
  description: string
  usage: number
  cavity: number
  weightG: number
  material: Material
  laborHkd: number
  toolingHkd: number
}
export interface YinhuiQuoteData {
  templateId?: YinhuiProfileId
  model: string
  productName: string
  quoteDate: string
  packaging: string
  moq: number
  stage: string
  adaptor: '' | 'included' | 'not included'
  tryMe: '' | 'YES' | 'NO'
  freightLclHkd: number | null
  freightFclHkd: number | null
  colorBoxCm: number[]
  cartonCm: number[]
  cartonPack: number
  tools: YinhuiToolRow[]
  plastic: YinhuiCostRow[]
  mechanical: YinhuiCostRow[]
  electronic: YinhuiCostRow[]
  fabric?: YinhuiCostRow[]
  packagingRows: YinhuiCostRow[]
  carton: YinhuiCostRow
  assemblyHkd: number
  sprayingHkd: number
  packagingLaborHkd: number
  battery: string
  internalTotalHkd: number
  image?: YinhuiProductImage
}
export interface YinhuiConversionResult {
  sourceFileName: string
  warnings: string[]
  quoteData: YinhuiQuoteData
  sheets: Array<{
    id: string; name: string; sourceFileName: string; rowCount: number
    totalInternalHkd: number; totalCustomerHkd: number
    details: Array<{
      id: string; sheetId: string; sheetName: string; itemNo: string; description: string
      internalPriceHkd: number; customerPriceHkd: number; previousCustomerPriceHkd: number
      differenceHkd: number; marginBand: string; compareStatus: '上调' | '下调' | '持平'
    }>
  }>
}
const text = (v: unknown) => String(v ?? '').trim()
const obj = (v: unknown): Record<string, unknown> => v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, unknown> : {}
const records = (v: unknown) => Array.isArray(v) ? v.map(obj) : []
const sum = (values: number[]) => values.reduce((a, b) => a + b, 0)
const round = (v: number) => Math.round((v + Number.EPSILON) * 1e8) / 1e8
const hasValue = (v: unknown) => v !== null && v !== undefined && v !== ''
function numeric(v: unknown, label: string, allowBlank = false) {
  if (!hasValue(v) && allowBlank) return 0
  const result = Number(v)
  if (!hasValue(v) || !Number.isFinite(result) || result < 0) throw new Error(`银辉：${label}缺少有效非负数（公式需先在 Excel 中计算并保存）`)
  return result
}
function positive(v: unknown, label: string) {
  const result = numeric(v, label)
  if (result <= 0) throw new Error(`银辉：${label}必须大于 0`)
  return result
}
export function isYinhuiCustomer(value: string) {
  return ['银辉', '銀輝', '银辉客', '銀輝客', 'yinhui', 'silverlit'].includes(value.trim().toLowerCase().replace(/[\s_-]/g, ''))
}
function material(v: unknown): Material {
  const key = text(v).normalize('NFKC').toUpperCase().replace(/[‐‑‒–—−]/g, '-').replace(/\s*-\s*/g, '-').replace(/料$/, '').trim()
  if (!key || /^#(?:NULL!|DIV\/0!|VALUE!|REF!|NAME\?|NUM!|N\/A|SPILL!|CALC!)$/.test(key)) throw new Error('银辉内部料型缺失或为公式错误，请先核对料型')
  return key
}
export function yinhuiMaterialPrice(_data: YinhuiQuoteData, resin: Material): number | null {
  const key = material(resin)
  if (!Object.hasOwn(YINHUI_MATERIAL_PRICES_HKD_KG, key)) return null
  return positive(YINHUI_MATERIAL_PRICES_HKD_KG[key as keyof typeof YINHUI_MATERIAL_PRICES_HKD_KG], `客表 ${key} 港币公斤价`)
}
export function yinhuiMissingMaterialPrices(data: YinhuiQuoteData) {
  return [...new Set(data.tools.filter(row => yinhuiMaterialPrice(data, row.material) === null).map(row => material(row.material)))]
}
const simplified = (value: string) => value.replace(/[殼電門輪轂膠遙蓋紅機鈕彈夾軸輸齒轉動馬頭銀後側發線潤貼說螺絲]/g, (c) => {
  const from = '殼電門輪轂膠遙蓋紅機鈕彈夾軸輸齒轉動馬頭銀後側發線潤貼說螺絲'
  const to =   '壳电门轮毂胶遥盖红机钮弹夹轴输齿转动马头银后侧发线润贴说螺丝'
  return to[from.indexOf(c)] || c
}).replace(/[\s（）()、，,]/g, '').toLowerCase()
const translations: Array<[RegExp, string]> = [
  [/双安全压簧/g, 'Double Safety Compression Spring '], [/密绕拉簧/g, 'Close-wound Extension Spring '],
  [/胶钉带/g, 'Plastic Fastener Tie '], [/透明胶圈/g, 'Clear Elastic Band '],
  [/介子头螺丝/g, 'Washer Head Screw '], [/直花钉轴/g, 'Knurled Pin '], [/钉轴/g, 'Pin '],
  [/单面强力背胶/g, 'Strong Single-sided Adhesive'], [/度/g, ' deg'],
  [/电子[（(]\d+[）)]/g, 'PCBA'], [/车[缝縫][（(]\d+[）)]/g, 'Fabric Assembly'],
  [/螺絲/g, 'Screw '], [/丝母/g, 'Nut '], [/机牙/g, 'Machine Screw '],
  [/AA[ A]*电池(?:负正片|正负片|正片|负片)/g, 'Battery Contact'],
  [/回中弹簧/g, 'Return Spring '], [/密绕弹簧/g, 'Close-wound Spring '], [/压力弹簧|压簧/g, 'Compression Spring '], [/接触弹簧/g, 'Contact Spring '], [/弹簧/g, 'Spring '],
  [/双花D轴/g, 'Double Knurled D Shaft '], [/双花轴/g, 'Double Knurled Shaft '], [/單花軸/g, 'Single Knurled Shaft '], [/光[軸轴]/g, 'Smooth Shaft '], [/軸|轴/g, 'Shaft '],
  [/直花钉轴|钉轴/g, 'Knurled Pin '], [/釘/g, 'Pin '], [/T钉/g, 'T-Pin '],
  [/介子螺丝/g, 'Washer Head Screw '], [/介子/g, 'Washer '], [/垫片/g, 'Pad '],
  [/單頭蝸桿齒/g, 'Single-start Worm Gear '], [/右旋/g, 'Right Hand'],
  [/单面背胶|單面背膠/g, 'Single-sided Adhesive '], [/黑色/g, 'Black '], [/白色/g, 'White '], [/矽膠/g, 'Silicone '],
  [/磁鐵/g, 'Magnet '], [/釹鐵錋/g, 'NdFeB '], [/電鎳/g, 'Nickel Plated'],
  [/软管|拉管/g, 'Tube '], [/泡棉/g, 'Foam '], [/胶袋/g, 'Poly Bag '], [/PC片/g, 'PC Sheet '],
  [/充电线(?!装配)/g, 'Charging Cable '], [/^马达/g, 'Motor '], [/车身贴纸/g, 'Product Sticker'],
  [/O型圈/g, 'O-Ring'], [/彩盒\+外箱/g, 'Color Box / Outer Carton'], [/利宝$/g, 'Label'],
  [/报关费用\/文件费\/操作费用[：:]?/g, 'Documents / Customs Fee'],
  [/驱动马达\s*金属刷130/gi, 'Drive Motor 130 with Metal Brush'],
  [/打炮马达\s*金属刷130/gi, 'Shooting Motor 130 with Metal Brush'],
  [/电子[（(]发射机器人[）)]/g, 'Electronics (Launching Robot)'],
  [/电子[（(]遥控器[）)]/g, 'Electronics (Remote Controller)'],
  [/电子[（(]充电模组[）)]/g, 'Electronics (Charging Module)'],
  [/电子[（(]弹夹[）)]/g, 'Electronics (Magazine)'],
  [/橡[膠胶]圈/g, 'Rubber Ring '], [/透明[膠胶]橡根/g, 'Clear Rubber'], [/聚氨脂/g, 'Polyurethane'], [/要求透/g, 'Clear'],
  [/介子头螺丝/g, 'Washer Head Screw '], [/回中彈簧/g, 'Return Spring '], [/压簧/g, 'Compression Spring '],
  [/螺丝/g, 'Screw '], [/螺母/g, 'Nut '], [/半牙/g, 'Partial Thread'], [/光轴/g, 'Smooth Shaft '],
  [/单面背胶黑色EVA/g, 'Black Single-sided Adhesive EVA '], [/子弹/g, 'Dart '],
  [/充电线装配和塑胶/g, 'Charging Cable'], [/脸4C的PC印刷片/g, '4C Printed PC Face Lens'],
  [/錫線|锡线/g, 'Solder Wire'], [/润滑油/g, 'Lubricant'], [/吸塑/g, 'Blister'],
  [/扎带/g, 'Cable Tie '], [/封箱胶纸\/[膠胶]水/g, 'Packing Tape / Adhesive Glue'],
  [/说明书/g, 'Instruction Manual'], [/利宝[貼贴]纸/g, 'Libo Sticker'], [/彩盒\+内卡|彩盒\/内咭/g, 'Color Box / Inner Card'], [/彩盒/g, 'Color Box'], [/内卡/g, 'Inner Card'],
  [/带插头线/g, 'Battery with Plug Wire'], [/电池/g, 'Battery'], [/透明/g, 'Clear'],
]
function translate(value: string) {
  return translations.reduce((s, [pattern, replacement]) => s.replace(pattern, replacement), value).replace(/（/g, '(').replace(/）/g, ')').trim()
}
function quantityFromDescription(value: string) {
  // These parentheses identify the product model, not the number of PCBAs/fabric sets.
  if (/^(?:电子|電子|车缝|車縫)[（(]\d+[)）]$/.test(value.trim())) return 1
  const match = value.match(/[（(]\s*(\d+(?:\.\d+)?(?:\s*[*×x]\s*\d+(?:\.\d+)?)*)\s*(?:PCS?|个|件)?\s*[)）]\s*$/i)
  return match ? match[1]!.split(/[*×x]/).reduce((a, b) => a * positive(b.trim(), `${value}用量`), 1) : 1
}
function today() { return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date()) }
function emptyData(): YinhuiQuoteData {
  return { model: '', productName: '', quoteDate: today(), packaging: 'Window Box', moq: 0, stage: '', adaptor: '', tryMe: '',
    freightLclHkd: null, freightFclHkd: null, colorBoxCm: [], cartonCm: [], cartonPack: 0,
    tools: [], plastic: [], mechanical: [], electronic: [], fabric: [], packagingRows: [],
    carton: { description: 'Outer Carton', source: '', quantity: 1, amountHkd: 0, internalHkd: 0 },
    assemblyHkd: 0, sprayingHkd: 0, packagingLaborHkd: 0, battery: '', internalTotalHkd: 0 }
}
function addCost(data: YinhuiQuoteData, category: string, description: string, quantity: number, amountHkd: number, internalHkd: number, source: string) {
  const line: YinhuiCostRow = { description: translate(description), quantity, amountHkd: round(amountHkd), internalHkd, source }
  if (/装配工|assembly/i.test(category)) {
    if (/包装|包裝|packing/i.test(description)) data.packagingLaborHkd += amountHkd
    else data.assemblyHkd += amountHkd
  } else if (/油漆|喷油|噴油|painting/i.test(category)) data.sprayingHkd += amountHkd
  else if (/纸箱|紙箱|carton/i.test(category)) data.carton = { ...line, description: 'Outer Carton', quantity: 1, amountHkd: round(data.carton.amountHkd + amountHkd), internalHkd: data.carton.internalHkd + internalHkd }
  else if (/车衣|車衣|车缝|車縫|sewing|fabric/i.test(category)) (data.fabric ||= []).push(line)
  else if (/电子|電子|电池|電池|electronic/i.test(category)) {
    data.electronic.push(line)
    if (/电池|電池|battery/i.test(`${category} ${description}`)) { line.isBattery = true; data.battery = [data.battery, line.description].filter(Boolean).join('; ') }
  } else if (/车身贴纸|產品貼紙|产品贴纸/.test(description)) data.mechanical.push(line)
  else if (/橡[膠胶]圈|rubber ring|PE泡棉|PVC拉管|PC片单面背胶|介子 .*PET|扎带3\.5[*x×]250/i.test(description) || (!/五金|hardware/i.test(category) && /EVA/i.test(description))) data.plastic.push(line)
  else if (/吸塑|利宝|利寶|彩盒|内咭|包装|报关|packaging/i.test(category) || /胶钉带|透明胶圈|扎带|^垫片[（(]|胶纸|膠紙|胶水|膠水|胶袋|吸塑|说明书|文件费|custom|document|carton/i.test(description)) data.packagingRows.push(line)
  else if (/马达|馬達|五金|其他外购|其他外購|hardware|auxiliary/i.test(category)) data.mechanical.push(line)
  else if (amountHkd !== 0) throw new Error(`银辉尚未映射成本类别“${category}”：${description}（${source}），不能漏项输出`)
}
export function yinhuiTotals(data: YinhuiQuoteData) {
  const missingMaterialPrices = yinhuiMissingMaterialPrices(data)
  // With missing prices these are known-cost subtotals, not complete quotations.
  // The workbook leaves the corresponding unit-price inputs blank for completion.
  const plastic = sum(data.tools.map((r) => r.weightG * (yinhuiMaterialPrice(data, r.material) ?? 0) / 1000)) + sum(data.plastic.map((r) => r.amountHkd))
  const mechanical = sum(data.mechanical.map((r) => r.amountHkd))
  const electronic = sum(data.electronic.map((r) => r.amountHkd))
  const fabric = sum((data.fabric || []).map((r) => r.amountHkd))
  const injection = sum(data.tools.map((r) => r.laborHkd))
  const packaging = sum(data.packagingRows.map((r) => r.amountHkd)) + data.carton.amountHkd
  const labour = injection + data.assemblyHkd + data.sprayingHkd
  const bom = plastic + mechanical + electronic + fabric + labour
  const exFactory = bom + packaging + data.packagingLaborHkd
  return { plastic, mechanical, electronic, fabric, injection, labour, packaging, bom, exFactory, missingMaterialPrices,
    fcl: data.freightFclHkd === null ? null : exFactory + data.freightFclHkd,
    lcl: data.freightLclHkd === null ? null : exFactory + data.freightLclHkd,
    tooling: sum(data.tools.map((r) => r.toolingHkd)) }
}
function finish(data: YinhuiQuoteData, sourceFileName: string, warnings: string[]): YinhuiConversionResult {
  // Only the first packaging detail row has the customer's three dimension input cells.
  const colorBox = data.packagingRows.findIndex((r) => /color box/i.test(r.description))
  if (colorBox > 0) data.packagingRows.unshift(data.packagingRows.splice(colorBox, 1)[0]!)
  const limits: Array<[string, number, number]> = [['Tool Plan', data.tools.length, 53], ['塑料外购', data.plastic.length, 8], ['五金', data.mechanical.length, 27], ['电子', data.electronic.length, 10], ['包装材料', data.packagingRows.length, 12]]
  for (const [name, count, max] of limits) if (count > max) throw new Error(`银辉${name}有 ${count} 行，超过当前模板 ${max} 行容量，请先扩展映射，不能截断明细`)
  const total = yinhuiTotals(data)
  if (total.missingMaterialPrices.length) warnings.push(`缺少银辉报客料价：${total.missingMaterialPrices.join('、')}。对应单价将留空，当前合计暂未包含这些料价；确认后可导出，发送客户前请补齐。`)
  const sheetId = 'yinhui-summary'
  const summaryName = total.missingMaterialPrices.length ? 'SUM(總計) · 待补料价' : 'SUM(總計)'
  const groups: Array<[string, number]> = [[total.missingMaterialPrices.length ? 'Plastic (price pending)' : 'Plastic', total.plastic], ['Mechanical', total.mechanical], ['Electronic', total.electronic], ['Fabric', total.fabric], ['Labour', total.labour], ['Packaging material', total.packaging], ['Packaging labour', data.packagingLaborHkd]]
  const details = groups.map(([description, price], i) => ({ id: `${sheetId}-${i}`, sheetId, sheetName: summaryName, itemNo: String(i + 1), description,
    internalPriceHkd: 0, customerPriceHkd: round(price), previousCustomerPriceHkd: round(price), differenceHkd: 0, marginBand: '独立客表口径', compareStatus: '持平' as const }))
  return { sourceFileName, quoteData: data, warnings: [...new Set(warnings)], sheets: [{ id: sheetId, name: summaryName, sourceFileName,
    rowCount: details.length, totalInternalHkd: round(data.internalTotalHkd), totalCustomerHkd: round(total.exFactory), details }] }
}

function legacyConversion(buffer: ArrayBuffer, sourceFileName: string, workbook = readYinhuiSource(buffer)): YinhuiConversionResult {
  workbook.sheets.forEach((sheet) => { sheet.rows = Array.from(sheet.rows, (row) => row || []) })
  const variants = workbook.sheets.filter(s => /^明细\s*[(（]/.test(s.name))
  const windowBox = variants.filter(s => s.name.replace(/\s/g, '').replace(/（/g, '(').replace(/）/g, ')') === '明细(开窗盒)')
  if (variants.length && (windowBox.length !== 1 || !windowBox[0]!.rows.slice(0, 12).some(r => /^#\s*89127\b/.test(text(r[0]))))) throw new Error('银辉存在包装版本明细，但无法唯一确认 89127 开窗盒页；请明确包装版本，不能默认取第一页')
  const main = windowBox[0] || workbook.sheets.find((s) => ['明细', '內部明細', '内部明细'].includes(s.name))
  const plan = workbook.sheets.find((s) => s.name.replace(/\s/g, '').toLowerCase() === 'toolplan')
  if (!main || !/银辉|銀輝|silverlit|yinhui/i.test(sourceFileName + workbook.sheets.flatMap((s) => s.rows.slice(0, 10).flat()).join(' '))) throw new Error('银辉原表需要“明细”页及银辉客户标识，请勿导入其他客户报价或报客成品表')
  const data = emptyData()
  const warnings = ['临时映射按单 BOM 汇入第一组；第二组保留空表，不推断 RX/TX 拆分。', '采用当前内部报价金额，不复制示例客表的手填金额、四舍五入金额或旧 MOQ。']
  const rows = main.rows
  const header = rows.findIndex((r) => text(r[2]) === '名称' && /料型/.test(text(r[3])) && /料重/.test(text(r[4])))
  if (header < 1) throw new Error('银辉内部明细未找到名称/料型/料重表头')
  const title = text(rows[header - 1]?.[0])
  data.model = title.match(/#\s*([\w-]+)/)?.[1] || ''
  data.templateId = yinhuiProfileForModel(data.model)
  const profile = YINHUI_PROFILES[data.templateId]
  data.productName = profile.product || title.replace(/^#\s*[\w-]+\s*/, '').split(/[（(]/)[0]?.trim() || ''
  data.packaging = profile.packaging
  const filenameModel = sourceFileName.match(/(?:银辉|銀輝|silverlit)[ _-]*(\d+)/i)?.[1]
  if (filenameModel && filenameModel !== data.model) warnings.push(`型号冲突：文件名 ${filenameModel}，内部明细 ${data.model}。请核对并修改型号。`)
  if (data.templateId !== 'standard') warnings.push(`使用 ${profile.label} 原客表版式；包装、英文产品名称来自对应参考客表，请复核。`)
  warnings.push('料价全型号统一：ABS 15.65、TPR 18.8、PP 12.6、POM 34.07、C-ABS 24（客户提供）；PVC 17.16、TPE 15.9（多表核对），单位 HKD/kg。不沿用个别客表错填料型或不同单价。')
  if (windowBox.length) warnings.push(`已选择“${main.name}”；密封盒属于另一包装方案，不参与本次计算。`)
  if (['81283', '89127'].includes(data.templateId)) warnings.push(`${data.templateId} 原客表部分料重公式含固定数值；对应内部料重改变时会阻止导出，需先核对模板公式。`)
  let activeBoxColumn: number | undefined
  const readLabel = (pattern: RegExp) => {
    for (const r of rows) for (let c = 10; c < Math.min(r.length, 20); c++) if ((activeBoxColumn === undefined || c === activeBoxColumn) && pattern.test(text(r[c]))) return r.slice(c + 1, c + 4)
    return []
  }
  let cartons = rows.flatMap((r, row) => r.flatMap((v, c) => c >= 10 && c < 20 && /^(?:裝箱尺碼|装箱尺码)/.test(text(v))
    ? [{ label: text(v), column: c, row: row + 1, size: r.slice(c + 1, c + 4).map(n => positive(n, '外箱尺寸')) }] : []))
  if (new Set(cartons.map(c => c.column)).size > 1) {
    // Side-by-side alternatives must follow the current carton-cost formula's
    // dependencies, never the first label or whichever dimensions are smaller.
    const dependencies = new Set<string>()
    const visit = (ref: string) => {
      if (dependencies.has(ref)) return
      dependencies.add(ref)
      const formula = (main.cellFormulas?.[ref] || '').replace(/\$/g, '')
      if (formula.includes('!')) return // cross-sheet ambiguity must be reviewed
      for (const child of formula.match(/\b[A-Z]{1,3}\d+\b/g) || []) visit(child)
    }
    rows.forEach((r, i) => { if (/纸箱|紙箱|carton/i.test(text(r[1])) && /外箱|outer carton/i.test(text(r[2]))) visit(`D${i + 1}`) })
    const columns = [...new Set(cartons.filter(c => c.size.every((_, i) => dependencies.has(`${String.fromCharCode(66 + c.column + i)}${c.row}`))).map(c => c.column))]
    if (columns.length !== 1) throw new Error('银辉并列外箱方案无法从当前纸箱成本公式唯一确认，已阻止输出，请核对')
    activeBoxColumn = columns[0]!
    cartons = cartons.filter(c => c.column === activeBoxColumn)
    warnings.push(`同页存在并列包装方案；按当前纸箱成本公式引用的 ${String.fromCharCode(65 + activeBoxColumn)} 列包装资料取尺寸、装箱数及 MOQ，不套用旁边的另一方案。`)
  }
  if (!cartons.length || cartons.some(c => c.size.length !== 3)) throw new Error('银辉外箱尺寸缺少完整的长宽高')
  const unit = (label: string) => /CM|厘米/i.test(label) ? 'cm' : /INCH|英寸|吋/i.test(label) ? 'inch' : ''
  if (cartons.length === 1) data.cartonCm = cartons[0]!.size.map(v => v * (unit(cartons[0]!.label) === 'cm' ? 1 : 2.54))
  else {
    const cmCandidates = cartons.filter(a => cartons.every(b => {
      const cm = unit(b.label) === 'cm' || (!unit(b.label) && b === a)
      return b.size.every((v, i) => Math.abs(v * (cm ? 1 : 2.54) - a.size[i]!) < .001)
    }) && unit(a.label) !== 'inch')
    if (cmCandidates.length !== 1) throw new Error('银辉多处外箱尺寸不能按厘米/英寸（2.54）唯一核对，已阻止输出，请确认单位及包装版本')
    data.cartonCm = cmCandidates[0]!.size
    warnings.push('外箱尺寸出现多处记录，已按 1 英寸 = 2.54 厘米交叉核对，避免重复换算。')
  }
  const colorCm = readLabel(/彩盒.*CM/i)
  data.colorBoxCm = colorCm.length ? colorCm.map((v) => positive(v, '彩盒厘米尺寸')) : readLabel(/^彩盒尺寸[：:]/).map((v) => positive(v, '彩盒英寸尺寸') * 2.54)
  data.cartonPack = positive(readLabel(/^装箱[：:]|^裝箱[：:]/)[0], '装箱数量')
  data.moq = positive(readLabel(/^MOQ[：:]/i)[0], 'MOQ')
  if (data.templateId !== 'standard' && data.moq !== 5000) warnings.push(`当前内部 MOQ 为 ${data.moq}，参考客表为 5000；本次使用内部 MOQ，请核对。`)
  const costStart = rows.findIndex((r) => text(r[3]) === '出厂价') + 1
  const management = rows.findIndex((r, i) => i > costStart && text(r[3]) === '货价')
  const end = management >= 0 ? management : rows.length
  if (!costStart) throw new Error('银辉明细未找到出厂价成本表头')
  const blocks: Array<{ start: number; end: number; factor: number; hinted: boolean }> = []
  let blockStart = costStart
  const isCost = (r: XlsxCellValue[]) => hasValue(r[1]) && hasValue(r[2]) && !['料价', '啤工', '运费', '吊柜费'].includes(text(r[1]))
  for (let i = costStart; i < end; i++) {
    if (!/^[×x*]$/.test(text(rows[i]?.[2]))) continue
    if (!/^[÷/]$/.test(text(rows[i + 1]?.[2]))) throw new Error('银辉倍率下方缺少结算除数')
    const factor = positive(rows[i]?.[3], '明细倍率') / positive(rows[i + 1]?.[3], '结算除数')
    const detail = rows.slice(blockStart, i).filter(isCost)
    const hintCol = blocks.length === 0 ? 4 : 6
    // Complete quoted-price columns cross-check the cost × multiplier rule; they do not override it.
    const hintCount = detail.filter(r => typeof r[hintCol] === 'number' && Math.abs(Number(r[hintCol]) - Number(r[3])) > 1e-8).length
    blocks.push({ start: blockStart, end: i, factor, hinted: detail.length > 0 && hintCount / detail.length >= .6 })
    blockStart = i + 2
  }
  if (!blocks.length) throw new Error('银辉未找到有效倍率区间')
  const mainFactor = blocks[0]!.factor
  const injections: Array<{ row: number; description: string; material: Material; weight: number; labor: number; cavity: number }> = []
  let rowIndex = header + 1
  while (hasValue(rows[rowIndex]?.[2]) && hasValue(rows[rowIndex]?.[3])) {
    const row = rows[rowIndex]!
    const rawLabor = numeric(row[9], `第${rowIndex + 1}行啤工`, blocks[0]!.hinted)
    const hintedLabor = blocks[0]!.hinted && typeof row[11] === 'number' && (rawLabor === 0 || Number(row[11]) <= rawLabor * 5)
    if (hintedLabor && hasValue(row[9]) && Math.abs(Number(row[11]) - rawLabor * mainFactor) > .005) throw new Error(`银辉第 ${rowIndex + 1} 行报客啤工与内部啤工×倍率不一致，请核对，不能自动选一边`)
    injections.push({ row: rowIndex + 1, description: text(row[2]), material: material(row[3]), weight: positive(row[4], `第${rowIndex + 1}行料重`), labor: !hasValue(row[9]) && hintedLabor ? numeric(row[11], '报客啤工') : rawLabor * mainFactor, cavity: numeric(row[7], '注塑出模套数', true) || 1 })
    rowIndex++
  }
  if (!injections.length) throw new Error('银辉没有可转换的注塑明细')
  if (plan) {
    type Group = { mold: string; resin: string; rows: XlsxCellValue[][] }
    const groups: Group[] = []; let group: Group | undefined
    for (const row of plan.rows) {
      if (hasValue(row[3]) && hasValue(row[0]) && hasValue(row[12]) && !/Material|膠料/.test(text(row[3]))) { group = { mold: text(row[0]), resin: text(row[3]), rows: [] }; groups.push(group) }
      if (group && hasValue(row[1]) && hasValue(row[2]) && hasValue(row[12]) && !/Net|重量/.test(text(row[12]))) group.rows.push(row)
    }
    const used = new Set<Group>()
    for (const injection of injections) {
      const firstName = simplified(injection.description.split('*')[0] || '')
      let matches = groups.filter((g) => !used.has(g) && simplified(text(g.rows[0]?.[1])) === firstName)
      if (matches.length !== 1) matches = groups.filter((g) => !used.has(g) && Math.abs(sum(g.rows.map((r) => numeric(r[6], 'Tool Plan用量') * numeric(r[12], 'Tool Plan重量'))) - injection.weight) <= .03)
      if (matches.length !== 1) throw new Error(`银辉无法唯一匹配注塑第 ${injection.row} 行到 Tool Plan：${injection.description}`)
      const matched = matches[0]!; used.add(matched)
      if (matched.resin.toUpperCase() !== injection.material) warnings.push(`模具 ${matched.mold} 料型 ${matched.resin} 与明细 ${injection.material} 不一致；按当前明细 ${injection.material} 计价。`)
      matched.rows.forEach((r, i) => data.tools.push({ moldNo: i === 0 ? matched.mold : '', partNo: text(r[2]), description: text(r[1]), usage: numeric(r[6], 'Tool Plan用量'), cavity: numeric(r[5], 'Tool Plan出模数'), weightG: i === 0 ? injection.weight : 0, material: injection.material, laborHkd: i === 0 ? injection.labor : 0, toolingHkd: 0 }))
    }
    if (used.size !== groups.length) throw new Error('银辉 Tool Plan 存在未匹配模具，不能遗漏输出')
  } else {
    warnings.push('内部文件无独立 Tool Plan：按明细模组拆出零件，用该组总料重和啤工计价；没有依据的客户模号、零件号留空。')
    for (const injection of injections) {
      const parts = injection.description.replace(/\s+/g, '').split(/[/;；](?=[\p{L}])/u).map(p => p.replace(/\/$/, '')).filter(Boolean)
      parts.forEach((part, i) => {
        const qty = part.match(/\*(\d+(?:\.\d+)?)$/)
        data.tools.push({ moldNo: '', partNo: '', description: part.replace(/\*\d+(?:\.\d+)?$/, ''), usage: qty ? positive(qty[1], '零件用量') : 1, cavity: injection.cavity, weightG: i ? 0 : injection.weight, material: injection.material, laborHkd: i ? 0 : injection.labor, toolingHkd: 0 })
      })
    }
  }
  const consumed = new Set<number>()
  blocks.forEach((block, index) => {
    for (let k = block.start; k < block.end; k++) {
      const row = rows[k] || []; if (!isCost(row)) continue
      const internal = numeric(row[3], `明细 ${k + 1} 行金额`)
      const hint = row[index === 0 ? 4 : 6]
      const amount = internal * block.factor
      if (block.hinted && typeof hint === 'number' && Math.abs(hint - amount) > .005) throw new Error(`银辉明细第 ${k + 1} 行报客金额与内部金额×所在区间倍率不一致，请核对，不能自动选一边`)
      addCost(data, text(row[1]), text(row[2]), quantityFromDescription(text(row[2])), amount, internal, `${main.name}!D${k + 1}`)
      consumed.add(k)
    }
  })
  for (let k = costStart; k < end; k++) if (isCost(rows[k] || []) && !consumed.has(k)) throw new Error(`银辉明细第 ${k + 1} 行没有归属倍率区间`)
  const finalIndex = rows.findIndex((r, i) => i >= costStart && text(r[2]) === '出厂价')
  const feeIndex = rows.findIndex((r, i) => i >= costStart && /报关费用.*文件费/.test(text(r[2])) && !consumed.has(i))
  let extraFee = 0
  const extraIndex = feeIndex >= 0 ? feeIndex : finalIndex > 0 && hasValue(rows[finalIndex - 1]?.[3]) ? finalIndex - 1 : -1
  if (extraIndex >= 0) {
    extraFee = numeric(rows[extraIndex]?.[3], '出厂价附加费用')
    data.packagingRows.push({ description: 'Documents / Customs Fee', source: `${main.name}!D${extraIndex + 1}`, quantity: 1, amountHkd: extraFee, internalHkd: extraFee })
    if (feeIndex < 0) warnings.push(`明细 D${extraIndex + 1} 是出厂价单独加回的费用但未标名称，暂列文件费，请复核。`)
  }
  const freightRow = rows.find((r, i) => i >= costStart && i < end && text(r[1]) === '运费')
  const costHeader = rows[costStart - 1]!
  if (freightRow) {
    for (const [key, pattern] of [['freightFclHkd', /盐田柜|鹽田柜/], ['freightLclHkd', /盐田散|鹽田散/]] as const) {
      const col = costHeader.findIndex(v => pattern.test(text(v)))
      if (col >= 0 && hasValue(freightRow[col])) data[key] = numeric(numeric(freightRow[col], '盐田运费') * mainFactor - extraFee, '盐田运费扣除另列文件费后的金额')
    }
  }
  // Earlier source version has explicit per-piece FCL/LCL prices next to the document fee.
  const explicit = rows.findIndex((r, i) => i >= costStart && text(r[4]) === 'FCL' && text(r[5]) === 'LCL')
  if (explicit >= 0 && !hasValue(rows[explicit + 1]?.[3]) && typeof rows[explicit + 1]?.[4] === 'number' && typeof rows[explicit + 1]?.[5] === 'number') {
    data.freightFclHkd = numeric(rows[explicit + 1]?.[4], 'FCL 运费'); data.freightLclHkd = numeric(rows[explicit + 1]?.[5], 'LCL 运费')
  }
  data.internalTotalHkd = finalIndex >= 0 ? numeric(rows[finalIndex]?.[3], '内部出厂报价') : numeric(rows[management + 1]?.[3], '内部出厂报价')
  const contacts = data.mechanical.filter(r => /Battery Contact/.test(r.description))
  if (contacts.length > 1) {
    const first = data.mechanical.indexOf(contacts[0]!)
    data.mechanical = data.mechanical.filter(r => !contacts.includes(r))
    data.mechanical.splice(first, 0, { description: 'Battery Contacts (set)', quantity: 1, amountHkd: sum(contacts.map(r => r.amountHkd)), internalHkd: sum(contacts.map(r => r.internalHkd)), source: contacts.map(r => r.source).join(', ') })
  }
  const tooling = workbook.sheets.find((s) => s.name === '模具报价')
  if (tooling) {
    const compatible = tooling.rows.slice(0, 12).flat().map(text).join(' ').includes(data.model)
    const moldPrices = tooling.rows.filter(r => /^\w[\w-]*$/.test(text(r[1])) && typeof r[9] === 'number' && text(r[2]))
    const firstPart = (name: string) => simplified(name.split(/[*/;]/)[0] || '')
    for (const row of moldPrices) {
      let target = data.tools.find(t => t.moldNo === text(row[1]))
      if (!plan && compatible) target = data.tools.find(t => t.weightG > 0 && firstPart(t.description) === firstPart(text(row[2])))
      if (target && compatible) {
        target.toolingHkd += numeric(row[9], '模具港币价'); if (!target.moldNo) target.moldNo = text(row[1])
        if (!plan) {
          const start = data.tools.indexOf(target)
          const next = data.tools.findIndex((t, i) => i > start && t.weightG > 0)
          const group = data.tools.slice(start, next < 0 ? undefined : next)
          const parts = text(row[2]).replace(/\s+/g, '').split(/[/;；](?=[\p{L}])/u).map(p => {
            const match = p.match(/^(.*)\*(\d+(?:\.\d+)?)$/)
            return { name: simplified(match?.[1] || ''), cavities: Number(match?.[2] || 0) }
          })
          const sets = Number(row[8]); const cavities = Number(row[7])
          if (sets > 0 && parts.length === group.length && parts.every(p => p.cavities > 0) && Math.abs(sum(parts.map(p => p.cavities)) - cavities) < .000001 && group.every(t => parts.filter(p => p.name === simplified(t.description)).length === 1)) {
            for (const t of group) {
              const p = parts.find(p => p.name === simplified(t.description))!
              t.cavity = p.cavities; t.usage = p.cavities / sets
            }
            warnings.push('有完整模具资料的模组：出模量取逐件模穴数，用量=逐件模穴数÷每啤成品数；已核对模穴合计，不把“1出几套”直接当作单件模穴。总料重及啤工仍取内部报价，避免重复乘用量。')
          }
        }
        continue
      }
      const purchaseMatch = !plan && compatible && rows.slice(costStart, end).some(r => firstPart(text(r[2])) === firstPart(text(row[2])))
      if (purchaseMatch) data.tools.push({ moldNo: text(row[1]), partNo: '', description: text(row[2]), usage: 1, cavity: 1, weightG: 0, material: material(row[6]), laborHkd: 0, toolingHkd: numeric(row[9], '外购件模具港币价') })
      else warnings.push('模具报价页存在型号/模号无法匹配的费用，本次未计入，请核对后再报客。')
    }
  }
  data.image = extractYinhuiProductImage(buffer, main.name)
  if (!data.image) warnings.push('未读取到主产品图，请在报客前补充确认。')
  return finish(data, sourceFileName, warnings)
}

export function convertYinhuiP4InternalQuote(artifact: P4InternalQuoteArtifact, sourceFileName: string): YinhuiConversionResult {
  if (!isYinhuiCustomer(artifact.customer)) throw new Error('受控文件客户与银辉映射不一致')
  if (!/huaxing|华兴|華興/i.test(artifact.factoryAndWorkshop)) throw new Error('银辉映射仅适用于华兴受控报价')
  const data = emptyData()
  const warnings = ['银辉临时映射按单 BOM 输出；请核对英文名称、型号、运费和产品资料。']
  data.productName = artifact.productName
  data.model = artifact.productName.match(/#\s*([\w-]+)/)?.[1] || ''
  data.moq = positive(artifact.quantity, 'P4 MOQ')
  const lines = (code: P4SectionCode) => records(artifact.sections[code].calculation.line_breakdown)
  const totals = (code: P4SectionCode) => obj(artifact.sections[code].calculation.totals)
  for (const code of ['slush', 'sewing', 'hair'] as const) if (numeric(totals(code).total_hkd, `${code}合计`, true) > 0) throw new Error(`银辉临时映射尚未覆盖${artifact.sections[code].name}，请先补充该类映射，不能漏项输出`)
  const sales = artifact.sections.sales.payload
  for (const [key, label] of [['testing_fee_total_usd', '测试费'], ['additional_tax_hkd', '附加税'], ['indonesia_freight_hkd', '印尼运费']] as const) {
    if (numeric(totals('sales')[key], `P4 ${label}`, true) > 0) throw new Error(`银辉临时映射尚未配置${label}的摊分位置，不能漏项输出`)
  }
  const shipping = obj(sales.shipping)
  const tiers = records(shipping.markup_tiers)
  const selected = tiers.find((r) => Number(r.moq) === Number(shipping.selected_markup_moq))
  if (tiers.length && !selected) throw new Error('银辉 P4 缺少明确选定的 MOQ 倍率')
  const multiplier = positive(selected?.markup_x ?? shipping.markup_x ?? artifact.referenceSnapshot.markup, 'P4 倍率')
  const misc = numeric(shipping.misc_ratio ?? artifact.referenceSnapshot.misc_ratio, 'P4 杂项比例')
  if (misc >= 1) throw new Error('银辉 P4 杂项比例必须小于 1')
  const quoted = (line: Record<string, unknown>, value: unknown) => numeric(value, 'P4 成本') * positive(line.markup_override ?? multiplier, 'P4 明细倍率') / (1 - misc)
  let internalQuotedTotal = 0
  for (const line of lines('molding')) {
    if (line.reference_only) continue
    if (line.kind !== 'injection') throw new Error('银辉临时 Tool Plan 仅支持注塑；吹气等工序须新增映射')
    const qty = positive(line.quantity ?? 1, '注塑用量')
    const weight = positive(line.net_weight_g, '注塑净重') * qty
    const amount = numeric(line.amount_hkd, '注塑合计'); internalQuotedTotal += quoted({}, amount)
    data.tools.push({ moldNo: text(line.mold_no), partNo: '', description: text(line.item), usage: qty, cavity: numeric(line.cavity, '出模数', true),
      weightG: weight, material: material(line.material), laborHkd: quoted({}, numeric(line.molding_cost_hkd, '啤工') * qty), toolingHkd: 0 })
  }
  if (!data.tools.length) throw new Error('银辉 P4 缺少注塑明细')
  for (const line of lines('engineering')) {
    if (line.reference_only) continue
    if (line.kind !== 'material') throw new Error(`银辉尚未映射工程成本 ${text(line.kind)}`)
    const amount = numeric(line.amount_hkd, '工程材料'); internalQuotedTotal += quoted(line, amount)
    addCost(data, text(line.auxiliary_category) || text(line.category), text(line.item) + (line.specification ? ` ${text(line.specification)}` : ''), positive(line.quantity ?? 1, '工程用量'), quoted(line, amount), amount, `工程/${text(line.item)}`)
  }
  const electronic = lines('electronic').filter((r) => !r.reference_only && hasValue(r.amount_hkd))
  const electronicTotal = numeric(totals('electronic').total_hkd, '电子总计', true)
  const rawElectronic = sum(electronic.map((r) => numeric(r.amount_hkd, '电子明细')))
  if (electronicTotal > 0 && rawElectronic <= 0) throw new Error('银辉 P4 电子合计缺少可拆分明细')
  for (const line of electronic) {
    const amount = numeric(line.amount_hkd, '电子明细') * (rawElectronic ? electronicTotal / rawElectronic : 1)
    internalQuotedTotal += quoted(line, amount)
    addCost(data, /电池|battery/i.test(text(line.item)) ? '电池' : '电子', text(line.item), positive(line.quantity ?? 1, '电子用量'), quoted(line, amount), amount, `电子/${text(line.item)}`)
  }
  for (const line of lines('assembly')) {
    if (line.reference_only) continue
    if (!['assembly_process', 'assembly_manual_total'].includes(text(line.kind))) throw new Error(`银辉尚未映射装配成本 ${text(line.kind)}`)
    const amount = numeric(line.amount_hkd_pcs ?? line.amount_hkd, '装配人工'); internalQuotedTotal += quoted(line, amount)
    if (line.category === 'packaging' || line.category === 'mixed_pack') data.packagingLaborHkd += quoted(line, amount)
    else data.assemblyHkd += quoted(line, amount)
  }
  for (const line of lines('painting')) {
    if (line.reference_only) continue
    const amount = numeric(line.amount_hkd, '喷油油漆成本'); internalQuotedTotal += quoted(line, amount)
    data.sprayingHkd += quoted(line, amount)
  }
  const cartonPayload = records(sales.cartons)
  if (cartonPayload.length !== 1) throw new Error('银辉临时映射要求一条明确主纸箱记录')
  const carton = cartonPayload[0]!
  data.cartonPack = positive(carton.qty_per_carton, '每箱数量')
  data.cartonCm = ['length_in', 'width_in', 'height_in'].map((k) => positive(carton[k], '外箱英寸尺寸') * 2.54)
  const cm = obj(sales.color_box_size_cm); const inch = obj(sales.color_box_size_in)
  data.colorBoxCm = ['length', 'width', 'height'].map((k) => hasValue(cm[k]) ? numeric(cm[k], '彩盒厘米尺寸') : numeric(inch[k], '彩盒英寸尺寸', true) * 2.54)
  for (const line of lines('sales')) {
    if (line.kind === 'sales_testing_fee' && numeric(line.total_usd, '测试费总计', true) > 0) throw new Error('银辉临时映射尚未配置测试费的摊分位置，不能漏项输出')
    if (line.reference_only || line.kind === 'tax') continue
    if (line.kind === 'packaging_material') {
      const amount = numeric(line.amount_hkd, '包装材料'); internalQuotedTotal += quoted(line, amount)
      addCost(data, 'packaging', text(line.item), positive(line.quantity ?? 1, '包装用量'), quoted(line, amount), amount, `业务/${text(line.item)}`)
    } else if (line.kind === 'carton') {
      const amount = numeric(line.per_piece_hkd, '纸箱每件价'); internalQuotedTotal += quoted(line, amount)
      data.carton = { description: 'Outer Carton', source: '业务/主纸箱', quantity: 1, internalHkd: amount, amountHkd: quoted(line, amount) }
    } else if (hasValue(line.amount_hkd) && numeric(line.amount_hkd, '业务成本') > 0) throw new Error(`银辉尚未映射业务成本 ${text(line.kind)}`)
  }
  if (!data.carton.source) throw new Error('银辉 P4 缺少主纸箱服务端计算')
  const routes = records(totals('sales').freight_options)
  for (const kind of ['Lcl', 'Fcl'] as const) {
    const matches = routes.filter((r) => /yt|盐田|鹽田/i.test(`${text(r.route_key)} ${text(r.item)}`) && (kind === 'Lcl' ? /lcl|散/i : /40/).test(`${text(r.route_key)} ${text(r.item)}`))
    if (matches.length === 1) data[`freight${kind}Hkd`] = quoted({}, matches[0]!.per_piece_hkd ?? matches[0]!.freight_per_piece_hkd)
  }
  if (data.freightFclHkd === null || data.freightLclHkd === null) warnings.push('P4 未提供唯一盐田 LCL / 40FT 路线，请在核对区填写已确认的每件运费（HKD）。')
  if (numeric(totals('engineering').mold_total_rmb, '模具总计', true) > 0) throw new Error('银辉 P4 有新开模费用，但尚无已确认的逐模港币价映射，请使用含匹配模具报价页的银辉原表')
  data.internalTotalHkd = internalQuotedTotal
  warnings.push('P4 主产品图未随结构化资料传入时，需在输出前核对图片；未填写的适配器、Try me 和阶段保持空白。')
  return finish(data, sourceFileName, warnings)
}

function readYinhuiSource(buffer: ArrayBuffer) {
  const variants = ['开窗盒', '密封盒'].flatMap(box => [`明细（${box}）`, `明细(${box})`, `明细 (${box})`, `明细 （${box}）`])
  return parseXlsxWorkbook(buffer, { sheetNames: ['明细', ...variants, '內部明細', '内部明细', 'Tool PLan', 'Tool Plan', 'Tool plan', 'TOOL PLAN', '模具报价', 'BOM', '结构化数据', '审批与版本'], valuesOnly: true, includeFormulas: true })
}
export function convertYinhuiInternalQuote(buffer: ArrayBuffer, sourceFileName: string): YinhuiConversionResult {
  const workbook = readYinhuiSource(buffer)
  const sheets = workbook.sheets
  if (sheets.some((s) => ['结构化数据', '审批与版本'].includes(s.name))) {
    const result = convertYinhuiP4InternalQuote(parseP4InternalQuoteArtifact(buffer), sourceFileName)
    result.quoteData.image = extractYinhuiProductImage(buffer, '报价明细')
    return result
  }
  return legacyConversion(buffer, sourceFileName, workbook)
}
export function validateYinhuiExport(data: YinhuiQuoteData) {
  if (!data.model.trim() || !data.productName.trim()) throw new Error('请核对并填写银辉型号及英文产品名称')
  positive(data.moq, 'MOQ')
  if (!Number.isInteger(data.moq)) throw new Error('银辉 MOQ 必须为整数')
  if (!/^\d{4}-\d{2}-\d{2}$/.test(data.quoteDate) || !Number.isFinite(Date.parse(data.quoteDate))) throw new Error('请填写有效报价日期')
  if (!data.packaging.trim()) throw new Error('请填写银辉包装方式')
  numeric(data.freightFclHkd, '40FT 每件运费'); numeric(data.freightLclHkd, 'LCL 每件运费')
  for (const line of [...data.plastic, ...data.mechanical, ...data.electronic, ...(data.fabric || []), ...data.packagingRows]) {
    positive(line.quantity, 'BOM 用量'); numeric(line.amountHkd, 'BOM 金额')
    if (!line.description.trim() || /[\u3400-\u9fff]/.test(line.description)) throw new Error(`请在核对区补全英文物料名称：${line.description || line.source}`)
  }
  if (/[\u3400-\u9fff]/.test(data.productName)) throw new Error('请在核对区填写英文产品名称')
}
export function buildYinhuiCustomerQuoteFileName(result: YinhuiConversionResult) {
  const pending = yinhuiMissingMaterialPrices(result.quoteData).length ? '-待补料价' : ''
  return `银辉-${result.quoteData.model}-报客价-${result.quoteData.quoteDate}${pending}.xlsx`.replace(/[\\/:*?"<>|]/g, '-')
}

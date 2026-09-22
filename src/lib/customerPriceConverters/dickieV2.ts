import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'
import { DICKIE_FIXED_MATERIALS, DICKIE_FIXED_REMARKS, normalizeDickieMapping, normalizeDickieMold, type DickieBilingual, type DickieMapping } from '../dickieQuote'
import { createXlsxWorkbook, type XlsxCellInput, type XlsxOutputSheet } from './xlsxLite'
import template from './dickieTemplateStyles.json'
import type { P4InternalQuoteArtifact } from './p4Artifact'
import type { DickyConversionResult } from './dicky'

export interface DickieProductImage { bytes: Uint8Array; extension: 'png' | 'jpg' }
export interface DickieMappedOffer { label: DickieBilingual; remark: DickieBilingual; moq: string; prices: [number, number, number] }
export interface DickieMappedMold {
  no: string; parts: DickieBilingual; group: DickieBilingual; shared: DickieBilingual
  resin: string; size: string; material: string; cavities: string; quantity: number; price: number; remark: DickieBilingual
}
export interface DickieMappedProduct {
  identity: string; mapping: DickieMapping; outerPack: number; dimensions: string; cartonDimensions: string
  cartonCbm: number; offers: DickieMappedOffer[]; molds: DickieMappedMold[]; image?: DickieProductImage
}
export interface DickieV2QuoteData { products: DickieMappedProduct[] }
const obj = (v: unknown): Record<string, unknown> => v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, unknown> : {}
const list = (v: unknown) => Array.isArray(v) ? v.map(obj) : []
const txt = (v: unknown) => String(v ?? '').trim()
function fail(message: string): never { throw new Error(`Dickie 报客资料待补：${message}`) }
function required(v: unknown, label: string, english = false) {
  const value = txt(v)
  if (!value || /#(?:REF!|VALUE!|DIV\/0!|N\/A)/.test(value)) fail(label)
  if (english && /[\u3400-\u9fff]/u.test(value)) fail(`${label}须填写英文`)
  return value
}
function positive(v: unknown, label: string, integer = false) {
  const n = Number(v)
  if (!Number.isFinite(n) || n <= 0 || (integer && !Number.isInteger(n))) fail(label)
  return n
}
function bilingual(v: DickieBilingual, label: string, optional = false) {
  if (optional && !v.zh && !v.en) return v
  required(v.zh, `${label}中文`); required(v.en, `${label}英文`, true)
  return v
}
// Excel ROUND for positive customer prices, to one decimal place.
const roundPrice = (n: number) => Math.round((n + Number.EPSILON * Math.max(1, Math.abs(n))) * 10) / 10
const dimText = (values: number[]) => values.map(n => Number(n.toFixed(3))).join(' × ')
function imageExtent(image: DickieProductImage, maxWidth: number, maxHeight: number) {
  const bytes = image.bytes
  let width = 4, height = 3
  if (image.extension === 'png' && bytes.length >= 24) {
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
    width = view.getUint32(16); height = view.getUint32(20)
  } else if (image.extension === 'jpg') {
    for (let p = 2; p + 8 < bytes.length;) {
      if (bytes[p] !== 0xff) break
      const marker = bytes[p + 1]!, length = (bytes[p + 2]! << 8) + bytes[p + 3]!
      if ([0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf].includes(marker)) {
        height = (bytes[p + 5]! << 8) + bytes[p + 6]!; width = (bytes[p + 7]! << 8) + bytes[p + 8]!; break
      }
      if (length < 2) break
      p += length + 2
    }
  }
  if (!(width > 0 && height > 0)) { width = 4; height = 3 }
  const scale = Math.min(maxWidth / width, maxHeight / height)
  return { cx: Math.round(width * scale), cy: Math.round(height * scale) }
}

export function convertDickieV2(artifact: P4InternalQuoteArtifact, sourceFileName: string): DickyConversionResult {
  const sales = artifact.sections.sales.payload
  const mapping = normalizeDickieMapping(obj(obj(sales.customer_quote_fields).dickie).mapping)
  if (!mapping) fail('请在内部报价台启用 Dickie 报客资料')
  const handoff = artifact.customerMapping
  if (!handoff || handoff.version !== 'dickie-v2') fail('当前文件没有新版报价结果，请重新最终放行并接收')
  if (handoff.factory_id !== 'huaxing' || !['dickie', 'dicky'].includes(txt(artifact.customer).toLowerCase())
      || handoff.customer !== artifact.customer || handoff.quote_no !== artifact.quoteNo
      || handoff.version_label !== artifact.versionLabel || handoff.formula_version !== artifact.formulaVersion
      || handoff.reference_snapshot_id !== artifact.referenceSnapshotId) fail('厂区、客户或放行版本不一致')
  required(mapping.client_name, '客户显示名称'); required(mapping.attention, 'Attn'); required(mapping.from_name, 'From', true)
  const date = new Date(`${mapping.quote_date}T00:00:00Z`)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(mapping.quote_date) || !Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== mapping.quote_date) fail('报价日期无效')
  required(mapping.item_number, '客户产品编号')
  bilingual(mapping.item_name, '产品名称'); bilingual(mapping.item_note, '产品附注', true)
  mapping.remarks.forEach((r, i) => bilingual(r, `变动说明第 ${i + 1} 条`, true))
  const inner = positive(mapping.inner_pack, '内装数须为正整数', true)
  const carton = list(sales.cartons)[0]
  if (!carton) fail('通用业务主纸箱')
  const outerPack = positive(carton.qty_per_carton, '通用业务外装数须为正整数', true)
  if (inner > outerPack || outerPack % inner !== 0) fail('外装数须为内装数的整数倍')
  const sizes = obj(sales[mapping.dimension_source === 'product' ? 'product_size_in' : 'color_box_size_in'])
  const scale = mapping.dimension_unit === 'mm' ? 25.4 : 2.54
  const dimensions = dimText(['length', 'width', 'height'].map(k => positive(sizes[k], '通用业务产品/彩盒长宽高') * scale))
  const cartonDims = mapping.customer_carton_enabled
    ? ['length', 'width', 'height'].map(k => positive(obj(mapping.customer_carton_cm)[k], '报客外箱长宽高（cm）'))
    : ['length_in', 'width_in', 'height_in'].map(k => positive(carton[k], '通用业务主纸箱长宽高') * 2.54)
  const tierRows = list(obj(sales.shipping).markup_tiers)
  const priceRows = list(handoff.prices)
  const ids = new Set<string>()
  const offers = mapping.offers.filter(o => o.included).map<DickieMappedOffer>((o, index) => {
    const label = `报价方案 ${index + 1}`
    if (!o.id || ids.has(o.id)) fail(`${label}标识重复，请重新新增方案`)
    ids.add(o.id)
    bilingual(o.label, `${label}名称`); bilingual(o.remark, `${label}备注`, true)
    const moq = positive(o.moq, `${label} MOQ`, true)
    if (tierRows.filter(t => Number(t.moq) === moq && t.include_in_output !== false).length !== 1) fail(`${label}必须选择已启用的唯一 MOQ 档位`)
    const routeKeys = [o.route_40, o.route_20, o.route_lcl]
    if (new Set(routeKeys).size !== 3 || routeKeys.some(k => !k)) fail(`${label}须分别选择 40柜、20柜和散货路线`)
    const computed = routeKeys.map(key => {
      const rows = priceRows.filter(p => Number(p.moq) === moq && p.route_key === key)
      if (rows.length !== 1) fail(`${label}缺少该 MOQ 的已计算运输报价，请检查运费设置后重新放行`)
      if (!Number.isFinite(Number(rows[0]!.lift_hkd)) || Number(rows[0]!.lift_hkd) !== 0) fail(`${label}含吊柜费，与固定说明不符；请在通用业务中核对吊柜费比例`)
      return positive(rows[0]!.price_hkd, `${label}运输报价必须大于 0`)
    })
    const bases = o.price_source === 'confirmed'
      ? [o.confirmed_40, o.confirmed_20, o.confirmed_lcl].map(p => positive(p, `${label}客人确认价`)) : computed
    if (o.price_source === 'confirmed') required(o.confirmed_reference, `${label}客人确认价依据`)
    // All amount changes in one step are applied before rounding. Separate steps model
    // a rounded regional uplift followed by a rounded seasonal reduction.
    const prices = bases.map(base => {
      let price = roundPrice(base)
      o.adjustments.forEach(a => {
        required(a.label, `${label}调整依据`)
        if (!Number.isFinite(a.percent) || !Number.isFinite(a.amount_hkd) || a.percent <= -100) fail(`${label}调整数值无效`)
        price = roundPrice(price * (1 + a.percent / 100) + a.amount_hkd)
        positive(price, `${label}调整后价格须大于 0`)
      })
      return price
    }) as [number, number, number]
    return { label: o.label, remark: o.remark, moq: o.moq_text || `${moq.toLocaleString('en-US')} pcs`, prices }
  })
  if (!offers.length) fail('至少启用一个报价方案')
  const molds: DickieMappedMold[] = []
  if (mapping.include_molds) {
    bilingual(mapping.first_shot, '首次试模期'); bilingual(mapping.finish, '完模期'); bilingual(mapping.lead_time_basis, '模期起算条件')
    const seen = new Set<string>()
    list(artifact.sections.engineering.payload.molds).forEach((m, index) => {
      const extra = normalizeDickieMold(m.dickie_export)
      if (!extra.included) return
      const label = `模具第 ${index + 1} 行`
      const no = required(extra.customer_mold_no || m.mold_no, `${label}模号`)
      bilingual(extra.group, `${label}分组`, true); bilingual(extra.shared_products, `${label}共用产品`, true); bilingual(extra.remark, `${label}报客备注`, true)
      const key = `${extra.group.zh}\u0000${extra.group.en}\u0000${no}`
      if (seen.has(key)) fail(`${label}同组模号重复`)
      seen.add(key)
      molds.push({ no, parts: { zh: required(m.chinese_name || m.item, `${label}中文名称`), en: required(extra.parts_en, `${label}英文名称`, true) },
        group: extra.group, shared: extra.shared_products, resin: required(m.material_type || m.material, `${label}胶料`),
        size: `${required(m.mold_size || m.mold_specification, `${label}模具尺寸`)} ${extra.size_unit}`,
        material: required(m.mold_base_material, `${label}模料`), cavities: required(m.cavity, `${label}模穴`),
        quantity: positive(m.quantity, `${label}套数`, true), price: positive(extra.customer_price_hkd, `${label}报客模费（HKD）`), remark: extra.remark })
    })
    if (!molds.length) fail('已启用模具报价，但未勾选模具')
  }
  const product: DickieMappedProduct = { identity: `${txt(handoff.quote_id)}:${artifact.versionLabel}`, mapping, outerPack, dimensions, cartonDimensions: dimText(cartonDims), cartonCbm: Number((cartonDims.reduce((a, b) => a * b, 1) / 1e6).toFixed(4)), offers, molds }
  return resultFromData({ products: [product] }, sourceFileName)
}

function resultFromData(data: DickieV2QuoteData, sourceFileName: string): DickyConversionResult {
  const details = data.products.flatMap((p, i) => p.offers.map((o, j) => ({ id: `${i}:${j}`, sheetId: 'dickie-v2', sheetName: 'Quotation', itemNo: p.mapping.item_number,
    description: `${p.mapping.item_name.zh} / ${o.label.zh} / MOQ ${o.moq} / 40柜 ${o.prices[0].toFixed(1)} · 20柜 ${o.prices[1].toFixed(1)} · 散货 ${o.prices[2].toFixed(1)}`,
    internalPriceHkd: 0, customerPriceHkd: o.prices[0], previousCustomerPriceHkd: o.prices[0], differenceHkd: 0, marginBand: '—', compareStatus: '持平' as const })))
  return { sourceFileName, sourceBuffer: new ArrayBuffer(0), summarySheetName: '总表', clientName: data.products[0]!.mapping.client_name,
    quoteDate: new Date(`${data.products[0]!.mapping.quote_date}T00:00:00`), v2Data: data,
    sheets: [{ id: 'dickie-v2', name: 'Quotation / 总表', sourceFileName, rowCount: details.length, totalInternalHkd: 0, totalCustomerHkd: details.reduce((n, d) => n + d.customerPriceHkd, 0), details }] }
}

export function combineDickieV2(results: DickyConversionResult[]): DickyConversionResult {
  if (!results.length || results.some(r => !r.v2Data)) fail('合并只接受新版 Dickie 放行报价')
  const products = results.flatMap(r => r.v2Data!.products)
  const header = products[0]!.mapping
  const keys = ['company', 'client_name', 'attention', 'from_name', 'quote_date', 'revision', 'quotation_kind'] as const
  const ids = new Set<string>()
  for (const p of products) {
    if (keys.some(k => p.mapping[k] !== header[k])) fail('合并报价的公司、客户、联系人、日期、版本及报价类型须一致')
    if (ids.has(p.identity)) fail('同一报价版本不能重复合并')
    ids.add(p.identity)
  }
  return resultFromData({ products }, 'Dickie-Combined-Quotation.xlsx')
}

/** Original Revell customer template styles, isolated from all source quotation data. */
function templateStyles() {
  const doc = new DOMParser().parseFromString(template.stylesXml, 'application/xml')
  const ns = doc.documentElement.namespaceURI!
  const xfs = doc.getElementsByTagName('cellXfs')[0]!
  const formats = doc.getElementsByTagName('numFmts')[0]!
  const variants = new Map<string, number>()
  const derive = (base: number, format?: string, wrap = false) => {
    const key = `${base}:${format}:${wrap}`
    if (variants.has(key)) return variants.get(key)!
    const xf = xfs.children[base]!.cloneNode(true) as Element
    if (format) {
      const id = 2000 + formats.children.length
      const fmt = doc.createElementNS(ns, 'numFmt')
      fmt.setAttribute('numFmtId', String(id)); fmt.setAttribute('formatCode', format)
      formats.appendChild(fmt); formats.setAttribute('count', String(formats.children.length))
      xf.setAttribute('numFmtId', String(id)); xf.setAttribute('applyNumberFormat', '1')
    }
    if (wrap) {
      let align = xf.getElementsByTagName('alignment')[0]
      if (!align) { align = doc.createElementNS(ns, 'alignment'); xf.appendChild(align) }
      align.setAttribute('wrapText', '1'); align.setAttribute('vertical', 'center')
      xf.setAttribute('applyAlignment', '1')
    }
    const id = xfs.children.length
    xfs.appendChild(xf); xfs.setAttribute('count', String(xfs.children.length)); variants.set(key, id)
    return id
  }
  return { derive, xml: () => new XMLSerializer().serializeToString(doc) }
}

function customerSheet(data: DickieV2QuoteData, lang: 'en' | 'zh', styles: ReturnType<typeof templateStyles>) {
  const en = lang === 'en', header = data.products[0]!.mapping, layout = template.sheets[lang]
  const rows: XlsxCellInput[][] = [], merges: string[] = [], heights = new Map<number, number>()
  const pageBreaks: number[] = []
  const images: { row: number; image: DickieProductImage }[] = []
  const add = (prototype: number, values: Record<string, string | number> = {}, height?: number) => {
    const source = layout.rows[prototype - 1]!
    rows.push(source.styles.map((style, col) => ({ value: values[String.fromCharCode(65 + col)] ?? '', style })))
    heights.set(rows.length, height ?? source.height)
    return rows.length
  }
  const at = (row: number, col: number) => rows[row - 1]![col] as { value: string | number; style: number; formula?: string }
  const merge = (row: number, start: string, end: string) => merges.push(`${start}${row}:${end}${row}`)
  const dateSerial = (Date.parse(`${header.quote_date}T00:00:00Z`) - Date.UTC(1899, 11, 30)) / 86400000
  const dimensionText = (value: string, unit: string, col: number) => {
    const parts = value.split(' × ')
    const text = `${parts.join('*')}${unit}`
    return text.length > layout.cols[col]! * 1.1 && parts.length === 3
      ? `${parts[0]}*${parts[1]}*\n${parts[2]}${unit}` : text
  }
  const heading = (mold = false) => {
    // The source mold block has its own taller letterhead and spacing.
    const addHeader = (prototype: number, values: Record<string, string | number> = {}) =>
      add(prototype + (mold ? (en ? 29 : 28) : 0), values)
    let r = addHeader(1, { A: header.company === 'asia' ? '华登制品 (亞洲) 有限公司' : '华登制品 (香港) 有限公司' }); merge(r, 'A', 'K')
    r = addHeader(2, { A: header.company === 'asia' ? 'ROYAL REGENT PRODUCTS (ASIA) LIMITED' : 'ROYAL REGENT PRODUCTS (H.K.) LIMITED' }); merge(r, 'A', 'K')
    addHeader(3, { A: 'Address: Unit07-08,12/F,Greenfield Tower,Concordia Plaza,', J: 'Tel: 852- 2425 0720 Fax: 852- 2424 3407' })
    addHeader(4, { A: 'No.1 Science Museum Road,Tsim Sha Tsui, Kowloon,Hong Kong.', J: 'E-mail:' })
    addHeader(5)
    r = addHeader(6, { A: header.quotation_kind === 'estimate' ? 'ESTIMATE QUOTATION (估價)' : 'QUOTATION (報價)' }); merge(r, 'A', 'K')
    r = addHeader(7, { A: 'Client(客  戶):', C: header.client_name, J: 'Date(日期):', K: dateSerial })
    at(r, 10).style = styles.derive(at(r, 10).style, 'yyyy/m/d')
    r = addHeader(8, { A: 'Attn:', C: header.attention, J: 'Rev.:', K: header.revision })
    at(r, 10).style = styles.derive(at(r, 10).style, undefined, true)
    addHeader(9, { A: 'From:', C: header.from_name }); addHeader(10)
  }
  heading()
  const dimensionKinds = new Set(data.products.map(p => `${p.mapping.dimension_source}:${p.mapping.dimension_unit}`))
  const first = data.products[0]!.mapping
  add(11, { A: 'NO.', B: 'ITEM', C: 'Units per Carton', D: 'Carton\nCBM',
    E: dimensionKinds.size === 1 ? `${first.dimension_source === 'product' ? 'Product\n(产品尺寸)' : 'Color Box\n(彩盒尺寸)'}\n(${first.dimension_unit})` : 'Dimensions\n(尺寸)',
    F: 'Carton Size\n(外箱尺寸)\n(cm)', G: 'Production\nMOQ', H: "40'HK /YT FCL\n(40'香港/盐田柜货)", I: "20'HK /YT FCL\n(20'香港/盐田柜货)", J: 'HK/YT LCL\n(香港/盐田散货)', K: 'Image\n(图片)' })
  data.products.forEach((p, index) => {
    const m = p.mapping, firstRow = rows.length + 1
    p.offers.forEach((o, offerIndex) => {
      const offerText = [o.moq, o.label[lang], o.remark[lang]].filter(Boolean).join('\n')
      const row = add(12, { A: index + 1, B: `${m.item_number}\n${m.item_name[lang]}${m.item_note[lang] ? `\n${m.item_note[lang]}` : ''}`,
        C: `${m.inner_pack}/${p.outerPack}`, D: p.cartonCbm,
        E: `${dimensionKinds.size > 1 ? `${m.dimension_source === 'product' ? 'Product' : 'Color Box'}\n` : ''}${dimensionText(p.dimensions, m.dimension_unit, 4)}`,
        F: dimensionText(p.cartonDimensions, 'cm', 5), G: offerText, H: o.prices[0], I: o.prices[1], J: o.prices[2] },
        Math.max(70, offerText.split('\n').reduce((n, line) => n + Math.ceil(line.length / (en ? 14 : 7)), 0) * 12))
      // Some sample cells inherited a currency style from the internal sheet. Keep
      // their font/border, but explicitly type CBM and all three customer prices.
      at(row, 3).style = styles.derive(layout.rows[11]!.styles[1]!, '0.000')
      for (const c of [4, 5]) at(row, c).style = styles.derive(at(row, c).style, undefined, true)
      at(row, 6).style = styles.derive(layout.rows[11]!.styles[1]!, undefined, true)
      for (const c of [7, 8, 9]) at(row, c).style = styles.derive(at(row, c).style, '"HK$"0.0')
      if (offerIndex === 0 && p.image) images.push({ row, image: p.image })
    })
    if (p.offers.length > 1) {
      for (const col of ['A', 'B', 'C', 'D', 'E', 'F', 'K']) merges.push(`${col}${firstRow}:${col}${rows.length}`)
      for (let r = firstRow + 1; r <= rows.length; r++) for (const c of [0, 1, 2, 3, 4, 5, 10]) at(r, c).value = ''
    }
  })
  add(13); add(14, { A: 'Remark（备注）：' })
  let number = 0
  const note = (text: string, prototype = 15, numbered = true) => {
    const height = Math.max(layout.rows[prototype - 1]!.height, Math.ceil(text.length / (en ? 155 : 77)) * 15)
    const r = add(prototype, { A: numbered ? ++number : '', B: text }, height)
    merge(r, 'B', prototype === 18 ? 'C' : 'K')
    at(r, 1).style = styles.derive(at(r, 1).style, undefined, true)
    return r
  }
  data.products.forEach(p => {
    if (data.products.length > 1) note(`${p.mapping.item_number} ${p.mapping.item_name[lang]}`, 15, false)
    p.mapping.remarks.filter(r => r.zh || r.en).forEach(r => note(r[lang]))
  })
  note(DICKIE_FIXED_REMARKS[0]![lang], 18)
  note(DICKIE_FIXED_REMARKS[1]![lang], 19)
  note(DICKIE_FIXED_REMARKS[2]![lang], 20)
  note(en ? 'Plastic Quotation(HK$/LB):' : '按现如下料价报价(HK$/LB)：', 21)
  add(22, { B: en ? 'Type' : '料型', C: en ? 'Cost' : '料价', E: en ? 'Type' : '料型', F: en ? 'Cost' : '料价' })
  for (let i = 0; i < 2; i++) {
    const left = DICKIE_FIXED_MATERIALS[i * 2]!, right = DICKIE_FIXED_MATERIALS[i * 2 + 1]!
    add(23 + i, { B: left.material, C: left.price, E: right.material, F: right.price })
  }
  note(DICKIE_FIXED_REMARKS[3]![lang], 25, false)
  note(DICKIE_FIXED_REMARKS[4]![lang], 26)
  note(DICKIE_FIXED_REMARKS[5]![lang], en ? 28 : 27)
  data.products.filter(p => p.molds.length).forEach(p => {
    add(en ? 29 : 28)
    pageBreaks.push(rows.length)
    heading(true)
    const offset = en ? 1 : 0
    let r = add(39 + offset, { A: 'Project Name (產品名稱):', C: `${p.mapping.item_number} ${p.mapping.item_name[lang]}` }, 28)
    merge(r, 'C', 'K'); at(r, 2).style = styles.derive(at(r, 2).style, undefined, true)
    r = add(40 + offset, { B: 'Mold #\n模具編號', C: 'Parts (膠件)', D: 'Resin\n(膠料)', E: 'Mold Size\n(模具尺寸)', F: 'Mold Material\n(模具材料)', G: 'Cav.\n模穴數', H: 'Up\n成品數', I: 'Mold Cost\n模具價錢', J: 'Remark\n備註' }); merge(r, 'J', 'K')
    let group = ''
    const moldRows: number[] = []
    p.molds.forEach(m => {
      if (m.group[lang] && m.group[lang] !== group) {
        group = m.group[lang]; r = add(41 + offset, { B: group }); merge(r, 'B', 'K')
      }
      const remark = [m.shared[lang], m.remark[lang]].filter(Boolean).join('\n')
      r = add(41 + offset, { B: m.no, C: m.parts[lang], D: m.resin, E: m.size, F: m.material, G: m.cavities, H: m.quantity, I: m.price, J: remark },
        Math.max(29, Math.ceil(m.parts[lang].length / (en ? 22 : 11)) * 13, Math.ceil(remark.length / (en ? 36 : 18)) * 13))
      merge(r, 'J', 'K'); moldRows.push(r)
      for (let c = 1; c < 11; c++) at(r, c).style = styles.derive(at(r, c).style, c === 8 ? '"HK$"#,##0' : undefined, true)
    })
    r = add(49 + offset, { B: 'TOTAL:HK$', I: p.molds.reduce((sum, m) => sum + m.price, 0) })
    merge(r, 'B', 'H'); merge(r, 'J', 'K')
    at(r, 8).formula = `SUM(I${moldRows[0]}:I${moldRows[moldRows.length - 1]})`
    at(r, 8).style = styles.derive(at(r, 8).style, '"HK$"#,##0')
    for (const [prototype, label, value] of [
      [50 + offset, 'First shot time (试模期):', p.mapping.first_shot[lang]],
      [50 + offset, 'Finish time (交模期):', p.mapping.finish[lang]],
      [51 + offset, en ? 'Lead time basis:' : '模期起算条件:', p.mapping.lead_time_basis[lang]],
    ] as const) {
      r = add(prototype, { B: label, I: value }, Math.max(28.5, Math.ceil(value.length / (en ? 44 : 22)) * 14))
      merge(r, 'B', 'H'); merge(r, 'I', 'K'); at(r, 8).style = styles.derive(at(r, 8).style, undefined, true)
    }
  })
  const sheet: XlsxOutputSheet = { name: en ? 'Quotation' : '总表', rows, merges, cols: layout.cols }
  return { sheet, heights, images, pageBreaks }
}

/** Rebuild only the customer whitelist; never copy the internal workbook ZIP. */
export function createDickieV2Workbook(data: DickieV2QuoteData) {
  if (!data.products.length) fail('没有报客产品')
  const styles = templateStyles()
  const built = [customerSheet(data, 'en', styles), customerSheet(data, 'zh', styles)]
  const zip = unzipSync(createXlsxWorkbook(built.map(b => b.sheet)))
  const relNs = 'http://schemas.openxmlformats.org/package/2006/relationships'
  const docRelNs = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
  let contentTypes = strFromU8(zip['[Content_Types].xml']!)
  for (const ext of ['png', 'jpg']) contentTypes = contentTypes.replace('</Types>', `<Default Extension="${ext}" ContentType="image/${ext === 'jpg' ? 'jpeg' : 'png'}"/></Types>`)
  built.forEach((b, i) => {
    const path = `xl/worksheets/sheet${i + 1}.xml`
    let xml = strFromU8(zip[path]!).replace(/<row r="(\d+)"/g, (_match, n: string) => `<row r="${n}" ht="${b.heights.get(Number(n)) || 24}" customHeight="1"`)
    xml = xml.replace('</worksheet>', '<pageMargins left="0.25" right="0.25" top="0.3" bottom="0.3" header="0.15" footer="0.15"/><pageSetup paperSize="9" orientation="portrait" fitToWidth="1" fitToHeight="0"/></worksheet>')
    xml = xml.replace(/(<worksheet\b[^>]*>)/, '$1<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>')
    if (b.pageBreaks.length) xml = xml.replace('</worksheet>', `<rowBreaks count="${b.pageBreaks.length}" manualBreakCount="${b.pageBreaks.length}">${b.pageBreaks.map(r => `<brk id="${r}" min="0" max="16383" man="1"/>`).join('')}</rowBreaks></worksheet>`)
    if (b.images.length) {
      const drawing = `drawing${i + 1}`
      const anchors: string[] = [], relationships: string[] = []
      b.images.forEach(({ row, image }, j) => {
        const name = `dickie-${i + 1}-${j + 1}.${image.extension}`
        const { cx, cy } = imageExtent(image, (b.sheet.cols![10]! * 7 - 5) * 9525, b.heights.get(row)! * 12700 - 100000)
        const x = Math.round(b.sheet.cols!.slice(0, 10).reduce((sum, w) => sum + w * 7 + 5, 0) * 9525 + 50000), y = Array.from(b.heights).filter(([r]) => r < row).reduce((sum, [, h]) => sum + h * 12700, 50000)
        zip[`xl/media/${name}`] = new Uint8Array(image.bytes)
        relationships.push(`<Relationship Id="rId${j + 1}" Type="${docRelNs}/image" Target="../media/${name}"/>`)
        anchors.push(`<xdr:oneCellAnchor><xdr:from><xdr:col>10</xdr:col><xdr:colOff>50000</xdr:colOff><xdr:row>${row - 1}</xdr:row><xdr:rowOff>50000</xdr:rowOff></xdr:from><xdr:ext cx="${cx}" cy="${cy}"/><xdr:pic><xdr:nvPicPr><xdr:cNvPr id="${j + 1}" name="Product ${j + 1}"/><xdr:cNvPicPr><a:picLocks noChangeAspect="1"/></xdr:cNvPicPr></xdr:nvPicPr><xdr:blipFill><a:blip r:embed="rId${j + 1}"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill><xdr:spPr><a:xfrm><a:off x="${x}" y="${y}"/><a:ext cx="${cx}" cy="${cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr></xdr:pic><xdr:clientData/></xdr:oneCellAnchor>`)
      })
      zip[`xl/drawings/${drawing}.xml`] = strToU8(`<?xml version="1.0" encoding="UTF-8"?><xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="${docRelNs}">${anchors.join('')}</xdr:wsDr>`)
      zip[`xl/drawings/_rels/${drawing}.xml.rels`] = strToU8(`<Relationships xmlns="${relNs}">${relationships.join('')}</Relationships>`)
      zip[`xl/worksheets/_rels/sheet${i + 1}.xml.rels`] = strToU8(`<Relationships xmlns="${relNs}"><Relationship Id="rIdImage" Type="${docRelNs}/drawing" Target="../drawings/${drawing}.xml"/></Relationships>`)
      xml = xml.replace('</worksheet>', '<drawing r:id="rIdImage"/></worksheet>')
      contentTypes = contentTypes.replace('</Types>', `<Override PartName="/xl/drawings/${drawing}.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/></Types>`)
    }
    zip[path] = strToU8(xml)
  })
  zip['[Content_Types].xml'] = strToU8(contentTypes)
  zip['xl/styles.xml'] = strToU8(styles.xml())
  zip['xl/theme/theme1.xml'] = strToU8(template.themeXml)
  zip['xl/_rels/workbook.xml.rels'] = strToU8(strFromU8(zip['xl/_rels/workbook.xml.rels']!).replace('</Relationships>', `<Relationship Id="rIdTheme" Type="${docRelNs}/theme" Target="theme/theme1.xml"/></Relationships>`))
  zip['[Content_Types].xml'] = strToU8(strFromU8(zip['[Content_Types].xml']!).replace('</Types>', '<Override PartName="/xl/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/></Types>'))
  zip['xl/workbook.xml'] = strToU8(strFromU8(zip['xl/workbook.xml']!).replace('</workbook>', `<definedNames>${built.map((b, i) => `<definedName name="_xlnm.Print_Area" localSheetId="${i}">'${b.sheet.name}'!$A$1:$K$${b.sheet.rows.length}</definedName>`).join('')}</definedNames></workbook>`))
  return zipSync(zip, { level: 6 })
}

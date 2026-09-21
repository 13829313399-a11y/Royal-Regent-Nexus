// Customer-facing additions only. Costs, packing and tooling facts stay in their owning sections.
export interface DickieBilingual { zh: string; en: string }
export interface DickieAdjustment { label: string; percent: number; amount_hkd: number }
export interface DickieOffer {
  id: string
  included: boolean
  label: DickieBilingual
  moq: number
  moq_text: string
  remark: DickieBilingual
  route_40: string
  route_20: string
  route_lcl: string
  price_source: 'calculated' | 'confirmed'
  confirmed_40: number | ''
  confirmed_20: number | ''
  confirmed_lcl: number | ''
  confirmed_reference: string
  adjustments: DickieAdjustment[]
}
export interface DickieMapping {
  version: 'dickie-v2'
  company: 'hk' | 'asia'
  client_name: string
  attention: string
  from_name: string
  quote_date: string
  revision: string
  quotation_kind: 'estimate' | 'quotation'
  item_number: string
  item_name: DickieBilingual
  item_note: DickieBilingual
  inner_pack: number
  dimension_source: 'color_box' | 'product'
  dimension_unit: 'cm' | 'mm'
  customer_carton_enabled: boolean
  customer_carton_cm: { length: number; width: number; height: number }
  remarks: DickieBilingual[]
  offers: DickieOffer[]
  include_molds: boolean
  first_shot: DickieBilingual
  finish: DickieBilingual
  lead_time_basis: DickieBilingual
}
export interface DickieMoldSupplement {
  included: boolean
  customer_mold_no: string
  parts_en: string
  group: DickieBilingual
  shared_products: DickieBilingual
  size_unit: 'cm' | 'mm'
  customer_price_hkd: number | ''
  remark: DickieBilingual
}
export const DICKIE_FIXED_MATERIALS = [
  { material: 'PP', price: 4.8 }, { material: 'C-ABS', price: 8.5 },
  { material: 'ABS', price: 5.8 }, { material: 'HIPS', price: 5.1 },
] as const
export const DICKIE_FIXED_REMARKS: DickieBilingual[] = [
  { zh: '此报价不含5%贸易折扣。', en: 'This quotation excludes the 5% trade discount.' },
  { zh: '产品可通过RoHS、Non Phthalates（6P标准）、Cadmium、ASTM、EN71、EN62115、FCC、EMC等测试。', en: 'Products comply with RoHS, Non-Phthalates (6P), Cadmium, ASTM, EN71, EN62115, FCC and EMC testing requirements.' },
  { zh: '报价未含吊柜费、入仓费。', en: 'This quotation excludes CFS and THC charges.' },
  { zh: '若人民币汇率升幅超过2%，人工工资和原材料升幅超过5%，本公司将保留加价的权利。', en: 'We reserve the right to increase prices if the RMB exchange rate rises by more than 2%, or wages and raw material costs rise by more than 5%.' },
  { zh: '客户负责来板的法律责任，包括知识产权。', en: 'The customer is responsible for legal matters concerning the supplied design or sample, including intellectual property rights.' },
  { zh: '除非产品价格全数清还，本公司仍拥有产品拥有权。', en: 'Royal Regent retains ownership of the products until the product price has been paid in full.' },
]
const obj = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
const txt = (value: unknown) => String(value ?? '').trim()
const num = (value: unknown, fallback = 0) => value === '' || value == null ? fallback : Number(value)
const bilingual = (value: unknown): DickieBilingual => ({ zh: txt(obj(value).zh), en: txt(obj(value).en) })
const list = (value: unknown) => Array.isArray(value) ? value : []
export function createDickieOffer(): DickieOffer {
  return { id: globalThis.crypto.randomUUID(), included: true, label: { zh: '', en: '' }, moq: 0, moq_text: '', remark: { zh: '', en: '' }, route_40: '', route_20: '', route_lcl: '', price_source: 'calculated', confirmed_40: '', confirmed_20: '', confirmed_lcl: '', confirmed_reference: '', adjustments: [] }
}
export function createDickieMapping(): DickieMapping {
  return { version: 'dickie-v2', company: 'hk', client_name: 'Simba Dickie toys', attention: 'Sam', from_name: 'Ben / Dickie', quote_date: '', revision: '', quotation_kind: 'quotation', item_number: '', item_name: { zh: '', en: '' }, item_note: { zh: '', en: '' }, inner_pack: 0, dimension_source: 'color_box', dimension_unit: 'cm', customer_carton_enabled: false, customer_carton_cm: { length: 0, width: 0, height: 0 }, remarks: [{ zh: '', en: '' }], offers: [createDickieOffer()], include_molds: false, first_shot: { zh: '', en: '' }, finish: { zh: '', en: '' }, lead_time_basis: { zh: '', en: '' } }
}
export function normalizeDickieMapping(value: unknown): DickieMapping | undefined {
  const s = obj(value)
  if (s.version !== 'dickie-v2') return undefined
  const result = createDickieMapping()
  for (const k of ['client_name', 'attention', 'from_name', 'quote_date', 'revision', 'item_number'] as const) result[k] = txt(s[k])
  for (const k of ['item_name', 'item_note', 'first_shot', 'finish', 'lead_time_basis'] as const) result[k] = bilingual(s[k])
  result.company = s.company === 'asia' ? 'asia' : 'hk'
  result.quotation_kind = s.quotation_kind === 'estimate' ? 'estimate' : 'quotation'
  result.inner_pack = num(s.inner_pack)
  result.dimension_source = s.dimension_source === 'product' ? 'product' : 'color_box'
  result.dimension_unit = s.dimension_unit === 'mm' ? 'mm' : 'cm'
  result.customer_carton_enabled = s.customer_carton_enabled === true
  const dims = obj(s.customer_carton_cm)
  result.customer_carton_cm = { length: num(dims.length), width: num(dims.width), height: num(dims.height) }
  result.remarks = list(s.remarks).map(bilingual)
  result.include_molds = s.include_molds === true
  result.offers = list(s.offers).map(value => {
    const row = obj(value), offer = createDickieOffer()
    for (const k of ['id', 'moq_text', 'route_40', 'route_20', 'route_lcl', 'confirmed_reference'] as const) offer[k] = txt(row[k])
    offer.included = row.included !== false
    offer.moq = num(row.moq)
    offer.label = bilingual(row.label); offer.remark = bilingual(row.remark)
    offer.price_source = row.price_source === 'confirmed' ? 'confirmed' : 'calculated'
    for (const k of ['confirmed_40', 'confirmed_20', 'confirmed_lcl'] as const) offer[k] = row[k] === '' || row[k] == null ? '' : num(row[k])
    offer.adjustments = list(row.adjustments).map(a => ({ label: txt(obj(a).label), percent: num(obj(a).percent), amount_hkd: num(obj(a).amount_hkd) }))
    return offer
  })
  return result
}
export function normalizeDickieMold(value: unknown): DickieMoldSupplement {
  const row = obj(value)
  return { included: row.included === true, customer_mold_no: txt(row.customer_mold_no), parts_en: txt(row.parts_en), group: bilingual(row.group), shared_products: bilingual(row.shared_products), size_unit: row.size_unit === 'mm' ? 'mm' : 'cm', customer_price_hkd: row.customer_price_hkd == null || row.customer_price_hkd === '' ? '' : num(row.customer_price_hkd), remark: bilingual(row.remark) }
}

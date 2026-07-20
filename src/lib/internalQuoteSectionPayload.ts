import type { InternalQuoteSectionCode } from '@/types/internalQuoteDesk'

export type DisneyPurchasedSection = 'product' | 'package'
export type EngineeringMaterialCategory = 'hardware' | 'auxiliary' | 'packaging'
export type EngineeringAuxiliaryCategory = '五金' | '吸塑' | '胶袋' | '彩盒/内卡' | '电池' | '利宝' | '电镀' | '其他外购'
export interface EngineeringMaterialRow {
  item: string
  category: EngineeringMaterialCategory
  purpose: string
  specification: string
  quantity: number
  unit: string
  unit_price_rmb: number
  material: string
  surface_treatment: string
  supplier: string
  contact: string
  auxiliary_category: EngineeringAuxiliaryCategory
  tax_rate_percent: number
  remark: string
  disney_description: string
  disney_section: DisneyPurchasedSection
  disney_unit_price_usd: number
  disney_included: number
}
export interface EngineeringMoldRow {
  item: string
  mold_no: string
  chinese_name: string
  mold_base_type: string
  mold_base_material: string
  structure: string
  process: string
  material: string
  material_type: string
  color: string
  cavity: string
  quantity: number
  net_weight_g: number
  cycle_time_seconds: number
  mold_size: string
  mold_specification: string
  image_reference: string
  image_attachment_ids: string[]
  cost_rmb: number
  remark: string
  machine_code: string
  target_output: number
  source_row: number
  disney_mold_no: string
  disney_parts: string
  disney_material: string
  disney_cavities: number
  disney_parts_per_shot: number
  disney_tool_cost_usd: number
  dickie_project_name_en: string
  dickie_mold_no: string
  dickie_parts_en: string
  dickie_resin: string
  dickie_mold_size: string
  dickie_mold_material: string
  dickie_cavities: number
  dickie_parts_per_shot: number
  dickie_mold_cost_hkd: number
  dickie_remark_en: string
  caixing_tool_plan_ref: string
  caixing_mold_cost_hkd: number
  caixing_customer_mold_cost_hkd: number
}
export interface EngineeringProductionMoldCostRow { item: string; cost_rmb: number }
export interface SalesDimensions { length: number; width: number; height: number }
export type SalesPackagingCategory = 'blister' | 'color_box_inner_card' | 'leaflet_manual' | 'other_purchase'
export interface SalesPackagingMaterialRow {
  item: string
  specification: string
  category: SalesPackagingCategory
  quantity: number
  unit_price_rmb: number
  tax_rate_percent: number
  remark: string
}
export interface SalesFlatCardRow { name: string; length_in: number; width_in: number; quantity: number }
export interface SalesCartonRow { item: string; length_in: number; width_in: number; height_in: number; qty_per_carton: number; flat_cards: SalesFlatCardRow[]; disney_unit_price_usd?: number }
export type EngineeringFlatCardRow = SalesFlatCardRow
export type EngineeringCartonRow = SalesCartonRow
export interface EngineeringPayload {
  materials: EngineeringMaterialRow[]
  molds: EngineeringMoldRow[]
  mold_allocation_enabled: boolean
  production_mold_costs: EngineeringProductionMoldCostRow[]
  mold_fx_rmb_usd: number
  amortization_qty: number
  customer_mold_subsidy_usd: number
  prototype_amortization_qty: number
  prototype_total_usd: number
  testing_amortization_qty: number
  testing_total_usd: number
  cartons?: EngineeringCartonRow[]
}

export interface ElectronicComponentRow {
  item: string
  specification: string
  quantity: number
  unit_price_rmb?: number
  unit_price_hkd?: number
  tax_rate_percent: number
  remark: string
  source_currency?: string
  source_row?: number
  children: ElectronicComponentRow[]
}
export interface ElectronicPayload {
  pricing_currency?: 'RMB'
  components: ElectronicComponentRow[]
  bonding_rmb?: number
  smt_rmb?: number
  labor_rmb?: number
  testing_rmb?: number
  packaging_rmb?: number
  profit_rate_percent: number
  // 兼容历史报价；新报价统一用上面的 RMB 字段，HKD 由冻结汇率自动换算。
  bonding_hkd?: number
  smt_hkd?: number
  labor_hkd?: number
  testing_hkd?: number
  packaging_hkd?: number
  tax_credit_difference_hkd?: number
}
export interface ElectronicSummary {
  componentCostRmb: number
  deductibleInputTaxRmb: number
  preTaxCostRmb: number
  withProfitRmb: number
  taxDifferenceRmb: number
  taxPayableRmb: number
  quoteRmb: number
  quoteHkd: number
}

export interface InjectionRow {
  engineering_source_key?: string
  engineering_synced_fields?: string[]
  item: string
  mold_no: string
  material: string
  grade: string
  color: string
  net_weight_g: number
  loss_rate_percent: number
  machine_name: string
  machine_code: string
  cavity: string
  sets: number
  target_output: number
  cycle_time_seconds: number
  quantity: number
  remark: string
  disney_mold_no: string
  disney_resin_cost_usd_kg: number
  disney_cycle_time_seconds: number
  disney_labor_rate_usd_hr: number
}
export type CaixingToolProcessType = 'IN' | 'BL' | 'CP' | 'DC' | 'RC'
export interface CaixingToolPlanRow {
  ref_no: string
  process_type: CaixingToolProcessType
  tool_no: string
  tooling_cost_hkd: number
  description: string
  sku_no: string
  cavities: number
  up: number
  net_weight_g: number
  material_code: number
  material: string
  color: string
  material_cost_hkd: number
  machine_size: string
  cycle_time_seconds: number
  process_cost_hkd: number
}
export interface BlowRow {
  item: string
  daily_capacity: string
  material: string
  grade: string
  estimated_weight_g: number
  labor_hkd: number
  burr_hkd: number
  profit_multiplier: number
  quantity: number
  output_count: string
  mold_price_rmb: number
  remark: string
}
export interface MoldingPayload { injection_loss_rate_percent: number; injection_lines: InjectionRow[]; blow_lines: BlowRow[]; caixing_tool_plan_rows: CaixingToolPlanRow[] }

export type PaintingOperationCode = 'clamp' | 'pad_print' | 'spray' | 'edge' | 'paint' | 'dip' | 'wipe' | 'pp_water'
export interface PaintingOperationValue { quantity: number; unit_price_hkd: number }
export type PaintingOperations = Record<PaintingOperationCode, PaintingOperationValue>
export interface PaintingRow {
  image_reference: string
  name: string
  position: string
  operations: PaintingOperations
  remark: string
  source_row?: number
}
export interface DisneyDecorationRow { application_type: string; rate_per_op_usd: number; operations: number }
export type InternalQuoteEntryMode = 'detail' | 'quick'
export interface PaintingQuickQuote { spray_labor_hkd: number; paint_hkd: number; paint_tax_rate_percent: 13 }
export interface PaintingPayload {
  quote_mode: InternalQuoteEntryMode
  quick_quote: PaintingQuickQuote
  rows: PaintingRow[]
  disney_decorations: DisneyDecorationRow[]
}

export interface SlushRow {
  product_code: string
  item: string
  material: string
  weight_g: number
  daily_output_24h: number
  quantity: number
  unit_price_hkd: number
  remark: string
  source_row?: number
}
export interface SlushPayload { lines: SlushRow[] }

export interface SewingMaterialRow {
  item: string
  part: string
  craft: '' | '电绣'
  pieces: number
  usage: number
  unit_price_rmb: number
  markup: number
  remark: string
  supplier?: string
  source_row?: number
}
export interface SewingGroup { name: string; category: 'clothes' | 'hair'; materials: SewingMaterialRow[]; labor_rmb: number }
export interface SewingQuickQuoteRow { doll_name: string; unit_price_hkd: number }
export interface SewingPayload { quote_mode: InternalQuoteEntryMode; quick_quotes: SewingQuickQuoteRow[]; groups: SewingGroup[] }

export interface AssemblyProcessRow {
  name: string
  persons: number
  remark: string
  /** Compatibility fields for servers that still read capacity from each process row. */
  production_qty?: number
  teams?: number
  source_row?: number
}
export interface AssemblyGroup {
  name: string
  category: 'assembly' | 'packaging'
  production_qty: number
  teams: number
  processes: AssemblyProcessRow[]
}
export interface AssemblyPayload { groups: AssemblyGroup[]; labor_base_hkd: number; standard_work_hours: number }

export interface SalesTaxRow { code: string; amount_hkd: number; rate: number | '' }
export interface SalesScenario { name: string; capacity_cuft: number; freight_cost_hkd: number; carton_cuft: number; qty_per_carton: number; freight_share: number; lift_share: number; markup: number; settlement: number }
export type SalesFreightCapacityKey = 'cap_10t' | 'cap_5t' | 'cap_40' | 'cap_20'
export type SalesFreightRouteKey = 'hk40' | 'hk20' | 'yt40' | 'yt20' | 'hk10t' | 'yt10t' | 'hk5t' | 'yt5t'
export type SalesFreightCalculation = { enabled: boolean } & Record<SalesFreightCapacityKey | SalesFreightRouteKey, number>
export interface SalesFreightOption {
  key: SalesFreightRouteKey
  label: string
  feeLabel: string
  capacityKey: SalesFreightCapacityKey
  capacityCuft: number
  freightCostHkd: number
  totalCartons: number
  perPieceHkd: number
}
export const defaultSalesFreightCalculation: SalesFreightCalculation = {
  enabled: true,
  cap_10t: 1166,
  cap_5t: 750,
  cap_40: 1980,
  cap_20: 883,
  hk40: 8000,
  hk20: 7100,
  yt40: 7200,
  yt20: 6000,
  hk10t: 14900,
  yt10t: 11500,
  hk5t: 12500,
  yt5t: 11000,
}
export const salesFreightCapacityDefinitions: Array<{ key: SalesFreightCapacityKey; label: string }> = [
  { key: 'cap_10t', label: '10 吨车容量' },
  { key: 'cap_5t', label: '5 吨车容量' },
  { key: 'cap_40', label: '40 尺柜容量' },
  { key: 'cap_20', label: '20 尺柜容量' },
]
export const salesFreightRouteDefinitions: Array<{ key: SalesFreightRouteKey; label: string; feeLabel: string; capacityKey: SalesFreightCapacityKey }> = [
  { key: 'hk40', label: 'HK 40 柜', capacityKey: 'cap_40', feeLabel: 'HK 40 尺柜运费 + 吊柜费' },
  { key: 'hk20', label: 'HK 20 柜', capacityKey: 'cap_20', feeLabel: 'HK 20 尺柜运费 + 吊柜费' },
  { key: 'yt40', label: 'YT 40 柜', capacityKey: 'cap_40', feeLabel: 'YT 40 尺柜运费 + 吊柜费' },
  { key: 'yt20', label: 'YT 20 柜', capacityKey: 'cap_20', feeLabel: 'YT 20 尺柜运费 + 吊柜费' },
  { key: 'hk10t', label: 'HK 10 吨车', capacityKey: 'cap_10t', feeLabel: 'HK 10 吨车运费' },
  { key: 'yt10t', label: 'YT 10 吨车', capacityKey: 'cap_10t', feeLabel: 'YT 10 吨车运费' },
  { key: 'hk5t', label: 'HK 5 吨车', capacityKey: 'cap_5t', feeLabel: 'HK 5 吨车运费' },
  { key: 'yt5t', label: 'YT 5 吨车', capacityKey: 'cap_5t', feeLabel: 'YT 5 吨车运费' },
]
export interface BuzzBeeColorBoxTier { quote_price_hkd: number; fsc_price_hkd: number; moq: string }
export interface DisneyCustomerQuoteFields { item_number: string; quote_date: string; revision: number; minimum_order_qty: number; moq_prices_usd: { qty_3000: number; qty_5000: number; qty_10000: number }; transportation_usd: number; model_cost_usd: number; setup_charge_usd: number }
export interface DickieProductQuoteRow { line_no: number; item_text_en: string; units_per_carton: string; carton_cbm: number; color_box_size_cm: string; carton_size_cm: string; production_moq: string; price_40h_hkd: number; price_20h_hkd: number; price_lcl_hkd: number }
export interface DickieRemarkLine { line_no: number; text_en: string }
export interface DickieMaterialPrice { material: string; price_hkd_lb: number }
export interface DickieCustomerQuoteFields { client_name: string; quote_date: string; attention: string; revision: string; from_name: string; project_name_en: string; first_shot_time: string; finish_time: string; product_rows: DickieProductQuoteRow[]; remark_lines: DickieRemarkLine[]; material_prices_hkd: DickieMaterialPrice[] }
export type CaixingCustomerCostGroup = 'special' | 'electronic' | 'purchase' | 'packing' | 'carton' | 'fabric' | 'spraying' | 'tampo' | 'assembly' | 'packout' | 'rooting' | 'sewing' | 'special_offer'
export interface CaixingCustomerCostRow { group: CaixingCustomerCostGroup; tax_tag: string; category: string; description: string; base_cost_hkd: number; customer_cost_hkd: number }
export interface CaixingCustomerQuoteFields {
  product_type: 'plastic' | 'plush'
  item_number: string
  item_name: string
  quote_date: string
  carton_length_in: number
  carton_width_in: number
  carton_height_in: number
  carton_cuft: number
  carton_cbm: number
  pcs_per_carton: number
  carton_price_hkd: number
  cost_rows: CaixingCustomerCostRow[]
}
export interface CustomerQuoteFields { buzzbee: { color_box_tiers: BuzzBeeColorBoxTier[] }; disney: DisneyCustomerQuoteFields; dickie: DickieCustomerQuoteFields; caixing: CaixingCustomerQuoteFields }
export interface SalesPayload {
  paper_price_factor: number
  flat_card_price_factor?: number
  packaging_materials: SalesPackagingMaterialRow[]
  product_size_cm: SalesDimensions
  color_box_size_cm: SalesDimensions
  cartons: SalesCartonRow[]
  freight_calc: SalesFreightCalculation
  additional_tax_hkd?: number
  indonesia_freight_hkd?: number
  tax_categories?: SalesTaxRow[]
  scenarios?: SalesScenario[]
  customer_quote_fields: CustomerQuoteFields
}

export type InternalQuoteSectionPayload = SalesPayload | EngineeringPayload | ElectronicPayload | MoldingPayload | PaintingPayload | SlushPayload | SewingPayload | AssemblyPayload

const operationCodes: PaintingOperationCode[] = ['clamp', 'pad_print', 'spray', 'edge', 'paint', 'dip', 'wipe', 'pp_water']

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function rows(value: unknown) {
  return Array.isArray(value) ? value.map(objectValue) : []
}

function numberValue(value: unknown, fallback = 0) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function booleanValue(value: unknown, fallback: boolean) {
  if (typeof value === 'boolean') return value
  if (value === 'true') return true
  if (value === 'false') return false
  return fallback
}

function positiveIntegerValue(value: unknown, fallback: number) {
  const parsed = numberValue(value, fallback)
  return parsed > 0 ? Math.max(Math.round(parsed), 1) : parsed
}

function dimensions(value: unknown): SalesDimensions {
  const source = objectValue(value)
  return {
    length: numberValue(source.length),
    width: numberValue(source.width),
    height: numberValue(source.height),
  }
}

function packagingMaterialRows(value: unknown): SalesPackagingMaterialRow[] {
  return rows(value).map((row) => {
    const category = textValue(row.category)
    return {
      item: textValue(row.item),
      specification: textValue(row.specification),
      category: ['blister', 'color_box_inner_card', 'leaflet_manual'].includes(category)
        ? category as SalesPackagingCategory
        : 'other_purchase',
      quantity: numberValue(row.quantity),
      unit_price_rmb: numberValue(row.unit_price_rmb),
      tax_rate_percent: numberValue(row.tax_rate_percent),
      remark: textValue(row.remark),
    }
  })
}

function cartonRows(value: unknown): SalesCartonRow[] {
  return rows(value).map((row) => ({
    item: textValue(row.item),
    length_in: numberValue(row.length_in),
    width_in: numberValue(row.width_in),
    height_in: numberValue(row.height_in),
    qty_per_carton: numberValue(row.qty_per_carton),
    ...(Object.prototype.hasOwnProperty.call(row, 'disney_unit_price_usd')
      ? { disney_unit_price_usd: numberValue(row.disney_unit_price_usd) }
      : {}),
    flat_cards: rows(row.flat_cards).map((flat) => ({
      name: textValue(flat.name),
      length_in: numberValue(flat.length_in),
      width_in: numberValue(flat.width_in),
      quantity: numberValue(flat.quantity, 1),
    })),
  }))
}

function positivePreviewNumber(value: unknown) {
  const parsed = numberValue(value)
  return parsed > 0 ? parsed : 0
}

export function calculateCartonCuft(carton: Pick<SalesCartonRow, 'length_in' | 'width_in' | 'height_in'>) {
  const length = positivePreviewNumber(carton.length_in)
  const width = positivePreviewNumber(carton.width_in)
  const height = positivePreviewNumber(carton.height_in)
  return length && width && height ? length * width * height / 1728 : 0
}

export function calculatePackagingMaterialUnitHkd(row: Pick<SalesPackagingMaterialRow, 'unit_price_rmb'>, rmbHkdRate: unknown) {
  const rate = positivePreviewNumber(rmbHkdRate)
  const unitPrice = positivePreviewNumber(row.unit_price_rmb)
  return rate && unitPrice ? unitPrice / rate : 0
}

export function calculatePackagingMaterialAmountHkd(row: Pick<SalesPackagingMaterialRow, 'quantity' | 'unit_price_rmb'>, rmbHkdRate: unknown) {
  const quantity = positivePreviewNumber(row.quantity)
  return quantity * calculatePackagingMaterialUnitHkd(row, rmbHkdRate)
}

export function calculateEngineeringMaterialUnitHkd(row: Pick<EngineeringMaterialRow, 'unit_price_rmb'>, rmbHkdRate: unknown) {
  return calculatePackagingMaterialUnitHkd(row, rmbHkdRate)
}

export function calculateEngineeringMaterialAmountHkd(row: Pick<EngineeringMaterialRow, 'quantity' | 'unit_price_rmb'>, rmbHkdRate: unknown) {
  return calculatePackagingMaterialAmountHkd(row, rmbHkdRate)
}

export function calculateEngineeringMoldPriceHkd(row: Pick<EngineeringMoldRow, 'cost_rmb'>, rmbHkdRate: unknown) {
  const rate = positivePreviewNumber(rmbHkdRate)
  const cost = positivePreviewNumber(row.cost_rmb)
  return rate && cost ? cost / rate : 0
}

export function calculateEngineeringMoldAllocation(payload: Pick<EngineeringPayload,
  'mold_allocation_enabled' | 'production_mold_costs' | 'mold_fx_rmb_usd' | 'amortization_qty' | 'customer_mold_subsidy_usd'
  | 'prototype_amortization_qty' | 'prototype_total_usd' | 'testing_amortization_qty' | 'testing_total_usd'>) {
  const rate = positivePreviewNumber(payload.mold_fx_rmb_usd) || 7.75
  const enabled = payload.mold_allocation_enabled !== false
  const productionTotalRmb = enabled ? payload.production_mold_costs.reduce(
    (total, row) => total + positivePreviewNumber(row.cost_rmb),
    0,
  ) : 0
  const productionTotalUsd = productionTotalRmb / rate
  const moldQty = positivePreviewNumber(payload.amortization_qty)
  const prototypeQty = positivePreviewNumber(payload.prototype_amortization_qty)
  const testingQty = positivePreviewNumber(payload.testing_amortization_qty)
  const moldShareRmb = enabled && moldQty ? productionTotalRmb / moldQty : 0
  const moldShareUsd = enabled && moldQty
    ? (productionTotalUsd - positivePreviewNumber(payload.customer_mold_subsidy_usd)) / moldQty
    : 0
  const prototypeShareUsd = enabled && prototypeQty ? positivePreviewNumber(payload.prototype_total_usd) / prototypeQty : 0
  const prototypeShareRmb = prototypeShareUsd * rate
  const testingShareUsd = enabled && testingQty ? positivePreviewNumber(payload.testing_total_usd) / testingQty : 0
  const testingShareRmb = testingShareUsd * rate
  return {
    rate,
    productionTotalRmb,
    productionTotalUsd,
    moldShareRmb,
    moldShareUsd,
    prototypeShareRmb,
    prototypeShareUsd,
    testingShareRmb,
    testingShareUsd,
    totalShareRmb: moldShareRmb + prototypeShareRmb + testingShareRmb,
    totalShareUsd: moldShareUsd + prototypeShareUsd + testingShareUsd,
  }
}

export function calculateCartonPriceHkd(carton: Pick<SalesCartonRow, 'length_in' | 'width_in' | 'height_in'>, paperPriceFactor: unknown) {
  const length = positivePreviewNumber(carton.length_in)
  const width = positivePreviewNumber(carton.width_in)
  const height = positivePreviewNumber(carton.height_in)
  const factor = positivePreviewNumber(paperPriceFactor)
  return length && width && height && factor
    ? (length + width + 2) * (width + height + 1) * 2 * factor / 1000
    : 0
}

export function calculateFlatCardPriceHkd(flatCard: Pick<SalesFlatCardRow, 'length_in' | 'width_in' | 'quantity'>, flatCardPriceFactor: unknown) {
  const length = positivePreviewNumber(flatCard.length_in)
  const width = positivePreviewNumber(flatCard.width_in)
  const quantity = positivePreviewNumber(flatCard.quantity) || 1
  const factor = positivePreviewNumber(flatCardPriceFactor)
  return length && width && factor ? (length + 1) * (width + 1) * 2 * factor / 1000 * quantity : 0
}

export function calculateCartonUnitCostHkd(carton: SalesCartonRow, paperPriceFactor: unknown, flatCardPriceFactor: unknown = paperPriceFactor) {
  const quantity = positivePreviewNumber(carton.qty_per_carton)
  if (!quantity) return 0
  const flatCards = carton.flat_cards.reduce((total, flatCard) => total + calculateFlatCardPriceHkd(flatCard, flatCardPriceFactor), 0)
  return (calculateCartonPriceHkd(carton, paperPriceFactor) + flatCards) / quantity
}

export function calculateSalesFreightOptions(
  freight: SalesFreightCalculation,
  carton?: Pick<SalesCartonRow, 'length_in' | 'width_in' | 'height_in' | 'qty_per_carton'>,
): SalesFreightOption[] {
  if (!freight.enabled) return []
  const cartonCuft = carton ? calculateCartonCuft(carton) : 0
  const quantity = carton ? positivePreviewNumber(carton.qty_per_carton) : 0
  return salesFreightRouteDefinitions.map((definition) => {
    const capacityCuft = positivePreviewNumber(freight[definition.capacityKey])
    const freightCostHkd = positivePreviewNumber(freight[definition.key])
    const totalCartons = cartonCuft && capacityCuft ? Math.max(Math.round(capacityCuft / cartonCuft), 1) : 0
    const perPieceHkd = totalCartons && quantity ? freightCostHkd / totalCartons / quantity : 0
    return { ...definition, capacityCuft, freightCostHkd, totalCartons, perPieceHkd }
  })
}

export function calculateElectronicUnitPriceRmb(row: ElectronicComponentRow, rmbHkdRate: unknown) {
  if (Object.prototype.hasOwnProperty.call(row, 'unit_price_rmb')) return positivePreviewNumber(row.unit_price_rmb)
  const rate = positivePreviewNumber(rmbHkdRate)
  return positivePreviewNumber(row.unit_price_hkd) * rate
}

export function calculateElectronicUnitPriceHkd(row: ElectronicComponentRow, rmbHkdRate: unknown) {
  const rate = positivePreviewNumber(rmbHkdRate)
  return rate ? calculateElectronicUnitPriceRmb(row, rate) / rate : positivePreviewNumber(row.unit_price_hkd)
}

export function calculateElectronicAmountRmb(row: ElectronicComponentRow, rmbHkdRate: unknown) {
  return positivePreviewNumber(row.quantity) * calculateElectronicUnitPriceRmb(row, rmbHkdRate)
}

export function calculateElectronicAmountHkd(row: ElectronicComponentRow, rmbHkdRate: unknown) {
  const rate = positivePreviewNumber(rmbHkdRate)
  return rate ? calculateElectronicAmountRmb(row, rate) / rate : positivePreviewNumber(row.quantity) * positivePreviewNumber(row.unit_price_hkd)
}

function electronicRowsSummary(rows: ElectronicComponentRow[], rmbHkdRate: unknown) {
  return rows.reduce((summary, row) => {
    const amountRmb = calculateElectronicAmountRmb(row, rmbHkdRate)
    const taxRate = positivePreviewNumber(row.tax_rate_percent)
    const children = electronicRowsSummary(row.children, rmbHkdRate)
    summary.componentCostRmb += amountRmb + children.componentCostRmb
    summary.deductibleInputTaxRmb += (taxRate ? amountRmb * taxRate / (100 + taxRate) : 0) + children.deductibleInputTaxRmb
    return summary
  }, { componentCostRmb: 0, deductibleInputTaxRmb: 0 })
}

export function electronicExtraRmb(
  payload: ElectronicPayload,
  rmbField: 'bonding_rmb' | 'smt_rmb' | 'labor_rmb' | 'testing_rmb' | 'packaging_rmb',
  hkdField: 'bonding_hkd' | 'smt_hkd' | 'labor_hkd' | 'testing_hkd' | 'packaging_hkd',
  rmbHkdRate: unknown,
) {
  if (Object.prototype.hasOwnProperty.call(payload, rmbField)) return positivePreviewNumber(payload[rmbField])
  return positivePreviewNumber(payload[hkdField]) * positivePreviewNumber(rmbHkdRate)
}

export function calculateElectronicSummary(payload: ElectronicPayload, rmbHkdRate: unknown): ElectronicSummary {
  const rate = positivePreviewNumber(rmbHkdRate)
  const component = electronicRowsSummary(payload.components, rate)
  const extras = electronicExtraRmb(payload, 'bonding_rmb', 'bonding_hkd', rate)
    + electronicExtraRmb(payload, 'smt_rmb', 'smt_hkd', rate)
    + electronicExtraRmb(payload, 'labor_rmb', 'labor_hkd', rate)
    + electronicExtraRmb(payload, 'testing_rmb', 'testing_hkd', rate)
    + electronicExtraRmb(payload, 'packaging_rmb', 'packaging_hkd', rate)
  const preTaxCostRmb = component.componentCostRmb + extras
  const withProfitRmb = preTaxCostRmb * (1 + positivePreviewNumber(payload.profit_rate_percent) / 100)
  const taxDifferenceRmb = withProfitRmb * .13 - component.deductibleInputTaxRmb
  const taxPayableRmb = taxDifferenceRmb * .10
  const quoteRmb = withProfitRmb + taxDifferenceRmb + taxPayableRmb
  return {
    ...component,
    preTaxCostRmb,
    withProfitRmb,
    taxDifferenceRmb,
    taxPayableRmb,
    quoteRmb,
    quoteHkd: rate ? quoteRmb / rate : 0,
  }
}

function textValue(value: unknown) {
  return value == null ? '' : String(value)
}

function electronicRows(value: unknown): ElectronicComponentRow[] {
  return rows(value).map((row) => ({
    item: textValue(row.item),
    specification: textValue(row.specification ?? row.spec),
    quantity: numberValue(row.quantity),
    ...(Object.prototype.hasOwnProperty.call(row, 'unit_price_rmb') ? { unit_price_rmb: numberValue(row.unit_price_rmb) } : {}),
    ...(Object.prototype.hasOwnProperty.call(row, 'unit_price_hkd') ? { unit_price_hkd: numberValue(row.unit_price_hkd) } : {}),
    tax_rate_percent: numberValue(row.tax_rate_percent, 13),
    remark: textValue(row.remark ?? row.note),
    ...(Object.prototype.hasOwnProperty.call(row, 'source_currency') ? { source_currency: textValue(row.source_currency) } : {}),
    ...(Object.prototype.hasOwnProperty.call(row, 'source_row') ? { source_row: numberValue(row.source_row) } : {}),
    children: electronicRows(row.children),
  }))
}

function paintingOperations(value: unknown): PaintingOperations {
  const source = objectValue(value)
  return Object.fromEntries(operationCodes.map((code) => {
    const operation = objectValue(source[code])
    return [code, { quantity: numberValue(operation.quantity), unit_price_hkd: numberValue(operation.unit_price_hkd) }]
  })) as PaintingOperations
}

export function calculatePaintingOperationAmount(row: PaintingRow, code: PaintingOperationCode) {
  const operation = row.operations[code]
  if (!operation) return 0
  return Math.max(Number(operation.quantity) || 0, 0) * Math.max(Number(operation.unit_price_hkd) || 0, 0)
}

export function calculatePaintingRowAmount(row: PaintingRow) {
  return operationCodes.reduce((total, code) => total + calculatePaintingOperationAmount(row, code), 0)
}

export function calculatePaintingOperationTotals(payload: PaintingPayload) {
  return Object.fromEntries(operationCodes.map((code) => [
    code,
    payload.rows.reduce((total, row) => total + calculatePaintingOperationAmount(row, code), 0),
  ])) as Record<PaintingOperationCode, number>
}

export function calculatePaintingQuickPaintTaxHkd(payload: PaintingPayload) {
  return Math.max(Number(payload.quick_quote?.paint_hkd) || 0, 0) * 0.13
}

export function calculatePaintingQuickTotalHkd(payload: PaintingPayload) {
  return Math.max(Number(payload.quick_quote?.spray_labor_hkd) || 0, 0)
    + Math.max(Number(payload.quick_quote?.paint_hkd) || 0, 0)
    + calculatePaintingQuickPaintTaxHkd(payload)
}

export function calculatePaintingTotalHkd(payload: PaintingPayload) {
  if (payload.quote_mode === 'quick') return calculatePaintingQuickTotalHkd(payload)
  return payload.rows.reduce((total, row) => total + calculatePaintingRowAmount(row), 0)
}

export function calculateSlushRowAmount(row: SlushRow) {
  return Math.max(Number(row.quantity) || 0, 0) * Math.max(Number(row.unit_price_hkd) || 0, 0)
}

export function calculateSlushTotalHkd(payload: SlushPayload) {
  return payload.lines.reduce((total, row) => total + calculateSlushRowAmount(row), 0)
}

export function calculateSlushTotalRmb(payload: SlushPayload, rmbHkdRate: unknown) {
  return calculateSlushTotalHkd(payload) * positivePreviewNumber(rmbHkdRate)
}

export function calculateSewingBasePriceRmb(row: SewingMaterialRow) {
  return Math.max(Number(row.usage) || 0, 0) * Math.max(Number(row.unit_price_rmb) || 0, 0)
}

export function calculateSewingRowTotalRmb(row: SewingMaterialRow) {
  const markup = Math.max(Number(row.markup) || 0, 0) || 1
  return calculateSewingBasePriceRmb(row) * markup
}

export function sewingGroupHasLaborLine(group: SewingGroup) {
  return group.materials.some((row) => `${row.item}${row.part}`.includes('人工'))
}

export function calculateSewingGroupTotalRmb(group: SewingGroup) {
  const materialTotal = group.materials.reduce((total, row) => total + calculateSewingRowTotalRmb(row), 0)
  return materialTotal + (sewingGroupHasLaborLine(group) ? 0 : Math.max(Number(group.labor_rmb) || 0, 0))
}

export function calculateSewingTotalRmb(payload: SewingPayload) {
  return payload.groups.reduce((total, group) => total + calculateSewingGroupTotalRmb(group), 0)
}

export function calculateSewingQuickTotalHkd(payload: SewingPayload) {
  return payload.quick_quotes.reduce((total, row) => total + Math.max(Number(row.unit_price_hkd) || 0, 0), 0)
}

export function calculateSewingTotalHkd(payload: SewingPayload, rmbHkdRate: unknown) {
  if (payload.quote_mode === 'quick') return calculateSewingQuickTotalHkd(payload)
  const rate = positivePreviewNumber(rmbHkdRate)
  return rate ? calculateSewingTotalRmb(payload) / rate : 0
}

export function calculateAssemblyGroupPeople(group: AssemblyGroup) {
  return group.processes.reduce((total, row) => total + positivePreviewNumber(row.persons), 0)
}

export function calculateAssemblyGroupLaborHkd(group: AssemblyGroup, laborBaseHkd: unknown) {
  const productionQty = positivePreviewNumber(group.production_qty)
  if (!productionQty) return 0
  return positivePreviewNumber(laborBaseHkd)
    * calculateAssemblyGroupPeople(group)
    * positivePreviewNumber(group.teams)
    / productionQty
}

export function calculateAssemblyCategoryLaborHkd(payload: AssemblyPayload, category: AssemblyGroup['category']) {
  return payload.groups
    .filter((group) => group.category === category)
    .reduce((total, group) => total + calculateAssemblyGroupLaborHkd(group, payload.labor_base_hkd), 0)
}

export function normalizeInternalQuotePayload(code: InternalQuoteSectionCode, value: Record<string, unknown>): Record<string, unknown> {
  const source = objectValue(value)
  if (code === 'engineering') {
    const hasLegacyCartons = Object.prototype.hasOwnProperty.call(source, 'cartons')
    const normalizedMolds: EngineeringMoldRow[] = rows(source.molds).map((row) => ({
      item: textValue(row.item ?? row.name), mold_no: textValue(row.mold_no), chinese_name: textValue(row.chinese_name), mold_base_type: textValue(row.mold_base_type ?? row.mold_type),
      mold_base_material: textValue(row.mold_base_material), structure: textValue(row.structure), process: textValue(row.process), material: textValue(row.material), material_type: textValue(row.material_type), color: textValue(row.color), cavity: textValue(row.cavity),
      quantity: numberValue(row.quantity ?? row.sets, 1), net_weight_g: numberValue(row.net_weight_g ?? row.weight_g),
      cycle_time_seconds: numberValue(row.cycle_time_seconds ?? row.cycle_sec), mold_size: textValue(row.mold_size), mold_specification: textValue(row.mold_specification),
      image_reference: textValue(row.image_reference), image_attachment_ids: Array.isArray(row.image_attachment_ids) ? row.image_attachment_ids.map(textValue).filter(Boolean) : [], cost_rmb: numberValue(row.cost_rmb ?? row.price_rmb), remark: textValue(row.remark ?? row.note),
      machine_code: textValue(row.machine_code), target_output: numberValue(row.target_output), source_row: numberValue(row.source_row),
      disney_mold_no: textValue(row.disney_mold_no), disney_parts: textValue(row.disney_parts), disney_material: textValue(row.disney_material), disney_cavities: numberValue(row.disney_cavities), disney_parts_per_shot: numberValue(row.disney_parts_per_shot), disney_tool_cost_usd: numberValue(row.disney_tool_cost_usd),
      dickie_project_name_en: textValue(row.dickie_project_name_en), dickie_mold_no: textValue(row.dickie_mold_no), dickie_parts_en: textValue(row.dickie_parts_en), dickie_resin: textValue(row.dickie_resin), dickie_mold_size: textValue(row.dickie_mold_size), dickie_mold_material: textValue(row.dickie_mold_material), dickie_cavities: numberValue(row.dickie_cavities), dickie_parts_per_shot: numberValue(row.dickie_parts_per_shot), dickie_mold_cost_hkd: numberValue(row.dickie_mold_cost_hkd), dickie_remark_en: textValue(row.dickie_remark_en),
      caixing_tool_plan_ref: textValue(row.caixing_tool_plan_ref), caixing_mold_cost_hkd: numberValue(row.caixing_mold_cost_hkd), caixing_customer_mold_cost_hkd: numberValue(row.caixing_customer_mold_cost_hkd),
    }))
    const hasProductionMoldCosts = Array.isArray(source.production_mold_costs)
    const legacyMoldTotalRmb = normalizedMolds.reduce((total, row) => total + row.cost_rmb, 0)
    const productionMoldCosts: EngineeringProductionMoldCostRow[] = hasProductionMoldCosts
      ? rows(source.production_mold_costs).map((row) => ({ item: textValue(row.item ?? row.name), cost_rmb: numberValue(row.cost_rmb ?? row.price_rmb) }))
      : [
          { item: '模具费用', cost_rmb: legacyMoldTotalRmb },
          { item: '超声模费用', cost_rmb: 0 },
          { item: '喷油模具', cost_rmb: 0 },
        ]
    return {
      materials: rows(source.materials).map((row) => {
        const category = ['hardware', 'packaging'].includes(textValue(row.category)) ? textValue(row.category) : 'auxiliary'
        const auxiliaryCategory = category === 'hardware'
          ? '五金'
          : ['吸塑', '胶袋', '彩盒/内卡', '电池', '利宝', '电镀'].includes(textValue(row.auxiliary_category))
            ? textValue(row.auxiliary_category)
            : '其他外购'
        return {
          item: textValue(row.item), category, purpose: textValue(row.purpose), specification: textValue(row.specification ?? row.spec),
          quantity: numberValue(row.quantity ?? row.qty), unit: textValue(row.unit), unit_price_rmb: numberValue(row.unit_price_rmb),
          material: textValue(row.material), surface_treatment: textValue(row.surface_treatment), supplier: textValue(row.supplier), contact: textValue(row.contact),
          auxiliary_category: auxiliaryCategory, tax_rate_percent: category === 'hardware' ? 13 : numberValue(row.tax_rate_percent ?? row.tax_pct), remark: textValue(row.remark ?? row.note),
          disney_description: textValue(row.disney_description), disney_section: textValue(row.disney_section) === 'package' ? 'package' : 'product', disney_unit_price_usd: numberValue(row.disney_unit_price_usd), disney_included: numberValue(row.disney_included, 1),
        }
      }),
      molds: normalizedMolds,
      mold_allocation_enabled: booleanValue(source.mold_allocation_enabled, true),
      production_mold_costs: productionMoldCosts,
      mold_fx_rmb_usd: numberValue(source.mold_fx_rmb_usd, 7.75),
      amortization_qty: numberValue(source.amortization_qty, 20000),
      customer_mold_subsidy_usd: numberValue(source.customer_mold_subsidy_usd),
      prototype_amortization_qty: numberValue(source.prototype_amortization_qty, 50000),
      prototype_total_usd: numberValue(source.prototype_total_usd),
      testing_amortization_qty: numberValue(source.testing_amortization_qty, 2000),
      testing_total_usd: numberValue(source.testing_total_usd),
      ...(hasLegacyCartons ? { cartons: cartonRows(source.cartons) } : {}),
    }
  }
  if (code === 'electronic') {
    const usesRmbContract = source.pricing_currency === 'RMB'
      || ['bonding_rmb', 'smt_rmb', 'labor_rmb', 'testing_rmb', 'packaging_rmb'].some((key) => Object.prototype.hasOwnProperty.call(source, key))
      || rows(source.components).some((row) => Object.prototype.hasOwnProperty.call(row, 'unit_price_rmb'))
      || !Object.keys(source).length
    return {
      components: electronicRows(source.components),
      ...(usesRmbContract
        ? {
            pricing_currency: 'RMB',
            bonding_rmb: numberValue(source.bonding_rmb), smt_rmb: numberValue(source.smt_rmb), labor_rmb: numberValue(source.labor_rmb),
            testing_rmb: numberValue(source.testing_rmb), packaging_rmb: numberValue(source.packaging_rmb),
          }
        : {
            bonding_hkd: numberValue(source.bonding_hkd), smt_hkd: numberValue(source.smt_hkd), labor_hkd: numberValue(source.labor_hkd),
            testing_hkd: numberValue(source.testing_hkd), packaging_hkd: numberValue(source.packaging_hkd),
            tax_credit_difference_hkd: numberValue(source.tax_credit_difference_hkd),
          }),
      profit_rate_percent: numberValue(source.profit_rate_percent, 10),
    }
  }
  if (code === 'molding') {
    const injectionLossRate = numberValue(source.injection_loss_rate_percent, 3)
    return {
      injection_loss_rate_percent: injectionLossRate,
      injection_lines: rows(source.injection_lines).map((row) => ({
        engineering_source_key: textValue(row.engineering_source_key),
        engineering_synced_fields: Array.isArray(row.engineering_synced_fields)
          ? row.engineering_synced_fields.filter((field): field is string => typeof field === 'string')
          : [],
        item: textValue(row.item ?? row.name), mold_no: textValue(row.mold_no), material: textValue(row.material), grade: textValue(row.grade ?? row.material_grade), color: textValue(row.color),
        net_weight_g: numberValue(row.net_weight_g ?? row.weight_g), loss_rate_percent: numberValue(row.loss_rate_percent, injectionLossRate),
        machine_name: textValue(row.machine_name ?? row.machine), machine_code: textValue(row.machine_code ?? row.machine_model), cavity: textValue(row.cavity),
        sets: numberValue(row.sets, 1), target_output: numberValue(row.target_output ?? row.target), cycle_time_seconds: numberValue(row.cycle_time_seconds ?? row.cycle_sec),
        quantity: numberValue(row.quantity, 1), remark: textValue(row.remark ?? row.note),
        disney_mold_no: textValue(row.disney_mold_no), disney_resin_cost_usd_kg: numberValue(row.disney_resin_cost_usd_kg), disney_cycle_time_seconds: numberValue(row.disney_cycle_time_seconds), disney_labor_rate_usd_hr: numberValue(row.disney_labor_rate_usd_hr),
      })),
      blow_lines: rows(source.blow_lines).map((row) => ({
        item: textValue(row.item ?? row.name), daily_capacity: textValue(row.daily_capacity ?? row.capacity), material: textValue(row.material), grade: textValue(row.grade),
        estimated_weight_g: numberValue(row.estimated_weight_g ?? row.weight_g), labor_hkd: numberValue(row.labor_hkd ?? row.blow_labor), burr_hkd: numberValue(row.burr_hkd ?? row.flash),
        profit_multiplier: numberValue(row.profit_multiplier ?? row.profit_x, 1.05), quantity: numberValue(row.quantity, 1),
        output_count: textValue(row.output_count ?? row.cavity_note), mold_price_rmb: numberValue(row.mold_price_rmb ?? row.mold_price_note), remark: textValue(row.remark ?? row.note),
      })),
      caixing_tool_plan_rows: rows(source.caixing_tool_plan_rows).map((row) => ({
        ref_no: textValue(row.ref_no), process_type: ['BL', 'CP', 'DC', 'RC'].includes(textValue(row.process_type)) ? textValue(row.process_type) : 'IN', tool_no: textValue(row.tool_no), tooling_cost_hkd: numberValue(row.tooling_cost_hkd), description: textValue(row.description), sku_no: textValue(row.sku_no), cavities: numberValue(row.cavities), up: numberValue(row.up), net_weight_g: numberValue(row.net_weight_g), material_code: numberValue(row.material_code), material: textValue(row.material), color: textValue(row.color), material_cost_hkd: numberValue(row.material_cost_hkd), machine_size: textValue(row.machine_size), cycle_time_seconds: numberValue(row.cycle_time_seconds), process_cost_hkd: numberValue(row.process_cost_hkd),
      })),
    }
  }
  if (code === 'painting') return {
    quote_mode: source.quote_mode === 'quick' ? 'quick' : 'detail',
    quick_quote: {
      spray_labor_hkd: numberValue(objectValue(source.quick_quote).spray_labor_hkd),
      paint_hkd: numberValue(objectValue(source.quick_quote).paint_hkd),
      paint_tax_rate_percent: 13,
    },
    rows: rows(source.rows).map((row) => ({
      image_reference: textValue(row.image_reference ?? row.image),
      name: textValue(row.name ?? row.item),
      position: textValue(row.position),
      operations: paintingOperations(row.operations),
      remark: textValue(row.remark ?? row.note),
      ...(Object.prototype.hasOwnProperty.call(row, 'source_row') ? { source_row: numberValue(row.source_row) } : {}),
    })),
    disney_decorations: rows(source.disney_decorations).map((row) => ({ application_type: textValue(row.application_type), rate_per_op_usd: numberValue(row.rate_per_op_usd), operations: numberValue(row.operations) })),
  }
  if (code === 'slush') return {
    lines: rows(source.lines).map((row) => ({
      product_code: textValue(row.product_code ?? row.product_no),
      item: textValue(row.item ?? row.name),
      material: textValue(row.material),
      weight_g: numberValue(row.weight_g ?? row.net_weight_g),
      daily_output_24h: numberValue(row.daily_output_24h ?? row.daily_output),
      quantity: numberValue(row.quantity ?? row.usage),
      unit_price_hkd: numberValue(row.unit_price_hkd),
      remark: textValue(row.remark ?? row.note),
      ...(Object.prototype.hasOwnProperty.call(row, 'source_row') ? { source_row: numberValue(row.source_row) } : {}),
    })),
  }
  if (code === 'sewing') {
    return {
      quote_mode: source.quote_mode === 'quick' ? 'quick' : 'detail',
      quick_quotes: rows(source.quick_quotes).map((row) => ({
        doll_name: textValue(row.doll_name ?? row.name),
        unit_price_hkd: numberValue(row.unit_price_hkd ?? row.price_hkd),
      })),
      groups: rows(source.groups).map((group) => ({
        name: textValue(group.name),
        category: ['hair', '车发'].includes(textValue(group.category)) ? 'hair' : 'clothes',
        labor_rmb: numberValue(group.labor_rmb ?? group.labor_amount),
        materials: rows(group.materials ?? group.items).map((row) => ({
          item: textValue(row.item ?? row.fabric ?? row.material),
          part: textValue(row.part),
          craft: textValue(row.craft) === '电绣' ? '电绣' : '',
          pieces: numberValue(row.pieces),
          usage: numberValue(row.usage ?? row.qty),
          unit_price_rmb: numberValue(row.unit_price_rmb ?? row.mat_price ?? row.unit_price),
          markup: numberValue(row.markup, 1),
          remark: textValue(row.remark ?? row.note),
          ...(Object.prototype.hasOwnProperty.call(row, 'supplier') ? { supplier: textValue(row.supplier) } : {}),
          ...(Object.prototype.hasOwnProperty.call(row, 'source_row') ? { source_row: numberValue(row.source_row) } : {}),
        })),
      })),
    }
  }
  if (code === 'assembly') {
    return {
      labor_base_hkd: numberValue(source.labor_base_hkd, 260),
      standard_work_hours: numberValue(source.standard_work_hours, 11),
      groups: rows(source.groups).map((group) => {
        const processes = rows(group.processes)
        const legacyReference = processes.find((row) => numberValue(row.production_qty) > 0 || numberValue(row.teams) > 0)
        const productionQty = numberValue(group.production_qty ?? legacyReference?.production_qty)
        const teams = numberValue(group.teams ?? legacyReference?.teams, 1)
        return {
          name: textValue(group.name),
          category: textValue(group.category) === 'packaging' ? 'packaging' : 'assembly',
          production_qty: productionQty,
          teams,
          processes: processes.map((row) => ({
            name: textValue(row.name),
            persons: numberValue(row.persons),
            remark: textValue(row.remark ?? row.note),
            // The current form owns these values at product-group level. Keep a
            // synchronized copy so a backend process that has not yet restarted
            // after the group-level migration does not incorrectly validate them as 0.
            production_qty: productionQty,
            teams,
            ...(Object.prototype.hasOwnProperty.call(row, 'source_row') ? { source_row: numberValue(row.source_row) } : {}),
          })),
        }
      }),
    }
  }
  const hasLegacySalesCostFields = ['additional_tax_hkd', 'indonesia_freight_hkd', 'tax_categories', 'scenarios']
    .some((key) => Object.prototype.hasOwnProperty.call(source, key))
  const paperPriceFactor = numberValue(source.paper_price_factor, 2.75)
  const hasFlatCardPriceFactor = Object.prototype.hasOwnProperty.call(source, 'flat_card_price_factor')
    && source.flat_card_price_factor !== ''
    && source.flat_card_price_factor != null
  const freightSource = objectValue(source.freight_calc)
  return {
    paper_price_factor: paperPriceFactor,
    ...(hasFlatCardPriceFactor ? { flat_card_price_factor: numberValue(source.flat_card_price_factor, paperPriceFactor) } : {}),
    packaging_materials: packagingMaterialRows(source.packaging_materials),
    product_size_cm: dimensions(source.product_size_cm),
    color_box_size_cm: dimensions(source.color_box_size_cm),
    cartons: cartonRows(source.cartons),
    freight_calc: {
      enabled: booleanValue(freightSource.enabled, true),
      ...Object.fromEntries(salesFreightCapacityDefinitions
        .map(({ key }) => [key, positiveIntegerValue(freightSource[key], defaultSalesFreightCalculation[key])])),
      ...Object.fromEntries(salesFreightRouteDefinitions
        .map(({ key }) => [key, numberValue(freightSource[key], defaultSalesFreightCalculation[key])])),
    } as SalesFreightCalculation,
    ...(hasLegacySalesCostFields ? {
      additional_tax_hkd: numberValue(source.additional_tax_hkd),
      indonesia_freight_hkd: numberValue(source.indonesia_freight_hkd),
      tax_categories: rows(source.tax_categories).map((row) => ({ code: textValue(row.code), amount_hkd: numberValue(row.amount_hkd), rate: row.rate === '' || row.rate == null ? '' : numberValue(row.rate) })),
      scenarios: rows(source.scenarios).map((row) => ({ name: textValue(row.name), capacity_cuft: numberValue(row.capacity_cuft), freight_cost_hkd: numberValue(row.freight_cost_hkd), carton_cuft: numberValue(row.carton_cuft), qty_per_carton: numberValue(row.qty_per_carton), freight_share: numberValue(row.freight_share, .48), lift_share: numberValue(row.lift_share, .52), markup: numberValue(row.markup, 1.2), settlement: numberValue(row.settlement, .98) })),
    } : {}),
    customer_quote_fields: {
      buzzbee: {
        color_box_tiers: rows(objectValue(objectValue(source.customer_quote_fields).buzzbee).color_box_tiers)
          .slice(0, 2)
          .map((row) => ({ quote_price_hkd: numberValue(row.quote_price_hkd), fsc_price_hkd: numberValue(row.fsc_price_hkd), moq: textValue(row.moq) })),
      },
      disney: {
        item_number: textValue(objectValue(objectValue(source.customer_quote_fields).disney).item_number),
        quote_date: textValue(objectValue(objectValue(source.customer_quote_fields).disney).quote_date),
        revision: numberValue(objectValue(objectValue(source.customer_quote_fields).disney).revision),
        minimum_order_qty: numberValue(objectValue(objectValue(source.customer_quote_fields).disney).minimum_order_qty, 3000),
        moq_prices_usd: {
          qty_3000: numberValue(objectValue(objectValue(objectValue(source.customer_quote_fields).disney).moq_prices_usd).qty_3000),
          qty_5000: numberValue(objectValue(objectValue(objectValue(source.customer_quote_fields).disney).moq_prices_usd).qty_5000),
          qty_10000: numberValue(objectValue(objectValue(objectValue(source.customer_quote_fields).disney).moq_prices_usd).qty_10000),
        },
        transportation_usd: numberValue(objectValue(objectValue(source.customer_quote_fields).disney).transportation_usd),
        model_cost_usd: numberValue(objectValue(objectValue(source.customer_quote_fields).disney).model_cost_usd),
        setup_charge_usd: numberValue(objectValue(objectValue(source.customer_quote_fields).disney).setup_charge_usd),
      },
      dickie: {
        client_name: textValue(objectValue(objectValue(source.customer_quote_fields).dickie).client_name),
        quote_date: textValue(objectValue(objectValue(source.customer_quote_fields).dickie).quote_date),
        attention: textValue(objectValue(objectValue(source.customer_quote_fields).dickie).attention),
        revision: textValue(objectValue(objectValue(source.customer_quote_fields).dickie).revision),
        from_name: textValue(objectValue(objectValue(source.customer_quote_fields).dickie).from_name),
        project_name_en: textValue(objectValue(objectValue(source.customer_quote_fields).dickie).project_name_en),
        first_shot_time: textValue(objectValue(objectValue(source.customer_quote_fields).dickie).first_shot_time),
        finish_time: textValue(objectValue(objectValue(source.customer_quote_fields).dickie).finish_time),
        product_rows: rows(objectValue(objectValue(source.customer_quote_fields).dickie).product_rows)
          .slice(0, 8)
          .map((row) => ({ line_no: numberValue(row.line_no), item_text_en: textValue(row.item_text_en), units_per_carton: textValue(row.units_per_carton), carton_cbm: numberValue(row.carton_cbm), color_box_size_cm: textValue(row.color_box_size_cm), carton_size_cm: textValue(row.carton_size_cm), production_moq: textValue(row.production_moq), price_40h_hkd: numberValue(row.price_40h_hkd), price_20h_hkd: numberValue(row.price_20h_hkd), price_lcl_hkd: numberValue(row.price_lcl_hkd) })),
        remark_lines: rows(objectValue(objectValue(source.customer_quote_fields).dickie).remark_lines)
          .slice(0, 12)
          .map((row) => ({ line_no: numberValue(row.line_no), text_en: textValue(row.text_en) })),
        material_prices_hkd: rows(objectValue(objectValue(source.customer_quote_fields).dickie).material_prices_hkd)
          .slice(0, 4)
          .map((row) => ({ material: textValue(row.material), price_hkd_lb: numberValue(row.price_hkd_lb) })),
      },
      caixing: {
        product_type: textValue(objectValue(objectValue(source.customer_quote_fields).caixing).product_type) === 'plush' ? 'plush' : 'plastic',
        item_number: textValue(objectValue(objectValue(source.customer_quote_fields).caixing).item_number),
        item_name: textValue(objectValue(objectValue(source.customer_quote_fields).caixing).item_name),
        quote_date: textValue(objectValue(objectValue(source.customer_quote_fields).caixing).quote_date),
        carton_length_in: numberValue(objectValue(objectValue(source.customer_quote_fields).caixing).carton_length_in),
        carton_width_in: numberValue(objectValue(objectValue(source.customer_quote_fields).caixing).carton_width_in),
        carton_height_in: numberValue(objectValue(objectValue(source.customer_quote_fields).caixing).carton_height_in),
        carton_cuft: numberValue(objectValue(objectValue(source.customer_quote_fields).caixing).carton_cuft),
        carton_cbm: numberValue(objectValue(objectValue(source.customer_quote_fields).caixing).carton_cbm),
        pcs_per_carton: numberValue(objectValue(objectValue(source.customer_quote_fields).caixing).pcs_per_carton),
        carton_price_hkd: numberValue(objectValue(objectValue(source.customer_quote_fields).caixing).carton_price_hkd),
        cost_rows: rows(objectValue(objectValue(source.customer_quote_fields).caixing).cost_rows).map((row) => ({
          group: ['special', 'electronic', 'purchase', 'packing', 'carton', 'fabric', 'spraying', 'tampo', 'assembly', 'packout', 'rooting', 'sewing', 'special_offer'].includes(textValue(row.group)) ? textValue(row.group) : 'purchase',
          tax_tag: textValue(row.tax_tag), category: textValue(row.category), description: textValue(row.description), base_cost_hkd: numberValue(row.base_cost_hkd), customer_cost_hkd: numberValue(row.customer_cost_hkd),
        })),
      },
    },
  }
}

export function cloneInternalQuotePayload(code: InternalQuoteSectionCode, value: Record<string, unknown>) {
  // Vue form models are deeply reactive proxies, which structuredClone cannot
  // clone. Normalization already rebuilds every supported payload branch as
  // plain JSON-compatible objects, so it is also the safe cloning boundary.
  return normalizeInternalQuotePayload(code, value)
}

export const paintingOperationLabels: Record<PaintingOperationCode, string> = {
  clamp: '夹模', pad_print: '移印', spray: '散枪', edge: '边模', paint: '油色', dip: '浸油', wipe: '抹油', pp_water: '擦PP水',
}

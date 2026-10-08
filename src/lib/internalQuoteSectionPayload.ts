import type { InternalQuoteSectionCode } from '@/types/internalQuoteDesk'
import { normalizeDickieMapping, normalizeDickieMold, type DickieMapping, type DickieMoldSupplement } from './dickieQuote'

export type DisneyPurchasedSection = 'product' | 'package'
export type EngineeringMaterialCategory = 'hardware' | 'auxiliary' | 'packaging'
export type EngineeringAuxiliaryCategory = '五金' | '吸塑' | '胶袋' | '彩盒/内卡' | '电池' | '利宝' | '电镀' | '其他外购'
export type UnitPriceSourceCurrency = 'RMB' | 'HKD'
export interface QuotePricingMetadata {
  pricing_component_id?: string
  markup_override?: number
}
export interface SalesPricingComponent {
  id: string
  name: string
  markup_x?: number
}
export const salesPackagingPricingGroupId = 'sales-packaging'
export const salesPackagingPricingGroupName = '业务部包装'
export interface EngineeringMaterialRow extends QuotePricingMetadata {
  item: string
  category: EngineeringMaterialCategory
  purpose: string
  specification: string
  quantity: number
  unit: string
  unit_price_rmb: number
  unit_price_hkd?: number
  unit_price_source_currency?: UnitPriceSourceCurrency
  loss_rate?: number
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
export interface EngineeringMoldPartRow {
  name: string
  color: string
  process: string
  process_unit_price_hkd: number
  unit_net_weight_g: number
  output_count: number
  quantity: number
}
export interface EngineeringMoldRow extends QuotePricingMetadata {
  dickie_export?: DickieMoldSupplement
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
  parts: EngineeringMoldPartRow[]
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
export interface SalesPackagingMaterialRow extends QuotePricingMetadata {
  item: string
  specification: string
  category: SalesPackagingCategory
  quantity: number
  unit_price_rmb: number
  unit_price_hkd?: number
  unit_price_source_currency?: UnitPriceSourceCurrency
  loss_rate?: number
  tax_rate_percent: number
  remark: string
  disney_description: string
  disney_unit_price_usd: number
  disney_included: number
}
export type SalesDimensionUnit = 'cm' | 'inch'
export interface SalesFlatCardRow { name: string; length_in: number; width_in: number; quantity: number }
export interface SalesCartonRow extends QuotePricingMetadata { item: string; size_unit?: SalesDimensionUnit; length_in: number; width_in: number; height_in: number; qty_per_carton: number; flat_cards: SalesFlatCardRow[]; disney_unit_price_usd?: number }
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

export type InternalQuoteEntryMode = 'detail' | 'quick'

export interface ElectronicQuickQuoteRow extends QuotePricingMetadata {
  item: string
  unit_price_rmb: number
  tax_rate_percent: number
  remark: string
}

export interface ElectronicComponentRow extends QuotePricingMetadata {
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
  quote_mode: InternalQuoteEntryMode
  quick_quotes: ElectronicQuickQuoteRow[]
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
export interface ElectronicQuoteGroup extends ElectronicPayload, Record<string, unknown> {
  id: string
  name: string
  import_batch_id?: string
  source_sha256?: string
}
export interface ElectronicQuoteGroupsPayload extends Record<string, unknown> {
  quote_groups: ElectronicQuoteGroup[]
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

export interface InjectionRow extends Omit<QuotePricingMetadata, 'markup_override'> {
  buzzbee_material?: string
  engineering_source_key?: string
  engineering_synced_fields?: string[]
  engineering_sync_disabled?: boolean
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
  material_price_hkd_lb: number | null
  machine_size: string
  cycle_time_seconds: number
  process_cost_hkd: number
  machine_daily_hkd: number | null
}
export interface BlowRow extends Omit<QuotePricingMetadata, 'markup_override'> {
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

export type PaintingOperationCode = 'clamp' | 'pad_print' | 'uv' | 'spray' | 'edge' | 'paint' | 'dip' | 'wipe' | 'pp_water'
export interface PaintingOperationValue { quantity: number; unit_price_hkd: number }
export type PaintingOperations = Record<PaintingOperationCode, PaintingOperationValue>
export interface PaintingRow extends QuotePricingMetadata {
  cost_allocation?: 'direct' | 'split'
  paint_cost_hkd?: number | null
  labor_cost_hkd?: number | null
  image_reference: string
  name: string
  position: string
  operations: PaintingOperations
  remark: string
  source_row?: number
}
export interface DisneyDecorationRow { application_type: string; rate_per_op_usd: number; operations: number }
export interface PaintingQuickQuote extends QuotePricingMetadata { spray_labor_hkd: number; paint_hkd: number; paint_tax_rate_percent: 13 }
export interface PaintingPayload {
  quote_mode: InternalQuoteEntryMode
  quick_quote: PaintingQuickQuote
  rows: PaintingRow[]
  disney_decorations: DisneyDecorationRow[]
}

export interface SlushRow extends QuotePricingMetadata {
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

export interface HairRow extends QuotePricingMetadata {
  name: string
  craft: string
  weight_g: number
  unit_price_hkd: number
  unit: string
  remark: string
}
export interface HairPayload { lines: HairRow[] }

export interface SewingMaterialRow {
  item: string
  part: string
  craft: '' | '电绣' | '丝印'
  pieces: number
  supplier?: string
  fabric_moq_y?: number
  below_moq_fee_rmb?: number
  usage: number
  unit_price_rmb: number
  exchange_rate?: number
  markup: number
  remark: string
  source_row?: number
}
export interface SewingGroup extends QuotePricingMetadata { name: string; category: 'clothes' | 'hair'; materials: SewingMaterialRow[]; labor_rmb: number }
export interface SewingQuickQuoteRow extends QuotePricingMetadata { doll_name: string; unit_price_hkd: number }
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
export interface AssemblyGroup extends QuotePricingMetadata {
  name: string
  category: 'assembly' | 'packaging'
  production_qty: number
  teams: number
  /** Manually entered only while the group has no process rows. */
  total_persons: number | null
  processes: AssemblyProcessRow[]
}
export interface AssemblyPayload { groups: AssemblyGroup[]; labor_base_hkd: number; standard_work_hours: number }

export interface SalesTaxRow { code: string; amount_hkd: number; rate: number | '' }
export interface SalesScenario { name: string; capacity_cuft: number; freight_cost_hkd: number; carton_cuft: number; qty_per_carton: number; freight_share: number; lift_share: number; markup: number; settlement: number }
export type SalesFreightCapacityKey = 'cap_10t' | 'cap_5t' | 'cap_40' | 'cap_20'
export type LegacySalesFreightRouteKey = 'hk40' | 'hk20' | 'yt40' | 'yt20' | 'hk10t' | 'yt10t' | 'hk5t' | 'yt5t'
export type SalesFreightCalculation = {
  enabled: boolean
  freight_enabled?: boolean
  lifting_enabled?: boolean
  selected_route_keys?: string[]
} & Record<SalesFreightCapacityKey, number>
  & Record<string, number | boolean | string[] | undefined>
export interface SalesFreightRouteDefinition {
  key: string
  label: string
  feeLabel: string
  liftingFeeLabel: string
  capacityKey: string
}
export interface SalesFreightReferenceRoute extends SalesFreightRouteDefinition {
  freightCostHkd: number
  liftingCostHkd: number
}
export interface SalesFreightOption {
  key: string
  label: string
  feeLabel: string
  liftingFeeLabel: string
  capacityKey: string
  capacityCuft: number
  freightCostHkd: number
  liftingCostHkd: number
  totalCartons: number
  freightPerPieceHkd: number
  liftingPerPieceHkd: number
  perPieceHkd: number
}
export const defaultSalesFreightCosts: Record<LegacySalesFreightRouteKey, number> = {
  hk40: 8000,
  hk20: 7100,
  yt40: 7200,
  yt20: 6000,
  hk10t: 14900,
  yt10t: 11500,
  hk5t: 12500,
  yt5t: 11000,
}
export const defaultSalesFreightCalculation: SalesFreightCalculation = {
  enabled: true,
  freight_enabled: true,
  lifting_enabled: true,
  cap_10t: 1166,
  cap_5t: 750,
  cap_40: 1980,
  cap_20: 883,
  ...defaultSalesFreightCosts,
}
export const salesFreightCapacityDefinitions: Array<{ key: SalesFreightCapacityKey; label: string }> = [
  { key: 'cap_10t', label: '10 吨车容量' },
  { key: 'cap_5t', label: '5 吨车容量' },
  { key: 'cap_40', label: '40 尺柜容量' },
  { key: 'cap_20', label: '20 尺柜容量' },
]
export const salesFreightRouteDefinitions: Array<SalesFreightRouteDefinition & { key: LegacySalesFreightRouteKey }> = [
  { key: 'hk40', label: 'HK 40 柜', capacityKey: 'cap_40', feeLabel: 'HK 40 尺柜运费', liftingFeeLabel: 'HK 40 尺柜吊柜费' },
  { key: 'hk20', label: 'HK 20 柜', capacityKey: 'cap_20', feeLabel: 'HK 20 尺柜运费', liftingFeeLabel: 'HK 20 尺柜吊柜费' },
  { key: 'yt40', label: 'YT 40 柜', capacityKey: 'cap_40', feeLabel: 'YT 40 尺柜运费', liftingFeeLabel: 'YT 40 尺柜吊柜费' },
  { key: 'yt20', label: 'YT 20 柜', capacityKey: 'cap_20', feeLabel: 'YT 20 尺柜运费', liftingFeeLabel: 'YT 20 尺柜吊柜费' },
  { key: 'hk10t', label: 'HK 10 吨车', capacityKey: 'cap_10t', feeLabel: 'HK 10 吨车运费', liftingFeeLabel: 'HK 10 吨车吊柜费' },
  { key: 'yt10t', label: 'YT 10 吨车', capacityKey: 'cap_10t', feeLabel: 'YT 10 吨车运费', liftingFeeLabel: 'YT 10 吨车吊柜费' },
  { key: 'hk5t', label: 'HK 5 吨车', capacityKey: 'cap_5t', feeLabel: 'HK 5 吨车运费', liftingFeeLabel: 'HK 5 吨车吊柜费' },
  { key: 'yt5t', label: 'YT 5 吨车', capacityKey: 'cap_5t', feeLabel: 'YT 5 吨车运费', liftingFeeLabel: 'YT 5 吨车吊柜费' },
]
export const salesFreightSnapshotCostKeys: Record<LegacySalesFreightRouteKey, string> = {
  hk40: 'hk_container_40',
  hk20: 'hk_container_20',
  yt40: 'yt_container_40',
  yt20: 'yt_container_20',
  hk10t: 'hk_truck_10t',
  yt10t: 'yt_truck_10t',
  hk5t: 'hk_truck_5t',
  yt5t: 'yt_truck_5t',
}
export const defaultSalesFreightReferenceRoutes: SalesFreightReferenceRoute[] = salesFreightRouteDefinitions.map((route) => ({
  ...route,
  freightCostHkd: defaultSalesFreightCosts[route.key],
  liftingCostHkd: 0,
}))

export function salesFreightReferenceRoutesFromSnapshot(value: unknown): SalesFreightReferenceRoute[] {
  const freight = value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
  const routeRows = Array.isArray(freight.routes) ? freight.routes : []
  const seen = new Set<string>()
  const routes = routeRows.flatMap((value) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return []
    const row = value as Record<string, unknown>
    const key = String(row.route_key ?? '').trim()
    const label = String(row.route_name ?? '').trim()
    const capacityKey = String(row.capacity_key ?? '').trim()
    const freightCostHkd = Number(row.freight_hkd)
    const liftingCostHkd = Number(row.lifting_hkd ?? 0)
    if (!key || seen.has(key.toLocaleLowerCase()) || !label || !capacityKey || !Number.isFinite(freightCostHkd) || freightCostHkd < 0 || !Number.isFinite(liftingCostHkd) || liftingCostHkd < 0) return []
    seen.add(key.toLocaleLowerCase())
    return [{ key, label, feeLabel: `${label}运费`, liftingFeeLabel: `${label}吊柜费`, capacityKey, freightCostHkd, liftingCostHkd }]
  })
  if (routes.length) return routes

  const legacyCosts = freight.cost_hkd && typeof freight.cost_hkd === 'object' && !Array.isArray(freight.cost_hkd)
    ? freight.cost_hkd as Record<string, unknown>
    : {}
  return defaultSalesFreightReferenceRoutes.map((route) => {
    const legacyKey = route.key as LegacySalesFreightRouteKey
    const value = Number(legacyCosts[salesFreightSnapshotCostKeys[legacyKey]])
    return { ...route, freightCostHkd: Number.isFinite(value) && value >= 0 ? value : route.freightCostHkd, liftingCostHkd: 0 }
  })
}
export interface BuzzBeeColorBoxTier { quote_price_hkd: number; fsc_price_hkd: number; moq: string }
export interface DisneyCustomerQuoteFields { item_number: string; quote_date: string; revision: number; minimum_order_qty: number; moq_prices_usd: { qty_3000: number; qty_5000: number; qty_10000: number }; transportation_usd: number; model_cost_usd: number; setup_charge_usd: number }
export interface DickieProductQuoteRow { line_no: number; item_text_en: string; units_per_carton: string; carton_cbm: number; color_box_size_cm: string; carton_size_cm: string; production_moq: string; price_40h_hkd: number; price_20h_hkd: number; price_lcl_hkd: number }
export interface DickieRemarkLine { line_no: number; text_en: string }
export interface DickieMaterialPrice { material: string; price_hkd_lb: number }
export interface DickieCustomerQuoteFields { mapping?: DickieMapping; client_name: string; quote_date: string; attention: string; revision: string; from_name: string; project_name_en: string; first_shot_time: string; finish_time: string; product_rows: DickieProductQuoteRow[]; remark_lines: DickieRemarkLine[]; material_prices_hkd: DickieMaterialPrice[] }
export interface CaixingCustomerQuoteFields {
  product_type: 'plastic' | 'plush'
  item_number: string
  item_name: string
  quote_date: string
  markup_rate_override: number | null
}
export interface ThreeSixtyCustomerQuoteFields {
  ms_brand: string
  prepared_by: string
  quote_date: string
  revision: string
  first_etd: string
  freight_route_key: string
}
export interface CustomerQuoteFields { buzzbee: { color_box_tiers: BuzzBeeColorBoxTier[]; template_profile?: string; notes?: string }; disney: DisneyCustomerQuoteFields; dickie: DickieCustomerQuoteFields; caixing: CaixingCustomerQuoteFields; three_sixty: ThreeSixtyCustomerQuoteFields }
export interface SalesMarkupTier {
  moq: number
  markup_x: number
  include_in_output?: boolean
}
export interface SalesShippingPricing {
  markup_x?: number
  packaging_markup_x?: number
  markup_tiers?: SalesMarkupTier[]
  selected_markup_moq?: number
  misc_ratio?: number
  divisor?: number
  freight_pct?: number
  lifting_pct?: number
}
export interface JustPlayPackagingInputs {
  adhesive_extra_hkd: number | ''
  paper_pallet_extra_hkd: number | ''
  pallet_length_mm?: number | ''
  pallet_width_mm?: number | ''
  pallet_height_mm?: number | ''
  cartons_per_pallet_override?: number | ''
}
export interface JustPlayCartonInputs {
  dimension_source: 'color_box' | 'product'
  length_count: number
  width_count: number
  height_count: number
}
export interface CustomerSuppliedMaterialRow {
  item: string
  unit_price_hkd: number | ''
  fee_rate_percent: number | ''
  pricing_component_id?: string
}

export function customerSuppliedMaterialValid(row: CustomerSuppliedMaterialRow): boolean {
  return Boolean(row.item.trim()) && row.unit_price_hkd !== '' && row.fee_rate_percent !== ''
    && Number.isFinite(Number(row.unit_price_hkd)) && Number(row.unit_price_hkd) >= 0
    && Number.isFinite(Number(row.fee_rate_percent)) && Number(row.fee_rate_percent) >= 0 && Number(row.fee_rate_percent) <= 100
}

export function calculateCustomerSuppliedFeeHkd(row: CustomerSuppliedMaterialRow): number {
  if (!customerSuppliedMaterialValid(row)) return 0
  const amount = Number(row.unit_price_hkd) * Number(row.fee_rate_percent) / 100
  // Counter binary rounding at half a unit in the fourth decimal place;
  // the authoritative Decimal calculator and Excel ROUND both round up there.
  return Math.round((amount + Number.EPSILON) * 10000) / 10000
}

export interface SalesPayload {
  paper_price_factor: number
  inner_paper_price_factor?: number
  flat_card_price_factor?: number
  testing_fee_enabled: boolean
  testing_fee_total_usd: number
  testing_fee_moqs: number[]
  testing_fee_moq?: number
  packaging_materials: SalesPackagingMaterialRow[]
  customer_supplied_materials?: CustomerSuppliedMaterialRow[]
  justplay_packaging?: JustPlayPackagingInputs
  product_size_in: SalesDimensions
  color_box_size_unit?: SalesDimensionUnit
  color_box_size_in: SalesDimensions
  pdq_size_in?: SalesDimensions
  pdq_size_unit?: SalesDimensionUnit
  justplay_carton?: JustPlayCartonInputs
  cartons: SalesCartonRow[]
  freight_calc: SalesFreightCalculation
  shipping?: SalesShippingPricing
  pricing_mode?: 'component'
  pricing_components?: SalesPricingComponent[]
  additional_tax_hkd?: number
  indonesia_freight_hkd?: number
  tax_categories?: SalesTaxRow[]
  scenarios?: SalesScenario[]
  customer_quote_fields: CustomerQuoteFields
}

export type InternalQuoteSectionPayload = SalesPayload | EngineeringPayload | ElectronicPayload | MoldingPayload | PaintingPayload | SlushPayload | SewingPayload | AssemblyPayload

const operationCodes: PaintingOperationCode[] = ['clamp', 'pad_print', 'uv', 'spray', 'edge', 'paint', 'dip', 'wipe', 'pp_water']

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

export const defaultSalesMiscRatio = .02
export const defaultSalesSettlementDivisor = .98

export function salesSettlementDivisorForMiscRatio(miscRatio: number) {
  if (!Number.isFinite(miscRatio) || miscRatio < 0 || miscRatio >= 1) {
    throw new RangeError('杂项率必须大于等于 0 且小于 1。')
  }
  return Number((1 - miscRatio).toFixed(4))
}

export function salesMiscRatioForSettlementDivisor(divisor: number) {
  if (!Number.isFinite(divisor) || divisor <= 0 || divisor > 1) {
    throw new RangeError('报表找数系数必须大于 0 且小于等于 1。')
  }
  return Number((1 - divisor).toFixed(4))
}

function normalizedSalesMiscPricing(
  shippingSource: Record<string, unknown>,
  legacySettlement: unknown,
) {
  const miscRatioSource = shippingSource.misc_ratio
  const miscRatio = Number(miscRatioSource)
  if (Object.prototype.hasOwnProperty.call(shippingSource, 'misc_ratio')
    && miscRatioSource !== '' && miscRatioSource != null
    && Number.isFinite(miscRatio) && miscRatio >= 0 && miscRatio < 1) {
    const normalizedMiscRatio = Number(miscRatio.toFixed(4))
    return {
      misc_ratio: normalizedMiscRatio,
      divisor: salesSettlementDivisorForMiscRatio(normalizedMiscRatio),
    }
  }

  const divisorCandidates = [
    Object.prototype.hasOwnProperty.call(shippingSource, 'divisor') ? shippingSource.divisor : undefined,
    legacySettlement,
  ]
  for (const candidate of divisorCandidates) {
    const divisor = Number(candidate)
    if (!Number.isFinite(divisor) || divisor <= 0 || divisor > 1) continue
    const normalizedDivisor = Number(divisor.toFixed(4))
    return {
      misc_ratio: salesMiscRatioForSettlementDivisor(normalizedDivisor),
      divisor: normalizedDivisor,
    }
  }

  return {
    misc_ratio: defaultSalesMiscRatio,
    divisor: defaultSalesSettlementDivisor,
  }
}

function multiplierValue(value: unknown, fallback = 1) {
  return value == null || value === '' ? fallback : numberValue(value, fallback)
}

export const defaultSalesMarkupMoqs = [3000, 5000, 10000] as const

export function createDefaultSalesMarkupTiers(markup = 1.2): SalesMarkupTier[] {
  const normalizedMarkup = Number.isFinite(markup) && markup > 0 ? markup : 1.2
  return defaultSalesMarkupMoqs.map((moq) => ({ moq, markup_x: normalizedMarkup, include_in_output: true }))
}

export function normalizeSalesMarkupTiers(value: unknown, fallbackMarkup = 1.2): SalesMarkupTier[] {
  if (!Array.isArray(value) || !value.length) return createDefaultSalesMarkupTiers(fallbackMarkup)
  return value.map((item) => {
    const row = objectValue(item)
    return {
      moq: numberValue(row.moq),
      markup_x: numberValue(row.markup_x, fallbackMarkup),
      include_in_output: booleanValue(row.include_in_output, true),
    }
  })
}

export function salesMarkupTierForQuantity(tiers: SalesMarkupTier[], quantity: unknown): SalesMarkupTier {
  const normalized = tiers
    .filter((tier) => Number.isFinite(tier.moq) && tier.moq > 0 && Number.isFinite(tier.markup_x) && tier.markup_x > 0)
    .slice()
    .sort((left, right) => left.moq - right.moq)
  if (!normalized.length) return createDefaultSalesMarkupTiers()[0]!
  const qty = Number(quantity)
  if (!Number.isFinite(qty) || qty <= 0) return normalized[0]!
  return normalized.reduce((selected, tier) => tier.moq <= qty ? tier : selected, normalized[0]!)
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

function testingFeeMoqValues(value: unknown, legacyValue: unknown): number[] {
  if (Array.isArray(value)) {
    const normalized = value.map((item) => positiveIntegerValue(item, 0))
    return normalized.length ? normalized : [0]
  }
  return [positiveIntegerValue(legacyValue, 0)]
}

function dimensions(value: unknown): SalesDimensions {
  const source = objectValue(value)
  return {
    length: numberValue(source.length),
    width: numberValue(source.width),
    height: numberValue(source.height),
  }
}

export function normalizeSalesDimensionUnit(value: unknown): SalesDimensionUnit {
  return String(value ?? '').trim().toLowerCase() === 'cm' ? 'cm' : 'inch'
}

function packagingMaterialRows(value: unknown): SalesPackagingMaterialRow[] {
  return rows(value).map((row) => {
    const category = textValue(row.category)
    const unitPriceSourceCurrency = normalizeUnitPriceSourceCurrency(row)
    return {
      ...pricingMetadata(row),
      item: textValue(row.item),
      specification: textValue(row.specification),
      category: ['blister', 'color_box_inner_card', 'leaflet_manual'].includes(category)
        ? category as SalesPackagingCategory
        : 'other_purchase',
      quantity: numberValue(row.quantity),
      unit_price_rmb: numberValue(row.unit_price_rmb),
      unit_price_hkd: numberValue(row.unit_price_hkd),
      unit_price_source_currency: unitPriceSourceCurrency,
      loss_rate: multiplierValue(row.loss_rate),
      tax_rate_percent: numberValue(row.tax_rate_percent),
      remark: textValue(row.remark),
      disney_description: textValue(row.disney_description),
      disney_unit_price_usd: numberValue(row.disney_unit_price_usd),
      disney_included: numberValue(row.disney_included, 1),
    }
  })
}

function cartonRows(value: unknown): SalesCartonRow[] {
  return rows(value).map((row) => ({
    ...pricingMetadata(row),
    item: textValue(row.item),
    size_unit: normalizeSalesDimensionUnit(row.size_unit),
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

function normalizeUnitPriceSourceCurrency(row: Record<string, unknown>): UnitPriceSourceCurrency {
  const explicit = textValue(row.unit_price_source_currency).toUpperCase()
  if (explicit === 'HKD') return 'HKD'
  if (explicit === 'RMB') return 'RMB'
  const hasRmb = Object.prototype.hasOwnProperty.call(row, 'unit_price_rmb')
    && row.unit_price_rmb !== ''
    && row.unit_price_rmb != null
  const hasHkd = Object.prototype.hasOwnProperty.call(row, 'unit_price_hkd')
    && row.unit_price_hkd !== ''
    && row.unit_price_hkd != null
  return !hasRmb && hasHkd ? 'HKD' : 'RMB'
}

type DualCurrencyUnitPrice = {
  unit_price_rmb?: number
  unit_price_hkd?: number
  unit_price_source_currency?: UnitPriceSourceCurrency
  loss_rate?: number
}

function calculateDualCurrencyUnitPrices(row: DualCurrencyUnitPrice, rmbHkdRate: unknown) {
  const rate = positivePreviewNumber(rmbHkdRate)
  const unitPriceRmb = positivePreviewNumber(row.unit_price_rmb)
  const unitPriceHkd = positivePreviewNumber(row.unit_price_hkd)
  const sourceCurrency = row.unit_price_source_currency === 'HKD'
    || (!unitPriceRmb && unitPriceHkd && row.unit_price_source_currency !== 'RMB')
    ? 'HKD'
    : 'RMB'
  if (sourceCurrency === 'HKD') {
    return {
      sourceCurrency,
      unitPriceHkd,
      unitPriceRmb: rate && unitPriceHkd ? unitPriceHkd * rate : 0,
    }
  }
  return {
    sourceCurrency,
    unitPriceRmb,
    unitPriceHkd: rate && unitPriceRmb ? unitPriceRmb / rate : 0,
  }
}

export function dimensionValueFromInches(value: unknown, unit: SalesDimensionUnit) {
  const inches = numberValue(value)
  return unit === 'cm' ? Number((inches * 2.54).toFixed(4)) : inches
}

export function dimensionValueToInches(value: unknown, unit: SalesDimensionUnit) {
  const displayValue = numberValue(value)
  return unit === 'cm' ? Number((displayValue / 2.54).toFixed(6)) : displayValue
}

export function calculateCartonCuft(carton: Pick<SalesCartonRow, 'length_in' | 'width_in' | 'height_in'>) {
  const length = positivePreviewNumber(carton.length_in)
  const width = positivePreviewNumber(carton.width_in)
  const height = positivePreviewNumber(carton.height_in)
  return length && width && height ? length * width * height / 1728 : 0
}

export function calculatePackagingMaterialUnitRmb(row: DualCurrencyUnitPrice, rmbHkdRate: unknown) {
  return calculateDualCurrencyUnitPrices(row, rmbHkdRate).unitPriceRmb
}

export function calculatePackagingMaterialUnitHkd(row: DualCurrencyUnitPrice, rmbHkdRate: unknown) {
  return calculateDualCurrencyUnitPrices(row, rmbHkdRate).unitPriceHkd
}

function calculateMaterialLossRate(value: unknown) {
  if (value == null || value === '') return 1
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0
}

export function calculatePackagingMaterialEffectiveUnitRmb(row: DualCurrencyUnitPrice, rmbHkdRate: unknown) {
  return calculatePackagingMaterialUnitRmb(row, rmbHkdRate) * calculateMaterialLossRate(row.loss_rate)
}

export function calculatePackagingMaterialEffectiveUnitHkd(row: DualCurrencyUnitPrice, rmbHkdRate: unknown) {
  return calculatePackagingMaterialUnitHkd(row, rmbHkdRate) * calculateMaterialLossRate(row.loss_rate)
}

export function calculatePackagingMaterialAmountHkd(row: Pick<SalesPackagingMaterialRow, 'quantity'> & DualCurrencyUnitPrice, rmbHkdRate: unknown) {
  const quantity = positivePreviewNumber(row.quantity)
  return quantity * calculatePackagingMaterialEffectiveUnitHkd(row, rmbHkdRate)
}

export function normalizeJustPlayPackagingInputs(value: unknown): JustPlayPackagingInputs {
  const source = objectValue(value)
  const input = (key: string, fallback: number, roundExtra = false): number | '' => {
    if (!Object.prototype.hasOwnProperty.call(source, key)) return fallback
    if (source[key] === '' || source[key] == null) return ''
    const parsed = Number(source[key])
    if (parsed < 0) return parsed
    if (!Number.isFinite(parsed)) return ''
    return roundExtra ? Math.round((parsed + Number.EPSILON) * 10) / 10 : parsed
  }
  return {
    adhesive_extra_hkd: input('adhesive_extra_hkd', 0, true),
    paper_pallet_extra_hkd: input('paper_pallet_extra_hkd', 0, true),
    // Preserve the historical axis mapping: 1000 along carton length, 1150 across width.
    pallet_length_mm: input('pallet_length_mm', 1000),
    pallet_width_mm: input('pallet_width_mm', 1150),
    pallet_height_mm: input('pallet_height_mm', 1300),
    ...(source.cartons_per_pallet_override == null ? {} : {
      cartons_per_pallet_override: input('cartons_per_pallet_override', 0),
    }),
  }
}

export function justPlayPackagingInputsValid(value: unknown) {
  const inputs = normalizeJustPlayPackagingInputs(value)
  return inputs.adhesive_extra_hkd !== '' && inputs.adhesive_extra_hkd >= 0
    && inputs.paper_pallet_extra_hkd !== '' && inputs.paper_pallet_extra_hkd >= 0
    && positivePreviewNumber(inputs.pallet_length_mm) > 0
    && positivePreviewNumber(inputs.pallet_width_mm) > 0
    && positivePreviewNumber(inputs.pallet_height_mm) > 0
    && (inputs.cartons_per_pallet_override === undefined
      || (Number.isInteger(inputs.cartons_per_pallet_override) && Number(inputs.cartons_per_pallet_override) > 0))
}

export function normalizeJustPlayCartonInputs(value: unknown): JustPlayCartonInputs {
  const source = objectValue(value)
  return {
    dimension_source: source.dimension_source === 'product' ? 'product' : 'color_box',
    length_count: numberValue(source.length_count, 1),
    width_count: numberValue(source.width_count, 1),
    height_count: numberValue(source.height_count, 1),
  }
}

type JustPlayCartonPayload = Pick<SalesPayload, 'color_box_size_in' | 'product_size_in' | 'pdq_size_in' | 'justplay_carton'>
export function justPlayCartonState(payload: JustPlayCartonPayload) {
  const inputs = normalizeJustPlayCartonInputs(payload.justplay_carton)
  const axes = ['length', 'width', 'height'] as const
  const pdq = payload.pdq_size_in
  const usesPdq = axes.some(axis => pdq?.[axis] != null && pdq[axis] !== 0)
  const source = usesPdq ? 'pdq' : inputs.dimension_source
  const base = (usesPdq ? pdq : source === 'product' ? payload.product_size_in : payload.color_box_size_in)
    ?? { length: 0, width: 0, height: 0 }
  const counts = usesPdq ? [1, 1, 1] : [inputs.length_count, inputs.width_count, inputs.height_count]
  const label = usesPdq ? 'PDQ' : source === 'product' ? '产品' : '彩盒'
  const error = !axes.every(axis => positivePreviewNumber(base[axis]) > 0)
    ? `请补齐${label}长、宽、高，三项必须大于 0。`
    : !counts.every(count => Number.isInteger(count) && count > 0)
      ? '长度、宽度、高度方向个数必须为正整数。' : ''
  return { source, usesPdq, base, counts, error }
}

export function calculateJustPlayMainCartonDimensions(payload: JustPlayCartonPayload) {
  const { base, counts, error } = justPlayCartonState(payload)
  return {
    length_in: error ? 0 : base.length * counts[0]! + 0.75,
    width_in: error ? 0 : base.width * counts[1]! + 0.75,
    height_in: error ? 0 : base.height * counts[2]! + 1,
  }
}

export function resolveSalesCartons(payload: JustPlayCartonPayload & Pick<SalesPayload, 'pricing_mode' | 'cartons'>) {
  if (payload.pricing_mode !== 'component' || !payload.cartons.length) return payload.cartons
  return [
    { ...payload.cartons[0]!, ...calculateJustPlayMainCartonDimensions(payload) },
    ...payload.cartons.slice(1),
  ]
}

export function calculateJustPlayCartonsPerPallet(
  carton: Pick<SalesCartonRow, 'length_in' | 'width_in' | 'height_in'> | undefined,
  parameters?: Partial<JustPlayPackagingInputs>,
) {
  if (!carton) return 0
  const length = positivePreviewNumber(carton.length_in)
  const width = positivePreviewNumber(carton.width_in)
  const height = positivePreviewNumber(carton.height_in)
  if (!length || !width || !height) return 0
  const inputs = normalizeJustPlayPackagingInputs(parameters)
  if (!justPlayPackagingInputsValid(inputs)) return 0
  if (inputs.cartons_per_pallet_override !== undefined) return Number(inputs.cartons_per_pallet_override)
  return Math.floor(positivePreviewNumber(inputs.pallet_width_mm) / (width * 25.4))
    * Math.floor(positivePreviewNumber(inputs.pallet_length_mm) / (length * 25.4))
    * Math.floor(positivePreviewNumber(inputs.pallet_height_mm) / (height * 25.4))
}

export function calculateJustPlayAdhesivePackagingCostHkd(
  carton: Pick<SalesCartonRow, 'length_in' | 'width_in' | 'qty_per_carton'> | undefined,
  parameters?: JustPlayPackagingInputs,
) {
  if (!carton) return 0
  const length = positivePreviewNumber(carton.length_in)
  const width = positivePreviewNumber(carton.width_in)
  const quantity = positivePreviewNumber(carton.qty_per_carton)
  const extra = normalizeJustPlayPackagingInputs(parameters).adhesive_extra_hkd
  return length && width && quantity && extra !== '' && extra >= 0
    ? 3.9 / 2150 * (length * 2 + width * 4 + 6) / quantity + extra
    : 0
}

export function calculateJustPlayPaperPalletCostHkd(
  carton: Pick<SalesCartonRow, 'length_in' | 'width_in' | 'height_in' | 'qty_per_carton'> | undefined,
  parameters?: JustPlayPackagingInputs,
) {
  if (!carton) return 0
  const quantity = positivePreviewNumber(carton.qty_per_carton)
  const cartonsPerPallet = calculateJustPlayCartonsPerPallet(carton, parameters)
  const inputs = normalizeJustPlayPackagingInputs(parameters)
  return quantity && cartonsPerPallet > 0 && inputs.paper_pallet_extra_hkd !== '' && inputs.paper_pallet_extra_hkd >= 0
    ? 19 / cartonsPerPallet / quantity + inputs.paper_pallet_extra_hkd : 0
}

export function calculateEngineeringMaterialUnitRmb(row: DualCurrencyUnitPrice, rmbHkdRate: unknown) {
  return calculatePackagingMaterialUnitRmb(row, rmbHkdRate)
}

export function calculateEngineeringMaterialUnitHkd(row: DualCurrencyUnitPrice, rmbHkdRate: unknown) {
  return calculatePackagingMaterialUnitHkd(row, rmbHkdRate)
}

export function calculateEngineeringMaterialEffectiveUnitRmb(row: DualCurrencyUnitPrice, rmbHkdRate: unknown) {
  return calculatePackagingMaterialEffectiveUnitRmb(row, rmbHkdRate)
}

export function calculateEngineeringMaterialEffectiveUnitHkd(row: DualCurrencyUnitPrice, rmbHkdRate: unknown) {
  return calculatePackagingMaterialEffectiveUnitHkd(row, rmbHkdRate)
}

export function calculateEngineeringMaterialAmountHkd(row: Pick<EngineeringMaterialRow, 'quantity'> & DualCurrencyUnitPrice, rmbHkdRate: unknown) {
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
  const quantity = positivePreviewNumber(flatCard.quantity)
  const factor = positivePreviewNumber(flatCardPriceFactor)
  return length && width && factor && quantity ? length * width * factor * quantity / 1000 : 0
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
  referenceRoutes: SalesFreightReferenceRoute[] = defaultSalesFreightReferenceRoutes,
): SalesFreightOption[] {
  const { freightEnabled, liftingEnabled } = salesFreightCalculationModes(freight)
  if (!freightEnabled && !liftingEnabled) return []
  const cartonCuft = carton ? calculateCartonCuft(carton) : 0
  const quantity = carton ? positivePreviewNumber(carton.qty_per_carton) : 0
  const legacyValues = freight as SalesFreightCalculation & Record<string, unknown>
  return referenceRoutes.map((definition) => {
    const capacityCuft = positivePreviewNumber(freight[definition.capacityKey])
    const freightCostHkd = freightEnabled ? positivePreviewNumber(
      legacyValues[definition.key] ?? definition.freightCostHkd,
    ) : 0
    const liftingCostHkd = liftingEnabled ? positivePreviewNumber(definition.liftingCostHkd) : 0
    const totalCartons = cartonCuft && capacityCuft ? Math.max(Math.round(capacityCuft / cartonCuft), 1) : 0
    const freightPerPieceHkd = totalCartons && quantity ? freightCostHkd / totalCartons / quantity : 0
    const liftingPerPieceHkd = totalCartons && quantity ? liftingCostHkd / totalCartons / quantity : 0
    return {
      ...definition,
      capacityCuft,
      freightCostHkd,
      liftingCostHkd,
      totalCartons,
      freightPerPieceHkd,
      liftingPerPieceHkd,
      perPieceHkd: freightPerPieceHkd + liftingPerPieceHkd,
    }
  })
}

export function salesFreightCalculationModes(freight: Pick<SalesFreightCalculation, 'enabled' | 'freight_enabled' | 'lifting_enabled'>) {
  const legacyEnabled = freight.enabled !== false
  if (!legacyEnabled) return { freightEnabled: false, liftingEnabled: false }
  return {
    freightEnabled: typeof freight.freight_enabled === 'boolean' ? freight.freight_enabled : legacyEnabled,
    liftingEnabled: typeof freight.lifting_enabled === 'boolean' ? freight.lifting_enabled : legacyEnabled,
  }
}

export function calculateSalesTestingFeeUnitUsd(totalUsd: unknown, moq: unknown) {
  const total = positivePreviewNumber(totalUsd)
  const quantity = positivePreviewNumber(moq)
  return quantity > 0 ? total / quantity : 0
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

function electronicCalculationRows(payload: ElectronicPayload): ElectronicComponentRow[] {
  if (payload.quote_mode !== 'quick') return payload.components
  return (payload.quick_quotes ?? []).map((row) => ({
    ...pricingMetadata(row),
    item: row.item,
    specification: '',
    quantity: 1,
    unit_price_rmb: row.unit_price_rmb,
    tax_rate_percent: row.tax_rate_percent,
    remark: row.remark,
    children: [],
  }))
}

export function createDefaultSalesCarton(item = '主纸箱'): SalesCartonRow {
  return {
    item,
    size_unit: 'inch',
    length_in: 0,
    width_in: 0,
    height_in: 0,
    qty_per_carton: 1,
    flat_cards: [],
  }
}

function salesCartonRows(value: unknown): SalesCartonRow[] {
  const normalized = cartonRows(value)
  return normalized.length ? normalized : [createDefaultSalesCarton()]
}

export function calculateElectronicQuickUnitPriceHkd(row: ElectronicQuickQuoteRow, rmbHkdRate: unknown) {
  const rate = positivePreviewNumber(rmbHkdRate)
  return rate ? positivePreviewNumber(row.unit_price_rmb) / rate : 0
}

export function calculateElectronicQuickSubtotalRmb(payload: ElectronicPayload) {
  return (payload.quick_quotes ?? []).reduce((total, row) => total + positivePreviewNumber(row.unit_price_rmb), 0)
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
  const component = electronicRowsSummary(electronicCalculationRows(payload), rate)
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

export function isElectronicQuoteGroupsPayload(value: Record<string, unknown>): value is ElectronicQuoteGroupsPayload {
  return Array.isArray(value.quote_groups)
}

export function electronicQuoteGroups(value: Record<string, unknown>): ElectronicQuoteGroup[] {
  return isElectronicQuoteGroupsPayload(value) ? value.quote_groups : []
}

export function calculateElectronicSectionSummary(payload: Record<string, unknown>, rmbHkdRate: unknown): ElectronicSummary {
  const groups = electronicQuoteGroups(payload)
  if (!isElectronicQuoteGroupsPayload(payload)) return calculateElectronicSummary(payload as unknown as ElectronicPayload, rmbHkdRate)
  return groups.reduce<ElectronicSummary>((total, group) => {
    const summary = calculateElectronicSummary(group, rmbHkdRate)
    return {
      componentCostRmb: total.componentCostRmb + summary.componentCostRmb,
      deductibleInputTaxRmb: total.deductibleInputTaxRmb + summary.deductibleInputTaxRmb,
      preTaxCostRmb: total.preTaxCostRmb + summary.preTaxCostRmb,
      withProfitRmb: total.withProfitRmb + summary.withProfitRmb,
      taxDifferenceRmb: total.taxDifferenceRmb + summary.taxDifferenceRmb,
      taxPayableRmb: total.taxPayableRmb + summary.taxPayableRmb,
      quoteRmb: total.quoteRmb + summary.quoteRmb,
      quoteHkd: total.quoteHkd + summary.quoteHkd,
    }
  }, {
    componentCostRmb: 0, deductibleInputTaxRmb: 0, preTaxCostRmb: 0, withProfitRmb: 0,
    taxDifferenceRmb: 0, taxPayableRmb: 0, quoteRmb: 0, quoteHkd: 0,
  })
}

function textValue(value: unknown) {
  return value == null ? '' : String(value)
}

function pricingMetadata(row: Partial<QuotePricingMetadata>, allowMarkupOverride = true): QuotePricingMetadata {
  const pricingComponentId = textValue(row.pricing_component_id).trim()
  const markupOverride = Number(row.markup_override)
  return {
    ...(pricingComponentId ? { pricing_component_id: pricingComponentId } : {}),
    ...(allowMarkupOverride && Number.isFinite(markupOverride) && markupOverride > 0 && markupOverride <= 9.99
      ? { markup_override: Number(markupOverride.toFixed(2)) }
      : {}),
  }
}

function pricingComponents(value: unknown): SalesPricingComponent[] {
  const seen = new Set<string>()
  return rows(value).flatMap((row) => {
    const id = textValue(row.id).trim()
    const name = textValue(row.name).trim()
    const key = id.toLocaleLowerCase()
    if (!id || !name || seen.has(key)) return []
    seen.add(key)
    const markup = Number(row.markup_x)
    return [{
      id,
      name,
      ...(Number.isFinite(markup) && markup > 0 && markup <= 9.99
        ? { markup_x: Number(markup.toFixed(2)) }
        : {}),
    }]
  })
}

function importBatchMetadata(row: Record<string, unknown>) {
  const importBatchId = textValue(row.import_batch_id).trim()
  return importBatchId ? { import_batch_id: importBatchId } : {}
}

export function splitEngineeringMoldPartNames(value: unknown): string[] {
  const source = textValue(value).replaceAll('／', '/').trim()
  if (!source) return []
  const tokens: string[] = []
  let tokenStart = 0
  let bracketDepth = 0
  for (let index = 0; index < source.length; index += 1) {
    const character = source[index]!
    if ('（(【['.includes(character)) bracketDepth += 1
    else if ('）)】]'.includes(character)) bracketDepth = Math.max(0, bracketDepth - 1)
    else if (character === '/' && bracketDepth === 0) {
      const token = source.slice(tokenStart, index).trim()
      if (token) tokens.push(token)
      tokenStart = index + 1
    }
  }
  const finalToken = source.slice(tokenStart).trim()
  if (finalToken) tokens.push(finalToken)
  const expanded: string[] = []
  const opposites: Record<string, string> = { 前: '后', 后: '前', 左: '右', 右: '左' }
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index]!
    const left = token.match(/^(.*?)([前后左右])([^前后左右]*)$/)
    const right = tokens[index + 1]?.match(/^(.*?)([前后左右])([^前后左右]*)$/)
    if (left && right && opposites[left[2]!] === right[2]
      && (!left[1] || !right[1] || left[1] === right[1])
      && (!left[3] || !right[3] || left[3] === right[3])
      && !/前后|左右/.test(left[1]! + right[1]!)) {
      const prefix = left[1] || right[1] || ''
      const suffix = left[3] || right[3] || ''
      expanded.push(`${prefix}${left[2]}${suffix}`, `${prefix}${right[2]}${suffix}`)
      index += 1
      continue
    }
    const pairs = token.match(/左右|前后/g) ?? []
    // Multiple direction pairs are ambiguous; keep the name for manual review.
    if (pairs.length === 1) {
      const pair = pairs[0]!
      expanded.push(token.replace(pair, pair[0]!), token.replace(pair, pair[1]!))
    } else expanded.push(token)
  }
  return expanded
}

export function previewEngineeringMoldPartSplit(value: unknown, existing: EngineeringMoldPartRow[]) {
  const names = splitEngineeringMoldPartNames(value)
  const matches = new Map<number, number>()
  const used = new Set<number>()
  // Reserve exact matches before attempting to repair legacy bare directions.
  names.forEach((name, index) => {
    const found = existing.findIndex((part, oldIndex) => !used.has(oldIndex) && part.name.trim() === name)
    if (found >= 0) { matches.set(index, found); used.add(found) }
  })
  const directionMatches = (short: string, full: string) => (
    /^[前后左右]$/.test(short) && (full.startsWith(short) || new RegExp(`${short}(?:[（(][^（）()]*[）)])?$`).test(full))
  )
  names.forEach((name, index) => {
    if (matches.has(index)) return
    const candidates = existing.flatMap((part, oldIndex) => !used.has(oldIndex) && directionMatches(part.name.trim(), name) ? [oldIndex] : [])
    if (candidates.length !== 1) return
    const oldIndex = candidates[0]!
    const short = existing[oldIndex]!.name.trim()
    if (names.filter((candidate, candidateIndex) => !matches.has(candidateIndex) && directionMatches(short, candidate)).length !== 1) return
    matches.set(index, oldIndex)
    used.add(oldIndex)
  })
  const proposed = names.map((name, index) => {
    const oldIndex = matches.get(index)
    const old = oldIndex === undefined ? undefined : existing[oldIndex]
    const part: EngineeringMoldPartRow = old
      ? (old.name === name ? old : { ...old, name })
      : { name, color: '', process: '', process_unit_price_hkd: 0, unit_net_weight_g: 0, output_count: 1, quantity: 1 }
    return { part, status: old ? 'matched' as const : 'added' as const }
  })
  const retained = existing.flatMap((part, index) => used.has(index) ? [] : [{ part, status: 'retained' as const }])
  return { rows: [...proposed, ...retained], nameCount: names.length, retainedCount: retained.length }
}

function engineeringMoldParts(row: Record<string, unknown>): EngineeringMoldPartRow[] {
  const savedParts = rows(row.parts)
  const sourceParts: Record<string, unknown>[] = savedParts.length
    ? savedParts
    : splitEngineeringMoldPartNames(row.item ?? row.name ?? row.chinese_name).map((name) => ({ name }))
  return sourceParts.map((part) => ({
    name: textValue(part.name ?? part.item),
    color: textValue(part.color),
    process: textValue(part.process),
    process_unit_price_hkd: numberValue(part.process_unit_price_hkd),
    unit_net_weight_g: numberValue(part.unit_net_weight_g ?? part.net_weight_g),
    output_count: numberValue(part.output_count, 1),
    quantity: numberValue(part.quantity, 1),
  }))
}

function electronicRows(value: unknown): ElectronicComponentRow[] {
  return rows(value).map((row) => ({
    ...importBatchMetadata(row),
    ...pricingMetadata(row),
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

function normalizeElectronicPayload(source: Record<string, unknown>): ElectronicPayload {
  const usesRmbContract = source.quote_mode === 'quick'
    || source.pricing_currency === 'RMB'
    || ['bonding_rmb', 'smt_rmb', 'labor_rmb', 'testing_rmb', 'packaging_rmb'].some((key) => Object.prototype.hasOwnProperty.call(source, key))
    || rows(source.components).some((row) => Object.prototype.hasOwnProperty.call(row, 'unit_price_rmb'))
    || !Object.keys(source).length
  return {
    quote_mode: source.quote_mode === 'quick' ? 'quick' : 'detail',
    quick_quotes: rows(source.quick_quotes).map((row) => ({
      ...importBatchMetadata(row),
      ...pricingMetadata(row),
      item: textValue(row.item ?? row.name),
      unit_price_rmb: numberValue(row.unit_price_rmb ?? row.price_rmb),
      tax_rate_percent: numberValue(row.tax_rate_percent, 13),
      remark: textValue(row.remark ?? row.note),
    })),
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

function normalizeElectronicQuoteGroup(row: Record<string, unknown>, index: number): ElectronicQuoteGroup {
  const id = textValue(row.id).trim() || `electronic-${index + 1}`
  return {
    id,
    name: textValue(row.name).trim() || `电子报价${index + 1}`,
    ...importBatchMetadata(row),
    ...(textValue(row.source_sha256).trim() ? { source_sha256: textValue(row.source_sha256).trim() } : {}),
    ...normalizeElectronicPayload(row),
  }
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

export function calculatePaintingRowSplit(row: PaintingRow) {
  const total = calculatePaintingRowAmount(row)
  if (row.cost_allocation !== 'split') {
    const paint = row.cost_allocation === 'direct' ? calculatePaintingOperationAmount(row, 'paint') : total * .3
    return { paint, labor: total - paint, valid: true }
  }
  const input = (value: unknown) => value == null || value === '' ? null : Number(value)
  let paint = input(row.paint_cost_hkd)
  let labor = input(row.labor_cost_hkd)
  if (paint === null && labor === null) return { paint, labor, valid: false }
  if (paint === null) paint = total - labor!
  if (labor === null) labor = total - paint
  return { paint, labor, valid: Number.isFinite(paint) && Number.isFinite(labor) && paint >= 0 && labor >= 0 && Math.abs(paint + labor - total) <= .00010000001 }
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

export function calculateHairRowAmountHkd(row: HairRow) {
  return positivePreviewNumber(row.unit_price_hkd)
}

export function calculateHairTotalHkd(payload: HairPayload) {
  return payload.lines.reduce((total, row) => total + calculateHairRowAmountHkd(row), 0)
}

export function calculateSewingBasePriceRmb(row: SewingMaterialRow) {
  return Math.max(Number(row.usage) || 0, 0) * Math.max(Number(row.unit_price_rmb) || 0, 0)
}

export function calculateSewingRowTotalRmb(row: SewingMaterialRow) {
  const markup = Math.max(Number(row.markup) || 0, 0) || 1
  return calculateSewingBasePriceRmb(row) * markup
}

export function calculateSewingExchangeRate(row: SewingMaterialRow, rmbHkdRate: unknown) {
  return positivePreviewNumber(row.exchange_rate) || positivePreviewNumber(rmbHkdRate)
}

export function calculateSewingBasePriceHkd(row: SewingMaterialRow, rmbHkdRate: unknown) {
  const rate = calculateSewingExchangeRate(row, rmbHkdRate)
  return rate ? calculateSewingBasePriceRmb(row) / rate : 0
}

export function calculateSewingRowTotalHkd(row: SewingMaterialRow, rmbHkdRate: unknown) {
  const markup = Math.max(Number(row.markup) || 0, 0) || 1
  return calculateSewingBasePriceHkd(row, rmbHkdRate) * markup
}

export function sewingGroupHasLaborLine(group: SewingGroup) {
  return group.materials.some((row) => `${row.item}${row.part}`.includes('人工'))
}

export function calculateSewingGroupTotalRmb(group: SewingGroup) {
  const materialTotal = group.materials.reduce((total, row) => total + calculateSewingRowTotalRmb(row), 0)
  return materialTotal + (sewingGroupHasLaborLine(group) ? 0 : Math.max(Number(group.labor_rmb) || 0, 0))
}

export function calculateSewingGroupTotalHkd(group: SewingGroup, rmbHkdRate: unknown) {
  const materialTotal = group.materials.reduce(
    (total, row) => total + calculateSewingRowTotalHkd(row, rmbHkdRate),
    0,
  )
  const rate = positivePreviewNumber(rmbHkdRate)
  const legacyLaborHkd = !sewingGroupHasLaborLine(group) && rate
    ? Math.max(Number(group.labor_rmb) || 0, 0) / rate
    : 0
  return materialTotal + legacyLaborHkd
}

export function calculateSewingTotalRmb(payload: SewingPayload) {
  return payload.groups.reduce((total, group) => total + calculateSewingGroupTotalRmb(group), 0)
}

export function calculateSewingQuickTotalHkd(payload: SewingPayload) {
  return payload.quick_quotes.reduce((total, row) => total + Math.max(Number(row.unit_price_hkd) || 0, 0), 0)
}

export function calculateSewingTotalHkd(payload: SewingPayload, rmbHkdRate: unknown) {
  if (payload.quote_mode === 'quick') return calculateSewingQuickTotalHkd(payload)
  return payload.groups.reduce(
    (total, group) => total + calculateSewingGroupTotalHkd(group, rmbHkdRate),
    0,
  )
}

export function calculateAssemblyGroupPeople(group: AssemblyGroup) {
  if (!group.processes.length) return positivePreviewNumber(group.total_persons)
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
      ...pricingMetadata(row),
      ...importBatchMetadata(row),
      item: textValue(row.item ?? row.name), mold_no: textValue(row.mold_no), chinese_name: textValue(row.chinese_name), mold_base_type: textValue(row.mold_base_type ?? row.mold_type),
      mold_base_material: textValue(row.mold_base_material), structure: textValue(row.structure), process: textValue(row.process), material: textValue(row.material), material_type: textValue(row.material_type), color: textValue(row.color), cavity: textValue(row.cavity),
      quantity: numberValue(row.quantity ?? row.sets, 1), net_weight_g: numberValue(row.net_weight_g ?? row.weight_g),
      cycle_time_seconds: numberValue(row.cycle_time_seconds ?? row.cycle_sec), mold_size: textValue(row.mold_size), mold_specification: textValue(row.mold_specification),
      image_reference: textValue(row.image_reference), image_attachment_ids: Array.isArray(row.image_attachment_ids) ? row.image_attachment_ids.map(textValue).filter(Boolean) : [], cost_rmb: numberValue(row.cost_rmb ?? row.price_rmb), remark: textValue(row.remark ?? row.note),
      ...(row.dickie_export ? { dickie_export: normalizeDickieMold(row.dickie_export) } : {}),
      machine_code: textValue(row.machine_code), target_output: numberValue(row.target_output), parts: engineeringMoldParts(row), source_row: numberValue(row.source_row),
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
          ...importBatchMetadata(row),
          ...pricingMetadata(row),
          item: textValue(row.item), category, purpose: textValue(row.purpose), specification: textValue(row.specification ?? row.spec),
          quantity: numberValue(row.quantity ?? row.qty), unit: textValue(row.unit), unit_price_rmb: numberValue(row.unit_price_rmb),
          loss_rate: multiplierValue(row.loss_rate),
          ...(category === 'hardware' ? {} : {
            unit_price_hkd: numberValue(row.unit_price_hkd),
            unit_price_source_currency: normalizeUnitPriceSourceCurrency(row),
          }),
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
    if (Array.isArray(source.quote_groups)) {
      return { quote_groups: rows(source.quote_groups).map(normalizeElectronicQuoteGroup) }
    }
    return normalizeElectronicPayload(source) as unknown as Record<string, unknown>
  }
  if (code === 'molding') {
    const injectionLossRate = numberValue(source.injection_loss_rate_percent, 3)
    return {
      injection_loss_rate_percent: injectionLossRate,
      injection_lines: rows(source.injection_lines).map((row) => ({
        buzzbee_material: textValue(row.buzzbee_material),
        ...importBatchMetadata(row),
        ...pricingMetadata(row, false),
        engineering_source_key: textValue(row.engineering_source_key),
        engineering_synced_fields: Array.isArray(row.engineering_synced_fields)
          ? row.engineering_synced_fields.filter((field): field is string => typeof field === 'string')
          : [],
        engineering_sync_disabled: booleanValue(row.engineering_sync_disabled, false),
        item: textValue(row.item ?? row.name), mold_no: textValue(row.mold_no), material: textValue(row.material), grade: textValue(row.grade ?? row.material_grade), color: textValue(row.color),
        net_weight_g: numberValue(row.net_weight_g ?? row.weight_g), loss_rate_percent: numberValue(row.loss_rate_percent, injectionLossRate),
        machine_name: textValue(row.machine_name ?? row.machine), machine_code: textValue(row.machine_code ?? row.machine_model), cavity: textValue(row.cavity),
        sets: numberValue(row.sets, 1), target_output: numberValue(row.target_output ?? row.target), cycle_time_seconds: numberValue(row.cycle_time_seconds ?? row.cycle_sec),
        quantity: numberValue(row.quantity, 1), remark: textValue(row.remark ?? row.note),
        disney_mold_no: textValue(row.disney_mold_no), disney_resin_cost_usd_kg: numberValue(row.disney_resin_cost_usd_kg), disney_cycle_time_seconds: numberValue(row.disney_cycle_time_seconds), disney_labor_rate_usd_hr: numberValue(row.disney_labor_rate_usd_hr),
      })),
      blow_lines: rows(source.blow_lines).map((row) => ({
        ...importBatchMetadata(row),
        ...pricingMetadata(row, false),
        item: textValue(row.item ?? row.name), daily_capacity: textValue(row.daily_capacity ?? row.capacity), material: textValue(row.material), grade: textValue(row.grade),
        estimated_weight_g: numberValue(row.estimated_weight_g ?? row.weight_g), labor_hkd: numberValue(row.labor_hkd ?? row.blow_labor), burr_hkd: numberValue(row.burr_hkd ?? row.flash),
        profit_multiplier: numberValue(row.profit_multiplier ?? row.profit_x, 1.05), quantity: numberValue(row.quantity, 1),
        output_count: textValue(row.output_count ?? row.cavity_note), mold_price_rmb: numberValue(row.mold_price_rmb ?? row.mold_price_note), remark: textValue(row.remark ?? row.note),
      })),
      caixing_tool_plan_rows: rows(source.caixing_tool_plan_rows).map((row) => ({
        ref_no: textValue(row.ref_no), process_type: ['BL', 'CP', 'DC', 'RC'].includes(textValue(row.process_type)) ? textValue(row.process_type) : 'IN', tool_no: textValue(row.tool_no), tooling_cost_hkd: numberValue(row.tooling_cost_hkd), description: textValue(row.description), sku_no: textValue(row.sku_no), cavities: numberValue(row.cavities), up: numberValue(row.up), net_weight_g: numberValue(row.net_weight_g), material_code: numberValue(row.material_code), material: textValue(row.material), color: textValue(row.color), material_cost_hkd: numberValue(row.material_cost_hkd), material_price_hkd_lb: row.material_price_hkd_lb == null || row.material_price_hkd_lb === '' ? null : numberValue(row.material_price_hkd_lb), machine_size: textValue(row.machine_size), cycle_time_seconds: numberValue(row.cycle_time_seconds), process_cost_hkd: numberValue(row.process_cost_hkd), machine_daily_hkd: row.machine_daily_hkd == null || row.machine_daily_hkd === '' ? null : numberValue(row.machine_daily_hkd),
      })),
    }
  }
  if (code === 'painting') return {
    quote_mode: source.quote_mode === 'quick' ? 'quick' : 'detail',
    quick_quote: {
      ...pricingMetadata(objectValue(source.quick_quote)),
      spray_labor_hkd: numberValue(objectValue(source.quick_quote).spray_labor_hkd),
      paint_hkd: numberValue(objectValue(source.quick_quote).paint_hkd),
      paint_tax_rate_percent: 13,
    },
    rows: rows(source.rows).map((row) => ({
      ...importBatchMetadata(row),
      ...pricingMetadata(row),
      image_reference: textValue(row.image_reference ?? row.image),
      name: textValue(row.name ?? row.item),
      position: textValue(row.position),
      operations: paintingOperations(row.operations),
      ...(row.cost_allocation === 'direct' ? { cost_allocation: 'direct' as const } : row.cost_allocation === 'split' ? {
        cost_allocation: 'split' as const,
        paint_cost_hkd: row.paint_cost_hkd == null || row.paint_cost_hkd === '' ? null : Number(row.paint_cost_hkd),
        labor_cost_hkd: row.labor_cost_hkd == null || row.labor_cost_hkd === '' ? null : Number(row.labor_cost_hkd),
      } : {}),
      remark: textValue(row.remark ?? row.note),
      ...(Object.prototype.hasOwnProperty.call(row, 'source_row') ? { source_row: numberValue(row.source_row) } : {}),
    })),
    disney_decorations: rows(source.disney_decorations).map((row) => ({ application_type: textValue(row.application_type), rate_per_op_usd: numberValue(row.rate_per_op_usd), operations: numberValue(row.operations) })),
  }
  if (code === 'slush') return {
    lines: rows(source.lines).map((row) => ({
      ...importBatchMetadata(row),
      ...pricingMetadata(row),
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
  if (code === 'hair') return {
    lines: rows(source.lines).map((row) => ({
      ...pricingMetadata(row),
      name: textValue(row.name ?? row.item),
      craft: textValue(row.craft ?? row.process),
      weight_g: numberValue(row.weight_g ?? row.net_weight_g),
      unit_price_hkd: numberValue(row.unit_price_hkd ?? row.price_hkd),
      unit: textValue(row.unit),
      remark: textValue(row.remark ?? row.note),
    })),
  }
  if (code === 'sewing') {
    return {
      quote_mode: source.quote_mode === 'quick' ? 'quick' : 'detail',
      quick_quotes: rows(source.quick_quotes).map((row) => ({
        ...pricingMetadata(row),
        doll_name: textValue(row.doll_name ?? row.name),
        unit_price_hkd: numberValue(row.unit_price_hkd ?? row.price_hkd),
      })),
      groups: rows(source.groups).map((group) => ({
        ...importBatchMetadata(group),
        ...pricingMetadata(group),
        name: textValue(group.name),
        category: ['hair', '车发'].includes(textValue(group.category)) ? 'hair' : 'clothes',
        labor_rmb: numberValue(group.labor_rmb ?? group.labor_amount),
        materials: rows(group.materials ?? group.items).map((row) => ({
          item: textValue(row.item ?? row.fabric ?? row.material),
          part: textValue(row.part),
          craft: ['电绣', '丝印'].includes(textValue(row.craft)) ? textValue(row.craft) as SewingMaterialRow['craft'] : '',
          pieces: numberValue(row.pieces),
          ...(Object.prototype.hasOwnProperty.call(row, 'supplier') ? { supplier: textValue(row.supplier) } : {}),
          ...(Object.prototype.hasOwnProperty.call(row, 'fabric_moq_y') ? { fabric_moq_y: numberValue(row.fabric_moq_y) } : {}),
          ...(Object.prototype.hasOwnProperty.call(row, 'below_moq_fee_rmb') ? { below_moq_fee_rmb: numberValue(row.below_moq_fee_rmb) } : {}),
          usage: numberValue(row.usage ?? row.qty),
          unit_price_rmb: numberValue(row.unit_price_rmb ?? row.mat_price ?? row.unit_price),
          ...(Object.prototype.hasOwnProperty.call(row, 'exchange_rate') ? { exchange_rate: numberValue(row.exchange_rate) } : {}),
          markup: numberValue(row.markup, 1),
          remark: textValue(row.remark ?? row.note),
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
        const manualPeopleValue = group.total_persons ?? group.total_people
        const totalPersons = processes.length || manualPeopleValue == null || manualPeopleValue === ''
          ? null
          : numberValue(manualPeopleValue)
        return {
          ...importBatchMetadata(group),
          ...pricingMetadata(group),
          name: textValue(group.name),
          category: textValue(group.category) === 'packaging' ? 'packaging' : 'assembly',
          production_qty: productionQty,
          teams,
          total_persons: totalPersons,
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
  const legacyScenarioRows = rows(source.scenarios)
  const legacyScenarioWithSettlement = legacyScenarioRows.find((row) => (
    Object.prototype.hasOwnProperty.call(row, 'settlement')
  ))
  const paperPriceFactor = numberValue(source.paper_price_factor, 2.75)
  const hasInnerPaperPriceFactor = Object.prototype.hasOwnProperty.call(source, 'inner_paper_price_factor')
    && source.inner_paper_price_factor !== ''
    && source.inner_paper_price_factor != null
  const hasFlatCardPriceFactor = Object.prototype.hasOwnProperty.call(source, 'flat_card_price_factor')
    && source.flat_card_price_factor !== ''
    && source.flat_card_price_factor != null
  const freightSource = objectValue(source.freight_calc)
  const legacyFreightEnabled = booleanValue(freightSource.enabled, true)
  const normalizedFreightEnabled = legacyFreightEnabled && booleanValue(freightSource.freight_enabled, true)
  const normalizedLiftingEnabled = legacyFreightEnabled && booleanValue(freightSource.lifting_enabled, true)
  const standardFreightKeys = new Set<string>([
    'enabled',
    'freight_enabled',
    'lifting_enabled',
    'selected_route_keys',
    ...salesFreightCapacityDefinitions.map(({ key }) => key),
    ...salesFreightRouteDefinitions.map(({ key }) => key),
  ])
  const customFreightCapacityValues = Object.fromEntries(
    Object.entries(freightSource)
      .filter(([key, value]) => key.trim() && !standardFreightKeys.has(key) && typeof value !== 'boolean')
      .map(([key, value]) => [key, positiveIntegerValue(value, 0)]),
  )
  const hasSelectedFreightRoutes = Object.prototype.hasOwnProperty.call(freightSource, 'selected_route_keys')
  const selectedFreightRouteKeys = Array.isArray(freightSource.selected_route_keys)
    ? Array.from(new Set(freightSource.selected_route_keys.map((key) => String(key).trim()).filter(Boolean)))
    : []
  const shippingSource = objectValue(source.shipping)
  const hasShippingPricing = Object.prototype.hasOwnProperty.call(source, 'shipping') || Boolean(legacyScenarioWithSettlement)
  const miscPricing = normalizedSalesMiscPricing(shippingSource, legacyScenarioWithSettlement?.settlement)
  const normalizedPricingComponents = pricingComponents(source.pricing_components)
  const cartonDimensions = {
    product_size_in: dimensions(source.product_size_in ?? source.product_size_cm),
    color_box_size_in: dimensions(source.color_box_size_in ?? source.color_box_size_cm),
    ...(source.pricing_mode === 'component' || source.justplay_carton || source.pdq_size_in ? {
      pdq_size_in: dimensions(source.pdq_size_in),
      pdq_size_unit: normalizeSalesDimensionUnit(source.pdq_size_unit),
      justplay_carton: normalizeJustPlayCartonInputs(source.justplay_carton),
    } : {}),
  }
  return {
    paper_price_factor: paperPriceFactor,
    ...(hasInnerPaperPriceFactor ? { inner_paper_price_factor: numberValue(source.inner_paper_price_factor, paperPriceFactor) } : {}),
    ...(hasFlatCardPriceFactor ? { flat_card_price_factor: numberValue(source.flat_card_price_factor, paperPriceFactor) } : {}),
    testing_fee_enabled: booleanValue(source.testing_fee_enabled, true),
    testing_fee_total_usd: numberValue(source.testing_fee_total_usd),
    testing_fee_moqs: testingFeeMoqValues(source.testing_fee_moqs, source.testing_fee_moq),
    packaging_materials: packagingMaterialRows(source.packaging_materials),
    ...(source.pricing_mode === 'component' || Object.prototype.hasOwnProperty.call(source, 'customer_supplied_materials') ? {
      customer_supplied_materials: rows(source.customer_supplied_materials).map((row) => ({
        item: textValue(row.item),
        unit_price_hkd: row.unit_price_hkd === '' ? '' as const : numberValue(row.unit_price_hkd),
        fee_rate_percent: row.fee_rate_percent === '' ? '' as const : numberValue(row.fee_rate_percent),
        ...(textValue(row.pricing_component_id).trim() ? { pricing_component_id: textValue(row.pricing_component_id).trim() } : {}),
      })),
    } : {}),
    ...(source.pricing_mode === 'component' || Object.prototype.hasOwnProperty.call(source, 'justplay_packaging')
      ? { justplay_packaging: normalizeJustPlayPackagingInputs(source.justplay_packaging) }
      : {}),
    // The historical keys were suffixed `_cm`, although the desk values were
    // entered as inches. Migrate them one-for-one; converting by 2.54 here
    // would corrupt existing quotes such as 5.25 × 8.75 × 3.
    ...cartonDimensions,
    color_box_size_unit: normalizeSalesDimensionUnit(source.color_box_size_unit),
    cartons: resolveSalesCartons({
      pricing_mode: source.pricing_mode === 'component' ? 'component' : undefined,
      ...cartonDimensions,
      cartons: salesCartonRows(source.cartons),
    }),
    freight_calc: {
      enabled: normalizedFreightEnabled || normalizedLiftingEnabled,
      freight_enabled: normalizedFreightEnabled,
      lifting_enabled: normalizedLiftingEnabled,
      ...(hasSelectedFreightRoutes ? { selected_route_keys: selectedFreightRouteKeys } : {}),
      ...customFreightCapacityValues,
      ...Object.fromEntries(salesFreightCapacityDefinitions
        .map(({ key }) => [key, positiveIntegerValue(freightSource[key], defaultSalesFreightCalculation[key])])),
      ...Object.fromEntries(salesFreightRouteDefinitions
        .flatMap(({ key }) => Object.prototype.hasOwnProperty.call(freightSource, key)
          ? [[key, numberValue(freightSource[key], defaultSalesFreightCosts[key])]]
          : [])),
    } as SalesFreightCalculation,
    ...(hasShippingPricing ? {
      shipping: {
        ...(Object.prototype.hasOwnProperty.call(shippingSource, 'markup_x') ? { markup_x: numberValue(shippingSource.markup_x, 1.2) } : {}),
        ...(Object.prototype.hasOwnProperty.call(shippingSource, 'packaging_markup_x') ? { packaging_markup_x: numberValue(shippingSource.packaging_markup_x, numberValue(shippingSource.markup_x, 1.2)) } : {}),
        ...(Object.prototype.hasOwnProperty.call(shippingSource, 'markup_tiers')
          ? { markup_tiers: normalizeSalesMarkupTiers(shippingSource.markup_tiers, numberValue(shippingSource.markup_x, 1.2)) }
          : {}),
        ...(Object.prototype.hasOwnProperty.call(shippingSource, 'selected_markup_moq')
          ? { selected_markup_moq: numberValue(shippingSource.selected_markup_moq) }
          : {}),
        misc_ratio: miscPricing.misc_ratio,
        divisor: miscPricing.divisor,
        ...(Object.prototype.hasOwnProperty.call(shippingSource, 'freight_pct') ? { freight_pct: numberValue(shippingSource.freight_pct, 48) } : {}),
        ...(Object.prototype.hasOwnProperty.call(shippingSource, 'lifting_pct') ? { lifting_pct: numberValue(shippingSource.lifting_pct, 52) } : {}),
      },
    } : {}),
    ...(source.pricing_mode === 'component' && normalizedPricingComponents.length
      ? { pricing_mode: 'component', pricing_components: normalizedPricingComponents }
      : {}),
    ...(hasLegacySalesCostFields ? {
      additional_tax_hkd: numberValue(source.additional_tax_hkd),
      indonesia_freight_hkd: numberValue(source.indonesia_freight_hkd),
      tax_categories: rows(source.tax_categories).map((row) => ({ code: textValue(row.code), amount_hkd: numberValue(row.amount_hkd), rate: row.rate === '' || row.rate == null ? '' : numberValue(row.rate) })),
      scenarios: legacyScenarioRows.map((row) => ({ name: textValue(row.name), capacity_cuft: numberValue(row.capacity_cuft), freight_cost_hkd: numberValue(row.freight_cost_hkd), carton_cuft: numberValue(row.carton_cuft), qty_per_carton: numberValue(row.qty_per_carton), freight_share: numberValue(row.freight_share, .48), lift_share: numberValue(row.lift_share, .52), markup: numberValue(row.markup, 1.2), settlement: numberValue(row.settlement, .98) })),
    } : {}),
    customer_quote_fields: {
      buzzbee: {
        template_profile: textValue(objectValue(objectValue(source.customer_quote_fields).buzzbee).template_profile) || 'standard',
        notes: textValue(objectValue(objectValue(source.customer_quote_fields).buzzbee).notes),
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
        mapping: normalizeDickieMapping(objectValue(objectValue(source.customer_quote_fields).dickie).mapping),
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
        markup_rate_override: (() => { const value = objectValue(objectValue(source.customer_quote_fields).caixing).markup_rate_override; return value == null || value === '' ? null : numberValue(value) })(),
      },
      three_sixty: {
        ms_brand: textValue(objectValue(objectValue(source.customer_quote_fields).three_sixty).ms_brand),
        prepared_by: textValue(objectValue(objectValue(source.customer_quote_fields).three_sixty).prepared_by) || '郑大能',
        quote_date: textValue(objectValue(objectValue(source.customer_quote_fields).three_sixty).quote_date),
        revision: textValue(objectValue(objectValue(source.customer_quote_fields).three_sixty).revision) || '0',
        first_etd: textValue(objectValue(objectValue(source.customer_quote_fields).three_sixty).first_etd),
        freight_route_key: textValue(objectValue(objectValue(source.customer_quote_fields).three_sixty).freight_route_key),
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
  clamp: '夹模', pad_print: '移印', uv: 'UV', spray: '散枪', edge: '边模', paint: '油色', dip: '浸油', wipe: '抹油', pp_water: '擦PP水',
}

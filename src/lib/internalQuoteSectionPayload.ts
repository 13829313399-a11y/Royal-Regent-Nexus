import type { InternalQuoteSectionCode } from '@/types/internalQuoteDesk'

export interface EngineeringMaterialRow { item: string; category: 'hardware' | 'auxiliary' | 'packaging'; quantity: number; unit_price_rmb: number }
export interface EngineeringMoldRow { item: string; quantity: number; cost_rmb: number }
export interface EngineeringFlatCardRow { length_in: number; width_in: number; quantity: number }
export interface EngineeringCartonRow { item: string; length_in: number; width_in: number; height_in: number; qty_per_carton: number; flat_cards: EngineeringFlatCardRow[] }
export interface EngineeringPayload { materials: EngineeringMaterialRow[]; molds: EngineeringMoldRow[]; amortization_qty: number; customer_mold_subsidy_usd: number; cartons: EngineeringCartonRow[] }

export interface ElectronicComponentRow { item: string; quantity: number; unit_price_hkd: number; children: ElectronicComponentRow[] }
export interface ElectronicPayload { components: ElectronicComponentRow[]; bonding_hkd: number; smt_hkd: number; labor_hkd: number; testing_hkd: number; packaging_hkd: number; profit_rate_percent: number; tax_credit_difference_hkd: number }

export interface InjectionRow { item: string; material: string; grade: string; net_weight_g: number; loss_rate_percent: number; machine_code: string; sets: number; target_output: number; quantity: number }
export interface BlowRow { item: string; material: string; grade: string; estimated_weight_g: number; labor_hkd: number; burr_hkd: number; profit_multiplier: number; quantity: number }
export interface MoldingPayload { injection_lines: InjectionRow[]; blow_lines: BlowRow[] }

export type PaintingOperationCode = 'clamp' | 'pad_print' | 'spray' | 'edge' | 'paint' | 'dip' | 'wipe'
export interface PaintingOperationValue { quantity: number; unit_price_hkd: number }
export type PaintingOperations = Record<PaintingOperationCode, PaintingOperationValue>
export interface PaintingRow { item: string; operations: PaintingOperations }
export interface PaintingPayload { rows: PaintingRow[] }

export interface SlushRow { item: string; quantity: number; unit_price_hkd: number }
export interface SlushPayload { lines: SlushRow[] }

export interface SewingMaterialRow { item: string; usage: number; unit_price_rmb: number; markup: number }
export interface SewingGroup { name: string; category: 'clothes' | 'hair'; materials: SewingMaterialRow[]; labor_rmb: number }
export interface SewingPayload { groups: SewingGroup[] }

export interface AssemblyProcessRow { name: string; persons: number; teams: number; production_qty: number }
export interface AssemblyGroup { name: string; category: 'assembly' | 'packaging'; processes: AssemblyProcessRow[] }
export interface AssemblyPayload { groups: AssemblyGroup[]; labor_base_hkd: number }

export interface SalesTaxRow { code: string; amount_hkd: number; rate: number | '' }
export interface SalesScenario { name: string; capacity_cuft: number; freight_cost_hkd: number; carton_cuft: number; qty_per_carton: number; freight_share: number; lift_share: number; markup: number; settlement: number }
export interface SalesPayload { additional_tax_hkd: number; indonesia_freight_hkd: number; tax_categories: SalesTaxRow[]; scenarios: SalesScenario[] }

export type InternalQuoteSectionPayload = SalesPayload | EngineeringPayload | ElectronicPayload | MoldingPayload | PaintingPayload | SlushPayload | SewingPayload | AssemblyPayload

const operationCodes: PaintingOperationCode[] = ['clamp', 'pad_print', 'spray', 'edge', 'paint', 'dip', 'wipe']

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

function textValue(value: unknown) {
  return value == null ? '' : String(value)
}

function electronicRows(value: unknown): ElectronicComponentRow[] {
  return rows(value).map((row) => ({
    item: textValue(row.item),
    quantity: numberValue(row.quantity),
    unit_price_hkd: numberValue(row.unit_price_hkd),
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

export function normalizeInternalQuotePayload(code: InternalQuoteSectionCode, value: Record<string, unknown>): Record<string, unknown> {
  const source = objectValue(value)
  if (code === 'engineering') {
    return {
      materials: rows(source.materials).map((row) => ({ item: textValue(row.item), category: ['hardware', 'packaging'].includes(textValue(row.category)) ? textValue(row.category) : 'auxiliary', quantity: numberValue(row.quantity), unit_price_rmb: numberValue(row.unit_price_rmb) })),
      molds: rows(source.molds).map((row) => ({ item: textValue(row.item), quantity: numberValue(row.quantity, 1), cost_rmb: numberValue(row.cost_rmb) })),
      amortization_qty: numberValue(source.amortization_qty),
      customer_mold_subsidy_usd: numberValue(source.customer_mold_subsidy_usd),
      cartons: rows(source.cartons).map((row) => ({
        item: textValue(row.item), length_in: numberValue(row.length_in), width_in: numberValue(row.width_in), height_in: numberValue(row.height_in), qty_per_carton: numberValue(row.qty_per_carton),
        flat_cards: rows(row.flat_cards).map((flat) => ({ length_in: numberValue(flat.length_in), width_in: numberValue(flat.width_in), quantity: numberValue(flat.quantity, 1) })),
      })),
    }
  }
  if (code === 'electronic') {
    return {
      components: electronicRows(source.components), bonding_hkd: numberValue(source.bonding_hkd), smt_hkd: numberValue(source.smt_hkd), labor_hkd: numberValue(source.labor_hkd), testing_hkd: numberValue(source.testing_hkd), packaging_hkd: numberValue(source.packaging_hkd), profit_rate_percent: numberValue(source.profit_rate_percent, 10), tax_credit_difference_hkd: numberValue(source.tax_credit_difference_hkd),
    }
  }
  if (code === 'molding') {
    return {
      injection_lines: rows(source.injection_lines).map((row) => ({ item: textValue(row.item), material: textValue(row.material), grade: textValue(row.grade), net_weight_g: numberValue(row.net_weight_g), loss_rate_percent: numberValue(row.loss_rate_percent, 3), machine_code: textValue(row.machine_code), sets: numberValue(row.sets, 1), target_output: numberValue(row.target_output), quantity: numberValue(row.quantity, 1) })),
      blow_lines: rows(source.blow_lines).map((row) => ({ item: textValue(row.item), material: textValue(row.material), grade: textValue(row.grade), estimated_weight_g: numberValue(row.estimated_weight_g), labor_hkd: numberValue(row.labor_hkd), burr_hkd: numberValue(row.burr_hkd), profit_multiplier: numberValue(row.profit_multiplier, 1.05), quantity: numberValue(row.quantity, 1) })),
    }
  }
  if (code === 'painting') return { rows: rows(source.rows).map((row) => ({ item: textValue(row.item), operations: paintingOperations(row.operations) })) }
  if (code === 'slush') return { lines: rows(source.lines).map((row) => ({ item: textValue(row.item), quantity: numberValue(row.quantity), unit_price_hkd: numberValue(row.unit_price_hkd) })) }
  if (code === 'sewing') {
    return { groups: rows(source.groups).map((group) => ({ name: textValue(group.name), category: textValue(group.category) === 'hair' ? 'hair' : 'clothes', labor_rmb: numberValue(group.labor_rmb), materials: rows(group.materials).map((row) => ({ item: textValue(row.item), usage: numberValue(row.usage), unit_price_rmb: numberValue(row.unit_price_rmb), markup: numberValue(row.markup, 1) })) })) }
  }
  if (code === 'assembly') {
    return { labor_base_hkd: numberValue(source.labor_base_hkd, 310), groups: rows(source.groups).map((group) => ({ name: textValue(group.name), category: textValue(group.category) === 'packaging' ? 'packaging' : 'assembly', processes: rows(group.processes).map((row) => ({ name: textValue(row.name), persons: numberValue(row.persons), teams: numberValue(row.teams), production_qty: numberValue(row.production_qty) })) })) }
  }
  return {
    additional_tax_hkd: numberValue(source.additional_tax_hkd),
    indonesia_freight_hkd: numberValue(source.indonesia_freight_hkd),
    tax_categories: rows(source.tax_categories).map((row) => ({ code: textValue(row.code), amount_hkd: numberValue(row.amount_hkd), rate: row.rate === '' || row.rate == null ? '' : numberValue(row.rate) })),
    scenarios: rows(source.scenarios).map((row) => ({ name: textValue(row.name), capacity_cuft: numberValue(row.capacity_cuft), freight_cost_hkd: numberValue(row.freight_cost_hkd), carton_cuft: numberValue(row.carton_cuft), qty_per_carton: numberValue(row.qty_per_carton), freight_share: numberValue(row.freight_share, .48), lift_share: numberValue(row.lift_share, .52), markup: numberValue(row.markup, 1.2), settlement: numberValue(row.settlement, .98) })),
  }
}

export function cloneInternalQuotePayload(code: InternalQuoteSectionCode, value: Record<string, unknown>) {
  return normalizeInternalQuotePayload(code, structuredClone(value))
}

export const paintingOperationLabels: Record<PaintingOperationCode, string> = {
  clamp: '夹模', pad_print: '移印', spray: '散枪', edge: '边模', paint: '油色', dip: '浸油', wipe: '抹油',
}

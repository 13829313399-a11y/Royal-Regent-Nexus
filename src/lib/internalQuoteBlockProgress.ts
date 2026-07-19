import type {
  AssemblyPayload,
  ElectronicComponentRow,
  ElectronicPayload,
  EngineeringPayload,
  MoldingPayload,
  PaintingPayload,
  SalesPayload,
  SewingPayload,
  SlushPayload,
} from '@/lib/internalQuoteSectionPayload'
import type { InternalQuoteSectionCode } from '@/types/internalQuoteDesk'

export type InternalQuoteBlockStatus = 'missing' | 'partial' | 'complete' | 'optional' | 'automatic'
export type InternalQuoteBlockRequirement = 'required' | 'optional' | 'automatic' | 'alternative'

export interface InternalQuoteFormBlock {
  id: string
  title: string
  requirement: InternalQuoteBlockRequirement
  status: InternalQuoteBlockStatus
  criteria: string
}

const text = (value: unknown) => String(value ?? '').trim()
const positive = (value: unknown) => Number.isFinite(Number(value)) && Number(value) > 0

function state(hasContent: boolean, complete: boolean, requirement: InternalQuoteBlockRequirement): InternalQuoteBlockStatus {
  if (requirement === 'automatic') return 'automatic'
  if (!hasContent) return requirement === 'optional' ? 'optional' : 'missing'
  return complete ? 'complete' : 'partial'
}

function block(
  id: string,
  title: string,
  requirement: InternalQuoteBlockRequirement,
  hasContent: boolean,
  complete: boolean,
  criteria: string,
): InternalQuoteFormBlock {
  return { id, title, requirement, status: state(hasContent, complete, requirement), criteria }
}

function electronicRowComplete(row: ElectronicComponentRow): boolean {
  const childrenComplete = row.children.every(electronicRowComplete)
  const ownPrice = positive(row.unit_price_rmb) || positive(row.unit_price_hkd)
  return Boolean(text(row.item) && positive(row.quantity) && (ownPrice || row.children.length) && childrenComplete)
}

function engineeringBlocks(payload: EngineeringPayload): InternalQuoteFormBlock[] {
  const hardware = payload.materials.filter((row) => row.category === 'hardware')
  const auxiliary = payload.materials.filter((row) => row.category === 'auxiliary')
  const materialComplete = (row: (typeof payload.materials)[number]) => Boolean(text(row.item) && positive(row.quantity) && positive(row.unit_price_rmb))
  const moldComplete = payload.molds.every((row) => Boolean(text(row.item) && positive(row.quantity) && positive(row.cost_rmb)))
  // The normalizer supplies named zero-value cost rows so the form is ready to edit.
  // They do not mean the user has started this optional block.
  const activeProductionRows = payload.production_mold_costs.filter((row) => positive(row.cost_rmb))
  const productionRowsComplete = activeProductionRows.every((row) => Boolean(text(row.item) && positive(row.cost_rmb)))
  const hasAllocation = activeProductionRows.length > 0 || positive(payload.prototype_total_usd) || positive(payload.testing_total_usd)
  const allocationComplete = productionRowsComplete
    && (!activeProductionRows.length || positive(payload.amortization_qty))
    && (!positive(payload.prototype_total_usd) || positive(payload.prototype_amortization_qty))
    && (!positive(payload.testing_total_usd) || positive(payload.testing_amortization_qty))
    && positive(payload.mold_fx_rmb_usd)
  return [
    block('hardware', '五金', 'optional', hardware.length > 0, hardware.length > 0 && hardware.every(materialComplete), '可选；填写时名称、用量、RMB 单价必填'),
    block('auxiliary', '辅助材料', 'optional', auxiliary.length > 0, auxiliary.length > 0 && auxiliary.every(materialComplete), '可选；填写时名称、类别、用量、RMB 单价必填'),
    block('molds', '模具资料', 'optional', payload.molds.length > 0, payload.molds.length > 0 && moldComplete, '可选；填写时模具名称、套数、模价 RMB 必填'),
    block('mold-allocation', '生产模具费用与分摊', 'optional', hasAllocation, hasAllocation && allocationComplete, '可选；有费用时金额、对应分摊套数和 RMB→USD 汇率必填'),
  ]
}

function electronicBlocks(payload: ElectronicPayload): InternalQuoteFormBlock[] {
  const complete = payload.components.length > 0 && payload.components.every(electronicRowComplete)
  return [
    block('components', '电子零件明细', 'required', payload.components.length > 0, complete, '必须；至少一项，名称、用量、RMB 单价必填'),
    block('electronic-summary', '电子成本汇总', 'automatic', true, true, '自动计算；邦定、贴片、人工、测试、包装费用按实际选填'),
  ]
}

function moldingBlocks(payload: MoldingPayload): InternalQuoteFormBlock[] {
  const hasInjection = payload.injection_lines.length > 0
  const hasBlow = payload.blow_lines.length > 0
  const injectionComplete = hasInjection && payload.injection_lines.every((row) => Boolean(
    text(row.item) && text(row.material) && text(row.grade) && positive(row.net_weight_g)
    && text(row.machine_code) && positive(row.sets) && positive(row.target_output) && positive(row.quantity),
  ))
  const blowComplete = hasBlow && payload.blow_lines.every((row) => Boolean(
    text(row.item) && text(row.material) && text(row.grade) && positive(row.estimated_weight_g)
    && positive(row.profit_multiplier) && positive(row.quantity),
  ))
  return [
    block('injection', '注塑部分', hasBlow ? 'optional' : 'alternative', hasInjection, injectionComplete, '注塑/吹气至少一项；注塑需名称、材质/料型、净重、机型、套数、目标数、用量'),
    block('blow', '吹气部分', hasInjection ? 'optional' : 'alternative', hasBlow, blowComplete, '注塑/吹气至少一项；吹气需名称、材质/料型、料重、利润倍率、用量'),
  ]
}

function paintingBlocks(payload: PaintingPayload): InternalQuoteFormBlock[] {
  const complete = payload.rows.length > 0 && payload.rows.every((row) => {
    const pricedOperation = Object.values(row.operations).some((operation) => positive(operation.quantity) && positive(operation.unit_price_hkd))
    return Boolean(text(row.name) && text(row.position) && pricedOperation)
  })
  return [block('painting', '二次加工（印喷报价）', 'required', payload.rows.length > 0, complete, '必须；名称、位置及至少一种工序的数量和单价必填')]
}

function slushBlocks(payload: SlushPayload): InternalQuoteFormBlock[] {
  const complete = payload.lines.length > 0 && payload.lines.every((row) => Boolean(
    text(row.item) && text(row.material) && positive(row.weight_g) && positive(row.daily_output_24h)
    && positive(row.quantity) && positive(row.unit_price_hkd),
  ))
  return [block('slush', '搪胶产品报价', 'required', payload.lines.length > 0, complete, '必须；胶件、材料、料重、日产量、用量和 HKD 单价必填')]
}

function sewingBlocks(payload: SewingPayload): InternalQuoteFormBlock[] {
  const complete = payload.groups.length > 0 && payload.groups.every((group) => Boolean(
    text(group.name) && group.materials.length > 0 && group.materials.every((row) => (
      text(row.item) && positive(row.usage) && positive(row.unit_price_rmb) && positive(row.markup)
    )),
  ))
  return [block('sewing', '车缝产品报价', 'required', payload.groups.length > 0, complete, '必须；产品组名及至少一项布料，布料名、用量、物料价、码点必填')]
}

function assemblyBlocks(payload: AssemblyPayload): InternalQuoteFormBlock[] {
  const complete = positive(payload.labor_base_hkd) && payload.groups.length > 0 && payload.groups.every((group) => Boolean(
    text(group.name) && group.processes.length > 0 && group.processes.every((row) => (
      text(row.name) && positive(row.persons) && positive(row.teams) && positive(row.production_qty)
    )),
  ))
  return [block('assembly', '装配与包装产品组', 'required', payload.groups.length > 0, complete, '必须；人工基数、产品组名及工序的人数、小组数、生产量必填')]
}

function salesBlocks(payload: SalesPayload): InternalQuoteFormBlock[] {
  const packagingComplete = payload.packaging_materials.length > 0 && payload.packaging_materials.every((row) => Boolean(
    text(row.item) && text(row.specification) && positive(row.quantity) && positive(row.unit_price_rmb),
  ))
  const dimensionsComplete = [payload.product_size_cm, payload.color_box_size_cm]
    .every((size) => positive(size.length) && positive(size.width) && positive(size.height))
  const cartonsComplete = payload.cartons.length > 0 && payload.cartons.every((row) => Boolean(
    text(row.item) && positive(row.length_in) && positive(row.width_in) && positive(row.height_in) && positive(row.qty_per_carton)
    && row.flat_cards.every((card) => text(card.name) && positive(card.length_in) && positive(card.width_in) && positive(card.quantity)),
  ))
  const capacityKeys = ['cap_10t', 'cap_5t', 'cap_40', 'cap_20'] as const
  const routeKeys = ['hk40', 'hk20', 'yt40', 'yt20', 'hk10t', 'yt10t', 'hk5t', 'yt5t'] as const
  const freightComplete = payload.freight_calc.enabled === false || (
    capacityKeys.every((key) => positive(payload.freight_calc[key]))
    && routeKeys.every((key) => positive(payload.freight_calc[key]))
    && cartonsComplete
  )
  return [
    block('packaging-materials', '包装材料', 'optional', payload.packaging_materials.length > 0, packagingComplete, '可选；填写时名称、规格、类别、用量、RMB 单价必填'),
    block('cartons', '纸箱计算与包装尺寸', 'required', payload.cartons.length > 0 || dimensionsComplete, dimensionsComplete && cartonsComplete, '必须；产品/彩盒三维尺寸、至少一个纸箱尺寸和每箱数量必填；平卡可选'),
    block('freight', '运费计算', 'required', true, freightComplete, '必须二选一：完整填写容量及运费，或明确切换为“客户自提”'),
  ]
}

export function getInternalQuoteFormBlocks(code: InternalQuoteSectionCode, payload: Record<string, unknown>): InternalQuoteFormBlock[] {
  if (code === 'engineering') return engineeringBlocks(payload as unknown as EngineeringPayload)
  if (code === 'electronic') return electronicBlocks(payload as unknown as ElectronicPayload)
  if (code === 'molding') return moldingBlocks(payload as unknown as MoldingPayload)
  if (code === 'painting') return paintingBlocks(payload as unknown as PaintingPayload)
  if (code === 'slush') return slushBlocks(payload as unknown as SlushPayload)
  if (code === 'sewing') return sewingBlocks(payload as unknown as SewingPayload)
  if (code === 'assembly') return assemblyBlocks(payload as unknown as AssemblyPayload)
  return salesBlocks(payload as unknown as SalesPayload)
}

export const internalQuoteBlockStatusLabels: Record<InternalQuoteBlockStatus, string> = {
  missing: '必填未开始',
  partial: '填写中',
  complete: '已完成',
  optional: '可不填',
  automatic: '自动计算',
}

export const internalQuoteBlockRequirementLabels: Record<InternalQuoteBlockRequirement, string> = {
  required: '必须',
  optional: '可选',
  automatic: '自动',
  alternative: '至少选一',
}

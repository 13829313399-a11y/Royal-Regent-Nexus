import type {
  AssemblyPayload,
  ElectronicComponentRow,
  ElectronicPayload,
  EngineeringPayload,
  HairPayload,
  MoldingPayload,
  PaintingPayload,
  SalesPayload,
  SewingPayload,
  SlushPayload,
} from '@/lib/internalQuoteSectionPayload'
import { salesFreightCalculationModes } from '@/lib/internalQuoteSectionPayload'
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
  const materialComplete = (row: (typeof payload.materials)[number]) => Boolean(
    text(row.item)
    && positive(row.quantity)
    && (positive(row.unit_price_rmb) || (row.category !== 'hardware' && positive(row.unit_price_hkd))),
  )
  const moldComplete = payload.molds.every((row) => Boolean(text(row.item) && positive(row.quantity) && positive(row.cost_rmb)))
  // The normalizer supplies named zero-value cost rows so the form is ready to edit.
  // They do not mean the user has started this optional block.
  const allocationEnabled = payload.mold_allocation_enabled !== false
  const activeProductionRows = allocationEnabled ? payload.production_mold_costs.filter((row) => positive(row.cost_rmb)) : []
  const productionRowsComplete = activeProductionRows.every((row) => Boolean(text(row.item) && positive(row.cost_rmb)))
  const hasAllocation = allocationEnabled && (activeProductionRows.length > 0 || positive(payload.prototype_total_usd) || positive(payload.testing_total_usd))
  const allocationComplete = productionRowsComplete
    && (!activeProductionRows.length || positive(payload.amortization_qty))
    && (!positive(payload.prototype_total_usd) || positive(payload.prototype_amortization_qty))
    && (!positive(payload.testing_total_usd) || positive(payload.testing_amortization_qty))
    && positive(payload.mold_fx_rmb_usd)
  return [
    block('hardware', '五金部分', 'optional', hardware.length > 0, hardware.length > 0 && hardware.every(materialComplete), '可选；填写时名称、用量、RMB 单价必填'),
    block('auxiliary', '辅助材料部分', 'optional', auxiliary.length > 0, auxiliary.length > 0 && auxiliary.every(materialComplete), '可选；填写时名称、类别、用量及 RMB/HKD 任一单价必填'),
    block('molds', '模具部分', 'optional', payload.molds.length > 0, payload.molds.length > 0 && moldComplete, '可选；填写时模具名称、套数、模价 RMB 必填'),
    block('mold-allocation', '生产模具费用与分摊部分', 'optional', hasAllocation, hasAllocation && allocationComplete, '可选；可关闭分摊，启用且有费用时金额、对应分摊套数和 RMB→USD 汇率必填'),
  ]
}

function electronicBlocks(payload: ElectronicPayload): InternalQuoteFormBlock[] {
  if (payload.quote_mode === 'quick') {
    const quickRows = payload.quick_quotes ?? []
    const complete = quickRows.length > 0 && quickRows.every((row) => Boolean(
      text(row.item)
      && positive(row.unit_price_rmb)
      && Number.isFinite(Number(row.tax_rate_percent))
      && Number(row.tax_rate_percent) >= 0
      && Number(row.tax_rate_percent) <= 100,
    ))
    return [
      block('components', '电子快捷报价部分', 'required', quickRows.length > 0, complete, '必须；至少一项，零件名称、RMB 单价和 0–100% 税点必填'),
      block('electronic-summary', '电子成本汇总部分', 'automatic', true, true, '自动计算；快捷行按每件用量 1 计价，邦定、贴片、人工、测试、包装费用按实际选填'),
    ]
  }
  const complete = payload.components.length > 0 && payload.components.every(electronicRowComplete)
  return [
    block('components', '电子零件部分', 'required', payload.components.length > 0, complete, '必须；至少一项，名称、用量、RMB 单价必填'),
    block('electronic-summary', '电子成本汇总部分', 'automatic', true, true, '自动计算；邦定、贴片、人工、测试、包装费用按实际选填'),
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
  if (payload.quote_mode === 'quick') {
    const labor = Number(payload.quick_quote?.spray_labor_hkd) || 0
    const paint = Number(payload.quick_quote?.paint_hkd) || 0
    const complete = labor >= 0 && paint >= 0 && labor + paint > 0
    return [block('painting', '喷油快捷报价部分', 'required', labor > 0 || paint > 0, complete, '快捷报价；喷油工与油漆按 HKD 填写，油漆固定加计 13% 税金，合计须大于 0')]
  }
  const complete = payload.rows.length > 0 && payload.rows.every((row) => {
    const pricedOperation = Object.values(row.operations).some((operation) => positive(operation.quantity) && positive(operation.unit_price_hkd))
    return Boolean(text(row.name) && text(row.position) && pricedOperation)
  })
  return [block('painting', '喷油/移印/UV部分', 'required', payload.rows.length > 0, complete, '必须；名称、位置及至少一种工序的数量和单价必填')]
}

function slushBlocks(payload: SlushPayload): InternalQuoteFormBlock[] {
  const complete = payload.lines.length > 0 && payload.lines.every((row) => Boolean(
    text(row.item) && text(row.material) && positive(row.weight_g) && positive(row.daily_output_24h)
    && positive(row.quantity) && positive(row.unit_price_hkd),
  ))
  return [block('slush', '搪胶部分', 'required', payload.lines.length > 0, complete, '必须；胶件、材料、料重、日产量、用量和 HKD 单价必填')]
}

function hairBlocks(payload: HairPayload): InternalQuoteFormBlock[] {
  const complete = payload.lines.length > 0 && payload.lines.every((row) => Boolean(
    text(row.name) && text(row.craft) && positive(row.weight_g)
    && positive(row.unit_price_hkd) && text(row.unit),
  ))
  return [block('hair', '车发部分', 'required', payload.lines.length > 0, complete, '必须；名称、工艺、重量、HKD 单价和单位必填，备注可不填')]
}

function sewingBlocks(payload: SewingPayload): InternalQuoteFormBlock[] {
  if (payload.quote_mode === 'quick') {
    const started = payload.quick_quotes.some((row) => Boolean(text(row.doll_name) || positive(row.unit_price_hkd)))
    const complete = payload.quick_quotes.length > 0 && payload.quick_quotes.every((row) => Boolean(text(row.doll_name) && positive(row.unit_price_hkd)))
    return [block('sewing', '车缝快捷报价部分', 'required', started, complete, '快捷报价；至少一个公仔，公仔名称与单个公仔 HKD 价钱必填')]
  }
  const complete = payload.groups.length > 0 && payload.groups.every((group) => Boolean(
    text(group.name) && group.materials.length > 0 && group.materials.every((row) => (
      text(row.item) && positive(row.usage) && positive(row.unit_price_rmb) && positive(row.markup)
    )),
  ))
  return [block('sewing', '车缝部分', 'required', payload.groups.length > 0, complete, '必须；产品组名及至少一项布料，布料名、用量、物料价、码点必填')]
}

function assemblyBlocks(payload: AssemblyPayload): InternalQuoteFormBlock[] {
  const groupComplete = (group: AssemblyPayload['groups'][number]) => Boolean(
    text(group.name) && positive(group.production_qty) && positive(group.teams)
    && group.processes.length > 0 && group.processes.every((row) => text(row.name) && positive(row.persons)),
  )
  const assemblyGroups = payload.groups.filter((group) => group.category === 'assembly')
  const packagingGroups = payload.groups.filter((group) => group.category === 'packaging')
  return [
    block('assembly-summary', '总表部分', 'required', true, positive(payload.labor_base_hkd) && positive(payload.standard_work_hours), '必须；人工基数和标准工时须大于 0，产品汇总由系统自动计算'),
    block('assembly-work', '组装部分', 'required', assemblyGroups.length > 0, assemblyGroups.length > 0 && assemblyGroups.every(groupComplete), '必须；产品、生产量、小组数及至少一道工序的名称和人数必填，备注可不填'),
    block('packaging-work', '包装部分', 'required', packagingGroups.length > 0, packagingGroups.length > 0 && packagingGroups.every(groupComplete), '必须；产品、生产量、小组数及至少一道工序的名称和人数必填，备注可不填'),
  ]
}

function salesBlocks(
  payload: SalesPayload,
  freightCapacityKeys: string[] = ['cap_10t', 'cap_5t', 'cap_40', 'cap_20'],
): InternalQuoteFormBlock[] {
  const testingFeeMoqs = payload.testing_fee_moqs?.length
    ? payload.testing_fee_moqs
    : payload.testing_fee_moq != null ? [payload.testing_fee_moq] : []
  const hasTestingFee = positive(payload.testing_fee_total_usd) || testingFeeMoqs.some(positive)
  const testingFeeComplete = positive(payload.testing_fee_total_usd)
    && testingFeeMoqs.length > 0
    && testingFeeMoqs.every(positive)
  const packagingComplete = payload.packaging_materials.length > 0 && payload.packaging_materials.every((row) => Boolean(
    text(row.item) && text(row.specification) && positive(row.quantity) && (positive(row.unit_price_rmb) || positive(row.unit_price_hkd)),
  ))
  const colorBoxDimensionsComplete = positive(payload.color_box_size_in.length)
    && positive(payload.color_box_size_in.width)
    && positive(payload.color_box_size_in.height)
  const cartonsComplete = payload.cartons.length > 0 && payload.cartons.every((row) => Boolean(
    text(row.item) && positive(row.length_in) && positive(row.width_in) && positive(row.height_in) && positive(row.qty_per_carton)
    && row.flat_cards.every((card) => text(card.name) && positive(card.length_in) && positive(card.width_in) && positive(card.quantity)),
  ))
  const capacityKeys = [...new Set(freightCapacityKeys.filter((key) => key.trim()))]
  const freightModes = salesFreightCalculationModes(payload.freight_calc)
  const freightComplete = (!freightModes.freightEnabled && !freightModes.liftingEnabled) || (
    capacityKeys.every((key) => positive(payload.freight_calc[key]))
    && cartonsComplete
  )
  return [
    block('testing-fee', '测试费部分', 'optional', hasTestingFee, testingFeeComplete, '可选；填写测试费用 USD 后，每个 MOQ 必须大于 0，各档单价 USD 由系统自动计算'),
    block('packaging-materials', '包装材料部分', 'optional', payload.packaging_materials.length > 0, packagingComplete, '可选；填写时名称、规格、类别、用量及 RMB/HKD 任一单价必填'),
    block('cartons', '纸箱计算与包装尺寸部分', 'required', payload.cartons.length > 0 || colorBoxDimensionsComplete, colorBoxDimensionsComplete && cartonsComplete, '必须；彩盒三维尺寸、至少一个纸箱尺寸和每箱数量必填，彩盒与纸箱可分别选择 cm 或 inch；产品尺寸（in）和平卡可选'),
    block('freight', '运费计算部分', 'required', true, freightComplete, '运费与吊柜费可独立启用；启用任一项时须完整填写容量和主纸箱资料，两项都关闭时不计运输费用'),
  ]
}

export function getInternalQuoteFormBlocks(
  code: InternalQuoteSectionCode,
  payload: Record<string, unknown>,
  salesFreightCapacityKeys?: string[],
): InternalQuoteFormBlock[] {
  if (code === 'engineering') return engineeringBlocks(payload as unknown as EngineeringPayload)
  if (code === 'electronic') return electronicBlocks(payload as unknown as ElectronicPayload)
  if (code === 'molding') return moldingBlocks(payload as unknown as MoldingPayload)
  if (code === 'painting') return paintingBlocks(payload as unknown as PaintingPayload)
  if (code === 'slush') return slushBlocks(payload as unknown as SlushPayload)
  if (code === 'sewing') return sewingBlocks(payload as unknown as SewingPayload)
  if (code === 'hair') return hairBlocks(payload as unknown as HairPayload)
  if (code === 'assembly') return assemblyBlocks(payload as unknown as AssemblyPayload)
  return salesBlocks(payload as unknown as SalesPayload, salesFreightCapacityKeys)
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

import type {
  MoldingSampleActualMaterialCostComponent,
  MoldingSampleItem,
  MoldingSampleMaterialComponent,
  MoldingSampleMaterialSource,
  MoldingSampleOrder,
  MoldingSampleProblemStatus,
  MoldingSampleRole,
  MoldingSampleStatus,
} from '../types/moldingSample.js'

export interface MoldingSampleMaterialPrice {
  material: string
  unit_price: number
  notes?: string
}

export interface MoldingSampleMaterialPriceInput {
  material: string
  unit_price?: string | number | null
  unitPriceHkdPerLb?: string | number | null
  notes?: string | null
}

export interface MoldingSamplePricingSettings {
  prices: MoldingSampleMaterialPrice[]
  rmb_to_hkd_rate: number
  errors: string[]
}

export type MoldingSampleStatusAction =
  | '主管通过'
  | '主管驳回'
  | '经理通过'
  | '经理驳回'
  | '工程重提'
  | '工程撤回'
  | '开始处理'
  | '撤回开始生产'
  | '标记完成'
  | '撤回完成'

export interface MoldingSampleStatusTransitionInput {
  order: MoldingSampleOrder
  action: MoldingSampleStatusAction
  actor_role: MoldingSampleRole
  actor_name: string
  reason?: string
  today?: string
}

export interface MoldingSampleStatusTransitionResult {
  allowed: boolean
  next_status: MoldingSampleStatus
  completed_date: string
  reject_reason?: string
  message?: string
}

export interface MoldingSampleCompletionGate {
  can_complete: boolean
  missing_item_ids: string[]
  message: string
}

export interface MoldingSampleAttentionRecord {
  order: Pick<MoldingSampleOrder, 'status' | 'send_to' | 'workshop'>
  items: Pick<MoldingSampleItem, 'id' | 'mold_id' | 'mold_name' | 'actual_weight_kg'>[]
  problems: Array<{ status: MoldingSampleProblemStatus }>
}

export interface MoldingSampleAttentionMetrics {
  rejectedCount: number
  withdrawnCount: number
  unresolvedProblemCount: number
  productionDataPendingCount: number
}

export interface MoldingSampleItemCostResult {
  actual_weight_kg: number | null
  expected_amount_hkd: number | null
  actual_amount_hkd: number | null
  injection_cost_hkd: number | null
  exchange_rate_at_save: number | null
  material_unit_price: number | null
  actual_material_cost_components: MoldingSampleActualMaterialCostComponent[] | null
}

export interface MoldingSampleMaterialCostComponentRow extends MoldingSampleMaterialComponent {
  weight_kg: number
  unit_price: number | null
  amount_hkd: number | null
}

export interface MoldingSampleMaterialCostBreakdown {
  components: MoldingSampleMaterialCostComponentRow[]
  total_amount_hkd: number | null
  weighted_unit_price: number | null
  has_missing_price: boolean
  has_invalid_ratio: boolean
}

export interface MoldingSampleMaterialCostBreakdownInput {
  components: readonly MoldingSampleMaterialComponent[]
  totalWeightKg: number | null | undefined
  prices: MoldingSampleMaterialPrice[]
}

export interface MoldingSampleResolvedActualMaterialCostBreakdown extends MoldingSampleMaterialCostBreakdown {
  source: 'persisted' | 'estimated'
}

export interface MoldingSampleMaterialReportRow {
  material: string
  source_type: MoldingSampleMaterialSource
  line_count: number
  total_weight_kg: number
  total_material_cost_hkd: number
  missing_price_item_ids: string[]
}

export interface MoldingSampleInjectionFeeRow {
  item_id: string
  injection_cost: number | null
  injection_cost_hkd: number | null
  is_missing: boolean
}

export interface MoldingSampleReportItemRow {
  item_id: string
  mold_id: string
  mold_name: string
  material: string
  actual_weight_kg: number | null
  actual_amount_hkd: number | null
  injection_cost: number | null
  injection_cost_hkd: number | null
  total_cost: number
}

export interface MoldingSampleReportSummary {
  total_material_cost: number
  total_injection_cost: number
  total_cost: number
  has_missing_price: boolean
  has_missing_actual_weight: boolean
  has_missing_injection_cost: boolean
  missing_price_item_ids: string[]
  missing_actual_weight_item_ids: string[]
  missing_injection_cost_item_ids: string[]
  material_rows: MoldingSampleMaterialReportRow[]
  injection_fee_rows: MoldingSampleInjectionFeeRow[]
  item_rows: MoldingSampleReportItemRow[]
  archive_ready: boolean
  archive_message: string
}

const KG_TO_LB = 2.20462

const lockedStatuses = new Set<MoldingSampleStatus>(['待经理审核', '待生产', '生产中', '已完成'])

export function roundMoney(value: number) {
  return Math.round(value * 100) / 100
}

export function createDefaultMoldingSampleOrder(
  input: Partial<MoldingSampleOrder> & Pick<MoldingSampleOrder, 'id' | 'product_name' | 'client_name' | 'date' | 'workshop' | 'supervisor' | 'eng_name'>,
): MoldingSampleOrder {
  const timestamp = `${input.date} 00:00`

  return {
    id: input.id,
    factory_id: input.factory_id ?? 'huakang-a',
    production_factory_id: input.production_factory_id ?? null,
    production_assigned_at: input.production_assigned_at ?? '',
    production_assigned_by: input.production_assigned_by ?? '',
    production_assignment_version: input.production_assignment_version ?? 0,
    order_number: input.order_number ?? '',
    doc_number: input.doc_number ?? '',
    product_name: input.product_name,
    client_name: input.client_name,
    date: input.date,
    stage: input.stage ?? '',
    order_type: input.order_type ?? '啤办',
    workshop: input.workshop,
    send_to: input.send_to ?? '',
    supervisor: input.supervisor,
    eng_name: input.eng_name,
    reason: input.reason ?? '',
    status: input.status ?? '待审核',
    reject_reason: input.reject_reason ?? '',
    completed_date: input.completed_date ?? '',
    created_at: input.created_at ?? timestamp,
    updated_at: input.updated_at ?? timestamp,
  }
}

export function isExternalMoldingSampleOrder(order: Pick<MoldingSampleOrder, 'send_to' | 'workshop'>) {
  return order.send_to === '发至湖南'
    || order.send_to === '发至模厂'
    || order.workshop === '模厂'
}

export function isMoldingSampleLocked(order: Pick<MoldingSampleOrder, 'status'>) {
  return lockedStatuses.has(order.status)
}

export function canEditMoldingSampleOrder(
  order: Pick<MoldingSampleOrder, 'status'>,
  role: MoldingSampleRole,
) {
  if (!isMoldingSampleLocked(order)) {
    return role === '工程部' || role === '主管' || role === '经理'
  }

  return role === '主管' || role === '经理'
}

function isAssignedSupervisor(order: MoldingSampleOrder, actorName: string) {
  return order.supervisor === '' || order.supervisor === actorName
}

function isOpeningEngineer(order: MoldingSampleOrder, actorName: string) {
  return order.eng_name === '' || order.eng_name === actorName
}

function rejectedResult(
  order: MoldingSampleOrder,
  message: string,
): MoldingSampleStatusTransitionResult {
  return {
    allowed: false,
    next_status: order.status,
    completed_date: order.completed_date,
    message,
  }
}

export function getMoldingSampleStatusTransition(
  input: MoldingSampleStatusTransitionInput,
): MoldingSampleStatusTransitionResult {
  const { order, action, actor_role, actor_name, reason = '', today = '' } = input

  if (action === '主管通过') {
    if (order.status !== '待审核' || actor_role !== '主管' || !isAssignedSupervisor(order, actor_name)) {
      return rejectedResult(order, '只有指定主管可以审核待审核单。')
    }

    if (isExternalMoldingSampleOrder(order)) {
      return {
        allowed: true,
        next_status: '已完成',
        completed_date: today || order.completed_date || order.date,
      }
    }

    return { allowed: true, next_status: '待生产', completed_date: order.completed_date }
  }

  if (action === '主管驳回') {
    if (order.status !== '待审核' || actor_role !== '主管' || !isAssignedSupervisor(order, actor_name)) {
      return rejectedResult(order, '只有指定主管可以驳回待审核单。')
    }

    return {
      allowed: true,
      next_status: '已驳回',
      completed_date: order.completed_date,
      reject_reason: reason,
    }
  }

  if (action === '经理通过') {
    if (order.status !== '待经理审核' || actor_role !== '经理') {
      return rejectedResult(order, '只有经理可以终审待经理审核单。')
    }

    if (isExternalMoldingSampleOrder(order)) {
      return {
        allowed: true,
        next_status: '已完成',
        completed_date: today || order.completed_date || order.date,
      }
    }

    return { allowed: true, next_status: '待生产', completed_date: order.completed_date }
  }

  if (action === '经理驳回') {
    if (order.status !== '待经理审核' || actor_role !== '经理') {
      return rejectedResult(order, '只有经理可以驳回待经理审核单。')
    }

    return {
      allowed: true,
      next_status: '已驳回',
      completed_date: order.completed_date,
      reject_reason: reason,
    }
  }

  if (action === '工程重提') {
    if (!['已驳回', '已撤回'].includes(order.status) || actor_role !== '工程部') {
      return rejectedResult(order, '只有工程部可以重提已驳回或已撤回单。')
    }

    return { allowed: true, next_status: '待审核', completed_date: '' }
  }

  if (action === '工程撤回') {
    if (order.status !== '待审核' || actor_role !== '工程部' || !isOpeningEngineer(order, actor_name)) {
      return rejectedResult(order, '只有开单工程师可以撤回待审核单。')
    }

    return { allowed: true, next_status: '已撤回', completed_date: order.completed_date }
  }

  if (action === '开始处理') {
    if (order.status !== '待生产' || actor_role !== '啤机部') {
      return rejectedResult(order, '只有啤机部可以开始处理待生产单。')
    }

    return { allowed: true, next_status: '生产中', completed_date: order.completed_date }
  }

  if (action === '撤回开始生产') {
    if (order.status !== '生产中' || actor_role !== '啤机部') {
      return rejectedResult(order, '只有啤机部可以撤回生产中单据到待生产。')
    }

    return { allowed: true, next_status: '待生产', completed_date: '' }
  }

  if (action === '标记完成') {
    if (order.status !== '生产中' || actor_role !== '啤机部') {
      return rejectedResult(order, '只有啤机部可以完成生产中单据。')
    }

    return {
      allowed: true,
      next_status: '已完成',
      completed_date: today || order.completed_date || order.date,
    }
  }

  if (action === '撤回完成') {
    if (order.status !== '已完成' || actor_role !== '啤机部') {
      return rejectedResult(order, '只有啤机部可以撤回已完成单据。')
    }

    return { allowed: true, next_status: '生产中', completed_date: '' }
  }

  return rejectedResult(order, '未知状态动作。')
}

export function buildCompletionGate(
  order: Pick<MoldingSampleOrder, 'send_to' | 'workshop'>,
  items: Pick<MoldingSampleItem, 'id' | 'mold_id' | 'mold_name' | 'actual_weight_kg'>[],
): MoldingSampleCompletionGate {
  if (isExternalMoldingSampleOrder(order)) {
    return {
      can_complete: true,
      missing_item_ids: [],
      message: '外厂或模厂路径主管通过后直接完成，不要求啤机部逐行回填实际用料。',
    }
  }

  const missingItemIds = items
    .filter((item) => !(Number(item.actual_weight_kg) > 0))
    .map((item) => item.id || item.mold_id || item.mold_name || '未命名明细')

  if (missingItemIds.length === 0) {
    return {
      can_complete: true,
      missing_item_ids: [],
      message: '所有明细已填写实际用料，可以标记完成。',
    }
  }

  return {
    can_complete: false,
    missing_item_ids: missingItemIds,
    message: `有 ${missingItemIds.length} 条明细未填写实际用料，无法标记完成：${missingItemIds.slice(0, 5).join('、')}${missingItemIds.length > 5 ? '…' : ''}`,
  }
}

export function countMoldingSampleAttentionMetrics(
  records: MoldingSampleAttentionRecord[],
): MoldingSampleAttentionMetrics {
  return {
    rejectedCount: records.filter((record) => record.order.status === '已驳回').length,
    withdrawnCount: records.filter((record) => record.order.status === '已撤回').length,
    unresolvedProblemCount: records.filter((record) =>
      record.problems.some((problem) => problem.status === '待处理'),
    ).length,
    productionDataPendingCount: records.filter((record) =>
      record.order.status === '生产中'
      && buildCompletionGate(record.order, record.items).missing_item_ids.length > 0,
    ).length,
  }
}

export function normalizeMaterialName(value: string) {
  return value
    .toLowerCase()
    .replace(/[０-９]/g, (char) => String.fromCharCode(char.charCodeAt(0) - 0xFEE0))
    .replace(/度/g, '°')
    .replace(/^\s*\d+\s*#/, '')
    .replace(/[\s\-()（）_]/g, '')
}

const RUNNER_MATERIAL_SUFFIX = /(?:水口料|水口|回料|抽粒)$/i

function findDirectMaterialPrice(material: string, prices: MoldingSampleMaterialPrice[]) {
  const normalized = normalizeMaterialName(material)
  return prices.find((price) => Number(price.unit_price) > 0 && normalizeMaterialName(price.material) === normalized) ?? null
}

function normalizeComponentMaterial(material: string, sourceType: MoldingSampleMaterialSource, fallbackMaterial = '') {
  const trimmed = material.trim()
  if (sourceType !== 'runner') {
    return trimmed
  }

  return trimmed.replace(RUNNER_MATERIAL_SUFFIX, '').trim() || fallbackMaterial
}

function hasValidMaterialComponentRatios(components: readonly MoldingSampleMaterialComponent[]) {
  return components.length > 0
    && components.every((component) => component.material !== '' && Number.isFinite(component.ratio_percent) && component.ratio_percent > 0)
    && Math.abs(components.reduce((sum, component) => sum + component.ratio_percent, 0) - 100) <= 0.01
}

export function normalizeMaterialComponents(
  material: string,
  components?: readonly MoldingSampleMaterialComponent[] | null,
): MoldingSampleMaterialComponent[] {
  if (components?.length) {
    const fallbackMaterial = components.find((component) => component.source_type === 'virgin' && component.material.trim())?.material.trim()
      ?? components.find((component) => component.material.trim())?.material.trim()
      ?? ''

    const normalizedComponents = components.map((component) => ({
        material: normalizeComponentMaterial(component.material, component.source_type, fallbackMaterial),
        source_type: component.source_type === 'runner' ? 'runner' as const : 'virgin' as const,
        ratio_percent: Number(component.ratio_percent),
      }))

    return hasValidMaterialComponentRatios(normalizedComponents) ? normalizedComponents : []
  }

  const trimmedMaterial = material.trim()
  if (!trimmedMaterial) {
    return []
  }

  const normalizedMaterial = trimmedMaterial.replace(/＋/g, '+')
  const hasLegacyCompositionSyntax = /^\s*\d+(?:\.\d+)?\s*[%％]/.test(normalizedMaterial)
  if (!hasLegacyCompositionSyntax) {
    return [{ material: trimmedMaterial, source_type: 'virgin', ratio_percent: 100 }]
  }
  if (normalizedMaterial.trimEnd().endsWith('+')) {
    return []
  }

  const rawParts = normalizedMaterial.split(/\+\s*(?=\d+(?:\.\d+)?\s*[%％])/)

  const parsedParts = rawParts.map((part) => {
    const match = part.trim().match(/^(\d+(?:\.\d+)?)\s*[%％]\s*(.+)$/)
    if (!match) {
      return null
    }
    const rawMaterial = match[2].trim()
    return {
      material: rawMaterial,
      source_type: RUNNER_MATERIAL_SUFFIX.test(rawMaterial) ? 'runner' as const : 'virgin' as const,
      ratio_percent: Number(match[1]),
    }
  })

  if (!parsedParts.every((part) => part !== null)) {
    return []
  }

  const typedParts = parsedParts as MoldingSampleMaterialComponent[]
  const fallbackMaterial = typedParts.find((component) => component.source_type === 'virgin')?.material ?? ''
  const normalizedParts = typedParts.map((component) => ({
    ...component,
    material: normalizeComponentMaterial(component.material, component.source_type, fallbackMaterial),
  }))

  return hasValidMaterialComponentRatios(normalizedParts) ? normalizedParts : []
}

export function resolveMaterialComponents(
  input: string | Pick<MoldingSampleItem, 'material' | 'material_components'>,
) {
  return typeof input === 'string'
    ? normalizeMaterialComponents(input)
    : normalizeMaterialComponents(input.material, input.material_components)
}

export function formatMaterialComposition(components: readonly MoldingSampleMaterialComponent[]) {
  if (components.length === 1 && components[0]?.source_type === 'virgin' && Number(components[0].ratio_percent) === 100) {
    return components[0].material
  }

  return components.map((component) => {
    const ratio = Number(component.ratio_percent)
    const ratioLabel = Number.isInteger(ratio) ? String(ratio) : String(roundMoney(ratio))
    const sourceLabel = component.source_type === 'runner' ? '水口料' : ''
    return `${ratioLabel}%${component.material}${sourceLabel}`
  }).join(' + ')
}

export function calculateMaterialCostBreakdown(
  input: MoldingSampleMaterialCostBreakdownInput,
): MoldingSampleMaterialCostBreakdown {
  const components = normalizeMaterialComponents('', input.components)
  const ratioTotal = components.reduce((sum, component) => sum + component.ratio_percent, 0)
  const hasInvalidRatio = components.length === 0 || Math.abs(ratioTotal - 100) > 0.01
  const totalWeightKg = Number(input.totalWeightKg)
  const hasValidWeight = Number.isFinite(totalWeightKg) && totalWeightKg > 0
  const rows = components.map<MoldingSampleMaterialCostComponentRow>((component) => {
    const price = findDirectMaterialPrice(component.material, input.prices)
    const weightKg = Math.round(totalWeightKg * component.ratio_percent * 100) / 10000
    return {
      ...component,
      weight_kg: hasValidWeight ? weightKg : 0,
      unit_price: price?.unit_price ?? null,
      amount_hkd: hasValidWeight && price
        ? roundMoney(weightKg * KG_TO_LB * price.unit_price)
        : null,
    }
  })
  const hasMissingPrice = rows.some((row) => row.unit_price === null)
  const weightedUnitPrice = !hasInvalidRatio && !hasMissingPrice
    ? roundMoney(rows.reduce((sum, row) => sum + (row.unit_price ?? 0) * row.ratio_percent / 100, 0))
    : null

  return {
    components: rows,
    total_amount_hkd: hasValidWeight && !hasInvalidRatio && !hasMissingPrice
      ? roundMoney(rows.reduce((sum, row) => sum + (row.amount_hkd ?? 0), 0))
      : null,
    weighted_unit_price: weightedUnitPrice,
    has_missing_price: hasMissingPrice,
    has_invalid_ratio: hasInvalidRatio,
  }
}

function createActualMaterialCostSnapshot(
  breakdown: MoldingSampleMaterialCostBreakdown,
): MoldingSampleActualMaterialCostComponent[] | null {
  if (
    breakdown.total_amount_hkd === null
    || breakdown.has_missing_price
    || breakdown.has_invalid_ratio
    || breakdown.components.some((component) => component.unit_price === null || component.amount_hkd === null)
  ) {
    return null
  }

  return breakdown.components.map((component) => ({
    material: component.material,
    source_type: component.source_type,
    ratio_percent: component.ratio_percent,
    weight_kg: component.weight_kg,
    unit_price: component.unit_price as number,
    amount_hkd: component.amount_hkd as number,
  }))
}

export function resolveActualMaterialCostBreakdown(
  item: MoldingSampleItem,
  prices: MoldingSampleMaterialPrice[],
): MoldingSampleResolvedActualMaterialCostBreakdown {
  const snapshot = item.actual_material_cost_components
  const hasValidSnapshot = Boolean(
    snapshot?.length
    && Math.abs(snapshot.reduce((sum, component) => sum + Number(component.ratio_percent), 0) - 100) <= 0.01
    && snapshot.every((component) =>
      component.material.trim() !== ''
      && (component.source_type === 'virgin' || component.source_type === 'runner')
      && Number.isFinite(Number(component.ratio_percent))
      && Number(component.ratio_percent) > 0
      && Number.isFinite(Number(component.weight_kg))
      && Number(component.weight_kg) >= 0
      && Number.isFinite(Number(component.unit_price))
      && Number(component.unit_price) > 0
      && Number.isFinite(Number(component.amount_hkd))
      && Number(component.amount_hkd) >= 0,
    ),
  )

  if (snapshot?.length && hasValidSnapshot) {
    const storedAmount = Number(item.actual_amount_hkd)
    const hasStoredAmount = item.actual_amount_hkd !== null
      && item.actual_amount_hkd !== undefined
      && Number.isFinite(storedAmount)
    return {
      components: snapshot.map((component) => ({ ...component })),
      total_amount_hkd: hasStoredAmount
        ? roundMoney(storedAmount)
        : roundMoney(snapshot.reduce((sum, component) => sum + component.amount_hkd, 0)),
      weighted_unit_price: roundMoney(snapshot.reduce(
        (sum, component) => sum + component.unit_price * component.ratio_percent / 100,
        0,
      )),
      has_missing_price: false,
      has_invalid_ratio: false,
      source: 'persisted',
    }
  }

  const estimate = calculateMaterialCostBreakdown({
    components: resolveMaterialComponents(item),
    totalWeightKg: item.actual_weight_kg ?? item.collected_weight_kg,
    prices,
  })
  const storedAmount = Number(item.actual_amount_hkd)
  const hasStoredAmount = item.actual_amount_hkd !== null
    && item.actual_amount_hkd !== undefined
    && Number.isFinite(storedAmount)

  return {
    ...estimate,
    total_amount_hkd: hasStoredAmount ? roundMoney(storedAmount) : estimate.total_amount_hkd,
    source: 'estimated',
  }
}

export function resolveMaterialPrice(
  material: string,
  prices: MoldingSampleMaterialPrice[],
) {
  const components = normalizeMaterialComponents(material)
  if (!components.length) {
    return null
  }
  if (components.length > 1) {
    const breakdown = calculateMaterialCostBreakdown({ components, totalWeightKg: 1, prices })
    return breakdown.weighted_unit_price === null
      ? null
      : {
          material: formatMaterialComposition(components),
          unit_price: breakdown.weighted_unit_price,
          notes: '混合原料加权单价',
        }
  }

  const directPrice = findDirectMaterialPrice(material, prices)

  if (directPrice) {
    return directPrice
  }

  const breakdown = calculateMaterialCostBreakdown({ components, totalWeightKg: 1, prices })
  if (breakdown.weighted_unit_price === null) {
    return null
  }

  return {
    material: formatMaterialComposition(components),
    unit_price: breakdown.weighted_unit_price,
    notes: '混合原料加权单价',
  }
}

export function calculateExpectedMaterialAmountHkd(
  item: Pick<MoldingSampleItem, 'material' | 'material_components' | 'required_material_kg'>,
  prices: MoldingSampleMaterialPrice[],
) {
  if (item.required_material_kg === null || item.required_material_kg === undefined) {
    return null
  }

  const expectedWeightKg = Number(item.required_material_kg)
  return calculateMaterialCostBreakdown({
    components: resolveMaterialComponents(item),
    totalWeightKg: expectedWeightKg,
    prices,
  }).total_amount_hkd
}

export function calculateMoldingSampleItemCosts(
  item: MoldingSampleItem,
  prices: MoldingSampleMaterialPrice[],
  rmbToHkdRate: number,
  isExternalOrder: boolean,
): MoldingSampleItemCostResult {
  const actualWeightKg = isExternalOrder
    ? item.collected_weight_kg ?? item.required_material_kg ?? null
    : item.actual_weight_kg
  const materialBreakdown = calculateMaterialCostBreakdown({
    components: resolveMaterialComponents(item),
    totalWeightKg: actualWeightKg,
    prices,
  })
  const actualAmountHkd = materialBreakdown.total_amount_hkd
  const hasInjectionCost = item.injection_cost !== null
    && item.injection_cost !== undefined
    && Number.isFinite(Number(item.injection_cost))
  const injectionCostHkd = !isExternalOrder && hasInjectionCost
    ? roundMoney(Number(item.injection_cost) * rmbToHkdRate)
    : null

  return {
    actual_weight_kg: actualWeightKg,
    expected_amount_hkd: calculateExpectedMaterialAmountHkd(item, prices),
    actual_amount_hkd: actualAmountHkd,
    injection_cost_hkd: injectionCostHkd,
    exchange_rate_at_save: injectionCostHkd !== null ? rmbToHkdRate : null,
    material_unit_price: materialBreakdown.weighted_unit_price,
    actual_material_cost_components: createActualMaterialCostSnapshot(materialBreakdown),
  }
}

export function applyCostPreviewToItems(
  items: MoldingSampleItem[],
  prices: MoldingSampleMaterialPrice[],
  rmbToHkdRate: number,
  isExternalOrder: boolean,
  forceRecalculateMaterialAmount = false,
): MoldingSampleItem[] {
  return items.map((item) => {
    const costs = calculateMoldingSampleItemCosts(item, prices, rmbToHkdRate, isExternalOrder)
    const shouldFillMaterialAmount = forceRecalculateMaterialAmount
      || item.actual_amount_hkd === null
      || item.actual_amount_hkd === undefined

    return {
      ...item,
      actual_weight_kg: isExternalOrder ? costs.actual_weight_kg : item.actual_weight_kg,
      actual_amount_hkd: shouldFillMaterialAmount ? costs.actual_amount_hkd : item.actual_amount_hkd,
      actual_material_cost_components: shouldFillMaterialAmount
        ? costs.actual_material_cost_components ?? undefined
        : item.actual_material_cost_components,
      injection_cost_hkd: costs.injection_cost_hkd,
      exchange_rate_at_save: costs.exchange_rate_at_save,
    }
  })
}

function getReportMaterialWeight(order: MoldingSampleOrder, item: MoldingSampleItem) {
  return isExternalMoldingSampleOrder(order)
    ? item.actual_weight_kg ?? item.collected_weight_kg ?? item.required_material_kg ?? null
    : item.actual_weight_kg
}

function getReportInjectionCost(order: MoldingSampleOrder, item: MoldingSampleItem) {
  if (isExternalMoldingSampleOrder(order)) {
    return 0
  }

  if (item.injection_cost_hkd !== null && item.injection_cost_hkd !== undefined) {
    return item.injection_cost_hkd
  }

  return item.injection_cost ?? 0
}

export function buildMoldingSampleReportSummary(
  order: MoldingSampleOrder,
  items: MoldingSampleItem[],
  prices: MoldingSampleMaterialPrice[] = [],
): MoldingSampleReportSummary {
  const isExternalOrder = isExternalMoldingSampleOrder(order)
  const materialRows = new Map<string, MoldingSampleMaterialReportRow>()
  const injectionFeeRows: MoldingSampleInjectionFeeRow[] = []
  const itemRows: MoldingSampleReportItemRow[] = []
  const missingPriceItemIds: string[] = []
  const missingActualWeightItemIds: string[] = []
  const missingInjectionCostItemIds: string[] = []

  for (const item of items) {
    const materialWeight = getReportMaterialWeight(order, item)
    const materialCost = item.actual_amount_hkd ?? 0
    const materialBreakdown = resolveActualMaterialCostBreakdown(item, prices)
    const injectionCost = getReportInjectionCost(order, item)
    const hasMaterialWeight = Number(materialWeight) > 0
    const isMissingPrice = hasMaterialWeight && (item.actual_amount_hkd === null || item.actual_amount_hkd === undefined)
    const isMissingActualWeight = !isExternalOrder && !hasMaterialWeight
    const isMissingInjectionCost = !isExternalOrder
      && item.injection_cost_hkd === null
      && item.injection_cost === null

    if (isMissingPrice) {
      missingPriceItemIds.push(item.id)
    }

    if (isMissingActualWeight) {
      missingActualWeightItemIds.push(item.id)
    }

    if (isMissingInjectionCost) {
      missingInjectionCostItemIds.push(item.id)
    }

    for (const component of materialBreakdown.components) {
      const materialKey = `${component.material}\u0000${component.source_type}`
      let materialRow = materialRows.get(materialKey)

      if (!materialRow) {
        materialRow = {
          material: component.material || '未填写原料',
          source_type: component.source_type,
          line_count: 0,
          total_weight_kg: 0,
          total_material_cost_hkd: 0,
          missing_price_item_ids: [],
        }
      }
      materialRow.line_count += 1
      materialRow.total_weight_kg = roundMoney(materialRow.total_weight_kg + component.weight_kg)
      materialRow.total_material_cost_hkd = roundMoney(
        materialRow.total_material_cost_hkd
        + (component.amount_hkd ?? (materialBreakdown.components.length === 1 ? materialCost : 0)),
      )

      if (isMissingPrice || component.unit_price === null) {
        materialRow.missing_price_item_ids.push(item.id)
      }

      materialRows.set(materialKey, materialRow)
    }

    if (!isExternalOrder) {
      injectionFeeRows.push({
        item_id: item.id,
        injection_cost: item.injection_cost,
        injection_cost_hkd: item.injection_cost_hkd,
        is_missing: isMissingInjectionCost,
      })
    }

    itemRows.push({
      item_id: item.id,
      mold_id: item.mold_id,
      mold_name: item.mold_name,
      material: item.material,
      actual_weight_kg: materialWeight,
      actual_amount_hkd: item.actual_amount_hkd,
      injection_cost: item.injection_cost,
      injection_cost_hkd: item.injection_cost_hkd,
      total_cost: roundMoney(materialCost + injectionCost),
    })
  }

  const totalMaterialCost = roundMoney(items.reduce((sum, item) => sum + (item.actual_amount_hkd ?? 0), 0))
  const totalInjectionCost = roundMoney(
    injectionFeeRows.reduce((sum, row) => sum + (row.injection_cost_hkd ?? row.injection_cost ?? 0), 0),
  )
  const hasMissingPrice = missingPriceItemIds.length > 0
  const hasMissingActualWeight = missingActualWeightItemIds.length > 0
  const hasMissingInjectionCost = missingInjectionCostItemIds.length > 0
  const archiveReady = order.status === '已完成'
    && !hasMissingPrice
    && !hasMissingActualWeight
    && !hasMissingInjectionCost

  return {
    total_material_cost: totalMaterialCost,
    total_injection_cost: isExternalOrder ? 0 : totalInjectionCost,
    total_cost: roundMoney(totalMaterialCost + (isExternalOrder ? 0 : totalInjectionCost)),
    has_missing_price: hasMissingPrice,
    has_missing_actual_weight: hasMissingActualWeight,
    has_missing_injection_cost: hasMissingInjectionCost,
    missing_price_item_ids: missingPriceItemIds,
    missing_actual_weight_item_ids: missingActualWeightItemIds,
    missing_injection_cost_item_ids: missingInjectionCostItemIds,
    material_rows: Array.from(materialRows.values()),
    injection_fee_rows: injectionFeeRows,
    item_rows: itemRows,
    archive_ready: archiveReady,
    archive_message: archiveReady ? '费用资料齐全，可以归档。' : '费用资料未齐，暂缓归档。',
  }
}

export function generateRequisitionNumber(
  date: string,
  requisitions: Pick<{ req_number: string }, 'req_number'>[],
) {
  const dateKey = date.replaceAll('-', '')
  const maxSequence = requisitions.reduce((max, requisition) => {
    const match = requisition.req_number.match(new RegExp(`^LL-${dateKey}-(\\d{3})$`))

    return match ? Math.max(max, Number(match[1])) : max
  }, 0)

  return `LL-${dateKey}-${String(maxSequence + 1).padStart(3, '0')}`
}

export function normalizeMoldingSamplePricingSettings(
  prices: MoldingSampleMaterialPriceInput[],
  rmbToHkdRate: string | number | null | undefined,
  fallbackRate: number,
): MoldingSamplePricingSettings {
  const errors: string[] = []
  const seenMaterials = new Set<string>()
  const normalizedPrices = prices
    .map((price) => ({
      material: price.material.trim(),
      unit_price: price.unit_price ?? price.unitPriceHkdPerLb,
      notes: (price.notes ?? '').trim(),
    }))
    .filter((price) => price.material !== '')
    .map((price) => {
      const normalizedKey = normalizeMaterialName(price.material)
      const parsedUnitPrice = Number(price.unit_price)
      const unitPrice = Number.isFinite(parsedUnitPrice) && parsedUnitPrice > 0
        ? roundMoney(parsedUnitPrice)
        : 0

      if (seenMaterials.has(normalizedKey)) {
        errors.push(`重复原料：${price.material}`)
      }
      else {
        seenMaterials.add(normalizedKey)
      }

      if (!(unitPrice > 0)) {
        errors.push(`${price.material} 原料单价必须大于 0`)
      }

      return {
        material: price.material,
        unit_price: unitPrice,
        notes: price.notes,
      }
    })
  const parsedRate = Number(rmbToHkdRate)
  const normalizedRate = Number.isFinite(parsedRate) && parsedRate > 0
    ? roundMoney(parsedRate)
    : fallbackRate

  if (!(Number.isFinite(parsedRate) && parsedRate > 0)) {
    errors.push(`汇率必须大于 0，已保留原汇率 ${fallbackRate}`)
  }

  return {
    prices: normalizedPrices,
    rmb_to_hkd_rate: normalizedRate,
    errors,
  }
}

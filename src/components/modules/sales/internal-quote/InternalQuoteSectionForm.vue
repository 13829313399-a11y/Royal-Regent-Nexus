<script setup lang="ts">
import { buzzBeeTemplateProfiles } from '@/lib/customerPriceConverters/buzzbeeTemplate'
import { Copy, Eye, Plus, Trash2 } from '@lucide/vue'
import { computed, ref, watchEffect } from 'vue'
import { canonicalizeMoldingReferences, moldingMaterialReferences as getMoldingMaterials, moldingMachineReferences as getMoldingMachines, moldingMaterialOptions, selectedMoldingMaterial, selectedMoldingMachine, normalizedReferenceToken, type MoldingMaterialSelection, type MoldingMaterialReference } from '@/lib/internalQuoteMoldingReferences'
import { internalQuoteAttachmentPreviewUrl } from '@/api/internalQuote'
import InternalQuotePricingFields from './InternalQuotePricingFields.vue'
import InternalQuoteDickieSales from './InternalQuoteDickieSales.vue'
import InternalQuoteDickieMolds from './InternalQuoteDickieMolds.vue'
import { calculateAssemblyCategoryLaborHkd, calculateAssemblyGroupLaborHkd, calculateAssemblyGroupPeople, calculateCartonCuft, calculateCartonPriceHkd, calculateCartonUnitCostHkd, calculateElectronicAmountHkd, calculateElectronicQuickSubtotalRmb, calculateElectronicQuickUnitPriceHkd, calculateElectronicSummary, calculateElectronicUnitPriceHkd, calculateElectronicUnitPriceRmb, calculateEngineeringMaterialAmountHkd, calculateEngineeringMaterialEffectiveUnitHkd, calculateEngineeringMaterialUnitHkd, calculateEngineeringMaterialUnitRmb, calculateEngineeringMoldAllocation, calculateEngineeringMoldPriceHkd, calculateFlatCardPriceHkd, calculateHairRowAmountHkd, calculateHairTotalHkd, calculateJustPlayAdhesivePackagingCostHkd, calculateJustPlayPaperPalletCostHkd, calculatePackagingMaterialAmountHkd, calculatePackagingMaterialEffectiveUnitHkd, calculatePackagingMaterialUnitHkd, calculatePackagingMaterialUnitRmb, calculatePaintingOperationTotals, calculatePaintingQuickPaintTaxHkd, calculatePaintingQuickTotalHkd, calculatePaintingRowAmount, calculatePaintingRowSplit, calculatePaintingTotalHkd, calculateSalesFreightOptions, calculateSalesTestingFeeUnitUsd, calculateSewingBasePriceHkd, calculateSewingGroupTotalHkd, calculateSewingQuickTotalHkd, calculateSewingRowTotalHkd, calculateSewingTotalHkd, calculateSlushRowAmount, calculateSlushTotalHkd, calculateSlushTotalRmb, createDefaultSalesCarton, dimensionValueFromInches, dimensionValueToInches, electronicExtraRmb, normalizeSalesDimensionUnit, paintingOperationLabels, salesFreightCalculationModes, salesFreightCapacityDefinitions, salesFreightReferenceRoutesFromSnapshot, sewingGroupHasLaborLine, type AssemblyGroup, type AssemblyPayload, type ElectronicComponentRow, type ElectronicPayload, type ElectronicQuickQuoteRow, type EngineeringMaterialRow, type EngineeringMoldPartRow, type EngineeringMoldRow, type EngineeringPayload, type HairPayload, type MoldingPayload, type PaintingOperationCode, type PaintingPayload, type SalesCartonRow, type SalesDimensionUnit, type SalesDimensions, type SalesPackagingMaterialRow, type SalesPayload, type SewingGroup, type SewingPayload, type SlushPayload, type UnitPriceSourceCurrency } from '@/lib/internalQuoteSectionPayload'
import { getInternalQuoteFormBlocks, type InternalQuoteFormBlock } from '@/lib/internalQuoteBlockProgress'
import { calculateJustPlayMainCartonDimensions, justPlayCartonState, normalizeJustPlayCartonInputs, calculateJustPlayCartonsPerPallet, normalizeJustPlayPackagingInputs, justPlayPackagingInputsValid, previewEngineeringMoldPartSplit, type JustPlayPackagingInputs, type JustPlayCartonInputs } from '@/lib/internalQuoteSectionPayload'
import type { InternalQuoteAttachmentRecord, InternalQuoteSectionCode } from '@/types/internalQuoteDesk'
import type { QuotePricingMetadata, SalesPricingComponent } from '@/lib/internalQuoteSectionPayload'
import { calculateCustomerSuppliedFeeHkd, type CustomerSuppliedMaterialRow } from '@/lib/internalQuoteSectionPayload'

const props = defineProps<{ code: InternalQuoteSectionCode; quoteId?: string; factoryId?: string; attachments?: InternalQuoteAttachmentRecord[]; disabled?: boolean; customer?: string; rmbHkdRate?: number; referenceSnapshot?: Record<string, unknown>; calculation?: Record<string, unknown>; pricingMode?: 'standard' | 'component'; pricingComponents?: SalesPricingComponent[]; activePricingComponentId?: string; mainMarkup?: number }>()
const model = defineModel<Record<string, unknown>>({ required: true })
const moldRowKeys = new WeakMap<object, number>()
let nextMoldRowKey = 0
function moldRowKey(row: object) {
  if (!moldRowKeys.has(row)) moldRowKeys.set(row, ++nextMoldRowKey)
  return moldRowKeys.get(row)!
}
const emit = defineEmits<{
  'block-progress': [blocks: InternalQuoteFormBlock[]]
  'preview-attachment': [attachment: InternalQuoteAttachmentRecord]
}>()

const sales = computed(() => model.value as unknown as SalesPayload)
const customerSuppliedRows = computed(() => (sales.value.customer_supplied_materials ?? []).filter(belongsToCurrentPricingComponent))
const customerSuppliedTotal = computed(() => customerSuppliedRows.value.reduce((total, row) => total + calculateCustomerSuppliedFeeHkd(row), 0))
function addCustomerSuppliedMaterial() {
  sales.value.customer_supplied_materials ??= []
  sales.value.customer_supplied_materials.push(assignCurrentPricingComponent<CustomerSuppliedMaterialRow>({ item: '', unit_price_hkd: 0, fee_rate_percent: 0 }))
}
const justPlayCartonAutomatic = computed(() => props.code === 'sales' && (props.pricingMode ?? sales.value.pricing_mode) === 'component')
watchEffect(() => {
  if (!justPlayCartonAutomatic.value) return
  const mainCarton = sales.value.cartons[0]
  if (!mainCarton) return
  const derived = calculateJustPlayMainCartonDimensions(sales.value)
  for (const key of ['length_in', 'width_in', 'height_in'] as const) {
    if (mainCarton[key] !== derived[key]) mainCarton[key] = derived[key]
  }
})
const hasInnerCarton = computed(() => sales.value.cartons.length > 1)
const innerPaperPriceFactor = computed<number>({
  get: () => {
    const mainFactor = Number(sales.value.paper_price_factor)
    const fallback = Number.isFinite(mainFactor) && mainFactor > 0 ? mainFactor : 2.75
    if (!hasInnerCarton.value) return fallback
    const override = Number(sales.value.inner_paper_price_factor)
    return Number.isFinite(override) && override > 0 ? override : fallback
  },
  set: (value) => {
    if (!hasInnerCarton.value) return
    const parsed = Number(value)
    if (Number.isFinite(parsed) && parsed > 0) sales.value.inner_paper_price_factor = parsed
    else delete sales.value.inner_paper_price_factor
  },
})
const flatCardPriceFactor = computed<number>({
  get: () => {
    const override = Number(sales.value.flat_card_price_factor)
    if (Number.isFinite(override) && override > 0) return override
    const cartonFactor = Number(sales.value.paper_price_factor)
    return Number.isFinite(cartonFactor) && cartonFactor > 0 ? cartonFactor : 2.75
  },
  set: (value) => {
    const parsed = Number(value)
    if (Number.isFinite(parsed) && parsed > 0) sales.value.flat_card_price_factor = parsed
    else delete sales.value.flat_card_price_factor
  },
})
const engineering = computed(() => model.value as unknown as EngineeringPayload)
const electronic = computed(() => model.value as unknown as ElectronicPayload)
const molding = computed(() => model.value as unknown as MoldingPayload)
const painting = computed(() => model.value as unknown as PaintingPayload)
const slush = computed(() => model.value as unknown as SlushPayload)
const sewing = computed(() => model.value as unknown as SewingPayload)
const hair = computed(() => model.value as unknown as HairPayload)
const assembly = computed(() => model.value as unknown as AssemblyPayload)
const effectivePricingComponents = computed(() => props.pricingComponents ?? (props.code === 'sales' ? sales.value.pricing_components ?? [] : []))
const pricingComponentIds = computed(() => new Set(effectivePricingComponents.value.map((component) => component.id)))
const currentPricingComponentId = computed(() => {
  if (props.pricingMode !== 'component') return ''
  if (props.activePricingComponentId && pricingComponentIds.value.has(props.activePricingComponentId)) return props.activePricingComponentId
  return effectivePricingComponents.value[0]?.id ?? ''
})
function resolvedPricingComponentId(meta: QuotePricingMetadata) {
  const id = String(meta.pricing_component_id ?? '')
  return pricingComponentIds.value.has(id) ? id : effectivePricingComponents.value[0]?.id ?? ''
}
function belongsToCurrentPricingComponent(meta: QuotePricingMetadata) {
  return props.pricingMode !== 'component' || resolvedPricingComponentId(meta) === currentPricingComponentId.value
}
function assignCurrentPricingComponent<T extends object>(row: T): T & QuotePricingMetadata {
  if (props.pricingMode === 'component' && currentPricingComponentId.value) {
    (row as QuotePricingMetadata).pricing_component_id = currentPricingComponentId.value
  }
  return row as T & QuotePricingMetadata
}
function removeItem<T>(items: T[], row: T) {
  const index = items.indexOf(row)
  if (index >= 0) items.splice(index, 1)
}
const assemblyGroups = computed(() => assembly.value.groups.filter((group) => group.category === 'assembly' && belongsToCurrentPricingComponent(group)))
const packagingGroups = computed(() => assembly.value.groups.filter((group) => group.category === 'packaging'))
const visibleAssemblySummaryGroups = computed(() => [...assemblyGroups.value, ...packagingGroups.value])
type PricingItem = { label: string; meta: QuotePricingMetadata; allowMarkupOverride: boolean }
function electronicPricingItems(rows: ElectronicComponentRow[], prefix = ''): PricingItem[] {
  return rows.flatMap((row, index) => {
    const label = `${prefix}${row.item.trim() || `电子件 ${index + 1}`}`
    return [
      { label, meta: row, allowMarkupOverride: true },
      ...electronicPricingItems(row.children ?? [], `${label} / `),
    ]
  })
}
const pricingItems = computed<PricingItem[]>(() => {
  const sectionCode = props.code
  if (props.pricingMode !== 'component' && sectionCode === 'molding') return []
  if (sectionCode === 'engineering') return engineering.value.materials.map((row, index) => ({ label: row.item.trim() || `工程明细 ${index + 1}`, meta: row, allowMarkupOverride: true }))
  if (sectionCode === 'electronic') return electronic.value.quote_mode === 'quick'
    ? electronic.value.quick_quotes.map((row, index) => ({ label: row.item.trim() || `电子快捷报价 ${index + 1}`, meta: row, allowMarkupOverride: true }))
    : electronicPricingItems(electronic.value.components)
  if (sectionCode === 'molding') return [
    ...molding.value.injection_lines.map((row, index) => ({ label: row.item.trim() || `胶件 ${index + 1}`, meta: row, allowMarkupOverride: false })),
    ...molding.value.blow_lines.map((row, index) => ({ label: row.item.trim() || `吹气件 ${index + 1}`, meta: row, allowMarkupOverride: false })),
  ]
  if (sectionCode === 'painting') return painting.value.quote_mode === 'quick'
    ? [{ label: '喷油快捷报价', meta: painting.value.quick_quote, allowMarkupOverride: true }]
    : painting.value.rows.map((row, index) => ({ label: row.name.trim() || row.position.trim() || `喷油明细 ${index + 1}`, meta: row, allowMarkupOverride: true }))
  if (sectionCode === 'slush') return slush.value.lines.map((row, index) => ({ label: row.item.trim() || `搪胶明细 ${index + 1}`, meta: row, allowMarkupOverride: true }))
  if (sectionCode === 'hair') return hair.value.lines.map((row, index) => ({ label: row.name.trim() || `车发明细 ${index + 1}`, meta: row, allowMarkupOverride: true }))
  if (sectionCode === 'sewing') return sewing.value.quote_mode === 'quick'
    ? sewing.value.quick_quotes.map((row, index) => ({ label: row.doll_name.trim() || `车缝快捷报价 ${index + 1}`, meta: row, allowMarkupOverride: true }))
    : sewing.value.groups.map((group, index) => ({ label: group.name.trim() || `车缝产品组 ${index + 1}`, meta: group, allowMarkupOverride: true }))
  if (sectionCode === 'assembly') return assembly.value.groups.map((group, index) => ({ label: group.name.trim() || `${group.category === 'packaging' ? '包装' : '组装'}产品 ${index + 1}`, meta: group, allowMarkupOverride: true }))
  return [
    ...sales.value.packaging_materials.map((row, index) => ({ label: row.item.trim() || `包装材料 ${index + 1}`, meta: row, allowMarkupOverride: true })),
    ...sales.value.cartons.map((row, index) => ({ label: row.item.trim() || `纸箱 ${index + 1}`, meta: row, allowMarkupOverride: true })),
  ]
})
function moldImageAttachments(row: EngineeringMoldRow) {
  const ids = new Set(row.image_attachment_ids ?? [])
  const references = new Set(String(row.image_reference || '').split(/[；;]/).map((item) => item.trim()).filter(Boolean))
  return (props.attachments ?? []).filter((attachment) => attachment.contentType.startsWith('image/') && (ids.has(attachment.id) || (!ids.size && references.has(attachment.fileName))))
}
function attachmentPreviewUrl(attachmentId: string) {
  return internalQuoteAttachmentPreviewUrl(props.quoteId ?? '', attachmentId)
}
function importSourceAttachment(importType: string) {
  return (props.attachments ?? []).find((attachment) => attachment.isImportSource && attachment.importType === importType)
}
function previewImportSource(importType: string) {
  const attachment = importSourceAttachment(importType)
  if (attachment) emit('preview-attachment', attachment)
}
const assemblyLaborTotal = computed(() => assemblyGroups.value.reduce((total, group) => total + calculateAssemblyGroupLaborHkd(group, assembly.value.labor_base_hkd), 0))
const packagingLaborTotal = computed(() => calculateAssemblyCategoryLaborHkd(assembly.value, 'packaging'))
const allAssemblyLaborTotal = computed(() => assemblyLaborTotal.value + packagingLaborTotal.value)
// 所有客户共用内部核价字段；仅在对应客户单据上显示报客模板专属字段。
// 这些字段不参与内部成本公式，也不改变统一工作簿基础布局。
const normalizedCustomer = computed(() => String(props.customer ?? '').trim().toLowerCase().replace(/[\s_-]+/g, ''))
const isBuzzBee = computed(() => normalizedCustomer.value === 'buzzbee')
const isDisney = computed(() => ['disney', '迪士尼'].includes(normalizedCustomer.value))
const isDickie = computed(() => props.factoryId === 'huaxing' && ['dickie', 'dicky'].includes(normalizedCustomer.value))
const isCaixing = computed(() => ['caixing', '彩星'].includes(normalizedCustomer.value))
const isThreeSixty = computed(() => ['360', 'threesixty'].includes(normalizedCustomer.value))
const referenceFreightRoutes = computed(() => salesFreightReferenceRoutesFromSnapshot(props.referenceSnapshot?.freight))
const formBlocks = computed(() => getInternalQuoteFormBlocks(
  props.code,
  props.code === 'sales' && props.pricingMode ? { ...model.value, pricing_mode: props.pricingMode } : model.value,
  referenceFreightRoutes.value.map(({ capacityKey }) => capacityKey),
))
watchEffect(() => emit('block-progress', formBlocks.value))
function blockDomId(id: string) { return `internal-quote-${props.code}-${id}` }
const operationCodes = Object.keys(paintingOperationLabels) as PaintingOperationCode[]
const visiblePaintingRows = computed(() => painting.value.rows.filter(belongsToCurrentPricingComponent))
const visiblePaintingPayload = computed<PaintingPayload>(() => ({ ...painting.value, rows: visiblePaintingRows.value }))
const paintingOperationTotals = computed(() => calculatePaintingOperationTotals(visiblePaintingPayload.value))
const paintingSplitTotals = computed(() => visiblePaintingRows.value.reduce((sum, row) => {
  const split = calculatePaintingRowSplit(row)
  return { paint: sum.paint + (split.paint ?? 0), labor: sum.labor + (split.labor ?? 0), valid: sum.valid && split.valid }
}, { paint: 0, labor: 0, valid: true }))
const paintingTotal = computed(() => calculatePaintingTotalHkd(visiblePaintingPayload.value))
const paintingQuickPaintTax = computed(() => calculatePaintingQuickPaintTaxHkd(painting.value))
const paintingQuickTotal = computed(() => calculatePaintingQuickTotalHkd(painting.value))
const visibleSlushRows = computed(() => slush.value.lines.filter(belongsToCurrentPricingComponent))
const visibleHairRows = computed(() => hair.value.lines.filter(belongsToCurrentPricingComponent))
const visibleSewingGroups = computed(() => sewing.value.groups.filter(belongsToCurrentPricingComponent))
const visibleSewingQuickRows = computed(() => sewing.value.quick_quotes.filter(belongsToCurrentPricingComponent))
const slushTotalHkd = computed(() => calculateSlushTotalHkd({ ...slush.value, lines: visibleSlushRows.value }))
const slushTotalRmb = computed(() => calculateSlushTotalRmb({ ...slush.value, lines: visibleSlushRows.value }, props.rmbHkdRate))
const hairTotalHkd = computed(() => calculateHairTotalHkd({ ...hair.value, lines: visibleHairRows.value }))
const sewingTotalHkd = computed(() => calculateSewingTotalHkd({ ...sewing.value, groups: visibleSewingGroups.value }, props.rmbHkdRate))
const sewingQuickTotalHkd = computed(() => calculateSewingQuickTotalHkd({ ...sewing.value, quick_quotes: visibleSewingQuickRows.value }))
const engineeringMaterialCategories: EngineeringMaterialRow['auxiliary_category'][] = ['吸塑', '胶袋', '彩盒/内卡', '电池', '利宝', '电镀', '其他外购']
const hardwareRows = computed(() => engineering.value.materials.filter((row) => row.category === 'hardware' && belongsToCurrentPricingComponent(row)))
const auxiliaryRows = computed(() => engineering.value.materials.filter((row) => row.category === 'auxiliary' && belongsToCurrentPricingComponent(row)))
const hardwareTotal = computed(() => hardwareRows.value.reduce((total, row) => total + calculateEngineeringMaterialAmountHkd(row, props.rmbHkdRate), 0))
const auxiliaryTotal = computed(() => auxiliaryRows.value.reduce((total, row) => total + calculateEngineeringMaterialAmountHkd(row, props.rmbHkdRate), 0))
const visibleEngineeringMolds = computed(() => engineering.value.molds.filter(belongsToCurrentPricingComponent))
const moldQuoteTotalRmb = computed(() => visibleEngineeringMolds.value.reduce((total, row) => total + Number(row.cost_rmb || 0), 0))
const moldQuoteTotalHkd = computed(() => visibleEngineeringMolds.value.reduce((total, row) => total + calculateEngineeringMoldPriceHkd(row, props.rmbHkdRate), 0))
const moldAllocation = computed(() => calculateEngineeringMoldAllocation(engineering.value))
const visibleElectronicQuickRows = computed(() => electronic.value.quick_quotes.filter(belongsToCurrentPricingComponent))
const visibleElectronicComponents = computed(() => electronic.value.components.filter(belongsToCurrentPricingComponent))
function visibleElectronicChildren(row: ElectronicComponentRow) { return row.children.filter(belongsToCurrentPricingComponent) }
const visibleElectronicPayload = computed<ElectronicPayload>(() => ({ ...electronic.value, quick_quotes: visibleElectronicQuickRows.value, components: visibleElectronicComponents.value.map((row) => ({ ...row, children: visibleElectronicChildren(row) })) }))
const electronicSummary = computed(() => calculateElectronicSummary(visibleElectronicPayload.value, props.rmbHkdRate))
const electronicQuickSubtotalRmb = computed(() => calculateElectronicQuickSubtotalRmb(visibleElectronicPayload.value))
const electronicQuickSubtotalHkd = computed(() => visibleElectronicQuickRows.value.reduce(
  (total, row) => total + calculateElectronicQuickUnitPriceHkd(row, props.rmbHkdRate),
  0,
))
const injectionLossRate = computed<number>({
  get: () => Number(molding.value.injection_loss_rate_percent ?? 3),
  set: (value) => {
    const parsed = Number(value)
    const rate = Number.isFinite(parsed) && parsed >= 0 ? parsed : 3
    molding.value.injection_loss_rate_percent = rate
    for (const row of molding.value.injection_lines) row.loss_rate_percent = rate
  },
})
const engineeringSyncedInjectionCount = computed(() => molding.value.injection_lines.filter((row) => Boolean(row.engineering_source_key) && !row.engineering_sync_disabled).length)
function injectionFieldLocked(row: MoldingPayload['injection_lines'][number], field: string) {
  return Boolean(!row.engineering_sync_disabled && row.engineering_source_key && row.engineering_synced_fields?.includes(field))
}
type InjectionRow = MoldingPayload['injection_lines'][number]
function finiteNumber(value: unknown, fallback = 0) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}
const moldingMaterialReferences = computed(() => getMoldingMaterials(props.referenceSnapshot))
const moldingMachineReferences = computed(() => getMoldingMachines(props.referenceSnapshot))
const moldingMaterialNames = computed(() => [...new Set(moldingMaterialReferences.value.map((row) => row.material))])
function materialOptions(row: MoldingMaterialSelection) {
  return moldingMaterialOptions(row, moldingMaterialReferences.value)
}
function selectedMaterialReference(row: MoldingMaterialSelection) {
  return selectedMoldingMaterial(row, moldingMaterialReferences.value)
}
function selectMaterial(row: MoldingMaterialSelection) {
  const candidates = moldingMaterialReferences.value.filter((item) => normalizedReferenceToken(item.material) === normalizedReferenceToken(row.material))
  if (!candidates.some((item) => normalizedReferenceToken(item.grade) === normalizedReferenceToken(row.grade))) row.grade = candidates.length === 1 ? candidates[0].grade : ''
}
function materialReferenceValue(item: MoldingMaterialReference) {
  return JSON.stringify([item.material, item.grade])
}
function selectMaterialGrade(row: MoldingMaterialSelection, value: string) {
  const selected = moldingMaterialReferences.value.find((item) => materialReferenceValue(item) === value)
  if (!selected) return
  row.material = selected.material
  row.grade = selected.grade
}
function selectedMachineReference(row: InjectionRow) {
  return selectedMoldingMachine(row, moldingMachineReferences.value)
}
function selectMachine(row: InjectionRow, range: string) {
  const selected = moldingMachineReferences.value.find((item) => item.range === range)
  row.machine_code = range
  if (selected) row.machine_name = selected.machine
}
watchEffect(() => {
  if (props.code === 'molding' && !props.disabled) canonicalizeMoldingReferences(molding.value, props.referenceSnapshot)
})
function injectionPreview(row: InjectionRow) {
  const material = selectedMaterialReference(row)
  const machine = selectedMachineReference(row)
  const netWeight = Math.max(0, finiteNumber(row.net_weight_g))
  const lossRate = Math.max(0, finiteNumber(row.loss_rate_percent, injectionLossRate.value))
  const sets = finiteNumber(row.sets)
  const targetOutput = finiteNumber(row.target_output)
  const quantity = Math.max(0, finiteNumber(row.quantity, 1))
  const lossWeightG = netWeight * (1 + lossRate / 100)
  const materialCostHkd = material ? lossWeightG * material.priceHkdLb / 454 : undefined
  const moldingCostHkd = machine && sets > 0 && targetOutput > 0 ? machine.shiftPriceHkd / sets / targetOutput : undefined
  const unitAmountHkd = materialCostHkd !== undefined && moldingCostHkd !== undefined ? materialCostHkd + moldingCostHkd : undefined
  return {
    lossWeightG,
    materialPriceHkdG: material ? material.priceHkdLb / 454 : undefined,
    materialCostHkd,
    moldingCostHkd,
    unitAmountHkd,
    lineAmountHkd: unitAmountHkd === undefined ? undefined : unitAmountHkd * quantity,
  }
}
function injectionPreviewText(row: InjectionRow, key: 'materialPriceHkdG' | 'materialCostHkd' | 'moldingCostHkd' | 'unitAmountHkd' | 'lineAmountHkd') {
  const value = injectionPreview(row)[key]
  if (value !== undefined) return fixedDecimal(value, 3)
  if ((key === 'materialPriceHkdG' || key === 'materialCostHkd') && !selectedMaterialReference(row)) return '请选择具体料型'
  if ((key === 'moldingCostHkd' || key === 'unitAmountHkd' || key === 'lineAmountHkd') && !selectedMachineReference(row)) return '请选择机型'
  return '补全套数 / 目标数'
}
const visibleInjectionRows = computed(() => molding.value.injection_lines.filter(belongsToCurrentPricingComponent))
const visibleBlowRows = computed(() => molding.value.blow_lines.filter(belongsToCurrentPricingComponent))
const liveInjectionTotal = computed(() => visibleInjectionRows.value.reduce((total, row) => total + (injectionPreview(row).lineAmountHkd ?? 0), 0))
const liveInjectionWeightTotal = computed(() => visibleInjectionRows.value.reduce((total, row) => {
  const quantity = Math.max(0, finiteNumber(row.quantity, 1))
  return total + injectionPreview(row).lossWeightG * quantity
}, 0))
const liveInjectionMaterialTotal = computed(() => visibleInjectionRows.value.reduce((total, row) => {
  const quantity = Math.max(0, finiteNumber(row.quantity, 1))
  return total + (injectionPreview(row).materialCostHkd ?? 0) * quantity
}, 0))
const liveInjectionMoldingLaborTotal = computed(() => visibleInjectionRows.value.reduce((total, row) => {
  const quantity = Math.max(0, finiteNumber(row.quantity, 1))
  return total + (injectionPreview(row).moldingCostHkd ?? 0) * quantity
}, 0))

function blowPreview(row: MoldingPayload['blow_lines'][number]) {
  const material = selectedMaterialReference(row)
  const estimatedWeightG = Math.max(0, finiteNumber(row.estimated_weight_g))
  const laborHkd = Math.max(0, finiteNumber(row.labor_hkd))
  const burrHkd = Math.max(0, finiteNumber(row.burr_hkd))
  const profitMultiplier = Math.max(0, finiteNumber(row.profit_multiplier, 1.05))
  const quantity = Math.max(0, finiteNumber(row.quantity, 1))
  const materialCostHkd = material ? estimatedWeightG * material.priceHkdLb / 454 : undefined
  const subtotalHkd = materialCostHkd === undefined ? undefined : materialCostHkd + laborHkd + burrHkd
  const unitAmountHkd = subtotalHkd === undefined ? undefined : subtotalHkd * profitMultiplier
  return {
    materialPriceHkdLb: material?.priceHkdLb,
    materialCostHkd,
    subtotalHkd,
    unitAmountHkd,
    lineAmountHkd: unitAmountHkd === undefined ? undefined : unitAmountHkd * quantity,
  }
}

function blowPreviewText(
  row: MoldingPayload['blow_lines'][number],
  key: 'materialPriceHkdLb' | 'materialCostHkd' | 'subtotalHkd' | 'unitAmountHkd',
) {
  const value = blowPreview(row)[key]
  if (value !== undefined) return fixedDecimal(value, 3)
  return row.material ? '请选择具体料型' : '请填写用料'
}

const liveBlowTotal = computed(() => visibleBlowRows.value.reduce((total, row) => total + (blowPreview(row).lineAmountHkd ?? 0), 0))
const liveMoldingTotal = computed(() => liveInjectionTotal.value + liveBlowTotal.value)

function fixedDecimal(value: number, precision: number) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return (0).toFixed(precision)
  const factor = 10 ** precision
  const rounded = Math.sign(numeric) * Math.round((Math.abs(numeric) + Number.EPSILON) * factor) / factor
  return rounded.toFixed(precision)
}
function remove<T>(items: T[], index: number) { items.splice(index, 1) }
function engineeringMaterialRow(category: 'hardware' | 'auxiliary'): EngineeringMaterialRow {
  return { item: '', category, purpose: '', specification: '', quantity: 0, unit: '', unit_price_rmb: 0, ...(category === 'auxiliary' ? { unit_price_hkd: 0, unit_price_source_currency: 'RMB' as const } : {}), loss_rate: 1, material: '', surface_treatment: '', supplier: '', contact: '', auxiliary_category: category === 'hardware' ? '五金' : '其他外购', tax_rate_percent: category === 'hardware' ? 13 : 0, remark: '', disney_description: '', disney_section: 'product', disney_unit_price_usd: 0, disney_included: 1 }
}
function addEngineeringHardware() { engineering.value.materials.push(assignCurrentPricingComponent(engineeringMaterialRow('hardware'))) }
function addEngineeringAuxiliary() { engineering.value.materials.push(assignCurrentPricingComponent(engineeringMaterialRow('auxiliary'))) }
function removeEngineeringMaterial(row: EngineeringMaterialRow) {
  const index = engineering.value.materials.indexOf(row)
  if (index >= 0) engineering.value.materials.splice(index, 1)
}
function engineeringMoldPartRow(name = ''): EngineeringMoldPartRow {
  return { name, color: '', process: '', process_unit_price_hkd: 0, unit_net_weight_g: 0, output_count: 1, quantity: 1 }
}
function splitEngineeringMoldParts(row: EngineeringMoldRow) {
  if (!props.disabled) moldSplitTarget.value = row
}
const moldSplitTarget = ref<EngineeringMoldRow>()
const moldSplitPreview = computed(() => {
  const row = moldSplitTarget.value
  if (props.code !== 'engineering' || !row || !engineering.value.molds.includes(row)) return undefined
  return previewEngineeringMoldPartSplit(row.item || row.chinese_name, row.parts)
})
function confirmMoldPartSplit() {
  if (props.disabled || !moldSplitTarget.value || !moldSplitPreview.value?.nameCount) return
  moldSplitTarget.value.parts = moldSplitPreview.value.rows.map(({ part }) => part)
  moldSplitTarget.value = undefined
}
function addEngineeringMoldPart(row: EngineeringMoldRow) {
  row.parts.push(engineeringMoldPartRow())
}
function addEngineeringMold() {
  engineering.value.molds.push(assignCurrentPricingComponent({
    item: '', mold_no: '', chinese_name: '', mold_base_type: '', mold_base_material: '', structure: '', process: '', material: '', material_type: '', color: '', cavity: '', quantity: 1,
    net_weight_g: 0, cycle_time_seconds: 0, mold_size: '', mold_specification: '', image_reference: '', image_attachment_ids: [], cost_rmb: 0, remark: '', machine_code: '', target_output: 0, parts: [], source_row: 0,
    disney_mold_no: '', disney_parts: '', disney_material: '', disney_cavities: 0, disney_parts_per_shot: 0, disney_tool_cost_usd: 0,
    dickie_project_name_en: '', dickie_mold_no: '', dickie_parts_en: '', dickie_resin: '', dickie_mold_size: '', dickie_mold_material: '', dickie_cavities: 0, dickie_parts_per_shot: 0, dickie_mold_cost_hkd: 0, dickie_remark_en: '',
    caixing_tool_plan_ref: '', caixing_mold_cost_hkd: 0, caixing_customer_mold_cost_hkd: 0,
  }))
}
function addProductionMoldCost() { engineering.value.production_mold_costs.push({ item: '', cost_rmb: 0 }) }
function addSalesTestingFeeMoq() { (sales.value.testing_fee_moqs ??= []).push(0) }
function addSalesPackagingMaterial() { sales.value.packaging_materials.push({ item: '', specification: '', category: 'blister', quantity: 0, unit_price_rmb: 0, unit_price_hkd: 0, unit_price_source_currency: 'RMB', loss_rate: 1, tax_rate_percent: 0, remark: '', disney_description: '', disney_unit_price_usd: 0, disney_included: 1 }) }
function addSalesCarton() {
  if (!hasInnerCarton.value) {
    const mainFactor = Number(sales.value.paper_price_factor)
    sales.value.inner_paper_price_factor = Number.isFinite(mainFactor) && mainFactor > 0 ? mainFactor : 2.75
  }
  sales.value.cartons.push(createDefaultSalesCarton(`内纸箱 ${sales.value.cartons.length}`))
}
function removeSalesCarton(index: number) {
  if (index <= 0 || index >= sales.value.cartons.length) return
  sales.value.cartons.splice(index, 1)
  if (!hasInnerCarton.value) delete sales.value.inner_paper_price_factor
}
function addSalesFlatCard(cartonIndex: number) { sales.value.cartons[cartonIndex].flat_cards.push({ name: `平卡${sales.value.cartons[cartonIndex].flat_cards.length + 1}`, length_in: 0, width_in: 0, quantity: 1 }) }
function flatCardTotal(index: number) { return sales.value.cartons[index].flat_cards.reduce((total, row) => total + calculateFlatCardPriceHkd(row, flatCardPriceFactor.value), 0) }
function cartonPaperPriceFactor(index: number) { return index === 0 ? sales.value.paper_price_factor : innerPaperPriceFactor.value }
type SalesDimensionKey = keyof SalesDimensions
type CartonDimensionKey = 'length_in' | 'width_in' | 'height_in'
const colorBoxSizeUnit = computed<SalesDimensionUnit>({
  get: () => normalizeSalesDimensionUnit(sales.value.color_box_size_unit),
  set: (value) => { sales.value.color_box_size_unit = normalizeSalesDimensionUnit(value) },
})
const pdqSizeUnit = computed<SalesDimensionUnit>({
  get: () => normalizeSalesDimensionUnit(sales.value.pdq_size_unit),
  set: value => { sales.value.pdq_size_unit = normalizeSalesDimensionUnit(value) },
})
const justPlayCarton = computed(() => normalizeJustPlayCartonInputs(sales.value.justplay_carton))
const cartonState = computed(() => justPlayCartonState(sales.value))
const cartonDimensionAxes = [
  { key: 'length', label: '长度', count: 'length_count' },
  { key: 'width', label: '宽度', count: 'width_count' },
  { key: 'height', label: '高度', count: 'height_count' },
] as const
function updateJustPlayCarton(key: keyof JustPlayCartonInputs, event: Event) {
  const value = (event.target as HTMLInputElement).value
  sales.value.justplay_carton = { ...justPlayCarton.value, [key]: key === 'dimension_source' ? value : Number(value) }
}
function updatePdqDimension(key: SalesDimensionKey, event: Event) {
  sales.value.pdq_size_in = {
    ...(sales.value.pdq_size_in ?? { length: 0, width: 0, height: 0 }),
    [key]: dimensionValueToInches((event.target as HTMLInputElement).value, pdqSizeUnit.value),
  }
}
function cartonSizeUnit(carton: SalesCartonRow) { return normalizeSalesDimensionUnit(carton.size_unit) }
function dimensionInputValue(value: unknown, unit: SalesDimensionUnit) { return dimensionValueFromInches(value, unit) }
function updateColorBoxDimension(key: SalesDimensionKey, event: Event) {
  const value = (event.target as HTMLInputElement).value
  sales.value.color_box_size_in[key] = dimensionValueToInches(value, colorBoxSizeUnit.value)
}
function updateCartonDimension(carton: SalesCartonRow, key: CartonDimensionKey, event: Event) {
  if (justPlayCartonAutomatic.value && carton === sales.value.cartons[0]) return
  const value = (event.target as HTMLInputElement).value
  carton[key] = dimensionValueToInches(value, cartonSizeUnit(carton))
}
function updateCartonSizeUnit(carton: SalesCartonRow, event: Event) {
  carton.size_unit = normalizeSalesDimensionUnit((event.target as HTMLSelectElement).value)
}
const primaryCarton = computed(() => sales.value.cartons[0])
const justPlayPackagingInputs = computed(() => normalizeJustPlayPackagingInputs(sales.value.justplay_packaging))
type JustPlayExtraKey = 'adhesive_extra_hkd' | 'paper_pallet_extra_hkd'
const editingJustPlayExtra = ref<JustPlayExtraKey | null>(null)
function justPlayExtraDisplay(key: JustPlayExtraKey) {
  const value = justPlayPackagingInputs.value[key]
  return value === '' || editingJustPlayExtra.value === key ? value : value.toFixed(1)
}
function updateJustPlayPackagingInput(key: keyof JustPlayPackagingInputs, event: Event) {
  const raw = (event.target as HTMLInputElement).value
  sales.value.justplay_packaging = { ...justPlayPackagingInputs.value, [key]: raw === '' ? '' : Number(raw) }
}
function finishJustPlayExtra(key: JustPlayExtraKey, event: Event) {
  const input = event.target as HTMLInputElement
  const value = input.value === '' ? '' : Number(input.value)
  const rounded = value === '' || !Number.isFinite(value) ? '' : Math.round((value + Number.EPSILON) * 10) / 10
  sales.value.justplay_packaging = { ...justPlayPackagingInputs.value, [key]: rounded }
  editingJustPlayExtra.value = null
  input.value = rounded === '' ? '' : rounded.toFixed(1)
}
const justPlayAdhesivePackagingCost = computed(() => calculateJustPlayAdhesivePackagingCostHkd(primaryCarton.value, justPlayPackagingInputs.value))
const justPlayPaperPalletCost = computed(() => calculateJustPlayPaperPalletCostHkd(primaryCarton.value, justPlayPackagingInputs.value))
const justPlayCartonsPerPallet = computed(() => calculateJustPlayCartonsPerPallet(primaryCarton.value, justPlayPackagingInputs.value))
const justPlayPalletFields = [
  { key: 'pallet_length_mm', label: '托板长度 mm' },
  { key: 'pallet_width_mm', label: '托板宽度 mm' },
  { key: 'pallet_height_mm', label: '托板高度 mm' },
] as const
const justPlayPackagingWarning = computed(() => {
  if (!justPlayPackagingInputsValid(justPlayPackagingInputs.value)) return '请填写两项附加金额（可填 0，保留一位小数），以及大于 0 的托板长、宽、高（mm）。'
  if (cartonState.value.error) return cartonState.value.error
  return justPlayCartonsPerPallet.value <= 0 ? '主纸箱须能放入所填写的托板空间，请检查托板与主纸箱尺寸，才能自动计算装箱数及纸托板成本。' : ''
})
const justPlayFixedPackagingTotal = computed(() => justPlayAdhesivePackagingCost.value + justPlayPaperPalletCost.value)
const packagingMaterialTotal = computed(() => (
  sales.value.packaging_materials.reduce((total, row) => total + calculatePackagingMaterialAmountHkd(row, props.rmbHkdRate), 0)
))
const testingFeeCalculationEnabled = computed<boolean>({
  get: () => sales.value.testing_fee_enabled !== false,
  set: (value) => { sales.value.testing_fee_enabled = value },
})
const freightCapacityDefinitions = computed(() => {
  const seen = new Set<string>()
  return referenceFreightRoutes.value.flatMap(({ capacityKey }) => {
    if (seen.has(capacityKey)) return []
    seen.add(capacityKey)
    const known = salesFreightCapacityDefinitions.find(({ key }) => key === capacityKey)
    return [{ key: capacityKey, label: known?.label ?? capacityKey }]
  })
})
const freightCalculationEnabled = computed<boolean>({
  get: () => salesFreightCalculationModes(sales.value.freight_calc).freightEnabled,
  set: (value) => {
    sales.value.freight_calc.freight_enabled = value
    sales.value.freight_calc.enabled = value || liftingCalculationEnabled.value
  },
})
const liftingCalculationEnabled = computed<boolean>({
  get: () => salesFreightCalculationModes(sales.value.freight_calc).liftingEnabled,
  set: (value) => {
    sales.value.freight_calc.lifting_enabled = value
    sales.value.freight_calc.enabled = value || freightCalculationEnabled.value
  },
})
const anyFreightCalculationEnabled = computed(() => freightCalculationEnabled.value || liftingCalculationEnabled.value)
const freightOptions = computed(() => calculateSalesFreightOptions(sales.value.freight_calc, primaryCarton.value, referenceFreightRoutes.value))
function freightRouteIncluded(routeKey: string) {
  const selected = sales.value.freight_calc.selected_route_keys
  return !Array.isArray(selected) || selected.includes(routeKey)
}
function setFreightRouteIncluded(routeKey: string, event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  const current = Array.isArray(sales.value.freight_calc.selected_route_keys)
    ? [...sales.value.freight_calc.selected_route_keys]
    : referenceFreightRoutes.value.map((route) => route.key)
  const next = new Set(current)
  if (checked) next.add(routeKey)
  else next.delete(routeKey)
  sales.value.freight_calc.selected_route_keys = referenceFreightRoutes.value
    .map((route) => route.key)
    .filter((key) => next.has(key))
}
const freightSourceCuft = computed(() => primaryCarton.value ? calculateCartonCuft(primaryCarton.value) : 0)
function calculated(value: number) { return fixedDecimal(value, 3) }
function measured(value: number) { return value.toFixed(4) }
function whole(value: number) { return Math.round(value).toString() }
function normalizeFreightCapacity(key: string) {
  const value = Number(sales.value.freight_calc[key])
  sales.value.freight_calc[key] = Number.isFinite(value) && value > 0 ? Math.max(Math.round(value), 1) : 0
}
function normalizeSalesTestingFeeMoq(index: number) {
  const value = Number(sales.value.testing_fee_moqs[index])
  sales.value.testing_fee_moqs[index] = Number.isFinite(value) && value > 0 ? Math.max(Math.round(value), 1) : 0
}
function electronicRow(): ElectronicComponentRow {
  return { item: '', specification: '', quantity: 1, unit_price_rmb: 0, tax_rate_percent: 13, remark: '', children: [] }
}
function electronicQuickRow(): ElectronicQuickQuoteRow {
  return { item: '', unit_price_rmb: 0, tax_rate_percent: 13, remark: '' }
}
function promoteElectronicRowsToRmb(rows: ElectronicComponentRow[]) {
  for (const row of rows) {
    if (!Object.prototype.hasOwnProperty.call(row, 'unit_price_rmb')) row.unit_price_rmb = calculateElectronicUnitPriceRmb(row, props.rmbHkdRate)
    delete row.unit_price_hkd
    promoteElectronicRowsToRmb(row.children)
  }
}
function promoteElectronicToRmb() {
  if (electronic.value.pricing_currency === 'RMB') return
  promoteElectronicRowsToRmb(electronic.value.components)
  electronic.value.bonding_rmb = electronicExtraRmb(electronic.value, 'bonding_rmb', 'bonding_hkd', props.rmbHkdRate)
  electronic.value.smt_rmb = electronicExtraRmb(electronic.value, 'smt_rmb', 'smt_hkd', props.rmbHkdRate)
  electronic.value.labor_rmb = electronicExtraRmb(electronic.value, 'labor_rmb', 'labor_hkd', props.rmbHkdRate)
  electronic.value.testing_rmb = electronicExtraRmb(electronic.value, 'testing_rmb', 'testing_hkd', props.rmbHkdRate)
  electronic.value.packaging_rmb = electronicExtraRmb(electronic.value, 'packaging_rmb', 'packaging_hkd', props.rmbHkdRate)
  for (const key of ['bonding_hkd', 'smt_hkd', 'labor_hkd', 'testing_hkd', 'packaging_hkd', 'tax_credit_difference_hkd'] as const) delete electronic.value[key]
  electronic.value.pricing_currency = 'RMB'
}
function inputNumber(event: Event) {
  const parsed = Number((event.target as HTMLInputElement).value)
  return Number.isFinite(parsed) ? parsed : 0
}
type DualCurrencyMaterialRow = Pick<EngineeringMaterialRow | SalesPackagingMaterialRow, 'unit_price_rmb' | 'unit_price_hkd' | 'unit_price_source_currency'>
function roundedUnitPrice(value: number) {
  return Math.round((Math.max(0, value) + Number.EPSILON) * 10000) / 10000
}
function setDualCurrencyUnitPrice(row: DualCurrencyMaterialRow, currency: UnitPriceSourceCurrency, event: Event) {
  const value = Math.max(0, inputNumber(event))
  const rate = Number(props.rmbHkdRate)
  row.unit_price_source_currency = currency
  if (currency === 'HKD') {
    row.unit_price_hkd = value
    row.unit_price_rmb = Number.isFinite(rate) && rate > 0 ? roundedUnitPrice(value * rate) : 0
    return
  }
  row.unit_price_rmb = value
  row.unit_price_hkd = Number.isFinite(rate) && rate > 0 ? roundedUnitPrice(value / rate) : 0
}
function setEngineeringMaterialUnitPrice(row: EngineeringMaterialRow, currency: UnitPriceSourceCurrency, event: Event) {
  setDualCurrencyUnitPrice(row, currency, event)
}
function setPackagingMaterialUnitPrice(row: SalesPackagingMaterialRow, currency: UnitPriceSourceCurrency, event: Event) {
  setDualCurrencyUnitPrice(row, currency, event)
}
function setElectronicUnitPriceRmb(row: ElectronicComponentRow, event: Event) {
  promoteElectronicToRmb()
  row.unit_price_rmb = inputNumber(event)
}
function setElectronicExtraRmb(
  rmbField: 'bonding_rmb' | 'smt_rmb' | 'labor_rmb' | 'testing_rmb' | 'packaging_rmb',
  event: Event,
) {
  promoteElectronicToRmb()
  electronic.value[rmbField] = inputNumber(event)
}
function addElectronicComponent() { promoteElectronicToRmb(); electronic.value.components.push(assignCurrentPricingComponent(electronicRow())) }
function addElectronicChild(row: ElectronicComponentRow) { promoteElectronicToRmb(); row.children.push(assignCurrentPricingComponent(electronicRow())) }
function addElectronicQuickQuote() { promoteElectronicToRmb(); electronic.value.quick_quotes.push(assignCurrentPricingComponent(electronicQuickRow())) }
function addInjection() { molding.value.injection_lines.push(assignCurrentPricingComponent({ engineering_source_key: '', engineering_synced_fields: [], engineering_sync_disabled: false, item: '', mold_no: '', material: '', grade: '', color: '', net_weight_g: 0, loss_rate_percent: injectionLossRate.value, machine_name: '', machine_code: '', cavity: '', sets: 1, target_output: 0, cycle_time_seconds: 0, quantity: 1, remark: '', disney_mold_no: '', disney_resin_cost_usd_kg: 0, disney_cycle_time_seconds: 0, disney_labor_rate_usd_hr: 0 })) }
function copyInjection(source: InjectionRow) {
  const index = molding.value.injection_lines.indexOf(source)
  if (index < 0) return
  if (!source) return
  source.engineering_sync_disabled = true
  source.engineering_synced_fields = []
  molding.value.injection_lines.splice(index + 1, 0, {
    ...source,
    engineering_source_key: '',
    engineering_synced_fields: [],
    engineering_sync_disabled: true,
  })
}
function addCaixingToolPlanRow() { molding.value.caixing_tool_plan_rows.push({ ref_no: '', process_type: 'IN', tool_no: '', tooling_cost_hkd: 0, description: '', sku_no: '', cavities: 1, up: 1, net_weight_g: 0, material_code: 0, material: '', color: '', material_cost_hkd: 0, material_price_hkd_lb: null, machine_size: '', cycle_time_seconds: 0, process_cost_hkd: 0, machine_daily_hkd: null }) }
function addBlow() { molding.value.blow_lines.push(assignCurrentPricingComponent({ item: '', daily_capacity: '', material: '', grade: '', estimated_weight_g: 0, labor_hkd: 0, burr_hkd: 0, profit_multiplier: 1.05, quantity: 1, output_count: '', mold_price_rmb: 0, remark: '' })) }
function addPainting() {
  painting.value.rows.push(assignCurrentPricingComponent({
    cost_allocation: 'split', paint_cost_hkd: null, labor_cost_hkd: null,
    image_reference: '', name: '', position: '', remark: '',
    operations: Object.fromEntries(operationCodes.map((code) => [code, { quantity: 0, unit_price_hkd: 0 }])) as PaintingPayload['rows'][number]['operations'],
  }))
}
function setPaintingSplit(row: PaintingPayload['rows'][number], field: 'paint_cost_hkd' | 'labor_cost_hkd', event: Event) {
  if (row.cost_allocation !== 'split') {
    row.cost_allocation = 'split'
    row.paint_cost_hkd = null
    row.labor_cost_hkd = null
  }
  const value = (event.target as HTMLInputElement).value
  row[field] = value === '' ? null : Number(value)
}
function addDisneyDecoration() { painting.value.disney_decorations.push({ application_type: '', rate_per_op_usd: 0, operations: 0 }) }
function addSlush() { slush.value.lines.push(assignCurrentPricingComponent({ product_code: '', item: '', material: '', weight_g: 0, daily_output_24h: 0, quantity: 1, unit_price_hkd: 0, remark: '' })) }
function addHair() { hair.value.lines.push(assignCurrentPricingComponent({ name: '', craft: '', weight_g: 0, unit_price_hkd: 0, unit: 'PCS', remark: '' })) }
function addSewingGroup() { sewing.value.groups.push(assignCurrentPricingComponent({ name: '', category: 'clothes', labor_rmb: 0, materials: [] })) }
function addSewingMaterial(group: SewingGroup) { group.materials.push({ item: '', part: '', craft: '', pieces: 0, supplier: '', fabric_moq_y: 0, below_moq_fee_rmb: 0, usage: 0, unit_price_rmb: 0, exchange_rate: Number(props.rmbHkdRate) || 0, markup: 1, remark: '' }) }
function addSewingQuickQuote() { sewing.value.quick_quotes.push(assignCurrentPricingComponent({ doll_name: '', unit_price_hkd: 0 })) }
function sewingEmbroideryCount(group: SewingGroup) { return group.materials.filter((row) => row.craft === '电绣').length }
function addAssemblyGroup(category: AssemblyGroup['category']) {
  const group = { name: '', category, production_qty: 1, teams: 1, total_persons: null, processes: [] } as AssemblyGroup
  assembly.value.groups.push(category === 'assembly' ? assignCurrentPricingComponent(group) : group)
}
function setAssemblyManualPeople(group: AssemblyGroup, event: Event) {
  const value = (event.target as HTMLInputElement).value.trim()
  group.total_persons = value === '' ? null : Math.max(0, finiteNumber(value))
}
function addAssemblyProcess(group: AssemblyGroup) {
  if (!group.processes.length) group.total_persons = null
  group.processes.push({ name: '', persons: 1, remark: '' })
}
function removeAssemblyProcess(group: AssemblyGroup, rowIndex: number) {
  group.processes.splice(rowIndex, 1)
  if (!group.processes.length) group.total_persons = null
}
function removeAssemblyGroup(group: AssemblyGroup) {
  const index = assembly.value.groups.indexOf(group)
  if (index >= 0) assembly.value.groups.splice(index, 1)
}
function addBuzzBeeColorBoxTier() {
  if (sales.value.customer_quote_fields.buzzbee.color_box_tiers.length >= 2) return
  sales.value.customer_quote_fields.buzzbee.color_box_tiers.push({ quote_price_hkd: 0, fsc_price_hkd: 0, moq: '' })
}
</script>

<template>
  <div class="section-payload-form" :class="{ disabled }">
    <section class="payload-standard-notice">
      <strong>统一填入格式：Huaxing Demo</strong>
      <span>所有客户共用同一套内部核价字段；当前客户的报客模板专属字段只用于最终转换，不参与内部成本计算。</span>
    </section>
    <main class="section-payload-blocks">
    <section v-if="pricingMode !== 'component' && pricingItems.length" class="quote-pricing-assignment">
      <header>
        <div>
          <strong>明细倍率</strong>
          <span>留空跟随右侧主倍率；填写不同倍率后自动从主倍率汇总中拆出，清空或填回主倍率即可恢复。</span>
        </div>
      </header>
      <div class="quote-pricing-assignment-grid">
        <article v-for="(item,index) in pricingItems" :key="`${item.label}-${index}`">
          <strong>{{ item.label }}</strong>
          <InternalQuotePricingFields v-model="item.meta" :mode="pricingMode" :components="pricingComponents" :main-markup="mainMarkup" :allow-markup-override="item.allowMarkupOverride" :disabled="disabled" />
        </article>
      </div>
    </section>
    <template v-if="props.code === 'engineering'">
      <section :id="blockDomId('hardware')" class="payload-block" data-form-block>
        <header><div><strong>五金部分</strong><span>损耗率默认 1；“五金1.xlsx”仅导入原有对应字段。</span></div><div class="block-header-actions"><button v-if="importSourceAttachment('hardware')" type="button" title="预览本部分最近导入的 Excel 原文件" @click="previewImportSource('hardware')"><Eye />预览附件</button><button type="button" :disabled="disabled" @click="addEngineeringHardware"><Plus />新增五金</button></div></header>
        <div class="payload-table-scroll">
          <table class="engineeringHardware">
            <thead><tr><th>#</th><th>零件名称</th><th>规格</th><th>类别</th><th>用量</th><th>原单价 RMB</th><th>损耗率</th><th>计价单价 HKD（自动）</th><th>金额 HKD（自动）</th><th>税点 %</th><th>备注</th><th /></tr></thead>
            <tbody>
              <tr v-for="(row,index) in hardwareRows" :key="index">
                <td>{{ index + 1 }}</td><td><input v-model="row.item" :disabled="disabled" aria-label="五金零件名称"></td><td><input v-model="row.specification" :disabled="disabled" aria-label="五金规格"></td><td><span class="fixed-field" aria-label="五金类别">五金</span></td><td><input v-model.number="row.quantity" :disabled="disabled" type="number" min="0" step="1" aria-label="五金用量"></td><td><input v-model.number="row.unit_price_rmb" :disabled="disabled" type="number" min="0" step="0.001" aria-label="五金原单价 RMB"></td><td><input v-model.number="row.loss_rate" :disabled="disabled" type="number" min="0.1" step="0.1" aria-label="五金损耗率"></td><td class="calculated-cell">{{ calculated(calculateEngineeringMaterialEffectiveUnitHkd(row, props.rmbHkdRate)) }}</td><td class="calculated-cell">{{ calculated(calculateEngineeringMaterialAmountHkd(row, props.rmbHkdRate)) }}</td><td><span class="fixed-field numeric" aria-label="五金税点">13%</span></td><td><input v-model="row.remark" :disabled="disabled" aria-label="五金备注"></td><td><button type="button" class="icon" :disabled="disabled" @click="removeEngineeringMaterial(row)"><Trash2 /></button></td>
              </tr>
              <tr v-if="!hardwareRows.length"><td colspan="12" class="empty">当前配件暂无五金明细，可新增或从五金报价单预览导入</td></tr>
            </tbody>
            <tfoot><tr><td colspan="8">五金成本汇总</td><td>HKD {{ calculated(hardwareTotal) }}</td><td colspan="3" /></tr></tfoot>
          </table>
        </div>
      </section>
      <section :id="blockDomId('auxiliary')" class="payload-block" data-form-block>
        <header><div><strong>辅助材料/外购件部分</strong><span>RMB、HKD 原单价任选一种填写；损耗率默认 1，计价结果由系统生成。</span></div><button type="button" :disabled="disabled" @click="addEngineeringAuxiliary"><Plus />新增辅助材料/外购件</button></header>
        <div class="payload-table-scroll">
          <table class="engineeringAuxiliary">
            <thead><tr><th>#</th><th>零件名称</th><th>规格</th><th>类别</th><th>用量</th><th>原单价 RMB</th><th>原单价 HKD</th><th>损耗率</th><th>计价单价 HKD（自动）</th><th>金额 HKD（自动）</th><th>税点 %</th><th>备注</th><th /></tr></thead>
            <tbody>
              <tr v-for="(row,index) in auxiliaryRows" :key="index">
                <td>{{ index + 1 }}</td><td><input v-model="row.item" :disabled="disabled" aria-label="辅助材料/外购件零件名称"></td><td><input v-model="row.specification" :disabled="disabled" aria-label="辅助材料/外购件规格"></td><td><select v-model="row.auxiliary_category" :disabled="disabled" aria-label="辅助材料/外购件类别"><option v-for="category in engineeringMaterialCategories" :key="category" :value="category">{{ category }}</option></select></td><td><input v-model.number="row.quantity" :disabled="disabled" type="number" min="0" step="1" aria-label="辅助材料/外购件用量"></td><td><input :value="calculateEngineeringMaterialUnitRmb(row, props.rmbHkdRate)" :disabled="disabled" type="number" min="0" step="0.001" aria-label="辅助材料/外购件原单价 RMB" @input="setEngineeringMaterialUnitPrice(row, 'RMB', $event)"></td><td><input :value="calculateEngineeringMaterialUnitHkd(row, props.rmbHkdRate)" :disabled="disabled" type="number" min="0" step="0.001" aria-label="辅助材料/外购件原单价 HKD" @input="setEngineeringMaterialUnitPrice(row, 'HKD', $event)"></td><td><input v-model.number="row.loss_rate" :disabled="disabled" type="number" min="0.1" step="0.1" aria-label="辅助材料/外购件损耗率"></td><td class="calculated-cell">{{ calculated(calculateEngineeringMaterialEffectiveUnitHkd(row, props.rmbHkdRate)) }}</td><td class="calculated-cell">{{ calculated(calculateEngineeringMaterialAmountHkd(row, props.rmbHkdRate)) }}</td><td><input v-model.number="row.tax_rate_percent" :disabled="disabled" type="number" min="0" max="100" step="0.01" aria-label="辅助材料/外购件税点"></td><td><input v-model="row.remark" :disabled="disabled" aria-label="辅助材料/外购件备注"></td><td><button type="button" class="icon" :disabled="disabled" @click="removeEngineeringMaterial(row)"><Trash2 /></button></td>
              </tr>
              <tr v-if="!auxiliaryRows.length"><td colspan="13" class="empty">当前配件暂无辅助材料/外购件明细</td></tr>
            </tbody>
            <tfoot><tr><td colspan="9">辅助材料/外购件成本汇总</td><td>HKD {{ calculated(auxiliaryTotal) }}</td><td colspan="3" /></tr></tfoot>
          </table>
        </div>
      </section>
      <section v-if="isDisney" class="payload-block disney-purchased-parts">
        <header><div><strong>迪士尼采购件客户字段部分</strong><span>五金和辅助材料/外购件逐行对应客户模板；Description、归属、USD 单价与 Included 必须显式填写。</span></div></header>
        <div class="payload-table-scroll"><table class="extraWide disneyPurchasedParts"><thead><tr><th>#</th><th>内部零件</th><th>内部类别</th><th>Disney Description</th><th>客户模板归属</th><th>Unit Cost USD</th><th>Included</th></tr></thead><tbody><tr v-for="(row,index) in engineering.materials" :key="index"><td>{{ index + 1 }}</td><td><span class="fixed-field">{{ row.item || '未填写' }}</span></td><td><span class="fixed-field">{{ row.category === 'hardware' ? '五金' : row.auxiliary_category }}</span></td><td><input v-model="row.disney_description" :disabled="disabled" aria-label="迪士尼采购件英文说明"></td><td><select v-model="row.disney_section" :disabled="disabled" aria-label="迪士尼采购件模板归属"><option value="product">Product Part</option><option value="package">Package Part</option></select></td><td><input v-model.number="row.disney_unit_price_usd" :disabled="disabled" type="number" min="0" step="0.001" aria-label="迪士尼采购件单价 USD"></td><td><input v-model.number="row.disney_included" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="迪士尼采购件 Included"></td></tr><tr v-if="!engineering.materials.length"><td colspan="7" class="empty">请先在五金或辅助材料/外购件部分新增内部成本行</td></tr></tbody></table></div>
      </section>
      <section :id="blockDomId('molds')" class="payload-block engineering-molds" data-form-block>
        <header><div><strong>模具部分</strong><span>字段按原内部报价模具表统一；模具价格为整套总价，模价 HKD 按本报价冻结汇率自动换算。</span></div><div class="block-header-actions"><button v-if="importSourceAttachment('mold')" type="button" title="预览本部分最近导入的 Excel 原文件" @click="previewImportSource('mold')"><Eye />预览附件</button><button type="button" :disabled="disabled" @click="addEngineeringMold"><Plus />新增模具</button></div></header>
        <div class="payload-table-scroll">
          <table class="extraWide engineeringMolds">
            <thead><tr><th>#</th><th>模具名称</th><th>中文名称</th><th>模号</th><th>模胚类型</th><th>模胚材质</th><th>模具结构</th><th>工艺</th><th>材质</th><th>料型</th><th>颜色</th><th>出模数</th><th>套数</th><th>净重 (g)</th><th>周期 (秒)</th><th>模具尺寸</th><th>模具规格</th><th>图片</th><th>模具价格 RMB</th><th>模价 HKD（自动）</th><th>备注</th><th /></tr></thead>
            <tbody>
              <tr v-for="(row,index) in visibleEngineeringMolds" :key="index">
                <td>{{ index + 1 }}</td>
                <td><textarea v-model="row.item" :disabled="disabled" rows="2" aria-label="模具名称" /></td>
                <td><textarea v-model="row.chinese_name" :disabled="disabled" rows="2" aria-label="模具中文名称" /></td>
                <td><input v-model="row.mold_no" :disabled="disabled" aria-label="模号"></td>
                <td><textarea v-model="row.mold_base_type" :disabled="disabled" rows="2" aria-label="模胚类型" /></td>
                <td><input v-model="row.mold_base_material" :disabled="disabled" aria-label="模胚材质"></td>
                <td><input v-model="row.structure" :disabled="disabled" aria-label="模具结构"></td>
                <td><input v-model="row.process" :disabled="disabled" aria-label="模具工艺"></td>
                <td><input v-model="row.material" :disabled="disabled" aria-label="模具材质"></td>
                <td><input v-model="row.material_type" :disabled="disabled" aria-label="料型"></td>
                <td><input v-model="row.color" :disabled="disabled" aria-label="模具颜色"></td>
                <td><input v-model="row.cavity" :disabled="disabled" aria-label="出模数"></td>
                <td><input v-model.number="row.quantity" :disabled="disabled" type="number" min="0" step="1" aria-label="模具套数"></td>
                <td><input v-model.number="row.net_weight_g" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="模具净重"></td>
                <td><input v-model.number="row.cycle_time_seconds" :disabled="disabled" type="number" min="0" step="0.01" aria-label="模具周期"></td>
                <td><input v-model="row.mold_size" :disabled="disabled" aria-label="模具尺寸"></td>
                <td><input v-model="row.mold_specification" :disabled="disabled" aria-label="模具规格"></td>
                <td class="mold-image-cell">
                  <div v-if="moldImageAttachments(row).length" class="mold-image-list">
                    <a v-for="attachment in moldImageAttachments(row)" :key="attachment.id" :href="attachmentPreviewUrl(attachment.id)" target="_blank" rel="noopener" :title="`查看 ${attachment.fileName}`">
                      <img :src="attachmentPreviewUrl(attachment.id)" :alt="`${row.mold_no || row.item || '模具'}图片`" loading="lazy">
                    </a>
                  </div>
                  <input v-else v-model="row.image_reference" :disabled="disabled" placeholder="暂无图片；可上传含嵌入图的模价表" aria-label="模具图片附件说明">
                  <small v-if="moldImageAttachments(row).length">{{ moldImageAttachments(row).length }} 张 · 点击放大</small>
                </td>
                <td><input v-model.number="row.cost_rmb" :disabled="disabled" type="number" min="0" step="0.01" aria-label="模具价格 RMB"></td>
                <td class="calculated-cell">{{ calculated(calculateEngineeringMoldPriceHkd(row, props.rmbHkdRate)) }}</td>
                <td><textarea v-model="row.remark" :disabled="disabled" rows="2" aria-label="模具备注" /></td>
                <td><button type="button" class="icon" :disabled="disabled" @click="removeItem(engineering.molds,row)"><Trash2 /></button></td>
              </tr>
              <tr v-if="!visibleEngineeringMolds.length"><td colspan="22" class="empty">暂无模具明细，可新增或从模具报价单预览导入</td></tr>
            </tbody>
            <tfoot v-if="visibleEngineeringMolds.length"><tr><td colspan="18">模具报价小计（RMB→HKD {{ Number(props.rmbHkdRate || 0).toFixed(2) }}）</td><td>RMB {{ calculated(moldQuoteTotalRmb) }}</td><td>HKD {{ calculated(moldQuoteTotalHkd) }}</td><td colspan="2" /></tr></tfoot>
          </table>
        </div>
        <div v-if="visibleEngineeringMolds.length" class="engineering-mold-parts">
          <article v-for="(row,index) in visibleEngineeringMolds" :key="moldRowKey(row)" class="nested-card engineering-mold-part-card">
            <div class="nested-head">
              <div><strong>{{ row.mold_no || `模具 ${index + 1}` }} 配件子行</strong><span>{{ row.item || row.chinese_name || '请先填写模具名称' }}</span></div>
              <div class="nested-actions">
                <button type="button" :disabled="disabled" @click="splitEngineeringMoldParts(row)">按名称拆分</button>
                <button type="button" :disabled="disabled" @click="addEngineeringMoldPart(row)"><Plus />新增子配件</button>
              </div>
            </div>
            <div class="mold-part-rule">“左右”“前后”展开为两个配件；“前/后”“前／后”补全共同名称。普通斜杠按名称分行。重新拆分先预览，保留匹配行数据和未匹配的手工行。</div>
            <section v-if="moldSplitTarget === row && moldSplitPreview && !disabled" class="mold-split-preview" role="dialog" aria-label="配件拆分预览">
              <strong>配件拆分预览 · 确认前不修改原行</strong>
              <p>匹配行保留已有数据；新增行需要补填颜色、重量、出模数和用量。</p>
              <p v-if="moldSplitPreview.retainedCount" class="split-warning">有 {{ moldSplitPreview.retainedCount }} 条原行无法匹配，将保留在末尾，不会自动删除；确认后请核对是否需要手工调整。</p>
              <p v-if="!moldSplitPreview.nameCount">请先填写模具名称。</p>
              <ol><li v-for="(entry,previewIndex) in moldSplitPreview.rows" :key="previewIndex"><span>{{ entry.part.name || '未命名' }}</span><b>{{ entry.status === 'matched' ? '保留数据' : entry.status === 'retained' ? '原行未匹配 · 保留' : '新增 · 待填写' }}</b></li></ol>
              <div class="nested-actions"><button type="button" @click="moldSplitTarget = undefined">取消拆分</button><button type="button" :disabled="disabled || !moldSplitPreview.nameCount" @click="confirmMoldPartSplit">确认拆分并保留数据</button></div>
            </section>
            <div class="payload-table-scroll">
              <table class="engineeringMoldParts">
                <thead><tr><th>#</th><th>配件名称</th><th>颜色</th><th>原胶件单净重 (g)</th><th>出模数</th><th>用量</th><th /></tr></thead>
                <tbody>
                  <tr v-for="(part,partIndex) in row.parts" :key="moldRowKey(part)">
                    <td>{{ partIndex + 1 }}</td>
                    <td><input v-model="part.name" :disabled="disabled" aria-label="模具子配件名称"></td>
                    <td><input v-model="part.color" :disabled="disabled" :placeholder="row.color || '可留空'" aria-label="模具子配件颜色"></td>
                    <td><input v-model.number="part.unit_net_weight_g" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="模具子配件单个净重"></td>
                    <td><input v-model.number="part.output_count" :disabled="disabled" type="number" min="0" step="1" aria-label="模具子配件出模数"></td>
                    <td><input v-model.number="part.quantity" :disabled="disabled" type="number" min="0" step="1" aria-label="模具子配件用量"></td>
                    <td><button type="button" class="icon" :disabled="disabled" @click="remove(row.parts,partIndex)"><Trash2 /></button></td>
                  </tr>
                  <tr v-if="!row.parts.length"><td colspan="7" class="empty">尚未生成子配件；可按名称拆分或手动新增</td></tr>
                </tbody>
              </table>
            </div>
          </article>
        </div>
      </section>
      <InternalQuoteDickieMolds v-if="isDickie" :molds="engineering.molds" :disabled="disabled" />
      <section v-if="isDisney" class="payload-block disney-mold-fields">
        <header><div><strong>迪士尼模具客户字段部分</strong><span>每条工程模具必须对应客户模号、部件、材料、穴数、每啤件数和客户模价 USD；模号会同步到啤机分段。</span></div></header>
        <div class="payload-table-scroll"><table class="extraWide disneyMoldFields"><thead><tr><th>#</th><th>内部模具</th><th>Disney Mold No.</th><th>Parts</th><th>Material</th><th>Cavities</th><th>Parts / Shot</th><th>Tool Cost USD</th></tr></thead><tbody><tr v-for="(row,index) in engineering.molds" :key="index"><td>{{ index + 1 }}</td><td><span class="fixed-field">{{ row.item || row.chinese_name || row.mold_no || '未填写' }}</span></td><td><input v-model="row.disney_mold_no" :disabled="disabled" aria-label="迪士尼模号"></td><td><input v-model="row.disney_parts" :disabled="disabled" aria-label="迪士尼模具部件"></td><td><input v-model="row.disney_material" :disabled="disabled" aria-label="迪士尼模具材料"></td><td><input v-model.number="row.disney_cavities" :disabled="disabled" type="number" min="0" step="1" aria-label="迪士尼模具穴数"></td><td><input v-model.number="row.disney_parts_per_shot" :disabled="disabled" type="number" min="0" step="1" aria-label="迪士尼每啤件数"></td><td><input v-model.number="row.disney_tool_cost_usd" :disabled="disabled" type="number" min="0" step="0.01" aria-label="迪士尼客户模价 USD"></td></tr><tr v-if="!engineering.molds.length"><td colspan="8" class="empty">请先在模具部分新增工程模具</td></tr></tbody></table></div>
      </section>
      <section :id="blockDomId('mold-allocation')" class="payload-block production-mold-costs" data-form-block>
        <header><div><strong>生产模具费用与分摊部分</strong><span>生产模费、手板费和测试费分别按套数分摊；关闭后保留原值，但不进入报价成本。</span></div><div class="calculation-header-actions"><label class="freight-status-toggle" :class="{ inactive: !engineering.mold_allocation_enabled }"><input v-model="engineering.mold_allocation_enabled" :disabled="disabled" type="checkbox" aria-label="启用生产模具费用分摊"><span>{{ engineering.mold_allocation_enabled ? '计算分摊' : '暂不分摊' }}</span></label><button v-if="engineering.mold_allocation_enabled" type="button" :disabled="disabled" @click="addProductionMoldCost"><Plus />增加费用行</button></div></header>
        <div v-if="!engineering.mold_allocation_enabled" class="freight-disabled-notice">
          <strong>本报价已暂时取消生产模具费用与分摊</strong>
          <span>生产模费、手板费、测试费及套数原值均已保留；服务端分摊结果归零，重新开启即可恢复计算。</span>
        </div>
        <template v-else>
        <div class="payload-table-scroll">
          <table class="productionMoldCosts">
            <thead><tr><th>模具名称</th><th>模价 RMB</th><th>模价 USD（自动）</th><th /></tr></thead>
            <tbody>
              <tr v-for="(row,index) in engineering.production_mold_costs" :key="index"><td><input v-model="row.item" :disabled="disabled" aria-label="生产模具费用名称"></td><td><input v-model.number="row.cost_rmb" :disabled="disabled" type="number" min="0" step="0.01" aria-label="生产模具费用 RMB"></td><td class="calculated-cell">{{ calculated(Number(row.cost_rmb || 0) / moldAllocation.rate) }}</td><td><button type="button" class="icon" :disabled="disabled" @click="remove(engineering.production_mold_costs,index)"><Trash2 /></button></td></tr>
              <tr v-if="!engineering.production_mold_costs.length"><td colspan="4" class="empty">暂无生产模具费用</td></tr>
            </tbody>
            <tfoot><tr><td>模具总计</td><td>RMB {{ calculated(moldAllocation.productionTotalRmb) }}</td><td>USD {{ calculated(moldAllocation.productionTotalUsd) }}</td><td /></tr></tfoot>
          </table>
        </div>
        <div class="inline-fields seven mold-allocation-inputs">
          <label><span>客户补贴模费 USD</span><input v-model.number="engineering.customer_mold_subsidy_usd" :disabled="disabled" type="number" min="0" step="0.01" aria-label="客户补贴模费 USD"></label>
          <label><span>模费分摊套数</span><input v-model.number="engineering.amortization_qty" :disabled="disabled" type="number" min="1" step="1" aria-label="模费分摊套数"></label>
          <label><span>手板费总额 USD</span><input v-model.number="engineering.prototype_total_usd" :disabled="disabled" type="number" min="0" step="0.01" aria-label="手板费总额 USD"></label>
          <label><span>手板费分摊套数</span><input v-model.number="engineering.prototype_amortization_qty" :disabled="disabled" type="number" min="1" step="1" aria-label="手板费分摊套数"></label>
          <label><span>测试费总额 USD</span><input v-model.number="engineering.testing_total_usd" :disabled="disabled" type="number" min="0" step="0.01" aria-label="测试费总额 USD"></label>
          <label><span>测试费分摊套数</span><input v-model.number="engineering.testing_amortization_qty" :disabled="disabled" type="number" min="1" step="1" aria-label="测试费分摊套数"></label>
          <label><span>RMB→USD 汇率</span><input v-model.number="engineering.mold_fx_rmb_usd" :disabled="disabled" type="number" min="0.01" step="0.01" aria-label="生产模具 RMB USD 汇率"></label>
        </div>
        <div class="payload-table-scroll">
          <table class="moldAllocationSummary">
            <thead><tr><th>分摊项目</th><th>每件 RMB</th><th>每件 USD</th></tr></thead>
            <tbody>
              <tr><td>生产模费</td><td class="calculated-cell">{{ calculated(moldAllocation.moldShareRmb) }}</td><td class="calculated-cell">{{ calculated(moldAllocation.moldShareUsd) }}</td></tr>
              <tr><td>手板费</td><td class="calculated-cell">{{ calculated(moldAllocation.prototypeShareRmb) }}</td><td class="calculated-cell">{{ calculated(moldAllocation.prototypeShareUsd) }}</td></tr>
              <tr><td>测试费</td><td class="calculated-cell">{{ calculated(moldAllocation.testingShareRmb) }}</td><td class="calculated-cell">{{ calculated(moldAllocation.testingShareUsd) }}</td></tr>
            </tbody>
            <tfoot><tr><td>每件分摊合计</td><td class="calculated-cell">RMB {{ calculated(moldAllocation.totalShareRmb) }}</td><td class="calculated-cell">USD {{ calculated(moldAllocation.totalShareUsd) }}</td></tr></tfoot>
          </table>
        </div>
        </template>
      </section>
    </template>

    <template v-else-if="props.code === 'electronic'">
      <section v-if="electronic.quote_mode === 'quick'" :id="blockDomId('components')" class="payload-block quick-quote-card electronic-quick-card" data-form-block>
        <header>
          <div><strong>电子快捷报价部分</strong><span>急单按零件人民币单价报价；港币单价按本报价冻结汇率自动换算，切回明细报价时快捷数据仍会保留。</span></div>
          <div class="block-header-actions"><button v-if="importSourceAttachment('electronic')" type="button" title="预览本部分最近导入的 Excel 原文件" @click="previewImportSource('electronic')"><Eye />预览附件</button><button type="button" :disabled="disabled" @click="addElectronicQuickQuote"><Plus />新增电子件</button></div>
        </header>
        <div class="payload-table-scroll">
          <table class="electronicQuickTable">
            <thead><tr><th>#</th><th>零件名称</th><th>单价 RMB</th><th>单价 HKD（自动）</th><th>税点 %</th><th>备注</th><th /></tr></thead>
            <tbody>
              <tr v-for="(row,index) in visibleElectronicQuickRows" :key="index">
                <td class="row-number">{{ index + 1 }}</td>
                <td><input v-model="row.item" :disabled="disabled" aria-label="电子快捷报价零件名称"></td>
                <td><input v-model.number="row.unit_price_rmb" :disabled="disabled" type="number" min="0" step="0.001" aria-label="电子快捷报价单价 RMB"></td>
                <td class="calculated-cell">{{ calculated(calculateElectronicQuickUnitPriceHkd(row, props.rmbHkdRate)) }}</td>
                <td><input v-model.number="row.tax_rate_percent" :disabled="disabled" type="number" min="0" max="100" step="0.01" aria-label="电子快捷报价税点"></td>
                <td><input v-model="row.remark" :disabled="disabled" aria-label="电子快捷报价备注"></td>
                <td><button type="button" class="icon" :disabled="disabled" aria-label="删除电子快捷报价行" @click="removeItem(electronic.quick_quotes,row)"><Trash2 /></button></td>
              </tr>
              <tr v-if="!visibleElectronicQuickRows.length"><td colspan="7" class="empty">当前配件暂无快捷报价行，请新增电子件</td></tr>
            </tbody>
            <tfoot><tr><td colspan="2">快捷零件小计</td><td>RMB {{ calculated(electronicQuickSubtotalRmb) }}</td><td>HKD {{ calculated(electronicQuickSubtotalHkd) }}</td><td colspan="3">每行按用量 1 计入电子部汇总</td></tr></tfoot>
          </table>
        </div>
      </section>
      <section v-else :id="blockDomId('components')" class="payload-block" data-form-block>
        <header>
          <div><strong>电子零件部分</strong><span>统一按人民币单价填入；港币单价与金额按本报价冻结汇率自动换算</span></div>
          <div class="block-header-actions"><button v-if="importSourceAttachment('electronic')" type="button" title="预览本部分最近导入的 Excel 原文件" @click="previewImportSource('electronic')"><Eye />预览附件</button><button type="button" :disabled="disabled" @click="addElectronicComponent"><Plus />新增电子件</button></div>
        </header>
        <article v-for="(row,index) in visibleElectronicComponents" :key="index" class="nested-card electronic-card">
          <div class="nested-head">
            <strong>零件组 {{ index + 1 }}</strong>
            <div class="nested-actions">
              <button type="button" :disabled="disabled" @click="addElectronicChild(row)"><Plus />新增子项</button>
              <button type="button" class="icon" :disabled="disabled" @click="removeItem(electronic.components,row)"><Trash2 /></button>
            </div>
          </div>
          <div class="payload-table-scroll">
            <table class="electronicTable">
              <thead><tr><th>#</th><th>零件名称</th><th>规格</th><th>用量</th><th>单价 RMB</th><th>单价 HKD（自动）</th><th>金额 HKD（自动）</th><th>税点 %</th><th>备注</th><th /></tr></thead>
              <tbody>
                <tr>
                  <td>{{ index + 1 }}</td>
                  <td><input v-model="row.item" :disabled="disabled" aria-label="电子零件名称"></td>
                  <td><input v-model="row.specification" :disabled="disabled" aria-label="电子零件规格"></td>
                  <td><input v-model.number="row.quantity" :disabled="disabled" type="number" min="0" step="1" aria-label="电子零件用量"></td>
                  <td><input :value="calculateElectronicUnitPriceRmb(row, props.rmbHkdRate)" :disabled="disabled" type="number" min="0" step="0.001" aria-label="电子零件单价 RMB" @input="setElectronicUnitPriceRmb(row, $event)"></td>
                  <td class="calculated-cell">{{ calculated(calculateElectronicUnitPriceHkd(row, props.rmbHkdRate)) }}</td>
                  <td class="calculated-cell">{{ calculated(calculateElectronicAmountHkd(row, props.rmbHkdRate)) }}</td>
                  <td><input v-model.number="row.tax_rate_percent" :disabled="disabled" type="number" min="0" max="100" step="0.01" aria-label="电子零件税点"></td>
                  <td><input v-model="row.remark" :disabled="disabled" aria-label="电子零件备注"></td>
                  <td />
                </tr>
                <tr v-for="(child,childIndex) in visibleElectronicChildren(row)" :key="childIndex" class="electronic-child-row">
                  <td>↳ {{ index + 1 }}.{{ childIndex + 1 }}</td>
                  <td><input v-model="child.item" :disabled="disabled" aria-label="电子子项名称"></td>
                  <td><input v-model="child.specification" :disabled="disabled" aria-label="电子子项规格"></td>
                  <td><input v-model.number="child.quantity" :disabled="disabled" type="number" min="0" step="1" aria-label="电子子项用量"></td>
                  <td><input :value="calculateElectronicUnitPriceRmb(child, props.rmbHkdRate)" :disabled="disabled" type="number" min="0" step="0.001" aria-label="电子子项单价 RMB" @input="setElectronicUnitPriceRmb(child, $event)"></td>
                  <td class="calculated-cell">{{ calculated(calculateElectronicUnitPriceHkd(child, props.rmbHkdRate)) }}</td>
                  <td class="calculated-cell">{{ calculated(calculateElectronicAmountHkd(child, props.rmbHkdRate)) }}</td>
                  <td><input v-model.number="child.tax_rate_percent" :disabled="disabled" type="number" min="0" max="100" step="0.01" aria-label="电子子项税点"></td>
                  <td><input v-model="child.remark" :disabled="disabled" aria-label="电子子项备注"></td>
                  <td><button type="button" class="icon" :disabled="disabled" @click="removeItem(row.children,child)"><Trash2 /></button></td>
                </tr>
              </tbody>
            </table>
          </div>
        </article>
        <div v-if="!visibleElectronicComponents.length" class="empty">当前配件暂无电子零件，可逐行新增或通过“上传附件”自动识别电子报价单</div>
      </section>
      <section :id="blockDomId('electronic-summary')" class="payload-block electronic-summary-block" data-form-block>
        <header><div><strong>电子成本汇总部分</strong><span>按电子报价口径自动汇总；含税报价 HKD 按冻结汇率换算</span></div></header>
        <div class="inline-fields four">
          <label><span>邦定成本 RMB</span><input :value="electronicExtraRmb(electronic, 'bonding_rmb', 'bonding_hkd', props.rmbHkdRate)" :disabled="disabled" type="number" min="0" step="0.001" @input="setElectronicExtraRmb('bonding_rmb', $event)"></label>
          <label><span>贴片成本 RMB</span><input :value="electronicExtraRmb(electronic, 'smt_rmb', 'smt_hkd', props.rmbHkdRate)" :disabled="disabled" type="number" min="0" step="0.001" @input="setElectronicExtraRmb('smt_rmb', $event)"></label>
          <label><span>人工成本 RMB</span><input :value="electronicExtraRmb(electronic, 'labor_rmb', 'labor_hkd', props.rmbHkdRate)" :disabled="disabled" type="number" min="0" step="0.001" @input="setElectronicExtraRmb('labor_rmb', $event)"></label>
          <label><span>测试费用 RMB</span><input :value="electronicExtraRmb(electronic, 'testing_rmb', 'testing_hkd', props.rmbHkdRate)" :disabled="disabled" type="number" min="0" step="0.001" @input="setElectronicExtraRmb('testing_rmb', $event)"></label>
          <label><span>包装运输 RMB</span><input :value="electronicExtraRmb(electronic, 'packaging_rmb', 'packaging_hkd', props.rmbHkdRate)" :disabled="disabled" type="number" min="0" step="0.001" @input="setElectronicExtraRmb('packaging_rmb', $event)"></label>
          <label><span>利润率 %</span><input v-model.number="electronic.profit_rate_percent" :disabled="disabled" type="number" min="0" step="0.01"></label>
        </div>
        <div class="payload-table-scroll">
          <table class="electronicSummaryTable">
            <thead><tr><th>零件成本</th><th>成本合计（不含税）</th><th>含利润价</th><th>抵税差额</th><th>应交税负</th><th>含税报价 RMB</th><th>含税报价 HKD</th></tr></thead>
            <tbody><tr><td>{{ calculated(electronicSummary.componentCostRmb) }}</td><td>{{ calculated(electronicSummary.preTaxCostRmb) }}</td><td>{{ calculated(electronicSummary.withProfitRmb) }}</td><td>{{ calculated(electronicSummary.taxDifferenceRmb) }}</td><td>{{ calculated(electronicSummary.taxPayableRmb) }}</td><td class="quote-total">{{ calculated(electronicSummary.quoteRmb) }}</td><td class="quote-total">{{ calculated(electronicSummary.quoteHkd) }}</td></tr></tbody>
          </table>
        </div>
      </section>
    </template>

    <template v-else-if="props.code === 'molding'">
      <section :id="blockDomId('injection')" class="payload-block molding-injection" data-form-block>
        <header>
          <div><strong>注塑部分</strong><span>工程部模具自动生成；同一模具对应多个部件时可复制该行，原行与副本随后均可完整编辑</span></div>
          <div class="molding-header-actions">
            <button v-if="importSourceAttachment('molding')" type="button" title="预览本部分最近导入的 Excel 原文件" @click="previewImportSource('molding')"><Eye />预览附件</button>
            <span v-if="engineeringSyncedInjectionCount" class="engineering-sync-badge">已同步 {{ engineeringSyncedInjectionCount }} 项模具</span>
            <label><span>料损耗 %</span><input v-model.number="injectionLossRate" :disabled="disabled" type="number" min="0" step="0.1" aria-label="注塑料损耗百分比"></label>
            <button type="button" :disabled="disabled" @click="addInjection"><Plus />新增注塑</button>
          </div>
        </header>
        <div class="payload-table-scroll">
          <table class="moldingInjectionTable">
            <thead><tr><th>#</th><th>模具名称</th><th>材质</th><th>料型</th><th>啤净重 (g)</th><th>料价 HKD/g（快照）</th><th>原料单价 HKD（自动）</th><th>啤价 HKD/啤（自动）</th><th>出模数</th><th>套数</th><th>机型 A码</th><th>目标数</th><th>周期 (秒)</th><th>成品金额 HKD（自动）</th><th>成品用量</th><th>备注</th><th /></tr></thead>
            <tbody>
              <tr v-for="(row,index) in visibleInjectionRows" :key="index">
                <td class="row-number">{{ index + 1 }}</td>
                <td><textarea v-model="row.item" :disabled="disabled || injectionFieldLocked(row, 'item')" :class="{ 'engineering-prefilled': injectionFieldLocked(row, 'item') }" rows="2"></textarea></td>
                <td><select v-model="row.material" :disabled="disabled" aria-label="材料类别" @change="selectMaterial(row)"><option value="">请选择材质</option><option v-if="row.material && !moldingMaterialNames.includes(row.material)" :value="row.material">{{ row.material }}</option><option v-for="material in moldingMaterialNames" :key="material" :value="material">{{ material }}</option></select></td>
                <td><select :value="selectedMaterialReference(row) ? materialReferenceValue(selectedMaterialReference(row)!) : ''" :disabled="disabled || !row.material" aria-label="具体材料料型" @change="selectMaterialGrade(row, ($event.target as HTMLSelectElement).value)"><option value="">{{ row.material ? '请选择具体料型' : '先选择材质' }}</option><option v-for="item in materialOptions(row)" :key="`${item.material}-${item.grade}`" :value="materialReferenceValue(item)">{{ item.grade }} · HKD {{ fixedDecimal(item.priceHkdLb, 3) }}/lb</option></select></td>
                <td><input v-model.number="row.net_weight_g" :disabled="disabled || injectionFieldLocked(row, 'net_weight_g')" :class="{ 'engineering-prefilled': injectionFieldLocked(row, 'net_weight_g') }" type="number" min="0" step="0.001"></td>
                <td class="snapshot-cell">{{ injectionPreviewText(row, 'materialPriceHkdG') }}</td>
                <td class="snapshot-cell">{{ injectionPreviewText(row, 'materialCostHkd') }}</td>
                <td class="snapshot-cell">{{ injectionPreviewText(row, 'moldingCostHkd') }}</td>
                <td><input v-model="row.cavity" :disabled="disabled || injectionFieldLocked(row, 'cavity')" :class="{ 'engineering-prefilled': injectionFieldLocked(row, 'cavity') }"></td>
                <td><input v-model.number="row.sets" :disabled="disabled || injectionFieldLocked(row, 'sets')" :class="{ 'engineering-prefilled': injectionFieldLocked(row, 'sets') }" type="number" min="0" step="1"></td>
                <td><select :value="selectedMachineReference(row)?.range ?? row.machine_code" :disabled="disabled" aria-label="注塑机型 A码" @change="selectMachine(row, ($event.target as HTMLSelectElement).value)"><option value="">请选择机型</option><option v-if="row.machine_code && !selectedMachineReference(row)" :value="row.machine_code">未匹配：{{ row.machine_code }}</option><option v-for="item in moldingMachineReferences" :key="item.range" :value="item.range">{{ item.range }} · {{ item.machine }} · HKD {{ fixedDecimal(item.shiftPriceHkd, 3) }}/班</option></select></td>
                <td><input v-model.number="row.target_output" :disabled="disabled || injectionFieldLocked(row, 'target_output')" :class="{ 'engineering-prefilled': injectionFieldLocked(row, 'target_output') }" type="number" min="0" step="1"></td>
                <td><input v-model.number="row.cycle_time_seconds" :disabled="disabled || injectionFieldLocked(row, 'cycle_time_seconds')" :class="{ 'engineering-prefilled': injectionFieldLocked(row, 'cycle_time_seconds') }" type="number" min="0" step="0.01"></td>
                <td class="snapshot-cell amount">{{ injectionPreviewText(row, 'lineAmountHkd') }}</td>
                <td><input v-model.number="row.quantity" :disabled="disabled" type="number" min="0" step="1"></td>
                <td><input v-model="row.remark" :disabled="disabled"></td>
                <td>
                  <div class="injection-row-actions">
                    <button type="button" class="icon" :disabled="disabled" :aria-label="`复制第 ${index + 1} 行注塑明细`" title="复制该行并解除两行的工程同步锁" @click="copyInjection(row)"><Copy /></button>
                    <button type="button" class="icon" :disabled="disabled || Boolean(row.engineering_source_key && !row.engineering_sync_disabled)" :title="row.engineering_source_key && !row.engineering_sync_disabled ? '此行由工程部模具自动生成；复制后可分别编辑和删除' : '删除注塑行'" :aria-label="`删除第 ${index + 1} 行注塑明细`" @click="removeItem(molding.injection_lines,row)"><Trash2 /></button>
                  </div>
                </td>
              </tr>
              <tr v-if="!visibleInjectionRows.length"><td colspan="17" class="empty">当前配件暂无注塑明细，可手工新增或通过“上传附件”自动识别啤机报价单</td></tr>
            </tbody>
          </table>
        </div>
        <div class="molding-summary-grid"><span>实时小结；保存时由服务端按冻结快照权威重算</span><b>重量汇总（含损耗）{{ measured(liveInjectionWeightTotal) }} g</b><b>料价汇总 HKD {{ calculated(liveInjectionMaterialTotal) }}</b><b>啤工汇总 HKD {{ calculated(liveInjectionMoldingLaborTotal) }}</b><b>注塑合计 HKD {{ calculated(liveInjectionTotal) }}</b></div>
      </section>
      <section v-if="isBuzzBee" class="payload-block"><header><div><strong>BuzzBee 报客料型对应</strong><span>料重按整套录入；客户料价名称留空时沿用材料名称。特殊料价请填写维护区中的准确名称，例如 C-ABS镜片。</span></div></header><div class="payload-table-scroll"><table><thead><tr><th>注塑件</th><th>客户料价名称</th></tr></thead><tbody><tr v-for="(row,index) in molding.injection_lines" :key="index"><td>{{ row.item || row.mold_no }}</td><td><input v-model="row.buzzbee_material" :disabled="disabled" aria-label="BuzzBee 客户料价名称" placeholder="留空沿用材料名称"></td></tr></tbody></table></div></section>
      <section v-if="isDisney" class="payload-block disney-injection-fields">
        <header><div><strong>迪士尼注塑客户参数部分</strong><span>每条注塑行必须匹配工程部 Disney Mold No.，并填写客户 Resin、Cycle 与 Labor Rate；这些值不从内部成本反推。</span></div></header>
        <div class="payload-table-scroll"><table class="extraWide disneyInjectionFields"><thead><tr><th>#</th><th>内部注塑件</th><th>Disney Mold No.</th><th>Resin USD/kg</th><th>Cycle Time (sec)</th><th>Labor USD/hr</th></tr></thead><tbody><tr v-for="(row,index) in molding.injection_lines" :key="index"><td>{{ index + 1 }}</td><td><span class="fixed-field">{{ row.item || row.mold_no || '未填写' }}</span></td><td><input v-model="row.disney_mold_no" :disabled="disabled || injectionFieldLocked(row, 'disney_mold_no')" :class="{ 'engineering-prefilled': injectionFieldLocked(row, 'disney_mold_no') }" aria-label="迪士尼注塑模号"></td><td><input v-model.number="row.disney_resin_cost_usd_kg" :disabled="disabled" type="number" min="0" step="0.001" aria-label="迪士尼 Resin USD 每公斤"></td><td><input v-model.number="row.disney_cycle_time_seconds" :disabled="disabled" type="number" min="0" step="0.01" aria-label="迪士尼 Cycle Time"></td><td><input v-model.number="row.disney_labor_rate_usd_hr" :disabled="disabled" type="number" min="0" step="0.001" aria-label="迪士尼 Labor USD 每小时"></td></tr><tr v-if="!molding.injection_lines.length"><td colspan="6" class="empty">请先在注塑部分新增或同步模具行</td></tr></tbody></table></div>
      </section>
      <section v-if="isCaixing" class="payload-block"><header><div><strong>彩星 Tool Plan 部分</strong><span>逐件填写 Cycle、Cav.、Up；录入内部材料磅价或啤机日价时按彩星参数自动换算，留空则使用已填客户料金额、啤工</span></div><button type="button" :disabled="disabled" @click="addCaixingToolPlanRow"><Plus />新增 Tool Plan</button></header><div class="payload-table-scroll"><table class="extraWide caixingToolPlan"><thead><tr><th>Ref</th><th>Type</th><th>Tool No.</th><th>Tooling HKD</th><th>Description</th><th>SKU</th><th>Cav.</th><th>Up</th><th>Net Wt. g</th><th>Material Code</th><th>Material</th><th>Color</th><th>客户料金额</th><th>内部料价 HKD/lb</th><th>M/C Size</th><th>Cycle s</th><th>客户啤工</th><th>内部啤机日价 HKD</th><th /></tr></thead><tbody><tr v-for="(row,index) in molding.caixing_tool_plan_rows" :key="index"><td><input v-model="row.ref_no" :disabled="disabled" aria-label="彩星 Tool Plan Ref"></td><td><select v-model="row.process_type" :disabled="disabled" aria-label="彩星 Tool Plan Type"><option value="IN">IN</option><option value="BL">BL</option><option value="CP">CP</option><option value="DC">DC</option><option value="RC">RC</option></select></td><td><input v-model="row.tool_no" :disabled="disabled" aria-label="彩星 Tool Number"></td><td><input v-model.number="row.tooling_cost_hkd" :disabled="disabled" type="number" min="0" step="0.01" aria-label="彩星 Tooling Cost"></td><td><input v-model="row.description" :disabled="disabled" aria-label="彩星 Tool Description"></td><td><input v-model="row.sku_no" :disabled="disabled" aria-label="彩星 Tool SKU"></td><td><input v-model.number="row.cavities" :disabled="disabled" type="number" min="0" aria-label="彩星 Cavities"></td><td><input v-model.number="row.up" :disabled="disabled" type="number" min="0" aria-label="彩星 Up"></td><td><input v-model.number="row.net_weight_g" :disabled="disabled" type="number" min="0" step="0.001" aria-label="彩星 Net Weight"></td><td><input v-model.number="row.material_code" :disabled="disabled" type="number" min="0" aria-label="彩星 Material Code"></td><td><input v-model="row.material" :disabled="disabled" aria-label="彩星 Material"></td><td><input v-model="row.color" :disabled="disabled" aria-label="彩星 Color"></td><td><input v-model.number="row.material_cost_hkd" :disabled="disabled" type="number" min="0" step="0.001" aria-label="彩星 Material Cost"></td><td><input v-model.number="row.material_price_hkd_lb" :disabled="disabled" type="number" min="0" step="0.0001" placeholder="可选：自动换算料价" aria-label="彩星内部材料磅价"></td><td><input v-model="row.machine_size" :disabled="disabled" aria-label="彩星 Machine Size"></td><td><input v-model.number="row.cycle_time_seconds" :disabled="disabled" type="number" min="0" step="0.01" aria-label="彩星 Cycle Time"></td><td><input v-model.number="row.process_cost_hkd" :disabled="disabled" type="number" min="0" step="0.001" aria-label="彩星 Process Cost"></td><td><input v-model.number="row.machine_daily_hkd" :disabled="disabled" type="number" min="0" step="0.01" placeholder="可选：自动换算啤工" aria-label="彩星内部啤机日价"></td><td><button type="button" class="icon" :disabled="disabled" @click="remove(molding.caixing_tool_plan_rows,index)"><Trash2 /></button></td></tr><tr v-if="!molding.caixing_tool_plan_rows.length"><td colspan="19" class="empty">未填写 Tool Plan 将阻断彩星 P4 接收</td></tr></tbody></table></div></section>
      <section :id="blockDomId('blow')" class="payload-block molding-blow" data-form-block>
        <header><div><strong>吹气部分</strong><span>填写用料后按厂区冻结快照生成可选料型；唯一料型自动选中并即时计算</span></div><button type="button" :disabled="disabled" @click="addBlow"><Plus />新增吹气货号</button></header>
        <div class="payload-table-scroll">
          <table class="moldingBlowTable">
            <thead><tr><th>#</th><th>货名</th><th>日产量 / 22H</th><th>用料</th><th>料型</th><th>预估料重 g</th><th>料价 HKD/lb（快照）</th><th>产品料价 HKD（自动）</th><th>吹工 HKD</th><th>披锋 HKD</th><th>小计 HKD（自动）</th><th>利润倍率</th><th>合计 HKD（自动）</th><th>成品用量</th><th>出数</th><th>模价 RMB</th><th>备注</th><th /></tr></thead>
            <tbody>
              <tr v-for="(row,index) in visibleBlowRows" :key="index">
                <td class="row-number">{{ index + 1 }}</td>
                <td><input v-model="row.item" :disabled="disabled"></td>
                <td><input v-model="row.daily_capacity" :disabled="disabled"></td>
                <td><input v-model="row.material" :disabled="disabled" placeholder="例如 ABS" aria-label="吹气用料" @input="row.grade = ''"></td>
                <td><select :value="selectedMaterialReference(row) ? materialReferenceValue(selectedMaterialReference(row)!) : ''" :disabled="disabled || !row.material" aria-label="吹气具体材料料型" @change="selectMaterialGrade(row, ($event.target as HTMLSelectElement).value)"><option value="">{{ row.material ? '请选择具体料型' : '先填写用料' }}</option><option v-for="item in materialOptions(row)" :key="`${item.material}-${item.grade}`" :value="materialReferenceValue(item)">{{ item.grade }} · HKD {{ fixedDecimal(item.priceHkdLb, 3) }}/lb</option></select></td>
                <td><input v-model.number="row.estimated_weight_g" :disabled="disabled" type="number" min="0" step="0.001"></td>
                <td class="snapshot-cell">{{ blowPreviewText(row, 'materialPriceHkdLb') }}</td>
                <td class="snapshot-cell">{{ blowPreviewText(row, 'materialCostHkd') }}</td>
                <td><input v-model.number="row.labor_hkd" :disabled="disabled" type="number" min="0" step="0.001"></td>
                <td><input v-model.number="row.burr_hkd" :disabled="disabled" type="number" min="0" step="0.001"></td>
                <td class="snapshot-cell">{{ blowPreviewText(row, 'subtotalHkd') }}</td>
                <td><input v-model.number="row.profit_multiplier" :disabled="disabled" type="number" min="0" step="0.01"></td>
                <td class="snapshot-cell amount">{{ blowPreviewText(row, 'unitAmountHkd') }}</td>
                <td><input v-model.number="row.quantity" :disabled="disabled" type="number" min="0" step="1"></td>
                <td><input v-model="row.output_count" :disabled="disabled"></td>
                <td><input v-model.number="row.mold_price_rmb" :disabled="disabled" type="number" min="0" step="0.01"></td>
                <td><input v-model="row.remark" :disabled="disabled"></td>
                <td><button type="button" class="icon" :disabled="disabled" @click="removeItem(molding.blow_lines,row)"><Trash2 /></button></td>
              </tr>
              <tr v-if="!visibleBlowRows.length"><td colspan="18" class="empty">当前配件暂无吹气明细；没有吹气件时可保持为空</td></tr>
            </tbody>
          </table>
        </div>
        <div class="molding-summary-grid"><span>材料和料型选定后即时按冻结快照预览；保存时服务端再作权威重算</span><b>吹气实时合计 HKD {{ calculated(liveBlowTotal) }}</b><b>啤机实时总计 HKD {{ calculated(liveMoldingTotal) }}</b></div>
      </section>
    </template>

    <template v-else-if="props.code === 'painting'">
      <section v-if="painting.quote_mode === 'quick'" :id="blockDomId('painting')" class="payload-block quick-quote-card painting-quick-card" data-form-block>
        <header><div><strong>喷油快捷报价部分</strong><span>急单可先按港币报价并完成审核；明细后补时切回明细报价，系统只采用当前模式，不会重复计价。</span></div><button v-if="importSourceAttachment('painting')" type="button" title="预览本部分最近导入的 Excel 原文件" @click="previewImportSource('painting')"><Eye />预览附件</button></header>
        <div class="quick-painting-fields">
          <label><span>喷油工 HKD</span><input v-model.number="painting.quick_quote.spray_labor_hkd" :disabled="disabled" type="number" min="0" step="0.001" aria-label="喷油快捷报价喷油工 HKD"></label>
          <label><span>油漆 HKD</span><input v-model.number="painting.quick_quote.paint_hkd" :disabled="disabled" type="number" min="0" step="0.001" aria-label="喷油快捷报价油漆 HKD"></label>
          <label class="quick-readonly"><span>油漆税金（固定 13%）</span><output>HKD {{ calculated(paintingQuickPaintTax) }}</output></label>
          <label class="quick-readonly total"><span>快捷报价合计</span><output>HKD {{ calculated(paintingQuickTotal) }}</output></label>
        </div>
      </section>
      <section v-else :id="blockDomId('painting')" class="payload-block painting-card" data-form-block>
        <header><div><strong>喷油/移印/UV部分</strong><span>填写工序数量和港币单价，并拆分油漆、人工；只填其中一项时另一项按总报价差额计算，两项都空则待填写。</span></div><div class="block-header-actions"><button v-if="importSourceAttachment('painting')" type="button" title="预览本部分最近导入的 Excel 原文件" @click="previewImportSource('painting')"><Eye />预览附件</button><button type="button" :disabled="disabled" @click="addPainting"><Plus />新增喷油/移印/UV</button></div></header>
        <div class="payload-table-scroll">
          <table class="painting">
            <thead>
              <tr><th rowspan="2">#</th><th rowspan="2">图片 / 附件引用</th><th rowspan="2">名称</th><th rowspan="2">位置</th><template v-for="code in operationCodes" :key="code"><th colspan="2">{{ paintingOperationLabels[code] }}</th></template><th rowspan="2">报价 HKD<br>（预览）</th><th rowspan="2">油漆 HKD</th><th rowspan="2">人工 HKD</th><th rowspan="2">备注</th><th rowspan="2" /></tr>
              <tr><template v-for="code in operationCodes" :key="`${code}-sub`"><th>数量</th><th>单价 HKD</th></template></tr>
            </thead>
            <tbody>
              <tr v-for="(row,index) in visiblePaintingRows" :key="index">
                <td class="row-number">{{ index + 1 }}</td>
                <td><input v-model="row.image_reference" :disabled="disabled" :aria-label="`喷油第 ${index + 1} 行图片引用`" placeholder="附件名称 / 图片引用"></td>
                <td><input v-model="row.name" :disabled="disabled" :aria-label="`喷油第 ${index + 1} 行名称`"></td>
                <td><input v-model="row.position" :disabled="disabled" :aria-label="`喷油第 ${index + 1} 行位置`"></td>
                <template v-for="code in operationCodes" :key="code"><td><input v-model.number="row.operations[code].quantity" :disabled="disabled" type="number" min="0" step="1" :aria-label="`${paintingOperationLabels[code]}数量`"></td><td><input v-model.number="row.operations[code].unit_price_hkd" :disabled="disabled" type="number" min="0" step="0.001" :aria-label="`${paintingOperationLabels[code]}单价 HKD`"></td></template>
                <td class="snapshot-cell amount">{{ calculated(calculatePaintingRowAmount(row)) }}</td>
                <td><input :value="row.paint_cost_hkd ?? ''" :disabled="disabled" type="number" min="0" step="0.0001" :aria-label="`喷油第 ${index + 1} 行油漆 HKD`" :placeholder="calculatePaintingRowSplit(row).paint === null ? '待填写' : calculated(calculatePaintingRowSplit(row).paint!)" @input="setPaintingSplit(row, 'paint_cost_hkd', $event)"></td>
                <td><input :value="row.labor_cost_hkd ?? ''" :disabled="disabled" type="number" min="0" step="0.0001" :aria-label="`喷油第 ${index + 1} 行人工 HKD`" :placeholder="calculatePaintingRowSplit(row).labor === null ? '待填写' : calculated(calculatePaintingRowSplit(row).labor!)" @input="setPaintingSplit(row, 'labor_cost_hkd', $event)"><small v-if="!calculatePaintingRowSplit(row).valid">待填写或核对拆分金额</small></td>
                <td><input v-model="row.remark" :disabled="disabled" :aria-label="`喷油第 ${index + 1} 行备注`"></td>
                <td><button type="button" class="icon" :disabled="disabled" @click="removeItem(painting.rows,row)"><Trash2 /></button></td>
              </tr>
              <tr v-if="!visiblePaintingRows.length"><td :colspan="operationCodes.length * 2 + 9" class="empty">当前配件暂无喷油/移印/UV明细，可新增或从喷油报价单预览导入</td></tr>
            </tbody>
            <tfoot v-if="visiblePaintingRows.length"><tr><td colspan="4">工序合计</td><template v-for="code in operationCodes" :key="`${code}-total`"><td colspan="2" class="painting-operation-total">HKD {{ calculated(paintingOperationTotals[code]) }}</td></template><td class="calculated-cell">HKD {{ calculated(paintingTotal) }}</td><td class="calculated-cell">{{ paintingSplitTotals.valid ? calculated(paintingSplitTotals.paint) : "待核对" }}</td><td class="calculated-cell">{{ paintingSplitTotals.valid ? calculated(paintingSplitTotals.labor) : "待核对" }}</td><td colspan="2" /></tr></tfoot>
          </table>
        </div>
        <div class="painting-summary-card"><strong>二、喷油/移印/UV成本汇总</strong><span>当前填入预览</span><b>HKD {{ calculated(paintingTotal) }}</b><span>正式金额</span><b>保存后由服务端权威重算</b></div>
      </section>
      <section v-if="isDisney" class="payload-block"><header><div><strong>迪士尼 Decoration 部分</strong><span>客户模板按 Application Type、Rate per Op 和 # of Ops 输出；不得从内部喷油小计反推</span></div><button type="button" :disabled="disabled" @click="addDisneyDecoration"><Plus />新增装饰工序</button></header><div class="payload-table-scroll"><table><thead><tr><th>Application Type</th><th>Rate per Op USD</th><th># of Ops</th><th /></tr></thead><tbody><tr v-for="(row,index) in painting.disney_decorations" :key="index"><td><input v-model="row.application_type" :disabled="disabled" aria-label="迪士尼装饰工序"></td><td><input v-model.number="row.rate_per_op_usd" :disabled="disabled" type="number" min="0" step="0.001" aria-label="迪士尼装饰单价 USD"></td><td><input v-model.number="row.operations" :disabled="disabled" type="number" min="0" aria-label="迪士尼装饰次数"></td><td><button type="button" class="icon" :disabled="disabled" @click="remove(painting.disney_decorations,index)"><Trash2 /></button></td></tr><tr v-if="!painting.disney_decorations.length"><td colspan="4" class="empty">存在喷油成本时，未填写客户 Decoration 工序将阻断 P4 接收</td></tr></tbody></table></div></section>
    </template>

    <template v-else-if="props.code === 'slush'">
      <section :id="blockDomId('slush')" class="payload-block" data-form-block>
        <header><div><strong>搪胶部分</strong><span>按产品编号、胶件、材料、料重和日产量记录；总价由系统自动计算。</span></div><div class="block-header-actions"><button v-if="importSourceAttachment('slush')" type="button" title="预览本部分最近导入的 Excel 原文件" @click="previewImportSource('slush')"><Eye />预览附件</button><button type="button" :disabled="disabled" @click="addSlush"><Plus />新增搪胶行</button></div></header>
        <div class="payload-table-scroll">
          <table class="slushTable">
            <thead><tr><th>#</th><th>产品编号</th><th>胶件名称</th><th>材料</th><th>料重 (g)</th><th>日产量 24H</th><th>用量 (PC)</th><th>单价 HKD</th><th>总价 HKD（自动）</th><th>备注</th><th /></tr></thead>
            <tbody>
              <tr v-for="(row,index) in visibleSlushRows" :key="index">
                <td class="row-number">{{ index + 1 }}</td>
                <td><input v-model="row.product_code" :disabled="disabled" aria-label="搪胶产品编号"></td>
                <td><input v-model="row.item" :disabled="disabled" aria-label="搪胶胶件名称"></td>
                <td><input v-model="row.material" :disabled="disabled" aria-label="搪胶材料"></td>
                <td><input v-model.number="row.weight_g" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="搪胶料重"></td>
                <td><input v-model.number="row.daily_output_24h" :disabled="disabled" type="number" min="0" step="1" aria-label="搪胶日产量 24H"></td>
                <td><input v-model.number="row.quantity" :disabled="disabled" type="number" min="0" step="1" aria-label="搪胶用量"></td>
                <td><input v-model.number="row.unit_price_hkd" :disabled="disabled" type="number" min="0" step="0.001" aria-label="搪胶单价 HKD"></td>
                <td class="calculated-cell">{{ calculated(calculateSlushRowAmount(row)) }}</td>
                <td><input v-model="row.remark" :disabled="disabled" aria-label="搪胶备注"></td>
                <td><button type="button" class="icon" :disabled="disabled" @click="removeItem(slush.lines,row)"><Trash2 /></button></td>
              </tr>
              <tr v-if="!visibleSlushRows.length"><td colspan="11" class="empty">当前配件暂无搪胶明细，可新增或从搪胶报价单预览导入</td></tr>
            </tbody>
            <tfoot v-if="visibleSlushRows.length"><tr><td colspan="8">搪胶成本汇总</td><td>HKD {{ calculated(slushTotalHkd) }}</td><td colspan="2" /></tr></tfoot>
          </table>
        </div>
        <div class="slush-summary-card"><strong>合计</strong><span>HKD</span><b>{{ calculated(slushTotalHkd) }}</b><span>RMB（冻结汇率 {{ Number(props.rmbHkdRate || 0).toFixed(2) }}）</span><b>{{ calculated(slushTotalRmb) }}</b></div>
      </section>
    </template>

    <template v-else-if="props.code === 'sewing'">
      <section v-if="sewing.quote_mode === 'quick'" :id="blockDomId('sewing')" class="payload-block quick-quote-card sewing-quick-card" data-form-block>
        <header><div><strong>车缝快捷报价部分</strong><span>急单按单个公仔的港币价钱报价，可增加多个公仔；明细后补时切回明细报价，快捷数据仍会保留。</span></div><div class="block-header-actions"><button v-if="importSourceAttachment('sewing')" type="button" title="预览本部分最近导入的 Excel 原文件" @click="previewImportSource('sewing')"><Eye />预览附件</button><button type="button" :disabled="disabled" @click="addSewingQuickQuote"><Plus />新增公仔</button></div></header>
        <div class="payload-table-scroll">
          <table class="sewingQuickTable">
            <thead><tr><th>#</th><th>公仔名称</th><th>单个公仔价钱 HKD</th><th /></tr></thead>
            <tbody>
              <tr v-for="(row,index) in visibleSewingQuickRows" :key="index"><td class="row-number">{{ index + 1 }}</td><td><input v-model="row.doll_name" :disabled="disabled" :aria-label="`快捷报价公仔 ${index + 1} 名称`" placeholder="填写公仔名称"></td><td><input v-model.number="row.unit_price_hkd" :disabled="disabled" type="number" min="0" step="0.001" :aria-label="`快捷报价公仔 ${index + 1} 价钱 HKD`"></td><td><button type="button" class="icon" :disabled="disabled" @click="removeItem(sewing.quick_quotes,row)"><Trash2 /></button></td></tr>
              <tr v-if="!visibleSewingQuickRows.length"><td colspan="4" class="empty">当前配件至少新增一个公仔并填写名称与 HKD 价钱</td></tr>
            </tbody>
            <tfoot v-if="visibleSewingQuickRows.length"><tr><td colspan="2">快捷报价合计</td><td>HKD {{ calculated(sewingQuickTotalHkd) }}</td><td /></tr></tfoot>
          </table>
        </div>
      </section>
      <section v-else :id="blockDomId('sewing')" class="payload-block" data-form-block>
        <header><div><strong>车缝部分</strong><span>逐行汇率参与换算；成本 HKD = 用量 × 单价 RMB ÷ 汇率，价钱 HKD = 成本 HKD × 码点。</span></div><div class="block-header-actions"><button v-if="importSourceAttachment('sewing')" type="button" title="预览本部分最近导入的 Excel 原文件" @click="previewImportSource('sewing')"><Eye />预览附件</button><button type="button" :disabled="disabled" @click="addSewingGroup"><Plus />新增产品组</button></div></header>
        <article v-for="(group,index) in visibleSewingGroups" :key="index" class="nested-card sewing-card">
          <div class="nested-head"><strong>产品组 {{ index + 1 }}</strong><button type="button" class="icon" :disabled="disabled" @click="removeItem(sewing.groups,group)"><Trash2 /></button></div>
          <div class="inline-fields sewing-group-fields"><label><span>产品</span><input v-model="group.name" :disabled="disabled" placeholder="例如：6寸小蜥蜴 / 盾牌" aria-label="车缝产品名称"></label><label><span>类型</span><select v-model="group.category" :disabled="disabled" aria-label="车缝产品类型"><option value="clothes">车衣</option><option v-if="group.category === 'hair'" value="hair">车发（历史数据，请改用车发部）</option></select></label></div>
          <div class="subhead"><span>车缝物料明细</span><button type="button" :disabled="disabled" @click="addSewingMaterial(group)"><Plus />增加行</button></div>
          <div class="payload-table-scroll">
            <table class="sewingTable">
              <thead><tr><th>#</th><th>物料名称</th><th>裁片部位</th><th>工艺</th><th>裁片数</th><th>供应商</th><th>布料 MOQ/Y</th><th>低于 MOQ/每色费用 RMB</th><th>用量/码</th><th>单价 RMB</th><th>汇率</th><th>成本 HKD（自动）</th><th>码点</th><th>价钱 HKD（自动）</th><th>备注</th><th /></tr></thead>
              <tbody>
                <tr v-for="(row,rowIndex) in group.materials" :key="rowIndex">
                  <td class="row-number">{{ rowIndex + 1 }}</td>
                  <td><textarea v-model="row.item" :disabled="disabled" rows="2" aria-label="车缝布料名称"></textarea></td>
                  <td><input v-model="row.part" :disabled="disabled" aria-label="车缝部位"></td>
                  <td><select v-model="row.craft" :disabled="disabled" aria-label="车缝工艺"><option value="">常规</option><option value="电绣">电绣</option><option value="丝印">丝印</option></select></td>
                  <td><input v-model.number="row.pieces" :disabled="disabled" type="number" min="0" step="1" aria-label="车缝裁片数"></td>
                  <td><input v-model="row.supplier" :disabled="disabled" aria-label="车缝供应商"></td>
                  <td><input v-model.number="row.fabric_moq_y" :disabled="disabled" type="number" min="0" step="1" aria-label="车缝布料 MOQ 每码"></td>
                  <td><input v-model.number="row.below_moq_fee_rmb" :disabled="disabled" type="number" min="0" step="0.001" aria-label="车缝低于 MOQ 每色费用 RMB"></td>
                  <td><input v-model.number="row.usage" :disabled="disabled" type="number" min="0" step="1" aria-label="车缝用量每码"></td>
                  <td><input v-model.number="row.unit_price_rmb" :disabled="disabled" type="number" min="0" step="0.001" aria-label="车缝单价 RMB"></td>
                  <td><input v-model.number="row.exchange_rate" :disabled="disabled" type="number" min="0.0001" step="0.0001" :placeholder="String(props.rmbHkdRate || '')" aria-label="车缝汇率 RMB 转 HKD"></td>
                  <td class="calculated-cell">{{ calculated(calculateSewingBasePriceHkd(row, props.rmbHkdRate)) }}</td>
                  <td><input v-model.number="row.markup" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="车缝码点"></td>
                  <td class="calculated-cell">{{ calculated(calculateSewingRowTotalHkd(row, props.rmbHkdRate)) }}</td>
                  <td><input v-model="row.remark" :disabled="disabled" aria-label="车缝备注"></td>
                  <td><button type="button" class="icon" :disabled="disabled" @click="remove(group.materials,rowIndex)"><Trash2 /></button></td>
                </tr>
                <tr v-if="!group.materials.length"><td colspan="16" class="empty">暂无车缝明细，可增加行或从车缝报价单预览导入</td></tr>
              </tbody>
              <tfoot v-if="group.materials.length"><tr><td colspan="13">本组小计</td><td>HKD {{ calculated(calculateSewingGroupTotalHkd(group, props.rmbHkdRate)) }}</td><td colspan="2" /></tr></tfoot>
            </table>
          </div>
          <div class="sewing-group-status"><span>本组小计：<b>{{ calculated(calculateSewingGroupTotalHkd(group, props.rmbHkdRate)) }}</b> HKD</span><span v-if="sewingEmbroideryCount(group)" class="embroidery-badge">含电绣 {{ sewingEmbroideryCount(group) }} 行</span><span v-if="group.labor_rmb > 0 && !sewingGroupHasLaborLine(group)" class="legacy-labor">已计入历史组人工 RMB {{ calculated(group.labor_rmb) }}</span></div>
        </article>
        <div v-if="!visibleSewingGroups.length" class="empty sewing-empty">当前配件暂无产品组，可新增或从车缝报价单预览导入</div>
        <div class="sewing-summary-card"><strong>配套合计</strong><span>HKD（逐行汇率；旧数据回退冻结汇率 {{ Number(props.rmbHkdRate || 0).toFixed(2) }}）</span><b>{{ calculated(sewingTotalHkd) }}</b></div>
      </section>
    </template>

    <template v-else-if="props.code === 'hair'">
      <section :id="blockDomId('hair')" class="payload-block" data-form-block>
        <header>
          <div><strong>车发部分</strong><span>模板导入读取“明细”页的单价和重量；每行港币单价直接计入本产品车发成本，不再乘以重量。</span></div>
          <button type="button" :disabled="disabled" @click="addHair"><Plus />新增车发行</button>
        </header>
        <div class="payload-table-scroll">
          <table class="hairTable">
            <thead><tr><th>#</th><th>名称</th><th>工艺</th><th>重量 (g)</th><th>单价 (HKD)</th><th>单位</th><th>计入成本 HKD（自动）</th><th>备注</th><th /></tr></thead>
            <tbody>
              <tr v-for="(row,index) in visibleHairRows" :key="index">
                <td class="row-number">{{ index + 1 }}</td>
                <td><input v-model="row.name" :disabled="disabled" aria-label="车发名称"></td>
                <td><input v-model="row.craft" :disabled="disabled" aria-label="车发工艺"></td>
                <td><input v-model.number="row.weight_g" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="车发重量"></td>
                <td><input v-model.number="row.unit_price_hkd" :disabled="disabled" type="number" min="0" step="0.001" aria-label="车发单价 HKD"></td>
                <td><input v-model="row.unit" :disabled="disabled" aria-label="车发单位"></td>
                <td class="calculated-cell">{{ calculated(calculateHairRowAmountHkd(row)) }}</td>
                <td><input v-model="row.remark" :disabled="disabled" aria-label="车发备注"></td>
                <td><button type="button" class="icon" :disabled="disabled" aria-label="删除车发行" @click="removeItem(hair.lines,row)"><Trash2 /></button></td>
              </tr>
              <tr v-if="!visibleHairRows.length"><td colspan="9" class="empty">当前配件暂无车发明细，请新增一行填写</td></tr>
            </tbody>
            <tfoot v-if="visibleHairRows.length"><tr><td colspan="6">车发成本汇总</td><td>HKD {{ calculated(hairTotalHkd) }}</td><td colspan="2" /></tr></tfoot>
          </table>
        </div>
      </section>
    </template>

    <template v-else-if="props.code === 'assembly'">
      <section :id="blockDomId('assembly-summary')" class="payload-block assembly-summary-block" data-form-block>
        <header><div><strong>总表部分</strong><span>各产品人工/PCS 汇总；人工基数与标准工时可按本报价调整</span></div><button v-if="importSourceAttachment('assembly')" type="button" title="预览本部分最近导入的 Excel 原文件" @click="previewImportSource('assembly')"><Eye />预览附件</button></header>
        <div class="inline-fields assembly-base-fields">
          <label><span>人工基数（HKD/人）</span><input v-model.number="assembly.labor_base_hkd" :disabled="disabled" type="number" min="0" step="0.01" aria-label="装配人工基数"></label>
          <label><span>标准工时（H）</span><input v-model.number="assembly.standard_work_hours" :disabled="disabled" type="number" min="0" step="0.01" aria-label="装配标准工时"></label>
        </div>
        <div class="payload-table-scroll">
          <table class="assemblySummaryTable">
            <thead><tr><th>类型</th><th>产品</th><th>标准工时</th><th>基数 HKD</th><th>生产量</th><th>小组</th><th>总人数</th><th>合计 人工/PCS HKD</th></tr></thead>
            <tbody>
              <tr v-for="(group,index) in visibleAssemblySummaryGroups" :key="index"><td>{{ group.category === 'assembly' ? '组装' : '包装/混装' }}</td><td>{{ group.name || '未命名' }}</td><td>{{ Number(assembly.standard_work_hours || 0).toFixed(2) }}</td><td>{{ Number(assembly.labor_base_hkd || 0).toFixed(2) }}</td><td>{{ whole(group.production_qty) }}</td><td>{{ whole(group.teams) }}</td><td>{{ whole(calculateAssemblyGroupPeople(group)) }}</td><td class="calculated-cell">{{ calculated(calculateAssemblyGroupLaborHkd(group, assembly.labor_base_hkd)) }}</td></tr>
              <tr v-if="!visibleAssemblySummaryGroups.length"><td colspan="8" class="empty">当前配件暂无组装产品；包装/混装共用项也尚未新增</td></tr>
            </tbody>
            <tfoot><tr><td colspan="7">组装人工合计</td><td>HKD {{ calculated(assemblyLaborTotal) }}</td></tr><tr><td colspan="7">包装/混装人工合计</td><td>HKD {{ calculated(packagingLaborTotal) }}</td></tr><tr class="assembly-grand-total"><td colspan="7">所有产品总合计 人工/PCS</td><td>HKD {{ calculated(allAssemblyLaborTotal) }}</td></tr></tfoot>
          </table>
        </div>
      </section>

      <section :id="blockDomId('assembly-work')" class="payload-block" data-form-block>
        <header><div><strong>组装部分</strong><span>按产品分组维护组装排拉工序；生产量与小组数在产品组内只填一次</span></div><button type="button" :disabled="disabled" @click="addAssemblyGroup('assembly')"><Plus />新增组装产品</button></header>
        <article v-for="(group,index) in assemblyGroups" :key="index" class="nested-card assembly-group-card">
          <div class="nested-head"><strong>组装产品 {{ index + 1 }}</strong><button type="button" class="icon" :disabled="disabled" aria-label="删除组装产品" @click="removeAssemblyGroup(group)"><Trash2 /></button></div>
          <div class="inline-fields assembly-group-fields">
            <label><span>产品</span><input v-model="group.name" :disabled="disabled" placeholder="例如：6寸小娇媚" aria-label="组装产品名称"></label>
            <label><span>生产量</span><input v-model.number="group.production_qty" :disabled="disabled" type="number" min="0" step="1" aria-label="组装生产量"></label>
            <label><span>小组数</span><input v-model.number="group.teams" :disabled="disabled" type="number" min="0" step="1" aria-label="组装小组数"></label>
            <label v-if="!group.processes.length"><span>总人数</span><input :value="group.total_persons ?? ''" :disabled="disabled" type="number" min="0" step="0.01" placeholder="无工序时手工填写" aria-label="组装总人数" @input="setAssemblyManualPeople(group, $event)"></label>
            <label v-else class="assembly-readonly"><span>总人数（工序汇总）</span><output>{{ whole(calculateAssemblyGroupPeople(group)) }}</output></label>
            <label class="assembly-readonly"><span>合计 人工/PCS HKD（自动）</span><output>{{ calculated(calculateAssemblyGroupLaborHkd(group, assembly.labor_base_hkd)) }}</output></label>
          </div>
          <div class="subhead"><span>工序明细（{{ group.processes.length }} 步）</span><button type="button" :disabled="disabled" @click="addAssemblyProcess(group)"><Plus />新增工序</button></div>
          <div class="payload-table-scroll"><table class="assemblyProcessTable"><thead><tr><th>#</th><th>工序名称</th><th>人数</th><th>备注</th><th /></tr></thead><tbody><tr v-for="(row,rowIndex) in group.processes" :key="rowIndex"><td class="row-number">{{ rowIndex + 1 }}</td><td><input v-model="row.name" :disabled="disabled" aria-label="组装工序名称"></td><td><input v-model.number="row.persons" :disabled="disabled" type="number" min="0" step="0.01" aria-label="组装工序人数"></td><td><input v-model="row.remark" :disabled="disabled" aria-label="组装工序备注"></td><td><button type="button" class="icon" :disabled="disabled" aria-label="删除组装工序" @click="removeAssemblyProcess(group,rowIndex)"><Trash2 /></button></td></tr><tr v-if="!group.processes.length"><td colspan="5" class="empty">暂无组装工序，可直接填写总人数或新增工序</td></tr></tbody></table></div>
        </article>
        <div v-if="!assemblyGroups.length" class="empty">暂无组装产品，可新增产品或上传排拉工序表自动导入</div>
        <div class="assembly-section-total"><strong>所有组装产品合计 人工/PCS</strong><b>HKD {{ calculated(assemblyLaborTotal) }}</b></div>
      </section>

      <section :id="blockDomId('packaging-work')" class="payload-block" data-form-block>
        <header><div><strong>包装部分</strong><span>{{ pricingMode === 'component' ? 'JustPlay 包装人工统一使用右侧“业务部包装”倍率，导出时归入包装明细；与组装共用人工基数和标准工时。' : '按产品分组维护包装/混装排拉工序；与组装共用人工基数和标准工时' }}</span></div><button type="button" :disabled="disabled" @click="addAssemblyGroup('packaging')"><Plus />新增包装产品</button></header>
        <article v-for="(group,index) in packagingGroups" :key="index" class="nested-card assembly-group-card">
          <div class="nested-head"><strong>包装/混装产品 {{ index + 1 }}</strong><button type="button" class="icon" :disabled="disabled" aria-label="删除包装产品" @click="removeAssemblyGroup(group)"><Trash2 /></button></div>
          <div class="inline-fields assembly-group-fields">
            <label><span>产品</span><input v-model="group.name" :disabled="disabled" placeholder="例如：6寸小娇媚" aria-label="包装产品名称"></label>
            <label><span>生产量</span><input v-model.number="group.production_qty" :disabled="disabled" type="number" min="0" step="1" aria-label="包装生产量"></label>
            <label><span>小组数</span><input v-model.number="group.teams" :disabled="disabled" type="number" min="0" step="1" aria-label="包装小组数"></label>
            <label v-if="!group.processes.length"><span>总人数</span><input :value="group.total_persons ?? ''" :disabled="disabled" type="number" min="0" step="0.01" placeholder="无工序时手工填写" aria-label="包装总人数" @input="setAssemblyManualPeople(group, $event)"></label>
            <label v-else class="assembly-readonly"><span>总人数（工序汇总）</span><output>{{ whole(calculateAssemblyGroupPeople(group)) }}</output></label>
            <label class="assembly-readonly"><span>合计 人工/PCS HKD（自动）</span><output>{{ calculated(calculateAssemblyGroupLaborHkd(group, assembly.labor_base_hkd)) }}</output></label>
          </div>
          <div class="subhead"><span>工序明细（{{ group.processes.length }} 步）</span><button type="button" :disabled="disabled" @click="addAssemblyProcess(group)"><Plus />新增工序</button></div>
          <div class="payload-table-scroll"><table class="assemblyProcessTable"><thead><tr><th>#</th><th>工序名称</th><th>人数</th><th>备注</th><th /></tr></thead><tbody><tr v-for="(row,rowIndex) in group.processes" :key="rowIndex"><td class="row-number">{{ rowIndex + 1 }}</td><td><input v-model="row.name" :disabled="disabled" aria-label="包装工序名称"></td><td><input v-model.number="row.persons" :disabled="disabled" type="number" min="0" step="0.01" aria-label="包装工序人数"></td><td><input v-model="row.remark" :disabled="disabled" aria-label="包装工序备注"></td><td><button type="button" class="icon" :disabled="disabled" aria-label="删除包装工序" @click="removeAssemblyProcess(group,rowIndex)"><Trash2 /></button></td></tr><tr v-if="!group.processes.length"><td colspan="5" class="empty">暂无包装工序，可直接填写总人数或新增工序</td></tr></tbody></table></div>
        </article>
        <div v-if="!packagingGroups.length" class="empty">暂无包装/混装产品，可新增产品或上传排拉工序表自动导入</div>
        <div class="assembly-section-total"><strong>所有包装/混装产品合计 人工/PCS</strong><b>HKD {{ calculated(packagingLaborTotal) }}</b></div>
      </section>
    </template>

    <template v-else>
      <section :id="blockDomId('testing-fee')" class="payload-block sales-testing-fee" data-form-block>
        <header>
          <div><strong>测试费部分</strong><span>由业务部填写测试费用总额与一个或多个 MOQ，系统自动计算各档每件测试费 USD。</span></div>
          <div class="calculation-header-actions">
            <label class="freight-status-toggle" :class="{ inactive: !testingFeeCalculationEnabled }">
              <input v-model="testingFeeCalculationEnabled" :disabled="disabled" type="checkbox" aria-label="启用测试费计算">
              <span>{{ testingFeeCalculationEnabled ? '计算测试费' : '不计测试费' }}</span>
            </label>
            <button v-if="testingFeeCalculationEnabled" type="button" :disabled="disabled" aria-label="新增业务部测试费 MOQ" @click="addSalesTestingFeeMoq"><Plus />新增 MOQ</button>
          </div>
        </header>
        <div v-if="!testingFeeCalculationEnabled" class="freight-disabled-notice">
          <strong>本单不计算测试费</strong>
          <span>不会生成测试费分摊结果，客户报价输出中的测试费按 0 处理；测试费用与 MOQ 原值已保留，重新开启即可继续计算。</span>
        </div>
        <template v-else>
          <div class="sales-testing-fee-total">
            <label>
              <span>测试费用 USD</span>
              <input v-model.number="sales.testing_fee_total_usd" :disabled="disabled" type="number" min="0" step="0.01" aria-label="业务部测试费用 USD">
            </label>
          </div>
          <div class="sales-testing-fee-breakdowns">
            <div v-for="(moq,index) in sales.testing_fee_moqs" :key="index" class="sales-testing-fee-breakdown">
              <label>
                <span>MOQ {{ index + 1 }}</span>
                <input v-model.number="sales.testing_fee_moqs[index]" :disabled="disabled" type="number" min="1" step="1" :aria-label="`业务部测试费 MOQ ${index + 1}`" @blur="normalizeSalesTestingFeeMoq(index)">
              </label>
              <label class="sales-testing-fee-result">
                <span>单价 USD（自动）</span>
                <output :aria-label="`业务部测试费单价 USD ${index + 1}`">{{ fixedDecimal(calculateSalesTestingFeeUnitUsd(sales.testing_fee_total_usd, moq), 4) }}</output>
              </label>
              <button type="button" class="icon sales-testing-fee-remove" :disabled="disabled || sales.testing_fee_moqs.length <= 1" :aria-label="`删除业务部测试费 MOQ ${index + 1}`" @click="remove(sales.testing_fee_moqs,index)"><Trash2 /></button>
            </div>
          </div>
        </template>
      </section>
      <section v-if="justPlayCartonAutomatic" :id="blockDomId('customer-supplied-materials')" class="payload-block sales-customer-supplied" data-form-block>
        <header>
          <div><strong>客供物料部分</strong><span>按当前配件填写。保管费 = 单价 × 费率；只收保管费，不取倍率、不加杂项、不退税，导出时单独列示并换算 USD。</span></div>
          <button type="button" :disabled="disabled" aria-label="新增客供物料" @click="addCustomerSuppliedMaterial"><Plus />新增客供物料</button>
        </header>
        <div class="payload-table-scroll">
          <table class="customerSuppliedMaterials">
            <thead><tr><th>#</th><th>物料名称</th><th>物料单价 HKD/件</th><th>保管费率 %</th><th>保管费 HKD/件（自动）</th><th /></tr></thead>
            <tbody>
              <tr v-for="(row,index) in customerSuppliedRows" :key="index">
                <td>{{ index + 1 }}</td>
                <td><input v-model="row.item" :disabled="disabled" aria-label="客供物料名称"></td>
                <td><input v-model.number="row.unit_price_hkd" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="客供物料单价 HKD"></td>
                <td><input v-model.number="row.fee_rate_percent" :disabled="disabled" type="number" min="0" max="100" step="0.01" aria-label="客供物料费率 %"></td>
                <td class="calculated-cell"><output aria-label="客供物料保管费 HKD">{{ fixedDecimal(calculateCustomerSuppliedFeeHkd(row), 4) }}</output></td>
                <td><button type="button" class="icon" :disabled="disabled" aria-label="删除客供物料" @click="removeItem(sales.customer_supplied_materials!,row)"><Trash2 /></button></td>
              </tr>
              <tr v-if="!customerSuppliedRows.length"><td colspan="6" class="empty">当前配件暂无客供物料，可按需要新增</td></tr>
            </tbody>
            <tfoot v-if="customerSuppliedRows.length"><tr><td colspan="4">当前配件保管费合计</td><td colspan="2">HKD {{ fixedDecimal(customerSuppliedTotal, 4) }}</td></tr></tfoot>
          </table>
        </div>
      </section>
      <section :id="blockDomId('packaging-materials')" class="payload-block sales-packaging-materials" data-form-block>
        <header>
          <div><strong>包装材料部分</strong><span>由业务部填写；RMB、HKD 原单价任选一种填写，损耗率默认 1，计价结果由系统生成。</span></div>
          <button type="button" :disabled="disabled" @click="addSalesPackagingMaterial"><Plus />新增包装材料</button>
        </header>
        <div class="payload-table-scroll">
          <table class="packagingMaterials">
            <thead><tr><th>#</th><th>零件名称</th><th>规格</th><th>类别</th><th>用量</th><th>原单价 RMB</th><th>原单价 HKD</th><th>损耗率</th><th>计价单价 HKD（自动）</th><th>成品金额 HKD（自动）</th><th>税点 %</th><th>备注</th><th /></tr></thead>
            <tbody>
              <tr v-for="(row,index) in sales.packaging_materials" :key="index">
                <td>{{ index + 1 }}</td>
                <td><input v-model="row.item" :disabled="disabled" aria-label="包装材料零件名称"></td>
                <td><input v-model="row.specification" :disabled="disabled" aria-label="包装材料规格"></td>
                <td><select v-model="row.category" :disabled="disabled" aria-label="包装材料类别"><option value="blister">吸塑</option><option value="color_box_inner_card">彩盒/内卡</option><option value="leaflet_manual">利宝/说明书</option><option value="other_purchase">其他外购</option></select></td>
                <td><input v-model.number="row.quantity" :disabled="disabled" type="number" min="0" step="1" aria-label="包装材料用量"></td>
                <td><input :value="calculatePackagingMaterialUnitRmb(row, props.rmbHkdRate)" :disabled="disabled" type="number" min="0" step="0.001" aria-label="包装材料原单价 RMB" @input="setPackagingMaterialUnitPrice(row, 'RMB', $event)"></td>
                <td><input :value="calculatePackagingMaterialUnitHkd(row, props.rmbHkdRate)" :disabled="disabled" type="number" min="0" step="0.001" aria-label="包装材料原单价 HKD" @input="setPackagingMaterialUnitPrice(row, 'HKD', $event)"></td>
                <td><input v-model.number="row.loss_rate" :disabled="disabled" type="number" min="0.1" step="0.1" aria-label="包装材料损耗率"></td>
                <td class="calculated-cell">{{ calculated(calculatePackagingMaterialEffectiveUnitHkd(row, props.rmbHkdRate)) }}</td>
                <td class="calculated-cell">{{ calculated(calculatePackagingMaterialAmountHkd(row, props.rmbHkdRate)) }}</td>
                <td><input v-model.number="row.tax_rate_percent" :disabled="disabled" type="number" min="0" max="100" step="0.01" aria-label="包装材料税点"></td>
                <td><input v-model="row.remark" :disabled="disabled" aria-label="包装材料备注"></td>
                <td><button type="button" class="icon" :disabled="disabled" @click="remove(sales.packaging_materials,index)"><Trash2 /></button></td>
              </tr>
              <tr v-if="!sales.packaging_materials.length"><td colspan="13" class="empty">暂无包装材料，可按需要新增</td></tr>
            </tbody>
            <tfoot v-if="sales.packaging_materials.length"><tr><td colspan="9">包装材料合计</td><td class="calculated-cell">HKD {{ calculated(packagingMaterialTotal) }}</td><td colspan="3" /></tr></tfoot>
          </table>
        </div>
      </section>
      <section v-if="pricingMode === 'component'" :id="blockDomId('justplay-packaging')" class="payload-block justplay-packaging" data-form-block>
        <header><div><strong>JustPlay 胶纸及纸托板成本部分</strong><span>自动读取主纸箱尺寸及每箱数量；统一使用右侧“业务部包装”倍率，导出仍列入包装明细。</span></div></header>
        <div class="justplay-packaging-items">
          <article>
            <strong>胶纸/胶水/胶针</strong>
            <div class="inline-fields">
              <label><span>胶纸附加金额 HKD/件</span><input :value="justPlayExtraDisplay('adhesive_extra_hkd')" :disabled="disabled" type="number" min="0" step="0.1" aria-label="胶纸附加金额 HKD/件" @focus="editingJustPlayExtra = 'adhesive_extra_hkd'" @input="updateJustPlayPackagingInput('adhesive_extra_hkd', $event)" @blur="finishJustPlayExtra('adhesive_extra_hkd', $event)"></label>
              <label class="sales-testing-fee-result"><span>单件成本 HKD（自动）</span><output aria-label="胶纸单件成本 HKD">{{ calculated(justPlayAdhesivePackagingCost) }}</output></label>
            </div>
          </article>
          <article>
            <strong>纸托板成本</strong>
            <div class="inline-fields">
              <label v-for="field in justPlayPalletFields" :key="field.key"><span>{{ field.label }}</span><input :value="justPlayPackagingInputs[field.key]" :disabled="disabled" type="number" min="0" step="any" :aria-label="field.label" @input="updateJustPlayPackagingInput(field.key, $event)"></label>
            </div>
            <div class="inline-fields">
              <label class="sales-testing-fee-result"><span>每托板装箱数（自动）</span><output aria-label="每托板装箱数">{{ justPlayCartonsPerPallet }}</output></label>
              <label><span>纸托板附加金额 HKD/件</span><input :value="justPlayExtraDisplay('paper_pallet_extra_hkd')" :disabled="disabled" type="number" min="0" step="0.1" aria-label="纸托板附加金额 HKD/件" @focus="editingJustPlayExtra = 'paper_pallet_extra_hkd'" @input="updateJustPlayPackagingInput('paper_pallet_extra_hkd', $event)" @blur="finishJustPlayExtra('paper_pallet_extra_hkd', $event)"></label>
              <label class="sales-testing-fee-result"><span>单件成本 HKD（自动）</span><output aria-label="纸托板单件成本 HKD">{{ calculated(justPlayPaperPalletCost) }}</output></label>
            </div>
          </article>
        </div>
        <p v-if="justPlayPackagingWarning" class="justplay-packaging-warning" role="alert">{{ justPlayPackagingWarning }}</p>
        <div class="calculation-strip"><span>胶纸及纸托板合计：<b>HKD {{ calculated(justPlayFixedPackagingTotal) }}</b></span></div>
      </section>
      <section v-if="isDisney" class="payload-block disney-packaging-fields">
        <header><div><strong>迪士尼包装件客户字段部分</strong><span>业务部包装材料逐行进入客户模板 Package Parts；英文说明、USD 单价与 Included 必须显式填写。</span></div></header>
        <div class="payload-table-scroll"><table class="extraWide disneyPackagingFields"><thead><tr><th>#</th><th>内部包装件</th><th>类别</th><th>Disney Description</th><th>Unit Cost USD</th><th>Included</th></tr></thead><tbody><tr v-for="(row,index) in sales.packaging_materials" :key="index"><td>{{ index + 1 }}</td><td><span class="fixed-field">{{ row.item || '未填写' }}</span></td><td><span class="fixed-field">{{ row.category }}</span></td><td><input v-model="row.disney_description" :disabled="disabled" aria-label="迪士尼包装件英文说明"></td><td><input v-model.number="row.disney_unit_price_usd" :disabled="disabled" type="number" min="0" step="0.001" aria-label="迪士尼包装件单价 USD"></td><td><input v-model.number="row.disney_included" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="迪士尼包装件 Included"></td></tr><tr v-if="!sales.packaging_materials.length"><td colspan="6" class="empty">请先在包装材料部分新增内部成本行</td></tr></tbody></table></div>
      </section>
      <section :id="blockDomId('cartons')" class="payload-block sales-packaging" data-form-block>
        <header>
          <div><strong>纸箱计算与包装尺寸部分</strong><span>由业务部填写；工程部不再维护纸箱和平卡。纸箱尺寸会自动计算 CU.FT、箱价和平卡单件成本。</span></div>
          <button type="button" :disabled="disabled" data-testid="add-sales-carton" aria-label="新增纸箱" title="新增内纸箱" @click="addSalesCarton"><Plus />新增纸箱</button>
        </header>
        <div class="inline-fields four packaging-base">
          <label><span>主纸箱系数（箱价基数）</span><input v-model.number="sales.paper_price_factor" :disabled="disabled" type="number" min="0.01" step="0.01" aria-label="主纸箱纸价系数"></label>
          <label><span>内纸箱系数（新增后可调）</span><input v-model.number="innerPaperPriceFactor" :disabled="disabled || !hasInnerCarton" type="number" min="0.01" step="0.01" aria-label="内纸箱纸价系数" :title="hasInnerCarton ? '用于所有内纸箱' : '新增内纸箱后可调整'"></label>
          <label><span>平卡报价系数（默认同箱价）</span><input v-model.number="flatCardPriceFactor" :disabled="disabled" type="number" min="0.01" step="0.01" aria-label="平卡报价系数"></label>
        </div>
        <div class="dimension-grid">
          <article class="dimension-card">
            <strong>产品尺寸 (in{{ justPlayCartonAutomatic && cartonState.source === 'product' ? '，当前计算来源' : '，可不填' }})</strong>
            <div class="inline-fields">
              <label><span>长 L</span><input v-model.number="sales.product_size_in.length" :disabled="disabled" type="number" min="0" step="0.01" aria-label="产品长度 IN"></label>
              <label><span>宽 W</span><input v-model.number="sales.product_size_in.width" :disabled="disabled" type="number" min="0" step="0.01" aria-label="产品宽度 IN"></label>
              <label><span>高 H</span><input v-model.number="sales.product_size_in.height" :disabled="disabled" type="number" min="0" step="0.01" aria-label="产品高度 IN"></label>
            </div>
          </article>
          <article class="dimension-card">
            <div class="dimension-card-title">
              <strong>彩盒尺寸</strong>
              <label class="dimension-unit-control"><span>单位</span><select v-model="colorBoxSizeUnit" :disabled="disabled" aria-label="彩盒尺寸单位"><option value="inch">inch</option><option value="cm">cm</option></select></label>
            </div>
            <div class="inline-fields">
              <label><span>长 L ({{ colorBoxSizeUnit }})</span><input :value="dimensionInputValue(sales.color_box_size_in.length, colorBoxSizeUnit)" :disabled="disabled" type="number" min="0" :step="colorBoxSizeUnit === 'cm' ? 0.1 : 0.01" :aria-label="`彩盒长度 ${colorBoxSizeUnit}`" @input="updateColorBoxDimension('length', $event)"></label>
              <label><span>宽 W ({{ colorBoxSizeUnit }})</span><input :value="dimensionInputValue(sales.color_box_size_in.width, colorBoxSizeUnit)" :disabled="disabled" type="number" min="0" :step="colorBoxSizeUnit === 'cm' ? 0.1 : 0.01" :aria-label="`彩盒宽度 ${colorBoxSizeUnit}`" @input="updateColorBoxDimension('width', $event)"></label>
              <label><span>高 H ({{ colorBoxSizeUnit }})</span><input :value="dimensionInputValue(sales.color_box_size_in.height, colorBoxSizeUnit)" :disabled="disabled" type="number" min="0" :step="colorBoxSizeUnit === 'cm' ? 0.1 : 0.01" :aria-label="`彩盒高度 ${colorBoxSizeUnit}`" @input="updateColorBoxDimension('height', $event)"></label>
            </div>
            <template v-if="justPlayCartonAutomatic">
              <div class="inline-fields">
                <label><span>无 PDQ 时的尺寸来源</span><select :value="justPlayCarton.dimension_source" :disabled="disabled || cartonState.usesPdq" aria-label="主纸箱尺寸来源" @change="updateJustPlayCarton('dimension_source', $event)"><option value="color_box">按彩盒尺寸</option><option value="product">按产品尺寸</option></select></label>
              </div>
              <div class="inline-fields">
                <label v-for="axis in cartonDimensionAxes" :key="axis.key"><span>{{ axis.label }}方向个数</span><input :value="justPlayCarton[axis.count]" :disabled="disabled || cartonState.usesPdq" type="number" min="1" step="1" :aria-label="`${axis.label}方向个数`" @input="updateJustPlayCarton(axis.count, $event)"></label>
              </div>
              <p class="justplay-carton-note">方向个数仅用于无 PDQ 时的纸箱尺寸计算，不会修改每箱产品数量。</p>
            </template>
          </article>
          <article v-if="justPlayCartonAutomatic" class="dimension-card pdq-dimensions">
            <div class="dimension-card-title"><strong>PDQ 尺寸（选填，有填写时优先使用）</strong><label class="dimension-unit-control"><span>单位</span><select v-model="pdqSizeUnit" :disabled="disabled" aria-label="PDQ 尺寸单位"><option value="inch">inch</option><option value="cm">cm</option></select></label></div>
            <div class="inline-fields">
              <label v-for="axis in cartonDimensionAxes" :key="axis.key"><span>{{ axis.label }} ({{ pdqSizeUnit }})</span><input :value="dimensionInputValue(sales.pdq_size_in?.[axis.key] ?? 0, pdqSizeUnit)" :disabled="disabled" type="number" min="0" :step="pdqSizeUnit === 'cm' ? 0.1 : 0.01" :aria-label="`PDQ ${axis.label} ${pdqSizeUnit}`" @input="updatePdqDimension(axis.key, $event)"></label>
            </div>
            <p class="justplay-carton-note">三项全部留空或为 0 表示不使用 PDQ；使用时请完整填写长、宽、高，不乘方向个数。</p>
          </article>
          <p v-if="justPlayCartonAutomatic && cartonState.error" class="justplay-packaging-warning" role="alert">{{ cartonState.error }}</p>
        </div>
        <article v-for="(carton,index) in sales.cartons" :key="index" class="nested-card carton-card">
          <p v-if="justPlayCartonAutomatic && index === 0" class="justplay-carton-note">{{ cartonState.usesPdq ? '主纸箱按 PDQ 尺寸自动计算：长、宽各加 0.75，高加 1。' : `主纸箱按${justPlayCarton.dimension_source === 'product' ? '产品' : '彩盒'}尺寸 × 各方向个数自动计算：长、宽再加 0.75，高再加 1。` }}计算单位为英寸。</p>
          <div class="nested-head"><strong>{{ index === 0 ? '主纸箱' : `内纸箱 ${index}` }}</strong><div class="nested-head-actions"><label class="dimension-unit-control"><span>尺寸单位</span><select :value="cartonSizeUnit(carton)" :disabled="disabled" :aria-label="`纸箱 ${index + 1} 尺寸单位`" @change="updateCartonSizeUnit(carton, $event)"><option value="inch">inch</option><option value="cm">cm</option></select></label><button type="button" class="icon" :disabled="disabled || index === 0" :title="index === 0 ? '主纸箱不可删除' : '删除内纸箱'" :aria-label="`删除纸箱 ${index + 1}`" @click="removeSalesCarton(index)"><Trash2 /></button></div></div>
          <div class="inline-fields five">
            <label><span>纸箱名称</span><input v-model="carton.item" :disabled="disabled" aria-label="纸箱名称"></label>
            <label><span>长 L ({{ cartonSizeUnit(carton) }}){{ justPlayCartonAutomatic && index === 0 ? '（自动）' : '' }}</span><input :value="dimensionInputValue(carton.length_in, cartonSizeUnit(carton))" :readonly="justPlayCartonAutomatic && index === 0" :disabled="disabled" type="number" min="0" :step="cartonSizeUnit(carton) === 'cm' ? 0.1 : 0.01" :aria-label="`纸箱长度 ${cartonSizeUnit(carton)}`" @input="updateCartonDimension(carton, 'length_in', $event)"></label>
            <label><span>宽 W ({{ cartonSizeUnit(carton) }}){{ justPlayCartonAutomatic && index === 0 ? '（自动）' : '' }}</span><input :value="dimensionInputValue(carton.width_in, cartonSizeUnit(carton))" :readonly="justPlayCartonAutomatic && index === 0" :disabled="disabled" type="number" min="0" :step="cartonSizeUnit(carton) === 'cm' ? 0.1 : 0.01" :aria-label="`纸箱宽度 ${cartonSizeUnit(carton)}`" @input="updateCartonDimension(carton, 'width_in', $event)"></label>
            <label><span>高 H ({{ cartonSizeUnit(carton) }}){{ justPlayCartonAutomatic && index === 0 ? '（自动）' : '' }}</span><input :value="dimensionInputValue(carton.height_in, cartonSizeUnit(carton))" :readonly="justPlayCartonAutomatic && index === 0" :disabled="disabled" type="number" min="0" :step="cartonSizeUnit(carton) === 'cm' ? 0.1 : 0.01" :aria-label="`纸箱高度 ${cartonSizeUnit(carton)}`" @input="updateCartonDimension(carton, 'height_in', $event)"></label>
            <label><span>一箱装的个数</span><input v-model.number="carton.qty_per_carton" :disabled="disabled" type="number" min="1" step="1" aria-label="一箱装的个数"></label>
          </div>
          <div class="calculation-strip">
            <span><b>CU.FT</b> {{ measured(calculateCartonCuft(carton)) }}</span>
            <span><b>纸价系数</b> {{ measured(cartonPaperPriceFactor(index)) }}</span>
            <span><b>箱价 HKD</b> {{ calculated(calculateCartonPriceHkd(carton, cartonPaperPriceFactor(index))) }}</span>
            <span><b>平卡合计 HKD</b> {{ calculated(flatCardTotal(index)) }}</span>
            <span><b>单件纸箱成本 HKD</b> {{ calculated(calculateCartonUnitCostHkd(carton, cartonPaperPriceFactor(index), flatCardPriceFactor)) }}</span>
            <span><b>每箱数量</b> {{ carton.qty_per_carton || 0 }}</span>
          </div>
          <div v-if="isDisney" class="inline-fields four disney-carton-fields"><label><span>迪士尼 Carton Unit Cost USD</span><input v-model.number="carton.disney_unit_price_usd" :disabled="disabled" type="number" min="0" step="0.001" aria-label="迪士尼纸箱单价 USD"></label></div>
          <div class="subhead"><span>配的平卡 (inch)</span><button type="button" :disabled="disabled" @click="addSalesFlatCard(index)"><Plus />新增平卡</button></div>
          <div class="payload-table-scroll"><table><thead><tr><th>名称</th><th>长 L (in)</th><th>宽 W (in)</th><th>用量</th><th>平卡价 HKD（自动）</th><th /></tr></thead><tbody><tr v-for="(flat,flatIndex) in carton.flat_cards" :key="flatIndex"><td><input v-model="flat.name" :disabled="disabled" aria-label="平卡名称"></td><td><input v-model.number="flat.length_in" :disabled="disabled" type="number" min="0" step="0.01" aria-label="平卡长度 IN"></td><td><input v-model.number="flat.width_in" :disabled="disabled" type="number" min="0" step="0.01" aria-label="平卡宽度 IN"></td><td><input v-model.number="flat.quantity" :disabled="disabled" type="number" min="0" step="1" :aria-label="`平卡 ${flatIndex + 1} 用量`"></td><td class="calculated-cell">{{ calculated(calculateFlatCardPriceHkd(flat, flatCardPriceFactor)) }}</td><td><button type="button" class="icon" :disabled="disabled" @click="remove(carton.flat_cards,flatIndex)"><Trash2 /></button></td></tr><tr v-if="!carton.flat_cards.length"><td colspan="6" class="empty">暂无平卡，可按需要新增</td></tr></tbody></table></div>
        </article>
      </section>
      <section :id="blockDomId('freight')" class="payload-block sales-freight" data-form-block>
        <header>
          <div><strong>运费计算部分</strong><span>运费与吊柜费可独立启用；两项分别读取冻结的报价基数，并按主纸箱 CU.FT 与每箱数量计算。</span></div>
          <div class="freight-toggle-group">
            <label class="freight-status-toggle" :class="{ inactive: !freightCalculationEnabled }">
              <input v-model="freightCalculationEnabled" :disabled="disabled" type="checkbox" aria-label="启用运费计算">
              <span>{{ freightCalculationEnabled ? '计算运费' : '不计运费' }}</span>
            </label>
            <label class="freight-status-toggle" :class="{ inactive: !liftingCalculationEnabled }">
              <input v-model="liftingCalculationEnabled" :disabled="disabled" type="checkbox" aria-label="启用吊柜费计算">
              <span>{{ liftingCalculationEnabled ? '计算吊柜费' : '不计吊柜费' }}</span>
            </label>
          </div>
        </header>
        <div v-if="!anyFreightCalculationEnabled" class="freight-disabled-notice">
          <strong>本单不计算运费和吊柜费</strong>
          <span>不会生成运输费用权威快照，也不计入成本；容量和费用原值已保留，重新开启即可继续计算。</span>
        </div>
        <template v-else>
          <div v-if="primaryCarton" class="freight-source-strip">
            <span><b>数据来源</b> {{ primaryCarton.item || '纸箱 1' }}</span>
            <span><b>主纸箱 CU.FT</b> {{ measured(freightSourceCuft) }}</span>
            <span><b>每箱数量</b> {{ primaryCarton.qty_per_carton || 0 }} PCS</span>
          </div>
          <div v-else class="freight-source-strip freight-source-missing">请先在“纸箱计算与包装尺寸”新增主纸箱，运费和吊柜费结果将自动联动。</div>
          <div class="inline-fields four freight-capacity-fields">
            <label v-for="capacity in freightCapacityDefinitions" :key="capacity.key">
              <span>{{ capacity.label }}（CUFT，整数）</span>
              <input v-model.number="sales.freight_calc[capacity.key]" :disabled="disabled" type="number" min="1" step="1" :aria-label="capacity.label" @blur="normalizeFreightCapacity(capacity.key)">
            </label>
          </div>
          <div class="payload-table-scroll">
            <table class="freightTable">
              <thead><tr><th>输出</th><th>运输方案</th><th>柜/车容量 CUFT</th><th>运费 HKD（报价基数）</th><th>吊柜费 HKD（报价基数）</th><th>总箱数（自动）</th><th>运费 HKD/PCS（自动）</th><th>吊柜费 HKD/PCS（自动）</th><th>合计 HKD/PCS（自动）</th></tr></thead>
              <tbody>
                <tr v-for="option in freightOptions" :key="option.key">
                  <td><label class="freight-route-output"><input :checked="freightRouteIncluded(option.key)" :disabled="disabled" type="checkbox" :aria-label="`输出运输规格 ${option.label}`" @change="setFreightRouteIncluded(option.key, $event)"><span>{{ freightRouteIncluded(option.key) ? '输出' : '不输出' }}</span></label></td>
                  <td><strong>{{ option.label }}</strong><span class="freight-fee-label">{{ option.feeLabel }} / {{ option.liftingFeeLabel }}</span></td>
                  <td class="calculated-cell">{{ whole(option.capacityCuft) }}</td>
                  <td class="calculated-cell"><output :aria-label="option.feeLabel">{{ whole(option.freightCostHkd) }}</output></td>
                  <td class="calculated-cell"><output :aria-label="option.liftingFeeLabel">{{ whole(option.liftingCostHkd) }}</output></td>
                  <td class="calculated-cell">{{ option.totalCartons || '—' }}</td>
                  <td class="calculated-cell">{{ option.totalCartons ? calculated(option.freightPerPieceHkd) : '—' }}</td>
                  <td class="calculated-cell">{{ option.totalCartons ? calculated(option.liftingPerPieceHkd) : '—' }}</td>
                  <td class="calculated-cell">{{ option.totalCartons ? calculated(option.perPieceHkd) : '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </section>
      <section v-if="isThreeSixty" class="payload-block">
        <header>
          <div>
            <strong>360 客户报价专属资料</strong>
            <span>纸箱、CU.FT、装箱数、测试费及各分段成本均自动读取上方资料和服务器计算；这里只填写客户抬头与最终采用的运费路线</span>
          </div>
        </header>
        <div class="inline-fields four">
          <label><span>MS Brand</span><input v-model="sales.customer_quote_fields.three_sixty.ms_brand" :disabled="disabled" aria-label="360 MS Brand"></label>
          <label><span>製表人</span><input v-model="sales.customer_quote_fields.three_sixty.prepared_by" :disabled="disabled" aria-label="360 製表人"></label>
          <label><span>发行日期</span><input v-model="sales.customer_quote_fields.three_sixty.quote_date" :disabled="disabled" type="date" aria-label="360 发行日期"></label>
          <label><span>Version</span><input v-model="sales.customer_quote_fields.three_sixty.revision" :disabled="disabled" aria-label="360 Version"></label>
          <label><span>首次货柜出货日期</span><input v-model="sales.customer_quote_fields.three_sixty.first_etd" :disabled="disabled" aria-label="360 首次货柜出货日期"></label>
          <label>
            <span>客户报价运费路线</span>
            <select v-model="sales.customer_quote_fields.three_sixty.freight_route_key" :disabled="disabled" aria-label="360 运费路线">
              <option value="">请选择服务器已计算路线</option>
              <option v-for="option in freightOptions" :key="option.key" :value="option.key">{{ option.label }}</option>
            </select>
          </label>
        </div>
      </section>
      <section v-if="isCaixing" class="payload-block"><header><div><strong>彩星客户报价专属资料</strong><span>外箱资料自动读取上方“基础纸箱”；包装、外购和工序成本按各已审批分段自动归入客户模板，不重复填写。加价比例留空时使用客户基础信息。</span></div></header><div class="inline-fields five"><label><span>产品类型</span><select v-model="sales.customer_quote_fields.caixing.product_type" :disabled="disabled" aria-label="彩星产品类型"><option value="plastic">塑胶</option><option value="plush">毛绒</option></select></label><label><span>Item No.</span><input v-model="sales.customer_quote_fields.caixing.item_number" :disabled="disabled" aria-label="彩星 Item Number"></label><label><span>Item Description</span><input v-model="sales.customer_quote_fields.caixing.item_name" :disabled="disabled" aria-label="彩星 Item Description"></label><label><span>Quote Date</span><input v-model="sales.customer_quote_fields.caixing.quote_date" :disabled="disabled" type="date" aria-label="彩星 Quote Date"></label><label><span>本单普通项目加价比例</span><input v-model.number="sales.customer_quote_fields.caixing.markup_rate_override" :disabled="disabled" type="number" min="0" max="1" step="0.01" placeholder="留空用客户默认" aria-label="彩星本单加价比例"></label></div></section>
      <section v-if="isBuzzBee" class="payload-block">
        <header><div><strong>BuzzBee 报客信息</strong><span>每个方案分别新建报价；彩盒按整箱价录入，输出除装箱数并始终另报。FSC 价由客户维护费率计算。</span></div></header>
        <div class="payload-grid">
          <label>报客版式<select v-model="sales.customer_quote_fields.buzzbee.template_profile" :disabled="disabled" aria-label="BuzzBee 报客版式"><option v-for="profile in buzzBeeTemplateProfiles" :key="profile.id" :value="profile.id">{{ profile.label }}</option></select></label>
          <label v-if="sales.customer_quote_fields.buzzbee.template_profile === 'laser'">功能说明<textarea v-model="sales.customer_quote_fields.buzzbee.notes" :disabled="disabled" aria-label="BuzzBee 功能说明" /></label>
        </div>
        <header><strong>彩盒报价分档</strong><button v-if="sales.customer_quote_fields.buzzbee.color_box_tiers.length < 2" type="button" :disabled="disabled" @click="addBuzzBeeColorBoxTier"><Plus />新增分档</button></header>
        <div class="payload-table-scroll"><table><thead><tr><th>分档</th><th>整箱报客彩盒价 HKD</th><th>MOQ</th><th /></tr></thead><tbody><tr v-for="(row,index) in sales.customer_quote_fields.buzzbee.color_box_tiers" :key="index"><td>第 {{ index + 1 }} 档</td><td><input v-model.number="row.quote_price_hkd" :disabled="disabled" type="number" min="0" step="0.001" :aria-label="`BuzzBee 第 ${index + 1} 档彩盒价`"></td><td><input v-model="row.moq" :disabled="disabled" :aria-label="`BuzzBee 第 ${index + 1} 档 MOQ`" placeholder="例如 MOQ3000"></td><td><button type="button" class="icon" :disabled="disabled" @click="remove(sales.customer_quote_fields.buzzbee.color_box_tiers,index)"><Trash2 /></button></td></tr><tr v-if="!sales.customer_quote_fields.buzzbee.color_box_tiers.length"><td colspan="4" class="empty">存在彩盒时，请完整填写两档价格和 MOQ</td></tr></tbody></table></div>
      </section>
      <section v-if="isDisney" class="payload-block"><header><div><strong>迪士尼客户报价字段部分</strong><span>Item Number、报价日期/版本及 3K/5K/10K 三档必须完整；这些值只用于客户模板，不参与内部成本计算</span></div></header><div class="inline-fields four"><label><span>Item Number</span><input v-model="sales.customer_quote_fields.disney.item_number" :disabled="disabled" aria-label="迪士尼 Item Number"></label><label><span>报价日期</span><input v-model="sales.customer_quote_fields.disney.quote_date" :disabled="disabled" type="date" aria-label="迪士尼报价日期"></label><label><span>Revision</span><input v-model.number="sales.customer_quote_fields.disney.revision" :disabled="disabled" type="number" min="0" aria-label="迪士尼 Revision"></label><label><span>最低 MOQ</span><input v-model.number="sales.customer_quote_fields.disney.minimum_order_qty" :disabled="disabled" type="number" min="0" aria-label="迪士尼最低 MOQ"></label><label><span>3K 报价 USD</span><input v-model.number="sales.customer_quote_fields.disney.moq_prices_usd.qty_3000" :disabled="disabled" type="number" min="0" step="0.001" aria-label="迪士尼 3K 报价"></label><label><span>5K 报价 USD</span><input v-model.number="sales.customer_quote_fields.disney.moq_prices_usd.qty_5000" :disabled="disabled" type="number" min="0" step="0.001" aria-label="迪士尼 5K 报价"></label><label><span>10K 报价 USD</span><input v-model.number="sales.customer_quote_fields.disney.moq_prices_usd.qty_10000" :disabled="disabled" type="number" min="0" step="0.001" aria-label="迪士尼 10K 报价"></label><label><span>Transportation USD</span><input v-model.number="sales.customer_quote_fields.disney.transportation_usd" :disabled="disabled" type="number" min="0" step="0.001" aria-label="迪士尼运输费 USD"></label><label><span>Model USD</span><input v-model.number="sales.customer_quote_fields.disney.model_cost_usd" :disabled="disabled" type="number" min="0" step="0.01" aria-label="迪士尼手办费 USD"></label><label><span>Set Up Charge USD</span><input v-model.number="sales.customer_quote_fields.disney.setup_charge_usd" :disabled="disabled" type="number" min="0" step="0.01" aria-label="迪士尼设置费 USD"></label></div></section>
      <InternalQuoteDickieSales v-if="isDickie" :sales="sales" :routes="referenceFreightRoutes" :disabled="disabled" />
    </template>
    </main>
  </div>
</template>

<style scoped>
.justplay-carton-note{margin:10px;color:#0f766e;font-size:12px}.carton-card input[readonly]{background:#f0fdfa;color:#0f766e}
.justplay-packaging-items{display:grid;gap:12px;padding:12px}.justplay-packaging-items article{border:1px solid #dbe5ea;border-radius:9px;background:#f8fafc;padding:12px}.justplay-packaging-items article>strong{color:#334155;font-size:13px}.justplay-packaging-items .inline-fields{padding:10px 0 0}.justplay-packaging-warning{margin:0 12px 12px;color:#b45309;font-size:12px}
.section-payload-form{display:grid;gap:12px;padding:12px;background:#f8fafc}.payload-standard-notice{display:flex;align-items:center;gap:10px;border:1px solid #99f6e4;border-radius:10px;background:#f0fdfa;padding:10px 12px}.payload-standard-notice strong{flex:0 0 auto;color:#0f766e;font-size:13px}.payload-standard-notice span{color:#475569;font-size:12px}.quote-pricing-assignment{display:grid;gap:9px;border:1px solid #bae6fd;border-radius:10px;background:#f0f9ff;padding:11px 12px}.quote-pricing-assignment header>div{display:grid;gap:3px}.quote-pricing-assignment header strong{color:#0c4a6e;font-size:13px}.quote-pricing-assignment header span{color:#475569;font-size:11px;line-height:1.45}.quote-pricing-assignment-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:7px}.quote-pricing-assignment-grid article{display:grid;grid-template-columns:minmax(0,1fr) 118px;align-items:center;gap:8px;border:1px solid #dbeafe;border-radius:8px;background:#fff;padding:8px}.quote-pricing-assignment-grid article>strong{overflow:hidden;color:#334155;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.payload-block{overflow:hidden;border:1px solid #dbe5ea;border-radius:11px;background:#fff}.payload-block>header{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid #e2e8f0;padding:11px 12px;background:#f8fafc}.payload-block>header>div{display:grid}.payload-block header strong{color:#334155;font-size:13px}.payload-block header span{margin-top:2px;color:#64748b;font-size:11px}.payload-block button,.subhead button{display:inline-flex;min-height:32px;align-items:center;gap:5px;border:1px solid #99f6e4;border-radius:8px;background:#f0fdfa;padding:0 10px;color:#0f766e;font-size:12px;font-weight:800}.payload-block button svg,.subhead button svg{width:14px;height:14px}.payload-block button:disabled{cursor:not-allowed;opacity:.4}.payload-table-scroll{overflow:auto}.payload-table-scroll table{width:100%;min-width:620px;border-collapse:collapse}.payload-table-scroll table.wide{min-width:1050px}.payload-table-scroll table.extraWide{min-width:1850px}.payload-table-scroll table.caixingToolPlan{min-width:2700px}.payload-table-scroll table.painting{min-width:2850px}.payload-table-scroll th{background:#eef2f6;padding:8px;color:#64748b;font-size:11px;text-align:left;white-space:nowrap}.payload-table-scroll td{border-top:1px solid #eef2f6;padding:6px}.payload-table-scroll input,.payload-table-scroll select,.payload-table-scroll textarea,.inline-fields input,.inline-fields select{width:100%;min-width:70px;border:1px solid #dbe5ea;border-radius:7px;background:#fff;padding:0 8px;color:#334155;font-size:13px}.payload-table-scroll input,.payload-table-scroll select,.inline-fields input,.inline-fields select{height:34px}.payload-table-scroll textarea{min-height:52px;padding-block:7px;resize:vertical}.payload-table-scroll input:focus,.payload-table-scroll select:focus,.payload-table-scroll textarea:focus,.inline-fields input:focus,.inline-fields select:focus{border-color:#14b8a6;outline:2px solid rgb(20 184 166/.12)}.payload-table-scroll input:disabled,.payload-table-scroll select:disabled,.payload-table-scroll textarea:disabled,.inline-fields input:disabled,.inline-fields select:disabled{background:#f8fafc;color:#64748b}.payload-table-scroll .icon,.nested-head .icon{display:grid;width:30px;min-height:30px;place-items:center;border-color:transparent;background:transparent;padding:0;color:#94a3b8}.payload-table-scroll .icon:hover:not(:disabled),.nested-head .icon:hover:not(:disabled){background:#fef2f2;color:#dc2626}.empty{padding:22px!important;color:#94a3b8;text-align:center;font-size:12px}.inline-fields{display:grid;grid-template-columns:repeat(3,minmax(150px,1fr));gap:10px;padding:12px}.inline-fields.four{grid-template-columns:repeat(4,minmax(130px,1fr))}.inline-fields.five{grid-template-columns:repeat(5,minmax(110px,1fr));padding:0}.inline-fields label{display:grid;gap:5px}.inline-fields label span{color:#64748b;font-size:11px;font-weight:700}.nested-card{margin:10px;border:1px solid #e2e8f0;border-radius:9px;background:#fff}.nested-head,.subhead{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:8px 10px}.nested-head{border-bottom:1px solid #eef2f6;background:#f8fafc}.nested-head strong{color:#475569;font-size:12px}.subhead{border-top:1px solid #eef2f6}.subhead span{color:#475569;font-size:11px;font-weight:800}.subhead button{min-height:28px;border-color:#dbe5ea;background:#fff;color:#475569;font-size:11px}.disabled{--form-disabled:1}
.payload-table-scroll table.packagingMaterials{min-width:1750px}.payload-table-scroll tfoot td{border-top:1px solid #99f6e4;background:#f0fdfa;color:#475569;font-size:12px;font-weight:800}.packaging-base{padding-bottom:4px}.dimension-grid{display:grid;grid-template-columns:1fr;gap:10px;padding:4px 12px 10px}.dimension-card{overflow:hidden;border:1px solid #e2e8f0;border-radius:9px;background:#f8fafc}.dimension-card>strong{display:block;padding:9px 12px 0;color:#475569;font-size:12px}.dimension-card-title{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:8px 12px 0}.dimension-card-title>strong{color:#475569;font-size:12px}.dimension-unit-control{display:flex!important;grid-template-columns:none!important;align-items:center;gap:7px}.dimension-unit-control span{white-space:nowrap}.dimension-unit-control select{height:30px;min-width:78px;border:1px solid #cbd5e1;border-radius:7px;background:#fff;padding:0 8px;color:#334155;font-size:12px}.dimension-unit-control select:focus{border-color:#14b8a6;outline:2px solid rgb(20 184 166/.12)}.dimension-unit-control select:disabled{background:#f1f5f9;color:#64748b}.nested-head-actions{display:flex;align-items:center;gap:8px}.dimension-card .inline-fields{padding-top:8px}.carton-card .inline-fields{padding:10px}.calculation-strip{display:flex;flex-wrap:wrap;gap:10px;margin:0 10px 10px;border:1px solid #fde68a;border-radius:8px;background:#fffbeb;padding:10px;color:#475569;font-size:12px}.calculation-strip span{display:inline-flex;gap:5px}.calculation-strip b{color:#0f766e;font-weight:800}.calculated-cell{background:#ecfdf5!important;color:#0f766e!important;font-variant-numeric:tabular-nums;font-weight:900!important}.packaging-empty{margin:0 12px 12px;border:1px dashed #cbd5e1;border-radius:9px}
.sales-testing-fee-total{padding:14px 14px 8px}.sales-testing-fee-total label,.sales-testing-fee-breakdown label{display:grid;gap:6px}.sales-testing-fee-total label{max-width:430px}.sales-testing-fee-total span,.sales-testing-fee-breakdown span{color:#64748b;font-size:11px;font-weight:800}.sales-testing-fee-total input,.sales-testing-fee-breakdown input{height:38px;width:100%;border:1px solid #dbe5ea;border-radius:8px;background:#fff;padding:0 10px;color:#334155;font-size:13px}.sales-testing-fee-total input:focus,.sales-testing-fee-breakdown input:focus{border-color:#14b8a6;outline:2px solid rgb(20 184 166/.12)}.sales-testing-fee-total input:disabled,.sales-testing-fee-breakdown input:disabled{background:#f8fafc;color:#64748b}.sales-testing-fee-breakdown{display:grid;grid-template-columns:minmax(180px,430px) minmax(180px,430px);gap:12px;padding:8px 14px 14px}.sales-testing-fee-result output{display:flex;height:38px;align-items:center;border:1px solid #99f6e4;border-radius:8px;background:#f0fdfa;padding:0 10px;color:#0f766e;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:13px;font-weight:900}.sales-testing-fee-formula{display:flex;gap:10px;border-top:1px solid #e2e8f0;background:#f8fafc;padding:10px 14px;color:#64748b;font-size:11px;line-height:1.5}.sales-testing-fee-formula strong{color:#0f766e}@media(max-width:720px){.sales-testing-fee-breakdown{grid-template-columns:1fr}}
.payload-table-scroll table.engineeringHardware{min-width:1650px}.payload-table-scroll table.engineeringAuxiliary{min-width:1850px}.fixed-field{display:flex;height:34px;align-items:center;border:1px solid #dbe5ea;border-radius:7px;background:#f8fafc;padding:0 8px;color:#0f766e;font-size:13px;font-weight:800}.fixed-field.numeric{justify-content:flex-end;font-variant-numeric:tabular-nums}.payload-table-scroll table.engineeringMolds{min-width:2650px}.mold-image-cell{min-width:126px}.mold-image-list{display:flex;max-width:150px;flex-wrap:wrap;gap:4px}.mold-image-list a{display:block;overflow:hidden;width:46px;height:46px;border:1px solid #99f6e4;border-radius:7px;background:#f0fdfa}.mold-image-list img{display:block;width:100%;height:100%;object-fit:contain}.mold-image-cell small{display:block;margin-top:4px;color:#0f766e;font-size:10px;white-space:nowrap}.engineering-mold-parts{display:grid;gap:10px;border-top:1px solid #ccfbf1;background:#f8fafc;padding:12px}.engineering-mold-part-card{overflow:hidden;background:#fff}.engineering-mold-part-card .nested-head>div:first-child{display:grid;gap:2px}.engineering-mold-part-card .nested-head span{color:#64748b;font-size:10px}.mold-part-rule{border-top:1px solid #eef2f6;border-bottom:1px solid #eef2f6;background:#f0fdfa;padding:8px 12px;color:#0f766e;font-size:10px;line-height:1.5}.payload-table-scroll table.engineeringMoldParts{min-width:1050px}.engineeringMoldParts th:nth-child(2),.engineeringMoldParts td:nth-child(2){min-width:220px}.engineeringMoldParts th:nth-child(3),.engineeringMoldParts td:nth-child(3),.engineeringMoldParts th:nth-child(4),.engineeringMoldParts td:nth-child(4){min-width:150px}.calculation-header-actions{display:flex!important;align-items:center;justify-content:flex-end;gap:8px}.payload-table-scroll table.productionMoldCosts{min-width:760px}.payload-table-scroll table.moldAllocationSummary{min-width:920px}.moldAllocationSummary th:nth-child(2),.moldAllocationSummary td:nth-child(2){min-width:430px}.inline-fields.seven.mold-allocation-inputs{grid-template-columns:repeat(7,minmax(0,1fr));gap:6px;border-top:1px solid #eef2f6;background:#f8fafc;padding:8px 10px}.mold-allocation-inputs label{min-width:0;gap:3px}.mold-allocation-inputs label span{overflow:hidden;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.mold-allocation-inputs input{height:30px;min-width:0;padding:0 6px;font-size:12px}
.electronic-card{overflow:hidden}.nested-actions{display:flex;align-items:center;gap:6px}.nested-actions button:not(.icon){display:inline-flex;min-height:28px;align-items:center;gap:4px;border:1px solid #dbe5ea;border-radius:7px;background:#fff;padding:0 9px;color:#0f766e;font-size:11px;font-weight:800}.payload-table-scroll table.electronicTable{min-width:1500px}.electronicTable th:first-child,.electronicTable td:first-child{width:80px;white-space:nowrap}.electronicTable th:nth-child(2),.electronicTable td:nth-child(2){min-width:170px}.electronicTable th:nth-child(3),.electronicTable td:nth-child(3){min-width:210px}.electronicTable th:nth-child(9),.electronicTable td:nth-child(9){min-width:190px}.electronic-child-row{background:#f8fafc}.payload-table-scroll table.electronicQuickTable{min-width:940px}.electronicQuickTable th:first-child,.electronicQuickTable td:first-child{width:52px}.electronicQuickTable th:nth-child(2),.electronicQuickTable td:nth-child(2){min-width:190px}.electronicQuickTable th:nth-child(6),.electronicQuickTable td:nth-child(6){min-width:220px}.payload-table-scroll table.electronicSummaryTable{min-width:1050px;table-layout:fixed}.electronicSummaryTable th,.electronicSummaryTable td{width:14.2857%;padding-right:8px;padding-left:8px;text-align:center;vertical-align:middle}.electronicSummaryTable td{color:#475569;font-variant-numeric:tabular-nums;font-weight:700}.electronicSummaryTable .quote-total{background:#ecfdf5;color:#0f766e;font-size:14px;font-weight:900}.electronic-formula-note{display:grid;grid-template-columns:auto 1fr;gap:10px;border-top:1px solid #e2e8f0;background:#f8fafc;padding:10px 12px;color:#64748b;font-size:11px;line-height:1.5}.electronic-formula-note strong{color:#0f766e}
.molding-header-actions{display:flex;align-items:center;gap:8px}.molding-header-actions label{display:flex;align-items:center;gap:6px;color:#64748b;font-size:11px;font-weight:800}.molding-header-actions label span{margin:0}.molding-header-actions input{width:76px;height:32px;border:1px solid #dbe5ea;border-radius:7px;padding:0 8px;color:#334155}.payload-table-scroll table.moldingInjectionTable{min-width:2450px}.payload-table-scroll table.moldingBlowTable{min-width:2450px}.moldingInjectionTable th:nth-child(2),.moldingInjectionTable td:nth-child(2){min-width:190px}.moldingInjectionTable th:nth-child(16),.moldingInjectionTable td:nth-child(16),.moldingBlowTable th:nth-child(17),.moldingBlowTable td:nth-child(17){min-width:170px}.injection-row-actions{display:flex;align-items:center;justify-content:center;gap:4px}.injection-row-actions .icon{flex:0 0 auto}.row-number{color:#64748b;text-align:center;font-weight:800}.snapshot-cell{min-width:116px;background:#ecfdf5;color:#0f766e;font-size:11px;font-variant-numeric:tabular-nums;font-weight:900;white-space:nowrap}.snapshot-cell.amount{background:#dcfce7;color:#047857}.molding-summary-grid{display:grid;grid-template-columns:minmax(260px,1fr) repeat(4,minmax(170px,auto));gap:10px;border-top:1px solid #99f6e4;background:#f0fdfa;padding:10px 12px;color:#64748b;font-size:11px}.molding-summary-grid b{color:#0f766e;text-align:right}.molding-formula-note{display:grid;grid-template-columns:auto 1fr;gap:10px;border-top:1px solid #e2e8f0;background:#f8fafc;padding:10px 12px;color:#64748b;font-size:11px;line-height:1.5}.molding-formula-note strong{color:#0f766e}
.painting th:nth-child(2),.painting td:nth-child(2){min-width:180px}.painting th:nth-child(3),.painting td:nth-child(3),.painting th:nth-child(4),.painting td:nth-child(4){min-width:135px}.painting th:nth-last-child(2),.painting td:nth-last-child(2){min-width:180px}.painting-operation-total{background:#ecfdf5;color:#0f766e;font-weight:900;text-align:center;white-space:nowrap}.painting-summary-card{display:grid;grid-template-columns:minmax(220px,1fr) auto minmax(130px,auto) auto minmax(200px,auto);align-items:center;gap:14px;border-top:1px solid #99f6e4;background:#f0fdfa;padding:11px 12px;color:#64748b;font-size:11px}.painting-summary-card strong{color:#334155;font-size:12px}.painting-summary-card b{color:#0f766e;text-align:right}.painting-formula-note{display:grid;grid-template-columns:auto 1fr;gap:10px;border-top:1px solid #e2e8f0;background:#f8fafc;padding:10px 12px;color:#64748b;font-size:11px;line-height:1.5}.painting-formula-note strong{color:#0f766e}
.payload-table-scroll table.slushTable{min-width:1650px}.slushTable th:nth-child(2),.slushTable td:nth-child(2){min-width:135px}.slushTable th:nth-child(3),.slushTable td:nth-child(3),.slushTable th:nth-child(4),.slushTable td:nth-child(4){min-width:150px}.slushTable th:nth-child(10),.slushTable td:nth-child(10){min-width:210px}.slush-summary-card{display:grid;grid-template-columns:minmax(180px,1fr) auto minmax(130px,auto) auto minmax(130px,auto);align-items:center;gap:14px;border-top:1px solid #99f6e4;background:#f0fdfa;padding:11px 12px;color:#64748b;font-size:11px}.slush-summary-card strong{color:#334155;font-size:12px}.slush-summary-card b{color:#0f766e;text-align:right}.slush-formula-note{display:grid;grid-template-columns:auto 1fr;gap:10px;border-top:1px solid #e2e8f0;background:#f8fafc;padding:10px 12px;color:#64748b;font-size:11px;line-height:1.5}.slush-formula-note strong{color:#0f766e}
.payload-table-scroll table.hairTable{min-width:1200px}.hairTable th:nth-child(2),.hairTable td:nth-child(2),.hairTable th:nth-child(3),.hairTable td:nth-child(3){min-width:180px}.hairTable th:nth-child(8),.hairTable td:nth-child(8){min-width:220px}.hair-formula-note{display:grid;grid-template-columns:auto 1fr;gap:10px;border-top:1px solid #e2e8f0;background:#f8fafc;padding:10px 12px;color:#64748b;font-size:11px;line-height:1.5}.hair-formula-note strong{color:#0f766e}
.sewing-group-fields{grid-template-columns:minmax(260px,1fr) minmax(140px,220px)}.payload-table-scroll table.sewingTable{min-width:2460px}.sewingTable th:nth-child(2),.sewingTable td:nth-child(2){min-width:230px}.sewingTable th:nth-child(3),.sewingTable td:nth-child(3){min-width:130px}.sewingTable th:nth-child(6),.sewingTable td:nth-child(6){min-width:130px}.sewingTable th:nth-child(15),.sewingTable td:nth-child(15){min-width:220px}.sewing-group-status{display:flex;flex-wrap:wrap;align-items:center;gap:12px;border-top:1px solid #eef2f6;padding:9px 12px;color:#64748b;font-size:11px}.sewing-group-status b{color:#0f766e}.embroidery-badge{border-radius:999px;background:#dcfce7;padding:3px 8px;color:#15803d;font-weight:800}.legacy-labor{border-radius:999px;background:#fffbeb;padding:3px 8px;color:#92400e}.sewing-empty{border-top:1px solid #eef2f6}.sewing-summary-card{display:grid;grid-template-columns:minmax(180px,1fr) auto minmax(130px,auto);align-items:center;gap:14px;border-top:1px solid #99f6e4;background:#f0fdfa;padding:11px 12px;color:#64748b;font-size:11px}.sewing-summary-card strong{color:#334155;font-size:12px}.sewing-summary-card b{color:#0f766e;text-align:right}.sewing-formula-note{display:grid;grid-template-columns:auto 1fr;gap:10px;border-top:1px solid #e2e8f0;background:#f8fafc;padding:10px 12px;color:#64748b;font-size:11px;line-height:1.5}.sewing-formula-note strong{color:#0f766e}
.assembly-base-fields{grid-template-columns:repeat(2,minmax(160px,260px))}.assembly-formula-note{display:flex;gap:10px;border-top:1px solid #fde68a;border-bottom:1px solid #fde68a;background:#fffbeb;padding:9px 12px;color:#64748b;font-size:11px;line-height:1.5}.assembly-formula-note strong{color:#0f766e}.payload-table-scroll table.assemblySummaryTable{min-width:780px}.assemblySummaryTable td{color:#475569;font-size:12px;font-variant-numeric:tabular-nums}.assemblySummaryTable td:last-child,.assemblySummaryTable th:last-child{text-align:right}.assemblySummaryTable tfoot td{text-align:right}.assemblySummaryTable tfoot td:first-child{color:#475569}.assemblySummaryTable tfoot .assembly-grand-total td{background:#dcfce7;color:#15803d;font-size:13px;font-weight:900}.assembly-group-fields{grid-template-columns:minmax(210px,1.5fr) repeat(2,minmax(95px,.65fr)) minmax(110px,.75fr) minmax(170px,1fr)}.assembly-readonly output{display:flex;height:34px;box-sizing:border-box;align-items:center;border:1px solid #99f6e4;border-radius:7px;background:#f0fdfa;padding:0 9px;color:#0f766e;font-size:13px;font-variant-numeric:tabular-nums;font-weight:900}.payload-table-scroll table.assemblyProcessTable{min-width:680px}.assemblyProcessTable th:first-child,.assemblyProcessTable td:first-child{width:52px}.assemblyProcessTable th:nth-child(2),.assemblyProcessTable td:nth-child(2){width:34%}.assemblyProcessTable th:nth-child(3),.assemblyProcessTable td:nth-child(3){width:120px}.assembly-section-total{display:flex;align-items:center;justify-content:space-between;gap:12px;border-top:1px solid #86efac;background:#ecfdf5;padding:11px 12px;color:#166534;font-size:12px}.assembly-section-total b{color:#15803d;font-size:13px;font-variant-numeric:tabular-nums}.assembly-group-card{overflow:hidden}
.freight-source-strip{display:flex;flex-wrap:wrap;gap:18px;margin:12px 12px 0;border:1px solid #99f6e4;border-radius:9px;background:#f0fdfa;padding:10px 12px;color:#475569;font-size:12px}.freight-source-strip b{color:#0f766e}.freight-source-missing{border-style:dashed;border-color:#cbd5e1;background:#f8fafc;color:#94a3b8}.freight-capacity-fields{padding-bottom:10px}.payload-table-scroll table.freightTable{min-width:1420px}.freightTable td:nth-child(2) strong,.freight-fee-label{display:block}.freight-route-output{display:grid;justify-items:center;gap:3px;color:#64748b;font-size:10px;font-weight:800}.freight-route-output input{width:15px;height:15px;accent-color:#0f766e}.freight-fee-label{margin-top:2px;color:#94a3b8;font-size:10px}.freight-formula-note{display:grid;grid-template-columns:auto 1fr;gap:4px 10px;border-top:1px solid #e2e8f0;background:#f8fafc;padding:10px 12px;color:#64748b;font-size:11px}.freight-formula-note strong{grid-row:1/3;color:#0f766e}.freight-formula-note span{line-height:1.5}
.freight-toggle-group{display:flex;flex-wrap:wrap;align-items:center;justify-content:flex-end;gap:7px}.freight-status-toggle{display:inline-flex;min-height:32px;align-items:center;gap:7px;border:1px solid #5eead4;border-radius:999px;background:#f0fdfa;padding:0 11px;color:#0f766e;cursor:pointer}.freight-status-toggle.inactive{border-color:#cbd5e1;background:#fff;color:#64748b}.freight-status-toggle input{width:14px;height:14px;accent-color:#0f766e}.freight-status-toggle span{margin:0!important;color:inherit!important;font-size:12px!important;font-weight:800}.freight-disabled-notice{display:grid;gap:4px;margin:12px;border:1px dashed #cbd5e1;border-radius:9px;background:#f8fafc;padding:14px}.freight-disabled-notice strong{color:#475569;font-size:12px}.freight-disabled-notice span{color:#64748b;font-size:11px;line-height:1.5}
/* Department forms can contain many independent blocks; completion now lives in page navigation. */
.section-payload-form{position:relative;grid-template-columns:minmax(0,1fr);align-items:start}.payload-standard-notice{grid-column:1;grid-row:1}.section-payload-blocks{display:grid;min-width:0;grid-column:1;grid-row:2;gap:12px}.form-block-anchor{display:none}[data-form-block]{scroll-margin-top:96px}.payload-block>header{position:relative;overflow:hidden;border-bottom-color:#0f766e;background:linear-gradient(105deg,#134e4a 0%,#0f766e 58%,#0d9488 100%);padding:13px 14px;box-shadow:inset 4px 0 #5eead4}.payload-block>header::after{position:absolute;right:-28px;top:-42px;width:132px;height:132px;border-radius:999px;background:rgb(255 255 255/.08);content:"";pointer-events:none}.payload-block>header>div,.payload-block>header>button,.payload-block>header>.molding-header-actions,.payload-block>header>.freight-status-toggle,.payload-block>header>.freight-toggle-group,.payload-block>header>.block-header-actions{position:relative;z-index:1}.payload-block>header strong{color:#fff;font-size:14px;letter-spacing:.02em}.payload-block>header span{color:#ccfbf1;font-size:11px}.payload-block>header button{border-color:#ccfbf1;background:#fff;color:#0f766e;box-shadow:0 3px 10px rgb(15 118 110/.18)}.block-header-actions{display:flex!important;align-items:center;justify-content:flex-end;gap:7px}
.quick-painting-fields{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:10px;padding:14px}.quick-painting-fields label{display:grid;gap:6px}.quick-painting-fields label>span{color:#64748b;font-size:11px;font-weight:800}.quick-painting-fields input,.quick-readonly output{display:flex;height:38px;box-sizing:border-box;align-items:center;border:1px solid #cbd5e1;border-radius:8px;background:#fff;padding:0 10px;color:#0f172a;font-size:14px}.quick-readonly output{border-color:#99f6e4;background:#f0fdfa;color:#0f766e;font-weight:900}.quick-readonly.total output{border-color:#6ee7b7;background:#ecfdf5;color:#047857}.quick-quote-note{display:flex;gap:10px;border-top:1px solid #ccfbf1;background:#f0fdfa;padding:10px 14px;color:#64748b;font-size:11px;line-height:1.55}.quick-quote-note strong{flex:0 0 auto;color:#0f766e}.payload-table-scroll table.sewingQuickTable{min-width:620px}.sewingQuickTable th:first-child,.sewingQuickTable td:first-child{width:52px}.sewingQuickTable th:nth-child(2),.sewingQuickTable td:nth-child(2){width:50%}.sewingQuickTable th:nth-child(3),.sewingQuickTable td:nth-child(3){width:34%}
@media(max-width:900px){.inline-fields,.inline-fields.four,.inline-fields.five,.inline-fields.seven.mold-allocation-inputs,.assembly-group-fields{grid-template-columns:1fr 1fr}.molding-summary-grid{grid-template-columns:1fr 1fr}.molding-summary-grid>span{grid-column:1/-1}.painting-summary-card,.slush-summary-card,.sewing-summary-card{grid-template-columns:1fr auto}.painting-summary-card strong,.slush-summary-card strong,.sewing-summary-card strong{grid-column:1/-1}}
@media(max-width:600px){.inline-fields,.inline-fields.four,.inline-fields.five,.inline-fields.seven.mold-allocation-inputs,.dimension-grid,.quick-painting-fields{grid-template-columns:1fr}.payload-block>header{align-items:flex-start;flex-direction:column}}
.sales-testing-fee-breakdowns{display:grid;padding:4px 14px 14px}.sales-testing-fee-breakdown{grid-template-columns:minmax(180px,430px) minmax(180px,430px) 38px;padding:10px 0}.sales-testing-fee-breakdown+.sales-testing-fee-breakdown{border-top:1px solid #eef2f6}.sales-testing-fee-remove{align-self:end;width:38px;height:38px}.sales-testing-fee-remove:disabled{cursor:not-allowed;opacity:.4}@media(max-width:720px){.sales-testing-fee-breakdown{grid-template-columns:1fr 1fr 38px}}@media(max-width:520px){.sales-testing-fee-breakdown{grid-template-columns:1fr 38px}.sales-testing-fee-result{grid-column:1}.sales-testing-fee-remove{grid-column:2;grid-row:1/3}}
.engineering-sync-badge{display:inline-flex!important;align-items:center;border:1px solid rgb(204 251 241/.7);border-radius:999px;background:rgb(255 255 255/.14);padding:4px 8px;color:#fff!important;font-size:10px!important;font-weight:800;white-space:nowrap}.payload-table-scroll input.engineering-prefilled:disabled,.payload-table-scroll textarea.engineering-prefilled:disabled{border-color:#99f6e4;background:#ecfdf5;color:#0f766e;font-weight:800;opacity:1;-webkit-text-fill-color:#0f766e}
.payload-table-scroll table.disneyPurchasedParts{min-width:1250px}.payload-table-scroll table.disneyMoldFields{min-width:1450px}.payload-table-scroll table.disneyInjectionFields{min-width:1050px}.payload-table-scroll table.disneyPackagingFields{min-width:980px}.disney-carton-fields{border-top:1px solid #eef2f6;background:#f8fafc}
.mold-split-preview{display:grid;gap:8px;margin:12px;border:1px solid #5eead4;border-radius:9px;background:#f0fdfa;padding:12px;font-size:12px;color:#134e4a}
.mold-split-preview p{margin:0;line-height:1.6}.mold-split-preview .split-warning{color:#92400e}
.mold-split-preview ol{margin:0;padding-left:24px}.mold-split-preview li{padding:4px}.mold-split-preview li b{margin-left:16px;font-size:11px}
.mold-split-preview .nested-actions{display:flex;gap:8px}.mold-split-preview button{border:1px solid #5eead4;border-radius:6px;background:#fff;padding:7px 12px}
.mold-split-preview button:disabled{opacity:.5;cursor:not-allowed}
.payload-table-scroll table.customerSuppliedMaterials{min-width:760px;width:100%}.customerSuppliedMaterials th:first-child,.customerSuppliedMaterials td:first-child{width:48px}.customerSuppliedMaterials th:nth-child(2),.customerSuppliedMaterials td:nth-child(2){width:38%}.customerSuppliedMaterials th:last-child,.customerSuppliedMaterials td:last-child{width:56px}.customerSuppliedMaterials output{color:#0f766e;font-weight:800;font-variant-numeric:tabular-nums}
</style>

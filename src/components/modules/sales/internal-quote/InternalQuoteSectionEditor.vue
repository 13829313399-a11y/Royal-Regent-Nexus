<script setup lang="ts">
import { AlertCircle, CheckCircle2, Download, Eye, FileSpreadsheet, Info, LockKeyhole, Paperclip, RefreshCw, Save, Send, Trash2, Undo2, XCircle, Zap } from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import type { ApiInternalQuoteImportPreview, ApiInternalQuoteSection } from '@/api/internalQuote'
import InternalQuoteAttachmentPreview from './InternalQuoteAttachmentPreview.vue'
import InternalQuoteSectionForm from './InternalQuoteSectionForm.vue'
import InternalQuoteImportAssignment from './InternalQuoteImportAssignment.vue'
import InternalQuoteMappedAssignment from './InternalQuoteMappedAssignment.vue'
import { getInternalQuoteFormBlocks, type InternalQuoteFormBlock } from '@/lib/internalQuoteBlockProgress'
import { calculateElectronicSectionSummary, cloneInternalQuotePayload, electronicQuoteGroups, isElectronicQuoteGroupsPayload, normalizeInternalQuotePayload, salesPackagingPricingGroupId, salesSettlementDivisorForMiscRatio, type ElectronicPayload, type ElectronicQuoteGroup, type SalesMarkupTier } from '@/lib/internalQuoteSectionPayload'
import { useAuthStore } from '@/stores/auth'
import { createRandomUuid } from '@/lib/randomUuid'
import { normalizeInternalQuoteDraft } from '@/lib/internalQuoteMoldingReferences'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import type { InternalQuote, InternalQuoteAttachmentRecord, InternalQuoteSection, InternalQuoteSectionCode, InternalQuoteSectionStatus } from '@/types/internalQuoteDesk'
import type { SalesPricingComponent } from '@/lib/internalQuoteSectionPayload'

const props = withDefaults(defineProps<{
  quote: InternalQuote
  section: InternalQuoteSection
  canEdit: boolean
  canReview: boolean
  canRemove: boolean
  wholeQuoteReview?: boolean
  activePricingComponentId?: string
  mainMarkupPreview?: number
  differsFromBaseline?: boolean
  differenceDetails?: string[]
}>(), {
  wholeQuoteReview: false,
  activePricingComponentId: '',
  differsFromBaseline: false,
  differenceDetails: () => [],
})
const emit = defineEmits<{
  remove: [sectionCode: InternalQuoteSectionCode]
  'block-progress': [sectionCode: InternalQuoteSectionCode, blocks: InternalQuoteFormBlock[]]
  'preview-file': [sectionCode: InternalQuoteSectionCode, attachment: InternalQuoteAttachmentRecord]
}>()

const quoteStore = useInternalQuoteDeskStore()
const authStore = useAuthStore()
const draftPayload = ref<Record<string, unknown>>({})
const baselinePayload = ref('')
const draftRevision = ref(props.section.revision)
const importPreview = ref<ApiInternalQuoteImportPreview>()
const importAssignments = ref<Record<string, string>>({})
const electronicImportTarget = ref<string>()
const activeElectronicGroupId = ref('legacy')
watch(() => importPreview.value?.batch_id, () => {
  importAssignments.value = {}
  electronicImportTarget.value = props.section.code === 'electronic' ? 'new' : undefined
})
const assignmentComplete = computed(() => (importPreview.value?.assignment_rows ?? []).every(row => Boolean(importAssignments.value[row.key])))
const previewAttachmentTarget = ref<InternalQuoteAttachmentRecord>()
const deleteAttachmentTarget = ref<InternalQuoteAttachmentRecord>()
const actionReason = ref('')
const reasonAction = ref<'reject' | 'na' | 'reopen'>()
const localMessage = ref('')
const localError = ref('')
const salesPricingPayload = computed(() => {
  const salesSection = props.quote.sections.find((section) => section.code === 'sales')
  return salesSection?.payload && typeof salesSection.payload === 'object' ? salesSection.payload : {}
})
const pricingComponents = computed<SalesPricingComponent[]>(() => {
  const source = salesPricingPayload.value.pricing_components
  if (!Array.isArray(source)) return []
  return source.flatMap((value) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return []
    const row = value as Record<string, unknown>
    const id = String(row.id ?? '').trim()
    const name = String(row.name ?? '').trim()
    const markup = Number(row.markup_x)
    return id && name ? [{ id, name, ...(Number.isFinite(markup) && markup > 0 ? { markup_x: markup } : {}) }] : []
  })
})
const pricingMode = computed<'standard' | 'component'>(() => (
  salesPricingPayload.value.pricing_mode === 'component' && pricingComponents.value.length ? 'component' : 'standard'
))
const mainMarkup = computed(() => {
  const preview = Number(props.mainMarkupPreview)
  if (Number.isFinite(preview) && preview > 0) return preview
  return Number(props.quote.rr2CostSummary.shippingPricing.markup) || 1.2
})
const supportsQuickQuote = computed(() => ['electronic', 'painting', 'sewing'].includes(props.section.code))
const electronicGroups = computed<ElectronicQuoteGroup[]>(() => (
  props.section.code === 'electronic' && isElectronicQuoteGroupsPayload(draftPayload.value)
    ? electronicQuoteGroups(draftPayload.value)
    : []
))
function electronicPayloadHasContent(payload: Record<string, unknown>) {
  const quickRows = Array.isArray(payload.quick_quotes) ? payload.quick_quotes : []
  const components = Array.isArray(payload.components) ? payload.components : []
  return quickRows.length > 0 || components.length > 0 || [
    'bonding_rmb', 'smt_rmb', 'labor_rmb', 'testing_rmb', 'packaging_rmb',
    'bonding_hkd', 'smt_hkd', 'labor_hkd', 'testing_hkd', 'packaging_hkd',
  ].some((key) => Number(payload[key]) > 0)
}
const electronicHasExistingData = computed(() => {
  if (props.section.code !== 'electronic') return false
  return electronicGroups.value.length > 0 || electronicPayloadHasContent(draftPayload.value)
})
const electronicGroupOptions = computed<ElectronicQuoteGroup[]>(() => {
  if (props.section.code !== 'electronic') return []
  if (electronicGroups.value.length) return electronicGroups.value
  return electronicPayloadHasContent(draftPayload.value)
    ? [{ id: 'legacy', name: '电子报价1', ...(draftPayload.value as unknown as ElectronicPayload) }]
    : []
})
const activeElectronicGroup = computed(() => electronicGroupOptions.value.find((group) => group.id === activeElectronicGroupId.value) ?? electronicGroupOptions.value[0])
const electronicFormPayload = computed<Record<string, unknown>>({
  get() {
    if (props.section.code !== 'electronic' || !electronicGroups.value.length) return draftPayload.value
    return activeElectronicGroup.value ?? normalizeInternalQuotePayload('electronic', {})
  },
  set(value) {
    const normalized = normalizeInternalQuotePayload('electronic', value)
    if (!electronicGroups.value.length) {
      draftPayload.value = normalized
      return
    }
    const activeId = activeElectronicGroup.value?.id
    draftPayload.value = normalizeInternalQuotePayload('electronic', {
      quote_groups: electronicGroups.value.map((group) => group.id === activeId ? {
        id: group.id,
        name: group.name,
        ...(group.import_batch_id ? { import_batch_id: group.import_batch_id } : {}),
        ...(group.source_sha256 ? { source_sha256: group.source_sha256 } : {}),
        ...normalized,
      } : group),
    })
  },
})
const formPayload = computed<Record<string, unknown>>({
  get: () => props.section.code === 'electronic' ? electronicFormPayload.value : draftPayload.value,
  set: (value) => {
    if (props.section.code === 'electronic') electronicFormPayload.value = value
    else draftPayload.value = value
  },
})
const isQuickQuoteMode = computed(() => (props.section.code === 'electronic' ? electronicFormPayload.value : draftPayload.value).quote_mode === 'quick')
const electronicSectionSummary = computed(() => calculateElectronicSectionSummary(draftPayload.value, props.quote.fxRmbHkd))
const electronicImportTargets = computed(() => electronicGroupOptions.value.map((group) => ({ id: group.id, name: group.name })))
const selectedElectronicImportTarget = computed(() => electronicImportTargets.value.find((target) => target.id === electronicImportTarget.value))
const selectedElectronicImportRows = computed(() => {
  const group = electronicGroupOptions.value.find((entry) => entry.id === selectedElectronicImportTarget.value?.id)
  return Array.isArray(group?.components) ? group.components.length : 0
})
const electronicImportExistingLabel = computed(() => electronicImportTarget.value === 'new'
  ? `当前已有 ${electronicGroupOptions.value.length} 份报价；新报价 0 行`
  : `当前目标报价 ${selectedElectronicImportRows.value} 行`)
const electronicImportResultRows = computed(() => Number(importPreview.value?.diff_summary.imported_rows ?? importPreview.value?.row_count ?? 0))
const showElectronicForm = computed(() => props.section.code !== 'electronic'
  || !isElectronicQuoteGroupsPayload(draftPayload.value)
  || electronicGroupOptions.value.length > 0)
watch(electronicGroupOptions, (groups) => {
  if (props.section.code === 'electronic' && groups.length && !groups.some((group) => group.id === activeElectronicGroupId.value)) {
    activeElectronicGroupId.value = groups[0]!.id
  }
}, { immediate: true })
const quickQuoteButtonLabel = computed(() => {
  if (!isQuickQuoteMode.value) return '快捷报价'
  return editable.value ? '返回明细报价' : '快捷报价中'
})

function toggleQuickQuoteMode() {
  if (!editable.value || !supportsQuickQuote.value) return
  const nextMode = isQuickQuoteMode.value ? 'detail' : 'quick'
  const base = props.section.code === 'electronic' ? electronicFormPayload.value : draftPayload.value
  const next: Record<string, unknown> = { ...base, quote_mode: nextMode }
  if (props.section.code === 'electronic' && nextMode === 'quick') {
    const quickRows = Array.isArray(next.quick_quotes) ? next.quick_quotes : []
    if (!quickRows.length) next.quick_quotes = [{ item: '', unit_price_rmb: 0, tax_rate_percent: 13, remark: '', ...(pricingMode.value === 'component' && props.activePricingComponentId ? { pricing_component_id: props.activePricingComponentId } : {}) }]
  }
  if (props.section.code === 'sewing' && nextMode === 'quick') {
    const quickRows = Array.isArray(next.quick_quotes) ? next.quick_quotes : []
    if (!quickRows.length) next.quick_quotes = [{ doll_name: '', unit_price_hkd: 0, ...(pricingMode.value === 'component' && props.activePricingComponentId ? { pricing_component_id: props.activePricingComponentId } : {}) }]
  }
  if (props.section.code === 'painting' && nextMode === 'quick' && pricingMode.value === 'component' && props.activePricingComponentId) {
    const quickQuote = next.quick_quote && typeof next.quick_quote === 'object' && !Array.isArray(next.quick_quote)
      ? next.quick_quote as Record<string, unknown>
      : {}
    if (!quickQuote.pricing_component_id && !Number(quickQuote.spray_labor_hkd) && !Number(quickQuote.paint_hkd)) {
      next.quick_quote = { ...quickQuote, pricing_component_id: props.activePricingComponentId }
    }
  }
  if (props.section.code === 'electronic') electronicFormPayload.value = next
  else draftPayload.value = normalizeInternalQuotePayload(props.section.code, next)
  localMessage.value = nextMode === 'quick'
    ? `${props.section.label}已切换为快捷报价；保存后可按快捷金额提交审核。`
    : `${props.section.label}已切回明细报价；快捷数据会保留但不重复计入金额。`
}

function addElectronicQuoteGroup() {
  if (!editable.value || props.section.code !== 'electronic') return
  const existing = electronicGroups.value.length
    ? electronicGroups.value
    : electronicPayloadHasContent(draftPayload.value)
      ? [{ id: 'legacy', name: '电子报价1', ...(draftPayload.value as unknown as ElectronicPayload) }]
      : []
  if (existing.length >= 20) {
    localError.value = '每张内部报价最多保留 20 份独立电子报价。'
    return
  }
  const id = `electronic-${createRandomUuid()}`
  draftPayload.value = normalizeInternalQuotePayload('electronic', {
    quote_groups: [...existing, { id, name: `电子报价${existing.length + 1}` }],
  })
  activeElectronicGroupId.value = id
  localMessage.value = '已新增一份独立电子报价；每份明细、费用和利润单独保存，金额会合计到电子部总价。'
}

function renameActiveElectronicGroup(name: string) {
  if (!editable.value || !activeElectronicGroup.value) return
  const trimmed = name.trim()
  if (!electronicGroups.value.length) {
    draftPayload.value = normalizeInternalQuotePayload('electronic', {
      quote_groups: [{ ...activeElectronicGroup.value, name: trimmed || activeElectronicGroup.value.name }],
    })
    return
  }
  draftPayload.value = normalizeInternalQuotePayload('electronic', {
    quote_groups: electronicGroups.value.map((group) => group.id === activeElectronicGroup.value!.id
      ? { ...group, name: trimmed || group.name }
      : group),
  })
}

function renameActiveElectronicGroupFromEvent(event: Event) {
  renameActiveElectronicGroup((event.target as HTMLInputElement | null)?.value ?? '')
}

function removeActiveElectronicGroup() {
  const group = activeElectronicGroup.value
  if (!editable.value || props.section.code !== 'electronic' || !group) return
  if (!window.confirm(`删除“${group.name}”会移除该份电子明细、费用和利润，确定继续吗？`)) return
  if (!electronicGroups.value.length) {
    draftPayload.value = normalizeInternalQuotePayload('electronic', {})
    return
  }
  const remaining = electronicGroups.value.filter((entry) => entry.id !== group.id)
  draftPayload.value = normalizeInternalQuotePayload('electronic', { quote_groups: remaining })
  activeElectronicGroupId.value = remaining[0]?.id ?? 'legacy'
  localMessage.value = `已删除“${group.name}”；电子部总价已按剩余报价更新。`
}

function handleBlockProgress(blocks: InternalQuoteFormBlock[]) {
  if (props.section.code === 'electronic') {
    emit('block-progress', props.section.code, getInternalQuoteFormBlocks('electronic', draftPayload.value))
    return
  }
  emit('block-progress', props.section.code, blocks)
}
const uploadInput = ref<HTMLInputElement>()
const templateMenuOpen = ref(false)
const unsavedPromptOpen = ref(false)
const removePromptOpen = ref(false)
const navigationSaving = ref(false)
let livePreviewTimer: ReturnType<typeof setTimeout> | undefined
type UnsavedNavigationChoice = 'save' | 'discard' | 'cancel'
let resolveUnsavedPrompt: ((choice: UnsavedNavigationChoice) => void) | undefined
let pendingUnsavedPrompt: Promise<UnsavedNavigationChoice> | undefined

const statusMeta: Record<InternalQuoteSectionStatus, { label: string; tone: string }> = {
  draft: { label: '草稿', tone: 'slate' }, pending_review: { label: '待业务审核人审核', tone: 'amber' },
  approved: { label: '审核通过', tone: 'green' }, rejected: { label: '已退回', tone: 'red' },
  na_pending: { label: '不适用待审', tone: 'amber' }, not_applicable: { label: '不适用', tone: 'slate' },
}
const activeStatusMeta = computed(() => {
  if (!props.wholeQuoteReview) return statusMeta[props.section.status]
  return {
    draft: { label: props.section.filledAt ? '部门内容已保存' : '等待填写', tone: props.section.filledAt ? 'green' : 'slate' },
    pending_review: { label: '已锁定，待整单审核', tone: 'amber' },
    approved: { label: '整单审核通过', tone: 'green' },
    rejected: { label: '整单已退回，可修改', tone: 'red' },
    na_pending: { label: '已锁定，待整单审核', tone: 'amber' },
    not_applicable: { label: '本单不适用', tone: 'slate' },
  }[props.section.status]
})

const mutable = computed(() => ['draft', 'rejected'].includes(props.section.status))
const editable = computed(() => props.canEdit && mutable.value && !quoteStore.submitting)
const isOwnPendingSubmission = computed(() => (
  ['pending_review', 'na_pending'].includes(props.section.status)
  && Boolean(props.section.submittedById)
  && props.section.submittedById === authStore.currentUser?.id
))
const canSelfReviewOwnSubmission = computed(() => (
  props.quote.createdById === authStore.currentUser?.id
  && authStore.can('internal_quote:self_review', props.quote.factoryId, 'sales-business')
))
const reviewable = computed(() => (
  !props.wholeQuoteReview
  && props.canReview
  && ['pending_review', 'na_pending'].includes(props.section.status)
  && (!isOwnPendingSubmission.value || canSelfReviewOwnSubmission.value)
  && !quoteStore.submitting
))
const canWithdraw = computed(() => !props.wholeQuoteReview && props.canEdit && isOwnPendingSubmission.value && !quoteStore.submitting)
const canReopen = computed(() => !props.wholeQuoteReview && props.canEdit && ['approved', 'not_applicable'].includes(props.section.status) && !quoteStore.submitting)
const lockMessage = computed(() => {
  if (props.wholeQuoteReview) {
    if (mutable.value) return '当前账号没有本部门编辑权限，内容保持只读。'
    if (props.section.status === 'pending_review') return '整份报价已经提交并统一锁定，等待指定整单审核人处理。'
    if (props.section.status === 'approved') return '整单审核已经通过，本部门内容保持锁定。'
    return `当前部门内容为“${activeStatusMeta.value.label}”，暂不可编辑。`
  }
  return canWithdraw.value
    ? '本分段已提交并等待他人审核；审核前可点击“返回修改”恢复草稿。'
    : mutable.value
      ? '当前账号没有本分段编辑权限，页面保持只读。'
      : `当前分段为“${activeStatusMeta.value.label}”，需退回或合法重开后才能编辑。`
})
const isDirty = computed(() => JSON.stringify(draftPayload.value) !== baselinePayload.value)
function detailAmount(value: number) {
  const factor = 1000
  const rounded = Math.sign(value) * Math.round((Math.abs(value) + Number.EPSILON) * factor) / factor
  return rounded.toFixed(3)
}
type ImportOption = {
  type: ApiInternalQuoteImportPreview['import_type']
  label: string
  fileName: string
}
const importOptions = computed<ImportOption[]>(() => ({
  engineering: [
    { type: 'hardware', label: '五金报价单', fileName: '五金1.xlsx' },
    { type: 'mold', label: '模具报价单 / 合同', fileName: '展兴模具--工模报价表.xlsx' },
  ],
  electronic: [{ type: 'electronic', label: '电子报价单', fileName: '电子报价单.xlsx' }],
  molding: [{ type: 'molding', label: '啤机报价单', fileName: '啤机部报价导入模板-2026.07.xlsx' }],
  painting: [{ type: 'painting', label: '喷油报价单', fileName: '喷油报价单.xlsx' }],
  slush: [{ type: 'slush', label: '搪胶报价单', fileName: '搪胶部报价导入模板-2026.07.xlsx' }],
  sewing: [{ type: 'sewing', label: '车缝报价单', fileName: '车缝报价单.xlsx' }],
  hair: [{ type: 'hair', label: '车发部报价单', fileName: '车发部报价单.xls' }],
  assembly: [{ type: 'assembly', label: '生产排拉工序表', fileName: '装工.xlsx' }],
} as Partial<Record<InternalQuoteSectionCode, ImportOption[]>>)[props.section.code] ?? [])

function importOption(type: ApiInternalQuoteImportPreview['import_type']) {
  return importOptions.value.find((option) => option.type === type)
}

const reasonActionAllowed = computed(() => {
  if (props.wholeQuoteReview) return false
  if (reasonAction.value === 'reject') return reviewable.value
  if (reasonAction.value === 'na') return editable.value
  if (reasonAction.value === 'reopen') return canReopen.value
  return false
})

function cancelLivePreviewTimer() {
  if (livePreviewTimer) clearTimeout(livePreviewTimer)
  livePreviewTimer = undefined
}

function scheduleLivePreview() {
  cancelLivePreviewTimer()
  if (!editable.value || !isDirty.value) {
    quoteStore.clearLiveCostPreview(props.quote.id, props.section.code)
    return
  }
  livePreviewTimer = setTimeout(() => {
    void quoteStore.previewSectionCost(
      props.quote.id,
      props.section.code,
      draftRevision.value,
      cloneInternalQuotePayload(props.section.code, draftPayload.value),
    )
  }, 450)
}

function normalizedDraft(payload: Record<string, unknown>) {
  return normalizeInternalQuoteDraft(props.section.code, payload, props.quote.referenceSnapshot)
}

let draftContext = ''
watch([
  () => props.quote.id, () => props.section.code, () => props.section.revision,
  () => props.section.updatedAt, () => props.section.payload, () => props.quote.referenceSnapshot,
], () => {
  const context = `${props.quote.id}:${props.section.code}`
  const contextChanged = context !== draftContext
  const incoming = normalizedDraft(props.section.payload)
  const incomingText = JSON.stringify(incoming)
  const currentText = JSON.stringify(draftPayload.value)
  // A quote refresh may replace section objects without changing their data.
  // Never overwrite a local edit (or recreate its focused input) in that case.
  if (!contextChanged && isDirty.value && incomingText !== currentText) {
    if (incomingText !== baselinePayload.value) localError.value = '服务器内容已更新，本页未保存输入已保留；请核对后再保存。'
    return
  }
  if (draftContext) {
    const separator = draftContext.lastIndexOf(':')
    const previousQuoteId = draftContext.slice(0, separator)
    const previousSectionCode = draftContext.slice(separator + 1) as InternalQuoteSectionCode
    quoteStore.clearLiveCostPreview(previousQuoteId, previousSectionCode)
  }
  draftContext = context
  cancelLivePreviewTimer()
  quoteStore.clearLiveCostPreview(props.quote.id, props.section.code)
  if (contextChanged || incomingText !== currentText) draftPayload.value = incoming
  baselinePayload.value = incomingText
  draftRevision.value = props.section.revision
  importPreview.value = undefined
  deleteAttachmentTarget.value = undefined
  reasonAction.value = undefined
  actionReason.value = ''
  localMessage.value = ''
  localError.value = ''
  removePromptOpen.value = false
  templateMenuOpen.value = false
}, { immediate: true })
watch(draftPayload, () => {
  scheduleLivePreview()
  if (props.section.code === 'electronic') {
    emit('block-progress', props.section.code, getInternalQuoteFormBlocks('electronic', draftPayload.value))
  }
}, { deep: true })
watch([editable, isDirty], scheduleLivePreview)
onBeforeUnmount(() => {
  cancelLivePreviewTimer()
  quoteStore.clearLiveCostPreview(props.quote.id, props.section.code)
  window.removeEventListener('beforeunload', handleBeforeUnload)
  resolveUnsavedPrompt?.('cancel')
  resolveUnsavedPrompt = undefined
  pendingUnsavedPrompt = undefined
})

function resetFeedback() { localMessage.value = ''; localError.value = '' }
function errorText(error: unknown) { return error instanceof Error ? error.message : '操作失败。' }

function acceptSavedPayload(payload: Record<string, unknown>, submitted: Record<string, unknown>, revision: number) {
  const saved = normalizedDraft(payload)
  const submittedText = JSON.stringify(normalizedDraft(submitted))
  const currentText = JSON.stringify(draftPayload.value)
  const savedText = JSON.stringify(saved)
  // Acknowledge only the submitted snapshot. Edits made while awaiting the
  // response must remain dirty, including when the server returns no new revision.
  if (currentText === submittedText && currentText !== savedText) draftPayload.value = saved
  baselinePayload.value = savedText
  draftRevision.value = revision
  cancelLivePreviewTimer()
  scheduleLivePreview()
}

async function saveDraft(showMessage = true, reason = '', refreshQuote = true) {
  resetFeedback()
  try {
    const requestedRevision = draftRevision.value
    const quoteId = props.quote.id
    const sectionCode = props.section.code
    const submitted = cloneInternalQuotePayload(sectionCode, draftPayload.value)
    const result = await quoteStore.saveSection(quoteId, sectionCode, requestedRevision, submitted, reason, refreshQuote) as ApiInternalQuoteSection
    if (props.quote.id !== quoteId || props.section.code !== sectionCode) return result
    acceptSavedPayload(result.payload, submitted, result.revision)
    if (showMessage) localMessage.value = result.revision === requestedRevision
      ? `${props.section.label}内容没有变化，沿用 revision ${result.revision}。`
      : `${props.section.label}草稿已保存，服务端已生成 revision ${result.revision} 并重新计算。`
    return result
  } catch (error) {
    localError.value = errorText(error)
    return undefined
  }
}

async function saveSalesMarkup(markupTiers: SalesMarkupTier[], selectedMoq: number, activeMarkup: number, miscRatio: number, componentMarkups?: Array<{ id: string; markup: number }>) {
  if (props.section.code !== 'sales') throw new Error('当前不是业务部分段，无法合并保存码数与杂项。')
  if (!editable.value) throw new Error('业务部分段当前不可编辑，请先重开后再保存码数与杂项。')
  const shipping = draftPayload.value.shipping && typeof draftPayload.value.shipping === 'object' && !Array.isArray(draftPayload.value.shipping)
    ? draftPayload.value.shipping as Record<string, unknown>
    : {}
  const componentMarkupById = new Map((componentMarkups ?? []).map((row) => [row.id, row.markup]))
  const packagingMarkup = componentMarkupById.get(salesPackagingPricingGroupId) ?? activeMarkup
  const sourcePricingComponents = Array.isArray(draftPayload.value.pricing_components) ? draftPayload.value.pricing_components : []
  const nextPricingComponents = sourcePricingComponents.flatMap((value, index) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return []
    const row = value as Record<string, unknown>
    const id = String(row.id ?? '').trim()
    const name = String(row.name ?? '').trim()
    const componentMarkup = componentMarkupById.get(id)
    if (!id || !name) return []
    return [{ id, name, ...(componentMarkup != null && (index === 0 || Math.abs(componentMarkup - activeMarkup) > .000001) ? { markup_x: Number(componentMarkup.toFixed(2)) } : {}) }]
  })
  draftPayload.value = normalizeInternalQuotePayload('sales', {
    ...draftPayload.value,
    ...(componentMarkups?.length ? { pricing_mode: 'component', pricing_components: nextPricingComponents } : {}),
    shipping: {
      ...shipping,
      markup_x: Number(activeMarkup.toFixed(2)),
      ...(componentMarkups?.length ? { packaging_markup_x: Number(packagingMarkup.toFixed(2)) } : {}),
      markup_tiers: markupTiers.map((tier) => ({ moq: tier.moq, markup_x: Number(tier.markup_x.toFixed(2)), include_in_output: tier.include_in_output !== false })),
      selected_markup_moq: selectedMoq,
      misc_ratio: Number(miscRatio.toFixed(4)),
      divisor: salesSettlementDivisorForMiscRatio(miscRatio),
    },
  })
  const result = await saveDraft(false, componentMarkups?.length ? '在协作侧栏保存 JustPlay 配件与业务部包装倍率及杂项系数' : '在协作侧栏保存分段 MOQ 码数与杂项系数')
  if (!result) throw new Error(localError.value || '保存码数与杂项失败。')
  localMessage.value = `业务部当前草稿、分段 MOQ 码数与杂项系数已保存，服务端已生成 revision ${result.revision} 并重新计算。`
  return result
}

function hasUnsavedChanges() {
  return isDirty.value
}

function canSaveWholeQuoteDraft() {
  return editable.value
}

function getWholeQuoteDraft() {
  if (!editable.value) throw new Error(`${props.section.label}当前不可编辑，无法统一保存。`)
  return {
    sectionCode: props.section.code,
    revision: draftRevision.value,
    payload: cloneInternalQuotePayload(props.section.code, draftPayload.value),
    baselinePayload: JSON.parse(baselinePayload.value) as Record<string, unknown>,
  }
}

async function saveWholeQuoteDraft(refreshQuote = true) {
  if (!editable.value) throw new Error(`${props.section.label}当前不可编辑，无法统一保存。`)
  const result = await saveDraft(false, '在连续报价页统一保存当前产品', refreshQuote)
  if (!result) throw new Error(localError.value || `${props.section.label}保存失败。`)
  return result
}

defineExpose({ saveSalesMarkup, saveWholeQuoteDraft, hasUnsavedChanges, canSaveWholeQuoteDraft, getWholeQuoteDraft, acceptSavedPayload })

function askHowToHandleUnsavedChanges() {
  if (pendingUnsavedPrompt) return pendingUnsavedPrompt
  unsavedPromptOpen.value = true
  pendingUnsavedPrompt = new Promise<UnsavedNavigationChoice>((resolve) => {
    resolveUnsavedPrompt = resolve
  })
  return pendingUnsavedPrompt
}

function answerUnsavedPrompt(choice: UnsavedNavigationChoice) {
  if (navigationSaving.value) return
  const resolve = resolveUnsavedPrompt
  resolveUnsavedPrompt = undefined
  pendingUnsavedPrompt = undefined
  unsavedPromptOpen.value = false
  resolve?.(choice)
}

async function confirmUnsavedNavigation() {
  if (!isDirty.value) return true
  const choice = await askHowToHandleUnsavedChanges()
  if (choice === 'cancel') return false
  if (choice === 'discard') return true

  navigationSaving.value = true
  const saved = await saveDraft(false)
  navigationSaving.value = false
  if (!saved) {
    localError.value = localError.value || '保存草稿失败，已留在当前部门，请处理后重试。'
    return false
  }
  return true
}

function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (!isDirty.value) return
  event.preventDefault()
  event.returnValue = ''
}

onBeforeRouteUpdate(confirmUnsavedNavigation)
onBeforeRouteLeave(confirmUnsavedNavigation)
onMounted(() => window.addEventListener('beforeunload', handleBeforeUnload))

async function submitSection() {
  resetFeedback()
  try {
    let revision = draftRevision.value
    if (isDirty.value) {
      const saved = await saveDraft(false)
      if (!saved) return
      revision = saved.revision
    }
    await quoteStore.submitSection(props.quote.id, props.section.code, revision)
    localMessage.value = `${props.section.label}已提交业务审核负责人审核。`
  } catch (error) { localError.value = errorText(error) }
}

async function approveSection() {
  resetFeedback()
  try {
    await quoteStore.reviewSection(props.quote.id, props.section.code, props.section.revision, 'approve')
    localMessage.value = props.section.status === 'na_pending' ? '不适用申请已批准。' : `${props.section.label}已审核通过。`
  } catch (error) { localError.value = errorText(error) }
}

function openReason(action: 'reject' | 'na' | 'reopen') { reasonAction.value = action; actionReason.value = ''; resetFeedback() }

async function confirmReasonAction() {
  if (!reasonAction.value || !actionReason.value.trim()) return
  if (!reasonActionAllowed.value) {
    reasonAction.value = undefined
    actionReason.value = ''
    localError.value = '当前账号没有执行该操作的权限。'
    return
  }
  const reason = actionReason.value.trim()
  resetFeedback()
  try {
    if (reasonAction.value === 'reject') await quoteStore.reviewSection(props.quote.id, props.section.code, props.section.revision, 'reject', reason)
    else if (reasonAction.value === 'na') await quoteStore.requestSectionNa(props.quote.id, props.section.code, props.section.revision, reason)
    else await quoteStore.reopenSection(props.quote.id, props.section.code, props.section.revision, reason)
    localMessage.value = reasonAction.value === 'reject' ? '审核已退回并留存原因。' : reasonAction.value === 'na' ? '不适用申请已提交业务审核负责人审核。' : '分段已合法重开。'
    reasonAction.value = undefined
    actionReason.value = ''
  } catch (error) { localError.value = errorText(error) }
}

function isImportWorkbook(file: File) {
  return /\.(xlsx|xlsm)$/i.test(file.name) || (props.section.code === 'hair' && /\.xls$/i.test(file.name))
}

async function withdrawSection() {
  resetFeedback()
  try {
    await quoteStore.withdrawSection(props.quote.id, props.section.code, props.section.revision)
    localMessage.value = `${props.section.label}已返回草稿，可以继续修改。`
  } catch (error) { localError.value = errorText(error) }
}

async function detectImportPreview(file: File) {
  if (!editable.value || !isImportWorkbook(file)) return undefined
  for (const option of importOptions.value) {
    try {
      return await quoteStore.previewImport(props.quote.id, option.type, file)
    } catch (error) {
      // Each server parser is authoritative for its own template. A parse miss is
      // expected while auto-detecting. Permission, size, conflict, timeout and
      // server errors must remain visible instead of silently becoming attachments.
      const status = error && typeof error === 'object' && 'status' in error
        ? Number((error as { status?: unknown }).status)
        : 0
      if (status !== 400 && status !== 404) throw error
    }
  }
  return undefined
}

async function handleUploadFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !editable.value) return
  resetFeedback()
  try {
    if (isImportWorkbook(file) && importOptions.value.length && isDirty.value) {
      localError.value = '当前有未保存修改，请先保存草稿，再重新选择报价单导入。'
      return
    }
    const detected = await detectImportPreview(file)
    if (detected) {
      importPreview.value = detected
      localMessage.value = `${file.name} 已自动识别为${importOption(detected.import_type)?.label ?? '报价单'}；请核对预览后确认写入。`
      return
    }
    await quoteStore.uploadAttachment(props.quote.id, props.section.code, file)
    localMessage.value = isImportWorkbook(file) && importOptions.value.length
      ? `${file.name} 未识别为本部门结构化报价单，已作为普通附件保存。`
      : `附件 ${file.name} 已校验并留存。`
  } catch (error) { localError.value = errorText(error) }
}

async function downloadImportTemplate(option?: ImportOption) {
  const target = option ?? importOptions.value[0]
  if (!target || quoteStore.fileBusy) return
  if (!option && importOptions.value.length > 1) {
    templateMenuOpen.value = !templateMenuOpen.value
    return
  }
  templateMenuOpen.value = false
  resetFeedback()
  try {
    await quoteStore.downloadImportTemplate(props.quote.id, target.type, target.fileName)
    localMessage.value = target.type === 'hair'
      ? '车发部原版模板已下载；填写“明细”页的单价和重量，保存后从“上传附件”导入。'
      : `${target.label}映射模板已下载；请按绿色表头填写黄色区域后，从“上传附件”导入。`
  } catch (error) {
    localError.value = errorText(error)
  }
}

async function confirmImport() {
  if (isDirty.value) {
    importPreview.value = undefined
    localError.value = '预览后有未保存修改，请先保存草稿，再重新选择报价单导入。'
    return
  }
  if (!importPreview.value || !editable.value) {
    importPreview.value = undefined
    localError.value = '当前账号没有确认导入该分段的权限。'
    return
  }
  resetFeedback()
  try {
    if (!assignmentComplete.value) { localError.value = '请为每条映射明细选择应用分项，或选择不采用。'; return }
    const target = props.section.code === 'electronic' ? electronicImportTarget.value : undefined
    await quoteStore.confirmImport(
      props.quote.id,
      importPreview.value.batch_id,
      importPreview.value.target_revision,
      importPreview.value.assignment_rows?.length ? importAssignments.value : undefined,
      target,
    )
    localMessage.value = props.section.code === 'electronic' && target === 'new'
      ? '电子报价已作为独立报价导入；每份报价金额都会合计到电子部总价。'
      : '报价单已导入并按模板负责区域更新，分段已重新计算。'
    importPreview.value = undefined
  } catch (error) { localError.value = errorText(error) }
}

async function downloadAttachment(id: string, fileName: string) {
  resetFeedback()
  try { await quoteStore.downloadAttachment(props.quote.id, id, fileName) }
  catch (error) { localError.value = errorText(error) }
}

function previewAttachment(attachment: InternalQuoteAttachmentRecord) {
  resetFeedback()
  previewAttachmentTarget.value = attachment
}

function requestDeleteImportAttachment(attachment: InternalQuoteAttachmentRecord) {
  resetFeedback()
  if (!editable.value) {
    localError.value = '本分段当前不可编辑，无法删除附件。'
    return
  }
  if (isDirty.value) {
    localError.value = '当前有未保存修改，请先保存草稿或放弃修改，再删除附件。'
    return
  }
  deleteAttachmentTarget.value = attachment
}

async function confirmDeleteImportAttachment() {
  const attachment = deleteAttachmentTarget.value
  if (!attachment || !editable.value || quoteStore.submitting) return
  if (isDirty.value) {
    localError.value = '当前有未保存修改，请先保存草稿，再删除附件。'
    deleteAttachmentTarget.value = undefined
    return
  }
  resetFeedback()
  try {
    if (attachment.isImportSource) {
      await quoteStore.deleteImportAttachment(props.quote.id, attachment.id, props.section.revision)
    } else {
      await quoteStore.deleteSupportingAttachment(props.quote.id, attachment.id, props.section.revision)
    }
    deleteAttachmentTarget.value = undefined
    localMessage.value = attachment.isImportSource
      ? `已删除 ${attachment.fileName}，并清除该文件仍在使用的导入数据。`
      : `已删除附件 ${attachment.fileName}。`
  } catch (error) { localError.value = errorText(error) }
}

function openRemovePrompt() {
  if (!props.canRemove || quoteStore.submitting) return
  removePromptOpen.value = true
}

function confirmRemoveParticipation() {
  if (!props.canRemove || quoteStore.submitting) return
  removePromptOpen.value = false
  emit('remove', props.section.code)
}
</script>

<template>
  <section class="quote-section-editor" :class="{ 'baseline-different': differsFromBaseline }">
    <header class="quote-editor-head">
      <div><div class="quote-editor-title-row"><h2>{{ section.label }}核价明细</h2><span v-if="differsFromBaseline" class="baseline-difference"><AlertCircle />与基准款不同</span><span class="quote-editor-status" :class="`tone-${activeStatusMeta.tone}`"><i />{{ activeStatusMeta.label }}</span><span class="quote-revision">revision {{ section.revision }}</span><span v-if="isDirty" class="dirty">有未保存修改</span></div></div>
      <div class="quote-editor-tools">
        <button v-if="section.code !== 'sales'" class="primary-upload" type="button" title="Excel 自动识别导入内容；其他文件按普通附件保存" :disabled="!editable || quoteStore.fileBusy || quoteStore.submitting" @click="uploadInput?.click()"><Paperclip />上传附件</button>
        <div v-if="importOptions.length" class="template-download-control">
          <button
            class="template-download"
            type="button"
            :aria-expanded="importOptions.length > 1 ? templateMenuOpen : undefined"
            :aria-haspopup="importOptions.length > 1 ? 'menu' : undefined"
            title="下载与当前部门导入映射一致的 Excel 模板"
            :disabled="quoteStore.fileBusy || quoteStore.submitting"
            @click="downloadImportTemplate()"
          ><Download />下载模板</button>
          <div v-if="templateMenuOpen && importOptions.length > 1" class="template-download-menu" role="menu">
            <button v-for="templateOption in importOptions" :key="templateOption.type" type="button" role="menuitem" @click="downloadImportTemplate(templateOption)"><FileSpreadsheet />{{ templateOption.label }}</button>
          </div>
        </div>
        <button v-if="supportsQuickQuote" class="quick-entry" :class="{ active: isQuickQuoteMode }" type="button" :title="isQuickQuoteMode ? '切回明细报价，快捷数据保留但不重复计价' : '急单暂缺明细时先填写快捷权威金额'" :disabled="!editable || quoteStore.submitting" @click="toggleQuickQuoteMode"><Zap />{{ quickQuoteButtonLabel }}</button>
        <input v-if="section.code !== 'sales'" ref="uploadInput" class="sr-only" type="file" accept=".xlsx,.xlsm,.xls,.doc,.docx,.pdf,.jpg,.jpeg" @change="handleUploadFile">
      </div>
    </header>
    <aside v-if="differsFromBaseline && differenceDetails.length" class="baseline-difference-details" aria-label="与基准款的差异明细">
      <strong>与基准款不同的明细</strong>
      <span>鼠标移开后自动收起</span>
      <ul><li v-for="detail in differenceDetails.slice(0, 12)" :key="detail">{{ detail }}</li></ul>
      <em v-if="differenceDetails.length > 12">另有 {{ differenceDetails.length - 12 }} 项差异</em>
    </aside>

    <div v-if="!editable" class="quote-lock-banner"><LockKeyhole />{{ lockMessage }}</div>
    <div class="quote-dependency-strip"><span><Info />依赖数据</span><b v-for="dependency in section.dependencies" :key="dependency">{{ dependency }}</b><em>计算 {{ section.calculationStatus }} · 依赖 {{ section.dependencyStatus }}</em></div>
    <div v-if="section.warnings.length" class="quote-warning-list"><p v-for="warning in section.warnings" :key="warning"><AlertCircle />{{ warning }}</p></div>

    <section v-if="importPreview && editable" class="quote-import-preview">
      <header><div><FileSpreadsheet /><span><strong>{{ importOption(importPreview.import_type)?.label }} · {{ importPreview.source_file_name }}</strong><small>{{ importPreview.sheet_name }} · 表头第 {{ importPreview.header_row }} 行 · 识别 {{ importPreview.row_count }} 行 · 预览不会修改正式数据</small></span></div><button type="button" aria-label="关闭导入预览" @click="importPreview = undefined"><XCircle /></button></header>
      <div class="preview-metrics"><span>{{ section.code === 'electronic' ? electronicImportExistingLabel : `当前 ${Number(importPreview.diff_summary.existing_rows ?? 0)} 行` }}</span><span>本次识别 {{ Number(importPreview.diff_summary.imported_rows ?? 0) }} 行</span><span>{{ section.code === 'electronic' ? `导入后该报价 ${electronicImportResultRows} 行` : `导入后 ${Number(importPreview.diff_summary.replace_result_rows ?? 0)} 行` }}</span></div>
      <label v-if="section.code === 'electronic'" class="electronic-import-target"><span>导入方式</span><select v-model="electronicImportTarget" :disabled="quoteStore.submitting"><option value="new">新增独立电子报价（全部金额会合计）</option><option v-for="target in electronicImportTargets" :key="target.id" :value="target.id">替换“{{ target.name }}”</option></select><small>新增会保留现有各份报价；替换只更新所选报价。若同一源文件已导入，请选择该报价替换。</small></label>
      <div v-if="importPreview.warnings.length" class="preview-warnings"><p v-for="warning in importPreview.warnings" :key="warning"><AlertCircle />{{ warning }}</p></div>
      <InternalQuoteImportAssignment v-if="importPreview.assignment_rows?.length" :key="importPreview.batch_id" v-model="importAssignments" :rows="importPreview.assignment_rows" :components="importPreview.assignment_components ?? []" :disabled="quoteStore.submitting" />
      <footer><strong class="replace-only-note">{{ section.code === 'electronic' ? '确认后仅更新目标报价；各份电子报价金额均计入电子部总价' : '确认后按模板负责的数据区域更新；重复导入不会累计金额' }}</strong><span /><button type="button" class="secondary" @click="importPreview = undefined">取消</button><button type="button" class="primary" :disabled="quoteStore.submitting || !editable || !assignmentComplete" @click="confirmImport">确认导入</button></footer>
    </section>

    <InternalQuoteMappedAssignment v-if="pricingMode === 'component' && ['engineering', 'painting'].includes(section.code)" v-model="draftPayload" :code="section.code" :components="pricingComponents" :disabled="!editable" />
    <section v-if="section.code === 'electronic'" class="electronic-quote-groups" aria-label="电子报价管理">
      <header><div><strong>独立电子报价</strong><span>每份报价分别保存明细、费用和利润；下方电子部合计包含全部报价。</span></div><button type="button" class="secondary" :disabled="!editable || quoteStore.submitting || electronicGroupOptions.length >= 20" @click="addElectronicQuoteGroup"><FileSpreadsheet />新增电子报价</button></header>
      <div v-if="electronicGroupOptions.length" class="electronic-quote-group-controls"><label><span>当前报价</span><select v-model="activeElectronicGroupId"><option v-for="group in electronicGroupOptions" :key="group.id" :value="group.id">{{ group.name }}</option></select></label><label v-if="activeElectronicGroup"><span>报价名称</span><input :value="activeElectronicGroup.name" :disabled="!editable" maxlength="80" @change="renameActiveElectronicGroupFromEvent"></label><button class="remove-electronic-group" type="button" :disabled="!editable || quoteStore.submitting || !activeElectronicGroup" @click="removeActiveElectronicGroup"><Trash2 />删除当前报价</button></div>
      <div class="electronic-quote-total"><strong>电子部全部报价预览</strong><span>RMB {{ detailAmount(electronicSectionSummary.quoteRmb) }}</span><span>HKD {{ detailAmount(electronicSectionSummary.quoteHkd) }}</span><em>{{ electronicGroupOptions.length }} 份报价金额合计；正式金额以保存后的服务端计算为准。</em></div>
    </section>
    <div v-if="section.code === 'electronic' && !showElectronicForm" class="electronic-empty-state"><FileSpreadsheet /><strong>暂无电子报价</strong><span>可新增空白电子报价，或上传报价单后选择“新增独立电子报价”。</span></div>
    <InternalQuoteSectionForm v-if="showElectronicForm" v-model="formPayload" :code="section.code" :quote-id="quote.id" :attachments="section.attachments" :customer="quote.customer" :rmb-hkd-rate="quote.fxRmbHkd" :reference-snapshot="quote.referenceSnapshot" :calculation="section.calculation" :pricing-mode="pricingMode" :pricing-components="pricingComponents" :active-pricing-component-id="activePricingComponentId" :main-markup="mainMarkup" :disabled="!editable" @block-progress="handleBlockProgress" @preview-attachment="previewAttachment" />

    <InternalQuoteAttachmentPreview
      :quote-id="quote.id"
      :attachment="previewAttachmentTarget"
      @close="previewAttachmentTarget = undefined"
      @download="downloadAttachment($event.id, $event.fileName)"
    />

    <section class="calculation-snapshot"><header><strong>服务端权威计算快照</strong><span>保存后由服务端重算；前端不生成正式金额</span></header><div class="snapshot-table-scroll"><table><thead><tr><th>项目</th><th>类型</th><th>金额 HKD</th></tr></thead><tbody><tr v-for="line in section.lines" :key="line.id"><td>{{ line.item }}</td><td>{{ line.specification }}</td><td class="calculated-amount-cell">{{ detailAmount(line.amountHkd) }}</td></tr><tr v-if="!section.lines.length"><td colspan="3" class="empty">保存有效明细后显示服务端计算结果</td></tr></tbody><tfoot><tr><td colspan="2">{{ section.label }}权威小计</td><td class="calculated-amount-cell">HKD {{ detailAmount(section.totalHkd) }}</td></tr></tfoot></table></div></section>

    <section class="quote-attachments"><header><strong>本部门资料 / 分段附件</strong><span>仅显示分配给当前部门的资料；导入源文件可连同其生成的报价数据一起删除</span></header><div><span v-for="attachment in section.attachments" :key="attachment.id" class="attachment-pill"><button type="button" class="attachment-download" :title="`${attachment.uploadedBy} · ${attachment.uploadedAt} · ${attachment.sha256}`" @click="downloadAttachment(attachment.id, attachment.fileName)"><Paperclip />{{ attachment.fileName }}<Download /></button><button type="button" class="attachment-preview" :title="`在右侧预览 ${attachment.fileName}`" :aria-label="`预览 ${attachment.fileName}`" @click="emit('preview-file', section.code, attachment)"><Eye />预览</button><button type="button" class="attachment-delete" :disabled="!editable || quoteStore.submitting" :title="`删除 ${attachment.fileName}${attachment.isImportSource ? ' 及其导入数据' : ''}`" :aria-label="`删除 ${attachment.fileName}${attachment.isImportSource ? ' 及其导入数据' : ''}`" @click="requestDeleteImportAttachment(attachment)"><Trash2 /></button></span><em v-if="!section.attachments.length">暂无分配给本部门的资料</em></div></section>

    <p v-if="localMessage" class="quote-local-message"><CheckCircle2 />{{ localMessage }}</p>
    <p v-if="localError" class="quote-local-error"><AlertCircle />{{ localError }}</p>

    <section v-if="reasonAction && reasonActionAllowed" class="quote-reason-panel"><div><strong>{{ reasonAction === 'reject' ? '填写退回原因' : reasonAction === 'na' ? '填写不适用原因' : '填写重开原因' }}</strong><span>原因将进入业务操作时间线和不可变审核记录。</span></div><textarea v-model="actionReason" rows="2" placeholder="必须填写原因" /><button type="button" class="secondary" @click="reasonAction = undefined">取消</button><button type="button" class="primary" :disabled="!actionReason.trim() || quoteStore.submitting || !reasonActionAllowed" @click="confirmReasonAction">确认</button></section>

    <footer v-if="!wholeQuoteReview" class="quote-editor-actions"><div><span>最后更新 {{ section.updatedAt }}</span><b>所有写入均携带 revision；409 时保留当前表单，不覆盖他人修改</b></div><div>
      <button v-if="editable && !wholeQuoteReview" type="button" class="secondary" @click="openReason('na')">申请不适用</button>
      <button v-if="editable" type="button" class="secondary" :disabled="quoteStore.submitting" @click="saveDraft()"><Save />保存草稿</button>
      <button v-if="editable && !wholeQuoteReview" type="button" class="primary" :disabled="quoteStore.submitting" @click="submitSection"><Send />{{ isDirty ? '保存并提交审核' : '提交分段审核' }}</button>
      <button v-if="canWithdraw" type="button" class="withdraw" :disabled="quoteStore.submitting" @click="withdrawSection"><Undo2 />返回修改</button>
      <button v-if="reviewable" type="button" class="danger" @click="openReason('reject')"><XCircle />{{ section.status === 'na_pending' ? '退回申请' : '退回' }}</button>
      <button v-if="reviewable" type="button" class="primary" @click="approveSection"><CheckCircle2 />{{ section.status === 'na_pending' ? '批准不适用' : '审核通过' }}</button>
      <button v-if="canReopen" type="button" class="secondary" @click="openReason('reopen')"><RefreshCw />合法重开</button>
      <button v-if="props.canRemove" type="button" class="remove-section" :disabled="quoteStore.submitting" @click="openRemovePrompt"><Trash2 />移除该部门报价</button>
    </div></footer>

    <Teleport to="body">
      <div v-if="unsavedPromptOpen" class="unsaved-draft-backdrop" @click.self="answerUnsavedPrompt('cancel')">
        <section class="unsaved-draft-dialog" role="dialog" aria-modal="true" aria-labelledby="unsaved-draft-title" aria-describedby="unsaved-draft-description">
          <header><span><Save aria-hidden="true" /></span><div><h3 id="unsaved-draft-title">{{ section.label }}有未保存修改</h3><p id="unsaved-draft-description">切换部门或离开当前页面前，是否先保存为草稿？</p></div></header>
          <div class="unsaved-draft-note"><Info aria-hidden="true" />内容有变化时，保存草稿会生成新的 revision 并重新计算；相同内容不会重复生成版本。不保存则放弃本次修改。</div>
          <footer>
            <button type="button" class="discard" :disabled="navigationSaving" @click="answerUnsavedPrompt('discard')">不保存并切换</button>
            <button type="button" class="cancel" :disabled="navigationSaving" @click="answerUnsavedPrompt('cancel')">继续填写</button>
            <button type="button" class="save" :disabled="navigationSaving" @click="answerUnsavedPrompt('save')"><Save aria-hidden="true" />保存草稿并切换</button>
          </footer>
        </section>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="deleteAttachmentTarget" class="unsaved-draft-backdrop" role="presentation" @click.self="deleteAttachmentTarget = undefined">
        <section class="unsaved-draft-dialog remove-department-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-import-attachment-title">
          <header><span><Trash2 /></span><div><h3 id="delete-import-attachment-title">{{ deleteAttachmentTarget.isImportSource ? '删除导入附件和相关数据？' : '删除附件？' }}</h3><p>{{ deleteAttachmentTarget.fileName }}</p></div></header>
          <p class="unsaved-draft-note remove-note"><AlertCircle />{{ deleteAttachmentTarget.isImportSource ? '该文件仍在使用的导入明细及关联图片会被清除，并重新计算；手工明细和其他文件的明细保留。此操作无法直接恢复。' : '仅删除该附件，报价明细保留。仍被明细引用的图片需先移除引用并保存。此操作无法直接恢复。' }}</p>
          <footer><button type="button" class="cancel" :disabled="quoteStore.submitting" @click="deleteAttachmentTarget = undefined">取消</button><button type="button" class="remove-confirm" :disabled="quoteStore.submitting" @click="confirmDeleteImportAttachment"><Trash2 />确认删除</button></footer>
        </section>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="removePromptOpen" class="unsaved-draft-backdrop" @click.self="removePromptOpen = false">
        <section class="unsaved-draft-dialog remove-department-dialog" role="dialog" aria-modal="true" aria-labelledby="remove-department-title" aria-describedby="remove-department-description">
          <header><span><Trash2 aria-hidden="true" /></span><div><h3 id="remove-department-title">移除{{ section.label }}报价？</h3><p id="remove-department-description">移除后，{{ section.label }}将退出当前报价的责任进度、成本汇总和最终放行。</p></div></header>
          <div class="unsaved-draft-note remove-note"><AlertCircle aria-hidden="true" />当前分段数据和未保存修改将不再生效；历史 revision 和审计记录仍会保留。以后可再次添加该部门。</div>
          <footer>
            <button type="button" class="cancel" :disabled="quoteStore.submitting" @click="removePromptOpen = false">取消</button>
            <button type="button" class="remove-confirm" :disabled="quoteStore.submitting" @click="confirmRemoveParticipation"><Trash2 aria-hidden="true" />确认移除</button>
          </footer>
        </section>
      </div>
    </Teleport>
  </section>
</template>

<style scoped>
.quote-section-editor{position:relative;min-width:0;overflow:clip;border:1px solid #dbe5ea;border-radius:13px;background:#fff;box-shadow:0 12px 28px rgb(15 23 42/.05)}.quote-editor-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:16px;border-bottom:1px solid #e2e8f0}.quote-editor-title-row{display:flex;flex-wrap:wrap;align-items:center;gap:7px}.quote-editor-title-row h2{margin:0;color:#0f172a;font-size:17px;font-weight:900}.quote-editor-head p{margin:6px 0 0;color:#64748b;font-size:12px;line-height:1.55}.quote-editor-status,.quote-revision,.dirty{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:4px 7px;font-size:11px;font-weight:900}.quote-editor-status{background:color-mix(in srgb,var(--tone) 10%,white);color:var(--tone)}.quote-editor-status i{width:5px;height:5px;border-radius:99px;background:currentColor}.quote-revision{background:#f1f5f9;color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.dirty{background:#fff7ed;color:#c2410c}.tone-slate{--tone:#64748b}.tone-amber{--tone:#d97706}.tone-green{--tone:#059669}.tone-red{--tone:#dc2626}.quote-editor-tools{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px}.quote-editor-tools button{display:inline-flex;height:34px;align-items:center;gap:5px;border:1px solid #dbe5ea;border-radius:8px;background:#fff;padding:0 10px;color:#475569;font-size:12px;font-weight:800}.quote-editor-tools button.primary-upload{border-color:#0f766e;background:#0f766e;color:#fff;box-shadow:0 5px 14px rgb(15 118 110/.2)}.quote-editor-tools button.primary-upload:hover:not(:disabled){border-color:#115e59;background:#115e59;transform:translateY(-1px)}.quote-editor-tools button.quick-entry{border-color:#f59e0b;background:#fffbeb;color:#b45309}.quote-editor-tools button.quick-entry.active{border-color:#0d9488;background:#ccfbf1;color:#0f766e}.quote-editor-tools button.quick-entry:hover:not(:disabled){transform:translateY(-1px)}.quote-editor-tools button:disabled{cursor:not-allowed;opacity:.4}.quote-editor-tools svg{width:14px;height:14px}.quote-lock-banner,.quote-dependency-strip{display:flex;align-items:center;gap:7px;border-bottom:1px solid #e2e8f0;padding:10px 13px;font-size:11px}.quote-lock-banner{background:#fffbeb;color:#92400e}.quote-lock-banner svg{width:14px}.quote-dependency-strip{flex-wrap:wrap;background:#f8fafc;color:#64748b}.quote-dependency-strip>span{display:inline-flex;align-items:center;gap:5px;color:#0f766e;font-weight:900}.quote-dependency-strip svg{width:13px}.quote-dependency-strip b{border:1px solid #dbe5ea;border-radius:999px;background:#fff;padding:3px 6px;color:#475569;font-size:11px}.quote-dependency-strip em{margin-left:auto;color:#94a3b8;font-size:11px;font-style:normal}.quote-warning-list{display:grid;gap:5px;padding:10px 13px;background:#fef2f2}.quote-warning-list p,.preview-warnings p{display:flex;align-items:flex-start;gap:5px;margin:0;color:#b91c1c;font-size:11px}.quote-warning-list svg,.preview-warnings svg{width:13px;flex:0 0 auto}
.quote-section-editor.baseline-different{border-color:#fdba74;box-shadow:0 12px 28px rgb(194 65 12/.1)}.baseline-difference{display:inline-flex;align-items:center;gap:4px;border-radius:999px;background:#ffedd5;padding:4px 7px;color:#c2410c;font-size:10px;font-weight:950}.baseline-difference svg{width:12px;height:12px}.baseline-difference-details{position:absolute;z-index:18;top:52px;left:16px;display:grid;width:min(440px,calc(100% - 32px));max-height:280px;overflow:auto;border:1px solid #fdba74;border-radius:10px;background:#fff7ed;padding:10px 12px;box-shadow:0 14px 32px rgb(124 45 18/.2);opacity:0;visibility:hidden;transform:translateY(-5px);transition:opacity .16s ease,transform .16s ease,visibility .16s}.quote-section-editor.baseline-different:hover>.baseline-difference-details,.quote-section-editor.baseline-different:focus-within>.baseline-difference-details{opacity:1;visibility:visible;transform:translateY(0)}.baseline-difference-details strong{color:#9a3412;font-size:11px}.baseline-difference-details>span{margin-top:2px;color:#c2410c;font-size:9px}.baseline-difference-details ul{display:grid;gap:4px;margin:8px 0 0;padding-left:18px;color:#7c2d12;font-size:10px}.baseline-difference-details em{margin-top:7px;color:#c2410c;font-size:9px;font-style:normal;font-weight:800}
.template-download-control{position:relative}.quote-editor-tools button.template-download{border-color:#5eead4;background:#f0fdfa;color:#0f766e}.quote-editor-tools button.template-download:hover:not(:disabled){border-color:#14b8a6;background:#ccfbf1;transform:translateY(-1px)}.template-download-menu{position:absolute;z-index:12;top:calc(100% + 6px);right:0;display:grid;min-width:190px;gap:4px;border:1px solid #dbe5ea;border-radius:10px;background:#fff;padding:6px;box-shadow:0 14px 32px rgb(15 23 42/.16)}.quote-editor-tools .template-download-menu button{width:100%;justify-content:flex-start;border-color:transparent;background:#fff;white-space:nowrap}.quote-editor-tools .template-download-menu button:hover{border-color:#99f6e4;background:#f0fdfa;color:#0f766e}
.quote-import-preview{margin:12px;border:1px solid #bfdbfe;border-radius:10px;background:#eff6ff}.quote-import-preview>header{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 12px}.quote-import-preview>header>div{display:flex;gap:8px}.quote-import-preview>header svg{width:18px;color:#2563eb}.quote-import-preview>header span{display:grid}.quote-import-preview>header strong{color:#1e3a8a;font-size:12px}.quote-import-preview>header small{margin-top:2px;color:#64748b;font-size:11px}.quote-import-preview>header button{border:0;background:transparent;color:#64748b}.preview-metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;border-top:1px solid #dbeafe;padding:10px 12px;background:#fff}.preview-metrics span{border-radius:7px;background:#eff6ff;padding:8px;color:#1d4ed8;font-size:11px;text-align:center}.preview-warnings{display:grid;gap:5px;border-top:1px solid #fed7aa;background:#fff7ed;padding:9px 12px}.quote-import-preview>footer{display:flex;align-items:center;gap:10px;border-top:1px solid #dbeafe;padding:9px 12px}.quote-import-preview>footer span{flex:1}.quote-import-preview>footer button{height:31px;border-radius:7px;padding:0 10px;font-size:12px;font-weight:900}.quote-import-preview .replace-only-note{color:#1d4ed8;font-size:12px}.quote-import-preview .secondary{border:1px solid #cbd5e1;background:#fff;color:#475569}.quote-import-preview .primary{border:1px solid #2563eb;background:#2563eb;color:#fff}
.electronic-import-target{display:grid;gap:5px;border-top:1px solid #dbeafe;background:#f8fbff;padding:10px 12px}.electronic-import-target>span{color:#1e3a8a;font-size:12px;font-weight:900}.electronic-import-target select{max-width:420px;border:1px solid #93c5fd;border-radius:7px;background:#fff;padding:7px 9px;color:#1e3a8a;font-size:12px}.electronic-import-target small{color:#64748b;font-size:11px;line-height:1.5}.electronic-quote-groups{margin:12px;border:1px solid #99f6e4;border-radius:10px;background:#f0fdfa}.electronic-quote-groups>header{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 12px}.electronic-quote-groups>header>div{display:grid;gap:3px}.electronic-quote-groups strong{color:#115e59;font-size:13px}.electronic-quote-groups header span,.electronic-quote-groups em{color:#64748b;font-size:11px;font-style:normal}.electronic-quote-groups button{display:inline-flex;align-items:center;justify-content:center;gap:5px;height:31px;border-radius:7px;padding:0 10px;font-size:12px;font-weight:900}.electronic-quote-groups button.secondary{border:1px solid #5eead4;background:#fff;color:#0f766e}.electronic-quote-groups button svg{width:13px}.electronic-quote-group-controls{display:flex;flex-wrap:wrap;align-items:end;gap:8px;border-top:1px solid #ccfbf1;background:#fff;padding:9px 12px}.electronic-quote-group-controls label{display:grid;gap:4px;min-width:170px;color:#475569;font-size:11px;font-weight:800}.electronic-quote-group-controls input,.electronic-quote-group-controls select{height:32px;border:1px solid #cbd5e1;border-radius:7px;background:#fff;padding:0 8px;color:#334155;font-size:12px}.electronic-quote-group-controls .remove-electronic-group{border:1px solid #fecaca;background:#fff;color:#b91c1c}.electronic-quote-total{display:flex;flex-wrap:wrap;align-items:center;gap:10px;border-top:1px solid #ccfbf1;padding:9px 12px}.electronic-quote-total span{border-radius:999px;background:#fff;padding:4px 8px;color:#0f766e;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;font-weight:900}.electronic-quote-total em{margin-left:auto}
.electronic-empty-state{display:flex;align-items:center;gap:8px;margin:12px;border:1px dashed #5eead4;border-radius:10px;background:#f0fdfa;padding:15px 13px;color:#0f766e}.electronic-empty-state svg{width:18px}.electronic-empty-state strong{font-size:13px}.electronic-empty-state span{color:#64748b;font-size:11px}
.calculation-snapshot{border-top:1px solid #dbe5ea}.calculation-snapshot>header,.quote-attachments header{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px;padding:11px 13px;background:#f8fafc}.calculation-snapshot header strong,.quote-attachments strong{color:#334155;font-size:12px}.calculation-snapshot header span,.quote-attachments header span{color:#64748b;font-size:11px}.snapshot-table-scroll{overflow:auto}.calculation-snapshot table{width:100%;min-width:520px;border-collapse:collapse}.calculation-snapshot th{background:#eef2f6;padding:8px;color:#64748b;font-size:11px;text-align:left}.calculation-snapshot td{border-top:1px solid #eef2f6;padding:8px;color:#475569;font-size:12px}.calculation-snapshot td:last-child,.calculation-snapshot tfoot td{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-weight:900}.calculation-snapshot .calculated-amount-cell{background:#ecfdf5;color:#0f766e;font-variant-numeric:tabular-nums;font-weight:900}.calculation-snapshot tfoot td{color:#0f766e;text-align:right}.empty{padding:22px!important;color:#94a3b8!important;text-align:center}.quote-attachments{border-top:1px solid #e2e8f0}.quote-attachments>div{display:flex;flex-wrap:wrap;gap:7px;padding:11px 13px}.attachment-pill{display:inline-flex;overflow:hidden;border:1px solid #dbe5ea;border-radius:999px;background:#fff}.quote-attachments>div .attachment-pill button{display:inline-flex;align-items:center;gap:5px;border:0;background:#fff;padding:6px 9px;color:#475569;font-size:11px}.quote-attachments>div .attachment-pill button:hover:not(:disabled){background:#f0fdfa;color:#0f766e}.quote-attachments>div .attachment-pill .attachment-preview{border-left:1px solid #ccfbf1;color:#0f766e}.quote-attachments>div .attachment-pill .attachment-delete{border-left:1px solid #fecaca;border-radius:0;color:#dc2626}.quote-attachments>div .attachment-pill .attachment-delete:hover:not(:disabled){background:#fef2f2;color:#b91c1c}.quote-attachments>div .attachment-pill button:disabled{cursor:not-allowed;opacity:.4}.quote-attachments svg{width:12px}.quote-attachments em{color:#94a3b8;font-size:11px;font-style:normal}.quote-local-message,.quote-local-error{display:flex;align-items:center;gap:6px;margin:0;border-top:1px solid;padding:10px 13px;font-size:11px}.quote-local-message{border-color:#a7f3d0;background:#ecfdf5;color:#047857}.quote-local-error{border-color:#fecaca;background:#fef2f2;color:#b91c1c}.quote-local-message svg,.quote-local-error svg{width:14px}
.quote-reason-panel{display:grid;grid-template-columns:minmax(180px,1fr) minmax(240px,2fr) auto auto;align-items:center;gap:8px;border-top:1px solid #fed7aa;background:#fff7ed;padding:10px 13px}.quote-reason-panel>div{display:grid}.quote-reason-panel strong{color:#9a3412;font-size:12px}.quote-reason-panel span{margin-top:2px;color:#c2410c;font-size:11px}.quote-reason-panel textarea{min-width:0;border:1px solid #fdba74;border-radius:7px;padding:7px 9px;font-size:13px;resize:none}.quote-reason-panel button{height:32px;border-radius:7px;padding:0 10px;font-size:12px;font-weight:900}.quote-reason-panel button.secondary{border:1px solid #fdba74;background:#fff;color:#9a3412}.quote-reason-panel button.primary{border:1px solid #c2410c;background:#c2410c;color:#fff}.quote-editor-actions{position:sticky;bottom:0;z-index:4;display:flex;align-items:center;justify-content:space-between;gap:12px;border-top:1px solid #cbd5e1;background:rgb(248 250 252/.96);padding:11px 13px;backdrop-filter:blur(8px)}.quote-editor-actions>div:first-child{display:grid}.quote-editor-actions>div:first-child span{color:#64748b;font-size:11px}.quote-editor-actions>div:first-child b{margin-top:3px;color:#94a3b8;font-size:10px;font-weight:500}.quote-editor-actions>div:last-child{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px}.quote-editor-actions button{display:inline-flex;height:34px;align-items:center;gap:5px;border-radius:8px;padding:0 10px;font-size:12px;font-weight:900}.quote-editor-actions button svg{width:13px}.quote-editor-actions button.secondary{border:1px solid #cbd5e1;background:#fff;color:#475569}.quote-editor-actions button.primary{border:1px solid #0f766e;background:#0f766e;color:#fff}.quote-editor-actions button.withdraw{border:1px solid #f59e0b;background:#fffbeb;color:#b45309}.quote-editor-actions button.danger{border:1px solid #fecaca;background:#fff;color:#dc2626}.quote-editor-actions button.remove-section{border:1px solid #fca5a5;background:#fff1f2;color:#be123c}.quote-editor-actions button.remove-section:hover:not(:disabled){border-color:#fb7185;background:#ffe4e6}.quote-editor-actions button:disabled{opacity:.45}
.unsaved-draft-backdrop{position:fixed;inset:0;z-index:1000;display:grid;place-items:center;background:rgb(15 23 42/.46);padding:20px;backdrop-filter:blur(4px)}.unsaved-draft-dialog{width:min(480px,100%);overflow:hidden;border:1px solid #cbd5e1;border-radius:16px;background:#fff;box-shadow:0 28px 70px rgb(15 23 42/.3)}.unsaved-draft-dialog>header{display:flex;align-items:flex-start;gap:12px;padding:20px 20px 14px}.unsaved-draft-dialog>header>span{display:grid;width:40px;height:40px;flex:0 0 auto;place-items:center;border-radius:11px;background:#ccfbf1;color:#0f766e}.unsaved-draft-dialog>header svg{width:20px;height:20px}.unsaved-draft-dialog h3{margin:0;color:#0f172a;font-size:18px;font-weight:950}.unsaved-draft-dialog p{margin:5px 0 0;color:#64748b;font-size:13px;line-height:1.6}.unsaved-draft-note{display:flex;align-items:flex-start;gap:7px;margin:0 20px 18px;border:1px solid #bae6fd;border-radius:9px;background:#f0f9ff;padding:9px 10px;color:#0369a1;font-size:11px;line-height:1.55}.unsaved-draft-note svg{width:14px;height:14px;flex:0 0 auto;margin-top:1px}.unsaved-draft-dialog>footer{display:flex;justify-content:flex-end;gap:8px;border-top:1px solid #e2e8f0;background:#f8fafc;padding:13px 20px}.unsaved-draft-dialog button{display:inline-flex;height:36px;align-items:center;justify-content:center;gap:5px;border-radius:8px;padding:0 12px;font-size:12px;font-weight:900}.unsaved-draft-dialog button:disabled{cursor:wait;opacity:.5}.unsaved-draft-dialog button.discard{margin-right:auto;border:1px solid #fecaca;background:#fff;color:#dc2626}.unsaved-draft-dialog button.cancel{border:1px solid #cbd5e1;background:#fff;color:#475569}.unsaved-draft-dialog button.save{border:1px solid #0f766e;background:#0f766e;color:#fff}.unsaved-draft-dialog button.save svg{width:14px;height:14px}.unsaved-draft-dialog button:not(:disabled):hover{transform:translateY(-1px);filter:brightness(.98)}.remove-department-dialog>header>span{background:#ffe4e6;color:#be123c}.remove-department-dialog .remove-note{border-color:#fecdd3;background:#fff1f2;color:#9f1239}.unsaved-draft-dialog button.remove-confirm{border:1px solid #be123c;background:#be123c;color:#fff}.unsaved-draft-dialog button.remove-confirm svg{width:14px;height:14px}
@media(max-width:800px){.quote-editor-head,.quote-editor-actions{align-items:stretch;flex-direction:column}.quote-editor-tools,.quote-editor-actions>div:last-child{justify-content:flex-start}.quote-editor-actions{position:static}.quote-reason-panel{grid-template-columns:1fr}.quote-dependency-strip em{margin-left:0}.preview-metrics{grid-template-columns:1fr 1fr}}
@media(max-width:560px){.unsaved-draft-dialog>footer{align-items:stretch;flex-direction:column}.unsaved-draft-dialog button.discard{margin-right:0;order:3}.unsaved-draft-dialog button.cancel{order:2}.unsaved-draft-dialog button.save{order:1}}
</style>

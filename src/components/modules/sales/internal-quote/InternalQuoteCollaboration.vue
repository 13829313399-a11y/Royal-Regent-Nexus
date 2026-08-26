<script setup lang="ts">
import { AlertTriangle, ArrowLeft, BarChart3, Building2, CalendarDays, CheckCircle2, ChevronRight, CircleDollarSign, CircleUserRound, FileImage, FileText, Layers3, LockKeyhole, Maximize2, Pencil, RefreshCw, Save, Send, ShieldCheck, UserPlus, XCircle } from '@lucide/vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import InternalQuoteActivityPanel from './InternalQuoteActivityPanel.vue'
import InternalQuoteComponentScopePicker from './InternalQuoteComponentScopePicker.vue'
import InternalQuoteDepartmentFilesPanel from './InternalQuoteDepartmentFilesPanel.vue'
import InternalQuoteHeaderDialog from './InternalQuoteHeaderDialog.vue'
import InternalQuoteMaterialsDialog from './InternalQuoteMaterialsDialog.vue'
import InternalQuoteProductActions from './InternalQuoteProductActions.vue'
import InternalQuoteSectionEditor from './InternalQuoteSectionEditor.vue'
import InternalQuoteSectionRail from './InternalQuoteSectionRail.vue'
import { getFactoryScopedRoute, isFactoryContextId } from '@/data/enterpriseMock'
import { internalQuoteSectionDefinitions } from '@/data/internalQuoteDeskConfig'
import { canEditAllInternalQuoteSections, canReviewInternalQuoteSections, isForeignFactory, isInternalQuoteReadOnly } from '@/lib/internalQuoteAccess'
import type { InternalQuoteFormBlock } from '@/lib/internalQuoteBlockProgress'
import { consumeInternalQuoteProductScroll, rememberInternalQuoteProductScroll } from '@/lib/internalQuoteProductScroll'
import { cloneInternalQuotePayload, salesSettlementDivisorForMiscRatio, type SalesMarkupTier, type SalesPricingComponent } from '@/lib/internalQuoteSectionPayload'
import { internalQuoteApi, internalQuoteAttachmentPreviewUrl, type InternalQuoteHeaderUpdateRequest } from '@/api/internalQuote'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import type { InternalQuoteAttachmentRecord, InternalQuoteBatchProduct, InternalQuoteSection, InternalQuoteSectionCode } from '@/types/internalQuoteDesk'

const route = useRoute()
const router = useRouter()
const quoteStore = useInternalQuoteDeskStore()
const authStore = useAuthStore()
const appStore = useAppStore()
const message = ref('')
const errorMessage = ref('')
const syncPanelOpen = ref(false)
const syncReason = ref('')
const participationPanelOpen = ref(false)
const selectedParticipation = ref<InternalQuoteSectionCode[]>([])
const initialParticipation = ref<InternalQuoteSectionCode[]>([])
const participationRemovalConfirmOpen = ref(false)
const activeContinuousSectionCode = ref<InternalQuoteSectionCode>('sales')
const sectionEditors = ref<Partial<Record<InternalQuoteSectionCode, InstanceType<typeof InternalQuoteSectionEditor> | null>>>({})
const sectionNodes = ref<Partial<Record<InternalQuoteSectionCode, HTMLElement>>>({})
const sectionBlockProgress = ref<Partial<Record<InternalQuoteSectionCode, InternalQuoteFormBlock[]>>>({})
const wholeRejectOpen = ref(false)
const wholeRejectReason = ref('')
const rightPanelTab = ref<'quote' | 'files'>('quote')
const rightPanelPinned = ref(false)
const rightPanelResizing = ref(false)
const rightPanelWidth = ref(360)
const requestedFileAttachmentId = ref('')
let rightPanelResizeStartX = 0
let rightPanelResizeStartWidth = 0
let sectionObserver: IntersectionObserver | undefined
const markupMessage = ref('')
const markupError = ref('')
const headerDialogOpen = ref(false)
const headerDialogBusy = ref(false)
const headerDialogError = ref('')
const headerBusinessOwners = ref<Array<{ id: string; username: string; displayName: string }>>([])
const headerCustomers = ref<string[]>([])
const copyBusyQuoteId = ref('')
const productImagePreviewOpen = ref(false)
const wholeProductSaving = ref(false)
const materialsDialogOpen = ref(false)
const materialsDialogBusy = ref(false)
const materialsDialogError = ref('')
const activePricingComponentId = ref('')

const quoteId = computed(() => String(route.params.quoteId ?? ''))
const loadedQuote = computed(() => quoteStore.getQuoteById(quoteId.value))
const quote = computed(() => loadedQuote.value ?? quoteStore.placeholderQuote)
const batchProducts = computed(() => quoteStore.batchProductsByQuoteId[quoteId.value] ?? [])
const currentBatchProduct = computed(() => batchProducts.value.find((product) => product.quoteId === quoteId.value))
const baselineDifferentSections = computed(() => currentBatchProduct.value?.differentSections ?? [])
const baselineDifferenceLabel = computed(() => {
  const product = currentBatchProduct.value
  if (!product || product.isBaseline) return ''
  if (!product.differsFromBaseline) return '全部内容沿用基准款'
  const parts: string[] = []
  if (product.differentHeaderFields.length) parts.push('报价资料')
  if (product.differentSections.length) parts.push(`${product.differentSections.length} 个部门`)
  return `与基准款不同：${parts.join('、')}`
})
const currentProductImageUrl = computed(() => {
  const product = currentBatchProduct.value
  return product?.mainImage ? internalQuoteAttachmentPreviewUrl(product.quoteId, product.mainImage.id) : ''
})
const isMultiProduct = computed(() => batchProducts.value.length > 1)
const batchReady = computed(() => batchProducts.value.length > 0
  && batchProducts.value.every((product) => product.status === 'fully_approved'))
const isWholeQuoteReview = computed(() => quote.value.moduleVersion === 'v3')
const selectedFactoryId = computed(() => appStore.activeFactory.id === 'group'
  ? appStore.activeProductionFactory.id
  : appStore.activeFactory.id)
const participatingSections = computed(() => quote.value.sections.filter((section) => section.isRequired))
const optionalSectionCodes: InternalQuoteSectionCode[] = ['electronic', 'molding', 'painting', 'slush', 'sewing', 'hair']
const manageableOptionalSections = computed(() => quote.value.sections.filter((section) => optionalSectionCodes.includes(section.code)))
const participationChanges = computed(() => {
  const initial = new Set(initialParticipation.value)
  const selected = new Set(selectedParticipation.value)
  return {
    additions: manageableOptionalSections.value.filter((section) => selected.has(section.code) && !initial.has(section.code)),
    removals: manageableOptionalSections.value.filter((section) => initial.has(section.code) && !selected.has(section.code)),
  }
})
const hasParticipationChanges = computed(() => participationChanges.value.additions.length > 0 || participationChanges.value.removals.length > 0)
const activeSectionCode = computed<InternalQuoteSectionCode>(() => {
  if (isWholeQuoteReview.value) return activeContinuousSectionCode.value
  const requested = String(route.query.section ?? '') as InternalQuoteSectionCode
  return participatingSections.value.some((section) => section.code === requested)
    ? requested
    : participatingSections.value[0]?.code ?? 'sales'
})
const activeSection = computed(() => participatingSections.value.find((section) => section.code === activeSectionCode.value) ?? participatingSections.value[0] ?? quote.value.sections[0])
const approvedCount = computed(() => participatingSections.value.filter((section) => ['approved', 'not_applicable'].includes(section.status)).length)
type SectionProgressState = 'empty' | 'in_progress' | 'completed' | 'issue'
function sectionProgress(section: InternalQuoteSection): SectionProgressState {
  if (section.status === 'rejected' || section.dependencyStatus === 'stale' || section.warnings.length) return 'issue'
  if (section.filledAt && section.calculationStatus === 'valid' && section.dependencyStatus === 'current') return 'completed'
  if (section.filledAt || Object.keys(section.payload).length) return 'in_progress'
  return 'empty'
}
const completedCount = computed(() => isWholeQuoteReview.value
  ? participatingSections.value.filter((section) => sectionProgress(section) === 'completed').length
  : approvedCount.value)
const progressPercent = computed(() => participatingSections.value.length ? completedCount.value / participatingSections.value.length * 100 : 0)
const collaborationStatusLabel = computed(() => {
  if (!isWholeQuoteReview.value) return quote.value.status === 'rejected' ? '存在退回' : '协作进行中'
  return {
    drafting: '整单填写中',
    pending_review: '整单填写中',
    fully_approved: '可提交整单',
    final_pending: '待整单审核',
    rejected: '整单已退回',
    released: '整单审核通过',
    exported: '整单已输出',
    archived: '已归档',
  }[quote.value.status]
})
const wholeReviewDescription = computed(() => {
  if (quote.value.status === 'fully_approved') return '所有参与部门资料已经保存并通过服务端校验，可以统一提交给指定审核人。'
  if (quote.value.status === 'final_pending') return `整份报价已经锁定，正在等待 ${quote.value.businessOwner} 统一审核。`
  if (quote.value.status === 'rejected') return quote.value.finalReviewComment
    ? `整单退回原因：${quote.value.finalReviewComment}。报价头及全部部门内容已经解锁。`
    : '整单已退回，报价头及全部部门内容已经解锁。'
  if (['released', 'exported'].includes(quote.value.status)) return '整单审核已经通过，可以进入汇总页面生成受控报价输出。'
  if (quote.value.status === 'archived') return '该报价已经归档，仅供查看。'
  return '各部门按原有权限填写并保存内容；全部完成后只提交一次整单审核。'
})
function canEditSection(code: InternalQuoteSectionCode) {
  const definition = internalQuoteSectionDefinitions.find((item) => item.code === code)
  return canEditAllInternalQuoteSections(authStore, quote.value.factoryId)
    || (definition?.departments ?? []).some((department) => authStore.can(`internal_quote:${code}_edit`, quote.value.factoryId, department))
}
const canEditActive = computed(() => canEditSection(activeSectionCode.value))
const canReviewActive = computed(() => canReviewInternalQuoteSections(
  authStore,
  quote.value.factoryId,
  quote.value.businessOwnerId,
  quote.value.createdById,
))
const canSubmitWholeReview = computed(() => isWholeQuoteReview.value
  && authStore.can('internal_quote:final_submit', quote.value.factoryId, 'sales-business'))
const canReviewWholeBase = computed(() => isWholeQuoteReview.value && canReviewInternalQuoteSections(
  authStore,
  quote.value.factoryId,
  quote.value.businessOwnerId,
  quote.value.createdById,
))
const canSelfReviewWhole = computed(() => quote.value.createdById === authStore.currentUser?.id
  && authStore.can('internal_quote:self_review', quote.value.factoryId, 'sales-business'))
const canReviewWhole = computed(() => canReviewWholeBase.value
  && (quote.value.finalSubmittedById !== authStore.currentUser?.id || canSelfReviewWhole.value))
const canSyncReference = computed(() => ['sales-business', 'engineering'].some((department) => authStore.can('internal_quote:reference_manage', quote.value.factoryId, department)))
const canEditSidebarPricing = computed(() => (
  !['final_pending', 'released', 'exported', 'archived'].includes(quote.value.status)
  && ([
    ['internal_quote:sales_edit', 'sales-business'],
    ['internal_quote:engineering_edit', 'engineering'],
  ] as const).some(([permission, department]) => authStore.can(permission, quote.value.factoryId, department))
))
const canEditFx = computed(() => canEditSidebarPricing.value)
const canEditMaterials = computed(() => canEditSidebarPricing.value)
const salesSection = computed(() => quote.value.sections.find((section) => section.code === 'sales'))
const pricingComponents = computed<SalesPricingComponent[]>(() => {
  const source = salesSection.value?.payload.pricing_components
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
const isComponentPricing = computed(() => salesSection.value?.payload.pricing_mode === 'component' && pricingComponents.value.length > 0)
const pricingComponentSignature = computed(() => pricingComponents.value.map((component) => component.id).join('|'))
let pricingComponentQuoteId = ''
watch([quoteId, pricingComponentSignature], () => {
  const quoteChanged = pricingComponentQuoteId !== quoteId.value
  pricingComponentQuoteId = quoteId.value
  if (!isComponentPricing.value) {
    activePricingComponentId.value = ''
    return
  }
  if (quoteChanged || !pricingComponents.value.some((component) => component.id === activePricingComponentId.value)) {
    activePricingComponentId.value = pricingComponents.value[0]?.id ?? ''
  }
}, { immediate: true })
const canEditMarkup = computed(() => canEditSidebarPricing.value)
const markupBlockedReason = computed(() => {
  if (!canEditMarkup.value) return ''
  if (!salesSection.value) return '业务部分段不存在，暂时无法保存码数与杂项。'
  if (['draft', 'rejected'].includes(salesSection.value.status)) return ''
  if (isWholeQuoteReview.value) return '整单已经提交或审核通过；整单退回并全部解锁后才能修改码数与杂项。'
  return '业务部已提交或审核完成；请先重开业务部分段，再保存新的码数与杂项。'
})
const canManageParticipation = computed(() => quote.value.status !== 'archived' && ['sales-business', 'engineering'].some((department) => authStore.can('internal_quote:create', quote.value.factoryId, department)))
const canEditHeader = computed(() => (
  !['final_pending', 'released', 'exported', 'archived'].includes(quote.value.status)
  && (isWholeQuoteReview.value && quote.value.status === 'rejected'
    || participatingSections.value.every((section) => section.status === 'draft' && section.revision === 1))
  && authStore.can('internal_quote:header_edit', quote.value.factoryId, 'sales-business')
))
const canRemoveActive = computed(() => canRemoveSection(activeSectionCode.value))
const isReadOnly = computed(() => isInternalQuoteReadOnly(authStore, quote.value.factoryId))
const isForeignReadOnly = computed(() => isReadOnly.value && isForeignFactory(authStore, quote.value.factoryId))
const getQuoteRoute = (path: string) => getFactoryScopedRoute(
  path,
  isFactoryContextId(quote.value.factoryId) ? quote.value.factoryId : 'huaxing',
)

function canRemoveSection(code: InternalQuoteSectionCode) {
  return canManageParticipation.value
    && optionalSectionCodes.includes(code)
    && (!isWholeQuoteReview.value || ['drafting', 'rejected'].includes(quote.value.status))
}

function setSectionEditorRef(code: InternalQuoteSectionCode, instance: unknown) {
  sectionEditors.value[code] = instance as InstanceType<typeof InternalQuoteSectionEditor> | null
}

function updateSectionBlockProgress(code: InternalQuoteSectionCode, blocks: InternalQuoteFormBlock[]) {
  const current = sectionBlockProgress.value[code]
  if (current?.length === blocks.length && current.every((block, index) => (
    block.id === blocks[index]?.id
    && block.status === blocks[index]?.status
    && block.requirement === blocks[index]?.requirement
    && block.criteria === blocks[index]?.criteria
  ))) return
  sectionBlockProgress.value = { ...sectionBlockProgress.value, [code]: blocks }
}

function setSectionNode(code: InternalQuoteSectionCode, node: unknown) {
  if (node instanceof HTMLElement) sectionNodes.value[code] = node
  else delete sectionNodes.value[code]
}

function setupSectionObserver() {
  sectionObserver?.disconnect()
  sectionObserver = undefined
  if (!isWholeQuoteReview.value || typeof IntersectionObserver === 'undefined') return
  sectionObserver = new IntersectionObserver((entries) => {
    const visible = entries.filter((entry) => entry.isIntersecting)
      .sort((left, right) => Math.abs(left.boundingClientRect.top - 140) - Math.abs(right.boundingClientRect.top - 140))
    const code = visible[0]?.target.getAttribute('data-section-code') as InternalQuoteSectionCode | null
    if (code) activeContinuousSectionCode.value = code
  }, { rootMargin: '-110px 0px -65% 0px', threshold: [0, 0.01] })
  Object.values(sectionNodes.value).forEach((node) => node && sectionObserver?.observe(node))
}

function selectSection(code: InternalQuoteSectionCode) {
  if (!isWholeQuoteReview.value) {
    void router.replace({ query: { ...route.query, section: code } })
    return
  }
  activeContinuousSectionCode.value = code
  sectionNodes.value[code]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function selectPageAnchor(anchor: 'overview' | 'actions') {
  document.getElementById(anchor === 'overview' ? 'quote-page-overview' : 'quote-page-actions')
    ?.scrollIntoView({ behavior: 'smooth', block: anchor === 'overview' ? 'start' : 'end' })
}

function openDepartmentFile(sectionCode: InternalQuoteSectionCode, attachment: InternalQuoteAttachmentRecord) {
  activeContinuousSectionCode.value = sectionCode
  rightPanelTab.value = 'files'
  requestedFileAttachmentId.value = attachment.id
  rightPanelPinned.value = true
}

async function downloadDepartmentFile(attachment: InternalQuoteAttachmentRecord) {
  message.value = ''
  errorMessage.value = ''
  try {
    await quoteStore.downloadAttachment(quote.value.id, attachment.id, attachment.fileName)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '下载资料失败。'
  }
}

function resizeRightPanel(event: PointerEvent) {
  if (!rightPanelResizing.value) return
  const maximum = Math.max(300, Math.min(920, window.innerWidth - 24))
  rightPanelWidth.value = Math.min(maximum, Math.max(300, rightPanelResizeStartWidth + rightPanelResizeStartX - event.clientX))
}

function stopRightPanelResize() {
  if (!rightPanelResizing.value) return
  rightPanelResizing.value = false
  window.removeEventListener('pointermove', resizeRightPanel)
  window.removeEventListener('pointerup', stopRightPanelResize)
}

function startRightPanelResize(event: PointerEvent) {
  event.preventDefault()
  rightPanelResizeStartX = event.clientX
  rightPanelResizeStartWidth = rightPanelWidth.value
  rightPanelResizing.value = true
  rightPanelPinned.value = true
  window.addEventListener('pointermove', resizeRightPanel)
  window.addEventListener('pointerup', stopRightPanelResize)
}

async function loadQuote() {
  message.value = ''
  errorMessage.value = ''
  quoteStore.conflictMessage = ''
  await Promise.all([
    quoteStore.loadQuote(quoteId.value),
    quoteStore.loadBatchProducts(quoteId.value),
  ])
}

async function switchProduct(product: InternalQuoteBatchProduct) {
  if (product.quoteId === quoteId.value) return
  rememberInternalQuoteProductScroll(document.scrollingElement?.scrollTop ?? window.scrollY)
  try {
    await router.push(getQuoteRoute(`/modules/sales-business/internal-quote-desk/${product.quoteId}/collaboration`))
  } catch (error) {
    consumeInternalQuoteProductScroll()
    throw error
  }
}

async function loadSwitchedProduct() {
  const scrollTop = consumeInternalQuoteProductScroll()
  await loadQuote()
  if (scrollTop === null) return
  await nextTick()
  requestAnimationFrame(() => requestAnimationFrame(() => {
    window.scrollTo({ top: scrollTop, behavior: 'auto' })
  }))
}

async function copyBaselineToProduct(product: InternalQuoteBatchProduct) {
  if (product.isBaseline || copyBusyQuoteId.value) return
  if (!window.confirm(`确认用基准款覆盖“${product.productName}”的全部部门报价与资料附件？产品名称和主图会保留。`)) return
  copyBusyQuoteId.value = product.quoteId
  message.value = ''
  errorMessage.value = ''
  try {
    await quoteStore.copyBatchBaseline(quoteId.value, product.quoteId, product.headerRevision)
    message.value = `已把基准款整份报价复制到“${product.productName}”；此后两款独立修改，不会自动同步。`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '复制基准款失败。'
  } finally {
    copyBusyQuoteId.value = ''
  }
}

async function uploadCurrentProductImage(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  message.value = ''
  errorMessage.value = ''
  try {
    await quoteStore.uploadProductImage(quote.value.id, file)
    message.value = `“${quote.value.productName}”的产品主图已更新。`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '上传产品主图失败。'
  }
}

async function syncReference() {
  if (!canSyncReference.value) {
    syncPanelOpen.value = false
    errorMessage.value = '当前账号没有该厂区的参考资料同步权限。'
    return
  }
  if (!syncReason.value.trim()) return
  message.value = ''
  errorMessage.value = ''
  try {
    await quoteStore.syncReferenceSnapshot(quote.value.id, quote.value.headerRevision, syncReason.value.trim())
    message.value = '参考快照已同步；受影响分段已重算或标记依赖失效。'
    syncReason.value = ''
    syncPanelOpen.value = false
  } catch (error) { errorMessage.value = error instanceof Error ? error.message : '同步参考快照失败。' }
}

async function updateReferenceFx(payload: { rmbHkd: string; hkdUsd: string }) {
  message.value = ''
  errorMessage.value = ''
  try {
    await quoteStore.updateReferenceFx(
      quote.value.id,
      quote.value.headerRevision,
      payload.rmbHkd,
      payload.hkdUsd,
    )
    message.value = '汇率已保存为新的冻结参考快照；该报价已按新汇率重算。'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '保存汇率失败。'
  }
}

async function updateQuoteMarkup(payload: { markupTiers: Array<{ moq: string; markup: string; includeInOutput: boolean }>; selectedMoq: string; miscRatio: string; componentMarkups?: Array<{ id: string; markup: string }> }) {
  markupMessage.value = ''
  markupError.value = ''
  message.value = ''
  errorMessage.value = ''
  if (!canEditMarkup.value || markupBlockedReason.value) {
    markupError.value = markupBlockedReason.value || '当前账号没有该厂区的工程部或业务部侧栏编辑权限。'
    return
  }
  const markupTiers: SalesMarkupTier[] = payload.markupTiers.map((tier) => ({
    moq: Number(tier.moq),
    markup_x: Number(tier.markup),
    include_in_output: tier.includeInOutput,
  }))
  const selectedMoq = Number(payload.selectedMoq)
  const miscRatio = Number(payload.miscRatio)
  if (markupTiers.length !== 3
    || markupTiers.some((tier) => !Number.isInteger(tier.moq) || tier.moq < 1 || tier.moq > 100000000
      || !Number.isFinite(tier.markup_x) || tier.markup_x < .01 || tier.markup_x > 9.99)
    || markupTiers.some((tier, index) => index > 0 && tier.moq <= markupTiers[index - 1]!.moq)) {
    markupError.value = '请完整填写三档递增的 MOQ 区间和 0.01 至 9.99 的码数。'
    return
  }
  if (!markupTiers.some((tier) => tier.include_in_output !== false)) {
    markupError.value = '内部报价表至少要输出一个 MOQ 价格。'
    return
  }
  const selectedTier = markupTiers.find((tier) => tier.moq === selectedMoq)
  if (!selectedTier) {
    markupError.value = '请选择本单采用的 MOQ 档位。'
    return
  }
  selectedTier.include_in_output = true
  if (!Number.isFinite(miscRatio) || miscRatio < 0 || miscRatio >= 1) {
    markupError.value = '杂项率必须大于等于 0% 且小于 100%。'
    return
  }
  const componentMarkups = (payload.componentMarkups ?? []).map((row) => ({ id: row.id, markup: Number(row.markup) }))
  if (componentMarkups.some((row) => !row.id || !Number.isFinite(row.markup) || row.markup < .01 || row.markup > 9.99)) {
    markupError.value = 'JustPlay 分项倍率必须在 0.01 至 9.99 之间。'
    return
  }
  const activeMarkup = componentMarkups[0]?.markup ?? selectedTier.markup_x
  if (componentMarkups.length) selectedTier.markup_x = activeMarkup
  try {
    const salesEditor = sectionEditors.value.sales
    if (salesEditor) {
      await salesEditor.saveSalesMarkup(markupTiers, selectedMoq, activeMarkup, miscRatio, componentMarkups.length ? componentMarkups : undefined)
      markupMessage.value = componentMarkups.length
        ? 'JustPlay 各分项倍率、杂项系数及当前业务部草稿已保存并重新计算。'
        : `已选择 MOQ ${selectedMoq.toLocaleString('zh-CN')} 档；三档码数、杂项系数及当前业务部草稿已保存并重新计算。`
    } else {
      const section = salesSection.value
      if (!section) throw new Error('业务部分段不存在，暂时无法保存码数与杂项。')
      const sourceShipping = section.payload.shipping && typeof section.payload.shipping === 'object' && !Array.isArray(section.payload.shipping)
        ? section.payload.shipping as Record<string, unknown>
        : {}
      const componentMarkupById = new Map(componentMarkups.map((row) => [row.id, row.markup]))
      const sourcePricingComponents = Array.isArray(section.payload.pricing_components) ? section.payload.pricing_components : []
      const nextPricingComponents = sourcePricingComponents.flatMap((value, index) => {
        if (!value || typeof value !== 'object' || Array.isArray(value)) return []
        const row = value as Record<string, unknown>
        const id = String(row.id ?? '').trim()
        const name = String(row.name ?? '').trim()
        const componentMarkup = componentMarkupById.get(id)
        return id && name ? [{ id, name, ...(componentMarkup != null && (index === 0 || Math.abs(componentMarkup - activeMarkup) > .000001) ? { markup_x: Number(componentMarkup.toFixed(2)) } : {}) }] : []
      })
      const nextPayload = cloneInternalQuotePayload('sales', {
        ...section.payload,
        ...(componentMarkups.length ? { pricing_mode: 'component', pricing_components: nextPricingComponents } : {}),
        shipping: {
          ...sourceShipping,
          markup_x: Number(activeMarkup.toFixed(2)),
          markup_tiers: markupTiers.map((tier) => ({ moq: tier.moq, markup_x: Number(tier.markup_x.toFixed(2)), include_in_output: tier.include_in_output !== false })),
          selected_markup_moq: selectedMoq,
          misc_ratio: Number(miscRatio.toFixed(4)),
          divisor: salesSettlementDivisorForMiscRatio(miscRatio),
        },
      })
      await quoteStore.saveSection(quote.value.id, 'sales', section.revision, nextPayload, componentMarkups.length ? '在协作侧栏保存 JustPlay 分项倍率与杂项系数' : '在协作侧栏保存分段 MOQ 码数与杂项系数')
      markupMessage.value = componentMarkups.length
        ? 'JustPlay 分项倍率与杂项系数已保存为业务部新 revision。'
        : `MOQ ${selectedMoq.toLocaleString('zh-CN')} 档已设为本单采用；分段码数与杂项系数已保存为业务部新 revision。`
    }
    message.value = markupMessage.value
  } catch (error) {
    markupError.value = error instanceof Error ? error.message : '保存分段码数与杂项失败。'
  }
}

function toggleParticipationPanel() {
  if (participationPanelOpen.value) {
    selectedParticipation.value = []
    initialParticipation.value = []
    participationRemovalConfirmOpen.value = false
    participationPanelOpen.value = false
    return
  }
  const current = manageableOptionalSections.value
    .filter((section) => section.isRequired)
    .map((section) => section.code)
  selectedParticipation.value = [...current]
  initialParticipation.value = [...current]
  participationRemovalConfirmOpen.value = false
  participationPanelOpen.value = true
}

async function saveParticipationChanges(confirmRemovals = false) {
  if (!hasParticipationChanges.value) {
    message.value = '参与部门没有变化，已保留当前设置。'
    errorMessage.value = ''
    toggleParticipationPanel()
    return
  }
  const additions = participationChanges.value.additions
  const removals = participationChanges.value.removals
  if (removals.length && !confirmRemovals) {
    participationRemovalConfirmOpen.value = true
    return
  }
  message.value = ''
  errorMessage.value = ''
  try {
    if (additions.length) {
      await quoteStore.addParticipation(
        quote.value.id,
        quote.value.headerRevision,
        additions.map((section) => section.code),
      )
    }
    if (removals.length) {
      await quoteStore.removeParticipation(
        quote.value.id,
        quote.value.headerRevision,
        removals.map((section) => section.code),
      )
    }
    const changeMessages = [
      additions.length ? `已添加：${additions.map((section) => section.label).join('、')}` : '',
      removals.length ? `已移除：${removals.map((section) => section.label).join('、')}` : '',
    ].filter(Boolean)
    message.value = `参与部门已更新；${changeMessages.join('；')}。协作进度、成本汇总和最终放行已同步调整。`
    selectedParticipation.value = []
    initialParticipation.value = []
    participationRemovalConfirmOpen.value = false
    participationPanelOpen.value = false
    const currentActiveCode = activeContinuousSectionCode.value
    if (removals.some((section) => section.code === currentActiveCode)) {
      activeContinuousSectionCode.value = participatingSections.value[0]?.code ?? 'sales'
    } else if (additions[0]) {
      selectSection(additions[0].code)
    }
  } catch (error) {
    participationRemovalConfirmOpen.value = false
    errorMessage.value = error instanceof Error ? error.message : '更新参与部门失败。'
  }
}

async function removeParticipation(sectionCode: InternalQuoteSectionCode) {
  if (!canManageParticipation.value || !optionalSectionCodes.includes(sectionCode)) return
  message.value = ''
  errorMessage.value = ''
  const sectionLabel = quote.value.sections.find((section) => section.code === sectionCode)?.label ?? '该部门'
  try {
    await quoteStore.removeParticipation(quote.value.id, quote.value.headerRevision, [sectionCode])
    message.value = `${sectionLabel}已移出当前报价；已不再计入进度、成本汇总和最终放行。`
    const fallbackSection = participatingSections.value[0]?.code ?? 'sales'
    await router.replace({ query: { ...route.query, section: fallbackSection } })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '移除参与部门失败。'
  }
}

async function openHeaderDialog() {
  if (!canEditHeader.value || !quote.value.id) return
  const requestedQuoteId = quote.value.id
  const requestedFactoryId = quote.value.factoryId
  headerDialogOpen.value = true
  headerDialogBusy.value = true
  headerDialogError.value = ''
  try {
    const [owners, customers] = await Promise.all([
      internalQuoteApi.listBusinessOwners(requestedFactoryId),
      internalQuoteApi.listCustomers(requestedFactoryId),
    ])
    if (!headerDialogOpen.value || quote.value.id !== requestedQuoteId) return
    headerBusinessOwners.value = owners.map((owner) => ({ id: owner.id, username: owner.username, displayName: owner.display_name }))
    headerCustomers.value = Array.from(new Set([quote.value.customer, ...customers.map((customer) => customer.name)]))
  } catch (error) {
    if (headerDialogOpen.value && quote.value.id === requestedQuoteId) {
      headerDialogError.value = error instanceof Error ? error.message : '读取当前厂区客户和业务负责人失败。'
    }
  } finally {
    if (headerDialogOpen.value && quote.value.id === requestedQuoteId) headerDialogBusy.value = false
  }
}

function closeHeaderDialog() {
  if (headerDialogBusy.value) return
  headerDialogOpen.value = false
  headerDialogError.value = ''
}

function openMaterialsDialog() {
  materialsDialogError.value = ''
  materialsDialogOpen.value = true
}

function closeMaterialsDialog() {
  if (materialsDialogBusy.value) return
  materialsDialogOpen.value = false
  materialsDialogError.value = ''
}

async function saveHeader(payload: InternalQuoteHeaderUpdateRequest) {
  if (!canEditHeader.value) return
  headerDialogBusy.value = true
  headerDialogError.value = ''
  try {
    await quoteStore.updateHeader(quote.value.id, payload)
    headerDialogOpen.value = false
    message.value = '报价资料已保存为新的报价头 revision。'
  } catch (error) {
    headerDialogError.value = error instanceof Error ? error.message : '保存报价资料失败。'
  } finally {
    headerDialogBusy.value = false
  }
}

async function saveReferenceMaterials(
  rows: Array<{ material: string; grade: string; price_hkd_lb: string }>,
  options: { closeAfter: boolean },
) {
  if (!canEditMaterials.value) return
  materialsDialogBusy.value = true
  materialsDialogError.value = ''
  message.value = ''
  errorMessage.value = ''
  try {
    await quoteStore.updateReferenceMaterials(quote.value.id, quote.value.headerRevision, rows)
    await quoteStore.loadBatchProducts(quote.value.id)
    if (options.closeAfter) materialsDialogOpen.value = false
    message.value = '本报价专用料价已保存；所有依赖部门已由服务器重新计算。'
  } catch (error) {
    const saveError = error instanceof Error ? error.message : '保存本报价专用料价失败。'
    materialsDialogError.value = saveError
    errorMessage.value = saveError
  } finally {
    materialsDialogBusy.value = false
  }
}

function hasUnsavedDepartmentChanges() {
  return Object.values(sectionEditors.value).some((editor) => editor?.hasUnsavedChanges())
}

async function saveWholeProductDraft() {
  message.value = ''
  errorMessage.value = ''
  const dirtySections = participatingSections.value.filter((section) => sectionEditors.value[section.code]?.hasUnsavedChanges())
  if (!dirtySections.length) {
    message.value = `“${quote.value.productName}”当前没有需要保存的修改。`
    return
  }
  wholeProductSaving.value = true
  const savedLabels: string[] = []
  try {
    for (const section of dirtySections) {
      const editor = sectionEditors.value[section.code]
      if (!editor) throw new Error(`${section.label}编辑器尚未就绪。`)
      await editor.saveWholeQuoteDraft(false)
      savedLabels.push(section.label)
    }
    const refreshed = await quoteStore.loadQuote(quote.value.id)
    if (!refreshed) throw new Error('全部分部已写入服务器，但页面未能读取最新报价，请点击“重新读取最新 revision”。')
    message.value = `“${quote.value.productName}”已统一保存：${savedLabels.join('、')}。`
  } catch (error) {
    const savedNote = savedLabels.length ? `；此前已保存：${savedLabels.join('、')}` : ''
    errorMessage.value = `${error instanceof Error ? error.message : '统一保存当前款失败'}${savedNote}。`
  } finally {
    wholeProductSaving.value = false
  }
}

async function submitWholeReview() {
  message.value = ''
  errorMessage.value = ''
  if (!canSubmitWholeReview.value) {
    errorMessage.value = '当前账号没有该厂区的整单提交权限。'
    return
  }
  if (!batchReady.value) {
    errorMessage.value = '批次内全部产品的参与部门都保存有效内容后，才能一次提交整批审核。'
    return
  }
  if (hasUnsavedDepartmentChanges()) {
    errorMessage.value = '页面仍有未保存的修改，请先在页面最下方点击“保存”，再提交审核。'
    return
  }
  try {
    await quoteStore.submitFinal(quote.value.id, quote.value.headerRevision)
    await quoteStore.loadBatchProducts(quote.value.id)
    message.value = `${batchProducts.value.length} 款报价已全部锁定并一次提交给 ${quote.value.businessOwner} 审核。`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '提交整单审核失败。'
  }
}

async function approveWholeReview() {
  message.value = ''
  errorMessage.value = ''
  if (!canReviewWhole.value) {
    errorMessage.value = `只有创建报价时指定的整单审核人（${quote.value.businessOwner}）可以审核。`
    return
  }
  try {
    await quoteStore.reviewFinal(quote.value.id, quote.value.headerRevision, 'approve')
    await quoteStore.loadBatchProducts(quote.value.id)
    message.value = '整批审核已通过，每款产品都可分别进入汇总与受控输出。'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '整单审核通过失败。'
  }
}

function toggleWholeReject() {
  wholeRejectOpen.value = !wholeRejectOpen.value
  wholeRejectReason.value = ''
}

async function rejectWholeReview() {
  message.value = ''
  errorMessage.value = ''
  if (!canReviewWhole.value) {
    errorMessage.value = `只有创建报价时指定的整单审核人（${quote.value.businessOwner}）可以退回。`
    return
  }
  if (!wholeRejectReason.value.trim()) {
    errorMessage.value = '整单退回必须填写原因。'
    return
  }
  try {
    await quoteStore.reviewFinal(quote.value.id, quote.value.headerRevision, 'reject', wholeRejectReason.value.trim())
    await quoteStore.loadBatchProducts(quote.value.id)
    message.value = '整批报价已退回并全部解锁，各产品、各部门可按原权限继续修改。'
    wholeRejectOpen.value = false
    wholeRejectReason.value = ''
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '整单退回失败。'
  }
}

onMounted(loadSwitchedProduct)
watch(quoteId, loadSwitchedProduct)
watch([selectedFactoryId, () => loadedQuote.value?.factoryId], ([factoryId, quoteFactoryId]) => {
  if (!quoteFactoryId || quoteFactoryId === factoryId || !isFactoryContextId(factoryId)) return
  void router.replace(getFactoryScopedRoute('/modules/sales-business/internal-quote-desk', factoryId))
})
watch([quoteId, canSyncReference], () => {
  syncPanelOpen.value = false
  syncReason.value = ''
})
watch(quoteId, () => {
  markupMessage.value = ''
  markupError.value = ''
  sectionBlockProgress.value = {}
  wholeRejectOpen.value = false
  wholeRejectReason.value = ''
  productImagePreviewOpen.value = false
  materialsDialogOpen.value = false
})
watch([isWholeQuoteReview, participatingSections], async ([whole]) => {
  if (!whole) {
    sectionObserver?.disconnect()
    sectionObserver = undefined
    return
  }
  if (!participatingSections.value.some((section) => section.code === activeContinuousSectionCode.value)) {
    activeContinuousSectionCode.value = participatingSections.value[0]?.code ?? 'sales'
  }
  if ('section' in route.query) {
    const { section: _section, ...query } = route.query
    await router.replace({ query })
  }
  await nextTick()
  setupSectionObserver()
}, { immediate: true })
onBeforeUnmount(() => {
  sectionObserver?.disconnect()
  stopRightPanelResize()
})
</script>

<template>
  <div class="quote-collaboration-page">
    <nav class="quote-breadcrumb" aria-label="内部报价导航"><RouterLink :to="getQuoteRoute('/modules/sales-business/internal-quote-desk')"><ArrowLeft />报价首页</RouterLink><ChevronRight /><span>{{ quote.quoteNo }}</span><ChevronRight /><strong>{{ isWholeQuoteReview ? '整单协作' : '部门协作' }}</strong></nav>

    <header id="quote-page-overview" class="quote-collaboration-head">
      <div class="quote-head-product">
        <div class="quote-head-image" :class="{ empty: !currentProductImageUrl }">
          <button v-if="currentProductImageUrl" type="button" class="quote-head-image-preview" :aria-label="`预览 ${quote.productName} 产品主图`" aria-haspopup="dialog" :aria-expanded="productImagePreviewOpen" @click="productImagePreviewOpen = true">
            <img :src="currentProductImageUrl" :alt="`${quote.productName} 产品主图`">
            <span><Maximize2 />点击预览</span>
          </button>
          <span v-else><FileImage /><b>产品主图</b></span>
          <label v-if="canManageParticipation && !['final_pending', 'released', 'exported', 'archived'].includes(quote.status)" :title="quoteStore.fileBusy ? '主图上传中' : currentProductImageUrl ? '更新产品主图' : '上传产品主图'">
            <input type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" :disabled="quoteStore.fileBusy" @change="uploadCurrentProductImage">
            <RefreshCw v-if="quoteStore.fileBusy" class="spinning" />
            <FileImage v-else />
            <span class="sr-only">{{ quoteStore.fileBusy ? '主图上传中' : currentProductImageUrl ? '更新产品主图' : '上传产品主图' }}</span>
          </label>
        </div>
        <div class="quote-head-main"><div class="quote-title-row"><h1>{{ quote.productName }}</h1><span>{{ collaborationStatusLabel }}</span><b v-if="isMultiProduct">第 {{ quote.batchPosition }}/{{ quote.batchSize }} 款</b><em v-if="baselineDifferenceLabel" class="quote-baseline-comparison" :class="{ same: !currentBatchProduct?.differsFromBaseline }">{{ baselineDifferenceLabel }}</em></div><p>{{ quote.batchQuoteNo || quote.quoteNo }} · {{ quote.customer }} · {{ quote.versionLabel }}</p><div class="quote-head-meta"><span><Building2 />{{ quote.factoryName }} / {{ quote.workshopName }}</span><span><CircleUserRound />{{ quote.initiatorDepartment === 'engineering' ? '工程部' : '业务部' }}发起 · {{ quote.initiatorName }}</span><span><CircleUserRound />{{ isWholeQuoteReview ? '整批审核人' : '全部分段审核' }} · {{ quote.businessOwner }}</span><span><CalendarDays />目标 {{ quote.targetDate }}</span></div></div>
      </div>
      <div class="quote-head-progress"><div><span>{{ isWholeQuoteReview ? '部门填写进度' : '参与分段进度' }}</span><strong>{{ completedCount }}/{{ participatingSections.length }}</strong></div><div class="quote-progress-bar"><span :style="{ width: `${progressPercent}%` }" /></div><button v-if="canEditMaterials" type="button" @click="openMaterialsDialog"><CircleDollarSign />本报价专用料价</button><button v-if="canEditHeader" type="button" @click="openHeaderDialog"><Pencil />修改报价资料</button><button v-if="canManageParticipation && manageableOptionalSections.length && (!isWholeQuoteReview || ['drafting', 'rejected'].includes(quote.status))" type="button" @click="toggleParticipationPanel"><UserPlus />添加、删除参与部门</button><button type="button" :disabled="quoteStore.detailLoading" @click="loadQuote"><RefreshCw />重新读取最新 revision</button></div>
    </header>

    <p v-if="isReadOnly" class="quote-readonly-banner"><Building2 aria-hidden="true" />{{ isForeignReadOnly ? '当前为跨厂只读视图；部门编辑、整单审核、参考同步及其他业务操作仅允许在所属厂区执行。' : '当前账号仅可查看该报价，没有可用的部门编辑、整单审核或参考同步权限。' }}</p>

    <section v-if="isWholeQuoteReview" class="quote-whole-review-panel" :class="quote.status">
      <div class="quote-whole-review-icon"><ShieldCheck v-if="['released', 'exported'].includes(quote.status)" /><AlertTriangle v-else-if="quote.status === 'rejected'" /><LockKeyhole v-else-if="quote.status === 'final_pending'" /><Send v-else /></div>
      <div class="quote-whole-review-copy"><span>{{ isMultiProduct ? '整批一次审核' : '整单审核' }}</span><h2>{{ collaborationStatusLabel }}</h2><p>{{ wholeReviewDescription }}</p><div><b>指定审核人：{{ quote.businessOwner }}</b><b v-if="isMultiProduct">产品数量：{{ batchProducts.length }} 款</b><b>当前款部门完成：{{ completedCount }}/{{ participatingSections.length }}</b><b>报价头 r{{ quote.headerRevision }}</b></div></div>
    </section>

    <div class="quote-snapshot-banner"><Layers3 /><span><strong>参考快照已冻结</strong>{{ quote.referenceSnapshotId }} · RMB→HKD {{ quote.fxRmbHkd.toFixed(2) }} · HKD→USD {{ quote.fxHkdUsd.toFixed(2) }}</span><em>同步最新参考表将产生新 revision，并使受影响审批失效</em><button v-if="canSyncReference" type="button" @click="syncPanelOpen = !syncPanelOpen">同步最新参考表</button></div>
    <section v-if="syncPanelOpen && canSyncReference" class="quote-sync-panel"><div><strong>同步最新参考表</strong><span>将重算已填写分段，并使受影响的审批、最终放行和 artifact 失效。</span></div><textarea v-model="syncReason" rows="2" placeholder="必须填写同步原因" /><button type="button" class="secondary" @click="syncPanelOpen = false">取消</button><button type="button" class="primary" :disabled="!syncReason.trim() || quoteStore.submitting || !canSyncReference" @click="syncReference">确认同步</button></section>
    <section v-if="participationPanelOpen" class="quote-participation-panel">
      <div class="quote-participation-copy"><UserPlus /><span><strong>添加、删除参与部门</strong><small>业务部、工程部和装配部固定参与；勾选可选部门表示参与，取消勾选表示移除。保存后会同步调整连续报价页、协作进度、成本汇总和最终放行。</small></span></div>
      <div class="quote-participation-options">
        <label v-for="section in manageableOptionalSections" :key="section.code" :class="{ active: selectedParticipation.includes(section.code) }">
          <input v-model="selectedParticipation" type="checkbox" :value="section.code" @change="participationRemovalConfirmOpen = false">
          <CheckCircle2 />
          <span>{{ section.label }}<small>{{ selectedParticipation.includes(section.code) ? '已参与' : '未参与' }}</small></span>
        </label>
      </div>
      <div class="quote-participation-actions"><button type="button" class="secondary" @click="toggleParticipationPanel">取消</button><button type="button" class="primary" :disabled="quoteStore.submitting" @click="saveParticipationChanges()">{{ quoteStore.submitting ? '保存中…' : '保存参与部门' }}</button></div>
      <div v-if="participationRemovalConfirmOpen" class="quote-participation-confirm" role="alert">
        <AlertTriangle />
        <span><strong>确认移除 {{ participationChanges.removals.map((section) => section.label).join('、') }}？</strong><small>这些部门当前填写内容和未保存修改将不再计入本报价；历史 revision 和审计记录仍会保留，以后仍可重新添加。</small></span>
        <button type="button" class="secondary" @click="participationRemovalConfirmOpen = false">返回选择</button>
        <button type="button" class="danger" :disabled="quoteStore.submitting" @click="saveParticipationChanges(true)">{{ quoteStore.submitting ? '保存中…' : '确认移除并保存' }}</button>
      </div>
    </section>

    <p v-if="message" class="quote-page-message success">{{ message }}</p><p v-if="errorMessage" class="quote-page-message error">{{ errorMessage }}</p><p v-if="quoteStore.errorMessage" class="quote-page-message error">{{ quoteStore.errorMessage }}</p>
    <p v-if="quoteStore.conflictMessage" class="quote-page-message conflict"><span>{{ quoteStore.conflictMessage }}</span><button type="button" @click="loadQuote">放弃本地表单并重新读取</button></p>

    <div class="quote-collaboration-grid" :class="{ 'whole-review-layout': isWholeQuoteReview }">
      <aside class="quote-edge-panel quote-edge-panel-left" aria-label="鼠标移入展开页面导航">
        <button type="button" class="quote-edge-handle" aria-label="展开页面导航" title="移入或聚焦后展开页面导航"><ChevronRight /><span>页面导航</span></button>
        <div class="quote-edge-panel-body quote-navigation-stack">
          <InternalQuoteSectionRail :sections="participatingSections" :active-code="activeSectionCode" :whole-quote-review="isWholeQuoteReview" :block-progress="sectionBlockProgress" :different-section-codes="baselineDifferentSections" @select="selectSection" @select-page="selectPageAnchor" />
        </div>
      </aside>
      <div v-if="isWholeQuoteReview" class="quote-continuous-sections" aria-label="整单连续报价内容">
        <section v-if="isMultiProduct" class="quote-component-product-level" :aria-label="isComponentPricing ? 'JustPlay 系列产品当前单款' : '系列产品当前单款'">
          <div><strong>系列产品 / 当前单款</strong><span>{{ isComponentPricing ? '先选择系列中的单款，再选择该单款下的配件。' : '在这里切换当前填写的系列单款。' }}</span></div>
          <InternalQuoteProductActions :products="batchProducts" :current-quote-id="quote.id" :can-manage="canManageParticipation" :copy-busy-quote-id="copyBusyQuoteId" @switch="switchProduct" @copy-baseline="copyBaselineToProduct" />
        </section>
        <InternalQuoteComponentScopePicker v-if="isComponentPricing" v-model="activePricingComponentId" :product-name="quote.productName" :components="pricingComponents" />
        <article v-for="section in participatingSections" :id="`quote-section-${section.code}`" :key="section.code" :ref="(node) => setSectionNode(section.code, node)" class="quote-continuous-section" :data-section-code="section.code">
          <InternalQuoteSectionEditor :ref="(instance) => setSectionEditorRef(section.code, instance)" :quote="quote" :section="section" :can-edit="canEditSection(section.code)" :can-review="false" :can-remove="canRemoveSection(section.code)" :active-pricing-component-id="activePricingComponentId" :differs-from-baseline="baselineDifferentSections.includes(section.code)" :difference-details="currentBatchProduct?.differentSectionDetails[section.code] ?? []" whole-quote-review @remove="removeParticipation" @block-progress="updateSectionBlockProgress" @preview-file="openDepartmentFile" />
        </article>
        <footer id="quote-page-actions" class="quote-whole-product-actions" aria-label="整单操作">
          <div class="quote-whole-product-actions-copy"><strong>整单操作</strong><span>在这里查看汇总、保存当前款、切换款号、复制基准款，以及提交或审核整单。</span><small>当前款：{{ quote.productName }} · 最后更新 {{ quote.updatedAt }}</small></div>
          <div class="quote-whole-product-actions-controls">
            <button type="button" class="quote-whole-product-save" title="保存当前款全部部门的修改" :disabled="wholeProductSaving || quoteStore.submitting" @click="saveWholeProductDraft"><Save />{{ wholeProductSaving ? '保存中…' : '保存' }}</button>
            <div class="quote-whole-review-actions quote-whole-product-workflow">
              <RouterLink :to="getQuoteRoute(`/modules/sales-business/internal-quote-desk/${quote.id}/summary`)"><BarChart3 />查看汇总与输出</RouterLink>
              <button v-if="!['final_pending', 'released', 'exported', 'archived'].includes(quote.status)" type="button" class="primary" :title="!canSubmitWholeReview ? '当前账号没有整单提交权限' : !batchReady ? '全部产品完成后可提交审核' : '提交审核'" :disabled="!canSubmitWholeReview || !batchReady || quoteStore.submitting" @click="submitWholeReview"><Send />{{ quoteStore.submitting ? '提交中…' : '提交审核' }}</button>
              <span v-if="!['final_pending', 'released', 'exported', 'archived'].includes(quote.status) && !canSubmitWholeReview">当前账号无提交权限</span>
              <span v-else-if="!['final_pending', 'released', 'exported', 'archived'].includes(quote.status) && !batchReady">全部产品完成后可提交</span>
              <template v-if="quote.status === 'final_pending' && canReviewWhole"><button type="button" class="reject" :disabled="quoteStore.submitting" @click="toggleWholeReject"><XCircle />退回整单</button><button type="button" class="primary" :disabled="quoteStore.submitting" @click="approveWholeReview"><ShieldCheck />整单审核通过</button></template>
              <span v-else-if="quote.status === 'final_pending'">等待指定审核人处理</span>
            </div>
          </div>
          <section v-if="wholeRejectOpen && canReviewWhole" class="quote-whole-reject-panel quote-whole-product-reject"><div><strong>退回整份报价</strong><span>退回原因会写入整单审核记录，确认后报价头和全部部门内容同时解锁。</span></div><textarea v-model="wholeRejectReason" rows="2" placeholder="必须填写整单退回原因" /><button type="button" @click="toggleWholeReject">取消</button><button type="button" class="primary" :disabled="!wholeRejectReason.trim() || quoteStore.submitting" @click="rejectWholeReview">确认退回整单</button></section>
        </footer>
      </div>
      <InternalQuoteSectionEditor v-else :ref="(instance) => setSectionEditorRef(activeSection.code, instance)" :quote="quote" :section="activeSection" :can-edit="canEditActive" :can-review="canReviewActive" :can-remove="canRemoveActive" :active-pricing-component-id="activePricingComponentId" :differs-from-baseline="baselineDifferentSections.includes(activeSection.code)" :difference-details="currentBatchProduct?.differentSectionDetails[activeSection.code] ?? []" @remove="removeParticipation" @block-progress="updateSectionBlockProgress" @preview-file="openDepartmentFile" />
      <aside class="quote-edge-panel quote-edge-panel-right" :class="{ open: rightPanelPinned, resizing: rightPanelResizing }" :style="{ width: `${rightPanelWidth}px` }" aria-label="鼠标移入展开报价与资料侧栏">
        <button type="button" class="quote-edge-handle" :aria-label="rightPanelPinned ? '收起报价与资料侧栏' : '展开报价与资料侧栏'" title="移入可临时展开；点击可固定或收起" @click="rightPanelPinned = !rightPanelPinned"><ChevronRight /><span>报价与资料</span></button>
        <button type="button" class="quote-edge-resizer" aria-label="拖动调整侧栏宽度" title="左右拖动调整侧栏宽度" @pointerdown="startRightPanelResize" />
        <div class="quote-edge-panel-body">
          <nav class="quote-side-mode-tabs" aria-label="报价侧栏功能">
            <button type="button" :class="{ active: rightPanelTab === 'quote' }" @click="rightPanelTab = 'quote'"><BarChart3 />报价</button>
            <button type="button" :class="{ active: rightPanelTab === 'files' }" @click="rightPanelTab = 'files'"><FileText />部门资料 <b>{{ activeSection.attachments.length }}</b></button>
            <button v-if="rightPanelPinned" type="button" class="collapse" aria-label="收起报价与资料侧栏" @click="rightPanelPinned = false"><XCircle /></button>
          </nav>
          <div class="quote-side-mode-content">
            <InternalQuoteActivityPanel v-if="rightPanelTab === 'quote'" :quote="quote" read-only :can-edit-fx="canEditFx" :can-edit-markup="canEditMarkup" :markup-blocked-reason="markupBlockedReason" :markup-message="markupMessage" :markup-error="markupError" :busy="quoteStore.submitting" @update-fx="updateReferenceFx" @update-markup="updateQuoteMarkup" />
            <InternalQuoteDepartmentFilesPanel v-else :quote-id="quote.id" :section-label="activeSection.label" :attachments="activeSection.attachments" :requested-attachment-id="requestedFileAttachmentId" @select="requestedFileAttachmentId = $event" @download="downloadDepartmentFile" />
          </div>
        </div>
      </aside>
    </div>
    <Teleport to="body">
      <div v-if="productImagePreviewOpen && currentProductImageUrl" class="quote-product-preview-backdrop" role="presentation" @click.self="productImagePreviewOpen = false">
        <section class="quote-product-preview-dialog" role="dialog" aria-modal="true" :aria-label="`${quote.productName} 产品主图预览`">
          <header><div><strong>{{ quote.productName }}</strong><span>产品主图预览</span></div><button type="button" aria-label="关闭产品主图预览" @click="productImagePreviewOpen = false"><XCircle /></button></header>
          <img :src="currentProductImageUrl" :alt="`${quote.productName} 产品主图大图预览`">
        </section>
      </div>
    </Teleport>
    <InternalQuoteHeaderDialog
      :open="headerDialogOpen"
      :quote="quote"
      :business-owners="headerBusinessOwners"
      :customers="headerCustomers"
      :busy="headerDialogBusy"
      :external-error="headerDialogError"
      @close="closeHeaderDialog"
      @confirm="saveHeader"
    />
    <InternalQuoteMaterialsDialog
      :open="materialsDialogOpen"
      :product-name="quote.productName"
      :snapshot="quote.referenceSnapshot"
      :busy="materialsDialogBusy"
      :external-error="materialsDialogError"
      @close="closeMaterialsDialog"
      @save="saveReferenceMaterials"
    />
  </div>
</template>

<style scoped>
.quote-collaboration-page{display:grid;gap:13px;padding-bottom:28px}.quote-breadcrumb{display:flex;align-items:center;gap:7px;color:#94a3b8;font-size:11px}.quote-breadcrumb a{display:inline-flex;align-items:center;gap:5px;color:#475569;font-weight:800}.quote-breadcrumb a:hover{color:#0f766e}.quote-breadcrumb svg{width:13px;height:13px}.quote-breadcrumb strong{color:#0f766e}.quote-collaboration-head{display:flex;align-items:center;justify-content:space-between;gap:20px;border:1px solid #dbe5ea;border-radius:14px;background:#fff;padding:18px;box-shadow:0 12px 28px rgb(15 23 42/.05)}.quote-head-product{display:flex;min-width:0;align-items:center;gap:16px}.quote-head-image{position:relative;display:grid;width:132px;height:98px;flex:0 0 132px;place-items:center;overflow:hidden;border:1px solid #cbd5e1;border-radius:12px;background:#f8fafc;box-shadow:0 7px 18px rgb(15 23 42/.08)}.quote-head-image-preview{position:absolute;inset:0;display:block;width:100%;height:100%;overflow:hidden;border:0;background:transparent;padding:0;cursor:zoom-in}.quote-head-image-preview img{width:100%;height:100%;object-fit:cover;transition:transform .18s ease}.quote-head-image-preview>span{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:4px;background:rgb(15 23 42/.48);color:#fff;font-size:9px;font-weight:900;opacity:0;transition:opacity .18s ease}.quote-head-image-preview>span svg{width:13px}.quote-head-image-preview:hover img,.quote-head-image-preview:focus-visible img{transform:scale(1.04)}.quote-head-image-preview:hover>span,.quote-head-image-preview:focus-visible>span{opacity:1}.quote-head-image>span{display:grid;place-items:center;gap:5px;color:#94a3b8}.quote-head-image>span svg{width:24px}.quote-head-image>span b{font-size:10px}.quote-head-image label{position:absolute;right:6px;bottom:6px;z-index:2;display:grid;width:28px;height:28px;place-items:center;border:1px solid rgb(255 255 255/.82);border-radius:8px;background:rgb(15 118 110/.92);padding:0;color:#fff;box-shadow:0 4px 12px rgb(15 23 42/.2);cursor:pointer}.quote-head-image label:hover{background:#0f766e}.quote-head-image label svg{width:13px}.quote-head-image label input{position:absolute;width:1px;height:1px;opacity:0}.quote-head-image label .spinning{animation:quote-product-image-spin .8s linear infinite}.quote-head-main{min-width:0}.quote-title-row{display:flex;flex-wrap:wrap;align-items:center;gap:8px}.quote-title-row h1{margin:0;color:#0f172a;font-size:24px;font-weight:950;letter-spacing:-.035em}.quote-title-row>span,.quote-title-row>b{border-radius:999px;background:#fef3c7;padding:5px 8px;color:#b45309;font-size:11px;font-weight:900}.quote-title-row>b{background:#ccfbf1;color:#0f766e}.quote-head-main>p{margin:6px 0 0;color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px}.quote-head-meta{display:flex;flex-wrap:wrap;gap:11px;margin-top:12px}.quote-head-meta span{display:flex;align-items:center;gap:5px;color:#475569;font-size:11px}.quote-head-meta svg{width:14px;color:#0d9488}.quote-head-progress{display:grid;width:min(330px,35%);gap:8px}.quote-head-progress>div:first-child{display:flex;align-items:end;justify-content:space-between}.quote-head-progress span{color:#64748b;font-size:11px}.quote-head-progress strong{color:#0f766e;font-size:18px}.quote-progress-bar{height:7px;overflow:hidden;border-radius:99px;background:#e2e8f0}.quote-progress-bar span{display:block;height:100%;border-radius:99px;background:#0d9488}.quote-head-progress a,.quote-head-progress button{display:inline-flex;align-items:center;justify-content:center;gap:6px;border:1px solid #99f6e4;border-radius:8px;background:#f0fdfa;padding:8px;color:#0f766e;font-size:11px;font-weight:900}.quote-head-progress a:hover,.quote-head-progress button:hover{background:#ccfbf1}.quote-head-progress a svg,.quote-head-progress button svg{width:14px}.quote-head-progress button:disabled{opacity:.45}.quote-readonly-banner{display:flex;align-items:center;gap:7px;margin:0;border:1px solid #99f6e4;border-radius:9px;background:#f0fdfa;padding:9px 11px;color:#0f766e;font-size:11px}.quote-readonly-banner svg{width:15px;flex:0 0 auto}
.quote-product-preview-backdrop{position:fixed;inset:0;z-index:180;display:grid;place-items:center;background:rgb(15 23 42/.76);padding:24px;backdrop-filter:blur(5px)}.quote-product-preview-dialog{display:grid;width:min(920px,92vw);max-height:90vh;overflow:hidden;border:1px solid rgb(255 255 255/.25);border-radius:16px;background:#fff;box-shadow:0 28px 80px rgb(0 0 0/.38)}.quote-product-preview-dialog header{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid #e2e8f0;padding:12px 15px}.quote-product-preview-dialog header>div{display:grid}.quote-product-preview-dialog header strong{color:#0f172a;font-size:14px}.quote-product-preview-dialog header span{margin-top:2px;color:#64748b;font-size:10px}.quote-product-preview-dialog header button{display:grid;width:32px;height:32px;place-items:center;border:1px solid #cbd5e1;border-radius:8px;background:#fff;color:#475569}.quote-product-preview-dialog header button svg{width:16px}.quote-product-preview-dialog>img{display:block;width:100%;max-height:calc(90vh - 58px);background:#f8fafc;object-fit:contain}
.quote-baseline-comparison{border-radius:999px;background:#ffedd5;padding:4px 8px;color:#c2410c;font-size:9px;font-style:normal;font-weight:950}.quote-baseline-comparison.same{background:#d1fae5;color:#047857}
@keyframes quote-product-image-spin{to{transform:rotate(360deg)}}
.quote-snapshot-banner{display:flex;align-items:center;gap:8px;border:1px solid #bae6fd;border-radius:10px;background:#f0f9ff;padding:9px 12px;color:#0369a1}.quote-snapshot-banner>svg{width:16px;flex:0 0 auto}.quote-snapshot-banner>span{display:flex;gap:7px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px}.quote-snapshot-banner strong{font-family:'Microsoft YaHei','PingFang SC',sans-serif}.quote-snapshot-banner em{margin-left:auto;color:#0284c7;font-size:11px;font-style:normal}.quote-snapshot-banner button{border:1px solid #7dd3fc;border-radius:7px;background:#fff;padding:6px 9px;color:#0369a1;font-size:11px;font-weight:900}.quote-sync-panel{display:grid;grid-template-columns:minmax(200px,1fr) minmax(260px,2fr) auto auto;align-items:center;gap:9px;border:1px solid #bae6fd;border-radius:10px;background:#f0f9ff;padding:10px 12px}.quote-sync-panel>div{display:grid}.quote-sync-panel strong{color:#075985;font-size:12px}.quote-sync-panel span{margin-top:2px;color:#0369a1;font-size:11px}.quote-sync-panel textarea{border:1px solid #7dd3fc;border-radius:7px;padding:7px 9px;font-size:13px;resize:none}.quote-sync-panel button{height:32px;border-radius:7px;padding:0 10px;font-size:11px;font-weight:900}.quote-sync-panel .secondary{border:1px solid #7dd3fc;background:#fff;color:#0369a1}.quote-sync-panel .primary{border:1px solid #0369a1;background:#0369a1;color:#fff}.quote-page-message{margin:0;border-radius:8px;padding:8px 11px;font-size:11px}.quote-page-message.success{border:1px solid #a7f3d0;background:#ecfdf5;color:#047857}.quote-page-message.error{border:1px solid #fecaca;background:#fef2f2;color:#b91c1c}.quote-page-message.conflict{display:flex;align-items:center;justify-content:space-between;gap:10px;border:1px solid #fdba74;background:#fff7ed;color:#9a3412}.quote-page-message.conflict button{border:1px solid #fb923c;border-radius:7px;background:#fff;padding:6px 9px;color:#9a3412;font-size:11px;font-weight:900}.quote-collaboration-grid{display:grid;grid-template-columns:190px minmax(0,1fr) clamp(290px,18vw,320px);align-items:start;gap:11px}.quote-collaboration-grid.focus-entry-mode{grid-template-columns:minmax(0,1fr)}.quote-collaboration-grid.focus-entry-mode>:first-child,.quote-collaboration-grid.focus-entry-mode>:last-child{display:none}.focus-entry-toggle{border-color:#0f766e!important;background:#0f766e!important;color:#fff!important}.focus-entry-toggle[aria-pressed="true"]{border-color:#99f6e4!important;background:#f0fdfa!important;color:#0f766e!important}
.quote-navigation-stack{display:grid;gap:10px;min-width:0}
.quote-whole-review-panel{display:grid;grid-template-columns:48px minmax(0,1fr) auto;align-items:center;gap:14px;border:1px solid #99f6e4;border-radius:14px;background:linear-gradient(110deg,#f0fdfa,#ecfeff);padding:15px 17px;box-shadow:0 10px 24px rgb(15 118 110/.08)}.quote-whole-review-panel.final_pending{border-color:#fcd34d;background:linear-gradient(110deg,#fffbeb,#fff)}.quote-whole-review-panel.rejected{border-color:#fca5a5;background:linear-gradient(110deg,#fef2f2,#fff)}.quote-whole-review-panel.released,.quote-whole-review-panel.exported{border-color:#6ee7b7;background:linear-gradient(110deg,#ecfdf5,#fff)}.quote-whole-review-icon{display:grid;width:46px;height:46px;place-items:center;border-radius:13px;background:#0f766e;color:#fff}.quote-whole-review-panel.final_pending .quote-whole-review-icon{background:#d97706}.quote-whole-review-panel.rejected .quote-whole-review-icon{background:#dc2626}.quote-whole-review-panel.released .quote-whole-review-icon,.quote-whole-review-panel.exported .quote-whole-review-icon{background:#059669}.quote-whole-review-icon svg{width:23px}.quote-whole-review-copy{display:grid}.quote-whole-review-copy>span{color:#0f766e;font-size:10px;font-weight:950;letter-spacing:.08em}.quote-whole-review-copy h2{margin:2px 0 0;color:#0f172a;font-size:18px}.quote-whole-review-copy p{margin:5px 0 0;color:#64748b;font-size:11px;line-height:1.55}.quote-whole-review-copy>div{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}.quote-whole-review-copy b{border-radius:999px;background:rgb(255 255 255/.8);padding:4px 7px;color:#475569;font-size:10px}.quote-whole-review-actions{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:7px;max-width:340px}.quote-whole-review-actions button,.quote-whole-review-actions a{display:inline-flex;min-height:36px;align-items:center;justify-content:center;gap:6px;border:1px solid #0f766e;border-radius:9px;background:#fff;padding:0 12px;color:#0f766e;font-size:11px;font-weight:950}.quote-whole-review-actions button.primary{background:#0f766e;color:#fff}.quote-whole-review-actions button.reject{border-color:#fca5a5;color:#dc2626}.quote-whole-review-actions button:disabled{cursor:not-allowed;border-color:#cbd5e1;background:#e2e8f0;color:#94a3b8}.quote-whole-review-actions svg{width:15px}.quote-whole-review-actions>span{color:#92400e;font-size:11px;font-weight:900}.quote-whole-reject-panel{display:grid;grid-template-columns:minmax(220px,1fr) minmax(300px,2fr) auto auto;align-items:center;gap:9px;border:1px solid #fecaca;border-radius:11px;background:#fef2f2;padding:11px 13px}.quote-whole-reject-panel>div{display:grid}.quote-whole-reject-panel strong{color:#991b1b;font-size:12px}.quote-whole-reject-panel span{margin-top:3px;color:#b91c1c;font-size:10px}.quote-whole-reject-panel textarea{border:1px solid #fca5a5;border-radius:7px;padding:7px 9px;font-size:13px;resize:none}.quote-whole-reject-panel button{height:33px;border:1px solid #fca5a5;border-radius:7px;background:#fff;padding:0 10px;color:#991b1b;font-size:11px;font-weight:900}.quote-whole-reject-panel button.primary{border-color:#b91c1c;background:#b91c1c;color:#fff}.quote-continuous-sections{display:grid;min-width:0;gap:16px}.quote-continuous-section{min-width:0;scroll-margin-top:92px}.quote-continuous-section :deep(.quote-section-editor){box-shadow:0 10px 24px rgb(15 23 42/.05)}.quote-whole-product-actions{display:flex;min-width:0;align-items:center;justify-content:space-between;gap:16px;border:1px solid #5eead4;border-radius:13px;background:linear-gradient(110deg,#f0fdfa,#fff);padding:14px 15px;box-shadow:0 10px 24px rgb(15 118 110/.08)}.quote-whole-product-actions-copy{display:grid;min-width:190px}.quote-whole-product-actions-copy strong{color:#134e4a;font-size:14px}.quote-whole-product-actions-copy span{margin-top:3px;color:#47716d;font-size:11px}.quote-whole-product-actions-copy small{margin-top:6px;color:#94a3b8;font-size:10px}.quote-whole-product-actions-controls{display:flex;min-width:0;align-items:center;justify-content:flex-end;gap:8px}.quote-whole-product-save{display:inline-flex;height:36px;flex:0 0 auto;align-items:center;justify-content:center;gap:5px;border:1px solid #0f766e;border-radius:8px;background:#0f766e;padding:0 12px;color:#fff;font-size:11px;font-weight:950}.quote-whole-product-save svg{width:14px}.quote-whole-product-save:disabled{cursor:wait;opacity:.5}
.quote-component-product-level{display:flex;align-items:center;justify-content:space-between;gap:14px;border:1px solid #cbd5e1;border-radius:12px;background:#fff;padding:11px 13px;box-shadow:0 8px 20px rgb(15 23 42/.045)}.quote-component-product-level>div:first-child{display:grid;gap:3px}.quote-component-product-level strong{color:#334155;font-size:12px}.quote-component-product-level span{color:#64748b;font-size:10px}
.quote-participation-panel{display:grid;grid-template-columns:minmax(240px,1.2fr) minmax(320px,2fr) auto;align-items:center;gap:14px;border:1px solid #99f6e4;border-radius:12px;background:#f0fdfa;padding:13px 14px;box-shadow:0 10px 22px rgb(15 118 110/.07)}.quote-participation-copy{display:flex;align-items:flex-start;gap:9px}.quote-participation-copy>svg{width:19px;flex:0 0 auto;color:#0f766e}.quote-participation-copy span{display:grid}.quote-participation-copy strong{color:#134e4a;font-size:13px}.quote-participation-copy small{margin-top:3px;color:#47716d;font-size:11px;line-height:1.45}.quote-participation-options{display:flex;flex-wrap:wrap;gap:7px}.quote-participation-options label{position:relative;display:inline-flex;align-items:center;gap:5px;border:1px solid #bae6df;border-radius:999px;background:#fff;padding:7px 10px;color:#475569;font-size:12px;font-weight:900;cursor:pointer;transition:border-color .18s ease,background-color .18s ease,color .18s ease,transform .18s ease}.quote-participation-options label:hover{border-color:#2dd4bf;transform:translateY(-1px)}.quote-participation-options label.active{border-color:#0d9488;background:#ccfbf1;color:#0f766e}.quote-participation-options input{position:absolute;opacity:0}.quote-participation-options svg{width:14px;height:14px;color:#cbd5e1}.quote-participation-options label.active svg{color:#0f766e}.quote-participation-options label>span{display:grid;line-height:1.1}.quote-participation-options label>span small{margin-top:2px;color:#94a3b8;font-size:9px;font-weight:800}.quote-participation-options label.active>span small{color:#0f766e}.quote-participation-actions{display:flex;gap:7px}.quote-participation-actions button{height:34px;border-radius:8px;padding:0 11px;font-size:12px;font-weight:900}.quote-participation-actions .secondary{border:1px solid #99f6e4;background:#fff;color:#0f766e}.quote-participation-actions .primary{border:1px solid #0f766e;background:#0f766e;color:#fff}.quote-participation-actions .primary:disabled{opacity:.45}.quote-participation-confirm{grid-column:1/-1;display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;align-items:center;gap:9px;border:1px solid #fca5a5;border-radius:9px;background:#fff7ed;padding:9px 10px;color:#991b1b}.quote-participation-confirm>svg{width:18px}.quote-participation-confirm>span{display:grid}.quote-participation-confirm strong{font-size:12px}.quote-participation-confirm small{margin-top:2px;color:#b45309;font-size:10px;line-height:1.4}.quote-participation-confirm button{height:32px;border-radius:7px;padding:0 10px;font-size:11px;font-weight:900}.quote-participation-confirm .secondary{border:1px solid #fdba74;background:#fff;color:#9a3412}.quote-participation-confirm .danger{border:1px solid #b91c1c;background:#b91c1c;color:#fff}.quote-participation-confirm button:disabled{opacity:.45}
@media(max-width:1280px){.quote-collaboration-grid{grid-template-columns:190px minmax(0,1fr)}.quote-collaboration-grid>*:last-child{grid-column:1/-1}.quote-participation-panel{grid-template-columns:1fr 1.6fr}.quote-participation-actions{grid-column:1/-1;justify-content:flex-end}.quote-whole-review-panel{grid-template-columns:48px minmax(0,1fr)}.quote-whole-review-actions{grid-column:1/-1;max-width:none;justify-content:flex-end}.quote-whole-product-actions{align-items:stretch;flex-direction:column}.quote-whole-product-actions-controls{justify-content:flex-start}}@media(max-width:980px){.quote-collaboration-grid{grid-template-columns:1fr}.quote-collaboration-grid>*:last-child{grid-column:auto}.quote-collaboration-head{align-items:stretch;flex-direction:column}.quote-head-progress{width:100%}.quote-snapshot-banner{align-items:flex-start;flex-wrap:wrap}.quote-sync-panel,.quote-participation-panel,.quote-whole-reject-panel{grid-template-columns:1fr}.quote-snapshot-banner em{width:100%;margin-left:24px}.quote-participation-actions{grid-column:auto}.quote-whole-review-actions{justify-content:flex-start}.quote-whole-product-actions-controls{align-items:stretch;flex-direction:column}.quote-whole-product-save{width:100%}}@media(max-width:600px){.focus-entry-float{right:12px;bottom:14px;width:36px;height:36px;border-radius:10px}.focus-entry-float::after{right:44px}.quote-whole-review-panel{grid-template-columns:1fr}.quote-whole-review-icon{width:40px;height:40px}.quote-whole-review-actions>*{width:100%}}

/* The quote sheet is always full width; auxiliary panels live on the viewport edges. */
.quote-collaboration-grid{grid-template-columns:minmax(0,1fr);min-width:0;gap:0}
.quote-edge-panel{position:fixed;top:72px;bottom:18px;z-index:90;display:flex;pointer-events:none;transition:transform .22s ease}
.quote-edge-panel-left{left:0;width:min(230px,calc(100vw - 24px));transform:translateX(-100%)}
.quote-edge-panel-right{right:0;max-width:calc(100vw - 24px);transform:translateX(100%)}
.quote-edge-panel:hover,.quote-edge-panel:focus-within,.quote-edge-panel.open,.quote-edge-panel.resizing{transform:translateX(0)}
.quote-edge-panel-body{width:100%;height:100%;overflow:auto;border:1px solid #cbd5e1;background:rgb(248 250 252/.98);padding:8px;pointer-events:none;box-shadow:0 18px 42px rgb(15 23 42/.2);backdrop-filter:blur(12px)}
.quote-edge-panel:hover .quote-edge-panel-body,.quote-edge-panel:focus-within .quote-edge-panel-body{pointer-events:auto}
.quote-edge-panel-left .quote-edge-panel-body{border-radius:0 14px 14px 0}
.quote-edge-panel-right .quote-edge-panel-body{border-radius:14px 0 0 14px}
.quote-edge-panel-right .quote-edge-panel-body{display:grid;min-width:0;overflow:hidden;grid-template-rows:auto minmax(0,1fr)}
.quote-edge-resizer{position:absolute;z-index:4;top:0;bottom:0;left:-5px;width:10px;border:0;background:transparent;pointer-events:auto;cursor:ew-resize}.quote-edge-resizer:hover,.quote-edge-panel.resizing .quote-edge-resizer{background:rgb(20 184 166/.28)}
.quote-side-mode-tabs{display:flex;align-items:center;gap:5px;border-bottom:1px solid #dbe5ea;background:#fff;padding:5px}.quote-side-mode-tabs button{display:inline-flex;height:31px;align-items:center;justify-content:center;gap:5px;border:1px solid transparent;border-radius:7px;background:#fff;padding:0 8px;color:#64748b;font-size:10px;font-weight:900}.quote-side-mode-tabs button svg{width:13px}.quote-side-mode-tabs button b{display:grid;min-width:18px;height:18px;place-items:center;border-radius:999px;background:#e2e8f0;color:#475569;font-size:9px}.quote-side-mode-tabs button.active{border-color:#99f6e4;background:#f0fdfa;color:#0f766e}.quote-side-mode-tabs button.active b{background:#0f766e;color:#fff}.quote-side-mode-tabs button.collapse{width:31px;margin-left:auto;padding:0}.quote-side-mode-content{min-width:0;min-height:0;overflow:auto}
.quote-edge-handle{position:absolute;top:24%;z-index:2;display:grid;width:20px;min-height:108px;place-items:center;gap:5px;border:1px solid #5eead4;background:rgb(15 118 110/.96);padding:8px 2px;color:#fff;pointer-events:auto;box-shadow:0 8px 20px rgb(15 23 42/.22);cursor:pointer}
.quote-edge-panel-left .quote-edge-handle{right:-20px;border-left:0;border-radius:0 9px 9px 0}
.quote-edge-panel-right .quote-edge-handle{left:-20px;border-right:0;border-radius:9px 0 0 9px}
.quote-edge-panel-right .quote-edge-handle svg{transform:rotate(180deg)}
.quote-edge-handle svg{width:13px;height:13px}
.quote-edge-handle span{font-size:9px;font-weight:950;letter-spacing:.08em;line-height:1.15;writing-mode:vertical-rl}
.quote-edge-handle:focus-visible{outline:3px solid rgb(45 212 191/.3);outline-offset:2px}
.quote-edge-panel :deep(.quote-section-rail),.quote-edge-panel :deep(.quote-activity-panel){position:static;top:auto;max-height:none;box-shadow:none}
.quote-edge-panel-left :deep(.quote-section-rail>header),.quote-edge-panel-left :deep(.quote-section-rail>footer){display:flex}
.quote-edge-panel-left :deep(.quote-section-rail nav){display:grid;min-width:0}
.quote-edge-panel-left :deep(.quote-section-rail nav button){min-width:0}
.quote-edge-panel-right :deep(.quote-activity-body){max-height:calc(100vh - 142px)}
.quote-collaboration-grid :deep(.payload-table-scroll),.quote-collaboration-grid :deep(.snapshot-table-scroll){overflow:visible}
.quote-collaboration-grid :deep(.payload-table-scroll table),.quote-collaboration-grid :deep(.snapshot-table-scroll table),.quote-collaboration-grid :deep(.calculation-snapshot table){width:100%;min-width:0!important;table-layout:fixed}
.quote-collaboration-grid :deep(.payload-table-scroll th),.quote-collaboration-grid :deep(.payload-table-scroll td),.quote-collaboration-grid :deep(.snapshot-table-scroll th),.quote-collaboration-grid :deep(.snapshot-table-scroll td){width:auto!important;min-width:0!important;padding:5px 4px;white-space:normal;overflow-wrap:anywhere}
.quote-collaboration-grid :deep(.payload-table-scroll input),.quote-collaboration-grid :deep(.payload-table-scroll select),.quote-collaboration-grid :deep(.payload-table-scroll textarea){min-width:0;padding-inline:5px;font-size:11px}
.quote-collaboration-grid :deep(.payload-table-scroll textarea){min-height:44px}
.quote-collaboration-grid :deep(.snapshot-cell){font-size:10px;white-space:normal}
.quote-collaboration-grid :deep(.row-number){width:28px!important}
.quote-collaboration-grid :deep(.icon){width:26px;min-height:28px;padding:0}
.quote-whole-product-actions{flex-wrap:wrap;scroll-margin-top:82px}
.quote-whole-product-actions-controls{flex:1;flex-wrap:wrap}
.quote-whole-product-actions .quote-whole-review-actions{max-width:none}
@media(max-width:900px){.quote-component-product-level{align-items:stretch;flex-direction:column}}
.quote-whole-product-workflow{align-items:center}
.quote-whole-product-reject{width:100%;flex:1 0 100%;box-sizing:border-box}
#quote-page-overview{scroll-margin-top:82px}
@media(max-width:600px){.quote-edge-panel{top:64px;bottom:10px}.quote-edge-panel-left{width:min(260px,calc(100vw - 20px))}.quote-edge-panel-right{width:min(340px,calc(100vw - 20px))}}
</style>

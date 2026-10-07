<script setup lang="ts">
import {
  Archive,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Clock3,
  Copy,
  Eye,
  Filter,
  PieChart,
  Plus,
  RotateCcw,
  Search,
  Settings2,
  ShieldCheck,
  TimerReset,
  Trash2,
  Users,
  XCircle,
} from '@lucide/vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import InternalQuoteCreateDialog from './InternalQuoteCreateDialog.vue'
import InternalQuoteBaselineDialog from './InternalQuoteBaselineDialog.vue'
import InternalQuoteComparisonDialog from './InternalQuoteComparisonDialog.vue'
import InternalQuoteCustomerDialog from './InternalQuoteCustomerDialog.vue'
import InternalQuoteStatusDonut from './InternalQuoteStatusDonut.vue'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { getFactoryScopedRoute, type FactoryContextId } from '@/data/enterpriseMock'
import { internalQuoteApi, type ApiInternalQuoteCustomer, type InternalQuoteDashboardPeriod, type InternalQuotePricingBaselineUpdateRequest } from '@/api/internalQuote'
import { isForeignFactory, isInternalQuoteReadOnly } from '@/lib/internalQuoteAccess'
import type { InternalQuote, InternalQuoteCreatePayload, InternalQuoteStatus } from '@/types/internalQuoteDesk'

const router = useRouter()
const quoteStore = useInternalQuoteDeskStore()
const appStore = useAppStore()
const authStore = useAuthStore()
const query = ref('')
const statusFilter = ref<'all' | InternalQuoteStatus>('all')
const customerFilter = ref('all')
const statsPeriod = ref<InternalQuoteDashboardPeriod>('month')
const createDialogOpen = ref(false)
const dialogMode = ref<'create' | 'clone'>('create')
const cloneSource = ref<InternalQuote>()
const dialogError = ref('')
const createDialogFactoryId = ref('')
const createDialogFactoryGeneration = ref(0)
const baselineDialogOpen = ref(false)
const baselineDialogError = ref('')
const baselineDialogFactoryId = ref('')
const baselineDialogFactoryGeneration = ref(0)
const customerDialogOpen = ref(false)
const customerDialogFactoryId = ref('')
const customerDialogFactoryGeneration = ref(0)
const deleteTarget = ref<InternalQuote>()
const deleteDialogError = ref('')
const deletingQuoteId = ref('')
const archiveTarget = ref<InternalQuote>()
const archiveReason = ref('')
const archiveDialogError = ref('')
const archivingQuoteId = ref('')
const comparisonQuotes = ref<InternalQuote[]>([])
const comparisonDialogOpen = ref(false)
const comparisonLoading = ref(false)
const comparisonError = ref('')
const comparisonLimit = 5
const activeFactory = computed(() => (
  appStore.activeFactory.id === 'group'
    ? appStore.activeProductionFactory
    : appStore.activeFactory
))
const activeFactoryId = computed(() => activeFactory.value?.id ?? 'huaxing')
const activeFactoryName = computed(() => activeFactory.value?.name ?? '华兴')
function getQuoteRoute(path: string, factoryId: string = activeFactory.value.id) {
  return getFactoryScopedRoute(path, factoryId as FactoryContextId)
}
quoteStore.activateFactoryContext(activeFactoryId.value)
const canViewPricingBaseline = computed(() => authStore.can('internal_quote:baseline_read', activeFactoryId.value, 'sales-business'))
const canManagePricingBaseline = computed(() => authStore.can('internal_quote:baseline_manage', activeFactoryId.value, 'sales-business'))
const canManageCustomers = computed(() => (
  authStore.can('internal_quote:customer_manage', activeFactoryId.value, 'sales-business')
  || authStore.can('internal_quote:customer_manage', activeFactoryId.value, 'engineering')
))
const initiatorDepartments = ['sales-business', 'engineering'] as const
const allowedInitiatorDepartments = computed(() => initiatorDepartments.filter((department) => (
  authStore.can('internal_quote:create', activeFactoryId.value, department)
)))
const canCreateCurrentFactory = computed(() => allowedInitiatorDepartments.value.length > 0)
const ownersReadyForCurrentFactory = computed(() => (
  !quoteStore.ownerLoading
  && quoteStore.businessOwnerFactoryId === activeFactoryId.value
))
const customersReadyForCurrentFactory = computed(() => (
  !quoteStore.customerLoading
  && quoteStore.customerFactoryId === activeFactoryId.value
))
const canOpenCreate = computed(() => (
  canCreateCurrentFactory.value
  && !quoteStore.listLoading
  && ownersReadyForCurrentFactory.value
  && customersReadyForCurrentFactory.value
  && quoteStore.factoryCustomers.length > 0
))
const isCurrentFactoryReadOnly = computed(() => isInternalQuoteReadOnly(authStore, activeFactoryId.value))
const isCurrentFactoryForeign = computed(() => isForeignFactory(authStore, activeFactoryId.value))
const createUnavailableMessage = computed(() => {
  if (isCurrentFactoryForeign.value) return '跨厂数据仅供查看，请切换回本厂后操作'
  if (canCreateCurrentFactory.value && !ownersReadyForCurrentFactory.value) return '正在读取当前厂区业务负责人'
  if (canCreateCurrentFactory.value && !customersReadyForCurrentFactory.value) return '正在读取当前厂区客户资料'
  if (canCreateCurrentFactory.value && !quoteStore.factoryCustomers.length) return '当前厂区暂无客户，请业务主管或工程主管先维护客户资料'
  return '当前账号没有新建内部报价权限'
})
const comparisonQuoteIds = computed(() => new Set(comparisonQuotes.value.map((quote) => quote.id)))
const comparisonButtonTitle = computed(() => comparisonQuotes.value.length >= 2
  ? `对比已选择的 ${comparisonQuotes.value.length} 张报价`
  : '至少选择 2 张报价后才能对比')

const periodOptions: Array<{ value: InternalQuoteDashboardPeriod; label: string; shortLabel: string }> = [
  { value: 'week', label: '本周统计', shortLabel: '周' },
  { value: 'month', label: '本月统计', shortLabel: '月' },
  { value: 'year', label: '本年统计', shortLabel: '年' },
]

const dashboard = computed(() => quoteStore.dashboard ?? {
  factory_id: activeFactoryId.value,
  period: statsPeriod.value,
  period_label: periodOptions.find((item) => item.value === statsPeriod.value)?.label.replace('统计', '') ?? '本月',
  period_start: '',
  period_end: '',
  totals: { total: 0, in_progress: 0, completed: 0, canceled: 0 },
  status_distribution: [
    { key: 'in_progress' as const, label: '进行中', count: 0, percentage: 0 },
    { key: 'completed' as const, label: '已完成', count: 0, percentage: 0 },
    { key: 'canceled' as const, label: '已取消', count: 0, percentage: 0 },
  ],
  customer_quote_counts: [],
  progress_items: [],
  customer_speed: [],
})

const statusColors = { in_progress: '#2563eb', completed: '#14b8a6', canceled: '#f87171' } as const
const statusRows = computed(() => dashboard.value.status_distribution.map((item) => ({
  ...item,
  color: statusColors[item.key],
})))
const customerCountMax = computed(() => Math.max(1, ...dashboard.value.customer_quote_counts.map((item) => item.count)))
const speedRange = computed(() => {
  const values = dashboard.value.customer_speed.map((item) => item.average_hours)
  return { min: values.length ? Math.min(...values) : 0, max: values.length ? Math.max(...values) : 0 }
})
const dashboardRange = computed(() => {
  if (!dashboard.value.period_start || !dashboard.value.period_end) return '等待服务端统计'
  return `${dashboard.value.period_start.slice(0, 10)} 至 ${dashboard.value.period_end.slice(0, 10)}`
})

function customerBarWidth(count: number) {
  return `${Math.max(3, count / customerCountMax.value * 100)}%`
}

function speedDotPosition(hours: number) {
  const { min, max } = speedRange.value
  if (max <= min) return '50%'
  return `${8 + (hours - min) / (max - min) * 84}%`
}

function durationLabel(hours: number) {
  return hours < 24 ? `${hours.toFixed(1)} 小时` : `${(hours / 24).toFixed(1)} 天`
}

const statusMeta: Record<InternalQuoteStatus, { label: string; tone: string }> = {
  drafting: { label: '协作草稿', tone: 'slate' },
  pending_review: { label: '待分段审核', tone: 'amber' },
  rejected: { label: '已退回', tone: 'red' },
  fully_approved: { label: '待最终提交', tone: 'teal' },
  final_pending: { label: '待最终放行', tone: 'blue' },
  released: { label: '已放行', tone: 'green' },
  exported: { label: '已导出', tone: 'green' },
  archived: { label: '已归档', tone: 'slate' },
}
function quoteStatusLabel(quote: InternalQuote) {
  if (quote.moduleVersion === 'v4') return quote.status === 'exported' ? '已输出并冻结' : quote.status === 'archived' ? '已归档' : '填写中 / 可直接输出'
  if (quote.moduleVersion !== 'v3') return statusMeta[quote.status].label
  return {
    drafting: '整单填写中',
    pending_review: '整单填写中',
    rejected: '整单已退回',
    fully_approved: '待整单提交',
    final_pending: '待整单审核',
    released: '整单审核通过',
    exported: '整单已输出',
    archived: '已归档',
  }[quote.status]
}

const managedCustomerNames = computed(() => quoteStore.factoryCustomers.map((customer) => customer.name))
const customers = computed(() => Array.from(new Set([
  ...managedCustomerNames.value,
  ...quoteStore.quoteListCustomers,
])).sort((left, right) => left.localeCompare(right, 'zh-CN')))
const pageStart = computed(() => quoteStore.quoteListTotal
  ? (quoteStore.quoteListPage - 1) * quoteStore.quoteListPageSize + 1
  : 0)
const pageEnd = computed(() => Math.min(
  quoteStore.quoteListPage * quoteStore.quoteListPageSize,
  quoteStore.quoteListTotal,
))

const kpis = computed(() => [
  { label: '总报价数', value: dashboard.value.totals.total, detail: `${dashboard.value.period_label}创建`, icon: ClipboardList, tone: 'blue' },
  { label: '进行中报价数', value: dashboard.value.totals.in_progress, detail: '含草稿、审核与退回补充', icon: Clock3, tone: 'amber' },
  { label: '已完成报价数', value: dashboard.value.totals.completed, detail: '最终放行或已导出', icon: CheckCircle2, tone: 'teal' },
  { label: '已取消报价数', value: dashboard.value.totals.canceled, detail: '已归档的取消报价', icon: XCircle, tone: 'red' },
])

function openCreate() {
  if (!canOpenCreate.value) return
  dialogMode.value = 'create'
  cloneSource.value = undefined
  dialogError.value = ''
  createDialogFactoryId.value = activeFactoryId.value
  createDialogFactoryGeneration.value = quoteStore.factoryContextGeneration
  createDialogOpen.value = true
}

function openClone(quote: InternalQuote) {
  if (!canCloneQuote(quote)) return
  dialogMode.value = 'clone'
  cloneSource.value = quote
  dialogError.value = ''
  createDialogFactoryId.value = activeFactoryId.value
  createDialogFactoryGeneration.value = quoteStore.factoryContextGeneration
  createDialogOpen.value = true
}

function closeCreateDialog() {
  createDialogOpen.value = false
  cloneSource.value = undefined
  createDialogFactoryId.value = ''
  createDialogFactoryGeneration.value = 0
}

function cloneUnavailableMessage(quote: InternalQuote) {
  return isForeignFactory(authStore, quote.factoryId)
    ? '跨厂报价仅供查看，不能复制'
    : '当前账号没有复制内部报价权限'
}

function canCloneQuote(quote: InternalQuote) {
  return quote.factoryId === activeFactoryId.value
    && ownersReadyForCurrentFactory.value
    && ['sales-business', 'engineering'].some((department) => (
    authStore.can('internal_quote:clone', quote.factoryId, department)
    ))
}

async function handleConfirm(payload: InternalQuoteCreatePayload) {
  const requestedFactoryId = createDialogFactoryId.value
  const requestedFactoryGeneration = createDialogFactoryGeneration.value
  if (
    !createDialogOpen.value
    || !requestedFactoryId
    || requestedFactoryId !== activeFactoryId.value
    || !quoteStore.isFactoryContextCurrent(requestedFactoryId, requestedFactoryGeneration)
  ) return

  dialogError.value = ''
  if (dialogMode.value === 'clone' && cloneSource.value && !canCloneQuote(cloneSource.value)) {
    dialogError.value = `${cloneUnavailableMessage(cloneSource.value)}。`
    return
  }
  if (dialogMode.value === 'create' && !canOpenCreate.value) {
    dialogError.value = `${createUnavailableMessage.value}。`
    return
  }
  const requestedMode = dialogMode.value
  const requestedCloneSource = cloneSource.value
  try {
    const quote = requestedMode === 'clone' && requestedCloneSource
      ? await quoteStore.cloneQuote(requestedCloneSource.id, payload, requestedFactoryId)
      : await quoteStore.createQuote(payload, requestedFactoryId)
    if (
      quote.factoryId !== requestedFactoryId
      || !quoteStore.isFactoryContextCurrent(requestedFactoryId, requestedFactoryGeneration)
    ) return

    closeCreateDialog()
    void router.push(getQuoteRoute(
      `/modules/sales-business/internal-quote-desk/${quote.id}/collaboration`,
      quote.factoryId,
    ))
  } catch (error) {
    if (
      createDialogOpen.value
      && createDialogFactoryId.value === requestedFactoryId
      && quoteStore.isFactoryContextCurrent(requestedFactoryId, requestedFactoryGeneration)
    ) {
      dialogError.value = getApiErrorMessage(error)
    }
  }
}

function openQuote(quote: InternalQuote) {
  const target = ['fully_approved', 'final_pending', 'released', 'exported'].includes(quote.status) ? 'summary' : 'collaboration'
  void router.push(getQuoteRoute(`/modules/sales-business/internal-quote-desk/${quote.id}/${target}`))
}

function isQuoteSelectedForComparison(quote: InternalQuote) {
  return comparisonQuoteIds.value.has(quote.id)
}

function comparisonSelectionDisabled(quote: InternalQuote) {
  return !isQuoteSelectedForComparison(quote) && comparisonQuotes.value.length >= comparisonLimit
}

function toggleQuoteComparison(quote: InternalQuote) {
  if (quote.factoryId !== activeFactoryId.value) return
  if (isQuoteSelectedForComparison(quote)) {
    comparisonQuotes.value = comparisonQuotes.value.filter((item) => item.id !== quote.id)
    if (comparisonQuotes.value.length < 2) comparisonDialogOpen.value = false
    return
  }
  if (comparisonQuotes.value.length >= comparisonLimit) return
  comparisonQuotes.value = [...comparisonQuotes.value, quote]
}

function clearQuoteComparison() {
  comparisonDialogOpen.value = false
  comparisonQuotes.value = []
}

async function openQuoteComparison() {
  if (comparisonQuotes.value.length < 2) return
  const requestedFactoryId = activeFactoryId.value
  const requestedGeneration = quoteStore.factoryContextGeneration
  const quoteIds = comparisonQuotes.value.map((quote) => quote.id)
  comparisonLoading.value = true
  comparisonError.value = ''
  try {
    const refreshed = await Promise.all(quoteIds.map((quoteId) => quoteStore.loadQuoteForComparison(quoteId)))
    if (!quoteStore.isFactoryContextCurrent(requestedFactoryId, requestedGeneration)) return
    if (refreshed.some((quote) => quote.factoryId !== requestedFactoryId)) {
      throw new Error('所选报价不属于当前厂区，请重新选择。')
    }
    comparisonQuotes.value = refreshed
    comparisonDialogOpen.value = true
  } catch (error) {
    if (quoteStore.isFactoryContextCurrent(requestedFactoryId, requestedGeneration)) {
      comparisonError.value = `报价对比读取失败：${getApiErrorMessage(error)}`
    }
  } finally {
    comparisonLoading.value = false
  }
}

function closeQuoteComparison() {
  comparisonDialogOpen.value = false
}

function approvedCount(quote: InternalQuote) {
  return quote.sections.filter((section) => section.isRequired && ['approved', 'not_applicable'].includes(section.status)).length
}

async function openPricingBaseline() {
  const requestedFactoryId = activeFactoryId.value
  const requestedFactoryGeneration = quoteStore.factoryContextGeneration
  baselineDialogFactoryId.value = requestedFactoryId
  baselineDialogFactoryGeneration.value = requestedFactoryGeneration
  baselineDialogOpen.value = true
  baselineDialogError.value = ''
  try {
    await quoteStore.loadPricingBaseline(requestedFactoryId, `${requestedFactoryId}-workshop`)
  } catch (error) {
    if (
      baselineDialogOpen.value
      && baselineDialogFactoryId.value === requestedFactoryId
      && quoteStore.isFactoryContextCurrent(requestedFactoryId, requestedFactoryGeneration)
    ) {
      baselineDialogError.value = getApiErrorMessage(error)
    }
  }
}

async function savePricingBaseline(payload: InternalQuotePricingBaselineUpdateRequest) {
  const requestedFactoryId = baselineDialogFactoryId.value
  const requestedFactoryGeneration = baselineDialogFactoryGeneration.value
  if (
    !baselineDialogOpen.value
    || !requestedFactoryId
    || requestedFactoryId !== activeFactoryId.value
    || !quoteStore.isFactoryContextCurrent(requestedFactoryId, requestedFactoryGeneration)
  ) return

  baselineDialogError.value = ''
  try {
    await quoteStore.updatePricingBaseline(requestedFactoryId, `${requestedFactoryId}-workshop`, payload)
    if (!quoteStore.isFactoryContextCurrent(requestedFactoryId, requestedFactoryGeneration)) return
    closePricingBaseline()
  } catch (error) {
    if (
      baselineDialogOpen.value
      && baselineDialogFactoryId.value === requestedFactoryId
      && quoteStore.isFactoryContextCurrent(requestedFactoryId, requestedFactoryGeneration)
    ) {
      baselineDialogError.value = getApiErrorMessage(error)
    }
  }
}

function closePricingBaseline() {
  baselineDialogOpen.value = false
  baselineDialogFactoryId.value = ''
  baselineDialogFactoryGeneration.value = 0
  baselineDialogError.value = ''
  quoteStore.clearPricingBaseline()
}

function canDeleteQuote(quote: InternalQuote) {
  if (quote.factoryId !== activeFactoryId.value || isForeignFactory(authStore, quote.factoryId)) return false
  return quote.createdById === authStore.currentUser?.id
    || authStore.can('internal_quote:archive', quote.factoryId, 'sales-business')
}

function deleteIsProtected(quote: InternalQuote) {
  return Boolean(quote.deleteBlockReason) || ['released', 'exported'].includes(quote.status)
    || quote.finalReleaseStatus === 'approved'
}

function deleteButtonTitle(quote: InternalQuote) {
  return quote.deleteBlockReason || (deleteIsProtected(quote)
    ? '已放行、已导出或已交接的报价不能删除，请使用归档'
    : '删除内部报价')
}

function canArchiveQuote(quote: InternalQuote) {
  return quote.factoryId === activeFactoryId.value
    && quote.status !== 'archived'
    && !isForeignFactory(authStore, quote.factoryId)
    && authStore.can('internal_quote:archive', quote.factoryId, 'sales-business')
}

function openArchiveDialog(quote: InternalQuote) {
  if (!canArchiveQuote(quote)) return
  archiveTarget.value = quote
  archiveReason.value = ''
  archiveDialogError.value = ''
}

function closeArchiveDialog() {
  if (archivingQuoteId.value) return
  archiveTarget.value = undefined
  archiveReason.value = ''
  archiveDialogError.value = ''
}

function resetArchiveDialog() {
  archiveTarget.value = undefined
  archiveReason.value = ''
  archiveDialogError.value = ''
}

async function confirmArchiveQuote() {
  const quote = archiveTarget.value
  const reason = archiveReason.value.trim()
  if (!quote || !canArchiveQuote(quote)) return
  if (!reason) {
    archiveDialogError.value = '请填写归档原因。'
    return
  }
  const requestedFactoryId = quote.factoryId
  const requestedGeneration = quoteStore.factoryContextGeneration
  archiveDialogError.value = ''
  archivingQuoteId.value = quote.id
  try {
    await quoteStore.archiveQuote(quote.id, quote.headerRevision, reason)
    if (!quoteStore.isFactoryContextCurrent(requestedFactoryId, requestedGeneration)) return
    comparisonQuotes.value = comparisonQuotes.value.filter((item) => item.id !== quote.id)
    if (comparisonQuotes.value.length < 2) comparisonDialogOpen.value = false
    resetArchiveDialog()
    await Promise.all([
      loadQuotePage(quoteStore.quoteListPage, requestedFactoryId),
      quoteStore.loadDashboard(requestedFactoryId, statsPeriod.value),
    ])
  } catch (error) {
    if (
      archiveTarget.value?.id === quote.id
      && quoteStore.isFactoryContextCurrent(requestedFactoryId, requestedGeneration)
    ) archiveDialogError.value = getApiErrorMessage(error)
  } finally {
    if (archivingQuoteId.value === quote.id) archivingQuoteId.value = ''
  }
}

function openDeleteDialog(quote: InternalQuote) {
  if (!canDeleteQuote(quote) || deleteIsProtected(quote)) return
  deleteTarget.value = quote
  deleteDialogError.value = ''
}

function closeDeleteDialog() {
  if (deletingQuoteId.value) return
  deleteTarget.value = undefined
  deleteDialogError.value = ''
}

function resetDeleteDialog() {
  deleteTarget.value = undefined
  deleteDialogError.value = ''
}

async function confirmDeleteQuote() {
  const quote = deleteTarget.value
  if (!quote || !canDeleteQuote(quote) || deleteIsProtected(quote)) return
  const requestedFactoryId = quote.factoryId
  const requestedGeneration = quoteStore.factoryContextGeneration
  deleteDialogError.value = ''
  deletingQuoteId.value = quote.id
  try {
    await internalQuoteApi.deleteQuote(quote.id, quote.headerRevision)
    if (!quoteStore.isFactoryContextCurrent(requestedFactoryId, requestedGeneration)) return
    const nextPage = quoteStore.quotes.length > 1 || quoteStore.quoteListPage <= 1
      ? quoteStore.quoteListPage
      : quoteStore.quoteListPage - 1
    comparisonQuotes.value = comparisonQuotes.value.filter((item) => item.id !== quote.id)
    if (comparisonQuotes.value.length < 2) comparisonDialogOpen.value = false
    resetDeleteDialog()
    await Promise.all([
      loadQuotePage(nextPage, requestedFactoryId),
      quoteStore.loadDashboard(requestedFactoryId, statsPeriod.value),
    ])
  } catch (error) {
    if (
      deleteTarget.value?.id === quote.id
      && quoteStore.isFactoryContextCurrent(requestedFactoryId, requestedGeneration)
    ) {
      deleteDialogError.value = getApiErrorMessage(error)
    }
  } finally {
    if (deletingQuoteId.value === quote.id) deletingQuoteId.value = ''
  }
}

function openCustomerDialog() {
  if (!canManageCustomers.value) return
  customerDialogFactoryId.value = activeFactoryId.value
  customerDialogFactoryGeneration.value = quoteStore.factoryContextGeneration
  customerDialogOpen.value = true
}

function closeCustomerDialog() {
  customerDialogOpen.value = false
  customerDialogFactoryId.value = ''
  customerDialogFactoryGeneration.value = 0
  quoteStore.customerErrorMessage = ''
}

function customerDialogContextIsCurrent() {
  return customerDialogOpen.value
    && customerDialogFactoryId.value === activeFactoryId.value
    && quoteStore.isFactoryContextCurrent(
      customerDialogFactoryId.value,
      customerDialogFactoryGeneration.value,
    )
}

async function createCustomer(name: string) {
  if (!customerDialogContextIsCurrent()) return
  await quoteStore.createCustomer(customerDialogFactoryId.value, name).catch(() => undefined)
}

async function updateCustomer(customer: ApiInternalQuoteCustomer, name: string) {
  if (!customerDialogContextIsCurrent() || customer.factory_id !== customerDialogFactoryId.value) return
  await quoteStore.updateCustomer(
    customer.factory_id,
    customer.id,
    name,
    customer.revision,
  ).catch(() => undefined)
}

async function deleteCustomer(customer: ApiInternalQuoteCustomer) {
  if (!customerDialogContextIsCurrent() || customer.factory_id !== customerDialogFactoryId.value) return
  const removed = await quoteStore.deleteCustomer(
    customer.factory_id,
    customer.id,
    customer.revision,
  ).catch(() => undefined)
  if (removed && customerFilter.value === customer.name) customerFilter.value = 'all'
}

function requiredCount(quote: InternalQuote) {
  return quote.sections.filter((section) => section.isRequired).length
}

function clearFilters() {
  query.value = ''
  statusFilter.value = 'all'
  customerFilter.value = 'all'
}

async function loadQuotePage(page = 1, factoryId: string = activeFactoryId.value) {
  const options = {
    page,
    pageSize: 10,
    ...(statusFilter.value !== 'all' ? { status: statusFilter.value } : {}),
    ...(query.value.trim() ? { keyword: query.value.trim() } : {}),
    ...(customerFilter.value !== 'all' ? { customer: customerFilter.value } : {}),
  }
  await quoteStore.loadQuotes(factoryId, options)
}

async function changeQuotePage(page: number) {
  if (quoteStore.listLoading || page < 1 || page > quoteStore.quoteListTotalPages || page === quoteStore.quoteListPage) return
  await loadQuotePage(page)
}

async function loadPage(factoryId = activeFactoryId.value) {
  quoteStore.activateFactoryContext(factoryId)
  await Promise.all([
    loadQuotePage(1, factoryId),
    quoteStore.loadBusinessOwners(factoryId),
    quoteStore.loadCustomers(factoryId),
    quoteStore.loadDashboard(factoryId, statsPeriod.value),
  ])
}

onMounted(() => { void loadPage() })
let suppressFilterReload = false
let listFilterTimer: ReturnType<typeof setTimeout> | undefined
watch(activeFactoryId, async (factoryId) => {
  closeCreateDialog()
  closePricingBaseline()
  closeCustomerDialog()
  resetDeleteDialog()
  resetArchiveDialog()
  clearQuoteComparison()
  dialogError.value = ''
  if (listFilterTimer) {
    clearTimeout(listFilterTimer)
    listFilterTimer = undefined
  }
  quoteStore.activateFactoryContext(factoryId)
  suppressFilterReload = true
  clearFilters()
  void loadPage(factoryId)
  await nextTick()
  suppressFilterReload = false
})
watch(() => quoteStore.quotes, (currentQuotes) => {
  if (!comparisonQuotes.value.length) return
  const currentById = new Map(currentQuotes.map((quote) => [quote.id, quote]))
  comparisonQuotes.value = comparisonQuotes.value.map((quote) => currentById.get(quote.id) ?? quote)
})
watch([query, statusFilter, customerFilter], () => {
  if (suppressFilterReload) return
  if (listFilterTimer) clearTimeout(listFilterTimer)
  listFilterTimer = setTimeout(() => { void loadQuotePage(1) }, 300)
})
watch(statsPeriod, () => { void quoteStore.loadDashboard(activeFactoryId.value, statsPeriod.value) })
onBeforeUnmount(() => {
  if (listFilterTimer) clearTimeout(listFilterTimer)
})
</script>

<template>
  <div class="quote-home">
    <section class="quote-home-heading">
      <div>
        <div class="quote-eyebrow"><span />业务部 · 内部成本协作</div>
        <h1>内部报价台</h1>
        <p>业务部与工程部均可新建或复制报价，业务部、工程部、装配部固定参与，其余部门按项目需要选择。</p>
      </div>
      <div class="quote-heading-actions">
        <button v-if="canViewPricingBaseline" type="button" class="quote-baseline-button" :disabled="quoteStore.baselineLoading" @click="openPricingBaseline">
          <Settings2 aria-hidden="true" />调整报价基数
        </button>
        <button type="button" class="quote-new-button" :disabled="!canOpenCreate" :title="canOpenCreate ? '新建内部报价' : createUnavailableMessage" @click="openCreate">
          <Plus aria-hidden="true" />新建内部报价
        </button>
      </div>
    </section>

    <div class="quote-stage-notice">
      <span>真实 API</span>{{ quoteStore.frontendNotice }}
    </div>

    <div v-if="isCurrentFactoryReadOnly" class="quote-readonly-notice" role="status">
      <ShieldCheck aria-hidden="true" />
      <div>
        <strong>{{ activeFactoryName }} · {{ isCurrentFactoryForeign ? '跨厂只读' : '只读' }}</strong>
        <span>{{ isCurrentFactoryForeign ? '可查看该厂区内部报价数据；新建、复制、编辑、审核、最终放行及受控导出仅允许在所属厂区执行。' : '当前账号可查看该厂区内部报价，但没有可用的业务操作权限。' }}</span>
      </div>
    </div>

    <p v-if="quoteStore.errorMessage" class="quote-page-message error" role="alert">{{ quoteStore.errorMessage }}</p>
    <p v-if="quoteStore.dashboardErrorMessage" class="quote-page-message error" role="alert">统计数据读取失败：{{ quoteStore.dashboardErrorMessage }}</p>
    <p v-if="comparisonError" class="quote-page-message error" role="alert">{{ comparisonError }}</p>

    <section class="quote-dashboard-heading" aria-label="报价统计周期">
      <div>
        <strong>报价经营概览</strong>
        <span>{{ activeFactoryName }} · {{ dashboard.period_label }} · {{ dashboardRange }}</span>
      </div>
      <div class="quote-period-switch" role="group" aria-label="周月年统计单位">
        <button
          v-for="option in periodOptions"
          :key="option.value"
          type="button"
          :class="{ active: statsPeriod === option.value }"
          :aria-pressed="statsPeriod === option.value"
          @click="statsPeriod = option.value"
        ><span>{{ option.shortLabel }}</span>{{ option.label }}</button>
      </div>
    </section>

    <section class="quote-kpi-grid" aria-label="内部报价指标">
      <article v-for="kpi in kpis" :key="kpi.label" :class="`tone-${kpi.tone}`">
        <div><component :is="kpi.icon" aria-hidden="true" /><span>{{ kpi.label }}</span></div>
        <strong>{{ kpi.value }}</strong>
        <p>{{ kpi.detail }}</p>
      </article>
    </section>

    <section class="quote-dashboard-grid" :aria-busy="quoteStore.dashboardLoading">
      <article class="quote-chart-card quote-status-chart">
        <header>
          <div><PieChart aria-hidden="true" /><span><strong>报价状态占比</strong><small>{{ dashboard.period_label }}全部新建报价</small></span></div>
          <em>{{ dashboard.totals.total }} 份</em>
        </header>
        <InternalQuoteStatusDonut
          :rows="statusRows"
          :total="dashboard.totals.total"
          :period-label="dashboard.period_label"
        />
      </article>

      <article class="quote-chart-card quote-customer-chart">
        <header>
          <div><BarChart3 aria-hidden="true" /><span><strong>各客户报价数量</strong><small>按{{ dashboard.period_label.replace('本', '') }}统计 · 数量从高到低</small></span></div>
          <em>{{ dashboard.customer_quote_counts.length }} 个客户</em>
        </header>
        <div v-if="dashboard.customer_quote_counts.length" class="quote-horizontal-bars">
          <div v-for="item in dashboard.customer_quote_counts" :key="item.customer" class="quote-horizontal-row">
            <div><strong :title="item.customer">{{ item.customer }}</strong><span>{{ item.count }} 份 · {{ item.percentage.toFixed(1) }}%</span></div>
            <div class="quote-horizontal-track"><i :style="{ width: customerBarWidth(item.count) }" /></div>
          </div>
        </div>
        <div v-else class="quote-chart-empty">{{ dashboard.period_label }}暂无客户报价</div>
      </article>

      <article class="quote-chart-card quote-speed-chart">
        <header>
          <div><TimerReset aria-hidden="true" /><span><strong>客户报价速度对比</strong><small>建单至最终放行的平均时长</small></span></div>
          <em>越靠左越快</em>
        </header>
        <div v-if="dashboard.customer_speed.length" class="quote-speed-plot">
          <div class="quote-speed-scale"><span>快</span><i /><span>慢</span></div>
          <div v-for="item in dashboard.customer_speed" :key="item.customer" class="quote-speed-row">
            <div class="quote-speed-meta"><strong :title="item.customer">{{ item.customer }}</strong><span>{{ durationLabel(item.average_hours) }} · {{ item.completed_count }} 份样本</span></div>
            <div class="quote-speed-track"><i :style="{ left: speedDotPosition(item.average_hours) }"><span>{{ durationLabel(item.average_hours) }}</span></i></div>
          </div>
        </div>
        <div v-else class="quote-chart-empty">{{ dashboard.period_label }}暂无已完成报价，暂不能比较速度</div>
        <p class="quote-speed-note">采用横向点图，避免把“耗时更长”误读成表现更好；样本数同时展示。</p>
      </article>

    </section>

    <section class="quote-list-panel">
      <header class="quote-list-toolbar">
        <label class="quote-search-box">
          <Search aria-hidden="true" />
          <input v-model="query" type="search" placeholder="搜索报价号、产品、客户、版本或创建人" aria-label="搜索内部报价">
        </label>
        <div class="quote-filters">
          <Filter aria-hidden="true" />
          <select v-model="statusFilter" aria-label="报价状态">
            <option value="all">全部状态</option>
            <option v-for="(meta, value) in statusMeta" :key="value" :value="value">{{ meta.label }}</option>
          </select>
          <select v-model="customerFilter" aria-label="客户筛选">
            <option value="all">全部客户</option>
            <option v-for="customer in customers" :key="customer">{{ customer }}</option>
          </select>
          <button
            v-if="canManageCustomers"
            type="button"
            class="quote-customer-button"
            :disabled="quoteStore.customerLoading"
            title="维护当前厂区客户"
            @click="openCustomerDialog"
          ><Users aria-hidden="true" />客户资料</button>
          <button
            type="button"
            class="quote-compare-button"
            :disabled="comparisonQuotes.length < 2 || comparisonLoading"
            :title="comparisonButtonTitle"
            @click="openQuoteComparison"
          ><BarChart3 aria-hidden="true" />{{ comparisonLoading ? '读取最新报价…' : '报价对比' }} <span>{{ comparisonQuotes.length }}/{{ comparisonLimit }}</span></button>
          <button v-if="comparisonQuotes.length" type="button" class="quote-comparison-clear" title="清空对比选择" @click="clearQuoteComparison">清空</button>
          <button type="button" class="quote-clear-filter" title="重置筛选" @click="clearFilters"><RotateCcw aria-hidden="true" /></button>
        </div>
      </header>

      <div class="quote-table-scroll">
        <table class="quote-table">
          <thead><tr><th class="quote-select-column"><span class="sr-only">选择对比</span></th><th>报价号</th><th>产品 / 客户</th><th>发起</th><th>版本</th><th>状态</th><th>部门完成进度</th><th>更新时间</th><th><span class="sr-only">操作</span></th></tr></thead>
          <tbody>
            <template v-if="!quoteStore.listLoading">
            <tr v-for="quote in quoteStore.quotes" :key="quote.id" :class="{ 'comparison-selected': isQuoteSelectedForComparison(quote) }" @dblclick="openQuote(quote)">
              <td class="quote-select-cell"><input type="checkbox" :checked="isQuoteSelectedForComparison(quote)" :disabled="comparisonSelectionDisabled(quote)" :aria-label="`选择 ${quote.quoteNo} 进行报价对比`" @click.stop @dblclick.stop @change="toggleQuoteComparison(quote)"></td>
              <td><button type="button" class="quote-number" @click="openQuote(quote)">{{ quote.quoteNo }}</button></td>
              <td><strong>{{ quote.productName }}</strong><span>{{ quote.customer }}</span></td>
              <td><span class="quote-initiator">{{ quote.initiatorDepartment === 'engineering' ? '工程部' : '业务部' }}</span><small>{{ quote.initiatorName }}</small></td>
              <td><span class="quote-version">{{ quote.versionLabel }}</span><span v-if="(quote.documentVersionCount ?? 1) > 1">{{ quote.documentProductCount }} 款 · {{ quote.documentVersionCount }} 个方案版本</span></td>
              <td><span class="quote-status" :class="`tone-${statusMeta[quote.status].tone}`"><i />{{ quoteStatusLabel(quote) }}</span></td>
              <td>
                <div class="quote-progress-cell"><div><span :style="{ width: `${requiredCount(quote) ? approvedCount(quote) / requiredCount(quote) * 100 : 0}%` }" /></div><strong>{{ approvedCount(quote) }}/{{ requiredCount(quote) }}</strong></div>
              </td>
              <td><span class="quote-date">{{ quote.updatedAt }}</span></td>
              <td>
                <div class="quote-row-actions">
                  <button type="button" title="查看报价" aria-label="查看报价" @click="openQuote(quote)"><Eye aria-hidden="true" /></button>
                  <button
                    type="button"
                    :disabled="!canCloneQuote(quote)"
                    :title="canCloneQuote(quote) ? '复制报价' : cloneUnavailableMessage(quote)"
                    :aria-label="canCloneQuote(quote) ? '复制报价' : cloneUnavailableMessage(quote)"
                    @click="openClone(quote)"
                  ><Copy aria-hidden="true" /></button>
                  <button
                    v-if="canDeleteQuote(quote)"
                    type="button"
                    class="danger"
                    :disabled="deleteIsProtected(quote) || deletingQuoteId === quote.id"
                    :title="deleteButtonTitle(quote)"
                    :aria-label="deleteButtonTitle(quote)"
                    @click.stop="openDeleteDialog(quote)"
                  ><Trash2 aria-hidden="true" /></button>
                  <button
                    v-if="canArchiveQuote(quote)"
                    type="button"
                    class="archive"
                    :disabled="archivingQuoteId === quote.id"
                    title="归档报价并保留审计记录"
                    aria-label="归档报价并保留审计记录"
                    @click.stop="openArchiveDialog(quote)"
                  ><Archive aria-hidden="true" /></button>
                  <button type="button" class="primary" title="进入报价" aria-label="进入报价" @click="openQuote(quote)"><ArrowRight aria-hidden="true" /></button>
                </div>
              </td>
            </tr>
            <tr v-if="!quoteStore.quotes.length"><td colspan="9" class="quote-empty">没有符合筛选条件的内部报价。</td></tr>
            </template>
            <tr v-else><td colspan="9" class="quote-empty">正在按页读取内部报价…</td></tr>
          </tbody>
        </table>
      </div>
      <footer class="quote-table-footer">
        <span>共 {{ quoteStore.quoteListTotal }} 条 · 当前显示 {{ pageStart }}–{{ pageEnd }} 条 · 每页 10 条 · 当前厂区：{{ activeFactoryName }}</span>
        <nav class="quote-pagination" aria-label="内部报价分页">
          <button type="button" :disabled="quoteStore.listLoading || quoteStore.quoteListPage <= 1" @click="changeQuotePage(quoteStore.quoteListPage - 1)"><ChevronLeft aria-hidden="true" />上一页</button>
          <strong>第 {{ quoteStore.quoteListPage }} / {{ quoteStore.quoteListTotalPages }} 页</strong>
          <button type="button" :disabled="quoteStore.listLoading || quoteStore.quoteListPage >= quoteStore.quoteListTotalPages" @click="changeQuotePage(quoteStore.quoteListPage + 1)">下一页<ChevronRight aria-hidden="true" /></button>
        </nav>
        <span>切换页码时按需加载，未访问页不会预先读取</span>
      </footer>
    </section>

    <div v-if="deleteTarget" class="quote-delete-backdrop" @click.self="closeDeleteDialog">
      <section class="quote-delete-dialog" role="dialog" aria-modal="true" aria-labelledby="quote-delete-title">
        <div class="quote-delete-icon"><Trash2 aria-hidden="true" /></div>
        <div>
          <h2 id="quote-delete-title">确认删除内部报价？</h2>
          <p>即将删除 <strong>{{ deleteTarget.quoteNo }}</strong> · {{ deleteTarget.productName }}（{{ deleteTarget.versionLabel }}）。此操作会同时删除尚未放行的分段明细、附件与修订记录，且无法恢复。</p>
          <p class="quote-delete-rule">仅建单人和本厂区业务主管可执行；已放行、已导出或已交接到报客价的报价只能归档。</p>
          <p v-if="deleteDialogError" class="quote-delete-error" role="alert">{{ deleteDialogError }}</p>
          <footer>
            <button type="button" :disabled="Boolean(deletingQuoteId)" @click="closeDeleteDialog">取消</button>
            <button type="button" class="danger" :disabled="Boolean(deletingQuoteId)" @click="confirmDeleteQuote">
              {{ deletingQuoteId ? '正在删除…' : '确认删除' }}
            </button>
          </footer>
        </div>
      </section>
    </div>

    <div v-if="archiveTarget" class="quote-delete-backdrop" @click.self="closeArchiveDialog">
      <section class="quote-delete-dialog quote-archive-dialog" role="dialog" aria-modal="true" aria-labelledby="quote-archive-title">
        <div class="quote-delete-icon"><Archive aria-hidden="true" /></div>
        <div>
          <h2 id="quote-archive-title">确认归档内部报价？</h2>
          <p>即将归档 <strong>{{ archiveTarget.quoteNo }}</strong> · {{ archiveTarget.productName }}（{{ archiveTarget.versionLabel }}）。报价、附件、放行和导出记录都会保留，可继续审计，但不能再参与业务操作。</p>
          <label class="quote-archive-reason">归档原因<textarea v-model="archiveReason" rows="3" maxlength="500" placeholder="请说明取消或归档原因" /></label>
          <p v-if="archiveDialogError" class="quote-delete-error" role="alert">{{ archiveDialogError }}</p>
          <footer>
            <button type="button" :disabled="Boolean(archivingQuoteId)" @click="closeArchiveDialog">取消</button>
            <button type="button" class="archive" :disabled="Boolean(archivingQuoteId)" @click="confirmArchiveQuote">
              {{ archivingQuoteId ? '正在归档…' : '确认归档' }}
            </button>
          </footer>
        </div>
      </section>
    </div>

    <InternalQuoteCreateDialog
      :open="createDialogOpen"
      :mode="dialogMode"
      :source-quote="cloneSource"
      :business-owners="quoteStore.businessOwners"
      :customers="managedCustomerNames"
      :busy="quoteStore.submitting"
      :external-error="dialogError"
      :factory-id="activeFactoryId"
      :factory-name="activeFactoryName"
      :allowed-initiator-departments="allowedInitiatorDepartments"
      @close="closeCreateDialog"
      @confirm="handleConfirm"
    />
    <InternalQuoteComparisonDialog
      :open="comparisonDialogOpen"
      :quotes="comparisonQuotes"
      :factory-name="activeFactoryName"
      @close="closeQuoteComparison"
    />
    <InternalQuoteBaselineDialog
      :open="baselineDialogOpen"
      :baseline="quoteStore.pricingBaseline"
      :busy="quoteStore.baselineLoading || quoteStore.baselineSaving"
      :can-edit="canManagePricingBaseline"
      :external-error="baselineDialogError"
      :factory-name="activeFactoryName"
      @close="closePricingBaseline"
      @save="savePricingBaseline"
    />
    <InternalQuoteCustomerDialog
      :open="customerDialogOpen"
      :customers="quoteStore.factoryCustomers"
      :busy="quoteStore.customerLoading || quoteStore.customerSaving"
      :factory-name="activeFactoryName"
      :external-error="quoteStore.customerErrorMessage"
      @close="closeCustomerDialog"
      @create="createCustomer"
      @update="updateCustomer"
      @delete="deleteCustomer"
    />
  </div>
</template>

<style scoped>
.quote-home{display:grid;gap:18px;padding-bottom:28px}.quote-home-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;padding-top:5px}.quote-home-heading h1{margin:6px 0 0;color:#0f172a;font-size:clamp(30px,3vw,46px);font-weight:950;letter-spacing:-.045em}.quote-home-heading p{max-width:820px;margin:10px 0 0;color:#64748b;font-size:13px;line-height:1.75}.quote-eyebrow{display:flex;align-items:center;gap:7px;color:#0f766e;font-size:11px;font-weight:900;letter-spacing:.08em}.quote-eyebrow span{width:22px;height:2px;border-radius:2px;background:#0d9488}.quote-heading-actions{display:flex;flex:0 0 auto;align-items:center;gap:10px}.quote-new-button,.quote-baseline-button{display:inline-flex;min-height:44px;align-items:center;gap:8px;border-radius:11px;padding:0 18px;font-size:13px;font-weight:900}.quote-new-button{border:1px solid #0f766e;background:#0f766e;color:#fff;box-shadow:0 10px 24px rgb(15 118 110/.2)}.quote-new-button:hover{background:#115e59}.quote-baseline-button{border:1px solid #99f6e4;background:#fff;color:#0f766e;box-shadow:0 8px 20px rgb(15 118 110/.08)}.quote-baseline-button:hover{border-color:#2dd4bf;background:#f0fdfa}.quote-new-button svg,.quote-baseline-button svg{width:18px}
.quote-home{display:grid;gap:18px;padding-bottom:28px}.quote-home-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;padding-top:5px}.quote-home-heading h1{margin:6px 0 0;color:#0f172a;font-size:clamp(30px,3vw,46px);font-weight:950;letter-spacing:-.045em}.quote-home-heading p{max-width:820px;margin:10px 0 0;color:#64748b;font-size:13px;line-height:1.75}.quote-eyebrow{display:flex;align-items:center;gap:7px;color:#0f766e;font-size:11px;font-weight:900;letter-spacing:.08em}.quote-eyebrow span{width:22px;height:2px;border-radius:2px;background:#0d9488}.quote-heading-actions{display:flex;flex:0 0 auto;align-items:center;gap:10px}.quote-new-button,.quote-baseline-button{display:inline-flex;min-height:44px;align-items:center;gap:8px;border-radius:11px;padding:0 18px;font-size:13px;font-weight:900}.quote-new-button{border:1px solid #0f766e;background:#0f766e;color:#fff;box-shadow:0 10px 24px rgb(15 118 110/.2)}.quote-new-button:hover{background:#115e59}.quote-baseline-button{border:1px solid #99f6e4;background:#fff;color:#0f766e;box-shadow:0 8px 20px rgb(15 118 110/.08)}.quote-baseline-button:hover{border-color:#2dd4bf;background:#f0fdfa}.quote-new-button:disabled,.quote-baseline-button:disabled{cursor:not-allowed;border-color:#cbd5e1;background:#e2e8f0;color:#64748b;box-shadow:none}.quote-new-button svg,.quote-baseline-button svg{width:18px}
.quote-stage-notice{display:flex;align-items:center;gap:8px;border:1px solid #bae6fd;border-radius:10px;background:#f0f9ff;padding:8px 11px;color:#0369a1;font-size:11px}.quote-stage-notice span{border-radius:999px;background:#0284c7;padding:3px 7px;color:#fff;font-size:9px;font-weight:900;letter-spacing:.08em}
.quote-readonly-notice{display:flex;align-items:flex-start;gap:10px;border:1px solid #99f6e4;border-radius:11px;background:#f0fdfa;padding:11px 13px;color:#115e59}.quote-readonly-notice>svg{width:18px;flex:0 0 auto;margin-top:1px}.quote-readonly-notice>div{display:grid;gap:3px}.quote-readonly-notice strong{font-size:12px}.quote-readonly-notice span{color:#0f766e;font-size:11px;line-height:1.55}
.quote-page-message{margin:0;border-radius:9px;padding:9px 12px;font-size:11px}.quote-page-message.error{border:1px solid #fecaca;background:#fef2f2;color:#b91c1c}
.quote-dashboard-heading{display:flex;align-items:center;justify-content:space-between;gap:18px;border:1px solid #dbe5ea;border-radius:13px;background:#fff;padding:12px 14px;box-shadow:0 8px 26px rgb(15 23 42/.04)}.quote-dashboard-heading>div:first-child{display:grid;gap:3px}.quote-dashboard-heading strong{color:#0f172a;font-size:14px}.quote-dashboard-heading>div:first-child span{color:#64748b;font-size:11px}.quote-period-switch{display:flex;align-items:center;gap:4px;border:1px solid #dbe5ea;border-radius:10px;background:#f8fafc;padding:4px}.quote-period-switch button{display:flex;min-height:34px;align-items:center;gap:6px;border:0;border-radius:7px;background:transparent;padding:0 11px;color:#64748b;font-size:11px;font-weight:850;transition:background .18s,color .18s,box-shadow .18s,transform .18s}.quote-period-switch button:hover{background:#fff;color:#0f766e;transform:translateY(-1px)}.quote-period-switch button.active{background:#0f766e;color:#fff;box-shadow:0 6px 14px rgb(15 118 110/.22)}.quote-period-switch button span{display:grid;width:20px;height:20px;place-items:center;border-radius:6px;background:rgb(255 255 255/.16);font-size:10px}
.quote-kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.quote-kpi-grid article{position:relative;overflow:hidden;border:1px solid #dbe5ea;border-radius:12px;background:#fff;padding:14px;box-shadow:0 7px 24px rgb(15 23 42/.04);transition:transform .18s,box-shadow .18s}.quote-kpi-grid article:hover{transform:translateY(-2px);box-shadow:0 12px 28px rgb(15 23 42/.08)}.quote-kpi-grid article::after{position:absolute;inset:0 auto 0 0;width:3px;background:var(--tone);content:''}.quote-kpi-grid article>div{display:flex;align-items:center;gap:7px;color:#64748b;font-size:11px;font-weight:900;letter-spacing:.03em}.quote-kpi-grid svg{width:17px;color:var(--tone)}.quote-kpi-grid strong{display:block;margin-top:12px;color:#0f172a;font-size:30px;line-height:1}.quote-kpi-grid p{margin:7px 0 0;color:#94a3b8;font-size:11px}.tone-blue{--tone:#2563eb}.tone-amber{--tone:#d97706}.tone-red{--tone:#dc2626}.tone-teal{--tone:#0f766e}.tone-green{--tone:#059669}.tone-slate{--tone:#64748b}
.quote-dashboard-grid{display:grid;grid-template-columns:minmax(270px,.85fr) minmax(350px,1.15fr) minmax(350px,1.15fr);gap:12px;transition:opacity .2s}.quote-dashboard-grid[aria-busy=true]{opacity:.62}.quote-chart-card{min-width:0;overflow:hidden;border:1px solid #dbe5ea;border-radius:14px;background:#fff;box-shadow:0 12px 30px rgb(15 23 42/.045)}.quote-chart-card>header{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid #edf2f5;background:linear-gradient(180deg,#fff,#fbfdfe);padding:13px 14px}.quote-chart-card>header>div{display:flex;align-items:center;gap:8px}.quote-chart-card>header svg{width:18px;flex:0 0 auto;color:#0f766e}.quote-chart-card>header span{display:grid;gap:2px}.quote-chart-card>header strong{color:#0f172a;font-size:12px}.quote-chart-card>header small{color:#94a3b8;font-size:10px}.quote-chart-card>header em{color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:10px;font-style:normal;white-space:nowrap}.quote-chart-empty{display:grid;min-height:190px;place-items:center;padding:20px;color:#94a3b8;font-size:11px}.quote-horizontal-bars,.quote-speed-plot{display:grid;max-height:250px;gap:10px;overflow:auto;padding:14px}.quote-horizontal-row{display:grid;gap:6px}.quote-horizontal-row>div:first-child{display:flex;align-items:center;justify-content:space-between;gap:12px}.quote-horizontal-row strong,.quote-speed-meta strong{overflow:hidden;color:#334155;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.quote-horizontal-row span,.quote-speed-meta span{color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:9px;white-space:nowrap}.quote-horizontal-track{height:9px;overflow:hidden;border-radius:99px;background:#eef2f6}.quote-horizontal-track i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#0f766e,#2dd4bf);box-shadow:0 0 12px rgb(20 184 166/.2);animation:quote-chart-grow .45s ease-out both}.quote-speed-scale{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:7px;color:#94a3b8;font-size:9px;font-weight:800}.quote-speed-scale i{height:1px;background:linear-gradient(90deg,#14b8a6,#cbd5e1,#f59e0b)}.quote-speed-row{display:grid;grid-template-columns:minmax(120px,.72fr) minmax(170px,1.28fr);align-items:center;gap:10px}.quote-speed-meta{display:grid;gap:3px;min-width:0}.quote-speed-track{position:relative;height:22px;border-radius:99px;background:linear-gradient(90deg,rgb(20 184 166/.11),rgb(245 158 11/.11))}.quote-speed-track::before{position:absolute;top:10px;right:8%;left:8%;height:2px;background:linear-gradient(90deg,#5eead4,#fbbf24);content:''}.quote-speed-track>i{position:absolute;top:5px;width:12px;height:12px;border:3px solid #fff;border-radius:99px;background:#0f766e;box-shadow:0 2px 8px rgb(15 118 110/.35);transform:translateX(-50%);transition:left .3s}.quote-speed-track>i span{position:absolute;right:50%;bottom:15px;display:none;border-radius:5px;background:#0f172a;padding:3px 5px;color:#fff;font-size:8px;font-style:normal;white-space:nowrap;transform:translateX(50%)}.quote-speed-row:hover .quote-speed-track>i span{display:block}.quote-speed-note{margin:0;border-top:1px solid #eef2f6;background:#f8fafc;padding:8px 14px;color:#64748b;font-size:9px;line-height:1.5}.quote-progress-chart{grid-column:1/-1}.quote-progress-bars{display:grid;max-height:320px;overflow:auto}.quote-progress-bars button{display:grid;grid-template-columns:minmax(220px,.9fr) minmax(300px,1.6fr) 92px 20px;align-items:center;gap:14px;border:0;border-top:1px solid #eef2f6;background:#fff;padding:11px 14px;text-align:left;transition:background .16s}.quote-progress-bars button:first-child{border-top:0}.quote-progress-bars button:hover{background:#f8fafc}.quote-progress-title,.quote-progress-value{display:grid;gap:3px;min-width:0}.quote-progress-title strong{color:#0f766e;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px}.quote-progress-title small{overflow:hidden;color:#64748b;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.quote-progress-track{height:10px;overflow:hidden;border-radius:99px;background:#e8eef2}.quote-progress-track i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#2563eb,#14b8a6);animation:quote-chart-grow .45s ease-out both}.quote-progress-value{text-align:right}.quote-progress-value strong{color:#0f172a;font-size:12px}.quote-progress-value small{color:#94a3b8;font-size:9px}.quote-progress-bars button>svg{width:16px;color:#94a3b8;transition:color .16s,transform .16s}.quote-progress-bars button:hover>svg{color:#0f766e;transform:translateX(2px)}
@keyframes quote-chart-grow{from{width:0}}
.quote-list-panel{overflow:hidden;border:1px solid #dbe5ea;border-radius:14px;background:#fff;box-shadow:0 16px 38px rgb(15 23 42/.05)}.quote-list-toolbar{display:flex;align-items:center;gap:14px;padding:13px;border-bottom:1px solid #e2e8f0}.quote-search-box{display:flex;min-width:280px;flex:1;align-items:center;gap:8px;border:1px solid #dbe5ea;border-radius:9px;background:#f8fafc;padding:0 11px;color:#94a3b8}.quote-search-box:focus-within{border-color:#14b8a6;background:#fff;box-shadow:0 0 0 3px rgb(20 184 166/.08)}.quote-search-box svg{width:16px}.quote-search-box input{min-width:0;flex:1;border:0;background:transparent;padding:9px 0;color:#0f172a;font-size:12px;outline:0}.quote-filters{display:flex;align-items:center;gap:8px;color:#94a3b8}.quote-filters>svg{width:16px}.quote-filters select{height:36px;border:1px solid #dbe5ea;border-radius:9px;background:#fff;padding:0 28px 0 10px;color:#475569;font-size:11px;font-weight:700}.quote-clear-filter{display:grid;width:36px;height:36px;place-items:center;border:1px solid #dbe5ea;border-radius:9px;background:#fff;color:#64748b}.quote-clear-filter:hover{border-color:#99f6e4;background:#f0fdfa;color:#0f766e}.quote-clear-filter svg{width:15px}
.quote-customer-button,.quote-compare-button{display:inline-flex;height:36px;align-items:center;gap:6px;border:1px solid #99f6e4;border-radius:9px;background:#f0fdfa;padding:0 10px;color:#0f766e;font-size:11px;font-weight:900;white-space:nowrap}.quote-customer-button:hover,.quote-compare-button:hover:not(:disabled){border-color:#2dd4bf;background:#ccfbf1}.quote-customer-button:disabled{cursor:wait;opacity:.55}.quote-compare-button:disabled{cursor:not-allowed;border-color:#e2e8f0;background:#f8fafc;color:#94a3b8}.quote-customer-button svg,.quote-compare-button svg{width:15px}.quote-compare-button span{border-radius:999px;background:rgb(15 118 110/.1);padding:2px 5px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:8px}.quote-comparison-clear{height:36px;border:0;background:transparent;padding:0 3px;color:#64748b;font-size:10px;font-weight:800}.quote-comparison-clear:hover{color:#dc2626}
.quote-table-scroll{overflow:auto}.quote-table{width:100%;min-width:1160px;border-collapse:collapse;text-align:left}.quote-table th{background:#f1f5f9;padding:10px 12px;color:#64748b;font-size:9px;font-weight:900;letter-spacing:.08em;text-transform:uppercase}.quote-table td{border-top:1px solid #eef2f6;padding:11px 12px;color:#334155;font-size:11px;vertical-align:middle}.quote-table tbody tr{transition:background .15s}.quote-table tbody tr:hover{background:#f8fafc}.quote-table tbody tr.comparison-selected{background:#f0fdfa}.quote-table tbody tr.comparison-selected:hover{background:#ccfbf1}.quote-select-column,.quote-select-cell{width:38px;padding-right:4px!important;text-align:center}.quote-select-cell input{width:15px;height:15px;margin:0;accent-color:#0f766e}.quote-select-cell input:disabled{cursor:not-allowed;opacity:.35}.quote-table td:nth-child(3) strong{display:block;color:#0f172a;font-size:12px}.quote-table td:nth-child(3) span,.quote-table small{display:block;margin-top:3px;color:#94a3b8;font-size:10px}.quote-number{border:0;background:transparent;padding:0;color:#0f766e;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px;font-weight:900}.quote-number:hover{text-decoration:underline}.quote-initiator,.quote-version{display:inline-flex;border-radius:999px;background:#f1f5f9;padding:4px 7px;color:#475569;font-size:9px;font-weight:900}.quote-status{display:inline-flex;align-items:center;gap:6px;border-radius:999px;background:color-mix(in srgb,var(--tone) 10%,white);padding:5px 8px;color:var(--tone);font-size:9px;font-weight:900;white-space:nowrap}.quote-status i{width:6px;height:6px;border-radius:99px;background:currentColor}.quote-progress-cell{display:flex;min-width:120px;align-items:center;gap:8px}.quote-progress-cell>div{height:6px;flex:1;overflow:hidden;border-radius:99px;background:#e2e8f0}.quote-progress-cell>div span{display:block;height:100%;border-radius:99px;background:#0d9488}.quote-progress-cell strong{color:#475569;font-size:10px}.quote-date{color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:10px;white-space:nowrap}.quote-row-actions{display:flex;justify-content:flex-end;gap:5px}.quote-row-actions button{display:grid;width:30px;height:30px;place-items:center;border:1px solid #e2e8f0;border-radius:8px;background:#fff;color:#64748b}.quote-row-actions button:hover{border-color:#99f6e4;background:#f0fdfa;color:#0f766e}.quote-row-actions button:disabled{cursor:not-allowed;border-color:#e2e8f0;background:#f8fafc;color:#cbd5e1}.quote-row-actions button.primary{border-color:#0f766e;background:#0f766e;color:#fff}.quote-row-actions button.danger{border-color:#fecaca;color:#dc2626}.quote-row-actions button.danger:hover:not(:disabled){border-color:#ef4444;background:#fef2f2;color:#b91c1c}.quote-row-actions svg{width:14px}.quote-empty{padding:40px!important;text-align:center;color:#94a3b8!important}.quote-table-footer{display:grid;grid-template-columns:minmax(260px,1fr) auto minmax(240px,1fr);align-items:center;gap:12px;border-top:1px solid #e2e8f0;background:#f8fafc;padding:9px 13px;color:#64748b;font-size:10px}.quote-table-footer>span:last-child{text-align:right}.quote-pagination{display:flex;align-items:center;justify-content:center;gap:8px}.quote-pagination button{display:inline-flex;height:30px;align-items:center;gap:4px;border:1px solid #dbe5ea;border-radius:8px;background:#fff;padding:0 9px;color:#475569;font-size:10px;font-weight:800}.quote-pagination button:hover:not(:disabled){border-color:#5eead4;background:#f0fdfa;color:#0f766e}.quote-pagination button:disabled{cursor:not-allowed;opacity:.42}.quote-pagination button svg{width:13px}.quote-pagination strong{min-width:72px;color:#334155;text-align:center;font-size:10px}
.quote-delete-backdrop{position:fixed;z-index:90;display:grid;inset:0;place-items:center;background:rgb(15 23 42/.52);padding:20px;backdrop-filter:blur(2px)}.quote-delete-dialog{display:grid;width:min(520px,100%);grid-template-columns:44px 1fr;gap:14px;border:1px solid #fecaca;border-radius:16px;background:#fff;padding:20px;box-shadow:0 24px 70px rgb(15 23 42/.28)}.quote-delete-icon{display:grid;width:44px;height:44px;place-items:center;border-radius:12px;background:#fef2f2;color:#dc2626}.quote-delete-icon svg{width:21px}.quote-delete-dialog h2{margin:1px 0 8px;color:#0f172a;font-size:18px}.quote-delete-dialog p{margin:0;color:#475569;font-size:12px;line-height:1.7}.quote-delete-dialog p strong{color:#0f172a}.quote-delete-dialog .quote-delete-rule{margin-top:10px;border-radius:8px;background:#fff7ed;padding:8px 10px;color:#9a3412;font-size:11px}.quote-delete-dialog .quote-delete-error{margin-top:10px;border:1px solid #fecaca;border-radius:8px;background:#fef2f2;padding:8px 10px;color:#b91c1c;font-size:11px}.quote-delete-dialog footer{display:flex;justify-content:flex-end;gap:8px;margin-top:17px}.quote-delete-dialog footer button{min-width:84px;height:36px;border:1px solid #dbe5ea;border-radius:9px;background:#fff;color:#475569;font-size:11px;font-weight:900}.quote-delete-dialog footer button:hover:not(:disabled){background:#f8fafc}.quote-delete-dialog footer button.danger{border-color:#dc2626;background:#dc2626;color:#fff}.quote-delete-dialog footer button.danger:hover:not(:disabled){background:#b91c1c}.quote-delete-dialog footer button:disabled{cursor:wait;opacity:.55}
.quote-row-actions button.archive{border-color:#fed7aa;color:#c2410c}.quote-row-actions button.archive:hover:not(:disabled){border-color:#fb923c;background:#fff7ed;color:#9a3412}.quote-archive-dialog{border-color:#fed7aa}.quote-archive-dialog .quote-delete-icon{background:#fff7ed;color:#c2410c}.quote-archive-reason{display:grid;gap:6px;margin-top:12px;color:#475569;font-size:11px;font-weight:850}.quote-archive-reason textarea{resize:vertical;border:1px solid #cbd5e1;border-radius:8px;padding:8px 10px;color:#0f172a;font:inherit;font-weight:500;line-height:1.5;outline:0}.quote-archive-reason textarea:focus{border-color:#fb923c;box-shadow:0 0 0 3px rgb(251 146 60/.12)}.quote-delete-dialog footer button.archive{border-color:#c2410c;background:#c2410c;color:#fff}.quote-delete-dialog footer button.archive:hover:not(:disabled){background:#9a3412}
@media(max-width:1300px){.quote-dashboard-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.quote-speed-chart{grid-column:1/-1}.quote-speed-plot{grid-template-columns:repeat(2,minmax(0,1fr))}.quote-speed-scale{grid-column:1/-1}}
@media(max-width:1100px){.quote-kpi-grid{grid-template-columns:repeat(2,1fr)}.quote-list-toolbar{align-items:stretch;flex-direction:column}.quote-filters{flex-wrap:wrap}.quote-filters select{flex:1}.quote-clear-filter{flex:0 0 auto}.quote-progress-bars button{grid-template-columns:minmax(180px,.85fr) minmax(220px,1.3fr) 82px 18px}}
@media(max-width:820px){.quote-dashboard-grid{grid-template-columns:1fr}.quote-speed-chart,.quote-progress-chart{grid-column:auto}.quote-speed-plot{grid-template-columns:1fr}.quote-dashboard-heading{align-items:stretch;flex-direction:column}.quote-period-switch{align-self:flex-start}.quote-progress-bars button{grid-template-columns:1fr 70px 18px}.quote-progress-title{grid-column:1/-1}.quote-progress-track{grid-column:1}.quote-progress-value{grid-column:2}.quote-progress-bars button>svg{grid-column:3}}
@media(max-width:700px){.quote-home-heading{align-items:stretch;flex-direction:column}.quote-heading-actions{display:grid;grid-template-columns:1fr 1fr}.quote-new-button,.quote-baseline-button{justify-content:center}.quote-kpi-grid{grid-template-columns:repeat(2,1fr)}.quote-search-box{min-width:0}.quote-filters>svg{display:none}.quote-table-footer{grid-template-columns:1fr;text-align:center}.quote-table-footer>span:last-child{text-align:center}.quote-pagination{order:3}.quote-stage-notice{align-items:flex-start}.quote-period-switch{width:100%}.quote-period-switch button{flex:1;justify-content:center;padding:0 7px}.quote-speed-row{grid-template-columns:1fr}.quote-speed-track{margin-top:2px}.quote-progress-bars button{padding:11px}}
@media(max-width:460px){.quote-heading-actions{grid-template-columns:1fr}.quote-kpi-grid{grid-template-columns:1fr 1fr}.quote-kpi-grid article{padding:12px}.quote-kpi-grid strong{font-size:26px}.quote-period-switch button span{display:none}}
@media(prefers-reduced-motion:reduce){.quote-period-switch button,.quote-kpi-grid article,.quote-horizontal-track i,.quote-progress-track i,.quote-progress-bars button>svg,.quote-speed-track>i{animation:none!important;transition:none!important}}
</style>

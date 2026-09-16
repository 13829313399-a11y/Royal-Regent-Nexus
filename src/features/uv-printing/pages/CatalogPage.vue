<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { Coins, Info, RefreshCw, X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type {
  BusinessDate,
  Id,
  Money,
  UvMachine,
  UvPricingQuote,
  UvProcessVersion,
  UvProduct,
  UvRateKind,
  UvRateVersion,
  UvWarning,
} from '../contracts'
import { UV_CONTEXT_KEY, UV_TRANSPORT_KEY } from '../composables/uvPageContext'
import { useUvRequest } from '../composables/useUvRequest'
import { useUvToast } from '../composables/useUvToast'
import { decimalCompare, decimalIsZero, formatDecimal, money } from '../domain/decimal'
import { PRICING_STATE, RATE_KIND_LABELS } from '../domain/status'
import { readAllPages } from '../transport/pagination'
import '../styles/workspace.css'
import PricingStudio from '../components/PricingStudio.vue'
import ProductVersionPanel from '../components/ProductVersionPanel.vue'
import RateVersionDrawer from '../components/RateVersionDrawer.vue'
import UvFilterBar from '../components/UvFilterBar.vue'
import UvNumber from '../components/UvNumber.vue'
import UvStateBlock from '../components/UvStateBlock.vue'
import UvStatusPill from '../components/UvStatusPill.vue'
import UvTable from '../components/UvTable.vue'

/**
 * 产品定价（catalog）工作区页面。
 *
 * - 左栏：产品列表 + 工艺版本与价规；右栏：定价测算台，两侧联动；
 * - 有价 / 零价 / 未定价三态分开显示，未定价永远不显示成 0；
 * - 货号是字符串精确匹配（保留前导零），同名不同货号不合并、不模糊匹配；
 * - 价格读取需要 cost_read，写入需要 cost_write，计件工价另需 payroll_write，
 *   产品与工艺维护需要 master_write；无权限时动作停用并说明后端权威；
 * - 所有读取走 useUvRequest，写入由子组件携带 operation_id + expected_version 完成，
 *   成功后调用 markDirty()，本页 watch revision 重新派生，不保留第二份事实。
 */

const RATE_KINDS: UvRateKind[] = ['commercial', 'piece_wage', 'area']
const RATE_PRIORITY_NOTE = '同一种价规内，精确机台覆盖 > 价组覆盖 > 标准价；同优先级同币种生效区间不得重叠；回退只发生在同一种价规内（缺工价不得回退到商业价，缺港币价不得回退到人民币价）。'

const transportRef = inject(UV_TRANSPORT_KEY)
const context = inject(UV_CONTEXT_KEY)
if (!transportRef || !context) {
  throw new Error('产品定价页面必须在 UV 工作区壳内使用。')
}

const workspace = context.workspace
const businessDate = computed<BusinessDate>(() => workspace.business_date.value)

const canReadCost = computed(() => workspace.can('uv_printing:cost_read'))
const canWriteCost = computed(() => workspace.can('uv_printing:cost_write'))
const canPayrollRead = computed(() => workspace.can('uv_printing:payroll_read'))
const canPayrollWrite = computed(() => workspace.can('uv_printing:payroll_write'))
const canMasterWrite = computed(() => workspace.can('uv_printing:master_write'))
const forbidden = computed(() => workspace.permissionDenied.value)

const { toasts, push, dismiss } = useUvToast()

/* ---------------- 筛选与选择 ---------------- */

const q = ref('')
const priceFilter = ref<'all' | 'priced' | 'zero' | 'unpriced'>('all')
const piecesFilter = ref<'all' | 'confirmed' | 'unconfirmed'>('all')
const sortKey = ref('product_no')
const sortDirection = ref<'asc' | 'desc'>('asc')
const selectedProductId = ref<Id>('')
const selectedVersionId = ref<Id>('')

/* ---------------- 读取：产品 / 机台 / 价规 / 详情 / 测算历史 ---------------- */

const productsRequest = useUvRequest(
  async (signal: AbortSignal) => {
    if (forbidden.value) return null
    return readAllPages((nextScope, nextSignal) => transportRef.value.products(nextScope, nextSignal), workspace.scopeFor({ q: q.value.trim() || undefined }), signal)
  },
  { watchSource: () => [context.revision.value, businessDate.value, q.value, forbidden.value], immediate: true },
)

const machinesRequest = useUvRequest(
  async (signal: AbortSignal) => {
    if (forbidden.value) return null
    return readAllPages((nextScope, nextSignal) => transportRef.value.machines(nextScope, nextSignal), workspace.scopeFor(), signal)
  },
  { watchSource: () => [context.revision.value, businessDate.value, forbidden.value], immediate: true },
)

// 价规金额属于成本口径：没有 cost_read 就完全不请求，也不在页面上假装「未定价」。
const ratesRequest = useUvRequest(
  async (signal: AbortSignal) => {
    if (forbidden.value || !canReadCost.value) return null
    return readAllPages((nextScope, nextSignal) => transportRef.value.rateVersions(nextScope, nextSignal), workspace.scopeFor(), signal)
  },
  { watchSource: () => [context.revision.value, businessDate.value, canReadCost.value, forbidden.value], immediate: true },
)

const detailRequest = useUvRequest(
  async (signal: AbortSignal) => {
    const productId = selectedProductId.value
    if (!productId) return null
    return transportRef.value.productDetail(productId, signal)
  },
  { watchSource: () => [selectedProductId.value, context.revision.value], immediate: true },
)

const quotesRequest = useUvRequest(
  async (signal: AbortSignal) => {
    if (!selectedProductId.value || !canReadCost.value) return null
    return readAllPages((nextScope, nextSignal) => transportRef.value.pricingQuotes(nextScope, nextSignal), workspace.scopeFor({ product_id: selectedProductId.value }), signal)
  },
  { watchSource: () => [selectedProductId.value, context.revision.value, canReadCost.value], immediate: true },
)

/* ---------------- 价规解析（只读展示，服务端为权威） ---------------- */

type RatePriority = 'machine' | 'group' | 'standard'

function ratePriority(rate: UvRateVersion): RatePriority {
  if (rate.machine_id) return 'machine'
  if (rate.price_group) return 'group'
  return 'standard'
}

function priorityScore(rate: UvRateVersion): number {
  const priority = ratePriority(rate)
  return priority === 'machine' ? 3 : priority === 'group' ? 2 : 1
}

/**
 * 生效价规：先在业务日与工艺版本范围内筛选，再按优先级取最高一档。
 * 同档同币种区间不得重叠（由服务端保证）；多币种并存时不做折算、不回退，全部保留。
 */
function effectiveRates(
  rates: UvRateVersion[],
  kind: UvRateKind,
  date: BusinessDate,
  scope: { productId: Id; processVersionId: Id | null },
): UvRateVersion[] {
  const candidates = rates.filter((rate) =>
    rate.rate_kind === kind
    && rate.product_id === scope.productId
    && (!rate.process_version_id || !scope.processVersionId || rate.process_version_id === scope.processVersionId)
    && rate.effective_from <= date
    && (rate.effective_to === null || date <= rate.effective_to),
  )
  if (!candidates.length) return []
  const best = Math.max(...candidates.map(priorityScore))
  return candidates
    .filter((rate) => priorityScore(rate) === best)
    .sort((a, b) => {
      if (a.currency === b.currency) return b.effective_from.localeCompare(a.effective_from)
      if (a.currency === 'HKD') return -1
      if (b.currency === 'HKD') return 1
      return a.currency.localeCompare(b.currency)
    })
}

interface ProductView {
  product: UvProduct
  activeVersion: UvProcessVersion | null
  effectiveCommercial: UvRateVersion[]
  primary: UvRateVersion | null
  state: 'priced' | 'zero' | 'unpriced'
  pricingArea: string
}

const allRates = computed<UvRateVersion[]>(() => ratesRequest.data.value?.items ?? [])
const machines = computed<UvMachine[]>(() => machinesRequest.data.value?.items ?? [])

function activeVersionOf(product: UvProduct): UvProcessVersion | null {
  const versions = product.process_versions ?? []
  return versions.find((version) => version.is_active) ?? versions[versions.length - 1] ?? null
}

const productViews = computed<ProductView[]>(() =>
  (productsRequest.data.value?.items ?? []).map((product) => {
    const activeVersion = activeVersionOf(product)
    const effectiveCommercial = effectiveRates(allRates.value, 'commercial', businessDate.value, {
      productId: product.id,
      processVersionId: activeVersion?.id ?? null,
    })
    const primary = effectiveCommercial[0] ?? null
    const state: ProductView['state'] = !primary
      ? 'unpriced'
      : decimalIsZero(primary.unit_price)
        ? 'zero'
        : 'priced'
    return {
      product,
      activeVersion,
      effectiveCommercial,
      primary,
      state,
      pricingArea: activeVersion?.pricing_area_cm2
        ? `${formatDecimal(activeVersion.pricing_area_cm2, 2)} cm²`
        : '未记录',
    }
  }),
)

const searchedViews = computed(() => productViews.value.filter((view) => {
  if (priceFilter.value !== 'all' && view.state !== priceFilter.value) return false
  if (piecesFilter.value === 'confirmed' && view.activeVersion?.pieces_per_board === null) return false
  if (piecesFilter.value === 'unconfirmed' && view.activeVersion?.pieces_per_board !== null) return false
  return true
}))

const visibleViews = computed<ProductView[]>(() => {
  const list = [...searchedViews.value]
  const direction = sortDirection.value === 'asc' ? 1 : -1
  list.sort((a, b) => {
    if (sortKey.value === 'pricing') return direction * a.state.localeCompare(b.state)
    if (sortKey.value === 'price') {
      return direction * decimalCompare(a.primary?.unit_price ?? '-1', b.primary?.unit_price ?? '-1')
    }
    return direction * a.product.product_no.localeCompare(b.product.product_no, 'en')
  })
  return list
})

function toggleSort(key: string) {
  if (sortKey.value === key) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
    return
  }
  sortKey.value = key
  sortDirection.value = 'asc'
}

function selectProduct(productId: Id) {
  if (selectedProductId.value === productId) return
  selectedProductId.value = productId
  selectedVersionId.value = ''
}

// 选中项只在整个产品集合里消失时重置；筛选条件不悄悄改掉当前选择。
watch(productViews, (views) => {
  if (!views.length) {
    selectedProductId.value = ''
    return
  }
  if (!views.some((view) => view.product.id === selectedProductId.value)) {
    selectedProductId.value = views[0]!.product.id
    selectedVersionId.value = ''
  }
}, { immediate: true })

const selectedView = computed(() =>
  productViews.value.find((view) => view.product.id === selectedProductId.value) ?? null,
)

/**
 * 详情响应可能属于上一个货号（切换选择时旧响应仍在内存里），
 * 只有 id 与当前选择一致才使用，避免把 A 的工艺版本显示在 B 下面。
 */
const detailProduct = computed<UvProduct | null>(() => {
  const data = detailRequest.data.value
  return data && data.id === selectedProductId.value ? data : null
})

const selectedProduct = computed<UvProduct | null>(() =>
  detailProduct.value ?? selectedView.value?.product ?? null,
)

const selectedVersion = computed<UvProcessVersion | null>(() => {
  const versions = selectedProduct.value?.process_versions ?? []
  return versions.find((version) => version.id === selectedVersionId.value)
    ?? versions.find((version) => version.is_active)
    ?? versions[versions.length - 1]
    ?? null
})

const productRates = computed<UvRateVersion[]>(() =>
  allRates.value.filter((rate) => rate.product_id === selectedProduct.value?.id),
)

const effectiveRateIds = computed<string[]>(() => {
  const product = selectedProduct.value
  if (!product) return []
  return RATE_KINDS.flatMap((kind) =>
    effectiveRates(allRates.value, kind, businessDate.value, {
      productId: product.id,
      processVersionId: selectedVersion.value?.id ?? null,
    }).map((rate) => rate.id),
  )
})

const effectiveCommercial = computed<UvRateVersion | null>(() =>
  effectiveRates(allRates.value, 'commercial', businessDate.value, {
    productId: selectedProduct.value?.id ?? '',
    processVersionId: selectedVersion.value?.id ?? null,
  })[0] ?? null,
)

const multiCurrency = computed(() => {
  const product = selectedProduct.value
  if (!product) return false
  const currencies = effectiveRates(allRates.value, 'commercial', businessDate.value, {
    productId: product.id,
    processVersionId: selectedVersion.value?.id ?? null,
  }).map((rate) => rate.currency)
  return new Set(currencies).size > 1
})

const effectiveRateLabel = computed(() => {
  const rate = effectiveCommercial.value
  if (!rate) return ''
  const machine = rate.machine_id
    ? machines.value.find((candidate) => candidate.id === rate.machine_id)?.code ?? rate.machine_id
    : ''
  const priority = rate.machine_id
    ? `精确机台覆盖${machine ? ` · ${machine}` : ''}`
    : rate.price_group
      ? `价组覆盖 · ${rate.price_group}`
      : '标准价'
  const interval = rate.effective_to
    ? `${rate.effective_from} 至 ${rate.effective_to}`
    : `${rate.effective_from} 起`
  return `${priority}，${rate.currency} ${formatDecimal(rate.unit_price, 6)}／件，${interval}`
})

const latestQuote = computed<UvPricingQuote | null>(() => productQuotes.value[0] ?? null)

/** 测算历史必须按货号过滤：同名不同货号不共享测算记录。 */
const productQuotes = computed<UvPricingQuote[]>(() =>
  (quotesRequest.data.value?.items ?? [])
    .filter((quote) => quote.product_id === selectedProductId.value)
    .slice()
    .sort((a, b) => b.created_at.localeCompare(a.created_at)),
)

function primaryMoney(view: ProductView): Money | null {
  const rate = view.primary
  return rate ? money(rate.currency, rate.unit_price) : null
}

function viewRateLabel(view: ProductView): string {
  const rate = view.primary
  if (!rate) return '—'
  if (rate.machine_id) {
    const machine = machines.value.find((candidate) => candidate.id === rate.machine_id)?.code ?? rate.machine_id
    return `精确机台覆盖 · ${machine}`
  }
  if (rate.price_group) return `价组覆盖 · ${rate.price_group}`
  return '标准价'
}

/* ---------------- 状态 ---------------- */

type PageState = 'idle' | 'loading' | 'ready' | 'empty' | 'no-result' | 'forbidden' | 'error' | 'stale'

const listState = computed<PageState>(() => {
  if (forbidden.value) return 'forbidden'
  if (productsRequest.error.value) return 'error'
  if (productsRequest.loading.value && !productsRequest.data.value) return 'loading'
  if (!productsRequest.settled.value) return 'idle'
  const meta = productsRequest.meta.value
  if (meta?.data_mode === 'sample' && !context.isPreview.value) return 'stale'
  const items = productsRequest.data.value?.items ?? []
  if (!items.length) return q.value.trim() ? 'no-result' : 'empty'
  if (!visibleViews.value.length) return 'no-result'
  return 'ready'
})

const rateState = computed<PageState>(() => {
  if (!canReadCost.value) return 'forbidden'
  if (ratesRequest.error.value) return 'error'
  if (ratesRequest.loading.value && !ratesRequest.data.value) return 'loading'
  if (!ratesRequest.settled.value) return 'idle'
  const meta = ratesRequest.meta.value
  if (meta?.data_mode === 'sample' && !context.isPreview.value) return 'stale'
  return 'ready'
})

const pageWarnings = computed<UvWarning[]>(() => [
  ...(productsRequest.meta.value?.warnings ?? []),
  ...(ratesRequest.meta.value?.warnings ?? []),
])

const listErrorDetail = computed(() => {
  const error = productsRequest.error.value
  if (!error) return ''
  return `范围：华康A · ${businessDate.value} · ${q.value.trim() ? `搜索「${q.value.trim()}」` : '全部货号'}｜错误码 ${error.code}`
})

const ratesErrorDetail = computed(() => {
  const error = ratesRequest.error.value
  if (!error) return ''
  return `范围：华康A · 价规版本列表｜错误码 ${error.code}`
})

const filterChips = computed(() => [
  {
    key: 'price',
    label: '价格状态',
    value: priceFilter.value,
    active: priceFilter.value !== 'all',
    options: [
      { value: 'all', label: '全部价格状态' },
      { value: 'priced', label: '有生效执行价' },
      { value: 'zero', label: '零价执行' },
      { value: 'unpriced', label: '未定价' },
    ],
    hint: '未定价不等于 0',
  },
  {
    key: 'pieces',
    label: '每板件数',
    value: piecesFilter.value,
    active: piecesFilter.value !== 'all',
    options: [
      { value: 'all', label: '全部工艺确认情况' },
      { value: 'confirmed', label: '每板件数已确认' },
      { value: 'unconfirmed', label: '每板件数未确认' },
    ],
    hint: '未确认不会被当成 1 件',
  },
])

function onFilterChange(key: string, value: string) {
  if (key === 'price') priceFilter.value = value as typeof priceFilter.value
  if (key === 'pieces') piecesFilter.value = value as typeof piecesFilter.value
}

function clearFilters() {
  priceFilter.value = 'all'
  piecesFilter.value = 'all'
  q.value = ''
}

const listSummary = computed(() => {
  const total = productsRequest.data.value?.total ?? 0
  return `显示 ${visibleViews.value.length} / ${total} 个货号 · 业务日 ${businessDate.value}`
})

/* ---------------- 动作 ---------------- */

const drawerOpen = ref(false)
const drawerRate = ref<UvRateVersion | null>(null)
const drawerKind = ref<UvRateKind>('commercial')

function openCreateRate(kind: UvRateKind) {
  drawerRate.value = null
  drawerKind.value = kind
  drawerOpen.value = true
}

function openEditRate(rate: UvRateVersion) {
  drawerRate.value = rate
  drawerKind.value = rate.rate_kind
  drawerOpen.value = true
}

const canMaintainRate = computed(() => canWriteCost.value)
const rateWriteBlockedReason = computed(() => (canWriteCost.value
  ? ''
  : '维护商业执行价与面积费率需要「成本维护权限」，当前账号没有该权限，操作已停用；是否允许写入以服务端判定为准。'))

function onRateSaved(rate: UvRateVersion) {
  push({
    message: '价规版本已保存',
    detail: `${RATE_KIND_LABELS[rate.rate_kind]} · ${rate.currency} ${formatDecimal(rate.unit_price, 6)}／件 · 生效 ${rate.effective_from}`,
    tone: 'green',
    retryable: false,
  })
}

function onQuoteSaved(quote: UvPricingQuote) {
  push({
    message: '定价测算已保存',
    detail: `「${quote.label}」编号 ${quote.id} · 公式版本 ${quote.result.formula_version}`,
    tone: 'green',
    retryable: false,
  })
}

function onQuoteAdopted(rate: UvRateVersion) {
  push({
    message: '已采用为执行价',
    detail: `${RATE_KIND_LABELS[rate.rate_kind]} · ${rate.currency} ${formatDecimal(rate.unit_price, 6)}／件 · 生效 ${rate.effective_from}`,
    tone: 'teal',
    retryable: false,
  })
}

function onProductSaved(product: UvProduct) {
  push({
    message: '产品资料已保存',
    detail: `${product.product_no} · ${product.name}（版本 v${product.version}）`,
    tone: 'green',
    retryable: false,
  })
}

function onVersionSaved(version: UvProcessVersion) {
  push({
    message: '工艺版本已新增',
    detail: `${version.version_label} · 生效 ${version.effective_from} · 每板件数${
      version.pieces_per_board === null ? '未确认' : ` ${version.pieces_per_board} 件`
    }`,
    tone: 'green',
    retryable: false,
  })
}

async function refreshAll() {
  await Promise.all([
    productsRequest.run(),
    machinesRequest.run(),
    ratesRequest.run(),
    detailRequest.run(),
    quotesRequest.run(),
  ])
}
</script>

<template>
  <div>
    <header class="uv-page-head">
      <div class="uv-page-head__titles">
        <p class="uv-page-head__eyebrow">华康A · UV打印管理 · 产品定价</p>
        <h1>产品定价</h1>
        <p class="uv-page-head__desc">
          左侧维护货号、工艺版本与三种价规，右侧按共享公式测算单价；有价、零价与未定价分开显示，
          未定价不是 0，测算结果需要显式「采用为执行价」才会成为执行价。
        </p>
      </div>
      <div class="uv-page-head__actions">
        <span class="uv-field__hint">{{ listSummary }}</span>
        <Button variant="outline" size="sm" type="button" @click="refreshAll">
          <RefreshCw class="size-3.5" aria-hidden="true" />
          刷新产品与价规
        </Button>
      </div>
    </header>

    <UvFilterBar
      :chips="filterChips"
      :summary="`业务日 ${businessDate} · 共 ${productViews.length} 个货号`"
      @change="onFilterChange"
      @clear="clearFilters"
    />

    <div v-if="forbidden" class="uv-panel">
      <div class="uv-panel__body">
        <UvStateBlock
          state="forbidden"
          subject="产品定价"
          message="当前账号在华康A生产部没有 UV 打印管理的读取权限，页面不会显示任何产品、价规或金额。"
          detail="产品定价页面需要读取权限；价格金额还需要单独的成本读取权限。权限判定以服务端为准。"
        />
      </div>
    </div>

    <div v-else class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)]">
      <div class="grid gap-4">
        <section class="uv-panel" aria-labelledby="uv-catalog-list-title">
          <header class="uv-panel__head">
            <div>
              <h2 id="uv-catalog-list-title" class="uv-panel__title">产品列表</h2>
              <p class="uv-panel__subtitle">
                货号是字符串精确匹配并保留前导零；同名不同货号是两条独立产品，不会按品名合并。
              </p>
            </div>
            <label class="uv-filter">
              <span class="uv-filter__label">搜索货号 / 品名 / 客户</span>
              <input
                v-model="q"
                class="uv-input"
                type="search"
                autocomplete="off"
                placeholder="例如 0007"
              >
            </label>
          </header>

          <div class="uv-panel__body uv-panel__body--flush">
            <div v-if="pageWarnings.length" class="px-4 pt-3">
              <ul class="uv-list">
                <li v-for="warning in pageWarnings" :key="warning.code">
                  <span class="uv-list__dot" aria-hidden="true" />
                  <span>{{ warning.message }}</span>
                </li>
              </ul>
            </div>

            <UvStateBlock
              :state="listState"
              subject="产品列表"
              :message="productsRequest.error.value?.message ?? ''"
              :detail="listErrorDetail"
              :retryable="productsRequest.error.value?.retryable ?? false"
              hint="可以放宽搜索条件或清除价格状态筛选后再看。"
              compact
              @retry="productsRequest.run()"
              @action="clearFilters"
            >
              <UvTable
                :columns="[
                  { key: 'product_no', label: '货号', width: 150, sortable: true, hint: '保留前导零' },
                  { key: 'name', label: '品名', width: 160 },
                  { key: 'customer', label: '客户', width: 130 },
                  { key: 'pricing', label: '价格状态', width: 150, sortable: true, hint: '未定价 ≠ 0' },
                  { key: 'price', label: '当前生效执行价', width: 160, align: 'right', sortable: true },
                  { key: 'source', label: '生效来源', width: 150 },
                  { key: 'process', label: '当前工艺版本', width: 170 },
                  { key: 'actions', label: '操作', width: 120 },
                ]"
                :min-width="1180"
                dense
                caption="产品与当前生效执行价"
                keyboard-hint="使用 Tab 移动到货号按钮或操作按钮，Enter 选择该货号用于右侧测算。"
                :sort-key="sortKey"
                :sort-direction="sortDirection"
                @sort="toggleSort"
              >
                <tr
                  v-for="view in visibleViews"
                  :key="view.product.id"
                  :aria-selected="selectedProductId === view.product.id"
                >
                  <td>
                    <button type="button" class="uv-row-button" @click="selectProduct(view.product.id)">
                      <span class="uv-row-primary uv-mono">{{ view.product.product_no }}</span>
                      <span class="uv-row-sub">{{ view.product.aliases.length ? `别名 ${view.product.aliases.join('、')}` : '无别名' }}</span>
                      <span class="sr-only">选择该货号并载入其工艺版本与生效价规</span>
                    </button>
                  </td>
                  <td>{{ view.product.name }}</td>
                  <td>{{ view.product.customer_name || '未登记' }}</td>
                  <td>
                    <span v-if="!canReadCost" class="uv-num uv-num--pending">无权限查看</span>
                    <UvStatusPill
                      v-else-if="view.state === 'priced'"
                      :status="PRICING_STATE.priced"
                      compact
                    />
                    <UvStatusPill
                      v-else-if="view.state === 'zero'"
                      :status="PRICING_STATE.priced"
                      compact
                      suffix="零价执行"
                    />
                    <UvStatusPill v-else :status="PRICING_STATE.unpriced" compact />
                  </td>
                  <td class="uv-table-cell--right">
                    <template v-if="!canReadCost">
                      <span class="uv-num uv-num--pending">无权限查看</span>
                    </template>
                    <template v-else-if="view.state === 'unpriced'">
                      <UvNumber state="unpriced" />
                      <span class="uv-field__hint">没有生效执行价</span>
                    </template>
                    <template v-else>
                      <UvNumber :money="primaryMoney(view)" unit="/件" />
                      <span v-if="view.state === 'zero'" class="uv-field__hint">显式零价，按 0 计产值</span>
                      <span v-else-if="view.effectiveCommercial.length > 1" class="uv-field__hint">
                        多币种并存：{{ view.effectiveCommercial.map((rate) => rate.currency).join('、') }}，不折算
                      </span>
                    </template>
                  </td>
                  <td>{{ canReadCost ? viewRateLabel(view) : '—' }}</td>
                  <td>
                    <span v-if="view.activeVersion" class="uv-mono">{{ view.activeVersion.version_label }}</span>
                    <span v-else class="uv-num uv-num--missing">无工艺版本</span>
                    <span class="uv-field__hint">
                      每板件数
                      {{ view.activeVersion?.pieces_per_board === null || !view.activeVersion
                        ? '未确认'
                        : `${view.activeVersion.pieces_per_board} 件` }}
                      · 计价面积 {{ view.pricingArea }}
                    </span>
                  </td>
                  <td>
                    <Button
                      variant="ghost"
                      size="xs"
                      type="button"
                      :disabled="!canMaintainRate"
                      :title="rateWriteBlockedReason || undefined"
                      @click="view.primary ? openEditRate(view.primary) : openCreateRate('commercial')"
                    >
                      {{ view.primary ? '编辑价规' : '新增价规' }}
                    </Button>
                  </td>
                </tr>
              </UvTable>
            </UvStateBlock>
          </div>
        </section>

        <UvStateBlock
          v-if="!canReadCost"
          state="forbidden"
          subject="价规与生效价"
          message="读取价格需要「成本读取权限」，当前账号没有该权限，价规金额不会下发到前端。"
          detail="这里不会用「未定价」代替无权限：没有权限就没有结论。权限判定以服务端为准。"
        />
        <UvStateBlock
          v-else-if="rateState === 'error'"
          state="error"
          subject="价规版本"
          :message="ratesRequest.error.value?.message ?? ''"
          :detail="ratesErrorDetail"
          :retryable="ratesRequest.error.value?.retryable ?? false"
          @retry="ratesRequest.run()"
        />
        <UvStateBlock
          v-else-if="rateState === 'loading' || rateState === 'idle'"
          :state="rateState === 'idle' ? 'idle' : 'loading'"
          subject="价规版本"
        />
        <UvStateBlock v-else-if="rateState === 'stale'" state="stale" subject="价规版本" message="服务端返回了样例口径，正式路由不接受该数据源。" />
        <ProductVersionPanel
          v-else
          :product="selectedProduct"
          :product-rates="productRates"
          :machines="machines"
          :business-date="businessDate"
          :effective-rate-ids="effectiveRateIds"
          :selected-version-id="selectedVersion?.id ?? ''"
          :can-read-cost="canReadCost"
          :can-payroll-read="canPayrollRead"
          :can-write-cost="canWriteCost"
          :can-payroll-write="canPayrollWrite"
          :can-master-write="canMasterWrite"
          :priority-note="RATE_PRIORITY_NOTE"
          @select-version="selectedVersionId = $event"
          @create-rate="openCreateRate"
          @edit-rate="openEditRate"
          @saved-product="onProductSaved"
          @saved-version="onVersionSaved"
        />
      </div>

      <div class="grid gap-4">
        <div v-if="multiCurrency" class="uv-callout uv-callout--warning" role="status">
          <Info class="inline size-3.5" aria-hidden="true" />
          该货号在 {{ businessDate }} 存在多个币种的生效商业执行价，系统不折算、也不回退；
          下方测算台按港币优先展示一条，请人工确认目标币种后再采用。
        </div>

        <UvStateBlock
          v-if="!canReadCost"
          state="forbidden"
          subject="定价测算台"
          message="定价测算属于成本口径，需要「成本读取权限」才能打开；当前账号没有该权限。"
          detail="页面不会用样例数字或 0 代替：没有权限就没有测算。权限判定以服务端为准。"
        />
        <PricingStudio
          v-else
          :product="selectedProduct"
          :process-version="selectedVersion"
          :effective-rate="effectiveCommercial"
          :effective-rate-label="effectiveRateLabel"
          :quote="latestQuote"
          :business-date="businessDate"
          :can-read-cost="canReadCost"
          :can-write-cost="canWriteCost"
          :can-payroll-write="canPayrollWrite"
          @saved="onQuoteSaved"
          @adopted="onQuoteAdopted"
        />

        <section v-if="canReadCost" class="uv-panel" aria-labelledby="uv-catalog-history-title">
          <header class="uv-panel__head">
            <div>
              <h2 id="uv-catalog-history-title" class="uv-panel__title">测算历史</h2>
              <p class="uv-panel__subtitle">只读留档：保存过的测算连同输入、公式版本与结果一起保留，采用记录会回写到价规。</p>
            </div>
          </header>
          <div class="uv-panel__body">
            <UvStateBlock
              v-if="quotesRequest.error.value"
              state="error"
              subject="测算历史"
              :message="quotesRequest.error.value.message"
              :retryable="quotesRequest.error.value.retryable"
              compact
              @retry="quotesRequest.run()"
            />
            <UvStateBlock
              v-else-if="quotesRequest.loading.value && !quotesRequest.data.value"
              state="loading"
              subject="测算历史"
              compact
            />
            <p v-else-if="!latestQuote" class="uv-state__hint">
              该货号还没有保存过测算。保存测算会记录输入、公式版本与结果，但不会自动成为执行价。
            </p>
            <dl v-else class="uv-detail-grid">
              <template v-for="quote in productQuotes" :key="quote.id">
                <dt class="uv-field__label">{{ quote.label }}</dt>
                <dd class="uv-field__value">
                  <span class="uv-mono">{{ quote.id }}</span>
                  · 公式 {{ quote.result.formula_version }}
                  · 成本加成报价
                  {{ quote.result.markup_price === null ? '不可计算' : `${formatDecimal(quote.result.markup_price, 6)} ${quote.result.currency}` }}
                  <span v-if="quote.adopted_rate_version_id" class="uv-form-readonly">已采用为执行价</span>
                  <span v-else class="uv-field__hint">仅留档，未采用</span>
                </dd>
              </template>
            </dl>
            <p v-if="latestQuote" class="uv-form-help">
              <Coins class="inline size-3.5" aria-hidden="true" />
              测算历史不参与产值计算：只有「采用为执行价」生成的价规版本才影响报工金额。
            </p>
          </div>
        </section>
      </div>
    </div>

    <RateVersionDrawer
      v-if="selectedProduct"
      :open="drawerOpen"
      :rate="drawerRate"
      :product="selectedProduct"
      :process-versions="selectedProduct.process_versions ?? []"
      :machines="machines"
      :business-date="businessDate"
      :default-kind="drawerKind"
      :can-write-cost="canWriteCost"
      :can-payroll-write="canPayrollWrite"
      :priority-note="RATE_PRIORITY_NOTE"
      @close="drawerOpen = false"
      @saved="onRateSaved"
    />

    <div class="uv-toasts" role="status" aria-live="polite">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        class="uv-toast"
        :class="`uv-toast--${toast.tone}`"
      >
        <p class="uv-toast__title">{{ toast.message }}</p>
        <p class="uv-toast__detail">{{ toast.detail }}</p>
        <button
          type="button"
          class="uv-toast__close"
          :aria-label="`关闭提示：${toast.message}`"
          @click="dismiss(toast.id)"
        >
          <X class="size-3" aria-hidden="true" />
        </button>
      </div>
    </div>
  </div>
</template>

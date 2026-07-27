<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  ArrowDownAZ,
  ArrowUpAZ,
  CalendarDays,
  CircleAlert,
  Filter,
  Search,
  Sparkles,
} from '@lucide/vue'
import type { InjectionMold, InjectionOrder } from '@/types/injectionSchedule'

type SortKey = 'priority' | 'outstandingShots' | 'deliveryDueAt' | 'orderNo'
type QualityFilter = 'all' | 'blocking' | 'warning' | 'source' | 'ready'
type ArmFilter = 'all' | 'double' | 'single' | 'none' | 'unconfirmed'
type DueFilter = 'all' | 'overdue' | 'seven_days' | 'eight_to_thirty' | 'later' | 'missing'
type DataQualityTone = 'blocking' | 'warning' | 'source' | 'clear'

interface OrderDataQuality {
  blockers: string[]
  warnings: string[]
  sources: string[]
}

interface PrimaryDataIssue {
  label: string
  tone: DataQualityTone
}

const SHANGHAI_TIME_ZONE = 'Asia/Shanghai'
const MISSING_FILTER_VALUE = '__missing__'
const sourceInformationPatterns = [
  /^机型要求来自计划表自由文本[:：]/,
  /^Excel 待排记录[:：]未生成计划开始\/完成时间$/,
]
const automaticPublishBlockingPattern =
  /自动发布阻断|阻断|毛重未提供|待定|待确认|资料不足|缺失|缺料|堵啤|半自动|结构化能力|未齐|不可发布|不能发布|冲突|异常|停机/

const props = withDefaults(defineProps<{
  orders: InjectionOrder[]
  molds: InjectionMold[]
  planBaseAt: string
  selectedOrderId?: string
}>(), {
  selectedOrderId: '',
})

const emit = defineEmits<{
  select: [orderId: string]
  inspectMatch: [orderId: string]
}>()

const query = ref('')
const priorityFilter = ref<'all' | InjectionOrder['priority']>('all')
const qualityFilter = ref<QualityFilter>('all')
const machineClassFilter = ref('all')
const colorFilter = ref('all')
const armFilter = ref<ArmFilter>('all')
const dueFilter = ref<DueFilter>('all')
const sortKey = ref<SortKey>('priority')
const sortDirection = ref<'asc' | 'desc'>('asc')
const scrollTop = ref(0)
const tableScrollElement = ref<HTMLElement | null>(null)
const viewportHeight = 610
const rowHeight = 56
const overscan = 4

const moldById = computed(() => new Map(props.molds.map((mold) => [mold.id, mold])))
const selectedOrder = computed(() => (
  props.orders.find((order) => order.id === props.selectedOrderId) ?? null
))
const selectedCount = computed(() => selectedOrder.value ? 1 : 0)
const selectedOutstandingShots = computed(() => (
  selectedOrder.value?.outstandingShots ?? 0
))
const priorityRank: Record<InjectionOrder['priority'], number> = {
  P0: 0,
  P1: 1,
  P2: 2,
  P3: 3,
}

function uniqueTextOptions(values: Array<string | null | undefined>) {
  return [...new Set(
    values
      .map((value) => value?.trim() ?? '')
      .filter((value) => value.length > 0),
  )].sort((left, right) => left.localeCompare(right, 'zh-CN', { numeric: true }))
}

function machineClass(order: InjectionOrder) {
  return moldById.value.get(order.moldId)?.recommendedMachineClass?.trim() || null
}

const machineClassOptions = computed(() => uniqueTextOptions(
  props.orders.map((order) => machineClass(order)),
))
const colorOptions = computed(() => uniqueTextOptions(
  props.orders.map((order) => order.colorName),
))

function classifyDataQualityFlags(flags: string[]): OrderDataQuality {
  const result: OrderDataQuality = {
    blockers: [],
    warnings: [],
    sources: [],
  }

  for (const rawFlag of flags) {
    const flag = rawFlag.trim()
    if (!flag) continue
    if (sourceInformationPatterns.some((pattern) => pattern.test(flag))) {
      result.sources.push(flag)
    } else if (automaticPublishBlockingPattern.test(flag)) {
      result.blockers.push(flag)
    } else {
      result.warnings.push(flag)
    }
  }

  return result
}

const qualityByOrderId = computed(() => new Map(
  props.orders.map((order) => [order.id, classifyDataQualityFlags(order.dataQualityFlags)]),
))

function dataQuality(order: InjectionOrder) {
  return qualityByOrderId.value.get(order.id) ?? {
    blockers: [],
    warnings: [],
    sources: [],
  }
}

function dueDays(order: InjectionOrder) {
  if (!order.deliveryDueAt) return null
  const dueTime = Date.parse(order.deliveryDueAt)
  const businessTime = Date.parse(props.planBaseAt)
  if (Number.isNaN(dueTime) || Number.isNaN(businessTime)) return null
  return Math.ceil((dueTime - businessTime) / 86_400_000)
}

function matchesDueFilter(order: InjectionOrder) {
  if (dueFilter.value === 'all') return true
  const days = dueDays(order)
  if (dueFilter.value === 'missing') return days === null
  if (days === null) return false
  if (dueFilter.value === 'overdue') return days < 0
  if (dueFilter.value === 'seven_days') return days >= 0 && days <= 7
  if (dueFilter.value === 'eight_to_thirty') return days >= 8 && days <= 30
  return days > 30
}

const filteredOrders = computed(() => {
  const normalizedQuery = query.value.trim().toLocaleLowerCase('zh-CN')
  return props.orders
    .filter((order) => {
      if (priorityFilter.value !== 'all' && order.priority !== priorityFilter.value) return false
      const quality = dataQuality(order)
      if (qualityFilter.value === 'blocking' && quality.blockers.length === 0) return false
      if (qualityFilter.value === 'warning' && quality.warnings.length === 0) return false
      if (qualityFilter.value === 'source' && quality.sources.length === 0) return false
      if (qualityFilter.value === 'ready' && quality.blockers.length > 0) return false
      const orderMachineClass = machineClass(order) ?? MISSING_FILTER_VALUE
      if (machineClassFilter.value !== 'all' && orderMachineClass !== machineClassFilter.value) return false
      const orderColor = order.colorName?.trim() || MISSING_FILTER_VALUE
      if (colorFilter.value !== 'all' && orderColor !== colorFilter.value) return false
      const orderArm = order.armRequirement ?? 'unconfirmed'
      if (armFilter.value !== 'all' && orderArm !== armFilter.value) return false
      if (!matchesDueFilter(order)) return false
      if (!normalizedQuery) return true
      const mold = moldById.value.get(order.moldId)
      return [
        order.orderNo,
        order.itemNo ?? '',
        order.productName,
        order.moldId,
        order.colorName ?? '',
        order.materialCode ?? '',
        mold?.recommendedMachineClass ?? '',
      ].some((value) => value.toLocaleLowerCase('zh-CN').includes(normalizedQuery))
    })
    .sort((left, right) => {
      let result = 0
      if (sortKey.value === 'priority') {
        result = priorityRank[left.priority] - priorityRank[right.priority]
      } else if (sortKey.value === 'outstandingShots') {
        result = left.outstandingShots - right.outstandingShots
      } else if (sortKey.value === 'deliveryDueAt') {
        result = (left.deliveryDueAt ?? '9999').localeCompare(right.deliveryDueAt ?? '9999')
      } else {
        result = left.orderNo.localeCompare(right.orderNo, 'zh-CN', { numeric: true })
      }
      return sortDirection.value === 'asc' ? result : -result
    })
})

const visibleCount = computed(() => Math.ceil(viewportHeight / rowHeight) + overscan * 2)
const maximumFirstVisibleIndex = computed(() => Math.max(
  0,
  filteredOrders.value.length - visibleCount.value,
))
const firstVisibleIndex = computed(() => Math.min(
  maximumFirstVisibleIndex.value,
  Math.max(0, Math.floor(scrollTop.value / rowHeight) - overscan),
))
const visibleRows = computed(() => filteredOrders.value.slice(
  firstVisibleIndex.value,
  firstVisibleIndex.value + visibleCount.value,
))
const topSpacerHeight = computed(() => firstVisibleIndex.value * rowHeight)
const bottomSpacerHeight = computed(() => Math.max(
  0,
  (filteredOrders.value.length - firstVisibleIndex.value - visibleRows.value.length) * rowHeight,
))

function handleScroll(event: Event) {
  scrollTop.value = (event.currentTarget as HTMLElement).scrollTop
}

function resetVirtualScroll() {
  scrollTop.value = 0
  if (tableScrollElement.value) tableScrollElement.value.scrollTop = 0
}

watch(
  [
    query,
    priorityFilter,
    qualityFilter,
    machineClassFilter,
    colorFilter,
    armFilter,
    dueFilter,
    sortKey,
    sortDirection,
  ],
  resetVirtualScroll,
)
watch(
  [() => props.orders, () => props.molds],
  resetVirtualScroll,
)

function toggleSort(key: SortKey) {
  if (sortKey.value === key) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDirection.value = 'asc'
  }
}

function sortAria(key: SortKey) {
  if (sortKey.value !== key) return 'none'
  return sortDirection.value === 'asc' ? 'ascending' : 'descending'
}

function isoDateInShanghai(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  const parts = new Intl.DateTimeFormat('en', {
    timeZone: SHANGHAI_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date)
  const partValue = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? ''
  const year = partValue('year')
  if (!year || Number(year) <= 1900) return null
  return `${year}-${partValue('month')}-${partValue('day')}`
}

function displayDate(value: string | null) {
  if (!value) return '交期缺失'
  return isoDateInShanghai(value) ?? '交期缺失'
}

function dueSlack(order: InjectionOrder) {
  const days = dueDays(order)
  if (days === null) return { label: '待确认', tone: 'missing' }
  if (days < 0) return { label: `${days} 天`, tone: 'late' }
  if (days <= 7) return { label: `+${days} 天`, tone: 'risk' }
  return { label: `+${days} 天`, tone: 'safe' }
}

function armFixture(order: InjectionOrder) {
  const mold = moldById.value.get(order.moldId)
  const arm = order.armRequirement === 'double'
    ? '双臂'
    : order.armRequirement === 'single'
      ? '单臂'
      : order.armRequirement === 'none'
        ? '无 / 通用'
        : '半自动 / 待确认'
  const fixtures = order.fixtureRequirements.length > 0
    ? order.fixtureRequirements
    : mold?.fixtureRequirements ?? []
  return [arm, ...fixtures].filter(Boolean).join(' / ')
}

function moldNo(order: InjectionOrder) {
  return moldById.value.get(order.moldId)?.moldNo ?? order.moldId
}

function primaryDataIssue(order: InjectionOrder): PrimaryDataIssue {
  const quality = dataQuality(order)
  if (quality.blockers[0]) return { label: quality.blockers[0], tone: 'blocking' }
  if (quality.warnings[0]) return { label: quality.warnings[0], tone: 'warning' }
  if (quality.sources[0]) return { label: quality.sources[0], tone: 'source' }
  return { label: '未发现自动发布阻断', tone: 'clear' }
}

function dataQualityToneLabel(tone: DataQualityTone) {
  if (tone === 'blocking') return '阻断'
  if (tone === 'warning') return '警告'
  if (tone === 'source') return '来源'
  return '通过'
}

function dataQualitySummary(order: InjectionOrder) {
  const quality = dataQuality(order)
  return `阻断 ${quality.blockers.length} · 警告 ${quality.warnings.length} · 来源 ${quality.sources.length}`
}

function sourceRowLabel(order: InjectionOrder) {
  const sourceRow = order.sourceWorkbookRow ?? order.provenance.sourceRow
  return sourceRow === null ? '来源行待确认' : `计划表第 ${sourceRow} 行`
}

function priorityClass(priority: InjectionOrder['priority']) {
  return `order-priority order-priority--${priority.toLocaleLowerCase()}`
}

const priorityBasisLabel = computed(() => {
  const snapshotDate = isoDateInShanghai(props.planBaseAt)
  return snapshotDate
    ? `按 ${snapshotDate} 快照交期推导`
    : '按当前快照交期推导'
})
</script>

<template>
  <section class="orders-workspace" aria-label="待排订单高密度工作表">
    <div class="orders-toolbar">
      <label class="orders-search">
        <Search aria-hidden="true" />
        <span class="sr-only">搜索待排订单</span>
        <input
          v-model="query"
          name="order-search"
          type="search"
          placeholder="搜索：模号 / 名称 / 单号 / 货号"
        >
      </label>

      <label>
        <span>优先级</span>
        <select v-model="priorityFilter" name="priority-filter">
          <option value="all">全部</option>
          <option value="P0">P0</option>
          <option value="P1">P1</option>
          <option value="P2">P2</option>
          <option value="P3">P3</option>
        </select>
      </label>

      <label>
        <span>资料状态</span>
        <select v-model="qualityFilter" name="quality-filter">
          <option value="all">全部</option>
          <option value="blocking">自动发布阻断</option>
          <option value="warning">需人工复核</option>
          <option value="source">含来源信息</option>
          <option value="ready">无发布阻断</option>
        </select>
      </label>

      <label>
        <span>机型</span>
        <select v-model="machineClassFilter" name="machine-class-filter">
          <option value="all">全部</option>
          <option
            v-for="option in machineClassOptions"
            :key="option"
            :value="option"
          >
            {{ option }}
          </option>
          <option :value="MISSING_FILTER_VALUE">待确认</option>
        </select>
      </label>

      <label>
        <span>颜色</span>
        <select v-model="colorFilter" name="color-filter">
          <option value="all">全部</option>
          <option
            v-for="option in colorOptions"
            :key="option"
            :value="option"
          >
            {{ option }}
          </option>
          <option :value="MISSING_FILTER_VALUE">待定</option>
        </select>
      </label>

      <label>
        <span>机械手</span>
        <select v-model="armFilter" name="arm-filter">
          <option value="all">全部</option>
          <option value="double">双臂</option>
          <option value="single">单臂</option>
          <option value="none">无 / 通用</option>
          <option value="unconfirmed">半自动 / 待确认</option>
        </select>
      </label>

      <label>
        <span>交期</span>
        <select v-model="dueFilter" name="due-filter">
          <option value="all">全部</option>
          <option value="overdue">已超期</option>
          <option value="seven_days">0–7 天</option>
          <option value="eight_to_thirty">8–30 天</option>
          <option value="later">30 天后</option>
          <option value="missing">交期缺失</option>
        </select>
      </label>

      <button
        type="button"
        class="toolbar-button"
        @click="toggleSort('deliveryDueAt')"
      >
        <CalendarDays aria-hidden="true" />
        交期排序
      </button>

      <span class="orders-toolbar__summary">
        未排 <strong>{{ orders.length }}</strong>
        <span aria-hidden="true">·</span>
        筛选 <strong>{{ filteredOrders.length }}</strong>
      </span>

      <span class="quality-inline" role="note">
        <CircleAlert aria-hidden="true" />
        未排订单不生成计划日期；硬约束资料不足时仅可人工确认
      </span>
    </div>

    <div
      ref="tableScrollElement"
      class="orders-table-scroll"
      tabindex="0"
      aria-label="待排订单高密度表格，可横向与纵向滚动"
      @scroll="handleScroll"
    >
      <table
        class="orders-table"
        role="grid"
        aria-multiselectable="false"
        aria-colcount="16"
        :aria-rowcount="filteredOrders.length > 0 ? filteredOrders.length + 1 : 2"
      >
        <thead>
          <tr aria-rowindex="1">
            <th :aria-sort="sortAria('priority')" scope="col">
              <button
                type="button"
                :title="`优先级${priorityBasisLabel}`"
                @click="toggleSort('priority')"
              >
                优先
                <ArrowUpAZ v-if="sortKey === 'priority' && sortDirection === 'asc'" aria-hidden="true" />
                <ArrowDownAZ v-else-if="sortKey === 'priority'" aria-hidden="true" />
              </button>
            </th>
            <th scope="col">工模</th>
            <th scope="col">名称</th>
            <th :aria-sort="sortAria('orderNo')" scope="col">
              <button type="button" @click="toggleSort('orderNo')">单号</button>
            </th>
            <th scope="col">货号</th>
            <th scope="col">机型要求</th>
            <th :aria-sort="sortAria('outstandingShots')" scope="col">
              <button type="button" @click="toggleSort('outstandingShots')">欠数</button>
            </th>
            <th scope="col">日目标</th>
            <th :aria-sort="sortAria('deliveryDueAt')" scope="col">
              <button type="button" @click="toggleSort('deliveryDueAt')">交货完成期</button>
            </th>
            <th scope="col">余量</th>
            <th scope="col">颜色</th>
            <th scope="col">用料</th>
            <th scope="col">机械手 / 夹具</th>
            <th scope="col">候选校验</th>
            <th scope="col">首要阻断 / 资料状态</th>
            <th scope="col">状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="topSpacerHeight > 0" class="spacer-row" aria-hidden="true">
            <td colspan="16" :style="{ height: `${topSpacerHeight}px` }" />
          </tr>
          <tr
            v-for="(order, localIndex) in visibleRows"
            :key="order.id"
            class="order-row"
            :class="{ 'order-row--selected': selectedOrderId === order.id }"
            tabindex="0"
            :aria-rowindex="firstVisibleIndex + localIndex + 2"
            :aria-selected="selectedOrderId === order.id"
            :aria-label="`${order.orderNo}，货号${order.itemNo ?? '缺失'}，${dataQualityToneLabel(primaryDataIssue(order).tone)}：${primaryDataIssue(order).label}，${sourceRowLabel(order)}，未排程`"
            @click="emit('select', order.id)"
            @keydown.enter.self="emit('select', order.id)"
            @keydown.space.self.prevent="emit('select', order.id)"
          >
            <td>
              <span
                :class="priorityClass(order.priority)"
                :title="`${order.priority}，${priorityBasisLabel}`"
                :aria-label="`${order.priority}，${priorityBasisLabel}`"
              >
                {{ order.priority }}
              </span>
            </td>
            <td>
              <button type="button" class="order-primary" @click.stop="emit('inspectMatch', order.id)">
                {{ moldNo(order) }}
              </button>
            </td>
            <td class="order-name" :title="order.productName">{{ order.productName }}</td>
            <td class="mono">{{ order.orderNo }}</td>
            <td class="mono">{{ order.itemNo || '—' }}</td>
            <td>{{ moldById.get(order.moldId)?.recommendedMachineClass ?? '待确认' }}</td>
            <td class="numeric"><strong>{{ order.outstandingShots.toLocaleString('zh-CN') }}</strong></td>
            <td class="numeric">{{ order.targetShotsPerDay?.toLocaleString('zh-CN') ?? '—' }}</td>
            <td>{{ displayDate(order.deliveryDueAt) }}</td>
            <td>
              <span :class="`slack slack--${dueSlack(order).tone}`">{{ dueSlack(order).label }}</span>
            </td>
            <td>{{ order.colorName || '待定' }}</td>
            <td>{{ order.materialCode || '待定' }}</td>
            <td>{{ armFixture(order) }}</td>
            <td>
              <button
                type="button"
                class="match-link"
                @click.stop="emit('inspectMatch', order.id)"
              >
                <Sparkles aria-hidden="true" />
                校验候选
              </button>
            </td>
            <td
              class="order-issue"
              :title="`${primaryDataIssue(order).label}；${dataQualitySummary(order)}；${sourceRowLabel(order)}`"
              :aria-label="`${dataQualityToneLabel(primaryDataIssue(order).tone)}：${primaryDataIssue(order).label}。${dataQualitySummary(order)}。${sourceRowLabel(order)}`"
            >
              <div class="order-issue__primary">
                <span :class="`order-issue__tone order-issue__tone--${primaryDataIssue(order).tone}`">
                  {{ dataQualityToneLabel(primaryDataIssue(order).tone) }}
                </span>
                <span class="order-issue__text">{{ primaryDataIssue(order).label }}</span>
              </div>
              <span class="order-issue__meta">
                {{ dataQualitySummary(order) }} · {{ sourceRowLabel(order) }}
              </span>
            </td>
            <td>
              <span
                class="order-status"
              >
                未排程
              </span>
            </td>
          </tr>
          <tr v-if="bottomSpacerHeight > 0" class="spacer-row" aria-hidden="true">
            <td colspan="16" :style="{ height: `${bottomSpacerHeight}px` }" />
          </tr>
          <tr v-if="filteredOrders.length === 0" aria-rowindex="2">
            <td colspan="16" class="orders-empty">
              <Filter aria-hidden="true" />
              没有符合当前筛选条件的订单
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <footer class="orders-footer">
      <span>
        优先级{{ priorityBasisLabel }} · 当前仅渲染 {{ visibleRows.length }} 行，虚拟窗口支持 1,500+ 订单
      </span>
      <span aria-live="polite">
        已选择 {{ selectedCount }} 条 · 选中欠数
        {{ selectedOutstandingShots.toLocaleString('zh-CN') }}
      </span>
    </footer>
  </section>
</template>

<style scoped>
.orders-workspace {
  display: grid;
  min-height: 0;
  grid-template-rows: auto minmax(0, 1fr) 40px;
  overflow: hidden;
  border: 1px solid #dde5e8;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 12px 28px -28px rgb(15 23 42 / 28%);
}

.orders-toolbar {
  display: flex;
  min-height: 50px;
  align-items: center;
  gap: 8px;
  border-bottom: 1px solid #e8eef0;
  background: #fbfcfc;
  padding: 7px 14px;
}

.orders-search {
  display: flex;
  height: 34px;
  min-width: 240px;
  max-width: 380px;
  flex: 1;
  align-items: center;
  gap: 8px;
  border: 1px solid #dbe5e8;
  border-radius: 8px;
  background: #fff;
  padding: 0 11px;
}

.orders-search:focus-within {
  border-color: #14b8a6;
  box-shadow: 0 0 0 3px rgb(20 184 166 / 14%);
}

.orders-search svg,
.toolbar-button svg {
  width: 15px;
  height: 15px;
  flex: none;
}

.orders-search svg {
  color: #94a3b8;
}

.orders-search input {
  min-width: 0;
  flex: 1;
  border: 0;
  background: transparent;
  color: #0f172a;
  font-size: 12px;
  outline: none;
}

.orders-toolbar label:not(.orders-search) {
  display: flex;
  height: 34px;
  align-items: center;
  gap: 7px;
  border: 1px solid #dbe5e8;
  border-radius: 8px;
  background: #fff;
  padding: 0 9px;
  color: #64748b;
  font-size: 10px;
}

.orders-toolbar select {
  max-width: 126px;
  border: 0;
  background: transparent;
  color: #334155;
  font-size: 11px;
  font-weight: 700;
  outline: none;
}

.orders-toolbar select:focus-visible,
.toolbar-button:focus-visible {
  outline: 2px solid #0f766e;
  outline-offset: 2px;
}

.toolbar-button {
  display: inline-flex;
  height: 34px;
  align-items: center;
  gap: 6px;
  border: 1px solid #dbe5e8;
  border-radius: 8px;
  background: #fff;
  padding: 0 12px;
  color: #334155;
  font-size: 11px;
  font-weight: 700;
}

.toolbar-button:hover {
  border-color: #5eead4;
  background: #ecfdf8;
  color: #0f766e;
}

.orders-toolbar__summary {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 4px;
  color: #64748b;
  font-size: 10px;
}

.orders-toolbar__summary strong {
  color: #0f766e;
  font-weight: 800;
}

.quality-inline {
  display: inline-flex;
  min-width: 0;
  flex: 1;
  align-items: center;
  gap: 5px;
  overflow: hidden;
  color: #64748b;
  font-size: 9.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quality-inline svg {
  width: 14px;
  height: 14px;
  flex: none;
  color: #b45309;
}

.orders-table-scroll {
  min-height: 0;
  overflow: auto;
  outline: none;
  scrollbar-color: #a7b7bd #f8fafc;
  scrollbar-width: thin;
}

.orders-table-scroll:focus-visible {
  box-shadow: inset 0 0 0 3px rgb(20 184 166 / 20%);
}

.orders-table {
  width: 100%;
  min-width: 1760px;
  border-collapse: separate;
  border-spacing: 0;
  color: #334155;
  font-size: 10.5px;
  table-layout: fixed;
}

.orders-table th {
  position: sticky;
  z-index: 5;
  top: 0;
  height: 42px;
  border-bottom: 1px solid #dbe5e8;
  background: #f1f6f6;
  color: #475569;
  font-size: 10px;
  font-weight: 700;
  text-align: left;
}

.orders-table th,
.orders-table td {
  padding: 0 10px;
}

.orders-table th:nth-child(1) { width: 58px; }
.orders-table th:nth-child(2) { width: 132px; }
.orders-table th:nth-child(3) { width: 160px; }
.orders-table th:nth-child(4) { width: 112px; }
.orders-table th:nth-child(5) { width: 120px; }
.orders-table th:nth-child(6) { width: 112px; }
.orders-table th:nth-child(7) { width: 86px; }
.orders-table th:nth-child(8) { width: 78px; }
.orders-table th:nth-child(9) { width: 116px; }
.orders-table th:nth-child(10) { width: 74px; }
.orders-table th:nth-child(11) { width: 84px; }
.orders-table th:nth-child(12) { width: 116px; }
.orders-table th:nth-child(13) { width: 124px; }
.orders-table th:nth-child(14) { width: 106px; }
.orders-table th:nth-child(15) { width: 220px; }
.orders-table th:nth-child(16) { width: 92px; }

.orders-table th button {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
}

.orders-table th button:focus-visible {
  outline: 2px solid #0f766e;
  outline-offset: 2px;
}

.orders-table th svg {
  width: 12px;
  height: 12px;
}

.order-row {
  height: 56px;
  background: #fff;
  cursor: pointer;
}

.order-row:nth-child(even) {
  background: #fafcfc;
}

.order-row:hover,
.order-row--selected {
  background: #eefbf8;
}

.order-row:focus-visible {
  outline: 2px solid #0f766e;
  outline-offset: -2px;
}

.order-row:focus-visible td {
  background: #e6f7f4;
}

.order-row td {
  overflow: hidden;
  height: 56px;
  border-bottom: 1px solid #edf2f3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.order-row--selected td:first-child {
  box-shadow: inset 3px 0 0 #14b8a6;
}

.order-priority {
  display: inline-flex;
  height: 20px;
  min-width: 32px;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  padding: 0 7px;
  font-size: 9px;
  font-weight: 800;
}

.order-priority--p0 { background: #feecec; color: #dc2626; }
.order-priority--p1 { background: #fff4d8; color: #b45309; }
.order-priority--p2 { background: #eaf1ff; color: #2563eb; }
.order-priority--p3 { background: #eef2f7; color: #64748b; }

.order-primary {
  border: 0;
  background: transparent;
  color: #0f172a;
  font-weight: 800;
}

.order-primary:hover {
  color: #0f766e;
  text-decoration: underline;
}

.order-primary:focus-visible {
  outline: 2px solid #0f766e;
  outline-offset: 2px;
}

.order-name {
  color: #0f172a;
  font-weight: 600;
}

.order-issue {
  color: #64748b;
  font-size: 9.5px;
}

.order-issue__primary {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 5px;
}

.order-issue__tone {
  display: inline-flex;
  height: 17px;
  flex: none;
  align-items: center;
  border-radius: 999px;
  padding: 0 5px;
  font-size: 8.5px;
  font-weight: 800;
}

.order-issue__tone--blocking {
  background: #feecec;
  color: #b91c1c;
}

.order-issue__tone--warning {
  background: #fff4d8;
  color: #b45309;
}

.order-issue__tone--source {
  background: #eaf1ff;
  color: #1d4ed8;
}

.order-issue__tone--clear {
  background: #eaf8ef;
  color: #15803d;
}

.order-issue__text {
  min-width: 0;
  overflow: hidden;
  color: #334155;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.order-issue__meta {
  display: block;
  overflow: hidden;
  margin-top: 3px;
  color: #7c8b9a;
  font-size: 8.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 9.5px;
}

.numeric {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.numeric strong {
  color: #0f172a;
}

.slack {
  font-weight: 800;
}

.slack--late { color: #dc2626; }
.slack--risk { color: #d97706; }
.slack--safe { color: #15803d; }
.slack--missing { color: #64748b; }

.match-link {
  display: inline-flex;
  height: 28px;
  align-items: center;
  gap: 5px;
  border: 1px solid #bcebe4;
  border-radius: 7px;
  background: #ecfdf8;
  padding: 0 8px;
  color: #0f766e;
  font-size: 9.5px;
  font-weight: 700;
}

.match-link svg {
  width: 12px;
  height: 12px;
}

.match-link:hover {
  background: #ccfbf1;
}

.match-link:focus-visible {
  outline: 2px solid #0f766e;
  outline-offset: 2px;
}

.order-status {
  display: inline-flex;
  height: 22px;
  align-items: center;
  border-radius: 999px;
  background: #eef2f7;
  padding: 0 8px;
  color: #475569;
  font-size: 9px;
  font-weight: 700;
}

.spacer-row td {
  border: 0;
  padding: 0;
}

.orders-empty {
  height: 180px;
  color: #64748b;
  text-align: center;
}

.orders-empty svg {
  display: inline;
  width: 16px;
  height: 16px;
  margin-right: 6px;
}

.orders-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-top: 1px solid #e8eef0;
  background: #fbfcfc;
  padding: 0 18px;
  color: #64748b;
  font-size: 10px;
}

@media (max-width: 900px) {
  .orders-toolbar {
    flex-wrap: wrap;
  }

  .orders-search {
    min-width: 100%;
  }

  .orders-toolbar__summary,
  .quality-inline {
    display: none;
  }
}
</style>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  FileSpreadsheet,
  RefreshCw,
  Search,
  ShieldCheck,
  Truck,
  X,
} from '@lucide/vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { getApiErrorMessage } from '@/lib/http'
import { importFactorySchedule, listScheduleRows, type ShippingScheduleRow } from '@/api/shippingMail'
import type { ShippingFactoryProfile, ShippingOrder, ShippingOrderStatus } from './contracts'
import { shippingOrderStatusMeta } from './contracts'

const props = defineProps<{ profile: ShippingFactoryProfile }>()
const emit = defineEmits<{ notify: [message: string]; 'open-so-sheet': []; 'open-truck-sheet': []; 'open-supplement': []; 'open-customs': [] }>()

const PAGE_SIZE = 10

const actionCards = [
  { id: 'so-export', title: 'SO排出货表', hint: '按 SO 汇总出货明细', icon: FileSpreadsheet },
  { id: 'vehicle-export', title: '车的排出货表', hint: '按车汇总交仓出货明细', icon: Truck },
  { id: 'si-supplement', title: '补料', hint: 'SI 截止前补料与配补料提醒', icon: CalendarClock },
  { id: 'customs-pack', title: '通关一体化资料', hint: '报关单 / 装箱单 / 发票', icon: ShieldCheck },
]

interface OrderFilters {
  keyword: string
  port: string
  containerType: string
  status: '' | ShippingOrderStatus
  from: string
  to: string
}

function emptyFilters(): OrderFilters {
  return { keyword: '', port: '', containerType: '', status: '', from: '', to: '' }
}

const filters = reactive<OrderFilters>(emptyFilters())

const page = ref(1)
const detail = ref<ShippingOrder | null>(null)
const refreshNote = ref('')
const closeButton = ref<HTMLButtonElement | null>(null)

const scheduleRows = ref<ShippingScheduleRow[]>([])
const scheduleTaskCount = ref(0)
const scheduleLoading = ref(false)
const scheduleError = ref('')
const scheduleKeyword = ref('')

/** 一个备案货号对应多个合同号时，接口已拆行；这里标记出来便于人工核对。 */
const multiContractCodes = computed(() => {
  const contracts = new Map<string, Set<string>>()
  for (const row of scheduleRows.value) {
    const code = row.product_code || '—'
    const set = contracts.get(code) ?? new Set<string>()
    set.add(row.contract_no || '—')
    contracts.set(code, set)
  }
  return new Set([...contracts.entries()].filter(([, set]) => set.size > 1).map(([code]) => code))
})

const visibleScheduleRows = computed(() => {
  const keyword = scheduleKeyword.value.trim().toLowerCase()
  if (!keyword) return scheduleRows.value
  return scheduleRows.value.filter((row) =>
    row.contract_no.toLowerCase().includes(keyword)
    || row.product_code.toLowerCase().includes(keyword)
    || row.product_name.toLowerCase().includes(keyword),
  )
})

async function loadScheduleRows() {
  scheduleLoading.value = true
  scheduleError.value = ''
  try {
    const result = await listScheduleRows(props.profile.factoryId)
    scheduleRows.value = result.rows
    scheduleTaskCount.value = result.tasks
  } catch (error) {
    scheduleError.value = getApiErrorMessage(error)
    scheduleRows.value = []
    scheduleTaskCount.value = 0
  } finally {
    scheduleLoading.value = false
  }
}

function formatNumber(value: number | null | undefined, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return digits ? Number(value).toFixed(digits) : String(Math.round(Number(value)))
}

const scheduleStatusLabels: Record<string, string> = {
  waiting: '待通知', review: '待复核', shipment: '待出货', completed: '已完成', cancelled: '已取消',
}

function scheduleStatusLabel(status: string) {
  return scheduleStatusLabels[status] ?? status
}

const ports = computed(() => [...new Set(props.profile.orders.map((order) => order.port))])
const containerTypes = computed(() => [...new Set(props.profile.orders.map((order) => order.containerType))])
const statuses = computed(() => Object.keys(shippingOrderStatusMeta) as ShippingOrderStatus[])

/** 所有条件都是即时筛选：下拉、日期、关键字变化后立即重新过滤。 */
const filteredOrders = computed(() => {
  const keyword = filters.keyword.trim().toLowerCase()
  return props.profile.orders
    .filter((order) => {
      if (keyword) {
        const matched = order.products.some((product) =>
          product.code.toLowerCase().includes(keyword) || product.name.toLowerCase().includes(keyword),
        )
        if (!matched) return false
      }
      if (filters.port && order.port !== filters.port) return false
      if (filters.containerType && order.containerType !== filters.containerType) return false
      if (filters.status && order.status !== filters.status) return false
      if (filters.from && (!order.departureDate || order.departureDate < filters.from)) return false
      if (filters.to && (!order.departureDate || order.departureDate > filters.to)) return false
      return true
    })
    .sort((a, b) => (b.departureDate || '').localeCompare(a.departureDate || ''))
})

const total = computed(() => filteredOrders.value.length)
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const pagedOrders = computed(() => filteredOrders.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE))

watch(filteredOrders, () => {
  page.value = 1
})

watch(pageCount, (count) => {
  if (page.value > count) page.value = count
})

function clearFilters() {
  Object.assign(filters, emptyFilters())
  refreshNote.value = ''
  page.value = 1
}

function refresh() {
  page.value = 1
  refreshNote.value = `已刷新 · 共 ${total.value} 条`
}

const importing = ref(false)

async function importSchedule(history = false) {
  importing.value = true
  try {
    const result = await importFactorySchedule(props.profile.factoryId, history)
    refresh()
    const label = history ? '厂区总排期旧单' : '厂区总排期'
    refreshNote.value = `${label}已导入 · 新增 ${result.created} / 更新 ${result.updated}`
    emit('notify', `${label}导入完成：新增 ${result.created} 条、更新 ${result.updated} 条排期。`)
    await loadScheduleRows()
  } catch (error) {
    emit('notify', `厂区总排期导入失败：${getApiErrorMessage(error)}`)
  } finally {
    importing.value = false
  }
}

function preview(title: string) {
  emit('notify', `界面预览：${title}尚未接入后端接口。`)
}

function openAction(action: { id: string; title: string }) {
  if (action.id === 'so-export') {
    emit('open-so-sheet')
    return
  }
  if (action.id === 'vehicle-export') {
    emit('open-truck-sheet')
    return
  }
  if (action.id === 'si-supplement') {
    emit('open-supplement')
    return
  }
  if (action.id === 'customs-pack') {
    emit('open-customs')
    return
  }
  preview(action.title)
}

function openDetail(order: ShippingOrder) {
  detail.value = order
  void nextTick(() => closeButton.value?.focus())
}

function closeDetail() {
  detail.value = null
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && detail.value) closeDetail()
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
onMounted(() => { void loadScheduleRows() })
watch(() => props.profile.factoryId, () => { void loadScheduleRows() })

function shortDate(value: string) {
  return value ? value.slice(5).replace('-', '/') : ''
}

function shortDateTime(value: string) {
  return value ? value.slice(5, 16).replace('-', '/') : '—'
}

function statusTone(order: ShippingOrder) {
  return shippingOrderStatusMeta[order.status].tone
}
</script>

<template>
  <div class="space-y-4">
    <section aria-label="船务作业" class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
      <button
        v-for="action in actionCards"
        :key="action.id"
        type="button"
        class="group flex min-w-0 items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-left transition hover:border-teal-200 hover:bg-slate-50/70 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-500"
        :aria-label="action.title"
        @click="openAction(action)"
      >
        <span class="flex size-7 shrink-0 items-center justify-center rounded-md bg-slate-100 text-slate-600 transition group-hover:bg-teal-100/70 group-hover:text-teal-800" aria-hidden="true">
          <component :is="action.icon" class="size-3.5" />
        </span>
        <span class="min-w-0">
          <span class="block truncate text-[13px] font-bold text-slate-900">{{ action.title }}</span>
          <span class="block truncate text-[11px] text-slate-500">{{ action.hint }}</span>
        </span>
      </button>
    </section>

    <section class="enterprise-panel rounded-xl" aria-label="工厂货期排单">
      <header class="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-4 py-4 sm:px-5">
        <div class="min-w-0">
          <h2 class="text-[17px] font-semibold tracking-[-0.02em] text-slate-950">工厂货期排单</h2>
          <p class="mt-1 text-[11px] text-slate-500">
            按开航日期倒序 · 状态默认「已创建」 · 每页 {{ PAGE_SIZE }} 条
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <p class="text-[11px] text-slate-500" role="status" aria-live="polite">
            共 <b class="tabular-nums text-slate-800">{{ total }}</b> 条
            <span v-if="refreshNote" class="ml-1 text-slate-400">{{ refreshNote }}</span>
          </p>
          <button
            type="button"
            class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 text-[12px] font-semibold text-emerald-800 transition hover:bg-emerald-100 disabled:opacity-60"
            :disabled="importing"
            @click="importSchedule(false)"
          >
            <RefreshCw class="size-3.5" :class="importing ? 'animate-spin' : ''" aria-hidden="true" />{{ importing ? '导入中…' : '从厂区总排期导入' }}
          </button>
          <button
            type="button"
            class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-2.5 text-[12px] font-semibold text-amber-800 transition hover:bg-amber-100 disabled:opacity-60"
            :disabled="importing"
            @click="importSchedule(true)"
          >
            <RefreshCw class="size-3.5" :class="importing ? 'animate-spin' : ''" aria-hidden="true" />拾取旧单
          </button>
          <button
            type="button"
            class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-[12px] font-semibold text-slate-600 transition hover:border-teal-200 hover:text-teal-800"
            @click="refresh"
          >
            <RefreshCw class="size-3.5" aria-hidden="true" />刷新
          </button>
        </div>
      </header>

      <div class="border-b border-slate-100 px-4 py-3 sm:px-5">
        <div class="flex flex-wrap items-center gap-2">
          <label class="relative min-w-[190px] flex-1">
            <span class="sr-only">搜索货号或货名</span>
            <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
            <input
              v-model="filters.keyword"
              type="search"
              aria-label="搜索货号或货名"
              placeholder="搜索货号或货名"
              class="h-9 w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-[13px] text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-teal-500 focus:ring-3 focus:ring-teal-500/15"
            >
          </label>
          <select v-model="filters.port" aria-label="筛选港口" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-[12px] text-slate-800 outline-none transition focus:border-teal-500 focus:ring-3 focus:ring-teal-500/15">
            <option value="">全部港口</option>
            <option v-for="port in ports" :key="port" :value="port">{{ port }}</option>
          </select>
          <select v-model="filters.containerType" aria-label="筛选柜型" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-[12px] text-slate-800 outline-none transition focus:border-teal-500 focus:ring-3 focus:ring-teal-500/15">
            <option value="">全部柜型</option>
            <option v-for="type in containerTypes" :key="type" :value="type">{{ type }}</option>
          </select>
          <select v-model="filters.status" aria-label="筛选状态" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-[12px] text-slate-800 outline-none transition focus:border-teal-500 focus:ring-3 focus:ring-teal-500/15">
            <option value="">全部状态</option>
            <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
          </select>
          <div class="flex items-center gap-1">
            <input v-model="filters.from" type="date" aria-label="开航日期起" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-[12px] text-slate-800 outline-none transition focus:border-teal-500 focus:ring-3 focus:ring-teal-500/15">
            <span class="text-[11px] text-slate-400">至</span>
            <input v-model="filters.to" type="date" aria-label="开航日期止" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-[12px] text-slate-800 outline-none transition focus:border-teal-500 focus:ring-3 focus:ring-teal-500/15">
          </div>
        </div>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full min-w-[1500px] border-collapse text-left text-[12px]">
          <thead class="bg-slate-50 text-[11px] font-semibold text-slate-500">
            <tr>
              <th scope="col" class="px-3 py-2">ID</th>
              <th scope="col" class="px-3 py-2">柜号</th>
              <th scope="col" class="px-3 py-2">合同号</th>
              <th scope="col" class="px-3 py-2">备案号</th>
              <th scope="col" class="px-3 py-2">柜型</th>
              <th scope="col" class="px-3 py-2">出场时间</th>
              <th scope="col" class="px-3 py-2">截止时间</th>
              <th scope="col" class="px-3 py-2" title="截关 / 截数期">截重期</th>
              <th scope="col" class="px-3 py-2">港口</th>
              <th scope="col" class="px-3 py-2">收货地</th>
              <th scope="col" class="px-3 py-2">客户</th>
              <th scope="col" class="px-3 py-2 text-right">CBM</th>
              <th scope="col" class="px-3 py-2">特殊要求</th>
              <th scope="col" class="px-3 py-2 text-right">状态</th>
              <th scope="col" class="sticky right-0 z-20 w-[160px] border-l border-slate-100 bg-slate-50 px-3 py-2 text-right shadow-[-8px_0_12px_-12px_rgba(15,23,42,0.35)]">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr
              v-for="order in pagedOrders"
              :key="order.id"
              class="bg-white hover:bg-slate-50/60"
            >
              <td class="px-3 py-2 font-semibold tabular-nums text-slate-800">{{ order.id }}</td>
              <td class="px-3 py-2 tabular-nums text-slate-600">{{ order.containerNo || '—' }}</td>
              <td class="px-3 py-2">
                <button type="button" class="font-semibold tabular-nums text-teal-700 underline-offset-2 hover:underline" :aria-label="`查看 SO ${order.so}`" @click="openDetail(order)">
                  {{ order.so }}
                </button>
              </td>
              <td class="px-3 py-2 tabular-nums text-slate-600">{{ order.products.map((product) => product.code).join(' / ') || '—' }}</td>
              <td class="px-3 py-2 text-slate-700">{{ order.containerType }}</td>
              <td class="px-3 py-2 tabular-nums text-slate-700" :title="order.departureDate || '待排'">{{ order.departureDate ? shortDate(order.departureDate) : '待排' }}</td>
              <td class="px-3 py-2 tabular-nums text-slate-600">{{ shortDateTime(order.siDeadline) }}</td>
              <td class="px-3 py-2 tabular-nums text-slate-600">{{ shortDateTime(order.cutoff) }}</td>
              <td class="px-3 py-2 text-slate-700">{{ order.port }}</td>
              <td class="px-3 py-2 text-slate-700">{{ order.destination }}</td>
              <td class="px-3 py-2 text-slate-700">{{ order.customer }}</td>
              <td class="px-3 py-2 text-right tabular-nums text-slate-800">{{ order.cbm.toFixed(1) }}</td>
              <td class="max-w-[190px] truncate px-3 py-2 text-slate-500" :title="order.special">{{ order.special || '—' }}</td>
              <td class="whitespace-nowrap px-3 py-2"><StatusPill :label="order.status" :tone="statusTone(order)" compact /></td>
              <td
                class="sticky right-0 z-10 border-l border-slate-100 bg-white px-3 py-2 shadow-[-8px_0_12px_-12px_rgba(15,23,42,0.35)]"
              >
                <div class="flex items-center justify-end gap-1">
                  <button type="button" class="h-7 whitespace-nowrap rounded-md border border-slate-200 bg-white px-1.5 text-[11px] font-semibold text-slate-600 hover:border-teal-200 hover:text-teal-800" @click="openDetail(order)">查看</button>
                  <button type="button" class="h-7 whitespace-nowrap rounded-md border border-slate-200 bg-white px-1.5 text-[11px] font-semibold text-slate-600 hover:border-teal-200 hover:text-teal-800" @click="preview(`修改出货单 ${order.so}（${order.id}）`)">修改</button>
                  <button type="button" class="h-7 whitespace-nowrap rounded-md border border-slate-200 bg-white px-1.5 text-[11px] font-semibold text-slate-600 hover:border-teal-200 hover:text-teal-800" @click="preview(`柜单 ${order.so}`)">柜单</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="!pagedOrders.length" class="px-5 py-12 text-center" role="status">
        <p class="text-[13px] font-semibold text-slate-800">没有匹配的出货单</p>
        <p class="mt-1 text-[12px] text-slate-500">调整关键字或筛选条件，或清空筛选查看全部 {{ profile.orders.length }} 票。</p>
        <button type="button" class="mt-3 text-[12px] font-semibold text-teal-700 hover:underline" @click="clearFilters">清空筛选</button>
      </div>

      <footer class="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 px-4 py-3 sm:px-5">
        <p class="text-[11px] text-slate-500">
          第 <span class="tabular-nums">{{ page }}</span> / <span class="tabular-nums">{{ pageCount }}</span> 页
          · 本页 <span class="tabular-nums">{{ pagedOrders.length }}</span> 条
        </p>
        <div class="flex items-center gap-1">
          <button
            type="button"
            class="inline-flex h-7 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 text-[11px] font-semibold text-slate-600 disabled:opacity-40"
            :disabled="page <= 1"
            aria-label="上一页"
            @click="page -= 1"
          >
            <ChevronLeft class="size-3.5" aria-hidden="true" />上一页
          </button>
          <button
            type="button"
            class="inline-flex h-7 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 text-[11px] font-semibold text-slate-600 disabled:opacity-40"
            :disabled="page >= pageCount"
            aria-label="下一页"
            @click="page += 1"
          >
            下一页<ChevronRight class="size-3.5" aria-hidden="true" />
          </button>
        </div>
      </footer>
    </section>

    <Teleport to="body">
      <div
        v-if="detail"
        class="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/40 p-4"
        role="dialog"
        aria-modal="true"
        aria-labelledby="shipping-order-detail-title"
        @click.self="closeDetail"
      >
        <div class="w-[min(760px,calc(100vw-2rem))] max-h-[calc(100vh-2rem)] overflow-y-auto rounded-2xl border border-slate-200 bg-white shadow-2xl">
          <header class="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
            <div class="min-w-0">
              <p class="text-[11px] font-bold uppercase tracking-[0.16em] text-teal-700">Shipment Order</p>
              <h2 id="shipping-order-detail-title" class="mt-1 flex flex-wrap items-baseline gap-2 text-lg font-semibold text-slate-950">
                <span class="tabular-nums">{{ detail.so }}</span>
                <span class="text-sm font-medium text-slate-500">ID {{ detail.id }}</span>
                <StatusPill :label="detail.status" :tone="statusTone(detail)" compact />
              </h2>
            </div>
            <button ref="closeButton" type="button" class="flex size-8 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:border-slate-300 hover:text-slate-800" aria-label="关闭详情" @click="closeDetail">
              <X class="size-4" aria-hidden="true" />
            </button>
          </header>
          <div class="grid gap-3 px-5 py-4 sm:grid-cols-2 lg:grid-cols-3">
            <div class="surface-subtle rounded-lg px-3 py-2">
              <p class="text-[10.5px] font-semibold text-slate-500">柜号</p>
              <p class="mt-0.5 text-[13px] font-semibold tabular-nums text-slate-900">{{ detail.containerNo || '—' }}</p>
            </div>
            <div class="surface-subtle rounded-lg px-3 py-2">
              <p class="text-[10.5px] font-semibold text-slate-500">柜型</p>
              <p class="mt-0.5 text-[13px] font-semibold text-slate-900">{{ detail.containerType }}</p>
            </div>
            <div class="surface-subtle rounded-lg px-3 py-2">
              <p class="text-[10.5px] font-semibold text-slate-500">出场时间</p>
              <p class="mt-0.5 text-[13px] font-semibold tabular-nums text-slate-900">{{ detail.departureDate || '待排' }}</p>
            </div>
            <div class="surface-subtle rounded-lg px-3 py-2">
              <p class="text-[10.5px] font-semibold text-slate-500">SI截止</p>
              <p class="mt-0.5 text-[13px] font-semibold tabular-nums text-slate-900">{{ detail.siDeadline || '—' }}</p>
            </div>
            <div class="surface-subtle rounded-lg px-3 py-2">
              <p class="text-[10.5px] font-semibold text-slate-500">截重期</p>
              <p class="mt-0.5 text-[13px] font-semibold tabular-nums text-slate-900">{{ detail.cutoff || '—' }}</p>
            </div>
            <div class="surface-subtle rounded-lg px-3 py-2">
              <p class="text-[10.5px] font-semibold text-slate-500">港口 / 收货地</p>
              <p class="mt-0.5 text-[13px] font-semibold text-slate-900">{{ detail.port }} · {{ detail.destination }}</p>
            </div>
            <div class="surface-subtle rounded-lg px-3 py-2">
              <p class="text-[10.5px] font-semibold text-slate-500">PL票数 / CBM</p>
              <p class="mt-0.5 text-[13px] font-semibold tabular-nums text-slate-900">{{ detail.plCount }} 票 · {{ detail.cbm.toFixed(1) }} CBM</p>
            </div>
            <div class="surface-subtle rounded-lg px-3 py-2 sm:col-span-2">
              <p class="text-[10.5px] font-semibold text-slate-500">特殊要求</p>
              <p class="mt-0.5 text-[13px] font-semibold text-slate-900">{{ detail.special || '—' }}</p>
            </div>
          </div>
          <footer class="flex flex-wrap justify-end gap-2 border-t border-slate-100 px-5 py-3">
            <button type="button" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-600 hover:border-teal-200 hover:text-teal-800" @click="preview(`修改出货单 ${detail.so}（${detail.id}）`)">修改</button>
            <button type="button" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-600 hover:border-teal-200 hover:text-teal-800" @click="preview(`柜单 ${detail.so}`)">柜单</button>
            <button type="button" class="h-9 rounded-lg bg-teal-700 px-3.5 text-[12px] font-semibold text-white hover:bg-teal-800" @click="closeDetail">关闭</button>
          </footer>
        </div>
      </div>
    </Teleport>
  </div>
</template>

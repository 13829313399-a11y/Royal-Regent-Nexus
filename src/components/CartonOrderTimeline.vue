<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { cartonOrderTimelineApi, type OrderTimelineEvent } from '@/api/cartonOrderTimeline'
import { getApiErrorMessage } from '@/lib/http'

const props = defineProps<{ factoryId: string; customerCode: string; dateFrom: string; dateTo: string; search: string; orderId: string; inventoryKey: string; targetLabel: string; refreshKey: number }>()
const events = ref<OrderTimelineEvent[]>([])
const loading = ref(false)
const error = ref('')
const eventType = ref('')
const sort = ref('ASC')
let version = 0
// Show business changes here; procedural audit evidence remains in the operation log.
const businessTypes = new Set([
  'ORDER_CREATED', 'HISTORY_ORDER_IMPORTED', 'ORDER_APPENDED', 'ORDER_REDUCED',
  'ORDER_CANCELLED', 'ORDER_RETURNED', 'INBOUND', 'OUTBOUND', 'ADJUSTMENT',
  'REVERSAL', 'INVENTORY_LOCATION_CHANGED',
])
const businessEvents = computed(() => events.value.filter(event => businessTypes.has(event.event_type)))
const orderIdentity = computed(() => events.value.at(-1))
const operationKey = (event: OrderTimelineEvent) => `${event.event_type}|${event.event_label}`
const eventOptions = computed(() => [...new Map(businessEvents.value.map(event => [operationKey(event), event.event_label])).entries()])
const visibleEvents = computed(() => {
  const result = businessEvents.value.filter(event => !eventType.value || operationKey(event) === eventType.value)
  return sort.value === 'ASC' ? result : [...result].reverse()
})
function quantity(value: string | null, signed = false) {
  if (value === null) return '—'
  const negative = value.startsWith('-')
  const [whole = '0', fraction = ''] = value.replace(/^-/, '').split('.')
  const decimal = fraction.replace(/0+$/, '')
  const prefix = negative ? '-' : signed && (BigInt(whole) !== 0n || decimal) ? '+' : ''
  return `${prefix}${BigInt(whole).toLocaleString('zh-CN')}${decimal ? `.${decimal}` : ''}`
}
async function load() {
  const request = ++version
  events.value = []
  error.value = ''
  if (!props.orderId && !props.inventoryKey) { loading.value = false; return }
  loading.value = true
  try {
    const result = await cartonOrderTimelineApi.get(props.factoryId, {
      customer_code: props.customerCode, date_from: props.dateFrom, date_to: props.dateTo,
      search: props.search.trim(), order_id: props.orderId, inventory_key: props.inventoryKey,
    })
    if (request === version) events.value = result.events
  } catch (cause) {
    if (request === version) error.value = getApiErrorMessage(cause) || '订单流水读取失败，请重试。'
  } finally { if (request === version) loading.value = false }
}
watch(() => [props.factoryId, props.customerCode, props.dateFrom, props.dateTo, props.search, props.orderId, props.inventoryKey, props.refreshKey], () => {
  eventType.value = ''
  void load()
}, { immediate: true })
onBeforeUnmount(() => { ++version })
</script>

<template>
  <section aria-label="订单流水明细">
    <div v-if="orderIdentity" class="flex flex-wrap gap-x-8 gap-y-2 border-b border-slate-100 px-4 py-3 text-xs text-slate-500" aria-label="订单基本信息">
      <span>客户 <b class="ml-2 text-slate-800">{{ orderIdentity.customer_name || '未填写' }}</b></span>
      <span v-if="orderIdentity.product_name">品名 <b class="ml-2 text-slate-800">{{ orderIdentity.product_name }}</b></span>
    </div>
    <div class="flex flex-wrap items-center gap-3 border-b border-slate-100 bg-slate-50/70 px-4 py-3">
      <label class="flex items-center gap-2 text-xs text-slate-600">操作<select v-model="eventType" aria-label="订单流水操作筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-3"><option value="">全部操作</option><option v-for="[value, label] in eventOptions" :key="value" :value="value">{{ label }}</option></select></label>
      <label class="flex items-center gap-2 text-xs text-slate-600">排序<select v-model="sort" aria-label="订单流水排序" class="h-9 rounded-lg border border-slate-200 bg-white px-3"><option value="ASC">从最早操作开始</option><option value="DESC">最新操作在前</option></select></label>
      <span v-if="targetLabel" class="rounded-lg bg-teal-50 px-3 py-2 text-xs font-semibold text-teal-800">{{ targetLabel }}</span>
      <span class="ml-auto text-xs text-slate-500">{{ visibleEvents.length }} 条记录</span>
    </div>
    <p class="border-b border-slate-100 px-4 py-3 text-xs leading-5 text-slate-500">仅显示订单和库存变化；保存、确认等过程记录可在操作日志查看。</p>
    <p v-if="loading" role="status" class="p-10 text-center text-sm text-slate-500">正在读取订单流水…</p>
    <div v-else-if="error" role="alert" class="flex items-center justify-between gap-3 p-6 text-sm text-red-700"><span>{{ error }}</span><button class="rounded-lg border border-red-200 px-3 py-2 font-semibold" @click="load">重新读取流水</button></div>
    <div v-else class="overflow-x-auto">
      <table class="w-full min-w-[980px] text-left text-xs" aria-label="订单全过程流水表">
        <thead class="bg-slate-50 text-slate-500"><tr><th class="px-4 py-3">时间</th><th class="px-4 py-3">事项</th><th class="px-4 py-3">纸品 / 单据</th><th class="px-4 py-3">数量变动</th><th class="px-4 py-3">备注</th><th class="px-4 py-3">经手人</th></tr></thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="event in visibleEvents" :key="event.id" class="hover:bg-slate-50/60">
            <td class="whitespace-nowrap px-4 py-4"><span class="text-slate-500">{{ event.occurred_at.replace('T', ' ').slice(0, 16) }}</span></td>
            <td class="whitespace-nowrap px-4 py-4 font-bold text-teal-800">{{ event.event_label }}</td>
            <td class="max-w-56 px-4 py-4"><div>{{ event.material_label || '整单' }}</div><div v-if="event.document_no" class="mt-1 break-all font-mono text-slate-500">{{ event.document_no }}</div></td>
            <td class="px-4 py-4 tabular-nums"><template v-if="event.quantity_basis !== 'NONE'"><div class="text-[10px] text-slate-500">{{ event.quantity_basis === 'ORDER_PRODUCT' ? '订单产品' : '库存纸品' }}</div><div class="mt-1 font-bold" :class="event.quantity_change?.startsWith('-') ? 'text-rose-700' : 'text-teal-700'">{{ quantity(event.quantity_change, true) }} {{ event.unit }}</div><div v-if="event.quantity_before !== null && event.quantity_after !== null" class="mt-1 whitespace-nowrap text-slate-500">{{ quantity(event.quantity_before) }} → {{ quantity(event.quantity_after) }} {{ event.unit }}</div></template><span v-else class="text-slate-400">—</span></td>
            <td class="max-w-80 px-4 py-4 leading-5"><div v-if="event.reason">{{ event.reason }}</div><div v-if="event.description" :class="event.reason ? 'mt-1 text-slate-500' : 'text-slate-600'">{{ event.description }}</div><span v-if="!event.reason && !event.description" class="text-slate-400">—</span></td>
            <td class="px-4 py-4">{{ event.actor_name || '未记录' }}</td>
          </tr>
          <tr v-if="!visibleEvents.length"><td colspan="6" class="p-12 text-center text-slate-400">所选条件下没有订单流水记录</td></tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import CartonOrderDetailDialog from '@/components/CartonOrderDetailDialog.vue'
import CartonOrderDetailContent from '@/components/CartonOrderDetailContent.vue'
import CartonOrderSummary from '@/components/CartonOrderSummary.vue'
import CartonOrderTimeline from '@/components/CartonOrderTimeline.vue'
import { cartonSpecialRequestsApi, type UnifiedOrderEntry } from '@/api/cartonSpecialRequests'
import { cartonInventoryReportApi, type InventoryOrderReportRow } from '@/api/cartonInventoryReport'
import { getApiErrorMessage } from '@/lib/http'
import { cartonDate, cartonIdentity, cartonInventoryIdentity, cartonOrderRef, isCartonInventoryIdentity } from './assistantContext'

const props = defineProps<{ factoryId: string; resourceId: string; viewerKey: string; scopeValid: boolean; dateFrom?: unknown; dateTo?: unknown; returnFocus?: HTMLElement | null }>()
const emit = defineEmits<{ close: []; selected: [id: string, label: string, dates: { date_from: string; date_to: string }]; unavailable: [id: string] }>()
const panel = ref<HTMLElement | null>(null)
const order = shallowRef<UnifiedOrderEntry | null>(null)
const inventory = shallowRef<InventoryOrderReportRow | null>(null)
const loading = ref(false), error = ref('')
const dates = ref({ date_from: '', date_to: '' })
const opener = props.returnFocus ?? (document.activeElement instanceof HTMLElement && document.activeElement !== document.body ? document.activeElement : null)
let sequence = 0, controller: AbortController | undefined
const kinds = { PURCHASE: '正单', SAMPLE: '样板', WORKSHOP_MISC: '杂单', SUPPLIER_GIFT: '历史赠送' }
const statuses: Record<string, string> = { DRAFT: '草稿', CONFIRMED: '已确认', PENDING_SUPPLIER: '待供应商',
  SUBMITTED: '待确认锁定', SENT: '已确认锁定', QUOTED: '已确认锁定', READY: '已确认锁定',
  PARTIALLY_RECEIVED: '部分收料', COMPLETED: '已完成', CANCELLED: '已取消' }
const sourceLabel = computed(() => order.value?.order?.order_no || order.value?.special?.request_no
  || (inventory.value ? `${inventory.value.contract_no || '无单库存'} · ${inventory.value.item_no}` : '读取原记录'))
const header = computed(() => order.value?.order ?? order.value?.special)
function numeric(value: unknown) {
  if (value == null || value === '' || !Number.isFinite(Number(value))) throw new Error('原记录的纸品数量不完整，请核对源台账。')
  return Number(value)
}
const papers = computed(() => (order.value?.order?.lines ?? order.value?.special?.lines ?? []).map(line => {
  const required = numeric('required_quantity' in line ? line.required_quantity : line.quantity)
  const received = numeric(line.received_quantity), remaining = numeric(line.remaining_quantity)
  return { id: line.id!, label: line.packaging_type, quality: line.paper_quality, specification: line.specification, unit: line.unit,
    rule: 'usage_quantity' in line && line.usage_quantity != null ? String(line.usage_quantity) : '未记录',
    required, received, remaining, progress: required > 0 ? Math.min(100, Math.round(received / required * 100)) : 0 }
}))
const fields = computed(() => {
  const row = header.value
  if (!row || !order.value) return []
  const purchase = order.value.order
  return [{ label: '客户', value: row.customer_name }, { label: '订单类型', value: kinds[order.value.kind] },
    { label: '订单单号', value: sourceLabel.value }, { label: '状态', value: statuses[row.status] || row.status },
    { label: '要求到货日期', value: purchase?.due_date ?? order.value.special?.required_date },
    { label: '原记录更新时间', value: row.updated_at || '未记录' },
    ...(purchase ? [{ label: '合同号', value: purchase.contract_no }, { label: '货号', value: purchase.item_no },
      { label: '产品名称', value: purchase.product_name }, { label: '产品订单数量', value: purchase.product_order_quantity ?? '未记录' },
      { label: '客户要求交期', value: purchase.customer_due_date || '未记录' },
      { label: '供应商接单', value: purchase.supplier_acceptance?.label ?? '未记录' }] : [])]
})
const inventoryFields = computed(() => {
  const row = inventory.value
  if (!row) return []
  return [{ label: '客户', value: row.customer_name }, { label: '合同号', value: row.contract_no || '无单库存' },
    { label: '货号', value: row.item_no }, { label: '纸品', value: `${row.packaging_type} ${row.paper_quality} ${row.specification}` },
    ...(['opening', 'inbound', 'outbound', 'adjustment', 'ending'] as const).map((key, index) => ({
      label: ['期初', '期间入库', '期间出库', '期间调整', '期末结存'][index]!, value: `${row[`${key}_quantity`]} ${row.unit}` })),
    { label: '最后流水时间', value: row.last_movement_at || '未记录' }, { label: '可分配库存', value: '源系统未提供，需另行核实' }]
})
async function load() {
  const run = ++sequence
  controller?.abort(); controller = new AbortController()
  order.value = null; inventory.value = null; error.value = ''; loading.value = true
  emit('unavailable', props.resourceId)
  try {
    const from = cartonDate(props.dateFrom), to = cartonDate(props.dateTo)
    const ref = cartonOrderRef(props.resourceId)
    if (!props.scopeValid || from === null || to === null || from && to && from > to || (!ref && !isCartonInventoryIdentity(props.resourceId))) {
      throw new Error('原记录入口的厂区、类型或日期无效，请从曜灵来源重新打开。')
    }
    dates.value = { date_from: from, date_to: to }
    if (ref) {
      if (from || to) throw new Error('订单入口不接受库存日期，请重新打开原订单。')
      const rows = await cartonSpecialRequestsApi.selected(props.factoryId, [ref], controller.signal)
      if (run !== sequence) return
      const row = rows.find(entry => cartonIdentity(entry) === props.resourceId)
      if (!row || row.special?.deleted || (row.order ?? row.special)?.factory_id !== props.factoryId) throw new Error('原订单已删除或不在当前可见范围。')
      for (const line of row.order?.lines ?? row.special?.lines ?? []) {
        if (!line.id) throw new Error('原记录缺少纸品标识，请核对源台账。')
        numeric('required_quantity' in line ? line.required_quantity : line.quantity)
        numeric(line.received_quantity); numeric(line.remaining_quantity)
      }
      order.value = row
    } else {
      const report = await cartonInventoryReportApi.get(props.factoryId, { customer_code: '', search: '', ...dates.value }, controller.signal)
      const identified = await Promise.all(report.order_rows.map(async row => [await cartonInventoryIdentity(row.key), row] as const))
      if (run !== sequence) return
      const row = identified.find(([id]) => id === props.resourceId)?.[1]
      if (!row) throw new Error('此库存记录已不在所选日期和厂区的报表中。')
      inventory.value = row
    }
    emit('selected', props.resourceId, sourceLabel.value, { ...dates.value })
  } catch (cause) {
    if (run === sequence) error.value = getApiErrorMessage(cause) || '原记录读取失败，请重试。'
  } finally { if (run === sequence) loading.value = false }
}
function retry() { panel.value?.focus(); void load() }
function restoreFocus(event: Event) {
  // Restore at Reka's close-focus boundary so its own deferred cleanup cannot
  // overwrite focus. Direct route entry has no opener and returns to the main.
  event.preventDefault()
  // Reloading the selected record briefly clears its old selection, so the
  // originating banner button can be replaced while this dialog is open.
  const currentOpener = props.returnFocus ? document.querySelector<HTMLElement>('[data-carton-source-opener]') : null
  const target = opener?.isConnected ? opener : currentOpener ?? document.querySelector<HTMLElement>('[data-yl-help="carton-procurement.overview"]')
  target?.focus({ preventScroll: true })
}
watch(() => [props.resourceId, props.factoryId, props.viewerKey, props.scopeValid, props.dateFrom, props.dateTo], () => { void load() }, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => {
  sequence++; controller?.abort()
})
</script>

<template>
  <CartonOrderDetailDialog :title="`原记录 — ${sourceLabel}`" description="按当前厂区和权限重新读取 · 不修改业务记录" @close="emit('close')" @close-auto-focus="restoreFocus">
    <div ref="panel" tabindex="-1" class="space-y-4 outline-none" data-testid="carton-source-record">
      <p v-if="loading" role="status" class="py-8 text-center text-sm text-slate-500">正在读取原记录…</p>
      <div v-else-if="error" role="alert" class="space-y-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        <p>{{ error }}</p><button type="button" class="rounded-lg border border-red-200 bg-white px-3 py-2 font-semibold" @click="retry">重新读取</button>
      </div>
      <template v-else-if="order"><CartonOrderDetailContent :fields="fields" :rows="papers" /><p class="text-xs text-slate-500">数量保持原纸品单位；待入库量不是库存缺口。已取消单据保留历史数量。</p></template>
      <template v-else-if="inventory">
        <p class="text-xs text-teal-700">报表期间：{{ dates.date_from || '流水起点' }} 至 {{ dates.date_to || '本次读取' }}</p>
        <CartonOrderSummary :fields="inventoryFields" />
        <section aria-label="当前仓位" class="rounded-xl border border-slate-200 p-4 text-xs"><h3 class="font-semibold">当前仓位分布</h3><p class="my-2 text-slate-500">当前累计情况，不随历史报表日期回溯，也不代表可分配量。</p><p v-for="part in inventory.current_positions" :key="part.location">{{ part.location }}：{{ part.quantity }} {{ inventory.unit }}</p><p v-if="!inventory.current_positions?.length">没有正结存仓位记录</p></section>
        <CartonOrderTimeline :factory-id="factoryId" customer-code="" :date-from="dates.date_from" :date-to="dates.date_to" search="" order-id="" :inventory-key="inventory.key" :target-label="sourceLabel" :refresh-key="sequence" />
      </template>
    </div>
  </CartonOrderDetailDialog>
</template>

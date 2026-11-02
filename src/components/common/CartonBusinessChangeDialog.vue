<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle } from 'reka-ui'
import { AlertCircle, Check, LoaderCircle, X } from '@lucide/vue'
import { getApiErrorMessage, http } from '@/lib/http'

interface OrderState {
  order_no: string
  revision: number
  status: string
  product_order_quantity: string | null
  customer_due_date: string | null
  due_date: string
  plan_date_manual: boolean
  lines: Array<{ id: string; packaging_type: string; specification: string; required_quantity: string; unit: string }>
}
interface Preview {
  version: number
  customer_name: string
  contract_no: string
  item_no: string
  source_before: { quantity: string | null; requested_ship_date: string | null; status: string | null }
  source_after: { quantity: string | null; requested_ship_date: string | null; status: string | null }
  reason: string
  before: OrderState | null
  after: OrderState | null
  can_confirm: boolean
  blocked_reason: string
  fingerprint: string
  processed: { processed_by: string; processed_at: string } | null
}
const props = defineProps<{ factoryId: string; recipient: string; dispatchId: string; returnFocus?: HTMLElement }>()
const emit = defineEmits<{ close: []; applied: [] }>()
const preview = ref<Preview | null>(null)
const loading = ref(true)
const saving = ref(false)
const error = ref('')
let active = true
const params = { factory_id: props.factoryId, recipient: props.recipient }
const endpoint = `/customer-order-ledger/inbox/${encodeURIComponent(props.dispatchId)}`
const show = (value: string | null | undefined) => value || '—'
const number = (value: string | null | undefined) => value == null ? '—' : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 6 })
const status = (value: string) => ({ DRAFT: '草稿', CONFIRMED: '待下单', PENDING_SUPPLIER: '已下单', PARTIALLY_RECEIVED: '部分到货', COMPLETED: '已完成', CANCELLED: '已取消' })[value] || value

async function load() {
  loading.value = true
  error.value = ''
  preview.value = null
  try {
    const response = await http.post<Preview>(`${endpoint}/carton-change-preview`, undefined, { params })
    if (active) preview.value = response.data
  } catch (cause) {
    if (active) error.value = getApiErrorMessage(cause)
  } finally {
    if (active) loading.value = false
  }
}
async function confirm() {
  if (!preview.value?.can_confirm || saving.value || error.value) return
  saving.value = true
  try {
    const response = await http.post<Preview>(`${endpoint}/carton-change-confirm`, {
      confirmed: true, fingerprint: preview.value.fingerprint,
    }, { params })
    if (!active) return
    preview.value = response.data
    emit('applied')
  } catch (cause) {
    if (active) error.value = getApiErrorMessage(cause)
  } finally {
    if (active) saving.value = false
  }
}
function close() { if (!saving.value) emit('close') }
function restoreFocus(event: Event) {
  event.preventDefault()
  const target = props.returnFocus?.isConnected ? props.returnFocus
    : Array.from(document.querySelectorAll<HTMLElement>('[data-carton-change]')).find(element => element.dataset.cartonChange === props.dispatchId)
  target?.focus()
}
onMounted(load)
onBeforeUnmount(() => { active = false })
</script>

<template>
  <DialogRoot :open="true" @update:open="(open) => { if (!open) close() }">
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 z-50 bg-slate-950/35" />
      <DialogContent class="change-dialog fixed left-1/2 top-1/2 z-50 flex max-h-[90dvh] w-[min(760px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white text-slate-800 shadow-xl"
        @close-auto-focus="restoreFocus" @interact-outside.prevent @escape-key-down="(event) => { if (saving) event.preventDefault() }">
        <header class="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-5">
          <div>
            <DialogTitle class="text-lg font-semibold">核对业务通知并修改纸箱采购单</DialogTitle>
            <DialogDescription class="mt-1 text-sm text-slate-500">核对下列内容，再确认收到并改单。关闭弹窗不会签收或修改订单。</DialogDescription>
          </div>
          <button type="button" aria-label="关闭" class="rounded p-1 hover:bg-slate-100 disabled:opacity-40" :disabled="saving" @click="close"><X class="size-5" /></button>
        </header>
        <div class="overflow-y-auto px-6 py-5">
          <p v-if="loading" class="flex items-center gap-2 py-8 text-sm text-slate-500" role="status"><LoaderCircle class="size-4 animate-spin" />正在核对业务变更及采购单…</p>
          <div v-if="error" class="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800" role="alert">{{ error }}<button v-if="!saving" type="button" class="ml-3 underline" @click="load">重新核对</button></div>
          <template v-if="preview">
            <p class="font-semibold">{{ preview.customer_name }} · {{ preview.contract_no }} · {{ preview.item_no }}</p>
            <p class="mt-1 text-sm text-slate-500">业务 V{{ preview.version }} · {{ preview.reason || '业务订单变更' }}</p>
            <dl class="mt-4 grid grid-cols-[100px_1fr] gap-x-3 gap-y-2 rounded-lg bg-slate-50 p-4 text-sm">
              <dt class="text-slate-500">业务数量</dt><dd>{{ number(preview.source_before.quantity) }} → {{ number(preview.source_after.quantity) }}</dd>
              <dt class="text-slate-500">客户交期</dt><dd>{{ show(preview.source_before.requested_ship_date) }} → {{ show(preview.source_after.requested_ship_date) }}</dd>
              <template v-if="preview.source_after.status === 'cancelled'"><dt class="text-slate-500">业务状态</dt><dd class="font-medium text-red-700">业务已取消，将核对采购单能否停止供货</dd></template>
            </dl>
            <div v-if="preview.blocked_reason" class="mt-4 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900" role="alert"><AlertCircle class="mt-0.5 size-4 shrink-0" /><div>{{ preview.blocked_reason }}<p class="mt-2">本次尚未改单或签收。请联系客户负责人核对处理。</p></div></div>
            <template v-if="preview.before && preview.after">
              <p class="mb-3 mt-5 font-semibold">采购单 {{ preview.before.order_no }}</p>
              <div class="overflow-x-auto rounded-lg border border-slate-200">
                <table class="w-full min-w-[440px] text-left text-sm">
                  <thead class="bg-slate-50 text-slate-500"><tr><th>变更项目</th><th>修改前</th><th>修改后</th></tr></thead>
                  <tbody>
                    <tr><th>产品数量</th><td>{{ number(preview.before.product_order_quantity) }}</td><td>{{ number(preview.after.product_order_quantity) }}</td></tr>
                    <tr><th>客户交期</th><td>{{ show(preview.before.customer_due_date) }}</td><td>{{ show(preview.after.customer_due_date) }}</td></tr>
                    <tr><th>计划交期</th><td>{{ preview.before.due_date }}</td><td>{{ preview.after.due_date }}<span v-if="preview.after.plan_date_manual" class="block text-xs text-slate-500">保留手工计划日期</span></td></tr>
                    <tr v-for="(line, index) in preview.before.lines" :key="line.id"><th>{{ line.packaging_type }}<span class="block text-xs font-normal text-slate-500">{{ line.specification }}</span></th><td>{{ number(line.required_quantity) }} {{ line.unit }}</td><td>{{ number(preview.after.lines[index]?.required_quantity) }} {{ line.unit }}</td></tr>
                    <tr><th>订单状态</th><td>{{ status(preview.before.status) }}</td><td>{{ status(preview.after.status) }}</td></tr>
                  </tbody>
                </table>
              </div>
              <p class="mt-3 text-sm text-slate-500">已向供应商下单的采购单，会发布变更版本供供应商重新确认；尚未下单的仍需按原流程下单。取消时原数量保留作历史记录。</p>
            </template>
            <div v-if="preview.processed" class="mt-4 rounded-lg bg-emerald-50 p-4 text-sm text-emerald-800" role="status"><p class="flex items-start gap-2"><Check class="size-4 shrink-0" />已处理改单 · {{ preview.processed.processed_by }} · {{ preview.processed.processed_at }}</p><p class="mt-2">同一业务版本只改单一次。若当前收件单位仍显示待签收，请返回列表点“仅签收”。</p></div>
          </template>
        </div>
        <footer class="flex flex-wrap justify-end gap-3 border-t border-slate-200 px-6 py-4">
          <button type="button" class="rounded-lg border border-slate-300 px-4 py-2 text-sm disabled:opacity-40" :disabled="saving" @click="close">{{ preview?.processed ? '关闭' : '暂不处理' }}</button>
          <button v-if="!preview?.processed" type="button" class="flex items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-40" :disabled="loading || saving || !preview?.can_confirm || !!error" @click="confirm"><LoaderCircle v-if="saving" class="size-4 animate-spin" />{{ saving ? '正在改单…' : '确认收到并改单' }}</button>
        </footer>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.change-dialog th, .change-dialog td { padding: 10px 14px; vertical-align: top; border-bottom: 1px solid #e2e8f0; }
.change-dialog th { font-weight: 500; }
.change-dialog tbody tr:last-child > * { border-bottom: 0; }
.change-dialog button:focus-visible { outline: 2px solid #0f766e; outline-offset: 3px; }
</style>

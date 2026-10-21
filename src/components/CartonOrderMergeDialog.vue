<script setup lang="ts">
import '@/features/carton-procurement/layout.css'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { cartonProcurementApi, type CartonOrderResponse } from '@/api/cartonProcurement'
import { mergeOrderContract, mergeStorageKey, type ContractMergeRequest } from '@/features/carton-procurement/contractMerge'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{ source: CartonOrderResponse }>()
const emit = defineEmits<{ close: []; merged: [] }>()
const auth = useAuthStore(), orders = ref<CartonOrderResponse[]>([]), selected = ref<string[]>([])
const contract = ref(''), reason = ref('按客户要求合单'), query = ref(''), error = ref('')
const loading = ref(false), busy = ref(false), completed = ref(false), storageBlocked = ref(false)
const pending = ref<ContractMergeRequest | null>(null), dialog = ref<HTMLElement | null>(null)
const returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
let generation = 0
const canWrite = computed(() => ['carton', 'pmc-warehouse'].some(dept => auth.can('carton_procurement:order_write', props.source.factory_id, dept)))
const storageKey = computed(() => auth.currentUser?.id ? mergeStorageKey(auth.currentUser.id, auth.currentUser.identity?.employment_epoch ?? 1, props.source.factory_id) : '')
const viewer = computed(() => `${storageKey.value}:${auth.authorizationVersion}:${auth.currentUser?.identity?.effective_context_key ?? ''}:${canWrite.value}`)
const locked = computed(() => busy.value || !!pending.value || completed.value || !canWrite.value || storageBlocked.value)
const visible = computed(() => orders.value.filter(order => [order.order_no, order.contract_no, order.customer_po, order.item_no, order.product_name].join(' ').toLowerCase().includes(query.value.trim().toLowerCase())))
const selectedOrders = computed(() => orders.value.filter(order => selected.value.includes(order.order_no)))
async function load() {
  const token = ++generation, key = storageKey.value
  orders.value = []; selected.value = []; pending.value = null; error.value = ''; storageBlocked.value = false
  contract.value = ''; reason.value = '按客户要求合单'; query.value = ''; completed.value = false; busy.value = false
  if (!canWrite.value || !key) { loading.value = false; return }
  loading.value = true
  try {
    const raw = localStorage.getItem(key)
    if (raw) {
      const value = JSON.parse(raw) as ContractMergeRequest
      if (!value || value.factory_id !== props.source.factory_id || typeof value.contract_no !== 'string'
        || typeof value.reason !== 'string' || typeof value.request_id !== 'string' || !/^[A-Za-z0-9_-]{16,96}$/.test(value.request_id)
        || !value.expected_revisions || typeof value.expected_revisions !== 'object' || Array.isArray(value.expected_revisions)
        || Object.keys(value.expected_revisions).length < 2 || Object.keys(value.expected_revisions).length > 50
        || Object.values(value.expected_revisions).some(revision => !Number.isInteger(revision) || revision < 1)) throw new Error('上次合单请求无法读取，请联系维护人员核对；原记录已保留')
      pending.value = value; contract.value = value.contract_no; reason.value = value.reason
      selected.value = Object.keys(value.expected_revisions)
    }
  } catch (cause) { storageBlocked.value = true; error.value = getApiErrorMessage(cause); loading.value = false; return }
  try {
    const result = await cartonProcurementApi.listOrders(props.source.factory_id, { status: 'CONFIRMED', responsibilityScope: 'OWN' })
    if (token !== generation || key !== storageKey.value) return
    orders.value = result.filter(order => order.status === 'CONFIRMED' && order.factory_id === props.source.factory_id
      && order.customer_code === props.source.customer_code && order.supplier_id === props.source.supplier_id)
    if (!pending.value) selected.value = orders.value.some(order => order.id === props.source.id) ? [props.source.order_no] : []
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}
watch(viewer, () => { void load() }, { immediate: true })
void nextTick(() => dialog.value?.querySelector<HTMLElement>('button')?.focus())
function toggle(order: CartonOrderResponse, checked: boolean) {
  if (locked.value) return
  selected.value = checked ? [...new Set([...selected.value, order.order_no])] : selected.value.filter(number => number !== order.order_no)
}
function close() { if (!busy.value) { if (completed.value) emit('merged'); else emit('close') } }
function keys(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.stopPropagation(); close() }
  if (event.key !== 'Tab') return
  const nodes = [...(dialog.value?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled)') ?? [])]
  if (event.shiftKey && document.activeElement === nodes[0]) { event.preventDefault(); nodes.at(-1)?.focus() }
  else if (!event.shiftKey && document.activeElement === nodes.at(-1)) { event.preventDefault(); nodes[0]?.focus() }
}
async function submit() {
  if (busy.value || completed.value || !canWrite.value || storageBlocked.value) return
  const token = generation, key = storageKey.value
  error.value = ''
  if (!pending.value) {
    if (selectedOrders.value.length < 2 || selectedOrders.value.length > 50) { error.value = '请选择 2 至 50 张订单'; return }
    if (!contract.value.trim() || reason.value.trim().length < 4) { error.value = '请填写新合同号和至少 4 字的合单原因'; return }
    const value: ContractMergeRequest = { factory_id: props.source.factory_id, request_id: createRandomUuid(), contract_no: contract.value.trim(), reason: reason.value.trim(), expected_revisions: Object.fromEntries(selectedOrders.value.map(order => [order.order_no, order.revision])) }
    try { localStorage.setItem(key, JSON.stringify(value)); pending.value = value }
    catch { error.value = '无法保存合单请求，尚未提交。请检查浏览器存储后重试'; return }
  }
  busy.value = true
  try {
    await mergeOrderContract(pending.value!)
    if (token !== generation || key !== storageKey.value) return
    completed.value = true
    try { localStorage.removeItem(key) } catch { /* Retained request is safe to replay. */ }
    pending.value = null
  } catch (cause) {
    if (token !== generation || key !== storageKey.value) return
    const status = (cause as { response?: { status?: number } }).response?.status
    const message = getApiErrorMessage(cause)
    if (status && status >= 400 && status < 500 && ![401, 403, 408].includes(status) && !/原合单请求已完成/.test(message)) {
      try { localStorage.removeItem(key); pending.value = null } catch { storageBlocked.value = true }
      orders.value = []; selected.value = []
      error.value = `${message}；本次未合单，请刷新候选订单后重新选择。`
    } else {
      if (status === 401 || status === 403) { orders.value = []; selected.value = [] }
      error.value = `${message}；结果尚未确认，已保留原请求。请核对原合单结果，勿另建重复合同。`
    }
  } finally { if (token === generation) busy.value = false }
}
onBeforeUnmount(() => { generation++; returnFocus?.focus() })
</script>

<template>
  <div class="fixed inset-0 z-[75] flex items-center justify-center bg-slate-950/45 p-4">
    <section ref="dialog" role="dialog" aria-modal="true" aria-label="合单新建合同" class="max-h-[92vh] w-full max-w-5xl overflow-auto rounded-xl bg-white p-5 shadow-xl" @keydown="keys">
      <header class="flex items-start justify-between gap-4"><div><h2 class="text-lg font-bold">合单 · 新建合同</h2><p class="mt-2 text-xs text-slate-600">{{ source.customer_name }} · 选择同厂区、同客户、同供应商的待下单订单，统一归入新合同号。各款 PO、货号、纸品和数量保留，不增加采购需求。</p></div><button type="button" :disabled="busy" class="shrink-0 rounded border px-3 py-2 text-xs" @click="close">关闭</button></header>
      <p v-if="error" role="alert" class="mt-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
      <div v-if="completed" role="status" class="mt-4 rounded border border-teal-200 bg-teal-50 p-4"><p>已将所选订单归入新合同 {{ contract }}，原需求数量和订单编号保留。</p><button type="button" class="mt-3 rounded bg-teal-700 px-4 py-2 text-white" @click="emit('merged')">返回台账核对新合同</button></div>
      <template v-else>
        <div v-if="pending" class="mt-4 rounded border border-amber-200 bg-amber-50 p-3 text-sm">上次合单结果待核对，合同号与所选订单已冻结。<p class="mt-2 break-words">订单：{{ Object.keys(pending.expected_revisions).join('、') }}</p></div>
        <form class="mt-4 space-y-4" @submit.prevent="submit">
          <fieldset :disabled="locked" class="grid gap-3 sm:grid-cols-2"><label class="text-xs font-semibold">新合同号 *<input v-model="contract" aria-label="合单新合同号" maxlength="128" class="mt-1 h-10 w-full rounded border px-3" placeholder="填写一个新的合同号"></label><label class="text-xs font-semibold">合单原因 *<input v-model="reason" aria-label="合单原因" maxlength="500" class="mt-1 h-10 w-full rounded border px-3"></label></fieldset>
          <div v-if="!pending" class="flex flex-wrap items-center gap-3"><input v-model="query" aria-label="搜索可合单订单" placeholder="订单 / 原合同 / PO / 货号" class="h-9 flex-1 rounded border px-3 text-xs" :disabled="locked"><button type="button" :disabled="loading || locked" class="rounded border px-3 py-2 text-xs" @click="load">刷新候选订单</button><b class="text-xs text-teal-800">已选 {{ selected.length }} 张 / 最多 50 张</b></div>
          <div v-if="!pending" class="max-h-[40vh] overflow-auto rounded-lg border carton-table-wrap"><table class="w-full min-w-[700px] text-left text-xs carton-table-fit"><thead class="sticky top-0 bg-slate-50"><tr><th class="p-3">选择</th><th class="p-3">订单 / 原合同</th><th class="p-3">客户 PO</th><th class="p-3">货号 / 产品</th><th class="p-3">纸品需求</th><th class="p-3">计划交期</th></tr></thead><tbody><tr v-for="order in visible" :key="order.id" class="border-t"><td data-label="选择" class="p-3"><input type="checkbox" :aria-label="`合单选择 ${order.order_no}`" :checked="selected.includes(order.order_no)" :disabled="locked || (!selected.includes(order.order_no) && selected.length >= 50)" @change="toggle(order, ($event.target as HTMLInputElement).checked)"></td><td data-label="订单 / 原合同" class="p-3"><b>{{ order.order_no }}</b><p class="mt-1 text-slate-500">{{ order.contract_no }}</p></td><td data-label="客户 PO" class="p-3">{{ order.customer_po || '未填写' }}</td><td data-label="货号 / 产品" class="p-3">{{ order.item_no }}<p class="text-slate-500">{{ order.product_name }}</p></td><td data-label="纸品需求" class="p-3"><p v-for="line in order.lines" :key="line.id">{{ line.packaging_type }} · {{ line.specification }} · {{ line.required_quantity }} {{ line.unit }}</p></td><td data-label="计划交期" class="p-3">{{ order.due_date }}</td></tr><tr v-if="!visible.length"><td colspan="6" class="p-6 text-center text-slate-500">{{ loading ? '正在读取可合单订单…' : '没有符合条件的待下单订单' }}</td></tr></tbody></table></div>
          <div v-if="!pending && selectedOrders.length" class="rounded bg-teal-50 p-3 text-xs leading-6">所选 {{ selectedOrders.length }} 张订单将统一归入：<b>{{ contract || '请填写新合同号' }}</b>。<p class="break-words">{{ selectedOrders.map(order => `${order.order_no}（${order.customer_po || '无 PO'} / ${order.item_no}）`).join('；') }}</p></div>
          <footer class="flex justify-end gap-2 border-t pt-4"><button type="button" :disabled="busy" class="rounded border px-4 py-2 text-sm" @click="close">返回</button><button type="submit" :disabled="busy || loading || !canWrite || storageBlocked || (!pending && selectedOrders.length < 2)" class="rounded bg-teal-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50">{{ busy ? '正在核对并合单…' : pending ? '核对原合单结果 / 重试' : '确认合单并新建合同' }}</button></footer>
        </form>
      </template>
    </section>
  </div>
</template>

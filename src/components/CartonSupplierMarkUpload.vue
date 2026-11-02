<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { cartonSupplierPortalApi, type SupplierMarkUploadResult } from '@/api/cartonSupplierPortal'
import { cartonMarkApi, type CartonMarkBindingTarget, type CartonMarkAssociationTarget } from '@/api/cartonMark'
import { createRandomUuid } from '@/lib/randomUuid'
import { getApiErrorMessage } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'
import { factoryContexts } from '@/data/enterpriseMock'

const props = defineProps<{ factoryIds: string[] }>()
const emit = defineEmits<{ uploaded: [] }>()
const auth = useAuthStore()
const factory = computed(() => props.factoryIds.length === 1 ? props.factoryIds[0]! : '')
const orderId = ref(''), lineId = ref(''), search = ref('')
const canUpload = computed(() => auth.can('carton_supplier:read', '*', '*') && auth.can('carton_supplier:edit', factory.value || '*', '*'))
const orders = ref<CartonMarkBindingTarget[]>([])
const orderKinds = { REGULAR: '正单', SAMPLE: '样板', MISC: '杂单' }
const selectedOrder = computed(() => orders.value.find(order => order.order_id === orderId.value))
const matchingOrders = computed(() => orders.value.filter(order => [order.contract_no, order.customer_name, order.item_no, order.order_no, orderKinds[order.order_kind]].join(' ').toLowerCase().includes(search.value.trim().toLowerCase())))
const files = ref<File[]>([]), outcomes = ref<SupplierMarkUploadResult[]>([])
const input = ref<HTMLInputElement | null>(null)
const busy = ref(false), loading = ref(false), error = ref('')
let generation = 0, controller = new AbortController()
const attempts = new Map<string, string>()
function factoryName(id: string) { return factoryContexts.find(row => row.id === id)?.shortName ?? id }
function chooseFiles(selected: File[]) {
  if (!canUpload.value || !factory.value || busy.value) return
  error.value = ''; outcomes.value = []
  if (selected.length > 50 || selected.some(file => file.size > 20 * 1024 * 1024) || selected.reduce((sum, file) => sum + file.size, 0) > 100 * 1024 * 1024) {
    error.value = '每批最多 50 个文件、合计 100 MB，单个文件最多 20 MB。'; return
  }
  files.value = selected
  attempts.clear()
  if (input.value) input.value.value = ''
}
async function loadOrders() {
  const token = ++generation
  controller.abort(); controller = new AbortController()
  busy.value = false; orders.value = []; orderId.value = ''; lineId.value = ''; search.value = ''; files.value = []; outcomes.value = []; error.value = ''; attempts.clear()
  loading.value = false
  if (!factory.value || !props.factoryIds.includes(factory.value) || !canUpload.value) return
  loading.value = true
  try {
    const result = await cartonMarkApi.bindingTargets(factory.value, true, controller.signal)
    if (token === generation) orders.value = result
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}
async function refreshTargets() {
  if (busy.value || loading.value || !factory.value || !canUpload.value) return
  const token = generation
  loading.value = true; error.value = ''
  try { const rows = await cartonMarkApi.bindingTargets(factory.value, true, controller.signal); if (token === generation) orders.value = rows }
  catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}
async function upload() {
  if (!canUpload.value || !factory.value || !props.factoryIds.includes(factory.value) || busy.value || loading.value || !files.value.length) return
  const selected = selectedOrder.value
  if (orderId.value && !selected || lineId.value && !selected?.lines.some(line => line.id === lineId.value)) { error.value = '订单或纸品已变更，请重新选择。'; return }
  const targets: CartonMarkAssociationTarget[] = selected ? [{ order_kind: selected.order_kind, order_id: selected.order_id, expected_revision: selected.revision, issue_id: selected.issue_id || '', line_id: lineId.value }] : []
  const token = generation, submitted = [...files.value]
  const signature = JSON.stringify([factory.value, submitted.map(file => [file.name, file.size, file.lastModified]), targets])
  if (!attempts.has(signature)) attempts.set(signature, createRandomUuid())
  busy.value = true; error.value = ''
  try {
    const result = await cartonSupplierPortalApi.uploadMarkAssets(factory.value, submitted, undefined, controller.signal, true, { request_id: attempts.get(signature)!, targets })
    if (token !== generation) return
    outcomes.value = result
    files.value = submitted.filter((_, index) => !result[index] || result[index]!.status === 'failed')
    attempts.delete(signature)
    if (result.some(row => row.status !== 'failed')) emit('uploaded')
  } catch (cause) {
    if (token === generation) error.value = `结果尚未确认：${getApiErrorMessage(cause)}。请先刷新资料库核实结果；保持本批文件和订单不变重试，会沿原请求核实，不重复创建。`
  } finally { if (token === generation) busy.value = false }
}
watch([() => props.factoryIds.join('\0'), () => auth.currentUser?.id, () => auth.authorizationVersion], () => {
  void loadOrders()
}, { immediate: true })
watch(canUpload, () => void loadOrders())
watch(orderId, () => { lineId.value = '' })
onBeforeUnmount(() => { generation++; controller.abort() })
</script>

<template>
  <section v-if="canUpload" class="mb-4 rounded-xl border border-teal-200 bg-white p-4 sm:p-5" aria-label="供应商批量上传箱唛">
    <h2 class="font-bold">批量上传箱唛资料</h2>
    <p class="mt-1 text-sm leading-6 text-slate-500">Excel、PDF、图片可以一起上传，沿用页面顶部所选厂区，与该厂区仓库共享，不必先关联订单。内容核对与 QC 沿原流程。</p>
    <p v-if="factory" class="mt-2 text-sm font-semibold text-teal-800">上传到：{{ factoryName(factory) }}</p>
    <p v-else role="status" class="mt-2 text-sm text-amber-700">当前查看全部厂区，请先在页面顶部选择一个厂区，再上传资料。</p>
    <div class="mt-3 flex flex-wrap gap-3">
      <label class="min-w-0 text-sm">搜索关联订单<input v-model="search" aria-label="搜索供应商箱唛上传订单" :disabled="busy || !factory" placeholder="合同 / 客户 / 货号" class="mt-1 block w-full rounded-lg border p-2"></label>
      <label class="min-w-0 flex-1 text-sm">关联订单（选填）<select v-model="orderId" aria-label="供应商箱唛上传订单" :disabled="busy || loading || !factory" class="mt-1 block w-full rounded-lg border bg-white p-2"><option value="">先保存共享资料，稍后关联订单</option><option v-for="order in matchingOrders" :key="order.order_id" :value="order.order_id">{{ orderKinds[order.order_kind] }} · {{ order.customer_name || '未关联客户' }} · {{ order.contract_no || '未填合同' }} · {{ order.order_no }} · {{ order.item_no }}</option></select></label>
      <button type="button" :disabled="busy || loading || !factory" class="self-end rounded-lg border px-3 py-2 text-sm disabled:opacity-50" @click="refreshTargets">刷新可关联订单</button>
    </div>
    <label v-if="selectedOrder && selectedOrder.order_kind !== 'REGULAR'" class="mt-3 block text-sm">对应纸品（选填）<select v-model="lineId" aria-label="供应商箱唛上传纸品" :disabled="busy" class="mt-1 block w-full rounded-lg border bg-white p-2"><option value="">关联整张订单，不指定纸品</option><option v-for="line in selectedOrder.lines" :key="line.id" :value="line.id">{{ line.label }}</option></select></label>
    <dl v-if="selectedOrder" aria-label="供应商箱唛绑定信息" class="mt-3 grid gap-3 rounded-lg border border-teal-100 bg-teal-50 p-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
      <div><dt class="text-slate-500">关联客户</dt><dd class="mt-1 break-all font-semibold">{{ selectedOrder.customer_name }}</dd></div>
      <div><dt class="text-slate-500">合同号</dt><dd class="mt-1 break-all font-semibold">{{ selectedOrder.contract_no }}</dd></div>
      <div v-if="selectedOrder.order_no"><dt class="text-slate-500">订单号</dt><dd class="mt-1 break-all font-semibold">{{ selectedOrder.order_no }}</dd></div>
      <div><dt class="text-slate-500">货号 / ITEM</dt><dd class="mt-1 break-all font-semibold">{{ selectedOrder.item_no }}</dd></div>
    </dl>
    <p v-else class="mt-2 text-xs text-slate-500">未选择订单也能上传，文件会标记为“未关联订单”，仓库可以直接查看。</p>
    <p v-if="orderId" class="mt-2 text-xs text-amber-700">本批文件由本次经办人直接关联所选订单；不改变采购数量、价格或接单状态，也不代表审核通过。</p>
    <p v-if="loading" role="status" class="mt-3 text-sm text-slate-500">正在读取可关联的正单、样板与杂单…</p>
    <div class="mt-4 rounded-lg border-2 border-dashed border-teal-200 bg-teal-50/50 p-4" @dragover.prevent @drop.prevent="chooseFiles(Array.from($event.dataTransfer?.files ?? []))">
      <input ref="input" type="file" multiple accept=".xls,.xlsx,.xlsm,.pdf,.jpg,.jpeg,.png,.webp" class="sr-only" aria-label="供应商批量选择箱唛原文件" :disabled="busy || !factory" @change="chooseFiles(Array.from(($event.target as HTMLInputElement).files ?? []))">
      <div class="flex flex-wrap items-center gap-3"><button type="button" :disabled="busy || !factory" class="rounded-lg border bg-white px-4 py-2 font-semibold disabled:opacity-50" @click="input?.click()">选择 Excel / PDF / 图片</button><span class="text-xs text-slate-500">支持多选或拖入 · 单个 20 MB · 每批 50 个 / 100 MB</span><button type="button" :disabled="busy || loading || !factory || !files.length" class="rounded-lg bg-teal-700 px-4 py-2 font-semibold text-white disabled:opacity-50" @click="upload">{{ busy ? '正在上传…' : `上传共享资料${files.length ? `（${files.length}）` : ''}` }}</button></div>
      <p v-if="files.length" class="mt-3 break-all text-xs">{{ files.map(file => file.name).join('、') }}</p>
      <p v-if="!factory" class="mt-3 text-xs text-amber-700">上传厂区沿用页面顶部选择，不在这里重复选择。</p>
      <p v-else-if="!loading && !orders.length && !error" class="mt-3 text-xs text-amber-700">当前厂区暂无可选订单，仍可先保存共享资料，之后再关联。</p>
    </div>
    <p v-if="error" role="alert" class="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">{{ error }}</p>
    <ul v-if="outcomes.length" role="status" class="mt-3 space-y-2 rounded-lg bg-slate-50 p-3 text-sm"><li v-for="(result, index) in outcomes" :key="index" class="break-all" :class="result.status === 'failed' ? 'text-red-700' : 'text-teal-800'">
      {{ result.file_name }}：{{ ({ created: '已上传共享资料', duplicate: '已存在，跳过重复', failed: '未入库，待核实' })[result.status] }}{{ result.message ? ` — ${result.message}` : '' }}
      <p v-for="order in result.asset?.orders ?? []" :key="order.id" class="mt-1 text-xs text-slate-600">已绑定：{{ factoryName(factory) }} · {{ order.customer_name }} · 合同 {{ order.contract_no }} · PO {{ order.customer_po || '未填写' }} · ITEM {{ order.item_no }}</p>
      <p v-for="order in result.asset?.associations?.filter(row => row.order_kind !== 'REGULAR') ?? result.asset?.special_orders ?? []" :key="`${order.order_id}:${order.line_id || ''}`" class="mt-1 text-xs text-slate-600">已关联：{{ factoryName(factory) }} · {{ orderKinds[order.order_kind] }} · {{ order.order_no }} · {{ order.line_id ? '指定纸品' : '整单资料' }}</p>
      <p v-for="proposal in result.asset?.pending_bindings ?? []" :key="proposal.id" class="mt-1 text-xs text-amber-700">历史关联提议：{{ proposal.contract_no || proposal.order_no }} · {{ proposal.item_no }}</p>
    </li></ul>
  </section>
</template>

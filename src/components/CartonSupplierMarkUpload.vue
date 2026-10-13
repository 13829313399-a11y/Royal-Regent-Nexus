<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { cartonSupplierPortalApi, type SupplierMarkUploadOrder, type SupplierMarkUploadResult } from '@/api/cartonSupplierPortal'
import { getApiErrorMessage } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'
import { factoryContexts } from '@/data/enterpriseMock'

const props = defineProps<{ factoryIds: string[] }>()
const emit = defineEmits<{ uploaded: [] }>()
const auth = useAuthStore()
const factory = ref(''), orderId = ref(''), search = ref('')
const canUpload = computed(() => auth.can('carton_supplier:read', '*', '*') && auth.can('carton_supplier:edit', factory.value || '*', '*'))
const orders = ref<SupplierMarkUploadOrder[]>([])
const selectedOrder = computed(() => orders.value.find(order => order.id === orderId.value))
const matchingOrders = computed(() => orders.value.filter(order => [order.contract_no, order.customer_name, order.item_no, order.document_no, order.order_date].join(' ').toLowerCase().includes(search.value.trim().toLowerCase())))
const files = ref<File[]>([]), outcomes = ref<SupplierMarkUploadResult[]>([])
const input = ref<HTMLInputElement | null>(null)
const busy = ref(false), loading = ref(false), error = ref('')
let generation = 0, controller = new AbortController()
function factoryName(id: string) { return factoryContexts.find(row => row.id === id)?.shortName ?? id }
function chooseFiles(selected: File[]) {
  if (!canUpload.value || busy.value) return
  error.value = ''; outcomes.value = []
  if (selected.length > 50 || selected.some(file => file.size > 20 * 1024 * 1024) || selected.reduce((sum, file) => sum + file.size, 0) > 100 * 1024 * 1024) {
    error.value = '每批最多 50 个文件、合计 100 MB，单个文件最多 20 MB。'; return
  }
  files.value = selected
  if (input.value) input.value.value = ''
}
async function loadOrders() {
  const token = ++generation
  controller.abort(); controller = new AbortController()
  busy.value = false; orders.value = []; orderId.value = ''; search.value = ''; files.value = []; outcomes.value = []; error.value = ''
  loading.value = false
  if (!factory.value || !props.factoryIds.includes(factory.value) || !canUpload.value) return
  loading.value = true
  try {
    const result = await cartonSupplierPortalApi.markUploadOrders(factory.value, controller.signal)
    if (token === generation) orders.value = result
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}
async function upload() {
  if (!canUpload.value || !factory.value || !props.factoryIds.includes(factory.value) || busy.value || loading.value || !files.value.length || !orders.value.length) return
  const selected = orders.value.find(order => order.id === orderId.value)
  if (orderId.value && !selected) { error.value = '采购订单已变更，请重新选择。'; return }
  const token = generation, submitted = [...files.value]
  busy.value = true; error.value = ''
  try {
    const result = await cartonSupplierPortalApi.uploadMarkAssets(factory.value, submitted, selected, controller.signal)
    if (token !== generation) return
    outcomes.value = result
    files.value = submitted.filter((_, index) => !result[index] || result[index]!.status === 'failed')
    if (result.some(row => row.status !== 'failed')) emit('uploaded')
  } catch (cause) {
    if (token === generation) error.value = `上传未完成：${getApiErrorMessage(cause)}。请刷新资料库确认；重试会跳过已有文件。`
  } finally { if (token === generation) busy.value = false }
}
watch([() => props.factoryIds.join('\0'), () => auth.currentUser?.id, () => auth.authorizationVersion], () => {
  factory.value = props.factoryIds.length === 1 ? props.factoryIds[0]! : ''
  void loadOrders()
}, { immediate: true })
watch([factory, canUpload], () => void loadOrders())
onBeforeUnmount(() => { generation++; controller.abort() })
</script>

<template>
  <section v-if="canUpload" class="mb-4 rounded-xl border border-teal-200 bg-white p-4 sm:p-5" aria-label="供应商批量上传箱唛">
    <h2 class="font-bold">批量上传箱唛资料</h2>
    <p class="mt-1 text-sm leading-6 text-slate-500">Excel、PDF、图片可以一起选择。先选收货厂区，再按合同自动匹配自己的已生成采购单，或直接选择本次采购单。客户、合同、PO 和货号从采购单带入，无需手工填写；没有唯一匹配时会提示选择订单重试。入库后可选择 Excel / PDF 一起核对。</p>
    <div class="mt-3 flex flex-wrap gap-3">
      <label class="min-w-0 text-sm">上传厂区<select v-model="factory" aria-label="供应商箱唛上传厂区" :disabled="busy" class="mt-1 block w-full rounded-lg border bg-white p-2"><option value="">请选择上传厂区</option><option v-for="id in factoryIds" :key="id" :value="id">{{ factoryName(id) }}</option></select></label>
      <label class="min-w-0 text-sm">搜索采购订单<input v-model="search" aria-label="搜索供应商箱唛上传订单" :disabled="busy || !factory" placeholder="合同 / 客户 / 货号" class="mt-1 block w-full rounded-lg border p-2"></label>
      <label class="min-w-0 flex-1 text-sm">本次关联采购订单<select v-model="orderId" aria-label="供应商箱唛上传订单" :disabled="busy || loading || !factory" class="mt-1 block w-full rounded-lg border bg-white p-2"><option value="">自动按合同匹配（推荐）</option><option v-for="order in matchingOrders" :key="order.id" :value="order.id">{{ order.customer_name }} · {{ order.contract_no }} · {{ order.item_no }} · {{ order.document_no }} · {{ order.order_date }}</option></select></label>
    </div>
    <dl v-if="selectedOrder" aria-label="供应商箱唛绑定信息" class="mt-3 grid gap-3 rounded-lg border border-teal-100 bg-teal-50 p-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
      <div><dt class="text-slate-500">绑定客户</dt><dd class="mt-1 break-all font-semibold">{{ selectedOrder.customer_name }}</dd></div>
      <div><dt class="text-slate-500">合同号</dt><dd class="mt-1 break-all font-semibold">{{ selectedOrder.contract_no }}</dd></div>
      <div><dt class="text-slate-500">客户 PO</dt><dd class="mt-1 break-all font-semibold">{{ selectedOrder.customer_po || '采购单未填写' }}</dd></div>
      <div><dt class="text-slate-500">货号 / ITEM</dt><dd class="mt-1 break-all font-semibold">{{ selectedOrder.item_no }}</dd></div>
    </dl>
    <p v-else class="mt-2 text-xs text-slate-500">自动匹配时，各文件上传结果会显示实际绑定的客户、合同和货号。</p>
    <p v-if="orderId" class="mt-2 text-xs text-amber-700">本批文件都关联所选订单；文件中识别到不同合同会提示核实。无合同名称的照片可在这里选订单后上传。</p>
    <p v-if="loading" role="status" class="mt-3 text-sm text-slate-500">正在读取可上传的采购订单…</p>
    <div class="mt-4 rounded-lg border-2 border-dashed border-teal-200 bg-teal-50/50 p-4" @dragover.prevent @drop.prevent="chooseFiles(Array.from($event.dataTransfer?.files ?? []))">
      <input ref="input" type="file" multiple accept=".xls,.xlsx,.xlsm,.pdf,.jpg,.jpeg,.png,.webp" class="sr-only" aria-label="供应商批量选择箱唛原文件" :disabled="busy" @change="chooseFiles(Array.from(($event.target as HTMLInputElement).files ?? []))">
      <div class="flex flex-wrap items-center gap-3"><button type="button" :disabled="busy" class="rounded-lg border bg-white px-4 py-2 font-semibold disabled:opacity-50" @click="input?.click()">选择 Excel / PDF / 图片</button><span class="text-xs text-slate-500">支持多选或拖入 · 单个 20 MB · 每批 50 个 / 100 MB</span><button type="button" :disabled="busy || loading || !factory || !orders.length || !files.length" class="rounded-lg bg-teal-700 px-4 py-2 font-semibold text-white disabled:opacity-50" @click="upload">{{ busy ? '正在识别并上传…' : `上传并自动关联${files.length ? `（${files.length}）` : ''}` }}</button></div>
      <p v-if="files.length" class="mt-3 break-all text-xs">{{ files.map(file => file.name).join('、') }}</p>
      <p v-if="!factory" class="mt-3 text-xs text-amber-700">请选择文件对应的收货厂区。</p>
      <p v-else-if="!loading && !orders.length && !error" class="mt-3 text-xs text-amber-700">当前厂区暂无可关联的本供应商已下单订单。</p>
    </div>
    <p v-if="error" role="alert" class="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">{{ error }}</p>
    <ul v-if="outcomes.length" role="status" class="mt-3 space-y-2 rounded-lg bg-slate-50 p-3 text-sm"><li v-for="(result, index) in outcomes" :key="index" class="break-all" :class="result.status === 'failed' ? 'text-red-700' : 'text-teal-800'">
      {{ result.file_name }}：{{ ({ created: '已入库并关联订单', duplicate: '已存在，跳过重复', failed: '未入库，待核实' })[result.status] }}{{ result.message ? ` — ${result.message}` : '' }}
      <p v-for="order in result.asset?.orders ?? []" :key="order.id" class="mt-1 text-xs text-slate-600">已绑定：{{ factoryName(factory) }} · {{ order.customer_name }} · 合同 {{ order.contract_no }} · PO {{ order.customer_po || '未填写' }} · ITEM {{ order.item_no }}</p>
    </li></ul>
  </section>
</template>

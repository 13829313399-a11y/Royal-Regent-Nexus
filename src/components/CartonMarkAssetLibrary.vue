<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Download, Eye, FileSpreadsheet, FileText, FolderOpen, RefreshCw, UploadCloud } from '@lucide/vue'
import { cartonSupplierPortalApi } from '@/api/cartonSupplierPortal'
import { http } from '@/lib/http'
import { cartonMarkApi, type CartonMarkAsset, type CartonMarkAssetUploadResult } from '@/api/cartonMark'
import { getApiErrorMessage, getApiErrorMessageAsync } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'
import { factoryContexts } from '@/data/enterpriseMock'

const props = defineProps<{ factoryId: string; supplierFactories?: string[]; orderId?: string; readOnly?: boolean; supplier?: boolean; uploadOnly?: boolean; checkEnabled?: boolean }>()
const emit = defineEmits<{ use: [asset: CartonMarkAsset] }>()
const auth = useAuthStore()
const canRead = computed(() => props.supplier ? auth.can('carton_supplier:read') : ['pmc-warehouse', 'carton', 'qa', 'qc'].some(d => auth.can('carton_mark:read', props.factoryId, d)))
const canWrite = computed(() => !props.supplier && !props.readOnly && ['pmc-warehouse', 'carton'].some(d => auth.can('carton_mark:template_upload', props.factoryId, d)))
const entries = ref<CartonMarkAsset[]>([])
const results = ref<CartonMarkAssetUploadResult[]>([])
const pendingFiles = ref<File[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const query = ref('')
const onlyUnbound = ref(false)
const kindFilter = ref('ALL')
const bindingFilter = ref('ALL'), customerFilter = ref(''), sort = ref('LATEST')
const customers = computed(() => [...new Set(entries.value.flatMap(asset => asset.orders.map(order => order.customer_name)))].sort((a, b) => a.localeCompare(b, 'zh-CN')))
function clearFilters() { query.value = ''; kindFilter.value = 'ALL'; onlyUnbound.value = false; bindingFilter.value = 'ALL'; customerFilter.value = '' }
const busy = ref(false)
const loading = ref(false)
const error = ref('')
const binding = ref<CartonMarkAsset | null>(null)
const contract = ref('')
const orderId = ref('')
let controller = new AbortController()
let generation = 0
let listSequence = 0
const statuses = { BOUND: '已关联订单', NO_ORDER: '等待订单', UNBOUND: '待关联', AMBIGUOUS: '需确认订单' }
function factoryDisplayName(id: string) { return factoryContexts.find(factory => factory.id === id)?.shortName ?? id }
const visible = computed(() => entries.value.filter(asset => {
  const key = query.value.trim().toLowerCase()
  return (kindFilter.value === 'ALL' || asset.kind === kindFilter.value) && (!onlyUnbound.value || asset.binding_status !== 'BOUND')
    && (bindingFilter.value === 'ALL' || asset.binding_status === bindingFilter.value)
    && (!customerFilter.value || asset.orders.some(order => order.customer_name === customerFilter.value)) && (!key ||
    [asset.file_name, asset.contract_number, ...asset.orders.flatMap(o => [o.order_no, o.customer_name, o.item_no])].some(v => v.toLowerCase().includes(key)))
}))
const groups = computed(() => {
  const grouped = new Map<string, { key: string; factory: string; contract: string; customer: string; latest: string; assets: CartonMarkAsset[] }>()
  for (const asset of visible.value) {
    const customer = [...new Set(asset.orders.map(order => order.customer_name))].sort().join('、')
    const key = JSON.stringify([asset.factory_id, asset.contract_number || asset.id, customer])
    const group = grouped.get(key) ?? { key, factory: asset.factory_id, contract: asset.contract_number, customer, latest: '', assets: [] }
    group.assets.push(asset); if (asset.created_at > group.latest) group.latest = asset.created_at
    grouped.set(key, group)
  }
  return [...grouped.values()].sort((a, b) => (sort.value === 'CONTRACT' ? a.contract.localeCompare(b.contract, 'zh-CN', { numeric: true }) : sort.value === 'CUSTOMER' ? a.customer.localeCompare(b.customer, 'zh-CN') : b.latest.localeCompare(a.latest)) || a.key.localeCompare(b.key))
    .map(group => ({ ...group, assets: group.assets.sort((a, b) => a.kind.localeCompare(b.kind) || b.created_at.localeCompare(a.created_at) || a.id.localeCompare(b.id)) }))
})

async function refresh() {
  const current = generation
  const sequence = ++listSequence
  const factory = props.factoryId
  loading.value = true
  error.value = ''
  try {
    let records: CartonMarkAsset[]
    if (props.supplier) {
      const scopes = [...new Set(props.supplierFactories ?? (factory ? [factory] : []))]
      const batches = await Promise.all(scopes.map(async scope => {
        try { return { scope, assets: await cartonSupplierPortalApi.markAssets(scope, controller.signal) } }
        catch (cause) { throw new Error(`${factoryDisplayName(scope)}：${getApiErrorMessage(cause)}`) }
      }))
      records = batches.flatMap(({ scope, assets }) => assets.map(asset => ({
        ...asset, factory_id: scope, sha256: '', bound_order_id: null, recognition_source: '', candidates: [], warning: '',
        revision: 0, created_by_name: '', binding_status: 'BOUND' as const, orders: asset.orders.map(order => ({ ...order, order_no: '' })),
      })))
      records.sort((a, b) => b.created_at.localeCompare(a.created_at) || a.factory_id.localeCompare(b.factory_id) || b.id.localeCompare(a.id))
    } else records = await cartonMarkApi.listAssets(factory, props.orderId, controller.signal)
    if (current === generation && sequence === listSequence) entries.value = records
  } catch (cause) {
    if (current === generation && sequence === listSequence) {
      if (props.supplier) entries.value = []
      error.value = getApiErrorMessage(cause)
    }
  } finally {
    if (current === generation && sequence === listSequence) loading.value = false
  }
}

function selectFiles(files: File[]) {
  if (!canWrite.value || busy.value) return
  pendingFiles.value = files
  results.value = []
  error.value = ''
  if (fileInput.value) fileInput.value.value = ''
}

async function upload() {
  if (!canWrite.value || busy.value || !pendingFiles.value.length) return
  const current = generation
  const factory = props.factoryId
  const files = [...pendingFiles.value]
  if (files.length > 50 || files.reduce((sum, file) => sum + file.size, 0) > 100 * 1024 * 1024 || files.some(file => file.size > 20 * 1024 * 1024)) {
    error.value = '每批最多 50 个文件、合计 100 MB，单个文件最多 20 MB。'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const outcomes = await cartonMarkApi.uploadAssets(factory, files, controller.signal)
    if (current !== generation) return
    results.value = outcomes
    pendingFiles.value = files.filter((_, index) => outcomes[index]?.status === 'failed')
    await refresh()
  } catch (cause) {
    if (current === generation) error.value = `上传未完成：${getApiErrorMessage(cause)}。可重试，重复文件会跳过。`
  } finally {
    if (current === generation) busy.value = false
  }
}

function edit(asset: CartonMarkAsset) {
  binding.value = asset
  contract.value = asset.contract_number
  orderId.value = asset.bound_order_id || ''
  error.value = ''
}

async function saveBinding() {
  if (!binding.value || busy.value || !canWrite.value) return
  const current = generation
  const selected = binding.value
  busy.value = true
  try {
    await cartonMarkApi.bindAsset(props.factoryId, selected, contract.value.trim(), orderId.value, controller.signal)
    if (current !== generation) return
    binding.value = null
    await refresh()
  } catch (cause) {
    if (current === generation) error.value = getApiErrorMessage(cause)
  } finally {
    if (current === generation) busy.value = false
  }
}

async function download(asset: CartonMarkAsset) {
  const current = generation
  try {
    const blob = props.supplier
      ? await cartonSupplierPortalApi.downloadMarkAsset(asset.id, asset.factory_id, controller.signal)
      : await cartonMarkApi.downloadAsset(props.factoryId, asset.id, controller.signal)
    if (current !== generation) return
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = asset.file_name
    anchor.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (cause) {
    const detail = await getApiErrorMessageAsync(cause)
    if (current === generation) error.value = detail
  }
}

async function archive(asset: CartonMarkAsset) {
  if (busy.value || !canWrite.value || !window.confirm(`将“${asset.file_name}”移出资料仓库？原文件会保留，重新上传可恢复。`)) return
  const current = generation
  busy.value = true
  try {
    await cartonMarkApi.archiveAsset(props.factoryId, asset, controller.signal)
    if (current === generation) await refresh()
  } catch (cause) {
    if (current === generation) error.value = getApiErrorMessage(cause)
  } finally {
    if (current === generation) busy.value = false
  }
}

function previewUrl(asset: CartonMarkAsset) {
  return props.supplier ? cartonSupplierPortalApi.previewMarkAssetUrl(asset.id, asset.factory_id)
    : http.getUri({ url: `/carton-mark/assets/${encodeURIComponent(asset.id)}/document`, params: { factory_id: props.factoryId, preview: true } })
}
function chooseFiles() { if (canWrite.value && !busy.value) fileInput.value?.click() }
defineExpose({ chooseFiles, refresh })
watch(() => [props.factoryId, props.supplierFactories?.join('\0'), props.orderId, props.supplier, canRead.value], () => {
  generation++
  controller.abort()
  controller = new AbortController()
  entries.value = []
  results.value = []
  pendingFiles.value = []
  binding.value = null
  contract.value = ''
  orderId.value = ''
  error.value = ''
  busy.value = false
  loading.value = false
  clearFilters(); sort.value = 'LATEST'
  if (canRead.value) void refresh()
}, { immediate: true })
onBeforeUnmount(() => { generation++; controller.abort() })
</script>

<template>
  <section v-if="canRead" class="rounded-xl border border-slate-200 bg-white p-4 sm:p-5" :style="{ '--asset-actions-width': canWrite ? '14rem' : '10rem' }" aria-label="箱唛资料仓库">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 class="flex items-center gap-2 text-base font-bold text-slate-900"><FolderOpen class="size-5 text-teal-700" />{{ uploadOnly ? '批量上传箱唛资料' : '箱唛资料库' }}</h2>
        <p class="mt-1 text-xs leading-5 text-slate-500">{{ supplier ? '仓库按合同号共享给已下单订单的原文件，可随时查看和下载。' : orderId ? '此订单关联的箱唛原文件，可直接查看和下载。' : 'PDF、Excel 可分别上传，按合同号自动关联本厂订单并共享给对应供应商；未识别的文件先保存，之后再关联。' }}</p>
        <p v-if="!supplier && !orderId" class="text-xs leading-5 text-slate-500">建议文件名：4500000123.pdf / 4500000123_Shipping Mark.xlsx。原文件共享与 Excel / PDF 内容核对分别管理。</p>
      </div>
      <button v-if="!uploadOnly" type="button" :disabled="busy || loading" class="inline-flex items-center gap-1 rounded-lg border px-3 py-2 text-xs disabled:opacity-50" @click="refresh"><RefreshCw class="size-3.5" />刷新</button>
    </div>
    <div v-if="canWrite" class="mt-4 rounded-lg border-2 border-dashed border-teal-200 bg-teal-50/50 p-4" @dragover.prevent @drop.prevent="selectFiles(Array.from($event.dataTransfer?.files ?? []))">
      <input ref="fileInput" type="file" multiple accept=".pdf,.xls,.xlsx,.xlsm" class="hidden" aria-label="批量选择箱唛原文件" @change="selectFiles(Array.from(($event.target as HTMLInputElement).files ?? []))">
      <div class="flex flex-wrap items-center gap-3">
        <button type="button" :disabled="busy" class="inline-flex items-center gap-2 rounded-lg border bg-white px-3 py-2 font-semibold disabled:opacity-50" @click="chooseFiles"><UploadCloud class="size-4" />选择多个文件</button>
        <span class="text-xs text-slate-500">或拖入文件 · 单个 20 MB · 每批最多 50 个 / 100 MB</span>
        <button type="button" :disabled="busy || !pendingFiles.length" class="rounded-lg bg-teal-700 px-4 py-2 font-semibold text-white disabled:opacity-50" @click="upload">{{ busy ? '处理中…' : `上传入库${pendingFiles.length ? `（${pendingFiles.length}）` : ''}` }}</button>
      </div>
      <p v-if="pendingFiles.length" class="mt-2 break-all text-xs text-slate-600">{{ pendingFiles.map(f => f.name).join('、') }}</p>
    </div>
    <p v-if="error" role="alert" class="mt-3 rounded-lg bg-red-50 p-3 text-xs text-red-700">{{ error }}</p>
    <div v-if="results.length" class="mt-3 space-y-1 rounded-lg bg-slate-50 p-3 text-xs" role="status">
      <p v-for="(result, index) in results" :key="index" :class="result.status === 'failed' ? 'text-red-700' : 'text-teal-800'" class="break-all">{{ result.file_name }}：{{ ({ created: '已入库', duplicate: '已存在，跳过重复', restored: '已恢复', failed: '未入库' })[result.status] }}{{ result.message ? ` — ${result.message}` : '' }}</p>
    </div>
    <template v-if="!uploadOnly">
      <div v-if="!orderId" class="mt-4 flex flex-wrap items-center gap-3 rounded-lg bg-slate-50 p-3">
        <input v-model="query" aria-label="搜索箱唛资料" placeholder="搜索合同号、客户、货号或文件名…" class="h-10 min-w-0 basis-full flex-1 rounded-lg border border-slate-200 bg-white px-3 text-sm sm:basis-auto">
        <select v-model="kindFilter" aria-label="箱唛文件类型" class="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm"><option value="ALL">全部格式</option><option value="pdf">PDF</option><option value="excel">Excel</option></select>
        <label v-if="!supplier" class="flex items-center gap-2 text-xs text-slate-600"><input v-model="onlyUnbound" type="checkbox">只看待关联</label>
        <select v-model="customerFilter" aria-label="箱唛客户筛选" class="h-10 rounded-lg border bg-white px-3 text-sm"><option value="">全部客户</option><option v-for="customer in customers" :key="customer">{{ customer }}</option></select>
        <select v-if="!supplier" v-model="bindingFilter" aria-label="箱唛关联状态" class="h-10 rounded-lg border bg-white px-3 text-sm"><option value="ALL">全部关联状态</option><option v-for="(label, state) in statuses" :key="state" :value="state">{{ label }}</option></select>
        <select v-model="sort" aria-label="箱唛资料排序" class="h-10 rounded-lg border bg-white px-3 text-sm"><option value="LATEST">最近上传的合同优先</option><option value="CONTRACT">合同号排序</option><option value="CUSTOMER">客户排序</option></select>
        <button type="button" class="h-10 rounded-lg border bg-white px-3 text-xs" @click="clearFilters">清除筛选</button><button type="button" class="h-10 rounded-lg border bg-white px-3 text-xs" @click="sort = 'LATEST'">恢复默认排序</button>
        <span class="whitespace-nowrap text-xs text-slate-500">{{ visible.length }} 份资料</span>
      </div>
      <p v-if="loading" class="py-6 text-center text-sm text-slate-500">正在读取资料…</p>
      <div v-else-if="!error && !visible.length" class="mt-4 rounded-xl border border-dashed border-slate-200 px-4 py-12 text-center">
        <FolderOpen class="mx-auto size-8 text-slate-300" /><p class="mt-3 text-sm text-slate-500">{{ entries.length ? '没有符合筛选条件的箱唛资料。' : supplier ? '暂无可查看的箱唛资料，仓库上传并关联已下单订单后会出现在这里。' : orderId ? '此订单暂无已关联箱唛资料。可在订单管理的箱唛资料库上传或关联。' : '暂无资料，上传后会长期保存在当前厂区。' }}</p>
      </div>
      <div v-if="visible.length" class="mt-4 overflow-hidden rounded-xl border border-slate-200">
      <div class="mark-library-columns hidden gap-6 border-b border-slate-200 bg-slate-50 px-4 py-3 text-xs font-semibold text-slate-500 lg:grid"><span>{{ supplier && supplierFactories ? '厂区 / 合同 / 客户 / 货号' : '合同 / 客户 / 货号' }}</span><span>原文件</span><span>关联状态 / 上传日期</span><span class="text-right">操作</span></div>
      <ul class="divide-y divide-slate-100">
        <template v-for="group in groups" :key="group.key">
        <li class="flex flex-wrap items-center gap-2 bg-slate-50 px-4 py-2 text-xs font-semibold text-slate-600" :aria-label="`箱唛合同分组 ${group.contract || '未识别'}`"><span v-if="supplier && supplierFactories">{{ factoryDisplayName(group.factory) }} ·</span><span>合同 {{ group.contract || '未识别' }}</span><span>{{ group.customer }}</span><span class="ml-auto">{{ group.assets.length }} 份原文件</span></li>
        <li v-for="asset in group.assets" :key="`${asset.factory_id}:${asset.id}`" class="mark-library-columns grid items-start gap-4 px-4 py-4 lg:min-h-24 lg:gap-6">
          <div class="col-span-2 min-w-0 lg:col-span-1">
            <p class="break-all text-sm font-bold leading-5 text-slate-900">合同号：{{ asset.contract_number || '未识别' }}</p>
            <p v-if="supplier && supplierFactories" class="mt-1 text-xs font-semibold leading-5 text-teal-700">{{ factoryDisplayName(asset.factory_id) }}</p>
            <p v-for="order in asset.orders" :key="order.id" class="mt-1 break-all text-xs leading-5 text-slate-500">{{ order.customer_name }} · {{ order.item_no }}<span v-if="!supplier && order.order_no"> · {{ order.order_no }}</span></p>
          </div>
          <div class="col-span-2 flex min-w-0 items-start gap-2 lg:col-span-1">
            <span class="flex size-8 shrink-0 items-center justify-center rounded-lg" :class="asset.kind === 'pdf' ? 'bg-red-50 text-red-600' : 'bg-teal-50 text-teal-700'"><FileText v-if="asset.kind === 'pdf'" class="size-4" /><FileSpreadsheet v-else class="size-4" /></span>
            <div class="min-w-0"><p class="text-sm font-semibold leading-5 text-slate-800 [overflow-wrap:anywhere]">{{ asset.file_name }}</p><p class="mt-1 text-xs leading-5 text-slate-400">{{ asset.kind === 'pdf' ? 'PDF' : 'Excel' }} · {{ (asset.size_bytes / 1024).toFixed(0) }} KB</p></div>
          </div>
          <div class="min-w-0 text-xs">
            <span class="inline-flex rounded-full px-2 py-1 leading-4" :class="asset.binding_status === 'BOUND' ? 'bg-teal-50 text-teal-700' : 'bg-amber-50 text-amber-700'">{{ supplier ? '仓库已共享' : statuses[asset.binding_status] }}</span>
            <p class="mt-1 leading-5 text-slate-400">{{ asset.created_at.slice(0, 10) }}</p>
            <p v-if="asset.warning || asset.binding_status === 'AMBIGUOUS'" class="mt-1 text-amber-700">{{ asset.binding_status === 'AMBIGUOUS' ? '同一合同号对应不同客户，请确认具体订单。' : asset.warning }}</p>
          </div>
          <div class="asset-actions grid min-w-0 grid-cols-2 items-start gap-2 text-xs">
            <a v-if="asset.kind === 'pdf'" :href="previewUrl(asset)" :aria-label="`预览 ${asset.file_name}`" target="_blank" rel="noopener" class="inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3"><Eye class="size-3.5" />预览</a>
            <span v-else aria-hidden="true" class="h-8"></span>
            <button type="button" :aria-label="`下载 ${asset.file_name}`" class="inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3" @click="download(asset)"><Download class="size-3.5" />下载</button>
            <button v-if="canWrite" type="button" :disabled="busy" class="rounded-lg border px-2.5 py-1.5" @click="edit(asset)">关联设置</button>
            <button v-if="canWrite" type="button" :disabled="busy" class="rounded-lg px-2.5 py-1.5 text-slate-400" @click="archive(asset)">移出</button>
            <button v-if="canWrite && checkEnabled" type="button" :disabled="busy" class="col-span-2 rounded-lg bg-teal-50 px-2.5 py-1.5 font-semibold text-teal-700" @click="emit('use', asset)">用于{{ asset.kind === 'pdf' ? 'PDF' : 'Excel' }}核对</button>
          </div>
        </li>
        </template>
      </ul>
      </div>
      <div v-if="binding" role="dialog" aria-label="关联箱唛资料" class="mt-4 rounded-xl border border-teal-200 bg-teal-50 p-4">
        <p class="break-all font-semibold">关联设置：{{ binding.file_name }}</p>
        <label class="mt-3 block text-xs">合同号（可留空，保留为待关联）<input v-model="contract" maxlength="128" class="mt-1 block w-full rounded-lg border bg-white px-3 py-2 text-sm" @input="orderId = ''"></label>
        <label v-if="binding.orders.length" class="mt-3 block text-xs">关联范围<select v-model="orderId" class="mt-1 block w-full rounded-lg border bg-white px-3 py-2 text-sm"><option value="">同一合同的订单共用</option><option v-for="order in binding.orders" :key="order.id" :value="order.id">{{ order.customer_name }} · {{ order.order_no }} · {{ order.item_no }}</option></select></label>
        <p v-if="binding.candidates.length > 1" class="mt-2 text-xs text-amber-700">候选合同号：{{ binding.candidates.join('、') }}</p>
        <div class="mt-3 flex gap-2"><button type="button" :disabled="busy" class="rounded-lg bg-teal-700 px-4 py-2 text-white disabled:opacity-50" @click="saveBinding">保存关联</button><button type="button" :disabled="busy" class="rounded-lg border bg-white px-4 py-2" @click="binding = null">取消</button></div>
      </div>
    </template>
  </section>
  <p v-else class="rounded-xl border bg-white p-6 text-sm text-slate-500">当前账号没有箱唛资料查看权限。</p>
</template>

<style scoped>
.asset-actions > a, .asset-actions > button { height: 2rem; display: inline-flex; align-items: center; justify-content: center; white-space: nowrap; }
.mark-library-columns {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
}

@media (min-width: 1024px) {
  .mark-library-columns {
    grid-template-columns: minmax(0, 1.1fr) minmax(0, 1.8fr) minmax(0, 0.9fr) var(--asset-actions-width);
  }
}
</style>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Download, Eye, FileSpreadsheet, FileText, FolderOpen, Image as ImageIcon, RefreshCw, UploadCloud } from '@lucide/vue'
import { cartonSupplierPortalApi, type SupplierMarkAsset } from '@/api/cartonSupplierPortal'
import { http } from '@/lib/http'
import { cartonMarkApi, type CartonMarkAsset, type CartonMarkAssetUploadResult } from '@/api/cartonMark'
import { getApiErrorMessage, getApiErrorMessageAsync } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'
import { factoryContexts } from '@/data/enterpriseMock'

const props = defineProps<{ factoryId: string; supplierFactories?: string[]; orderId?: string; readOnly?: boolean; supplier?: boolean; supplierCheckEnabled?: boolean; uploadOnly?: boolean; checkEnabled?: boolean }>()
const emit = defineEmits<{ use: [asset: CartonMarkAsset]; useSources: [assets: CartonMarkAsset[]]; supplierExcel: [asset: SupplierMarkAsset & { factory_id: string }]; supplierSources: [assets: (SupplierMarkAsset & { factory_id: string })[]] }>()
const auth = useAuthStore()
const canRead = computed(() => props.supplier ? auth.can('carton_supplier:read') : ['pmc-warehouse', 'carton', 'qa', 'qc'].some(d => auth.can('carton_mark:read', props.factoryId, d)))
const canWrite = computed(() => !props.supplier && !props.readOnly && ['pmc-warehouse', 'carton'].some(d => auth.can('carton_mark:template_upload', props.factoryId, d)))
const entries = ref<CartonMarkAsset[]>([])
const supplierSources = ref<(SupplierMarkAsset & { factory_id: string })[]>([])
function chooseSupplierExcel(asset: CartonMarkAsset) {
  if (!props.supplier || !props.supplierCheckEnabled || busy.value || !auth.can('carton_supplier:edit', asset.factory_id, '*')) return
  const source = supplierSources.value.find(row => row.id === asset.id && row.factory_id === asset.factory_id && row.kind === 'excel')
  if (source) emit('supplierExcel', source)
}
const results = ref<CartonMarkAssetUploadResult[]>([])
const pendingFiles = ref<File[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const sourcePanel = ref<HTMLElement | null>(null)
const sourceGroup = ref(''), sourceExcelId = ref(''), sourcePdfId = ref('')
function groupKey(asset: CartonMarkAsset) {
  const customer = [...new Set(asset.orders.map(order => order.customer_name))].sort().join('、')
  return JSON.stringify(asset.photo_group_id ? [asset.factory_id, 'photos', asset.photo_group_id] : [asset.factory_id, asset.contract_number || asset.id, customer])
}
const sourceCandidates = computed(() => entries.value.filter(asset => asset.kind !== 'image' && groupKey(asset) === sourceGroup.value))
const sourceExcels = computed(() => sourceCandidates.value.filter(asset => asset.kind === 'excel'))
const sourcePdfs = computed(() => sourceCandidates.value.filter(asset => asset.kind === 'pdf'))
const selectedSources = computed(() => [sourceExcels.value.find(asset => asset.id === sourceExcelId.value), sourcePdfs.value.find(asset => asset.id === sourcePdfId.value)])
function chooseSources(key: string) {
  const candidate = entries.value.find(asset => groupKey(asset) === key)
  if (busy.value || !(canWrite.value && props.checkEnabled || props.supplier && props.supplierCheckEnabled && candidate && auth.can('carton_supplier:edit', candidate.factory_id, '*'))) return
  sourceGroup.value = key
  sourceExcelId.value = sourceExcels.value.length === 1 ? sourceExcels.value[0]!.id : ''
  sourcePdfId.value = sourcePdfs.value.length === 1 ? sourcePdfs.value[0]!.id : ''
  void nextTick(() => sourcePanel.value?.scrollIntoView?.({ behavior: 'smooth', block: 'center' }))
}
function useSources() {
  if (props.supplier) {
    if (!props.supplierCheckEnabled || busy.value || selectedSources.value.some(asset => !asset)) return
    const [excel, pdf] = selectedSources.value.map(asset => supplierSources.value.find(row => row.id === asset!.id && row.factory_id === asset!.factory_id))
    if (!excel || !pdf || excel.factory_id !== pdf.factory_id || !auth.can('carton_supplier:edit', excel.factory_id, '*')) return
    const orders = excel.orders.filter(order => pdf.orders.some(row => row.id === order.id && row.issue_id === order.issue_id))
    if (!orders.length) { error.value = 'Excel 与 PDF 没有共同的采购订单，请选择同一订单的文件。'; return }
    emit('supplierSources', [{ ...excel, orders }, pdf]); sourceGroup.value = ''; return
  }
  if (!canWrite.value || !props.checkEnabled || busy.value || selectedSources.value.some(asset => !asset || asset.factory_id !== props.factoryId)) return
  emit('useSources', selectedSources.value as CartonMarkAsset[])
  sourceGroup.value = ''
}
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
const bindingPanel = ref<HTMLDivElement | null>(null)
const bindingPhotos = ref<CartonMarkAsset[]>([])
const bindingGroupId = ref<string>()
const selectedPhotos = ref<string[]>([])
const selectedPhotoAssets = computed(() => entries.value.filter(asset => selectedPhotos.value.includes(asset.id) && asset.kind === 'image'))
const allOrders = ref<CartonMarkAsset['orders']>([])
const orderQuery = ref('')
const ordersLoading = ref(false)
const orderOptions = computed(() => {
  const options = allOrders.value.length ? allOrders.value : binding.value?.orders ?? []
  const search = orderQuery.value.trim().toLowerCase()
  return options.filter(order => (!contract.value.trim() || search || order.contract_no.toLowerCase() === contract.value.trim().toLowerCase() || order.id === boundOrderId.value)
    && (!search || [order.contract_no, order.customer_name, order.order_no, order.item_no].some(value => value.toLowerCase().includes(search))))
})
const gallery = ref<CartonMarkAsset[]>([])
let bindingSequence = 0
const contract = ref('')
const boundOrderId = ref('')
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
  const grouped = new Map<string, { key: string; factory: string; contract: string; customer: string; latest: string; photoGroupId: string | null; assets: CartonMarkAsset[] }>()
  for (const asset of visible.value) {
    const customer = [...new Set(asset.orders.map(order => order.customer_name))].sort().join('、')
    const key = groupKey(asset)
    const group = grouped.get(key) ?? { key, factory: asset.factory_id, contract: asset.contract_number, customer, latest: '', photoGroupId: asset.photo_group_id ?? null, assets: [] }
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
      if (current === generation && sequence === listSequence) supplierSources.value = batches.flatMap(({ scope, assets }) => assets.map(asset => ({ ...asset, factory_id: scope })))
      records = batches.flatMap(({ scope, assets }) => assets.map(asset => ({
        ...asset, factory_id: scope, sha256: '', bound_order_id: null, recognition_source: '', candidates: [], warning: '',
        created_by_name: '', binding_status: 'BOUND' as const, orders: asset.orders.map(order => ({ ...order, order_no: '' })),
      })))
      records.sort((a, b) => b.created_at.localeCompare(a.created_at) || a.factory_id.localeCompare(b.factory_id) || b.id.localeCompare(a.id))
    } else records = await cartonMarkApi.listAssets(factory, props.orderId, controller.signal)
    if (current === generation && sequence === listSequence) {
      entries.value = records
      selectedPhotos.value = selectedPhotos.value.filter(id => records.some(asset => asset.id === id))
      const previewing = gallery.value[0]
      if (previewing) gallery.value = records.filter(asset => asset.factory_id === previewing.factory_id && asset.photo_group_id === previewing.photo_group_id)
    }
  } catch (cause) {
    if (current === generation && sequence === listSequence) {
      if (props.supplier) { entries.value = []; supplierSources.value = [] }
      gallery.value = []
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

function photoMembers(groupId: string, factory = props.factoryId) { return entries.value.filter(asset => asset.factory_id === factory && asset.photo_group_id === groupId) }
function togglePhoto(asset: CartonMarkAsset, checked: boolean) {
  const ids = (asset.photo_group_id ? photoMembers(asset.photo_group_id, asset.factory_id) : [asset]).map(photo => photo.id)
  selectedPhotos.value = checked ? [...new Set([...selectedPhotos.value, ...ids])] : selectedPhotos.value.filter(id => !ids.includes(id))
}
async function edit(asset: CartonMarkAsset, photos: CartonMarkAsset[] = [], groupId?: string) {
  if (!canWrite.value || busy.value) return
  const members = photos.length ? photos : asset.photo_group_id ? photoMembers(asset.photo_group_id, asset.factory_id) : []
  binding.value = asset
  bindingPhotos.value = [...members]
  bindingGroupId.value = groupId ?? (photos.length ? undefined : asset.photo_group_id ?? undefined)
  const targets = members.length ? members : [asset]
  contract.value = targets.every(photo => photo.contract_number === asset.contract_number) ? asset.contract_number : ''
  boundOrderId.value = targets.every(photo => photo.bound_order_id === asset.bound_order_id) ? asset.bound_order_id || '' : ''
  orderQuery.value = ''
  error.value = ''
  void nextTick(() => bindingPanel.value?.scrollIntoView?.({ behavior: 'smooth', block: 'center' }))
  const current = generation, sequence = ++bindingSequence
  ordersLoading.value = true
  try {
    const orders = await cartonMarkApi.bindingOrders(props.factoryId, controller.signal)
    if (current === generation && sequence === bindingSequence) allOrders.value = orders
  } catch (cause) {
    if (current === generation && sequence === bindingSequence) error.value = `读取可关联订单失败：${getApiErrorMessage(cause)}；仍可填写合同号。`
  } finally {
    if (current === generation && sequence === bindingSequence) ordersLoading.value = false
  }
}

function closeBinding() { bindingSequence++; binding.value = null; bindingPhotos.value = []; ordersLoading.value = false }
function createPhotoGroup() {
  const photos = selectedPhotoAssets.value
  if (photos.length >= 2 && photos.length <= 50 && photos[0]) void edit(photos[0], photos)
}
function chooseOrder() {
  const selected = allOrders.value.find(order => order.id === boundOrderId.value) ?? binding.value?.orders.find(order => order.id === boundOrderId.value)
  if (selected) contract.value = selected.contract_no
}

async function ungroup(groupId: string) {
  if (!canWrite.value || busy.value || !window.confirm('解除照片分组？各照片保留原文件和当前订单关联。')) return
  const current = generation
  busy.value = true
  try {
    await cartonMarkApi.ungroupPhotos(props.factoryId, groupId, photoMembers(groupId), controller.signal)
    if (current !== generation) return
    selectedPhotos.value = []; closeBinding(); await refresh()
  } catch (cause) { if (current === generation) error.value = getApiErrorMessage(cause) }
  finally { if (current === generation) busy.value = false }
}

async function saveBinding() {
  if (!binding.value || busy.value || !canWrite.value) return
  const current = generation
  const selected = binding.value
  busy.value = true
  try {
    if (bindingPhotos.value.length) await cartonMarkApi.savePhotoGroup(props.factoryId, bindingPhotos.value, contract.value.trim(), boundOrderId.value, bindingGroupId.value, controller.signal)
    else await cartonMarkApi.bindAsset(props.factoryId, selected, contract.value.trim(), boundOrderId.value, controller.signal)
    if (current !== generation) return
    closeBinding(); selectedPhotos.value = []
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
watch(() => [props.factoryId, props.supplierFactories?.join('\0'), props.orderId, props.supplier, canRead.value, canWrite.value, auth.currentUser?.id, auth.authorizationVersion], () => {
  generation++
  controller.abort()
  controller = new AbortController()
  entries.value = []
  supplierSources.value = []
  results.value = []
  pendingFiles.value = []
  closeBinding(); selectedPhotos.value = []; allOrders.value = []; gallery.value = []
  sourceGroup.value = ''; sourceExcelId.value = ''; sourcePdfId.value = ''
  contract.value = ''
  boundOrderId.value = ''
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
        <p class="mt-1 text-xs leading-5 text-slate-500">{{ supplier ? '本供应商采购订单的箱唛原文件，可查看、下载，并选择 Excel / PDF 一起核对。' : orderId ? '此订单关联的箱唛原文件，可直接查看和下载。' : 'PDF、Excel、图片可分别上传，按合同号自动关联本厂订单并共享给对应供应商；未识别的文件先保存，之后再关联。' }}</p>
        <p v-if="!supplier && !orderId" class="text-xs leading-5 text-slate-500">图片支持 JPG、PNG、WebP。无需改照片名：上传后可搜索订单手动关联，或勾选多张照片组成组、整组关联。同合同命名可自动识别，如 4500000123_正唛.jpg。</p>
      </div>
      <button v-if="!uploadOnly" type="button" :disabled="busy || loading" class="inline-flex items-center gap-1 rounded-lg border px-3 py-2 text-xs disabled:opacity-50" @click="refresh"><RefreshCw class="size-3.5" />刷新</button>
    </div>
    <div v-if="canWrite" class="mt-4 rounded-lg border-2 border-dashed border-teal-200 bg-teal-50/50 p-4" @dragover.prevent @drop.prevent="selectFiles(Array.from($event.dataTransfer?.files ?? []))">
      <input ref="fileInput" type="file" multiple accept=".pdf,.xls,.xlsx,.xlsm,.jpg,.jpeg,.png,.webp" class="hidden" aria-label="批量选择箱唛原文件" @change="selectFiles(Array.from(($event.target as HTMLInputElement).files ?? []))">
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
        <select v-model="kindFilter" aria-label="箱唛文件类型" class="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm"><option value="ALL">全部格式</option><option value="pdf">PDF</option><option value="excel">Excel</option><option value="image">图片</option></select>
        <label v-if="!supplier" class="flex items-center gap-2 text-xs text-slate-600"><input v-model="onlyUnbound" type="checkbox">只看待关联</label>
        <select v-model="customerFilter" aria-label="箱唛客户筛选" class="h-10 rounded-lg border bg-white px-3 text-sm"><option value="">全部客户</option><option v-for="customer in customers" :key="customer">{{ customer }}</option></select>
        <select v-if="!supplier" v-model="bindingFilter" aria-label="箱唛关联状态" class="h-10 rounded-lg border bg-white px-3 text-sm"><option value="ALL">全部关联状态</option><option v-for="(label, state) in statuses" :key="state" :value="state">{{ label }}</option></select>
        <select v-model="sort" aria-label="箱唛资料排序" class="h-10 rounded-lg border bg-white px-3 text-sm"><option value="LATEST">最近上传的合同优先</option><option value="CONTRACT">合同号排序</option><option value="CUSTOMER">客户排序</option></select>
        <button type="button" class="h-10 rounded-lg border bg-white px-3 text-xs" @click="clearFilters">清除筛选</button><button type="button" class="h-10 rounded-lg border bg-white px-3 text-xs" @click="sort = 'LATEST'">恢复默认排序</button>
        <span class="whitespace-nowrap text-xs text-slate-500">{{ visible.length }} 份资料</span>
      </div>
      <div v-if="canWrite" class="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-600">
        <span>已选 {{ selectedPhotoAssets.length }} 张照片</span>
        <button type="button" :disabled="busy || selectedPhotoAssets.length < 2 || selectedPhotoAssets.length > 50" class="rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 font-semibold text-teal-700 disabled:opacity-50" @click="createPhotoGroup">组成照片组</button>
        <button v-if="selectedPhotoAssets.length" type="button" class="text-teal-700" @click="selectedPhotos = []">清空选择</button>
        <span>每组最多 50 张；选择组内照片会选中整组，包括筛选外照片。</span>
      </div>
      <p v-if="loading" class="py-6 text-center text-sm text-slate-500">正在读取资料…</p>
      <div v-else-if="!error && !visible.length" class="mt-4 rounded-xl border border-dashed border-slate-200 px-4 py-12 text-center">
        <FolderOpen class="mx-auto size-8 text-slate-300" /><p class="mt-3 text-sm text-slate-500">{{ entries.length ? '没有符合筛选条件的箱唛资料。' : supplier ? '暂无可查看的箱唛资料，仓库上传并关联已下单订单后会出现在这里。' : orderId ? '此订单暂无已关联箱唛资料。可在订单管理的箱唛资料库上传或关联。' : '暂无资料，上传后会长期保存在当前厂区。' }}</p>
      </div>
      <div v-if="visible.length" class="mt-4 overflow-hidden rounded-xl border border-slate-200">
      <div class="mark-library-columns hidden gap-6 border-b border-slate-200 bg-slate-50 px-4 py-3 text-xs font-semibold text-slate-500 lg:grid"><span>{{ supplier && supplierFactories ? '厂区 / 合同 / 客户 / 货号' : '合同 / 客户 / 货号' }}</span><span>原文件</span><span>关联状态 / 上传日期</span><span class="text-right">操作</span></div>
      <ul class="divide-y divide-slate-100">
        <template v-for="group in groups" :key="group.key">
        <li class="flex flex-wrap items-center gap-2 bg-slate-50 px-4 py-2 text-xs font-semibold text-slate-600" :aria-label="`箱唛合同分组 ${group.contract || '未识别'}`">
          <span v-if="supplier && supplierFactories">{{ factoryDisplayName(group.factory) }} ·</span>
          <span v-if="group.photoGroupId" class="rounded bg-blue-100 px-2 py-1 text-blue-700">照片组</span>
          <span>合同 {{ group.contract || '未识别' }}</span><span>{{ group.customer }}</span><span class="ml-auto">{{ group.assets.length }} 份原文件<span v-if="group.photoGroupId && photoMembers(group.photoGroupId, group.factory).length !== group.assets.length"> / 整组 {{ photoMembers(group.photoGroupId, group.factory).length }} 张</span></span>
          <button v-if="(canWrite && checkEnabled || supplier && supplierCheckEnabled && auth.can('carton_supplier:edit', group.factory, '*')) && group.assets.some(asset => asset.kind !== 'image')" type="button" :disabled="busy" class="rounded border border-teal-200 bg-white px-3 py-1.5 text-teal-700" :aria-label="`选择合同 ${group.contract || '未识别'} 的 Excel / PDF 核对文件`" @click="chooseSources(group.key)">选择 Excel / PDF 核对</button>
          <button v-if="group.photoGroupId" type="button" class="rounded border bg-white px-2 py-1.5" @click="gallery = photoMembers(group.photoGroupId, group.factory)">查看照片组</button>
          <button v-if="canWrite && group.photoGroupId" type="button" :disabled="busy" class="rounded border bg-white px-2 py-1.5" @click="edit(group.assets[0]!)">整组关联</button>
          <button v-if="canWrite && group.photoGroupId" type="button" :disabled="busy" class="rounded border bg-white px-2 py-1.5" @click="ungroup(group.photoGroupId)">解除分组</button>
        </li>
        <li v-for="asset in group.assets" :key="`${asset.factory_id}:${asset.id}`" class="mark-library-columns grid items-start gap-4 px-4 py-4 lg:min-h-24 lg:gap-6">
          <div class="col-span-2 min-w-0 lg:col-span-1">
            <label v-if="canWrite && asset.kind === 'image'" class="mb-2 flex items-center gap-2 text-xs text-slate-500"><input type="checkbox" :aria-label="`选择照片 ${asset.file_name}`" :checked="selectedPhotos.includes(asset.id)" :disabled="busy" @change="togglePhoto(asset, ($event.target as HTMLInputElement).checked)">{{ asset.photo_group_id ? '选择整组' : '选择照片' }}</label>
            <p class="break-all text-sm font-bold leading-5 text-slate-900">合同号：{{ asset.contract_number || '未识别' }}</p>
            <p v-if="supplier && supplierFactories" class="mt-1 text-xs font-semibold leading-5 text-teal-700">{{ factoryDisplayName(asset.factory_id) }}</p>
            <p v-for="order in asset.orders" :key="order.id" class="mt-1 break-all text-xs leading-5 text-slate-500">{{ order.customer_name }} · {{ order.item_no }}<span v-if="!supplier && order.order_no"> · {{ order.order_no }}</span></p>
          </div>
          <div class="col-span-2 flex min-w-0 items-start gap-2 lg:col-span-1">
            <span class="flex size-8 shrink-0 items-center justify-center rounded-lg" :class="asset.kind === 'pdf' ? 'bg-red-50 text-red-600' : asset.kind === 'image' ? 'bg-blue-50 text-blue-600' : 'bg-teal-50 text-teal-700'"><FileText v-if="asset.kind === 'pdf'" class="size-4" /><ImageIcon v-else-if="asset.kind === 'image'" class="size-4" /><FileSpreadsheet v-else class="size-4" /></span>
            <div class="min-w-0"><p class="text-sm font-semibold leading-5 text-slate-800 [overflow-wrap:anywhere]">{{ asset.file_name }}</p><p class="mt-1 text-xs leading-5 text-slate-400">{{ asset.kind === 'pdf' ? 'PDF' : asset.kind === 'image' ? '图片' : 'Excel' }} · {{ (asset.size_bytes / 1024).toFixed(0) }} KB</p></div>
          </div>
          <div class="min-w-0 text-xs">
            <span class="inline-flex rounded-full px-2 py-1 leading-4" :class="asset.binding_status === 'BOUND' ? 'bg-teal-50 text-teal-700' : 'bg-amber-50 text-amber-700'">{{ supplier ? '已关联采购订单' : statuses[asset.binding_status] }}</span>
            <p class="mt-1 leading-5 text-slate-400">{{ asset.created_at.slice(0, 10) }}</p>
            <p v-if="asset.warning || asset.binding_status === 'AMBIGUOUS'" class="mt-1 text-amber-700">{{ asset.binding_status === 'AMBIGUOUS' ? '同一合同号对应不同客户，请确认具体订单。' : asset.warning }}</p>
          </div>
          <div class="asset-actions grid min-w-0 grid-cols-2 items-start gap-2 text-xs">
            <a v-if="asset.kind === 'pdf' || asset.kind === 'image'" :href="previewUrl(asset)" :aria-label="`预览 ${asset.file_name}`" target="_blank" rel="noopener" class="inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3"><Eye class="size-3.5" />预览</a>
            <span v-else aria-hidden="true" class="h-8"></span>
            <button type="button" :aria-label="`下载 ${asset.file_name}`" class="inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3" @click="download(asset)"><Download class="size-3.5" />下载</button>
            <button v-if="canWrite" type="button" :disabled="busy" class="rounded-lg border px-2.5 py-1.5" @click="edit(asset)">关联设置</button>
            <button v-if="canWrite" type="button" :disabled="busy" class="rounded-lg px-2.5 py-1.5 text-slate-400" @click="archive(asset)">移出</button>
            <button v-if="canWrite && checkEnabled && asset.kind !== 'image'" type="button" :disabled="busy" class="col-span-2 rounded-lg bg-teal-50 px-2.5 py-1.5 font-semibold text-teal-700" @click="emit('use', asset)">用于{{ asset.kind === 'pdf' ? 'PDF' : 'Excel' }}核对</button>
            <button v-if="supplier && supplierCheckEnabled && asset.kind === 'excel' && auth.can('carton_supplier:edit', asset.factory_id, '*')" type="button" :disabled="busy" class="col-span-2 rounded-lg bg-teal-50 px-2.5 py-1.5 font-semibold text-teal-700" @click="chooseSupplierExcel(asset)">选择 Excel 并上传 PDF 核对</button>
          </div>
        </li>
        </template>
      </ul>
      </div>
      <div v-if="sourceGroup && (canWrite && checkEnabled || supplier && supplierCheckEnabled)" ref="sourcePanel" role="dialog" aria-label="选择仓库核对文件" class="mt-4 rounded-xl border border-teal-200 bg-teal-50 p-4">
        <p class="font-semibold">从同一合同的原文件选择 Excel 与打印 PDF</p>
        <p class="mt-1 text-xs text-slate-600">包含列表筛选隐藏的同合同文件；多个版本请明确选择。带入后仍需提交内容核对，通过或人工放行后才可供 QC 使用。</p>
        <div class="mt-3 grid gap-3 sm:grid-cols-2">
          <label class="text-xs">客人 Excel<select v-model="sourceExcelId" aria-label="仓库核对 Excel" class="mt-1 h-10 w-full rounded border bg-white px-2"><option value="">请选择 Excel</option><option v-for="asset in sourceExcels" :key="asset.id" :value="asset.id">{{ asset.file_name }} · {{ asset.created_at.slice(0, 10) }}</option></select></label>
          <label class="text-xs">打印 PDF<select v-model="sourcePdfId" aria-label="仓库核对 PDF" class="mt-1 h-10 w-full rounded border bg-white px-2"><option value="">请选择 PDF</option><option v-for="asset in sourcePdfs" :key="asset.id" :value="asset.id">{{ asset.file_name }} · {{ asset.created_at.slice(0, 10) }}</option></select></label>
        </div>
        <p v-if="!sourceExcels.length || !sourcePdfs.length" class="mt-2 text-xs text-amber-800">此合同缺少 {{ !sourceExcels.length ? 'Excel' : 'PDF' }}，请先上传，或用单个文件的核对入口补选另一份文件。</p>
        <div class="mt-3 flex flex-wrap gap-2"><button type="button" :disabled="busy || selectedSources.some(asset => !asset)" class="rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" @click="useSources">带入 Excel / PDF 核对</button><button type="button" class="rounded-lg border bg-white px-4 py-2 text-sm" @click="sourceGroup = ''">取消</button></div>
      </div>
      <div v-if="binding" ref="bindingPanel" role="dialog" aria-label="关联箱唛资料" class="mt-4 rounded-xl border border-teal-200 bg-teal-50 p-4">
        <p class="break-all font-semibold">{{ bindingPhotos.length ? `${bindingGroupId ? '整组关联' : '组成照片组'}：${bindingPhotos.length} 张照片` : `关联设置：${binding.file_name}` }}</p>
        <p v-if="bindingPhotos.length" class="mt-2 break-all text-xs text-slate-600">{{ bindingPhotos.map(photo => photo.file_name).join('、') }}。保存后整组使用下面同一合同和关联范围，留空则整组待关联。</p>
        <label class="mt-3 block text-xs">合同号（可留空，保留为待关联）<input v-model="contract" maxlength="128" class="mt-1 block w-full rounded-lg border bg-white px-3 py-2 text-sm" @input="boundOrderId = ''"></label>
        <label class="mt-3 block text-xs">搜索本厂订单<input v-model="orderQuery" aria-label="搜索可关联订单" placeholder="合同号 / 客户 / 货号 / 订单号" class="mt-1 block w-full rounded-lg border bg-white px-3 py-2 text-sm"></label>
        <label class="mt-3 block text-xs">关联范围<select v-model="boundOrderId" aria-label="选择关联订单" class="mt-1 block w-full rounded-lg border bg-white px-3 py-2 text-sm" @change="chooseOrder"><option value="">同一合同的订单共用</option><option v-for="order in orderOptions" :key="order.id" :value="order.id">{{ order.contract_no }} · {{ order.customer_name }} · {{ order.order_no }} · {{ order.item_no }}</option></select></label>
        <p v-if="ordersLoading" class="mt-2 text-xs text-slate-500">正在读取本厂订单…</p>
        <p v-else-if="!orderOptions.length" class="mt-2 text-xs text-slate-500">暂无匹配订单，可搜索其他合同或手工填写合同号，后续订单可共用。</p>
        <p v-if="binding.candidates.length > 1" class="mt-2 text-xs text-amber-700">候选合同号：{{ binding.candidates.join('、') }}</p>
        <div class="mt-3 flex gap-2"><button type="button" :disabled="busy" class="rounded-lg bg-teal-700 px-4 py-2 text-white disabled:opacity-50" @click="saveBinding">{{ bindingPhotos.length ? '保存照片组' : '保存关联' }}</button><button type="button" :disabled="busy" class="rounded-lg border bg-white px-4 py-2" @click="closeBinding">取消</button></div>
      </div>
    </template>
    <div v-if="gallery.length" role="dialog" aria-label="箱唛照片组预览" aria-modal="true" class="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 p-4 sm:p-8" @click.self="gallery = []">
      <section class="mx-auto max-w-5xl rounded-xl bg-white p-4 sm:p-6">
        <div class="flex items-center justify-between gap-3"><h3 class="font-bold">箱唛照片组 · {{ gallery.length }} 张</h3><button type="button" class="rounded-lg border px-3 py-2 text-sm" @click="gallery = []">关闭预览</button></div>
        <div class="mt-4 grid gap-4 sm:grid-cols-2"><figure v-for="photo in gallery" :key="photo.id" class="min-w-0 rounded-lg border p-3"><img :src="previewUrl(photo)" :alt="photo.file_name" loading="lazy" class="h-80 w-full object-contain"><figcaption class="mt-2 flex items-center justify-between gap-2 text-xs"><span class="break-all">{{ photo.file_name }}</span><button type="button" class="shrink-0 rounded border px-2 py-1.5" @click="download(photo)">下载</button></figcaption></figure></div>
      </section>
    </div>
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

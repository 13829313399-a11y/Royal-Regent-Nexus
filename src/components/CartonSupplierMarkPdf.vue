<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { cartonSupplierPortalApi, type SupplierMarkAsset, type SupplierMarkPdfResult, type SupplierMarkUploadOrder, type SupplierMarkLayout } from '@/api/cartonSupplierPortal'
import CartonSupplierMarkLayout from './CartonSupplierMarkLayout.vue'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { factoryContexts } from '@/data/enterpriseMock'

type Source = SupplierMarkAsset & { factory_id: string }
const props = defineProps<{ factoryIds: string[]; source: Source | null }>()
const emit = defineEmits<{ choose: []; saved: []; check: [sources: Source[]] }>()
const auth = useAuthStore()
const factory = ref(''), orderId = ref(''), file = ref<File | null>(null), stored = ref<Source | null>(null)
const orders = ref<SupplierMarkUploadOrder[]>([]), result = ref<SupplierMarkPdfResult | null>(null)
const busy = ref(false), loading = ref(false), error = ref(''), previewUrl = ref('')
const layout = ref<SupplierMarkLayout | null>(null), layoutLoading = ref(false), editingLayout = ref(false)
const input = ref<HTMLInputElement | null>(null)
const canWrite = computed(() => auth.can('carton_supplier:read', '*', '*') && auth.can('carton_supplier:edit', factory.value || '*', '*'))
const choices = computed(() => stored.value ? orders.value.filter(order => stored.value!.orders.some(link => link.id === order.id && link.issue_id === order.issue_id)) : orders.value)
const selected = computed(() => choices.value.find(order => order.id === orderId.value))
let generation = 0, controller = new AbortController()
let layoutGeneration = 0
function clearPreview() { if (previewUrl.value) URL.revokeObjectURL(previewUrl.value); previewUrl.value = '' }
function factoryName(id: string) { return factoryContexts.find(row => row.id === id)?.shortName ?? id }
async function reset() {
  const token = ++generation
  controller.abort(); controller = new AbortController(); clearPreview()
  busy.value = false; loading.value = false; error.value = ''; result.value = null; orders.value = []; orderId.value = ''; file.value = null
  layoutGeneration++; layout.value = null; layoutLoading.value = false; editingLayout.value = false
  stored.value = props.source && props.source.factory_id === factory.value && props.factoryIds.includes(factory.value) ? props.source : null
  if (!factory.value || !props.factoryIds.includes(factory.value) || !canWrite.value) { stored.value = null; return }
  loading.value = true
  try {
    const available = await cartonSupplierPortalApi.markUploadOrders(factory.value, controller.signal)
    if (token !== generation) return
    orders.value = available
    if (choices.value.length === 1) orderId.value = choices.value[0]!.id
    if (stored.value && !choices.value.length) error.value = '原稿关联订单已变更，请刷新资料库重新选择。'
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}
function chooseFiles(files: File[]) {
  if (busy.value || !canWrite.value || !files.length) return
  if (files.length !== 1 || !/\.(xlsx|xls)$/i.test(files[0]!.name) || !files[0]!.size || files[0]!.size > 20 * 1024 * 1024) {
    error.value = '请选择一个 .xls / .xlsx 文件，最多 20 MB。'; return
  }
  file.value = files[0]!; stored.value = null; result.value = null; error.value = ''; clearPreview()
  if (orders.value.length === 1) orderId.value = orders.value[0]!.id
  if (input.value) input.value.value = ''
}
async function generate() {
  if (busy.value || loading.value || layoutLoading.value || editingLayout.value || !layout.value || !canWrite.value || !selected.value || (!file.value && !stored.value)) return
  const token = generation, target = factory.value, order = selected.value
  busy.value = true; error.value = ''; result.value = null; clearPreview()
  try {
    if (!stored.value && file.value) {
      const uploaded = await cartonSupplierPortalApi.uploadMarkAssets(target, [file.value], order, controller.signal)
      if (token !== generation) return
      const outcome = uploaded[0]
      if (!outcome?.asset || outcome.status === 'failed') throw new Error(outcome?.message || 'Excel 原稿上传失败')
      stored.value = { ...outcome.asset, factory_id: target }; file.value = null; emit('saved')
    }
    const original = stored.value!
    const converted = await cartonSupplierPortalApi.generateMarkPdf({ factory_id: target, order_id: order.id,
      issue_id: order.issue_id, excel_asset_id: original.id, expected_revision: original.revision, layout_id: layout.value.id }, controller.signal)
    if (token !== generation) return
    result.value = converted; emit('saved')
    await showPreview()
  } catch (cause) {
    if (token === generation) error.value = `生成未完成：${getApiErrorMessage(cause)}。原稿已入库时可以直接重试；请求中断后请先刷新资料库确认 PDF 是否已保存。`
  } finally { if (token === generation) busy.value = false }
}
async function showPreview() {
  if (!result.value) return
  const token = generation, pdf = result.value.asset, target = factory.value
  try {
    const bytes = await cartonSupplierPortalApi.downloadMarkAsset(pdf.id, target, controller.signal)
    if (token !== generation || result.value?.asset.id !== pdf.id) return
    clearPreview(); previewUrl.value = URL.createObjectURL(bytes)
  } catch (cause) { if (token === generation) error.value = `PDF 已保存，预览暂时无法打开：${getApiErrorMessage(cause)}。可刷新资料库查看。` }
}
function goCheck() {
  if (stored.value && result.value && selected.value) emit('check', [
    { ...stored.value, orders: [selected.value] }, { ...result.value.asset, factory_id: factory.value },
  ])
}
function download() {
  if (!previewUrl.value || !result.value) return
  const anchor = document.createElement('a'); anchor.href = previewUrl.value; anchor.download = result.value.asset.file_name; anchor.click()
}
watch([() => props.factoryIds.join('\0'), () => props.source, () => auth.currentUser?.id, () => auth.authorizationVersion], () => {
  const target = props.source && props.factoryIds.includes(props.source.factory_id) ? props.source.factory_id : props.factoryIds.length === 1 ? props.factoryIds[0]! : ''
  if (factory.value !== target) factory.value = target
  void reset()
}, { immediate: true })
watch([factory, canWrite], () => void reset())
async function loadLayout() {
  const token = ++layoutGeneration, context = generation, order = selected.value
  layout.value = null; editingLayout.value = false; layoutLoading.value = false; result.value = null; clearPreview()
  if (!order || !canWrite.value) return
  layoutLoading.value = true
  try {
    const versions = await cartonSupplierPortalApi.markLayouts(factory.value, order, controller.signal)
    if (token !== layoutGeneration || context !== generation) return
    layout.value = versions[0] ?? null
  } catch (cause) { if (token === layoutGeneration && context === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === layoutGeneration && context === generation) layoutLoading.value = false }
}
function layoutSaved(saved: SupplierMarkLayout) { layout.value = saved; editingLayout.value = false; result.value = null; clearPreview() }
watch(() => selected.value ? `${selected.value.id}:${selected.value.issue_id}` : '', () => void loadLayout())
onBeforeUnmount(() => { generation++; controller.abort(); clearPreview() })
</script>

<template>
  <section class="rounded-xl border bg-white p-4 sm:p-6" aria-label="箱唛文档生成 PDF">
    <h2 class="text-lg font-bold">文档生成 PDF</h2>
    <p class="mt-1 text-sm leading-6 text-slate-500">按客户固定模板自动排版，填入 Excel 里的货号、品名、装箱数和条码，自动关联所选采购订单。新客户先用历史稿建立模板，后续订单直接套用。</p>
    <p v-if="!canWrite" class="mt-4 text-sm text-amber-800">当前账号没有此厂区的资料提交权限。</p>
    <div class="mt-4 flex flex-wrap gap-3">
      <label class="text-sm">收货厂区<select v-model="factory" aria-label="PDF 生成厂区" :disabled="busy" class="mt-1 block rounded-lg border bg-white p-2"><option value="">请选择厂区</option><option v-for="id in factoryIds" :key="id" :value="id">{{ factoryName(id) }}</option></select></label>
      <label v-if="choices.length !== 1" class="min-w-0 flex-1 text-sm">关联采购订单<select v-model="orderId" aria-label="PDF 生成订单" :disabled="busy || loading || !factory || !canWrite" class="mt-1 block w-full rounded-lg border bg-white p-2"><option value="">请选择采购订单</option><option v-for="order in choices" :key="order.id" :value="order.id">{{ order.customer_name }} · {{ order.contract_no }} · {{ order.item_no }} · {{ order.document_no }}</option></select></label>
    </div>
    <p v-if="selected" class="mt-3 rounded-lg bg-teal-50 p-3 text-sm text-teal-900">{{ selected.customer_name }} · 合同 {{ selected.contract_no }} · PO {{ selected.customer_po || '未填写' }} · ITEM {{ selected.item_no }}</p>
    <div v-if="selected" class="mt-3 flex flex-wrap items-center gap-3 rounded-lg border p-3 text-sm">
      <span v-if="layoutLoading">正在读取客户模板…</span><span v-else-if="layout">客户模板：{{ layout.name }} · V{{ layout.version }}</span><span v-else>此客户还没有排版模板，先用历史稿确认一次。</span>
      <button type="button" :disabled="busy || layoutLoading || !canWrite" class="rounded border px-3 py-1 disabled:opacity-50" @click="editingLayout = !editingLayout">{{ layout ? '调整客户模板' : '建立客户模板' }}</button>
    </div>
    <CartonSupplierMarkLayout v-if="editingLayout && selected && canWrite" :key="`${factory}:${selected.id}:${layout?.id || 'new'}`" :factory="factory" :order="selected" :current="layout" @saved="layoutSaved" @close="editingLayout = false"/>
    <div class="mt-4 rounded-lg border-2 border-dashed border-teal-200 p-4" @dragover.prevent @drop.prevent="chooseFiles(Array.from($event.dataTransfer?.files ?? []))">
      <input ref="input" type="file" accept=".xls,.xlsx" class="sr-only" aria-label="选择生成 PDF 的 Excel" :disabled="busy || !canWrite" @change="chooseFiles(Array.from(($event.target as HTMLInputElement).files ?? []))">
      <div class="flex flex-wrap gap-3"><button type="button" :disabled="busy || !canWrite" class="rounded-lg border px-4 py-2 disabled:opacity-50" @click="input?.click()">上传 Excel</button><button type="button" :disabled="busy" class="rounded-lg border px-4 py-2" @click="emit('choose')">从资料库选择 Excel</button><button type="button" :disabled="busy || loading || layoutLoading || editingLayout || !layout || !canWrite || !selected || (!file && !stored)" class="rounded-lg bg-teal-700 px-4 py-2 font-semibold text-white disabled:opacity-50" @click="generate">{{ busy ? '正在生成 PDF…' : '生成 PDF' }}</button></div>
      <p class="mt-3 break-all text-sm">{{ stored?.file_name || file?.name || '支持 .xls / .xlsx，单个文件最多 20 MB；可直接拖入。' }}</p>
    </div>
    <p v-if="loading" role="status" class="mt-3 text-sm text-slate-500">正在读取可关联订单…</p>
    <p v-else-if="factory && !orders.length && !error" class="mt-3 text-sm text-amber-800">当前厂区暂无可关联采购订单。</p>
    <p v-if="error" role="alert" class="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">{{ error }}</p>
    <div v-if="result" class="mt-5 space-y-3">
      <p role="status" class="rounded-lg bg-teal-50 p-3 text-sm text-teal-900">{{ result.asset.file_name }} · {{ result.page_count }} 页 · {{ result.layout_name }} V{{ result.layout_version }} · 已保存到资料库，待核对 / 审核。</p>
      <ul v-if="result.warnings.length" class="list-inside list-disc rounded-lg bg-amber-50 p-3 text-sm text-amber-900"><li v-for="warning in result.warnings" :key="warning">{{ warning }}</li></ul>
      <p class="text-xs text-slate-500">请查看完整内容和素材，打印后扫码验证条码。此处生成客户模板排版审阅稿，生产 1:1 尺寸需另行确认。</p>
      <div class="flex flex-wrap gap-3"><button type="button" :disabled="!previewUrl" class="rounded-lg border px-4 py-2 disabled:opacity-50" @click="download">下载 PDF</button><button v-if="!previewUrl" type="button" class="rounded-lg border px-4 py-2" @click="showPreview">重新打开预览</button><button type="button" :disabled="busy" class="rounded-lg bg-teal-700 px-4 py-2 text-white" @click="goCheck">用 Excel / PDF 核对</button></div>
      <iframe v-if="previewUrl" :src="previewUrl" title="生成的箱唛 PDF 预览" class="h-[65vh] min-h-96 w-full rounded-lg border"></iframe>
    </div>
  </section>
</template>

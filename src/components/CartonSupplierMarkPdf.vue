<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { cartonSupplierPortalApi, type SupplierMarkAsset, type SupplierMarkPdfResult, type SupplierMarkUploadOrder, type SupplierMarkLayout, type MarkPdfSupplements, type MarkPdfAiStatus, type MarkPdfDraftResult, type MarkReadResult, type MarkReviewEdits, type MarkSourceInspection } from '@/api/cartonSupplierPortal'
import CartonSupplierMarkLayout from './CartonSupplierMarkLayout.vue'
import CartonMarkReadReview from './CartonMarkReadReview.vue'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'

type Source = SupplierMarkAsset & { factory_id: string }
const props = defineProps<{ factoryIds: string[]; source: Source | null }>()
const emit = defineEmits<{ choose: []; saved: []; check: [sources: Source[]] }>()
const auth = useAuthStore()
const factory = ref(''), orderId = ref(''), file = ref<File | null>(null), stored = ref<Source | null>(null)
const orders = ref<SupplierMarkUploadOrder[]>([]), result = ref<SupplierMarkPdfResult | null>(null)
const draftResult = ref<MarkPdfDraftResult | null>(null)
const readResult = ref<MarkReadResult | null>(null)
const lastReviewEdits = ref<MarkReviewEdits | null>(null)
const renderedReviewEdits = ref<MarkReviewEdits | null>(null)
const advancedOpen = ref(false), stage = ref('')
const sheetInfo = ref<MarkSourceInspection | null>(null), sheetLoading = ref(false), worksheets = ref<string[]>([])
const busy = ref(false), loading = ref(false), error = ref(''), previewUrl = ref('')
const layout = ref<SupplierMarkLayout | null>(null), layoutLoading = ref(false), editingLayout = ref(false)
const engine = ref<'excel_original' | 'customer_layout' | 'deepseek_zumiez'>('deepseek_zumiez')
const aiStatus = ref<MarkPdfAiStatus | null>(null), aiConsent = ref(false)
const aiMode = computed(() => engine.value === 'deepseek_zumiez')
const supplements = ref<MarkPdfSupplements>({})
const sourceItem = ref('')
const supplementFields = [
  { key: 'quantity', title: '每箱数量', placeholder: '如 12 PCS' }, { key: 'carton_total', title: '总箱数', placeholder: '如 42' },
  { key: 'dimensions', title: '长宽高（cm）', placeholder: '如 56.5 x 31.4 x 63.5 CM' },
  { key: 'net_weight', title: '每箱净重（kg）', placeholder: '如 5.04 KGS' }, { key: 'gross_weight', title: '每箱毛重（kg）', placeholder: '如 5.93 KGS' },
] as const
const input = ref<HTMLInputElement | null>(null)
const canWrite = computed(() => auth.can('carton_supplier:read', '*', '*') && (factory.value
  ? auth.can('carton_supplier:edit', factory.value, '*') : props.factoryIds.some(id => auth.can('carton_supplier:edit', id, '*'))))
const choices = computed(() => stored.value ? orders.value.filter(order => stored.value!.orders.some(link => link.id === order.id && link.issue_id === order.issue_id)) : orders.value)
const selected = computed(() => choices.value.find(order => order.id === orderId.value))
const confirmedTemplate = computed(() => !selected.value && sheetInfo.value?.selected.length === worksheets.value.length
  && sheetInfo.value.selected.every(name => worksheets.value.includes(name)) ? sheetInfo.value.confirmed_template : undefined)
const canGenerate = computed(() => !busy.value && !loading.value && !layoutLoading.value && !editingLayout.value
  && !sheetLoading.value && canWrite.value && !!(file.value || stored.value)
  && (!aiMode.value || !!selected.value || (!!sheetInfo.value && worksheets.value.length > 0))
  && (aiMode.value ? (!selected.value && !!readResult.value) || !!confirmedTemplate.value || (!!aiStatus.value?.available && aiConsent.value) : selected.value ? !!layout.value : engine.value === 'excel_original'))
let generation = 0, controller = new AbortController()
let layoutGeneration = 0
function clearPreview() { if (previewUrl.value) URL.revokeObjectURL(previewUrl.value); previewUrl.value = '' }
async function reset() {
  const token = ++generation
  controller.abort(); controller = new AbortController(); clearPreview()
  busy.value = false; loading.value = false; error.value = ''; result.value = null; draftResult.value = null; orders.value = []; orderId.value = ''; file.value = null
  readResult.value = null; lastReviewEdits.value = null; renderedReviewEdits.value = null; stage.value = ''; advancedOpen.value = false
  sheetInfo.value = null; sheetLoading.value = false; worksheets.value = []
  layoutGeneration++; layout.value = null; layoutLoading.value = false; editingLayout.value = false
  aiStatus.value = null; aiConsent.value = false; engine.value = 'deepseek_zumiez'
  supplements.value = {}
  sourceItem.value = ''
  stored.value = props.source && props.source.factory_id === factory.value && props.factoryIds.includes(factory.value) ? props.source : null
  if (!canWrite.value) { stored.value = null; return }
  if (!factory.value) { void loadLayout(); return }
  if (!props.factoryIds.includes(factory.value)) { stored.value = null; return }
  loading.value = true
  try {
    const available = await cartonSupplierPortalApi.markUploadOrders(factory.value, controller.signal)
    if (token !== generation) return
    orders.value = available
    void loadLayout()
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}
function chooseFiles(files: File[]) {
  if (busy.value || !canWrite.value || !files.length) return
  if (files.length !== 1 || !/\.(xlsx|xls)$/i.test(files[0]!.name) || !files[0]!.size || files[0]!.size > 20 * 1024 * 1024) {
    error.value = '请选择一个 .xls / .xlsx 文件，最多 20 MB。'; return
  }
  file.value = files[0]!; stored.value = null; result.value = null; draftResult.value = null; error.value = ''; clearPreview()
  readResult.value = null
  aiConsent.value = false
  supplements.value = {}
  sourceItem.value = ''
  if (input.value) input.value.value = ''
  if (aiMode.value && !selected.value) void inspectSource()
}
async function generate() {
  if (!canGenerate.value) return
  if (!selected.value) {
    if (aiMode.value) {
      if (readResult.value && lastReviewEdits.value) await renderReviewed(lastReviewEdits.value)
      else await readForReview()
    } else await generateDraft()
    return
  }
  const layoutId = aiMode.value ? aiStatus.value?.template_id : layout.value?.id
  if (!layoutId) return
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
    const filled = Object.fromEntries(Object.entries(supplements.value).filter(([key, value]) => value?.trim() && (!aiMode.value || ['quantity', 'carton_total'].includes(key))).map(([key, value]) => [key, value!.trim()]))
    const converted = await cartonSupplierPortalApi.generateMarkPdf({ factory_id: target, order_id: order.id,
      issue_id: order.issue_id, excel_asset_id: original.id, expected_revision: original.revision, layout_id: layoutId,
      ...(aiMode.value ? { engine: 'deepseek_zumiez' as const, ai_consent: true } : {}),
      ...(Object.keys(filled).length ? { supplements: filled } : {}),
      ...(!aiMode.value && sourceItem.value.trim() ? { source_item: sourceItem.value.trim() } : {}) }, controller.signal)
    if (token !== generation) return
    result.value = converted; emit('saved')
    await showPreview()
  } catch (cause) {
    if (token === generation) error.value = `生成未完成：${getApiErrorMessage(cause)}。原稿已入库时可以直接重试；请求中断后请先刷新资料库确认 PDF 是否已保存。`
  } finally { if (token === generation) busy.value = false }
}
async function generateDraft() {
  const token = generation
  busy.value = true; error.value = ''; result.value = null; draftResult.value = null; clearPreview()
  try {
    const filled = aiMode.value ? Object.fromEntries(Object.entries(supplements.value).filter(([key, value]) =>
      ['quantity', 'carton_total'].includes(key) && value?.trim()).map(([key, value]) => [key, value!.trim()])) : {}
    const converted = await cartonSupplierPortalApi.generateMarkPdfDraft({
      ...(factory.value ? { factory_id: factory.value } : {}),
      ...(stored.value ? { excel_asset_id: stored.value.id, expected_revision: stored.value.revision } : { excel: file.value! }),
      engine: aiMode.value ? 'deepseek_zumiez' : 'excel_original',
      ...(aiMode.value ? { ai_consent: true, supplements: filled } : {}),
    }, controller.signal)
    if (token !== generation) return
    converted.file_name = (stored.value?.file_name || file.value?.name || '箱唛').replace(/\.(xls|xlsx)$/i, '') + '_审阅稿.pdf'
    draftResult.value = converted; previewUrl.value = URL.createObjectURL(converted.blob)
  } catch (cause) {
    if (token === generation) error.value = `生成未完成：${getApiErrorMessage(cause).replace(/[。；;\s]+$/, '')}。未自动重试，请核实后再生成。`
  } finally { if (token === generation) busy.value = false }
}
function draftSource() {
  return { ...(factory.value ? { factory_id: factory.value } : {}),
    ...(stored.value ? { excel_asset_id: stored.value.id, expected_revision: stored.value.revision } : { excel: file.value! }), worksheets: worksheets.value }
}
async function inspectSource() {
  if (!canWrite.value || selected.value || !aiMode.value || (!file.value && !stored.value)) return
  const token = generation, original = file.value, source = stored.value
  sheetLoading.value = true; sheetInfo.value = null; worksheets.value = []
  try {
    const value = await cartonSupplierPortalApi.inspectMarkPdfDraft(draftSource(), controller.signal)
    if (token !== generation || file.value !== original || stored.value !== source || selected.value || !aiMode.value) return
    sheetInfo.value = value; worksheets.value = value.selected
  } catch (cause) { if (token === generation && file.value === original && stored.value === source) error.value = `工作表读取未完成：${getApiErrorMessage(cause)}` }
  finally { if (token === generation && file.value === original && stored.value === source) sheetLoading.value = false }
}
async function readForReview() {
  if (busy.value || !canWrite.value || (!confirmedTemplate.value && (!aiStatus.value?.available || !aiConsent.value)) || !worksheets.value.length) return
  const token = generation
  busy.value = true; stage.value = '正在理解原稿与制版要求…'; error.value = ''; draftResult.value = null; readResult.value = null; lastReviewEdits.value = null; renderedReviewEdits.value = null; clearPreview()
  try {
    const value = await cartonSupplierPortalApi.readMarkPdfDraft({ ...draftSource(), ...(confirmedTemplate.value ? { ai_consent: false } : {}) }, controller.signal)
    if (token !== generation) return
    readResult.value = value
    const edits: MarkReviewEdits = { edits: {}, reviewed_notes: [], paper: value.paper, orientation: value.orientation, include_sources: false }
    lastReviewEdits.value = edits; stage.value = '原稿已读取，正在生成预览…'
    await renderPreview(value, edits, token)
  } catch (cause) {
    if (token === generation) error.value = readResult.value
      ? `原稿已读取，预览生成未完成：${getApiErrorMessage(cause)}。可再次生成预览，不会重新调用 API。`
      : `原稿读取未完成：${getApiErrorMessage(cause)}。未自动重试；只有通过本地检查才会调用 API。`
  } finally { if (token === generation) { busy.value = false; stage.value = '' } }
}
async function renderPreview(review: MarkReadResult, edits: MarkReviewEdits, token: number) {
  const value = await cartonSupplierPortalApi.renderReviewedMarkDraft(draftSource(), review, edits, controller.signal)
  if (token !== generation) return
  value.file_name = (stored.value?.file_name || file.value?.name || '箱唛').replace(/\.(xls|xlsx)$/i, '') + '_审阅稿.pdf'
  draftResult.value = value; renderedReviewEdits.value = JSON.parse(JSON.stringify(edits)) as MarkReviewEdits; clearPreview(); previewUrl.value = URL.createObjectURL(value.blob)
}
async function renderReviewed(edits: MarkReviewEdits) {
  if (!readResult.value || busy.value || !canWrite.value) return
  const token = generation
  busy.value = true; stage.value = '正在更新预览，不重新读稿…'; error.value = ''; lastReviewEdits.value = JSON.parse(JSON.stringify({ ...edits, include_sources: false })) as MarkReviewEdits
  try {
    await renderPreview(readResult.value, lastReviewEdits.value, token)
  } catch (cause) {
    if (token === generation) error.value = `排版未完成：${getApiErrorMessage(cause)}。本次没有再次调用 API。`
  } finally { if (token === generation) { busy.value = false; stage.value = '' } }
}
async function downloadReviewRecord() {
  if (!readResult.value || !renderedReviewEdits.value || busy.value || !canWrite.value) return
  const token = generation
  busy.value = true; stage.value = '正在整理完整核对记录…'; error.value = ''
  try {
    const value = await cartonSupplierPortalApi.renderReviewedMarkDraft(draftSource(), readResult.value, { ...renderedReviewEdits.value, include_sources: true }, controller.signal)
    if (token !== generation) return
    const url = URL.createObjectURL(value.blob), anchor = document.createElement('a')
    anchor.href = url; anchor.download = (stored.value?.file_name || file.value?.name || '箱唛').replace(/\.(xls|xlsx)$/i, '') + '_核对记录.pdf'; anchor.click()
    URL.revokeObjectURL(url)
  } catch (cause) { if (token === generation) error.value = `核对记录下载未完成：${getApiErrorMessage(cause)}。没有再次调用 API。` }
  finally { if (token === generation) { busy.value = false; stage.value = '' } }
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
  if (!previewUrl.value || (!result.value && !draftResult.value)) return
  const anchor = document.createElement('a'); anchor.href = previewUrl.value; anchor.download = result.value?.asset.file_name || draftResult.value!.file_name; anchor.click()
}
watch([() => props.factoryIds.join('\0'), () => props.source, () => auth.currentUser?.id, () => auth.authorizationVersion], () => {
  const target = props.source && props.factoryIds.includes(props.source.factory_id) ? props.source.factory_id : props.factoryIds.length === 1 ? props.factoryIds[0]! : ''
  if (factory.value !== target) factory.value = target
  void reset()
}, { immediate: true })
watch([factory, canWrite], () => void reset())
async function loadLayout() {
  const token = ++layoutGeneration, context = generation, order = selected.value
  layout.value = null; editingLayout.value = false; layoutLoading.value = false; result.value = null; draftResult.value = null; readResult.value = null; clearPreview()
  aiStatus.value = null; aiConsent.value = false
  supplements.value = {}
  sourceItem.value = ''
  if (!canWrite.value) return
  if (!order) {
    void inspectSource()
    if (engine.value === 'customer_layout') engine.value = 'deepseek_zumiez'
    layoutLoading.value = true
    try {
      const status = await cartonSupplierPortalApi.markPdfDraftStatus(factory.value, controller.signal)
      if (token === layoutGeneration && context === generation) aiStatus.value = status
    } catch { if (token === layoutGeneration && context === generation) aiStatus.value = { available: false, template_id: '', name: '', model: '', message: 'DeepSeek状态读取失败，请刷新后重试。' } }
    finally { if (token === layoutGeneration && context === generation) layoutLoading.value = false }
    return
  }
  engine.value = 'customer_layout'
  layoutLoading.value = true
  try {
    const [versions, ai] = await Promise.allSettled([
      cartonSupplierPortalApi.markLayouts(factory.value, order, controller.signal),
      cartonSupplierPortalApi.markPdfAiStatus(factory.value, order, controller.signal),
    ])
    if (token !== layoutGeneration || context !== generation) return
    if (versions.status === 'fulfilled') layout.value = versions.value[0] ?? null
    else error.value = getApiErrorMessage(versions.reason)
    aiStatus.value = ai.status === 'fulfilled' ? ai.value : { available: false, template_id: '', name: '', model: '', message: 'DeepSeek状态读取失败，请刷新后重试。' }
  } catch (cause) { if (token === layoutGeneration && context === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === layoutGeneration && context === generation) layoutLoading.value = false }
}
function layoutSaved(saved: SupplierMarkLayout) { layout.value = saved; supplements.value = {}; sourceItem.value = ''; editingLayout.value = false; result.value = null; clearPreview() }
watch(supplements, () => { result.value = null; draftResult.value = null; aiConsent.value = false; clearPreview() }, { deep: true })
watch(sourceItem, () => { result.value = null; draftResult.value = null; aiConsent.value = false; clearPreview() })
watch(engine, () => { result.value = null; draftResult.value = null; readResult.value = null; sheetInfo.value = null; aiConsent.value = false; error.value = ''; clearPreview(); if (aiMode.value && !selected.value) void inspectSource() })
watch(worksheets, () => { readResult.value = null; draftResult.value = null; aiConsent.value = false; clearPreview() }, { deep: true })
watch(() => selected.value ? `${selected.value.id}:${selected.value.issue_id}` : '', () => void loadLayout())
onBeforeUnmount(() => { generation++; controller.abort(); clearPreview() })
</script>

<template>
  <section class="rounded-xl border bg-white p-4 sm:p-6" aria-label="箱唛文档生成 PDF">
    <h2 class="text-lg font-bold">文档生成 PDF</h2>
    <p class="mt-1 text-sm leading-6 text-slate-500">上传原稿，自动读稿并生成预览；有缺项时再补充。厂区沿用当前范围，无需先选采购订单。</p>
    <p v-if="!selected" class="mt-1 text-xs leading-5 text-slate-500">合同、货号和数量只取本次原稿或本次明确补充，不借用其他订单数据。</p>
    <p v-if="!canWrite" class="mt-4 text-sm text-amber-800">当前账号没有此厂区的资料提交权限。</p>
    <div class="mt-4 rounded-lg border-2 border-dashed border-teal-200 p-4" @dragover.prevent @drop.prevent="chooseFiles(Array.from($event.dataTransfer?.files ?? []))">
      <input ref="input" type="file" accept=".xls,.xlsx" class="sr-only" aria-label="选择生成 PDF 的 Excel" :disabled="busy || !canWrite" @change="chooseFiles(Array.from(($event.target as HTMLInputElement).files ?? []))">
      <div class="flex flex-wrap gap-3"><button type="button" :disabled="busy || !canWrite" class="rounded-lg border px-4 py-2 disabled:opacity-50" @click="input?.click()">上传 Excel</button><button type="button" :disabled="busy" class="rounded-lg border px-4 py-2" @click="emit('choose')">从资料库选择 Excel</button><button type="button" aria-label="生成箱唛预览" :disabled="!canGenerate" class="rounded-lg bg-teal-700 px-4 py-2 font-semibold text-white disabled:opacity-50" @click="generate">{{ busy ? '正在处理…' : !selected && aiMode ? readResult ? '重新生成预览（不重新读稿）' : '生成预览' : '生成 PDF' }}</button></div>
      <p class="mt-3 break-all text-sm">{{ stored?.file_name || file?.name || '支持 .xls / .xlsx，单个文件最多 20 MB；可直接拖入。' }}</p>
    </div>
    <div v-if="aiMode" class="mt-3 space-y-2 text-sm">
      <p v-if="confirmedTemplate" role="status" class="rounded-lg bg-teal-50 p-3 text-teal-900">已匹配 {{ confirmedTemplate.name }} V{{ confirmedTemplate.version }}，将从本次原稿取值，本地生成左右箱唛，不调用 API。</p>
      <p v-else-if="layoutLoading" role="status" class="text-slate-500">正在检查读稿服务…</p>
      <p v-else-if="!aiStatus?.available" role="status" class="rounded-lg bg-amber-50 p-3 text-amber-900">{{ aiStatus?.message || '读稿服务暂不可用，可在生成设置中选择原版导出。' }}</p>
      <label v-else class="flex items-start gap-2 leading-6 text-slate-600"><input v-model="aiConsent" type="checkbox" aria-label="同意发送本单必要文字给 DeepSeek" :disabled="busy" class="mt-1.5 shrink-0"><span>同意将本单文字、备注及本地识别的图片文字交给 DeepSeek 读稿；不发送原文件或图片像素。点击生成时读取一次，修改预览不再调用。</span></label>
    </div>
    <p v-if="selected" class="mt-3 rounded-lg bg-teal-50 p-3 text-sm text-teal-900">已关联 {{ selected.customer_name }} · 合同 {{ selected.contract_no }} · PO {{ selected.customer_po || '未填写' }} · ITEM {{ selected.item_no }}，生成后按原流程保存到资料库。</p>
    <p v-if="busy && stage" role="status" class="mt-3 text-sm text-teal-800">{{ stage }}</p>
    <p v-if="sheetInfo && worksheets.length < sheetInfo.worksheets.length" class="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">本次仅选中 {{ worksheets.length }} / {{ sheetInfo.worksheets.length }} 张工作表，请在生成设置中确认读取范围。</p>
    <details :open="advancedOpen" class="mt-4 rounded-lg border p-3 text-sm" aria-label="生成设置" @toggle="advancedOpen = ($event.target as HTMLDetailsElement).open">
      <summary class="cursor-pointer font-semibold">生成设置（选填）</summary>
    <details v-if="orders.length" class="mt-4 rounded-lg border p-3 text-sm">
      <summary class="cursor-pointer font-semibold">关联采购订单（选填）{{ selected ? ` · ${selected.contract_no}` : '' }}</summary>
      <label class="mt-3 block">采购订单<select v-model="orderId" aria-label="PDF 生成订单" :disabled="busy || loading || !canWrite" class="mt-1 block w-full rounded-lg border bg-white p-2"><option value="">暂不关联，先生成审阅稿</option><option v-for="order in choices" :key="order.id" :value="order.id">{{ order.customer_name }} · {{ order.contract_no }} · {{ order.item_no }} · {{ order.document_no }}</option></select></label>
    </details>
    <label class="mt-4 block text-sm font-semibold">生成方式<select v-model="engine" aria-label="PDF 生成方式" :disabled="busy || layoutLoading || editingLayout" class="mt-1 block w-full rounded-lg border bg-white p-2 sm:max-w-md"><option v-if="!selected" value="excel_original">按 Excel 原版导出（不读取制版备注）</option><option v-if="selected" value="customer_layout">客户固定模板</option><option value="deepseek_zumiez">{{ selected ? 'DeepSeek · Zumiez 原稿与备注' : 'DeepSeek · 读取原稿并核对' }}</option></select></label>
    <p v-if="!selected" class="mt-2 text-xs leading-5 text-slate-500">先预览、下载，不自动入库或提交审核。需要入库时再上传到资料库并关联订单；全部厂区范围也可直接使用新 Excel 生成。</p>
    <div v-if="selected && !aiMode" class="mt-3 flex flex-wrap items-center gap-3 rounded-lg border p-3 text-sm">
      <span v-if="layoutLoading">正在读取客户模板…</span><span v-else-if="layout">客户模板：{{ layout.name }} · V{{ layout.version }}</span><span v-else>此客户还没有排版模板，先用历史稿确认一次。</span>
      <button type="button" :disabled="busy || layoutLoading || !canWrite" class="rounded border px-3 py-1 disabled:opacity-50" @click="editingLayout = !editingLayout">{{ layout ? '调整客户模板' : '建立客户模板' }}</button>
    </div>
    <CartonSupplierMarkLayout v-if="editingLayout && selected && canWrite" :key="`${factory}:${selected.id}:${layout?.id || 'new'}`" :factory="factory" :order="selected" :current="layout" @saved="layoutSaved" @close="editingLayout = false"/>
    <details v-if="(aiMode && selected) || layout?.config?.series === 'zuru'" class="mt-3 rounded-lg border p-3 text-sm">
      <summary class="cursor-pointer font-semibold">本单缺少的内容（需要时补齐）</summary>
      <p class="mt-2 text-xs text-slate-500">先读取 Excel；{{ selected ? '缺失时取采购单中唯一外箱明细，仍缺少时可明确补齐。' : '未关联订单时，仅使用原稿和本次明确补齐的内容。' }}补齐不会覆盖原稿已有值，也不会成为客户模板的固定内容。</p>
      <div class="mt-3 grid gap-3 sm:grid-cols-2"><label v-for="field in aiMode ? supplementFields.slice(0, 2) : supplementFields" :key="field.key">{{ field.title }}<input v-model="supplements[field.key]" :disabled="busy" :placeholder="field.placeholder" maxlength="100" class="mt-1 w-full rounded border p-2"></label></div>
      <label v-if="!aiMode" class="mt-3 block">Excel 箱唛货号（与订单不同才填写）<input v-model="sourceItem" :disabled="busy" placeholder="如 77794UQ1；留空按订单货号匹配" maxlength="128" class="mt-1 w-full rounded border p-2"></label>
    </details>
    <fieldset v-if="sheetInfo && !selected && aiMode" class="mt-4 rounded-lg border p-3 text-sm">
      <legend class="px-1 font-semibold">调整读取的工作表（自动选好）</legend>
      <p class="text-xs leading-5 text-slate-500">可去掉翻译表、旧示例或条码目录。每次最多读取2500个文字单元格；只读取勾选范围的文字、备注和图片参考。</p>
      <div class="mt-2 flex flex-wrap gap-3"><label v-for="sheet in sheetInfo.worksheets" :key="sheet.name" class="flex min-w-0 items-start gap-2"><input v-model="worksheets" type="checkbox" :value="sheet.name" :disabled="busy" :aria-label="`读取工作表 ${sheet.name}`" class="mt-1 shrink-0"><span class="break-all">{{ sheet.name }} <span class="text-slate-500">({{ sheet.cells }} 项)</span></span></label></div>
    </fieldset>
      <button v-if="readResult && aiMode && !selected" type="button" :disabled="busy || (!confirmedTemplate && (!aiConsent || !aiStatus?.available)) || !worksheets.length" class="mt-3 rounded-lg border px-3 py-2 disabled:opacity-50" @click="readForReview">{{ confirmedTemplate ? '重新读取原稿（本地套版）' : '重新读稿（再次调用 API）' }}</button>
      <p v-if="sheetInfo && worksheets.length < sheetInfo.worksheets.length" class="mt-2 text-amber-800">本次选中 {{ worksheets.length }} / {{ sheetInfo.worksheets.length }} 张工作表；请确认未排除本单所需数据。</p>
    </details>
    <p v-if="loading" role="status" class="mt-3 text-sm text-slate-500">正在读取可关联订单…</p>
    <p v-else-if="factory && !orders.length && !error" class="mt-3 text-sm text-slate-500">当前范围暂无可关联采购订单，可以先生成审阅稿。</p>
    <p v-if="error" role="alert" class="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">{{ error }}</p>
    <p v-if="sheetLoading" role="status" class="mt-3 text-sm text-slate-500">正在本地读取工作表，不调用 API…</p>
    <CartonMarkReadReview v-if="readResult && !selected && aiMode" :key="readResult.signature" :review="readResult" :applied="renderedReviewEdits" :busy="busy" @render="renderReviewed" />
    <div v-if="draftResult" class="mt-5 space-y-3">
      <p role="status" class="rounded-lg bg-teal-50 p-3 text-sm text-teal-900">{{ draftResult.file_name }} · {{ draftResult.page_count }} 页 · {{ readResult?.mode === 'needs_mapping' ? '待调整预览，AI 排版尚未通过。' : '审阅稿已生成。' }}尚未入库或关联订单。</p>
      <details v-if="draftResult.warnings.length" class="rounded-lg border p-3 text-sm"><summary class="cursor-pointer font-medium">排版提示 · {{ draftResult.warnings.length }} 条</summary><ul class="mt-2 list-inside list-disc leading-6 text-slate-600"><li v-for="warning in draftResult.warnings" :key="warning">{{ warning }}</li></ul></details>
      <div class="flex flex-wrap gap-3"><button type="button" :disabled="busy" class="rounded-lg bg-teal-700 px-4 py-2 font-semibold text-white disabled:opacity-50" @click="download">下载箱唛 PDF</button><button v-if="readResult" type="button" :disabled="busy" class="rounded-lg border px-4 py-2 disabled:opacity-50" @click="downloadReviewRecord">下载完整核对记录</button></div>
      <iframe v-if="previewUrl" :src="previewUrl" title="未关联订单的箱唛 PDF 预览" class="h-[65vh] min-h-96 w-full rounded-lg border"></iframe>
    </div>
    <div v-if="result" class="mt-5 space-y-3">
      <p role="status" class="rounded-lg bg-teal-50 p-3 text-sm text-teal-900">{{ result.asset.file_name }} · {{ result.page_count }} 页 · {{ result.layout_name }} V{{ result.layout_version }} · 已保存到资料库，待核对 / 审核。</p>
      <ul v-if="result.warnings.length" class="list-inside list-disc rounded-lg bg-amber-50 p-3 text-sm text-amber-900"><li v-for="warning in result.warnings" :key="warning">{{ warning }}</li></ul>
      <p class="text-xs text-slate-500">请查看完整内容和素材。{{ aiMode ? 'Zumiez 模板按原稿排版，字段仍需审核；' : layout?.config?.series === 'zuru' ? 'ZURU 按客户版式显示条码号码或重生成条码；Hy-Vee 请打印后扫码验证；' : '打印后扫码验证条码；' }}此处生成客户模板排版审阅稿，生产 1:1 尺寸需另行确认。</p>
      <div class="flex flex-wrap gap-3"><button type="button" :disabled="!previewUrl" class="rounded-lg border px-4 py-2 disabled:opacity-50" @click="download">下载 PDF</button><button v-if="!previewUrl" type="button" class="rounded-lg border px-4 py-2" @click="showPreview">重新打开预览</button><button type="button" :disabled="busy" class="rounded-lg bg-teal-700 px-4 py-2 text-white" @click="goCheck">用 Excel / PDF 核对</button></div>
      <iframe v-if="previewUrl" :src="previewUrl" title="生成的箱唛 PDF 预览" class="h-[65vh] min-h-96 w-full rounded-lg border"></iframe>
    </div>
  </section>
</template>

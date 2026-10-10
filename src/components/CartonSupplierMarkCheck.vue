<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { cartonSupplierPortalApi, type SupplierMarkAsset, type SupplierMarkCheck } from '@/api/cartonSupplierPortal'
import { getApiErrorMessage, getApiErrorMessageAsync } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'
import { factoryContexts } from '@/data/enterpriseMock'

const props = defineProps<{ factoryIds: string[]; source: (SupplierMarkAsset & { factory_id: string }) | null; pdfSource?: (SupplierMarkAsset & { factory_id: string }) | null; refreshKey: number }>()
const emit = defineEmits<{ chooseSource: []; clearSource: []; clearPdfSource: [] }>()
const auth = useAuthStore()
const canRead = computed(() => auth.can('carton_supplier:read', '*', '*'))
const canEdit = computed(() => canRead.value && auth.can('carton_supplier:edit', props.source?.factory_id ?? '*', '*'))
const orderId = ref('')
const order = computed(() => props.source?.orders.find(row => row.id === orderId.value))
const storedPdf = computed(() => props.pdfSource?.kind === 'pdf' && props.pdfSource.factory_id === props.source?.factory_id && props.pdfSource.orders.some(row => row.id === order.value?.id && row.issue_id === order.value?.issue_id) ? props.pdfSource : null)
const pdf = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const form = ref<HTMLElement | null>(null)
const busy = ref(false), loading = ref(false)
const error = ref(''), historyError = ref(''), message = ref('')
const checks = ref<SupplierMarkCheck[]>([])
const expandedId = ref('')
const downloadable = ref('')
let generation = 0, historySequence = 0, controller = new AbortController()
function factoryName(id: string) { return factoryContexts.find(row => row.id === id)?.shortName ?? id }

function selectPdf(files: File[]) {
  if (!canEdit.value || busy.value || !files.length) return
  error.value = ''; message.value = ''
  if (files.length !== 1 || !files[0]!.name.toLowerCase().endsWith('.pdf') || !files[0]!.size || files[0]!.size > 20 * 1024 * 1024) {
    error.value = '请选择一个不超过 20 MB 的非空 PDF 文件。'; return
  }
  pdf.value = files[0]!; emit('clearPdfSource')
}
function fileChanged(event: Event) {
  const input = event.target as HTMLInputElement
  selectPdf(Array.from(input.files ?? [])); input.value = ''
}
async function loadHistory() {
  const token = generation, sequence = ++historySequence
  checks.value = []; historyError.value = ''
  if (!canRead.value || !props.factoryIds.length) return
  loading.value = true
  try {
    const batches = await Promise.all(props.factoryIds.map(async factory => {
      try { return await cartonSupplierPortalApi.markChecks(factory, controller.signal) }
      catch (reason) { throw new Error(`${factoryName(factory)}：${getApiErrorMessage(reason)}`) }
    }))
    if (token === generation && sequence === historySequence) checks.value = batches.flat().sort((a, b) => b.created_at.localeCompare(a.created_at) || b.id.localeCompare(a.id))
  } catch (reason) {
    if (token === generation && sequence === historySequence) historyError.value = getApiErrorMessage(reason)
  } finally { if (token === generation && sequence === historySequence) loading.value = false }
}
async function submit() {
  const source = props.source, selectedOrder = order.value, file = pdf.value
  const libraryPdf = storedPdf.value
  if (!source || !selectedOrder || !(file || libraryPdf) || !canEdit.value || busy.value || !props.factoryIds.includes(source.factory_id)) return
  const token = generation
  busy.value = true; error.value = ''; message.value = ''
  try {
    const record = await cartonSupplierPortalApi.createMarkCheck({ factory_id: source.factory_id,
      order_id: selectedOrder.id, issue_id: selectedOrder.issue_id, excel_asset_id: source.id,
      expected_revision: source.revision, ...(file ? { print_pdf: file } : { pdf_asset_id: libraryPdf!.id, expected_pdf_revision: libraryPdf!.revision }) })
    if (token !== generation) return
    pdf.value = null
    message.value = `核对已保存：${record.check_status}。${record.qc_ready ? '已进入内部箱唛流程，可供 QC 核验。' : '暂不能用于 QC，请修正 PDF 后重新核对，或联系内部人员复核。'}`
    expandedId.value = record.id
    await loadHistory()
  } catch (reason) {
    const detail = await getApiErrorMessageAsync(reason)
    if (token === generation) {
      error.value = `${detail}。若请求中断，请先刷新核对记录确认是否已保存，再重试。`
      await loadHistory()
    }
  } finally { if (token === generation) busy.value = false }
}
async function download(record: SupplierMarkCheck, kind: 'source_excel' | 'print_pdf') {
  if (!canRead.value || downloadable.value) return
  const token = generation
  downloadable.value = record.id; historyError.value = ''
  try {
    const blob = await cartonSupplierPortalApi.downloadMarkCheck(record.id, kind, record.factory_id, controller.signal)
    if (token !== generation) return
    const url = URL.createObjectURL(blob), link = document.createElement('a')
    link.href = url; link.download = kind === 'source_excel' ? record.excel_file_name : record.pdf_file_name
    link.click(); URL.revokeObjectURL(url)
  } catch (reason) {
    const detail = await getApiErrorMessageAsync(reason)
    if (token === generation) historyError.value = detail
  } finally { if (token === generation) downloadable.value = '' }
}
watch(() => props.source, async source => {
  generation++; controller.abort(); controller = new AbortController()
  busy.value = false; downloadable.value = ''; pdf.value = null; error.value = ''; message.value = ''
  orderId.value = source?.orders.length === 1 ? source.orders[0]!.id : ''
  await loadHistory(); await nextTick(); form.value?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
})
watch([() => props.factoryIds.join('\0'), () => props.refreshKey, () => auth.currentUser?.id,
  () => auth.authorizationVersion, canRead, canEdit], () => {
  generation++; controller.abort(); controller = new AbortController()
  busy.value = false; downloadable.value = ''; loading.value = false; pdf.value = null
  error.value = ''; message.value = ''; expandedId.value = ''
  emit('clearSource'); void loadHistory()
}, { immediate: true })
watch(orderId, () => { pdf.value = null; error.value = ''; message.value = '' })
onBeforeUnmount(() => { generation++; controller.abort() })
</script>

<template>
  <div v-if="canRead" class="space-y-5">
    <section ref="form" class="rounded-xl border border-teal-200 bg-white p-4 sm:p-6" aria-label="供应商 Excel / PDF 核对">
      <h2 class="text-xl font-bold">客人 Excel / 印刷 PDF 核对</h2>
      <p class="mt-2 text-sm leading-6 text-slate-500">从资料库一起选择 Excel 与 PDF，也可选择 Excel 后上传新的印刷 PDF。客户、合同和货号沿用采购单资料；发现差异或需复核时，由内部人员决定是否放行。</p>
      <p v-if="!canEdit" role="status" class="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">当前账号可查看资料和核对记录。上传 PDF 需要供应商协同的编辑权限。</p>
      <button type="button" :disabled="busy" class="mt-4 rounded-lg border border-teal-200 px-4 py-2 text-sm font-semibold text-teal-700 disabled:opacity-50" @click="emit('chooseSource')">{{ source ? '重新选择客人 Excel' : '到资料库选择客人 Excel' }}</button>
      <form v-if="source && canEdit" class="mt-4 space-y-4" @submit.prevent="submit">
        <p class="break-all rounded-lg bg-teal-50 p-3 text-sm">{{ factoryName(source.factory_id) }} · 客人 Excel：{{ source.file_name }}</p>
        <label class="block text-sm font-semibold">关联采购订单
          <select v-model="orderId" :disabled="busy" required class="mt-2 w-full rounded-lg border bg-white p-3" aria-label="核对关联采购订单">
            <option value="" disabled>此 Excel 对应多个订单，请选择本次核对的订单</option>
            <option v-for="row in source.orders" :key="row.id" :value="row.id">{{ row.customer_name }} · 合同 {{ row.contract_no }} · ITEM {{ row.item_no }}</option>
          </select>
        </label>
        <dl v-if="order" class="grid gap-3 rounded-lg border bg-slate-50 p-4 text-sm sm:grid-cols-3">
          <div><dt class="text-slate-500">客户</dt><dd class="mt-1 break-all font-semibold">{{ order.customer_name }}</dd></div>
          <div><dt class="text-slate-500">合同 / 客户 PO</dt><dd class="mt-1 break-all font-semibold">{{ order.contract_no }} / {{ order.customer_po || '采购单未填写' }}</dd></div>
          <div><dt class="text-slate-500">ITEM</dt><dd class="mt-1 break-all font-semibold">{{ order.item_no }}</dd></div>
        </dl>
        <div class="rounded-lg border-2 border-dashed border-teal-200 p-4" @dragover.prevent @drop.prevent="selectPdf(Array.from($event.dataTransfer?.files ?? []))">
          <input ref="fileInput" type="file" accept="application/pdf,.pdf" class="sr-only" aria-label="供应商印刷 PDF" :disabled="busy || !order" @change="fileChanged">
          <p class="mb-3 break-all text-sm text-slate-500">{{ pdf ? pdf.name : storedPdf ? `已从资料库选择 PDF：${storedPdf.file_name}` : '选择或拖入一个印刷 PDF，每个文件不超过 20 MB。' }}</p>
          <button type="button" :disabled="busy || !order" class="rounded-lg border bg-white px-4 py-2 text-sm disabled:opacity-50" @click="fileInput?.click()">选择印刷 PDF</button>
        </div>
        <button type="submit" :disabled="busy || !(pdf || storedPdf) || !order" class="w-full rounded-lg bg-teal-700 px-4 py-3 font-semibold text-white disabled:opacity-50">{{ busy ? '正在核对并保存…' : storedPdf ? '使用所选 Excel / PDF 开始核对' : '上传 PDF 并开始核对' }}</button>
      </form>
      <p v-if="error" role="alert" class="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-800">{{ error }}</p>
      <p v-if="message" role="status" class="mt-4 rounded-lg bg-teal-50 p-3 text-sm text-teal-800">{{ message }}</p>
    </section>
    <section class="rounded-xl border bg-white p-4 sm:p-6" aria-label="供应商箱唛核对记录">
      <div class="flex flex-wrap items-center justify-between gap-3"><h2 class="text-lg font-bold">核对 / 审核记录</h2><button type="button" :disabled="loading || busy" class="rounded-lg border px-3 py-2 text-sm disabled:opacity-50" @click="loadHistory">刷新核对记录</button></div>
      <p v-if="historyError" role="alert" class="mt-3 text-sm text-red-700">{{ historyError }}</p>
      <p v-if="loading" role="status" class="mt-4 text-sm text-slate-500">正在读取核对记录…</p>
      <p v-else-if="!checks.length && !historyError" class="mt-4 text-sm text-slate-500">暂无核对或审核记录。可选择 Excel / PDF 核对，或在资料库选择单 PDF / 图片提交人工审核。</p>
      <article v-for="record in checks" :key="record.id" class="mt-4 rounded-lg border p-4">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div><h3 class="break-all font-semibold">{{ factoryName(record.factory_id) }} · {{ record.customer_name }} · {{ record.contract_number }}</h3><p class="mt-1 break-all text-xs text-slate-500">ITEM {{ record.item }} · 版本 {{ record.version }} · {{ record.created_at }} · {{ record.pdf_file_name }}</p></div>
          <div class="text-sm font-semibold" :class="record.qc_ready ? 'text-teal-700' : 'text-amber-700'">{{ record.check_result.review_method === 'manual_sources' ? record.manual_released ? '人工审核通过' : '待人工审核' : record.check_status }} · {{ record.manual_released ? '内部已放行' : record.qc_ready ? '可供 QC 核验' : '待修正 / 内部复核' }}</div>
        </div>
        <p v-if="record.check_result.review_method === 'manual_sources'" class="mt-3 text-sm text-amber-800">{{ record.manual_released ? '人工审核通过，可供 QC 使用' : '单 PDF / 图片已提交，等待内部人工审核' }}<template v-if="record.check_result.review_note">；备注：{{ record.check_result.review_note }}</template></p>
        <div class="mt-3 flex flex-wrap gap-2 text-sm">
          <button type="button" class="rounded border px-3 py-2" :aria-expanded="expandedId === record.id" @click="expandedId = expandedId === record.id ? '' : record.id">查看核对结果</button>
          <a :href="cartonSupplierPortalApi.previewMarkCheckUrl(record.id, record.factory_id)" target="_blank" rel="noopener" class="rounded border px-3 py-2">预览 PDF</a>
          <button type="button" :disabled="!!downloadable" class="rounded border px-3 py-2 disabled:opacity-50" @click="download(record, 'print_pdf')">下载 PDF</button>
          <button v-if="record.excel_file_name" type="button" :disabled="!!downloadable" class="rounded border px-3 py-2 disabled:opacity-50" @click="download(record, 'source_excel')">下载客人 Excel</button>
        </div>
        <div v-if="expandedId === record.id && record.check_result.review_method === 'manual_sources'" class="mt-4 space-y-2 text-sm"><p>此资料未执行 Excel / PDF 自动比对。</p><p v-for="source in record.check_result.source_assets" :key="source.id">原稿：{{ source.file_name }}</p></div>
        <div v-if="expandedId === record.id && record.check_result.review_method !== 'manual_sources'" class="mt-4 space-y-3">
          <p class="text-sm">通过 {{ record.check_result.summary.pass_count }} · 文字差异 {{ record.check_result.summary.changed_count }} · 缺失 {{ record.check_result.summary.missing_count }} · 新增 {{ record.check_result.summary.unexpected_count }} · 需复核 {{ record.check_result.summary.review_count }}</p>
          <div v-for="(item, index) in record.check_result.extraction.filter(row => !row.ok || row.requires_review)" :key="index" class="rounded bg-amber-50 p-3 text-sm text-amber-800">{{ item.review_reason || item.message }}</div>
          <div class="overflow-x-auto"><table class="w-full min-w-[480px] text-left text-sm"><thead><tr class="bg-slate-50"><th class="p-2">结果</th><th class="p-2">Excel 原文</th><th class="p-2">PDF 原文</th><th class="p-2">说明</th></tr></thead><tbody><tr v-for="(item, index) in record.check_result.comparisons" :key="index" class="border-b align-top"><td class="p-2">{{ ({ pass: '通过', changed: '差异', missing: '缺失', unexpected: '新增', review: '复核' })[item.status] }}</td><td class="whitespace-pre-wrap break-all p-2">{{ item.expected }}<p class="text-xs text-slate-400">{{ item.expected_location }}</p></td><td class="whitespace-pre-wrap break-all p-2">{{ item.actual }}<p class="text-xs text-slate-400">{{ item.actual_location }}</p></td><td class="p-2">{{ item.note }}</td></tr></tbody></table></div>
        </div>
      </article>
    </section>
  </div>
</template>

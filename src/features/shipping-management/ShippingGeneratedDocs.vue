<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ChevronDown, Download, FileSpreadsheet, RefreshCw, Trash2 } from '@lucide/vue'
import { getApiErrorMessage } from '@/lib/http'
import {
  deleteGeneratedDoc,
  getGeneratedDoc,
  listGeneratedDocs,
  type GeneratedDoc,
  type GeneratedDocDetail,
} from '@/api/shippingMail'

const props = defineProps<{ factoryId: string; module: 'so' | 'truck' | 'supplement'; label?: string }>()
const emit = defineEmits<{
  'import-cabinet': [payload: { taskId: string; filename: string; header: Record<string, unknown>; lines: Array<Record<string, unknown>> }]
}>()

const docs = ref<GeneratedDoc[]>([])
const loading = ref(false)
const message = ref('')
const pendingId = ref('')
const busyId = ref('')
const selectedDocIds = ref<string[]>([])
const bulkDeleteArmed = ref(false)
const bulkDeleting = ref(false)
const imported = ref<Record<string, boolean>>({})
const selectedId = ref('')
const detail = ref<GeneratedDocDetail | null>(null)
const showDetail = ref(false)
const loadingDetail = ref(false)

const isSo = computed(() => props.module === 'so')
const selectedDoc = computed(() => docs.value.find((doc) => doc.id === selectedId.value) ?? null)
const allDocsSelected = computed(() => docs.value.length > 0 && docs.value.every((doc) => selectedDocIds.value.includes(doc.id)))

function toggleDoc(docId: string) {
  selectedDocIds.value = selectedDocIds.value.includes(docId)
    ? selectedDocIds.value.filter((id) => id !== docId)
    : [...selectedDocIds.value, docId]
  bulkDeleteArmed.value = false
}

function onToggleAllDocs(event: Event) {
  selectedDocIds.value = (event.target as HTMLInputElement).checked ? docs.value.map((doc) => doc.id) : []
  bulkDeleteArmed.value = false
}

async function bulkDeleteDocs() {
  if (!selectedDocIds.value.length) return
  if (!bulkDeleteArmed.value) {
    bulkDeleteArmed.value = true
    window.setTimeout(() => { bulkDeleteArmed.value = false }, 5000)
    return
  }
  bulkDeleting.value = true
  try {
    let deleted = 0
    for (const docId of [...selectedDocIds.value]) {
      try {
        await deleteGeneratedDoc(props.factoryId, docId)
        deleted += 1
      } catch {
        // continue with the rest
      }
    }
    selectedDocIds.value = []
    bulkDeleteArmed.value = false
    selectedId.value = ''
    await load()
    message.value = `已删除 ${deleted} 份生成文件。`
  } finally {
    bulkDeleting.value = false
  }
}

type CabinetField = {
  key: string
  label: string
  hint: string
  type?: 'date' | 'select'
  options?: readonly string[]
}

const fields: CabinetField[] = [
  { key: 'number', label: '柜', hint: '手动' },
  { key: 'shipper', label: '发货商', hint: '固定' },
  { key: 'consignee', label: '收货商', hint: '邮件自动识别' },
  { key: 'cutoff', label: '到货截止日期', hint: '邮件自动识别' },
  { key: 'contractNo', label: '合同号', hint: '邮件自动识别' },
  { key: 'vesselName', label: '船名', hint: '邮件自动识别' },
  { key: 'voyageNo', label: '航次', hint: '邮件自动识别' },
  { key: 'transportCompany', label: '运输公司', hint: '邮件自动识别' },
  { key: 'containerType', label: '柜型', hint: '邮件自动识别' },
  { key: 'tradeTerm', label: '成交方式', hint: '手动', type: 'select', options: ['FOB', 'EXW', 'CIF'] },
  { key: 'country', label: '出口国家', hint: '邮件自动识别' },
  { key: 'destination', label: '出港口', hint: '邮件自动识别' },
  { key: 'bookingNo', label: '订仓号', hint: '邮件自动识别' },
  { key: 'containerNo', label: '柜号', hint: '邮件自动识别' },
  { key: 'tareWeight', label: '柜重', hint: '手动' },
  { key: 'shippingClerk', label: '船务', hint: '手动', type: 'select', options: ['农建壮', '小美', 'SO'] },
]

const form = reactive<Record<string, string>>({})

function importedKey(id: string) {
  return `shipping-cabinet-imported:${props.factoryId}:${id}`
}

function isImported(doc: GeneratedDoc | null) {
  return Boolean(doc && imported.value[doc.id])
}

function downloadUrl(doc: GeneratedDoc) {
  return `/api/shipping/generated-docs/${doc.id}/download?factory_id=${encodeURIComponent(props.factoryId)}`
}

function value(value: unknown) {
  return value == null ? '' : String(value)
}

function fillForm(source: GeneratedDocDetail) {
  const header = source.header ?? {}
  form.number = value(header.number)
  form.shipper = value(header.shipper) || '华兴玩具制品（河源）有限公司'
  form.consignee = value(header.consignee)
  form.cutoff = value(header.cutoff)
  form.contractNo = value(header.contractNo) || value(source.lines?.[0]?.contract)
  form.vesselName = value(header.vessel)
  form.voyageNo = value(header.voyage)
  form.transportCompany = value(header.transportCompany)
  form.containerType = value(header.containerType)
  form.tradeTerm = value(header.tradeTerm) || 'FOB'
  form.country = value(header.destinationCountry)
  form.destination = value(header.destination) || value(header.to_port)
  form.bookingNo = value(header.bookingNo) || value(header.soNo)
  form.containerNo = value(header.containerNo)
  form.tareWeight = value(header.tareWeight)
  form.shippingClerk = value(header.shippingClerk) || value(header.preparer)
}

async function loadDetail(doc: GeneratedDoc | null) {
  detail.value = null
  if (!doc) return
  loadingDetail.value = true
  try {
    detail.value = await getGeneratedDoc(props.factoryId, doc.id)
    fillForm(detail.value)
  } catch (error) {
    const text = getApiErrorMessage(error)
    if (text.includes('生成文件不存在')) {
      docs.value = docs.value.filter((item) => item.id !== doc.id)
      selectedId.value = docs.value[0]?.id ?? ''
      detail.value = null
    }
    message.value = `读取文件详情失败：${text}`
  } finally {
    loadingDetail.value = false
  }
}

async function load() {
  loading.value = true
  try {
    docs.value = await listGeneratedDocs(props.factoryId, props.module)
    const ids = new Set(docs.value.map((doc) => doc.id))
    selectedDocIds.value = selectedDocIds.value.filter((id) => ids.has(id))
    imported.value = Object.fromEntries(docs.value.map((doc) => [doc.id, window.localStorage.getItem(importedKey(doc.id)) === '1']))
    if (!docs.value.some((doc) => doc.id === selectedId.value)) selectedId.value = docs.value[0]?.id ?? ''
    await loadDetail(selectedDoc.value)
    message.value = ''
  } catch (error) {
    message.value = getApiErrorMessage(error)
  } finally {
    loading.value = false
  }
}

async function selectDoc(doc: GeneratedDoc) {
  if (selectedId.value === doc.id) return
  selectedId.value = doc.id
  showDetail.value = false
  await loadDetail(doc)
}

function buildHeader(): Record<string, unknown> {
  if (!detail.value) return {}
  return {
    ...(detail.value.header ?? {}),
    shipper: form.shipper,
    consignee: form.consignee,
    contractNo: form.contractNo,
    vessel: form.vesselName,
    voyage: form.voyageNo,
    cutoff: form.cutoff,
    number: form.number,
    bookingNo: form.bookingNo,
    transportCompany: form.transportCompany,
    containerType: form.containerType,
    tradeTerm: form.tradeTerm,
    destinationCountry: form.country,
    destination: form.destination,
    containerNo: form.containerNo,
    tareWeight: form.tareWeight,
    shippingClerk: form.shippingClerk,
    preparer: form.shippingClerk,
  }
}

function importCabinet() {
  if (!detail.value) return
  emit('import-cabinet', {
    taskId: detail.value.task_id,
    filename: detail.value.filename,
    header: buildHeader(),
    lines: detail.value.lines ?? [],
  })
  imported.value = { ...imported.value, [detail.value.id]: true }
  window.localStorage.setItem(importedKey(detail.value.id), '1')
  message.value = `已把 ${detail.value.filename} 的表头与明细导入柜货单。`
}

function askDelete(doc: GeneratedDoc) {
  pendingId.value = doc.id
  window.setTimeout(() => {
    if (pendingId.value === doc.id) pendingId.value = ''
  }, 5000)
}

async function confirmDelete(doc: GeneratedDoc) {
  busyId.value = doc.id
  try {
    await deleteGeneratedDoc(props.factoryId, doc.id)
    pendingId.value = ''
    selectedId.value = ''
    await load()
  } catch (error) {
    message.value = `删除失败：${getApiErrorMessage(error)}`
  } finally {
    busyId.value = ''
  }
}

onMounted(load)
watch(() => props.factoryId, load)
</script>

<template>
  <section class="rounded-xl border border-emerald-100/80 bg-white" aria-label="自动生成文件">
    <header class="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
      <div class="flex items-center gap-2">
        <FileSpreadsheet class="size-4 text-emerald-600" aria-hidden="true" />
        <h3 class="text-[13px] font-bold text-slate-800">{{ isSo ? '邮件信息资料' : `已自动生成${label ? ` · ${label}` : ''}` }}</h3>
        <span class="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold tabular-nums text-emerald-700">{{ docs.length }}</span>
      </div>
      <div class="flex items-center gap-2">
        <label v-if="docs.length" class="inline-flex items-center gap-1 text-[10px] font-medium text-slate-500">
          <input type="checkbox" aria-label="全选生成文件" :checked="allDocsSelected" @change="onToggleAllDocs">
          全选
        </label>
        <button
          type="button"
          class="inline-flex h-7 items-center gap-1 rounded border px-2 text-[11px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-40"
          :class="bulkDeleteArmed ? 'border-rose-300 bg-rose-50 text-rose-700' : 'border-rose-200 text-rose-600 hover:bg-rose-50'"
          :disabled="!selectedDocIds.length || bulkDeleting"
          @click="bulkDeleteDocs"
        >
          <Trash2 class="size-3" />{{ bulkDeleteArmed ? `确认删除 ${selectedDocIds.length} 份` : `删除${selectedDocIds.length ? ` (${selectedDocIds.length})` : ''}` }}
        </button>
        <button
          v-if="bulkDeleteArmed"
          type="button"
          class="inline-flex h-7 items-center rounded border border-slate-200 px-2 text-[11px] font-semibold text-slate-600 hover:bg-slate-50"
          @click="bulkDeleteArmed = false"
        >取消删除</button>
        <button type="button" class="inline-flex h-7 items-center gap-1 rounded border border-slate-200 px-2 text-[11px] text-slate-600" @click="load">
          <RefreshCw class="size-3" :class="loading ? 'animate-spin' : ''" />刷新
        </button>
      </div>
    </header>

    <p v-if="message" class="break-all px-4 py-2 text-[11px]" :class="message.startsWith('已') ? 'text-emerald-700' : 'text-rose-600'">{{ message }}</p>

    <template v-if="isSo && docs.length">
      <div v-if="docs.length > 1" class="flex flex-wrap gap-2 border-b border-slate-100 px-4 py-2">
        <div v-for="doc in docs" :key="doc.id" class="inline-flex max-w-full items-center gap-1.5 rounded-lg border px-2 py-1 text-[11px]" :class="doc.id === selectedId ? 'border-emerald-300 bg-emerald-50' : 'border-slate-200'">
          <input type="checkbox" :aria-label="`选择 ${doc.filename}`" :checked="selectedDocIds.includes(doc.id)" @change="toggleDoc(doc.id)">
          <button type="button" class="inline-flex max-w-full items-center gap-1.5" :class="doc.id === selectedId ? 'text-emerald-800' : 'text-slate-600'" @click="selectDoc(doc)">
            <span v-if="!isImported(doc)" class="size-1.5 rounded-full bg-rose-500"></span>
            <span class="truncate">{{ doc.filename }}</span>
          </button>
        </div>
      </div>

      <div v-if="selectedDoc" class="p-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-2 text-[11px] font-semibold text-slate-700">
            <input v-if="docs.length === 1" type="checkbox" :aria-label="`选择 ${selectedDoc.filename}`" :checked="selectedDocIds.includes(selectedDoc.id)" @change="toggleDoc(selectedDoc.id)">
            <span v-if="!isImported(selectedDoc)" class="size-2 rounded-full bg-rose-500" aria-label="待确认柜货单"></span>
            {{ selectedDoc.filename }}
          </div>
          <span class="text-[10px] text-slate-400 tabular-nums">{{ selectedDoc.created_at.replace('T', ' ') }}</span>
        </div>

        <div class="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <label v-for="field in fields" :key="field.key" class="block">
            <span class="mb-0.5 flex items-center gap-1 text-[9px] font-medium text-slate-400">
              {{ field.label }}
              <span class="rounded bg-slate-100 px-1 py-0.5 text-[8px] text-slate-500">{{ field.hint }}</span>
            </span>
            <select
              v-if="field.type === 'select'"
              v-model="form[field.key]"
              class="h-8 w-full rounded-md border border-slate-200 bg-slate-50 px-2 text-[11px] text-slate-800 outline-none focus:border-emerald-400"
            >
              <option v-for="option in field.options ?? []" :key="option" :value="option">{{ option }}</option>
            </select>
            <input
              v-else
              v-model="form[field.key]"
              :type="field.type === 'date' ? 'date' : 'text'"
              :placeholder="field.hint === '手动' ? '装柜后补录' : ''"
              class="h-8 w-full rounded-md border border-slate-200 bg-slate-50 px-2 text-[11px] text-slate-800 outline-none placeholder:text-slate-300 focus:border-emerald-400"
            >
          </label>
        </div>

        <div class="mt-2 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-2">
          <button
            type="button"
            class="inline-flex h-7 items-center gap-1 rounded-md px-2.5 text-[10px] font-semibold text-white disabled:opacity-50"
            :class="isImported(selectedDoc) ? 'bg-emerald-600' : 'bg-rose-600'"
            :disabled="busyId === selectedDoc.id || loadingDetail"
            @click="importCabinet"
          >
            {{ isImported(selectedDoc) ? '已导入柜货单' : '导入柜货单' }}
          </button>
          <a :href="downloadUrl(selectedDoc)" :download="selectedDoc.filename" target="_blank" rel="noopener" class="inline-flex h-7 items-center gap-1 rounded-md border border-emerald-200 px-2.5 text-[10px] font-semibold text-emerald-700">
            <Download class="size-3" />下载
          </a>
          <button type="button" class="inline-flex h-7 items-center gap-1 rounded-md border border-slate-200 px-2.5 text-[10px] font-semibold text-slate-600" @click="showDetail = !showDetail">
            <ChevronDown class="size-3" :class="showDetail ? 'rotate-180' : ''" />打开详情信息
          </button>
          <button
            v-if="pendingId === selectedDoc.id"
            type="button"
            class="inline-flex h-7 items-center gap-1 rounded-md border border-rose-300 px-2.5 text-[10px] font-semibold text-rose-700 disabled:opacity-50"
            :disabled="busyId === selectedDoc.id"
            @click="confirmDelete(selectedDoc)"
          >
            <Trash2 class="size-3" />确认删除
          </button>
          <button v-else type="button" class="inline-flex h-7 items-center gap-1 rounded-md border border-rose-200 px-2.5 text-[10px] font-semibold text-rose-600" @click="askDelete(selectedDoc)">
            <Trash2 class="size-3" />删除
          </button>
        </div>

        <dl v-if="showDetail" class="mt-3 grid gap-2 rounded-lg bg-slate-50 p-3 text-[11px] text-slate-600 sm:grid-cols-2">
          <div><dt class="text-slate-400">文件名</dt><dd class="break-all font-medium text-slate-700">{{ selectedDoc.filename }}</dd></div>
          <div><dt class="text-slate-400">模块</dt><dd class="font-medium text-slate-700">{{ selectedDoc.module }}</dd></div>
          <div><dt class="text-slate-400">任务 ID</dt><dd class="break-all font-medium text-slate-700">{{ selectedDoc.task_id || '—' }}</dd></div>
          <div><dt class="text-slate-400">生成时间</dt><dd class="font-medium text-slate-700">{{ selectedDoc.created_at.replace('T', ' ') }}</dd></div>
          <div><dt class="text-slate-400">明细行数</dt><dd class="font-medium text-slate-700">{{ detail?.lines.length ?? 0 }}</dd></div>
        </dl>
      </div>
    </template>

    <template v-else>
      <div v-if="docs.length" class="divide-y divide-slate-100">
        <div v-for="doc in docs" :key="doc.id" class="flex flex-wrap items-center justify-between gap-2 px-4 py-1.5 text-[11px]">
          <span class="flex min-w-0 items-center gap-2">
            <input type="checkbox" :aria-label="`选择 ${doc.filename}`" :checked="selectedDocIds.includes(doc.id)" @change="toggleDoc(doc.id)">
            <span class="truncate font-semibold text-slate-700">{{ doc.filename }}</span>
          </span>
          <span class="text-slate-400 tabular-nums">{{ doc.created_at.replace('T', ' ') }}</span>
          <div class="flex items-center gap-3">
            <a :href="downloadUrl(doc)" :download="doc.filename" target="_blank" rel="noopener" class="inline-flex items-center gap-1 font-semibold text-emerald-700">
              <Download class="size-3" />下载
            </a>
            <button
              v-if="pendingId === doc.id"
              type="button"
              class="inline-flex items-center gap-1 font-semibold text-rose-700 disabled:opacity-50"
              :disabled="busyId === doc.id"
              @click="confirmDelete(doc)"
            >
              <Trash2 class="size-3" />确认删除
            </button>
            <button v-else type="button" class="inline-flex items-center gap-1 font-semibold text-rose-600" @click="askDelete(doc)">
              <Trash2 class="size-3" />删除
            </button>
          </div>
        </div>
      </div>
      <p v-else class="px-4 py-3 text-[11px] text-slate-400">暂无自动生成文件；确认邮件后会自动生成。</p>
    </template>
  </section>
</template>

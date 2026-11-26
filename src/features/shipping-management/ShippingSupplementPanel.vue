<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Download, Plus, Trash2 } from '@lucide/vue'
import { getApiErrorMessage } from '@/lib/http'
import {
  draftSupplementSheet,
  exportSupplementSheet,
  deleteGeneratedDoc,
  downloadGeneratedDoc,
  getGeneratedDoc,
  getLoadingSheet,
  listGeneratedDocs,
  listLoadingSheets,
  openGeneratedDoc,
  type GeneratedDoc,
  type LoadingSheetRecord,
  type SupplementDraft,
  type SupplementLine,
  type WorkbookPreviewSheet,
} from '@/api/shippingMail'
import { listShippingTasks, type ShippingScheduleTask } from '@/api/shippingTasks'
import type { LoadingSheetDetail } from '@/api/shippingMail'
import { filingCodeFilename } from './contracts'
import ShippingWorkbookPreviewModal from './ShippingWorkbookPreviewModal.vue'

const props = defineProps<{ factoryId: string }>()
const emit = defineEmits<{ notify: [message: string]; back: [] }>()

const tasks = ref<ShippingScheduleTask[]>([])
const sheets = ref<LoadingSheetRecord[]>([])
const selectedTaskId = ref('')
const LAST_TASK_KEY = `shipping-supplement-last-task:${props.factoryId}`
const selectedSheetId = ref('')
const sheetSearch = ref('')
const generatedDocs = ref<GeneratedDoc[]>([])
const generatedSearch = ref('')
const generatedViewed = ref<Record<string, string>>({})
const generatedDeleteArmed = ref(false)
const selectedGenerated = ref<string[]>([])
const draft = ref<SupplementDraft | null>(null)
const loading = ref(false)
const exporting = ref(false)
const message = ref('')
const previewState = ref<{ doc: GeneratedDoc; filename: string; path: string; sheets: WorkbookPreviewSheet[] } | null>(null)

const filteredSheets = computed(() => {
  const query = sheetSearch.value.trim().toLowerCase()
  return query ? sheets.value.filter((doc) => [doc.contractNo, ...(doc.filingCodes ?? []), doc.soNo, doc.filename].join(' ').toLowerCase().includes(query)) : sheets.value
})

const filteredGenerated = computed(() => {
  const query = generatedSearch.value.trim().toLowerCase()
  return query ? generatedDocs.value.filter((doc) => doc.filename.toLowerCase().includes(query)) : generatedDocs.value
})

const totals = computed(() => {
  const sum = (key: keyof SupplementLine) => (draft.value?.lines ?? [])
    .reduce((total, line) => total + (Number(line[key]) || 0), 0)
  const gw = sum('gw')
  const tare = sum('tare')
  return { ctns: sum('ctns'), pallet: sum('pallet'), qty: sum('qty'), cbm: sum('cbm'), gw, tare, vgm: gw + tare }
})

const summary = computed(() => {
  const map = new Map<string, { itemNo: string; salesConf: string; pcs: number; ctns: number }>()
  for (const line of draft.value?.lines ?? []) {
    const key = `${line.itemNo}-${line.salesConf}`
    const entry = map.get(key) ?? { itemNo: line.itemNo, salesConf: line.salesConf, pcs: 0, ctns: 0 }
    entry.pcs += Number(line.qty) || 0
    entry.ctns += Number(line.ctns) || 0
    map.set(key, entry)
  }
  return [...map.values()]
})

async function loadTasks() {
  try {
    tasks.value = await listShippingTasks(props.factoryId)
    await loadSheets()
  } catch (error) {
    message.value = `无法读取工厂排期：${getApiErrorMessage(error)}`
  }
}

async function loadSheets() {
  try {
    const rows = await listLoadingSheets(props.factoryId, 'dk')
    sheets.value = [...rows].sort((a, b) => String(b.createdAt || '').localeCompare(String(a.createdAt || '')))
  } catch (error) {
    message.value = `读取已导出柜货单失败：${getApiErrorMessage(error)}`
  }
}

function generatedKey(id: string) {
  return `supplement-generated-viewed:${props.factoryId}:${id}`
}

function isGeneratedUnread(doc: GeneratedDoc) {
  return generatedViewed.value[doc.id] !== doc.created_at
}

function markGeneratedViewed(doc: GeneratedDoc) {
  window.localStorage.setItem(generatedKey(doc.id), doc.created_at)
  generatedViewed.value = { ...generatedViewed.value, [doc.id]: doc.created_at }
}

async function loadGeneratedDocs() {
  try {
    generatedDocs.value = await listGeneratedDocs(props.factoryId, 'supplement')
    const cutoff = Date.now() - 30 * 60 * 1000
    for (const doc of generatedDocs.value) {
      if (!window.localStorage.getItem(generatedKey(doc.id)) && Date.parse(doc.created_at || '') < cutoff) {
        window.localStorage.setItem(generatedKey(doc.id), doc.created_at)
      }
    }
    generatedViewed.value = Object.fromEntries(generatedDocs.value.map((doc) => [doc.id, window.localStorage.getItem(generatedKey(doc.id)) || '']))
    selectedGenerated.value = selectedGenerated.value.filter((id) => generatedDocs.value.some((doc) => doc.id === id))
  } catch {
    generatedDocs.value = []
  }
}

function toggleGenerated(doc: GeneratedDoc) {
  selectedGenerated.value = selectedGenerated.value.includes(doc.id)
    ? selectedGenerated.value.filter((id) => id !== doc.id)
    : [...selectedGenerated.value, doc.id]
}

async function removeSelectedGenerated() {
  if (!selectedGenerated.value.length) return
  for (const id of [...selectedGenerated.value]) {
    try { await deleteGeneratedDoc(props.factoryId, id) } catch { /* continue */ }
  }
  selectedGenerated.value = []
  await loadGeneratedDocs()
}

async function removeAllGenerated() {
  if (!generatedDocs.value.length) return
  if (!generatedDeleteArmed.value) {
    generatedDeleteArmed.value = true
    window.setTimeout(() => { generatedDeleteArmed.value = false }, 5000)
    return
  }
  for (const doc of [...generatedDocs.value]) {
    try { await deleteGeneratedDoc(props.factoryId, doc.id) } catch { /* continue */ }
  }
  generatedDeleteArmed.value = false
  await loadGeneratedDocs()
}

async function downloadGenerated(doc: GeneratedDoc) {
  try {
    const blob = await downloadGeneratedDoc(props.factoryId, doc.id)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = doc.filename
    link.click()
    URL.revokeObjectURL(url)
    emit('notify', `已下载 ${doc.filename}，并按月存入 D:\\导入文件\\补料单`)
  } catch (error) {
    message.value = `下载失败：${getApiErrorMessage(error)}`
  }
}

async function openGenerated(doc: GeneratedDoc) {
  markGeneratedViewed(doc)
  message.value = ''
  try {
    const result = await openGeneratedDoc(props.factoryId, doc.id)
    emit('notify', result.opened ? `已在 WPS 打开 ${doc.filename}` : `已保存 ${result.path}`)
  } catch (error) {
    message.value = `打开失败：${getApiErrorMessage(error)}`
  }
}

async function removeGenerated(doc: GeneratedDoc) {
  try {
    await deleteGeneratedDoc(props.factoryId, doc.id)
    await loadGeneratedDocs()
  } catch (error) {
    message.value = `删除失败：${getApiErrorMessage(error)}`
  }
}

async function loadSheet() {
  const id = selectedSheetId.value
  if (!id) return
  loading.value = true
  try {
    const detail = await getLoadingSheet(props.factoryId, id)
    await importCabinet(detail)
  } catch (error) {
    message.value = `导入已导出柜货单失败：${getApiErrorMessage(error)}`
  } finally {
    loading.value = false
  }
}

async function loadDraft() {
  if (!selectedTaskId.value) { draft.value = null; return }
  loading.value = true
  message.value = ''
  try {
    draft.value = await draftSupplementSheet(props.factoryId, selectedTaskId.value)
  } catch (error) {
    message.value = `生成补料单失败：${getApiErrorMessage(error)}`
  } finally {
    loading.value = false
  }
}

async function importCabinet(detail: LoadingSheetDetail) {
  if (!detail.task_id) {
    message.value = '该柜货单没有关联船务排期，无法导入'
    return
  }
  loading.value = true
  message.value = ''
  try {
    const base = await draftSupplementSheet(props.factoryId, detail.task_id)
    selectedTaskId.value = detail.task_id
    base.header.to = detail.header.consignee || base.header.to
    base.header.vessel = detail.header.vessel || base.header.vessel
    base.header.portOfLoading = detail.header.originPort || base.header.portOfLoading
    base.header.portOfDischarge = detail.header.destinationCountry || base.header.portOfDischarge
    const exportCountry = String(detail.header.destinationCountry || '').trim()
    if (exportCountry) base.header.customerMarket = exportCountry
    base.header.receipt = '中国'
    base.header.etd = detail.sheetDate || base.header.etd
    base.header.date = detail.sheetDate || base.header.date
    const contracts = [...new Set([
      String(detail.header.contractNo || '').trim(),
      ...(detail.lines ?? []).map((line) => String(line.contract || '').trim()),
    ].filter(Boolean))]
    if (contracts.length) base.header.invoice = contracts.join(' / ')
    base.lines = detail.lines.map((line) => ({
      id: crypto.randomUUID(),
      mixNo: '',
      containerNo: detail.header.containerNo || '',
      sealNo: detail.header.sealNo || '',
      size: detail.header.containerType || '',
      itemNo: line.filingCode || line.declareCode || '',
      description: line.description || '',
      salesConf: line.contract || '',
      po: line.cartonMark || '',
      ctns: line.cartons ?? null,
      pallet: '',
      qty: line.quantity ?? null,
      booking: detail.header.soNo || '',
      deliveryDate: detail.sheetDate || '',
      cbmPerCarton: line.cbm && line.cartons ? Number(line.cbm) / Number(line.cartons) : null,
      cbm: line.cbm ?? null,
      gwPerCarton: line.grossWeight && line.cartons ? Number(line.grossWeight) / Number(line.cartons) : null,
      gw: line.grossWeight ?? null,
      pack: line.coefficient != null ? String(line.coefficient) : '',
      tare: 0,
      vgm: line.grossWeight ?? null,
    }))
    draft.value = base
    emit('notify', `已从柜货单 ${detail.filename} 导入补料单。`)
  } catch (error) {
    message.value = `导入柜货单失败：${getApiErrorMessage(error)}`
  } finally {
    loading.value = false
  }
}

function recalc(line: SupplementLine) {
  if (line.cbmPerCarton != null && line.ctns != null) {
    line.cbm = Math.round(line.ctns * line.cbmPerCarton * 1000) / 1000
  }
  if (line.gwPerCarton != null && line.ctns != null) {
    line.gw = Math.round(line.ctns * line.gwPerCarton * 1000) / 1000
  }
  line.vgm = (Number(line.gw) || 0) + (Number(line.tare) || 0)
}

function addLine() {
  if (!draft.value) return
  draft.value.lines.push({
    id: crypto.randomUUID(), mixNo: '', containerNo: '', sealNo: '', size: draft.value.lines[0]?.size ?? '',
    itemNo: '', description: '', salesConf: '', po: '', ctns: null, pallet: '', qty: null,
    booking: '', deliveryDate: '', cbmPerCarton: null, cbm: null, gwPerCarton: null, gw: null,
    pack: '', tare: null, vgm: null,
  })
}

async function download() {
  if (!draft.value) return
  exporting.value = true
  try {
    const blob = await exportSupplementSheet(props.factoryId, draft.value)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filingCodeFilename(draft.value.lines, '.xlsx', '补料单')
    link.click()
    URL.revokeObjectURL(url)
    await loadGeneratedDocs()
    emit('notify', '补料单已生成并下载，并按月存入 D:\\导入文件\\补料单。')
  } catch (error) {
    message.value = `导出失败：${getApiErrorMessage(error)}`
  } finally {
    exporting.value = false
  }
}

onMounted(async () => {
  await loadTasks()
  await loadGeneratedDocs()
  if (!selectedTaskId.value) {
    const last = typeof window !== 'undefined' && window.localStorage
      ? window.localStorage.getItem(LAST_TASK_KEY)
      : ''
    if (last) {
      selectedTaskId.value = last
      await loadDraft()
    }
  }
})
watch(selectedTaskId, (id) => {
  if (typeof window !== 'undefined' && window.localStorage && id) {
    window.localStorage.setItem(LAST_TASK_KEY, id)
  }
})
</script>

<template>
  <section class="space-y-4" aria-label="补料单">
    <div class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50 p-4">
      <div class="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 class="text-[16px] font-bold text-emerald-950">补料单 / SHIPMENT ADVICE</h2>
          <p class="mt-0.5 text-[11px] text-slate-500">按船务排期生成补料单；船名、港口、ETD、箱数等来自邮件/排期，合计自动汇总。</p>
        </div>
        <div class="flex items-center gap-3">
          <button type="button" class="text-[13px] font-semibold text-emerald-800 hover:underline" @click="emit('back')">← 返回工厂排期单</button>
        </div>
      </div>
      <div class="mt-3 flex flex-wrap items-center gap-2">
        <input v-model="sheetSearch" type="search" placeholder="搜索合同号 / 备案货号" class="h-9 w-36 rounded-lg border border-emerald-200 px-2 text-[11px]">
        <select v-model="selectedSheetId" aria-label="选择SO出货表柜货单" class="h-9 min-w-[280px] rounded-lg border border-emerald-200 bg-white px-2 text-[12px]" @change="loadSheet">
          <option value="">选择 SO 出货表生成的柜货单</option>
          <option v-for="sheet in filteredSheets" :key="sheet.id" :value="sheet.id">
            {{ sheet.filename }} · {{ String(sheet.createdAt || '').replace('T', ' ').slice(0, 16) }}
          </option>
        </select>
        <button type="button" class="h-9 rounded-lg border border-emerald-200 px-3 text-[11px] font-semibold text-emerald-700" @click="loadSheets">刷新</button>
        <button type="button" class="h-9 rounded-lg border border-emerald-200 bg-white px-3 text-[12px] font-semibold text-emerald-800" @click="emit('back')">← 返回工厂排期</button>
        <button type="button" class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-emerald-700 px-4 text-[12px] font-semibold text-white disabled:opacity-60" :disabled="!draft || exporting" @click="download">
          <Download class="size-3.5" />{{ exporting ? '生成中…' : '导出补料单' }}
        </button>
      </div>
      <p v-if="message" class="mt-2 text-[11px] text-rose-600">{{ message }}</p>
      <p v-if="loading" class="mt-2 text-[11px] text-slate-500">正在生成…</p>
    </div>

    <template v-if="draft">
      <div class="rounded-xl border border-emerald-100/80 bg-white p-4">
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label class="text-[11px] text-slate-500">To / 收件人
            <input v-model="draft.header.to" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">From / 发件人
            <input v-model="draft.header.from" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">Subject / 主题
            <input v-model="draft.header.subject" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">REF# / 参考号
            <input v-model="draft.header.ref" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">Date / 日期
            <input v-model="draft.header.date" type="date" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">Customer / Market（客户 / 市场）
            <input v-model="draft.header.customerMarket" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">Name of Vessel / 船名
            <input v-model="draft.header.vessel" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">Port of Loading / 装货港
            <input v-model="draft.header.portOfLoading" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">Port of Discharge / 卸货港
            <input v-model="draft.header.portOfDischarge" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">E.T.D. / 预计开船日
            <input v-model="draft.header.etd" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">Invoice No./Date / 发票号及日期
            <input v-model="draft.header.invoice" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">Country of Origin / 原产国
            <input v-model="draft.header.origin" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">Place of receipt / 收货地
            <input v-model="draft.header.receipt" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">Total no. of cartons / 总箱数
            <input :value="totals.ctns" readonly class="mt-1 h-9 w-full rounded-lg border border-emerald-100 bg-slate-50 px-2 text-[12px]">
          </label>
        </div>
      </div>

      <div class="overflow-x-auto rounded-xl border border-emerald-100/80 bg-white">
        <div class="flex justify-end gap-2 border-b border-emerald-100 px-3 py-2">
          <button type="button" class="h-9 rounded-lg border border-emerald-200 bg-white px-3 text-[11px] font-semibold text-emerald-800" @click="emit('back')">← 返回工厂排期</button>
          <button type="button" class="inline-flex h-9 items-center gap-1 rounded-lg bg-emerald-700 px-3 text-[11px] font-semibold text-white disabled:opacity-60" :disabled="!draft || exporting" @click="download">
            <Download class="size-3.5" />{{ exporting ? '生成中…' : '导出补料单' }}
          </button>
        </div>
        <table class="w-full min-w-[1700px] text-left text-[11px]">
          <thead class="bg-emerald-50 text-emerald-900/70">
            <tr>
              <th class="px-2 py-2">No.<span class="block text-[9px] font-normal text-emerald-700/60">序号</span></th>
              <th class="px-2 py-2">Mix#<span class="block text-[9px] font-normal text-emerald-700/60">混装号</span></th>
              <th class="px-2 py-2">Container#<span class="block text-[9px] font-normal text-emerald-700/60">柜号</span></th>
              <th class="px-2 py-2">Seal#<span class="block text-[9px] font-normal text-emerald-700/60">封条号</span></th>
              <th class="px-2 py-2">Size<span class="block text-[9px] font-normal text-emerald-700/60">柜型</span></th>
              <th class="px-2 py-2">Item#<span class="block text-[9px] font-normal text-emerald-700/60">货号</span></th>
              <th class="px-2 py-2">Description<span class="block text-[9px] font-normal text-emerald-700/60">品名</span></th>
              <th class="px-2 py-2">Sales Conf#<span class="block text-[9px] font-normal text-emerald-700/60">销售合同号</span></th>
              <th class="px-2 py-2">P.O. No.#<span class="block text-[9px] font-normal text-emerald-700/60">订单号</span></th>
              <th class="px-2 py-2">Ctns<span class="block text-[9px] font-normal text-emerald-700/60">箱数</span></th>
              <th class="px-2 py-2">pallet<span class="block text-[9px] font-normal text-emerald-700/60">卡板数</span></th>
              <th class="px-2 py-2">Qty (Pcs)<span class="block text-[9px] font-normal text-emerald-700/60">数量</span></th>
              <th class="px-2 py-2">Booking#<span class="block text-[9px] font-normal text-emerald-700/60">订舱号</span></th>
              <th class="px-2 py-2">Delivery Date<span class="block text-[9px] font-normal text-emerald-700/60">交货日期</span></th>
              <th class="px-2 py-2">cbm<span class="block text-[9px] font-normal text-emerald-700/60">体积</span></th>
              <th class="px-2 py-2">G.W (kgs)<span class="block text-[9px] font-normal text-emerald-700/60">毛重</span></th>
              <th class="px-2 py-2">pack (pcs)<span class="block text-[9px] font-normal text-emerald-700/60">每箱数量</span></th>
              <th class="px-2 py-2">Tare (kgs)<span class="block text-[9px] font-normal text-emerald-700/60">柜重</span></th>
              <th class="px-2 py-2">VGM (kgs)<span class="block text-[9px] font-normal text-emerald-700/60">总重</span></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-emerald-50">
            <tr v-for="(line, index) in draft.lines" :key="line.id">
              <td class="px-1 py-1 text-center">{{ index + 1 }}</td>
              <td class="px-1 py-1"><input v-model="line.mixNo" class="h-7 w-12 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.containerNo" class="h-7 w-24 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.sealNo" class="h-7 w-24 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.size" class="h-7 w-14 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.itemNo" class="h-7 w-20 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.description" class="h-7 w-52 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.salesConf" class="h-7 w-24 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.po" class="h-7 w-20 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model.number="line.ctns" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right" @input="recalc(line)"></td>
              <td class="px-1 py-1"><input v-model="line.pallet" class="h-7 w-10 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model.number="line.qty" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-1 py-1"><input v-model="line.booking" class="h-7 w-24 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.deliveryDate" class="h-7 w-24 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model.number="line.cbm" type="number" class="h-7 w-14 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-1 py-1"><input v-model.number="line.gw" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right" @input="recalc(line)"></td>
              <td class="px-1 py-1"><input v-model="line.pack" class="h-7 w-10 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model.number="line.tare" type="number" class="h-7 w-14 rounded border border-emerald-100 px-1 text-right" @input="recalc(line)"></td>
              <td class="px-1 py-1"><input v-model.number="line.vgm" type="number" class="h-7 w-16 rounded border border-emerald-100 bg-slate-50 px-1 text-right" readonly></td>
              <td class="px-1 py-1 text-center">
                <button type="button" class="text-rose-500" aria-label="删除明细" @click="draft.lines.splice(index, 1)"><Trash2 class="size-3.5" /></button>
              </td>
            </tr>
            <tr class="bg-emerald-50/60 font-semibold text-emerald-950">
              <td class="px-2 py-2" colspan="9">合计</td>
              <td class="px-2 py-2 text-right">{{ totals.ctns }}</td>
              <td class="px-2 py-2 text-right">{{ totals.pallet }}</td>
              <td class="px-2 py-2 text-right">{{ totals.qty }}</td>
              <td colspan="2"></td>
              <td class="px-2 py-2 text-right">{{ totals.cbm.toFixed(2) }}</td>
              <td class="px-2 py-2 text-right">{{ totals.gw.toFixed(2) }}</td>
              <td></td>
              <td class="px-2 py-2 text-right">{{ totals.tare.toFixed(2) }}</td>
              <td class="px-2 py-2 text-right">{{ totals.vgm.toFixed(2) }}</td>
              <td></td>
            </tr>
          </tbody>
        </table>
        <div class="p-3">
          <button type="button" class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-emerald-200 px-3 text-[12px] font-semibold text-emerald-800" @click="addLine">
            <Plus class="size-3.5" />添加明细
          </button>
        </div>
      </div>

      <div v-if="summary.length" class="rounded-xl border border-emerald-100/80 bg-white p-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h3 class="text-[13px] font-bold text-slate-800">补料表</h3>
        </div>
        <table class="mt-2 w-full max-w-2xl text-left text-[11px]">
          <thead class="bg-slate-50 text-slate-500">
            <tr>
              <th class="px-2 py-1.5">Item#<span class="block text-[9px] font-normal text-slate-400">货号</span></th>
              <th class="px-2 py-1.5 text-right">Pcs<span class="block text-[9px] font-normal text-slate-400">数量</span></th>
              <th class="px-2 py-1.5 text-right">Ctns<span class="block text-[9px] font-normal text-slate-400">箱数</span></th>
              <th class="px-2 py-1.5">Sales Conf#<span class="block text-[9px] font-normal text-slate-400">销售合同号</span></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="entry in summary" :key="`${entry.itemNo}-${entry.salesConf}`">
              <td class="px-2 py-1.5 font-semibold text-slate-800">{{ entry.itemNo }}</td>
              <td class="px-2 py-1.5 text-right tabular-nums">{{ entry.pcs }}</td>
              <td class="px-2 py-1.5 text-right tabular-nums">{{ entry.ctns }}</td>
              <td class="px-2 py-1.5">{{ entry.salesConf }}</td>
            </tr>
          </tbody>
        </table>
      </div>

    </template>
      <div v-if="generatedDocs.length" class="rounded-xl border border-emerald-100/80 bg-white p-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h3 class="text-[13px] font-bold text-slate-800">已生成补料单</h3>
          <div class="flex flex-wrap items-center gap-2">
            <input v-model="generatedSearch" type="search" placeholder="搜索补料单文件名" class="h-8 w-48 rounded-lg border border-emerald-200 px-2 text-[11px]">
            <button type="button" class="rounded-lg border border-rose-200 px-2 py-1 text-[11px] font-semibold text-rose-600 disabled:opacity-40" :disabled="!selectedGenerated.length" @click="removeSelectedGenerated">删除选中{{ selectedGenerated.length ? ` (${selectedGenerated.length})` : '' }}</button>
            <button type="button" class="rounded-lg border px-2 py-1 text-[11px] font-semibold" :class="generatedDeleteArmed ? 'border-rose-300 bg-rose-50 text-rose-700' : 'border-rose-200 text-rose-600'" @click="removeAllGenerated">{{ generatedDeleteArmed ? '确认一键删除' : '一键删除' }}</button>
            <button type="button" class="text-[11px] text-emerald-700" @click="loadGeneratedDocs">刷新</button>
          </div>
        </div>
        <div class="mt-2 divide-y divide-slate-100">
          <div v-for="doc in filteredGenerated" :key="doc.id" class="flex flex-wrap items-center justify-between gap-2 py-1.5 text-[11px]">
            <span class="flex min-w-0 flex-1 items-center gap-1.5">
              <input type="checkbox" :aria-label="`选择 ${doc.filename}`" :checked="selectedGenerated.includes(doc.id)" @change="toggleGenerated(doc)">
              <span v-if="isGeneratedUnread(doc)" class="size-1.5 shrink-0 rounded-full bg-rose-500"></span>
              <span class="truncate font-semibold text-emerald-700">{{ doc.filename }}</span>
            </span>
            <span class="tabular-nums text-slate-400">{{ String(doc.created_at || '').replace('T', ' ').slice(0, 16) }}</span>
            <span class="flex gap-3">
              <button type="button" class="text-emerald-700 hover:underline" @click="downloadGenerated(doc)">下载</button>
              <button type="button" class="text-emerald-700 hover:underline" @click="openGenerated(doc)">打开</button>
              <button type="button" class="text-rose-600 hover:underline" @click="removeGenerated(doc)">删除</button>
            </span>
          </div>
        </div>
      </div>

    <ShippingWorkbookPreviewModal
      v-if="previewState"
      :filename="previewState.filename"
      :path="previewState.path"
      :sheets="previewState.sheets"
      can-download
      @close="previewState = null"
      @download="downloadGenerated(previewState.doc)"
    />
  </section>
</template>

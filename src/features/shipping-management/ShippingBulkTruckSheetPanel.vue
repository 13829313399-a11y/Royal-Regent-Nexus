<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Download, Plus, Trash2 } from '@lucide/vue'
import { getApiErrorMessage } from '@/lib/http'
import {
  draftBulkTruckSheet,
  exportBulkTruckSheet,
  searchScheduleProducts,
  type BulkTruckDraft,
  type BulkTruckLine,
} from '@/api/shippingMail'
import { listShippingTasks, type ShippingScheduleTask } from '@/api/shippingTasks'
import ShippingTruckExportHistory from './ShippingTruckExportHistory.vue'

const props = defineProps<{ factoryId: string; initialTaskId?: string; initialHeader?: Record<string, unknown> | null }>()
const emit = defineEmits<{ notify: [message: string]; back: [] }>()

const tasks = ref<ShippingScheduleTask[]>([])
const selectedTaskId = ref('')
const search = ref('')
const searchField = ref<'all' | 'contract' | 'filing'>('all')
const searching = ref(false)
const historyVersion = ref(0)
const draft = ref<BulkTruckDraft | null>(null)
const loading = ref(false)
const exporting = ref(false)
const message = ref('')

const totals = computed(() => {
  const sum = (key: keyof BulkTruckLine) => (draft.value?.lines ?? [])
    .reduce((total, line) => total + (Number(line[key]) || 0), 0)
  return {
    quantity: sum('quantity'), cartons: sum('cartons'), grossWeight: sum('grossWeight'),
    netWeight: sum('netWeight'), cbm: sum('cbm'),
  }
})

async function loadTasks() {
  try {
    tasks.value = await listShippingTasks(props.factoryId)
  } catch (error) {
    message.value = `无法读取工厂排期：${getApiErrorMessage(error)}`
  }
}

async function loadDraft() {
  if (!selectedTaskId.value) { draft.value = null; return }
  loading.value = true
  message.value = ''
  try {
    draft.value = await draftBulkTruckSheet(props.factoryId, selectedTaskId.value)
    applyInitialHeader()
    dedupeLines()
    syncTableName()
  } catch (error) {
    message.value = `生成失败：${getApiErrorMessage(error)}`
  } finally {
    loading.value = false
  }
}

function applyInitialHeader() {
  if (!draft.value || !props.initialHeader) return
  const source = props.initialHeader
  const text = (value: unknown) => String(value ?? '').trim()
  const brand = text(source.brandName) || text(source.brandNote) || text(source.brand)
  if (brand) draft.value.header.brandName = brand
  if (text(source.shipper)) draft.value.header.shipper = text(source.shipper)
  if (text(source.consignee)) draft.value.header.consignee = text(source.consignee)
  if (text(source.country) || text(source.destinationCountry)) draft.value.header.country = text(source.country) || text(source.destinationCountry)
  if (text(source.contractNo)) draft.value.header.contractNo = text(source.contractNo)
  if (text(source.tradingHouse)) draft.value.header.tradingHouse = text(source.tradingHouse)
  if (text(source.plate)) draft.value.header.plate = text(source.plate)
  if (text(source.vehicle)) draft.value.header.vehicle = text(source.vehicle)
  if (text(source.truckType)) draft.value.header.truckType = text(source.truckType)
  if (text(source.tableName)) draft.value.header.tableName = text(source.tableName)
  if (text(source.warehouseNo)) draft.value.header.warehouseNo = text(source.warehouseNo)
  if (text(source.originPort)) draft.value.header.originPort = text(source.originPort)
  if (text(source.poNo)) draft.value.header.poNo = text(source.poNo)
  if (text(source.orderNo)) draft.value.header.orderNo = text(source.orderNo)
  if (text(source.filingCode)) draft.value.header.filingCode = text(source.filingCode)
  if (text(source.bookingNo)) draft.value.header.bookingNo = text(source.bookingNo)
  const carrier = text(source.transport) || text(source.transportCompanyName) || text(source.transportCompany)
  if (carrier) {
    draft.value.header.transportCompanyName = carrier
    draft.value.header.transport = carrier
  }
  if (text(source.shippingClerk) || text(source.preparer)) draft.value.header.fromName = text(source.shippingClerk) || text(source.preparer)
  if (text(source.tradeTerm)) draft.value.header.tradeTerm = text(source.tradeTerm)
  if (text(source.cutoff)) draft.value.header.arrivalCutoff = text(source.cutoff)
  const sail = text(source.sailingDate) || text(source.sheetDate) || text(source.cutoff)
  if (sail) draft.value.header.sheetDate = sail.slice(0, 10)
  if (text(source.sailingDate)) draft.value.header.cutoff = text(source.sailingDate)
  if (text(source.remark)) draft.value.header.remark = text(source.remark)
  syncTableName()
}

watch(() => props.initialHeader, applyInitialHeader)

function dedupeLines() {
  if (!draft.value) return 0
  const seen = new Set<string>()
  const before = draft.value.lines.length
  draft.value.lines = draft.value.lines.filter((line) => {
    const contract = String(line.contract || '').trim()
    const code = String(line.filingCode || '').trim()
    if (!contract && !code) return true
    if (code && !contract) return false
    const key = `${contract}|${code}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
  return before - draft.value.lines.length
}

async function runSearch() {
  const query = search.value.trim()
  if (!query) return
  searching.value = true
  message.value = ''
  try {
    dedupeLines()
    const items = await searchScheduleProducts(props.factoryId, query)
    if (!draft.value) {
      message.value = '请先选择工厂排期'
      return
    }
    let added = 0
    let skipped = 0
    const existing = new Set(draft.value.lines.map((line) => `${String(line.contract || '').trim()}|${String(line.filingCode || '').trim()}`))
    for (const item of items) {
      const code = String(item.product_code || '').trim()
      if (!code) continue
      const cartons = Number(item.cartons) || 0
      const mapped: BulkTruckLine = {
        id: crypto.randomUUID(),
        tradingHouse: draft.value.header.tradingHouse || 'DK',
        contract: String(item.contract_no || ''),
        filingCode: code,
        declareCode: code,
        coefficient: Number(item.coefficient) || (cartons ? (Number(item.quantity) || 0) / cartons : null),
        name: String(item.product_name || ''),
        quantity: Number(item.quantity) || 0,
        cartons,
        boards: '',
        grossWeight: Number(item.gross_weight) || 0,
        netWeight: Number(item.net_weight) || 0,
        cbm: Number(item.cbm) || 0,
        country: String(item.country || ''),
        grossPerCarton: cartons && item.gross_weight ? Number(item.gross_weight) / cartons : null,
        netPerCarton: cartons && item.net_weight ? Number(item.net_weight) / cartons : null,
        cbmPerCarton: cartons && item.cbm ? Number(item.cbm) / cartons : null,
        brand: '',
        so: String(item.so_number || ''),
        po: String(item.customer_po || ''),
        shippingNote: '',
        remark: '',
      }
      if (!String(mapped.contract || '').trim()) {
        skipped += 1
        continue
      }
      const key = `${String(mapped.contract || '').trim()}|${String(mapped.filingCode || '').trim()}`
      if (existing.has(key)) {
        skipped += 1
        continue
      }
      existing.add(key)
      const blankIndex = draft.value.lines.findIndex((line) => !line.filingCode?.trim() && (line.cartons == null || Number(line.cartons) === 0))
      if (blankIndex >= 0) {
        const blank = draft.value.lines[blankIndex]!
        draft.value.lines.splice(blankIndex, 1, { ...mapped, id: blank.id })
      } else {
        draft.value.lines.push(mapped)
      }
      added += 1
    }
    if (!added && skipped) message.value = `合同号 + 备案货号已存在，不能重复导入（跳过 ${skipped} 行）`
    else message.value = added ? `已找到备案号 ${query} 并填入 ${added} 行` : `未找到备案号 ${query} 对应的业务排期`
  } catch (error) {
    message.value = `搜索失败：${getApiErrorMessage(error)}`
  } finally {
    searching.value = false
  }
}

function formatTableName(transportRaw: unknown, originPortRaw: unknown) {
  const transport = String(transportRaw ?? '').trim().replace(/[，,\s]+$/, '')
  const carrier = transport ? (transport.endsWith('运输') ? transport : `${transport}运输`) : ''
  const port = String(originPortRaw ?? '').trim()
  if (carrier && port) return `${carrier}，出${port}`
  if (port) return `出${port}`
  return carrier
}

function syncTableName() {
  if (!draft.value) return
  const header = draft.value.header
  header.tableName = formatTableName(header.transport || header.transportCompanyName, header.originPort)
}

function recalc(line: BulkTruckLine) {
  const cartons = Number(line.cartons)
  const coefficient = Number(line.coefficient)
  if (!Number.isFinite(cartons)) return
  if (Number.isFinite(coefficient) && coefficient > 0) line.quantity = Math.round(cartons * coefficient * 1000) / 1000
  if (line.grossPerCarton != null) line.grossWeight = Math.round(cartons * line.grossPerCarton * 1000) / 1000
  if (line.netPerCarton != null) line.netWeight = Math.round(cartons * line.netPerCarton * 1000) / 1000
  if (line.cbmPerCarton != null) line.cbm = Math.round((cartons * line.cbmPerCarton / 35.4) * 1000) / 1000
}

function addLine() {
  if (!draft.value) return
  draft.value.lines.push({
    id: crypto.randomUUID(), tradingHouse: 'ZURU', contract: '', filingCode: '', declareCode: '',
    coefficient: null, quantity: null, cartons: null, boards: '', grossWeight: null, netWeight: null,
    cbm: null, country: draft.value.lines[0]?.country ?? '', grossPerCarton: null, netPerCarton: null,
    cbmPerCarton: null, brand: '', so: '', po: '', shippingNote: '', remark: '',
  })
}

async function download() {
  if (!draft.value) return
  exporting.value = true
  try {
    const blob = await exportBulkTruckSheet(props.factoryId, draft.value)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const codes = [...new Set((draft.value.lines ?? []).map((line) => String(line.filingCode || '').trim()).filter(Boolean))]
    link.download = `${codes.join('_') || draft.value.header.tableName || '2026年盐田散货'}.xls`
    link.click()
    URL.revokeObjectURL(url)
    emit('notify', `已生成 ${draft.value.header.tableName}。`)
    historyVersion.value += 1
  } catch (error) {
    message.value = `导出失败：${getApiErrorMessage(error)}`
  } finally {
    exporting.value = false
  }
}

onMounted(loadTasks)
watch(
  () => draft.value
    ? `${draft.value.header.transport || ''}|${draft.value.header.originPort || ''}`
    : '',
  (value, previous) => {
    if (value && value !== previous) syncTableName()
  },
)
watch(() => props.initialTaskId, (taskId) => {
  if (!taskId) return
  selectedTaskId.value = taskId
  void loadDraft()
}, { immediate: true })
</script>

<template>
  <section class="space-y-4" aria-label="盐田散货车货表">
    <div class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50 p-4">
      <div class="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 class="text-[16px] font-bold text-emerald-950">2026 盐田散货（W 车）</h2>
          <p class="mt-0.5 text-[11px] text-slate-500">散货送仓车货表；数量 = 箱数 × 每箱数量，毛重/净重 = 每箱重量 × 箱数。</p>
        </div>
        <button type="button" class="text-[11px] font-semibold text-emerald-800 hover:underline" @click="emit('back')">← 返回工厂排期单</button>
      </div>
      <p v-if="message" class="mt-2 text-[11px] text-rose-600">{{ message }}</p>
      <p v-if="loading" class="mt-2 text-[11px] text-slate-500">正在生成…</p>
      <div v-if="!draft" class="mt-3 flex flex-wrap items-center gap-2">
        <select v-model="selectedTaskId" aria-label="选择工厂排期" class="h-9 rounded-lg border border-emerald-200 bg-white px-2 text-[12px]" @change="loadDraft">
          <option value="">选择工厂排期</option>
          <option v-for="task in tasks" :key="task.id" :value="task.id">
            {{ task.so_number || task.id }} · {{ task.port || '-' }} · {{ task.planned_ship_date || '-' }}
          </option>
        </select>
      </div>
    </div>

    <template v-if="draft">
      <div class="rounded-xl border border-emerald-100/80 bg-white p-4">
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label class="text-[11px] text-slate-500">发货商
            <input v-model="draft.header.shipper" type="text" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">收货商
            <input v-model="draft.header.consignee" type="text" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">合同号
            <input v-model="draft.header.contractNo" type="text" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">订舱号/SO
            <input v-model="draft.header.bookingNo" type="text" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">备案货号
            <input v-model="draft.header.filingCode" type="text" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">箱唛（PO）
            <input v-model="draft.header.poNo" type="text" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">国家
            <input v-model="draft.header.country" type="text" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">品牌
            <input v-model="draft.header.brandName" type="text" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">洋行
            <input v-model="draft.header.tradingHouse" type="text" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">车头注明（车次）
            <input v-model="draft.header.vehicle" type="text" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">到货截止日期
            <input v-model="draft.header.arrivalCutoff" type="text" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">发车日期
            <input v-model="draft.header.sheetDate" type="date" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">运输公司
            <input v-model="draft.header.transport" type="text" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]" @input="syncTableName">
          </label>
          <label class="text-[11px] text-slate-500">派车公司
            <input v-model="draft.header.consolidator" type="text" placeholder="自己填" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">成交方式
            <select v-model="draft.header.tradeTerm" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
              <option value="FOB">FOB</option>
              <option value="EXW">EXW</option>
            </select>
          </label>
          <label class="text-[11px] text-slate-500">出港口
            <input v-model="draft.header.originPort" list="truck-port-options" placeholder="从邮件识别，可改盐田/蛇口" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]" @input="syncTableName">
            <datalist id="truck-port-options">
              <option value="盐田" />
              <option value="蛇口" />
            </datalist>
          </label>
          <label class="text-[11px] text-slate-500">截单日期
            <input v-model="draft.header.cutoff" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">车辆数量
            <input v-model="draft.header.truckCount" type="number" min="1" step="1" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">入仓号 <span class="ml-1 rounded bg-slate-100 px-1 text-[9px] text-slate-500">邮件自动识别</span>
            <input v-model="draft.header.warehouseNo" type="text" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]" @input="syncTableName">
          </label>
          <label class="text-[11px] text-slate-500">船务
            <select v-model="draft.header.fromName" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
              <option value="农建壮">农建壮</option>
              <option value="小美">小美</option>
            </select>
          </label>
          <label class="text-[11px] text-slate-500">车型（吨数）
            <select v-model="draft.header.truckType" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]" @change="syncTableName">
              <option value="3T">3吨</option>
              <option value="5T">5吨</option>
              <option value="8T">8吨</option>
              <option value="10T">10吨</option>
              <option value="12T">12吨</option>
              <option value="15T">15吨</option>
              <option value="客上车">客上车</option>
              <option value="W">客车W车</option>
            </select>
          </label>
          <label class="text-[11px] text-slate-500">车牌
            <input v-model="draft.header.plate" type="text" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">备注
            <input v-model="draft.header.remark" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">表格名称
            <input v-model="draft.header.tableName" placeholder="例如：成隆达运输，出盐田" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
        </div>
      </div>
      <div class="mt-3 flex flex-wrap items-center justify-end gap-2">
        <select v-model="searchField" aria-label="搜索字段" class="h-9 rounded-lg border border-emerald-200 bg-white px-2 text-[12px]">
          <option value="all">全部</option>
          <option value="contract">合同号</option>
          <option value="filing">备案货号</option>
        </select>
        <input
          v-model="search"
          type="search"
          aria-label="搜索合同号或备案货号"
          placeholder="搜索合同号 / 备案货号"
          class="h-9 w-[200px] rounded-lg border border-emerald-200 bg-white px-2.5 text-[12px]"
          @keyup.enter="runSearch"
        >
        <button type="button" class="h-9 rounded-lg bg-emerald-700 px-3 text-[12px] font-semibold text-white disabled:opacity-60" :disabled="searching" @click="runSearch">{{ searching ? '搜索中…' : '搜索' }}</button>
        <select v-model="selectedTaskId" aria-label="选择工厂排期" class="h-9 rounded-lg border border-emerald-200 bg-white px-2 text-[12px]" @change="loadDraft">
          <option value="">选择工厂排期</option>
          <option v-for="task in tasks" :key="task.id" :value="task.id">
            {{ task.so_number || task.id }} · {{ task.port || '-' }} · {{ task.planned_ship_date || '-' }}
          </option>
        </select>
        <button type="button" class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-emerald-700 px-4 text-[12px] font-semibold text-white disabled:opacity-60" :disabled="!draft || exporting" @click="download">
          <Download class="size-3.5" />{{ exporting ? '生成中…' : '导出发货表' }}
        </button>
      </div>

      <div class="overflow-x-auto rounded-xl border border-emerald-100/80 bg-white">
        <table class="w-full min-w-[1600px] text-left text-[11px]">
          <thead class="bg-emerald-50 text-emerald-900/70">
            <tr>
              <th class="px-2 py-2">序号</th><th class="px-2 py-2">洋行</th><th class="px-2 py-2">合约</th>
              <th class="px-2 py-2">工厂备案货号</th><th class="px-2 py-2">出货申报货号</th><th class="px-2 py-2">货名</th><th class="px-2 py-2">数量</th>
              <th class="px-2 py-2">箱数</th><th class="px-2 py-2">板数</th><th class="px-2 py-2">毛重</th><th class="px-2 py-2">净重</th>
              <th class="px-2 py-2">CBM</th><th class="px-2 py-2">出口国家</th><th class="px-2 py-2">每箱毛重</th>
              <th class="px-2 py-2">每箱净重</th><th class="px-2 py-2">每箱体积</th><th class="px-2 py-2">品牌</th>
              <th class="px-2 py-2">SO</th><th class="px-2 py-2">PO</th><th class="px-2 py-2">船期</th><th class="px-2 py-2">备注</th><th></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-emerald-50">
            <tr v-for="(line, index) in draft.lines" :key="line.id">
              <td class="px-1 py-1 text-center">{{ index + 1 }}</td>
              <td class="px-1 py-1"><input v-model="line.tradingHouse" class="h-7 w-14 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.contract" class="h-7 w-28 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.filingCode" class="h-7 w-28 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.declareCode" class="h-7 w-28 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.name" class="h-7 w-36 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model.number="line.quantity" type="number" class="h-7 w-20 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-1 py-1"><input v-model.number="line.cartons" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right" @input="recalc(line)"></td>
              <td class="px-1 py-1"><input v-model="line.boards" class="h-7 w-12 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model.number="line.grossWeight" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-1 py-1"><input v-model.number="line.netWeight" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-1 py-1"><input v-model.number="line.cbm" type="number" class="h-7 w-14 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-1 py-1"><input v-model="line.country" class="h-7 w-20 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model.number="line.grossPerCarton" type="number" class="h-7 w-14 rounded border border-emerald-100 px-1 text-right" @input="recalc(line)"></td>
              <td class="px-1 py-1"><input v-model.number="line.netPerCarton" type="number" class="h-7 w-14 rounded border border-emerald-100 px-1 text-right" @input="recalc(line)"></td>
              <td class="px-1 py-1"><input v-model.number="line.cbmPerCarton" type="number" class="h-7 w-14 rounded border border-emerald-100 px-1 text-right" @input="recalc(line)"></td>
              <td class="px-1 py-1"><input v-model="line.brand" class="h-7 w-28 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.so" class="h-7 w-28 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.po" class="h-7 w-20 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.shippingNote" class="h-7 w-28 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.remark" class="h-7 w-28 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1 text-center">
                <button type="button" class="text-rose-500" aria-label="删除明细" @click="draft.lines.splice(index, 1)"><Trash2 class="size-3.5" /></button>
              </td>
            </tr>
            <tr class="bg-emerald-50/60 font-semibold text-emerald-950">
              <td class="px-2 py-2" colspan="6">合计</td>
              <td class="px-2 py-2 text-right">{{ totals.quantity }}</td>
              <td class="px-2 py-2 text-right">{{ totals.cartons }}</td>
              <td class="px-2 py-2"></td>
              <td class="px-2 py-2 text-right">{{ totals.grossWeight.toFixed(2) }}</td>
              <td class="px-2 py-2 text-right">{{ totals.netWeight.toFixed(2) }}</td>
              <td class="px-2 py-2 text-right">{{ totals.cbm.toFixed(2) }}</td>
              <td colspan="10"></td>
            </tr>
          </tbody>
        </table>
        <div class="p-3">
          <button type="button" class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-emerald-200 px-3 text-[12px] font-semibold text-emerald-800" @click="addLine">
            <Plus class="size-3.5" />添加明细
          </button>
        </div>
      </div>
    </template>

    <ShippingTruckExportHistory :factory-id="factoryId" :refresh-key="historyVersion" @notify="emit('notify', $event)" />
  </section>
</template>

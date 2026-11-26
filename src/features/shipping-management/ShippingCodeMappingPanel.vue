<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Download, Info, Plus, RefreshCw, RotateCcw, Search, Trash2, Upload } from '@lucide/vue'
import { getGeneratedDoc, importCodeMappingFile, listGeneratedDocs, type GeneratedDoc } from '@/api/shippingMail'

const props = defineProps<{ factoryId: string }>()
const emit = defineEmits<{ notify: [message: string] }>()

interface CodeRow {
  code: string
  name: string
  perCarton: string
  category: string
  note: string
  gross: string
  net: string
  source: string
  customer: string
  date?: string
  contractNo?: string
  quantity?: string
  cartons?: string
  volume?: string
  country?: string
  transport?: string
  containerMode?: string
  trip?: string
  containerType?: string
  plate?: string
  containerNo?: string
  sealNo?: string
  port?: string
  mode?: string
  po?: string
  status: string
  tone: 'blue' | 'orange' | 'red'
}

const seedRows: CodeRow[] = [
  { code: '10201', name: '全能足球6个/箱', perCarton: '6 个', category: '塑胶', note: '-', gross: '4.047', net: '2.496', source: 'X盘', customer: 'ZURU', status: '已同步', tone: 'blue' },
  { code: '10731', name: '公仔系列', perCarton: '默认', category: '塑胶', note: '-', gross: '1.350', net: '1.100', source: 'X盘', customer: 'MOOSE', status: '已同步', tone: 'blue' },
  { code: '10740', name: '工具盒', perCarton: '默认', category: '塑胶', note: '-', gross: '2.470', net: '2.150', source: 'X盘', customer: 'TIG', status: '待同步', tone: 'orange' },
  { code: '10761', name: '公仔系列', perCarton: '默认', category: '塑胶', note: '-', gross: '1.180', net: '0.900', source: 'X盘', customer: 'TOMY', status: '已同步', tone: 'blue' },
  { code: '1085', name: '马桶3个/箱', perCarton: '3 个', category: '塑胶', note: '-', gross: '1.993', net: '1.140', source: 'X盘', customer: 'CEPIA', status: '异常', tone: 'red' },
  { code: '11-1501', name: '风扇香蕉机12个/箱', perCarton: '12 个', category: '电子', note: '-', gross: '7.161', net: '5.760', source: 'X盘', customer: 'AZAD', status: '已同步', tone: 'blue' },
  { code: '11-2101', name: '香蕉套装24个/箱', perCarton: '24 个', category: '塑胶', note: '-', gross: '4.777', net: '1.920', source: 'X盘', customer: 'ZANZOON', status: '待同步', tone: 'orange' },
  { code: '11-PROD-001-0003', name: '风扇香蕉机40个/箱', perCarton: '40 个', category: '电子', note: '-', gross: '9.820', net: '9.200', source: 'X盘', customer: 'JOHN ADAMS', status: '已同步', tone: 'blue' },
  { code: '11-PROD-002-0001-B', name: '香蕉盒144个/箱', perCarton: '144 个', category: '塑胶', note: '-', gross: '7.185', net: '5.760', source: 'X盘', customer: 'ZURU', status: '已同步', tone: 'blue' },
  { code: '11-PROD-002-0002', name: '蜡烛香蕉灯100个/箱', perCarton: '100 个', category: '电子', note: '-', gross: '7.185', net: '5.100', source: 'X盘', customer: 'MOOSE', status: '异常', tone: 'red' },
  { code: '11-PROD-002-0003', name: '蜡烛香蕉灯100个/箱', perCarton: '100 个', category: '电子', note: '-', gross: '10.556', net: '7.700', source: 'X盘', customer: 'TIG', status: '已同步', tone: 'blue' },
  { code: '11250', name: '雨衣8个/箱', perCarton: '8 个', category: '电子', note: '-', gross: '5.039', net: '3.560', source: 'X盘', customer: 'TOMY', status: '待同步', tone: 'orange' },
]

const rows = ref<CodeRow[]>([...seedRows])
const keyword = ref('')
const appliedKeyword = ref('')
const activeCustomer = ref<string>('全部')
const page = ref(1)
const pageSize = 50
const selectedKeys = ref<string[]>([])
function loadDeletedKeys(): string[] {
  if (typeof window === 'undefined' || !window.localStorage) return []
  try {
    return JSON.parse(window.localStorage.getItem('shipping-code-mapping-deleted') || '[]') as string[]
  } catch {
    return []
  }
}

const deletedKeys = ref<Set<string>>(new Set(loadDeletedKeys()))
const fileInput = ref<HTMLInputElement | null>(null)
const importingFile = ref(false)
const CUSTOM_KEY = `shipping-code-mapping-imported:${props.factoryId}`

function loadCustomRows(): CodeRow[] {
  if (typeof window === 'undefined' || !window.localStorage) return []
  try {
    return JSON.parse(window.localStorage.getItem(CUSTOM_KEY) || '[]') as CodeRow[]
  } catch {
    return []
  }
}

const customRows = ref<CodeRow[]>(loadCustomRows())

function persistCustomRows() {
  if (typeof window === 'undefined' || !window.localStorage) return
  try {
    window.localStorage.setItem(CUSTOM_KEY, JSON.stringify(customRows.value))
  } catch {
    // ignore quota errors
  }
}
const customers = computed(() => ['全部', ...new Set(rows.value.map((row) => row.customer).filter(Boolean))])

const filteredRows = computed(() => {
  const search = appliedKeyword.value.trim().toLowerCase()
  return rows.value.filter((row) => {
    if (activeCustomer.value !== '全部' && row.customer !== activeCustomer.value) return false
    if (!search) return true
    return [
      row.code,
      row.name,
      row.contractNo,
      row.transport,
      row.plate,
      row.trip,
      row.containerType,
      row.containerNo,
      row.sealNo,
    ].some((field) => String(field || '').toLowerCase().includes(search))
  })
})

const pageCount = computed(() => Math.max(1, Math.ceil(filteredRows.value.length / pageSize)))
const pagedRows = computed(() => filteredRows.value.slice((page.value - 1) * pageSize, page.value * pageSize))

watch([appliedKeyword, activeCustomer], () => { page.value = 1 })

const statusDot: Record<CodeRow['tone'], string> = {
  blue: 'bg-blue-500',
  orange: 'bg-amber-500',
  red: 'bg-rose-500',
}

const yearOptions = ['2026', '2025', '2024', '2023', '2022', '2021', '2020']
const selectedYear = ref('2026')
const generatedRows = ref<CodeRow[]>([])
const importedRows = ref<CodeRow[]>([])
const loadingYear = ref(false)
const yearCache = new Map<string, CodeRow[]>()

function modeLabel(row: CodeRow) {
  const mode = String(row.mode || row.containerMode || '-').trim()
  const customer = String(row.customer || '').trim()
  if (customer && customer !== '-' && mode.startsWith(customer)) {
    return mode.slice(customer.length).replace(/^出/, '').trim() || '-'
  }
  return mode || '-'
}

function rowKey(row: CodeRow) {
  return [row.date, row.contractNo, row.code, row.quantity, row.cartons, row.trip, row.containerNo, row.sealNo].join('|')
}

function persistDeleted() {
  if (typeof window === 'undefined' || !window.localStorage) return
  window.localStorage.setItem('shipping-code-mapping-deleted', JSON.stringify([...deletedKeys.value]))
}

const allPageSelected = computed(() => pagedRows.value.length > 0 && pagedRows.value.every((row) => selectedKeys.value.includes(rowKey(row))))
const somePageSelected = computed(() => pagedRows.value.some((row) => selectedKeys.value.includes(rowKey(row))))

function toggleRow(row: CodeRow) {
  const key = rowKey(row)
  selectedKeys.value = selectedKeys.value.includes(key) ? selectedKeys.value.filter((item) => item !== key) : [...selectedKeys.value, key]
}

function togglePage() {
  const keys = pagedRows.value.map(rowKey)
  if (allPageSelected.value) {
    selectedKeys.value = selectedKeys.value.filter((key) => !keys.includes(key))
  } else {
    selectedKeys.value = [...new Set([...selectedKeys.value, ...keys])]
  }
}

function deleteRows(keys: string[]) {
  if (!keys.length) return
  const removing = new Set(keys)
  deletedKeys.value = new Set([...deletedKeys.value, ...keys])
  persistDeleted()
  rows.value = rows.value.filter((row) => !removing.has(rowKey(row)))
  generatedRows.value = generatedRows.value.filter((row) => !removing.has(rowKey(row)))
  importedRows.value = importedRows.value.filter((row) => !removing.has(rowKey(row)))
  customRows.value = customRows.value.filter((row) => !removing.has(rowKey(row)))
  persistCustomRows()
  selectedKeys.value = selectedKeys.value.filter((key) => !removing.has(key))
  page.value = Math.min(page.value, pageCount.value)
  emit('notify', `已删除 ${keys.length} 条货号映射`)
}

function deleteSelected() {
  deleteRows(selectedKeys.value)
}

function mergeRows() {
  const seen = new Set<string>()
  const combined = [...generatedRows.value, ...importedRows.value, ...customRows.value]
  if (!combined.length) {
    rows.value = [...seedRows]
    page.value = 1
    return
  }
  rows.value = combined.filter((row) => {
    const key = rowKey(row)
    if (deletedKeys.value.has(key)) return false
    if (seen.has(key)) return false
    seen.add(key)
    return true
  }).map((row) => ({ ...row, category: row.category && row.category !== '-' ? row.category : '塑胶' }))
  page.value = 1
}

async function importMappingFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  importingFile.value = true
  try {
    const result = await importCodeMappingFile(props.factoryId, file)
    const imported = result.rows as CodeRow[]
    customRows.value = [...imported, ...customRows.value]
    persistCustomRows()
    mergeRows()
    emit('notify', `${file.name} 已识别导入 ${result.count} 条货号映射。`)
  } catch (error) {
    emit('notify', `文件识别失败：${String(error)}`)
  } finally {
    importingFile.value = false
  }
}

async function loadYear(year: string) {
  const cached = yearCache.get(year)
  if (cached) {
    importedRows.value = cached
    mergeRows()
    return
  }
  loadingYear.value = true
  try {
    const response = await fetch(`/data/code-mappings-${year}.json?v=20261124`, { cache: 'no-store' })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = (await response.json()) as CodeRow[]
    yearCache.set(year, data)
    importedRows.value = data
    mergeRows()
  } catch (error) {
    importedRows.value = []
    mergeRows()
    emit('notify', `读取 ${year} 年出货登记失败：${String(error)}`)
  } finally {
    loadingYear.value = false
  }
}

async function changeYear() {
  selectedKeys.value = []
  await loadYear(selectedYear.value)
}

async function loadGeneratedRows() {
  const soDocs = await listGeneratedDocs(props.factoryId, 'so')
  const truckDocs = await listGeneratedDocs(props.factoryId, 'truck_export')
  const docs: GeneratedDoc[] = [...soDocs.slice(0, 12), ...truckDocs.slice(0, 8)]
  const next: CodeRow[] = []
  const seen = new Set<string>()
  for (const doc of docs) {
    let detail
    try { detail = await getGeneratedDoc(props.factoryId, doc.id) } catch { continue }
    const header = (detail.header ?? {}) as Record<string, unknown>
    const customer = String(doc.brand_name || header.brandName || header.brandNote || '').trim() || '—'
    for (const line of detail.lines ?? []) {
      const row = line as Record<string, unknown>
      const code = String(row.filingCode || row.product_code || row.declareCode || '').trim()
      if (!code) continue
      const cartons = Number(row.cartons) || 0
      const qty = Number(row.quantity) || 0
      const coefficient = Number(row.coefficient) || (cartons ? qty / cartons : 0)
      const perCarton = coefficient ? `${Math.round(coefficient * 100) / 100} 个` : '默认'
      const key = `${code}|${String(row.description || row.name || '')}|${perCarton}|${customer}`
      if (seen.has(key)) continue
      seen.add(key)
      const gross = Number(row.grossPerCarton) || (cartons ? (Number(row.grossWeight) || 0) / cartons : 0)
      const net = Number(row.netPerCarton) || (cartons ? (Number(row.netWeight) || 0) / cartons : 0)
      const headerDate = String(header.sheetDate || header.etd || header.shipDate || '').slice(0, 10)
      const rowCbm = Number(row.cbm) || 0
      const transport = String(header.transportCompany || header.transport || '').trim()
      const trip = String(header.truckHead || header.vehicle || header.number || header.truckNo || header.truck_no || '').trim()
      const containerType = String(header.containerType || header.truckType || '').trim()
      const plate = String(header.plate || row.plate || '').trim()
      const containerNo = String(header.containerNo || row.containerNo || '').trim()
      const sealNo = String(header.sealNo || row.sealNo || '').trim()
      next.push({
        code,
        name: String(row.description || row.name || ''),
        date: headerDate || doc.created_at.slice(0, 10),
        contractNo: String(header.contractNo || row.contractNo || row.contract_no || '-'),
        quantity: qty ? String(qty) : '-',
        cartons: cartons ? String(cartons) : '-',
        volume: rowCbm ? rowCbm.toFixed(3) : '-',
        country: String(header.destinationCountry || header.country || row.country || '-'),
        transport: transport || '-',
        containerMode: containerType ? '柜' : (trip ? 'T车' : '-'),
        trip: trip || '-',
        containerType: containerType || '-',
        plate: plate || '-',
        containerNo: containerNo || '-',
        sealNo: sealNo || '-',
        port: String(header.originPort || '-'),
        mode: String(header.truckType || header.containerType || '-'),
        po: String(row.customer_po || header.poNo || '-'),
        perCarton,
        category: String(row.category || '塑胶'),
        note: String(row.cartonMark || '-'),
        gross: gross ? gross.toFixed(3) : '-',
        net: net ? net.toFixed(3) : '-',
        source: doc.module === 'truck_export' ? '车表' : 'SO',
        customer,
        status: '已同步',
        tone: 'blue',
      })
    }
  }
  generatedRows.value = next
  mergeRows()
}

async function loadMappings() {
  try {
    await Promise.all([loadGeneratedRows(), loadYear(selectedYear.value)])
  } catch (error) {
    emit('notify', `货号映射自动导入失败：${String(error)}`)
  }
}

onMounted(loadMappings)

function preview(title: string) {
  emit('notify', `界面预览：${title}尚未接入后端接口。`)
}

function applySearch() {
  appliedKeyword.value = keyword.value
  page.value = 1
}

function reset() {
  keyword.value = ''
  appliedKeyword.value = ''
  activeCustomer.value = '全部'
  selectedKeys.value = []
  page.value = 1
}
</script>

<template>
  <section class="space-y-3" aria-label="货号映射管理">
    <div class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50 p-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex min-w-0 items-center gap-2">
          <h2 class="text-[16px] font-bold tracking-[-0.02em] text-emerald-950">货号映射管理</h2>
          <span class="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold tabular-nums text-emerald-900">{{ rows.length }}</span>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <label class="relative">
            <span class="sr-only">搜索货号、柜号或车牌</span>
            <Search class="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-emerald-700/50" aria-hidden="true" />
            <input
              v-model="keyword"
              type="search"
              aria-label="搜索合同号或货号"
              placeholder="搜索货号 / 柜号 / 车牌"
              class="h-8 w-[220px] rounded-lg border border-emerald-100 bg-white pl-8 pr-2.5 text-[12px] text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-3 focus:ring-emerald-500/15"
              @keydown.enter="applySearch"
            >
          </label>
          <button
            type="button"
            class="inline-flex h-8 items-center gap-1.5 rounded-lg bg-emerald-800 px-3 text-[12px] font-semibold text-white shadow-sm transition hover:bg-emerald-900"
            @click="applySearch"
          >
            <Search class="size-3.5" aria-hidden="true" />搜索
          </button>
          <button
            type="button"
            class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-emerald-200 bg-white px-3 text-[12px] font-semibold text-emerald-900 transition hover:bg-emerald-50"
            @click="loadMappings"
          >
            <RefreshCw class="size-3.5" aria-hidden="true" />刷新
          </button>
          <button
            type="button"
            class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-emerald-200 bg-white px-3 text-[12px] font-semibold text-emerald-900 transition hover:bg-emerald-50 disabled:opacity-60"
            :disabled="importingFile"
            @click="fileInput?.click()"
          >
            <Upload class="size-3.5" aria-hidden="true" />{{ importingFile ? '识别中…' : '导入文件' }}
          </button>
          <input ref="fileInput" type="file" accept=".xlsx,.xls" class="hidden" @change="importMappingFile">
          <button
            type="button"
            class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-emerald-200 bg-white px-3 text-[12px] font-semibold text-emerald-900 transition hover:bg-emerald-50"
            @click="reset"
          >
            <RotateCcw class="size-3.5" aria-hidden="true" />重置
          </button>
          <button
            type="button"
            class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-rose-200 bg-white px-3 text-[12px] font-semibold text-rose-600 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-40"
            :disabled="!selectedKeys.length"
            @click="deleteSelected"
          >
            <Trash2 class="size-3.5" aria-hidden="true" />删除选中{{ selectedKeys.length ? `（${selectedKeys.length}）` : '' }}
          </button>
          <button
            type="button"
            class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-emerald-200 bg-white px-3 text-[12px] font-semibold text-emerald-900 transition hover:bg-emerald-50"
            @click="preview('导出')"
          >
            <Download class="size-3.5" aria-hidden="true" />导出
          </button>
          <button
            type="button"
            class="inline-flex h-8 items-center gap-1.5 rounded-lg bg-emerald-700 px-3 text-[12px] font-semibold text-white shadow-sm transition hover:bg-emerald-800"
            @click="preview('新增货号映射')"
          >
            <Plus class="size-3.5" aria-hidden="true" />新增
          </button>
        </div>
      </div>

      <div class="mt-3 flex flex-wrap items-center gap-3">
        <label class="flex items-center gap-1.5 text-[11px] text-slate-500">年份
          <select v-model="selectedYear" class="h-7 rounded-lg border border-emerald-200 bg-white px-2 text-[11px] font-medium text-emerald-900" :disabled="loadingYear" @change="changeYear">
            <option v-for="year in yearOptions" :key="year" :value="year">{{ year }}</option>
          </select>
        </label>
        <span v-if="loadingYear" class="text-[11px] text-emerald-700">读取中…</span>
        <span class="text-[11px] text-slate-500">客户筛选：</span>
        <button
          v-for="customer in customers"
          :key="customer"
          type="button"
          class="rounded-full px-2.5 py-1 text-[11px] font-medium transition"
          :class="activeCustomer === customer ? 'bg-emerald-900 text-white' : 'border border-emerald-100 bg-white text-slate-600 hover:border-emerald-200 hover:text-emerald-900'"
          @click="activeCustomer = customer; page = 1"
        >
          {{ customer }}
        </button>
      </div>
    </div>

    <p class="flex items-start gap-2 rounded-lg border border-emerald-100 bg-emerald-50/70 px-3 py-2 text-[11px] leading-5 text-emerald-900/80">
      <Info class="mt-0.5 size-3.5 shrink-0 text-emerald-700" aria-hidden="true" />
      多规格匹配规则：货号相同、货名相同、每箱个数不同 → 视为独立记录，分行展示，导出时各自对应正确重量。
    </p>

    <div class="overflow-hidden rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/40">
      <div class="max-h-[68vh] overflow-auto">
        <table class="w-full min-w-[1360px] border-collapse text-left text-[11px]">
          <thead class="sticky top-0 z-10 bg-emerald-50/95 text-[11px] font-semibold text-emerald-900/75 backdrop-blur-sm">
            <tr>
              <th scope="col" class="w-9 px-2 py-2 text-center">
                <input type="checkbox" aria-label="全选当前页" :checked="allPageSelected" :indeterminate="somePageSelected && !allPageSelected" @change="togglePage">
              </th>
              <th scope="col" class="whitespace-nowrap px-2 py-2">日期</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2">合同号</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2">货号</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2">柜型/T车</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2 text-right">数量</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2 text-right">箱数</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2 text-right">每箱个数</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2">玩具类别</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2 text-right">每箱毛重（kg）</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2 text-right">每箱净重（kg）</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2 text-right">体积</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2">来源</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2">国家</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2">客户</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2">运输公司</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2">车牌号</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2">车次</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2">柜型</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2">柜号</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2">封条号</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2">港口</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2">状态</th>
              <th scope="col" class="whitespace-nowrap px-2 py-2 text-right">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-emerald-50/80">
            <tr v-for="row in pagedRows" :key="rowKey(row)" class="bg-white/70 hover:bg-emerald-50/50" :class="selectedKeys.includes(rowKey(row)) ? 'bg-emerald-50/70' : ''">
              <td class="px-2 py-2 text-center">
                <input type="checkbox" :aria-label="`选择 ${row.code}`" :checked="selectedKeys.includes(rowKey(row))" @change="toggleRow(row)">
              </td>
              <td class="whitespace-nowrap px-2 py-2 tabular-nums text-slate-600">{{ row.date || '-' }}</td>
              <td class="whitespace-nowrap px-2 py-2 tabular-nums text-slate-700">{{ row.contractNo || '-' }}</td>
              <td class="whitespace-nowrap px-2 py-2 font-semibold tabular-nums text-emerald-800">{{ row.code }}</td>
              <td class="max-w-[180px] truncate px-2 py-2 text-slate-600" :title="row.mode">{{ modeLabel(row) }}</td>
              <td class="whitespace-nowrap px-2 py-2 text-right tabular-nums text-slate-600">{{ row.quantity || '-' }}</td>
              <td class="whitespace-nowrap px-2 py-2 text-right tabular-nums text-slate-600">{{ row.cartons || '-' }}</td>
              <td class="whitespace-nowrap px-2 py-2 text-right tabular-nums text-slate-600">{{ row.perCarton }}</td>
              <td class="whitespace-nowrap px-2 py-2 text-slate-600">{{ row.category }}</td>
              <td class="whitespace-nowrap px-2 py-2 text-right tabular-nums text-slate-700">{{ row.gross }}</td>
              <td class="whitespace-nowrap px-2 py-2 text-right tabular-nums text-slate-700">{{ row.net }}</td>
              <td class="whitespace-nowrap px-2 py-2 text-right tabular-nums text-slate-700">{{ row.volume || '-' }}</td>
              <td class="whitespace-nowrap px-2 py-2">
                <span class="rounded-full border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-800">{{ row.source }}</span>
              </td>
              <td class="whitespace-nowrap px-2 py-2 text-slate-700">{{ row.country || '-' }}</td>
              <td class="max-w-[140px] truncate px-2 py-2 text-slate-700" :title="row.customer">{{ row.customer }}</td>
              <td class="whitespace-nowrap px-2 py-2 text-slate-600">{{ row.transport || '-' }}</td>
              <td class="whitespace-nowrap px-2 py-2 tabular-nums text-slate-600">{{ row.plate || '-' }}</td>
              <td class="whitespace-nowrap px-2 py-2 text-slate-600">{{ row.trip || '-' }}</td>
              <td class="whitespace-nowrap px-2 py-2 text-slate-600">{{ row.containerType || '-' }}</td>
              <td class="whitespace-nowrap px-2 py-2 tabular-nums text-slate-600">{{ row.containerNo || '-' }}</td>
              <td class="whitespace-nowrap px-2 py-2 tabular-nums text-slate-600">{{ row.sealNo || '-' }}</td>
              <td class="whitespace-nowrap px-2 py-2 text-slate-600">{{ row.port || '-' }}</td>
              <td class="whitespace-nowrap px-2 py-2">
                <span class="inline-flex items-center gap-1.5 text-[11px] text-slate-600">
                  <span class="size-1.5 rounded-full" :class="statusDot[row.tone]" aria-hidden="true" />
                  {{ row.status }}
                </span>
              </td>
              <td class="whitespace-nowrap px-2 py-2 text-right">
                <div class="inline-flex items-center gap-2">
                  <button type="button" class="text-[11px] font-semibold text-emerald-700 hover:text-emerald-900" @click="preview(`编辑货号映射 ${row.code}`)">编辑</button>
                  <button type="button" class="text-[11px] font-semibold text-rose-500 hover:text-rose-700" @click="deleteRows([rowKey(row)])">删除</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="filteredRows.length" class="flex flex-wrap items-center justify-between gap-2 border-t border-emerald-100 px-3 py-2 text-[11px] text-slate-600">
        <span>共 {{ filteredRows.length }} 条，第 {{ page }} / {{ pageCount }} 页</span>
        <div class="flex items-center gap-2">
          <button type="button" class="rounded border border-emerald-200 px-2 py-1 font-semibold text-emerald-800 disabled:opacity-40" :disabled="page <= 1" @click="page = Math.max(1, page - 1)">上一页</button>
          <button type="button" class="rounded border border-emerald-200 px-2 py-1 font-semibold text-emerald-800 disabled:opacity-40" :disabled="page >= pageCount" @click="page = Math.min(pageCount, page + 1)">下一页</button>
        </div>
      </div>
      <p v-if="!filteredRows.length" class="px-4 py-10 text-center text-[12px] text-slate-500">没有匹配的货号映射</p>
    </div>
  </section>
</template>

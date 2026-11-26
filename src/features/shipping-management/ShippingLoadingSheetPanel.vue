<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Download, Plus, Trash2 } from '@lucide/vue'
import { getApiErrorMessage } from '@/lib/http'
import {
  deleteLoadingSheet,
  downloadLoadingSheet,
  draftLoadingSheet,
  exportLoadingSheet,
  getLoadingSheet,
  listLoadingSheets,
  lookupScheduleLines,
  openLoadingSheet,
  searchScheduleProducts,
  type LoadingDraft,
  type LoadingHeader,
  type LoadingLine,
  type LoadingSheetDetail,
  type LoadingSheetRecord,
  type WorkbookPreviewSheet,
} from '@/api/shippingMail'
import { listShippingTasks, type ShippingScheduleTask } from '@/api/shippingTasks'
import { filingCodeFilename } from './contracts'
import { productNameForCode } from './productName'
import ShippingWorkbookPreviewModal from './ShippingWorkbookPreviewModal.vue'

const props = defineProps<{ factoryId: string; initialDraft?: LoadingDraft | null; searchQuery?: string; variant?: 'dk' | 'hq' }>()
const emit = defineEmits<{ notify: [message: string]; back: [] }>()

const tasks = ref<ShippingScheduleTask[]>([])
const selectedTaskId = ref('')
const LAST_TASK_KEY = `shipping-so-last-task:${props.factoryId}`

function saveLastTask(id: string) {
  if (typeof window === 'undefined' || !window.localStorage || !id) return
  window.localStorage.setItem(LAST_TASK_KEY, id)
}
const search = ref('')
const searching = ref(false)
const draft = ref<LoadingDraft | null>(null)
const tableNameEdited = ref(false)
const loadedTaskId = ref('')
const loading = ref(false)
const exporting = ref(false)
const recognizing = ref(false)
const message = ref('')
const sheets = ref<LoadingSheetRecord[]>([])
const selectedSheetIds = ref<string[]>([])
const viewedSheetIds = ref<Record<string, boolean>>({})
const sheetDetail = ref<LoadingSheetDetail | null>(null)
const sheetMessage = ref('')
const sheetLoading = ref(false)
const sheetBusy = ref(false)
const sheetDeleteArmed = ref(false)
const sheetPanelOpen = ref(true)
const sheetSearch = ref('')
const previewState = ref<{ sheet: LoadingSheetRecord; filename: string; path: string; sheets: WorkbookPreviewSheet[] } | null>(null)

const preparers = ['农建壮', '小美']
const isHq = computed(() => props.variant === 'hq')

function scheduleOptionLabel(task: ShippingScheduleTask) {
  const codes = [...new Set((task.items ?? []).map((item) => String(item.product_code || '').trim()).filter(Boolean))]
  const name = codes.length ? codes.join(' / ') : (task.so_number || task.id)
  return `${name} · ${task.planned_ship_date || '待定'} · ${task.port || '待定'}`
}

const filteredTasks = computed(() => {
  const keyword = (props.searchQuery?.trim() || search.value).trim().toLowerCase()
  if (!keyword) return tasks.value
  return tasks.value.filter((task) => {
    const values = [task.so_number, task.customer, task.port, task.planned_ship_date,
      ...(task.items ?? []).flatMap((item) => [item.contract_no, item.product_code, item.customer_po])]
    return values.some((value) => String(value || '').toLowerCase().includes(keyword))
  })
})

const totals = computed(() => {
  const sum = (key: keyof LoadingLine) => (draft.value?.lines ?? [])
    .reduce((total, line) => total + (Number(line[key]) || 0), 0)
  return {
    quantity: sum('quantity'),
    cartons: sum('cartons'),
    grossWeight: sum('grossWeight'),
    netWeight: sum('netWeight'),
    cbm: sum('cbm'),
    pallet: Math.round(sum('pallet') * 1000) / 1000,
  }
})

const allContracts = computed(() => [...new Set(
  (draft.value?.lines ?? []).map((line) => String(line.contract || '').trim()).filter(Boolean),
)])

watch(() => draft.value?.header.contractNo, (value) => {
  if (!draft.value || !value || !value.includes('/')) return
  draft.value.header.contractNo = value.split('/').map((part) => part.trim()).join('')
})

async function runSearch() {
  const query = search.value.trim()
  if (!query) return
  searching.value = true
  message.value = ''
  try {
    const items = await searchScheduleProducts(props.factoryId, query)
    const tokens = query.split(/[\s/,，]+/).map((token) => token.trim().toLowerCase()).filter(Boolean)
    const matched = items.filter((item) => {
      const code = String(item.product_code || '').trim().toLowerCase()
      const contract = String(item.contract_no || '').trim().toLowerCase()
      if (tokens.length >= 2) {
        return tokens.includes(code) && tokens.includes(contract)
      }
      return code === tokens[0] || contract === tokens[0]
    })
    if (!matched.length) {
      message.value = `合同号与备案货号未同时匹配：${query}`
      return
    }
    if (!draft.value) {
      message.value = `已匹对 ${query}，请先选择工厂排期或导入柜货单`
      return
    }
    const existing = new Set(draft.value.lines.map((line) => `${line.contract}|${line.filingCode}`))
    let added = 0
    for (const item of matched) {
      const code = String(item.product_code || '').trim()
      if (!code) continue
      const key = `${String(item.contract_no || '')}|${code}`
      if (existing.has(key)) continue
      const mapped = lineFromSchedule(item as unknown as Record<string, unknown>)
      const blankIndex = draft.value.lines.findIndex((line) =>
        !line.filingCode?.trim()
        && !line.declareCode?.trim()
        && (line.quantity == null || Number(line.quantity) === 0),
      )
      if (blankIndex >= 0) {
        const blank = draft.value.lines[blankIndex]!
        draft.value.lines.splice(blankIndex, 1, { ...mapped, id: blank.id })
      } else {
        draft.value.lines.push(mapped)
      }
      existing.add(key)
      added += 1
    }
    if (!draft.value.header.poNo && matched[0]?.customer_po) {
      draft.value.header.poNo = String(matched[0].customer_po)
    }
    if (added) {
      message.value = `已匹对 ${query}，填入 ${added} 行`
      await loadTasks()
      return
    }
    message.value = `合同号/备案货号 ${query} 对应数据已在明细中`
  } catch (error) {
    message.value = `搜索失败：${getApiErrorMessage(error)}`
  } finally {
    searching.value = false
  }
}

async function loadTasks() {
  try {
    const all = await listShippingTasks(props.factoryId)
    const today = new Date().toISOString().slice(0, 10)
    const valid = all
      .filter((task) => task.source === 'schedule')
      .filter((task) => (task.items?.length ?? 0) > 0)
      .filter((task) => Boolean(task.planned_ship_date) && task.planned_ship_date >= today)
      .sort((a, b) => String(b.planned_ship_date).localeCompare(String(a.planned_ship_date)))
    const bySo = new Map<string, ShippingScheduleTask>()
    for (const task of valid) {
      if (!bySo.has(task.so_number)) bySo.set(task.so_number, task)
    }
    tasks.value = [...bySo.values()].sort((a, b) => String(b.planned_ship_date).localeCompare(String(a.planned_ship_date)))
  } catch (error) {
    message.value = `无法读取工厂排期：${getApiErrorMessage(error)}`
  }
}

function lineFromSchedule(item: Record<string, unknown>): LoadingLine {
  const quantity = Number(item.quantity) || null
  const cartons = Number(item.cartons) || null
  return {
    id: crypto.randomUUID(),
    tradingCompany: 'DK',
    contract: String(item.contract_no || ''),
    filingCode: String(item.product_code || ''),
    declareCode: String(item.product_code || ''),
    coefficient: Number(item.coefficient) || (quantity && cartons ? quantity / cartons : null),
    quantity,
    cartons,
    grossWeight: Number(item.gross_weight) || null,
    netWeight: Number(item.net_weight) || null,
    cbm: Number(item.cbm) || null,
    category: '塑胶',
    grossPerCarton: cartons && Number(item.gross_weight) ? Number(item.gross_weight) / cartons : null,
    netPerCarton: cartons && Number(item.net_weight) ? Number(item.net_weight) / cartons : null,
    description: String(item.product_name || ''),
    department: 'W',
    pallet: null,
    cartonMark: String(item.customer_po || ''),
  }
}

async function recognizeContract() {
  if (!draft.value) return
  const query = draft.value.header.contractNo?.trim() || draft.value.header.soNo.trim()
  if (!query) return
  recognizing.value = true
  message.value = ''
  try {
    const items = await lookupScheduleLines(props.factoryId, query)
    if (!items.length) {
      syncLineContracts()
      if (!draft.value.lines.length) addLine()
      message.value = `提示：未找到 ${query} 对应的工厂排期，可直接按邮件信息资料补录明细，合同号沿用上方柜货单。`
      return
    }
    const existing = new Set(draft.value.lines.map((line) => `${line.contract}|${line.filingCode}`))
    let added = 0
    for (const item of items) {
      const key = `${String(item.contract_no || '')}|${String(item.product_code || '')}`
      if (existing.has(key)) continue
      draft.value.lines.push(lineFromSchedule(item))
      existing.add(key)
      added += 1
    }
    if (!draft.value.header.contractNo && items[0].contract_no) {
      draft.value.header.contractNo = String(items[0].contract_no)
    }
    if (!draft.value.header.soNo && items[0].so_number) {
      draft.value.header.soNo = String(items[0].so_number)
    }
    if (!draft.value.header.poNo && items[0].customer_po) {
      draft.value.header.poNo = String(items[0].customer_po)
    }
    if (selectedTaskId.value) {
      try {
        const scheduled = await draftLoadingSheet(props.factoryId, selectedTaskId.value)
        const target = draft.value.header as unknown as Record<string, string>
        const source = scheduled.header as unknown as Record<string, string>
        for (const key of ['vessel', 'voyage', 'bookingNo', 'cutoff', 'transportCompany', 'originPort', 'consignee']) {
          if (!target[key] && source[key]) target[key] = source[key]
        }
      } catch {
        // header fields from the imported document remain authoritative
      }
    }
    message.value = added ? `已从工厂排期识别并填入 ${added} 行产品` : '对应产品已在明细中'
  } catch (error) {
    message.value = `识别失败：${getApiErrorMessage(error)}`
  } finally {
    recognizing.value = false
  }
}

async function loadDraft() {
  if (!selectedTaskId.value) {
    draft.value = null
    return
  }
  loading.value = true
  message.value = ''
  tableNameEdited.value = false
  try {
    const sameTask = Boolean(draft.value && loadedTaskId.value === selectedTaskId.value)
    const previousHeader = sameTask
      ? JSON.parse(JSON.stringify(draft.value!.header)) as LoadingHeader
      : null
    const scheduled = await draftLoadingSheet(props.factoryId, selectedTaskId.value)
    const recognizedTableName = String(scheduled.header.tableName || '').trim()
    if (previousHeader) {
      scheduled.header = previousHeader
    }
    if (!tableNameEdited.value) {
      scheduled.header.tableName = recognizedTableName || scheduled.header.tableName
    }
    draft.value = scheduled
    loadedTaskId.value = selectedTaskId.value
    ensureTableName()
    if (!draft.value.header.shippingClerk) draft.value.header.shippingClerk = draft.value.header.preparer || '农建壮'
    if (!draft.value.header.tradeTerm) draft.value.header.tradeTerm = 'FOB'
    if (draft.value.lines.length === 0) addLine()
  } catch (error) {
    message.value = `生成柜单失败：${getApiErrorMessage(error)}`
  } finally {
    loading.value = false
  }
}

function addLine() {
  if (!draft.value) return
  draft.value.lines.push({
    id: crypto.randomUUID(), tradingCompany: 'DK',
    contract: draft.value.header.contractNo?.trim() || draft.value.lines[0]?.contract || '',
    filingCode: '', declareCode: '', coefficient: null, quantity: null, cartons: null, grossWeight: null, netWeight: null,
    cbm: null, category: '塑胶', grossPerCarton: null, netPerCarton: null, description: '', department: 'W', pallet: null,
  })
}

function ensureTableName() {
  if (!draft.value) return
  if (!String(draft.value.header.tableName || '').trim()) syncTableName()
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
  draft.value.header.tableName = formatTableName(draft.value.header.transportCompany, draft.value.header.originPort)
}

function syncLineContracts() {
  const contract = draft.value?.header.contractNo?.trim()
  if (!contract || !draft.value) return
  for (const line of draft.value.lines) {
    if (!line.contract?.trim()) line.contract = contract
  }
}

function sheetDateTime(value: string, createdAt?: string) {
  const time = String(createdAt || '').match(/(\d{1,2}:\d{2})/)?.[1] || ''
  return time ? `${value} ${time}` : value
}

function applyHeaderContract() {
  const contract = draft.value?.header.contractNo?.trim()
  if (!contract || !draft.value) return
  for (const line of draft.value.lines) line.contract = contract
}

function removeLine(index: number) {
  draft.value?.lines.splice(index, 1)
}

function recalcLine(line: LoadingLine) {
  const quantity = Number(line.quantity)
  const coefficient = Number(line.coefficient)
  if (!Number.isFinite(quantity) || !Number.isFinite(coefficient) || coefficient <= 0) return
  line.cartons = Math.round((quantity / coefficient) * 1000) / 1000
  if (line.grossPerCarton != null) line.grossWeight = Math.round(line.cartons * line.grossPerCarton * 1000) / 1000
  if (line.netPerCarton != null) line.netWeight = Math.round(line.cartons * line.netPerCarton * 1000) / 1000
}

function recalcWeights(line: LoadingLine) {
  const cartons = Number(line.cartons)
  if (!Number.isFinite(cartons)) return
  if (line.grossPerCarton != null) {
    line.grossWeight = Math.round(cartons * Number(line.grossPerCarton) * 1000) / 1000
  }
  if (line.netPerCarton != null) {
    line.netWeight = Math.round(cartons * Number(line.netPerCarton) * 1000) / 1000
  }
}

async function download() {
  if (!draft.value) return
  exporting.value = true
  try {
    const blob = await exportLoadingSheet(props.factoryId, {
      ...draft.value,
      lines: draft.value.lines,
    }, props.variant === 'hq' ? 'hq' : 'dk')
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const so = String(draft.value.header.soNo || '')
    const title = String(draft.value.header.tableName || '').trim()
      || formatTableName(draft.value.header.transportCompany, draft.value.header.originPort)
    const fallback = props.variant === 'hq' ? 'HQ柜出货' : `${title}${so ? `_${so}` : ''}`
    link.download = filingCodeFilename(
      draft.value.lines,
      props.variant === 'hq' ? '.xlsx' : '.xls',
      fallback,
      draft.value.header.filingCode,
    )
    link.click()
    URL.revokeObjectURL(url)
    emit('notify', `${isHq.value ? 'HQ柜出货' : '柜单'} ${draft.value.number} 已生成并下载。`)
    await loadTasks()
    await loadSheets()
  } catch (error) {
    message.value = `导出失败：${getApiErrorMessage(error)}`
  } finally {
    exporting.value = false
  }
}

async function loadSheets() {  sheetLoading.value = true
  try {
    sheets.value = await listLoadingSheets(props.factoryId, props.variant === 'hq' ? 'hq' : 'dk')
    const ids = new Set(sheets.value.map((sheet) => sheet.id))
    selectedSheetIds.value = selectedSheetIds.value.filter((id) => ids.has(id))
    const known = loadKnownSheetIds()
    if (known === null) {
      // First visit: current files are historical; only files generated after this point get a dot.
      for (const sheet of sheets.value) {
        window.localStorage.setItem(viewedSheetKey(sheet.id), '1')
      }
      viewedSheetIds.value = Object.fromEntries(sheets.value.map((sheet) => [sheet.id, true]))
      saveKnownSheetIds([...ids])
    } else {
      viewedSheetIds.value = Object.fromEntries(sheets.value.map((sheet) => [sheet.id, window.localStorage.getItem(viewedSheetKey(sheet.id)) === '1']))
      saveKnownSheetIds([...known, ...ids])
    }
  } catch (error) {
    sheetMessage.value = `读取导出记录失败：${getApiErrorMessage(error)}`
  } finally {
    sheetLoading.value = false
  }
}

function toggleSheet(id: string) {
  selectedSheetIds.value = selectedSheetIds.value.includes(id)
    ? selectedSheetIds.value.filter((value) => value !== id)
    : [...selectedSheetIds.value, id]
  sheetDeleteArmed.value = false
}

function viewedSheetKey(id: string) {
  return `shipping-sheet-viewed:${props.factoryId}:${id}`
}

function knownSheetsKey() {
  return `shipping-sheet-known:${props.factoryId}`
}

function loadKnownSheetIds(): Set<string> | null {
  const raw = window.localStorage.getItem(knownSheetsKey())
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    return new Set(Array.isArray(parsed) ? parsed.map((id) => String(id)) : [])
  } catch {
    return new Set()
  }
}

function saveKnownSheetIds(ids: string[]) {
  window.localStorage.setItem(knownSheetsKey(), JSON.stringify([...new Set(ids)]))
}

function isNewSheet(sheet: LoadingSheetRecord) {
  return !viewedSheetIds.value[sheet.id]
}

function markSheetViewed(sheet: LoadingSheetRecord) {
  window.localStorage.setItem(viewedSheetKey(sheet.id), '1')
  viewedSheetIds.value = { ...viewedSheetIds.value, [sheet.id]: true }
}

async function viewSheet(sheet: LoadingSheetRecord) {
  markSheetViewed(sheet)
  sheetBusy.value = true
  sheetMessage.value = ''
  try {
    sheetDetail.value = await getLoadingSheet(props.factoryId, sheet.id)
  } catch (error) {
    sheetMessage.value = `查看失败：${getApiErrorMessage(error)}`
  } finally {
    sheetBusy.value = false
  }
}

async function downloadSheet(sheet: LoadingSheetRecord) {
  markSheetViewed(sheet)
  sheetBusy.value = true
  sheetMessage.value = ''
  try {
    const blob = await downloadLoadingSheet(props.factoryId, sheet.id)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = sheet.filename || `${sheet.number}.xls`
    link.click()
    URL.revokeObjectURL(url)
    sheetMessage.value = `已下载 ${link.download}，并按月存入 D:\\导入文件\\SO 出货表`
  } catch (error) {
    sheetMessage.value = `下载失败：${getApiErrorMessage(error)}`
  } finally {
    sheetBusy.value = false
  }
}

async function openSheet(sheet: LoadingSheetRecord) {
  markSheetViewed(sheet)
  sheetBusy.value = true
  sheetMessage.value = ''
  try {
    const result = await openLoadingSheet(props.factoryId, sheet.id)
    sheetMessage.value = result.opened ? `已在 WPS 打开 ${sheet.filename}` : `已保存 ${result.path}`
  } catch (error) {
    sheetMessage.value = `打开失败：${getApiErrorMessage(error)}`
  } finally {
    sheetBusy.value = false
  }
}

async function bulkDeleteSheets() {
  if (!selectedSheetIds.value.length) return
  if (!sheetDeleteArmed.value) {
    sheetDeleteArmed.value = true
    window.setTimeout(() => { sheetDeleteArmed.value = false }, 5000)
    return
  }
  sheetBusy.value = true
  try {
    let deleted = 0
    for (const sheetId of [...selectedSheetIds.value]) {
      try {
        await deleteLoadingSheet(props.factoryId, sheetId)
        deleted += 1
      } catch {
        // continue with the remaining records
      }
    }
    selectedSheetIds.value = []
    sheetDeleteArmed.value = false
    sheetDetail.value = null
    await loadSheets()
    sheetMessage.value = `已删除 ${deleted} 份柜货单。`
  } finally {
    sheetBusy.value = false
  }
}

function firstSelectedSheet() {
  return sheets.value.find((sheet) => sheet.id === selectedSheetIds.value[0]) ?? null
}

const filteredSheets = computed(() => {
  const query = sheetSearch.value.trim().toLowerCase()
  if (!query) return sheets.value
  return sheets.value.filter((sheet) => {
    const haystack = [
      ...(sheet.filingCodes ?? []),
      sheet.filename,
      sheet.soNo,
      sheet.contractNo,
      sheet.number,
      sheet.transportCompany,
      sheet.originPort,
    ].join(' ').toLowerCase()
    return haystack.includes(query)
  })
})

const allVisibleSheetsSelected = computed(
  () => filteredSheets.value.length > 0 && filteredSheets.value.every((sheet) => selectedSheetIds.value.includes(sheet.id)),
)

function toggleAllVisibleSheets(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  selectedSheetIds.value = checked ? filteredSheets.value.map((sheet) => sheet.id) : []
  sheetDeleteArmed.value = false
}

async function viewSelectedSheet() {
  const sheet = firstSelectedSheet()
  if (sheet) await viewSheet(sheet)
}

async function openSelectedSheet() {
  const sheet = firstSelectedSheet()
  if (sheet) await openSheet(sheet)
}

watch(selectedTaskId, (id) => saveLastTask(id))

onMounted(async () => {
  await loadTasks()
  void loadSheets()
  if (!props.initialDraft && !selectedTaskId.value) {
    const last = typeof window !== 'undefined' && window.localStorage
      ? window.localStorage.getItem(LAST_TASK_KEY)
      : ''
    if (last) {
      selectedTaskId.value = last
      await loadDraft()
    }
  }
})

function blankCabinetHeader(scheduled: LoadingHeader): LoadingHeader {
  return {
    ...scheduled,
    shipper: scheduled.shipper || '华兴玩具制品（河源）有限公司',
    soNo: '',
    contractNo: '',
    bookingNo: '',
    vessel: '',
    voyage: '',
    containerType: '',
    cutoff: '',
    originPort: '',
    destinationCountry: '',
    transportCompany: '',
    consignee: '',
    plate: '',
    containerNo: '',
    sealNo: '',
    tareWeight: '',
    filingCode: '',
    truckHead: '',
    cartonMark: '',
    tradingCompany: '',
    brandNote: '',
    tradeTerm: 'FOB',
    shippingClerk: '农建壮',
    preparer: '农建壮',
  }
}

function lineCode(line: LoadingLine) {
  return (line.filingCode || line.declareCode || '').trim().toUpperCase()
}

function mergeScheduleLines(imported: LoadingLine[], scheduled: LoadingLine[], contract: string): LoadingLine[] {
  const byCode = new Map<string, LoadingLine[]>()
  for (const line of scheduled) {
    const code = lineCode(line)
    if (!code) continue
    byCode.set(code, [...(byCode.get(code) ?? []), line])
  }
  const merged: LoadingLine[] = []
  const emitted = new Set<string>()
  for (const line of imported) {
    const matches = byCode.get(lineCode(line)) ?? []
    if (!matches.length) {
      merged.push({ ...line, id: crypto.randomUUID(), contract: contract || line.contract })
      continue
    }
    for (const match of matches) {
      const key = `${match.contract}|${lineCode(match)}`
      if (emitted.has(key)) continue
      emitted.add(key)
      merged.push({ ...match, id: crypto.randomUUID(), contract: match.contract || contract })
    }
  }
  if (!merged.length) {
    for (const line of scheduled) {
      merged.push({ ...line, id: crypto.randomUUID(), contract: line.contract || contract })
    }
  }
  return merged
}

async function fillMissingDescriptions() {
  if (!draft.value) return
  const blank = draft.value.lines.filter((line) => !String(line.description || '').trim() && String(line.filingCode || line.declareCode || '').trim())
  if (!blank.length) return
  const names = new Map<string, string>()
  for (const line of blank) {
    const code = String(line.filingCode || line.declareCode || '').trim()
    const contract = String(line.contract || '').trim()
    try {
      const items = await searchScheduleProducts(props.factoryId, code)
      const candidates = items.filter((item) => item.product_name && (String(item.product_code || '').replace(/\s+/g, '') === code.replace(/\s+/g, '') || String(item.product_name).includes(code)))
      const hit = candidates.find((item) => contract && String(item.contract_no || '').trim() === contract) || candidates[0]
      if (hit?.product_name) names.set(`${contract}|${code}`, String(hit.product_name))
    } catch {
      // keep descriptions blank when schedule lookup fails
    }
  }
  for (const line of draft.value.lines) {
    const code = String(line.filingCode || line.declareCode || '').trim()
    const contract = String(line.contract || '').trim()
    const name = names.get(`${contract}|${code}`) || names.get(`|${code}`)
    line.description = productNameForCode(line.description || name, code)
  }
}

watch(() => props.initialDraft, async (value) => {
  if (!value) return
  draft.value = JSON.parse(JSON.stringify(value)) as LoadingDraft
  ensureTableName()
  if (!draft.value.header.shippingClerk) draft.value.header.shippingClerk = draft.value.header.preparer || '农建壮'
  if (!draft.value.header.tradeTerm) draft.value.header.tradeTerm = 'FOB'
  if (!selectedTaskId.value) selectedTaskId.value = value.taskId
  message.value = ''
  const importedContract = (draft.value.header.contractNo || '').trim()
  const importedContracts = new Set(draft.value.lines.map((line) => String(line.contract || '').trim()).filter(Boolean))
  const multiContract = importedContracts.size > 1
  const scheduleTaskId = selectedTaskId.value || value.taskId
  if (scheduleTaskId && !multiContract) {
    try {
      const scheduled = await draftLoadingSheet(props.factoryId, scheduleTaskId)
      const importedSo = (draft.value.header.soNo || '').trim()
      const scheduledSo = (scheduled.header.soNo || '').trim()
      const importedContractKey = String(draft.value.header.contractNo || '').replace(/\/\d+$/, '').trim().toLowerCase()
      const scheduledContractKey = String(scheduled.header.contractNo || '').replace(/\/\d+$/, '').trim().toLowerCase()
      const contractMatches = !importedContractKey || !scheduledContractKey || importedContractKey === scheduledContractKey
      const rebooked = Boolean(importedSo && scheduledSo && importedSo !== scheduledSo && contractMatches)
      const target = draft.value.header as unknown as Record<string, string>
      const source = scheduled.header as unknown as Record<string, string>
      if (rebooked) {
        for (const key of ['soNo', 'contractNo', 'bookingNo', 'cutoff', 'vessel', 'voyage', 'containerType', 'originPort', 'destinationCountry', 'transportCompany']) {
          if (source[key]) target[key] = source[key]
        }
      } else {
        if (!importedContract && scheduled.header.contractNo) {
          draft.value.header.contractNo = scheduled.header.contractNo
        }
        for (const key of ['vessel', 'voyage', 'bookingNo', 'cutoff', 'transportCompany', 'originPort', 'consignee']) {
          if (!target[key] && source[key]) target[key] = source[key]
        }
      }
      const contract = (draft.value.header.contractNo || '').trim()
      draft.value.lines = mergeScheduleLines(draft.value.lines, scheduled.lines, contract)
      if (contract && !multiContract) {
        for (const line of draft.value.lines) line.contract = contract
      }
      if (!draft.value.header.poNo) {
        draft.value.header.poNo = String(
          scheduled.header.poNo
          || scheduled.header.cartonMark
          || draft.value.header.cartonMark
          || draft.value.lines.find((line) => line.cartonMark)?.cartonMark
          || '',
        ).trim()
      }
      ensureTableName()
      if (rebooked) {
        message.value = '已按产品编号匹配新排期，合同号 / SO / 订舱号 / 截单日已更新为新排期。'
      } else if (!contractMatches) {
        message.value = '邮件合同号与匹配排期合同号不一致，已保留邮件合同号，未覆盖。'
      }
      await fillMissingDescriptions()
      return
    } catch {
      // fall back to the imported document's own lines
    }
  }
  await fillMissingDescriptions()
  syncLineContracts()
  ensureTableName()
  if (!draft.value.header.poNo) {
    draft.value.header.poNo = String(
      draft.value.header.cartonMark
      || draft.value.lines.find((line) => line.cartonMark)?.cartonMark
      || '',
    ).trim()
  }
  if (!draft.value.lines.length) addLine()
}, { immediate: true })
</script>

<template>
  <section class="space-y-4" aria-label="柜货单">
    <div class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50 p-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-[16px] font-bold text-emerald-950">柜货单</h2>
          <p class="mt-0.5 text-[11px] text-slate-500">{{ isHq ? '按 ZURU 盐田柜货模板生成；数量 = 箱数 × 装箱数，毛重/净重 = 每箱重量 × 箱数。' : '选择工厂排期生成柜货单；单号按当天顺序从 W1 起递增。' }}</p>
          <p v-if="allContracts.length" class="mt-0.5 text-[11px] font-medium text-emerald-700">合同号：{{ allContracts.join(' / ') }}</p>
        </div>
        <div v-if="!draft" class="flex flex-wrap items-center gap-2">
          <input
            v-model="search"
            type="search"
            aria-label="搜索合同号或备案货号"
            placeholder="合同号 + 备案货号"
            class="h-9 w-[190px] rounded-lg border border-emerald-200 bg-white px-2.5 text-[12px] text-slate-800 outline-none placeholder:text-slate-400 focus:border-emerald-500"
            @keyup.enter="runSearch"
          >
          <button type="button" class="h-9 rounded-lg bg-emerald-700 px-3 text-[12px] font-semibold text-white disabled:opacity-60" :disabled="searching" @click="runSearch">{{ searching ? '同步中…' : '搜索' }}</button>
          <select v-model="selectedTaskId" aria-label="选择工厂排期" class="h-9 max-w-[320px] rounded-lg border border-emerald-200 bg-white px-2 text-[12px]" @change="loadDraft">
            <option value="">选择工厂排期</option>
            <option v-for="task in filteredTasks" :key="task.id" :value="task.id">
              {{ scheduleOptionLabel(task) }}
            </option>
          </select>
        </div>
      </div>
      <p v-if="message" class="mt-2 text-[11px]" :class="message.startsWith('提示：') ? 'text-amber-700' : 'text-rose-600'">{{ message }}</p>
      <p v-if="loading" class="mt-2 text-[11px] text-slate-500">正在按排期生成…</p>
    </div>

    <template v-if="draft">
      <div class="rounded-xl border border-emerald-100/80 bg-white p-4">
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label class="text-[11px] text-slate-500">柜
            <input v-model="draft.header.number" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px] font-semibold">
          </label>
          <label class="text-[11px] text-slate-500">发货商
            <input v-model="draft.header.shipper" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">收货商
            <input v-model="draft.header.consignee" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">到货截止日期
            <input v-model="draft.header.cutoff" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">合同号
            <span class="mt-1 flex gap-1">
              <input v-model="draft.header.contractNo" class="h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]" @change="applyHeaderContract">
              <button type="button" class="shrink-0 rounded-lg border border-emerald-200 px-2 text-[10px] font-semibold text-emerald-700 disabled:opacity-50" :disabled="recognizing" @click="recognizeContract">
                {{ recognizing ? '识别中…' : '识别填入' }}
              </button>
            </span>
          </label>
          <label class="text-[11px] text-slate-500">船名
            <input v-model="draft.header.vessel" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">航次
            <input v-model="draft.header.voyage" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">运输公司
            <input v-model="draft.header.transportCompany" placeholder="成隆达" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]" @input="syncTableName">
          </label>
          <label class="text-[11px] text-slate-500">柜型
            <input v-model="draft.header.containerType" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">成交方式
            <select v-model="draft.header.tradeTerm" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
              <option value="FOB">FOB</option>
              <option value="EXW">EXW</option>
              <option value="CIF">CIF</option>
            </select>
          </label>
          <label class="text-[11px] text-slate-500">出口国家
            <input v-model="draft.header.destinationCountry" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">出港口
            <select v-model="draft.header.originPort" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]" @change="syncTableName">
              <option value="盐田">盐田</option>
              <option value="蛇口">蛇口</option>
            </select>
          </label>
          <label class="text-[11px] text-slate-500">订仓号
            <input v-model="draft.header.bookingNo" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">柜号
            <input v-model="draft.header.containerNo" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">柜重
            <input v-model="draft.header.tareWeight" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">船务
            <select v-model="draft.header.shippingClerk" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]" @change="draft.header.preparer = draft.header.shippingClerk || draft.header.preparer">
              <option v-for="name in preparers" :key="name" :value="name">{{ name }}</option>
            </select>
          </label>
          <label class="text-[11px] text-slate-500">车牌
            <input v-model="draft.header.plate" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">封条号
            <input v-model="draft.header.sealNo" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">备案货号
            <input v-model="draft.header.filingCode" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">车头注明 W 柜
            <input v-model="draft.header.truckHead" placeholder="如 W187" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">洋行
            <input v-model="draft.header.tradingCompany" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">品牌
            <input v-model="draft.header.brandNote" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">PO（箱唛）
            <input v-model="draft.header.poNo" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">表格名称
            <input v-model="draft.header.tableName" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]" @input="tableNameEdited = true">
          </label>
        </div>
      </div>

      <div class="flex flex-wrap items-center justify-end gap-2 px-1">
        <input
          v-model="search"
          type="search"
          aria-label="搜索合同号或备案货号"
          placeholder="合同号 + 备案货号"
          class="h-9 w-[190px] rounded-lg border border-emerald-200 bg-white px-2.5 text-[12px] text-slate-800 outline-none placeholder:text-slate-400 focus:border-emerald-500"
          @keyup.enter="runSearch"
        >
        <button type="button" class="h-9 rounded-lg bg-emerald-700 px-3 text-[12px] font-semibold text-white disabled:opacity-60" :disabled="searching" @click="runSearch">{{ searching ? '同步中…' : '搜索' }}</button>
        <select v-model="selectedTaskId" aria-label="选择工厂排期" class="h-9 max-w-[320px] rounded-lg border border-emerald-200 bg-white px-2 text-[12px]" @change="loadDraft">
          <option value="">选择工厂排期</option>
          <option v-for="task in filteredTasks" :key="task.id" :value="task.id">
            {{ scheduleOptionLabel(task) }}
          </option>
        </select>
        <button type="button" class="h-9 rounded-lg border border-emerald-200 bg-white px-3 text-[12px] font-semibold text-emerald-800 transition hover:bg-emerald-50" @click="emit('back')">← 返回工厂排期</button>
        <button type="button" class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-emerald-700 px-4 text-[12px] font-semibold text-white transition hover:bg-emerald-800 disabled:opacity-60" :disabled="!draft || exporting" @click="download">
          <Download class="size-3.5" />{{ exporting ? '生成中…' : '导出柜货单' }}
        </button>
      </div>

      <p v-if="allContracts.length" class="px-1 text-[11px] font-medium text-emerald-800">合同号：{{ allContracts.join(' / ') }}</p>

      <div class="overflow-x-auto rounded-xl border border-emerald-100/80 bg-white">
        <table class="w-full min-w-[1260px] text-left text-[11px]">
          <thead class="bg-emerald-50 text-emerald-900/70">
            <tr>
              <th class="px-2 py-2">洋行</th><th class="px-2 py-2">合同号</th><th class="px-2 py-2">备案货号</th>
              <th class="px-2 py-2">走货申报货号</th><th class="px-2 py-2">出箱数</th><th class="px-2 py-2">数量</th><th class="px-2 py-2">件数</th>
              <th class="px-2 py-2">毛重</th><th class="px-2 py-2">净重</th><th class="px-2 py-2">体积CBM</th>
              <th class="px-2 py-2">玩具类别</th><th class="px-2 py-2">KG/箱（毛重）</th><th class="px-2 py-2">KG/箱（净重）</th>
              <th class="px-2 py-2">产品名称</th><th class="px-2 py-2">箱唛</th><th class="px-2 py-2">部门</th><th class="px-2 py-2" title="仅用于页面记录与卡板统计，不写入导出的柜货单表格">卡板数量</th><th class="px-2 py-2"></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-emerald-50">
            <tr v-for="(line, index) in draft.lines" :key="line.id">
              <td class="px-2 py-1"><input v-model="line.tradingCompany" class="h-7 w-14 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1"><input v-model="line.contract" class="h-7 w-40 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1"><input v-model="line.filingCode" class="h-7 w-28 rounded border border-emerald-100 px-1" @input="line.declareCode = line.filingCode"></td>
              <td class="px-2 py-1"><input v-model="line.declareCode" class="h-7 w-28 rounded border border-emerald-100 px-1" @input="line.filingCode = line.declareCode"></td>
              <td class="px-2 py-1"><input v-model.number="line.coefficient" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right" @input="recalcLine(line)"></td>
              <td class="px-2 py-1"><input v-model.number="line.quantity" type="number" class="h-7 w-20 rounded border border-emerald-100 px-1 text-right" @input="recalcLine(line)"></td>
              <td class="px-2 py-1"><input v-model.number="line.cartons" type="number" class="h-7 w-16 rounded border border-emerald-100 bg-slate-50 px-1 text-right" readonly title="件数 = 数量 ÷ 出箱数"></td>
              <td class="px-2 py-1"><input v-model.number="line.grossWeight" type="number" class="h-7 w-20 rounded border border-emerald-100 bg-slate-50 px-1 text-right" readonly title="毛重 = KG/箱毛重 × 件数"></td>
              <td class="px-2 py-1"><input v-model.number="line.netWeight" type="number" class="h-7 w-20 rounded border border-emerald-100 bg-slate-50 px-1 text-right" readonly title="净重 = KG/箱净重 × 件数"></td>
              <td class="px-2 py-1"><input v-model.number="line.cbm" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-2 py-1"><input v-model="line.category" class="h-7 w-16 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1"><input v-model.number="line.grossPerCarton" type="number" class="h-7 w-20 rounded border border-emerald-100 px-1 text-right" @input="recalcWeights(line)"></td>
              <td class="px-2 py-1"><input v-model.number="line.netPerCarton" type="number" class="h-7 w-20 rounded border border-emerald-100 px-1 text-right" @input="recalcWeights(line)"></td>
              <td class="px-2 py-1"><input v-model="line.description" class="h-7 w-40 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1"><input v-model="line.cartonMark" class="h-7 w-24 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1"><input v-model="line.department" class="h-7 w-10 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1"><input v-model.number="line.pallet" type="number" min="0" step="0.5" placeholder="0" aria-label="卡板数量" title="仅用于页面记录与卡板统计，不写入导出的柜货单表格" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right tabular-nums"></td>
              <td class="px-2 py-1 text-center">
                <button type="button" class="text-rose-500 hover:text-rose-700" aria-label="删除明细" @click="removeLine(index)"><Trash2 class="size-3.5" /></button>
              </td>
            </tr>
            <tr class="bg-emerald-50/60 font-semibold text-emerald-950">
              <td class="px-2 py-2" colspan="4">合计</td>
              <td class="px-2 py-2"></td>
              <td class="px-2 py-2 text-right">{{ totals.quantity }}</td>
              <td class="px-2 py-2 text-right">{{ totals.cartons }}</td>
              <td class="px-2 py-2 text-right">{{ totals.grossWeight.toFixed(2) }}</td>
              <td class="px-2 py-2 text-right">{{ totals.netWeight.toFixed(2) }}</td>
              <td class="px-2 py-2 text-right">{{ totals.cbm.toFixed(2) }}</td>
              <td colspan="6"></td>
              <td class="px-2 py-2 text-right tabular-nums">{{ totals.pallet }}</td>
              <td></td>
            </tr>
          </tbody>
        </table>
        <div class="flex flex-wrap items-center gap-2 p-3">
          <button type="button" class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-emerald-200 px-3 text-[12px] font-semibold text-emerald-800" @click="addLine">
            <Plus class="size-3.5" />添加明细
          </button>
        </div>
      </div>
    </template>

    <div class="rounded-xl border border-emerald-100/80 bg-white p-3">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <h3 class="text-[13px] font-bold text-emerald-950">{{ isHq ? '已导出HQ柜出货' : '已导出柜货单' }}</h3>
          <span class="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">{{ filteredSheets.length }}/{{ sheets.length }}</span>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <input
            v-model="sheetSearch"
            type="search"
            aria-label="搜索备案货号或文件名"
            placeholder="搜索备案货号 / 文件名"
            class="h-7 w-[190px] rounded border border-emerald-200 bg-white px-2 text-[11px] text-slate-700 outline-none placeholder:text-slate-400 focus:border-emerald-500"
          >
          <button type="button" class="h-7 rounded border border-slate-200 px-2 text-[11px] text-slate-600 disabled:opacity-40" :disabled="selectedSheetIds.length !== 1 || sheetBusy" @click="viewSelectedSheet">查看文件</button>
          <button type="button" class="h-7 rounded border border-emerald-200 px-2 text-[11px] font-semibold text-emerald-700 disabled:opacity-40" :disabled="selectedSheetIds.length !== 1 || sheetBusy" @click="openSelectedSheet">打开文件</button>
          <label class="inline-flex items-center gap-1 text-[10px] font-medium text-slate-500">
            <input type="checkbox" aria-label="全选已导出柜货单" :checked="allVisibleSheetsSelected" @change="toggleAllVisibleSheets">
            全选
          </label>
          <button
            type="button"
            class="h-7 rounded border px-2 text-[11px] font-semibold disabled:opacity-40"
            :class="sheetDeleteArmed ? 'border-rose-300 bg-rose-50 text-rose-700' : 'border-rose-200 text-rose-600'"
            :disabled="!selectedSheetIds.length || sheetBusy"
            @click="bulkDeleteSheets"
          >{{ sheetDeleteArmed ? `确认删除 ${selectedSheetIds.length} 份` : `批量删除${selectedSheetIds.length ? ` (${selectedSheetIds.length})` : ''}` }}</button>
          <button type="button" class="h-7 rounded border border-slate-200 px-2 text-[11px] text-slate-600" :disabled="sheetLoading" @click="loadSheets">刷新</button>
          <button type="button" class="h-7 rounded border border-slate-200 px-2 text-[11px] text-slate-600" :aria-expanded="sheetPanelOpen" @click="sheetPanelOpen = !sheetPanelOpen">{{ sheetPanelOpen ? '收起' : '展开' }}</button>
        </div>
      </div>

      <p v-if="sheetMessage" class="mt-2 text-[11px]" :class="sheetMessage.startsWith('已') ? 'text-emerald-700' : 'text-rose-600'">{{ sheetMessage }}</p>

      <template v-if="sheetPanelOpen">

      <div v-if="sheets.length" class="mt-2 overflow-x-auto">
        <table class="w-full min-w-[760px] text-left text-[11px]">
          <thead class="bg-emerald-50 text-emerald-900/70">
            <tr>
              <th class="w-8 px-2 py-1.5"></th>
              <th class="px-2 py-1.5">文件名</th>
              <th class="px-2 py-1.5">备案货号</th>
              <th class="px-2 py-1.5">柜号</th>
              <th class="px-2 py-1.5">建表时间</th>
              <th class="px-2 py-1.5">SO</th>
              <th class="px-2 py-1.5">合同号</th>
              <th class="px-2 py-1.5 text-right">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-emerald-50">
            <tr v-for="sheet in filteredSheets" :key="sheet.id" class="hover:bg-emerald-50/50">
              <td class="px-2 py-1.5"><input type="checkbox" :aria-label="`选择 ${sheet.filename}`" :checked="selectedSheetIds.includes(sheet.id)" @change="toggleSheet(sheet.id)"></td>
              <td class="max-w-[300px] truncate px-2 py-1.5"><button type="button" class="inline-flex items-center gap-1.5 font-semibold text-emerald-800 hover:underline" @click="viewSheet(sheet)"><span v-if="isNewSheet(sheet)" class="size-2 shrink-0 rounded-full bg-rose-500" :data-sheet-id="sheet.id" aria-label="新文件"></span>{{ sheet.filename || `${sheet.number}.xls` }}</button></td>
              <td class="px-2 py-1.5 tabular-nums text-slate-600">{{ (sheet.filingCodes ?? []).join(' / ') || '—' }}</td>
              <td class="px-2 py-1.5 tabular-nums">{{ sheet.number }}</td>
              <td class="px-2 py-1.5 tabular-nums">{{ sheetDateTime(sheet.sheetDate, sheet.createdAt) }}</td>
              <td class="px-2 py-1.5">{{ sheet.soNo || '—' }}</td>
              <td class="px-2 py-1.5">{{ sheet.contractNo || '—' }}</td>
              <td class="px-2 py-1.5 text-right whitespace-nowrap">
                <button type="button" class="mr-2 text-emerald-700" @click="downloadSheet(sheet)">下载</button>
                <button type="button" class="mr-2 text-emerald-700" @click="viewSheet(sheet)">查看</button>
                <button type="button" class="text-emerald-700" @click="openSheet(sheet)">打开</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="mt-2 text-[11px] text-slate-400">暂无导出记录；导出一份柜货单后会出现在这里。</p>

      <div v-if="sheetDetail" class="mt-3 rounded-lg border border-emerald-100 bg-emerald-50/40 p-3 text-[11px]">
        <div class="grid gap-2 sm:grid-cols-3">
          <p><span class="text-slate-400">文件：</span>{{ sheetDetail.filename }}</p>
          <p><span class="text-slate-400">柜号：</span>{{ sheetDetail.number }}</p>
          <p><span class="text-slate-400">建表时间：</span>{{ sheetDateTime(sheetDetail.sheetDate, sheetDetail.createdAt) }}</p>
          <p><span class="text-slate-400">SO：</span>{{ sheetDetail.header.soNo || '—' }}</p>
          <p><span class="text-slate-400">合同号：</span>{{ sheetDetail.header.contractNo || '—' }}</p>
          <p><span class="text-slate-400">运输公司：</span>{{ sheetDetail.header.transportCompany || '—' }}</p>
          <p><span class="text-slate-400">明细行数：</span>{{ sheetDetail.lines.length }}</p>
          <p><span class="text-slate-400">数量：</span>{{ sheetDetail.totals.quantity ?? 0 }}</p>
          <p><span class="text-slate-400">CBM：</span>{{ sheetDetail.totals.cbm ?? 0 }}</p>
          <p><span class="text-slate-400">卡板数量：</span>{{ sheetDetail.lines.reduce((acc, item) => acc + (Number(item.pallet) || 0), 0) }}</p>
        </div>
        <button type="button" class="mt-2 text-[11px] text-slate-500 hover:text-slate-700" @click="sheetDetail = null">关闭查看</button>
      </div>
      </template>
    </div>

    <ShippingWorkbookPreviewModal
      v-if="previewState"
      :filename="previewState.filename"
      :path="previewState.path"
      :sheets="previewState.sheets"
      can-download
      @close="previewState = null"
      @download="downloadSheet(previewState.sheet)"
    />
  </section>
</template>

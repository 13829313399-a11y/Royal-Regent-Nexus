<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  ArrowLeft,
  ArrowUpRight,
  Check,
  Coins,
  Download,
  Layers,
  Package,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  RotateCw,
  Search,
  Ship,
  Trash2,
  X,
} from '@lucide/vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { Tone } from '@/data/enterpriseMock'
import { getApiErrorMessage } from '@/lib/http'
import {
  batchDeleteShippingPalletRecords,
  createShippingPalletRecord,
  exportShippingPalletStats,
  fetchShippingPalletStats,
  restoreExcludedShippingPalletRecords,
  updateShippingPalletGroup,
  updateShippingPalletRecord,
  type ManualPalletRecordPayload,
  type PalletBatchDeleteItem,
  type PalletRecordType,
  type PalletStatsDetail,
  type PalletStatsGroup,
  type PalletStatsResponse,
} from '@/api/shippingMail'
import { shippingFactoryProfiles, type ShippingFactoryId } from './contracts'

const props = withDefaults(defineProps<{ factoryId?: string }>(), {
  factoryId: 'huaxing',
})

const emit = defineEmits<{ notify: [message: string] }>()

const SPEC_PRESETS = [
  { value: '标准木卡板 (1200×1000)', price: 65 },
  { value: '出口熏蒸卡板 (1100×1100)', price: 75 },
  { value: '散货周转卡板 (1200×1000)', price: 55 },
] as const

const CONTAINER_TYPE_OPTIONS = ['40HQ', '40GP', '20GP', '散货车', '其他'] as const

const MONTH_OPTIONS = Array.from({ length: 12 }, (_, idx) => {
  const num = String(idx + 1).padStart(2, '0')
  return { value: num, label: `${idx + 1}月` }
})

function todayIsoDate() {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function currentYearValue() {
  return String(new Date().getFullYear())
}

function currentMonthPart() {
  return String(new Date().getMonth() + 1).padStart(2, '0')
}

const filters = reactive({
  year: currentYearValue(),
  month: currentMonthPart(),
  factoryId: props.factoryId || 'huaxing',
  customer: 'all',
  unitPriceInput: '',
  q: '',
})

const searchInput = ref('')
const activeTab = ref<'summary' | 'details'>('summary')
const drilldownGroup = ref<PalletStatsGroup | null>(null)
const loading = ref(false)
const exporting = ref(false)
const saving = ref(false)
const deleting = ref(false)
const restoring = ref(false)
const errorMessage = ref('')
const lastUpdated = ref('')
const stats = ref<PalletStatsResponse | null>(null)
const selectedKeys = ref<string[]>([])

const formOpen = ref(false)
const editingRecordId = ref<string | null>(null)
const editingRecordType = ref<PalletRecordType>('manual')
const editingOriginFactoryId = ref('')
const formError = ref('')
const priceTouched = ref(false)

const editingGroupKey = ref<string | null>(null)
const savingGroup = ref(false)
const groupCostTouched = ref(false)
const groupDraft = reactive({
  factoryId: props.factoryId || 'huaxing',
  customer: '',
  spec: '',
  containerCount: '0',
  totalPallets: '0',
  unitPrice: '65',
  estimatedCost: '0',
})
const manualForm = reactive({
  factory_id: props.factoryId || 'huaxing',
  ship_date: todayIsoDate(),
  customer: '',
  container_no: '',
  container_type: '40HQ',
  so_no: '',
  contract_no: '',
  filing_codes: '',
  specPreset: SPEC_PRESETS[0].value as string,
  customSpec: '',
  cartons: '0',
  pallets: '',
  unit_price: String(SPEC_PRESETS[0].price),
  is_container: true,
  remark: '',
})

const deleteDialogOpen = ref(false)
const deleteTargets = ref<PalletBatchDeleteItem[]>([])

let searchTimer: ReturnType<typeof setTimeout> | null = null

const fallbackFactories = computed(() =>
  (Object.keys(shippingFactoryProfiles) as ShippingFactoryId[]).map((id) => ({
    id,
    name: shippingFactoryProfiles[id].label,
  })),
)

const factoryOptions = computed(() => {
  const available = stats.value?.availableFactories ?? []
  return available.length ? available : fallbackFactories.value
})

const yearOptions = computed(() => {
  const current = new Date().getFullYear()
  const base = [current + 1, current, current - 1, current - 2, current - 3].map(String)
  const merged = new Set([...(stats.value?.availableYears ?? []), ...base])
  return Array.from(merged).filter((y) => /^\d{4}$/.test(y)).sort((a, b) => b.localeCompare(a))
})

const customerOptions = computed(() => stats.value?.availableCustomers ?? [])

const customerSuggestions = computed(() => {
  const names = new Set<string>(customerOptions.value)
  for (const row of stats.value?.details ?? []) {
    if (row.customer) names.add(row.customer)
  }
  return Array.from(names).sort((a, b) => a.localeCompare(b))
})

const summary = computed(() => stats.value?.summary ?? {
  totalPallets: 0,
  totalContainers: 0,
  estimatedCost: 0,
  recordCount: 0,
  customerCount: 0,
})

const groups = computed(() => stats.value?.groups ?? [])
const allDetails = computed(() => stats.value?.details ?? [])

const visibleDetails = computed<PalletStatsDetail[]>(() => {
  if (!drilldownGroup.value) return allDetails.value
  const target = drilldownGroup.value
  return allDetails.value.filter(
    (row) => row.factoryId === target.factoryId && row.customer === target.customer && row.spec === target.spec,
  )
})

function selectionKey(row: Pick<PalletStatsDetail, 'id' | 'factoryId' | 'recordType'>) {
  return `${row.recordType}::${row.factoryId}::${row.id}`
}

const detailByKey = computed(() => {
  const map = new Map<string, PalletStatsDetail>()
  for (const row of allDetails.value) {
    map.set(selectionKey(row), row)
  }
  return map
})

const selectedKeySet = computed(() => new Set(selectedKeys.value))

const selectedItems = computed<PalletBatchDeleteItem[]>(() => {
  const list: PalletBatchDeleteItem[] = []
  for (const key of selectedKeys.value) {
    const row = detailByKey.value.get(key)
    if (row) {
      list.push({
        id: row.id,
        factoryId: row.factoryId,
        originFactoryId: row.originFactoryId || row.factoryId,
        recordType: row.recordType,
      })
    }
  }
  return list
})

function detailsForGroup(group: PalletStatsGroup): PalletStatsDetail[] {
  return allDetails.value.filter(
    (row) => row.factoryId === group.factoryId && row.customer === group.customer && row.spec === group.spec,
  )
}

function groupSelectionState(group: PalletStatsGroup): boolean | 'indeterminate' {
  const rows = detailsForGroup(group)
  if (!rows.length) return false
  let count = 0
  for (const row of rows) {
    if (selectedKeySet.value.has(selectionKey(row))) count += 1
  }
  if (count === 0) return false
  if (count === rows.length) return true
  return 'indeterminate'
}

const summaryGroupKeys = computed(() => {
  const keys: string[] = []
  for (const group of groups.value) {
    for (const row of detailsForGroup(group)) {
      keys.push(selectionKey(row))
    }
  }
  return keys
})

const summarySelectAllState = computed<boolean | 'indeterminate'>(() => {
  const keys = summaryGroupKeys.value
  if (!keys.length) return false
  let count = 0
  for (const key of keys) {
    if (selectedKeySet.value.has(key)) count += 1
  }
  if (count === 0) return false
  if (count === keys.length) return true
  return 'indeterminate'
})

const detailsSelectAllState = computed<boolean | 'indeterminate'>(() => {
  const rows = visibleDetails.value
  if (!rows.length) return false
  let count = 0
  for (const row of rows) {
    if (selectedKeySet.value.has(selectionKey(row))) count += 1
  }
  if (count === 0) return false
  if (count === rows.length) return true
  return 'indeterminate'
})

const isCurrentMonthSelected = computed(
  () => filters.year === currentYearValue() && filters.month === currentMonthPart(),
)

const kpiPalletTitle = computed(() => {
  if (filters.year === 'all') return '累计总用板数'
  if (filters.month === 'all') return '年度总用板数'
  return '当月总用板数'
})

const periodLabel = computed(() => {
  if (filters.year === 'all') return '全部年份'
  if (filters.month === 'all') return `${filters.year} 年全年`
  return `${filters.year}-${filters.month} 当月`
})

const resolvedSpec = computed(() =>
  manualForm.specPreset === 'custom' ? manualForm.customSpec.trim() : manualForm.specPreset,
)

const previewManualCost = computed(() => {
  const qty = Number(manualForm.pallets)
  const price = Number(manualForm.unit_price)
  if (!Number.isFinite(qty) || !Number.isFinite(price) || qty < 0 || price < 0) return 0
  return Math.round(qty * price * 100) / 100
})

const deleteBreakdown = computed(() => {
  const manualCount = deleteTargets.value.filter((item) => item.recordType === 'manual').length
  const syncCount = deleteTargets.value.length - manualCount
  return { manualCount, syncCount }
})

function formatCurrency(value: number) {
  return Number(value || 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function sourceTone(source: string): Tone {
  if (source.includes('补料单') && source.includes('柜货单')) return 'green'
  if (source.includes('柜货单')) return 'teal'
  if (source.includes('补料单') || source.includes('手动录入')) return 'blue'
  if (source.includes('车货单')) return 'amber'
  return 'slate'
}

function queryParams() {
  const parsedPrice = Number(filters.unitPriceInput)
  const yearParam = filters.year || 'all'
  const monthParam = yearParam === 'all' || filters.month === 'all'
    ? 'all'
    : `${yearParam}-${filters.month}`
  return {
    factory_id: filters.factoryId || 'all',
    year: yearParam,
    month: monthParam,
    customer: filters.customer || 'all',
    unit_price: Number.isFinite(parsedPrice) && parsedPrice > 0 ? parsedPrice : undefined,
    q: filters.q.trim() || undefined,
  }
}

async function loadStats() {
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await fetchShippingPalletStats(queryParams())
    stats.value = data
    if (filters.customer !== 'all' && !data.availableCustomers.includes(filters.customer)) {
      filters.customer = 'all'
    }
    const validKeys = new Set(data.details.map((row) => selectionKey(row)))
    selectedKeys.value = selectedKeys.value.filter((key) => validKeys.has(key))
    if (drilldownGroup.value) {
      drilldownGroup.value = data.groups.find((g) => g.key === drilldownGroup.value?.key) ?? null
    }
    lastUpdated.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } catch (error) {
    errorMessage.value = `读取卡板统计失败：${getApiErrorMessage(error)}`
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  editingGroupKey.value = null
  drilldownGroup.value = null
  void loadStats()
}

function onYearSelect(val: unknown) {
  const nextYear = String(val ?? 'all')
  filters.year = nextYear
  if (nextYear === 'all') {
    filters.month = 'all'
  }
  onFilterChange()
}

function onMonthSelect(val: unknown) {
  const nextMonth = String(val ?? 'all')
  filters.month = nextMonth
  if (nextMonth !== 'all' && filters.year === 'all') {
    filters.year = currentYearValue()
  }
  onFilterChange()
}

function togglePeriodQuick() {
  if (isCurrentMonthSelected.value) {
    filters.year = 'all'
    filters.month = 'all'
  } else {
    filters.year = currentYearValue()
    filters.month = currentMonthPart()
  }
  onFilterChange()
}

function applySearchNow() {
  if (searchTimer) {
    clearTimeout(searchTimer)
    searchTimer = null
  }
  const nextQ = searchInput.value.trim()
  if (filters.q === nextQ) return
  filters.q = nextQ
  onFilterChange()
}

function clearSearch() {
  if (searchTimer) {
    clearTimeout(searchTimer)
    searchTimer = null
  }
  searchInput.value = ''
  if (filters.q !== '') {
    filters.q = ''
    onFilterChange()
  }
}

watch(searchInput, (val) => {
  if (searchTimer) clearTimeout(searchTimer)
  const trimmed = val.trim()
  if (trimmed === filters.q) return
  searchTimer = setTimeout(() => {
    filters.q = trimmed
    onFilterChange()
  }, 250)
})

function resetFilters() {
  if (searchTimer) {
    clearTimeout(searchTimer)
    searchTimer = null
  }
  filters.year = currentYearValue()
  filters.month = currentMonthPart()
  filters.factoryId = props.factoryId || 'all'
  filters.customer = 'all'
  filters.unitPriceInput = ''
  filters.q = ''
  searchInput.value = ''
  selectedKeys.value = []
  editingGroupKey.value = null
  drilldownGroup.value = null
  activeTab.value = 'summary'
  void loadStats()
}

function toggleKeys(keys: string[], checked: boolean) {
  const next = new Set(selectedKeys.value)
  for (const key of keys) {
    if (checked) next.add(key)
    else next.delete(key)
  }
  selectedKeys.value = Array.from(next)
}

function toggleGroupSelection(group: PalletStatsGroup, checked: boolean | 'indeterminate') {
  const keys = detailsForGroup(group).map((row) => selectionKey(row))
  toggleKeys(keys, checked === true)
}

function toggleAllSummary(checked: boolean | 'indeterminate') {
  toggleKeys(summaryGroupKeys.value, checked === true)
}

function toggleDetailSelection(row: PalletStatsDetail, checked: boolean | 'indeterminate') {
  toggleKeys([selectionKey(row)], checked === true)
}

function toggleAllDetails(checked: boolean | 'indeterminate') {
  toggleKeys(
    visibleDetails.value.map((row) => selectionKey(row)),
    checked === true,
  )
}

function drillDown(group: PalletStatsGroup) {
  drilldownGroup.value = group
  activeTab.value = 'details'
}

function clearDrilldown() {
  drilldownGroup.value = null
}

function backToSummary() {
  drilldownGroup.value = null
  activeTab.value = 'summary'
}

function defaultManualDate() {
  const today = todayIsoDate()
  if (filters.year === 'all') return today
  if (filters.year === today.slice(0, 4) && (filters.month === 'all' || filters.month === today.slice(5, 7))) {
    return today
  }
  const monthPart = filters.month === 'all' ? today.slice(5, 7) : filters.month
  return `${filters.year}-${monthPart}-01`
}

function openCreateDialog() {
  editingRecordId.value = null
  editingRecordType.value = 'manual'
  editingOriginFactoryId.value = ''
  formError.value = ''
  priceTouched.value = false
  const defaultFac = filters.factoryId !== 'all'
    ? filters.factoryId
    : (factoryOptions.value[0]?.id || 'huaxing')
  manualForm.factory_id = defaultFac
  manualForm.ship_date = defaultManualDate()
  manualForm.customer = filters.customer !== 'all' ? filters.customer : ''
  manualForm.container_no = ''
  manualForm.container_type = '40HQ'
  manualForm.so_no = ''
  manualForm.contract_no = ''
  manualForm.filing_codes = ''
  manualForm.specPreset = SPEC_PRESETS[0].value
  manualForm.customSpec = ''
  manualForm.cartons = '0'
  manualForm.pallets = ''
  manualForm.unit_price = String(SPEC_PRESETS[0].price)
  manualForm.is_container = true
  manualForm.remark = ''
  formOpen.value = true
}

function openEditDialog(row: PalletStatsDetail) {
  if (!row.editable) return
  editingRecordId.value = row.id
  editingRecordType.value = row.recordType
  editingOriginFactoryId.value = row.originFactoryId || row.factoryId
  formError.value = ''
  priceTouched.value = true
  manualForm.factory_id = row.factoryId
  manualForm.ship_date = row.date || todayIsoDate()
  manualForm.customer = row.customer
  manualForm.container_no = row.containerNo === '手动录入' ? '' : row.containerNo
  manualForm.container_type = row.containerType || '40HQ'
  manualForm.so_no = row.soNo
  manualForm.contract_no = row.contractNo
  manualForm.filing_codes = row.filingCodes.join(', ')
  const presetMatch = SPEC_PRESETS.find((item) => item.value === row.spec)
  if (presetMatch) {
    manualForm.specPreset = presetMatch.value
    manualForm.customSpec = ''
  } else {
    manualForm.specPreset = 'custom'
    manualForm.customSpec = row.spec
  }
  manualForm.cartons = String(row.cartons ?? 0)
  manualForm.pallets = String(row.pallets ?? 0)
  manualForm.unit_price = String(row.unitPrice ?? 65)
  manualForm.is_container = row.isContainer
  manualForm.remark = row.remark || ''
  formOpen.value = true
}

function onSpecPresetChange(val: unknown) {
  const next = String(val ?? SPEC_PRESETS[0].value)
  manualForm.specPreset = next
  const preset = SPEC_PRESETS.find((item) => item.value === next)
  if (preset && !priceTouched.value) {
    manualForm.unit_price = String(preset.price)
  }
}

function onContainerTypeChange(val: unknown) {
  const next = String(val ?? '40HQ')
  manualForm.container_type = next
  manualForm.is_container = next !== '散货车' && next !== '其他'
}

async function saveManualRecord() {
  formError.value = ''
  if (!/^\d{4}-\d{2}-\d{2}$/.test(manualForm.ship_date.trim())) {
    formError.value = '请选择有效的出货日期'
    return
  }
  if (!manualForm.customer.trim()) {
    formError.value = '请填写客户名称'
    return
  }
  const palletsNum = Number(manualForm.pallets)
  if (manualForm.pallets === '' || !Number.isFinite(palletsNum) || palletsNum < 0) {
    formError.value = '请填写有效的用板数（大于或等于 0）'
    return
  }
  const cartonsNum = Number(manualForm.cartons || 0)
  if (!Number.isFinite(cartonsNum) || cartonsNum < 0) {
    formError.value = '箱数不能为负数'
    return
  }
  const specText = resolvedSpec.value
  if (!specText) {
    formError.value = '请填写自定义卡板规格名称'
    return
  }
  const priceNum = Number(manualForm.unit_price)
  if (manualForm.unit_price !== '' && (!Number.isFinite(priceNum) || priceNum < 0)) {
    formError.value = '参考单价不能为负数'
    return
  }

  const payload: ManualPalletRecordPayload = {
    factory_id: manualForm.factory_id,
    ship_date: manualForm.ship_date.trim(),
    customer: manualForm.customer.trim(),
    container_no: manualForm.container_no.trim(),
    container_type: manualForm.container_type,
    so_no: manualForm.so_no.trim(),
    contract_no: manualForm.contract_no.trim(),
    filing_codes: manualForm.filing_codes.trim(),
    spec: specText,
    cartons: cartonsNum,
    pallets: palletsNum,
    unit_price: manualForm.unit_price !== '' ? priceNum : undefined,
    is_container: manualForm.is_container,
    remark: manualForm.remark.trim(),
    ...(editingRecordId.value
      ? {
          record_type: editingRecordType.value,
          origin_factory_id: editingOriginFactoryId.value || manualForm.factory_id,
        }
      : {}),
  }

  saving.value = true
  try {
    if (editingRecordId.value) {
      await updateShippingPalletRecord(editingRecordId.value, payload)
      emit('notify', `已更新 ${payload.customer} 的卡板记录`)
    } else {
      await createShippingPalletRecord(payload)
      emit('notify', `已添加 ${payload.ship_date} · ${payload.customer} 卡板记录`)
    }
    formOpen.value = false

    const savedYear = payload.ship_date.slice(0, 4)
    const savedMonth = payload.ship_date.slice(5, 7)
    if (filters.year !== 'all' && filters.year !== savedYear) {
      filters.year = savedYear
      filters.month = savedMonth
    } else if (filters.month !== 'all' && filters.month !== savedMonth) {
      filters.month = savedMonth
    }
    if (filters.factoryId !== 'all' && filters.factoryId !== payload.factory_id) {
      filters.factoryId = payload.factory_id
    }
    if (filters.customer !== 'all' && filters.customer !== payload.customer) {
      filters.customer = 'all'
    }
    drilldownGroup.value = null
    await loadStats()
  } catch (error) {
    formError.value = `保存失败：${getApiErrorMessage(error)}`
  } finally {
    saving.value = false
  }
}

function startEditGroup(group: PalletStatsGroup) {
  errorMessage.value = ''
  editingGroupKey.value = group.key
  groupCostTouched.value = false
  groupDraft.factoryId = group.factoryId
  groupDraft.customer = group.customer
  groupDraft.spec = group.spec
  groupDraft.containerCount = String(group.containerCount ?? 0)
  groupDraft.totalPallets = String(group.totalPallets ?? 0)
  groupDraft.unitPrice = String(group.unitPrice ?? 65)
  groupDraft.estimatedCost = Number(group.estimatedCost ?? 0).toFixed(2)
}

function cancelGroupEdit() {
  editingGroupKey.value = null
  groupCostTouched.value = false
}

function onGroupQtyOrPriceInput() {
  groupCostTouched.value = false
  const qty = Number(groupDraft.totalPallets)
  const price = Number(groupDraft.unitPrice)
  if (Number.isFinite(qty) && Number.isFinite(price) && qty >= 0 && price >= 0) {
    groupDraft.estimatedCost = (Math.round(qty * price * 100) / 100).toFixed(2)
  }
}

function onGroupCostInput() {
  groupCostTouched.value = true
}

async function saveGroupEdit(group: PalletStatsGroup) {
  errorMessage.value = ''
  const customerText = groupDraft.customer.trim()
  const specText = groupDraft.spec.trim()
  if (!customerText) {
    errorMessage.value = '请填写客户名称'
    return
  }
  if (!specText) {
    errorMessage.value = '请填写卡板规格'
    return
  }
  const containerNum = Math.round(Number(groupDraft.containerCount))
  if (!Number.isFinite(containerNum) || containerNum < 0) {
    errorMessage.value = '柜数必须为大于或等于 0 的整数'
    return
  }
  const palletsNum = Number(groupDraft.totalPallets)
  if (!Number.isFinite(palletsNum) || palletsNum < 0) {
    errorMessage.value = '用板数不能为负数'
    return
  }
  const priceNum = Number(groupDraft.unitPrice)
  if (!Number.isFinite(priceNum) || priceNum < 0) {
    errorMessage.value = '参考单价不能为负数'
    return
  }
  const costNum = Number(groupDraft.estimatedCost)
  if (!Number.isFinite(costNum) || costNum < 0) {
    errorMessage.value = '预估费用不能为负数'
    return
  }

  const items = detailsForGroup(group).map((row) => ({
    id: row.id,
    factoryId: row.factoryId,
    originFactoryId: row.originFactoryId || row.factoryId,
    recordType: row.recordType,
  }))
  if (!items.length) {
    errorMessage.value = '未找到该汇总行对应的明细记录'
    return
  }

  const computedCost = Math.round(palletsNum * priceNum * 100) / 100
  const costOverridden = groupCostTouched.value && Math.abs(costNum - computedCost) >= 0.005

  savingGroup.value = true
  try {
    await updateShippingPalletGroup({
      items,
      factory_id: groupDraft.factoryId,
      customer: customerText,
      spec: specText,
      container_count: containerNum,
      total_pallets: palletsNum,
      unit_price: priceNum,
      estimated_cost: costNum,
      cost_overridden: costOverridden,
    })
    editingGroupKey.value = null
    groupCostTouched.value = false
    if (filters.factoryId !== 'all' && filters.factoryId !== groupDraft.factoryId) {
      filters.factoryId = groupDraft.factoryId
    }
    if (filters.customer !== 'all' && filters.customer !== customerText) {
      filters.customer = 'all'
    }
    await loadStats()
    emit('notify', `已更新 ${customerText} 的卡板汇总记录`)
  } catch (error) {
    errorMessage.value = `保存汇总修改失败：${getApiErrorMessage(error)}`
  } finally {
    savingGroup.value = false
  }
}

function openBatchDeleteDialog() {
  if (!selectedItems.value.length) return
  deleteTargets.value = [...selectedItems.value]
  deleteDialogOpen.value = true
}

function confirmSingleDelete(row: PalletStatsDetail) {
  deleteTargets.value = [{
    id: row.id,
    factoryId: row.factoryId,
    originFactoryId: row.originFactoryId || row.factoryId,
    recordType: row.recordType,
  }]
  deleteDialogOpen.value = true
}

async function confirmDeleteExecution() {
  if (!deleteTargets.value.length) return
  deleting.value = true
  errorMessage.value = ''
  try {
    const result = await batchDeleteShippingPalletRecords(deleteTargets.value)
    const removedKeys = new Set(
      deleteTargets.value.map((item) => selectionKey(item)),
    )
    selectedKeys.value = selectedKeys.value.filter((key) => !removedKeys.has(key))
    deleteDialogOpen.value = false
    deleteTargets.value = []
    await loadStats()
    emit('notify', `已移除 ${result.totalRemoved} 条卡板记录`)
  } catch (error) {
    errorMessage.value = `删除卡板记录失败：${getApiErrorMessage(error)}`
    deleteDialogOpen.value = false
  } finally {
    deleting.value = false
  }
}

async function handleRestoreExcluded() {
  restoring.value = true
  errorMessage.value = ''
  try {
    const res = await restoreExcludedShippingPalletRecords(filters.factoryId || 'all')
    await loadStats()
    emit('notify', `已恢复 ${res.restoredCount} 条已隐藏的单据记录`)
  } catch (error) {
    errorMessage.value = `恢复单据失败：${getApiErrorMessage(error)}`
  } finally {
    restoring.value = false
  }
}

async function handleExportExcel() {
  exporting.value = true
  errorMessage.value = ''
  try {
    const blob = await exportShippingPalletStats(queryParams())
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    if (filters.year === 'all') {
      link.download = '卡板对账_全部.xlsx'
    } else if (filters.month === 'all') {
      link.download = `卡板年度对账_${filters.year}全年.xlsx`
    } else {
      link.download = `卡板月度对账_${filters.year}-${filters.month}.xlsx`
    }
    link.click()
    URL.revokeObjectURL(url)
    emit('notify', `已导出 ${link.download}`)
  } catch (error) {
    errorMessage.value = `导出月度对账 Excel 失败：${getApiErrorMessage(error)}`
  } finally {
    exporting.value = false
  }
}

watch(() => props.factoryId, (nextFactory) => {
  if (!nextFactory || nextFactory === filters.factoryId) return
  filters.factoryId = nextFactory
  editingGroupKey.value = null
  drilldownGroup.value = null
  selectedKeys.value = []
  void loadStats()
})

onMounted(() => {
  void loadStats()
})

onBeforeUnmount(() => {
  if (searchTimer) {
    clearTimeout(searchTimer)
    searchTimer = null
  }
})
</script>

<template>
  <section class="space-y-6" aria-label="卡板统计">
    <datalist id="pallet-customer-datalist">
      <option v-for="cust in customerSuggestions" :key="cust" :value="cust" />
    </datalist>
    <datalist id="pallet-spec-datalist">
      <option v-for="preset in SPEC_PRESETS" :key="preset.value" :value="preset.value" />
    </datalist>

    <header class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h2 class="text-[18px] font-semibold tracking-[-0.02em] text-foreground">卡板统计</h2>
        <p class="mt-1 text-sm text-muted-foreground">
          按年份与月份保留各厂区、客户的用板与柜号统计记录，支持手动补录、多条件检索、勾选清理与对账单导出。
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <span v-if="lastUpdated" class="text-xs tabular-nums text-muted-foreground">更新于 {{ lastUpdated }}</span>
        <Button variant="outline" size="sm" :disabled="loading" @click="loadStats">
          <RefreshCw class="size-3.5" :class="loading ? 'animate-spin' : ''" aria-hidden="true" />
          刷新
        </Button>
        <Button variant="default" size="sm" :disabled="exporting || loading" @click="handleExportExcel">
          <Download class="size-3.5" aria-hidden="true" />
          {{ exporting ? '正在导出…' : '导出月度对账 Excel' }}
        </Button>
      </div>
    </header>

    <!-- 筛选栏（L2 玻璃工具条） -->
    <div class="glass-chrome rounded-xl border border-border/80 p-4 shadow-elevation-2">
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-12">
        <div class="space-y-1.5 lg:col-span-4">
          <div class="flex items-center justify-between">
            <Label class="text-xs font-medium text-muted-foreground">年月</Label>
            <button
              type="button"
              class="text-xs font-medium text-primary transition-opacity duration-[var(--motion-duration-fast)] hover:opacity-80"
              @click="togglePeriodQuick"
            >
              {{ isCurrentMonthSelected ? '全部年份' : '回到本月' }}
            </button>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <Select :model-value="filters.year" @update:model-value="onYearSelect">
              <SelectTrigger size="sm" aria-label="年份">
                <SelectValue placeholder="选择年份" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部年份</SelectItem>
                <SelectItem v-for="y in yearOptions" :key="y" :value="y">
                  {{ y }}年
                </SelectItem>
              </SelectContent>
            </Select>

            <Select :model-value="filters.month" @update:model-value="onMonthSelect">
              <SelectTrigger size="sm" aria-label="月份">
                <SelectValue placeholder="选择月份" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全年</SelectItem>
                <SelectItem v-for="m in MONTH_OPTIONS" :key="m.value" :value="m.value">
                  {{ m.label }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div class="space-y-1.5 lg:col-span-3">
          <Label class="text-xs font-medium text-muted-foreground">厂区</Label>
          <Select v-model="filters.factoryId" @update:model-value="onFilterChange">
            <SelectTrigger size="sm" aria-label="厂区">
              <SelectValue placeholder="选择厂区" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-if="factoryOptions.length > 1" value="all">全部厂区</SelectItem>
              <SelectItem v-for="fac in factoryOptions" :key="fac.id" :value="fac.id">
                {{ fac.name }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div class="space-y-1.5 lg:col-span-3">
          <Label class="text-xs font-medium text-muted-foreground">客户</Label>
          <Select v-model="filters.customer" @update:model-value="onFilterChange">
            <SelectTrigger size="sm" aria-label="客户">
              <SelectValue placeholder="全部客户" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部客户</SelectItem>
              <SelectItem v-for="cust in customerOptions" :key="cust" :value="cust">
                {{ cust }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div class="space-y-1.5 lg:col-span-2">
          <Label for="pallet-unit-price" class="text-xs font-medium text-muted-foreground">参考单价（元 / 块）</Label>
          <Input
            id="pallet-unit-price"
            v-model="filters.unitPriceInput"
            type="number"
            min="0"
            step="5"
            size="sm"
            placeholder="按规格默认"
            aria-label="自定义卡板单价"
            @change="onFilterChange"
          />
        </div>
      </div>
    </div>

    <div
      v-if="errorMessage"
      role="alert"
      class="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
    >
      <span>{{ errorMessage }}</span>
      <Button variant="outline" size="xs" @click="loadStats">重试</Button>
    </div>

    <!-- 顶部汇总卡片（L1 实色卡片） -->
    <div v-if="loading && !stats" class="grid gap-4 md:grid-cols-3" aria-label="卡板汇总加载中">
      <div v-for="n in 3" :key="n" class="rounded-2xl border border-border/80 bg-card p-5 shadow-elevation-1">
        <div class="skeleton-shimmer h-4 w-24 rounded bg-muted" />
        <div class="skeleton-shimmer mt-4 h-8 w-32 rounded bg-muted" />
        <div class="skeleton-shimmer mt-3 h-3 w-28 rounded bg-muted" />
      </div>
    </div>

    <div v-else class="grid gap-4 md:grid-cols-3">
      <article class="rounded-2xl border border-border/80 bg-card p-5 shadow-elevation-1 transition-[transform,box-shadow] duration-[var(--motion-duration-fast)] ease-spring-snappy hover:-translate-y-0.5 hover:shadow-elevation-2">
        <div class="flex items-center justify-between gap-2">
          <p class="text-[13px] font-medium text-muted-foreground">{{ kpiPalletTitle }}</p>
          <span class="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Package class="size-4" aria-hidden="true" />
          </span>
        </div>
        <div class="mt-3 flex items-baseline gap-1.5">
          <span class="text-3xl font-semibold tracking-tight tabular-nums text-foreground">{{ summary.totalPallets }}</span>
          <span class="text-sm text-muted-foreground">块</span>
        </div>
        <p class="mt-2 text-xs text-muted-foreground">{{ periodLabel }} · 涉及 {{ summary.customerCount }} 位客户</p>
      </article>

      <article class="rounded-2xl border border-border/80 bg-card p-5 shadow-elevation-1 transition-[transform,box-shadow] duration-[var(--motion-duration-fast)] ease-spring-snappy hover:-translate-y-0.5 hover:shadow-elevation-2">
        <div class="flex items-center justify-between gap-2">
          <p class="text-[13px] font-medium text-muted-foreground">总柜数</p>
          <span class="flex size-8 items-center justify-center rounded-lg bg-secondary text-secondary-foreground">
            <Ship class="size-4" aria-hidden="true" />
          </span>
        </div>
        <div class="mt-3 flex items-baseline gap-1.5">
          <span class="text-3xl font-semibold tracking-tight tabular-nums text-foreground">{{ summary.totalContainers }}</span>
          <span class="text-sm text-muted-foreground">柜</span>
        </div>
        <p class="mt-2 text-xs text-muted-foreground">共 {{ summary.recordCount }} 笔出货统计记录</p>
      </article>

      <article class="rounded-2xl border border-border/80 bg-card p-5 shadow-elevation-1 transition-[transform,box-shadow] duration-[var(--motion-duration-fast)] ease-spring-snappy hover:-translate-y-0.5 hover:shadow-elevation-2">
        <div class="flex items-center justify-between gap-2">
          <p class="text-[13px] font-medium text-muted-foreground">预估卡板总费用</p>
          <span class="flex size-8 items-center justify-center rounded-lg bg-accent text-accent-foreground">
            <Coins class="size-4" aria-hidden="true" />
          </span>
        </div>
        <div class="mt-3 flex items-baseline gap-1">
          <span class="text-base font-medium text-muted-foreground">¥</span>
          <span class="text-3xl font-semibold tracking-tight tabular-nums text-foreground">{{ formatCurrency(summary.estimatedCost) }}</span>
        </div>
        <p class="mt-2 text-xs text-muted-foreground">
          {{ filters.unitPriceInput ? `按单价 ¥${filters.unitPriceInput}/块 估算` : '按规格标准单价自动核算' }}
        </p>
      </article>
    </div>

    <!-- 下方双视图 + 操作栏 -->
    <Tabs v-model="activeTab" class="space-y-4">
      <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div class="flex flex-wrap items-center gap-2.5">
          <TabsList>
            <TabsTrigger value="summary">
              <Layers class="size-3.5" aria-hidden="true" />
              按客户 / 规格汇总（{{ groups.length }}）
            </TabsTrigger>
            <TabsTrigger value="details">
              柜号明细（{{ visibleDetails.length }}）
            </TabsTrigger>
          </TabsList>

          <Button variant="outline" size="sm" @click="openCreateDialog">
            <Plus class="size-3.5" aria-hidden="true" />
            添加卡板
          </Button>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <div class="relative w-full sm:w-64">
            <Search
              class="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              v-model="searchInput"
              size="sm"
              class="pr-7 pl-8"
              placeholder="搜索客户 / 柜号 / SO / 合同号 / 规格"
              aria-label="搜索卡板记录"
              @keydown.enter="applySearchNow"
            />
            <button
              v-if="searchInput"
              type="button"
              aria-label="清空搜索"
              class="absolute top-1/2 right-2 -translate-y-1/2 rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
              @click="clearSearch"
            >
              <X class="size-3.5" aria-hidden="true" />
            </button>
          </div>

          <Button
            v-if="(stats?.excludedCount ?? 0) > 0"
            variant="ghost"
            size="xs"
            :disabled="restoring"
            @click="handleRestoreExcluded"
          >
            <RotateCw class="size-3" :class="restoring ? 'animate-spin' : ''" aria-hidden="true" />
            恢复隐藏单据（{{ stats?.excludedCount }}）
          </Button>

          <Button
            variant="outline"
            size="sm"
            :disabled="selectedItems.length === 0 || deleting"
            :class="selectedItems.length > 0 ? 'border-destructive/40 text-destructive hover:bg-destructive/10' : ''"
            @click="openBatchDeleteDialog"
          >
            <Trash2 class="size-3.5" aria-hidden="true" />
            删除选中{{ selectedItems.length ? `（${selectedItems.length}）` : '' }}
          </Button>
        </div>
      </div>

      <TabsContent value="summary" class="mt-0">
        <div class="overflow-hidden rounded-2xl border border-border/80 bg-card shadow-elevation-1">
          <div v-if="groups.length" class="overflow-x-auto">
            <table class="w-full min-w-[980px] text-left text-sm">
              <thead class="border-b border-border/80 bg-muted/40 text-xs font-semibold text-muted-foreground">
                <tr>
                  <th class="w-10 px-3 py-3 text-center" @click.stop>
                    <Checkbox
                      aria-label="全选汇总记录"
                      :disabled="!summaryGroupKeys.length"
                      :model-value="summarySelectAllState"
                      @update:model-value="toggleAllSummary"
                    />
                  </th>
                  <th class="px-4 py-3">客户</th>
                  <th class="px-4 py-3">厂区</th>
                  <th class="px-4 py-3">卡板规格</th>
                  <th class="px-4 py-3 text-right">柜数</th>
                  <th class="px-4 py-3 text-right">用板数（块）</th>
                  <th class="px-4 py-3 text-right">参考单价（元）</th>
                  <th class="px-4 py-3 text-right">预估费用（元）</th>
                  <th class="px-4 py-3 text-right">操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-border/60">
                <tr
                  v-for="group in groups"
                  :key="group.key"
                  :class="
                    editingGroupKey === group.key
                      ? 'bg-primary/[0.04]'
                      : 'cursor-pointer transition-colors duration-[var(--motion-duration-instant)] hover:bg-accent/40'
                  "
                  @click="editingGroupKey === group.key ? undefined : drillDown(group)"
                  @dblclick.stop="startEditGroup(group)"
                >
                  <td class="px-3 py-3 text-center" @click.stop>
                    <Checkbox
                      :aria-label="`选择 ${group.customer} 全部记录`"
                      :model-value="groupSelectionState(group)"
                      @update:model-value="(v) => toggleGroupSelection(group, v)"
                    />
                  </td>

                  <template v-if="editingGroupKey === group.key">
                    <td class="px-3 py-2" @click.stop>
                      <Input
                        v-model="groupDraft.customer"
                        size="sm"
                        list="pallet-customer-datalist"
                        aria-label="编辑汇总客户"
                        class="h-8 min-w-[110px]"
                        @keydown.enter="saveGroupEdit(group)"
                        @keydown.esc="cancelGroupEdit"
                      />
                    </td>
                    <td class="px-3 py-2" @click.stop>
                      <Select v-model="groupDraft.factoryId">
                        <SelectTrigger size="sm" aria-label="编辑汇总厂区" class="h-8 min-w-[92px]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem v-for="fac in factoryOptions" :key="fac.id" :value="fac.id">
                            {{ fac.name }}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </td>
                    <td class="px-3 py-2" @click.stop>
                      <Input
                        v-model="groupDraft.spec"
                        size="sm"
                        list="pallet-spec-datalist"
                        aria-label="编辑汇总卡板规格"
                        class="h-8 min-w-[175px]"
                        @keydown.enter="saveGroupEdit(group)"
                        @keydown.esc="cancelGroupEdit"
                      />
                    </td>
                    <td class="px-3 py-2" @click.stop>
                      <Input
                        v-model="groupDraft.containerCount"
                        type="number"
                        min="0"
                        step="1"
                        size="sm"
                        aria-label="编辑汇总柜数"
                        class="ml-auto h-8 w-20 text-right tabular-nums"
                        @keydown.enter="saveGroupEdit(group)"
                        @keydown.esc="cancelGroupEdit"
                      />
                    </td>
                    <td class="px-3 py-2" @click.stop>
                      <Input
                        v-model="groupDraft.totalPallets"
                        type="number"
                        min="0"
                        step="0.5"
                        size="sm"
                        aria-label="编辑汇总用板数"
                        class="ml-auto h-8 w-24 text-right tabular-nums"
                        @input="onGroupQtyOrPriceInput"
                        @keydown.enter="saveGroupEdit(group)"
                        @keydown.esc="cancelGroupEdit"
                      />
                    </td>
                    <td class="px-3 py-2" @click.stop>
                      <Input
                        v-model="groupDraft.unitPrice"
                        type="number"
                        min="0"
                        step="5"
                        size="sm"
                        aria-label="编辑汇总参考单价"
                        class="ml-auto h-8 w-24 text-right tabular-nums"
                        @input="onGroupQtyOrPriceInput"
                        @keydown.enter="saveGroupEdit(group)"
                        @keydown.esc="cancelGroupEdit"
                      />
                    </td>
                    <td class="px-3 py-2" @click.stop>
                      <Input
                        v-model="groupDraft.estimatedCost"
                        type="number"
                        min="0"
                        step="0.01"
                        size="sm"
                        aria-label="编辑汇总预估费用"
                        class="ml-auto h-8 w-28 text-right tabular-nums"
                        @input="onGroupCostInput"
                        @keydown.enter="saveGroupEdit(group)"
                        @keydown.esc="cancelGroupEdit"
                      />
                    </td>
                    <td class="px-3 py-2 text-right whitespace-nowrap" @click.stop>
                      <div class="inline-flex items-center justify-end gap-1">
                        <Button
                          variant="outline"
                          size="xs"
                          class="border-primary/40 text-primary hover:bg-primary/10"
                          :disabled="savingGroup"
                          :aria-label="`保存 ${group.customer} 汇总修改`"
                          @click.stop="saveGroupEdit(group)"
                        >
                          <Check class="size-3.5" aria-hidden="true" />
                          {{ savingGroup ? '保存中…' : '保存' }}
                        </Button>
                        <Button
                          variant="ghost"
                          size="xs"
                          :disabled="savingGroup"
                          @click.stop="cancelGroupEdit"
                        >
                          取消
                        </Button>
                      </div>
                    </td>
                  </template>

                  <template v-else>
                    <td class="px-4 py-3 font-medium text-foreground">{{ group.customer }}</td>
                    <td class="px-4 py-3 text-muted-foreground">{{ group.factoryName }}</td>
                    <td class="px-4 py-3 text-foreground/90">{{ group.spec }}</td>
                    <td class="px-4 py-3 text-right tabular-nums text-foreground">{{ group.containerCount }}</td>
                    <td class="px-4 py-3 text-right font-semibold tabular-nums text-primary">{{ group.totalPallets }}</td>
                    <td class="px-4 py-3 text-right tabular-nums text-muted-foreground">{{ formatCurrency(group.unitPrice) }}</td>
                    <td class="px-4 py-3 text-right font-semibold tabular-nums text-foreground">¥{{ formatCurrency(group.estimatedCost) }}</td>
                    <td class="px-4 py-3 text-right whitespace-nowrap">
                      <div class="inline-flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="xs"
                          :aria-label="`编辑 ${group.customer} 汇总`"
                          @click.stop="startEditGroup(group)"
                        >
                          <Pencil class="size-3.5" aria-hidden="true" />
                          编辑
                        </Button>
                        <Button
                          variant="ghost"
                          size="xs"
                          :aria-label="`查看 ${group.customer} 柜号明细`"
                          @click.stop="drillDown(group)"
                        >
                          查看明细
                          <ArrowUpRight class="size-3.5" aria-hidden="true" />
                        </Button>
                      </div>
                    </td>
                  </template>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
            <span class="flex size-11 items-center justify-center rounded-xl bg-muted text-muted-foreground">
              <Package class="size-5" aria-hidden="true" />
            </span>
            <div>
              <p class="text-sm font-medium text-foreground">当前筛选条件下暂无卡板统计数据</p>
              <p class="mt-1 text-xs text-muted-foreground">可切换其他年份 / 月份、清空搜索关键词，或点击「添加卡板」直接补录。</p>
            </div>
            <div class="flex flex-wrap items-center justify-center gap-2">
              <Button variant="outline" size="sm" @click="openCreateDialog">
                <Plus class="size-3.5" aria-hidden="true" />
                添加卡板
              </Button>
              <Button variant="ghost" size="sm" @click="resetFilters">
                <RotateCcw class="size-3.5" aria-hidden="true" />
                重置筛选
              </Button>
            </div>
          </div>
        </div>
      </TabsContent>

      <TabsContent value="details" class="mt-0 space-y-3">
        <div
          v-if="drilldownGroup"
          class="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-primary/20 bg-primary/5 px-4 py-2.5"
        >
          <div class="flex flex-wrap items-center gap-2">
            <StatusPill tone="teal" :label="`下钻：${drilldownGroup.customer}`" />
            <span class="text-xs text-muted-foreground">
              {{ drilldownGroup.factoryName }} · {{ drilldownGroup.spec }} · 共 {{ visibleDetails.length }} 笔
            </span>
          </div>
          <div class="flex items-center gap-2">
            <Button variant="outline" size="xs" @click="clearDrilldown">查看全部明细</Button>
            <Button variant="ghost" size="xs" @click="backToSummary">
              <ArrowLeft class="size-3.5" aria-hidden="true" />
              返回汇总表
            </Button>
          </div>
        </div>

        <div class="overflow-hidden rounded-2xl border border-border/80 bg-card shadow-elevation-1">
          <div v-if="visibleDetails.length" class="overflow-x-auto">
            <table class="w-full min-w-[1260px] text-left text-sm">
              <thead class="border-b border-border/80 bg-muted/40 text-xs font-semibold text-muted-foreground">
                <tr>
                  <th class="w-10 px-3 py-3 text-center">
                    <Checkbox
                      aria-label="全选明细记录"
                      :disabled="!visibleDetails.length"
                      :model-value="detailsSelectAllState"
                      @update:model-value="toggleAllDetails"
                    />
                  </th>
                  <th class="px-3.5 py-3">出货日期</th>
                  <th class="px-3.5 py-3">厂区</th>
                  <th class="px-3.5 py-3">客户</th>
                  <th class="px-3.5 py-3">柜号 / 车次</th>
                  <th class="px-3.5 py-3">柜型</th>
                  <th class="px-3.5 py-3">SO号</th>
                  <th class="px-3.5 py-3">合同号</th>
                  <th class="px-3.5 py-3">备案货号</th>
                  <th class="px-3.5 py-3">卡板规格</th>
                  <th class="px-3.5 py-3 text-right">箱数</th>
                  <th class="px-3.5 py-3 text-right">用板数（块）</th>
                  <th class="px-3.5 py-3 text-right">预估费用（元）</th>
                  <th class="px-3.5 py-3">来源</th>
                  <th class="px-3.5 py-3 text-right">操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-border/60">
                <tr
                  v-for="row in visibleDetails"
                  :key="selectionKey(row)"
                  class="transition-colors duration-[var(--motion-duration-instant)] hover:bg-accent/40"
                >
                  <td class="px-3 py-3 text-center" @click.stop>
                    <Checkbox
                      :aria-label="`选择 ${row.customer} ${row.containerNo}`"
                      :model-value="selectedKeySet.has(selectionKey(row))"
                      @update:model-value="(v) => toggleDetailSelection(row, v)"
                    />
                  </td>
                  <td class="px-3.5 py-3 tabular-nums text-muted-foreground">{{ row.date || '—' }}</td>
                  <td class="px-3.5 py-3 text-foreground/90">{{ row.factoryName }}</td>
                  <td class="px-3.5 py-3 font-medium text-foreground">{{ row.customer }}</td>
                  <td class="px-3.5 py-3 font-medium tabular-nums text-foreground">{{ row.containerNo || '—' }}</td>
                  <td class="px-3.5 py-3 text-muted-foreground">{{ row.containerType || '—' }}</td>
                  <td class="px-3.5 py-3 tabular-nums text-muted-foreground">{{ row.soNo || '—' }}</td>
                  <td class="px-3.5 py-3 tabular-nums text-muted-foreground">{{ row.contractNo || '—' }}</td>
                  <td class="max-w-[180px] break-all px-3.5 py-3 tabular-nums text-muted-foreground">
                    {{ row.filingCodes.length ? row.filingCodes.join(', ') : '—' }}
                  </td>
                  <td class="px-3.5 py-3 text-foreground/90">{{ row.spec }}</td>
                  <td class="px-3.5 py-3 text-right tabular-nums text-muted-foreground">{{ row.cartons }}</td>
                  <td class="px-3.5 py-3 text-right font-semibold tabular-nums text-primary">{{ row.pallets }}</td>
                  <td class="px-3.5 py-3 text-right font-semibold tabular-nums text-foreground">¥{{ formatCurrency(row.estimatedCost) }}</td>
                  <td class="px-3.5 py-3">
                    <StatusPill compact :tone="sourceTone(row.source)" :label="row.source" />
                    <p
                      v-if="row.remark"
                      class="mt-1 max-w-[140px] truncate text-xs text-muted-foreground"
                      :title="row.remark"
                    >
                      {{ row.remark }}
                    </p>
                  </td>
                  <td class="px-3.5 py-3 text-right">
                    <div class="inline-flex items-center justify-end gap-1">
                      <Button
                        v-if="row.editable"
                        variant="ghost"
                        size="xs"
                        :aria-label="`编辑 ${row.customer} 卡板记录`"
                        @click="openEditDialog(row)"
                      >
                        <Pencil class="size-3.5" aria-hidden="true" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="xs"
                        class="text-destructive hover:bg-destructive/10 hover:text-destructive"
                        :aria-label="`删除 ${row.customer} ${row.containerNo}`"
                        @click="confirmSingleDelete(row)"
                      >
                        <Trash2 class="size-3.5" aria-hidden="true" />
                      </Button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
            <span class="flex size-11 items-center justify-center rounded-xl bg-muted text-muted-foreground">
              <Package class="size-5" aria-hidden="true" />
            </span>
            <div>
              <p class="text-sm font-medium text-foreground">暂无对应的柜号明细记录</p>
              <p class="mt-1 text-xs text-muted-foreground">可返回汇总表切换分类、添加卡板记录，或点击重置筛选查看更多出货数据。</p>
            </div>
            <div class="flex flex-wrap items-center justify-center gap-2">
              <Button variant="outline" size="sm" @click="openCreateDialog">
                <Plus class="size-3.5" aria-hidden="true" />
                添加卡板
              </Button>
              <Button variant="ghost" size="sm" @click="backToSummary">返回汇总表</Button>
            </div>
          </div>
        </div>
      </TabsContent>
    </Tabs>

    <!-- 添加 / 编辑卡板弹窗 -->
    <Dialog v-model:open="formOpen">
      <DialogContent class="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {{ editingRecordId ? (editingRecordType === 'manual' ? '编辑手动卡板记录' : '调整出货卡板记录') : '添加卡板记录' }}
          </DialogTitle>
          <DialogDescription>
            {{
              editingRecordId && editingRecordType !== 'manual'
                ? '调整结果仅保存于卡板统计与月度对账单中，不会改动原始柜货单 / 补料单 / 车货单源文件。'
                : '手动补录或调整的卡板记录将按年份长期保存在对应厂区数据库中，并与柜货单 / 补料单统一计入统计和 Excel 对账。'
            }}
          </DialogDescription>
        </DialogHeader>

        <div class="grid max-h-[65dvh] gap-4 overflow-y-auto py-1 pr-1 sm:grid-cols-2">
          <div class="space-y-1.5">
            <Label for="manual-ship-date" class="text-xs font-medium text-muted-foreground">出货日期 *</Label>
            <Input
              id="manual-ship-date"
              v-model="manualForm.ship_date"
              type="date"
              size="sm"
              aria-label="出货日期"
            />
          </div>

          <div class="space-y-1.5">
            <Label class="text-xs font-medium text-muted-foreground">厂区 *</Label>
            <Select v-model="manualForm.factory_id">
              <SelectTrigger size="sm" aria-label="记录所属厂区">
                <SelectValue placeholder="选择厂区" />
              </SelectTrigger>
              <SelectContent class="z-[60]">
                <SelectItem v-for="fac in factoryOptions" :key="fac.id" :value="fac.id">
                  {{ fac.name }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div class="space-y-1.5">
            <Label for="manual-customer" class="text-xs font-medium text-muted-foreground">客户 *</Label>
            <Input
              id="manual-customer"
              v-model="manualForm.customer"
              size="sm"
              list="pallet-customer-datalist"
              placeholder="输入客户名称（如 ROSS / SIMBA）"
              aria-label="客户名称"
            />
          </div>

          <div class="space-y-1.5">
            <Label for="manual-pallets" class="text-xs font-medium text-muted-foreground">用板数（块） *</Label>
            <Input
              id="manual-pallets"
              v-model="manualForm.pallets"
              type="number"
              min="0"
              step="0.5"
              size="sm"
              placeholder="输入卡板数量"
              aria-label="用板数"
            />
          </div>

          <div class="space-y-1.5">
            <Label class="text-xs font-medium text-muted-foreground">卡板规格</Label>
            <Select :model-value="manualForm.specPreset" @update:model-value="onSpecPresetChange">
              <SelectTrigger size="sm" aria-label="卡板规格">
                <SelectValue placeholder="选择卡板规格" />
              </SelectTrigger>
              <SelectContent class="z-[60]">
                <SelectItem v-for="preset in SPEC_PRESETS" :key="preset.value" :value="preset.value">
                  {{ preset.value }}
                </SelectItem>
                <SelectItem value="custom">自定义规格</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div class="space-y-1.5">
            <Label for="manual-unit-price" class="text-xs font-medium text-muted-foreground">参考单价（元 / 块）</Label>
            <Input
              id="manual-unit-price"
              v-model="manualForm.unit_price"
              type="number"
              min="0"
              step="5"
              size="sm"
              aria-label="记录单价"
              @input="priceTouched = true"
            />
          </div>

          <div v-if="manualForm.specPreset === 'custom'" class="space-y-1.5 sm:col-span-2">
            <Label for="manual-custom-spec" class="text-xs font-medium text-muted-foreground">自定义规格名称 *</Label>
            <Input
              id="manual-custom-spec"
              v-model="manualForm.customSpec"
              size="sm"
              placeholder="如：胶合板免熏蒸卡板 (1200×800)"
              aria-label="自定义规格名称"
            />
          </div>

          <div class="space-y-1.5">
            <Label for="manual-container-no" class="text-xs font-medium text-muted-foreground">柜号 / 车次</Label>
            <Input
              id="manual-container-no"
              v-model="manualForm.container_no"
              size="sm"
              placeholder="如：MSKU1234567"
              aria-label="柜号或车次"
            />
          </div>

          <div class="space-y-1.5">
            <Label class="text-xs font-medium text-muted-foreground">柜型 / 车型</Label>
            <Select :model-value="manualForm.container_type" @update:model-value="onContainerTypeChange">
              <SelectTrigger size="sm" aria-label="柜型或车型">
                <SelectValue placeholder="选择柜型" />
              </SelectTrigger>
              <SelectContent class="z-[60]">
                <SelectItem v-for="ct in CONTAINER_TYPE_OPTIONS" :key="ct" :value="ct">
                  {{ ct }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div class="space-y-1.5">
            <Label for="manual-so-no" class="text-xs font-medium text-muted-foreground">SO号</Label>
            <Input
              id="manual-so-no"
              v-model="manualForm.so_no"
              size="sm"
              placeholder="选填"
              aria-label="SO号"
            />
          </div>

          <div class="space-y-1.5">
            <Label for="manual-contract-no" class="text-xs font-medium text-muted-foreground">合同号</Label>
            <Input
              id="manual-contract-no"
              v-model="manualForm.contract_no"
              size="sm"
              placeholder="选填"
              aria-label="合同号"
            />
          </div>

          <div class="space-y-1.5">
            <Label for="manual-filing-codes" class="text-xs font-medium text-muted-foreground">备案货号</Label>
            <Input
              id="manual-filing-codes"
              v-model="manualForm.filing_codes"
              size="sm"
              placeholder="多个货号用逗号分隔"
              aria-label="备案货号"
            />
          </div>

          <div class="space-y-1.5">
            <Label for="manual-cartons" class="text-xs font-medium text-muted-foreground">箱数</Label>
            <Input
              id="manual-cartons"
              v-model="manualForm.cartons"
              type="number"
              min="0"
              step="1"
              size="sm"
              aria-label="箱数"
            />
          </div>

          <div class="flex items-center gap-2.5 sm:col-span-2">
            <Checkbox
              id="manual-is-container"
              :model-value="manualForm.is_container"
              @update:model-value="(v) => { manualForm.is_container = v === true }"
            />
            <Label for="manual-is-container" class="cursor-pointer text-xs text-muted-foreground">
              计入「总柜数」统计（取消勾选则仅统计用板数与预估费用，例如散货补卡板）
            </Label>
          </div>

          <div class="space-y-1.5 sm:col-span-2">
            <Label for="manual-remark" class="text-xs font-medium text-muted-foreground">备注</Label>
            <Input
              id="manual-remark"
              v-model="manualForm.remark"
              size="sm"
              placeholder="选填：换板原因、客户特殊包装说明等"
              aria-label="卡板备注"
            />
          </div>
        </div>

        <p
          v-if="formError"
          role="alert"
          class="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive"
        >
          {{ formError }}
        </p>

        <DialogFooter class="flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p class="text-xs text-muted-foreground">
            预估费用：
            <span class="font-semibold tabular-nums text-foreground">¥{{ formatCurrency(previewManualCost) }}</span>
          </p>
          <div class="flex items-center justify-end gap-2">
            <Button variant="outline" size="sm" :disabled="saving" @click="formOpen = false">取消</Button>
            <Button variant="default" size="sm" :disabled="saving" @click="saveManualRecord">
              {{ saving ? '正在保存…' : (editingRecordId ? '保存修改' : '保存记录') }}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- 批量 / 单条删除确认弹窗 -->
    <Dialog v-model:open="deleteDialogOpen">
      <DialogContent class="max-w-md">
        <DialogHeader>
          <DialogTitle>确认移除所选卡板记录</DialogTitle>
          <DialogDescription>
            已选中 {{ deleteTargets.length }} 条记录。
            <span v-if="deleteBreakdown.manualCount">
              其中 {{ deleteBreakdown.manualCount }} 条「手动录入」记录将被永久删除；
            </span>
            <span v-if="deleteBreakdown.syncCount">
              {{ deleteBreakdown.syncCount }} 条同步自柜货单 / 补料单 / 车货单的记录将仅从「卡板统计」中隐藏，不会删除原始出货单据，可随时点击「恢复隐藏单据」还原。
            </span>
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" size="sm" :disabled="deleting" @click="deleteDialogOpen = false">取消</Button>
          <Button variant="destructive" size="sm" :disabled="deleting" @click="confirmDeleteExecution">
            {{ deleting ? '正在删除…' : '确认删除' }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch, watchEffect, type Component } from 'vue'
import {
  AlertTriangle,
  ArrowLeft,
  Boxes,
  Building2,
  CheckCircle2,
  ClipboardCheck,
  GitBranch,
  Package,
  PackageCheck,
  Plus,
  RotateCcw,
  Search,
  Table2,
  X,
} from '@lucide/vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  getFactoryScopedRoute,
  isProductionFactoryContextId,
  type ProductionFactoryContextId,
  type Tone,
} from '@/data/enterpriseMock'
import { rawMaterialApi, type RawMaterialResponse } from '@/api/rawMaterial'
import { getApiErrorMessage } from '@/lib/http'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

type RawMaterialTab = 'material' | 'requisition' | 'batch' | 'movement'
type MaterialStatus = '启用' | '停用'
type RequisitionStatus = '待出库' | '已出库'
type MovementType = '入库' | '出库' | '撤回'

interface RawMaterialTabItem {
  id: RawMaterialTab
  label: string
  description: string
  icon: Component
}

interface RawMaterialRow {
  id: string
  rowNumber: number
  code: string
  name: string
  spec: string
  category: string
  unit: string
  supplier: string
  unitPriceHkdPerLb: number | null
  safetyStockKg: number | null
  currentStockKg: number | null
  status: MaterialStatus
  notes: string
}

interface MaterialFormState {
  materialCode: string
  materialName: string
  category: string
  spec: string
  unit: string
  supplier: string
  safetyStockKg: string | number
  unitPriceHkdPerLb: string | number
  notes: string
  status: MaterialStatus
}

interface RequisitionRow {
  factoryId: ProductionFactoryContextId
  reqNumber: string
  date: string
  orderId: string
  material: string
  requestedWeightKg: number
  applicant: string
  status: RequisitionStatus
  issuedAt: string
}

interface InventoryBatchRow {
  factoryId: ProductionFactoryContextId
  batchNo: string
  material: string
  location: string
  inboundDate: string
  initialWeightKg: number
  availableWeightKg: number
}

interface InventoryMovementRow {
  factoryId: ProductionFactoryContextId
  time: string
  type: MovementType
  material: string
  batchNo: string
  quantityKg: number
  afterWeightKg: number
  sourceDocument: string
  actor: string
}

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const authStore = useAuthStore()

const rawMaterialTabs: RawMaterialTabItem[] = [
  { id: 'material', label: '原料资料', description: '物料主数据', icon: Table2 },
  { id: 'requisition', label: '仓库领料单', description: '待出库与已出库', icon: ClipboardCheck },
  { id: 'batch', label: '库存批次', description: '批号与库位', icon: Boxes },
  { id: 'movement', label: '库存流水', description: '出入库记录', icon: GitBranch },
]
const requisitionStatusFilters: Array<'全部' | RequisitionStatus> = ['全部', '待出库', '已出库']
const movementTypeFilters: Array<'全部' | MovementType> = ['全部', '入库', '出库', '撤回']
const materialStatusFilters: Array<'全部状态' | MaterialStatus> = ['全部状态', '启用', '停用']

const rawMaterialRows = reactive<RawMaterialRow[]>([])
const rawMaterialPageSize = 10
const isSavingMaterial = ref(false)
const materialFormError = ref('')
const editingMaterialId = ref<string | null>(null)
const materialForm = reactive<MaterialFormState>({
  materialCode: '',
  materialName: '',
  category: 'PVC',
  spec: '',
  unit: 'KG',
  supplier: '',
  safetyStockKg: '',
  unitPriceHkdPerLb: '',
  notes: '',
  status: '启用' as MaterialStatus,
})

const requisitionRows: RequisitionRow[] = [
  {
    factoryId: 'huaxing',
    reqNumber: 'LL-20260706-003',
    date: '2026-07-06',
    orderId: 'PB-20260705-012',
    material: '透明PVC30度',
    requestedWeightKg: 25,
    applicant: '李工',
    status: '待出库',
    issuedAt: '',
  },
  {
    factoryId: 'huaxing',
    reqNumber: 'LL-20260706-002',
    date: '2026-07-06',
    orderId: 'PB-20260705-009',
    material: 'ABS 750W 白',
    requestedWeightKg: 40,
    applicant: '张工',
    status: '已出库',
    issuedAt: '10:24',
  },
  {
    factoryId: 'huaxing',
    reqNumber: 'LL-20260706-001',
    date: '2026-07-06',
    orderId: '',
    material: 'PP(EP332K)',
    requestedWeightKg: 15,
    applicant: '王工',
    status: '已出库',
    issuedAt: '09:07',
  },
  {
    factoryId: 'huaxing',
    reqNumber: 'LL-20260705-008',
    date: '2026-07-05',
    orderId: 'PB-20260704-016',
    material: 'PC 110 透明',
    requestedWeightKg: 18.5,
    applicant: '陈工',
    status: '待出库',
    issuedAt: '',
  },
]

const inventoryBatchRows: InventoryBatchRow[] = [
  {
    factoryId: 'huaxing',
    batchNo: 'B-20260701-01',
    material: '透明PVC30度',
    location: 'A-01',
    inboundDate: '2026-07-01',
    initialWeightKg: 200,
    availableWeightKg: 128.5,
  },
  {
    factoryId: 'huaxing',
    batchNo: 'B-20260628-03',
    material: 'ABS 750W 白',
    location: 'A-02',
    inboundDate: '2026-06-28',
    initialWeightKg: 150,
    availableWeightKg: 42,
  },
  {
    factoryId: 'huaxing',
    batchNo: 'B-20260620-05',
    material: 'PC 110 透明',
    location: 'B-01',
    inboundDate: '2026-06-20',
    initialWeightKg: 80,
    availableWeightKg: 36.5,
  },
  {
    factoryId: 'huaxing',
    batchNo: 'B-20260615-02',
    material: 'PP(EP332K)',
    location: 'B-03',
    inboundDate: '2026-06-15',
    initialWeightKg: 100,
    availableWeightKg: 0,
  },
]

const inventoryMovementRows: InventoryMovementRow[] = [
  {
    factoryId: 'huaxing',
    time: '07-06 10:24',
    type: '出库',
    material: 'ABS 750W 白',
    batchNo: 'B-20260628-03',
    quantityKg: -40,
    afterWeightKg: 42,
    sourceDocument: 'LL-20260706-002',
    actor: '仓管·陈',
  },
  {
    factoryId: 'huaxing',
    time: '07-06 09:07',
    type: '出库',
    material: 'PP(EP332K)',
    batchNo: 'B-20260615-02',
    quantityKg: -15,
    afterWeightKg: 18,
    sourceDocument: 'LL-20260706-001',
    actor: '仓管·陈',
  },
  {
    factoryId: 'huaxing',
    time: '07-05 16:40',
    type: '撤回',
    material: '透明PVC30度',
    batchNo: 'B-20260701-01',
    quantityKg: 25,
    afterWeightKg: 153.5,
    sourceDocument: 'LL-20260705-008',
    actor: '仓管·陈',
  },
  {
    factoryId: 'huaxing',
    time: '07-01 08:30',
    type: '入库',
    material: '透明PVC30度',
    batchNo: 'B-20260701-01',
    quantityKg: 200,
    afterWeightKg: 200,
    sourceDocument: '新批次入库',
    actor: '仓管·陈',
  },
]

const validTabs = rawMaterialTabs.map((tab) => tab.id)

const normalizeTab = (tab: unknown): RawMaterialTab => {
  if (typeof tab === 'string' && validTabs.includes(tab as RawMaterialTab)) {
    return tab as RawMaterialTab
  }

  return 'material'
}

const activeTab = ref<RawMaterialTab>(normalizeTab(route.query.tab))
const globalSearch = ref('')
const selectedCategoryFilter = ref('全部类别')
const selectedMaterialStatusFilter = ref<'全部状态' | MaterialStatus>('全部状态')
const materialPage = ref(1)
const requisitionStatusFilter = ref<'全部' | RequisitionStatus>('全部')
const selectedMaterialFilter = ref('全部原料')
const selectedLocationFilter = ref('全部库位')
const movementTypeFilter = ref<'全部' | MovementType>('全部')
const showMaterialModal = ref(false)
const showRequisitionModal = ref(false)
const showBatchModal = ref(false)
const actionMessage = ref('正在从公共原料资料库读取资料...')
let rawMaterialRequestSequence = 0

const selectedFactoryId = computed<ProductionFactoryContextId>(() => {
  const routeFactory = route.query.factory

  if (typeof routeFactory === 'string' && isProductionFactoryContextId(routeFactory)) {
    return routeFactory
  }

  return isProductionFactoryContextId(appStore.activeProductionFactory.id)
    ? appStore.activeProductionFactory.id
    : 'huakang-a'
})

const activeFactory = computed(() =>
  appStore.activeProductionFactory,
)
const scopedRequisitionRows = computed(() =>
  requisitionRows.filter((row) => row.factoryId === selectedFactoryId.value),
)
const scopedInventoryBatchRows = computed(() =>
  inventoryBatchRows.filter((row) => row.factoryId === selectedFactoryId.value),
)
const scopedInventoryMovementRows = computed(() =>
  inventoryMovementRows.filter((row) => row.factoryId === selectedFactoryId.value),
)
const warehouseDepartmentRoute = computed(() => getFactoryScopedRoute(
  '/modules/pmc-warehouse',
  selectedFactoryId.value,
))

const canManageSelectedFactory = computed(() =>
  ['engineering', 'pmc-warehouse', 'warehouse'].some((department) =>
    authStore.can(
      'molding_sample:raw_material_write',
      selectedFactoryId.value,
      department,
    ),
  ),
)

async function loadPersistedRawMaterials(factoryId: string) {
  const requestSequence = ++rawMaterialRequestSequence
  try {
    const persistedRows = await rawMaterialApi.list(factoryId)
    if (
      requestSequence !== rawMaterialRequestSequence
      || factoryId !== selectedFactoryId.value
    ) {
      return
    }

    rawMaterialRows.splice(0, rawMaterialRows.length, ...persistedRows.map(mapPersistedRawMaterialRow))
    actionMessage.value = `已从公共原料资料库读取 ${persistedRows.length} 条资料，${activeFactory.value.name} 可直接共用。`
  }
  catch {
    if (
      requestSequence === rawMaterialRequestSequence
      && factoryId === selectedFactoryId.value
    ) {
      rawMaterialRows.splice(0, rawMaterialRows.length)
      notifyAction('无法读取已保存的原料资料，请检查登录状态与后端服务。')
    }
  }
}

watch(selectedFactoryId, (factoryId) => {
  closeModals()
  rawMaterialRows.splice(0, rawMaterialRows.length)
  materialPage.value = 1
  actionMessage.value = `正在为 ${activeFactory.value.name} 读取公共原料资料库...`
  void loadPersistedRawMaterials(factoryId)
}, { immediate: true })

const normalizedSearch = computed(() => globalSearch.value.trim().toLowerCase())

const normalizedMaterialRows = computed(() =>
  rawMaterialRows.map((row) => ({
    row,
    category: materialCategoryLabel(row),
    searchText: [
      row.code,
      row.name,
      row.spec,
      row.category,
      row.unit,
      row.supplier,
      row.status,
      row.notes,
    ]
      .map((value) => value ?? '')
      .join(' ')
      .toLowerCase(),
  })),
)

const materialCategoryOptions = computed(() => {
  const categories = new Set(normalizedMaterialRows.value.map((entry) => entry.category))

  return ['全部类别', ...Array.from(categories).sort((left, right) => left.localeCompare(right, 'zh-Hans-CN'))]
})

const materialRows = computed(() => {
  const keyword = normalizedSearch.value

  return normalizedMaterialRows.value
    .filter((entry) => {
      const matchesCategory = selectedCategoryFilter.value === '全部类别'
        || entry.category === selectedCategoryFilter.value
      const matchesStatus = selectedMaterialStatusFilter.value === '全部状态'
        || entry.row.status === selectedMaterialStatusFilter.value
      const matchesKeyword = !keyword || entry.searchText.includes(keyword)

      return matchesCategory && matchesStatus && matchesKeyword
    })
    .map((entry) => entry.row)
})

const materialPageCount = computed(() =>
  Math.max(1, Math.ceil(materialRows.value.length / rawMaterialPageSize)),
)

const paginatedMaterialRows = computed(() => {
  const start = (materialPage.value - 1) * rawMaterialPageSize

  return materialRows.value.slice(start, start + rawMaterialPageSize)
})

const materialStartIndex = computed(() => {
  if (materialRows.value.length === 0) {
    return 0
  }

  return (materialPage.value - 1) * rawMaterialPageSize + 1
})

const materialEndIndex = computed(() =>
  Math.min(materialRows.value.length, materialPage.value * rawMaterialPageSize),
)

const filteredRequisitionRows = computed(() => {
  const keyword = normalizedSearch.value

  return scopedRequisitionRows.value.filter((row) => {
    const matchesStatus = requisitionStatusFilter.value === '全部' || row.status === requisitionStatusFilter.value
    const matchesKeyword = !keyword || [row.reqNumber, row.orderId, row.material, row.applicant]
      .some((value) => value.toLowerCase().includes(keyword))

    return matchesStatus && matchesKeyword
  })
})

const materialOptions = computed(() => ['全部原料', ...new Set(scopedInventoryBatchRows.value.map((row) => row.material))])
const locationOptions = computed(() => ['全部库位', ...new Set(scopedInventoryBatchRows.value.map((row) => row.location))])

const filteredBatchRows = computed(() =>
  scopedInventoryBatchRows.value.filter((row) => {
    const matchesMaterial = selectedMaterialFilter.value === '全部原料' || row.material === selectedMaterialFilter.value
    const matchesLocation = selectedLocationFilter.value === '全部库位' || row.location === selectedLocationFilter.value

    return matchesMaterial && matchesLocation
  }),
)

const filteredMovementRows = computed(() =>
  scopedInventoryMovementRows.value.filter((row) =>
    movementTypeFilter.value === '全部' || row.type === movementTypeFilter.value,
  ),
)

const categoryCount = computed(() => new Set(normalizedMaterialRows.value.map((entry) => entry.category)).size)
const enabledMaterialCount = computed(() => rawMaterialRows.filter((row) => row.status === '启用').length)
const disabledMaterialCount = computed(() => rawMaterialRows.length - enabledMaterialCount.value)
const supplierCount = computed(() =>
  new Set(rawMaterialRows.map((row) => row.supplier).filter((supplier) => supplier && supplier !== '未填写')).size,
)
const lowStockCount = computed(() =>
  rawMaterialRows.filter((row) =>
    row.safetyStockKg !== null
    && row.currentStockKg !== null
    && row.currentStockKg < row.safetyStockKg,
  ).length,
)
const pendingStockProfileCount = computed(() =>
  rawMaterialRows.filter((row) => row.safetyStockKg === null || row.currentStockKg === null).length,
)
const materialCategorySummary = computed(() => materialCategoryOptions.value.slice(1, 6).join(' / '))
const pendingRequisitionCount = computed(() => scopedRequisitionRows.value.filter((row) => row.status === '待出库').length)
const issuedTodayCount = computed(() => scopedRequisitionRows.value.filter((row) => row.status === '已出库' && row.date === '2026-07-06').length)
const monthlyRequestedWeight = computed(() => scopedRequisitionRows.value.reduce((total, row) => total + row.requestedWeightKg, 0))
const availableInventoryWeight = computed(() => scopedInventoryBatchRows.value.reduce((total, row) => total + row.availableWeightKg, 0))
const depletedBatchCount = computed(() => scopedInventoryBatchRows.value.filter((row) => row.availableWeightKg <= 0).length)

const tabTitle = computed(() => rawMaterialTabs.find((tab) => tab.id === activeTab.value)?.label ?? '原料资料')
const isEditingMaterial = computed(() => editingMaterialId.value !== null)

watch(() => route.query.tab, (tab) => {
  activeTab.value = normalizeTab(tab)
})

watch([normalizedSearch, selectedCategoryFilter, selectedMaterialStatusFilter], () => {
  materialPage.value = 1
})

watch(materialPageCount, (pageCount) => {
  if (materialPage.value > pageCount) {
    materialPage.value = pageCount
  }
})

watchEffect(() => {
  appStore.setActiveDepartment('pmc-warehouse')
  appStore.setActiveFactory(selectedFactoryId.value)
})

function setActiveTab(tab: RawMaterialTab) {
  activeTab.value = tab
  void router.replace({
    path: route.path,
    query: {
      ...route.query,
      tab,
    },
  })
}

function formatDecimal(value: number, digits = 1) {
  return Number(value).toFixed(digits)
}

function formatPrice(value: number | null) {
  return value === null ? '—' : value.toFixed(6).replace(/0+$/, '').replace(/\.$/, '')
}

function formatSignedWeight(value: number) {
  const sign = value > 0 ? '+' : ''
  return `${sign}${formatDecimal(value)}`
}

function categoryTone(category: string): Tone {
  if (category.includes('PVC')) return 'blue'
  if (category.includes('ABS')) return 'teal'
  if (category.includes('色粉') || category.includes('TPE') || category.includes('TPR')) return 'amber'
  if (category.includes('PC') || category.includes('HDPE') || category.includes('LDPE')) return 'green'
  if (category.includes('PP')) return 'slate'
  return 'slate'
}

function materialCategoryLabel(row: RawMaterialRow) {
  return row.category
}

function formatStockValue(value: number | null, emptyLabel: string) {
  return value === null ? emptyLabel : formatDecimal(value)
}

function materialRowLabel(row: RawMaterialRow) {
  return row.name || row.code || `第 ${row.rowNumber} 行`
}

function goMaterialPage(delta: number) {
  materialPage.value = Math.min(Math.max(1, materialPage.value + delta), materialPageCount.value)
}

function badgeClass(tone: Tone) {
  const classes: Record<Tone, string> = {
    teal: 'bg-teal-50 text-teal-700 ring-teal-100',
    blue: 'bg-blue-50 text-blue-700 ring-blue-100',
    amber: 'bg-amber-50 text-amber-700 ring-amber-100',
    red: 'bg-red-50 text-red-700 ring-red-100',
    slate: 'bg-slate-100 text-slate-600 ring-slate-200',
    green: 'bg-emerald-50 text-emerald-700 ring-emerald-100',
  }

  return classes[tone]
}

function stockClass(row: RawMaterialRow) {
  if (row.safetyStockKg === null || row.currentStockKg === null) {
    return 'text-slate-400'
  }

  const ratio = row.currentStockKg / Math.max(row.safetyStockKg, 1)

  if (ratio < 0.5) {
    return 'text-red-600'
  }
  if (ratio < 1) {
    return 'text-amber-600'
  }

  return 'text-slate-950'
}

function statusTone(status: MaterialStatus | RequisitionStatus): Tone {
  if (status === '启用' || status === '已出库') {
    return 'green'
  }
  if (status === '待出库') {
    return 'amber'
  }

  return 'slate'
}

function movementTone(type: MovementType): Tone {
  if (type === '入库') {
    return 'green'
  }
  if (type === '出库') {
    return 'red'
  }

  return 'slate'
}

function mapPersistedRawMaterialRow(material: RawMaterialResponse, index: number): RawMaterialRow {
  return {
    id: material.id,
    rowNumber: index + 1,
    code: material.material_code,
    name: material.material_name || '未命名原料',
    spec: material.spec || '—',
    category: material.category,
    unit: material.unit,
    supplier: material.supplier || '未填写',
    unitPriceHkdPerLb: material.unit_price_hkd_per_lb,
    safetyStockKg: material.safety_stock_kg,
    currentStockKg: null,
    status: material.status,
    notes: material.notes,
  }
}

function batchAvailableRatio(row: InventoryBatchRow) {
  if (!row.initialWeightKg) {
    return 0
  }

  return Math.max(0, Math.min(100, Math.round((row.availableWeightKg / row.initialWeightKg) * 100)))
}

function batchProgressClass(row: InventoryBatchRow) {
  const ratio = batchAvailableRatio(row)

  if (ratio === 0) {
    return 'bg-slate-400'
  }
  if (ratio < 35) {
    return 'bg-amber-500'
  }

  return 'bg-teal-600'
}

function notifyAction(message: string) {
  actionMessage.value = message
}

function closeModals() {
  showMaterialModal.value = false
  showRequisitionModal.value = false
  showBatchModal.value = false
  editingMaterialId.value = null
  materialFormError.value = ''
}

function resetMaterialForm() {
  materialForm.materialCode = ''
  materialForm.materialName = ''
  materialForm.category = 'PVC'
  materialForm.spec = ''
  materialForm.unit = 'KG'
  materialForm.supplier = ''
  materialForm.safetyStockKg = ''
  materialForm.unitPriceHkdPerLb = ''
  materialForm.notes = ''
  materialForm.status = '启用'
  editingMaterialId.value = null
  materialFormError.value = ''
}

function openMaterialModal() {
  if (!canManageSelectedFactory.value) {
    notifyAction('当前厂区为只读，不能新增原料资料。')
    return
  }
  resetMaterialForm()
  showMaterialModal.value = true
}

function openEditMaterialModal(row: RawMaterialRow) {
  if (!canManageSelectedFactory.value) {
    notifyAction('当前厂区为只读，不能编辑原料资料。')
    return
  }
  materialForm.materialCode = row.code
  materialForm.materialName = row.name
  materialForm.category = row.category
  materialForm.spec = row.spec === '—' ? '' : row.spec
  materialForm.unit = row.unit
  materialForm.supplier = row.supplier === '未填写' ? '' : row.supplier
  materialForm.safetyStockKg = row.safetyStockKg === null ? '' : String(row.safetyStockKg)
  materialForm.unitPriceHkdPerLb = row.unitPriceHkdPerLb === null ? '' : String(row.unitPriceHkdPerLb)
  materialForm.notes = row.notes
  materialForm.status = row.status
  editingMaterialId.value = row.id
  materialFormError.value = ''
  showMaterialModal.value = true
}

function parseOptionalNumber(value: string | number) {
  const normalized = String(value ?? '').trim()
  return normalized === '' ? null : Number(normalized)
}

async function saveMaterial() {
  if (!canManageSelectedFactory.value) {
    closeModals()
    notifyAction('当前厂区为只读，不能保存原料资料。')
    return
  }
  materialFormError.value = ''
  const materialName = materialForm.materialName.trim()
  const safetyStockKg = parseOptionalNumber(materialForm.safetyStockKg)
  const unitPriceHkdPerLb = parseOptionalNumber(materialForm.unitPriceHkdPerLb)

  if (!materialName) {
    materialFormError.value = '请填写原料名称。'
    notifyAction(materialFormError.value)
    return
  }
  if (
    safetyStockKg !== null
    && (!Number.isFinite(safetyStockKg) || safetyStockKg < 0)
  ) {
    materialFormError.value = '安全库存必须是大于或等于 0 的数字。'
    notifyAction(materialFormError.value)
    return
  }
  if (
    unitPriceHkdPerLb !== null
    && (!Number.isFinite(unitPriceHkdPerLb) || unitPriceHkdPerLb <= 0)
  ) {
    materialFormError.value = '单价必须是大于 0 的数字，或留空表示暂不维护。'
    notifyAction(materialFormError.value)
    return
  }
  isSavingMaterial.value = true
  try {
    const payload = {
      material_name: materialName,
      category: materialForm.category,
      spec: materialForm.spec,
      unit: materialForm.unit,
      supplier: materialForm.supplier,
      safety_stock_kg: safetyStockKg,
      unit_price_hkd_per_lb: unitPriceHkdPerLb,
      status: materialForm.status,
      notes: materialForm.notes,
    }
    if (editingMaterialId.value) {
      const updated = await rawMaterialApi.update(editingMaterialId.value, selectedFactoryId.value, payload)
      const rowIndex = rawMaterialRows.findIndex((row) => row.id === updated.id)
      if (rowIndex >= 0) {
        rawMaterialRows.splice(rowIndex, 1, mapPersistedRawMaterialRow(updated, rowIndex))
      }
      closeModals()
      notifyAction(`原料“${updated.material_name}”及单价已更新。`)
    }
    else {
      const created = await rawMaterialApi.create({
        factory_id: selectedFactoryId.value,
        ...payload,
      })
      rawMaterialRows.push(mapPersistedRawMaterialRow(created, rawMaterialRows.length))
      materialPage.value = materialPageCount.value
      closeModals()
      notifyAction(`原料“${created.material_name}”已保存到公共原料资料库，所有厂区可共用。`)
    }
  }
  catch (error) {
    materialFormError.value = `保存原料失败：${getApiErrorMessage(error)}`
    notifyAction(materialFormError.value)
  }
  finally {
    isSavingMaterial.value = false
  }
}

function saveSecondaryModal() {
  if (!canManageSelectedFactory.value) {
    closeModals()
    notifyAction('当前厂区为只读，不能新建领料单或库存批次。')
    return
  }
  const message = showRequisitionModal.value
    ? '领料单保存动作待接 requisitions 接口。'
    : '批次入库动作待接 inventory-batches 接口。'

  closeModals()
  notifyAction(message)
}

function openRequisitionModal() {
  if (!canManageSelectedFactory.value) {
    notifyAction('当前厂区为只读，不能新建领料单。')
    return
  }
  showRequisitionModal.value = true
}

function openBatchModal() {
  if (!canManageSelectedFactory.value) {
    notifyAction('当前厂区为只读，不能新建库存批次。')
    return
  }
  showBatchModal.value = true
}
</script>

<template>
  <main class="min-h-screen bg-slate-100 text-[13px] leading-relaxed text-slate-900">
    <header class="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div class="mx-auto flex max-w-[1720px] items-center gap-3 px-5 py-2.5">
        <RouterLink
          :to="warehouseDepartmentRoute"
          class="inline-flex h-9 shrink-0 items-center gap-2 whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-950"
        >
          <ArrowLeft class="size-4" aria-hidden="true" />
          <span class="hidden sm:inline">PMC / 仓管模块</span>
          <span class="sm:hidden">仓管</span>
        </RouterLink>

        <div class="flex min-w-0 items-center gap-2.5">
          <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-white">
            <Boxes class="size-5" aria-hidden="true" />
          </span>
          <div class="min-w-0">
            <div class="truncate text-[15px] font-bold leading-tight">原料管理模块</div>
            <div class="truncate text-[11px] text-slate-400">Warehouse & Raw Material · 原料资料 / 领料 / 库存</div>
          </div>
        </div>

        <label class="relative ml-1 hidden md:block">
          <Search class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
          <input
            v-model="globalSearch"
            placeholder="搜索原料 / 编号 / 单号..."
            class="h-8 w-72 rounded-lg border border-slate-200 bg-slate-50 pl-8 pr-3 text-[12px] outline-none transition focus:border-slate-400 focus:bg-white"
          >
        </label>

        <div class="ml-auto flex items-center gap-2">
          <span class="hidden h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-[12px] font-medium text-slate-600 sm:inline-flex">
            <Building2 class="size-4" aria-hidden="true" />
            当前厂区：{{ activeFactory.shortName }}
          </span>
          <AccountMenu />
        </div>
      </div>

      <nav class="mx-auto flex max-w-[1720px] items-center gap-1 overflow-x-auto px-5">
        <button
          v-for="tab in rawMaterialTabs"
          :key="tab.id"
          type="button"
          class="inline-flex items-center gap-1.5 whitespace-nowrap rounded-t-lg px-3 py-2 text-[12.5px] font-semibold transition hover:text-slate-900"
          :class="activeTab === tab.id ? 'bg-slate-900 text-white' : 'text-slate-500'"
          @click="setActiveTab(tab.id)"
        >
          <component :is="tab.icon" class="size-4" aria-hidden="true" />
          {{ tab.label }}
        </button>
      </nav>
    </header>

    <div class="mx-auto max-w-[1720px] space-y-4 px-5 pb-12 pt-4">
      <div class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
        <div class="min-w-0">
          <div class="text-[13px] font-bold text-slate-950">{{ tabTitle }}工作台</div>
          <p class="mt-0.5 text-[11px] text-slate-500">{{ actionMessage }}</p>
        </div>
        <button
          type="button"
          class="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-950"
          @click="notifyAction('已刷新当前前端样式数据。后续接入真实接口时保留这个页面结构。')"
        >
          <RotateCcw class="size-4" aria-hidden="true" />
          刷新
        </button>
      </div>

      <div
        v-if="!canManageSelectedFactory"
        class="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-[12px] font-semibold text-amber-800"
      >
        <AlertTriangle class="size-4 shrink-0 text-amber-600" aria-hidden="true" />
        当前厂区为只读，可查看原料资料，但不能新增、编辑、领料或调整库存。
      </div>

      <section v-if="activeTab === 'material'" class="space-y-4">
        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <article class="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
            <div class="flex items-center justify-between">
              <span class="text-[11px] font-medium text-slate-500">原料总数</span>
              <span class="flex size-8 items-center justify-center rounded-xl bg-teal-50 text-teal-700">
                <Package class="size-4" aria-hidden="true" />
              </span>
            </div>
            <div class="mt-2 text-3xl font-semibold tracking-tight text-slate-950 tabular-nums">{{ rawMaterialRows.length }}</div>
            <div class="mt-1 text-[11px] text-slate-400">启用 {{ enabledMaterialCount }} · 停用 {{ disabledMaterialCount }}</div>
          </article>
          <article class="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
            <div class="flex items-center justify-between">
              <span class="text-[11px] font-medium text-slate-500">物料类别</span>
              <span class="flex size-8 items-center justify-center rounded-xl bg-blue-50 text-blue-700">
                <Table2 class="size-4" aria-hidden="true" />
              </span>
            </div>
            <div class="mt-2 text-3xl font-semibold tracking-tight text-slate-950 tabular-nums">{{ categoryCount }}</div>
            <div class="mt-1 truncate text-[11px] text-slate-400">{{ materialCategorySummary }}</div>
          </article>
          <article class="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
            <div class="flex items-center justify-between">
              <span class="text-[11px] font-medium text-slate-500">供应商</span>
              <span class="flex size-8 items-center justify-center rounded-xl bg-slate-100 text-slate-700">
                <Building2 class="size-4" aria-hidden="true" />
              </span>
            </div>
            <div class="mt-2 text-3xl font-semibold tracking-tight text-slate-950 tabular-nums">{{ supplierCount }}</div>
            <div class="mt-1 text-[11px] text-slate-400">由表格产地字段映射</div>
          </article>
          <article class="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
            <div class="flex items-center justify-between">
              <span class="text-[11px] font-medium text-slate-500">库存预警</span>
              <span class="flex size-8 items-center justify-center rounded-xl bg-amber-50 text-amber-700">
                <AlertTriangle class="size-4" aria-hidden="true" />
              </span>
            </div>
            <div class="mt-2 text-3xl font-semibold tracking-tight text-amber-600 tabular-nums">{{ lowStockCount }}</div>
            <div class="mt-1 text-[11px] text-slate-400">{{ pendingStockProfileCount }} 条待维护库存</div>
          </article>
        </div>

        <section class="rounded-lg border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
          <div class="flex flex-wrap items-center gap-3 border-b border-slate-100 px-4 py-3">
            <div>
              <h2 class="text-[13px] font-bold text-slate-950">原料资料 · 物料主数据</h2>
              <p class="mt-0.5 text-[11px] text-slate-400">
                公共原料主数据 · 所有厂区共用 · 每页 {{ rawMaterialPageSize }} 条
              </p>
            </div>
            <div class="ml-auto flex flex-wrap items-center gap-2">
              <label class="relative">
                <Search class="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-slate-400" aria-hidden="true" />
                <input
                  v-model="globalSearch"
                  placeholder="按名称 / 编号搜索"
                  class="h-9 w-56 rounded-lg border border-slate-200 bg-white pl-8 pr-3 text-[12px] outline-none transition focus:border-slate-400"
                >
              </label>
              <select
                v-model="selectedCategoryFilter"
                class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-[12px] text-slate-600 outline-none focus:border-slate-400"
              >
                <option v-for="category in materialCategoryOptions" :key="category">{{ category }}</option>
              </select>
              <select
                v-model="selectedMaterialStatusFilter"
                class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-[12px] text-slate-600 outline-none focus:border-slate-400"
              >
                <option v-for="status in materialStatusFilters" :key="status">{{ status }}</option>
              </select>
              <button
                type="button"
                class="inline-flex h-9 items-center rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-600 transition hover:border-slate-300"
                @click="notifyAction(`当前筛选命中 ${materialRows.length} 条物料；导出入口待接入正式文件服务。`)"
              >
                导出
              </button>
              <button
                type="button"
                :disabled="!canManageSelectedFactory"
                class="inline-flex h-9 items-center gap-2 rounded-lg bg-slate-950 px-4 text-[12px] font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                @click="openMaterialModal"
              >
                <Plus class="size-4" aria-hidden="true" />
                新增原料
              </button>
            </div>
          </div>

          <div class="overflow-x-auto">
            <table class="min-w-[1180px] w-full text-[12px]">
              <thead>
                <tr class="border-b border-slate-100 bg-slate-50 text-[11px] text-slate-500">
                  <th class="px-3 py-2 text-left font-medium">序号</th>
                  <th class="px-3 py-2 text-left font-medium">物料编号</th>
                  <th class="px-3 py-2 text-left font-medium">原料名称 / 型号</th>
                  <th class="px-3 py-2 text-left font-medium">规格</th>
                  <th class="px-3 py-2 text-left font-medium">类别</th>
                  <th class="px-3 py-2 text-left font-medium">单位</th>
                  <th class="px-3 py-2 text-left font-medium">供应商</th>
                  <th class="px-3 py-2 text-right font-medium">单价(HKD/磅)</th>
                  <th class="px-3 py-2 text-right font-medium">安全库存(KG)</th>
                  <th class="px-3 py-2 text-right font-medium">当前库存(KG)</th>
                  <th class="px-3 py-2 text-center font-medium">状态</th>
                  <th class="px-3 py-2 text-center font-medium">操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-50 text-slate-700">
                <tr v-for="row in paginatedMaterialRows" :key="row.id" class="hover:bg-slate-50">
                  <td class="px-3 py-2.5 tabular-nums text-slate-400">{{ row.rowNumber }}</td>
                  <td class="px-3 py-2.5 font-semibold text-slate-950">{{ row.code }}</td>
                  <td class="px-3 py-2.5 font-semibold text-slate-800">{{ row.name }}</td>
                  <td class="px-3 py-2.5 text-slate-500">{{ row.spec }}</td>
                  <td class="px-3 py-2.5">
                    <span class="rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="badgeClass(categoryTone(row.category))">
                      {{ materialCategoryLabel(row) }}
                    </span>
                  </td>
                  <td class="px-3 py-2.5">{{ row.unit }}</td>
                  <td class="px-3 py-2.5 text-slate-500">{{ row.supplier }}</td>
                  <td class="px-3 py-2.5 text-right tabular-nums" :class="row.unitPriceHkdPerLb === null ? 'text-slate-300' : 'text-slate-700'">
                    {{ formatPrice(row.unitPriceHkdPerLb) }}
                  </td>
                  <td class="px-3 py-2.5 text-right tabular-nums text-slate-400">{{ formatStockValue(row.safetyStockKg, '待维护') }}</td>
                  <td class="px-3 py-2.5 text-right font-semibold tabular-nums" :class="stockClass(row)">
                    {{ formatStockValue(row.currentStockKg, '待盘点') }}
                  </td>
                  <td class="px-3 py-2.5 text-center">
                    <span class="rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="badgeClass(statusTone(row.status))">
                      {{ row.status }}
                    </span>
                  </td>
                  <td class="whitespace-nowrap px-3 py-2.5 text-center">
                    <button type="button" :disabled="!canManageSelectedFactory" class="text-[11px] font-semibold text-teal-700 hover:underline disabled:cursor-not-allowed disabled:text-slate-300 disabled:no-underline" @click="openEditMaterialModal(row)">编辑</button>
                    <span class="mx-1 text-slate-200">|</span>
                    <button type="button" :disabled="!canManageSelectedFactory" class="text-[11px] font-semibold text-slate-400 hover:text-slate-700 disabled:cursor-not-allowed disabled:text-slate-300" @click="notifyAction(`${materialRowLabel(row)} 状态操作待接入原料主数据接口。`)">
                      {{ row.status === '启用' ? '停用' : '启用' }}
                    </button>
                  </td>
                </tr>
                <tr v-if="paginatedMaterialRows.length === 0">
                  <td colspan="12" class="px-3 py-10 text-center text-[12px] text-slate-400">
                    没有匹配的原料资料
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="flex items-center justify-between border-t border-slate-100 px-4 py-3 text-[12px] text-slate-500">
            <span>共 {{ materialRows.length }} 条 · 显示 {{ materialStartIndex }}-{{ materialEndIndex }} 条</span>
            <div class="flex items-center gap-1">
              <button
                type="button"
                class="h-7 rounded-md border border-slate-200 px-2 transition disabled:cursor-not-allowed disabled:text-slate-300 enabled:text-slate-600 enabled:hover:border-slate-300"
                :disabled="materialPage <= 1"
                @click="goMaterialPage(-1)"
              >
                上一页
              </button>
              <span class="inline-flex h-7 items-center rounded-md bg-slate-900 px-2.5 text-white">
                {{ materialPage }} / {{ materialPageCount }}
              </span>
              <button
                type="button"
                class="h-7 rounded-md border border-slate-200 px-2 transition disabled:cursor-not-allowed disabled:text-slate-300 enabled:text-slate-600 enabled:hover:border-slate-300"
                :disabled="materialPage >= materialPageCount"
                @click="goMaterialPage(1)"
              >
                下一页
              </button>
            </div>
          </div>
        </section>
      </section>

      <section v-else-if="activeTab === 'requisition'" class="space-y-4">
        <div class="grid gap-4 md:grid-cols-3">
          <article class="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
            <div class="flex items-center justify-between">
              <span class="text-[11px] font-medium text-slate-500">待出库</span>
              <span class="flex size-8 items-center justify-center rounded-xl bg-amber-50 text-amber-700">
                <ClipboardCheck class="size-4" aria-hidden="true" />
              </span>
            </div>
            <div class="mt-2 text-3xl font-semibold tracking-tight text-amber-600 tabular-nums">{{ pendingRequisitionCount }}</div>
          </article>
          <article class="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
            <div class="flex items-center justify-between">
              <span class="text-[11px] font-medium text-slate-500">今日已出库</span>
              <span class="flex size-8 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700">
                <CheckCircle2 class="size-4" aria-hidden="true" />
              </span>
            </div>
            <div class="mt-2 text-3xl font-semibold tracking-tight text-slate-950 tabular-nums">{{ issuedTodayCount }}</div>
          </article>
          <article class="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
            <div class="flex items-center justify-between">
              <span class="text-[11px] font-medium text-slate-500">本月领料重量 (KG)</span>
              <span class="flex size-8 items-center justify-center rounded-xl bg-teal-50 text-teal-700">
                <PackageCheck class="size-4" aria-hidden="true" />
              </span>
            </div>
            <div class="mt-2 text-3xl font-semibold tracking-tight text-slate-950 tabular-nums">{{ formatDecimal(monthlyRequestedWeight) }}</div>
          </article>
        </div>

        <section class="rounded-lg border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
          <div class="flex flex-wrap items-center gap-3 border-b border-slate-100 px-4 py-3">
            <div>
              <h2 class="text-[13px] font-bold text-slate-950">领料单列表</h2>
              <p class="mt-0.5 text-[11px] text-slate-400">与 requisitions 后端契约保持字段一致。</p>
            </div>
            <div class="flex items-center gap-1 rounded-lg bg-slate-100 p-0.5 text-[11px]">
              <button
                v-for="filter in requisitionStatusFilters"
                :key="filter"
                type="button"
                class="rounded-md px-2.5 py-1 font-semibold transition"
                :class="requisitionStatusFilter === filter ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-900'"
                @click="requisitionStatusFilter = filter"
              >
                {{ filter }}
              </button>
            </div>
            <div class="ml-auto flex flex-wrap items-center gap-2">
              <label class="relative">
                <Search class="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-slate-400" aria-hidden="true" />
                <input
                  v-model="globalSearch"
                  placeholder="单号 / 原料 / 申请人"
                  class="h-9 w-56 rounded-lg border border-slate-200 bg-white pl-8 pr-3 text-[12px] outline-none transition focus:border-slate-400"
                >
              </label>
              <button
                type="button"
                :disabled="!canManageSelectedFactory"
                class="inline-flex h-9 items-center gap-2 rounded-lg bg-slate-950 px-4 text-[12px] font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                @click="openRequisitionModal"
              >
                <Plus class="size-4" aria-hidden="true" />
                新建领料单
              </button>
            </div>
          </div>

          <div class="overflow-x-auto">
            <table class="min-w-[980px] w-full text-[12px]">
              <thead>
                <tr class="border-b border-slate-100 bg-slate-50 text-[11px] text-slate-500">
                  <th class="px-3 py-2 text-left font-medium">领料单号</th>
                  <th class="px-3 py-2 text-left font-medium">日期</th>
                  <th class="px-3 py-2 text-left font-medium">关联啤办单</th>
                  <th class="px-3 py-2 text-left font-medium">原料型号</th>
                  <th class="px-3 py-2 text-right font-medium">申请料重(KG)</th>
                  <th class="px-3 py-2 text-left font-medium">申请人</th>
                  <th class="px-3 py-2 text-center font-medium">状态</th>
                  <th class="px-3 py-2 text-left font-medium">出库时间</th>
                  <th class="px-3 py-2 text-center font-medium">操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-50 text-slate-700">
                <tr v-for="row in filteredRequisitionRows" :key="row.reqNumber" class="hover:bg-slate-50">
                  <td class="px-3 py-2.5 font-semibold text-slate-950 tabular-nums">{{ row.reqNumber }}</td>
                  <td class="px-3 py-2.5 text-slate-500 tabular-nums">{{ row.date }}</td>
                  <td class="px-3 py-2.5">
                    <span v-if="row.orderId" class="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-semibold text-slate-600">{{ row.orderId }}</span>
                    <span v-else class="text-slate-300">无关联</span>
                  </td>
                  <td class="px-3 py-2.5">{{ row.material }}</td>
                  <td class="px-3 py-2.5 text-right font-semibold tabular-nums">{{ formatDecimal(row.requestedWeightKg) }}</td>
                  <td class="px-3 py-2.5 text-slate-500">{{ row.applicant }}</td>
                  <td class="px-3 py-2.5 text-center">
                    <span class="rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="badgeClass(statusTone(row.status))">{{ row.status }}</span>
                  </td>
                  <td class="px-3 py-2.5 text-slate-500 tabular-nums">{{ row.issuedAt || '—' }}</td>
                  <td class="whitespace-nowrap px-3 py-2.5 text-center">
                    <template v-if="row.status === '待出库'">
                      <button type="button" :disabled="!canManageSelectedFactory" class="rounded-md bg-teal-700 px-2 py-1 text-[11px] font-semibold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-300" @click="notifyAction(`${row.reqNumber} 确认出库动作待接正式库存扣减。`)">
                        确认出库
                      </button>
                      <button type="button" :disabled="!canManageSelectedFactory" class="ml-1 text-[11px] font-semibold text-slate-400 hover:text-red-600 disabled:cursor-not-allowed disabled:text-slate-300" @click="notifyAction(`${row.reqNumber} 删除动作待接权限校验。`)">删除</button>
                    </template>
                    <template v-else>
                      <button type="button" :disabled="!canManageSelectedFactory" class="text-[11px] font-semibold text-slate-500 hover:text-slate-800 disabled:cursor-not-allowed disabled:text-slate-300" @click="notifyAction(`${row.reqNumber} 撤回动作待接库存流水。`)">撤回</button>
                      <span class="mx-1 text-slate-200">|</span>
                      <button type="button" class="text-[11px] font-semibold text-teal-700 hover:underline" @click="notifyAction(`${row.reqNumber} 详情入口已预留。`)">详情</button>
                    </template>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </section>

      <section v-else-if="activeTab === 'batch'" class="space-y-4">
        <div class="grid gap-4 md:grid-cols-4">
          <article class="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
            <span class="text-[11px] font-medium text-slate-500">批次总数</span>
            <div class="mt-2 text-3xl font-semibold tracking-tight text-slate-950 tabular-nums">{{ scopedInventoryBatchRows.length }}</div>
          </article>
          <article class="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
            <span class="text-[11px] font-medium text-slate-500">可用库存(KG)</span>
            <div class="mt-2 text-3xl font-semibold tracking-tight text-slate-950 tabular-nums">{{ formatDecimal(availableInventoryWeight) }}</div>
          </article>
          <article class="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
            <span class="text-[11px] font-medium text-slate-500">库位数</span>
            <div class="mt-2 text-3xl font-semibold tracking-tight text-slate-950 tabular-nums">{{ locationOptions.length - 1 }}</div>
          </article>
          <article class="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
            <span class="text-[11px] font-medium text-slate-500">已耗尽批次</span>
            <div class="mt-2 text-3xl font-semibold tracking-tight text-slate-950 tabular-nums">{{ depletedBatchCount }}</div>
          </article>
        </div>

        <section class="rounded-lg border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
          <div class="flex flex-wrap items-center gap-3 border-b border-slate-100 px-4 py-3">
            <div>
              <h2 class="text-[13px] font-bold text-slate-950">库存批次 · 库位余量</h2>
              <p class="mt-0.5 text-[11px] text-slate-400">对齐 inventory-batches 字段，突出批次剩余和耗尽状态。</p>
            </div>
            <div class="ml-auto flex flex-wrap items-center gap-2">
              <select v-model="selectedMaterialFilter" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-[12px] text-slate-600 outline-none focus:border-slate-400">
                <option v-for="option in materialOptions" :key="option">{{ option }}</option>
              </select>
              <select v-model="selectedLocationFilter" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-[12px] text-slate-600 outline-none focus:border-slate-400">
                <option v-for="option in locationOptions" :key="option">{{ option }}</option>
              </select>
              <button
                type="button"
                :disabled="!canManageSelectedFactory"
                class="inline-flex h-9 items-center gap-2 rounded-lg bg-slate-950 px-4 text-[12px] font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                @click="openBatchModal"
              >
                <Plus class="size-4" aria-hidden="true" />
                入库新批次
              </button>
            </div>
          </div>

          <div class="overflow-x-auto">
            <table class="min-w-[900px] w-full text-[12px]">
              <thead>
                <tr class="border-b border-slate-100 bg-slate-50 text-[11px] text-slate-500">
                  <th class="px-3 py-2 text-left font-medium">批次号</th>
                  <th class="px-3 py-2 text-left font-medium">原料型号</th>
                  <th class="px-3 py-2 text-left font-medium">库位</th>
                  <th class="px-3 py-2 text-left font-medium">入库日期</th>
                  <th class="px-3 py-2 text-right font-medium">初始重量(KG)</th>
                  <th class="px-3 py-2 text-right font-medium">可用重量(KG)</th>
                  <th class="px-3 py-2 text-left font-medium">消耗进度</th>
                  <th class="px-3 py-2 text-center font-medium">操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-50 text-slate-700">
                <tr v-for="row in filteredBatchRows" :key="row.batchNo" class="hover:bg-slate-50" :class="row.availableWeightKg <= 0 ? 'opacity-60' : ''">
                  <td class="px-3 py-2.5 font-semibold text-slate-950 tabular-nums">{{ row.batchNo }}</td>
                  <td class="px-3 py-2.5">{{ row.material }}</td>
                  <td class="px-3 py-2.5">
                    <span class="rounded bg-blue-50 px-1.5 py-0.5 text-[11px] font-semibold text-blue-700">{{ row.location }}</span>
                  </td>
                  <td class="px-3 py-2.5 text-slate-500 tabular-nums">{{ row.inboundDate }}</td>
                  <td class="px-3 py-2.5 text-right tabular-nums">{{ formatDecimal(row.initialWeightKg) }}</td>
                  <td class="px-3 py-2.5 text-right font-semibold tabular-nums" :class="row.availableWeightKg <= 0 ? 'text-slate-400' : row.availableWeightKg < row.initialWeightKg * 0.35 ? 'text-amber-600' : 'text-slate-950'">
                    {{ formatDecimal(row.availableWeightKg) }}
                  </td>
                  <td class="px-3 py-2.5">
                    <div class="flex items-center gap-2">
                      <div class="h-1.5 w-24 rounded-full bg-slate-100">
                        <div class="h-1.5 rounded-full" :class="batchProgressClass(row)" :style="{ width: `${batchAvailableRatio(row)}%` }" />
                      </div>
                      <span v-if="row.availableWeightKg > 0" class="text-[11px] text-slate-500 tabular-nums">剩余 {{ batchAvailableRatio(row) }}%</span>
                      <span v-else class="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-500 ring-1 ring-inset ring-slate-200">已耗尽</span>
                    </div>
                  </td>
                  <td class="whitespace-nowrap px-3 py-2.5 text-center">
                    <button type="button" :disabled="!canManageSelectedFactory" class="text-[11px] font-semibold text-teal-700 hover:underline disabled:cursor-not-allowed disabled:text-slate-300 disabled:no-underline" @click="notifyAction(`${row.batchNo} 调整入口已预留。`)">调整</button>
                    <span class="mx-1 text-slate-200">|</span>
                    <button type="button" class="text-[11px] font-semibold text-slate-400 hover:text-slate-700" @click="setActiveTab('movement')">流水</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </section>

      <section v-else class="space-y-4">
        <section class="rounded-lg border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
          <div class="flex flex-wrap items-center gap-3 border-b border-slate-100 px-4 py-3">
            <div>
              <h2 class="text-[13px] font-bold text-slate-950">库存流水 · 出入库记录</h2>
              <p class="mt-0.5 text-[11px] text-slate-400">对齐 inventory-movements 字段，保留领料单溯源。</p>
            </div>
            <div class="flex items-center gap-1 rounded-lg bg-slate-100 p-0.5 text-[11px]">
              <button
                v-for="filter in movementTypeFilters"
                :key="filter"
                type="button"
                class="rounded-md px-2.5 py-1 font-semibold transition"
                :class="movementTypeFilter === filter ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-900'"
                @click="movementTypeFilter = filter"
              >
                {{ filter }}
              </button>
            </div>
            <div class="ml-auto flex flex-wrap items-center gap-2">
              <input type="date" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-[12px] text-slate-600 outline-none focus:border-slate-400">
              <span class="text-[12px] text-slate-400">至</span>
              <input type="date" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-[12px] text-slate-600 outline-none focus:border-slate-400">
              <button type="button" class="inline-flex h-9 items-center rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-600 transition hover:border-slate-300" @click="notifyAction('库存流水导出入口已预留。')">
                导出
              </button>
            </div>
          </div>

          <div class="overflow-x-auto">
            <table class="min-w-[960px] w-full text-[12px]">
              <thead>
                <tr class="border-b border-slate-100 bg-slate-50 text-[11px] text-slate-500">
                  <th class="px-3 py-2 text-left font-medium">时间</th>
                  <th class="px-3 py-2 text-center font-medium">类型</th>
                  <th class="px-3 py-2 text-left font-medium">原料型号</th>
                  <th class="px-3 py-2 text-left font-medium">批次号</th>
                  <th class="px-3 py-2 text-right font-medium">变动量(KG)</th>
                  <th class="px-3 py-2 text-right font-medium">变动后可用(KG)</th>
                  <th class="px-3 py-2 text-left font-medium">来源单据</th>
                  <th class="px-3 py-2 text-left font-medium">操作人</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-50 text-slate-700">
                <tr v-for="row in filteredMovementRows" :key="`${row.time}-${row.batchNo}-${row.sourceDocument}`" class="hover:bg-slate-50">
                  <td class="px-3 py-2.5 text-slate-500 tabular-nums">{{ row.time }}</td>
                  <td class="px-3 py-2.5 text-center">
                    <span class="rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="badgeClass(movementTone(row.type))">{{ row.type }}</span>
                  </td>
                  <td class="px-3 py-2.5">{{ row.material }}</td>
                  <td class="px-3 py-2.5 text-slate-500 tabular-nums">{{ row.batchNo }}</td>
                  <td class="px-3 py-2.5 text-right font-semibold tabular-nums" :class="row.quantityKg < 0 ? 'text-red-600' : 'text-emerald-600'">{{ formatSignedWeight(row.quantityKg) }}</td>
                  <td class="px-3 py-2.5 text-right tabular-nums">{{ formatDecimal(row.afterWeightKg) }}</td>
                  <td class="px-3 py-2.5">
                    <span class="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-semibold text-slate-600">{{ row.sourceDocument }}</span>
                  </td>
                  <td class="px-3 py-2.5 text-slate-500">{{ row.actor }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </section>
    </div>

    <div
      v-if="showMaterialModal"
      class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-6"
      @click.self="closeModals"
    >
      <section class="w-full max-w-2xl rounded-xl border border-slate-200 bg-white shadow-2xl">
        <div class="flex items-center gap-2 border-b border-slate-100 px-5 py-3.5">
          <span class="flex size-8 items-center justify-center rounded-lg bg-slate-900 text-white">
            <Plus class="size-4" aria-hidden="true" />
          </span>
          <div>
            <div class="text-[14px] font-bold text-slate-950">{{ isEditingMaterial ? '编辑原料' : '新增原料' }}</div>
            <div class="text-[11px] text-slate-400">{{ isEditingMaterial ? 'Edit Raw Material · 物料主数据与单价' : 'Add Raw Material · 物料主数据' }}</div>
          </div>
          <button type="button" class="ml-auto flex size-7 items-center justify-center rounded-md text-slate-400 transition hover:bg-slate-100" aria-label="关闭新增原料弹窗" @click="closeModals">
            <X class="size-4" aria-hidden="true" />
          </button>
        </div>
        <div class="max-h-[70vh] overflow-y-auto p-5">
          <div class="grid gap-x-4 gap-y-3.5 sm:grid-cols-2">
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-slate-500">物料编号（系统自动生成）</span>
              <input v-model="materialForm.materialCode" readonly class="h-9 w-full cursor-not-allowed rounded-md border border-slate-200 bg-slate-50 px-2.5 text-[12px] text-slate-500 outline-none" :placeholder="isEditingMaterial ? '' : '保存后自动生成'">
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-slate-500">原料名称 / 型号 <span class="text-red-500">*</span></span>
              <input v-model.trim="materialForm.materialName" class="h-9 w-full rounded-md border border-slate-200 bg-white px-2.5 text-[12px] outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100" placeholder="如：ABS 750NSW">
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-slate-500">类别 <span class="text-red-500">*</span></span>
              <select v-model="materialForm.category" class="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                <option>PVC</option>
                <option>ABS</option>
                <option>PP</option>
                <option>PC</option>
                <option>色粉</option>
                <option>其它</option>
              </select>
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-slate-500">规格</span>
              <input v-model.trim="materialForm.spec" class="h-9 w-full rounded-md border border-slate-200 bg-white px-2.5 text-[12px] outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100" placeholder="如：30度 软胶">
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-slate-500">计量单位 <span class="text-red-500">*</span></span>
              <select v-model="materialForm.unit" class="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                <option>KG</option>
                <option>g</option>
                <option>磅</option>
                <option>包</option>
              </select>
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-slate-500">单价 (HKD/磅)</span>
              <input v-model="materialForm.unitPriceHkdPerLb" type="number" min="0" step="0.000001" data-testid="raw-material-unit-price" class="h-9 w-full rounded-md border border-slate-200 bg-white px-2.5 text-[12px] outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100" placeholder="如：4.85">
              <span class="mt-1 block text-[10px] text-slate-400">单价可留空。工程部维护后会同步用于啤办成本计算。</span>
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-slate-500">供应商</span>
              <input v-model.trim="materialForm.supplier" class="h-9 w-full rounded-md border border-slate-200 bg-white px-2.5 text-[12px] outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100" placeholder="如：东莞恒益塑胶">
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-slate-500">安全库存 (KG)</span>
              <input v-model="materialForm.safetyStockKg" type="number" min="0" class="h-9 w-full rounded-md border border-slate-200 bg-white px-2.5 text-[12px] outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100" placeholder="50">
            </label>
            <label class="block sm:col-span-2">
              <span class="mb-1 block text-[11px] font-medium text-slate-500">备注</span>
              <textarea v-model.trim="materialForm.notes" rows="2" class="w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-[12px] outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100" placeholder="混合料配比、别名、注意事项"></textarea>
            </label>
            <div class="flex items-center gap-2 rounded-md bg-slate-50 px-3 py-2 sm:col-span-2">
              <span class="text-[11px] font-medium text-slate-500">状态</span>
              <label class="ml-2 inline-flex items-center gap-1 text-[12px]"><input v-model="materialForm.status" type="radio" name="material-status" value="启用" class="accent-teal-700"> 启用</label>
              <label class="inline-flex items-center gap-1 text-[12px]"><input v-model="materialForm.status" type="radio" name="material-status" value="停用" class="accent-teal-700"> 停用</label>
            </div>
          </div>
        </div>
        <div v-if="materialFormError" class="mx-5 mb-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[11px] leading-5 text-red-700" role="alert">
          <AlertTriangle class="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <span>{{ materialFormError }}</span>
        </div>
        <div class="flex items-center justify-end gap-2 border-t border-slate-100 px-5 py-3">
          <button type="button" class="inline-flex h-9 items-center rounded-lg border border-slate-200 bg-white px-4 text-[12px] font-semibold text-slate-600 transition hover:border-slate-300" @click="closeModals">取消</button>
          <button type="button" class="inline-flex h-9 items-center rounded-lg bg-slate-950 px-5 text-[12px] font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400" :disabled="isSavingMaterial || !canManageSelectedFactory" @click="saveMaterial">{{ isSavingMaterial ? '保存中…' : '保存' }}</button>
        </div>
      </section>
    </div>

    <div
      v-if="showRequisitionModal || showBatchModal"
      class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-6"
      @click.self="closeModals"
    >
      <section class="w-full max-w-lg rounded-xl border border-slate-200 bg-white shadow-2xl">
        <div class="flex items-center gap-2 border-b border-slate-100 px-5 py-3.5">
          <span class="flex size-8 items-center justify-center rounded-lg bg-slate-900 text-white">
            <ClipboardCheck v-if="showRequisitionModal" class="size-4" aria-hidden="true" />
            <Boxes v-else class="size-4" aria-hidden="true" />
          </span>
          <div>
            <div class="text-[14px] font-bold text-slate-950">{{ showRequisitionModal ? '新建领料单' : '入库新批次' }}</div>
            <div class="text-[11px] text-slate-400">{{ showRequisitionModal ? 'New Requisition · LL-YYYYMMDD-NNN' : 'New Inventory Batch · 批次与库位' }}</div>
          </div>
          <button type="button" class="ml-auto flex size-7 items-center justify-center rounded-md text-slate-400 transition hover:bg-slate-100" aria-label="关闭弹窗" @click="closeModals">
            <X class="size-4" aria-hidden="true" />
          </button>
        </div>
        <div class="p-5">
          <div v-if="showRequisitionModal" class="grid gap-x-4 gap-y-3.5 sm:grid-cols-2">
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-slate-500">日期 <span class="text-red-500">*</span></span>
              <input type="date" value="2026-07-06" class="h-9 w-full rounded-md border border-slate-200 bg-white px-2.5 text-[12px] outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100">
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-slate-500">申请人 <span class="text-red-500">*</span></span>
              <input class="h-9 w-full rounded-md border border-slate-200 bg-white px-2.5 text-[12px] outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100" placeholder="如：李工">
            </label>
            <label class="block sm:col-span-2">
              <span class="mb-1 block text-[11px] font-medium text-slate-500">关联啤办单</span>
              <select class="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                <option>无关联</option>
                <option>PB-20260705-012（待生产）</option>
                <option>PB-20260705-009（生产中）</option>
              </select>
            </label>
            <label class="block sm:col-span-2">
              <span class="mb-1 block text-[11px] font-medium text-slate-500">原料型号 <span class="text-red-500">*</span></span>
              <input list="raw-material-list" class="h-9 w-full rounded-md border border-slate-200 bg-white px-2.5 text-[12px] outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100" placeholder="选择或输入原料">
              <datalist id="raw-material-list">
                <option v-for="row in rawMaterialRows" :key="row.code">{{ materialRowLabel(row) }}</option>
              </datalist>
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-slate-500">申请料重 (KG) <span class="text-red-500">*</span></span>
              <input type="number" class="h-9 w-full rounded-md border border-slate-200 bg-white px-2.5 text-[12px] outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100" placeholder="25.0">
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-slate-500">单价参考 (HKD/磅)</span>
              <input value="选择原料后显示" disabled class="h-9 w-full rounded-md border border-slate-200 bg-slate-50 px-2.5 text-[12px] text-slate-400 outline-none">
            </label>
          </div>
          <div v-else class="grid gap-x-4 gap-y-3.5 sm:grid-cols-2">
            <label class="block sm:col-span-2">
              <span class="mb-1 block text-[11px] font-medium text-slate-500">原料型号 <span class="text-red-500">*</span></span>
              <select class="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                <option v-for="row in rawMaterialRows" :key="row.code">{{ materialRowLabel(row) }}</option>
              </select>
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-slate-500">批次号 <span class="text-red-500">*</span></span>
              <input value="B-20260706-01" class="h-9 w-full rounded-md border border-slate-200 bg-white px-2.5 text-[12px] outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100">
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-slate-500">库位</span>
              <input placeholder="A-01" class="h-9 w-full rounded-md border border-slate-200 bg-white px-2.5 text-[12px] outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100">
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-slate-500">入库日期</span>
              <input type="date" value="2026-07-06" class="h-9 w-full rounded-md border border-slate-200 bg-white px-2.5 text-[12px] outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100">
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-slate-500">初始重量 (KG) <span class="text-red-500">*</span></span>
              <input type="number" placeholder="100.0" class="h-9 w-full rounded-md border border-slate-200 bg-white px-2.5 text-[12px] outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100">
            </label>
          </div>
        </div>
        <div class="flex items-center justify-end gap-2 border-t border-slate-100 px-5 py-3">
          <button type="button" class="inline-flex h-9 items-center rounded-lg border border-slate-200 bg-white px-4 text-[12px] font-semibold text-slate-600 transition hover:border-slate-300" @click="closeModals">取消</button>
          <button type="button" :disabled="!canManageSelectedFactory" class="inline-flex h-9 items-center rounded-lg bg-slate-950 px-5 text-[12px] font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300" @click="saveSecondaryModal">
            {{ showRequisitionModal ? '保存并创建' : '保存批次' }}
          </button>
        </div>
      </section>
    </div>
  </main>
</template>

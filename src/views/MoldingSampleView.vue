<script setup lang="ts">
import { computed, onMounted, ref, watch, watchEffect, type Component } from 'vue'
import {
  Archive,
  ArrowLeft,
  CheckCircle2,
  Play,
  Plus,
  RotateCcw,
  Save,
  Send,
  ShieldCheck,
  XCircle,
} from '@lucide/vue'
import { useRoute } from 'vue-router'
import {
  factoryContexts,
  isProductionFactoryContextId,
  type ProductionFactoryContextId,
  type Tone,
} from '@/data/enterpriseMock'
import {
  getMoldingSampleRecord,
  moldingSampleFactoryRecords,
} from '@/data/moldingSampleWorkflowMock'
import {
  applyCostPreviewToItems,
  buildCompletionGate,
  buildMoldingSampleReportSummary,
  getMoldingSampleStatusTransition,
  isExternalMoldingSampleOrder,
  normalizeMoldingSamplePricingSettings,
  type MoldingSampleMaterialPrice,
} from '@/lib/moldingSampleBusiness'
import {
  moldingSampleMaterialPrices,
  moldingSampleRmbToHkdRate,
} from '@/data/moldingSampleCostMock'
import type {
  MoldingSampleAuditLog,
  MoldingSampleItem,
  MoldingSampleOrder,
  MoldingSampleRequisition,
  MoldingSampleRole,
  MoldingSampleStatus,
} from '@/types/moldingSample'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { useAppStore } from '@/stores/app'
import {
  moldingSampleApi,
  type InventoryBatchResponse,
  type InventoryMovementResponse,
  type MoldingSampleDetailResponse,
  type MoldingSampleStatusRequest,
  type RequisitionResponse,
  type SensitiveAuditLogResponse,
} from '@/api/moldingSample'
import { getApiErrorMessage } from '@/lib/http'

type RoleTabId = 'engineering' | 'supervisor' | 'manager' | 'warehouse' | 'production' | 'reports'

interface RoleTab {
  id: RoleTabId
  label: string
  role: MoldingSampleRole | '汇总'
  icon: Component
}

interface SummaryCard {
  label: string
  value: string
  detail: string
  tone: Tone
}

interface EditableMaterialPrice {
  material: string
  unit_price: string | number
  notes: string
}

interface PinChangeDraft {
  old_pin: string
  new_pin: string
  confirm_pin: string
}

const route = useRoute()
const appStore = useAppStore()

const today = '2026-07-01'
const activeTab = ref<RoleTabId>('engineering')
const rejectReason = ref('资料不齐，请补充用料或交期说明。')
const supervisorPin = ref('')
const managerPin = ref('')
const productionProblem = ref('现场反馈：请工程确认色粉比例。')
const actionMessage = ref('')
const activeReportTab = ref<'materials' | 'injection' | 'total'>('materials')

const orderOverrides = ref<Record<string, Partial<MoldingSampleOrder>>>({})
const itemOverrides = ref<Record<string, Record<string, Partial<MoldingSampleItem>>>>({})
const auditOverrides = ref<Record<string, MoldingSampleAuditLog[]>>({})
const problemOverrides = ref<Record<string, string[]>>({})

const appliedMaterialPrices = ref<MoldingSampleMaterialPrice[]>(clonePrices(moldingSampleMaterialPrices))
const appliedRmbToHkdRate = ref(moldingSampleRmbToHkdRate)
const editableMaterialPrices = ref<EditableMaterialPrice[]>(createEditablePrices(moldingSampleMaterialPrices))
const editableRmbToHkdRate = ref(String(moldingSampleRmbToHkdRate))
const pricingErrors = ref<string[]>([])
const apiRecords = ref<MoldingSampleDetailResponse[]>([])
const apiRecord = ref<MoldingSampleDetailResponse | null>(null)
const apiRequisitions = ref<RequisitionResponse[]>([])
const apiInventoryBatches = ref<InventoryBatchResponse[]>([])
const apiInventoryMovements = ref<InventoryMovementResponse[]>([])
const apiSensitiveAuditLogs = ref<SensitiveAuditLogResponse[]>([])
const selectedInventoryBatchIds = ref<Record<string, string>>({})
const inventoryBatchDraft = ref({
  material: '',
  batch_no: '',
  location: '试啤仓',
  initial_weight_kg: '5',
})
const supervisorPinResetDraft = ref({
  supervisor_name: '李主管',
  new_pin: '1234',
})
const supervisorPinChangeDraft = ref<PinChangeDraft>({
  old_pin: '',
  new_pin: '',
  confirm_pin: '',
})
const managerPinChangeDraft = ref<PinChangeDraft>({
  old_pin: '',
  new_pin: '',
  confirm_pin: '',
})
const apiState = ref<'checking' | 'connected' | 'empty' | 'fallback'>('checking')
const apiMessage = ref('正在检查后端 API...')

const roleTabs: RoleTab[] = [
  { id: 'engineering', label: '工程部', role: '工程部', icon: Send },
  { id: 'supervisor', label: '主管', role: '主管', icon: ShieldCheck },
  { id: 'manager', label: '经理', role: '经理', icon: CheckCircle2 },
  { id: 'warehouse', label: '仓库', role: '仓库', icon: Archive },
  { id: 'production', label: '啤机部', role: '啤机部', icon: Play },
  { id: 'reports', label: '汇总', role: '汇总', icon: Save },
]

const statusTones: Record<MoldingSampleStatus, Tone> = {
  待审核: 'amber',
  待经理审核: 'blue',
  待生产: 'teal',
  生产中: 'amber',
  已完成: 'green',
  已驳回: 'red',
}

const toneClasses: Record<Tone, string> = {
  teal: 'border-teal-100 bg-teal-50 text-teal-800',
  blue: 'border-blue-100 bg-blue-50 text-blue-800',
  amber: 'border-amber-100 bg-amber-50 text-amber-800',
  red: 'border-red-100 bg-red-50 text-red-800',
  slate: 'border-slate-200 bg-slate-50 text-slate-700',
  green: 'border-emerald-100 bg-emerald-50 text-emerald-800',
}

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
  factoryContexts.find((factory) => factory.id === selectedFactoryId.value) ?? factoryContexts[1],
)
const fallbackRecord = computed(() => getMoldingSampleRecord(selectedFactoryId.value))
const activeRecord = computed(() => {
  if (apiRecord.value) {
    return {
      factory_id: apiRecord.value.order.factory_id,
      order: apiRecord.value.order,
      items: apiRecord.value.items,
      audit_logs: apiRecord.value.audit_logs,
      requisitions: apiRequisitions.value,
      problems: [],
    }
  }

  return fallbackRecord.value
})
const activeOrder = computed<MoldingSampleOrder>(() => ({
  ...activeRecord.value.order,
  ...(orderOverrides.value[activeRecord.value.order.id] ?? {}),
}))
const activeItems = computed<MoldingSampleItem[]>(() => {
  const overrides = itemOverrides.value[activeOrder.value.id] ?? {}
  const mergedItems = activeRecord.value.items.map((item) => ({
    ...item,
    ...(overrides[item.id] ?? {}),
  }))

  return applyCostPreviewToItems(
    mergedItems,
    appliedMaterialPrices.value,
    appliedRmbToHkdRate.value,
    isExternalOrder.value,
  )
})
const activeAuditLogs = computed<MoldingSampleAuditLog[]>(() => [
  ...(auditOverrides.value[activeOrder.value.id] ?? []),
  ...activeRecord.value.audit_logs,
])
const activeProblems = computed(() => [
  ...activeRecord.value.problems.map((problem) => problem.description),
  ...(problemOverrides.value[activeOrder.value.id] ?? []),
])
const activeRequisitions = computed(() => activeRecord.value.requisitions)
const activeInventoryBatches = computed(() => apiInventoryBatches.value)
const activeInventoryMovements = computed(() => apiInventoryMovements.value)
const activeSensitiveAuditLogs = computed(() => apiSensitiveAuditLogs.value)
const warehouseMaterials = computed(() => Array.from(new Set(activeItems.value.map((item) => item.material).filter(Boolean))))
const isExternalOrder = computed(() => isExternalMoldingSampleOrder(activeOrder.value))
const completionGate = computed(() => buildCompletionGate(activeOrder.value, activeItems.value))
const reportSummary = computed(() => buildMoldingSampleReportSummary(activeOrder.value, activeItems.value))
const isProductionEditable = computed(() => !isExternalOrder.value && activeOrder.value.status === '生产中')
const isWarehouseEditable = computed(() =>
  !isExternalOrder.value && ['待生产', '生产中'].includes(activeOrder.value.status),
)

const factoryQueue = computed(() =>
  (apiRecords.value.length
    ? apiRecords.value.map((record) => ({
      factory_id: record.order.factory_id as ProductionFactoryContextId,
      order: record.order,
      items: record.items,
      audit_logs: record.audit_logs,
      requisitions: [],
      problems: [],
    }))
    : Object.values(moldingSampleFactoryRecords)
  ).map((record) => {
    const order = {
      ...record.order,
      ...(orderOverrides.value[record.order.id] ?? {}),
    }

    return {
      factory_id: record.factory_id,
      order,
      item_count: record.items.length,
      blocked_count: buildCompletionGate(order, record.items).missing_item_ids.length,
    }
  }),
)

function inventoryBatchesForMaterial(material: string) {
  return activeInventoryBatches.value.filter((batch) => batch.material === material)
}

function defaultInventoryBatchId(requisition: MoldingSampleRequisition) {
  const selectedBatchId = selectedInventoryBatchIds.value[requisition.id]
  if (selectedBatchId) {
    return selectedBatchId
  }

  return inventoryBatchesForMaterial(requisition.material)
    .find((batch) => batch.available_weight_kg >= (requisition.requested_weight_kg ?? 0))?.id ?? ''
}

function syncInventoryBatchDraftMaterial() {
  if (!inventoryBatchDraft.value.material) {
    inventoryBatchDraft.value.material = activeItems.value[0]?.material ?? ''
  }
}

function syncSupervisorPinResetDraft() {
  if (!supervisorPinResetDraft.value.supervisor_name) {
    supervisorPinResetDraft.value.supervisor_name = activeOrder.value.supervisor || '李主管'
  }
}

const summaryCards = computed<SummaryCard[]>(() => [
  {
    label: '当前状态',
    value: activeOrder.value.status,
    detail: isExternalOrder.value ? '外厂 / 模厂自动完成路径' : '内部生产路径',
    tone: statusTones[activeOrder.value.status],
  },
  {
    label: '明细行',
    value: String(activeItems.value.length),
    detail: `${activeOrder.value.client_name} · ${activeOrder.value.product_name}`,
    tone: 'teal',
  },
  {
    label: '完成卡点',
    value: completionGate.value.can_complete ? '通过' : `${completionGate.value.missing_item_ids.length} 项`,
    detail: completionGate.value.message,
    tone: completionGate.value.can_complete ? 'green' : 'red',
  },
  {
    label: '总费用',
    value: `${reportSummary.value.total_cost.toFixed(2)} HKD`,
    detail: `料费 ${reportSummary.value.total_material_cost.toFixed(2)} · 啤办费 ${reportSummary.value.total_injection_cost.toFixed(2)}`,
    tone: reportSummary.value.archive_ready ? 'green' : 'blue',
  },
])

const engineeringEditable = computed(() => ['待审核', '已驳回'].includes(activeOrder.value.status))
const managerCanReview = computed(() => activeOrder.value.status === '待经理审核')
const supervisorCanReview = computed(() => activeOrder.value.status === '待审核')

function clonePrices(prices: MoldingSampleMaterialPrice[]) {
  return prices.map((price) => ({ ...price }))
}

function createEditablePrices(prices: MoldingSampleMaterialPrice[]): EditableMaterialPrice[] {
  return prices.map((price) => ({
    material: price.material,
    unit_price: price.unit_price,
    notes: price.notes ?? '',
  }))
}

function setApiRecord(record: MoldingSampleDetailResponse | null) {
  apiRecord.value = record

  if (record) {
    orderOverrides.value = {
      ...orderOverrides.value,
      [record.order.id]: {},
    }
    itemOverrides.value = {
      ...itemOverrides.value,
      [record.order.id]: {},
    }
    auditOverrides.value = {
      ...auditOverrides.value,
      [record.order.id]: [],
    }
  }
}

async function refreshActiveRequisitions() {
  if (!apiRecord.value) {
    apiRequisitions.value = []
    return
  }

  apiRequisitions.value = await moldingSampleApi.listRequisitions(apiRecord.value.order.id)
}

async function refreshWarehouseData() {
  if (!apiRecord.value) {
    apiRequisitions.value = []
    apiInventoryBatches.value = []
    apiInventoryMovements.value = []
    selectedInventoryBatchIds.value = {}
    return
  }

  const [requisitions, inventoryBatches, inventoryMovements] = await Promise.all([
    moldingSampleApi.listRequisitions(apiRecord.value.order.id),
    moldingSampleApi.listInventoryBatches(),
    moldingSampleApi.listInventoryMovements(),
  ])
  apiRequisitions.value = requisitions
  apiInventoryBatches.value = inventoryBatches
  apiInventoryMovements.value = inventoryMovements
  syncInventoryBatchDraftMaterial()
}

async function refreshSensitiveAuditLogs() {
  if (apiState.value === 'fallback') {
    apiSensitiveAuditLogs.value = []
    return
  }

  apiSensitiveAuditLogs.value = await moldingSampleApi.listSensitiveAuditLogs()
}

async function loadApiData() {
  apiState.value = 'checking'
  apiMessage.value = '正在检查后端 API...'

  try {
    const [records, pricing, sensitiveAuditLogs] = await Promise.all([
      moldingSampleApi.listOrders(),
      moldingSampleApi.getMaterialPrices(),
      moldingSampleApi.listSensitiveAuditLogs(),
    ])
    apiRecords.value = records
    apiSensitiveAuditLogs.value = sensitiveAuditLogs
    appliedMaterialPrices.value = clonePrices(pricing.prices)
    appliedRmbToHkdRate.value = pricing.rmb_to_hkd_rate
    editableMaterialPrices.value = createEditablePrices(pricing.prices)
    editableRmbToHkdRate.value = String(pricing.rmb_to_hkd_rate)

    const selectedRecord = records.find((record) => record.order.factory_id === selectedFactoryId.value) ?? records[0] ?? null
    setApiRecord(selectedRecord)
    syncSupervisorPinResetDraft()
    await refreshWarehouseData()
    apiState.value = selectedRecord ? 'connected' : 'empty'
    apiMessage.value = selectedRecord
      ? '已连接后端 API，当前操作会写入数据库。'
      : '后端 API 可用，但还没有啤办单数据。'
  }
  catch (error) {
    apiRecords.value = []
    apiRequisitions.value = []
    apiInventoryBatches.value = []
    apiInventoryMovements.value = []
    apiSensitiveAuditLogs.value = []
    selectedInventoryBatchIds.value = {}
    setApiRecord(null)
    apiState.value = 'fallback'
    apiMessage.value = `后端 API 暂不可用，当前使用前端 mock：${getApiErrorMessage(error)}`
  }
}

async function syncCurrentMockToApi() {
  const source = fallbackRecord.value

  try {
    const created = await moldingSampleApi.createOrder({
      order: source.order,
      items: source.items,
    })
    await loadApiData()
    setApiRecord(created)
    actionMessage.value = '当前示例单据已同步到后端数据库。'
  }
  catch (error) {
    actionMessage.value = `同步失败：${getApiErrorMessage(error)}`
  }
}

function readInputValue(event: Event) {
  return (event.target as HTMLInputElement).value
}

function parseOptionalNumber(value: string) {
  if (value.trim() === '') {
    return null
  }

  const parsed = Number(value)

  return Number.isFinite(parsed) ? parsed : null
}

function formatBlank(value: string | number | null | undefined, fallback = '待填写') {
  return value === null || value === undefined || value === '' ? fallback : String(value)
}

function formatMoney(value: number | null | undefined) {
  return value === null || value === undefined ? '待计算' : `${value.toFixed(2)} HKD`
}

function formatWeight(value: number | null | undefined) {
  return value === null || value === undefined ? '待填写' : `${value} KG`
}

function formatMovementWeight(value: number) {
  return `${value > 0 ? '+' : ''}${value} KG`
}

function setOrderPatch(patch: Partial<MoldingSampleOrder>) {
  orderOverrides.value = {
    ...orderOverrides.value,
    [activeOrder.value.id]: {
      ...(orderOverrides.value[activeOrder.value.id] ?? {}),
      ...patch,
      updated_at: `${today} 09:00`,
    },
  }
}

function patchItem(itemId: string, patch: Partial<MoldingSampleItem>) {
  const currentOrderOverrides = itemOverrides.value[activeOrder.value.id] ?? {}

  itemOverrides.value = {
    ...itemOverrides.value,
    [activeOrder.value.id]: {
      ...currentOrderOverrides,
      [itemId]: {
        ...(currentOrderOverrides[itemId] ?? {}),
        ...patch,
      },
    },
  }
}

function appendAudit(
  action: string,
  role: MoldingSampleRole,
  actorName: string,
  fromStatus: MoldingSampleStatus,
  toStatus: MoldingSampleStatus,
  reason: string,
  tone: Tone,
) {
  const nextAudit: MoldingSampleAuditLog = {
    id: `${activeOrder.value.id}-audit-${Date.now()}`,
    order_id: activeOrder.value.id,
    action,
    actor_name: actorName,
    actor_role: role,
    decision: action.includes('驳回') ? '驳回' : action.includes('重提') ? '重提' : action.includes('开始') ? '开始处理' : action.includes('完成') ? '完成' : '通过',
    from_status: fromStatus,
    to_status: toStatus,
    reason,
    created_at: `${today} 10:30`,
    tone,
  }

  auditOverrides.value = {
    ...auditOverrides.value,
    [activeOrder.value.id]: [
      nextAudit,
      ...(auditOverrides.value[activeOrder.value.id] ?? []),
    ],
  }
}

function commitCurrentCostPreview(forceMaterialAmount = false) {
  const costedItems = applyCostPreviewToItems(
    activeItems.value,
    appliedMaterialPrices.value,
    appliedRmbToHkdRate.value,
    isExternalOrder.value,
    forceMaterialAmount,
  )
  const nextOverrides = costedItems.reduce<Record<string, Partial<MoldingSampleItem>>>((acc, item) => {
    acc[item.id] = {
      actual_weight_kg: item.actual_weight_kg,
      actual_amount_hkd: item.actual_amount_hkd,
      injection_cost_hkd: item.injection_cost_hkd,
      exchange_rate_at_save: item.exchange_rate_at_save,
    }

    return acc
  }, {})

  itemOverrides.value = {
    ...itemOverrides.value,
    [activeOrder.value.id]: {
      ...(itemOverrides.value[activeOrder.value.id] ?? {}),
      ...nextOverrides,
    },
  }
}

async function runTransition(
  action: Parameters<typeof getMoldingSampleStatusTransition>[0]['action'],
  role: MoldingSampleRole,
  actorName: string,
  reason = '',
) {
  if (action === '标记完成' && !completionGate.value.can_complete) {
    actionMessage.value = completionGate.value.message
    return
  }

  const pin = role === '主管'
    ? supervisorPin.value.trim()
    : role === '经理'
      ? managerPin.value.trim()
      : ''

  if ((role === '主管' || role === '经理') && !pin) {
    actionMessage.value = `请输入${role} PIN 后再执行${action}。`
    return
  }

  if (apiRecord.value) {
    try {
      const payload: MoldingSampleStatusRequest = {
        action,
        reviewer_name: actorName,
        reviewer_role: role,
        reason,
        today,
      }
      if (pin) {
        payload.pin = pin
      }

      const updated = await moldingSampleApi.updateStatus(activeOrder.value.id, payload)
      setApiRecord(updated)
      await loadApiData()
      actionMessage.value = `${action}已写入后端。`
    }
    catch (error) {
      actionMessage.value = `后端状态流转失败：${getApiErrorMessage(error)}`
    }

    return
  }

  const fromStatus = activeOrder.value.status
  const transition = getMoldingSampleStatusTransition({
    order: activeOrder.value,
    action,
    actor_role: role,
    actor_name: actorName,
    reason,
    today,
  })

  if (!transition.allowed) {
    actionMessage.value = transition.message ?? '当前状态不允许执行此动作。'
    return
  }

  setOrderPatch({
    status: transition.next_status,
    completed_date: transition.completed_date,
    reject_reason: transition.reject_reason ?? (transition.next_status === '待审核' ? '' : activeOrder.value.reject_reason),
  })

  if (transition.next_status === '已完成') {
    commitCurrentCostPreview(true)
  }

  appendAudit(
    action,
    role,
    actorName,
    fromStatus,
    transition.next_status,
    reason || transition.message || `${actorName} 执行 ${action}`,
    transition.next_status === '已驳回' ? 'red' : transition.next_status === '已完成' ? 'green' : 'blue',
  )
  actionMessage.value = `${action}完成：${fromStatus} -> ${transition.next_status}`
}

function updateOrderTextField(field: keyof Pick<MoldingSampleOrder, 'product_name' | 'client_name' | 'order_number' | 'doc_number' | 'supervisor' | 'reason'>, value: string) {
  setOrderPatch({ [field]: value })
}

async function saveEngineeringChanges() {
  if (!engineeringEditable.value) {
    actionMessage.value = '当前状态已锁定，工程部不能保存改动。'
    return
  }

  if (!apiRecord.value) {
    actionMessage.value = '当前为前端 mock 数据，改动只保存在本页。'
    return
  }

  try {
    const updated = await moldingSampleApi.editOrder(activeOrder.value.id, {
      actor_name: activeOrder.value.eng_name || '工程部',
      actor_role: '工程部',
      order: activeOrder.value,
      items: activeItems.value,
    })
    setApiRecord(updated)
    await loadApiData()
    actionMessage.value = '工程部改动已写入后端。'
  }
  catch (error) {
    actionMessage.value = `工程部保存失败：${getApiErrorMessage(error)}`
  }
}

async function deleteCurrentOrder() {
  if (!engineeringEditable.value) {
    actionMessage.value = '当前状态已锁定，工程部不能删除。'
    return
  }

  if (!apiRecord.value) {
    actionMessage.value = '当前为前端 mock 数据，不能删除后端单据。'
    return
  }

  if (!globalThis.confirm?.(`确认删除啤办单 ${activeOrder.value.order_number || activeOrder.value.id}？`)) {
    return
  }

  try {
    await moldingSampleApi.deleteOrder(activeOrder.value.id, {
      actor_name: activeOrder.value.eng_name || '工程部',
      actor_role: '工程部',
    })
    apiRecord.value = null
    await loadApiData()
    actionMessage.value = '啤办单已从后端删除。'
  }
  catch (error) {
    actionMessage.value = `啤办单删除失败：${getApiErrorMessage(error)}`
  }
}

async function saveItemPatchToApi(itemId: string, patch: Partial<MoldingSampleItem>) {
  if (!apiRecord.value) {
    return
  }

  try {
    const updated = await moldingSampleApi.updateItems(activeOrder.value.id, {
      items: [{ id: itemId, ...patch }],
    })
    setApiRecord(updated)
  }
  catch (error) {
    actionMessage.value = `后端明细保存失败：${getApiErrorMessage(error)}`
  }
}

async function updateItemNumber(itemId: string, field: keyof Pick<MoldingSampleItem, 'collected_weight_kg' | 'actual_weight_kg' | 'injection_cost'>, value: string) {
  const patch = { [field]: parseOptionalNumber(value) }
  patchItem(itemId, patch)
  await saveItemPatchToApi(itemId, patch)
}

async function updateItemText(itemId: string, field: keyof Pick<MoldingSampleItem, 'receipt_no' | 'notes'>, value: string) {
  const patch = { [field]: value }
  patchItem(itemId, patch)

  if (field === 'receipt_no') {
    await saveItemPatchToApi(itemId, patch)
  }
}

async function fillWarehouseSample() {
  const patches = activeItems.value.map((item, index) => ({
    id: item.id,
    receipt_no: item.receipt_no || `LL-${today.replaceAll('-', '')}-${String(index + 1).padStart(3, '0')}`,
    collected_weight_kg: item.collected_weight_kg ?? item.required_material_kg,
  }))

  patches.forEach((patch) => {
    patchItem(patch.id, {
      receipt_no: patch.receipt_no,
      collected_weight_kg: patch.collected_weight_kg,
    })
  })

  if (apiRecord.value) {
    try {
      const updated = await moldingSampleApi.updateItems(activeOrder.value.id, { items: patches })
      setApiRecord(updated)
      actionMessage.value = '仓库领料已写入后端。'
      return
    }
    catch (error) {
      actionMessage.value = `仓库领料保存失败：${getApiErrorMessage(error)}`
      return
    }
  }

  actionMessage.value = '仓库领料示例已回填。'
}

async function createRequisitionsFromItems() {
  if (!isWarehouseEditable.value) {
    actionMessage.value = '当前状态不能生成领料单。'
    return
  }

  if (!apiRecord.value) {
    actionMessage.value = '当前为前端 mock 数据，不能生成后端领料单。'
    return
  }

  const requisitionItems = activeItems.value
    .map((item) => ({
      item,
      requestedWeight: item.collected_weight_kg ?? item.required_material_kg ?? 0,
      notes: `${item.mold_id} · ${item.mold_name}`,
    }))
    .filter((entry) => {
      if (entry.requestedWeight <= 0) {
        return false
      }

      return !activeRequisitions.value.some((requisition) =>
        requisition.material === entry.item.material && requisition.notes === entry.notes
      )
    })

  if (!requisitionItems.length) {
    actionMessage.value = activeRequisitions.value.length
      ? '当前明细已生成领料单，无需重复生成。'
      : '没有可生成领料单的用料重量。'
    return
  }

  try {
    const created = []
    for (const entry of requisitionItems) {
      const requisition = await moldingSampleApi.createRequisition({
        date: today,
        order_id: activeOrder.value.id,
        material: entry.item.material,
        requested_weight_kg: entry.requestedWeight,
        applicant: activeOrder.value.eng_name || '工程部',
        notes: entry.notes,
      })
      created.push({ requisition, item: entry.item, requestedWeight: entry.requestedWeight })
    }

    const updated = await moldingSampleApi.updateItems(activeOrder.value.id, {
      items: created.map((entry) => ({
        id: entry.item.id,
        receipt_no: entry.requisition.req_number,
        collected_weight_kg: entry.requestedWeight,
      })),
    })
    setApiRecord(updated)
    await refreshWarehouseData()
    actionMessage.value = `已生成 ${created.length} 张后端领料单。`
  }
  catch (error) {
    actionMessage.value = `生成领料单失败：${getApiErrorMessage(error)}`
  }
}

async function createInventoryBatchFromDraft() {
  if (!apiRecord.value) {
    actionMessage.value = '当前为前端 mock 数据，不能新增库存批次。'
    return
  }

  const initialWeight = Number(inventoryBatchDraft.value.initial_weight_kg)
  if (!inventoryBatchDraft.value.material || !inventoryBatchDraft.value.batch_no || !Number.isFinite(initialWeight) || initialWeight <= 0) {
    actionMessage.value = '请补齐原料、批次号和有效库存重量。'
    return
  }

  try {
    await moldingSampleApi.createInventoryBatch({
      material: inventoryBatchDraft.value.material,
      batch_no: inventoryBatchDraft.value.batch_no,
      location: inventoryBatchDraft.value.location,
      initial_weight_kg: initialWeight,
    })
    inventoryBatchDraft.value.batch_no = ''
    inventoryBatchDraft.value.initial_weight_kg = '5'
    await refreshWarehouseData()
    actionMessage.value = '库存批次已新增。'
  }
  catch (error) {
    actionMessage.value = `新增库存批次失败：${getApiErrorMessage(error)}`
  }
}

async function markRequisitionIssued(requisition: MoldingSampleRequisition) {
  if (!apiRecord.value) {
    actionMessage.value = '当前为前端 mock 数据，不能更新后端领料单。'
    return
  }

  const inventoryBatchId = defaultInventoryBatchId(requisition)
  if (!inventoryBatchId) {
    actionMessage.value = '请选择可用库存批次后再出库。'
    return
  }

  try {
    await moldingSampleApi.updateRequisitionStatus(requisition.id, {
      status: '已出库',
      issued_at: `${today} 15:30`,
      inventory_batch_id: inventoryBatchId,
    })
    await refreshWarehouseData()
    actionMessage.value = '领料单已标记出库。'
  }
  catch (error) {
    actionMessage.value = `领料单出库失败：${getApiErrorMessage(error)}`
  }
}

async function deleteRequisitionRow(requisitionId: string) {
  if (!apiRecord.value) {
    actionMessage.value = '当前为前端 mock 数据，不能删除后端领料单。'
    return
  }

  if (!globalThis.confirm?.('确认删除这张领料单？')) {
    return
  }

  try {
    await moldingSampleApi.deleteRequisition(requisitionId)
    await refreshWarehouseData()
    actionMessage.value = '领料单已删除。'
  }
  catch (error) {
    actionMessage.value = `领料单删除失败：${getApiErrorMessage(error)}`
  }
}

async function fillProductionSample() {
  const patches = activeItems.value.map((item, index) => ({
    id: item.id,
    actual_weight_kg: item.actual_weight_kg ?? roundTwo((item.collected_weight_kg ?? item.required_material_kg ?? 1) * 0.96),
    injection_cost: item.injection_cost ?? 80 + index * 20,
  }))

  patches.forEach((patch) => {
    patchItem(patch.id, {
      actual_weight_kg: patch.actual_weight_kg,
      injection_cost: patch.injection_cost,
    })
  })

  if (apiRecord.value) {
    try {
      const updated = await moldingSampleApi.updateItems(activeOrder.value.id, { items: patches })
      setApiRecord(updated)
      actionMessage.value = '啤机部回填已写入后端。'
      return
    }
    catch (error) {
      actionMessage.value = `啤机部回填保存失败：${getApiErrorMessage(error)}`
      return
    }
  }

  actionMessage.value = '啤机部实际用料和啤办费示例已回填。'
}

function roundTwo(value: number) {
  return Math.round(value * 100) / 100
}

function updateMaterialPrice(index: number, field: keyof EditableMaterialPrice, value: string) {
  editableMaterialPrices.value = editableMaterialPrices.value.map((price, priceIndex) =>
    priceIndex === index ? { ...price, [field]: value } : price,
  )
}

function addMaterialPriceRow() {
  editableMaterialPrices.value = [
    ...editableMaterialPrices.value,
    { material: '', unit_price: '', notes: '' },
  ]
}

async function applyPricingSettings() {
  if ((apiState.value === 'connected' || apiState.value === 'empty') && !managerPin.value.trim()) {
    actionMessage.value = '请输入经理 PIN 后保存价格口径。'
    return
  }

  const normalized = normalizeMoldingSamplePricingSettings(
    editableMaterialPrices.value,
    editableRmbToHkdRate.value,
    appliedRmbToHkdRate.value,
  )

  appliedMaterialPrices.value = clonePrices(normalized.prices)
  appliedRmbToHkdRate.value = normalized.rmb_to_hkd_rate
  editableMaterialPrices.value = createEditablePrices(normalized.prices)
  editableRmbToHkdRate.value = String(normalized.rmb_to_hkd_rate)
  pricingErrors.value = normalized.errors

  if (apiState.value === 'connected' || apiState.value === 'empty') {
    try {
      const updated = await moldingSampleApi.updateMaterialPrices({
        prices: normalized.prices,
        rmb_to_hkd_rate: normalized.rmb_to_hkd_rate,
        manager_name: '王经理',
        manager_pin: managerPin.value.trim(),
      })
      appliedMaterialPrices.value = clonePrices(updated.prices)
      appliedRmbToHkdRate.value = updated.rmb_to_hkd_rate
      editableMaterialPrices.value = createEditablePrices(updated.prices)
      editableRmbToHkdRate.value = String(updated.rmb_to_hkd_rate)
      await loadApiData()
      actionMessage.value = normalized.errors.length ? '价格口径已写入后端，但存在需要修正的提示。' : '价格口径已写入后端。'
      return
    }
    catch (error) {
      actionMessage.value = `价格口径后端保存失败：${getApiErrorMessage(error)}`
      return
    }
  }

  commitCurrentCostPreview(false)
  appendAudit('经理保存价格表', '经理', '王经理', activeOrder.value.status, activeOrder.value.status, '经理维护原料单价和汇率。', 'blue')
  actionMessage.value = normalized.errors.length ? '价格口径已保存，但存在需要修正的提示。' : '价格口径已保存。'
}

async function resetSupervisorPin() {
  if (apiState.value === 'fallback') {
    actionMessage.value = '当前为前端 mock 数据，不能重置后端主管 PIN。'
    return
  }

  if (!managerPin.value.trim()) {
    actionMessage.value = '请输入经理 PIN 后重置主管 PIN。'
    return
  }

  const supervisorName = supervisorPinResetDraft.value.supervisor_name.trim()
  const newPin = supervisorPinResetDraft.value.new_pin.trim()
  if (!supervisorName || newPin.length < 4) {
    actionMessage.value = '请填写主管姓名，并输入至少 4 位的新 PIN。'
    return
  }

  try {
    const updated = await moldingSampleApi.resetSupervisorPin({
      manager_name: '王经理',
      manager_pin: managerPin.value.trim(),
      supervisor_name: supervisorName,
      new_pin: newPin,
    })
    supervisorPinResetDraft.value.new_pin = '1234'
    await refreshSensitiveAuditLogs()
    actionMessage.value = `${updated.name} 的主管 PIN 已重置，并要求首次修改。`
  }
  catch (error) {
    actionMessage.value = `重置主管 PIN 失败：${getApiErrorMessage(error)}`
  }
}

async function changeWorkbenchPin(role: '主管' | '经理') {
  if (apiState.value === 'fallback') {
    actionMessage.value = '当前为前端 mock 数据，不能修改后端 PIN。'
    return
  }

  const draft = role === '主管' ? supervisorPinChangeDraft.value : managerPinChangeDraft.value
  const oldPin = draft.old_pin.trim()
  const newPin = draft.new_pin.trim()
  const confirmPin = draft.confirm_pin.trim()
  const name = role === '主管' ? (activeOrder.value.supervisor || '李主管') : '王经理'

  if (!oldPin || newPin.length < 4) {
    actionMessage.value = `${role}旧 PIN 和至少 4 位的新 PIN 都必须填写。`
    return
  }
  if (newPin !== confirmPin) {
    actionMessage.value = `${role}两次输入的新 PIN 不一致。`
    return
  }
  if (newPin === oldPin) {
    actionMessage.value = `${role}新 PIN 不能与旧 PIN 相同。`
    return
  }

  try {
    const updated = await moldingSampleApi.changePin({
      name,
      role,
      old_pin: oldPin,
      new_pin: newPin,
    })
    draft.old_pin = ''
    draft.new_pin = ''
    draft.confirm_pin = ''
    if (role === '主管') {
      supervisorPin.value = newPin
    }
    else {
      managerPin.value = newPin
    }
    await refreshSensitiveAuditLogs()
    actionMessage.value = `${updated.name} 的 PIN 已修改，可以继续执行${role}操作。`
  }
  catch (error) {
    actionMessage.value = `${role} PIN 修改失败：${getApiErrorMessage(error)}`
  }
}

function resetPricingSettings() {
  appliedMaterialPrices.value = clonePrices(moldingSampleMaterialPrices)
  appliedRmbToHkdRate.value = moldingSampleRmbToHkdRate
  editableMaterialPrices.value = createEditablePrices(moldingSampleMaterialPrices)
  editableRmbToHkdRate.value = String(moldingSampleRmbToHkdRate)
  pricingErrors.value = []
  commitCurrentCostPreview(false)
  actionMessage.value = '价格口径已恢复默认。'
}

function addProblem() {
  const description = productionProblem.value.trim()

  if (!description) {
    return
  }

  problemOverrides.value = {
    ...problemOverrides.value,
    [activeOrder.value.id]: [
      ...(problemOverrides.value[activeOrder.value.id] ?? []),
      description,
    ],
  }
  productionProblem.value = ''
  actionMessage.value = '问题反馈已记录。'
}

onMounted(() => {
  void loadApiData()
})

watch(selectedFactoryId, () => {
  if (apiRecords.value.length) {
    const selectedRecord = apiRecords.value.find((record) => record.order.factory_id === selectedFactoryId.value) ?? null
    setApiRecord(selectedRecord)
    void refreshWarehouseData()
    apiState.value = selectedRecord ? 'connected' : 'empty'
    apiMessage.value = selectedRecord ? '已连接后端 API，当前操作会写入数据库。' : '当前厂区暂无后端单据，可同步示例单据。'
  }
})

watchEffect(() => {
  appStore.setActiveFactory(selectedFactoryId.value)
})
</script>

<template>
  <main class="min-h-screen bg-slate-100 px-4 py-6 text-slate-950 sm:px-6 xl:px-10">
    <div class="mx-auto max-w-[1680px] space-y-5">
      <div class="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <RouterLink
            to="/modules"
            class="inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-slate-950"
          >
            <ArrowLeft class="size-4" aria-hidden="true" />
            工程部模块
          </RouterLink>
          <div class="mt-3 flex flex-wrap items-center gap-3">
            <h1 class="text-3xl font-semibold tracking-tight">啤办单工作台</h1>
            <StatusPill :label="activeOrder.status" :tone="statusTones[activeOrder.status]" />
            <StatusPill :label="isExternalOrder ? '外厂路径' : '内部生产'" :tone="isExternalOrder ? 'slate' : 'teal'" />
          </div>
          <p class="mt-2 text-sm text-slate-600">
            {{ activeFactory.name }} · {{ activeOrder.order_number }} {{ activeOrder.product_name }} · {{ activeOrder.client_name }}
          </p>
        </div>

        <div class="grid grid-cols-2 gap-3 md:grid-cols-4 xl:w-[820px]">
          <article
            v-for="card in summaryCards"
            :key="card.label"
            class="min-h-[92px] rounded-lg border bg-white p-4"
            :class="toneClasses[card.tone]"
          >
            <p class="text-xs font-medium opacity-80">{{ card.label }}</p>
            <p class="mt-1 text-xl font-semibold text-slate-950">{{ card.value }}</p>
            <p class="mt-1 line-clamp-2 text-xs opacity-75">{{ card.detail }}</p>
          </article>
        </div>
      </div>

      <div class="overflow-x-auto rounded-lg border border-slate-200 bg-white p-1">
        <div class="flex min-w-max gap-1">
          <button
            v-for="tab in roleTabs"
            :key="tab.id"
            type="button"
            class="inline-flex h-10 items-center gap-2 rounded-md px-4 text-sm font-semibold transition-colors"
            :class="activeTab === tab.id ? 'bg-slate-950 text-white' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-950'"
            @click="activeTab = tab.id"
          >
            <component :is="tab.icon" class="size-4" aria-hidden="true" />
            {{ tab.label }}
          </button>
        </div>
      </div>

      <div
        class="flex flex-col gap-3 rounded-lg border px-4 py-3 text-sm md:flex-row md:items-center md:justify-between"
        :class="apiState === 'connected'
          ? 'border-emerald-100 bg-emerald-50 text-emerald-800'
          : apiState === 'empty'
            ? 'border-blue-100 bg-blue-50 text-blue-800'
            : apiState === 'checking'
              ? 'border-slate-200 bg-white text-slate-600'
              : 'border-amber-100 bg-amber-50 text-amber-800'"
      >
        <div class="flex flex-wrap items-center gap-2">
          <StatusPill
            :label="apiState === 'connected' ? '后端已连接' : apiState === 'empty' ? '后端空库' : apiState === 'checking' ? '检查中' : '前端 mock'"
            :tone="apiState === 'connected' ? 'green' : apiState === 'empty' ? 'blue' : apiState === 'checking' ? 'slate' : 'amber'"
            compact
          />
          <span>{{ apiMessage }}</span>
        </div>
        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            class="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700"
            @click="loadApiData"
          >
            <RotateCcw class="size-4" aria-hidden="true" />
            刷新后端
          </button>
          <button
            type="button"
            :disabled="apiRecord !== null"
            class="inline-flex h-9 items-center justify-center gap-2 rounded-lg border px-3 text-sm font-semibold disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-white/60 disabled:text-slate-400"
            :class="apiRecord === null ? 'border-slate-950 bg-slate-950 text-white' : ''"
            @click="syncCurrentMockToApi"
          >
            <Save class="size-4" aria-hidden="true" />
            同步当前示例
          </button>
        </div>
      </div>

      <div class="grid gap-5 xl:grid-cols-[340px_minmax(0,1fr)]">
        <SectionPanel title="单据队列" subtitle="按当前厂区入口切换单据">
          <div class="space-y-3">
            <RouterLink
              v-for="entry in factoryQueue"
              :key="entry.order.id"
              :to="`/modules/molding-sample?factory=${entry.factory_id}`"
              class="block rounded-lg border p-4 transition-colors hover:border-slate-300 hover:bg-slate-50"
              :class="entry.factory_id === selectedFactoryId ? 'border-slate-950 bg-slate-50' : 'border-slate-200 bg-white'"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="font-semibold text-slate-950">{{ entry.order.order_number }} · {{ entry.order.product_name }}</p>
                  <p class="mt-1 text-xs text-slate-500">{{ entry.order.client_name }} · {{ entry.order.workshop || '未定车间' }}</p>
                </div>
                <StatusPill :label="entry.order.status" :tone="statusTones[entry.order.status]" compact />
              </div>
              <div class="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-600">
                <span>明细 {{ entry.item_count }}</span>
                <span>{{ entry.blocked_count ? `卡点 ${entry.blocked_count}` : '无完成卡点' }}</span>
              </div>
            </RouterLink>
          </div>
        </SectionPanel>

        <div class="space-y-5">
          <SectionPanel title="单头信息" subtitle="规格字段统一为 injection 啤办单口径">
            <div class="grid gap-4 lg:grid-cols-4">
              <div class="rounded-lg border border-slate-200 bg-white p-4">
                <p class="text-xs font-semibold text-slate-500">产品编号</p>
                <input
                  :value="activeOrder.order_number"
                  :disabled="!engineeringEditable"
                  class="mt-2 h-10 w-full rounded-md border border-slate-200 px-3 text-sm font-semibold disabled:bg-slate-50 disabled:text-slate-500"
                  @input="updateOrderTextField('order_number', readInputValue($event))"
                >
              </div>
              <div class="rounded-lg border border-slate-200 bg-white p-4">
                <p class="text-xs font-semibold text-slate-500">订单编号</p>
                <input
                  :value="activeOrder.doc_number"
                  :disabled="!engineeringEditable"
                  class="mt-2 h-10 w-full rounded-md border border-slate-200 px-3 text-sm font-semibold disabled:bg-slate-50 disabled:text-slate-500"
                  @input="updateOrderTextField('doc_number', readInputValue($event))"
                >
              </div>
              <div class="rounded-lg border border-slate-200 bg-white p-4">
                <p class="text-xs font-semibold text-slate-500">客户</p>
                <input
                  :value="activeOrder.client_name"
                  :disabled="!engineeringEditable"
                  class="mt-2 h-10 w-full rounded-md border border-slate-200 px-3 text-sm font-semibold disabled:bg-slate-50 disabled:text-slate-500"
                  @input="updateOrderTextField('client_name', readInputValue($event))"
                >
              </div>
              <div class="rounded-lg border border-slate-200 bg-white p-4">
                <p class="text-xs font-semibold text-slate-500">主管</p>
                <input
                  :value="activeOrder.supervisor"
                  :disabled="!engineeringEditable"
                  class="mt-2 h-10 w-full rounded-md border border-slate-200 px-3 text-sm font-semibold disabled:bg-slate-50 disabled:text-slate-500"
                  @input="updateOrderTextField('supervisor', readInputValue($event))"
                >
              </div>
            </div>

            <div class="mt-4 grid gap-4 lg:grid-cols-[1fr_260px_260px]">
              <label class="block rounded-lg border border-slate-200 bg-white p-4">
                <span class="text-xs font-semibold text-slate-500">产品名称</span>
                <input
                  :value="activeOrder.product_name"
                  :disabled="!engineeringEditable"
                  class="mt-2 h-10 w-full rounded-md border border-slate-200 px-3 text-sm font-semibold disabled:bg-slate-50 disabled:text-slate-500"
                  @input="updateOrderTextField('product_name', readInputValue($event))"
                >
              </label>
              <div class="rounded-lg border border-slate-200 bg-white p-4">
                <p class="text-xs font-semibold text-slate-500">阶段 / 用途</p>
                <p class="mt-2 text-sm font-semibold">{{ formatBlank(activeOrder.stage, '空') }} · {{ activeOrder.order_type }}</p>
              </div>
              <div class="rounded-lg border border-slate-200 bg-white p-4">
                <p class="text-xs font-semibold text-slate-500">车间 / 发至</p>
                <p class="mt-2 text-sm font-semibold">{{ activeOrder.workshop }} · {{ activeOrder.send_to || '内部' }}</p>
              </div>
            </div>

            <label class="mt-4 block rounded-lg border border-slate-200 bg-white p-4">
              <span class="text-xs font-semibold text-slate-500">原因 / 备注</span>
              <textarea
                :value="activeOrder.reason"
                :disabled="!engineeringEditable"
                rows="3"
                class="mt-2 w-full rounded-md border border-slate-200 px-3 py-2 text-sm leading-6 disabled:bg-slate-50 disabled:text-slate-500"
                @input="updateOrderTextField('reason', readInputValue($event))"
              />
            </label>

            <div v-if="activeOrder.reject_reason" class="mt-4 rounded-lg border border-red-100 bg-red-50 p-4 text-sm text-red-800">
              驳回原因：{{ activeOrder.reject_reason }}
            </div>
          </SectionPanel>

          <SectionPanel v-if="activeTab === 'engineering'" title="工程部工作台" subtitle="开单、返工、维护可编辑字段">
            <div class="grid gap-4 lg:grid-cols-[1fr_180px_180px_220px]">
              <div class="rounded-lg border border-slate-200 bg-white p-4">
                <h3 class="font-semibold">编辑权限</h3>
                <p class="mt-2 text-sm leading-6 text-slate-600">
                  当前状态 {{ activeOrder.status }}，工程部{{ engineeringEditable ? '可以编辑和重提' : '只读，需按审核或生产节点继续流转' }}。
                </p>
              </div>
              <button
                type="button"
                :disabled="!engineeringEditable"
                class="inline-flex min-h-12 items-center justify-center gap-2 rounded-lg border px-4 py-3 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                :class="engineeringEditable ? 'border-slate-950 bg-slate-950 text-white hover:bg-slate-800' : ''"
                @click="saveEngineeringChanges"
              >
                <Save class="size-4" aria-hidden="true" />
                保存改动
              </button>
              <button
                type="button"
                :disabled="!engineeringEditable"
                class="inline-flex min-h-12 items-center justify-center gap-2 rounded-lg border px-4 py-3 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                :class="engineeringEditable ? 'border-red-700 bg-red-700 text-white hover:bg-red-800' : ''"
                @click="deleteCurrentOrder"
              >
                <XCircle class="size-4" aria-hidden="true" />
                删除单据
              </button>
              <button
                type="button"
                :disabled="activeOrder.status !== '已驳回'"
                class="inline-flex min-h-12 items-center justify-center gap-2 rounded-lg border px-4 py-3 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                :class="activeOrder.status === '已驳回' ? 'border-slate-950 bg-slate-950 text-white hover:bg-slate-800' : ''"
                @click="runTransition('工程重提', '工程部', activeOrder.eng_name, '工程按驳回原因修正后重新提交。')"
              >
                <Send class="size-4" aria-hidden="true" />
                修改后重提
              </button>
            </div>
          </SectionPanel>

          <SectionPanel v-else-if="activeTab === 'supervisor'" title="主管工作台" subtitle="只处理待审核单，审核动作需 PIN 校验">
            <div class="grid gap-4 lg:grid-cols-[1fr_180px_220px_220px]">
              <div class="rounded-lg border border-slate-200 bg-white p-4">
                <h3 class="font-semibold">主管责任</h3>
                <p class="mt-2 text-sm leading-6 text-slate-600">
                  指定主管：{{ activeOrder.supervisor }}。通过后进入待经理审核，驳回后工程部返工。
                </p>
              </div>
              <div class="rounded-lg border border-slate-200 bg-white p-4">
                <label class="text-xs font-semibold text-slate-500">主管 PIN</label>
                <input
                  v-model="supervisorPin"
                  type="password"
                  inputmode="numeric"
                  autocomplete="current-password"
                  placeholder="首次需先修改"
                  class="mt-2 h-10 w-full rounded-md border border-slate-200 px-3 text-sm font-semibold"
                >
              </div>
              <button
                type="button"
                :disabled="!supervisorCanReview"
                class="inline-flex min-h-12 items-center justify-center gap-2 rounded-lg border px-4 py-3 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                :class="supervisorCanReview ? 'border-emerald-700 bg-emerald-700 text-white hover:bg-emerald-800' : ''"
                @click="runTransition('主管通过', '主管', activeOrder.supervisor, '主管确认单头、用料和交期。')"
              >
                <CheckCircle2 class="size-4" aria-hidden="true" />
                主管通过
              </button>
              <button
                type="button"
                :disabled="!supervisorCanReview"
                class="inline-flex min-h-12 items-center justify-center gap-2 rounded-lg border px-4 py-3 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                :class="supervisorCanReview ? 'border-red-700 bg-red-700 text-white hover:bg-red-800' : ''"
                @click="runTransition('主管驳回', '主管', activeOrder.supervisor, rejectReason)"
              >
                <XCircle class="size-4" aria-hidden="true" />
                主管驳回
              </button>
            </div>
            <textarea
              v-model="rejectReason"
              rows="3"
              class="mt-4 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm leading-6"
            />
            <div class="mt-4 rounded-lg border border-slate-200 bg-white p-4">
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 class="font-semibold">修改主管 PIN</h3>
                  <p class="mt-1 text-xs text-slate-500">首次使用默认 PIN 时，必须先改 PIN 才能审核。</p>
                </div>
                <button
                  type="button"
                  :disabled="apiState === 'fallback'"
                  class="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-950 bg-slate-950 px-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                  @click="changeWorkbenchPin('主管')"
                >
                  <ShieldCheck class="size-4" aria-hidden="true" />
                  修改 PIN
                </button>
              </div>
              <div class="mt-4 grid gap-3 md:grid-cols-3">
                <label class="text-xs font-semibold text-slate-500">
                  旧 PIN
                  <input
                    v-model="supervisorPinChangeDraft.old_pin"
                    type="password"
                    inputmode="numeric"
                    autocomplete="current-password"
                    class="mt-1 h-9 w-full rounded-md border border-slate-200 px-2 text-sm"
                  >
                </label>
                <label class="text-xs font-semibold text-slate-500">
                  新 PIN
                  <input
                    v-model="supervisorPinChangeDraft.new_pin"
                    type="password"
                    inputmode="numeric"
                    autocomplete="new-password"
                    class="mt-1 h-9 w-full rounded-md border border-slate-200 px-2 text-sm"
                  >
                </label>
                <label class="text-xs font-semibold text-slate-500">
                  确认新 PIN
                  <input
                    v-model="supervisorPinChangeDraft.confirm_pin"
                    type="password"
                    inputmode="numeric"
                    autocomplete="new-password"
                    class="mt-1 h-9 w-full rounded-md border border-slate-200 px-2 text-sm"
                  >
                </label>
              </div>
            </div>
          </SectionPanel>

          <SectionPanel v-else-if="activeTab === 'manager'" title="经理工作台" subtitle="终审、外厂自动完成、价格表与汇率维护">
            <div class="grid gap-4 xl:grid-cols-[1fr_180px_220px_220px]">
              <div class="rounded-lg border border-slate-200 bg-white p-4">
                <h3 class="font-semibold">终审分支</h3>
                <p class="mt-2 text-sm leading-6 text-slate-600">
                  {{ isExternalOrder ? '经理通过后直接已完成并计算料费，不进入内部啤机部。' : '经理通过后进入待生产，后续由仓库和啤机部补录。' }}
                </p>
              </div>
              <div class="rounded-lg border border-slate-200 bg-white p-4">
                <label class="text-xs font-semibold text-slate-500">经理 PIN</label>
                <input
                  v-model="managerPin"
                  type="password"
                  inputmode="numeric"
                  autocomplete="current-password"
                  placeholder="首次需先修改"
                  class="mt-2 h-10 w-full rounded-md border border-slate-200 px-3 text-sm font-semibold"
                >
              </div>
              <button
                type="button"
                :disabled="!managerCanReview"
                class="inline-flex min-h-12 items-center justify-center gap-2 rounded-lg border px-4 py-3 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                :class="managerCanReview ? 'border-emerald-700 bg-emerald-700 text-white hover:bg-emerald-800' : ''"
                @click="runTransition('经理通过', '经理', '王经理', isExternalOrder ? '外厂单经理通过，自动完成。' : '内部单经理通过，进入待生产。')"
              >
                <CheckCircle2 class="size-4" aria-hidden="true" />
                经理通过
              </button>
              <button
                type="button"
                :disabled="!managerCanReview"
                class="inline-flex min-h-12 items-center justify-center gap-2 rounded-lg border px-4 py-3 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                :class="managerCanReview ? 'border-red-700 bg-red-700 text-white hover:bg-red-800' : ''"
                @click="runTransition('经理驳回', '经理', '王经理', rejectReason)"
              >
                <XCircle class="size-4" aria-hidden="true" />
                经理驳回
              </button>
            </div>

            <div class="mt-4 rounded-lg border border-slate-200 bg-white p-4">
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 class="font-semibold">修改经理 PIN</h3>
                  <p class="mt-1 text-xs text-slate-500">默认 PIN 只能用于首次验证和修改，终审、价格维护和重置主管 PIN 前必须先修改。</p>
                </div>
                <button
                  type="button"
                  :disabled="apiState === 'fallback'"
                  class="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-950 bg-slate-950 px-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                  @click="changeWorkbenchPin('经理')"
                >
                  <ShieldCheck class="size-4" aria-hidden="true" />
                  修改 PIN
                </button>
              </div>
              <div class="mt-4 grid gap-3 md:grid-cols-3">
                <label class="text-xs font-semibold text-slate-500">
                  旧 PIN
                  <input
                    v-model="managerPinChangeDraft.old_pin"
                    type="password"
                    inputmode="numeric"
                    autocomplete="current-password"
                    class="mt-1 h-9 w-full rounded-md border border-slate-200 px-2 text-sm"
                  >
                </label>
                <label class="text-xs font-semibold text-slate-500">
                  新 PIN
                  <input
                    v-model="managerPinChangeDraft.new_pin"
                    type="password"
                    inputmode="numeric"
                    autocomplete="new-password"
                    class="mt-1 h-9 w-full rounded-md border border-slate-200 px-2 text-sm"
                  >
                </label>
                <label class="text-xs font-semibold text-slate-500">
                  确认新 PIN
                  <input
                    v-model="managerPinChangeDraft.confirm_pin"
                    type="password"
                    inputmode="numeric"
                    autocomplete="new-password"
                    class="mt-1 h-9 w-full rounded-md border border-slate-200 px-2 text-sm"
                  >
                </label>
              </div>
            </div>

            <div class="mt-5 grid gap-4 xl:grid-cols-[260px_minmax(0,1fr)]">
              <div class="rounded-lg border border-slate-200 bg-white p-4">
                <label class="text-xs font-semibold text-slate-500">RMB -> HKD</label>
                <input
                  v-model="editableRmbToHkdRate"
                  type="number"
                  min="0"
                  step="0.01"
                  class="mt-2 h-10 w-full rounded-md border border-slate-200 px-3 text-right text-sm font-semibold"
                >
                <label class="mt-4 block text-xs font-semibold text-slate-500">经理 PIN</label>
                <input
                  v-model="managerPin"
                  type="password"
                  inputmode="numeric"
                  autocomplete="current-password"
                  placeholder="首次需先修改"
                  class="mt-2 h-10 w-full rounded-md border border-slate-200 px-3 text-sm font-semibold"
                >
                <div class="mt-4 grid gap-2">
                  <button
                    type="button"
                    class="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-slate-950 px-3 text-sm font-semibold text-white"
                    @click="applyPricingSettings"
                  >
                    <Save class="size-4" aria-hidden="true" />
                    保存口径
                  </button>
                  <button
                    type="button"
                    class="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 px-3 text-sm font-semibold text-slate-700"
                    @click="addMaterialPriceRow"
                  >
                    <Plus class="size-4" aria-hidden="true" />
                    新增原料
                  </button>
                  <button
                    type="button"
                    class="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 px-3 text-sm font-semibold text-slate-700"
                    @click="resetPricingSettings"
                  >
                    <RotateCcw class="size-4" aria-hidden="true" />
                    恢复默认
                  </button>
                </div>
                <ul v-if="pricingErrors.length" class="mt-4 space-y-1 text-xs text-amber-700">
                  <li v-for="error in pricingErrors" :key="error">{{ error }}</li>
                </ul>
              </div>

              <div class="overflow-hidden rounded-lg border border-slate-200 bg-white">
                <table class="min-w-[760px] divide-y divide-slate-200 text-sm">
                  <thead class="bg-slate-50 text-left text-xs font-semibold text-slate-500">
                    <tr>
                      <th class="px-4 py-3">原料</th>
                      <th class="px-4 py-3 text-right">HKD/磅</th>
                      <th class="px-4 py-3">备注</th>
                      <th class="px-4 py-3">状态</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-100">
                    <tr v-for="(price, index) in editableMaterialPrices" :key="`${price.material}-${index}`">
                      <td class="px-4 py-3">
                        <input
                          :value="price.material"
                          class="h-9 w-full rounded-md border border-slate-200 px-2"
                          @input="updateMaterialPrice(index, 'material', readInputValue($event))"
                        >
                      </td>
                      <td class="px-4 py-3 text-right">
                        <input
                          :value="price.unit_price"
                          type="number"
                          min="0"
                          step="0.01"
                          class="h-9 w-28 rounded-md border border-slate-200 px-2 text-right"
                          @input="updateMaterialPrice(index, 'unit_price', readInputValue($event))"
                        >
                      </td>
                      <td class="px-4 py-3">
                        <input
                          :value="price.notes"
                          class="h-9 w-full rounded-md border border-slate-200 px-2"
                          @input="updateMaterialPrice(index, 'notes', readInputValue($event))"
                        >
                      </td>
                      <td class="px-4 py-3">
                        <StatusPill :label="Number(price.unit_price) > 0 ? '可用' : '待补价'" :tone="Number(price.unit_price) > 0 ? 'green' : 'amber'" compact />
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div class="mt-5 grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
              <div class="rounded-lg border border-slate-200 bg-white p-4">
                <h3 class="font-semibold">主管 PIN 重置</h3>
                <div class="mt-4 grid gap-3">
                  <label class="text-xs font-semibold text-slate-500">
                    主管姓名
                    <input
                      v-model="supervisorPinResetDraft.supervisor_name"
                      class="mt-1 h-9 w-full rounded-md border border-slate-200 px-2 text-sm"
                    >
                  </label>
                  <label class="text-xs font-semibold text-slate-500">
                    新 PIN
                    <input
                      v-model="supervisorPinResetDraft.new_pin"
                      type="password"
                      inputmode="numeric"
                      autocomplete="new-password"
                      class="mt-1 h-9 w-full rounded-md border border-slate-200 px-2 text-sm"
                    >
                  </label>
                  <button
                    type="button"
                    :disabled="apiState === 'fallback'"
                    class="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-950 bg-slate-950 px-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                    @click="resetSupervisorPin"
                  >
                    <ShieldCheck class="size-4" aria-hidden="true" />
                    重置主管 PIN
                  </button>
                </div>
              </div>

              <div class="overflow-x-auto rounded-lg border border-slate-200 bg-white">
                <table class="min-w-[860px] divide-y divide-slate-200 text-sm">
                  <thead class="bg-slate-50 text-left text-xs font-semibold text-slate-500">
                    <tr>
                      <th class="px-4 py-3">时间</th>
                      <th class="px-4 py-3">动作</th>
                      <th class="px-4 py-3">操作人</th>
                      <th class="px-4 py-3">对象</th>
                      <th class="px-4 py-3">说明</th>
                    </tr>
                  </thead>
                  <tbody v-if="activeSensitiveAuditLogs.length" class="divide-y divide-slate-100">
                    <tr v-for="log in activeSensitiveAuditLogs" :key="log.id">
                      <td class="px-4 py-3">{{ log.created_at }}</td>
                      <td class="px-4 py-3">
                        <StatusPill :label="log.action" tone="blue" compact />
                      </td>
                      <td class="px-4 py-3">{{ log.actor_name }} · {{ log.actor_role }}</td>
                      <td class="px-4 py-3">{{ log.target_name || log.target_type }}</td>
                      <td class="px-4 py-3 text-slate-600">{{ log.detail }}</td>
                    </tr>
                  </tbody>
                  <tbody v-else>
                    <tr>
                      <td colspan="5" class="px-4 py-8 text-center text-sm text-slate-500">
                        暂无敏感操作审计。
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </SectionPanel>

          <SectionPanel v-else-if="activeTab === 'warehouse'" title="仓库工作台" subtitle="领料单与出库重量维护">
            <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
              <p class="text-sm text-slate-600">
                {{ isExternalOrder ? '外厂单不走内部仓库发料。' : `当前可维护：${isWarehouseEditable ? '是' : '否'}` }}
              </p>
              <div class="flex flex-wrap gap-2">
                <button
                  type="button"
                  :disabled="!isWarehouseEditable || !apiRecord"
                  class="inline-flex h-10 items-center gap-2 rounded-lg border px-3 text-sm font-semibold disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                  :class="isWarehouseEditable && apiRecord ? 'border-slate-950 bg-slate-950 text-white' : ''"
                  @click="createRequisitionsFromItems"
                >
                  <Plus class="size-4" aria-hidden="true" />
                  生成领料单
                </button>
                <button
                  type="button"
                  :disabled="!isWarehouseEditable"
                  class="inline-flex h-10 items-center gap-2 rounded-lg border px-3 text-sm font-semibold disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                  :class="isWarehouseEditable ? 'border-blue-700 bg-blue-700 text-white' : ''"
                  @click="fillWarehouseSample"
                >
                  <Archive class="size-4" aria-hidden="true" />
                  批量出库
                </button>
              </div>
            </div>

            <div class="mb-4 grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
              <div class="rounded-lg border border-slate-200 bg-white p-4">
                <div class="grid gap-3">
                  <label class="text-xs font-semibold text-slate-500">
                    原料
                    <select
                      v-model="inventoryBatchDraft.material"
                      :disabled="!apiRecord"
                      class="mt-1 h-9 w-full rounded-md border border-slate-200 px-2 text-sm disabled:bg-slate-50 disabled:text-slate-400"
                    >
                      <option value="">选择原料</option>
                      <option v-for="material in warehouseMaterials" :key="material" :value="material">
                        {{ material }}
                      </option>
                    </select>
                  </label>
                  <label class="text-xs font-semibold text-slate-500">
                    批次号
                    <input
                      v-model="inventoryBatchDraft.batch_no"
                      :disabled="!apiRecord"
                      class="mt-1 h-9 w-full rounded-md border border-slate-200 px-2 text-sm disabled:bg-slate-50 disabled:text-slate-400"
                      placeholder="HIPS-20260701-A"
                    >
                  </label>
                  <div class="grid grid-cols-2 gap-3">
                    <label class="text-xs font-semibold text-slate-500">
                      仓位
                      <input
                        v-model="inventoryBatchDraft.location"
                        :disabled="!apiRecord"
                        class="mt-1 h-9 w-full rounded-md border border-slate-200 px-2 text-sm disabled:bg-slate-50 disabled:text-slate-400"
                      >
                    </label>
                    <label class="text-xs font-semibold text-slate-500">
                      初始KG
                      <input
                        v-model="inventoryBatchDraft.initial_weight_kg"
                        :disabled="!apiRecord"
                        type="number"
                        min="0"
                        step="0.01"
                        class="mt-1 h-9 w-full rounded-md border border-slate-200 px-2 text-right text-sm disabled:bg-slate-50 disabled:text-slate-400"
                      >
                    </label>
                  </div>
                  <button
                    type="button"
                    :disabled="!apiRecord"
                    class="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-950 bg-slate-950 px-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                    @click="createInventoryBatchFromDraft"
                  >
                    <Plus class="size-4" aria-hidden="true" />
                    新增批次
                  </button>
                </div>
              </div>

              <div class="overflow-x-auto rounded-lg border border-slate-200 bg-white">
                <table class="min-w-[720px] divide-y divide-slate-200 text-sm">
                  <thead class="bg-slate-50 text-left text-xs font-semibold text-slate-500">
                    <tr>
                      <th class="px-4 py-3">原料</th>
                      <th class="px-4 py-3">批次号</th>
                      <th class="px-4 py-3">仓位</th>
                      <th class="px-4 py-3 text-right">初始KG</th>
                      <th class="px-4 py-3 text-right">可用KG</th>
                    </tr>
                  </thead>
                  <tbody v-if="activeInventoryBatches.length" class="divide-y divide-slate-100">
                    <tr v-for="batch in activeInventoryBatches" :key="batch.id">
                      <td class="px-4 py-3 font-medium">{{ batch.material }}</td>
                      <td class="px-4 py-3">{{ batch.batch_no }}</td>
                      <td class="px-4 py-3">{{ batch.location || '未填' }}</td>
                      <td class="px-4 py-3 text-right">{{ formatWeight(batch.initial_weight_kg) }}</td>
                      <td class="px-4 py-3 text-right">{{ formatWeight(batch.available_weight_kg) }}</td>
                    </tr>
                  </tbody>
                  <tbody v-else>
                    <tr>
                      <td colspan="5" class="px-4 py-8 text-center text-sm text-slate-500">
                        暂无库存批次。
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div class="mb-4 overflow-x-auto rounded-lg border border-slate-200 bg-white">
              <table class="min-w-[1120px] divide-y divide-slate-200 text-sm">
                <thead class="bg-slate-50 text-left text-xs font-semibold text-slate-500">
                  <tr>
                    <th class="px-4 py-3">时间</th>
                    <th class="px-4 py-3">类型</th>
                    <th class="px-4 py-3">原料</th>
                    <th class="px-4 py-3">批次号</th>
                    <th class="px-4 py-3">领料单</th>
                    <th class="px-4 py-3 text-right">变动KG</th>
                    <th class="px-4 py-3 text-right">变动前</th>
                    <th class="px-4 py-3 text-right">变动后</th>
                    <th class="px-4 py-3">操作人</th>
                    <th class="px-4 py-3">说明</th>
                  </tr>
                </thead>
                <tbody v-if="activeInventoryMovements.length" class="divide-y divide-slate-100">
                  <tr v-for="movement in activeInventoryMovements" :key="movement.id">
                    <td class="px-4 py-3">{{ movement.created_at }}</td>
                    <td class="px-4 py-3">
                      <StatusPill
                        :label="movement.movement_type"
                        :tone="movement.quantity_kg < 0 ? 'amber' : 'green'"
                        compact
                      />
                    </td>
                    <td class="px-4 py-3 font-medium">{{ movement.material }}</td>
                    <td class="px-4 py-3">{{ movement.batch_no }}</td>
                    <td class="px-4 py-3">{{ movement.req_number || '无' }}</td>
                    <td
                      class="px-4 py-3 text-right font-semibold"
                      :class="movement.quantity_kg < 0 ? 'text-amber-700' : 'text-emerald-700'"
                    >
                      {{ formatMovementWeight(movement.quantity_kg) }}
                    </td>
                    <td class="px-4 py-3 text-right">{{ formatWeight(movement.before_weight_kg) }}</td>
                    <td class="px-4 py-3 text-right">{{ formatWeight(movement.after_weight_kg) }}</td>
                    <td class="px-4 py-3">{{ movement.actor_name || '仓库' }}</td>
                    <td class="px-4 py-3 text-slate-600">{{ movement.reason || '库存变动' }}</td>
                  </tr>
                </tbody>
                <tbody v-else>
                  <tr>
                    <td colspan="10" class="px-4 py-8 text-center text-sm text-slate-500">
                      暂无库存流水。
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="mb-4 overflow-x-auto rounded-lg border border-slate-200 bg-white">
              <table class="min-w-[1120px] divide-y divide-slate-200 text-sm">
                <thead class="bg-slate-50 text-left text-xs font-semibold text-slate-500">
                  <tr>
                    <th class="px-4 py-3">领料单号</th>
                    <th class="px-4 py-3">日期</th>
                    <th class="px-4 py-3">啤办单号</th>
                    <th class="px-4 py-3">原料</th>
                    <th class="px-4 py-3 text-right">申请KG</th>
                    <th class="px-4 py-3">申请人</th>
                    <th class="px-4 py-3">库存批次</th>
                    <th class="px-4 py-3">状态</th>
                    <th class="px-4 py-3">出库时间</th>
                    <th class="px-4 py-3 text-right">操作</th>
                  </tr>
                </thead>
                <tbody v-if="activeRequisitions.length" class="divide-y divide-slate-100">
                  <tr v-for="requisition in activeRequisitions" :key="requisition.id">
                    <td class="px-4 py-3 font-medium">{{ requisition.req_number }}</td>
                    <td class="px-4 py-3">{{ requisition.date }}</td>
                    <td class="px-4 py-3">{{ requisition.order_number }}</td>
                    <td class="px-4 py-3">{{ requisition.material }}</td>
                    <td class="px-4 py-3 text-right">{{ formatWeight(requisition.requested_weight_kg) }}</td>
                    <td class="px-4 py-3">{{ requisition.applicant }}</td>
                    <td class="px-4 py-3">
                      <span v-if="requisition.status === '已出库'" class="text-slate-700">
                        {{ requisition.inventory_batch_no || '未记录' }}
                      </span>
                      <select
                        v-else
                        :value="defaultInventoryBatchId(requisition)"
                        :disabled="!apiRecord"
                        class="h-9 w-48 rounded-md border border-slate-200 px-2 text-sm disabled:bg-slate-50 disabled:text-slate-400"
                        @change="selectedInventoryBatchIds = { ...selectedInventoryBatchIds, [requisition.id]: readInputValue($event) }"
                      >
                        <option value="">选择批次</option>
                        <option
                          v-for="batch in inventoryBatchesForMaterial(requisition.material)"
                          :key="batch.id"
                          :value="batch.id"
                          :disabled="batch.available_weight_kg < (requisition.requested_weight_kg ?? 0)"
                        >
                          {{ batch.batch_no }} / {{ formatWeight(batch.available_weight_kg) }}KG
                        </option>
                      </select>
                    </td>
                    <td class="px-4 py-3">
                      <StatusPill
                        :label="requisition.status"
                        :tone="requisition.status === '已出库' ? 'green' : 'amber'"
                        compact
                      />
                    </td>
                    <td class="px-4 py-3">{{ requisition.issued_at || '未出库' }}</td>
                    <td class="px-4 py-3">
                      <div class="flex justify-end gap-2">
                        <button
                          type="button"
                          :disabled="requisition.status === '已出库' || !apiRecord"
                          class="inline-flex h-8 items-center gap-1 rounded-md border border-emerald-200 px-2 text-xs font-semibold text-emerald-700 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400"
                          @click="markRequisitionIssued(requisition)"
                        >
                          <CheckCircle2 class="size-3.5" aria-hidden="true" />
                          出库
                        </button>
                        <button
                          type="button"
                          :disabled="!apiRecord"
                          class="inline-flex h-8 items-center gap-1 rounded-md border border-rose-200 px-2 text-xs font-semibold text-rose-700 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400"
                          @click="deleteRequisitionRow(requisition.id)"
                        >
                          <XCircle class="size-3.5" aria-hidden="true" />
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                </tbody>
                <tbody v-else>
                  <tr>
                    <td colspan="10" class="px-4 py-8 text-center text-sm text-slate-500">
                      暂无领料单，确认用料重量后可生成。
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="overflow-x-auto rounded-lg border border-slate-200 bg-white">
              <table class="min-w-[1020px] divide-y divide-slate-200 text-sm">
                <thead class="bg-slate-50 text-left text-xs font-semibold text-slate-500">
                  <tr>
                    <th class="px-4 py-3">明细</th>
                    <th class="px-4 py-3">原料</th>
                    <th class="px-4 py-3 text-right">需求KG</th>
                    <th class="px-4 py-3">领料单号</th>
                    <th class="px-4 py-3 text-right">领料KG</th>
                    <th class="px-4 py-3">备注</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-for="item in activeItems" :key="item.id">
                    <td class="px-4 py-3 font-medium">{{ item.mold_id }} · {{ item.mold_name }}</td>
                    <td class="px-4 py-3">{{ item.material }}</td>
                    <td class="px-4 py-3 text-right">{{ formatWeight(item.required_material_kg) }}</td>
                    <td class="px-4 py-3">
                      <input
                        :value="item.receipt_no"
                        :disabled="!isWarehouseEditable"
                        class="h-9 w-44 rounded-md border border-slate-200 px-2 disabled:bg-slate-50 disabled:text-slate-400"
                        @input="updateItemText(item.id, 'receipt_no', readInputValue($event))"
                      >
                    </td>
                    <td class="px-4 py-3 text-right">
                      <input
                        :value="item.collected_weight_kg ?? ''"
                        :disabled="!isWarehouseEditable"
                        type="number"
                        min="0"
                        step="0.01"
                        class="h-9 w-28 rounded-md border border-slate-200 px-2 text-right disabled:bg-slate-50 disabled:text-slate-400"
                        @input="updateItemNumber(item.id, 'collected_weight_kg', readInputValue($event))"
                      >
                    </td>
                    <td class="px-4 py-3">
                      <input
                        :value="item.notes"
                        class="h-9 w-full rounded-md border border-slate-200 px-2"
                        @input="updateItemText(item.id, 'notes', readInputValue($event))"
                      >
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </SectionPanel>

          <SectionPanel v-else-if="activeTab === 'production'" title="啤机部工作台" subtitle="开始处理、回填实际用料和啤办费、完成校验">
            <div class="mb-4 grid gap-3 md:grid-cols-3">
              <button
                type="button"
                :disabled="isExternalOrder || activeOrder.status !== '待生产'"
                class="inline-flex h-11 items-center justify-center gap-2 rounded-lg border px-3 text-sm font-semibold disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                :class="!isExternalOrder && activeOrder.status === '待生产' ? 'border-slate-950 bg-slate-950 text-white' : ''"
                @click="runTransition('开始处理', '啤机部', '啤机部', '啤机部接收任务并开始处理。')"
              >
                <Play class="size-4" aria-hidden="true" />
                开始处理
              </button>
              <button
                type="button"
                :disabled="!isProductionEditable"
                class="inline-flex h-11 items-center justify-center gap-2 rounded-lg border px-3 text-sm font-semibold disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                :class="isProductionEditable ? 'border-blue-700 bg-blue-700 text-white' : ''"
                @click="fillProductionSample"
              >
                <Send class="size-4" aria-hidden="true" />
                批量回填
              </button>
              <button
                type="button"
                :disabled="!isProductionEditable || !completionGate.can_complete"
                class="inline-flex h-11 items-center justify-center gap-2 rounded-lg border px-3 text-sm font-semibold disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                :class="isProductionEditable && completionGate.can_complete ? 'border-emerald-700 bg-emerald-700 text-white' : ''"
                @click="runTransition('标记完成', '啤机部', '啤机部', '啤机部已完成实际用料回填。')"
              >
                <CheckCircle2 class="size-4" aria-hidden="true" />
                标记完成
              </button>
            </div>

            <div class="rounded-lg border p-4 text-sm" :class="toneClasses[completionGate.can_complete ? 'green' : 'red']">
              {{ completionGate.message }}
            </div>

            <div class="mt-4 overflow-x-auto rounded-lg border border-slate-200 bg-white">
              <table class="min-w-[1180px] divide-y divide-slate-200 text-sm">
                <thead class="bg-slate-50 text-left text-xs font-semibold text-slate-500">
                  <tr>
                    <th class="px-4 py-3">模具</th>
                    <th class="px-4 py-3">原料</th>
                    <th class="px-4 py-3 text-right">实际KG</th>
                    <th class="px-4 py-3 text-right">料费HKD</th>
                    <th class="px-4 py-3 text-right">啤办费RMB</th>
                    <th class="px-4 py-3 text-right">啤办费HKD</th>
                    <th class="px-4 py-3 text-right">汇率快照</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-for="item in activeItems" :key="item.id">
                    <td class="px-4 py-3 font-medium">{{ item.mold_id }} · {{ item.mold_name }}</td>
                    <td class="px-4 py-3">{{ item.material }}</td>
                    <td class="px-4 py-3 text-right">
                      <input
                        :value="item.actual_weight_kg ?? ''"
                        :disabled="!isProductionEditable"
                        type="number"
                        min="0"
                        step="0.01"
                        class="h-9 w-28 rounded-md border border-slate-200 px-2 text-right disabled:bg-slate-50 disabled:text-slate-400"
                        @input="updateItemNumber(item.id, 'actual_weight_kg', readInputValue($event))"
                      >
                    </td>
                    <td class="px-4 py-3 text-right font-medium">{{ formatMoney(item.actual_amount_hkd) }}</td>
                    <td class="px-4 py-3 text-right">
                      <input
                        :value="item.injection_cost ?? ''"
                        :disabled="!isProductionEditable"
                        type="number"
                        min="0"
                        step="0.01"
                        class="h-9 w-28 rounded-md border border-slate-200 px-2 text-right disabled:bg-slate-50 disabled:text-slate-400"
                        @input="updateItemNumber(item.id, 'injection_cost', readInputValue($event))"
                      >
                    </td>
                    <td class="px-4 py-3 text-right font-medium">{{ isExternalOrder ? '不适用' : formatMoney(item.injection_cost_hkd) }}</td>
                    <td class="px-4 py-3 text-right">{{ item.exchange_rate_at_save ?? '待保存' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="mt-4 grid gap-3 lg:grid-cols-[1fr_180px]">
              <input
                v-model="productionProblem"
                class="h-10 rounded-lg border border-slate-200 px-3 text-sm"
                placeholder="问题反馈"
              >
              <button
                type="button"
                class="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 px-3 text-sm font-semibold"
                @click="addProblem"
              >
                <Plus class="size-4" aria-hidden="true" />
                提交问题
              </button>
            </div>
          </SectionPanel>

          <SectionPanel v-else title="汇总查账" subtitle="完成单进入原料汇总、啤办费用和总费用口径">
            <div class="grid gap-4 md:grid-cols-4">
              <article class="rounded-lg border p-4" :class="toneClasses[reportSummary.has_missing_price ? 'amber' : 'green']">
                <p class="text-xs font-semibold opacity-75">缺料价</p>
                <p class="mt-1 text-xl font-semibold">{{ reportSummary.missing_price_item_ids.length }}</p>
              </article>
              <article class="rounded-lg border p-4" :class="toneClasses[reportSummary.has_missing_actual_weight ? 'red' : 'green']">
                <p class="text-xs font-semibold opacity-75">缺实际用料</p>
                <p class="mt-1 text-xl font-semibold">{{ reportSummary.missing_actual_weight_item_ids.length }}</p>
              </article>
              <article class="rounded-lg border p-4" :class="toneClasses[reportSummary.has_missing_injection_cost ? 'blue' : 'green']">
                <p class="text-xs font-semibold opacity-75">缺啤办费</p>
                <p class="mt-1 text-xl font-semibold">{{ reportSummary.missing_injection_cost_item_ids.length }}</p>
              </article>
              <article class="rounded-lg border p-4" :class="toneClasses[reportSummary.archive_ready ? 'green' : 'amber']">
                <p class="text-xs font-semibold opacity-75">归档</p>
                <p class="mt-1 text-xl font-semibold">{{ reportSummary.archive_ready ? '可归档' : '暂缓' }}</p>
              </article>
            </div>

            <div class="mt-5 flex flex-wrap gap-2">
              <button
                v-for="tab in [
                  { id: 'materials', label: '原料汇总' },
                  { id: 'injection', label: '啤办费用' },
                  { id: 'total', label: '总费用' },
                ]"
                :key="tab.id"
                type="button"
                class="h-10 rounded-lg border px-4 text-sm font-semibold"
                :class="activeReportTab === tab.id ? 'border-slate-950 bg-slate-950 text-white' : 'border-slate-200 bg-white text-slate-700'"
                @click="activeReportTab = tab.id as 'materials' | 'injection' | 'total'"
              >
                {{ tab.label }}
              </button>
            </div>

            <div class="mt-4 overflow-x-auto rounded-lg border border-slate-200 bg-white">
              <table v-if="activeReportTab === 'materials'" class="min-w-[820px] divide-y divide-slate-200 text-sm">
                <thead class="bg-slate-50 text-left text-xs font-semibold text-slate-500">
                  <tr>
                    <th class="px-4 py-3">原料</th>
                    <th class="px-4 py-3 text-right">明细数</th>
                    <th class="px-4 py-3 text-right">用量KG</th>
                    <th class="px-4 py-3 text-right">料费HKD</th>
                    <th class="px-4 py-3">缺价明细</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-for="row in reportSummary.material_rows" :key="row.material">
                    <td class="px-4 py-3 font-medium">{{ row.material }}</td>
                    <td class="px-4 py-3 text-right">{{ row.line_count }}</td>
                    <td class="px-4 py-3 text-right">{{ row.total_weight_kg.toFixed(2) }}</td>
                    <td class="px-4 py-3 text-right">{{ row.total_material_cost_hkd.toFixed(2) }}</td>
                    <td class="px-4 py-3">{{ row.missing_price_item_ids.join('、') || '无' }}</td>
                  </tr>
                </tbody>
              </table>

              <table v-else-if="activeReportTab === 'injection'" class="min-w-[760px] divide-y divide-slate-200 text-sm">
                <thead class="bg-slate-50 text-left text-xs font-semibold text-slate-500">
                  <tr>
                    <th class="px-4 py-3">明细</th>
                    <th class="px-4 py-3 text-right">RMB</th>
                    <th class="px-4 py-3 text-right">HKD</th>
                    <th class="px-4 py-3">状态</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-for="row in reportSummary.injection_fee_rows" :key="row.item_id">
                    <td class="px-4 py-3 font-medium">{{ row.item_id }}</td>
                    <td class="px-4 py-3 text-right">{{ formatBlank(row.injection_cost) }}</td>
                    <td class="px-4 py-3 text-right">{{ formatMoney(row.injection_cost_hkd) }}</td>
                    <td class="px-4 py-3">
                      <StatusPill :label="row.is_missing ? '缺啤办费' : '已计费'" :tone="row.is_missing ? 'blue' : 'green'" compact />
                    </td>
                  </tr>
                  <tr v-if="reportSummary.injection_fee_rows.length === 0">
                    <td colspan="4" class="px-4 py-6 text-center text-slate-500">外厂或模厂路径不产生内部啤办费</td>
                  </tr>
                </tbody>
              </table>

              <table v-else class="min-w-[980px] divide-y divide-slate-200 text-sm">
                <thead class="bg-slate-50 text-left text-xs font-semibold text-slate-500">
                  <tr>
                    <th class="px-4 py-3">明细</th>
                    <th class="px-4 py-3">模具</th>
                    <th class="px-4 py-3 text-right">料费HKD</th>
                    <th class="px-4 py-3 text-right">啤办费HKD</th>
                    <th class="px-4 py-3 text-right">总费用HKD</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-for="row in reportSummary.item_rows" :key="row.item_id">
                    <td class="px-4 py-3 font-medium">{{ row.item_id }}</td>
                    <td class="px-4 py-3">{{ row.mold_id }} · {{ row.mold_name }}</td>
                    <td class="px-4 py-3 text-right">{{ formatMoney(row.actual_amount_hkd) }}</td>
                    <td class="px-4 py-3 text-right">{{ isExternalOrder ? '不适用' : formatMoney(row.injection_cost_hkd) }}</td>
                    <td class="px-4 py-3 text-right font-semibold">{{ row.total_cost.toFixed(2) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-if="activeProblems.length" class="mt-4 rounded-lg border border-amber-100 bg-amber-50 p-4 text-sm text-amber-900">
              <p class="font-semibold">问题反馈</p>
              <ul class="mt-2 space-y-1">
                <li v-for="problem in activeProblems" :key="problem">{{ problem }}</li>
              </ul>
            </div>
          </SectionPanel>

          <SectionPanel title="明细清单" subtitle="工模、用料、领料、实际用料和费用字段统一展示">
            <div class="overflow-x-auto rounded-lg border border-slate-200 bg-white">
              <table class="min-w-[1500px] divide-y divide-slate-200 text-sm">
                <thead class="bg-slate-50 text-left text-xs font-semibold text-slate-500">
                  <tr>
                    <th class="px-4 py-3">排序</th>
                    <th class="px-4 py-3">工模编号</th>
                    <th class="px-4 py-3">工模名称</th>
                    <th class="px-4 py-3">机型</th>
                    <th class="px-4 py-3">原料</th>
                    <th class="px-4 py-3">颜色</th>
                    <th class="px-4 py-3">色粉</th>
                    <th class="px-4 py-3 text-right">啤数</th>
                    <th class="px-4 py-3 text-right">需求KG</th>
                    <th class="px-4 py-3 text-right">领料KG</th>
                    <th class="px-4 py-3 text-right">实际KG</th>
                    <th class="px-4 py-3 text-right">料费HKD</th>
                    <th class="px-4 py-3 text-right">啤办费RMB</th>
                    <th class="px-4 py-3 text-right">啤办费HKD</th>
                    <th class="px-4 py-3">完成时间</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-for="item in activeItems" :key="item.id">
                    <td class="px-4 py-3">{{ item.sort_order }}</td>
                    <td class="px-4 py-3 font-medium text-slate-950">{{ item.mold_id }}</td>
                    <td class="px-4 py-3">{{ item.mold_name }}</td>
                    <td class="px-4 py-3">{{ item.machine_type }}</td>
                    <td class="px-4 py-3">{{ item.material }}</td>
                    <td class="px-4 py-3">{{ item.color }}</td>
                    <td class="px-4 py-3">{{ item.pigment_no }}</td>
                    <td class="px-4 py-3 text-right">{{ item.shoot_qty }}</td>
                    <td class="px-4 py-3 text-right">{{ formatWeight(item.required_material_kg) }}</td>
                    <td class="px-4 py-3 text-right">{{ formatWeight(item.collected_weight_kg) }}</td>
                    <td class="px-4 py-3 text-right">{{ formatWeight(item.actual_weight_kg) }}</td>
                    <td class="px-4 py-3 text-right">{{ formatMoney(item.actual_amount_hkd) }}</td>
                    <td class="px-4 py-3 text-right">{{ isExternalOrder ? '不适用' : formatBlank(item.injection_cost) }}</td>
                    <td class="px-4 py-3 text-right">{{ isExternalOrder ? '不适用' : formatMoney(item.injection_cost_hkd) }}</td>
                    <td class="px-4 py-3">{{ formatBlank(item.completion_time) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </SectionPanel>

          <SectionPanel title="审核轨迹" subtitle="状态流转和敏感操作会追加到责任链">
            <div class="grid gap-3 lg:grid-cols-2">
              <article
                v-for="audit in activeAuditLogs"
                :key="audit.id"
                class="rounded-lg border bg-white p-4"
                :class="toneClasses[audit.tone]"
              >
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <h3 class="font-semibold text-slate-950">{{ audit.action }}</h3>
                    <p class="mt-1 text-xs opacity-75">{{ audit.actor_name }} · {{ audit.actor_role }} · {{ audit.created_at }}</p>
                  </div>
                  <StatusPill :label="`${audit.from_status} -> ${audit.to_status}`" :tone="audit.tone" compact />
                </div>
                <p class="mt-3 text-sm leading-6 text-slate-700">{{ audit.reason }}</p>
              </article>
            </div>
          </SectionPanel>

          <div
            v-if="actionMessage"
            class="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm font-medium text-blue-800"
          >
            {{ actionMessage }}
          </div>
        </div>
      </div>
    </div>
  </main>
</template>

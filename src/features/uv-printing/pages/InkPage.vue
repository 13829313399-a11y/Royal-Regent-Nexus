<script lang="ts">
import type {
  ShiftScope,
  UvInkBalance,
  UvInkMaterial,
  UvInkMovement as InkMovement,
  UvInkMovementKind,
  UvInkSku as InkSku,
} from '../contracts'
// 两个 script 块会被合并成同一个模块，因此这里统一取别名，避免与 <script setup> 的同名绑定冲突。
import {
  INK_MATERIAL_LABELS as MATERIAL_LABELS,
  INK_MOVEMENT_LABELS as MOVEMENT_LABELS,
} from '../domain/status'
import { SHIFT_LABELS as SHIFT_LABEL_TEXT } from '../domain/businessTime'
import type { InkMovementRow as MovementRow } from '../components/InkMovementTable.vue'
import type { InkStockRow as StockRow } from '../components/InkSkuStockTable.vue'

/**
 * 墨水页面纯函数：筛选、视图状态与「导出与网页同一条件」的作用域文案。
 * 这些函数不依赖组件实例，便于单独验证「同色不同供应商不合并」「切换视图保留条件」等口径。
 */

export type InkView = 'stock' | 'flows'

export interface InkFilters {
  q: string
  supplier: string
  material: '' | UvInkMaterial
  color: string
  lowOnly: boolean
  kind: '' | UvInkMovementKind
  dateFrom: string
  dateTo: string
}

export function emptyInkFilters(): InkFilters {
  return { q: '', supplier: '', material: '', color: '', lowOnly: false, kind: '', dateFrom: '', dateTo: '' }
}

export function activeInkFilterCount(filters: InkFilters): number {
  let count = 0
  if (filters.q.trim()) count += 1
  if (filters.supplier) count += 1
  if (filters.material) count += 1
  if (filters.color) count += 1
  if (filters.lowOnly) count += 1
  if (filters.kind) count += 1
  if (filters.dateFrom) count += 1
  if (filters.dateTo) count += 1
  return count
}

/**
 * SKU 级条件（供应商 / 材质 / 颜色）必须同时成立；关键字匹配 SKU 自身的文本。
 * 每个 SKU 独立判断，同色不同供应商不会被合并成一行。
 */
export function matchesInkSku(sku: InkSku, filters: InkFilters): boolean {
  if (filters.supplier && sku.supplier !== filters.supplier) return false
  if (filters.material && sku.material !== filters.material) return false
  if (filters.color && sku.color !== filters.color) return false
  const needle = filters.q.trim().toLowerCase()
  if (!needle) return true
  const haystack = [
    sku.id,
    sku.supplier,
    sku.color,
    sku.location,
    MATERIAL_LABELS[sku.material] ?? '',
    ...sku.color_aliases,
  ].join(' ').toLowerCase()
  return haystack.includes(needle)
}

/** 库存行：SKU 条件 + 可选「仅看低库」。 */
export function filterInkStock(rows: StockRow[], filters: InkFilters): StockRow[] {
  return rows.filter((row) => matchesInkSku(row.sku, filters) && (!filters.lowOnly || row.balance.low_stock))
}

/**
 * 流水行：类型与发生日直接过滤；供应商/材质/颜色通过该流水的 SKU 过滤；
 * 关键字匹配流水文本（SKU 标签、用途、单号、创建人）或该 SKU 的文本。
 * 「仅看低库」是库存视图条件，切到流水时保留但不参与流水筛选。
 */
export function filterInkMovements(rows: MovementRow[], filters: InkFilters): MovementRow[] {
  const skuScoped = Boolean(filters.supplier || filters.material || filters.color)
  const needle = filters.q.trim().toLowerCase()
  return rows.filter((row) => {
    const movement = row.movement
    if (filters.kind && movement.kind !== filters.kind) return false
    if (filters.dateFrom && movement.occurred_on < filters.dateFrom) return false
    if (filters.dateTo && movement.occurred_on > filters.dateTo) return false
    if (skuScoped) {
      if (!row.sku) return false
      if (filters.supplier && row.sku.supplier !== filters.supplier) return false
      if (filters.material && row.sku.material !== filters.material) return false
      if (filters.color && row.sku.color !== filters.color) return false
    }
    if (!needle) return true
    const movementText = [
      movement.sku_label,
      movement.sku_id,
      movement.purpose,
      movement.source_doc,
      movement.created_by_name,
      row.machineCode,
    ].join(' ').toLowerCase()
    if (movementText.includes(needle)) return true
    return row.sku ? matchesInkSku(row.sku, { ...filters, supplier: '', material: '', color: '' }) : false
  })
}

/** 页面状态必须互相可区分：加载 / 空 / 无结果 / 无权限 / 失败 / 过期。 */
export type InkSurfaceState =
  | 'idle'
  | 'loading'
  | 'ready'
  | 'empty'
  | 'no-result'
  | 'forbidden'
  | 'readonly'
  | 'error'
  | 'stale'

export function inkSurfaceState(input: {
  forbidden: boolean
  loading: boolean
  settled: boolean
  hasData: boolean
  failed: boolean
  sourceCount: number
  filteredCount: number
}): InkSurfaceState {
  if (input.forbidden) return 'forbidden'
  if (input.loading && !input.hasData) return 'loading'
  if (input.failed && !input.hasData) return 'error'
  // 已经读到过数据、但这次刷新失败：宁可标成过期，也不让旧数字看起来仍然有效。
  if (input.failed && input.hasData) return 'stale'
  if (!input.settled || !input.hasData) return 'idle'
  if (input.sourceCount === 0) return 'empty'
  if (input.filteredCount === 0) return 'no-result'
  return 'ready'
}

/** 导出、Toast 与页面摘要共用的过滤条件文案（scope_label 口径）。 */
export function describeInkScope(input: {
  view: InkView
  businessDate: string
  shift: ShiftScope
  filters: InkFilters
  totalCount: number
  resultCount: number
}): string {
  const { filters } = input
  const parts = [
    input.view === 'stock' ? '墨水库存' : '墨水流水',
    '华康A',
    `业务日 ${input.businessDate}`,
    SHIFT_LABEL_TEXT[input.shift] ?? '全天',
    `供应商 ${filters.supplier || '全部'}`,
    `材质 ${filters.material ? (MATERIAL_LABELS[filters.material] ?? filters.material) : '全部'}`,
    `颜色 ${filters.color || '全部'}`,
    `关键字 ${filters.q.trim() || '无'}`,
    `库存状态 ${filters.lowOnly ? '仅看低于阈值' : '全部'}`,
  ]
  if (input.view === 'flows') {
    parts.push(`流水类型 ${filters.kind ? (MOVEMENT_LABELS[filters.kind] ?? filters.kind) : '全部'}`)
    parts.push(`发生日 ${filters.dateFrom || '不限'} 至 ${filters.dateTo || '不限'}`)
  }
  parts.push(`结果 ${input.resultCount}/${input.totalCount} 条`)
  return parts.join(' · ')
}
</script>

<script setup lang="ts">
import { computed, inject, nextTick, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { AlertTriangle, FileSpreadsheet, PackageMinus, PackagePlus, Undo2, X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type {
  UvInkMovement,
  UvInkSku,
  UvMachine,
  UvMutationResult,
  UvPage,
} from '../contracts'
import { UV_CONTEXT_KEY, UV_TRANSPORT_KEY } from '../composables/uvPageContext'
import { newOperationId, useUvCommand, useUvRequest, type UvRequestError } from '../composables/useUvRequest'
import { useUvToast } from '../composables/useUvToast'
import { INK_MATERIAL_LABELS, INK_MOVEMENT_LABELS } from '../domain/status'
import { formatDecimal, formatMoney } from '../domain/decimal'
import { readAllPages } from '../transport/pagination'
import UvConfirmDialog from '../components/UvConfirmDialog.vue'
import UvStateBlock from '../components/UvStateBlock.vue'
import InkIssueDrawer, { type InkIssueSubmission } from '../components/InkIssueDrawer.vue'
import InkMovementTable, { type InkMovementRow } from '../components/InkMovementTable.vue'
import InkSkuStockTable, { type InkStockRow } from '../components/InkSkuStockTable.vue'

/**
 * 墨水账本页（spec 6.6）。
 *
 * - 「库存 / 流水」是页内视图切换，筛选条件属于页面、切换时保留；
 * - 供应商 / 材质 / 颜色 / 关键字是组合条件，同色不同供应商不合并、不互相抵扣；
 * - 写操作（领用 / 采购入库 / 冲销）需要 uv_printing:ink_write；
 *   成本字段（单价 / 金额）需要 uv_printing:cost_read，未授权时不渲染数值；
 * - 冲销新增反向记录并保留原流水；未知单价只让成本「待核」，不阻断数量操作；
 * - 读取失败绝不留存样例数据、也不显示 0。
 */

/** 上下文用注入取；缺一个就直接报错，而不是悄悄新建一份 transport 或库存公式。 */
function requiredInject<T>(value: T | undefined, name: string, hint: string): T {
  if (value === undefined || value === null) {
    throw new Error(`${name} 缺失：${hint}`)
  }
  return value
}

const ctx = requiredInject(
  inject(UV_CONTEXT_KEY),
  'UV_CONTEXT_KEY',
  '墨水页面必须挂在 UvWorkspaceShell 之下，页面不自己新建 transport 或第二份库存公式。',
)
const transport = requiredInject(
  inject(UV_TRANSPORT_KEY),
  'UV_TRANSPORT_KEY',
  '墨水页面只能通过注入的 transport 读写，不直接拼接 HTTP 或读样例数据。',
)

const route = useRoute()
const toast = useUvToast()

const workspace = ctx.workspace
const revision = ctx.revision
const scope = computed(() => workspace.scope.value)

const canInkWrite = computed(() => workspace.can('uv_printing:ink_write'))
const canCostRead = computed(() => workspace.can('uv_printing:cost_read'))
const canExport = computed(() => workspace.can('uv_printing:export'))
const forbidden = computed(() => workspace.permissionDenied.value)

/* ---------------- 视图与筛选 ---------------- */

const view = ref<InkView>(route.query.view === 'flows' ? 'flows' : 'stock')
const filters = reactive({
  ...emptyInkFilters(),
  lowOnly: route.query.low === '1',
})

function setView(next: InkView) {
  // 只切视图，不动筛选条件：切回库存时关键字、供应商、材质、颜色、仅看低库都还在。
  view.value = next
}

function clearFilters() {
  Object.assign(filters, emptyInkFilters())
}

const activeFilterCount = computed(() => activeInkFilterCount(filters))

/* ---------------- 读取 ---------------- */

const skuRequest = useUvRequest<UvPage<UvInkSku>>(
  (signal) => readAllPages((nextScope, nextSignal) => transport.value.inkSkus(nextScope, nextSignal), scope.value, signal),
  { watchSource: () => [scope.value.business_date, scope.value.shift, revision.value] },
)

const balanceRequest = useUvRequest<UvPage<UvInkBalance>>(
  (signal) => readAllPages((nextScope, nextSignal) => transport.value.inkBalances(nextScope, nextSignal), scope.value, signal),
  { watchSource: () => [scope.value.business_date, scope.value.shift, revision.value] },
)

const movementRequest = useUvRequest<UvPage<UvInkMovement>>(
  (signal) => readAllPages((nextScope, nextSignal) => transport.value.inkMovements(nextScope, nextSignal), scope.value, signal),
  { watchSource: () => [scope.value.business_date, scope.value.shift, revision.value] },
)

/** 机台列表只在要显示机台的地方读取（流水视图或写抽屉），避免只读浏览多发请求。 */
const machineRequest = useUvRequest<UvPage<UvMachine>>(
  (signal) => readAllPages((nextScope, nextSignal) => transport.value.machines(nextScope, nextSignal), scope.value, signal),
  { watchSource: () => [revision.value], immediate: false },
)

// 流水列要显示机台编号，切到流水视图时补读一次；拿不到就退回显示机台 ID，不猜。
watch(view, (next) => {
  if (next === 'flows' && !machineRequest.settled.value) void machineRequest.run()
}, { immediate: true })

const skus = computed(() => skuRequest.data.value?.items ?? [])
const balances = computed(() => balanceRequest.data.value?.items ?? [])
const movements = computed(() => movementRequest.data.value?.items ?? [])
const machines = computed(() => machineRequest.data.value?.items ?? [])

const skuReady = computed(() => skuRequest.settled.value && skuRequest.data.value !== null)
const balanceReady = computed(() => balanceRequest.settled.value && balanceRequest.data.value !== null)
const movementReady = computed(() => movementRequest.settled.value && movementRequest.data.value !== null)

/** SKU × 自身余额：一行一个 SKU，不做同色合并。 */
const allStockRows = computed<InkStockRow[]>(() => {
  const bySku = new Map(balances.value.map((balance) => [balance.sku_id, balance]))
  return skus.value
    .map((sku) => {
      const balance = bySku.get(sku.id)
      return balance ? { sku, balance } : null
    })
    .filter((row): row is InkStockRow => row !== null)
    .sort((a, b) =>
      a.sku.supplier.localeCompare(b.sku.supplier, 'zh-Hans-CN')
      || a.sku.color.localeCompare(b.sku.color, 'zh-Hans-CN')
      || a.sku.material.localeCompare(b.sku.material, 'en'),
    )
})

const orphanBalanceCount = computed(() => balances.value.length - allStockRows.value.length)

const filteredStockRows = computed(() => filterInkStock(allStockRows.value, filters))

const allMovementRows = computed<InkMovementRow[]>(() => {
  const skuById = new Map(skus.value.map((sku) => [sku.id, sku]))
  const machineById = new Map(machines.value.map((machine) => [machine.id, machine.code]))
  return movements.value.map((movement) => ({
    movement,
    sku: skuById.get(movement.sku_id) ?? null,
    machineCode: movement.machine_id
      ? (machineById.get(movement.machine_id) ?? movement.machine_id)
      : '',
  }))
})

const filteredMovementRows = computed(() => filterInkMovements(allMovementRows.value, filters))

const stockError = computed<UvRequestError | null>(
  () => skuRequest.error.value ?? balanceRequest.error.value,
)
const movementError = computed<UvRequestError | null>(
  () => skuRequest.error.value ?? movementRequest.error.value,
)

const stockState = computed(() => inkSurfaceState({
  forbidden: forbidden.value,
  loading: skuRequest.loading.value || balanceRequest.loading.value,
  settled: skuReady.value && balanceReady.value,
  hasData: skuReady.value && balanceReady.value,
  failed: stockError.value !== null,
  sourceCount: allStockRows.value.length,
  filteredCount: filteredStockRows.value.length,
}))

const movementState = computed(() => inkSurfaceState({
  forbidden: forbidden.value,
  loading: skuRequest.loading.value || movementRequest.loading.value,
  settled: skuReady.value && movementReady.value,
  hasData: skuReady.value && movementReady.value,
  failed: movementError.value !== null,
  sourceCount: allMovementRows.value.length,
  filteredCount: filteredMovementRows.value.length,
}))

const surfaceState = computed(() => (view.value === 'stock' ? stockState.value : movementState.value))
const surfaceError = computed(() => (view.value === 'stock' ? stockError.value : movementError.value))
const surfaceSubject = computed(() => (view.value === 'stock' ? '墨水库存' : '墨水流水'))

const supplierOptions = computed(() =>
  [...new Set(skus.value.map((sku) => sku.supplier))].sort((a, b) => a.localeCompare(b, 'zh-Hans-CN')),
)
const colorOptions = computed(() =>
  [...new Set(skus.value.map((sku) => sku.color))].sort((a, b) => a.localeCompare(b, 'zh-Hans-CN')),
)

const materialOptions = computed(() =>
  (['hard', 'soft', 'other'] as const).map((value) => ({ value, label: INK_MATERIAL_LABELS[value] })),
)
const kindOptions = computed(() =>
  (['opening', 'purchase_in', 'issue_out', 'return_in', 'stocktake', 'reversal'] as const)
    .map((value) => ({ value, label: INK_MOVEMENT_LABELS[value] })),
)

const lowStockCount = computed(() => allStockRows.value.filter((row) => row.balance.low_stock).length)
const costPendingCount = computed(() => allStockRows.value.filter((row) => row.balance.cost_pending).length)

const summaryText = computed(() => (view.value === 'stock'
  ? `库存 ${allStockRows.value.length} 个 SKU · 低于阈值 ${lowStockCount.value} 个 · 当前显示 ${filteredStockRows.value.length} 个`
  : `流水 ${allMovementRows.value.length} 条 · 当前显示 ${filteredMovementRows.value.length} 条`))

const scopeLabel = computed(() => describeInkScope({
  view: view.value,
  businessDate: scope.value.business_date ?? '',
  shift: scope.value.shift ?? 'all',
  filters,
  totalCount: view.value === 'stock' ? allStockRows.value.length : allMovementRows.value.length,
  resultCount: view.value === 'stock' ? filteredStockRows.value.length : filteredMovementRows.value.length,
}))

function retryReads() {
  void skuRequest.run()
  if (view.value === 'stock') void balanceRequest.run()
  else void movementRequest.run()
}

/* ---------------- 写操作 ---------------- */

const drawerOpen = ref(false)
const drawerMode = ref<'issue' | 'purchase'>('issue')
const presetSkuId = ref<string | null>(null)
const reverseTarget = ref<UvInkMovement | null>(null)
const highlightId = ref<string | null>(null)
const movementHost = ref<HTMLElement | null>(null)

const issueCommand = useUvCommand<UvMutationResult<UvInkMovement>>()
const purchaseCommand = useUvCommand<UvMutationResult<UvInkMovement>>()
const reverseCommand = useUvCommand<UvMutationResult<UvInkMovement>>()

const drawerCommand = computed(() => (drawerMode.value === 'purchase' ? purchaseCommand : issueCommand))
const drawerPending = computed(() => drawerCommand.value.pending.value)
const drawerError = computed(() => drawerCommand.value.error.value)

/** 同一份表单内容重试时复用同一个 operation_id，内容变了才换新的幂等键。 */
let lastFingerprint = ''
let lastOperationId = ''
function operationIdFor(fingerprint: string): string {
  if (fingerprint !== lastFingerprint) {
    lastFingerprint = fingerprint
    lastOperationId = newOperationId()
  }
  return lastOperationId
}

function openDrawer(mode: 'issue' | 'purchase', skuId?: string) {
  drawerMode.value = mode
  presetSkuId.value = skuId ?? null
  issueCommand.clearError()
  purchaseCommand.clearError()
  reverseCommand.clearError()
  drawerOpen.value = true
  if (!machineRequest.settled.value) void machineRequest.run()
}

function closeDrawer() {
  drawerOpen.value = false
}

async function submitDrawer(payload: InkIssueSubmission) {
  const mode = drawerMode.value
  const fingerprint = JSON.stringify({ mode, payload })
  const operationId = operationIdFor(fingerprint)
  const factoryId = scope.value.factory_id

  const run = async (): Promise<UvMutationResult<UvInkMovement>> => {
    if (mode === 'purchase') {
      const response = await transport.value.createInkPurchase({
        factory_id: factoryId,
        operation_id: operationId,
        sku_id: payload.sku_id,
        quantity_ml: payload.quantity_ml,
        bottle_input: payload.bottle_input,
        occurred_on: payload.occurred_on,
        machine_id: payload.machine_id,
        purpose: payload.purpose,
        source_doc: payload.source_doc,
        created_by_name: payload.created_by_name,
        unit_cost: payload.unit_cost,
        currency: payload.currency,
      })
      return response.data
    }
    const response = await transport.value.createInkIssue({
      factory_id: factoryId,
      operation_id: operationId,
      sku_id: payload.sku_id,
      quantity_ml: payload.quantity_ml,
      bottle_input: payload.bottle_input,
      occurred_on: payload.occurred_on,
      machine_id: payload.machine_id,
      purpose: payload.purpose,
      source_doc: payload.source_doc,
      created_by_name: payload.created_by_name,
    })
    return response.data
  }

  const result = await drawerCommand.value.execute(operationId, run)
  if (!result) return

  const movement = result.entity
  drawerOpen.value = false
  ctx.markDirty()
  lastFingerprint = ''
  lastOperationId = ''

  const bottleText = movement.bottle_input ? `（${formatDecimal(movement.bottle_input, 3)} 瓶）` : ''
  const costText = movement.cost_pending
    ? '成本待核：该 SKU 没有单价，金额显示为「待核」而不是 0'
    : movement.amount
      ? `金额 ${formatMoney(movement.amount)}`
      : '金额缺失：没有可用的单价与币种'
  toast.push({
    message: `${mode === 'purchase' ? '采购入库' : '领用出库'}已登记：${movement.sku_label}`,
    detail: [
      `${formatDecimal(movement.quantity_ml, 1)} ml${bottleText}`,
      movement.source_doc ? `来源单号 ${movement.source_doc}` : '无来源单号',
      costText,
      result.replayed ? '重复提交按幂等返回原结果' : '',
    ].filter(Boolean).join(' · '),
    tone: movement.cost_pending ? 'amber' : 'green',
    retryable: false,
  })
}

/** 冲销必须带原单链接：影响清单里写清对象、后果与审计保留。 */
const reverseImpacts = computed(() => {
  const target = reverseTarget.value
  if (!target) return []
  const rows = [
    `新增一条反向流水，与原单 ${target.id} 双向关联；金额与数量都按原值反向。`,
    `原流水不会被删除或覆盖，仍保留在流水中并可追溯（原流水会标记「已冲销」）。`,
    `库存回补 ${formatDecimal(target.quantity_ml, 1)} ml：${target.sku_label}`,
    `成本与经营报表按冲销后的净额重算；冲销本身不能再被冲销。`,
  ]
  if (target.cost_pending) rows.push('原流水成本待核，冲销记录同样是待核，不会显示成 0。')
  return rows
})

const reverseCostHint = computed(() => {
  const target = reverseTarget.value
  if (!target) return ''
  if (!canCostRead.value) return '缺少 uv_printing:cost_read：本次冲销的单价与金额不会下发前端。'
  return target.cost_pending
    ? '原流水单价待核，冲销金额同样待核。'
    : `原流水金额 ${target.amount ? formatMoney(target.amount) : '—'}，冲销后按相反数记账。`
})

async function confirmReverse(reason: string) {
  const target = reverseTarget.value
  if (!target) return
  const operationId = newOperationId()
  const result = await reverseCommand.execute(operationId, async () => {
    const response = await transport.value.reverseInkMovement({
      factory_id: scope.value.factory_id,
      operation_id: operationId,
      expected_version: target.version,
      target_id: target.id,
      reason,
    })
    return response.data
  })
  if (!result) {
    const error = reverseCommand.error.value
    toast.push({
      message: '冲销未完成',
      detail: error ? `${error.message}（原单 ${target.id} 仍然有效，可修正后重试）` : `原单 ${target.id} 仍然有效。`,
      tone: 'red',
      retryable: true,
    })
    return
  }
  reverseTarget.value = null
  highlightId.value = result.entity.id
  ctx.markDirty()
  toast.push({
    message: `已冲销：${target.sku_label}`,
    detail: `原单 ${target.id} 保留，新增反向流水 ${result.entity.id}；回补 ${formatDecimal(target.quantity_ml, 1)} ml。`,
    tone: 'amber',
    retryable: false,
  })
}

function requestReverse(movement: UvInkMovement) {
  reverseCommand.clearError()
  reverseTarget.value = movement
}

/** 冲销行带原单链接：点击后高亮被冲销的原流水，不隐藏任何历史。 */
function focusMovement(movementId: string) {
  highlightId.value = movementId
  void nextTick(() => {
    const rows = movementHost.value?.querySelectorAll<HTMLElement>('tr[data-movement-id]')
    for (const row of rows ?? []) {
      if (row.dataset.movementId === movementId && typeof row.scrollIntoView === 'function') {
        row.scrollIntoView({ block: 'center' })
        break
      }
    }
  })
}

/* ---------------- 导出（样例） ---------------- */

function handleExport() {
  // 样例导出：只用当前过滤条件生成 scope_label，不伪造文件下载。
  toast.push({
    message: '样例导出（不生成文件）',
    detail: `导出与网页使用同一过滤条件：${scopeLabel.value}`,
    tone: 'blue',
    retryable: false,
  })
}
</script>

<template>
  <div class="space-y-4">
    <header class="uv-page-head">
      <div class="uv-page-head__titles">
        <p class="uv-page-head__eyebrow">Ink Ledger</p>
        <h1>墨水账本</h1>
        <p class="uv-page-head__desc">
          库存按 SKU 独立计算：同色不同供应商、不同材质不会合并，也不会互相抵扣。
          可用 ml、折合瓶数与预警阈值直接可见，收发流水可追溯、可冲销。
        </p>
      </div>
      <div class="uv-page-head__actions">
        <span v-if="!canInkWrite" class="uv-readonly-note">
          领用 / 入库 / 冲销已停用：缺少 uv_printing:ink_write
        </span>
        <span v-if="!canCostRead" class="uv-readonly-note">
          单价与金额不显示：缺少 uv_printing:cost_read
        </span>
        <Button
          variant="outline"
          size="lg"
          class="min-h-11"
          type="button"
          :disabled="!canExport"
          :title="canExport ? '按当前过滤条件导出样例口径' : '缺少 uv_printing:export 权限'"
          @click="handleExport"
        >
          <FileSpreadsheet class="size-4" aria-hidden="true" />
          样例导出
        </Button>
        <Button
          variant="outline"
          size="lg"
          class="min-h-11"
          type="button"
          :disabled="!canInkWrite"
          :title="canInkWrite ? '登记采购入库' : '缺少 uv_printing:ink_write 权限'"
          @click="openDrawer('purchase')"
        >
          <PackagePlus class="size-4" aria-hidden="true" />
          采购入库
        </Button>
        <Button
          size="lg"
          class="min-h-11"
          type="button"
          :disabled="!canInkWrite"
          :title="canInkWrite ? '登记机台领用出库' : '缺少 uv_printing:ink_write 权限'"
          @click="openDrawer('issue')"
        >
          <PackageMinus class="size-4" aria-hidden="true" />
          领用出库
        </Button>
      </div>
    </header>

    <div v-if="!canInkWrite" class="uv-callout uv-callout--warning" role="note">
      <strong>写操作按权限停用</strong>：当前账号在华康A生产部没有
      <span class="uv-mono">uv_printing:ink_write</span>，领用出库、采购入库与冲销按钮已禁用并写明原因。
      前端禁用只是提前阻止误操作；<strong>服务端才是权威校验</strong>，权限与库存都以服务端判定为准。
    </div>

    <div v-if="!canCostRead" class="uv-callout" role="note">
      <strong>成本字段未授权</strong>：单价与金额需要
      <span class="uv-mono">uv_printing:cost_read</span>；未授权时这些列不渲染数值（显示「未授权」），
      也不会用 0 代替。数量与库存不受影响。
    </div>

    <form class="uv-filters" role="search" aria-label="墨水筛选条件" @submit.prevent>
      <div class="uv-filters__row">
        <label class="uv-filter">
          <span class="uv-filter__label">关键字</span>
          <input
            v-model="filters.q"
            class="uv-input"
            type="search"
            aria-label="按关键字搜索墨水"
            placeholder="供应商 / 颜色 / 别名 / 用途 / 单号"
          >
        </label>

        <label class="uv-filter">
          <span class="uv-filter__label">供应商</span>
          <select
            v-model="filters.supplier"
            class="uv-input uv-select"
            :class="filters.supplier ? 'uv-select--active' : ''"
            aria-label="供应商"
          >
            <option value="">全部供应商</option>
            <option v-for="supplier in supplierOptions" :key="supplier" :value="supplier">{{ supplier }}</option>
          </select>
        </label>

        <label class="uv-filter">
          <span class="uv-filter__label">墨水材质</span>
          <select
            v-model="filters.material"
            class="uv-input uv-select"
            :class="filters.material ? 'uv-select--active' : ''"
            aria-label="墨水材质"
          >
            <option value="">全部材质</option>
            <option v-for="option in materialOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </label>

        <label class="uv-filter">
          <span class="uv-filter__label">颜色</span>
          <select
            v-model="filters.color"
            class="uv-input uv-select"
            :class="filters.color ? 'uv-select--active' : ''"
            aria-label="颜色"
          >
            <option value="">全部颜色</option>
            <option v-for="color in colorOptions" :key="color" :value="color">{{ color }}</option>
          </select>
        </label>

        <div class="uv-filter">
          <span class="uv-filter__label">库存状态</span>
          <span class="uv-check" :class="filters.lowOnly ? 'uv-check--on' : ''">
            <input v-model="filters.lowOnly" type="checkbox" aria-label="仅看低库">
            仅看低库（低于阈值）
          </span>
          <span class="uv-filter__hint">
            {{ view === 'stock' ? '只保留低于该 SKU 自身阈值的行' : '库存视图条件，已保留，切回库存仍然生效' }}
          </span>
        </div>

        <label v-if="view === 'flows'" class="uv-filter">
          <span class="uv-filter__label">流水类型</span>
          <select v-model="filters.kind" class="uv-input uv-select" :class="filters.kind ? 'uv-select--active' : ''" aria-label="流水类型">
            <option value="">全部类型</option>
            <option v-for="option in kindOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </label>

        <label v-if="view === 'flows'" class="uv-filter">
          <span class="uv-filter__label">发生日从</span>
          <input v-model="filters.dateFrom" class="uv-input" type="date" aria-label="发生日从">
        </label>

        <label v-if="view === 'flows'" class="uv-filter">
          <span class="uv-filter__label">发生日至</span>
          <input v-model="filters.dateTo" class="uv-input" type="date" aria-label="发生日至">
        </label>

        <div class="uv-filters__meta">
          <span class="uv-filters__summary">{{ summaryText }}</span>
          <button
            v-if="activeFilterCount"
            type="button"
            class="uv-chip uv-chip--clear"
            @click="clearFilters"
          >
            <X class="size-3" aria-hidden="true" />
            清除 {{ activeFilterCount }} 个条件
          </button>
        </div>
      </div>
      <p class="uv-filters__summary">
        导出与网页使用同一过滤条件：{{ scopeLabel }}
      </p>
    </form>

    <section class="uv-panel" aria-label="墨水库存与流水">
      <div class="uv-panel__head">
        <div>
          <h2 class="uv-panel__title">{{ view === 'stock' ? '库存' : '流水' }}</h2>
          <p class="uv-panel__subtitle">
            {{ view === 'stock'
              ? '每行是一个 SKU（供应商 · 材质 · 颜色）。可用 ml、折合瓶数、阈值与刻度对比同时可见。'
              : '期初、采购入库、领用出库、退回入库、盘点调整与冲销都在这里，冲销会保留原流水。' }}
          </p>
        </div>

        <div class="uv-actions" role="group" aria-label="墨水视图切换">
          <Button
            size="sm"
            type="button"
            :variant="view === 'stock' ? 'default' : 'outline'"
            :aria-pressed="view === 'stock'"
            @click="setView('stock')"
          >
            库存
          </Button>
          <Button
            size="sm"
            type="button"
            :variant="view === 'flows' ? 'default' : 'outline'"
            :aria-pressed="view === 'flows'"
            @click="setView('flows')"
          >
            流水
          </Button>
        </div>
      </div>

      <div class="uv-panel__body uv-panel__body--flush">
        <p v-if="orphanBalanceCount > 0" class="uv-callout uv-callout--warning" role="alert">
          有 {{ orphanBalanceCount }} 条余额没有对应的 SKU 主数据，未在此显示；请检查主数据完整性，不要按缺失值当 0。
        </p>

        <UvStateBlock
          :state="surfaceState"
          :subject="surfaceSubject"
          :message="surfaceError?.message ?? ''"
          :detail="surfaceError ? `错误码 ${surfaceError.code} · ${scopeLabel}` : ''"
          :retryable="Boolean(surfaceError)"
          @retry="retryReads"
          @action="clearFilters"
        >
          <div ref="movementHost">
            <InkSkuStockTable
              v-if="view === 'stock'"
              :rows="filteredStockRows"
              :can-write="canInkWrite"
              :can-cost-read="canCostRead"
              @issue="(skuId) => openDrawer('issue', skuId)"
            />
            <InkMovementTable
              v-else
              :rows="filteredMovementRows"
              :can-write="canInkWrite"
              :can-cost-read="canCostRead"
              :busy-id="reverseCommand.pending.value ? reverseTarget?.id ?? null : null"
              :highlight-id="highlightId"
              @reverse="requestReverse"
              @focus="focusMovement"
            />
          </div>
        </UvStateBlock>

        <div v-if="view === 'flows' && highlightId" class="uv-actions" style="padding: 10px 16px">
          <span class="uv-readonly-note">
            已定位原单 {{ highlightId }}：被冲销的流水仍在列表中，未删除也未覆盖。
          </span>
          <Button variant="ghost" size="sm" type="button" @click="highlightId = null">取消定位</Button>
        </div>

        <div v-if="view === 'stock' && costPendingCount > 0" class="uv-callout" style="margin: 12px 16px">
          有 {{ costPendingCount }} 个 SKU 存在缺单价的流水：数量与库存照常可用，成本显示「待核」而不是 0。
        </div>
      </div>
    </section>

    <InkIssueDrawer
      :open="drawerOpen"
      :mode="drawerMode"
      :skus="allStockRows"
      :machines="machines"
      :machines-loading="machineRequest.loading.value"
      :machines-error="machineRequest.error.value?.message ?? ''"
      :can-cost-read="canCostRead"
      :can-write="canInkWrite"
      :pending="drawerPending"
      :error="drawerError"
      :business-date="scope.business_date ?? ''"
      :preset-sku-id="presetSkuId"
      @close="closeDrawer"
      @submit="submitDrawer"
      @retry-machines="machineRequest.run"
    />

    <UvConfirmDialog
      :open="reverseTarget !== null"
      title="冲销这条墨水流水？"
      :hint="reverseCostHint"
      :impacts="reverseImpacts"
      confirm-label="确认冲销"
      cancel-label="取消"
      destructive
      require-reason
      reason-label="冲销原因"
      reason-placeholder="说明为什么冲销，例如领用登记错误、发错机台"
      :busy="reverseCommand.pending.value"
      @cancel="reverseTarget = null"
      @confirm="confirmReverse"
    />

    <div class="uv-toasts pointer-events-none" role="status" aria-live="polite">
      <div
        v-for="item in toast.toasts.value"
        :key="item.id"
        class="uv-toast pointer-events-auto"
        :class="`uv-toast--${item.tone}`"
      >
        <AlertTriangle v-if="item.tone === 'red' || item.tone === 'amber'" class="size-4" aria-hidden="true" />
        <FileSpreadsheet v-else class="size-4" aria-hidden="true" />
        <div>
          <p class="uv-toast__title">{{ item.message }}</p>
          <p class="uv-toast__detail">{{ item.detail }}</p>
        </div>
        <button
          type="button"
          class="uv-toast__close"
          :aria-label="`关闭提示：${item.message}`"
          @click="toast.dismiss(item.id)"
        >
          <X class="size-3.5" aria-hidden="true" />
        </button>
      </div>
    </div>

    <p v-if="workspace.isReadOnly.value" class="uv-readonly-note">
      <Undo2 class="size-3" aria-hidden="true" />
      只读：当前账号没有 uv_printing:report，写操作全部不可用。
    </p>
  </div>
</template>

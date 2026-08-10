<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { AlertOctagon, Boxes, Clock3, Columns3, Filter, GripHorizontal, History, ListChecks, Maximize2, Minimize2, PanelBottomOpen, Plus, Search, ShieldAlert, SlidersHorizontal, Sparkles, Trash2 } from '@lucide/vue'
import { useInjectionSchedulingV2Store } from './stores/useInjectionSchedulingV2Store'
import { enrichDemandOrderMolds } from './api/injectionSchedulingV2Api'
import { useScheduleLiveEvents } from './composables/useScheduleLiveEvents'
import AutoSchedulePreviewDialog from './components/AutoSchedulePreviewDialog.vue'
import BacklogDock from './components/BacklogDock.vue'
import BacklogOrderCancelDialog from './components/BacklogOrderCancelDialog.vue'
import ColumnPresetMenu from './components/ColumnPresetMenu.vue'
import MachinePlanGrid from './components/MachinePlanGrid.vue'
import InjectionSchedulingImportWizard from './components/InjectionSchedulingImportWizard.vue'
import InjectionSchedulingExportDialog from './components/InjectionSchedulingExportDialog.vue'
import ManualAppendDialog from './components/ManualAppendDialog.vue'
import ManualDemandDialog from './components/ManualDemandDialog.vue'
import PublishPlanDialog from './components/PublishPlanDialog.vue'
import WithdrawTaskDialog from './components/WithdrawTaskDialog.vue'
import ScheduleTimeline from './components/ScheduleTimeline.vue'
import SchedulingCommandBar from './components/SchedulingCommandBar.vue'
import SchedulingKpiStrip from './components/SchedulingKpiStrip.vue'
import SchedulingFeedbackToast from './components/SchedulingFeedbackToast.vue'
import TaskInspectorDrawer from './components/TaskInspectorDrawer.vue'
import ManualMoveDialog from './components/ManualMoveDialog.vue'
import Phase5OperationsDashboard from './components/Phase5OperationsDashboard.vue'
import RevisionConflictDialog from './components/RevisionConflictDialog.vue'
import ScheduleRunHistory from './components/ScheduleRunHistory.vue'
import type { AutoScheduleRunRecord, OrderRecord } from './types'
import type { ColumnPreset, EditableCellKey, FactoryId, WorkspaceView } from './types'
import './injection-scheduling-v2.css'
import './styles/tokens.css'
import './styles/polish.css'
import './styles/motion.css'

const route = useRoute()
const router = useRouter()
const store = useInjectionSchedulingV2Store()
const importWizardOpen = ref(false)
const importBatchId = computed(() => {
  const value = Array.isArray(route.query.batch) ? route.query.batch[0] : route.query.batch
  return typeof value === 'string' ? value.trim() : ''
})
const exportDialogOpen = ref(false)
const manualAppendOrderId = ref<string | null>(null)
const manualDemandOpen = ref(false)
const manualDemandOrderId = ref<string | null>(null)
const publishDialogOpen = ref(false)
const withdrawDialogOpen = ref(false)
const backlogCancelOrderId = ref<string | null>(null)
const enrichingMolds = ref(false)
const kpiContent = ref<HTMLElement | null>(null)
const kpiPanelHeight = ref<number | null>(null)
const kpiFullHeight = ref(0)
const kpiRestoreHeight = ref(0)
const kpiResizing = ref(false)
let kpiResizeStartY = 0
let kpiResizeStartHeight = 0
const manualAppendOrder = computed(() => store.orders.find((item) => item.id === manualAppendOrderId.value) ?? null)
const manualDemandOrder = computed(() => store.orders.find((item) => item.id === manualDemandOrderId.value) ?? null)
const backlogCancelOrder = computed(() => store.backlogOrders.find((item) => item.id === backlogCancelOrderId.value) ?? null)
const appendDisabledReason = computed(() => !store.planningPlan ? '尚无 planning DRAFT，请先导入或创建接续草案' : !store.canEdit ? '请切换到规划 DRAFT，或检查编辑权限' : '')
const publishDisabledReason = computed(() => {
  if (!store.planningPlan) return '当前没有可发布的规划草案'
  if (!store.canPublish) return '当前账号没有排产编辑或发布权限'
  if (store.pendingEditCount) return '请先保存或放弃未保存修改'
  if (!store.planningDraftPlan.tasks.length) return '空计划不能发布'
  return ''
})
const tabs: Array<{ key: WorkspaceView; label: string; icon: typeof ListChecks }> = [
  { key: 'plan', label: '计划总表', icon: ListChecks }, { key: 'timeline', label: '机台时间轴', icon: Clock3 },
  { key: 'backlog', label: '待排订单', icon: Boxes }, { key: 'alerts', label: '异常预警', icon: ShieldAlert }, { key: 'history', label: '自动排期记录', icon: History },
  { key: 'analytics', label: '运营分析', icon: SlidersHorizontal },
]
const tabCount = computed<Record<WorkspaceView, number>>(() => ({ plan: store.tasks.length, timeline: store.machines.length, backlog: store.backlogOrders.length, alerts: store.alerts.length, history: store.autoScheduleRuns.length, analytics: store.phase5Analytics?.speedModels.length ?? 0 }))
const visibleKeys = computed(() => store.visibleColumns.map((column) => String(column.key)))
const selectedOpen = computed(() => Boolean(store.selectedTaskId && store.activeView === 'plan'))
const currentKpiHeight = computed(() => kpiPanelHeight.value ?? kpiFullHeight.value)
const workspaceExpanded = computed(() => kpiPanelHeight.value !== null && kpiPanelHeight.value <= 1)
const kpiPanelStyle = computed(() => kpiPanelHeight.value === null ? undefined : { height: `${kpiPanelHeight.value}px` })
const feedback = computed(() => {
  const error = store.autoScheduleError || store.phase5AnalyticsError
  if (error) return { message: error, tone: 'error' as const }
  if (store.revisionConflict) return { message: store.revisionConflict.message, tone: 'error' as const }
  const message = store.saveMessage
  return { message, tone: /失败|不足|冲突|禁止/.test(message) ? 'error' as const : 'success' as const }
})
const presetLabels: Record<ColumnPreset, string> = { planner: '计划员视图', production: '生产视图', fit: '资格适配', full: '完整字段' }

async function changeFactory(value: string) {
  if (!store.setFactory(value)) return
  importWizardOpen.value = false
  const { batch: _batch, ...query } = route.query
  await router.replace({ query: { ...query, factory: value } })
  await store.load()
  if (store.activeView === 'analytics') await store.loadPhase5Analytics()
}
async function trackImportBatch(batchId: string) {
  if (importBatchId.value === batchId) return
  await router.replace({ query: { ...route.query, batch: batchId } })
}
async function closeImportWizard() {
  importWizardOpen.value = false
  const { batch: _batch, ...query } = route.query
  await router.replace({ query })
}
function goHome() {
  if (store.pendingEditCount) {
    store.saveMessage = '存在未保存的规划修改，请先保存或放弃后再离开。'
    return
  }
  void router.push({ name: 'dashboard' })
}

function openMasterData() {
  if (store.pendingEditCount) {
    store.saveMessage = '存在未保存的规划修改，请先保存或放弃后再打开模具数据库。'
    return
  }
  void router.push({ name: 'injection-scheduling-mold-database', query: { factory: store.factoryId } })
}
async function importConfirmed() {
  await store.load({ quiet: true })
  store.activatePlanSlice('planning', true)
}
function openManualAppend(orderId: string) {
  if (!store.planningPlan) { store.saveMessage = '尚无 planning DRAFT，请先导入或创建接续草案。'; return }
  if (store.activePlanSlice !== 'planning' && !store.activatePlanSlice('planning')) return
  manualAppendOrderId.value = orderId
}
async function manualAppendConfirmed() { await store.load({ quiet: true }); store.activatePlanSlice('planning', true) }
function openManualDemand(orderId: string | null = null) {
  manualDemandOrderId.value = orderId
  manualDemandOpen.value = true
}
async function manualDemandChanged(message: string) {
  manualDemandOpen.value = false
  manualDemandOrderId.value = null
  await store.load({ quiet: true })
  store.activatePlanSlice('planning', true)
  store.activeView = 'backlog'
  store.saveMessage = message
}
function openPublishDialog() {
  store.publishPlanError = ''
  if (publishDisabledReason.value) {
    store.saveMessage = publishDisabledReason.value
    return
  }
  publishDialogOpen.value = true
}
async function confirmPublishPlan() {
  if (await store.publishPlanningPlan()) publishDialogOpen.value = false
}
function openWithdrawDialog() {
  store.withdrawTaskError = ''
  if (store.withdrawDisabledReason) {
    store.saveMessage = store.withdrawDisabledReason
    return
  }
  withdrawDialogOpen.value = true
}
async function confirmWithdrawTask(reason: string) {
  if (await store.withdrawSelectedTask(reason)) withdrawDialogOpen.value = false
}
function openBacklogCancel(orderId: string) {
  store.cancelBacklogOrderError = ''
  backlogCancelOrderId.value = orderId
}
async function confirmBacklogCancel(reason: string) {
  if (!backlogCancelOrderId.value) return
  if (await store.cancelBacklog(backlogCancelOrderId.value, reason)) backlogCancelOrderId.value = null
}
function selectView(view: WorkspaceView) { store.activeView = view; if (view === 'analytics') void store.loadPhase5Analytics() }
function resizeColumn(key: string, width: number) { store.columnWidths = { ...store.columnWidths, [key]: Math.max(54, Math.min(420, width)) } }
function closeInspector() { store.selectedTaskId = null }
function openBacklogOrder(orderId: string) { store.activeView = 'backlog'; const order = store.orders.find((item) => item.id === orderId); store.search = order?.orderNo ?? '' }
function sourceMoldNo(order: Pick<OrderRecord, 'moldId' | 'lineage'>) { return store.molds.find((mold) => mold.id === order.moldId)?.moldNo || String(order.lineage.source_mold_no || '待补模具') }
function sharedMoldMatched(order: Pick<OrderRecord, 'moldDefinitionId' | 'lineage'>) { return Boolean(order.moldDefinitionId) || order.lineage.mold_enrichment_status === 'MATCHED' }
function hasSchedulableMold(order: Pick<OrderRecord, 'moldId' | 'moldDefinitionId'>) { return Boolean(order.moldId || order.moldDefinitionId) }
function moldEnrichmentLabel(order: Pick<OrderRecord, 'moldId' | 'moldDefinitionId' | 'lineage'>) { return sharedMoldMatched(order) ? '共享资料已补齐' : order.moldId ? '旧模具已关联' : '待补齐' }
function moldReadinessLabel(order: Pick<OrderRecord, 'moldId' | 'moldDefinitionId' | 'lineage'>) {
  if (order.lineage.factory_readiness_status === 'FACTORY_READY') return '可排机'
  return sharedMoldMatched(order) ? '草案可排 · 发布前补实体' : '待复核'
}
function backlogAppendTitle(order: Pick<OrderRecord, 'moldId' | 'moldDefinitionId' | 'lineage'>) {
  if (!hasSchedulableMold(order)) return '共享模具资料待补齐，暂不能排到机台'
  return appendDisabledReason.value
}
async function enrichBacklogMolds() {
  if (enrichingMolds.value || !store.canEdit) return
  enrichingMolds.value = true
  try {
    const result = await enrichDemandOrderMolds(store.factoryId)
    await store.load({ quiet: true })
    store.saveMessage = `共享模具补齐完成：匹配 ${Number(result.matched ?? 0)} 条，待补 ${Number(result.pending ?? 0)} 条，歧义 ${Number(result.ambiguous ?? 0)} 条；其中可直接排机 ${Number(result.execution_ready ?? 0)} 条。`
  } catch (cause) {
    store.saveMessage = `模具补齐失败：${cause instanceof Error ? cause.message : '请稍后重试'}`
  } finally {
    enrichingMolds.value = false
  }
}
function stageReport(edits: Array<{ key: EditableCellKey; value: string | number }>) {
  if (!store.selectedTaskId) return
  edits.forEach((edit) => store.stageCellEdit(store.selectedTaskId!, edit.key, edit.value))
}
function measureKpiPanel() {
  const nextFullHeight = Math.ceil(kpiContent.value?.scrollHeight ?? 0)
  if (!nextFullHeight) return
  const wasFullyOpen = kpiPanelHeight.value === null || Math.abs((kpiPanelHeight.value ?? 0) - kpiFullHeight.value) <= 2
  kpiFullHeight.value = nextFullHeight
  if (wasFullyOpen) kpiPanelHeight.value = nextFullHeight
  else kpiPanelHeight.value = Math.min(kpiPanelHeight.value ?? nextFullHeight, nextFullHeight)
  if (!kpiRestoreHeight.value || kpiRestoreHeight.value > nextFullHeight) kpiRestoreHeight.value = nextFullHeight
}
function setKpiPanelHeight(value: number) {
  const nextHeight = Math.max(0, Math.min(kpiFullHeight.value, Math.round(value)))
  kpiPanelHeight.value = nextHeight
  if (nextHeight > 1) kpiRestoreHeight.value = nextHeight
}
function resizeKpiPanel(event: PointerEvent) {
  if (!kpiResizing.value) return
  setKpiPanelHeight(kpiResizeStartHeight + event.clientY - kpiResizeStartY)
}
function kpiSnapPoints() {
  return kpiFullHeight.value > 100 ? [0, 70, kpiFullHeight.value] : [0, kpiFullHeight.value]
}
function snapKpiPanelHeight() {
  const currentHeight = currentKpiHeight.value
  const closestHeight = kpiSnapPoints().reduce((closest, candidate) => Math.abs(candidate - currentHeight) < Math.abs(closest - currentHeight) ? candidate : closest)
  setKpiPanelHeight(closestHeight)
}
function stopKpiResize() {
  if (!kpiResizing.value) return
  kpiResizing.value = false
  document.body.classList.remove('is-scheduling-kpi-resizing')
  window.removeEventListener('pointermove', resizeKpiPanel)
  window.removeEventListener('pointerup', stopKpiResize)
  window.removeEventListener('pointercancel', stopKpiResize)
  snapKpiPanelHeight()
}
function startKpiResize(event: PointerEvent) {
  if (event.button !== 0 || !kpiFullHeight.value) return
  kpiResizeStartY = event.clientY
  kpiResizeStartHeight = currentKpiHeight.value
  kpiResizing.value = true
  document.body.classList.add('is-scheduling-kpi-resizing')
  window.addEventListener('pointermove', resizeKpiPanel)
  window.addEventListener('pointerup', stopKpiResize)
  window.addEventListener('pointercancel', stopKpiResize)
  event.preventDefault()
}
function toggleWorkspaceHeight() {
  if (workspaceExpanded.value) setKpiPanelHeight(kpiRestoreHeight.value || kpiFullHeight.value)
  else {
    if (currentKpiHeight.value > 1) kpiRestoreHeight.value = currentKpiHeight.value
    setKpiPanelHeight(0)
  }
}
function handleKpiResizeKey(event: KeyboardEvent) {
  const snapPoints = kpiSnapPoints()
  if (event.key === 'ArrowUp') setKpiPanelHeight([...snapPoints].reverse().find((height) => height < currentKpiHeight.value - 1) ?? 0)
  else if (event.key === 'ArrowDown') setKpiPanelHeight(snapPoints.find((height) => height > currentKpiHeight.value + 1) ?? kpiFullHeight.value)
  else if (event.key === 'Home') setKpiPanelHeight(0)
  else if (event.key === 'End') setKpiPanelHeight(kpiFullHeight.value)
  else return
  event.preventDefault()
}
async function reapplyConflict() { await store.revisionConflict?.retry?.() }
function openScheduleRun(run: AutoScheduleRunRecord) { store.selectAutoScheduleRun(run); store.autoScheduleDialogOpen = true }

watch(() => route.query.factory, async (value) => {
  const normalized = Array.isArray(value) ? value[0] : value
  if (typeof normalized === 'string' && normalized !== store.factoryId) {
    if (!store.setFactory(normalized)) return
    await store.load()
    if (store.activeView === 'analytics') await store.loadPhase5Analytics()
  }
})
watch(importBatchId, (value) => {
  if (value) importWizardOpen.value = true
})
onMounted(async () => {
  const requested = Array.isArray(route.query.factory) ? route.query.factory[0] : route.query.factory
  if (typeof requested === 'string') store.setFactory(requested)
  requestAnimationFrame(measureKpiPanel)
  window.addEventListener('resize', measureKpiPanel)
  await store.load()
  if (importBatchId.value) importWizardOpen.value = true
  window.addEventListener('beforeunload', guardBeforeUnload)
})
function guardBeforeUnload(event: BeforeUnloadEvent) {
  if (!store.pendingEditCount) return
  event.preventDefault()
}
onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', guardBeforeUnload)
  window.removeEventListener('resize', measureKpiPanel)
  stopKpiResize()
})
useScheduleLiveEvents(store.pollEvents)
</script>

<template>
  <div class="injection-scheduling-v2" :class="{ 'has-backlog-dock': store.backlogDockOpen && store.activeView === 'plan' }">
    <SchedulingCommandBar :factory-id="store.factoryId as FactoryId" :factory-name="store.factoryName" :source-mode="store.sourceMode" :source-message="store.sourceMessage" :refreshing="store.refreshing" :search="store.search" :last-synced-at="store.lastSyncedAt" :plan-status="store.plan?.status ?? ''" :pending-count="store.pendingEditCount" :saving="store.savingEdits" :can-save="store.canEdit || store.canReport" :can-import="store.canImport" :can-export="store.canExport && Boolean(store.plan)" :has-planning-draft="Boolean(store.planningPlan)" :can-publish="store.canPublish" :publishing-plan="store.publishingPlan" :publish-disabled-reason="publishDisabledReason" :save-message="store.saveMessage" @update:factory-id="changeFactory" @update:search="store.search = $event" @home="goHome" @refresh="store.load({ quiet: true })" @open-auto-schedule="store.autoScheduleDialogOpen = true" @open-import="importWizardOpen = true" @open-export="exportDialogOpen = true" @open-master-data="openMasterData" @publish="openPublishDialog" @save="store.savePendingEdits" @discard="store.discardPendingEdits" />
    <main :class="{ 'workspace-expanded': workspaceExpanded }">
      <div v-if="store.sourceMode === 'fallback'" class="fallback-banner"><AlertOctagon :size="15" /><strong>只读演示：</strong><span>{{ store.sourceMessage }}</span></div>
      <div class="schedule-overview-shell" :class="{ 'is-resizing': kpiResizing, 'is-collapsed': workspaceExpanded }" :style="kpiPanelStyle">
        <div class="schedule-overview-viewport">
          <div ref="kpiContent" class="schedule-overview-content">
            <SchedulingKpiStrip :summary="store.summary" :class="{ 'is-loading': store.loading }" />
          </div>
        </div>
        <div
          class="workspace-vertical-resizer"
          role="separator"
          aria-label="调整计划表高度"
          aria-orientation="horizontal"
          :aria-valuemin="0"
          :aria-valuemax="kpiFullHeight"
          :aria-valuenow="currentKpiHeight"
          :aria-valuetext="workspaceExpanded ? '计划表已放大' : `指标区高度 ${currentKpiHeight} 像素`"
          tabindex="0"
          title="上下拖动调整计划表高度；双击可放大或恢复"
          @pointerdown="startKpiResize"
          @dblclick="toggleWorkspaceHeight"
          @keydown="handleKpiResizeKey"
        >
          <span class="workspace-resize-grip"><GripHorizontal :size="15" /></span>
        </div>
      </div>
      <section class="scheduling-workspace">
        <nav class="workspace-tabs" aria-label="排产视图">
          <button v-for="tab in tabs" :key="tab.key" :class="{ active: store.activeView === tab.key }" @click="selectView(tab.key)"><component :is="tab.icon" :size="15" /><span>{{ tab.label }}</span><em>{{ tabCount[tab.key] }}</em></button>
          <div class="workspace-status"><span class="status-dot"></span><button :class="{ active: store.activePlanSlice === 'execution' }" :disabled="!store.executionPlan" @click="store.activatePlanSlice('execution')">执行 {{ store.executionPlan ? `PUBLISHED · r${store.executionPlan.revision}` : '暂无' }}</button><button :class="{ active: store.activePlanSlice === 'planning' }" :disabled="!store.planningPlan" @click="store.activatePlanSlice('planning')">规划 {{ store.planningPlan ? `DRAFT · r${store.planningPlan.revision}` : '暂无' }}</button><b>轮询 {{ store.pollingRevision }}</b></div>
        </nav>

        <Transition name="workspace-view" mode="out-in">
        <section v-if="store.activeView === 'plan'" key="plan" class="plan-view">
          <div class="plan-toolbar">
            <div class="toolbar-search"><Search :size="15" /><input v-model="store.search" placeholder="机号 / 工模 / 产品 / 单号 / 货号" /></div>
            <label><Filter :size="14" /><select v-model="store.statusFilter"><option value="all">全部状态</option><option value="RUNNING">正在生产</option><option value="QUEUED">排队中</option><option value="BLOCKED">异常 / 待料</option><option value="COMPLETED">已完成</option></select></label>
            <label><ShieldAlert :size="14" /><select v-model="store.riskFilter"><option value="all">全部风险</option><option value="overdue">已经超期</option><option value="soon">3 天内到期</option><option value="review">资格待复核</option></select></label>
            <span class="rule-note">资格口径：安数 · 射胶量 · 机械手 · 夹具 · 工艺限制 · 状态</span>
            <div class="toolbar-spacer"></div>
            <button class="toolbar-button workspace-size-button" :class="{ active: workspaceExpanded }" :aria-pressed="workspaceExpanded" @click="toggleWorkspaceHeight"><Minimize2 v-if="workspaceExpanded" :size="15" /><Maximize2 v-else :size="15" />{{ workspaceExpanded ? '恢复指标' : '放大表格' }}</button>
            <button class="toolbar-button" :class="{ active: store.columnMenuOpen }" @click="store.columnMenuOpen = !store.columnMenuOpen"><Columns3 :size="15" />{{ presetLabels[store.activePreset] }}</button>
            <button class="toolbar-button" @click="store.backlogDockOpen = !store.backlogDockOpen"><PanelBottomOpen :size="15" />待排池</button>
            <button class="toolbar-button quick-schedule" @click="store.autoScheduleDialogOpen = true"><Sparkles :size="15" />方案预览</button>
            <ColumnPresetMenu :open="store.columnMenuOpen" :preset="store.activePreset" :visible-keys="visibleKeys" :widths="store.columnWidths" @close="store.columnMenuOpen = false" @preset="store.setPreset" @toggle="store.toggleColumn" @move="store.moveColumn" @reset="store.resetColumns" @resize="resizeColumn" />
          </div>
          <div v-if="store.loading && !store.tasks.length" class="table-skeleton" role="status" aria-label="正在读取排产任务">
            <span v-for="line in 8" :key="line" :style="{ '--skeleton-delay': `${line * 28}ms` }"></span>
          </div>
          <div v-else class="plan-work-area" :class="{ 'inspector-open': selectedOpen }">
            <MachinePlanGrid :rows="store.gridRows" :columns="store.visibleColumns" :collapsed-machine-ids="store.collapsedMachineIds" :widths="store.columnWidths" :sort="store.sort" :selected-task-id="store.selectedTaskId" :plan-status="store.plan?.status ?? ''" :can-edit="store.canEdit" :can-report="store.canReport" :pending-edits="store.cellDrafts" @toggle-machine="store.toggleMachine" @select="store.selectTask" @sort="store.cycleSort" @resize="resizeColumn" @edit="store.stageCellEdit" @move-request="store.prepareMove" @keyboard-move="store.moveByKeyboard" />
            <Transition name="inspector">
              <TaskInspectorDrawer v-if="selectedOpen" :task="store.selectedTask" :order="store.selectedOrder" :mold="store.selectedMold" :machine="store.selectedMachine" :tab="store.inspectorTab" :events="store.events" :plan-status="store.plan?.status ?? ''" :can-report="store.canReport" :can-withdraw="store.canWithdraw" :withdraw-disabled-reason="store.withdrawDisabledReason" :withdrawing="store.withdrawingTask" :pending-count="store.pendingEditCount" :saving="store.savingEdits" @update:tab="store.inspectorTab = $event" @close="closeInspector" @stage="stageReport" @save="store.savePendingEdits" @withdraw="openWithdrawDialog" />
            </Transition>
          </div>
          <BacklogDock :orders="store.backlogOrders" :molds="store.molds" :open="store.backlogDockOpen" :can-append="store.canEdit && Boolean(store.planningPlan)" :can-edit-demand="store.canCreateDemand" :append-disabled-reason="appendDisabledReason" @toggle="store.backlogDockOpen = !store.backlogDockOpen" @view="openBacklogOrder" @append="openManualAppend" @edit="openManualDemand" @delete="openBacklogCancel" />
        </section>

        <ScheduleTimeline v-else-if="store.activeView === 'timeline'" :machines="store.machines" :tasks="store.tasks" :orders="store.orders" :business-date="store.plan?.businessDate || new Date().toISOString().slice(0, 10)" :scroll-left="store.timelineScrollLeft" :zoom="store.timelineZoom" @update:scroll-left="store.timelineScrollLeft = $event" @update:zoom="store.timelineZoom = $event" />

        <section v-else-if="store.activeView === 'backlog'" class="backlog-view">
          <header>
            <div><span class="view-icon"><Boxes :size="18" /></span><div><strong>待排订单</strong><p>下单表与手工需求都可直接排入草案；实体模具在发布前校验</p></div></div>
            <button :disabled="!store.canCreateDemand" @click="openManualDemand()"><Plus :size="15" />新增排期任务</button>
            <button :disabled="!store.canCreateDemand || enrichingMolds" @click="enrichBacklogMolds"><Sparkles :size="15" />{{ enrichingMolds ? '匹配中' : '从模具库补齐' }}</button>
            <label><Search :size="15" /><input v-model="store.search" placeholder="搜索订单、模号、货号、产品" /></label>
          </header>
          <div class="backlog-list">
            <article v-for="order in store.backlogOrders.filter((item) => !store.search || [item.orderNo, sourceMoldNo(item), item.itemNo, item.productName].join(' ').toLowerCase().includes(store.search.toLowerCase()))" :key="order.id">
              <span class="priority" :class="order.priorityCode.toLowerCase()">{{ order.priorityCode === 'CRITICAL' ? '特急' : order.priorityCode === 'URGENT' ? '加急' : '普通' }}</span>
              <div><strong>{{ sourceMoldNo(order) }} · {{ order.productName }}</strong><p>{{ order.orderNo }} · {{ order.itemNo }} · {{ order.sourceType === 'MANUAL_PLANNING_DEMAND' ? '手工需求' : '下单表' }} · 欠 {{ order.outstandingQuantity.toLocaleString('zh-CN') }} · {{ order.deliveryDueDate || '交期待补充' }}</p></div>
              <dl><div><dt>模具补齐</dt><dd>{{ moldEnrichmentLabel(order) }}</dd></div><div><dt>资格状态</dt><dd>{{ moldReadinessLabel(order) }}</dd></div></dl>
              <div class="backlog-actions">
                <button v-if="order.sourceType === 'MANUAL_PLANNING_DEMAND'" :disabled="!store.canCreateDemand" @click="openManualDemand(order.id)">修改需求</button>
                <button :disabled="!store.planningPlan || !hasSchedulableMold(order)" :title="backlogAppendTitle(order)" @click="openManualAppend(order.id)">追加到机台末尾</button>
                <button class="danger" :disabled="!store.canCancelBacklogOrder" @click="openBacklogCancel(order.id)"><Trash2 :size="14" />删除</button>
              </div>
            </article>
            <p v-if="!store.backlogOrders.length" class="empty-copy">当前没有待排订单</p>
          </div>
        </section>

        <section v-else-if="store.activeView === 'alerts'" class="alert-view"><header><div><span class="view-icon danger"><ShieldAlert :size="18" /></span><div><strong>异常预警</strong><p>按当前快照聚合交期、资料与机台风险</p></div></div></header><div class="alert-list"><article v-for="alert in store.alerts" :key="alert.title" :class="alert.tone"><span><AlertOctagon v-if="alert.tone === 'danger'" :size="18" /><ShieldAlert v-else :size="18" /></span><div><strong>{{ alert.title }}</strong><p>{{ alert.description }}</p></div><button @click="store.activeView = 'plan'; store.riskFilter = alert.tone === 'danger' ? 'overdue' : alert.tone === 'warning' ? 'review' : 'all'">查看计划</button></article></div></section>

        <Phase5OperationsDashboard v-else-if="store.activeView === 'analytics'" :analytics="store.phase5Analytics" :loading="store.phase5AnalyticsLoading" :error="store.phase5AnalyticsError" :can-manage-rules="store.canManageRules" @refresh="store.loadPhase5Analytics" @calibrate="store.calibratePhase5SpeedModels" />

        <section v-else key="history" class="history-view"><header><div><span class="view-icon"><History :size="18" /></span><div><strong>自动排期运行记录</strong><p>保留输入快照、方案指标、未排原因、应用人和版本信息</p></div></div></header><ScheduleRunHistory :runs="store.autoScheduleRuns" @select="openScheduleRun" /></section>
        </Transition>
      </section>
    </main>
    <AutoSchedulePreviewDialog :open="store.autoScheduleDialogOpen" :backlog-count="store.backlogOrders.length" :machine-count="store.machines.length" :plan-status="store.plan?.status ?? ''" :can-edit="store.canEdit" :can-override="store.canOverride" :run="store.autoScheduleRun" :comparison-runs="store.autoScheduleComparisonRuns" :loading="store.autoScheduleLoading" :error="store.autoScheduleError" :orders="store.orders" :machines="store.machines" @close="store.autoScheduleDialogOpen = false" @generate="store.generateAutoSchedulePreview" @compare="store.generateAutoScheduleAlternatives" @select="store.selectAutoScheduleRun" @replay="store.replayAutoScheduleRun" @apply="store.applyAutoScheduleRun" />
    <ManualMoveDialog :preview="store.movePreview" :machines="store.machines" :loading="store.moveLoading" :can-override="store.canOverride" @close="store.movePreview = null" @update="store.updateMovePreview" @confirm="store.confirmMove" />
    <PublishPlanDialog :open="publishDialogOpen" :plan="store.planningPlan" :task-count="store.planningDraftPlan.tasks.length" :can-publish="store.canPublish" :publishing="store.publishingPlan" :error="store.publishPlanError" @close="publishDialogOpen = false" @confirm="confirmPublishPlan" />
    <WithdrawTaskDialog :open="withdrawDialogOpen" :task="store.selectedTask" :order="store.selectedOrder" :plan-status="store.plan?.status ?? ''" :can-withdraw="store.canWithdraw" :disabled-reason="store.withdrawDisabledReason" :withdrawing="store.withdrawingTask" :error="store.withdrawTaskError" @close="withdrawDialogOpen = false" @confirm="confirmWithdrawTask" />
    <BacklogOrderCancelDialog :open="Boolean(backlogCancelOrderId)" :order="backlogCancelOrder" :can-cancel="store.canCancelBacklogOrder" :cancelling="store.cancellingBacklogOrderId === backlogCancelOrderId" :error="store.cancelBacklogOrderError" @close="backlogCancelOrderId = null" @confirm="confirmBacklogCancel" />
    <RevisionConflictDialog :conflict="store.revisionConflict" :loading="store.savingEdits || store.moveLoading" @close="store.revisionConflict = null" @use-server="store.discardPendingEdits" @reapply="reapplyConflict" />
    <InjectionSchedulingImportWizard :open="importWizardOpen" :factory-id="store.factoryId as FactoryId" :business-date="store.planningPlan?.businessDate || store.plan?.businessDate || new Date().toISOString().slice(0, 10)" :can-import="store.canImport" :can-confirm-demand="store.canConfirmDemand" :can-propose-profile="store.canProposeImportProfile" :can-propose-master-data="store.canProposeMasterData" :can-manage-profiles="store.canManageImportProfiles" :can-review-shared-molds="store.canReviewSharedMolds" :can-activate-shared-molds="store.canActivateSharedMolds" :can-manage-factory-capabilities="store.canManageFactoryCapabilities" :can-manage-shared-mold-prices="store.canManageSharedMoldPrices" :can-manage-master="store.canManageMaster" :initial-batch-id="importBatchId" :source-mode="store.sourceMode" @close="closeImportWizard" @batch-change="trackImportBatch" @confirmed="importConfirmed" />
    <InjectionSchedulingExportDialog :open="exportDialogOpen" :factory-id="store.factoryId as FactoryId" :plan="store.plan" :can-export="store.canExport" :source-mode="store.sourceMode" :pending-count="store.pendingEditCount" @close="exportDialogOpen = false" @exported="store.saveMessage = `导出完成：${$event.fileName}`" />
    <ManualAppendDialog :open="Boolean(manualAppendOrderId)" :factory-id="store.factoryId as FactoryId" :plan="store.planningPlan" :order="manualAppendOrder" :machines="store.machines" :can-edit="store.canEdit" @close="manualAppendOrderId = null" @confirmed="manualAppendConfirmed" />
    <ManualDemandDialog :open="manualDemandOpen" :factory-id="store.factoryId as FactoryId" :business-date="store.planningPlan?.businessDate || store.plan?.businessDate || new Date().toISOString().slice(0, 10)" :order="manualDemandOrder" :can-edit="store.canCreateDemand" @close="manualDemandOpen = false" @saved="manualDemandChanged('排期需求已保存并加入待排池。')" @cancelled="manualDemandChanged('手工排期需求已取消。')" />
    <div v-if="store.refreshing" class="sync-progress" aria-hidden="true"><span></span></div>
    <SchedulingFeedbackToast :message="feedback.message" :tone="feedback.tone" />
  </div>
</template>

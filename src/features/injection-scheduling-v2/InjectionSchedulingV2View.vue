<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { AlertOctagon, Boxes, Clock3, Columns3, Filter, History, ListChecks, PanelBottomOpen, Search, ShieldAlert, SlidersHorizontal, Sparkles } from '@lucide/vue'
import { useInjectionSchedulingV2Store } from './stores/useInjectionSchedulingV2Store'
import { useScheduleLiveEvents } from './composables/useScheduleLiveEvents'
import AutoSchedulePreviewDialog from './components/AutoSchedulePreviewDialog.vue'
import BacklogDock from './components/BacklogDock.vue'
import ColumnPresetMenu from './components/ColumnPresetMenu.vue'
import MachinePlanGrid from './components/MachinePlanGrid.vue'
import ScheduleTimeline from './components/ScheduleTimeline.vue'
import SchedulingCommandBar from './components/SchedulingCommandBar.vue'
import SchedulingKpiStrip from './components/SchedulingKpiStrip.vue'
import TaskInspectorDrawer from './components/TaskInspectorDrawer.vue'
import ManualMoveDialog from './components/ManualMoveDialog.vue'
import RevisionConflictDialog from './components/RevisionConflictDialog.vue'
import ScheduleRunHistory from './components/ScheduleRunHistory.vue'
import type { AutoScheduleRunRecord } from './types'
import type { ColumnPreset, EditableCellKey, FactoryId, WorkspaceView } from './types'
import './injection-scheduling-v2.css'

const route = useRoute()
const router = useRouter()
const store = useInjectionSchedulingV2Store()
const tabs: Array<{ key: WorkspaceView; label: string; icon: typeof ListChecks }> = [
  { key: 'plan', label: '计划总表', icon: ListChecks }, { key: 'timeline', label: '机台时间轴', icon: Clock3 },
  { key: 'backlog', label: '待排订单', icon: Boxes }, { key: 'alerts', label: '异常预警', icon: ShieldAlert }, { key: 'history', label: '自动排期记录', icon: History },
]
const tabCount = computed<Record<WorkspaceView, number>>(() => ({ plan: store.tasks.length, timeline: store.machines.length, backlog: store.backlogOrders.length, alerts: store.alerts.length, history: store.autoScheduleRuns.length }))
const visibleKeys = computed(() => store.visibleColumns.map((column) => String(column.key)))
const selectedOpen = computed(() => Boolean(store.selectedTaskId && store.activeView === 'plan'))
const presetLabels: Record<ColumnPreset, string> = { planner: '计划员视图', production: '生产视图', fit: '资格适配', full: '完整字段' }

async function changeFactory(value: string) {
  store.setFactory(value)
  await router.replace({ query: { ...route.query, factory: value } })
  await store.load()
}
function resizeColumn(key: string, width: number) { store.columnWidths = { ...store.columnWidths, [key]: Math.max(54, Math.min(420, width)) } }
function closeInspector() { store.selectedTaskId = null }
function openBacklogOrder(orderId: string) { store.activeView = 'backlog'; const order = store.orders.find((item) => item.id === orderId); store.search = order?.orderNo ?? '' }
function stageReport(edits: Array<{ key: EditableCellKey; value: string | number }>) {
  if (!store.selectedTaskId) return
  edits.forEach((edit) => store.stageCellEdit(store.selectedTaskId!, edit.key, edit.value))
}
async function reapplyConflict() { await store.revisionConflict?.retry?.() }
function openScheduleRun(run: AutoScheduleRunRecord) { store.selectAutoScheduleRun(run); store.autoScheduleDialogOpen = true }

watch(() => route.query.factory, (value) => {
  const normalized = Array.isArray(value) ? value[0] : value
  if (typeof normalized === 'string' && normalized !== store.factoryId) { store.setFactory(normalized); void store.load() }
})
onMounted(async () => {
  const requested = Array.isArray(route.query.factory) ? route.query.factory[0] : route.query.factory
  if (typeof requested === 'string') store.setFactory(requested)
  await store.load()
})
useScheduleLiveEvents(store.pollEvents)
</script>

<template>
  <div class="injection-scheduling-v2" :class="{ 'has-backlog-dock': store.backlogDockOpen && store.activeView === 'plan' }">
    <SchedulingCommandBar :factory-id="store.factoryId as FactoryId" :factory-name="store.factoryName" :source-mode="store.sourceMode" :source-message="store.sourceMessage" :refreshing="store.refreshing" :search="store.search" :last-synced-at="store.lastSyncedAt" :plan-status="store.plan?.status ?? ''" :pending-count="store.pendingEditCount" :saving="store.savingEdits" :can-save="store.canEdit || store.canReport" :save-message="store.saveMessage" @update:factory-id="changeFactory" @update:search="store.search = $event" @refresh="store.load({ quiet: true })" @open-auto-schedule="store.autoScheduleDialogOpen = true" @save="store.savePendingEdits" @discard="store.discardPendingEdits" />
    <main>
      <div v-if="store.sourceMode === 'fallback'" class="fallback-banner"><AlertOctagon :size="15" /><strong>只读演示：</strong><span>{{ store.sourceMessage }}</span></div>
      <SchedulingKpiStrip :summary="store.summary" />
      <section class="scheduling-workspace">
        <nav class="workspace-tabs" aria-label="排产视图">
          <button v-for="tab in tabs" :key="tab.key" :class="{ active: store.activeView === tab.key }" @click="store.activeView = tab.key"><component :is="tab.icon" :size="15" /><span>{{ tab.label }}</span><em>{{ tabCount[tab.key] }}</em></button>
          <div class="workspace-status"><span class="status-dot"></span>{{ store.plan ? `${store.plan.status} · r${store.plan.revision}` : '暂无当前计划' }}<b>轮询 {{ store.pollingRevision }}</b></div>
        </nav>

        <template v-if="store.activeView === 'plan'">
          <div class="plan-toolbar">
            <div class="toolbar-search"><Search :size="15" /><input v-model="store.search" placeholder="机号 / 工模 / 产品 / 单号 / 货号" /></div>
            <label><Filter :size="14" /><select v-model="store.statusFilter"><option value="all">全部状态</option><option value="RUNNING">正在生产</option><option value="QUEUED">排队中</option><option value="BLOCKED">异常 / 待料</option><option value="COMPLETED">已完成</option></select></label>
            <label><ShieldAlert :size="14" /><select v-model="store.riskFilter"><option value="all">全部风险</option><option value="overdue">已经超期</option><option value="soon">3 天内到期</option><option value="review">资格待复核</option></select></label>
            <span class="rule-note">资格口径：安数 · 射胶量 · 机械手 · 夹具 · 工艺限制 · 状态</span>
            <div class="toolbar-spacer"></div>
            <button class="toolbar-button" :class="{ active: store.columnMenuOpen }" @click="store.columnMenuOpen = !store.columnMenuOpen"><Columns3 :size="15" />{{ presetLabels[store.activePreset] }}</button>
            <button class="toolbar-button" @click="store.backlogDockOpen = !store.backlogDockOpen"><PanelBottomOpen :size="15" />待排池</button>
            <button class="toolbar-button auto" @click="store.autoScheduleDialogOpen = true"><Sparkles :size="15" />自动排期</button>
            <ColumnPresetMenu :open="store.columnMenuOpen" :preset="store.activePreset" :visible-keys="visibleKeys" :widths="store.columnWidths" @close="store.columnMenuOpen = false" @preset="store.setPreset" @toggle="store.toggleColumn" @move="store.moveColumn" @reset="store.resetColumns" @resize="resizeColumn" />
          </div>
          <div class="plan-work-area" :class="{ 'inspector-open': selectedOpen }">
            <MachinePlanGrid :rows="store.gridRows" :columns="store.visibleColumns" :collapsed-machine-ids="store.collapsedMachineIds" :widths="store.columnWidths" :sort="store.sort" :plan-status="store.plan?.status ?? ''" :can-edit="store.canEdit" :can-report="store.canReport" :pending-edits="store.cellDrafts" @toggle-machine="store.toggleMachine" @select="store.selectTask" @sort="store.cycleSort" @resize="resizeColumn" @edit="store.stageCellEdit" @move-request="store.prepareMove" @keyboard-move="store.moveByKeyboard" />
            <TaskInspectorDrawer v-if="selectedOpen" :task="store.selectedTask" :order="store.selectedOrder" :mold="store.selectedMold" :machine="store.selectedMachine" :tab="store.inspectorTab" :events="store.events" :plan-status="store.plan?.status ?? ''" :can-report="store.canReport" :pending-count="store.pendingEditCount" :saving="store.savingEdits" @update:tab="store.inspectorTab = $event" @close="closeInspector" @stage="stageReport" @save="store.savePendingEdits" />
          </div>
          <BacklogDock :orders="store.backlogOrders" :molds="store.molds" :open="store.backlogDockOpen" @toggle="store.backlogDockOpen = !store.backlogDockOpen" @view="openBacklogOrder" />
        </template>

        <ScheduleTimeline v-else-if="store.activeView === 'timeline'" :machines="store.machines" :tasks="store.tasks" :orders="store.orders" />

        <section v-else-if="store.activeView === 'backlog'" class="backlog-view"><header><div><span class="view-icon"><Boxes :size="18" /></span><div><strong>待排订单</strong><p>查看订单资格与候选机台解释；正式入计划由草案流程处理</p></div></div><label><Search :size="15" /><input v-model="store.search" placeholder="搜索订单、货号、产品" /></label></header><div class="backlog-list"><article v-for="order in store.backlogOrders.filter((item) => !store.search || [item.orderNo, item.itemNo, item.productName].join(' ').toLowerCase().includes(store.search.toLowerCase()))" :key="order.id"><span class="priority" :class="order.priorityCode.toLowerCase()">{{ order.priorityCode === 'CRITICAL' ? '特急' : order.priorityCode === 'URGENT' ? '加急' : '普通' }}</span><div><strong>{{ order.orderNo }} · {{ order.productName }}</strong><p>{{ order.itemNo }} · 欠 {{ order.outstandingQuantity.toLocaleString('zh-CN') }} · {{ order.deliveryDueDate || '交期待补充' }}</p></div><dl><div><dt>物料状态</dt><dd>{{ order.materialReadinessStatus }}</dd></div><div><dt>资格状态</dt><dd>{{ store.molds.find((mold) => mold.id === order.moldId)?.normalizationStatus === 'COMPLETE' ? '可评估' : '待复核' }}</dd></div></dl><button disabled>由草案计划分配</button></article><p v-if="!store.backlogOrders.length" class="empty-copy">当前没有待排订单</p></div></section>

        <section v-else-if="store.activeView === 'alerts'" class="alert-view"><header><div><span class="view-icon danger"><ShieldAlert :size="18" /></span><div><strong>异常预警</strong><p>按当前快照聚合交期、资料与机台风险</p></div></div></header><div class="alert-list"><article v-for="alert in store.alerts" :key="alert.title" :class="alert.tone"><span><AlertOctagon v-if="alert.tone === 'danger'" :size="18" /><ShieldAlert v-else :size="18" /></span><div><strong>{{ alert.title }}</strong><p>{{ alert.description }}</p></div><button @click="store.activeView = 'plan'; store.riskFilter = alert.tone === 'danger' ? 'overdue' : alert.tone === 'warning' ? 'review' : 'all'">查看计划</button></article></div></section>

        <section v-else class="history-view"><header><div><span class="view-icon"><History :size="18" /></span><div><strong>自动排期运行记录</strong><p>保留输入快照、方案指标、未排原因、应用人和 revision</p></div></div></header><ScheduleRunHistory :runs="store.autoScheduleRuns" @select="openScheduleRun" /></section>
      </section>
    </main>
    <AutoSchedulePreviewDialog :open="store.autoScheduleDialogOpen" :backlog-count="store.backlogOrders.length" :machine-count="store.machines.length" :plan-status="store.plan?.status ?? ''" :can-edit="store.canEdit" :can-override="store.canOverride" :run="store.autoScheduleRun" :comparison-runs="store.autoScheduleComparisonRuns" :loading="store.autoScheduleLoading" :error="store.autoScheduleError" :orders="store.orders" :machines="store.machines" @close="store.autoScheduleDialogOpen = false" @generate="store.generateAutoSchedulePreview" @compare="store.generateAutoScheduleAlternatives" @select="store.selectAutoScheduleRun" @replay="store.replayAutoScheduleRun" @apply="store.applyAutoScheduleRun" />
    <ManualMoveDialog :preview="store.movePreview" :machines="store.machines" :loading="store.moveLoading" :can-override="store.canOverride" @close="store.movePreview = null" @update="store.updateMovePreview" @confirm="store.confirmMove" />
    <RevisionConflictDialog :conflict="store.revisionConflict" :loading="store.savingEdits || store.moveLoading" @close="store.revisionConflict = null" @use-server="store.discardPendingEdits" @reapply="reapplyConflict" />
    <div v-if="store.loading" class="loading-layer"><span></span><strong>正在读取 {{ store.factoryName }} 排产快照…</strong></div>
  </div>
</template>

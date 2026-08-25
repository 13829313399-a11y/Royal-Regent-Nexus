<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import {
  Activity, ArrowLeft, Boxes, ChevronDown, ClockAlert, Columns3, Download,
  Grid3X3, ListTodo, Moon, RefreshCw, Search, Sparkles, Sun, TriangleAlert, Upload, X,
} from '@lucide/vue'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { useInjectionWorkbenchStore } from './store'
import WorkbenchGrid from './WorkbenchGrid.vue'
import MachineQueueBoard from './MachineQueueBoard.vue'
import JobDetailDrawer from './JobDetailDrawer.vue'
import SimpleImportDialog from './SimpleImportDialog.vue'
import ScheduleSuggestionDialog from './ScheduleSuggestionDialog.vue'
import WorkbenchActionButton from './ui/WorkbenchActionButton.vue'
import type { ShiftReportInput, WorkbenchCellChange, WorkbenchFactoryId, WorkbenchJob, WorkbenchView } from './types'
import './workbench.css'
import './workbench.motion.css'

const route = useRoute()
const router = useRouter()
const store = useInjectionWorkbenchStore()
const {
  factoryId, factoryName, snapshot, loading, saving, message, error, lastSavedAt,
  view, preset, search, statusFilter, machineFilter, selectedJobId, selectedJob,
  schedulePreview, scheduling, columns, pendingCount, filteredJobs, jobsByMachine,
} = storeToRefs(store)
const importOpen = ref(false)
const scheduleOpen = ref(false)
const insightOpen = ref(true)
const searchInput = ref<HTMLInputElement | null>(null)
const tabSheet = ref<HTMLButtonElement | null>(null)
const tabQueue = ref<HTMLButtonElement | null>(null)
const factories: Array<{ id: WorkbenchFactoryId; label: string }> = [
  { id: 'huaxing', label: '华兴' }, { id: 'huakang-a', label: '华康 A' },
  { id: 'huakang-b', label: '华康 B' }, { id: 'huakang-c', label: '华康 C' },
  { id: 'huakang-d', label: '华康 D' }, { id: 'huadeng', label: '华登' },
]
const planModeLabel = computed(() => snapshot.value?.planMode === 'PLANNING' ? '规划中' : snapshot.value?.planMode === 'EXECUTION' ? '执行中' : '暂无计划')
const editable = computed(() => snapshot.value?.planMode !== 'EXECUTION')
const pendingKeys = computed(() => Object.keys(store.pending))
const selectedMachineSummary = computed(() => snapshot.value?.machines.find((machine) => machine.id === machineFilter.value)?.parsedConstraintSummary ?? '')
const syncState = computed(() => {
  if (error.value) return { label: '同步需处理', tone: 'red' as const }
  if (saving.value) return { label: '正在自动保存', tone: 'amber' as const }
  if (pendingCount.value) return { label: `${pendingCount.value} 处待保存`, tone: 'amber' as const }
  return { label: lastSavedAt.value ? `已同步 ${lastSavedAt.value}` : '数据已同步', tone: 'green' as const }
})
const kpis = computed(() => [
  { label: '待排任务', value: snapshot.value?.summary.unplannedCount ?? 0, icon: Boxes, tone: 'slate', hint: '等待分配机台' },
  { label: '已超交期', value: snapshot.value?.summary.overdueCount ?? 0, icon: ClockAlert, tone: 'red', hint: '需要优先处理' },
  { label: '冲突 / 暂停', value: snapshot.value?.summary.conflictCount ?? 0, icon: TriangleAlert, tone: 'amber', hint: '存在排程阻塞' },
  { label: '生产中', value: snapshot.value?.summary.runningCount ?? 0, icon: Activity, tone: 'teal', hint: '当前运行任务' },
  { label: '今日白班', value: (snapshot.value?.summary.todayDayQuantity ?? 0).toLocaleString('zh-CN'), icon: Sun, tone: 'blue', hint: '累计回报数量' },
  { label: '今日夜班', value: (snapshot.value?.summary.todayNightQuantity ?? 0).toLocaleString('zh-CN'), icon: Moon, tone: 'indigo', hint: '累计回报数量' },
])

function validFactory(value: unknown): value is WorkbenchFactoryId { return factories.some((factory) => factory.id === value) }
async function changeFactory(event: Event) {
  const next = (event.target as HTMLSelectElement).value
  if (!validFactory(next)) return
  if (await store.setFactory(next)) await router.replace({ query: { ...route.query, factory: next } })
}
function stage(changes: WorkbenchCellChange[]) {
  try { store.stageChanges(changes) }
  catch (cause) { store.error = cause instanceof Error ? cause.message : '修改无法暂存' }
}
function report(job: WorkbenchJob, input: ShiftReportInput) { void store.reportShift(job, input) }
async function imported(importMessage: string) { store.message = importMessage; await store.load({ quiet: true }) }
async function openSchedule() { scheduleOpen.value = true; store.schedulePreview = null }
async function applySchedule() { await store.applySchedule(); if (!store.error) scheduleOpen.value = false }
function switchView(next: WorkbenchView) { view.value = next }
async function moveTab(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const next: WorkbenchView = event.key === 'ArrowLeft' || event.key === 'Home' ? 'sheet' : 'queue'
  switchView(next)
  await nextTick()
  ;(next === 'sheet' ? tabSheet.value : tabQueue.value)?.focus()
}
function clearSearch() { search.value = ''; searchInput.value?.focus() }
function clearFilters() { search.value = ''; statusFilter.value = 'ALL'; machineFilter.value = 'ALL' }
async function exportCurrentView() {
  const rows = filteredJobs.value
  const header = columns.value.map((column) => column.label).join('\t')
  const body = rows.map((job) => columns.value.map((column) => String(job[column.key] ?? '')).join('\t')).join('\n')
  const blob = new Blob([`\ufeff${header}\n${body}`], { type: 'text/tab-separated-values;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `${factoryName.value}-注塑排产-${snapshot.value?.businessDate || 'current'}.tsv`
  link.click()
  URL.revokeObjectURL(link.href)
  store.message = `已导出当前筛选的 ${rows.length} 行`
}

onMounted(async () => {
  const requested = route.query.factory
  if (validFactory(requested)) store.factoryId = requested
  await store.load()
})
watch(() => route.query.factory, async (value) => {
  if (validFactory(value) && value !== store.factoryId) await store.setFactory(value)
})
</script>

<template>
  <main class="injection-workbench">
    <header class="wb-command-bar">
      <WorkbenchActionButton variant="ghost" icon-only aria-label="返回模块中心" @click="router.push('/modules')"><template #icon><ArrowLeft :size="18" /></template></WorkbenchActionButton>
      <div class="wb-brand"><span class="wb-brand-mark"><img src="/brand/huadeng_group_dynamic_logo.svg" alt="华登集团" /></span><div><h1>注塑生产计划</h1><p>{{ snapshot?.businessDate || '业务日待建立' }} · {{ planModeLabel }}</p></div></div>
      <label class="wb-factory-select"><span>当前厂区</span><select :value="factoryId" @change="changeFactory"><option v-for="factory in factories" :key="factory.id" :value="factory.id">{{ factory.label }}</option></select></label>
      <div class="wb-save-state" role="status" aria-live="polite"><span class="wb-live-dot" :class="syncState.tone"></span><span>{{ syncState.label }}</span></div>
      <nav class="wb-command-actions" aria-label="工作台命令">
        <WorkbenchActionButton variant="secondary" @click="importOpen = true"><template #icon><Upload :size="15" /></template>导入 Excel</WorkbenchActionButton>
        <WorkbenchActionButton variant="primary" :disabled="!snapshot?.planId" @click="openSchedule"><template #icon><Sparkles :size="15" /></template>排期建议</WorkbenchActionButton>
        <WorkbenchActionButton variant="secondary" :disabled="!filteredJobs.length" @click="exportCurrentView"><template #icon><Download :size="15" /></template>导出当前表</WorkbenchActionButton>
        <WorkbenchActionButton variant="ghost" icon-only :loading="loading" aria-label="刷新数据" @click="store.load({ quiet: true })"><template #icon><RefreshCw :size="17" /></template></WorkbenchActionButton>
      </nav>
      <AccountMenu variant="obsidian" compact />
    </header>

    <section class="wb-kpi-strip" aria-label="排产摘要">
      <article v-for="(kpi, index) in kpis" :key="kpi.label" class="wb-kpi-card" :class="`tone-${kpi.tone}`" :style="{ '--wb-stagger': `${index * 32}ms` }">
        <span class="wb-kpi-icon"><component :is="kpi.icon" :size="17" aria-hidden="true" /></span>
        <div><span>{{ kpi.label }}</span><small>{{ kpi.hint }}</small></div>
        <Transition name="wb-metric" mode="out-in"><b :key="String(kpi.value)">{{ kpi.value }}</b></Transition>
      </article>
    </section>

    <section class="wb-filter-bar" aria-label="筛选与视图">
      <div class="wb-view-switch" role="tablist" aria-label="工作台视图" @keydown="moveTab">
        <span class="wb-tab-indicator" :class="{ queue: view === 'queue' }" aria-hidden="true"></span>
        <button id="wb-tab-sheet" ref="tabSheet" type="button" role="tab" :aria-selected="view === 'sheet'" aria-controls="wb-panel-sheet" :tabindex="view === 'sheet' ? 0 : -1" @click="switchView('sheet')"><Grid3X3 :size="15" />计划表</button>
        <button id="wb-tab-queue" ref="tabQueue" type="button" role="tab" :aria-selected="view === 'queue'" aria-controls="wb-panel-queue" :tabindex="view === 'queue' ? 0 : -1" @click="switchView('queue')"><ListTodo :size="15" />机台队列</button>
      </div>
      <label class="wb-search"><Search :size="15" aria-hidden="true" /><input ref="searchInput" v-model="search" aria-label="搜索排产任务" placeholder="搜索机台、单号、货号、产品或模具" @keydown.esc="clearSearch" /><button v-if="search" type="button" aria-label="清除搜索" @click="clearSearch"><X :size="14" /></button></label>
      <label><span>状态</span><select v-model="statusFilter"><option value="ALL">全部状态</option><option value="UNPLANNED">待排</option><option value="PLANNED">已排</option><option value="RUNNING">生产中</option><option value="PAUSED">暂停</option><option value="DONE">完成</option></select></label>
      <label><span>机台</span><select v-model="machineFilter"><option value="ALL">全部机台</option><option value="UNPLANNED">待排池</option><option v-for="machine in snapshot?.machines ?? []" :key="machine.id" :value="machine.id">{{ machine.code }}</option></select></label>
      <label v-if="view === 'sheet'"><Columns3 :size="14" aria-hidden="true" /><span>列模板</span><select v-model="preset"><option value="scheduler">调度排机</option><option value="reporter">班次回报</option><option value="full">全部字段</option></select></label>
      <span class="wb-row-count"><b>{{ filteredJobs.length }}</b> 行任务</span>
    </section>

    <section class="wb-notice-stack" aria-label="工作台通知">
      <Transition name="wb-fade-up"><div v-if="selectedMachineSummary" class="wb-insight"><button type="button" :aria-expanded="insightOpen" aria-controls="wb-machine-insight" @click="insightOpen = !insightOpen"><TriangleAlert :size="14" /><span>当前机台限制</span><ChevronDown :size="14" :class="{ open: insightOpen }" /></button><p v-show="insightOpen" id="wb-machine-insight">{{ selectedMachineSummary }}</p></div></Transition>
      <Transition name="wb-fade-up" mode="out-in">
        <p v-if="error" key="error" class="wb-error-banner" role="alert"><b>操作未完成：</b><span>{{ error }}</span><button type="button" @click="error = ''">关闭</button></p>
        <p v-else-if="message" key="message" class="wb-message-banner" role="status" aria-live="polite"><StatusPill label="已更新" tone="green" compact /><span>{{ message }}</span><button v-if="pendingCount" type="button" @click="store.savePendingChanges">立即保存</button><button v-if="pendingCount" type="button" @click="store.discardPendingChanges">放弃修改</button></p>
      </Transition>
    </section>

    <section class="wb-content" :aria-busy="loading">
      <div v-if="loading && !snapshot" class="wb-loading-skeleton" role="status" aria-live="polite" aria-label="正在读取排产数据"><span v-for="index in 9" :key="index"></span></div>
      <Transition v-else name="wb-view-morph" mode="out-in">
        <WorkbenchGrid v-if="view === 'sheet'" id="wb-panel-sheet" key="sheet" role="tabpanel" aria-labelledby="wb-tab-sheet" :jobs="filteredJobs" :columns="columns" :selected-job-id="selectedJobId" :editable="editable" :pending-keys="pendingKeys" @select="selectedJobId = $event" @stage="stage" @error="error = $event" @clear-filters="clearFilters" @import="importOpen = true" />
        <MachineQueueBoard v-else id="wb-panel-queue" key="queue" role="tabpanel" aria-labelledby="wb-tab-queue" :machines="snapshot?.machines ?? []" :jobs-by-machine="jobsByMachine" :selected-job-id="selectedJobId" :editable="snapshot?.planMode === 'PLANNING'" @select="selectedJobId = $event" @move="store.moveJob" @withdraw="store.withdrawJob" />
      </Transition>
    </section>

    <footer class="wb-status-bar"><span>Enter / Tab / 方向键移动 · 支持从 Excel 多单元格粘贴</span><span>版本 {{ snapshot?.pollingRevision ?? 0 }} · 每次修改保留审计信息</span></footer>

    <JobDetailDrawer :job="selectedJob" :can-report="Boolean(selectedJob?.taskId) && snapshot?.planMode === 'EXECUTION'" :saving="saving" @close="selectedJobId = null" @report="report" />
    <SimpleImportDialog :open="importOpen" :factory-id="factoryId" :business-date="snapshot?.businessDate || new Date().toISOString().slice(0, 10)" @close="importOpen = false" @imported="imported" />
    <ScheduleSuggestionDialog :open="scheduleOpen" :preview="schedulePreview" :loading="scheduling" :can-apply="snapshot?.planMode === 'PLANNING'" @close="scheduleOpen = false" @preview="store.previewSchedule" @apply="applySchedule" />
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { ArrowLeft, Columns3, Download, Grid3X3, ListTodo, RefreshCw, Search, Sparkles, Upload } from '@lucide/vue'
import { useInjectionWorkbenchStore } from './store'
import WorkbenchGrid from './WorkbenchGrid.vue'
import MachineQueueBoard from './MachineQueueBoard.vue'
import JobDetailDrawer from './JobDetailDrawer.vue'
import SimpleImportDialog from './SimpleImportDialog.vue'
import ScheduleSuggestionDialog from './ScheduleSuggestionDialog.vue'
import type { ShiftReportInput, WorkbenchCellChange, WorkbenchFactoryId, WorkbenchJob } from './types'
import './workbench.css'

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
const factories: Array<{ id: WorkbenchFactoryId; label: string }> = [
  { id: 'huaxing', label: '华兴' }, { id: 'huakang-a', label: '华康 A' },
  { id: 'huakang-b', label: '华康 B' }, { id: 'huakang-c', label: '华康 C' },
  { id: 'huakang-d', label: '华康 D' }, { id: 'huadeng', label: '华登' },
]
const planModeLabel = computed(() => snapshot.value?.planMode === 'PLANNING' ? '规划中' : snapshot.value?.planMode === 'EXECUTION' ? '执行中' : '暂无计划')
const editable = computed(() => snapshot.value?.planMode !== 'EXECUTION')
const pendingKeys = computed(() => Object.keys(store.pending))
const selectedMachineSummary = computed(() => snapshot.value?.machines.find((machine) => machine.id === machineFilter.value)?.parsedConstraintSummary ?? '')

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
      <button type="button" class="wb-icon-button" aria-label="返回模块中心" @click="router.push('/modules')"><ArrowLeft :size="18" /></button>
      <div class="wb-brand"><span>RR</span><div><h1>注塑生产计划</h1><p>{{ factoryName }} · {{ snapshot?.businessDate || '业务日待建立' }} · {{ planModeLabel }}</p></div></div>
      <label class="wb-factory-select"><span>厂区</span><select :value="factoryId" @change="changeFactory"><option v-for="factory in factories" :key="factory.id" :value="factory.id">{{ factory.label }}</option></select></label>
      <div class="wb-save-state" :class="{ danger: error }"><i :class="{ active: saving || pendingCount }"></i><span>{{ saving ? '自动保存中…' : pendingCount ? `${pendingCount} 处待保存` : error ? '保存需处理' : `已同步 ${lastSavedAt || ''}` }}</span></div>
      <div class="wb-command-actions">
        <button type="button" class="wb-secondary-button" @click="importOpen = true"><Upload :size="15" />导入 Excel</button>
        <button type="button" class="wb-secondary-button" :disabled="!snapshot?.planId" @click="openSchedule"><Sparkles :size="15" />排期建议</button>
        <button type="button" class="wb-secondary-button" :disabled="!filteredJobs.length" @click="exportCurrentView"><Download :size="15" />导出当前表</button>
        <button type="button" class="wb-icon-button" :disabled="loading" title="刷新" @click="store.load({ quiet: true })"><RefreshCw :size="17" :class="{ spinning: loading }" /></button>
      </div>
    </header>

    <section class="wb-kpi-strip" aria-label="排产摘要">
      <div><span>待排</span><b>{{ snapshot?.summary.unplannedCount ?? 0 }}</b></div>
      <div><span>超交期</span><b class="danger">{{ snapshot?.summary.overdueCount ?? 0 }}</b></div>
      <div><span>冲突/暂停</span><b class="warning">{{ snapshot?.summary.conflictCount ?? 0 }}</b></div>
      <div><span>生产中</span><b>{{ snapshot?.summary.runningCount ?? 0 }}</b></div>
      <div><span>今日白班</span><b>{{ (snapshot?.summary.todayDayQuantity ?? 0).toLocaleString('zh-CN') }}</b></div>
      <div><span>今日夜班</span><b>{{ (snapshot?.summary.todayNightQuantity ?? 0).toLocaleString('zh-CN') }}</b></div>
    </section>

    <section class="wb-filter-bar">
      <div class="wb-view-switch" aria-label="视图切换"><button type="button" :class="{ active: view === 'sheet' }" @click="view = 'sheet'"><Grid3X3 :size="15" />计划表</button><button type="button" :class="{ active: view === 'queue' }" @click="view = 'queue'"><ListTodo :size="15" />机台队列</button></div>
      <label class="wb-search"><Search :size="15" /><input v-model="search" placeholder="搜索机台、单号、货号、产品或模具" /></label>
      <label><span>状态</span><select v-model="statusFilter"><option value="ALL">全部状态</option><option value="UNPLANNED">待排</option><option value="PLANNED">已排</option><option value="RUNNING">生产中</option><option value="PAUSED">暂停</option><option value="DONE">完成</option></select></label>
      <label><span>机台</span><select v-model="machineFilter"><option value="ALL">全部机台</option><option value="UNPLANNED">待排池</option><option v-for="machine in snapshot?.machines ?? []" :key="machine.id" :value="machine.id">{{ machine.code }}</option></select></label>
      <label v-if="view === 'sheet'"><Columns3 :size="14" /><span>列模板</span><select v-model="preset"><option value="scheduler">调度排机</option><option value="reporter">班次回报</option><option value="full">全部字段</option></select></label>
      <span class="wb-row-count">{{ filteredJobs.length }} 行</span>
    </section>
    <div class="wb-notice-stack">
      <p v-if="selectedMachineSummary" class="wb-machine-filter-note">当前机台限制：{{ selectedMachineSummary }}</p>
      <p v-if="error" class="wb-error-banner"><b>操作未完成：</b>{{ error }}<button type="button" @click="error = ''">关闭</button></p>
      <p v-else-if="message" class="wb-message-banner">{{ message }}<button v-if="pendingCount" type="button" @click="store.savePendingChanges">立即保存</button><button v-if="pendingCount" type="button" @click="store.discardPendingChanges">放弃修改</button></p>
    </div>

    <section class="wb-content" :aria-busy="loading">
      <div v-if="loading && !snapshot" class="wb-loading">正在读取{{ factoryName }}排产数据…</div>
      <WorkbenchGrid v-else-if="view === 'sheet'" :jobs="filteredJobs" :columns="columns" :selected-job-id="selectedJobId" :editable="editable" :pending-keys="pendingKeys" @select="selectedJobId = $event" @stage="stage" @error="error = $event" />
      <MachineQueueBoard v-else :machines="snapshot?.machines ?? []" :jobs-by-machine="jobsByMachine" :selected-job-id="selectedJobId" :editable="snapshot?.planMode === 'PLANNING'" @select="selectedJobId = $event" @move="store.moveJob" @withdraw="store.withdrawJob" />
    </section>

    <footer class="wb-status-bar"><span>表格键盘：Enter / Tab / 方向键 · 支持从 Excel 多单元格粘贴</span><span>轮询版本 {{ snapshot?.pollingRevision ?? 0 }} · 每次修改保留审计信息</span></footer>

    <JobDetailDrawer :job="selectedJob" :can-report="Boolean(selectedJob?.taskId) && snapshot?.planMode === 'EXECUTION'" :saving="saving" @close="selectedJobId = null" @report="report" />
    <SimpleImportDialog :open="importOpen" :factory-id="factoryId" :business-date="snapshot?.businessDate || new Date().toISOString().slice(0, 10)" @close="importOpen = false" @imported="imported" />
    <ScheduleSuggestionDialog :open="scheduleOpen" :preview="schedulePreview" :loading="scheduling" :can-apply="snapshot?.planMode === 'PLANNING'" @close="scheduleOpen = false" @preview="store.previewSchedule" @apply="applySchedule" />
  </main>
</template>

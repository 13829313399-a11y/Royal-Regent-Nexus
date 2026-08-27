<script setup lang="ts">
import {
  AlertTriangle,
  ArrowLeft,
  CalendarClock,
  Check,
  ChevronRight,
  Download,
  Factory,
  FileUp,
  GripVertical,
  Info,
  LoaderCircle,
  Lock,
  Play,
  RefreshCw,
  Save,
  Search,
  Sparkles,
  Unlock,
  UploadCloud,
} from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import StatusPill from '@/components/common/StatusPill.vue'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'

import { injectionSchedulingApi } from './api'
import StandardImportDialog from './components/StandardImportDialog.vue'
import TaskDetailDrawer from './components/TaskDetailDrawer.vue'
import type { ScheduleRun, SchedulingJob, SchedulingMachine, SchedulingWorkbench } from './types'
import './workbench.css'

const props = defineProps<{ factoryId: string; factoryName: string }>()
const authStore = useAuthStore()
const workbench = ref<SchedulingWorkbench | null>(null)
const loading = ref(true)
const busyAction = ref('')
const error = ref('')
const notice = ref('')
const search = ref('')
const priorityFilter = ref('ALL')
const dueFilter = ref('ALL')
const machineFilter = ref('ALL')
const importOpen = ref(false)
const detailJob = ref<SchedulingJob | null>(null)
const scheduleRun = ref<ScheduleRun | null>(null)
const draggedJob = ref<SchedulingJob | null>(null)

const canImport = computed(() => authStore.can('injection_scheduling:import', props.factoryId))
const canEdit = computed(() => authStore.can('injection_scheduling:edit', props.factoryId))
const canPublish = computed(() => authStore.can('injection_scheduling:publish', props.factoryId) || canEdit.value)
const planLabel = computed(() => ({ PLANNING: '规划中', EXECUTION: '执行中', EMPTY: '暂无计划' }[workbench.value?.plan_mode ?? 'EMPTY']))

const filteredJobs = computed(() => {
  const needle = search.value.trim().toLocaleLowerCase()
  return (workbench.value?.jobs ?? []).filter((job) => {
    if (needle && !`${job.order_no} ${job.product_name} ${job.mold_no} ${job.item_no}`.toLocaleLowerCase().includes(needle)) return false
    if (priorityFilter.value !== 'ALL' && job.priority !== priorityFilter.value) return false
    if (dueFilter.value === 'OVERDUE' && !(job.delivery_slack_days != null && job.delivery_slack_days < 0)) return false
    if (dueFilter.value === 'DUE_SOON' && !(job.delivery_slack_days != null && job.delivery_slack_days >= 0 && job.delivery_slack_days <= 3)) return false
    if (machineFilter.value !== 'ALL' && job.machine_id !== machineFilter.value) return false
    return true
  })
})

const backlog = computed(() => filteredJobs.value
  .filter(job => job.status === 'UNPLANNED')
  .sort((left, right) => {
    const priority = { CRITICAL: 0, URGENT: 1, NORMAL: 2 } as Record<string, number>
    return (priority[left.priority] ?? 3) - (priority[right.priority] ?? 3)
      || (left.delivery_slack_days ?? 9999) - (right.delivery_slack_days ?? 9999)
      || left.order_no.localeCompare(right.order_no)
  }))
const scheduledCount = computed(() => (workbench.value?.jobs ?? []).filter(job => job.task_id && job.status !== 'DONE').length)
const incompleteCount = computed(() => (workbench.value?.jobs ?? []).filter(job => !job.required_machine_a || !job.net_weight_g).length)

function machineJobs(machine: SchedulingMachine) {
  return filteredJobs.value
    .filter(job => job.machine_id === machine.id)
    .sort((left, right) => (left.sequence_no ?? 9999) - (right.sequence_no ?? 9999))
}

function showNotice(message: string) {
  notice.value = message
  window.setTimeout(() => {
    if (notice.value === message) notice.value = ''
  }, 5000)
}

async function loadWorkbench() {
  loading.value = true
  error.value = ''
  try {
    workbench.value = await injectionSchedulingApi.getWorkbench(props.factoryId)
  }
  catch (cause) {
    error.value = getApiErrorMessage(cause)
  }
  finally {
    loading.value = false
  }
}

async function downloadTemplate() {
  busyAction.value = 'download'
  error.value = ''
  try {
    const blob = await injectionSchedulingApi.downloadTemplate(props.factoryId)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${props.factoryName}_统一注塑排产导入模板_RR-ISP-1.0.xlsx`
    link.click()
    URL.revokeObjectURL(url)
    showNotice('统一模板已开始下载。')
  }
  catch (cause) {
    error.value = getApiErrorMessage(cause)
  }
  finally {
    busyAction.value = ''
  }
}

function scheduleHorizon() {
  const start = new Date()
  const dueDates = (workbench.value?.jobs ?? [])
    .map(job => Date.parse(job.delivery_due_date))
    .filter(Number.isFinite)
  const maxDue = dueDates.length ? Math.max(...dueDates) : start.getTime() + 14 * 86400000
  const end = new Date(Math.max(maxDue + 7 * 86400000, start.getTime() + 7 * 86400000))
  return [start.toISOString(), end.toISOString()] as const
}

async function generateSchedule() {
  if (!workbench.value?.plan_id || !workbench.value.plan_revision || !workbench.value.rule_revision) return
  busyAction.value = 'schedule'
  error.value = ''
  scheduleRun.value = null
  try {
    const [start, end] = scheduleHorizon()
    scheduleRun.value = await injectionSchedulingApi.createScheduleRun(workbench.value, start, end)
    showNotice('排期建议已生成，尚未应用到规划。')
  }
  catch (cause) {
    error.value = getApiErrorMessage(cause)
  }
  finally {
    busyAction.value = ''
  }
}

async function applySchedule() {
  if (!workbench.value || !scheduleRun.value) return
  busyAction.value = 'apply'
  error.value = ''
  try {
    await injectionSchedulingApi.applyScheduleRun(scheduleRun.value, workbench.value)
    scheduleRun.value = null
    await loadWorkbench()
    showNotice('排期建议已应用到当前规划。')
  }
  catch (cause) {
    error.value = getApiErrorMessage(cause)
  }
  finally {
    busyAction.value = ''
  }
}

function startDrag(job: SchedulingJob, event: DragEvent) {
  if (!canEdit.value || job.locked || job.status === 'RUNNING') {
    event.preventDefault()
    showNotice('生产中或已锁定任务不能移动。')
    return
  }
  draggedJob.value = job
  event.dataTransfer?.setData('text/plain', job.id)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}

async function dropOnMachine(machine: SchedulingMachine) {
  const job = draggedJob.value
  draggedJob.value = null
  if (!job || !workbench.value || !canEdit.value) return
  busyAction.value = `move:${job.id}`
  error.value = ''
  try {
    if (!job.task_id) {
      const preview = await injectionSchedulingApi.previewManualAppend(
        workbench.value,
        job.order_id,
        job.order_revision,
        machine.id,
      )
      if (preview.decision === 'FAIL' || preview.hard_failures.length) {
        const reasons = [...preview.hard_failures, ...preview.warnings].map(item => `${item.label}：${item.detail}`).join('；')
        throw new Error(reasons || '该机台未通过硬约束检查。')
      }
      await injectionSchedulingApi.confirmManualAppend(preview)
    }
    else {
      const evaluation = await injectionSchedulingApi.evaluateOrder(
        props.factoryId,
        job.order_id,
        true,
      )
      const target = evaluation.results.find(item => item.machine_id === machine.id)
      if (!target || target.decision === 'FAIL' || target.hard_failures.length) {
        const reasons = target?.hard_failures.map(item => `${item.label}：${item.detail}`).join('；')
        throw new Error(reasons || '该机台未通过硬约束检查。')
      }
      if (job.planned_start && job.planned_finish) {
        await injectionSchedulingApi.moveTask(
          workbench.value,
          job,
          machine.id,
          machineJobs(machine).length,
        )
      }
      else {
        workbench.value = await injectionSchedulingApi.reassignQueuedTask(
          workbench.value,
          job,
          machine.id,
          machineJobs(machine).length,
        )
      }
    }
    await loadWorkbench()
    showNotice(`${job.order_no} 已移动到 ${machine.code}。`)
  }
  catch (cause) {
    error.value = getApiErrorMessage(cause)
  }
  finally {
    busyAction.value = ''
  }
}

async function withdraw(job: SchedulingJob) {
  if (!workbench.value || !job.task_id || job.locked || job.status === 'RUNNING') return
  busyAction.value = `withdraw:${job.id}`
  try {
    await injectionSchedulingApi.withdrawToBacklog(workbench.value, job)
    await loadWorkbench()
    showNotice(`${job.order_no} 已移回待排池。`)
  }
  catch (cause) {
    error.value = getApiErrorMessage(cause)
  }
  finally {
    busyAction.value = ''
  }
}

function dropOnBacklog() {
  const job = draggedJob.value
  draggedJob.value = null
  if (job?.task_id) void withdraw(job)
}

async function toggleLock(job: SchedulingJob) {
  if (!workbench.value || !job.task_id) return
  busyAction.value = `lock:${job.id}`
  try {
    workbench.value = await injectionSchedulingApi.setLocked(workbench.value, job, !job.locked)
    showNotice(`${job.order_no} 已${job.locked ? '解锁' : '锁定'}。`)
  }
  catch (cause) {
    error.value = getApiErrorMessage(cause)
  }
  finally {
    busyAction.value = ''
  }
}

async function publishPlan() {
  if (!workbench.value?.plan_id || !workbench.value.plan_revision) return
  busyAction.value = 'publish'
  try {
    await injectionSchedulingApi.publishPlan(workbench.value)
    await loadWorkbench()
    showNotice('当前规划已设为执行计划。')
  }
  catch (cause) {
    error.value = getApiErrorMessage(cause)
  }
  finally {
    busyAction.value = ''
  }
}

function priorityLabel(value: string) {
  return ({ CRITICAL: '特急', URGENT: '急单', NORMAL: '普通' } as Record<string, string>)[value] ?? value
}
function priorityTone(value: string) {
  return value === 'CRITICAL' ? 'red' : value === 'URGENT' ? 'amber' : 'slate'
}
function statusLabel(value: string) {
  return ({ UNPLANNED: '待排', PLANNED: '排队', RUNNING: '生产中', PAUSED: '阻塞', DONE: '完成' } as Record<string, string>)[value] ?? value
}
function statusTone(value: string) {
  return value === 'RUNNING' ? 'teal' : value === 'PLANNED' ? 'blue' : value === 'PAUSED' ? 'red' : value === 'DONE' ? 'green' : 'slate'
}

watch(() => props.factoryId, () => loadWorkbench())
onMounted(loadWorkbench)
</script>

<template>
  <main class="injection-workbench">
    <header class="wb-command-bar">
      <div class="wb-command-bar__identity">
        <RouterLink :to="{ path: '/modules/production', query: { factory: factoryId } }" class="wb-back-link">
          <ArrowLeft class="size-4" aria-hidden="true" />
          <span>生产部模块中心</span>
        </RouterLink>
        <span class="wb-divider" />
        <Factory class="size-5 text-teal-300" aria-hidden="true" />
        <div><strong>注塑排产中枢</strong><small>{{ factoryName }} · {{ planLabel }}</small></div>
      </div>
      <div class="wb-command-bar__actions">
        <Button variant="ghost" class="wb-dark-button" :disabled="busyAction === 'download'" @click="downloadTemplate"><Download class="size-4" />下载模板</Button>
        <Button variant="soft" :disabled="!canImport" @click="importOpen = true"><FileUp class="size-4" />导入计划表</Button>
        <Button :disabled="!canEdit || !workbench?.plan_id || backlog.length === 0 || busyAction === 'schedule'" @click="generateSchedule"><LoaderCircle v-if="busyAction === 'schedule'" class="size-4 animate-spin" /><Sparkles v-else class="size-4" />生成排期建议</Button>
        <Button variant="ghost" class="wb-dark-button" :disabled="loading" @click="loadWorkbench"><RefreshCw class="size-4" />刷新</Button>
        <AccountMenu compact variant="obsidian" />
      </div>
    </header>

    <section class="wb-workspace" aria-label="注塑排产工作台">
      <div v-if="notice" class="wb-toast" role="status"><Check class="size-4" />{{ notice }}</div>
      <div v-if="error" class="wb-alert wb-alert--error" role="alert"><AlertTriangle class="size-4" /><span>{{ error }}</span><button aria-label="关闭错误" @click="error = ''">×</button></div>

      <div class="wb-toolbar">
        <label class="wb-search"><Search class="size-4" aria-hidden="true" /><input v-model="search" type="search" placeholder="搜索单号、产品、工模、货号"><span class="sr-only">搜索排产任务</span></label>
        <select v-model="priorityFilter" aria-label="优先级筛选"><option value="ALL">全部优先级</option><option value="CRITICAL">特急</option><option value="URGENT">急单</option><option value="NORMAL">普通</option></select>
        <select v-model="dueFilter" aria-label="交期筛选"><option value="ALL">全部交期</option><option value="OVERDUE">已超期</option><option value="DUE_SOON">三天内</option></select>
        <select v-model="machineFilter" aria-label="机台筛选"><option value="ALL">全部机台</option><option v-for="machine in workbench?.machines" :key="machine.id" :value="machine.id">{{ machine.code }}</option></select>
        <span class="wb-toolbar__spacer" />
        <Button variant="outline" size="sm" :disabled="!workbench?.plan_id" @click="showNotice('当前规划的所有操作均已按 revision 保存。')"><Save class="size-4" />保存规划</Button>
        <Button size="sm" :disabled="!canPublish || workbench?.plan_mode !== 'PLANNING' || busyAction === 'publish'" @click="publishPlan"><Play class="size-4" />设为执行计划</Button>
      </div>

      <div v-if="scheduleRun" class="wb-suggestion-banner">
        <div><Sparkles class="size-5" /><span><strong>排期建议已生成</strong><small>新排入 {{ scheduleRun.summary.assigned_count ?? scheduleRun.assignments.filter(item => item.machine_id).length }} · 未排 {{ scheduleRun.summary.unassigned_count ?? scheduleRun.assignments.filter(item => !item.machine_id).length }} · 仅预览，尚未修改规划</small></span></div>
        <div><Button variant="outline" size="sm" @click="scheduleRun = null">暂不应用</Button><Button size="sm" :disabled="busyAction === 'apply'" @click="applySchedule"><LoaderCircle v-if="busyAction === 'apply'" class="size-4 animate-spin" />应用到当前规划</Button></div>
      </div>

      <div class="wb-kpis" aria-label="排产关键指标">
        <article><span>待排订单</span><strong>{{ workbench?.summary.unplanned_count ?? 0 }}</strong><small>等待系统或人工排机</small></article>
        <article><span>已排任务</span><strong>{{ scheduledCount }}</strong><small>含排队、生产中和阻塞</small></article>
        <article data-tone="amber"><span>临期 / 超期</span><strong>{{ workbench?.summary.overdue_count ?? 0 }}</strong><small>按交货完成期计算</small></article>
        <article data-tone="amber"><span>排机资料不完整</span><strong>{{ incompleteCount }}</strong><small>缺安数或权威整啤净重</small></article>
        <article data-tone="red"><span>冲突数量</span><strong>{{ workbench?.summary.conflict_count ?? 0 }}</strong><small>阻塞、物料或模具待核</small></article>
      </div>

      <div v-if="loading" class="wb-loading"><LoaderCircle class="size-6 animate-spin" /><span>正在读取 {{ factoryName }} 排产数据</span></div>
      <div v-else class="wb-board">
        <section class="wb-backlog-panel" @dragover.prevent @drop="dropOnBacklog">
          <header><div><p class="wb-eyebrow">BACKLOG</p><h2>待排订单池 <span>{{ backlog.length }}</span></h2></div><UploadCloud class="size-5" aria-hidden="true" /></header>
          <div v-if="!backlog.length" class="wb-empty"><Check class="size-5" /><strong>当前没有待排订单</strong><p>导入统一模板或把任务移回待排池后会显示在这里。</p></div>
          <div v-else class="wb-backlog-list">
            <article v-for="job in backlog" :key="job.id" class="wb-order-card" draggable="true" @dragstart="startDrag(job, $event)" @click="detailJob = job">
              <GripVertical class="wb-grip" aria-hidden="true" />
              <div class="wb-order-card__main"><div><strong>{{ job.product_name || job.order_no }}</strong><span>{{ job.order_no }} · {{ job.mold_no || '工模待核' }}</span></div><StatusPill :label="priorityLabel(job.priority)" :tone="priorityTone(job.priority)" compact /></div>
              <dl><div><dt>欠数</dt><dd>{{ job.outstanding_quantity.toLocaleString() }}</dd></div><div><dt>交期</dt><dd :class="{ 'wb-text-danger': job.delivery_slack_days != null && job.delivery_slack_days < 0 }">{{ job.delivery_due_date || '—' }}</dd></div><div><dt>资料</dt><dd>{{ job.required_machine_a && job.net_weight_g ? '可评估' : '待补齐' }}</dd></div></dl>
              <button class="wb-card-link">查看候选机台 <ChevronRight class="size-3" /></button>
            </article>
          </div>
        </section>

        <section class="wb-machine-panel">
          <header class="wb-machine-panel__header"><div><p class="wb-eyebrow">MACHINE QUEUES</p><h2>机台排程区 <span>{{ workbench?.machines.length ?? 0 }} 台</span></h2></div><p>拖入前由后端执行安数、射胶量、单双臂、夹具、工艺与占用检查。</p></header>
          <div v-if="!workbench?.machines.length" class="wb-empty"><AlertTriangle class="size-5" /><strong>当前厂区没有机台主数据</strong><p>请先维护机台主数据，系统不会从 Excel 静默创建机台。</p></div>
          <div v-else class="wb-machine-grid">
            <article v-for="machine in workbench.machines" :key="machine.id" class="wb-machine-card" :data-status="machine.status" @dragover.prevent @drop="dropOnMachine(machine)">
              <header><div><strong>{{ machine.code }}</strong><span>{{ machine.area || machine.position || '未分区' }}</span></div><StatusPill :label="machine.status === 'running' ? '生产中' : machine.status === 'available' ? '可用' : machine.status" :tone="machine.status === 'running' ? 'teal' : machine.status === 'available' ? 'green' : 'slate'" compact /></header>
              <div class="wb-machine-meta"><span>{{ machine.a_class ? `${machine.a_class}A` : '安数待补' }}</span><span>{{ machine.tonnage ? `${machine.tonnage}T` : '吨位待补' }}</span><span>{{ machine.arm_capabilities.join('/') || '机械手待补' }}</span><span>{{ machine.fixture_capabilities.join('/') || '夹具待补' }}</span></div>
              <div class="wb-queue">
                <p v-if="!machineJobs(machine).length" class="wb-queue-empty">拖动待排订单到此机台</p>
                <article v-for="job in machineJobs(machine)" :key="job.id" class="wb-task-card" :class="{ 'wb-task-card--locked': job.locked }" :draggable="!job.locked && job.status !== 'RUNNING'" @dragstart="startDrag(job, $event)" @click="detailJob = job">
                  <div class="wb-task-sequence"><GripVertical v-if="!job.locked" class="size-3" /><Lock v-else class="size-3" />{{ (job.sequence_no ?? 0) + 1 }}</div>
                  <div class="wb-task-card__body"><div><strong>{{ job.product_name || job.order_no }}</strong><StatusPill :label="statusLabel(job.status)" :tone="statusTone(job.status)" compact /></div><p>{{ job.order_no }} · {{ job.mold_no || '工模待核' }} · 欠 {{ job.outstanding_quantity.toLocaleString() }}</p><small><CalendarClock class="size-3" />{{ job.planned_start ? `${job.planned_start.slice(5, 16)} → ${job.planned_finish.slice(5, 16)}` : '等待系统计算计划时间' }}</small></div>
                  <div class="wb-task-actions"><button :aria-label="job.locked ? '解锁任务' : '锁定任务'" :disabled="busyAction === `lock:${job.id}`" @click.stop="toggleLock(job)"><Unlock v-if="job.locked" class="size-3.5" /><Lock v-else class="size-3.5" /></button><button aria-label="移回待排池" :disabled="job.locked || job.status === 'RUNNING'" @click.stop="withdraw(job)"><UploadCloud class="size-3.5" /></button></div>
                </article>
              </div>
            </article>
          </div>
        </section>
      </div>
      <footer class="wb-status-bar"><span><Info class="size-3.5" />模板 RR-ISP-1.0 · 固定 Profile · 严格字段映射</span><span>计划 revision {{ workbench?.plan_revision ?? '—' }} · 规则 revision {{ workbench?.rule_revision ?? '—' }} · 事件 {{ workbench?.polling_revision ?? 0 }}</span></footer>
    </section>

    <StandardImportDialog :open="importOpen" :factory-id="factoryId" :factory-name="factoryName" @close="importOpen = false" @imported="loadWorkbench" />
    <TaskDetailDrawer :open="Boolean(detailJob)" :factory-id="factoryId" :job="detailJob" @close="detailJob = null" />
  </main>
</template>

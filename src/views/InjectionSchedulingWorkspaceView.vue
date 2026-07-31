<script setup lang="ts">
import {
  AlertTriangle,
  ArrowLeft,
  Boxes,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronRight,
  CircleGauge,
  Clock3,
  Database,
  FileClock,
  Filter,
  History,
  LayoutGrid,
  ListChecks,
  LoaderCircle,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Upload,
  Wrench,
  X,
} from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useInjectionSchedulingStore } from '@/stores/injectionScheduling'
import type {
  ConstraintCheck,
  FitDecision,
  InjectionFactoryId,
  MachineCandidate,
  SchedulingTask,
} from '@/types/injectionScheduling'

const route = useRoute()
const router = useRouter()
const store = useInjectionSchedulingStore()
const {
  snapshot,
  loading,
  error,
  search,
  statusFilter,
  machineClass,
  armType,
  dataQuality,
  view,
  collapsedMachines,
  selectedTask,
  selectedMachine,
  selectedBacklog,
  detailTab,
  detailDrawerOpen,
  backlogDrawerOpen,
  saving,
  toast,
  conflict,
  filteredGroups,
  filteredTaskCount,
  machineClasses,
  isDirty,
} = storeToRefs(store)

const backlogTab = ref<'candidates' | 'rules' | 'unmatched'>('candidates')
const localNotice = ref('')
const searchInput = ref<HTMLInputElement | null>(null)
const visibleGroupLimit = ref(12)
const density = ref<'standard' | 'compact'>('standard')
const columnChooserOpen = ref(false)
const isOnline = ref(true)
const columnVisibility = reactive({
  colorMaterial: true,
  quantities: true,
  shift: true,
  dates: true,
  fit: true,
})

const renderedGroups = computed(() => filteredGroups.value.slice(0, visibleGroupLimit.value))
const renderedTaskCount = computed(() => renderedGroups.value.reduce((total, group) => total + group.tasks.length, 0))
const hasMoreGroups = computed(() => renderedGroups.value.length < filteredGroups.value.length)
const visibleColumnCount = computed(() => (
  5
  + (columnVisibility.colorMaterial ? 1 : 0)
  + (columnVisibility.quantities ? 3 : 0)
  + (columnVisibility.shift ? 3 : 0)
  + (columnVisibility.dates ? 3 : 0)
  + (columnVisibility.fit ? 1 : 0)
))

const factoryOptions: Array<{ id: InjectionFactoryId; label: string }> = [
  { id: 'huaxing', label: '华兴' },
  { id: 'huakang-a', label: '华康 A' },
  { id: 'huakang-b', label: '华康 B' },
  { id: 'huakang-c', label: '华康 C' },
  { id: 'huakang-d', label: '华康 D' },
  { id: 'huadeng', label: '华登' },
]

const summaryCards = computed(() => {
  const summary = snapshot.value?.summary
  if (!summary) return []
  return [
    { label: '机台覆盖', value: summary.availableMachines.toLocaleString(), unit: `/ ${summary.totalMachines} 台已排`, detail: '老车间 39 · 新车间 36', tone: 'teal', icon: CircleGauge },
    { label: '已排任务', value: summary.scheduledTasks.toLocaleString(), unit: '条', detail: '按机台分组，当前与后续队列分离', tone: 'blue', icon: ListChecks },
    { label: '已超交期', value: summary.overdueTasks.toLocaleString(), unit: '条', detail: '以“交期差 < 0”识别', tone: 'red', icon: AlertTriangle },
    { label: '3 天内到期', value: summary.dueSoonTasks.toLocaleString(), unit: '条', detail: '优先恢复机台与物料', tone: 'amber', icon: CalendarDays },
    { label: '当前总欠数', value: summary.remainingQuantity.toLocaleString(), unit: '啤', detail: '由订单数 − 累计已啤计算', tone: 'slate', icon: Boxes },
    { label: '模具尺寸完整率', value: summary.moldDimensionCompleteness.toFixed(1), unit: '%', detail: '缺 L/W/H 时必须人工复核', tone: 'amber', icon: Wrench },
  ]
})

const selectedValues = computed(() => selectedTask.value ? store.displayValues(selectedTask.value) : null)

const detailChecks = computed<ConstraintCheck[]>(() => {
  const task = selectedTask.value
  const machine = selectedMachine.value
  if (!task || !machine) return []
  const mold = task.moldDimensions
  const sizePass = Boolean(mold && mold.length <= machine.platen.width && mold.width <= machine.platen.height)
  const armPass = machine.armCapability === '双臂' || task.armRequirement === '单臂'
  return [
    {
      key: 'mold-size',
      label: '模具安装面',
      decision: !mold ? 'REVIEW_REQUIRED' : sizePass ? 'PASS' : 'FAIL',
      detail: mold
        ? `模具 ${mold.length}×${mold.width}×${mold.height}mm；机台模板 ${machine.platen.width}×${machine.platen.height}mm。当前只核对 L×W。`
        : '模具 L/W/H 未完整，系统不得自动判为适配。',
    },
    {
      key: 'shot-capacity',
      label: '射胶容量',
      decision: task.shotNetWeightGrams <= machine.shotCapacityGrams ? 'PASS' : 'FAIL',
      detail: `整啤净重 ${task.shotNetWeightGrams}g / 机台射胶量 ${machine.shotCapacityGrams}g，占用 ${(task.shotNetWeightGrams / machine.shotCapacityGrams * 100).toFixed(1)}%；安全系数仍需业务确认。`,
    },
    {
      key: 'robot-arm',
      label: '机械手能力',
      decision: armPass ? 'PASS' : 'FAIL',
      detail: `模具要求 ${task.armRequirement}；${machine.code} 配置 ${machine.armCapability}。双臂按能力集合覆盖单臂。`,
    },
    {
      key: 'fixture',
      label: '夹具要求',
      decision: task.fixtureRequirement ? 'PASS' : 'REVIEW_REQUIRED',
      detail: `当前记录：${task.fixtureRequirement || '未填写'}。`,
    },
    {
      key: 'process',
      label: '机台限制',
      decision: machine.processNote ? 'REVIEW_REQUIRED' : 'PASS',
      detail: machine.processNote || '暂无特殊限制；生产版仍需覆盖 PC/PVC 螺杆、抽芯、高压与透明料规则。',
    },
  ]
})

function parseFactory(): InjectionFactoryId {
  const candidate = String(route.query.factory ?? 'huaxing')
  return factoryOptions.some((entry) => entry.id === candidate) ? candidate as InjectionFactoryId : 'huaxing'
}

function numberFromEvent(event: Event) {
  return Number((event.target as HTMLInputElement).value)
}

function textFromEvent(event: Event) {
  return (event.target as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement).value
}

function formatDateTime(value: string) {
  return value.replace('2026-', '').replace(' ', ' · ')
}

function statusLabel(status: SchedulingTask['status']) {
  return { RUNNING: '正在生产', QUEUED: '后续队列', BLOCKED: '已阻塞', DONE: '已完成' }[status]
}

function decisionLabel(decision: FitDecision) {
  return { PASS: '通过', REVIEW_REQUIRED: '需复核', FAIL: '不适配' }[decision]
}

function currentTask(machineId: string) {
  return snapshot.value?.tasks.find((entry) => entry.machineId === machineId && entry.status === 'RUNNING')
}

function taskClass(task: SchedulingTask) {
  return {
    'task-row--running': task.status === 'RUNNING',
    'task-row--critical': task.priority === 'CRITICAL' && task.status !== 'RUNNING',
  }
}

function progressWidth(task: SchedulingTask) {
  return `${Math.min(100, store.displayValues(task).progress).toFixed(1)}%`
}

function timelinePosition(task: SchedulingTask) {
  const startDay = Math.max(0, Number(task.plannedStart.slice(8, 10)) - 31)
  const duration = Math.max(1, Math.min(12, Number(task.plannedEnd.slice(8, 10)) - Number(task.plannedStart.slice(8, 10)) + 1))
  return { left: `${Math.min(86, startDay * 7)}%`, width: `${Math.max(7, duration * 6.7)}%`, top: `${9 + task.sequence * 25}px` }
}

function showNotice(message: string) {
  store.clearError()
  localNotice.value = message
  window.setTimeout(() => { localNotice.value = '' }, 3200)
}

async function refresh() {
  if (!isOnline.value) {
    showNotice('离线状态不能刷新；当前页面数据与草稿已保留')
    return
  }
  if (isDirty.value && !window.confirm('有尚未保存的本班回报，刷新会丢失草稿。仍要继续吗？')) return
  await store.load(parseFactory())
}

async function selectFactory(event: Event) {
  const nextFactory = textFromEvent(event) as InjectionFactoryId
  if (isDirty.value && !window.confirm('切换厂区会丢失未保存草稿。仍要继续吗？')) return
  await router.replace({ query: { ...route.query, factory: nextFactory } })
}

function beforeUnload(event: BeforeUnloadEvent) {
  if (!isDirty.value) return
  event.preventDefault()
  event.returnValue = ''
}

function closeDrawers() {
  detailDrawerOpen.value = false
  backlogDrawerOpen.value = false
}

function handleGlobalShortcut(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === 'f') {
    event.preventDefault()
    searchInput.value?.focus()
    searchInput.value?.select()
    return
  }

  if (event.key === 'Escape') {
    if (detailDrawerOpen.value || backlogDrawerOpen.value) closeDrawers()
    else if (search.value) search.value = ''
    columnChooserOpen.value = false
  }
}

function openCandidate(candidate: MachineCandidate) {
  if (!selectedBacklog.value || candidate.decision === 'FAIL') return
  if (!isOnline.value) {
    showNotice('当前处于离线状态，候选机台仍可查看，但不能写入草案')
    return
  }
  void store.assignBacklog(selectedBacklog.value, candidate.machineId)
}

function loadMoreGroups() {
  visibleGroupLimit.value = Math.min(filteredGroups.value.length, visibleGroupLimit.value + 12)
}

function loadMoreOnScroll(event: Event) {
  if (!hasMoreGroups.value) return
  const target = event.currentTarget as HTMLElement
  if (target.scrollTop + target.clientHeight >= target.scrollHeight - 220) loadMoreGroups()
}

function toggleDensity() {
  density.value = density.value === 'standard' ? 'compact' : 'standard'
  showNotice(density.value === 'compact' ? '已切换为紧凑密度' : '已切换为标准密度')
}

function updateConnectivity() {
  isOnline.value = navigator.onLine
  if (!isOnline.value) showNotice('网络已断开：本地输入仍保留，保存操作已暂停')
}

async function saveAllDrafts() {
  if (!isOnline.value) {
    showNotice('离线状态不能保存；草稿已保留在当前页面')
    return
  }
  await store.saveAllDrafts()
}

async function saveSelectedTask() {
  if (!selectedTask.value) return
  if (!isOnline.value) {
    showNotice('离线状态不能保存；本任务草稿仍保留')
    return
  }
  await store.saveDraft(selectedTask.value.id)
}

watch(() => route.query.factory, async () => {
  await store.load(parseFactory())
})

watch([search, statusFilter, machineClass, armType, dataQuality], () => {
  visibleGroupLimit.value = 12
})

onMounted(async () => {
  isOnline.value = navigator.onLine
  window.addEventListener('beforeunload', beforeUnload)
  window.addEventListener('online', updateConnectivity)
  window.addEventListener('offline', updateConnectivity)
  document.addEventListener('keydown', handleGlobalShortcut)
  await store.load(parseFactory())
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', beforeUnload)
  window.removeEventListener('online', updateConnectivity)
  window.removeEventListener('offline', updateConnectivity)
  document.removeEventListener('keydown', handleGlobalShortcut)
})
</script>

<template>
  <div class="schedule-shell">
    <a class="skip-link" href="#scheduling-workbench">跳到排程工作区</a>
    <aside class="schedule-sidebar">
      <div class="brand-block">
        <div class="brand-mark"><LayoutGrid :size="20" /></div>
        <div><strong>Royal Regent Nexus</strong><span>PRODUCTION OPERATIONS</span></div>
      </div>

      <nav aria-label="注塑排产导航">
        <p class="nav-label">排产中枢</p>
        <button class="nav-item active" type="button"><ListChecks :size="17" />机台日排计划<span>{{ snapshot?.summary.scheduledTasks ?? 0 }}</span></button>
        <button class="nav-item" type="button" @click="store.openBacklog()"><Boxes :size="17" />待排订单池<span>{{ snapshot?.summary.backlogOrders ?? 0 }}</span></button>
        <button class="nav-item" type="button" @click="view = 'timeline'"><Clock3 :size="17" />负荷时间轴</button>

        <p class="nav-label">基础资料</p>
        <button class="nav-item" type="button" @click="showNotice('阶段 1B 暂不建设模具资料维护页')"><Wrench :size="17" />模具资料<span>1,956</span></button>
        <button class="nav-item" type="button" @click="showNotice('阶段 1B 暂不建设机台能力维护页')"><LayoutGrid :size="17" />机台能力</button>
        <button class="nav-item" type="button" @click="showNotice('规则仅在候选机台抽屉中做可解释预览')"><SlidersHorizontal :size="17" />排产规则</button>

        <p class="nav-label">追溯</p>
        <button class="nav-item" type="button" @click="showNotice('Excel 导入预览与确认属于阶段 4，本轮保持只读证据边界')"><Upload :size="17" />导入批次</button>
        <button class="nav-item" type="button" @click="selectedTask && store.openTask(selectedTask.id, 'history')"><History :size="17" />变更记录</button>
      </nav>

      <div class="source-panel">
        <div><span><i :class="{ offline: !isOnline }" />连接状态</span><strong>{{ isOnline ? '前端 Mock' : '离线草稿' }}</strong></div>
        <div><span>厂区隔离</span><strong>{{ snapshot?.factoryName ?? '—' }}</strong></div>
        <div><span>计划版本</span><strong>{{ snapshot?.planVersion ?? '—' }}</strong></div>
      </div>
    </aside>

    <main id="scheduling-workbench" class="schedule-main">
      <header class="workspace-header">
        <div class="title-cluster">
          <button class="icon-button" type="button" aria-label="返回生产模块" @click="router.push({ path: '/modules/production', query: { factory: parseFactory() } })"><ArrowLeft :size="18" /></button>
          <div><p>生产部 <ChevronRight :size="12" /> 注塑排产 <ChevronRight :size="12" /> 日计划</p><h1>{{ snapshot?.factoryName ?? '厂区' }}注塑排产中枢</h1></div>
          <span class="mode-badge"><AlertTriangle :size="13" />交互原型 · Mock 数据</span>
        </div>
        <div class="header-actions">
          <select :value="parseFactory()" aria-label="选择厂区" @change="selectFactory"><option v-for="factory in factoryOptions" :key="factory.id" :value="factory.id">{{ factory.label }}区</option></select>
          <span class="date-chip"><Clock3 :size="15" />2026-07-31</span>
          <button class="button" :class="isOnline ? 'success' : 'offline'" type="button" :disabled="!isOnline || loading" @click="refresh"><RefreshCw :size="15" :class="{ spin: loading }" />{{ isOnline ? '刚刚同步' : '当前离线' }}</button>
          <button class="button" type="button" @click="showNotice('当前为前端 Mock 模式，未上传或改写 Excel')"><Upload :size="15" />导入计划表</button>
          <button class="button primary" type="button" :disabled="!isDirty || saving || !isOnline" @click="saveAllDrafts"><LoaderCircle v-if="saving" class="spin" :size="15" /><Save v-else :size="15" />保存草案<span v-if="isDirty" class="dirty-dot" /></button>
          <button class="avatar" type="button" title="啤机文员">啤机</button>
        </div>
      </header>

      <div v-if="!isOnline" class="connection-banner" role="status"><AlertTriangle :size="16" /><span><strong>离线草稿模式</strong> 可以继续查看与填写本班回报；保存、刷新和候选机台确认将在联网后恢复。</span></div>
      <div v-if="error && snapshot" class="operation-error" role="alert"><AlertTriangle :size="16" /><span>{{ error }}</span><button type="button" aria-label="关闭错误提示" @click="store.clearError"><X :size="15" /></button></div>

      <section v-if="error && !snapshot" class="empty-state">
        <Database :size="32" />
        <h2>当前厂区没有注塑排产 Mock 数据</h2>
        <p>{{ error }}</p>
        <p>系统没有回退到其他厂区数据，避免跨厂混用。</p>
        <button class="button primary" type="button" @click="router.replace({ query: { factory: 'huaxing' } })">返回华兴演示数据</button>
      </section>

      <template v-else>
        <section class="summary-grid" aria-label="排程摘要">
          <article v-for="card in summaryCards" :key="card.label" class="summary-card" :class="`summary-card--${card.tone}`">
            <div><span>{{ card.label }}</span><component :is="card.icon" :size="17" /></div>
            <p><strong>{{ card.value }}</strong><b>{{ card.unit }}</b></p>
            <small>{{ card.detail }}</small>
          </article>
        </section>

        <section class="workbench" :class="`density-${density}`" aria-label="注塑排程工作台">
          <div class="toolbar toolbar--top">
            <div class="segmented">
              <button type="button" :class="{ active: view === 'board' }" @click="view = 'board'"><ListChecks :size="15" />机台计划表</button>
              <button type="button" :class="{ active: view === 'timeline' }" @click="view = 'timeline'"><Clock3 :size="15" />负荷时间轴</button>
            </div>
            <label class="search-box"><span class="sr-only">搜索排程任务</span><Search :size="16" /><input ref="searchInput" v-model="search" type="search" placeholder="查机台、模号、单号、货号、产品名、材料……" /><kbd>Ctrl / ⌘ + F</kbd></label>
            <div class="toolbar-spacer" />
            <button class="button compact" type="button" @click="refresh"><RefreshCw :size="14" />刷新</button>
            <button class="button compact" type="button" :aria-pressed="density === 'compact'" @click="toggleDensity"><SlidersHorizontal :size="14" />{{ density === 'compact' ? '紧凑' : '标准' }}</button>
            <div class="column-chooser">
              <button class="button compact" type="button" :aria-expanded="columnChooserOpen" aria-controls="column-chooser-menu" @click="columnChooserOpen = !columnChooserOpen"><Filter :size="14" />字段</button>
              <div v-if="columnChooserOpen" id="column-chooser-menu" class="column-menu">
                <strong>显示字段组</strong>
                <label><input v-model="columnVisibility.colorMaterial" type="checkbox" />颜色与用料</label>
                <label><input v-model="columnVisibility.quantities" type="checkbox" />订单与欠数</label>
                <label><input v-model="columnVisibility.shift" type="checkbox" />班次与进度</label>
                <label><input v-model="columnVisibility.dates" type="checkbox" />日期与风险</label>
                <label><input v-model="columnVisibility.fit" type="checkbox" />机台匹配</label>
              </div>
            </div>
            <button class="button primary compact" type="button" @click="store.openBacklog()"><Sparkles :size="14" />智能待排 {{ snapshot?.summary.backlogOrders }}</button>
          </div>

          <div class="toolbar toolbar--filters">
            <div class="filter-pills">
              <button type="button" :class="{ active: statusFilter === 'all' }" @click="statusFilter = 'all'">全部</button>
              <button type="button" :class="{ active: statusFilter === 'running' }" @click="statusFilter = 'running'">正在生产</button>
              <button type="button" :class="{ active: statusFilter === 'overdue' }" @click="statusFilter = 'overdue'">已逾期</button>
              <button type="button" :class="{ active: statusFilter === 'dueSoon' }" @click="statusFilter = 'dueSoon'">3 天内</button>
              <button type="button" :class="{ active: statusFilter === 'review' }" @click="statusFilter = 'review'">匹配待复核</button>
            </div>
            <select v-model="machineClass"><option value="all">全部机型</option><option v-for="item in machineClasses" :key="item" :value="item">{{ item }}</option></select>
            <select v-model="armType"><option value="all">全部机械手</option><option value="单臂">单臂</option><option value="双臂">双臂</option></select>
            <select v-model="dataQuality" aria-label="资料完整度"><option value="all">全部资料</option><option value="complete">尺寸完整</option><option value="missing">缺模具尺寸</option></select>
            <span class="result-count">筛选 {{ filteredGroups.length }} 台 · {{ filteredTaskCount }} 条；已渲染 {{ renderedGroups.length }} 台 · {{ renderedTaskCount }} 条</span>
          </div>

          <div v-if="loading" class="loading-state"><LoaderCircle class="spin" :size="24" />正在加载厂区排程草案…</div>

          <div v-else-if="filteredGroups.length === 0" class="filter-empty-state">
            <Search :size="28" />
            <strong>没有符合当前条件的排程任务</strong>
            <span>可以清空搜索词，或切换状态、机型、机械手和资料完整度筛选。</span>
            <button class="button" type="button" @click="search = ''; statusFilter = 'all'; machineClass = 'all'; armType = 'all'; dataQuality = 'all'">清除全部筛选</button>
          </div>

          <div v-else-if="view === 'board'" class="table-scroller" tabindex="0" aria-label="机台排程表，可横向和纵向滚动" @scroll.passive="loadMoreOnScroll">
            <table class="schedule-table">
              <caption class="sr-only">{{ snapshot?.factoryName }}注塑机台日排程，共 {{ filteredTaskCount }} 条筛选结果，当前增量渲染 {{ renderedTaskCount }} 条。</caption>
              <thead><tr><th scope="col">任务状态</th><th scope="col">队列</th><th scope="col">模具 / 产品</th><th scope="col">单号 / 货号</th><th v-if="columnVisibility.colorMaterial" scope="col">颜色 / 用料</th><template v-if="columnVisibility.quantities"><th scope="col">订单数</th><th scope="col">已啤数</th><th scope="col">欠数</th></template><template v-if="columnVisibility.shift"><th scope="col">本班目标</th><th scope="col">本班完成（可改）</th><th scope="col">完成进度</th></template><template v-if="columnVisibility.dates"><th scope="col">交货完成期</th><th scope="col">计划完成期</th><th scope="col">交期风险</th></template><th v-if="columnVisibility.fit" scope="col">机台匹配</th><th scope="col">操作</th></tr></thead>
              <tbody v-for="group in renderedGroups" :key="group.machine.id">
                <tr class="machine-row">
                  <td :colspan="visibleColumnCount">
                    <div class="machine-strip">
                      <button class="collapse-button" type="button" :aria-label="`${collapsedMachines.has(group.machine.id) ? '展开' : '折叠'}${group.machine.code}`" @click="store.toggleMachine(group.machine.id)"><ChevronDown :size="15" :class="{ collapsed: collapsedMachines.has(group.machine.id) }" /></button>
                      <strong class="machine-code"><i />{{ group.machine.code }}</strong>
                      <span><b>{{ group.machine.machineClass }} · {{ group.machine.tonnage }}T</b><em />射胶 {{ group.machine.shotCapacityGrams }}g<em />机架 {{ group.machine.platen.width }}×{{ group.machine.platen.height }}mm<em />{{ group.machine.armCapability }} · {{ group.machine.machineType }}</span>
                      <span class="machine-current">当前：<strong>{{ currentTask(group.machine.id)?.moldCode ?? '未开机' }} · {{ currentTask(group.machine.id)?.orderNo ?? '—' }}</strong></span>
                      <span v-if="group.machine.processNote" class="machine-note">限制：{{ group.machine.processNote }}</span>
                      <div class="machine-load"><span>队列 {{ group.tasks.length }} 单</span><i><b :style="{ width: `${group.machine.loadPercent}%` }" /></i><span>负荷 {{ group.machine.loadPercent }}%</span></div>
                    </div>
                  </td>
                </tr>
                <template v-if="!collapsedMachines.has(group.machine.id)">
                  <tr v-for="task in group.tasks" :key="task.id" :class="taskClass(task)" class="task-row" @dblclick="store.openTask(task.id)">
                    <td><button class="status-chip" :class="task.status.toLowerCase()" type="button" @click="store.openTask(task.id)"><i v-if="task.status === 'RUNNING'" />{{ statusLabel(task.status) }}</button><small v-if="task.originalMarker">原表标记：{{ task.originalMarker }}</small></td>
                    <td><span v-if="task.status === 'RUNNING'" class="now-badge">NOW</span><span v-else class="sequence-badge">{{ task.sequence }}</span></td>
                    <td><button class="cell-link" type="button" @click="store.openTask(task.id)"><strong>{{ task.moldCode }}</strong><small>{{ task.productName }}</small></button></td>
                    <td><strong>{{ task.orderNo }}</strong><small>{{ task.itemNo }}</small></td>
                    <td v-if="columnVisibility.colorMaterial"><span class="color-line"><i :style="{ background: task.colorHex }" />{{ task.color }}</span><small>{{ task.material }} · {{ task.shotNetWeightGrams }}g</small></td>
                    <template v-if="columnVisibility.quantities"><td class="numeric">{{ task.orderQuantity.toLocaleString() }}</td><td class="numeric">{{ store.displayValues(task).cumulativeCompleted.toLocaleString() }}</td><td class="numeric danger-text">{{ store.displayValues(task).remaining.toLocaleString() }}</td></template>
                    <template v-if="columnVisibility.shift"><td class="numeric">{{ store.displayValues(task).shiftTarget.toLocaleString() }}</td><td><div class="inline-stepper"><button type="button" :aria-label="`${task.orderNo} 本班完成减一`" @click="store.updateShiftCompleted(task, store.displayValues(task).shiftCompleted - 1)">−</button><input :value="store.displayValues(task).shiftCompleted" type="number" min="0" :aria-label="`${task.orderNo} 本班完成`" @input="store.updateShiftCompleted(task, numberFromEvent($event))" /><button type="button" :aria-label="`${task.orderNo} 本班完成加一`" @click="store.updateShiftCompleted(task, store.displayValues(task).shiftCompleted + 1)">＋</button></div></td><td><div class="progress-cell"><div><i :style="{ width: progressWidth(task) }" /></div><strong>{{ store.displayValues(task).progress.toFixed(1) }}%</strong><small>约余 {{ store.displayValues(task).remainingShifts.toFixed(1) }} 班</small></div></td></template>
                    <template v-if="columnVisibility.dates"><td><strong>{{ task.deliveryDate }}</strong><small>来源：计划表</small></td><td><strong>{{ formatDateTime(task.plannedEnd) }}</strong><small>自动推演预览</small></td><td><span class="risk-chip" :class="task.slackDays < 0 ? 'overdue' : task.slackDays <= 3 ? 'soon' : 'safe'">{{ task.slackDays < 0 ? `逾期 ${Math.abs(task.slackDays).toFixed(1)} 天` : `余 ${task.slackDays.toFixed(1)} 天` }}</span><small v-if="task.priority === 'CRITICAL'">特急 / 高优先级</small></td></template>
                    <td v-if="columnVisibility.fit"><button class="fit-chip" :class="task.fitDecision.toLowerCase()" type="button" @click="store.openTask(task.id, 'fit')">{{ decisionLabel(task.fitDecision) }} · {{ task.fitScore }}</button><small v-if="!task.moldDimensions">缺模具尺寸</small></td>
                    <td><button class="row-action" type="button" @click="store.openTask(task.id)">详情</button></td>
                  </tr>
                </template>
              </tbody>
            </table>
            <div v-if="hasMoreGroups" class="load-more-row"><span>已增量渲染 {{ renderedGroups.length }} / {{ filteredGroups.length }} 台机，继续滚动会自动加载。</span><button class="button" type="button" @click="loadMoreGroups">加载更多机台</button></div>
          </div>

          <div v-else class="timeline-view" tabindex="0" aria-label="机台负荷时间轴" @scroll.passive="loadMoreOnScroll">
            <div class="timeline-board">
              <div class="timeline-head"><strong>机台 / 负荷</strong><span v-for="day in 14" :key="day">{{ day === 1 ? '07-31' : `08-${String(day - 1).padStart(2, '0')}` }}</span></div>
              <div v-for="group in renderedGroups" :key="group.machine.id" class="timeline-row">
                <div class="timeline-label"><strong>{{ group.machine.code }} · {{ group.machine.machineClass }}</strong><span>负荷 {{ group.machine.loadPercent }}% · {{ group.tasks.length }} 单</span></div>
                <div class="timeline-grid"><i v-for="day in 14" :key="day" /></div>
                <button v-for="task in group.tasks.slice(0, 3)" :key="task.id" class="timeline-bar" :class="{ critical: task.slackDays < 0, review: task.fitDecision === 'REVIEW_REQUIRED' }" :style="timelinePosition(task)" type="button" @click="store.openTask(task.id)">{{ task.moldCode }} · {{ task.orderNo }}</button>
              </div>
            </div>
            <div v-if="hasMoreGroups" class="load-more-row"><span>已增量渲染 {{ renderedGroups.length }} / {{ filteredGroups.length }} 台机。</span><button class="button" type="button" @click="loadMoreGroups">加载更多机台</button></div>
          </div>

          <footer class="workbench-footer"><span><strong>数据样例：</strong>{{ snapshot?.sourceLabel }}；当前为静态前端交互，未执行真实 Excel 导入。</span><span>双击任务或点击匹配状态可打开详情 · 所有修改保存前均为草稿</span></footer>
        </section>
      </template>
    </main>

    <div v-if="detailDrawerOpen" class="drawer-backdrop" @click.self="detailDrawerOpen = false">
      <aside class="drawer" role="dialog" aria-modal="true" aria-label="任务详情">
        <header class="drawer-header">
          <div><span>任务详情 · revision {{ selectedTask?.revision }}</span><h2>{{ selectedTask?.moldCode }} · {{ selectedTask?.orderNo }}</h2><p>{{ selectedMachine?.code }} / {{ selectedTask?.productName }}</p></div>
          <button class="drawer-close" type="button" aria-label="关闭任务详情" @click="detailDrawerOpen = false"><X :size="18" /></button>
          <div class="drawer-actions"><button type="button" :disabled="!isOnline" @click="selectedTask && store.simulateConflict(selectedTask.id)"><FileClock :size="14" />模拟并发更新</button><button class="primary" type="button" :disabled="!selectedTask || !store.reportDrafts[selectedTask.id] || saving || !isOnline" @click="saveSelectedTask"><Save :size="14" />保存本任务</button></div>
        </header>
        <div class="drawer-tabs">
          <button type="button" :class="{ active: detailTab === 'order' }" @click="detailTab = 'order'">订单资料</button>
          <button type="button" :class="{ active: detailTab === 'fit' }" @click="detailTab = 'fit'">匹配核对</button>
          <button type="button" :class="{ active: detailTab === 'report' }" @click="detailTab = 'report'">生产回报</button>
          <button type="button" :class="{ active: detailTab === 'history' }" @click="detailTab = 'history'">变更记录</button>
        </div>
        <div v-if="selectedTask" class="drawer-body">
          <template v-if="detailTab === 'order'">
            <section class="detail-card"><div class="section-title"><h3>订单与模具</h3><span>源行 {{ selectedTask.sourceRow ?? 'Mock' }}</span></div><div class="detail-grid"><div><label>模具编号</label><strong>{{ selectedTask.moldCode }}</strong></div><div><label>产品名称</label><strong>{{ selectedTask.productName }}</strong></div><div><label>单号 / 货号</label><strong>{{ selectedTask.orderNo }} / {{ selectedTask.itemNo }}</strong></div><div><label>颜色 / 材料</label><strong>{{ selectedTask.color }} / {{ selectedTask.material }}</strong></div><div><label>订单数</label><strong>{{ selectedTask.orderQuantity.toLocaleString() }}</strong></div><div><label>累计已啤</label><strong>{{ selectedValues?.cumulativeCompleted.toLocaleString() }}</strong></div></div></section>
            <section class="detail-card"><div class="section-title"><h3>计划区间</h3><span>{{ statusLabel(selectedTask.status) }}</span></div><div class="detail-grid"><div><label>计划开始</label><strong>{{ selectedTask.plannedStart }}</strong></div><div><label>计划完成</label><strong>{{ selectedTask.plannedEnd }}</strong></div><div><label>交货完成期</label><strong>{{ selectedTask.deliveryDate }}</strong></div><div><label>交期差</label><strong :class="{ 'danger-text': selectedTask.slackDays < 0 }">{{ selectedTask.slackDays.toFixed(1) }} 天</strong></div></div></section>
            <section class="detail-card"><div class="section-title"><h3>业务备注</h3><span>只读来源</span></div><p class="detail-copy">{{ selectedTask.note || '暂无备注' }}</p></section>
          </template>

          <template v-else-if="detailTab === 'fit'">
            <section class="detail-card"><div class="match-summary"><span :class="selectedTask.fitDecision.toLowerCase()">{{ selectedTask.fitScore }}</span><div><h3>{{ decisionLabel(selectedTask.fitDecision) }}</h3><p>先执行硬约束，再计算软评分。任何 FAIL 均禁止确认；资料缺失必须 REVIEW_REQUIRED。</p></div></div></section>
            <section class="detail-card"><div class="section-title"><h3>硬约束核对矩阵</h3><span>{{ selectedMachine?.code }} 对 {{ selectedTask.moldCode }}</span></div><div class="constraint-list"><div v-for="row in detailChecks" :key="row.key" class="constraint-row"><div><strong>{{ row.label }}</strong><p>{{ row.detail }}</p></div><span :class="row.decision.toLowerCase()">{{ decisionLabel(row.decision) }}</span></div></div></section>
            <section class="detail-card amber-card"><div class="section-title"><h3>尚未确认的规则</h3><span>生产版前必需</span></div><ul><li>射胶量是否取整啤净重、是否含水口，以及安全系数。</li><li>模具 L/W/H 的字段方向、模厚与开模行程语义。</li><li>双臂是否在所有边界下覆盖单臂要求。</li></ul></section>
          </template>

          <template v-else-if="detailTab === 'report'">
            <section class="detail-card">
              <div class="section-title"><h3>本班生产回报</h3><span>输入即预览，保存后写入 Mock 仓储</span></div>
              <div class="form-grid">
                <label>本班完成数<input :value="selectedValues?.shiftCompleted" type="number" min="0" @input="store.updateShiftCompleted(selectedTask, numberFromEvent($event))" /><small>本班累计完成，不是增量。</small></label>
                <label>累计已啤数<input :value="selectedValues?.cumulativeCompleted" type="number" min="0" :max="selectedTask.orderQuantity" @input="store.updateDraft(selectedTask, { cumulativeCompleted: numberFromEvent($event) })" /></label>
                <label>本班计划目标<input :value="selectedValues?.shiftTarget" type="number" min="1" @input="store.updateDraft(selectedTask, { shiftTarget: numberFromEvent($event) })" /></label>
                <label>停机 / 故障时间（小时）<input :value="store.reportDrafts[selectedTask.id]?.downtimeHours ?? selectedTask.downtimeHours" type="number" min="0" step="0.1" @input="store.updateDraft(selectedTask, { downtimeHours: numberFromEvent($event) })" /></label>
                <label>异常类型<select :value="store.reportDrafts[selectedTask.id]?.exceptionType ?? selectedTask.exceptionType" @change="store.updateDraft(selectedTask, { exceptionType: textFromEvent($event) })"><option value="">无异常</option><option value="换模">换模</option><option value="转色">转色</option><option value="设备故障">设备故障</option><option value="模具故障">模具故障</option><option value="缺料">缺料</option><option value="品质异常">品质异常</option></select></label>
                <label>任务状态<select :value="store.reportDrafts[selectedTask.id]?.status ?? selectedTask.status" @change="store.updateDraft(selectedTask, { status: textFromEvent($event) as SchedulingTask['status'] })"><option value="RUNNING">正在生产</option><option value="QUEUED">后续队列</option><option value="BLOCKED">已阻塞</option><option value="DONE">已完成</option></select></label>
                <label class="wide">回报备注<textarea :value="store.reportDrafts[selectedTask.id]?.remark ?? selectedTask.note" placeholder="填写本班异常、换模、转色或交接说明……" @input="store.updateDraft(selectedTask, { remark: textFromEvent($event) })" /></label>
              </div>
            </section>
            <section class="detail-card"><div class="section-title"><h3>保存后的派生结果</h3><span>实时预览</span></div><div class="preview-stats"><div><span>欠数</span><strong>{{ selectedValues?.remaining.toLocaleString() }}</strong></div><div><span>约需班次</span><strong>{{ selectedValues?.remainingShifts.toFixed(1) }}</strong></div><div><span>完成进度</span><strong>{{ selectedValues?.progress.toFixed(1) }}%</strong></div><div><span>计划完成</span><strong>{{ formatDateTime(selectedTask.plannedEnd) }}</strong></div></div></section>
          </template>

          <template v-else>
            <section class="detail-card"><div class="section-title"><h3>变更记录</h3><span>Mock 审计预览</span></div><div class="audit-list"><div><i><History :size="15" /></i><p><strong>啤机文员 · 更新累计已啤数</strong><span>2026-07-31 16:12 · 当前 revision {{ selectedTask.revision }}</span></p></div><div><i><ShieldCheck :size="15" /></i><p><strong>计划员 · 确认机台分配</strong><span>2026-07-31 09:28 · 分配至 {{ selectedMachine?.code }} · 匹配评分 {{ selectedTask.fitScore }}</span></p></div><div><i><Upload :size="15" /></i><p><strong>系统 · 从 Excel 抽样建立 Mock</strong><span>源行 {{ selectedTask.sourceRow ?? '模拟生成' }} · 未写回原工作簿</span></p></div></div></section>
            <section class="detail-card"><div class="section-title"><h3>并发保护演示</h3><span>optimistic revision</span></div><p class="detail-copy">点击顶部“模拟并发更新”，再修改并保存本任务，可验证 409 等价冲突提示与保留草稿后的重试流程。</p></section>
          </template>
        </div>
      </aside>
    </div>

    <div v-if="backlogDrawerOpen" class="drawer-backdrop" @click.self="backlogDrawerOpen = false">
      <aside class="drawer backlog-drawer" role="dialog" aria-modal="true" aria-label="待排订单池">
        <header class="drawer-header"><div><span>智能排程建议 · 先解释，后确认</span><h2>待排订单池</h2><p>硬约束过滤 → 交期 / 同模 / 颜色 / 负荷排序；不会自动发布。</p></div><button class="drawer-close" type="button" aria-label="关闭待排订单池" @click="backlogDrawerOpen = false"><X :size="18" /></button></header>
        <div class="drawer-tabs"><button type="button" :class="{ active: backlogTab === 'candidates' }" @click="backlogTab = 'candidates'">候选机台</button><button type="button" :class="{ active: backlogTab === 'rules' }" @click="backlogTab = 'rules'">规则解释</button><button type="button" :class="{ active: backlogTab === 'unmatched' }" @click="backlogTab = 'unmatched'">未匹配 {{ snapshot?.backlogOrders.filter((entry) => entry.moldDimensions === null).length }}</button></div>
        <div class="backlog-layout">
          <div class="backlog-list"><button v-for="order in snapshot?.backlogOrders" :key="order.id" type="button" :class="{ active: selectedBacklog?.id === order.id }" @click="store.selectedBacklogId = order.id"><strong>{{ order.orderNo }} · {{ order.moldCode }}</strong><span>{{ order.productName }} · {{ order.quantity.toLocaleString() }} 啤</span><small>交期 {{ order.deliveryDate }} · {{ order.note }}</small></button></div>
          <div class="candidate-content" v-if="selectedBacklog">
            <template v-if="backlogTab === 'candidates'">
              <section class="order-snapshot"><div><strong>{{ selectedBacklog.orderNo }} · {{ selectedBacklog.moldCode }}</strong><span>{{ selectedBacklog.productName }} · {{ selectedBacklog.quantity.toLocaleString() }} 啤</span></div><div><span>货号</span><strong>{{ selectedBacklog.itemNo }}</strong></div><div><span>交货完成期</span><strong>{{ selectedBacklog.deliveryDate }}</strong></div><div><span>颜色 / 用料</span><strong>{{ selectedBacklog.color }} · {{ selectedBacklog.material }}</strong></div><div><span>夹具要求</span><strong>{{ selectedBacklog.fixtureRequirement }}</strong></div></section>
              <div class="candidate-list"><article v-for="candidate in selectedBacklog.candidates" :key="candidate.machineId" class="candidate-card" :class="candidate.decision.toLowerCase()"><span class="rank">{{ candidate.rank }}</span><div><h3>{{ candidate.machineCode }} · {{ candidate.resultLabel }}</h3><p>{{ candidate.explanation }}</p><small>{{ candidate.warning }}</small><div class="constraint-chips"><span v-for="constraint in candidate.constraints" :key="constraint.key" :class="constraint.decision.toLowerCase()">{{ constraint.label }} · {{ decisionLabel(constraint.decision) }}</span></div></div><div class="candidate-score"><strong>{{ candidate.score }}</strong><span>匹配分</span><button type="button" :disabled="candidate.decision === 'FAIL' || saving || !isOnline" @click="openCandidate(candidate)">{{ candidate.decision === 'FAIL' ? '禁止排入' : !isOnline ? '离线暂停' : '放入草案' }}</button></div></article></div>
            </template>
            <template v-else-if="backlogTab === 'rules'">
              <section class="detail-card"><div class="section-title"><h3>候选机台决策顺序</h3><span>前端规则预览</span></div><ol class="rule-steps"><li><b>1</b><div><strong>厂区边界</strong><span>只在 {{ snapshot?.factoryName }} 数据集内查找，缺数据直接显错。</span></div></li><li><b>2</b><div><strong>硬约束</strong><span>安装面、射胶量、机械手、夹具与工艺能力；FAIL 立即淘汰。</span></div></li><li><b>3</b><div><strong>资料完整性</strong><span>模具 L/W/H 缺失时标记 REVIEW_REQUIRED，不得假定适配。</span></div></li><li><b>4</b><div><strong>软评分</strong><span>同模、同色、交期、机台负荷与换模成本仅用于排序。</span></div></li><li><b>5</b><div><strong>人工确认</strong><span>候选建议只写入草案，不自动发布正式计划。</span></div></li></ol></section>
            </template>
            <template v-else>
              <section class="detail-card amber-card"><div class="section-title"><h3>缺资料订单</h3><span>REVIEW_REQUIRED</span></div><p class="detail-copy">当前订单{{ selectedBacklog.moldDimensions ? '尺寸资料完整，可返回候选机台查看。' : '缺少模具尺寸，所有候选最多只能进入“需复核”状态。' }}</p><ul><li>补齐模具 L/W/H 与字段方向。</li><li>确认射胶净重是否包含水口及安全系数。</li><li>由有权限人员记录人工例外原因。</li></ul></section>
            </template>
          </div>
        </div>
      </aside>
    </div>

    <div v-if="conflict" class="conflict-banner" role="alert"><AlertTriangle :size="18" /><div><strong>检测到版本冲突</strong><span>{{ conflict.message }}</span></div><button type="button" @click="store.retryConflict">基于 revision {{ conflict.currentRevision }} 重试</button><button type="button" aria-label="关闭冲突提示" @click="store.conflict = null"><X :size="16" /></button></div>
    <div v-if="toast || localNotice" class="toast" role="status"><Check :size="16" />{{ toast || localNotice }}</div>
  </div>
</template>

<style scoped>
:global(html), :global(body), :global(#app) { min-width: 1180px; min-height: 100%; }
:global(body) { margin: 0; overflow: hidden; background: #edf3f3; }
button, input, select, textarea { font: inherit; }
button { cursor: pointer; }
button:disabled { cursor: not-allowed; opacity: .55; }
button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible, [tabindex]:focus-visible { outline:2px solid #1aa58f; outline-offset:2px; }
.skip-link { position:fixed; top:10px; left:10px; z-index:120; transform:translateY(-160%); padding:8px 12px; border-radius:8px; color:#fff; background:#062f2c; font-weight:800; transition:transform .15s; }.skip-link:focus { transform:translateY(0); }
.sr-only { position:absolute!important; width:1px!important; height:1px!important; padding:0!important; margin:-1px!important; overflow:hidden!important; clip:rect(0,0,0,0)!important; white-space:nowrap!important; border:0!important; }
.schedule-shell { --brand-950:#052f2c; --brand-900:#073d38; --brand-800:#07554c; --brand-700:#0b6b5f; --brand-600:#0f8878; --mint:#2bc6a7; --line:#d7e2e5; --ink:#17303c; --muted:#6c808a; display:flex; width:100vw; height:100vh; overflow:hidden; color:var(--ink); background:#edf3f3; font:12px/1.45 Inter,"Microsoft YaHei",system-ui,sans-serif; }
.schedule-sidebar { display:flex; flex:0 0 224px; flex-direction:column; min-height:0; color:#d7efeb; background:linear-gradient(180deg,#073a36 0%,#062d2b 100%); border-right:1px solid rgba(255,255,255,.07); }
.brand-block { display:flex; align-items:center; gap:12px; height:72px; padding:0 18px; border-bottom:1px solid rgba(255,255,255,.09); }
.brand-mark { display:grid; width:37px; height:37px; place-items:center; border:1px solid rgba(255,255,255,.2); border-radius:11px; color:white; background:linear-gradient(145deg,#25ab97,#087064); box-shadow:0 8px 20px rgba(0,0,0,.2); }
.brand-block strong { display:block; font-size:14px; color:#fff; }.brand-block span { display:block; margin-top:2px; color:#81afa8; font-size:10px; letter-spacing:.8px; }
.schedule-sidebar nav { flex:1; overflow:auto; padding:8px 12px 16px; }.nav-label { margin:14px 9px 8px; color:#70a099; font-size:11px; font-weight:800; letter-spacing:.5px; }
.nav-item { display:flex; align-items:center; gap:11px; width:100%; height:42px; margin:2px 0; padding:0 12px; border:0; border-radius:11px; color:#bcd8d4; background:transparent; text-align:left; }
.nav-item:hover { color:#fff; background:rgba(255,255,255,.06); }.nav-item.active { color:#fff; background:rgba(30,180,156,.16); box-shadow:inset 3px 0 #2dd2b3; }.nav-item span { margin-left:auto; padding:2px 7px; border-radius:999px; color:#ffe3a2; background:rgba(188,128,9,.22); font-size:11px; font-weight:800; }
.source-panel { margin:12px; padding:12px; border:1px solid rgba(255,255,255,.12); border-radius:12px; background:rgba(255,255,255,.035); }.source-panel div { display:flex; justify-content:space-between; gap:10px; padding:3px 0; }.source-panel span { color:#89aaa5; }.source-panel strong { color:#fff; }.source-panel i { display:inline-block; width:7px; height:7px; margin-right:6px; border-radius:50%; background:#32d3aa; box-shadow:0 0 0 4px rgba(50,211,170,.12); }.source-panel i.offline { background:#f0aa35; box-shadow:0 0 0 4px rgba(240,170,53,.14); }
.schedule-main { flex:1; min-width:0; min-height:0; overflow:auto; }.workspace-header { position:sticky; top:0; z-index:30; display:flex; align-items:center; justify-content:space-between; gap:18px; height:72px; padding:0 18px; border-bottom:1px solid #cbd8dc; background:rgba(255,255,255,.97); box-shadow:0 2px 12px rgba(20,50,58,.05); }
.title-cluster,.header-actions,.title-cluster>div>p,.drawer-actions,.machine-strip,.machine-load,.color-line,.progress-cell,.match-summary { display:flex; align-items:center; }.title-cluster { gap:11px; min-width:0; }.icon-button { display:grid; width:34px; height:34px; place-items:center; border:1px solid var(--line); border-radius:9px; color:#38525d; background:#fff; }.title-cluster>div>p { gap:4px; margin:0; color:#7c8f98; font-weight:700; }.title-cluster h1 { margin:2px 0 0; font-size:19px; line-height:1.2; color:#162b35; }.mode-badge { display:inline-flex; align-items:center; gap:5px; margin-left:10px; padding:5px 9px; border:1px solid #e9ce8d; border-radius:999px; color:#936100; background:#fff8e4; font-weight:800; white-space:nowrap; }
.header-actions { gap:8px; }.header-actions select,.date-chip,.button { height:36px; border:1px solid #cbd9dd; border-radius:9px; color:#29414d; background:#fff; }.header-actions select { min-width:106px; padding:0 12px; font-weight:750; }.date-chip,.button { display:inline-flex; align-items:center; justify-content:center; gap:7px; padding:0 12px; font-weight:750; white-space:nowrap; }.button:hover { border-color:#79b7ac; background:#f5fbfa; }.button.success { color:#08735d; border-color:#b8e5da; background:#eaf9f4; }.button.offline { color:#9b6206; border-color:#e8cc8f; background:#fff7e3; }.button.primary { color:white; border-color:var(--brand-700); background:var(--brand-700); }.button.primary:hover { background:var(--brand-800); }.button.compact { height:32px; padding:0 10px; }.avatar { width:38px; height:38px; border:0; border-radius:10px; color:#fff; background:var(--brand-950); font-weight:900; }.dirty-dot { width:6px; height:6px; border-radius:50%; background:#ffd56b; }
.connection-banner,.operation-error { display:flex; align-items:center; gap:8px; min-height:34px; margin:10px 16px -2px; padding:6px 10px; border:1px solid #e4c77f; border-radius:9px; color:#815408; background:#fff7df; }.connection-banner strong { margin-right:5px; }.operation-error { color:#a52735; border-color:#efb5bc; background:#fff0f2; }.operation-error span { flex:1; }.operation-error button { display:grid; width:27px; height:27px; place-items:center; border:0; border-radius:7px; color:inherit; background:transparent; }
.summary-grid { display:grid; grid-template-columns:repeat(6,minmax(165px,1fr)); gap:9px; min-width:1050px; padding:14px 16px 12px; }.summary-card { position:relative; min-width:0; overflow:hidden; padding:12px 14px 11px; border:1px solid #d6e1e4; border-radius:12px; background:#fff; box-shadow:0 2px 7px rgba(27,59,66,.05); }.summary-card::after { content:""; position:absolute; top:-26px; right:-24px; width:72px; height:72px; border-radius:50%; background:#e9f6f2; }.summary-card--blue::after { background:#e8f1fb; }.summary-card--red::after { background:#ffeaec; }.summary-card--amber::after { background:#fff0d2; }.summary-card>div { position:relative; z-index:1; display:flex; justify-content:space-between; color:#657a84; font-weight:800; }.summary-card p { margin:6px 0 1px; }.summary-card strong { color:var(--brand-700); font-size:23px; letter-spacing:-.6px; }.summary-card--blue strong { color:#195b93; }.summary-card--red strong { color:#b52d3a; }.summary-card--amber strong { color:#a56505; }.summary-card--slate strong { color:#1d3540; }.summary-card b { margin-left:5px; color:#607782; font-weight:700; }.summary-card small { color:#84959d; }
.workbench { display:flex; flex-direction:column; min-width:1050px; height:calc(100vh - 173px); margin:0 16px 12px; overflow:hidden; border:1px solid #cedbdd; border-radius:13px; background:#fff; box-shadow:0 5px 14px rgba(22,53,60,.06); }.toolbar { display:flex; align-items:center; gap:8px; flex:0 0 auto; padding:7px 12px; border-bottom:1px solid var(--line); }.toolbar--top { height:44px; }.toolbar--filters { min-height:42px; background:#fbfdfd; }.segmented,.filter-pills { display:flex; align-items:center; gap:3px; }.segmented { padding:3px; border:1px solid #d7e2e4; border-radius:9px; background:#f2f6f6; }.segmented button,.filter-pills button { display:flex; align-items:center; gap:6px; height:28px; padding:0 10px; border:0; border-radius:7px; color:#61747e; background:transparent; font-weight:750; }.segmented button.active { color:#0b6559; background:#fff; box-shadow:0 1px 4px rgba(18,49,55,.1); }.filter-pills button { border:1px solid transparent; border-radius:999px; }.filter-pills button.active { color:#fff; background:var(--brand-700); }.search-box { display:flex; align-items:center; gap:8px; width:min(500px,32vw); height:32px; padding:0 9px; border:1px solid #d2dee1; border-radius:9px; color:#738891; background:#fff; }.search-box input { flex:1; min-width:0; border:0; outline:0; color:#263f4a; background:transparent; }.search-box:focus-within { border-color:#4fae9e; box-shadow:0 0 0 3px rgba(47,170,150,.12); }.search-box kbd { padding:1px 6px; border:1px solid #d8e1e4; border-radius:5px; color:#87969d; background:#f3f6f7; font-size:10px; }.toolbar-spacer { flex:1; }.toolbar--filters select { height:30px; padding:0 28px 0 9px; border:1px solid #d4e0e3; border-radius:8px; color:#405862; background:#fff; }.result-count { margin-left:auto; color:#7d8f97; white-space:nowrap; }
.column-chooser { position:relative; }.column-menu { position:absolute; top:38px; right:0; z-index:35; display:grid; gap:8px; width:180px; padding:12px; border:1px solid #cbdadd; border-radius:10px; background:#fff; box-shadow:0 12px 30px rgba(20,49,57,.16); }.column-menu>strong { color:#243e49; }.column-menu label { display:flex; align-items:center; gap:8px; color:#58707a; }.column-menu input { accent-color:#0b7567; }
.loading-state,.empty-state,.filter-empty-state { display:grid; flex:1; place-items:center; align-content:center; gap:10px; min-height:280px; color:#68808a; }.empty-state { margin:32px; padding:50px; border:1px dashed #aebfc3; border-radius:16px; background:#fff; }.empty-state h2,.empty-state p { margin:0; }.empty-state h2,.filter-empty-state strong { color:#243b45; }.filter-empty-state span { max-width:460px; text-align:center; }
.table-scroller { flex:1; min-height:0; overflow:auto; background:#fff; }.schedule-table { width:100%; min-width:1900px; border-collapse:separate; border-spacing:0; table-layout:fixed; }.schedule-table th { position:sticky; top:0; z-index:8; height:38px; padding:0 9px; border-bottom:1px solid #ccdadd; color:#536b75; background:#edf3f4; font-weight:850; text-align:left; white-space:nowrap; }.schedule-table th:nth-child(1){width:112px}.schedule-table th:nth-child(2){width:62px}.schedule-table th:nth-child(3){width:220px}.schedule-table th:nth-child(4){width:170px}.schedule-table th:nth-child(5){width:165px}.schedule-table th:nth-child(n+6):nth-child(-n+10){width:108px}.schedule-table th:nth-child(11){width:155px}.schedule-table th:nth-child(12),.schedule-table th:nth-child(13){width:150px}.schedule-table th:nth-child(14){width:125px}.schedule-table th:nth-child(15){width:125px}.schedule-table th:nth-child(16){width:82px}.schedule-table td { height:52px; padding:6px 9px; border-right:1px solid #e3eaec; border-bottom:1px solid #dde6e8; vertical-align:middle; background:var(--row-background,#fff); }.schedule-table td small { display:block; margin-top:2px; color:#7c9099; font-size:12px; }.schedule-table td>strong { color:#213a45; }.task-row { --row-background:#fff; background:var(--row-background); }.task-row:hover { --row-background:#f3fbf9; }.task-row--running { --row-background:#eefaf7; }.task-row--critical { --row-background:#fffafb; }.schedule-table th:nth-child(1),.task-row td:nth-child(1) { position:sticky; left:0; z-index:9; }.schedule-table th:nth-child(2),.task-row td:nth-child(2) { position:sticky; left:112px; z-index:9; }.schedule-table th:nth-child(3),.task-row td:nth-child(3) { position:sticky; left:174px; z-index:9; box-shadow:7px 0 10px -10px rgba(20,54,62,.7); }.schedule-table th:nth-child(-n+3) { z-index:14; }.machine-row td { position:sticky; top:38px; left:0; z-index:7; height:42px; padding:0; color:#d5f1ec; background:#0b6157; border:0; }.machine-strip { min-width:1500px; height:42px; padding:0 12px; gap:10px; }.density-compact .schedule-table td { height:44px; padding-top:3px; padding-bottom:3px; }.density-compact .machine-row td,.density-compact .machine-strip { height:38px; }.collapse-button { display:grid; width:27px; height:27px; place-items:center; border:1px solid rgba(255,255,255,.2); border-radius:8px; color:#fff; background:rgba(255,255,255,.04); }.collapse-button svg { transition:transform .2s; }.collapse-button svg.collapsed { transform:rotate(-90deg); }.machine-code { display:flex; align-items:center; gap:8px; min-width:72px; color:#fff; font-size:14px; }.machine-code i { width:8px; height:8px; border-radius:50%; background:#65e3bc; box-shadow:0 0 0 4px rgba(101,227,188,.14); }.machine-strip>span { display:flex; align-items:center; gap:7px; white-space:nowrap; }.machine-strip em { width:1px; height:17px; background:rgba(255,255,255,.18); }.machine-current { color:#bde2dc; }.machine-current strong { color:#fff; }.machine-note { color:#ffd18b; }.machine-load { margin-left:auto; gap:7px; }.machine-load>i { width:90px; height:6px; overflow:hidden; border-radius:999px; background:rgba(255,255,255,.16); }.machine-load>i>b { display:block; height:100%; border-radius:inherit; background:#53d6b5; }
.row-action { min-height:28px; padding:0 9px; border:1px solid #b9cdd1; border-radius:7px; color:#0a6b5e; background:#fff; font-weight:800; }.row-action:hover { color:#fff; border-color:#0b7567; background:#0b7567; }.load-more-row { display:flex; align-items:center; justify-content:center; gap:14px; min-height:48px; padding:8px; color:#6d818a; background:#f8fbfb; }.load-more-row .button { height:30px; }
.status-chip,.fit-chip { display:inline-flex; align-items:center; gap:6px; min-height:25px; padding:2px 8px; border:0; border-radius:999px; font-weight:800; }.status-chip.running { color:#08755e; background:#dff8ef; }.status-chip.queued { color:#596e78; background:#eaf0f2; }.status-chip.blocked { color:#ac3a45; background:#ffe9ec; }.status-chip.done { color:#315a78; background:#e5f0fb; }.status-chip i { width:6px; height:6px; border-radius:50%; background:#28bf91; }.now-badge { display:grid; width:34px; height:34px; place-items:center; border-radius:10px; color:#fff; background:var(--brand-700); font-size:10px; font-weight:900; }.sequence-badge { display:grid; width:28px; height:28px; place-items:center; border-radius:8px; color:#5e737d; background:#edf2f3; font-weight:900; }.cell-link { display:block; width:100%; padding:0; border:0; color:#203844; background:transparent; text-align:left; }.cell-link:hover strong { color:var(--brand-700); text-decoration:underline; }.cell-link strong,.cell-link small { display:block; }.color-line { gap:6px; font-weight:800; }.color-line i { width:9px; height:9px; border:1px solid rgba(0,0,0,.1); border-radius:50%; }.numeric { color:#25404b; font-variant-numeric:tabular-nums; font-weight:800; }.danger-text { color:#c62f3e!important; }.inline-stepper { display:grid; grid-template-columns:26px 52px 26px; height:29px; }.inline-stepper button,.inline-stepper input { min-width:0; border:1px solid #cbdcdf; background:#fff; text-align:center; }.inline-stepper button:first-child { border-radius:7px 0 0 7px; }.inline-stepper button:last-child { border-radius:0 7px 7px 0; }.inline-stepper input { border-right:0; border-left:0; outline:0; font-weight:850; }.inline-stepper input::-webkit-inner-spin-button { appearance:none; }.progress-cell { position:relative; flex-wrap:wrap; gap:7px; }.progress-cell>div { width:92px; height:7px; overflow:hidden; border-radius:999px; background:#e5edef; }.progress-cell>div i { display:block; height:100%; border-radius:inherit; background:linear-gradient(90deg,#0e7a6c,#31c4a8); }.progress-cell strong { color:#58707b; }.progress-cell small { flex-basis:100%; }.risk-chip,.fit-chip { display:inline-flex; padding:4px 8px; border-radius:999px; font-weight:850; }.risk-chip.overdue { color:#c13543; background:#ffe9ec; }.risk-chip.soon { color:#a36505; background:#fff2d7; }.risk-chip.safe { color:#0b735f; background:#e4f7f1; }.fit-chip.pass { color:#08705d; background:#ddf5ee; }.fit-chip.review_required { color:#9b6108; background:#fff0d2; }.fit-chip.fail { color:#b62d3b; background:#ffe6e9; }
.timeline-view { flex:1; min-height:0; overflow:auto; padding:12px; background:#f7fafb; }.timeline-board { min-width:1300px; overflow:hidden; border:1px solid var(--line); border-radius:10px; background:#fff; }.timeline-head,.timeline-row { display:grid; grid-template-columns:210px 1fr; }.timeline-head { position:sticky; top:0; z-index:10; height:40px; background:#edf3f4; }.timeline-head strong { padding:11px 12px; border-right:1px solid var(--line); }.timeline-head span { display:none; }.timeline-head::after { content:"07-31     08-01     08-02     08-03     08-04     08-05     08-06     08-07     08-08     08-09     08-10     08-11     08-12     08-13"; align-self:center; padding:0 18px; color:#607681; word-spacing:26px; white-space:pre; }.timeline-row { position:relative; min-height:92px; border-top:1px solid var(--line); }.timeline-label { position:sticky; left:0; z-index:3; padding:15px 12px; border-right:1px solid var(--line); background:#fff; }.timeline-label strong,.timeline-label span { display:block; }.timeline-label span { margin-top:5px; color:#748891; }.timeline-grid { display:grid; grid-template-columns:repeat(14,1fr); }.timeline-grid i { border-right:1px solid #edf1f2; }.timeline-bar { position:absolute; z-index:2; height:22px; overflow:hidden; padding:2px 8px; border:1px solid #a9ddd2; border-radius:6px; color:#07584e; background:#dff5ef; font-weight:800; text-overflow:ellipsis; white-space:nowrap; }.timeline-bar.critical { color:#9d2e3a; border-color:#efbac0; background:#ffe7ea; }.timeline-bar.review { box-shadow:inset 0 -3px #e3a82d; }.workbench-footer { display:flex; justify-content:space-between; gap:24px; flex:0 0 auto; min-height:32px; padding:7px 12px; border-top:1px solid var(--line); color:#778991; background:#fbfdfd; }
.drawer-backdrop { position:fixed; inset:0; z-index:60; background:rgba(5,31,31,.42); backdrop-filter:blur(3px); }.drawer { position:absolute; top:0; right:0; display:flex; flex-direction:column; width:min(610px,94vw); height:100%; background:#f5f8f8; box-shadow:-18px 0 42px rgba(0,0,0,.18); animation:slide-in .2s ease-out; }.backlog-drawer { width:min(820px,96vw); }.drawer-header { position:relative; padding:18px 20px 15px; color:#fff; background:linear-gradient(130deg,#063e39,#0b6a5e); }.drawer-header span { color:#a9dcd3; font-weight:750; }.drawer-header h2 { margin:5px 0 0; font-size:19px; }.drawer-header p { margin:5px 0 0; color:#d1ebe6; }.drawer-close { position:absolute; top:17px; right:18px; display:grid; width:34px; height:34px; place-items:center; border:1px solid rgba(255,255,255,.22); border-radius:9px; color:#fff; background:rgba(255,255,255,.06); }.drawer-actions { gap:7px; margin-top:13px; }.drawer-actions button { display:inline-flex; align-items:center; gap:6px; height:31px; padding:0 10px; border:1px solid rgba(255,255,255,.2); border-radius:8px; color:#fff; background:rgba(255,255,255,.07); font-weight:750; }.drawer-actions button.primary { color:#075248; background:#e4fff7; }.drawer-tabs { display:flex; gap:2px; flex:0 0 auto; height:45px; padding:6px 12px 0; border-bottom:1px solid var(--line); background:#fff; }.drawer-tabs button { position:relative; padding:0 12px; border:0; color:#697d86; background:transparent; font-weight:800; }.drawer-tabs button.active { color:var(--brand-700); }.drawer-tabs button.active::after { content:""; position:absolute; right:10px; bottom:0; left:10px; height:2px; background:var(--brand-700); }.drawer-body { flex:1; min-height:0; overflow:auto; padding:14px; }.detail-card { margin-bottom:12px; padding:14px; border:1px solid var(--line); border-radius:11px; background:#fff; }.section-title { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:12px; }.section-title h3 { margin:0; font-size:14px; }.section-title span { color:#778a93; }.detail-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }.detail-grid>div { padding:10px; border-radius:9px; background:#f4f7f8; }.detail-grid label,.detail-grid strong { display:block; }.detail-grid label { margin-bottom:4px; color:#778b94; }.detail-copy { margin:0; color:#5d727c; line-height:1.7; }.match-summary { gap:14px; }.match-summary>span { display:grid; width:58px; height:58px; place-items:center; border-radius:13px; font-size:22px; font-weight:950; }.match-summary>span.pass { color:#fff; background:var(--brand-700); }.match-summary>span.review_required { color:#885400; background:#ffe9b9; }.match-summary>span.fail { color:#fff; background:#bd3341; }.match-summary h3,.match-summary p { margin:0; }.match-summary p { margin-top:4px; color:#6a7e87; }.constraint-list { display:grid; gap:8px; }.constraint-row { display:flex; align-items:center; gap:10px; padding:10px; border:1px solid #e1e8ea; border-radius:9px; }.constraint-row>div { flex:1; }.constraint-row strong,.constraint-row p { margin:0; }.constraint-row p { margin-top:3px; color:#6f838c; }.constraint-row>span,.constraint-chips span { padding:4px 7px; border-radius:999px; font-weight:800; }.constraint-row>span.pass,.constraint-chips .pass { color:#08705d; background:#ddf5ee; }.constraint-row>span.review_required,.constraint-chips .review_required { color:#986009; background:#fff0d0; }.constraint-row>span.fail,.constraint-chips .fail { color:#b22d3a; background:#ffe4e8; }.amber-card { border-color:#ead5a1; background:#fffbf0; }.detail-card ul { margin:8px 0 0; padding-left:20px; color:#5e727c; }.detail-card li { margin:6px 0; }.form-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:11px; }.form-grid label { color:#516872; font-weight:750; }.form-grid input,.form-grid select,.form-grid textarea { display:block; width:100%; min-height:36px; margin-top:5px; padding:7px 9px; border:1px solid #cad9dc; border-radius:8px; color:#223b46; background:#fff; box-sizing:border-box; outline:0; }.form-grid input:focus,.form-grid select:focus,.form-grid textarea:focus { border-color:#4fae9e; box-shadow:0 0 0 3px rgba(47,170,150,.12); }.form-grid small { display:block; margin-top:4px; color:#8999a0; }.form-grid .wide { grid-column:1/-1; }.form-grid textarea { min-height:82px; resize:vertical; }.preview-stats { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; }.preview-stats div { padding:10px; border-radius:9px; background:#f1f6f6; }.preview-stats span,.preview-stats strong { display:block; }.preview-stats span { color:#738790; }.preview-stats strong { margin-top:4px; font-size:15px; }.audit-list { display:grid; gap:12px; }.audit-list>div { display:flex; gap:10px; }.audit-list i { display:grid; flex:0 0 32px; height:32px; place-items:center; border-radius:9px; color:#0b6b5f; background:#e2f4ef; }.audit-list p,.audit-list strong,.audit-list span { display:block; margin:0; }.audit-list span { margin-top:3px; color:#7b8e96; }
.backlog-layout { display:grid; grid-template-columns:220px minmax(0,1fr); flex:1; min-height:0; }.backlog-list { overflow:auto; padding:10px; border-right:1px solid var(--line); background:#f4f7f7; }.backlog-list button { display:block; width:100%; margin-bottom:7px; padding:10px; border:1px solid #d4e0e2; border-radius:9px; color:#263f49; background:#fff; text-align:left; }.backlog-list button.active { border-color:#55b5a5; background:#ecfaf6; box-shadow:inset 3px 0 #12937f; }.backlog-list strong,.backlog-list span,.backlog-list small { display:block; }.backlog-list span { margin-top:3px; color:#697f88; }.backlog-list small { margin-top:4px; color:#8a999f; }.candidate-content { overflow:auto; padding:12px; }.order-snapshot { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin-bottom:11px; padding:11px; border:1px solid var(--line); border-radius:10px; background:#fff; }.order-snapshot>div:first-child { grid-column:1/-1; }.order-snapshot span,.order-snapshot strong { display:block; }.order-snapshot span { color:#738790; }.order-snapshot>div:first-child span { margin-top:3px; }.candidate-list { display:grid; gap:9px; }.candidate-card { display:grid; grid-template-columns:42px 1fr 86px; gap:10px; align-items:start; padding:11px; border:1px solid var(--line); border-radius:10px; background:#fff; }.candidate-card.pass { border-left:3px solid #159681; }.candidate-card.review_required { border-left:3px solid #d39a28; }.candidate-card.fail { border-left:3px solid #d44b58; }.rank { display:grid; width:38px; height:38px; place-items:center; border-radius:10px; color:#fff; background:var(--brand-700); font-size:15px; font-weight:950; }.candidate-card h3,.candidate-card p { margin:0; }.candidate-card p { margin-top:4px; color:#657a84; }.candidate-card small { display:block; margin-top:4px; color:#ad6d0a; }.constraint-chips { display:flex; flex-wrap:wrap; gap:4px; margin-top:8px; }.candidate-score { text-align:center; }.candidate-score strong,.candidate-score span { display:block; }.candidate-score strong { color:var(--brand-700); font-size:21px; }.candidate-score span { color:#7b8e96; }.candidate-score button { width:82px; min-height:30px; margin-top:8px; border:1px solid #b9ced2; border-radius:8px; color:#29434d; background:#fff; font-weight:800; }.candidate-score button:not(:disabled):hover { color:#fff; border-color:var(--brand-700); background:var(--brand-700); }.rule-steps { display:grid; gap:12px; margin:0; padding:0; list-style:none; }.rule-steps li { display:flex; gap:10px; align-items:flex-start; }.rule-steps b { display:grid; flex:0 0 30px; height:30px; place-items:center; border-radius:8px; color:#fff; background:var(--brand-700); }.rule-steps strong,.rule-steps span { display:block; }.rule-steps span { margin-top:3px; color:#6c8089; }
.conflict-banner { position:fixed; right:24px; bottom:24px; z-index:90; display:flex; align-items:center; gap:10px; max-width:600px; padding:12px; border:1px solid #e7be67; border-radius:11px; color:#724b04; background:#fff6dd; box-shadow:0 10px 30px rgba(0,0,0,.18); }.conflict-banner div { flex:1; }.conflict-banner strong,.conflict-banner span { display:block; }.conflict-banner button { min-height:30px; border:1px solid #d6b45d; border-radius:7px; color:#704a03; background:#fff; font-weight:750; }.toast { position:fixed; left:50%; bottom:22px; z-index:95; display:flex; align-items:center; gap:8px; transform:translateX(-50%); padding:11px 16px; border-radius:10px; color:#fff; background:#064a43; box-shadow:0 10px 25px rgba(0,0,0,.2); font-weight:750; }.spin { animation:spin 1s linear infinite; }
@keyframes spin { to { transform:rotate(360deg) } } @keyframes slide-in { from { transform:translateX(100%) } to { transform:translateX(0) } }
@media (max-width:1280px) { .schedule-sidebar { flex-basis:200px; }.summary-grid { grid-template-columns:repeat(3,1fr); }.workbench { height:calc(100vh - 276px); }.mode-badge { display:none; }.header-actions .date-chip { display:none; } }
@media (prefers-reduced-motion: reduce) { :global(*), :global(*::before), :global(*::after) { scroll-behavior:auto!important; animation-duration:.01ms!important; animation-iteration-count:1!important; transition-duration:.01ms!important; } }
</style>

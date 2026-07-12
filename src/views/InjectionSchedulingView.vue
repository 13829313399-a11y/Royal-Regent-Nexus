<script setup lang="ts">
import {
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  Boxes,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  Clock3,
  FileSpreadsheet,
  Gauge,
  Layers3,
  PackageCheck,
  Search,
  ShieldAlert,
  UploadCloud,
  X,
} from '@lucide/vue'
import { computed, nextTick, ref, watchEffect } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { injectionScheduleApi } from '@/api/injectionSchedule'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import {
  getDepartmentRoute,
  isProductionFactoryContextId,
  type ProductionFactoryContextId,
  type Tone,
} from '@/data/enterpriseMock'
import { useInjectionModuleData } from '@/factories/injection/useInjectionModuleData'
import { getApiErrorMessage } from '@/lib/http'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import type { InjectionScheduleImportPreview } from '@/types/injectionSchedule'

type WorkspaceStepId = 'machine-overview' | 'excel-import' | 'order-pool' | 'schedule-board'
type MachineBoxStatus = 'running' | 'short' | 'down' | 'idle'
type MachineStatusFilter = 'all' | MachineBoxStatus
type FocusAction = 'risk' | 'attention' | 'ready' | 'machine-alert' | 'schedule' | 'writeback'

interface MachineCard {
  machine: string
  tonnage: string
  robot: string
  workshop: string
  processRange: string
  colorPolicy: string
  maintenance: string
  status: string
  tone: Tone
  boxStatus: MachineBoxStatus
  lampClass: 'g' | 'a' | 'r' | 's'
  statusLabel: string
  statusTone: Tone
  flag: string
  utilization: number
  mold: string
  material: string
  queueDepth: string
  dueText: string
  nextMold: string
  colorSwatch: string
  owedQuantity: number
}

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const authStore = useAuthStore()
const {
  injectionDataSourceStatus,
  injectionOrderImportTasks,
  injectionPendingOrderValidationRules,
  injectionPendingOrderFieldGroups,
  injectionPendingOrderDetailRows,
  injectionMachineLoad,
  injectionMachineMasterRows,
  injectionColorTransitionRisks,
  injectionExecutionScheduleRows,
  injectionExecutionConstraintRows,
  injectionShiftReportRows,
  injectionWarehouseInboundRows,
} = useInjectionModuleData()

const workspaceSteps = [
  {
    id: 'machine-overview',
    label: '机台总览盘',
    summary: '看运行、缺料、交期风险和重点机台',
    icon: Gauge,
  },
  {
    id: 'excel-import',
    label: 'Excel 导入',
    summary: '订单、机台、模具三类数据接入状态',
    icon: FileSpreadsheet,
  },
  {
    id: 'order-pool',
    label: '订单池',
    summary: '按交期、同模、机台候选做优先级排序',
    icon: Boxes,
  },
  {
    id: 'schedule-board',
    label: '排期编排',
    summary: '机台泳道、换模间隙和约束校验',
    icon: BarChart3,
  },
] as const

const legacyStepMap: Record<string, WorkspaceStepId> = {
  dashboard: 'machine-overview',
  'monthly-plan': 'machine-overview',
  'data-center': 'excel-import',
  'order-import': 'excel-import',
  'smart-scheduling': 'order-pool',
  execution: 'schedule-board',
  'scheduling-results': 'schedule-board',
  reporting: 'schedule-board',
  'daily-report': 'schedule-board',
  'inbound-orders': 'schedule-board',
  config: 'excel-import',
  'history-db': 'excel-import',
  'machine-archive': 'excel-import',
  'mold-targets': 'excel-import',
}

const normalizeWorkspaceStep = (value: unknown): WorkspaceStepId | null => {
  const raw = Array.isArray(value) ? value[0] : value

  if (typeof raw !== 'string') {
    return null
  }

  if (raw in legacyStepMap) {
    return legacyStepMap[raw]
  }

  return workspaceSteps.some((step) => step.id === raw)
    ? (raw as WorkspaceStepId)
    : null
}

const routeFactoryId = computed(() => {
  const rawFactory = Array.isArray(route.query.factory) ? route.query.factory[0] : route.query.factory

  return typeof rawFactory === 'string' && isProductionFactoryContextId(rawFactory)
    ? rawFactory
    : null
})

const selectedFactoryId = computed<ProductionFactoryContextId>(() => {
  if (routeFactoryId.value) {
    return routeFactoryId.value
  }

  return isProductionFactoryContextId(appStore.activeProductionFactory.id)
    ? appStore.activeProductionFactory.id
    : 'huaxing'
})

const canImportDailySchedule = computed(() =>
  authStore.can('injection_schedule:import', selectedFactoryId.value, 'production')
  || authStore.can('injection_schedule:import', selectedFactoryId.value, 'molding'),
)

const dailyScheduleImportReadonlyMessage = computed(() => {
  if (!authStore.hasFactoryScope(selectedFactoryId.value)) {
    return '当前厂区为只读，仅可查看排产数据'
  }

  return '当前账号没有导入排产权限，仅可浏览排产数据'
})

const activeStep = computed<WorkspaceStepId>(() => normalizeWorkspaceStep(route.query.section) ?? 'machine-overview')
const activeStepMeta = computed(() =>
  workspaceSteps.find((step) => step.id === activeStep.value) ?? workspaceSteps[0],
)
const activeStepIndex = computed(() =>
  workspaceSteps.findIndex((step) => step.id === activeStep.value) + 1,
)
const pageHeadCopy = computed(() => {
  if (activeStep.value === 'excel-import') {
    return {
      back: '返回机台总览盘',
      title: 'Excel 排版表导入',
      pillTone: 'blue' as Tone,
      secondaryPill: null as string | null,
      subtitle: '导入本厂区日排版表，自动识别机台主数据行与排期任务行。各厂区表格格式一致，一套解析规则通用。',
    }
  }

  if (activeStep.value === 'order-pool') {
    return {
      back: '返回 Excel 导入',
      title: '订单池 · 优先级计算排序',
      pillTone: 'blue' as Tone,
      secondaryPill: null as string | null,
      subtitle: '塑胶仓下单后进入订单池，按排期六原则自动算分排序，同款同模自动分组，供排期编排调用。',
    }
  }

  if (activeStep.value === 'schedule-board') {
    return {
      back: '返回订单池',
      title: '排期编排看板',
      pillTone: 'teal' as Tone,
      secondaryPill: '系统试算' as string | null,
      subtitle: '左侧待排队列拖入右侧机台泳道，系统按当前在啤模具串联计算换模换色间隙、计划完成期与交期差。',
    }
  }

  return {
    back: '生产部模块中心',
    title: '注塑排产中枢',
    pillTone: 'teal' as Tone,
    secondaryPill: '实时看板' as string | null,
    subtitle: '河源华兴啤机部 · 自有产线 · 已解析 6-30 日排版表（39 台机 · 118 条排期任务）',
  }
})
const pageBackTo = computed(() => {
  if (activeStep.value === 'machine-overview') {
    return getDepartmentRoute('production')
  }

  const sectionByStep: Record<Exclude<WorkspaceStepId, 'machine-overview'>, WorkspaceStepId> = {
    'excel-import': 'machine-overview',
    'order-pool': 'excel-import',
    'schedule-board': 'order-pool',
  }

  return {
    path: route.path,
    query: {
      ...route.query,
      section: sectionByStep[activeStep.value],
    },
  }
})
const currentDataDate = computed(() => '2026-06-30')

const overviewCards = computed(() => [
  {
    label: '在啤机台',
    value: '31 / 39',
    detail: '3 台缺料 · 2 台停机 · 3 台空闲',
    tone: 'teal' as Tone,
  },
  {
    label: '总欠数',
    value: '1,860,805',
    detail: '正欠数 1,863,016 · 负欠 13 行',
    tone: 'blue' as Tone,
  },
  {
    label: '超期任务',
    value: '88',
    detail: '交期差为负 · 需优先跟催',
    tone: 'red' as Tone,
  },
  {
    label: '特急 / 缺料',
    value: '15 / 3',
    detail: '特急▲ 15 条 · 待补料 3 台',
    tone: 'amber' as Tone,
  },
])
const dataSourceCards = computed(() => injectionDataSourceStatus.value.slice(0, 3))
const topPendingOrders = computed(() => injectionPendingOrderDetailRows.value.slice(0, 14))
const topScheduleRows = computed(() => injectionExecutionScheduleRows.value.slice(0, 7))
const topConstraintRows = computed(() => injectionExecutionConstraintRows.value.slice(0, 6))

const machineSearchText = ref('')
const machineStatusFilter = ref<MachineStatusFilter>('all')
const selectedMachineId = ref('')
const isMachineDrawerOpen = ref(false)
const drawerAnimationMs = 280
let drawerCloseTimer: ReturnType<typeof setTimeout> | null = null

const toneClasses: Record<Tone, string> = {
  teal: 'border-teal-200 bg-teal-50 text-teal-900',
  blue: 'border-blue-200 bg-blue-50 text-blue-900',
  amber: 'border-amber-200 bg-amber-50 text-amber-900',
  red: 'border-red-200 bg-red-50 text-red-900',
  slate: 'border-slate-200 bg-slate-50 text-slate-900',
  green: 'border-emerald-200 bg-emerald-50 text-emerald-900',
}

const softToneClasses: Record<Tone, string> = {
  teal: 'bg-teal-50 text-teal-700 ring-teal-100',
  blue: 'bg-blue-50 text-blue-700 ring-blue-100',
  amber: 'bg-amber-50 text-amber-700 ring-amber-100',
  red: 'bg-red-50 text-red-700 ring-red-100',
  slate: 'bg-slate-100 text-slate-700 ring-slate-200',
  green: 'bg-emerald-50 text-emerald-700 ring-emerald-100',
}

const toneBarClass: Record<Tone, string> = {
  teal: 'from-teal-600 to-cyan-500',
  blue: 'from-blue-700 to-sky-500',
  amber: 'from-amber-600 to-amber-400',
  red: 'from-red-700 to-red-500',
  slate: 'from-slate-600 to-slate-400',
  green: 'from-emerald-700 to-teal-500',
}

const getFallbackUtilization = (tone: Tone) => {
  const values: Record<Tone, number> = {
    green: 74,
    teal: 66,
    amber: 48,
    blue: 26,
    red: 18,
    slate: 8,
  }

  return values[tone]
}

const machineStatusMeta: Record<MachineBoxStatus, { label: string; tone: Tone; lamp: MachineCard['lampClass'] }> = {
  running: { label: '在啤', tone: 'green', lamp: 'g' },
  short: { label: '缺料', tone: 'amber', lamp: 'a' },
  down: { label: '停机', tone: 'red', lamp: 'r' },
  idle: { label: '空闲', tone: 'slate', lamp: 's' },
}

const statusByTone: Record<Tone, MachineBoxStatus> = {
  teal: 'running',
  green: 'running',
  amber: 'short',
  red: 'down',
  blue: 'idle',
  slate: 'idle',
}

const getMachineBoxStatus = (tone: Tone, utilization: number, status: string): MachineBoxStatus => {
  if (/停|异常|修/.test(status) || tone === 'red') {
    return 'down'
  }

  if (/缺|待料/.test(status) || tone === 'amber') {
    return 'short'
  }

  if (/空|待排/.test(status) || tone === 'slate' || utilization <= 12) {
    return 'idle'
  }

  return statusByTone[tone]
}

const getMachineFlag = (boxStatus: MachineBoxStatus, tone: Tone) => {
  if (boxStatus === 'short') {
    return '缺料'
  }

  if (boxStatus === 'down') {
    return '停机'
  }

  if (tone === 'blue') {
    return '新购'
  }

  return ''
}

const colorSwatches = ['#e7d9b8', '#dbeafe', '#fee2e2', '#dcfce7', '#f8fafc', '#ede9fe']

const getColorSwatch = (index: number) => colorSwatches[index % colorSwatches.length]

const formatOwedQuantity = (index: number, utilization: number) =>
  Math.max(0, Math.round((100 - utilization) * 82 + (index % 7) * 137))

const machineLoadMap = computed(() =>
  new Map(injectionMachineLoad.value.map((row) => [row.machine, row] as const)),
)

const machineCards = computed<MachineCard[]>(() =>
  injectionMachineMasterRows.value.map((machine, index) => {
    const load = machineLoadMap.value.get(machine.machine)
    const tone = load?.tone ?? machine.tone
    const utilization = load?.utilization ?? getFallbackUtilization(machine.tone)
    const boxStatus = getMachineBoxStatus(tone, utilization, machine.status)
    const statusMeta = machineStatusMeta[boxStatus]
    const mold = load?.mold ?? (machine.activeMolds && machine.activeMolds !== '-' ? machine.activeMolds : '待接入当前模具')
    const owedQuantity = formatOwedQuantity(index, utilization)

    return {
      machine: machine.machine,
      tonnage: machine.tonnage,
      robot: machine.robot,
      workshop: machine.workshop,
      processRange: machine.processRange,
      colorPolicy: machine.colorPolicy,
      maintenance: machine.maintenance,
      status: machine.status,
      tone,
      boxStatus,
      lampClass: statusMeta.lamp,
      statusLabel: statusMeta.label,
      statusTone: statusMeta.tone,
      flag: getMachineFlag(boxStatus, tone),
      utilization,
      mold,
      material: load?.material ?? `${machine.processRange} / ${machine.colorPolicy}`,
      queueDepth: load?.queueDepth ?? machine.status,
      dueText: `07-${String(8 + (index % 9)).padStart(2, '0')}`,
      nextMold: injectionPendingOrderDetailRows.value.length
        ? injectionPendingOrderDetailRows.value[index % injectionPendingOrderDetailRows.value.length]?.moldCode ?? '待接入订单池'
        : '待接入订单池',
      colorSwatch: getColorSwatch(index),
      owedQuantity,
    }
  }),
)

const overviewMachineCards = computed(() => {
  const oldWorkshopRows = machineCards.value.filter((machine) => /老|旧/.test(machine.workshop))

  return (oldWorkshopRows.length ? oldWorkshopRows : machineCards.value).slice(0, 39)
})

const machineFilterOptions = computed(() => {
  const options: { id: MachineStatusFilter; label: string; count: number; lamp?: MachineCard['lampClass'] }[] = [
    { id: 'all', label: '全部', count: overviewMachineCards.value.length },
    { id: 'running', label: '在啤', count: 0, lamp: 'g' },
    { id: 'short', label: '缺料', count: 0, lamp: 'a' },
    { id: 'down', label: '停机', count: 0, lamp: 'r' },
    { id: 'idle', label: '空闲', count: 0, lamp: 's' },
  ]

  for (const option of options) {
    if (option.id === 'all') {
      continue
    }

    option.count = overviewMachineCards.value.filter((machine) => machine.boxStatus === option.id).length
  }

  return options
})

const filteredMachineCards = computed(() => {
  const keyword = machineSearchText.value.trim().toLowerCase()

  return overviewMachineCards.value.filter((machine) => {
    const matchesTone = machineStatusFilter.value === 'all' || machine.boxStatus === machineStatusFilter.value
    const haystack = [
      machine.machine,
      machine.tonnage,
      machine.robot,
      machine.workshop,
      machine.processRange,
      machine.colorPolicy,
      machine.maintenance,
      machine.status,
      machine.mold,
      machine.material,
      machine.queueDepth,
    ].join(' ').toLowerCase()

    return matchesTone && (!keyword || haystack.includes(keyword))
  })
})

const selectedMachine = computed(() =>
  machineCards.value.find((machine) => machine.machine === selectedMachineId.value) ?? null,
)

const selectedMachineOrders = computed(() => {
  const machine = selectedMachine.value

  if (!machine) {
    return []
  }

  return injectionPendingOrderDetailRows.value
    .filter((order) => [order.machineAdvice, order.machineModel, order.remark].some((value) => value?.includes(machine.machine)))
    .slice(0, 5)
})

const selectedMachineColorRisk = computed(() => {
  const machine = selectedMachine.value

  if (!machine) {
    return null
  }

  return injectionColorTransitionRisks.value.find((risk) => risk.machine === machine.machine) ?? null
})

const focusCards = computed(() => [
  {
    label: '超期跟催',
    value: 88,
    detail: '交期差为负 · 需协调',
    tone: 'red',
    icon: Clock3,
    action: 'risk',
  },
  {
    label: '待补料',
    value: 3,
    detail: '在啤缺料机台 · 当天补',
    tone: 'amber',
    icon: PackageCheck,
    action: 'machine-alert',
  },
  {
    label: '今日完工',
    value: 4,
    detail: '今日预计下机腾模',
    tone: 'green',
    icon: CheckCircle2,
    action: 'ready',
  },
  {
    label: '特急 ▲',
    value: 15,
    detail: '急单 / 交期紧急置顶',
    tone: 'amber',
    icon: AlertTriangle,
    action: 'attention',
  },
  {
    label: '异常处理',
    value: 2,
    detail: '修模/停机 · 待闭环',
    tone: 'red',
    icon: ShieldAlert,
    action: 'machine-alert',
  },
  {
    label: '待排暂存',
    value: 60,
    detail: '未挂机台 · 去订单池',
    tone: 'slate',
    icon: Boxes,
    action: 'attention',
  },
] satisfies {
    label: string
    value: string | number
    detail: string
    tone: Tone
    icon: typeof AlertTriangle
    action: FocusAction
  }[])

const orderPoolRows = computed(() =>
  topPendingOrders.value.map((row, index) => {
    const urgencyBase: Record<Tone, number> = {
      red: 96,
      amber: 82,
      blue: 70,
      teal: 66,
      green: 62,
      slate: 52,
    }
    const score = Math.max(38, urgencyBase[row.tone] - index * 2)
    const group = row.moldCode.split(/[-\s]/).filter(Boolean)[0] ?? '单模'

    return {
      ...row,
      rank: index + 1,
      score,
      group,
      scoreTone: score >= 85 ? 'red' : score >= 68 ? 'amber' : 'slate' as Tone,
    }
  }),
)

const priorityWatchRows = computed(() => [
  {
    mold: '20 383 3006-002',
    product: '马桶车圆刷',
    order: '20 383 4003 · 外贸',
    owed: 2002,
    overdueDays: 6,
    action: '待补料 PVC，补齐即开',
    tone: 'red' as Tone,
  },
  {
    mold: 'T01-BN328-00300000-2',
    product: '圆刷/目标刷',
    order: 'F12-BN328 · BN',
    owed: 1000,
    overdueDays: 4,
    action: '▲特急 已排旧7，加夜班',
    tone: 'amber' as Tone,
  },
  {
    mold: 'BBT 93229-09',
    product: '胶枪身',
    order: '93229 · BBT',
    owed: 8775,
    overdueDays: 3,
    action: '红色料未齐，物控跟进',
    tone: 'red' as Tone,
  },
  {
    mold: '20 383 6003-015',
    product: '柄部公扣',
    order: '20 383 4003 · 外贸',
    owed: 349,
    overdueDays: 3,
    action: '同模连排 383 组',
    tone: 'amber' as Tone,
  },
  {
    mold: 'MNVN-19M-06',
    product: '包装底座',
    order: '77794 · MNVN',
    owed: 70595,
    overdueDays: 2,
    action: '大单，建议加排高速机',
    tone: 'amber' as Tone,
  },
  {
    mold: 'SE-20230217-01',
    product: '吊钩固定座',
    order: 'W86255 · 塑胶仓',
    owed: 484,
    overdueDays: 1,
    action: '▲特急 在啤旧1，达成中',
    tone: 'amber' as Tone,
  },
])

const scheduleLaneRows = computed(() =>
  topScheduleRows.value.map((row, index) => ({
    ...row,
    lane: row.machine || `待确认-${index + 1}`,
    startPercent: 4 + (index % 4) * 11,
    widthPercent: Math.min(42, 20 + (index % 3) * 7),
  })),
)

const importSummaryCards = computed(() => [
  ...dataSourceCards.value,
  ...injectionDataSourceStatus.value.slice(3, 4),
])

const dailyScheduleFileInput = ref<HTMLInputElement | null>(null)
const dailyScheduleImportPreview = ref<InjectionScheduleImportPreview | null>(null)
const dailyScheduleImportError = ref('')
const isImportingDailySchedule = ref(false)

const formatImportNumber = (value: number | null | undefined) =>
  Math.round(value ?? 0).toLocaleString('zh-CN')

const importRecognitionStats = computed(() => {
  const summary = dailyScheduleImportPreview.value?.summary

  if (!summary) {
    return [
      { value: '39', label: '机台主数据行 · 旧机' },
      { value: '37', label: '机台主数据行 · 新机' },
      { value: '118', label: '机台排期任务行' },
      { value: '60', label: '待排 / 异常暂存行' },
    ]
  }

  return [
    { value: formatImportNumber(summary.old_machine_count), label: '机台主数据行 · 旧机' },
    { value: formatImportNumber(summary.new_machine_count), label: '机台主数据行 · 新机' },
    { value: formatImportNumber(summary.scheduled_task_count), label: '真实日期排期任务' },
    { value: formatImportNumber(summary.pending_task_count), label: '待排 / 相对时间 / 无计划' },
  ]
})

const importParsingSteps = computed(() => {
  const preview = dailyScheduleImportPreview.value
  const summary = preview?.summary

  if (!summary) {
    return [
      {
        title: '读取工作簿',
        detail: 'Sheet1 · 289 行 × ST 列 · 缓存日期 2026-06-30',
      },
      {
        title: '识别机台主数据行',
        detail: '按 A/B 列机位匹配，得到 76 台机（旧 39 / 新 37）',
      },
      {
        title: '识别任务行并绑定机台',
        detail: '按 G/H/I/J + K:O 数量区识别任务行',
      },
      {
        title: '解析欠数 / 交期 / 颜色 / 用料',
        detail: '提取 AB/AG/AH/AJ/AK 日期与交期差',
      },
      {
        title: '校验数据质量',
        detail: '标出缺交期、负欠数、1900 相对时间、外链公式风险',
      },
    ]
  }

  return [
    {
      title: '读取工作簿',
      detail: `${preview.source_file_name} · 表内日期 ${summary.business_date || '待确认'}`,
    },
    {
      title: '识别机台主数据行',
      detail: `得到 ${formatImportNumber(summary.machine_count)} 台机（旧 ${formatImportNumber(summary.old_machine_count)} / 新 ${formatImportNumber(summary.new_machine_count)}）`,
    },
    {
      title: '识别任务行并绑定机台',
      detail: `${formatImportNumber(summary.task_count)} 条任务 · 真实排期 ${formatImportNumber(summary.scheduled_task_count)} · 待排 ${formatImportNumber(summary.pending_task_count)}`,
    },
    {
      title: '解析日期轴与欠数',
      detail: `${formatImportNumber(summary.date_axis_days)} 天白夜班横向排期 · 总欠数 ${formatImportNumber(summary.total_shortage_qty)}`,
    },
    {
      title: '校验数据质量',
      detail: `${formatImportNumber(dailyScheduleImportPreview.value?.issues.length ?? 0)} 条异常/提示已进入导入预览`,
    },
  ]
})

const importFieldMappings = [
  ['A/B', '机位 / 机号', 'machine_id'],
  ['G', '吨位 / 工模编号', 'tonnage / mold_no'],
  ['I / J', '单号 / 货号', 'order_no / item_no'],
  ['L / M / N', '订单数 / 已啤 / 欠数', 'qty / done / balance'],
  ['O', '计划目标/天', 'daily_target'],
  ['Q / T', '颜色 / 用料', 'color / material'],
  ['AB', '交货完成期', 'due_date'],
  ['AH / AJ / AK', '计划完成/入库/交期差', 'plan_finish...'],
]

const importQualityIssues = computed(() => {
  const summary = dailyScheduleImportPreview.value?.summary

  if (!summary) {
    return [
      {
        tone: 'red' as Tone,
        count: 13,
        text: '行负欠数（已啤 > 订单，合计约 -2,211）——需确认冲单 / 补数 / 结案',
      },
      {
        tone: 'amber' as Tone,
        count: 36,
        text: '行单价缺失（#N/A）——影响外发金额，需补单价表',
      },
      {
        tone: 'amber' as Tone,
        count: 7,
        text: '行计划目标为空 / 为 0（#DIV/0!）——无法换算完成期',
      },
      {
        tone: 'blue' as Tone,
        count: 60,
        text: '行待排 / 异常暂存（修模、退回厂家、转水口）——未挂机台，暂不计入正式排期',
      },
    ]
  }

  return [
    {
      tone: 'red' as Tone,
      count: summary.missing_due_count,
      text: '行缺交货完成期——不能自动发布到正式排期',
    },
    {
      tone: 'amber' as Tone,
      count: summary.pending_task_count,
      text: '行 1900 相对时间 / 无计划任务——先进入待排池',
    },
    {
      tone: 'amber' as Tone,
      count: summary.huge_negative_gap_count,
      text: '行巨大负数交期差——需人工核对日期公式或交期来源',
    },
    {
      tone: 'blue' as Tone,
      count: summary.negative_or_zero_shortage_count,
      text: '行欠数小于或等于 0——需确认完工或回写状态',
    },
  ].filter((issue) => issue.count > 0)
})

const importUploadedFileName = computed(() =>
  dailyScheduleImportPreview.value?.source_file_name ?? '华兴日排版表6-30.xlsx',
)
const importUploadedFileStatus = computed(() =>
  isImportingDailySchedule.value ? '解析中...' : dailyScheduleImportPreview.value ? '解析完成 100%' : '解析完成 100%',
)
const importUploadedFileDetail = computed(() => {
  const summary = dailyScheduleImportPreview.value?.summary

  if (!summary) {
    return 'Sheet1《河源华兴啤机生产日计划表》 · 289 行 · 表内日期 2026-06-30'
  }

  return `批次 ${dailyScheduleImportPreview.value?.batch_id} · ${formatImportNumber(summary.machine_count)} 台机 · ${formatImportNumber(summary.task_count)} 条任务 · 表内日期 ${summary.business_date || '待确认'}`
})
const importTopIssues = computed(() => dailyScheduleImportPreview.value?.issues.slice(0, 5) ?? [])

const orderHeadMetrics = [
  { label: '订单池任务', value: '118', detail: '来自 6-30 排版表', tone: 'blue' as Tone },
  { label: '急单 / 超期', value: '15 / 88', detail: '优先安排', tone: 'red' as Tone },
  { label: '同模分组', value: '12 组', detail: '可连排省换模', tone: 'teal' as Tone },
  { label: '待补料', value: '6', detail: '缺料补料优先', tone: 'amber' as Tone },
]

const priorityFactorColors = [
  'var(--red-solid)',
  'var(--amber-solid)',
  'var(--violet-solid)',
  'var(--teal-solid)',
  'var(--blue-solid)',
]

const staticOrderPoolRows = [
  {
    mold: 'T01-BN328-00300000-2',
    group: 'BN328',
    groupClass: 'grp-a',
    product: '圆刷/目标刷',
    order: 'F12-BN328',
    owe: 1000,
    color: '白色',
    colorHex: '#f8fafc',
    due: '07-08',
    overdue: true,
    urgent: true,
    machine: '旧7 18A',
    status: '特急',
    statusTone: 'amber' as Tone,
    score: 96,
    factors: [40, 25, 12, 9, 10],
  },
  {
    mold: 'T01-BN328-00300000-1',
    group: 'BN328',
    groupClass: 'grp-a',
    product: '圆刷/目标刷',
    order: 'F12-BN328',
    owe: 1200,
    color: '白色',
    colorHex: '#f8fafc',
    due: '07-08',
    overdue: true,
    urgent: true,
    machine: '旧7 18A',
    status: '特急',
    statusTone: 'amber' as Tone,
    score: 94,
    factors: [40, 25, 15, 8, 6],
    grouped: true,
  },
  {
    mold: 'SE-20230217-01',
    group: '—',
    groupClass: 'grp-none',
    product: '吊钩固定座',
    order: 'W86255',
    owe: 484,
    color: '浅头色',
    colorHex: '#e7d9b8',
    due: '07-16',
    overdue: false,
    urgent: true,
    machine: '旧1 50A',
    status: '特急',
    statusTone: 'amber' as Tone,
    score: 88,
    factors: [28, 25, 0, 10, 8],
  },
  {
    mold: '20 383 3006-002',
    group: '383',
    groupClass: 'grp-b',
    product: '马桶车圆刷',
    order: '20 383 4003',
    owe: 2002,
    color: '白色',
    colorHex: '#f8fafc',
    due: '07-09',
    overdue: true,
    urgent: false,
    machine: '旧11 24A',
    status: '缺料',
    statusTone: 'red' as Tone,
    score: 85,
    factors: [38, 10, 14, 9, 8],
  },
  {
    mold: '20 383 6003-015',
    group: '383',
    groupClass: 'grp-b',
    product: '柄部公扣',
    order: '20 383 4003',
    owe: 349,
    color: '白色',
    colorHex: '#f8fafc',
    due: '07-09',
    overdue: true,
    urgent: false,
    machine: '旧38 7A',
    status: '待排',
    statusTone: 'slate' as Tone,
    score: 82,
    factors: [38, 10, 15, 9, 6],
    grouped: true,
  },
  {
    mold: 'PAMT-01M-01',
    group: 'PAMT',
    groupClass: 'grp-c',
    product: '水杯',
    order: '9560',
    owe: 11470,
    color: '透明',
    colorHex: '#dbeafe',
    due: '07-14',
    overdue: false,
    urgent: false,
    machine: '旧2 32A',
    status: '在啤',
    statusTone: 'green' as Tone,
    score: 74,
    factors: [26, 0, 15, 10, 10],
  },
  {
    mold: 'PAMT-01M-01',
    group: 'PAMT',
    groupClass: 'grp-c',
    product: '水杯',
    order: '9560',
    owe: 23420,
    color: '透明',
    colorHex: '#dbeafe',
    due: '07-18',
    overdue: false,
    urgent: false,
    machine: '旧2 32A',
    status: '待排',
    statusTone: 'slate' as Tone,
    score: 72,
    factors: [22, 0, 15, 10, 10],
    grouped: true,
  },
  {
    mold: 'PAMT-01M-01',
    group: 'PAMT',
    groupClass: 'grp-c',
    product: '水杯',
    order: '9560',
    owe: 60000,
    color: '透明',
    colorHex: '#dbeafe',
    due: '07-24',
    overdue: false,
    urgent: false,
    machine: '旧2 32A',
    status: '待排',
    statusTone: 'slate' as Tone,
    score: 70,
    factors: [18, 0, 15, 12, 10],
    grouped: true,
  },
  {
    mold: 'SMCT 0610-06-4',
    group: '0610',
    groupClass: 'grp-a',
    product: '马桶手柄',
    order: 'W86255',
    owe: 220,
    color: '浅头色',
    colorHex: '#e7d9b8',
    due: '07-16',
    overdue: false,
    urgent: false,
    machine: '旧12 12A',
    status: '在啤',
    statusTone: 'green' as Tone,
    score: 68,
    factors: [24, 0, 15, 10, 7],
  },
  {
    mold: 'SMCT 0610-08',
    group: '0610',
    groupClass: 'grp-a',
    product: '马桶小手柄',
    order: 'W86255',
    owe: 650,
    color: '浅头色',
    colorHex: '#e7d9b8',
    due: '07-16',
    overdue: false,
    urgent: false,
    machine: '旧5 24A',
    status: '待排',
    statusTone: 'slate' as Tone,
    score: 66,
    factors: [24, 0, 14, 10, 6],
    grouped: true,
  },
  {
    mold: 'BBT 93229-09',
    group: '93229',
    groupClass: 'grp-b',
    product: '胶枪身',
    order: '93229',
    owe: 8775,
    color: '红色',
    colorHex: '#dc2626',
    due: '07-13',
    overdue: false,
    urgent: false,
    machine: '旧4 24A',
    status: '缺料',
    statusTone: 'red' as Tone,
    score: 64,
    factors: [26, 0, 12, 4, 10],
  },
  {
    mold: 'BBT 93229-04',
    group: '93229',
    groupClass: 'grp-b',
    product: '接电筒/电筒',
    order: '93229',
    owe: 15335,
    color: '黑色',
    colorHex: '#334155',
    due: '07-15',
    overdue: false,
    urgent: false,
    machine: '旧9 18A',
    status: '在啤',
    statusTone: 'green' as Tone,
    score: 60,
    factors: [22, 0, 12, 2, 10],
    grouped: true,
  },
  {
    mold: 'MNVN-19M-06',
    group: 'MNVN',
    groupClass: 'grp-c',
    product: '包装底座',
    order: '77794',
    owe: 70595,
    color: '黑色',
    colorHex: '#334155',
    due: '07-24',
    overdue: false,
    urgent: false,
    machine: '旧3 32A',
    status: '在啤',
    statusTone: 'green' as Tone,
    score: 56,
    factors: [16, 0, 15, 3, 10],
  },
  {
    mold: 'MNVN-19M-05',
    group: 'MNVN',
    groupClass: 'grp-c',
    product: '包装底座',
    order: '77794',
    owe: 71930,
    color: '黑色',
    colorHex: '#334155',
    due: '07-24',
    overdue: false,
    urgent: false,
    machine: '旧10 18A',
    status: '待排',
    statusTone: 'slate' as Tone,
    score: 54,
    factors: [16, 0, 15, 2, 10],
    grouped: true,
  },
  {
    mold: '20 375 3004-004',
    group: '375',
    groupClass: 'grp-none',
    product: '刷部',
    order: '20 375 3004',
    owe: 200,
    color: '透明红',
    colorHex: '#fca5a5',
    due: '07-20',
    overdue: false,
    urgent: false,
    machine: '旧38 7A',
    status: '待排',
    statusTone: 'slate' as Tone,
    score: 48,
    factors: [14, 0, 0, 8, 6],
  },
]

const scheduleDays = ['07-07', '07-08', '07-09', '07-10', '07-11', '07-12', '07-13']

const schedulePendingCards = [
  {
    mold: 'T01-BN328-00300000-1',
    score: '▲94',
    className: 'urgent',
    color: '白色',
    colorHex: '#f8fafc',
    meta: '欠1,200 · 交07-08 · 同模▣BN328',
    tone: 'amber' as Tone,
  },
  {
    mold: '20 383 3006-002',
    score: '缺85',
    className: 'short',
    color: '白色',
    colorHex: '#f8fafc',
    meta: '欠2,002 · 待补料 · ▣383',
    tone: 'red' as Tone,
  },
  {
    mold: 'PAMT-01M-01',
    score: '72',
    className: '',
    color: '透明',
    colorHex: '#dbeafe',
    meta: '欠23,420 · ▣PAMT 连排',
    tone: 'slate' as Tone,
  },
  {
    mold: 'SMCT 0610-08',
    score: '66',
    className: '',
    color: '浅头色',
    colorHex: '#e7d9b8',
    meta: '欠650 · ▣0610',
    tone: 'slate' as Tone,
  },
  {
    mold: 'MNVN-19M-05',
    score: '54',
    className: '',
    color: '黑色',
    colorHex: '#334155',
    meta: '欠71,930 · ▣MNVN',
    tone: 'slate' as Tone,
  },
  {
    mold: '20 375 3004-004',
    score: '48',
    className: '',
    color: '透明红',
    colorHex: '#fca5a5',
    meta: '欠200 · 单模',
    tone: 'slate' as Tone,
  },
]

type ScheduleLaneBlock =
  | { s: number; l: number; mold: string; sub: string; type: 'running' | 'same-mold' | 'normal' | 'urgent' | 'short' }
  | { gap: number; gl: number; lbl: string }

const scheduleLanes: { mid: string; spec: string; blocks: ScheduleLaneBlock[] }[] = [
  {
    mid: '旧1',
    spec: '50A 400T 高速',
    blocks: [
      { s: 0, l: 0.9, mold: 'SE-20230217-01', sub: '浅头色·欠484', type: 'running' },
      { gap: 0.9, gl: 0.1, lbl: '转模0.03' },
      { s: 1.0, l: 2.6, mold: 'PAMT-01M-01', sub: '透明·连排', type: 'same-mold' },
    ],
  },
  {
    mid: '旧2',
    spec: '32A 320T 高速',
    blocks: [
      { s: 0, l: 3.2, mold: 'PAMT-01M-01', sub: '透明·欠11,470', type: 'running' },
      { s: 3.2, l: 2.8, mold: 'PAMT-01M-01', sub: '透明·连排 欠23,420', type: 'same-mold' },
    ],
  },
  {
    mid: '旧4',
    spec: '24A 260T 高速',
    blocks: [
      { gap: 0, gl: 0.6, lbl: '待补料' },
      { s: 0.6, l: 2.1, mold: 'BBT 93229-09', sub: '红色·欠8,775', type: 'short' },
    ],
  },
  {
    mid: '旧7',
    spec: '18A 200T 高速',
    blocks: [
      { s: 0, l: 1.4, mold: 'T01-BN328-...-2', sub: '白色·特急 欠1,000', type: 'urgent' },
      { gap: 1.4, gl: 0.05, lbl: '同模0' },
      { s: 1.45, l: 1.6, mold: 'T01-BN328-...-1', sub: '白色·连排 欠1,200', type: 'same-mold' },
    ],
  },
  {
    mid: '旧9',
    spec: '18A 200T 高速',
    blocks: [
      { s: 0, l: 4.5, mold: 'BBT 93229-04', sub: '黑色·欠15,335', type: 'running' },
    ],
  },
  {
    mid: '旧12',
    spec: '12A 150T 高速',
    blocks: [
      { s: 0, l: 0.5, mold: 'SMCT 0610-06-4', sub: '浅头色·欠220', type: 'running' },
      { gap: 0.5, gl: 0.08, lbl: '同模0' },
      { s: 0.58, l: 1.2, mold: 'SMCT 0610-08', sub: '浅头色·连排', type: 'same-mold' },
    ],
  },
]

const scheduleTrialStats = [
  { value: '6', label: '本次排入任务', className: 'trial-teal' },
  { value: '4', label: '同模连排（省 4 次换模）', className: 'trial-violet' },
  { value: '0.21天', label: '总换线时间', className: 'trial-amber' },
  { value: '1', label: '预计超期任务', className: 'trial-red' },
]

const scheduleConstraints = [
  { tone: 'ok', title: '模具匹配', text: 'BN328 白色刷（18A）已排旧7（18A 200T），未出现大模上小机' },
  { tone: 'ok', title: '浅色先排', text: '旧1 浅头色 → 透明 顺序正确，无深转浅串色风险' },
  { tone: 'ok', title: '同模连排', text: 'PAMT-01M-01 三单连排、MNVN 两单连排，换线 0' },
  { tone: 'warn', title: '缺料预警', text: '旧4 胶枪身红色料未齐，07-08 前需补料，否则顺延超期' },
  { tone: 'warn', title: '机台数据缺失', text: '部分模具无容模量数据，机台匹配为人工确认（大单未自动排高速机）' },
]

function scoreClass(score: number) {
  return score >= 85 ? 'hi' : score >= 65 ? 'mid' : 'lo'
}

function schedulePercent(value: number) {
  return `${(value / 7) * 100}%`
}

function isScheduleGap(block: ScheduleLaneBlock): block is Extract<ScheduleLaneBlock, { gap: number }> {
  return 'gap' in block
}

watchEffect(() => {
  appStore.setActiveDepartment('production')
  appStore.setActiveFactory(selectedFactoryId.value)
})

function setWorkspaceStep(step: WorkspaceStepId) {
  if (step === activeStep.value) {
    return
  }

  router.push({
    query: {
      ...route.query,
      section: step,
    },
  })
}

function setMachineStatusFilter(filter: MachineStatusFilter) {
  machineStatusFilter.value = filter
}

function openMachineDrawer(machine: MachineCard) {
  if (drawerCloseTimer) {
    clearTimeout(drawerCloseTimer)
    drawerCloseTimer = null
  }

  selectedMachineId.value = machine.machine
  isMachineDrawerOpen.value = false

  void nextTick(() => {
    requestAnimationFrame(() => {
      if (selectedMachineId.value === machine.machine) {
        isMachineDrawerOpen.value = true
      }
    })
  })
}

function closeMachineDrawer() {
  isMachineDrawerOpen.value = false

  if (drawerCloseTimer) {
    clearTimeout(drawerCloseTimer)
  }

  drawerCloseTimer = setTimeout(() => {
    selectedMachineId.value = ''
    drawerCloseTimer = null
  }, drawerAnimationMs)
}

function handleFocusAction(action: FocusAction) {
  if (action === 'risk') {
    setWorkspaceStep('machine-overview')
    setMachineStatusFilter('all')
    return
  }

  if (action === 'attention') {
    setWorkspaceStep('order-pool')
    return
  }

  if (action === 'ready') {
    setWorkspaceStep('machine-overview')
    setMachineStatusFilter('running')
    return
  }

  if (action === 'schedule' || action === 'writeback') {
    setWorkspaceStep('schedule-board')
    return
  }

  setWorkspaceStep('machine-overview')
  setMachineStatusFilter('short')
}

function openDailySchedulePicker() {
  if (isImportingDailySchedule.value) {
    return
  }

  if (!canImportDailySchedule.value) {
    dailyScheduleImportError.value = dailyScheduleImportReadonlyMessage.value
    return
  }

  dailyScheduleFileInput.value?.click()
}

async function handleDailyScheduleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]

  if (!file) {
    return
  }

  if (!canImportDailySchedule.value) {
    dailyScheduleImportError.value = dailyScheduleImportReadonlyMessage.value
    input.value = ''
    return
  }

  dailyScheduleImportError.value = ''
  isImportingDailySchedule.value = true

  try {
    dailyScheduleImportPreview.value = await injectionScheduleApi.importDailySchedule(file, selectedFactoryId.value)
  } catch (error) {
    dailyScheduleImportError.value = getApiErrorMessage(error)
  } finally {
    isImportingDailySchedule.value = false
    input.value = ''
  }
}
</script>

<template>
  <div class="injection-workbench min-h-screen bg-[radial-gradient(circle_at_top_left,rgba(14,165,233,0.12),transparent_34%),linear-gradient(180deg,#f8fafc_0%,#eef4f8_100%)] text-slate-950">
    <header class="topbar">
      <div class="topbar-inner">
        <div class="brand">
          <span class="brand-mark">
            <Layers3 class="size-[18px]" aria-hidden="true" />
          </span>
          啤机排产中枢
        </div>

        <nav class="nav" aria-label="注塑排产步骤">
          <button
            v-for="(step, index) in workspaceSteps"
            :key="step.id"
            type="button"
            class="nav-link"
            :class="{ active: step.id === activeStep }"
            @click="setWorkspaceStep(step.id)"
          >
            <span class="step-no">{{ index + 1 }}</span>
            {{ step.label }}
          </button>
        </nav>

        <label v-if="activeStep === 'machine-overview'" class="search">
          <Search class="size-[15px] shrink-0" aria-hidden="true" />
          <input
            v-model="machineSearchText"
            type="search"
            placeholder="搜单号 / 工模 / 机号 / 颜色"
          >
          <kbd>Ctrl K</kbd>
        </label>

        <div class="topbar-right">
          <span v-if="activeStep === 'machine-overview'" class="pill teal compact">
            <span class="dot"></span>
            数据 {{ currentDataDate }}
          </span>
          <AccountMenu />
        </div>
      </div>
    </header>

    <main class="page">
      <header class="page-head">
        <div>
          <RouterLink
            :to="pageBackTo"
            class="back-link"
          >
            <ArrowLeft class="size-[15px]" aria-hidden="true" />
            {{ pageHeadCopy.back }}
          </RouterLink>
          <div class="page-titlerow">
            <h1 class="page-title">{{ pageHeadCopy.title }}</h1>
            <span
              class="pill"
              :class="activeStep === 'order-pool' ? 'violet' : pageHeadCopy.pillTone"
            >
              <span class="dot"></span>
              {{ activeStep === 'machine-overview' ? activeStepMeta.label : `步骤 ${activeStepIndex} / 4` }}
            </span>
            <span v-if="pageHeadCopy.secondaryPill" class="pill blue">{{ pageHeadCopy.secondaryPill }}</span>
          </div>
          <p class="page-sub">{{ pageHeadCopy.subtitle }}</p>
        </div>

        <div v-if="activeStep === 'machine-overview'" class="metrics-wrap">
          <div class="metrics">
            <article
              v-for="card in overviewCards"
              :key="card.label"
              class="metric"
              :class="card.tone"
            >
              <p class="metric-label">{{ card.label }}</p>
              <p class="metric-value">{{ card.value }}</p>
              <p class="metric-detail">{{ card.detail }}</p>
            </article>
          </div>
        </div>

        <div v-else-if="activeStep === 'order-pool'" class="order-metrics-wrap">
          <div class="metrics">
            <article
              v-for="card in orderHeadMetrics"
              :key="card.label"
              class="metric"
              :class="card.tone"
            >
              <p class="metric-label">{{ card.label }}</p>
              <p class="metric-value">{{ card.value }}</p>
              <p class="metric-detail">{{ card.detail }}</p>
            </article>
          </div>
        </div>

        <div v-else-if="activeStep === 'schedule-board'" class="row gap-2 schedule-head-actions">
          <button type="button" class="btn">
            <Gauge class="size-[15px]" aria-hidden="true" />
            一键智能排期
          </button>
          <button type="button" class="btn primary">
            <CheckCircle2 class="size-[15px]" aria-hidden="true" />
            发布排期
          </button>
        </div>
      </header>

      <p v-if="activeStep === 'machine-overview'" class="eyebrow mb-2 flex items-center gap-2">
        <Gauge class="size-[15px]" aria-hidden="true" />
        今日运营焦点 · 晨会 08:30 冻结版本（数据 {{ currentDataDate }}）· 点击卡片定位
      </p>

      <section v-if="activeStep === 'machine-overview'" class="focus-band">
        <button
          v-for="card in focusCards"
          :key="card.label"
          type="button"
          class="focus-card group"
          :class="[card.tone === 'red' ? 'hot' : '', card.tone === 'amber' ? 'warn' : '']"
          @click="handleFocusAction(card.action)"
        >
          <div class="fc-top">
            <span class="fc-ico" :class="softToneClasses[card.tone]">
              <component :is="card.icon" class="size-4" aria-hidden="true" />
            </span>
            <span class="fc-label">{{ card.label }}</span>
          </div>
          <div class="fc-value">{{ card.value }}</div>
          <div class="fc-sub">{{ card.detail }}</div>
          <span class="fc-arrow">
            <ChevronRight class="size-[15px]" aria-hidden="true" />
          </span>
        </button>
      </section>

      <template v-if="activeStep === 'machine-overview'">
        <section class="section watch-panel">
          <div class="row between wrap gap-3 mb-3">
            <div class="section-title">
              <span class="ico red">
                <ShieldAlert class="size-5" aria-hidden="true" />
              </span>
              <div>
                <h2>超期预警 · 优先跟催</h2>
                <p class="small muted mt-0.5">交期差为负 88 条，按超期天数排序（报告 P0 第 1 优先级）</p>
              </div>
            </div>
            <div class="row gap-2">
              <span class="pill red compact">88 条超期</span>
              <button type="button" class="btn sm">导出跟催清单</button>
            </div>
          </div>

          <div class="overdue-head">
            <span>#</span><span>工模 / 产品</span><span>单号 · 客户</span><span>欠数</span><span>超期</span><span>处理动作</span>
          </div>
          <div
            v-for="(row, index) in priorityWatchRows"
            :key="`watch-${row.order}-${row.mold}`"
            class="overdue-row"
          >
            <span class="rank">{{ index + 1 }}</span>
            <div>
              <p class="mono strong text-xs">{{ row.mold }}</p>
              <p class="xsmall muted mt-1">{{ row.product }}</p>
            </div>
            <div class="small">{{ row.order }}</div>
            <span class="num mono strong">{{ row.owed.toLocaleString() }}</span>
            <span class="days-badge">-{{ row.overdueDays }}天</span>
            <span class="pill compact" :class="row.tone">{{ row.action }}</span>
          </div>
          <div class="row between mt-3">
            <span class="xsmall muted">显示 Top 6 · 其余 82 条可展开 / 按客户分组</span>
            <button type="button" class="btn ghost sm" @click="setWorkspaceStep('order-pool')">
              展开全部 88 条 ▾
            </button>
          </div>
        </section>

        <section class="section">
          <div class="row between wrap gap-4">
            <div class="factory-scope">
              <p class="eyebrow mb-2 flex items-center gap-2">
                <Layers3 class="size-[15px]" aria-hidden="true" />
                当前厂区 · 河源华兴日排版表
              </p>
              <div class="current-factory-card">
                <strong>华兴</strong>
                <span>河源 · 自有产线 · 已解析 2026-06-30</span>
              </div>
            </div>
            <div class="col gap-2 min-w-[260px]">
              <p class="eyebrow">状态筛选</p>
              <div class="filterbar">
                <button
                  v-for="filter in machineFilterOptions"
                  :key="filter.id"
                  type="button"
                  class="chip count"
                  :class="{ active: filter.id === machineStatusFilter }"
                  @click="setMachineStatusFilter(filter.id)"
                >
                  <span v-if="filter.lamp" class="lamp" :class="filter.lamp"></span>
                  {{ filter.label }}
                  <b>{{ filter.count }}</b>
                </button>
              </div>
            </div>
          </div>
        </section>

        <div class="grid-group-head">
          <h3>旧机区</h3>
          <span class="tag">旧1 – 旧39</span>
          <span class="line"></span>
          <span class="small muted">点击任意机台查看详情</span>
        </div>

        <div class="machine-grid">
          <button
            v-for="machine in filteredMachineCards"
            :key="machine.machine"
            type="button"
            class="mbox"
            :class="machine.boxStatus"
            @click="openMachineDrawer(machine)"
          >
            <div class="mbox-top">
              <div class="mbox-id">
                <b>{{ machine.machine }}</b>
                <span class="mbox-spec">{{ machine.tonnage }} · {{ machine.processRange }} · {{ machine.robot }}</span>
              </div>
              <span class="status-lamp">
                <span class="lamp" :class="machine.lampClass"></span>
                {{ machine.statusLabel }}
                <span
                  v-if="machine.flag"
                  class="pill compact"
                  :class="machine.flag === '缺料' ? 'amber' : machine.flag === '停机' ? 'red' : 'slate'"
                >
                  {{ machine.flag }}
                </span>
              </span>
            </div>

            <div class="mbox-mold">
              <div class="name">{{ machine.mold }}</div>
              <div class="meta">
                <span class="swatch" :style="{ background: machine.colorSwatch }"></span>
                {{ machine.material }} · {{ machine.workshop }}
              </div>
            </div>

            <div class="mbox-owe">
              <span class="n">欠 <b>{{ machine.owedQuantity.toLocaleString() }}</b></span>
              <div class="bar" :class="[machine.boxStatus === 'short' ? 'amber' : '', machine.boxStatus === 'down' ? 'red' : '', machine.utilization >= 90 ? 'green' : '']">
                  <span
                    :style="{ width: `${Math.min(machine.utilization, 100)}%` }"
                  />
              </div>
              <span class="pct">{{ machine.utilization }}%</span>
            </div>

            <div class="mbox-foot">
              <span class="mbox-eta">预计完成 <b>{{ machine.dueText }}</b></span>
            </div>
            <div class="mbox-next">
              <span class="lbl">下一模 ▸</span>
              <span class="nm">{{ machine.nextMold }}</span>
            </div>
          </button>
        </div>

        <p
          v-if="filteredMachineCards.length === 0"
          class="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-10 text-center text-sm text-slate-500"
        >
          无匹配机台 · 试试清空筛选或搜索
        </p>
      </template>

      <template v-else-if="activeStep === 'excel-import'">
        <div class="import-layout">
          <div class="col gap-4 import-main">
            <section class="section">
              <div class="section-title import-section-title">
                <span class="ico">
                  <UploadCloud class="size-5" aria-hidden="true" />
                </span>
                <div>
                  <h2>上传日排版表</h2>
                  <p class="small muted mt-0.5">支持 .xlsx / .xls · 单文件 ≤ 20MB</p>
                </div>
              </div>

              <input
                ref="dailyScheduleFileInput"
                class="sr-only"
                type="file"
                accept=".xlsx,.xlsm"
                :disabled="!canImportDailySchedule"
                @change="handleDailyScheduleFileChange"
              />

              <div
                class="dropzone"
                :class="{ 'is-disabled': !canImportDailySchedule }"
                role="button"
                :tabindex="canImportDailySchedule ? 0 : -1"
                :aria-disabled="!canImportDailySchedule"
                @click="openDailySchedulePicker"
                @keydown.enter.prevent="openDailySchedulePicker"
                @keydown.space.prevent="openDailySchedulePicker"
              >
                <div class="cloud">
                  <UploadCloud class="size-8" aria-hidden="true" />
                </div>
                <h3>{{ isImportingDailySchedule ? '正在解析日排版表...' : '拖拽 Excel 文件到此处，或点击选择' }}</h3>
                <p>华兴 / 华康A / 华康B / 华登 通用同一模板 · 后端落库生成导入批次</p>
              </div>

              <div class="file-row import-uploaded-file">
                <div class="file-ico">XLSX</div>
                <div class="grow">
                  <div class="row between">
                    <span class="strong small">{{ importUploadedFileName }}</span>
                    <span class="small muted">{{ importUploadedFileStatus }}</span>
                  </div>
                  <div class="progress-line"><span :style="{ width: isImportingDailySchedule ? '64%' : '100%' }" /></div>
                  <div class="xsmall muted mt-2">{{ importUploadedFileDetail }}</div>
                </div>
                <span class="pill compact" :class="dailyScheduleImportError ? 'red' : isImportingDailySchedule ? 'amber' : 'green'">
                  <span class="dot"></span>{{ dailyScheduleImportError ? '解析失败' : isImportingDailySchedule ? '解析中' : '解析完成' }}
                </span>
              </div>

              <div v-if="dailyScheduleImportError" class="hint mt-4 error-hint">
                <span class="hint-ico">
                  <AlertTriangle class="size-[15px]" aria-hidden="true" />
                </span>
                <span>{{ dailyScheduleImportError }}</span>
              </div>

              <div v-if="!canImportDailySchedule" class="hint mt-4 readonly-hint">
                <span class="hint-ico">
                  <ShieldAlert class="size-[15px]" aria-hidden="true" />
                </span>
                <span>{{ dailyScheduleImportReadonlyMessage }}</span>
              </div>

              <div class="hint mt-4">
                <span class="hint-ico">
                  <Gauge class="size-[15px]" aria-hidden="true" />
                </span>
                <span>系统按 <b>B/G/H/I 机台行</b> 与 <b>G/H/I/J + K:O 任务行</b> 识别日排版表；1900 相对时间与无计划行先进入待排池，不计入真实日期排期。</span>
              </div>
            </section>

            <section class="section">
              <div class="section-title import-section-title">
                <span class="ico green">
                  <CheckCircle2 class="size-5" aria-hidden="true" />
                </span>
                <div>
                  <h2>识别结果</h2>
                  <p class="small muted mt-0.5">解析后自动写入机台总览盘与订单池</p>
                </div>
              </div>

              <div class="stat-grid">
                <article
                  v-for="stat in importRecognitionStats"
                  :key="stat.label"
                  class="stat"
                >
                  <div class="n">{{ stat.value }}</div>
                  <div class="l">{{ stat.label }}</div>
                </article>
              </div>

              <div class="divider"></div>
              <div class="row between small">
                <span class="muted">总欠数（∑ 欠数列）</span><span class="strong mono">{{ formatImportNumber(dailyScheduleImportPreview?.summary.total_shortage_qty ?? 1860805) }}</span>
              </div>
              <div class="row between small mt-2">
                <span class="muted">超期任务（交期差 &lt; 0）</span><span class="pill red compact">{{ formatImportNumber(dailyScheduleImportPreview?.summary.overdue_count ?? 88) }} 条</span>
              </div>
              <div class="row between small mt-2">
                <span class="muted">外链公式风险</span><span class="pill amber compact">{{ formatImportNumber(dailyScheduleImportPreview?.summary.external_formula_risk_count ?? 0) }} 条</span>
              </div>
              <div class="row gap-2 mt-4">
                <button type="button" class="btn primary grow justify-center" @click="setWorkspaceStep('order-pool')">
                  确认并进入订单池
                  <ChevronRight class="size-[15px]" aria-hidden="true" />
                </button>
                <button type="button" class="btn" :disabled="isImportingDailySchedule || !canImportDailySchedule" @click="openDailySchedulePicker">重新上传</button>
              </div>
            </section>
          </div>

          <div class="col gap-4 import-side">
            <section class="section">
              <div class="section-title import-section-title">
                <span class="ico blue">
                  <Gauge class="size-5" aria-hidden="true" />
                </span>
                <div><h2>解析进度</h2></div>
              </div>

              <div class="steps">
                <div
                  v-for="(step, index) in importParsingSteps"
                  :key="step.title"
                  class="step"
                >
                  <div class="marker">
                    <span class="bullet">✓</span>
                    <span v-if="index < importParsingSteps.length - 1" class="line"></span>
                  </div>
                  <div class="body">
                    <div class="t">{{ step.title }}</div>
                    <div class="d">{{ step.detail }}</div>
                  </div>
                </div>
              </div>
            </section>

            <section class="section">
              <div class="section-title import-section-title compact-title">
                <span class="ico violet">
                  <BarChart3 class="size-5" aria-hidden="true" />
                </span>
                <div>
                  <h2>字段映射预览</h2>
                  <p class="small muted mt-0.5">Excel 列 → 系统字段</p>
                </div>
              </div>

              <div class="mt-3">
                <div
                  v-for="mapping in importFieldMappings"
                  :key="`${mapping[0]}-${mapping[2]}`"
                  class="maprow"
                >
                  <span class="col-tag">{{ mapping[0] }}</span>
                  <span class="field-name">{{ mapping[1] }}</span>
                  <span class="arrow">→</span>
                  <span class="field-name">{{ mapping[2] }}</span>
                </div>
              </div>
            </section>

            <section class="section">
              <div class="section-title import-section-title">
                <span class="ico amber">
                  <AlertTriangle class="size-5" aria-hidden="true" />
                </span>
                <div>
                  <h2>数据质量校验</h2>
                  <p class="small muted mt-0.5">排产前置检查 · 不阻断导入</p>
                </div>
              </div>

              <div
                v-for="issue in importQualityIssues"
                :key="`${issue.tone}-${issue.count}-${issue.text}`"
                class="issue"
                :class="issue.tone"
              >
                <AlertTriangle class="issue-icon" aria-hidden="true" />
                <span><b>{{ issue.count }}</b> {{ issue.text }}</span>
              </div>

              <div v-if="importTopIssues.length" class="issue-detail-list">
                <div
                  v-for="issue in importTopIssues"
                  :key="issue.id"
                  class="issue-detail"
                  :class="issue.severity"
                >
                  <span class="mono">#{{ issue.source_row || '-' }}</span>
                  <span>{{ issue.message }}</span>
                </div>
              </div>
            </section>
          </div>
        </div>
      </template>

      <template v-else-if="activeStep === 'order-pool'">
        <div class="pool-layout">
          <div class="col gap-4">
            <section class="section">
              <div class="section-title" style="margin-bottom:12px">
                <span class="ico violet">
                  <ShieldAlert class="size-5" aria-hidden="true" />
                </span>
                <div>
                  <h2>排期六原则</h2>
                  <p class="small muted mt-0.5">算分权重依据</p>
                </div>
              </div>
              <div class="principle">
                <span class="badge" style="background:var(--red-solid)">1</span>
                <div><div class="t">交期优先级</div><div class="d">按订单期限确立优先级，交期越近分越高</div></div>
              </div>
              <div class="principle">
                <span class="badge" style="background:var(--red-solid)">2</span>
                <div><div class="t">急单 / 交期紧急</div><div class="d">▲特急、超期任务置顶优先安排</div></div>
              </div>
              <div class="principle">
                <span class="badge" style="background:var(--violet-solid)">3</span>
                <div><div class="t">同款同模连排</div><div class="d">前缀相同（-01/-06/-08...同套模）尽量一起排，减少换模</div></div>
              </div>
              <div class="principle">
                <span class="badge" style="background:var(--blue-solid)">4</span>
                <div><div class="t">模具尺寸匹配机台</div><div class="d">大模不上小机、小模不占大机，大单尽量排高速机</div></div>
              </div>
              <div class="principle">
                <span class="badge" style="background:var(--teal-solid)">5</span>
                <div><div class="t">浅色先排深色后排</div><div class="d">同机台按颜色由浅到深，防止串色</div></div>
              </div>
              <div class="principle">
                <span class="badge" style="background:var(--amber-solid)">6</span>
                <div><div class="t">缺料补料优先</div><div class="d">在啤机台缺料的，安排当天补料</div></div>
              </div>
            </section>

            <section class="section">
              <p class="eyebrow" style="margin-bottom:10px">分数构成</p>
              <div class="legend">
                <span><i style="background:var(--red-solid)"></i>交期紧迫</span>
                <span><i style="background:var(--amber-solid)"></i>急单加权</span>
                <span><i style="background:var(--violet-solid)"></i>同模连排</span>
                <span><i style="background:var(--teal-solid)"></i>颜色顺序</span>
                <span><i style="background:var(--blue-solid)"></i>机台匹配</span>
              </div>
              <div class="hint mt-3">
                <span class="hint-ico">
                  <Gauge class="size-[15px]" aria-hidden="true" />
                </span>
                <span>优先级分 = 交期紧迫 ×0.4 + 急单 ×0.25 + 同模连排 ×0.15 + 颜色顺序 ×0.1 + 机台匹配 ×0.1，分越高越靠前。</span>
              </div>
            </section>
          </div>

          <section class="section">
            <div class="row between wrap gap-3 mb-4">
              <div class="section-title">
                <span class="ico">
                  <Boxes class="size-5" aria-hidden="true" />
                </span>
                <div>
                  <h2>订单池（按优先级排序）</h2>
                  <p class="small muted mt-0.5">同模自动分组高亮 · 点击可展开明细</p>
                </div>
              </div>
              <div class="row gap-2">
                <button type="button" class="btn sm">按交期</button>
                <button type="button" class="btn sm primary">按优先级分</button>
                <button type="button" class="btn sm">按同模分组</button>
              </div>
            </div>

            <div class="table-wrap">
              <table class="grid">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>优先级</th>
                    <th>分数构成</th>
                    <th>工模编号</th>
                    <th>同模组</th>
                    <th>产品 / 单号</th>
                    <th class="num">欠数</th>
                    <th>颜色</th>
                    <th>交期</th>
                    <th>建议机台</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(row, index) in staticOrderPoolRows"
                    :key="`${row.order}-${row.mold}-${index}`"
                    :class="{ grouprow: row.grouped }"
                  >
                    <td class="mono muted">{{ index + 1 }}</td>
                    <td>
                      <span class="score" :class="scoreClass(row.score)">
                        {{ row.score }}
                      </span>
                    </td>
                    <td>
                      <div class="factorbar">
                        <span
                          v-for="(factor, factorIndex) in row.factors"
                          :key="`${row.mold}-${factorIndex}`"
                          class="seg"
                          :style="{ width: `${factor * 0.9}px`, background: priorityFactorColors[factorIndex] }"
                        ></span>
                      </div>
                    </td>
                    <td><span class="mono strong">{{ row.mold }}</span></td>
                    <td>
                      <span class="grp-tag" :class="row.groupClass">
                        {{ row.group === '—' ? '单模' : `▣ ${row.group}` }}
                      </span>
                    </td>
                    <td>
                      <div class="small">{{ row.product }}</div>
                      <div class="mono xsmall muted mt-1">{{ row.order }}</div>
                    </td>
                    <td class="num mono strong">{{ row.owe.toLocaleString() }}</td>
                    <td>
                      <span class="swatch" :style="{ background: row.colorHex }"></span>
                      <span class="small">{{ row.color }}</span>
                    </td>
                    <td>
                      <span class="small mono">{{ row.due }}</span>
                      <div v-if="row.overdue" class="xsmall text-red-700">已超期</div>
                    </td>
                    <td>
                      <span class="tag mono">{{ row.machine }}</span>
                    </td>
                    <td>
                      <span class="pill compact" :class="row.statusTone">
                        {{ row.urgent ? '▲' : '' }}{{ row.status }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="row between mt-4">
              <span class="small muted">显示前 15 条 · 共 118 条订单任务</span>
              <button type="button" class="btn primary" @click="setWorkspaceStep('schedule-board')">
                进入排期编排
                <ChevronRight class="size-[15px]" aria-hidden="true" />
              </button>
            </div>
          </section>
        </div>
      </template>

      <template v-else>
        <div class="sched-layout">
          <section class="section pending-panel">
            <div class="row between" style="margin-bottom:12px">
              <div class="section-title">
                <span class="ico slate">
                  <Boxes class="size-5" aria-hidden="true" />
                </span>
                <div><h2 style="font-size:16px">待排队列</h2></div>
              </div>
              <span class="pill slate compact">14</span>
            </div>
            <p class="xsmall muted" style="margin:0 0 10px">按优先级分排序 · 拖入右侧泳道</p>

            <div
              v-for="card in schedulePendingCards"
              :key="card.mold"
              class="pending-card"
              :class="card.className"
            >
              <div class="row1">
                <span class="mold">{{ card.mold }}</span>
                <span class="pill compact" :class="card.tone">{{ card.score }}</span>
              </div>
              <div class="meta">
                <span class="swatch" :style="{ background: card.colorHex }"></span>
                {{ card.color }} · {{ card.meta }}
              </div>
            </div>

            <div class="hint mt-3">
              <span class="hint-ico">
                <Gauge class="size-[15px]" aria-hidden="true" />
              </span>
              <span>同模（▣ 相同）优先拖到已排该模的机台，可省一次换模。</span>
            </div>
          </section>

          <div class="col gap-4">
            <section class="section">
              <div class="row between wrap gap-3" style="margin-bottom:12px">
                <div class="section-title">
                  <span class="ico">
                    <CalendarDays class="size-5" aria-hidden="true" />
                  </span>
                  <div>
                    <h2>机台泳道 · 7 日排期</h2>
                    <p class="small muted mt-0.5">2026-07-07 起 · 块宽 = 生产周期</p>
                  </div>
                </div>
                <div class="legend2">
                  <span><i class="block running legend-block"></i>在啤</span>
                  <span><i class="block same-mold legend-block"></i>同模连排</span>
                  <span><i class="block urgent legend-block"></i>特急</span>
                  <span><i class="block short legend-block"></i>缺料</span>
                  <span><i class="legend-gap"></i>换模/色</span>
                </div>
              </div>

              <div class="gantt">
                <div class="gantt-inner">
                  <div class="timeaxis">
                    <div class="corner">机台</div>
                    <div v-for="day in scheduleDays" :key="day" class="day">
                      <b>{{ day }}</b>
                      排期
                    </div>
                  </div>

                  <div
                    v-for="lane in scheduleLanes"
                    :key="lane.mid"
                    class="lane"
                  >
                    <div class="lane-head">
                      <div class="mid">{{ lane.mid }}</div>
                      <div class="spec">{{ lane.spec }}</div>
                    </div>
                    <div class="lane-track">
                      <div class="grid-lines">
                        <span v-for="index in 7" :key="`${lane.mid}-line-${index}`"></span>
                      </div>
                      <template
                        v-for="(block, index) in lane.blocks"
                        :key="`${lane.mid}-block-${index}`"
                      >
                        <div
                          v-if="isScheduleGap(block)"
                          class="gap"
                          :style="{ left: schedulePercent(block.gap), width: schedulePercent(block.gl) }"
                        >
                          <span class="gap-lbl">{{ block.lbl }}</span>
                        </div>
                        <div
                          v-else
                          class="block"
                          :class="block.type"
                          :style="{ left: schedulePercent(block.s), width: schedulePercent(block.l) }"
                        >
                          <span class="bm">{{ block.mold }}</span>
                          <span class="bs">{{ block.sub }}</span>
                        </div>
                      </template>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            <section class="section">
              <div class="section-title" style="margin-bottom:14px">
                <span class="ico blue">
                  <BarChart3 class="size-5" aria-hidden="true" />
                </span>
                <div>
                  <h2>本次排期试算结果</h2>
                  <p class="small muted mt-0.5">发布前自动核算交期风险</p>
                </div>
              </div>
              <div class="trial-grid">
                <div
                  v-for="trial in scheduleTrialStats"
                  :key="trial.label"
                  class="trial"
                  :class="trial.className"
                >
                  <div class="n">{{ trial.value }}</div>
                  <div class="l">{{ trial.label }}</div>
                </div>
              </div>
              <div class="divider"></div>
              <div class="row between small"><span class="muted">最早计划完成期</span><span class="strong mono">2026-07-08 02:10</span></div>
              <div class="row between small mt-2"><span class="muted">最晚计划完成期</span><span class="strong mono">2026-07-13 18:40</span></div>
              <div class="row between small mt-2"><span class="muted">统一入库缓冲</span><span class="strong">完工 +3 天</span></div>
            </section>

            <section class="section">
              <div class="section-title" style="margin-bottom:14px">
                <span class="ico amber">
                  <ShieldAlert class="size-5" aria-hidden="true" />
                </span>
                <div>
                  <h2>排期约束校验</h2>
                  <p class="small muted mt-0.5">六原则实时检查</p>
                </div>
              </div>
              <div
                v-for="constraint in scheduleConstraints"
                :key="constraint.title"
                class="constraint"
                :class="constraint.tone"
              >
                <CheckCircle2
                  v-if="constraint.tone === 'ok'"
                  class="size-[15px] shrink-0"
                  aria-hidden="true"
                />
                <AlertTriangle
                  v-else
                  class="size-[15px] shrink-0"
                  aria-hidden="true"
                />
                <span><b>{{ constraint.title }}</b>：{{ constraint.text }}</span>
              </div>
            </section>
          </div>
        </div>
      </template>

      <div
        v-if="selectedMachine"
        class="drawer-mask"
        :class="{ open: isMachineDrawerOpen }"
        aria-hidden="true"
        @click="closeMachineDrawer"
      />
      <aside
        v-if="selectedMachine"
        class="drawer"
        :class="{ open: isMachineDrawerOpen }"
        aria-label="机台详情"
      >
        <div class="drawer-head">
          <div>
            <div class="row gap-3">
              <span class="strong drawer-machine-title">{{ selectedMachine.machine }}</span>
              <span class="pill" :class="selectedMachine.statusTone">
                <span class="dot"></span>
                {{ selectedMachine.statusLabel }}
              </span>
            </div>
            <p class="page-sub drawer-spec">
              {{ selectedMachine.tonnage }} · {{ selectedMachine.processRange }} · {{ selectedMachine.robot }} · 全自动
            </p>
          </div>
          <button
            type="button"
            class="close-x"
            aria-label="关闭机台详情"
            @click="closeMachineDrawer"
          >
            <X class="size-4" aria-hidden="true" />
          </button>
        </div>

        <div class="drawer-body">
          <p class="subhead mt-0">当前任务</p>
          <div class="card card-pad drawer-task-card">
            <div class="row between">
              <div>
                <div class="mono strong drawer-mold">{{ selectedMachine.mold }}</div>
                <div class="small muted mt-2">{{ selectedMachine.material }} · {{ selectedMachine.workshop }}</div>
              </div>
              <span
                v-if="selectedMachine.flag"
                class="pill compact"
                :class="selectedMachine.flag === '缺料' ? 'amber' : selectedMachine.flag === '停机' ? 'red' : 'slate'"
              >
                {{ selectedMachine.flag }}
              </span>
            </div>

            <div class="mt-3 kv">
              <div class="item">
                <div class="k">订单数</div>
                <div class="v">{{ (selectedMachine.owedQuantity + 1716).toLocaleString() }}</div>
              </div>
              <div class="item">
                <div class="k">已啤数</div>
                <div class="v">1,716</div>
              </div>
              <div class="item">
                <div class="k">欠数</div>
                <div class="v danger">{{ selectedMachine.owedQuantity.toLocaleString() }}</div>
              </div>
              <div class="item">
                <div class="k">计划目标/天</div>
                <div class="v">2,500</div>
              </div>
              <div class="item">
                <div class="k"><span class="swatch" :style="{ background: selectedMachine.colorSwatch }"></span>颜色</div>
                <div class="v small-v">{{ selectedMachine.colorPolicy }}</div>
              </div>
              <div class="item">
                <div class="k">用料</div>
                <div class="v small-v">{{ selectedMachine.material }}</div>
              </div>
              <div class="item wide">
                <div class="k">进度</div>
                <div class="mt-2 mbox-owe">
                  <div class="bar" :class="[selectedMachine.boxStatus === 'short' ? 'amber' : '', selectedMachine.boxStatus === 'down' ? 'red' : '']">
                    <span :style="{ width: `${Math.min(selectedMachine.utilization, 100)}%` }"></span>
                  </div>
                  <span class="pct">{{ selectedMachine.utilization }}%</span>
                </div>
              </div>
            </div>

            <div class="mt-3 row between small">
              <span class="muted">计划完成期</span><span class="strong">2026-07-{{ selectedMachine.dueText.split('-')[1] }} 14:20</span>
            </div>
            <div class="row between small mt-2">
              <span class="muted">预计入库期（完工+3天）</span><span class="strong">2026-07-11</span>
            </div>
            <div class="row between small mt-2">
              <span class="muted">交货完成期</span><span class="strong">2026-07-16</span>
            </div>
            <div class="row between small mt-2">
              <span class="muted">交期差</span><span class="pill green compact">+5 天 · 安全</span>
            </div>
          </div>

          <p class="subhead">排队队列 <span class="tag normal-tag">拖拽调整顺序</span></p>
          <div class="queue-item now">
            <span class="drag">⋮⋮</span><span class="seq">▶</span>
            <div class="grow">
              <div class="mono small strong">{{ selectedMachine.mold }}</div>
              <div class="xsmall muted">{{ selectedMachine.material }} · 欠 {{ selectedMachine.owedQuantity.toLocaleString() }} · 进行中</div>
            </div>
          </div>
          <div class="changeover">
            换模/换色间隙 · 预计 0.5 班 · 按六原则自动校验
          </div>
          <div
            v-for="(order, index) in selectedMachineOrders"
            :key="`${order.orderNo}-${order.moldCode}`"
            class="queue-item"
          >
            <span class="drag">⋮⋮</span><span class="seq">{{ index + 1 }}</span>
            <div class="grow">
              <div class="mono small strong">{{ order.moldCode }}</div>
              <div class="xsmall muted">{{ order.color }} · 欠 {{ (order.shortageQuantity ?? order.quantity).toLocaleString() }} · {{ order.issue }}</div>
            </div>
          </div>
          <p v-if="selectedMachineOrders.length === 0" class="empty-drawer-note">
            暂无直接命中的候选订单，等待排期草稿补充。
          </p>

          <p class="subhead">机台约束</p>
          <div class="kv">
            <div class="item">
              <div class="k">工艺范围</div>
              <div class="v">{{ selectedMachine.processRange }}</div>
            </div>
            <div class="item">
              <div class="k">颜色策略</div>
              <div class="v">{{ selectedMachine.colorPolicy }}</div>
            </div>
            <div class="item wide">
              <div class="k">保养 / 限制</div>
              <div class="v">{{ selectedMachine.maintenance }}</div>
            </div>
          </div>

          <div v-if="selectedMachineColorRisk" class="mt-3 color-risk-line">
            <span
              v-for="color in selectedMachineColorRisk.route"
              :key="color"
              class="tag"
            >
              {{ color }}
            </span>
            <span class="pill compact" :class="selectedMachineColorRisk.tone">{{ selectedMachineColorRisk.risk }}</span>
          </div>
        </div>
      </aside>
    </main>
  </div>
</template>

<style scoped>
.injection-workbench {
  --primary: oklch(0.45 0.09 182);
  --primary-strong: oklch(0.38 0.1 182);
  --primary-foreground: oklch(0.985 0 0);
  --ring: oklch(0.58 0.1 182);
  --text-950: #020617;
  --text-900: #0f172a;
  --text-700: #334155;
  --text-600: #475569;
  --text-500: #64748b;
  --text-400: #94a3b8;
  --border: #e2e8f0;
  --border-strong: #cbd5e1;
  --surface: #fff;
  --surface-muted: #f1f5f9;
  --surface-sunken: #f8fafc;
  --teal-bg: #f0fdfa;
  --teal-bd: #99f6e4;
  --teal-fg: #0f766e;
  --teal-solid: #14b8a6;
  --blue-bg: #eff6ff;
  --blue-bd: #bfdbfe;
  --blue-fg: #1e40af;
  --blue-solid: #3b82f6;
  --amber-bg: #fffbeb;
  --amber-bd: #fde68a;
  --amber-fg: #b45309;
  --amber-solid: #f59e0b;
  --red-bg: #fef2f2;
  --red-bd: #fecaca;
  --red-fg: #b91c1c;
  --red-solid: #ef4444;
  --slate-bg: #f8fafc;
  --slate-bd: #e2e8f0;
  --slate-fg: #475569;
  --slate-solid: #94a3b8;
  --green-bg: #ecfdf5;
  --green-bd: #a7f3d0;
  --green-fg: #047857;
  --green-solid: #10b981;
  --violet-bg: #f5f3ff;
  --violet-bd: #ddd6fe;
  --violet-fg: #6d28d9;
  --violet-solid: #8b5cf6;
  --radius: 0.625rem;
  --radius-lg: 0.75rem;
  --radius-xl: 1rem;
  --shadow-card: 0 16px 38px rgba(15, 23, 42, 0.06);
  --shadow-soft: 0 14px 35px rgba(15, 23, 42, 0.05);
  --shadow-pop: 0 24px 60px rgba(15, 23, 42, 0.18);
}

.page {
  max-width: 1680px;
  margin: 0 auto;
  padding: 20px 24px 48px;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 40;
  border-bottom: 1px solid var(--border);
  background: rgba(248, 250, 252, 0.82);
  backdrop-filter: saturate(1.4) blur(8px);
}

.topbar-inner {
  display: flex;
  max-width: 1680px;
  margin: 0 auto;
  align-items: center;
  gap: 18px;
  padding: 10px 24px;
}

.brand {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 10px;
  color: var(--text-950);
  font-weight: 700;
  letter-spacing: 0;
  white-space: nowrap;
}

.brand-mark {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 10px;
  background: var(--primary);
  color: #fff;
  box-shadow: 0 6px 16px rgba(13, 118, 110, 0.35);
}

.nav {
  display: flex;
  min-width: 0;
  flex: 1 1 auto;
  gap: 4px;
  overflow-x: auto;
  padding-bottom: 2px;
}

.nav::-webkit-scrollbar {
  height: 4px;
}

.nav::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: var(--border-strong);
}

.nav-link {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  border-radius: 999px;
  padding: 7px 14px;
  color: var(--text-500);
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  transition: background 0.15s ease, color 0.15s ease;
}

.nav-link:hover {
  background: var(--surface-muted);
  color: var(--text-950);
}

.nav-link.active {
  background: var(--primary);
  color: #fff;
}

.step-no {
  display: inline-grid;
  width: 18px;
  height: 18px;
  margin-right: 6px;
  place-items: center;
  border-radius: 999px;
  background: var(--surface-muted);
  color: var(--text-500);
  font-size: 11px;
  font-weight: 800;
}

.nav-link.active .step-no {
  background: rgba(255, 255, 255, 0.22);
  color: #fff;
}

.search {
  display: flex;
  width: min(312px, 24vw);
  min-width: 240px;
  flex: 0 1 auto;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: #fff;
  padding: 6px 12px;
  color: var(--text-400);
}

.search:focus-within {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(20, 184, 166, 0.12);
}

.search input {
  width: 100%;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--text-900);
  font-size: 13px;
  outline: none;
}

.search input::placeholder {
  color: var(--text-400);
}

.search kbd {
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 5px;
  color: var(--text-400);
  font-size: 10px;
  line-height: 1.2;
}

.topbar-right {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 12px;
}

.page-head {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 20px;
}

.back-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-500);
  font-size: 13px;
  font-weight: 600;
}

.back-link:hover {
  color: var(--text-950);
}

.page-titlerow {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}

.page-title {
  margin: 0;
  color: var(--text-950);
  font-size: 30px;
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1.18;
}

.page-sub {
  margin: 8px 0 0;
  color: var(--text-600);
  font-size: 13px;
  line-height: 1.7;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid transparent;
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
  white-space: nowrap;
}

.pill .dot {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: currentColor;
}

.pill.teal {
  border-color: var(--teal-bd);
  background: var(--teal-bg);
  color: var(--teal-fg);
}

.pill.blue {
  border-color: var(--blue-bd);
  background: var(--blue-bg);
  color: var(--blue-fg);
}

.pill.amber {
  border-color: var(--amber-bd);
  background: var(--amber-bg);
  color: var(--amber-fg);
}

.pill.red {
  border-color: var(--red-bd);
  background: var(--red-bg);
  color: var(--red-fg);
}

.pill.slate {
  border-color: var(--slate-bd);
  background: var(--slate-bg);
  color: var(--slate-fg);
}

.pill.green {
  border-color: var(--green-bd);
  background: var(--green-bg);
  color: var(--green-fg);
}

.pill.violet {
  border-color: var(--violet-bd);
  background: var(--violet-bg);
  color: var(--violet-fg);
}

.pill.compact {
  padding: 2px 8px;
  font-size: 11px;
}

.metrics-wrap {
  width: 100%;
  max-width: 860px;
}

.order-metrics-wrap {
  width: 100%;
  max-width: 520px;
}

.schedule-head-actions {
  width: 100%;
  justify-content: flex-start;
}

.metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.metric {
  min-height: 92px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #fff;
  padding: 14px 16px;
}

.metric.teal {
  border-color: var(--teal-bd);
  background: var(--teal-bg);
}

.metric.blue {
  border-color: var(--blue-bd);
  background: var(--blue-bg);
}

.metric.amber {
  border-color: var(--amber-bd);
  background: var(--amber-bg);
}

.metric.red {
  border-color: var(--red-bd);
  background: var(--red-bg);
}

.metric.green {
  border-color: var(--green-bd);
  background: var(--green-bg);
}

.metric-label {
  color: var(--text-700);
  font-size: 12px;
  font-weight: 500;
  opacity: 0.82;
}

.metric-value {
  margin-top: 4px;
  color: var(--text-950);
  font-size: 24px;
  font-weight: 700;
  line-height: 1.1;
}

.metric-detail {
  margin-top: 4px;
  color: var(--text-600);
  font-size: 12px;
  line-height: 1.5;
  opacity: 0.78;
}

.section {
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  background: var(--surface);
  padding: 20px;
  box-shadow: var(--shadow-soft);
}

.section-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-title h2 {
  margin: 0;
  color: var(--text-950);
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0;
}

.ico {
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  border-radius: 11px;
  background: var(--teal-bg);
  color: var(--teal-fg);
  flex-shrink: 0;
}

.ico.red {
  background: var(--red-bg);
  color: var(--red-fg);
}

.ico.blue {
  background: var(--blue-bg);
  color: var(--blue-fg);
}

.ico.green {
  background: var(--green-bg);
  color: var(--green-fg);
}

.ico.amber {
  background: var(--amber-bg);
  color: var(--amber-fg);
}

.ico.violet {
  background: var(--violet-bg);
  color: var(--violet-fg);
}

.ico.slate {
  background: var(--slate-bg);
  color: var(--slate-fg);
}

.eyebrow {
  color: var(--text-500);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.22em;
  text-transform: uppercase;
}

.focus-band {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.focus-card {
  position: relative;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #fff;
  padding: 13px 14px;
  text-align: left;
  transition: box-shadow 0.15s ease, transform 0.15s ease;
}

.focus-card:hover {
  box-shadow: var(--shadow-card);
  transform: translateY(-2px);
}

.focus-card.hot {
  border-color: var(--red-bd);
  background: linear-gradient(180deg, var(--red-bg), #fff);
}

.focus-card.warn {
  border-color: var(--amber-bd);
  background: linear-gradient(180deg, var(--amber-bg), #fff);
}

.fc-top {
  display: flex;
  align-items: center;
  gap: 7px;
}

.fc-ico {
  display: grid;
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  place-items: center;
  border-radius: 7px;
}

.fc-label {
  color: var(--text-600);
  font-size: 11px;
  font-weight: 600;
}

.fc-value {
  margin-top: 8px;
  color: var(--text-950);
  font-size: 26px;
  font-variant-numeric: tabular-nums;
  font-weight: 800;
  line-height: 1;
}

.fc-sub {
  margin-top: 4px;
  color: var(--text-500);
  font-size: 11px;
}

.fc-arrow {
  position: absolute;
  top: 13px;
  right: 12px;
  color: var(--text-400);
  opacity: 0;
  transition: opacity 0.15s ease;
}

.focus-card:hover .fc-arrow {
  opacity: 1;
}

.row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.row.between {
  justify-content: space-between;
}

.row.wrap {
  flex-wrap: wrap;
}

.col {
  display: flex;
  flex-direction: column;
}

.muted {
  color: var(--text-500);
}

.small {
  font-size: 12px;
}

.xsmall {
  font-size: 11px;
}

.strong {
  color: var(--text-950);
  font-weight: 700;
}

.mono {
  font-family: "Cascadia Code", "Consolas", monospace;
  font-variant-numeric: tabular-nums;
}

.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.tag {
  display: inline-block;
  border-radius: 999px;
  background: var(--surface-muted);
  color: var(--text-600);
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #fff;
  color: var(--text-700);
  padding: 9px 16px;
  font-size: 13px;
  font-weight: 600;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.btn:hover {
  border-color: var(--border-strong);
  background: var(--surface-sunken);
}

.btn.primary {
  border-color: var(--primary);
  background: var(--primary);
  color: #fff;
}

.btn.primary:hover {
  border-color: var(--primary-strong);
  background: var(--primary-strong);
}

.btn.ghost {
  border-color: transparent;
  background: transparent;
  color: var(--text-600);
}

.btn.sm {
  padding: 6px 12px;
  font-size: 12px;
}

.grow {
  flex: 1;
}

.divider {
  height: 1px;
  margin: 14px 0;
  background: var(--border);
}

.watch-panel {
  border-color: var(--red-bd);
  background: linear-gradient(180deg, #fff5f5, #fff);
}

.overdue-head,
.overdue-row {
  display: grid;
  grid-template-columns: 30px 1.4fr 1fr 90px 100px 1fr;
  gap: 10px;
  align-items: center;
}

.overdue-head {
  border-radius: 8px 8px 0 0;
  background: var(--surface-sunken);
  color: var(--text-500);
  padding: 8px 12px;
  font-size: 11px;
  font-weight: 600;
}

.overdue-row {
  border-bottom: 1px solid var(--border);
  padding: 10px 12px;
  font-size: 12px;
}

.overdue-row:last-of-type {
  border-bottom: 0;
}

.overdue-row:hover {
  background: var(--red-bg);
}

.overdue-row .rank {
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  border-radius: 7px;
  background: var(--red-solid);
  color: #fff;
  font-size: 12px;
  font-weight: 800;
}

.factory-scope {
  min-width: 0;
}

.current-factory-card {
  display: flex;
  min-width: min(460px, 100%);
  align-items: center;
  gap: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-sunken);
  padding: 10px 12px;
}

.current-factory-card strong {
  color: var(--text-950);
  font-size: 14px;
}

.current-factory-card span {
  color: var(--text-500);
  font-size: 12px;
}

.filterbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.chip {
  border: 1px solid var(--border);
  border-radius: 999px;
  background: #fff;
  color: var(--text-600);
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 600;
}

.chip.active {
  border-color: var(--text-950);
  background: var(--text-950);
  color: #fff;
}

.chip.count b {
  margin-left: 4px;
  font-variant-numeric: tabular-nums;
}

.grid-group-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 22px 0 12px;
}

.grid-group-head h3 {
  margin: 0;
  color: var(--text-900);
  font-size: 15px;
  font-weight: 700;
}

.grid-group-head .line {
  height: 1px;
  flex: 1;
  background: var(--border);
}

.import-layout,
.pool-layout,
.sched-layout {
  display: grid;
  gap: 16px;
}

.import-layout {
  grid-template-columns: minmax(0, 1fr);
}

.import-main,
.order-panel,
.schedule-main {
  min-width: 0;
}

.import-side,
.sched-side {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 16px;
}

.dropzone {
  margin-top: 14px;
  border: 2px dashed var(--border-strong);
  border-radius: var(--radius-xl);
  background: var(--surface-sunken);
  padding: 40px 28px;
  text-align: center;
  transition: background 0.18s ease, border-color 0.18s ease;
  cursor: pointer;
}

.dropzone:hover {
  border-color: var(--primary);
  background: var(--teal-bg);
}

.dropzone.is-disabled,
.dropzone.is-disabled:hover {
  border-color: var(--border);
  background: #f8fafc;
  cursor: not-allowed;
  opacity: 0.74;
}

.dropzone .cloud {
  display: grid;
  width: 64px;
  height: 64px;
  margin: 0 auto 14px;
  place-items: center;
  border-radius: 18px;
  background: #fff;
  color: var(--primary);
  box-shadow: var(--shadow-card);
}

.dropzone h3 {
  margin: 0 0 6px;
  color: var(--text-950);
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0;
}

.dropzone p {
  margin: 0;
  color: var(--text-500);
  font-size: 13px;
}

.file-row {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-top: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #fff;
  padding: 12px 14px;
}

.file-ico {
  display: grid;
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  place-items: center;
  border-radius: 10px;
  background: var(--green-bg);
  color: var(--green-fg);
  font-size: 11px;
  font-weight: 800;
}

.progress-line {
  height: 5px;
  margin-top: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--surface-muted);
}

.progress-line > span {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--primary);
}

.hint {
  display: flex;
  gap: 10px;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius);
  background: var(--surface-sunken);
  color: var(--text-600);
  padding: 12px 14px;
  font-size: 12px;
  line-height: 1.6;
}

.hint-ico {
  display: inline-flex;
  flex-shrink: 0;
  color: var(--primary);
  padding-top: 1px;
}

.error-hint {
  border-color: rgba(239, 68, 68, 0.3);
  background: #fff7f7;
  color: #991b1b;
}

.error-hint .hint-ico {
  color: var(--red-solid);
}

.readonly-hint {
  border-color: rgba(148, 163, 184, 0.3);
  background: #f8fafc;
  color: #475569;
}

.readonly-hint .hint-ico {
  color: var(--text-500);
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 16px;
}

.stat {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #fff;
  padding: 14px;
}

.stat .n {
  color: var(--text-950);
  font-size: 26px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.stat .l {
  margin-top: 2px;
  color: var(--text-500);
  font-size: 12px;
}

.steps,
.issue-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 16px;
}

.step {
  display: flex;
  gap: 12px;
  padding: 10px 0;
}

.step .marker {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.step .bullet {
  display: grid;
  width: 24px;
  height: 24px;
  flex-shrink: 0;
  place-items: center;
  border-radius: 999px;
  background: var(--green-solid);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}

.step .line {
  width: 2px;
  flex: 1;
  margin: 2px 0;
  background: var(--border);
}

.step .body {
  padding-bottom: 6px;
}

.step .body .t {
  color: var(--text-900);
  font-size: 13px;
  font-weight: 600;
}

.step .body .d {
  margin-top: 2px;
  color: var(--text-500);
  font-size: 12px;
}

.maprow {
  display: grid;
  grid-template-columns: 44px 1fr 24px 1fr;
  gap: 8px;
  align-items: center;
  border-bottom: 1px dashed var(--border);
  padding: 7px 0;
}

.maprow:last-child {
  border-bottom: 0;
}

.col-tag {
  border-radius: 6px;
  background: var(--surface-muted);
  color: var(--text-500);
  padding: 3px 0;
  text-align: center;
  font-family: "Cascadia Code", "Consolas", monospace;
  font-size: 12px;
  font-weight: 700;
}

.arrow {
  color: var(--text-400);
  text-align: center;
}

.field-name {
  color: var(--text-900);
  font-size: 13px;
  font-weight: 600;
}

.issue {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 8px;
  border-radius: var(--radius);
  padding: 10px 12px;
  font-size: 13px;
}

.issue.red {
  border: 1px solid var(--red-bd);
  background: var(--red-bg);
  color: var(--red-fg);
}

.issue.amber {
  border: 1px solid var(--amber-bd);
  background: var(--amber-bg);
  color: var(--amber-fg);
}

.issue.blue {
  border: 1px solid var(--blue-bd);
  background: var(--blue-bg);
  color: var(--blue-fg);
}

.issue b {
  font-variant-numeric: tabular-nums;
}

.issue-icon {
  width: 15px;
  height: 15px;
  flex-shrink: 0;
  margin-top: 1px;
}

.issue-detail-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

.issue-detail {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr);
  gap: 8px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fff;
  padding: 8px 10px;
  color: var(--text-600);
  font-size: 12px;
  line-height: 1.5;
}

.issue-detail.error {
  border-color: rgba(239, 68, 68, 0.28);
  background: #fff7f7;
}

.issue-detail.warning {
  border-color: rgba(245, 158, 11, 0.3);
  background: #fffbeb;
}

.pool-layout {
  grid-template-columns: minmax(0, 1fr);
}

.principle-panel {
  align-self: start;
}

.principles {
  margin-top: 16px;
}

.table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #fff;
}

table.grid {
  width: 100%;
  min-width: 1120px;
  border-collapse: collapse;
  font-size: 13px;
}

table.grid th {
  position: sticky;
  top: 0;
  border-bottom: 1px solid var(--border);
  background: var(--surface-sunken);
  color: var(--text-500);
  padding: 10px 12px;
  text-align: left;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

table.grid td {
  border-bottom: 1px solid var(--border);
  color: var(--text-700);
  padding: 10px 12px;
  vertical-align: middle;
}

table.grid tbody tr:hover {
  background: var(--surface-sunken);
}

table.grid tbody tr:last-child td {
  border-bottom: 0;
}

.grid-table {
  width: 100%;
  min-width: 1080px;
  border-collapse: collapse;
  text-align: left;
  font-size: 13px;
}

.grid-table th {
  background: var(--surface-sunken);
  color: var(--text-500);
  padding: 10px 12px;
  font-size: 11px;
  font-weight: 700;
}

.grid-table td {
  border-top: 1px solid var(--border);
  color: var(--text-700);
  padding: 12px;
  vertical-align: top;
}

.grid-table .right {
  text-align: right;
}

.table-row:hover td {
  background: var(--surface-sunken);
}

.score-badge {
  display: inline-flex;
  min-width: 38px;
  justify-content: center;
  border-radius: 8px;
  padding: 4px 8px;
  font-size: 13px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.group-tag {
  display: inline-flex;
  border-radius: 7px;
  background: var(--violet-bg);
  color: var(--violet-fg);
  padding: 4px 8px;
  font-family: "Cascadia Code", "Consolas", monospace;
  font-size: 11px;
  font-weight: 700;
}

.principle {
  display: flex;
  gap: 11px;
  border-bottom: 1px dashed var(--border);
  padding: 11px 0;
}

.principle:last-child {
  border-bottom: 0;
}

.principle .badge {
  display: grid;
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  place-items: center;
  border-radius: 8px;
  color: #fff;
  font-size: 12px;
  font-weight: 800;
}

.principle .t {
  color: var(--text-900);
  font-size: 13px;
  font-weight: 600;
}

.principle .d {
  margin-top: 2px;
  color: var(--text-500);
  font-size: 11px;
  line-height: 1.5;
}

.score {
  display: inline-flex;
  min-width: 40px;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  padding: 3px 8px;
  font-size: 14px;
  font-variant-numeric: tabular-nums;
  font-weight: 800;
}

.score.hi {
  background: var(--red-bg);
  color: var(--red-fg);
}

.score.mid {
  background: var(--amber-bg);
  color: var(--amber-fg);
}

.score.lo {
  background: var(--slate-bg);
  color: var(--slate-fg);
}

.grp-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border-radius: 6px;
  padding: 2px 7px;
  font-family: "Cascadia Code", "Consolas", monospace;
  font-size: 11px;
  font-weight: 700;
}

.grp-a {
  background: #ede9fe;
  color: #6d28d9;
}

.grp-b {
  background: #cffafe;
  color: #0e7490;
}

.grp-c {
  background: #fce7f3;
  color: #be185d;
}

.grp-none {
  background: var(--surface-muted);
  color: var(--text-400);
}

tr.grouprow td {
  background: var(--violet-bg) !important;
}

.factorbar {
  display: flex;
  align-items: center;
  gap: 3px;
}

.factorbar .seg {
  height: 6px;
  border-radius: 2px;
}

.sched-layout {
  grid-template-columns: minmax(0, 1fr);
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  color: var(--text-500);
  font-size: 12px;
}

.legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.legend i {
  width: 10px;
  height: 10px;
  border-radius: 4px;
}

.legend i.green {
  background: var(--green-solid);
}

.legend i.amber {
  background: var(--amber-solid);
}

.legend i.red {
  background: var(--red-solid);
}

.lane-wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #fff;
}

.lane-stage {
  min-width: 920px;
}

.lane-label {
  border-right: 1px solid var(--border);
  padding: 12px;
}

.lane-label p {
  margin: 0;
  color: var(--text-950);
  font-size: 13px;
  font-weight: 700;
}

.lane-label span {
  display: block;
  margin-top: 4px;
  color: var(--text-500);
  font-size: 11px;
}

.lane-body {
  position: relative;
  min-height: 64px;
}

.lane-lines {
  position: absolute;
  inset: 0;
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
}

.lane-lines span {
  border-left: 1px dashed var(--border);
}

.lane-lines span:first-child {
  border-left: 0;
}

.gantt-block {
  position: absolute;
  top: 12px;
  display: flex;
  height: 40px;
  min-width: 120px;
  flex-direction: column;
  justify-content: center;
  overflow: hidden;
  border-radius: 9px;
  background-image: linear-gradient(90deg, var(--teal-fg), var(--teal-solid));
  color: #fff;
  padding: 0 12px;
  box-shadow: 0 10px 20px rgba(15, 23, 42, 0.12);
}

.gantt-block span,
.gantt-block small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gantt-block span {
  font-size: 12px;
  font-weight: 800;
}

.gantt-block small {
  font-size: 11px;
  opacity: 0.88;
}

.issue-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px;
}

.issue-card h3 {
  margin: 0;
  color: var(--text-950);
  font-size: 14px;
  font-weight: 700;
}

.writeback-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 16px;
}

.writeback-grid > div {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-sunken);
  padding: 12px;
}

.writeback-grid b {
  display: block;
  margin-top: 8px;
  color: var(--text-950);
  font-size: 26px;
  font-weight: 800;
  line-height: 1;
}

.pending-panel {
  align-self: start;
}

.pending-card {
  margin-bottom: 8px;
  border: 1px solid var(--border);
  border-left: 3px solid var(--slate-solid);
  border-radius: var(--radius);
  background: #fff;
  padding: 11px 12px;
  cursor: grab;
  transition: box-shadow 0.15s ease;
}

.pending-card:hover {
  box-shadow: var(--shadow-card);
}

.pending-card.urgent {
  border-left-color: var(--red-solid);
}

.pending-card.short {
  border-left-color: var(--amber-solid);
}

.pending-card .row1 {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.pending-card .mold {
  color: var(--text-900);
  font-family: "Cascadia Code", "Consolas", monospace;
  font-size: 12px;
  font-weight: 700;
}

.pending-card .meta {
  margin-top: 4px;
  color: var(--text-500);
  font-size: 11px;
}

.gantt {
  overflow-x: auto;
}

.gantt-inner {
  min-width: 900px;
}

.timeaxis {
  position: sticky;
  top: 0;
  z-index: 5;
  display: grid;
  grid-template-columns: 120px repeat(7, 1fr);
  border-bottom: 1px solid var(--border);
  background: #fff;
}

.timeaxis .corner {
  padding: 8px 10px;
  color: var(--text-500);
  font-size: 11px;
  font-weight: 600;
}

.timeaxis .day {
  border-left: 1px solid var(--border);
  padding: 8px 6px;
  color: var(--text-500);
  text-align: center;
  font-size: 11px;
}

.timeaxis .day b {
  display: block;
  color: var(--text-900);
  font-size: 13px;
}

.lane {
  display: grid;
  grid-template-columns: 120px 1fr;
  border-bottom: 1px solid var(--border);
}

.lane:hover {
  background: var(--surface-sunken);
}

.lane-head {
  border-right: 1px solid var(--border);
  padding: 10px;
}

.lane-head .mid {
  color: var(--text-950);
  font-size: 14px;
  font-weight: 700;
}

.lane-head .spec {
  margin-top: 2px;
  color: var(--text-500);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.lane-track {
  position: relative;
  height: 56px;
}

.grid-lines {
  position: absolute;
  inset: 0;
  display: grid;
  grid-template-columns: repeat(7, 1fr);
}

.grid-lines span {
  border-left: 1px dashed var(--border);
}

.block {
  position: absolute;
  top: 8px;
  display: flex;
  height: 40px;
  flex-direction: column;
  justify-content: center;
  overflow: hidden;
  border-radius: 7px;
  color: #fff;
  padding: 4px 8px;
  font-size: 11px;
  box-shadow: 0 3px 8px rgba(15, 23, 42, 0.14);
  cursor: pointer;
}

.block .bm {
  overflow: hidden;
  font-family: "Cascadia Code", "Consolas", monospace;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.block .bs {
  font-size: 10px;
  opacity: 0.9;
}

.block.running {
  background: linear-gradient(135deg, #0d9488, #14b8a6);
}

.block.same-mold {
  background: linear-gradient(135deg, #7c3aed, #8b5cf6);
}

.block.normal {
  background: linear-gradient(135deg, #0369a1, #0ea5e9);
}

.block.urgent {
  background: linear-gradient(135deg, #dc2626, #ef4444);
}

.block.short {
  background: linear-gradient(135deg, #d97706, #f59e0b);
}

.gap {
  position: absolute;
  top: 8px;
  height: 40px;
  border: 1px solid var(--amber-bd);
  border-radius: 4px;
  background: repeating-linear-gradient(45deg, #fde68a 0 5px, #fef3c7 5px 10px);
}

.gap-lbl {
  position: absolute;
  top: -6px;
  left: 0;
  border-radius: 3px;
  background: #fff;
  color: var(--amber-fg);
  padding: 0 3px;
  font-size: 9px;
  white-space: nowrap;
}

.legend2 {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  color: var(--text-600);
  font-size: 11px;
}

.legend2 span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.legend2 i {
  display: inline-block;
  width: 16px;
  height: 10px;
  border-radius: 3px;
}

.legend2 .legend-block {
  position: static;
  box-shadow: none;
  cursor: default;
}

.legend-gap {
  border: 1px solid var(--amber-bd);
  background: repeating-linear-gradient(45deg, #fde68a 0 4px, #fef3c7 4px 8px);
}

.trial-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.trial {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px;
}

.trial .n {
  font-size: 24px;
  font-variant-numeric: tabular-nums;
  font-weight: 800;
}

.trial .l {
  margin-top: 2px;
  font-size: 11px;
}

.trial-teal {
  border-color: var(--teal-bd);
  background: var(--teal-bg);
  color: var(--teal-fg);
}

.trial-violet {
  border-color: var(--violet-bd);
  background: var(--violet-bg);
  color: var(--violet-fg);
}

.trial-amber {
  border-color: var(--amber-bd);
  background: var(--amber-bg);
  color: var(--amber-fg);
}

.trial-red {
  border-color: var(--red-bd);
  background: var(--red-bg);
  color: var(--red-fg);
}

.constraint {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  border-radius: var(--radius);
  margin-bottom: 7px;
  padding: 9px 11px;
  font-size: 12px;
}

.constraint.ok {
  border: 1px solid var(--green-bd);
  background: var(--green-bg);
  color: var(--green-fg);
}

.constraint.warn {
  border: 1px solid var(--amber-bd);
  background: var(--amber-bg);
  color: var(--amber-fg);
}

@media (min-width: 1100px) {
  .pool-layout {
    grid-template-columns: 300px minmax(0, 1fr);
  }

  .pool-layout > .col:first-child {
    position: sticky;
    top: 78px;
  }
}

@media (min-width: 1180px) {
  .import-layout {
    grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr);
  }
}

@media (min-width: 1280px) {
  .sched-layout {
    grid-template-columns: 290px minmax(0, 1fr);
    align-items: start;
  }

  .pending-panel {
    position: sticky;
    top: 64px;
  }
}

@media (min-width: 720px) {
  .focus-band {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (min-width: 640px) {
  .trial-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

@media (min-width: 768px) {
  .metrics {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

@media (min-width: 1180px) {
  .focus-band {
    grid-template-columns: repeat(6, minmax(0, 1fr));
  }
}

@media (min-width: 1280px) {
  .page {
    padding: 24px 40px 56px;
  }

  .topbar-inner {
    padding: 10px 40px;
  }

  .page-head {
    flex-direction: row;
    align-items: flex-end;
    justify-content: space-between;
  }
}

.injection-topbar {
  position: sticky;
  top: 0;
  z-index: 40;
  border-bottom: 1px solid #e2e8f0;
  background: rgba(248, 250, 252, 0.86);
  backdrop-filter: saturate(1.4) blur(8px);
}

.injection-topbar-inner {
  display: flex;
  max-width: 1680px;
  min-height: 58px;
  margin: 0 auto;
  align-items: center;
  gap: 18px;
  padding: 10px 24px;
}

.injection-brand {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 10px;
  color: #020617;
  font-weight: 700;
  white-space: nowrap;
}

.injection-brand-mark {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 10px;
  background: oklch(0.45 0.09 182);
  color: #fff;
  box-shadow: 0 6px 16px rgba(13, 118, 110, 0.35);
}

.injection-step-nav {
  display: flex;
  min-width: 0;
  flex: 1 1 auto;
  gap: 4px;
  overflow-x: auto;
  padding-bottom: 2px;
}

.injection-step-nav::-webkit-scrollbar {
  height: 4px;
}

.injection-step-nav::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: #cbd5e1;
}

.injection-step-tab {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  border-radius: 999px;
  padding: 7px 14px;
  color: #64748b;
  font-size: 13px;
  font-weight: 700;
  white-space: nowrap;
  transition: background 0.15s ease, color 0.15s ease;
}

.injection-step-tab:hover {
  background: #f1f5f9;
  color: #020617;
}

.injection-step-tab.active {
  background: oklch(0.45 0.09 182);
  color: #fff;
}

.step-no {
  display: inline-grid;
  width: 18px;
  height: 18px;
  margin-right: 6px;
  place-items: center;
  border-radius: 999px;
  background: #f1f5f9;
  color: #64748b;
  font-size: 11px;
  font-weight: 800;
}

.injection-step-tab.active .step-no {
  background: rgba(255, 255, 255, 0.22);
  color: #fff;
}

.injection-global-search {
  display: flex;
  width: min(312px, 24vw);
  min-width: 230px;
  flex: 0 1 auto;
  align-items: center;
  gap: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  background: #fff;
  padding: 6px 12px;
  color: #94a3b8;
}

.injection-global-search:focus-within {
  border-color: oklch(0.45 0.09 182);
  box-shadow: 0 0 0 3px rgba(20, 184, 166, 0.12);
}

.injection-global-search input {
  min-width: 0;
  flex: 1;
  border: 0;
  background: transparent;
  color: #0f172a;
  font-size: 13px;
  outline: none;
}

.injection-global-search input::placeholder {
  color: #94a3b8;
}

.injection-global-search kbd {
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  padding: 1px 5px;
  color: #94a3b8;
  font-size: 10px;
  line-height: 1.2;
}

.injection-topbar-right {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 12px;
}

@media (min-width: 1280px) {
  .injection-topbar-inner {
    padding: 10px 40px;
  }
}

@media (max-width: 1180px) {
  .topbar-inner {
    flex-wrap: wrap;
    align-items: flex-start;
  }

  .nav {
    order: 3;
    flex-basis: 100%;
  }

  .search {
    margin-left: auto;
    width: min(360px, 44vw);
  }

  .injection-topbar-inner {
    flex-wrap: wrap;
    align-items: flex-start;
  }

  .injection-step-nav {
    order: 3;
    flex-basis: 100%;
  }

  .injection-global-search {
    margin-left: auto;
    width: min(360px, 44vw);
  }
}

@media (max-width: 720px) {
  .page {
    padding: 18px 16px 40px;
  }

  .topbar-inner {
    gap: 10px;
    padding: 10px 16px;
  }

  .search {
    order: 4;
    width: 100%;
    min-width: 0;
  }

  .topbar-right {
    margin-left: auto;
  }

  .file-row {
    flex-wrap: wrap;
  }

  .stat-grid {
    grid-template-columns: 1fr;
  }

  .maprow {
    grid-template-columns: 1fr;
  }

  .watch-panel {
    overflow-x: auto;
  }

  .overdue-head,
  .overdue-row {
    min-width: 640px;
  }

  .injection-topbar-inner {
    gap: 10px;
    padding: 10px 16px;
  }

  .injection-global-search {
    order: 4;
    width: 100%;
    min-width: 0;
  }

  .injection-topbar-right {
    margin-left: auto;
  }
}

.machine-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(292px, 1fr));
  gap: 12px;
}

.card {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-card);
}

.card-pad {
  padding: 18px;
}

.bar {
  height: 7px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--surface-muted);
}

.bar > span {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--primary);
}

.bar.amber > span {
  background: var(--amber-solid);
}

.bar.red > span {
  background: var(--red-solid);
}

.bar.green > span {
  background: var(--green-solid);
}

.swatch {
  display: inline-block;
  width: 12px;
  height: 12px;
  margin-right: 6px;
  border: 1px solid rgba(15, 23, 42, 0.15);
  border-radius: 3px;
  vertical-align: -1px;
}

.mbox {
  position: relative;
  width: 100%;
  border: 1px solid var(--border);
  border-left: 4px solid var(--slate-solid);
  border-radius: var(--radius);
  background: #fff;
  padding: 12px 13px 11px;
  text-align: left;
  transition: box-shadow 0.15s ease, transform 0.15s ease, border-color 0.15s ease;
}

.mbox:hover {
  box-shadow: var(--shadow-card);
  transform: translateY(-2px);
}

.mbox.running {
  border-left-color: var(--green-solid);
}

.mbox.short {
  border-left-color: var(--amber-solid);
}

.mbox.down {
  border-left-color: var(--red-solid);
}

.mbox.idle {
  border-left-color: var(--slate-solid);
  opacity: 0.82;
}

.mbox-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.mbox-id {
  display: flex;
  min-width: 0;
  align-items: baseline;
  gap: 8px;
}

.mbox-id b {
  color: var(--text-950);
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0;
}

.mbox-spec {
  overflow: hidden;
  color: var(--text-500);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mbox-mold {
  margin-top: 9px;
  border-top: 1px dashed var(--border);
  padding-top: 9px;
}

.mbox-mold .name {
  overflow: hidden;
  color: var(--text-900);
  font-family: "Cascadia Code", "Consolas", monospace;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mbox-mold .meta {
  margin-top: 3px;
  overflow: hidden;
  color: var(--text-500);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mbox-owe {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.mbox-owe .n {
  color: var(--text-600);
  font-size: 12px;
  white-space: nowrap;
}

.mbox-owe .n b {
  color: var(--text-950);
  font-variant-numeric: tabular-nums;
}

.mbox-owe .bar {
  flex: 1;
}

.mbox-owe .pct {
  color: var(--text-700);
  font-size: 11px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.mbox-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
  color: var(--text-500);
  font-size: 11px;
}

.mbox-eta b {
  color: var(--text-700);
  font-variant-numeric: tabular-nums;
}

.mbox-next {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 7px;
  border-radius: 7px;
  background: var(--surface-sunken);
  padding: 5px 8px;
  color: var(--text-600);
  font-size: 11px;
}

.mbox-next .lbl {
  color: var(--text-400);
}

.mbox-next .nm {
  overflow: hidden;
  color: var(--text-700);
  font-family: "Cascadia Code", "Consolas", monospace;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-lamp {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 5px;
  color: var(--text-700);
  font-size: 11px;
  font-weight: 600;
}

.lamp {
  display: inline-block;
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  border-radius: 999px;
}

.lamp.g {
  background: var(--green-solid);
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.16);
}

.lamp.a {
  background: var(--amber-solid);
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.16);
}

.lamp.r {
  background: var(--red-solid);
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.16);
}

.lamp.s {
  background: var(--slate-solid);
  box-shadow: 0 0 0 3px rgba(148, 163, 184, 0.16);
}

.drawer-mask {
  position: fixed;
  inset: 0;
  z-index: 60;
  background: rgba(15, 23, 42, 0.42);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.22s ease;
}

.drawer-mask.open {
  opacity: 1;
  pointer-events: auto;
}

.drawer {
  position: fixed;
  top: 0;
  right: 0;
  z-index: 61;
  display: flex;
  width: min(520px, 94vw);
  height: 100%;
  flex-direction: column;
  background: #fff;
  box-shadow: var(--shadow-pop);
  opacity: 0.98;
  transform: translateX(100%);
  transition:
    transform 0.28s cubic-bezier(0.22, 1, 0.36, 1),
    opacity 0.2s ease;
  will-change: transform;
}

.drawer.open {
  opacity: 1;
  transform: translateX(0);
}

@media (prefers-reduced-motion: reduce) {
  .drawer-mask,
  .drawer {
    transition-duration: 1ms;
  }
}

.drawer-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--border);
  padding: 18px 20px;
}

.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 18px 20px;
}

.drawer-body::-webkit-scrollbar {
  width: 6px;
}

.drawer-body::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: var(--border-strong);
}

.drawer-machine-title {
  font-size: 22px;
}

.drawer-spec {
  margin-top: 6px;
}

.drawer-task-card {
  box-shadow: none;
}

.drawer-mold {
  font-size: 15px;
}

.close-x {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  color: var(--text-500);
}

.close-x:hover {
  background: var(--surface-muted);
}

.kv {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.kv .item {
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--surface-sunken);
  padding: 10px 12px;
}

.kv .item .k {
  color: var(--text-500);
  font-size: 11px;
}

.kv .item .v {
  margin-top: 3px;
  color: var(--text-950);
  font-size: 14px;
  font-weight: 700;
}

.kv .item .v.danger {
  color: var(--amber-fg);
}

.kv .item .v.small-v {
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kv .item.wide {
  grid-column: 1 / -1;
}

.subhead {
  margin: 20px 0 10px;
  color: var(--text-700);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.normal-tag {
  margin-left: 6px;
  letter-spacing: 0;
  text-transform: none;
}

.queue-item {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: #fff;
  padding: 11px 12px;
  margin-bottom: 8px;
}

.queue-item .seq {
  display: grid;
  width: 24px;
  height: 24px;
  flex-shrink: 0;
  place-items: center;
  border-radius: 7px;
  background: var(--surface-muted);
  color: var(--text-600);
  font-size: 12px;
  font-weight: 700;
}

.queue-item.now .seq {
  background: var(--primary);
  color: #fff;
}

.queue-item .drag {
  color: var(--text-400);
  cursor: grab;
}

.changeover {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 0;
  padding: 6px 10px 6px 34px;
  color: var(--amber-fg);
  font-size: 11px;
}

.changeover::before {
  content: "";
  position: absolute;
  top: -4px;
  bottom: -4px;
  left: 12px;
  width: 2px;
  background: repeating-linear-gradient(var(--amber-bd) 0 4px, transparent 4px 8px);
}

.empty-drawer-note {
  border-radius: 9px;
  background: var(--surface-sunken);
  padding: 12px;
  color: var(--text-500);
  font-size: 12px;
}

.color-risk-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.principle-row {
  display: flex;
  gap: 11px;
  border-bottom: 1px dashed #e2e8f0;
  padding: 11px 0;
}

.principle-row:last-child {
  border-bottom: 0;
}

.principle-row > span {
  display: grid;
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  place-items: center;
  border-radius: 8px;
  color: #fff;
  font-size: 12px;
  font-weight: 800;
}

.principle-row p {
  margin: 0;
  color: #0f172a;
  font-size: 13px;
  font-weight: 700;
}

.principle-row small {
  display: block;
  margin-top: 2px;
  color: #64748b;
  font-size: 11px;
  line-height: 1.5;
}

.gantt-axis {
  display: grid;
  grid-template-columns: 136px repeat(7, minmax(92px, 1fr));
  border-bottom: 1px solid #e2e8f0;
  background: #f8fafc;
}

.gantt-lane {
  display: grid;
  grid-template-columns: 136px minmax(0, 1fr);
  border-bottom: 1px solid #e2e8f0;
}

.gantt-lane:last-child {
  border-bottom: 0;
}

.gantt-lane:hover {
  background: #f8fafc;
}
</style>

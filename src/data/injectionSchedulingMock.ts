import type { Tone } from '@/data/enterpriseMock'

export type InjectionSectionId =
  | 'dashboard'
  | 'data-center'
  | 'execution'
  | 'reporting'
  | 'config'

export interface InjectionMetric {
  label: string
  value: string
  detail: string
  tone: Tone
}

export interface ShiftSummary {
  shift: string
  date: string
  completion: number
  machineRunning: string
  carryOver: string
  alert: string
}

export interface MachineLoad {
  machine: string
  utilization: number
  mold: string
  material: string
  tone: Tone
  queueDepth: string
}

export interface ColorTransitionRisk {
  machine: string
  route: string[]
  risk: string
  tone: Tone
}

export interface DataSourceStatus {
  name: string
  freshness: string
  status: string
  statusTone: Tone
  summary: string
}

export interface ExecutionTask {
  title: string
  meta: string
  tone: Tone
}

export interface InjectionStage {
  title: string
  owner: string
  detail: string
  state: 'done' | 'active' | 'pending'
}

export interface InjectionNavItem {
  id: InjectionSectionId
  label: string
  summary: string
}

export interface DataCenterDataset {
  name: string
  owner: string
  freshness: string
  completeness: number
  status: string
  statusTone: Tone
  summary: string
  issues: string[]
}

export interface OrderSnapshotRow {
  orderNo: string
  productCode: string
  moldName: string
  color: string
  material: string
  quantity: string
  due: string
  state: string
  tone: Tone
}

export interface MachineProfileRow {
  machine: string
  tonnage: string
  armType: string
  workshop: string
  status: string
  tone: Tone
  fit: string
}

export interface MoldTargetRow {
  moldCode: string
  target24h: string
  target11h: string
  source: string
  health: string
  tone: Tone
}

export interface ExecutionOrderRow {
  machine: string
  orderNo: string
  moldName: string
  color: string
  target24h: string
  shortage: string
  priority: string
  tone: Tone
}

export interface ManualActionRow {
  title: string
  reason: string
  owner: string
  action: string
  tone: Tone
}

export interface ReportingMetric {
  label: string
  value: string
  detail: string
  tone: Tone
}

export interface ShiftReportRow {
  machine: string
  worker: string
  target11h: string
  actual: string
  variance: string
  downtime: string
  tone: Tone
}

export interface WarehouseInboundRow {
  deliveryCode: string
  orderNo: string
  shots: string
  materialKg: string
  pmc: string
  status: string
  tone: Tone
}

export interface ConfigRuleCard {
  title: string
  owner: string
  summary: string
  status: string
  tone: Tone
  items: string[]
}

export const injectionSectionNav: InjectionNavItem[] = [
  {
    id: 'dashboard',
    label: '驾驶舱',
    summary: '先看待排、结转、机台负载和排产异常。',
  },
  {
    id: 'data-center',
    label: '数据中心',
    summary: '统一订单、机台、模具目标和历史主数据。',
  },
  {
    id: 'execution',
    label: '排机执行',
    summary: '承接智能排机、人工微调和结转延续。',
  },
  {
    id: 'reporting',
    label: '回报中心',
    summary: '沉淀日报、入库、月结和回写闭环。',
  },
  {
    id: 'config',
    label: '配置中心',
    summary: '维护规则参数、映射关系、责任人与权限。',
  },
]

export const injectionOverviewMetrics: InjectionMetric[] = [
  { label: '待排订单', value: '86', detail: '新单 64 · 插单 5 · 缺资料 3', tone: 'amber' },
  { label: '结转订单', value: '12', detail: '夜班延续 8 · 白班延续 4', tone: 'blue' },
  { label: '运行机台', value: '28 / 34', detail: '稼动率 82.4% · 空闲 6 台', tone: 'teal' },
  { label: '排产异常', value: '4', detail: '颜色逆序 2 · 目标缺失 2', tone: 'red' },
]

export const injectionShiftSummaries: ShiftSummary[] = [
  {
    shift: '白班',
    date: '2026-06-29',
    completion: 78,
    machineRunning: '16 台运行',
    carryOver: '结转 4 单',
    alert: '2 单因模具目标缺失待人工确认',
  },
  {
    shift: '夜班',
    date: '2026-06-29',
    completion: 64,
    machineRunning: '12 台运行',
    carryOver: '结转 8 单',
    alert: '黑转白颜色切换风险 2 台机',
  },
]

export const injectionMachineLoad: MachineLoad[] = [
  { machine: 'A-06#', utilization: 92, mold: 'MCKP-17M-01', material: 'ABS KF-740', tone: 'green', queueDepth: '排程 3 条' },
  { machine: 'A-12#', utilization: 88, mold: 'RBCEZ-05M-01', material: 'PP 本白', tone: 'teal', queueDepth: '排程 2 条' },
  { machine: 'A-19#', utilization: 73, mold: 'FUGG-07M-01', material: 'TPE 透明', tone: 'blue', queueDepth: '排程 2 条' },
  { machine: 'A-23#', utilization: 66, mold: 'MNVN-17M-01', material: 'ABS 黑', tone: 'amber', queueDepth: '结转 1 条' },
  { machine: 'A-26#', utilization: 54, mold: 'RBCA-08M-01', material: 'LDPE 金色', tone: 'amber', queueDepth: '待确认 1 条' },
  { machine: 'A-31#', utilization: 28, mold: '吹气机台', material: '未分配', tone: 'red', queueDepth: '异常 1 条' },
]

export const injectionColorTransitionRisks: ColorTransitionRisk[] = [
  { machine: 'A-06#', route: ['本白', '浅灰', '银', '黑'], risk: '顺序健康', tone: 'green' },
  { machine: 'A-12#', route: ['透明', '蓝', '黑', '白'], risk: '黑后接白，需人工确认', tone: 'red' },
  { machine: 'A-19#', route: ['米黄', '橙', '红'], risk: '顺序健康', tone: 'green' },
  { machine: 'A-23#', route: ['黑', '白'], risk: '逆序，建议换台或重排', tone: 'red' },
]

export const injectionDataSourceStatus: DataSourceStatus[] = [
  {
    name: '订单池',
    freshness: '5 分钟前更新',
    status: '正常',
    statusTone: 'green',
    summary: 'PDF / Excel / 图片导入都已接入，当前有 3 条订单字段缺失。',
  },
  {
    name: '机台主数据',
    freshness: '昨日同步',
    status: '待补',
    statusTone: 'amber',
    summary: '34 台机台已建档，但仍缺 6 台详细机械手与工艺范围。',
  },
  {
    name: '模具目标',
    freshness: '3 天前维护',
    status: '风险',
    statusTone: 'red',
    summary: '2 套模具没有 24H / 11H 目标，影响自动排产准确率。',
  },
  {
    name: '历史数据库',
    freshness: '实时回写',
    status: '正常',
    statusTone: 'green',
    summary: '历史命中率可用于啤重与同模机台匹配，当前样本 1,248 条。',
  },
]

export const injectionExecutionTasks: ExecutionTask[] = [
  { title: 'A-12# 黑转白风险待确认', meta: '需要计划员调整顺序或切换机台', tone: 'red' },
  { title: 'FUGG-07M-01 缺 24H 目标值', meta: '建议先补模具目标后再自动计算天数', tone: 'amber' },
  { title: '夜班 8 条结转已锁定原机台', meta: '系统已按原机延续，可进入人工微调', tone: 'blue' },
  { title: '入库单与排产回写待打通', meta: '建议下一步接日报 / 入库联动', tone: 'teal' },
]

export const injectionWorkflowStages: InjectionStage[] = [
  {
    title: '订单入池',
    owner: '计划 / 文员',
    detail: '导入 PDF、Excel、图片和手工补单，统一进入待排订单池。',
    state: 'done',
  },
  {
    title: '结转识别',
    owner: '系统',
    detail: '自动识别上一班未完成订单并锁定原机台延续。',
    state: 'done',
  },
  {
    title: '智能排机',
    owner: '系统 + 计划员',
    detail: '综合同模、啤重、料型、颜色顺序和历史命中率排机。',
    state: 'active',
  },
  {
    title: '人工微调',
    owner: '生产主管',
    detail: '处理异常、颜色逆序、目标缺失与重点插单。',
    state: 'pending',
  },
  {
    title: '回报闭环',
    owner: '车间 / PMC',
    detail: '日报、入库、月结与历史回写，反哺下一轮排产。',
    state: 'pending',
  },
]

export const injectionDataCenterDatasets: DataCenterDataset[] = [
  {
    name: '订单主数据',
    owner: '计划 / 文员',
    freshness: '5 分钟前',
    completeness: 96,
    status: '健康',
    statusTone: 'green',
    summary: '已接 PDF / Excel / 图片导入，字段整体完整。',
    issues: ['3 条订单缺交期', '1 条订单缺色粉编号'],
  },
  {
    name: '机台主数据',
    owner: '生产主管',
    freshness: '昨日',
    completeness: 81,
    status: '待补',
    statusTone: 'amber',
    summary: '机台基本台账齐全，但工艺适配和机械手信息仍不完整。',
    issues: ['6 台缺工艺范围', '2 台状态未更新'],
  },
  {
    name: '模具目标数据',
    owner: '工程 / 生产',
    freshness: '3 天前',
    completeness: 72,
    status: '风险',
    statusTone: 'red',
    summary: '部分模具缺 24H/11H 目标，影响天数和优先级计算。',
    issues: ['2 套模具缺目标', '4 套模具目标已过旧'],
  },
  {
    name: '历史生产数据',
    owner: '系统回写',
    freshness: '实时',
    completeness: 93,
    status: '健康',
    statusTone: 'green',
    summary: '支持啤重区间、同模历史与同料型经验匹配。',
    issues: ['停机原因字段回写口径仍待统一'],
  },
]

export const injectionOrderSnapshotRows: OrderSnapshotRow[] = [
  {
    orderNo: 'CMC260234',
    productCode: '77858',
    moldName: 'MCKP-17M-01 喷水',
    color: '877C 金属银',
    material: 'ABS KF-740',
    quantity: '8,600',
    due: '06-30',
    state: '待排',
    tone: 'amber',
  },
  {
    orderNo: 'ZWY260002/B',
    productCode: '92105',
    moldName: 'RBCA-08M-01 奶嘴',
    color: '金色',
    material: 'LDPE 260GG',
    quantity: '4,138',
    due: '07-01',
    state: '结转',
    tone: 'blue',
  },
  {
    orderNo: 'LWW20260317006/B',
    productCode: '47391',
    moldName: 'RC01854 吃尺转动轴',
    color: '黑色',
    material: 'ABS AG15AIH',
    quantity: '2,800',
    due: '06-29',
    state: '异常',
    tone: 'red',
  },
  {
    orderNo: 'CMC260301',
    productCode: '71172',
    moldName: 'FUGG-07M-01 按钮',
    color: '透明蓝',
    material: 'TPE',
    quantity: '5,200',
    due: '07-02',
    state: '待排',
    tone: 'amber',
  },
]

export const injectionMachineProfileRows: MachineProfileRow[] = [
  { machine: 'A-06#', tonnage: '260T', armType: '五轴双臂', workshop: 'A车间', status: '运行', tone: 'green', fit: '适合 ABS / 同模延续' },
  { machine: 'A-12#', tonnage: '150T', armType: '三轴单臂', workshop: 'A车间', status: '运行', tone: 'green', fit: '本白 / 小件' },
  { machine: 'A-19#', tonnage: '260T', armType: '五轴双臂', workshop: 'A车间', status: '运行', tone: 'blue', fit: '透明料 / TPE' },
  { machine: 'A-31#', tonnage: '150T', armType: '未维护', workshop: 'A车间', status: '待确认', tone: 'amber', fit: '资料待补' },
]

export const injectionMoldTargetRows: MoldTargetRow[] = [
  { moldCode: 'MCKP-17M-01', target24h: '18,000', target11h: '8,250', source: '历史众数', health: '稳定', tone: 'green' },
  { moldCode: 'RBCA-08M-01', target24h: '12,500', target11h: '5,730', source: '人工维护', health: '稳定', tone: 'green' },
  { moldCode: 'FUGG-07M-01', target24h: '-', target11h: '-', source: '缺失', health: '待补', tone: 'red' },
  { moldCode: 'MNVN-17M-01', target24h: '15,800', target11h: '7,240', source: '历史 + 人工', health: '需复核', tone: 'amber' },
]

export const injectionExecutionQueueRows: ExecutionOrderRow[] = [
  {
    machine: 'A-06#',
    orderNo: 'CMC260234',
    moldName: 'MCKP-17M-01 喷水',
    color: '877C 金属银',
    target24h: '18,000',
    shortage: '6,400',
    priority: '重点插单',
    tone: 'red',
  },
  {
    machine: 'A-12#',
    orderNo: 'ZWY260002/B',
    moldName: 'RBCA-08M-01 奶嘴',
    color: '金色',
    target24h: '12,500',
    shortage: '3,980',
    priority: '结转优先',
    tone: 'blue',
  },
  {
    machine: 'A-19#',
    orderNo: 'CMC260301',
    moldName: 'FUGG-07M-01 按钮',
    color: '透明蓝',
    target24h: '-',
    shortage: '5,200',
    priority: '待补目标',
    tone: 'amber',
  },
  {
    machine: '未分配',
    orderNo: 'LWW20260317006/B',
    moldName: 'RC01854 吃尺转动轴',
    color: '黑色',
    target24h: '9,800',
    shortage: '2,800',
    priority: '人工确认',
    tone: 'red',
  },
]

export const injectionManualActionRows: ManualActionRow[] = [
  {
    title: '调整 A-12# 顺序',
    reason: '当前颜色链出现黑后接白',
    owner: '计划员',
    action: '切换顺序或换到 A-19#',
    tone: 'red',
  },
  {
    title: '补 FUGG-07M-01 目标值',
    reason: '缺 24H / 11H 目标导致天数不准',
    owner: '工程 / 生产',
    action: '在模具目标中心补录',
    tone: 'amber',
  },
  {
    title: '确认夜班结转延续',
    reason: '8 条结转已锁定原机台',
    owner: '生产主管',
    action: '进入排机结果页核对',
    tone: 'blue',
  },
]

export const injectionReportingMetrics: ReportingMetric[] = [
  { label: '班次达成率', value: '78%', detail: '白班高于夜班 14 个点', tone: 'green' },
  { label: '当日产值', value: '¥ 42,860', detail: '含啤货工资待复核数据', tone: 'blue' },
  { label: '待入库单', value: '19', detail: 'PMC 当日需清理入库队列', tone: 'amber' },
  { label: '停机异常', value: '2', detail: '1 条调机、1 条缺料', tone: 'red' },
]

export const injectionShiftReportRows: ShiftReportRow[] = [
  { machine: 'A-06#', worker: '陈海', target11h: '8,250', actual: '8,680', variance: '+430', downtime: '无', tone: 'green' },
  { machine: 'A-12#', worker: '李峰', target11h: '5,730', actual: '5,320', variance: '-410', downtime: '换色 35 分钟', tone: 'amber' },
  { machine: 'A-19#', worker: '黄敏', target11h: '4,980', actual: '4,160', variance: '-820', downtime: '目标缺失 + 调机', tone: 'red' },
]

export const injectionWarehouseInboundRows: WarehouseInboundRow[] = [
  { deliveryCode: 'A2511514', orderNo: 'CMC260234', shots: '3,800', materialKg: '295.4', pmc: '陈梦楚', status: '待入库', tone: 'amber' },
  { deliveryCode: 'A2511515', orderNo: 'ZWY260002/B', shots: '2,400', materialKg: '188.2', pmc: '罗良庆', status: '已入库', tone: 'green' },
  { deliveryCode: 'A2511516', orderNo: 'CMC260301', shots: '1,650', materialKg: '102.0', pmc: '陈梦楚', status: '待核对', tone: 'red' },
]

export const injectionConfigRuleCards: ConfigRuleCard[] = [
  {
    title: '排机规则优先级',
    owner: '计划规则',
    summary: '决定同模同机、结转优先、颜色顺序、啤重匹配和负载均衡的权重。',
    status: '待参数化',
    tone: 'amber',
    items: ['结转优先', '同套模强制同机', '颜色浅到深', '啤重 / 吨位适配'],
  },
  {
    title: '模具 → 机台映射',
    owner: '人工学习映射',
    summary: '计划员人工改过一次机台后，系统会记住并在下次排产时优先命中。',
    status: '已接入',
    tone: 'green',
    items: ['MCKP-17M-01 → A-06#', 'RBCA-08M-01 → A-12#', 'MNVN-17M-01 → A-23#'],
  },
  {
    title: '颜色 / 料型例外规则',
    owner: '生产工艺',
    summary: '识别黑转白、特殊料型、五轴双臂需求等例外场景。',
    status: '待补',
    tone: 'red',
    items: ['黑后接白需人工确认', 'TPE / PVC 特殊料型优先固定机台', '三板模优先五轴双臂'],
  },
  {
    title: '组织与权限',
    owner: '管理员',
    summary: '区分计划员、生产主管、PMC、文员对数据中心、执行页和回报页的操作权限。',
    status: '基础已就绪',
    tone: 'blue',
    items: ['计划员可排机', '生产主管可微调', 'PMC 可看回报与入库', '文员可维护订单池'],
  },
]

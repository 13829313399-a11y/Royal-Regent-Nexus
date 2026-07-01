import type { Tone } from '@/data/enterpriseMock'
import {
  huaxingMachineImportSummary,
  huaxingMachineMasterImportRows,
  huaxingMachineProfileImportRows,
} from '@/data/huaxingMachineImport'
import {
  huaxingMoldImportSummary,
  huaxingMoldTargetCardImportRows,
  huaxingMoldTargetDetailImportRows,
} from '@/data/huaxingMoldImport'
import {
  huaxingOrderImportSummary,
  huaxingPendingOrderImportDetailRows,
  huaxingPendingOrderImportRows,
} from '@/data/huaxingOrderImport'
import {
  injectionPendingOrderFieldGroups,
  injectionSectionNav,
  type InjectionModuleData,
} from '@/data/injectionSchedulingMock'
import {
  createSharedInjectionConfigRuleCards,
  sharedInjectionWorkflowStages,
} from '@/factories/injection/rules'

const topHuaxingMoldCustomers = Object.entries(huaxingMoldImportSummary.customerCounts)
  .filter(([customer]) => customer !== '废模')
  .sort((left, right) => right[1] - left[1])
  .slice(0, 3)
  .map(([customer, count]) => `${customer} ${count} 套`)
  .join(' · ')

const topHuaxingOrderMaterials = huaxingOrderImportSummary.topMaterials
  .slice(0, 3)
  .map((item) => `${item.label} ${item.count} 单`)
  .join(' · ')

const topHuaxingOrderColors = huaxingOrderImportSummary.topColors
  .slice(0, 3)
  .map((item) => `${item.label} ${item.count} 单`)
  .join(' · ')

const injectionOverviewMetrics = [
  {
    label: '待排订单',
    value: `${huaxingOrderImportSummary.pendingOrderCount}`,
    detail: `交期风险 ${huaxingOrderImportSummary.overdueCount} · 待分机 ${huaxingOrderImportSummary.missingMachineCount}`,
    tone: 'amber',
  },
  {
    label: '结转 / 转模',
    value: `${huaxingOrderImportSummary.remarkTransitionCount}`,
    detail: '来源于日排版表转模 / 转色备注，后续再与真实结转口径对齐',
    tone: 'blue',
  },
  { label: '运行机台', value: '28 / 34', detail: '稼动率 82.4% · 空闲 6 台', tone: 'teal' },
  {
    label: '排产异常',
    value: `${huaxingOrderImportSummary.overdueCount + huaxingOrderImportSummary.missingMachineCount}`,
    detail: `交期风险 ${huaxingOrderImportSummary.overdueCount} · 机台待确认 ${huaxingOrderImportSummary.missingMachineCount}`,
    tone: 'red',
  },
] as const

const injectionShiftSummaries = [
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
] as const

const injectionMachineLoad = [
  { machine: '新车间-04#', utilization: 92, mold: 'MCKP-17M-01', material: 'ABS KF-740', tone: 'green', queueDepth: '排程 3 条' },
  { machine: '老车间-13#', utilization: 88, mold: 'RBCEZ-05M-01', material: 'PP 本白', tone: 'teal', queueDepth: '排程 2 条' },
  { machine: '老车间-11#', utilization: 73, mold: 'FUGG-07M-01', material: 'TPE 透明', tone: 'blue', queueDepth: '排程 2 条' },
  { machine: '新车间-05#', utilization: 66, mold: 'MNVN-17M-01', material: 'ABS 黑', tone: 'amber', queueDepth: '结转 1 条' },
  { machine: '新车间-17#', utilization: 54, mold: 'RBCA-08M-01', material: 'LDPE 金色', tone: 'amber', queueDepth: '待确认 1 条' },
  { machine: '吹气机台（待建档）', utilization: 28, mold: '吹气机台', material: '未分配', tone: 'red', queueDepth: '异常 1 条' },
] as const

const injectionColorTransitionRisks = [
  { machine: '新车间-04#', route: ['本白', '浅灰', '银', '黑'], risk: '顺序健康', tone: 'green' },
  { machine: '老车间-13#', route: ['透明', '蓝', '黑', '白'], risk: '黑后接白，需人工确认', tone: 'red' },
  { machine: '老车间-11#', route: ['米黄', '橙', '红'], risk: '顺序健康', tone: 'green' },
  { machine: '新车间-05#', route: ['黑', '白'], risk: '逆序，建议换台或重排', tone: 'red' },
] as const

const injectionDataSourceStatus = [
  {
    name: '订单池',
    freshness: `${huaxingOrderImportSummary.importedAt} 导入`,
    status: '正常',
    statusTone: 'green',
    summary: `华兴日排版表已接入 ${huaxingOrderImportSummary.pendingOrderCount} 条待排订单，当前交期风险 ${huaxingOrderImportSummary.overdueCount} 条，待分机 ${huaxingOrderImportSummary.missingMachineCount} 条。`,
  },
  {
    name: '机台主数据',
    freshness: '昨日同步',
    status: '待补',
    statusTone: 'amber',
    summary: `已导入 ${huaxingMachineImportSummary.rowCount} 台设备（新车间 ${huaxingMachineImportSummary.areas['新车间']} / 老车间 ${huaxingMachineImportSummary.areas['老车间']}），但工艺限制仍有部分停留在备注自由文本。`,
  },
  {
    name: '模具目标',
    freshness: '3 天前维护',
    status: '风险',
    statusTone: 'red',
    summary: `华兴模具总表已接入 ${huaxingMoldImportSummary.rowCount} 条明细（在册 ${huaxingMoldImportSummary.activeRowCount} / 废模 ${huaxingMoldImportSummary.scrapRowCount}），但 24H / 11H、穴数、节拍和优选机台仍待补录。`,
  },
  {
    name: '历史数据库',
    freshness: '实时回写',
    status: '正常',
    statusTone: 'green',
    summary: '历史命中率可用于啤重与同模机台匹配，当前样本 1,248 条。',
  },
] as const

const injectionExecutionTasks = [
  { title: '老车间-13# 黑转白风险待确认', meta: '需要计划员调整顺序或切换机台', tone: 'red' },
  { title: '华兴模具目标待补', meta: `已接入 ${huaxingMoldImportSummary.activeRowCount} 套在册模具，但 24H / 11H 和优选机台仍未正式建档`, tone: 'amber' },
  { title: '夜班 8 条结转已锁定原机台', meta: '系统已按原机延续，可进入人工微调', tone: 'blue' },
  { title: '入库单与排产回写待打通', meta: '建议下一步接日报 / 入库联动', tone: 'teal' },
] as const

const injectionDataCenterDatasets = [
  {
    name: '订单主数据',
    owner: '计划 / 文员',
    freshness: `${huaxingOrderImportSummary.importedAt} / 日排版表`,
    completeness: 84,
    status: '已接入',
    statusTone: 'green',
    summary: `已导入华兴日排版表待排订单 ${huaxingOrderImportSummary.pendingOrderCount} 条，主要料型为 ${topHuaxingOrderMaterials}。`,
    issues: [
      `交期风险 ${huaxingOrderImportSummary.overdueCount} 条`,
      `待分机 ${huaxingOrderImportSummary.missingMachineCount} 条`,
      `高频颜色 ${topHuaxingOrderColors}`,
    ],
  },
  {
    name: '机台主数据',
    owner: '生产主管',
    freshness: '昨日',
    completeness: 88,
    status: '待补',
    statusTone: 'amber',
    summary: `已收到 ${huaxingMachineImportSummary.rowCount} 台机台台账，吨位、机械手和周边设备基础信息可用，但工艺适配和活跃模具仍需结构化。`,
    issues: ['PVC / PC / 抽芯限制仍写在备注里', '活跃模具与保养日期尚未结构化'],
  },
  {
    name: '模具目标数据',
    owner: '工程 / 生产',
    freshness: '总表已导入',
    completeness: 38,
    status: '风险',
    statusTone: 'red',
    summary: `已接入华兴模具总表 ${huaxingMoldImportSummary.rowCount} 条明细，客户分布以 ${topHuaxingMoldCustomers} 为主，但目标产能字段仍未结构化。`,
    issues: ['标题口径 1923 套与明细 1932 套存在 9 套差异待核对', '废模区另标注无模号 21 套，需单独补编号'],
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
] as const

const injectionOrderSnapshotRows = huaxingPendingOrderImportDetailRows
  .slice(0, 4)
  .map((row) => ({
    orderNo: row.orderNo,
    productCode: row.productCode,
    moldName: `${row.moldCode} ${row.productName}`,
    color: row.color,
    material: row.material,
    quantity: row.shortageQty,
    due: row.deliveryEnd,
    state: row.overdue ? '交期风险' : row.machine ? '待排' : '待分机',
    tone: row.overdue ? 'red' : row.machine ? 'amber' : 'blue',
  })) satisfies InjectionModuleData['orderSnapshotRows']

const injectionMachineProfileRows = huaxingMachineProfileImportRows
  .slice(0, 8)
  .map((row) => ({ ...row }))

const injectionMoldTargetRows = huaxingMoldTargetCardImportRows.map((row) => ({ ...row }))

const injectionExecutionQueueRows = [
  {
    machine: '新车间-04#',
    orderNo: 'CMC260234',
    moldName: 'MCKP-17M-01 喷水',
    color: '877C 金属银',
    target24h: '18,000',
    shortage: '6,400',
    priority: '重点插单',
    tone: 'red',
  },
  {
    machine: '老车间-13#',
    orderNo: 'ZWY260002/B',
    moldName: 'RBCA-08M-01 奶嘴',
    color: '金色',
    target24h: '12,500',
    shortage: '3,980',
    priority: '结转优先',
    tone: 'blue',
  },
  {
    machine: '老车间-11#',
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
] as const

const machineCountByTone = huaxingMachineMasterImportRows.reduce(
  (accumulator, row) => {
    accumulator[row.tone] = (accumulator[row.tone] ?? 0) + 1
    return accumulator
  },
  {} as Record<Tone, number>,
)

const specialProcessMachines = huaxingMachineMasterImportRows.filter(
  (row) =>
    row.processRange.includes('PVC')
    || row.processRange.includes('PC')
    || row.processRange.includes('不适合PVC')
    || row.processRange.includes('全电动机')
    || row.processRange.includes('立式')
    || row.processRange.includes('双色'),
)

const cautionMachines = huaxingMachineMasterImportRows.filter(
  (row) => row.status !== '运行' || row.maintenance.includes('抽芯') || row.maintenance.includes('不稳定'),
)

const injectionExecutionRuleMetrics = [
  {
    label: '设备台账',
    value: `${huaxingMachineImportSummary.rowCount} 台`,
    detail: `新车间 ${huaxingMachineImportSummary.areas['新车间']} · 老车间 ${huaxingMachineImportSummary.areas['老车间']}`,
    tone: 'teal',
  },
  {
    label: '五轴双臂',
    value: `${huaxingMachineImportSummary.robotTypes['五轴双臂']} 台`,
    detail: '三板模 / 热流道 / 细水口优先进入这组候选池',
    tone: 'blue',
  },
  {
    label: '特殊工艺机',
    value: `${specialProcessMachines.length} 台`,
    detail: '包含 PVC / PC / 全电动 / 立式 / 双色 等非普通通用机台',
    tone: 'amber',
  },
  {
    label: '注意 / 新购',
    value: `${(machineCountByTone.amber ?? 0) + (machineCountByTone.blue ?? 0)} 台`,
    detail: `注意 ${machineCountByTone.amber ?? 0} · 新购 ${machineCountByTone.blue ?? 0}`,
    tone: 'red',
  },
] as const

const injectionExecutionConstraintRows = [
  ...specialProcessMachines.slice(0, 4).map((row) => ({
    machine: row.machine,
    workshop: row.workshop,
    tonnage: row.tonnage,
    robot: row.robot,
    limit: `${row.processRange} / ${row.colorPolicy}`,
    action: row.maintenance,
    tone: row.tone,
  })),
  ...cautionMachines
    .filter((row) => !specialProcessMachines.some((machine) => machine.machine === row.machine))
    .slice(0, 4)
    .map((row) => ({
      machine: row.machine,
      workshop: row.workshop,
      tonnage: row.tonnage,
      robot: row.robot,
      limit: `${row.processRange} / ${row.status}`,
      action: row.maintenance,
      tone: row.tone,
    })),
]

const injectionExecutionCandidateRows = [
  {
    orderNo: 'CMC260234',
    moldCode: 'MCKP-17M-01',
    recommendedMachine: '新车间-04#',
    backupMachine: '新车间-05#',
    reason: '重点插单 + ABS + 同模历史命中，优先保留五轴双臂候选池。',
    blocker: '已映射到真实设备编码，下一步只差把模具映射和真实订单池一起接进来。',
    tone: 'green',
  },
  {
    orderNo: 'ZWY260002/B',
    moldCode: 'RBCA-08M-01',
    recommendedMachine: '老车间-13#',
    backupMachine: '吹气机台（待建档）',
    reason: '夜班结转优先，优先延续原机台，不参与普通新单抢机。',
    blocker: '存在颜色链黑后接白风险，需要计划员确认顺序。',
    tone: 'amber',
  },
  {
    orderNo: 'LWW20260317006/B',
    moldCode: 'RC01854',
    recommendedMachine: '待确认',
    backupMachine: '新车间-08# / 老车间-39#',
    reason: '黑色 ABS 小件，理论可落三轴单臂小机，但当前缺色粉号与标准机台映射。',
    blocker: '缺色粉号 / 缺建议机台，不能直接进入自动排机。',
    tone: 'red',
  },
  {
    orderNo: 'CMC260301',
    moldCode: 'FUGG-07M-01',
    recommendedMachine: '老车间-11#',
    backupMachine: '新车间-02# / 新车间-03#',
    reason: 'TPE / 透明料优先固定机台，且需参考五轴双臂与透明料经验。',
    blocker: '缺 24H / 11H 目标值，天数与优先级仍需人工补齐。',
    tone: 'amber',
  },
] as const

const injectionExecutionScheduleRows = [
  {
    orderNo: 'CMC260234',
    machine: '新车间-04#',
    startWindow: '07-01 白班 08:30',
    endWindow: '07-02 白班 11:00',
    shiftPlan: '白班开机 + 夜班续产',
    expectedOutput: '预计完成 8,600 / 余量 0',
    dependency: '银粉号与上料确认已齐，可直接锁机下发。',
    tone: 'green',
  },
  {
    orderNo: 'ZWY260002/B',
    machine: '老车间-13#',
    startWindow: '承接 06-30 夜班',
    endWindow: '07-01 白班 15:30',
    shiftPlan: '结转延续，不换模',
    expectedOutput: '预计完成 4,138 / 余量 0',
    dependency: '需先确认黑转白顺序，确认后按原机台延续。',
    tone: 'amber',
  },
  {
    orderNo: 'CMC260301',
    machine: '老车间-11#',
    startWindow: '07-01 夜班待定',
    endWindow: '补齐目标后重算',
    shiftPlan: '先预留半班产能',
    expectedOutput: '当前只能预估 4,100 - 4,600',
    dependency: '缺 24H / 11H 目标，未满足自动下发条件。',
    tone: 'red',
  },
] as const

const injectionManualActionRows = [
  {
    title: '调整老车间-13#顺序',
    reason: '当前颜色链出现黑后接白',
    owner: '计划员',
    action: '切换顺序或换到老车间-11#',
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
] as const

const injectionReportingMetrics = [
  { label: '班次达成率', value: '78%', detail: '白班高于夜班 14 个点', tone: 'green' },
  { label: '当日产值', value: '¥ 42,860', detail: '含啤货工资待复核数据', tone: 'blue' },
  { label: '待入库单', value: '19', detail: 'PMC 当日需清理入库队列', tone: 'amber' },
  { label: '停机异常', value: '2', detail: '1 条调机、1 条缺料', tone: 'red' },
] as const

const injectionShiftReportRows = [
  { machine: '新车间-04#', worker: '陈海', target11h: '8,250', actual: '8,680', variance: '+430', downtime: '无', tone: 'green' },
  { machine: '老车间-13#', worker: '李峰', target11h: '5,730', actual: '5,320', variance: '-410', downtime: '换色 35 分钟', tone: 'amber' },
  { machine: '老车间-11#', worker: '黄敏', target11h: '4,980', actual: '4,160', variance: '-820', downtime: '目标缺失 + 调机', tone: 'red' },
] as const

const injectionWarehouseInboundRows = [
  { deliveryCode: 'A2511514', orderNo: 'CMC260234', shots: '3,800', materialKg: '295.4', pmc: '陈梦楚', status: '待入库', tone: 'amber' },
  { deliveryCode: 'A2511515', orderNo: 'ZWY260002/B', shots: '2,400', materialKg: '188.2', pmc: '罗良庆', status: '已入库', tone: 'green' },
  { deliveryCode: 'A2511516', orderNo: 'CMC260301', shots: '1,650', materialKg: '102.0', pmc: '陈梦楚', status: '待核对', tone: 'red' },
] as const

const injectionConfigRuleCards = createSharedInjectionConfigRuleCards(
  huaxingMoldTargetCardImportRows.map((row) => `${row.moldCode} → 待补机台映射`),
)

const injectionPendingOrderValidationRules = [
  {
    label: '交期风险',
    hit: `${huaxingOrderImportSummary.overdueCount} 单`,
    detail: '交期差为负值的订单已直接打上风险标记，后续应优先进入排机执行页。',
    tone: 'red',
  },
  {
    label: '待分机',
    hit: `${huaxingOrderImportSummary.missingMachineCount} 单`,
    detail: '日排版表中当前未挂机台的订单，需要先补机台候选池或人工锁机。',
    tone: 'amber',
  },
  {
    label: '转模 / 转色',
    hit: `${huaxingOrderImportSummary.remarkTransitionCount} 单`,
    detail: '备注里已识别出转模、转色、水口等切换动作，后续可联动换模时长规则。',
    tone: 'blue',
  },
  {
    label: '导入重复校验',
    hit: `${huaxingOrderImportSummary.duplicateOrderCount} 单`,
    detail: '当前按单号 + 模号 + 机台 + 计划开始期去重，本轮导入未发现重复排程行。',
    tone: 'green',
  },
] as const

const injectionOrderImportTasks = [
  {
    step: '订单标准字段',
    owner: '计划 / 文员',
    status: '已定义',
    detail: `已经抽出 ${injectionPendingOrderFieldGroups.reduce((count, group) => count + group.fields.length, 0)} 个待排核心字段，后续华兴只需往标准表灌数据。`,
    tone: 'green',
  },
  {
    step: '华兴订单池导入',
    owner: '计划',
    status: '已导入',
    detail: `已从日排版表导入 ${huaxingOrderImportSummary.pendingOrderCount} 条待排订单，当前已能承接真实订单池。`,
    tone: 'green',
  },
  {
    step: '模具编码关联',
    owner: '工程 / 生产',
    status: '模具总表已接',
    detail: `华兴模具总表已接入 ${huaxingMoldImportSummary.activeRowCount} 套在册模具，下一步把订单模具编码和总表编码正式关联。`,
    tone: 'blue',
  },
  {
    step: '结转 / 入库回写',
    owner: 'PMC / 系统',
    status: '待打通',
    detail: '当前结转、日报、入库回写还在页面模拟层，尚未接真实闭环数据。',
    tone: 'red',
  },
] as const

const injectionPendingOrderDetailRows = huaxingPendingOrderImportRows.map((row) => ({ ...row }))

const injectionMachineMasterRows = huaxingMachineMasterImportRows
  .slice(0, 12)
  .map((row) => ({ ...row }))

const injectionMoldTargetDetailRows = huaxingMoldTargetDetailImportRows.map((row) => ({ ...row }))

const injectionMoldMachineMappingRows = [
  {
    moldCode: 'ES-20250037-10',
    customer: '施信',
    productName: '36寸骷髅人-左后小手骨',
    candidatePool: '高速 150T-200T / 五轴双臂优先',
    recommendedMachine: '新车间-25#',
    backupMachine: '新车间-27# / 老车间-11#',
    status: '待补料型确认',
    detail: '模号已入总表，但穴数、料型和24H目标未补齐，先给高速小吨位候选池。',
    tone: 'amber',
  },
  {
    moldCode: '41769A-019-01',
    customer: '巴士比',
    productName: '8粒子弹盒',
    candidatePool: '高速 150T / 三轴单臂可候选',
    recommendedMachine: '老车间-30#',
    backupMachine: '新车间-21# / 新车间-22#',
    status: '候选已给',
    detail: '可先进入高速小吨位候选池，后续根据真实颜色和单位啤重确认是否锁五轴。',
    tone: 'blue',
  },
  {
    moldCode: '20 308 9510-006',
    customer: '迪奇',
    productName: '涡轮盖/C形环扣',
    candidatePool: '普通 / 高速 200T-260T',
    recommendedMachine: '新车间-04#',
    backupMachine: '新车间-05# / 老车间-05#',
    status: '待补目标值',
    detail: '当前缺24H / 11H目标，先按260T通用高速机台给建议池，不能直接下发。',
    tone: 'amber',
  },
  {
    moldCode: 'T01-01010-00500000',
    customer: 'EDU',
    productName: '弹球',
    candidatePool: '小吨位高速 / 全电动待确认',
    recommendedMachine: '新车间-32#',
    backupMachine: '老车间-17# / 老车间-18#',
    status: '需工程确认',
    detail: '产品名较轻小，先放进小吨位候选池；最终还要看料型和颜色策略决定是否走PVC或普通机。',
    tone: 'red',
  },
] as const

const injectionShiftReportChecklistItems = [
  {
    title: '白班实际产量回报',
    owner: '车间组长',
    status: '待提交',
    detail: '老车间-11# 透明按钮因目标缺失暂未锁日报。',
    tone: 'amber',
  },
  {
    title: '夜班停机原因归档',
    owner: '生产主管',
    status: '已完成',
    detail: '2 条停机已区分为换色和缺料，允许月结统计。',
    tone: 'green',
  },
  {
    title: '结转交接确认',
    owner: 'PMC / 计划',
    status: '待确认',
    detail: '8 条结转需确认原机锁定是否延续到白班。',
    tone: 'blue',
  },
  {
    title: '入库与欠数回写',
    owner: '仓库 / PMC',
    status: '风险',
    detail: '2 张送货单已入库但欠数未回写排产池。',
    tone: 'red',
  },
] as const

const injectionShiftHandoverRows = [
  {
    shift: '夜班 → 白班',
    machine: '老车间-13#',
    orderNo: 'ZWY260002/B',
    carryOverQty: '1,740',
    nextOwner: '白班组长',
    note: '维持原机延续，禁止先切白色单。',
    tone: 'blue',
  },
  {
    shift: '夜班 → 白班',
    machine: '老车间-11#',
    orderNo: 'CMC260301',
    carryOverQty: '2,960',
    nextOwner: '计划员',
    note: '待补模具目标后再锁今日天数。',
    tone: 'amber',
  },
  {
    shift: '白班 → 夜班',
    machine: '新车间-04#',
    orderNo: 'CMC260234',
    carryOverQty: '4,800',
    nextOwner: '夜班组长',
    note: '重点插单，优先保机不中断。',
    tone: 'red',
  },
] as const

const injectionInboundWritebackRows = [
  {
    deliveryCode: 'A2511514',
    orderNo: 'CMC260234',
    inboundQty: '3,800',
    shortageAfter: '4,800',
    warehouseStatus: '待入库',
    erpStatus: '未回写',
    schedulerStatus: '待更新',
    owner: 'PMC 陈梦楚',
    tone: 'amber',
  },
  {
    deliveryCode: 'A2511515',
    orderNo: 'ZWY260002/B',
    inboundQty: '2,400',
    shortageAfter: '1,738',
    warehouseStatus: '已入库',
    erpStatus: '已回写',
    schedulerStatus: '已更新',
    owner: '仓库 罗良庆',
    tone: 'green',
  },
  {
    deliveryCode: 'A2511516',
    orderNo: 'CMC260301',
    inboundQty: '1,650',
    shortageAfter: '3,550',
    warehouseStatus: '待核对',
    erpStatus: '待回写',
    schedulerStatus: '排产池未刷新',
    owner: 'PMC 陈梦楚',
    tone: 'red',
  },
] as const

export const huaxingInjectionModuleData: InjectionModuleData = {
  sectionNav: injectionSectionNav,
  overviewMetrics: [...injectionOverviewMetrics],
  shiftSummaries: [...injectionShiftSummaries],
  machineLoad: [...injectionMachineLoad],
  colorTransitionRisks: injectionColorTransitionRisks.map((row) => ({ ...row, route: [...row.route] })),
  dataSourceStatus: [...injectionDataSourceStatus],
  executionTasks: [...injectionExecutionTasks],
  workflowStages: sharedInjectionWorkflowStages.map((row) => ({ ...row })),
  dataCenterDatasets: injectionDataCenterDatasets.map((row) => ({ ...row, issues: [...row.issues] })),
  orderSnapshotRows: [...injectionOrderSnapshotRows],
  machineProfileRows: injectionMachineProfileRows,
  moldTargetRows: injectionMoldTargetRows,
  executionQueueRows: [...injectionExecutionQueueRows],
  executionRuleMetrics: [...injectionExecutionRuleMetrics],
  executionConstraintRows: injectionExecutionConstraintRows,
  executionCandidateRows: [...injectionExecutionCandidateRows],
  executionScheduleRows: [...injectionExecutionScheduleRows],
  manualActionRows: [...injectionManualActionRows],
  reportingMetrics: [...injectionReportingMetrics],
  shiftReportRows: [...injectionShiftReportRows],
  warehouseInboundRows: [...injectionWarehouseInboundRows],
  configRuleCards: injectionConfigRuleCards.map((row) => ({ ...row, items: [...row.items] })),
  pendingOrderFieldGroups: injectionPendingOrderFieldGroups.map((group) => ({
    ...group,
    fields: group.fields.map((field) => ({ ...field })),
  })),
  pendingOrderValidationRules: [...injectionPendingOrderValidationRules],
  orderImportTasks: [...injectionOrderImportTasks],
  pendingOrderDetailRows: [...injectionPendingOrderDetailRows],
  machineMasterRows: injectionMachineMasterRows,
  moldTargetDetailRows: injectionMoldTargetDetailRows,
  moldMachineMappingRows: [...injectionMoldMachineMappingRows],
  shiftReportChecklistItems: [...injectionShiftReportChecklistItems],
  shiftHandoverRows: [...injectionShiftHandoverRows],
  inboundWritebackRows: [...injectionInboundWritebackRows],
}

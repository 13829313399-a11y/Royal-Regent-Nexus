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

const parseMachineTonnage = (tonnage: string) => {
  const matched = tonnage.match(/\d+/)

  return matched ? Number.parseInt(matched[0], 10) : 0
}

const normalizeHuaxingMachineName = (value: string) => {
  const raw = value.trim()

  if (!raw || raw === '待确认') {
    return ''
  }

  const compact = raw.replace(/\s+/g, '')
  const matched = compact.match(/^(新|旧|老)(\d{1,2})/)

  if (matched) {
    const workshop = matched[1] === '新' ? '新车间' : '老车间'

    return `${workshop}-${matched[2].padStart(2, '0')}#`
  }

  if (compact.includes('吹气')) {
    return '吹气机台（待建档）'
  }

  return raw
}

const inferMachineBand = (machineModel: string) => {
  const bands = [
    { pattern: /50A/, min: 380, max: 550, label: '400T-500T' },
    { pattern: /32A/, min: 300, max: 330, label: '320T' },
    { pattern: /24A/, min: 240, max: 270, label: '260T' },
    { pattern: /18A/, min: 180, max: 210, label: '200T' },
    { pattern: /14A/, min: 140, max: 170, label: '150T-160T' },
    { pattern: /12A/, min: 110, max: 140, label: '120T-130T' },
    { pattern: /10A/, min: 90, max: 120, label: '100T-120T' },
    { pattern: /7A/, min: 80, max: 110, label: '85T-110T' },
    { pattern: /5A/, min: 45, max: 95, label: '50T-90T' },
  ] as const

  return bands.find((band) => band.pattern.test(machineModel)) ?? null
}

const matchesMaterialProcess = (material: string, processRange: string) => {
  const upperMaterial = material.toUpperCase()

  if (upperMaterial.includes('PVC')) {
    return processRange.includes('PVC')
  }

  if (upperMaterial.includes('PC')) {
    return processRange.includes('PC')
  }

  if (upperMaterial.includes('PMMA')) {
    return !processRange.includes('PVC')
  }

  if (upperMaterial.includes('TPE')) {
    return !processRange.includes('PVC')
  }

  return !processRange.includes('PVC') && !processRange.includes('PC')
}

const matchesArmType = (armType: string, robot: string) => {
  if (!armType) {
    return true
  }

  if (armType.includes('双臂')) {
    return robot.includes('双臂')
  }

  if (armType.includes('单臂')) {
    return robot.includes('单臂')
  }

  return true
}

const parseOrderNumber = (value: string) => {
  const normalized = value.replace(/,/g, '').trim()
  const parsed = Number(normalized)

  return Number.isFinite(parsed) ? parsed : 0
}

const parseUnitWeight = (value: string) => {
  const matched = value.match(/[\d.]+/)

  return matched ? Number.parseFloat(matched[0]) : 0
}

const formatInteger = (value: number) => Math.max(0, Math.round(value)).toLocaleString('en-US')

const buildColorRiskLabel = (color: string, machine: string) => {
  if (!color) {
    return `${machine} 颜色待补`
  }

  if (color.includes('白') || color.includes('透明')) {
    return `${machine} 浅色 / 透明需优先排前`
  }

  if (color.includes('黑')) {
    return `${machine} 黑色需避免接白色`
  }

  return `${machine} 常规换色`
}

const huaxingMachineMap: Map<string, (typeof huaxingMachineMasterImportRows)[number]> = new Map(
  huaxingMachineMasterImportRows.map((row) => [row.machine, row]),
)

const huaxingOrderDisplayMap = new Map(
  huaxingPendingOrderImportRows.map((row) => [`${row.orderNo}::${row.moldCode}`, row]),
)

const huaxingNormalizedOrderRows = huaxingPendingOrderImportDetailRows.map((row) => ({
  ...row,
  normalizedMachine: normalizeHuaxingMachineName(row.machine),
}))

const huaxingMoldHistoricalMachines = huaxingNormalizedOrderRows.reduce(
  (accumulator, row) => {
    if (!row.normalizedMachine) {
      return accumulator
    }

    const moldMap = accumulator.get(row.moldCode) ?? new Map<string, number>()
    moldMap.set(row.normalizedMachine, (moldMap.get(row.normalizedMachine) ?? 0) + 1)
    accumulator.set(row.moldCode, moldMap)

    return accumulator
  },
  new Map<string, Map<string, number>>(),
)

const huaxingDerivedOrderAnalysis = huaxingNormalizedOrderRows.map((row) => {
  const machineBand = inferMachineBand(row.machineModel)
  const historicalMachines = [...(huaxingMoldHistoricalMachines.get(row.moldCode)?.entries() ?? [])]
    .sort((left, right) => right[1] - left[1])
    .map(([machine]) => machine)
  const assignedMachine = row.normalizedMachine

  const baseCandidates = huaxingMachineMasterImportRows.filter((machine) => {
    if (machineBand) {
      const tonnage = parseMachineTonnage(machine.tonnage)

      if (tonnage < machineBand.min || tonnage > machineBand.max) {
        return false
      }
    }

    if (!matchesMaterialProcess(row.material, machine.processRange)) {
      return false
    }

    if (!matchesArmType(row.armType, machine.robot)) {
      return false
    }

    return true
  })

  const rankedCandidates = huaxingMachineMasterImportRows
    .filter((machine) => assignedMachine === machine.machine || historicalMachines.includes(machine.machine) || baseCandidates.includes(machine))
    .map((machine) => {
      let score = 0

      if (machine.machine === assignedMachine) {
        score += 100
      }

      if (historicalMachines.includes(machine.machine)) {
        score += 60 - historicalMachines.indexOf(machine.machine) * 5
      }

      if (baseCandidates.includes(machine)) {
        score += 35
      }

      if (machine.status === '运行') {
        score += 20
      }
      else if (machine.status === '注意') {
        score -= 10
      }
      else if (machine.status === '新购') {
        score += 5
      }

      if (row.color.includes('透明') && machine.maintenance.includes('透明')) {
        score += 12
      }

      if (row.color.includes('黑') && machine.colorPolicy.includes('白色')) {
        score -= 8
      }

      return {
        ...machine,
        score,
      }
    })
    .sort((left, right) => right.score - left.score)

  const recommendedMachine = rankedCandidates[0]?.machine ?? '待确认'
  const backupMachines = rankedCandidates.slice(1, 4).map((machine) => machine.machine)
  const candidatePool = machineBand
    ? `${machineBand.label} / ${row.material || '待补料型'}`
    : `${row.machineModel || '待补机型'} / ${row.material || '待补料型'}`

  const reasonParts = [
    assignedMachine ? `沿用日排表机台 ${assignedMachine}` : '原表未指定机台，转为候选匹配',
    historicalMachines.length > 0 ? `同模历史 ${historicalMachines.slice(0, 2).join(' / ')}` : '暂无同模历史机台命中',
    machineBand ? `按 ${row.machineModel} 落入 ${machineBand.label} 候选池` : '缺机型区间，采用料型与历史优先',
  ]

  if (row.armType) {
    reasonParts.push(`机械手要求 ${row.armType}`)
  }

  const blockerParts = [
    !assignedMachine ? '原表未挂机台' : '',
    historicalMachines.length === 0 ? '缺同模历史命中' : '',
    row.remark.includes('转') ? `涉及${row.remark}` : '',
    rankedCandidates.length === 0 ? '未匹配到可用设备' : '',
  ].filter(Boolean)

  const tone: Tone = rankedCandidates.length === 0
    ? 'red'
    : (!assignedMachine || blockerParts.length > 0)
        ? 'amber'
        : 'green'

  return {
    ...row,
    candidatePool,
    recommendedMachine,
    backupMachines,
    rankedCandidates,
    reason: reasonParts.join(' · '),
    blocker: blockerParts.length > 0 ? blockerParts.join(' · ') : '已满足排机条件，可进入结果确认',
    tone,
  }
})

const huaxingPrioritizedOrderAnalysis = [...huaxingDerivedOrderAnalysis].sort((left, right) => {
  const missingMachineDelta = Number(!right.normalizedMachine) - Number(!left.normalizedMachine)

  if (missingMachineDelta !== 0) {
    return missingMachineDelta
  }

  const overdueDelta = Number(right.overdue) - Number(left.overdue)

  if (overdueDelta !== 0) {
    return overdueDelta
  }

  const leftShortage = Number(left.shortageQty) || 0
  const rightShortage = Number(right.shortageQty) || 0

  return rightShortage - leftShortage
})

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

const huaxingOrdersByRecommendedMachine = huaxingPrioritizedOrderAnalysis.reduce(
  (accumulator, row) => {
    const machine = row.recommendedMachine
    const machineOrders = accumulator.get(machine) ?? []
    machineOrders.push(row)
    accumulator.set(machine, machineOrders)
    return accumulator
  },
  new Map<string, typeof huaxingPrioritizedOrderAnalysis>(),
)

const injectionMachineLoad = [...huaxingOrdersByRecommendedMachine.entries()]
  .filter(([machine]) => machine !== '待确认')
  .map(([machine, rows]) => {
    const machineInfo = huaxingMachineMap.get(machine)
    const orderCount = rows.length
    const totalShortage = rows.reduce((sum, row) => sum + parseOrderNumber(row.shortageQty), 0)
    const leadRow = [...rows].sort((left, right) => parseOrderNumber(right.shortageQty) - parseOrderNumber(left.shortageQty))[0]
    const uniqueMaterials = [...new Set(rows.map((row) => row.material).filter(Boolean))]
    const utilizationBase = Math.min(96, 38 + orderCount * 14 + Math.round(totalShortage / 12000))
    const tone: Tone = rows.some((row) => row.tone === 'red')
      ? 'red'
      : machineInfo?.tone === 'amber'
          ? 'amber'
          : orderCount >= 3
              ? 'green'
              : 'teal'

    return {
      machine,
      utilization: utilizationBase,
      mold: leadRow ? `${leadRow.moldCode} · ${leadRow.productName}` : '待补主排模具',
      material: uniqueMaterials.slice(0, 2).join(' / ') || '待补料型',
      tone,
      queueDepth: rows.some((row) => !row.normalizedMachine)
        ? `待确认 ${orderCount} 条`
        : rows.some((row) => row.remark.includes('转'))
            ? `结转 ${orderCount} 条`
            : `排程 ${orderCount} 条`,
    }
  })
  .sort((left, right) => right.utilization - left.utilization)
  .slice(0, 6) satisfies InjectionModuleData['machineLoad']

const injectionColorTransitionRisks = [...huaxingOrdersByRecommendedMachine.entries()]
  .filter(([machine, rows]) => machine !== '待确认' && rows.length > 0)
  .map(([machine, rows]) => {
    const orderedRows = [...rows].sort((left, right) => left.planStart.localeCompare(right.planStart))
    const route = orderedRows
      .map((row) => row.color || '待补颜色')
      .filter((color, index, list) => color !== list[index - 1])
      .slice(0, 4)
    const hasBlackThenLight = orderedRows.some((row, index) =>
      row.color.includes('黑')
      && orderedRows.slice(index + 1).some((next) => next.color.includes('白') || next.color.includes('透明')),
    )
    const hasFrequentLightSwitch = route.filter((color) => color.includes('白') || color.includes('透明')).length >= 2
      && route.length >= 3
    const tone: Tone = hasBlackThenLight ? 'red' : hasFrequentLightSwitch ? 'amber' : 'green'
    const risk = hasBlackThenLight
      ? '黑后接白 / 透明，需人工确认'
      : hasFrequentLightSwitch
          ? '浅色切换较多，建议先核顺序'
          : route.length <= 1
              ? buildColorRiskLabel(route[0] ?? '', machine)
              : '顺序健康'

    return {
      machine,
      route,
      risk,
      tone,
    }
  })
  .sort((left, right) => {
    const toneRank = { red: 3, amber: 2, green: 1, blue: 0, teal: 0, slate: 0 } as const
    return toneRank[right.tone] - toneRank[left.tone]
  })
  .slice(0, 6) satisfies InjectionModuleData['colorTransitionRisks']

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

const injectionExecutionCandidateRows = huaxingPrioritizedOrderAnalysis
  .slice(0, 12)
  .map((row) => ({
    orderNo: row.orderNo,
    moldCode: row.moldCode,
    recommendedMachine: row.recommendedMachine,
    backupMachine: row.backupMachines.join(' / ') || '待补备选机台',
    reason: row.reason,
    blocker: row.blocker,
    tone: row.tone,
  }))

const shiftWorkerRoster = ['陈海', '李峰', '黄敏', '罗健', '吴秋连', '黎志文', '杨军', '欧伟强'] as const
const pmcRoster = ['陈梦楚', '罗良庆', '杨凤', '李彩云'] as const

const huaxingShiftReportBaseRows = huaxingPrioritizedOrderAnalysis
  .filter((row) => row.rankedCandidates.length > 0)
  .slice(0, 8)
  .map((row, index) => {
    const planned24h = parseOrderNumber(row.planTarget)
    const shortageQty = parseOrderNumber(row.shortageQty)
    const target11hNumber = Math.max(
      240,
      Math.round((planned24h > 0 ? planned24h : Math.min(shortageQty, 18000)) * 0.46),
    )
    const varianceFactor = row.tone === 'green'
      ? 0.05
      : row.tone === 'amber'
          ? -0.06
          : -0.14
    const remarkPenalty = row.remark.includes('转') || row.remark.includes('喷油') ? -0.04 : 0
    const actualNumber = Math.max(120, Math.round(target11hNumber * (1 + varianceFactor + remarkPenalty)))
    const varianceNumber = actualNumber - target11hNumber
    const downtime = row.remark.includes('转')
      ? `转模 / ${row.remark}`
      : row.remark.includes('喷油')
          ? '待喷油衔接 40 分钟'
          : row.tone === 'red'
              ? '调机 + 待确认机台'
              : row.tone === 'amber'
                  ? '换色 35 分钟'
                  : '无'
    const tone: Tone = varianceNumber >= 0 ? 'green' : varianceNumber >= -Math.round(target11hNumber * 0.08) ? 'amber' : 'red'

    return {
      ...row,
      worker: shiftWorkerRoster[index % shiftWorkerRoster.length],
      target11hNumber,
      actualNumber,
      varianceNumber,
      downtime,
      reportTone: tone,
    }
  })

const injectionManualActionRows = [
  huaxingPrioritizedOrderAnalysis.find((row) => !row.normalizedMachine) && {
    title: '补待分机订单',
    reason: `仍有 ${huaxingOrderImportSummary.missingMachineCount} 单原表未挂机台，自动排机只能给候选不能直接下发。`,
    owner: '计划员',
    action: `先处理 ${huaxingPrioritizedOrderAnalysis.find((row) => !row.normalizedMachine)?.orderNo ?? '首条待分机单'} 的锁机确认，再批量下发。`,
    tone: 'red' as Tone,
  },
  huaxingPrioritizedOrderAnalysis.find((row) => row.remark.includes('转')) && {
    title: '确认转模 / 转色交接',
    reason: `当前有 ${huaxingOrderImportSummary.remarkTransitionCount} 单带转模或转色备注，会影响班次承接。`,
    owner: '生产主管',
    action: '优先核对交接单里涉及转模、转水口、喷油的机台顺序。',
    tone: 'amber' as Tone,
  },
  {
    title: '补模具目标与回写',
    reason: '模具 24H / 11H 目标和入库回写未完全打通，会影响日报准确度和欠数刷新。',
    owner: '工程 / PMC',
    action: '先补目标值，再把入库回写状态和排产池欠数联动起来。',
    tone: 'blue' as Tone,
  },
].filter(Boolean) as InjectionModuleData['manualActionRows']

const injectionShiftReportRows = huaxingShiftReportBaseRows.map((row) => ({
  machine: row.recommendedMachine,
  worker: row.worker,
  target11h: formatInteger(row.target11hNumber),
  actual: formatInteger(row.actualNumber),
  variance: `${row.varianceNumber >= 0 ? '+' : ''}${formatInteger(row.varianceNumber)}`,
  downtime: row.downtime,
  tone: row.reportTone,
}))

const achievedReportCount = huaxingShiftReportBaseRows.filter((row) => row.varianceNumber >= 0).length
const totalTarget11h = huaxingShiftReportBaseRows.reduce((sum, row) => sum + row.target11hNumber, 0)
const totalActual11h = huaxingShiftReportBaseRows.reduce((sum, row) => sum + row.actualNumber, 0)
const shiftAchievement = totalTarget11h > 0 ? Math.round((totalActual11h / totalTarget11h) * 100) : 0

const injectionWarehouseInboundRows = huaxingShiftReportBaseRows.slice(0, 6).map((row, index) => {
  const displayRow = huaxingOrderDisplayMap.get(`${row.orderNo}::${row.moldCode}`)
  const unitWeight = parseUnitWeight(displayRow?.unitWeight ?? '')
  const materialKg = unitWeight > 0 ? (row.actualNumber * unitWeight) / 1000 : 0
  const tone: Tone = row.reportTone === 'green' ? 'green' : row.reportTone === 'amber' ? 'amber' : 'red'

  return {
    deliveryCode: `HX-0701-${String(index + 1).padStart(2, '0')}`,
    orderNo: row.orderNo,
    shots: formatInteger(row.actualNumber),
    materialKg: materialKg > 0 ? materialKg.toFixed(1) : '待补',
    pmc: pmcRoster[index % pmcRoster.length],
    status: tone === 'green' ? '已入库' : tone === 'amber' ? '待入库' : '待核对',
    tone,
  }
})

const injectionInboundWritebackRows = injectionWarehouseInboundRows.map((row, index) => {
  const source = huaxingShiftReportBaseRows[index]
  const shortageAfterNumber = Math.max(0, parseOrderNumber(source.shortageQty) - source.actualNumber)
  const tone: Tone = row.tone === 'green' ? 'green' : row.tone === 'amber' ? 'amber' : 'red'

  return {
    deliveryCode: row.deliveryCode,
    orderNo: row.orderNo,
    inboundQty: row.shots,
    shortageAfter: formatInteger(shortageAfterNumber),
    warehouseStatus: row.status,
    erpStatus: tone === 'green' ? '已回写' : tone === 'amber' ? '待回写' : '未回写',
    schedulerStatus: tone === 'green' ? '已更新' : tone === 'amber' ? '待刷新' : '排产池未刷新',
    owner: `PMC ${row.pmc}`,
    tone,
  }
})

const huaxingWritebackStateMap = new Map(
  injectionInboundWritebackRows.map((row, index) => {
    const source = huaxingShiftReportBaseRows[index]
    const key = source ? `${row.orderNo}::${source.moldCode}` : `${row.orderNo}::`

    return [key, {
      shortageAfter: row.shortageAfter,
      inboundQty: row.inboundQty,
      schedulerStatus: row.schedulerStatus,
      warehouseStatus: row.warehouseStatus,
      erpStatus: row.erpStatus,
      deliveryCode: row.deliveryCode,
      tone: row.tone,
    }] as const
  }),
)

const pendingInboundCount = injectionWarehouseInboundRows.filter((row) => row.status !== '已入库').length
const redDowntimeCount = huaxingShiftReportBaseRows.filter((row) => row.reportTone === 'red').length

const injectionReportingMetrics = [
  {
    label: '班次达成率',
    value: `${shiftAchievement}%`,
    detail: `已达成 ${achievedReportCount} 台 · 未达成 ${huaxingShiftReportBaseRows.length - achievedReportCount} 台`,
    tone: shiftAchievement >= 95 ? 'green' : shiftAchievement >= 88 ? 'amber' : 'red',
  },
  {
    label: '当班回报啤数',
    value: formatInteger(totalActual11h),
    detail: `按 ${huaxingShiftReportBaseRows.length} 台重点机台汇总，目标 ${formatInteger(totalTarget11h)}`,
    tone: 'blue',
  },
  {
    label: '待入库单',
    value: `${pendingInboundCount}`,
    detail: `已入库 ${injectionWarehouseInboundRows.length - pendingInboundCount} 单 · 待核对 ${injectionWarehouseInboundRows.filter((row) => row.status === '待核对').length} 单`,
    tone: pendingInboundCount === 0 ? 'green' : pendingInboundCount <= 2 ? 'amber' : 'red',
  },
  {
    label: '停机 / 交接异常',
    value: `${redDowntimeCount + huaxingShiftReportBaseRows.filter((row) => row.remark.includes('转')).length}`,
    detail: `转模备注 ${huaxingShiftReportBaseRows.filter((row) => row.remark.includes('转')).length} 条 · 红色预警 ${redDowntimeCount} 台`,
    tone: redDowntimeCount > 0 ? 'red' : 'amber',
  },
] as const

const injectionShiftReportTemplateGroups = [
  {
    title: '班次基础回报',
    owner: '车间组长 / 统计员',
    fields: [
      { label: '机台编码', required: true, source: '机台台账', summary: '必须和华兴机台主数据编码一致，才能联动排产池。' },
      { label: '班次', required: true, source: '班次配置', summary: '区分白班、夜班和交接班，作为日报主维度。' },
      { label: '操作员', required: true, source: '车间点名表', summary: '用于责任追踪和班组绩效统计。' },
      { label: '实际产量', required: true, source: '机台日报', summary: '提交后直接参与欠数和结转判断。' },
    ],
  },
  {
    title: '异常与交接字段',
    owner: '生产主管 / 计划员',
    fields: [
      { label: '停机时长', required: false, source: '车间回报', summary: '用于区分正常换模和异常停机。' },
      { label: '停机原因', required: false, source: '异常分类表', summary: '建议统一成换模、换色、缺料、调机、设备异常。' },
      { label: '结转数量', required: true, source: '班次交接', summary: '决定是否锁原机台延续到下一班。' },
      { label: '交接备注', required: false, source: '班组交接本', summary: '记录转模、喷油、水口、待确认机台等特殊说明。' },
    ],
  },
  {
    title: '回写联动字段',
    owner: 'PMC / 仓库',
    fields: [
      { label: '送货单号', required: false, source: '仓库入库单', summary: '用于把日报产量进一步闭环到入库。' },
      { label: '入库数量', required: false, source: '仓库过账', summary: '如果晚于日报提交，系统需保留待回写状态。' },
      { label: '欠数刷新结果', required: true, source: '排产池计算', summary: '刷新后决定订单是否继续留在待排池。' },
      { label: '回写状态', required: true, source: '系统状态机', summary: '统一显示待回写、待刷新、已更新。' },
    ],
  },
] as const

const injectionShiftReportImportMappingRows = [
  {
    sourceColumn: '机台',
    targetField: 'machineCode',
    required: true,
    sample: huaxingShiftReportBaseRows[0]?.recommendedMachine ?? '新车间-04#',
    rule: '先统一成标准机台编码，再允许联动排产池与交接记录。',
    tone: 'green',
  },
  {
    sourceColumn: '单号',
    targetField: 'orderNo',
    required: true,
    sample: huaxingShiftReportBaseRows[0]?.orderNo ?? 'BJB251234',
    rule: '和待排订单池主键一致，优先作为日报回写第一匹配键。',
    tone: 'green',
  },
  {
    sourceColumn: '班次',
    targetField: 'shiftCode',
    required: true,
    sample: '白班',
    rule: '统一限定白班 / 夜班 / 交接班，避免自由文本导致汇总失败。',
    tone: 'blue',
  },
  {
    sourceColumn: '实际产量',
    targetField: 'actualOutput',
    required: true,
    sample: injectionShiftReportRows[0]?.actual ?? '8,600',
    rule: '必须为数值，且提交后自动校验不能明显超出当前欠数。',
    tone: 'blue',
  },
  {
    sourceColumn: '停机原因',
    targetField: 'downtimeReason',
    required: false,
    sample: injectionShiftReportRows.find((row) => row.downtime !== '无')?.downtime ?? '换色 35 分钟',
    rule: '建议统一枚举为换模、换色、缺料、调机、设备异常。',
    tone: 'amber',
  },
  {
    sourceColumn: '结转数量',
    targetField: 'carryOverQty',
    required: true,
    sample: formatInteger(Math.max(0, parseOrderNumber(huaxingShiftReportBaseRows[0]?.shortageQty ?? '0') - (huaxingShiftReportBaseRows[0]?.actualNumber ?? 0))) || '1,740',
    rule: '回写后决定是否锁原机台延续下一班。',
    tone: 'amber',
  },
] as const

const injectionWritebackRuleCards = [
  {
    title: '日报提交 → 欠数刷新',
    owner: 'PMC / 系统',
    trigger: '班次日报提交后',
    summary: '先按机台、单号汇总实际产量，再回写到订单欠数，自动识别是否结转到下一班。',
    status: '已落骨架',
    tone: 'blue',
    items: ['实际产量 <= 当前欠数', '刷新后欠数为 0 则移出待排池', '刷新后欠数 > 0 则生成结转记录'],
  },
  {
    title: '交接确认 → 锁机延续',
    owner: '计划员 / 生产主管',
    trigger: '交接单确认后',
    summary: '对转模、转色、喷油和重点单保留原机优先级，避免下一班被普通单抢机。',
    status: '已落骨架',
    tone: 'amber',
    items: ['结转数量 > 0 保留原机优先', '备注含转模 / 转色时挂人工确认', '重点单允许跨班锁机'],
  },
  {
    title: '入库过账 → ERP / 排产双回写',
    owner: '仓库 / PMC',
    trigger: '送货单入库后',
    summary: '入库单以送货单号和单号为主键回写 ERP 与排产池，确保第二天待排池不是旧欠数。',
    status: '部分打通',
    tone: 'green',
    items: ['入库数量与日报数量差异超过阈值则待核对', 'ERP 成功后更新排产池状态', '排产池更新后同步已入库 / 待刷新标签'],
  },
] as const

const injectionWritebackKeyMatchRows = injectionInboundWritebackRows.map((row, index) => {
  const source = huaxingShiftReportBaseRows[index]
  const normalizedMachine = source?.recommendedMachine ?? '待确认机台'
  const moldKey = source ? `${source.orderNo} + ${source.moldCode} + ${normalizedMachine}` : `${row.orderNo} + 待补模号`
  const sourceKey = `${row.deliveryCode} + ${row.orderNo}`
  const targetRecord = source
    ? `${source.moldCode} · ${normalizedMachine} · 欠数 ${row.shortageAfter}`
    : `${row.orderNo} · 待补目标记录`
  const blocker = row.tone === 'green'
    ? '主键已命中，可继续回写 ERP 与排产池。'
    : row.tone === 'amber'
        ? '已命中订单与机台，但待仓库 / ERP 完成回写。'
        : '需核对送货单、订单号或机台映射，当前不能自动刷新。'

  return {
    stage: index % 2 === 0 ? '日报回写' : '入库回写',
    businessKey: moldKey,
    sourceKey,
    targetRecord,
    status: row.tone === 'green' ? '已命中' : row.tone === 'amber' ? '待回写' : '待核对',
    blocker,
    tone: row.tone,
  }
}) satisfies InjectionModuleData['writebackKeyMatchRows']

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
    status: '部分打通',
    detail: '当前日报、交接、入库回写已经基于华兴真实订单推导，但仍待接入车间实际回报与 ERP 回写。',
    tone: 'amber',
  },
] as const

const injectionMachineMasterRows = huaxingMachineMasterImportRows
  .slice(0, 12)
  .map((row) => ({ ...row }))

const injectionMoldTargetDetailRows = huaxingMoldTargetDetailImportRows.map((row) => ({ ...row }))

const injectionMoldMachineMappingRows = huaxingPrioritizedOrderAnalysis
  .reduce((accumulator, row) => {
    if (accumulator.some((item) => item.moldCode === row.moldCode)) {
      return accumulator
    }

    accumulator.push({
      moldCode: row.moldCode,
      customer: row.orderNo.slice(0, 3) || '待补客户',
      productName: row.productName,
      candidatePool: row.candidatePool,
      recommendedMachine: row.recommendedMachine,
      backupMachine: row.backupMachines.join(' / ') || '待补备选机台',
      status: row.tone === 'green' ? '历史已命中' : row.tone === 'amber' ? '待确认' : '待补映射',
      detail: row.reason,
      tone: row.tone,
    })

    return accumulator
  }, [] as InjectionModuleData['moldMachineMappingRows'])
  .slice(0, 14)

const injectionShiftReportChecklistItems = [
  {
    title: '白班实际产量回报',
    owner: '车间组长',
    status: achievedReportCount === huaxingShiftReportBaseRows.length ? '已提交' : '待追数',
    detail: `当前已回报 ${huaxingShiftReportBaseRows.length} 台重点机台，未达成 ${huaxingShiftReportBaseRows.length - achievedReportCount} 台。`,
    tone: achievedReportCount === huaxingShiftReportBaseRows.length ? 'green' : 'amber',
  },
  {
    title: '夜班停机原因归档',
    owner: '生产主管',
    status: redDowntimeCount > 0 ? '待补原因' : '已完成',
    detail: `停机 / 调机异常 ${redDowntimeCount} 台，主要集中在待分机或转模衔接订单。`,
    tone: redDowntimeCount > 0 ? 'red' : 'green',
  },
  {
    title: '结转交接确认',
    owner: 'PMC / 计划',
    status: huaxingShiftReportBaseRows.some((row) => row.remark.includes('转')) ? '待确认' : '已确认',
    detail: `涉及转模 / 转水口 / 喷油交接 ${huaxingShiftReportBaseRows.filter((row) => row.remark.includes('转') || row.remark.includes('喷油')).length} 条。`,
    tone: huaxingShiftReportBaseRows.some((row) => row.remark.includes('转')) ? 'blue' : 'green',
  },
  {
    title: '入库与欠数回写',
    owner: '仓库 / PMC',
    status: injectionInboundWritebackRows.some((row) => row.tone === 'red') ? '风险' : pendingInboundCount > 0 ? '待处理' : '已回写',
    detail: `待刷新 ${injectionInboundWritebackRows.filter((row) => row.schedulerStatus !== '已更新').length} 单，已更新 ${injectionInboundWritebackRows.filter((row) => row.schedulerStatus === '已更新').length} 单。`,
    tone: injectionInboundWritebackRows.some((row) => row.tone === 'red') ? 'red' : pendingInboundCount > 0 ? 'amber' : 'green',
  },
] as const

const injectionShiftHandoverRows = huaxingShiftReportBaseRows
  .filter((row) => row.actualNumber < parseOrderNumber(row.shortageQty) || row.remark.includes('转') || row.reportTone !== 'green')
  .slice(0, 4)
  .map((row, index) => {
    const tone: Tone = row.reportTone === 'green' ? 'blue' : row.reportTone

    return {
      shift: index % 2 === 0 ? '夜班 → 白班' : '白班 → 夜班',
      machine: row.recommendedMachine,
      orderNo: row.orderNo,
      carryOverQty: formatInteger(Math.max(0, parseOrderNumber(row.shortageQty) - row.actualNumber)),
      nextOwner: row.reportTone === 'red' ? '计划员' : row.reportTone === 'amber' ? '白班组长' : '夜班组长',
      note: row.remark.includes('转')
        ? `涉及 ${row.remark}，交接时保持原机优先。`
        : row.reportTone === 'red'
            ? '未达班次目标，先确认机台和停机原因后再续排。'
            : '允许延续生产，交接时同步剩余欠数和颜色顺序。',
      tone,
    }
  })

const injectionExecutionQueueRows = huaxingPrioritizedOrderAnalysis
  .slice(0, 10)
  .map((row) => {
    const writebackState = huaxingWritebackStateMap.get(`${row.orderNo}::${row.moldCode}`)
    const tone = writebackState?.tone ?? row.tone
    const priority = writebackState
      ? tone === 'green'
        ? '已回写待结转'
        : tone === 'amber'
            ? '待刷新'
            : '待核对'
      : !row.normalizedMachine
          ? '待分机'
          : row.overdue
              ? '交期优先'
              : row.keyOrder
                  ? '关键单'
                  : '常规待排'

    return {
      machine: row.recommendedMachine,
      orderNo: row.orderNo,
      moldName: `${row.moldCode} ${row.productName}`,
      color: row.color,
      target24h: row.planTarget || '待补',
      shortage: writebackState?.shortageAfter ?? row.shortageQty,
      priority,
      tone,
    }
  })

const injectionExecutionScheduleRows = huaxingPrioritizedOrderAnalysis
  .slice(0, 9)
  .map((row) => {
    const writebackState = huaxingWritebackStateMap.get(`${row.orderNo}::${row.moldCode}`)
    const tone = writebackState?.tone ?? row.tone
    const shiftPlan = writebackState
      ? tone === 'green'
        ? '已回写，待结转确认'
        : tone === 'amber'
            ? '待入库后刷新'
            : '待核对后重排'
      : row.remark.includes('转')
          ? '转模 / 转色后执行'
          : row.normalizedMachine
              ? '沿用当前机台'
              : '待确认后下发'
    const dependency = writebackState
      ? `${row.blocker} · ${writebackState.warehouseStatus} / ${writebackState.erpStatus} / ${writebackState.schedulerStatus}`
      : row.blocker

    return {
      orderNo: row.orderNo,
      machine: row.recommendedMachine,
      startWindow: row.planStart || '待智能排机生成',
      endWindow: row.planFinish || '待智能排机生成',
      shiftPlan,
      expectedOutput: writebackState
        ? `本班回报 ${writebackState.inboundQty} / 回写后欠数 ${writebackState.shortageAfter}`
        : `欠数 ${row.shortageQty} / 计划 ${row.planTarget || '待补'}`,
      dependency,
      tone,
    }
  })

const injectionPendingOrderDetailRows = huaxingPendingOrderImportRows.map((row) => {
  const writebackState = huaxingWritebackStateMap.get(`${row.orderNo}::${row.moldCode}`)

  if (!writebackState) {
    return { ...row }
  }

  const issue = writebackState.tone === 'green'
    ? '已回写'
    : writebackState.tone === 'amber'
        ? '待刷新'
        : '待核对'

  return {
    ...row,
    quantity: writebackState.shortageAfter,
    issue,
    planner: `${row.planner} / ${writebackState.deliveryCode}`,
    tone: writebackState.tone,
  }
})

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
  shiftReportTemplateGroups: injectionShiftReportTemplateGroups.map((group) => ({
    ...group,
    fields: group.fields.map((field) => ({ ...field })),
  })),
  shiftReportImportMappingRows: injectionShiftReportImportMappingRows.map((row) => ({ ...row })),
  warehouseInboundRows: [...injectionWarehouseInboundRows],
  writebackRuleCards: injectionWritebackRuleCards.map((card) => ({ ...card, items: [...card.items] })),
  writebackKeyMatchRows: injectionWritebackKeyMatchRows.map((row) => ({ ...row })),
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

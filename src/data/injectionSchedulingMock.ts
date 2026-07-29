import {
  addCalendarHours,
  calculateProductionProgress,
  calculateScheduleTiming,
  evaluateChangeover,
  evaluateMachineEligibility,
  scoreCandidateMachine,
} from '@/domain/injection-scheduling'
import type { ProductionFactoryContextId } from '@/data/enterpriseMock'
import type {
  BacklogOrder,
  ColorFamily,
  InjectionMachine,
  MachineCapability,
  MachineClass,
  OrderRequirement,
  PriorityCode,
  ProductionCalendar,
  ScheduleTask,
  SchedulingSnapshot,
} from '@/types/injectionScheduling'

const calendar: ProductionCalendar = {
  timezone: 'Asia/Shanghai',
  availabilityWindows: [
    { startAt: '2026-07-28T00:00:00+08:00', endAt: '2026-08-31T23:59:59+08:00', label: '白/夜班连续生产窗口' },
  ],
  downtimeWindows: [
    { startAt: '2026-07-31T08:00:00+08:00', endAt: '2026-07-31T14:00:00+08:00', label: '计划保养示例' },
    { startAt: '2026-08-05T02:00:00+08:00', endAt: '2026-08-05T06:00:00+08:00', label: '厂区停电演练示例' },
  ],
}

const classProfile: Record<MachineClass, {
  tonnage: number
  shot: number
  tieBar: number
  moldMin: number
  moldMax: number
}> = {
  '4A': { tonnage: 45, shot: 82, tieBar: 300, moldMin: 90, moldMax: 260 },
  '5A': { tonnage: 50, shot: 96, tieBar: 310, moldMin: 100, moldMax: 280 },
  '7A': { tonnage: 80, shot: 145, tieBar: 360, moldMin: 110, moldMax: 330 },
  '10A': { tonnage: 120, shot: 220, tieBar: 400, moldMin: 130, moldMax: 380 },
  '12A': { tonnage: 150, shot: 260, tieBar: 450, moldMin: 140, moldMax: 420 },
  '14A': { tonnage: 180, shot: 360, tieBar: 455, moldMin: 150, moldMax: 450 },
  '18A': { tonnage: 200, shot: 420, tieBar: 500, moldMin: 160, moldMax: 480 },
  '24A': { tonnage: 250, shot: 530, tieBar: 570, moldMin: 180, moldMax: 540 },
  '32A': { tonnage: 320, shot: 745, tieBar: 665, moldMin: 200, moldMax: 650 },
  '50A': { tonnage: 400, shot: 980, tieBar: 700, moldMin: 220, moldMax: 700 },
  '60A': { tonnage: 480, shot: 1200, tieBar: 725, moldMin: 240, moldMax: 760 },
  '80A': { tonnage: 650, shot: 1600, tieBar: 910, moldMin: 260, moldMax: 850 },
  '104A': { tonnage: 850, shot: 2100, tieBar: 1050, moldMin: 280, moldMax: 960 },
  '120A': { tonnage: 1000, shot: 2600, tieBar: 1200, moldMin: 300, moldMax: 1100 },
}

const machineClasses: MachineClass[] = ['32A', '32A', '18A', '12A', '5A', '24A', '14A', '7A', '60A', '4A', '10A']
const colors: Array<{ name: string; family: ColorFamily }> = [
  { name: '透明', family: 'natural' },
  { name: '本白', family: 'natural' },
  { name: '浅粉', family: 'light' },
  { name: '黄色', family: 'medium' },
  { name: '深棕', family: 'dark' },
  { name: '黑色', family: 'black' },
  { name: '金属银', family: 'special' },
]
const materials = ['ABS 750NSW', 'PP AV161', 'PC 透明料', 'POM PM820', 'PVC 85度']

function capability(machineClass: MachineClass, index: number): MachineCapability {
  const profile = classProfile[machineClass]
  const special = index % 13
  return {
    machineClass,
    tonnage: profile.tonnage,
    shotCapacityGrams: profile.shot,
    safetyUtilization: 0.82,
    tieBarWidthMm: profile.tieBar,
    tieBarHeightMm: profile.tieBar,
    minMoldThicknessMm: profile.moldMin,
    maxMoldThicknessMm: profile.moldMax,
    openingStrokeMm: Math.round(profile.tieBar * 0.85),
    ejectionStrokeMm: Math.round(profile.tieBar * 0.28),
    armType: special === 2 ? 'single-arm' : 'multi-arm',
    supportsCorePull: special !== 4,
    supportsUnscrewing: special !== 8,
    compatibleMaterials: special === 3
      ? ['PC', 'PMMA']
      : special === 7 ? ['PVC'] : ['ABS', 'PP', 'POM', 'PC', 'PMMA', 'PVC'],
    screwType: special === 3 ? 'PC' : special === 7 ? 'PVC' : special === 6 ? 'transparent' : 'standard',
    transparentOnly: special === 6,
  }
}

function createMachines(factoryId: 'huaxing' | 'huakang-b', count: number): InjectionMachine[] {
  const prefix = factoryId === 'huaxing' ? 'hx' : 'hkb'
  return Array.from({ length: count }, (_, index) => {
    const number = index + 1
    const machineClass = machineClasses[index % machineClasses.length]!
    const machineCapability = capability(machineClass, index)
    const state = index % 19 === 5
      ? 'fault'
      : index % 17 === 8 ? 'maintenance'
        : index % 11 === 2 ? 'risk'
          : index % 13 === 4 ? 'urgent'
            : index % 9 === 0 ? 'idle' : 'running'
    const workshop = factoryId === 'huaxing'
      ? (index < Math.ceil(count * 0.42) ? '旧车间' : '新车间')
      : (index < Math.ceil(count * 0.72) ? 'A区' : 'B区')
    const name = factoryId === 'huaxing'
      ? `${workshop === '旧车间' ? '旧' : '新'}${number}`
      : `${workshop}${number}号机`
    const restriction = machineCapability.transparentOnly
      ? '透明/本色专机'
      : !machineCapability.supportsCorePull
        ? '不可抽芯'
        : machineCapability.screwType === 'PC'
          ? 'PC 螺杆'
          : machineCapability.screwType === 'PVC'
            ? 'PVC 螺杆'
            : machineCapability.armType === 'single-arm' ? '单臂三轴' : '标准机台'
    return {
      id: `${prefix}-${number}`,
      name,
      code: factoryId === 'huaxing'
        ? `${workshop === '旧车间' ? 'O' : 'N'}${String(number).padStart(2, '0')}`
        : `B${String(number).padStart(2, '0')}`,
      workshop,
      kind: index % 5 === 0 ? '全电动' : index % 3 === 0 ? '高速机' : '普通机',
      capability: machineCapability,
      restriction,
      load: state === 'idle' || state === 'fault' ? 0 : 68 + index % 29,
      state,
      resourceState: state === 'fault' ? 'blocked' : state === 'maintenance' ? 'warning' : 'available',
      taskIds: [],
    }
  })
}

function createRequirement(input: {
  moldNo: string
  productName: string
  orderNo: string
  colorIndex: number
  material: string
  priorityCode: PriorityCode
  machine: InjectionMachine
  shotWeight?: number
  armRequirement?: 'none' | 'single-arm' | 'multi-arm'
  requiresCorePull?: boolean
  requiresUnscrewing?: boolean
  incomplete?: boolean
}): OrderRequirement {
  const color = colors[input.colorIndex % colors.length]!
  const tieBar = input.machine.capability.tieBarWidthMm
  return {
    productName: input.productName,
    orderNo: input.orderNo,
    itemNo: `ITEM-${input.orderNo.slice(-4)}`,
    color: color.name,
    colorFamily: color.family,
    material: input.material,
    priorityCode: input.priorityCode,
    priorityFlag: input.priorityCode === 'P0' ? '特急' : undefined,
    mold: {
      moldNo: input.moldNo,
      widthMm: input.incomplete ? undefined : Math.round(tieBar * 0.62),
      heightMm: input.incomplete ? undefined : Math.round(tieBar * 0.58),
      thicknessMm: Math.round((input.machine.capability.minMoldThicknessMm + input.machine.capability.maxMoldThicknessMm) / 2),
      openingStrokeMm: Math.round(input.machine.capability.openingStrokeMm * 0.65),
      ejectionStrokeMm: Math.round(input.machine.capability.ejectionStrokeMm * 0.6),
      shotWeightGrams: input.incomplete ? undefined : (input.shotWeight ?? Math.round(input.machine.capability.shotCapacityGrams * 0.46)),
      material: input.material,
      armRequirement: input.armRequirement ?? 'single-arm',
      requiresCorePull: input.requiresCorePull,
      requiresUnscrewing: input.requiresUnscrewing,
      state: 'available',
    },
  }
}

function riskFrom(requirement: OrderRequirement, slackHours: number, changeoverStatus: 'ok' | 'missing-rule') {
  if (requirement.mold.widthMm == null || requirement.mold.shotWeightGrams == null || changeoverStatus === 'missing-rule') return 'incomplete'
  if (requirement.priorityCode === 'P0') return 'urgent'
  if (slackHours < 0) return 'overdue'
  if (slackHours < 36) return 'warning'
  return 'normal'
}

function createTasks(
  factoryId: 'huaxing' | 'huakang-b',
  machines: InjectionMachine[],
  anchorAt: string,
): ScheduleTask[] {
  const tasks: ScheduleTask[] = []
  machines.forEach((machine, machineIndex) => {
    if (machine.state === 'idle' || machine.state === 'fault' || machine.state === 'maintenance') return
    let taskAnchor = addCalendarHours(anchorAt, (machineIndex % 4) * 1.5)
    let previous: OrderRequirement | null = null
    const baseMold = `${factoryId === 'huaxing' ? 'HX' : 'HKB'}-${String(machineIndex + 1).padStart(2, '0')}-M`
    const taskCount = 2 + machineIndex % 4
    for (let taskIndex = 0; taskIndex < taskCount; taskIndex += 1) {
      const sameMold = taskIndex <= 1
      const requirement = createRequirement({
        moldNo: sameMold ? baseMold : `${baseMold}-${taskIndex}`,
        productName: ['车轮/座椅组合', '透明水箱', '包装底座', '牌仔面', '钥匙扣支架'][machineIndex % 5]!,
        orderNo: `${factoryId === 'huaxing' ? 'HXE' : 'BJB'}26${String(machineIndex + 1).padStart(3, '0')}-${taskIndex + 1}`,
        colorIndex: taskIndex === 1 ? machineIndex + 1 : machineIndex,
        material: materials[machineIndex % materials.length]!,
        priorityCode: machineIndex % 13 === 4 && taskIndex === 0 ? 'P0' : taskIndex === 0 ? 'P1' : taskIndex === 1 ? 'P2' : 'P3',
        machine,
        armRequirement: machineIndex % 17 === 2 && taskIndex === 1 ? 'multi-arm' : 'single-arm',
        requiresCorePull: machineIndex % 19 === 4 && taskIndex === 1,
        incomplete: machineIndex % 23 === 9 && taskIndex === 1,
      })
      const orderQuantity = 1_200 + (machineIndex * 419 + taskIndex * 907) % 18_000
      const progress = calculateProductionProgress(
        orderQuantity,
        taskIndex === 0 ? [Math.round(orderQuantity * (0.22 + machineIndex % 5 * 0.08))] : [],
        1_400 + machineIndex % 7 * 450,
      )
      const changeover = evaluateChangeover(machine.capability.machineClass, previous, requirement)
      const deliveryDueAt = addCalendarHours(anchorAt, 48 + machineIndex % 10 * 24 + taskIndex * 42)
      const timing = calculateScheduleTiming({
        anchorAt: taskAnchor,
        changeoverHours: changeover.totalHours,
        productionDurationHours: progress.productionDurationHours,
        deliveryDueAt,
        calendar,
      })
      const task: ScheduleTask = {
        id: `${factoryId}-${machineIndex + 1}-${taskIndex + 1}`,
        machineId: machine.id,
        requirement,
        production: progress,
        timing,
        changeover,
        sequence: taskIndex + 1,
        current: taskIndex === 0,
        locked: taskIndex === 0,
        risk: riskFrom(requirement, timing.slackHours, changeover.status),
        remark: taskIndex === 0 ? '当前生产任务已锁定。' : undefined,
      }
      tasks.push(task)
      machine.taskIds.push(task.id)
      taskAnchor = timing.plannedEnd
      previous = requirement
    }
  })
  return tasks
}

function createBacklog(
  factoryId: 'huaxing' | 'huakang-b',
  machines: InjectionMachine[],
  tasks: ScheduleTask[],
  anchorAt: string,
): BacklogOrder[] {
  const profiles = [
    { mold: 'TY-2407-08', product: '超纤羊前保险杠', priority: 'P0' as const, material: 'ABS 750NSW', arm: 'multi-arm' as const, core: false, incomplete: false, shot: 742 },
    { mold: 'JP45801-21', product: '赛车女孩侧裙', priority: 'P0' as const, material: 'PP AV161', arm: 'single-arm' as const, core: false, incomplete: false, shot: 168 },
    { mold: 'CORE-1802', product: '抽芯底座', priority: 'P1' as const, material: 'ABS 750NSW', arm: 'single-arm' as const, core: true, incomplete: false, shot: 286 },
    { mold: 'PVC-5002', product: 'PVC 透明眼睛', priority: 'P1' as const, material: 'PVC 85度', arm: 'single-arm' as const, core: false, incomplete: false, shot: 88 },
    { mold: 'JP50021-03', product: '驾驶室支架', priority: 'P2' as const, material: 'PC 透明料', arm: 'single-arm' as const, core: false, incomplete: true, shot: undefined },
  ]
  return profiles.map((profile, index) => {
    const referenceMachine = machines.find((machine) => machine.capability.machineClass === (index === 0 ? '80A' : index === 3 ? '7A' : '18A'))
      ?? machines[0]!
    const requirement = createRequirement({
      moldNo: profile.mold,
      productName: profile.product,
      orderNo: `${factoryId === 'huaxing' ? 'BJB' : 'HKB'}26-B${index + 1}`,
      colorIndex: index + 1,
      material: profile.material,
      priorityCode: profile.priority,
      machine: referenceMachine,
      shotWeight: profile.shot,
      armRequirement: profile.arm,
      requiresCorePull: profile.core,
      incomplete: profile.incomplete,
    })
    const production = calculateProductionProgress(4_200 + index * 1_900, [], 1_800 + index * 350)
    const requiredDate = addCalendarHours(anchorAt, 72 + index * 30)
    const candidates = machines
      .map((machine) => {
        const previousTask = machine.taskIds.length
          ? tasks.find((task) => task.id === machine.taskIds[machine.taskIds.length - 1])
          : undefined
        const projectedEndAt = previousTask?.timing.plannedEnd ?? anchorAt
        return scoreCandidateMachine({
          machine,
          requirement,
          dueAt: requiredDate,
          previousTask,
          projectedEndAt,
        })
      })
      .filter((candidate): candidate is NonNullable<typeof candidate> => Boolean(candidate))
      .sort((left, right) => right.score - left.score)
      .slice(0, 4)
    const eligibilityResults = machines.map((machine) => evaluateMachineEligibility({ machine, requirement }))
    const incomplete = eligibilityResults.some((result) => result.status === 'incomplete')
    return {
      id: `${factoryId}-backlog-${index + 1}`,
      requirement,
      production,
      requiredDate,
      candidates,
      noMatchReason: candidates.length
        ? undefined
        : incomplete
          ? '关键模具尺寸或整啤毛重缺失，需补资料后重新匹配。'
          : '所有机台均未通过射胶量、机械手、抽芯或材料螺杆硬约束。',
    }
  })
}

function createSnapshot(factoryId: 'huaxing' | 'huakang-b'): SchedulingSnapshot {
  const isHuaxing = factoryId === 'huaxing'
  const anchorAt = isHuaxing ? '2026-07-28T08:00:00+08:00' : '2026-07-28T07:30:00+08:00'
  const machines = createMachines(factoryId, isHuaxing ? 71 : 96)
  const tasks = createTasks(factoryId, machines, anchorAt)
  const backlog = createBacklog(factoryId, machines, tasks, anchorAt)
  const activeMachines = machines.filter((machine) => machine.taskIds.length)
  const overdueTasks = tasks.filter((task) => task.risk === 'overdue')
  const remainingTotal = tasks.reduce((total, task) => total + task.production.remainingQuantity, 0)
  return {
    factoryId,
    sourceLabel: isHuaxing ? '华兴啤机日排版表1.xlsx' : '华康B啤机日排表新6.2(1).xlsx',
    snapshotAt: isHuaxing ? '2026-07-28 16:30' : '2026-07-28 16:18',
    notice: '源工作簿包含 NOW()/上一行公式和缓存日期；本页按固定 anchorAt 重新生成前端演示快照。',
    plan: {
      id: `${factoryId}-draft-1`,
      label: isHuaxing ? '草案 v1.3' : '草案 v0.9',
      revision: 1,
      rulesVersion: '换模/转色规则 2026.07-demo',
      status: 'draft',
      anchorAt,
    },
    calendar,
    kpis: [
      { label: '运行机台', value: `${activeMachines.length} / ${machines.length}`, detail: `${Math.round(activeMachines.length / machines.length * 100)}% 已排程`, tone: 'teal' },
      { label: '已排任务', value: tasks.length.toLocaleString(), detail: '当前 + 后续', tone: 'default' },
      { label: '待排订单', value: backlog.length.toLocaleString(), detail: '需确认候选', tone: 'amber', action: 'backlog' },
      { label: '交期异常', value: overdueTasks.length.toLocaleString(), detail: '交期余量 < 0', tone: 'red', action: 'alerts' },
      { label: '换模 / 转色', value: `${tasks.filter((task) => task.changeover.moldChangeHours > 0).length}/${tasks.filter((task) => task.changeover.colorChangeHours > 0).length}`, detail: '当前草案', tone: 'violet' },
      { label: '剩余订单数', value: remainingTotal.toLocaleString(), detail: 'SUM(欠数)', tone: 'default' },
    ],
    machines,
    tasks,
    backlog,
  }
}

export const schedulingSnapshots: Partial<Record<ProductionFactoryContextId, SchedulingSnapshot>> = {
  huaxing: createSnapshot('huaxing'),
  'huakang-b': createSnapshot('huakang-b'),
}

export function cloneSchedulingSnapshot(factoryId: ProductionFactoryContextId) {
  const snapshot = schedulingSnapshots[factoryId]
  return snapshot ? structuredClone(snapshot) : null
}

export function cloneHuaxingSchedulingSnapshot() {
  return structuredClone(schedulingSnapshots.huaxing!)
}

import type {
  MachineRecord,
  MoldRecord,
  OrderRecord,
  ScheduleTaskRecord,
  SchedulingPlanRecord,
} from '../../types'

export const schedulingBaselineFixtureVersion = 'b0-v1'
export const schedulingBaselineFixtureSeed = 20_260_810

export interface SchedulingBaselineFixture {
  metadata: {
    fixtureVersion: string
    seed: number
    machineCount: number
    taskCount: number
    containsProductionData: false
  }
  machines: MachineRecord[]
  molds: MoldRecord[]
  orders: OrderRecord[]
  tasks: ScheduleTaskRecord[]
  plan: SchedulingPlanRecord
}

function createDeterministicRandom(seed: number) {
  let state = seed >>> 0
  return () => {
    state = (Math.imul(state, 1_664_525) + 1_013_904_223) >>> 0
    return state / 0x1_0000_0000
  }
}

function fixedDateTime(minutesFromStart: number) {
  return new Date(Date.UTC(2026, 7, 10, 0, minutesFromStart))
    .toISOString()
    .slice(0, 16)
    .replace('T', ' ')
}

export function createSchedulingBaselineFixture(
  machineCount: number,
  taskCount: number,
  seed = schedulingBaselineFixtureSeed,
): SchedulingBaselineFixture {
  if (!Number.isInteger(machineCount) || machineCount <= 0) throw new Error('machineCount must be a positive integer')
  if (!Number.isInteger(taskCount) || taskCount < machineCount) throw new Error('taskCount must be at least machineCount')

  const random = createDeterministicRandom(seed)
  const machines: MachineRecord[] = Array.from({ length: machineCount }, (_, index) => ({
    id: `b0-machine-${index + 1}`,
    factoryId: 'huaxing',
    code: `QA-M${String(index + 1).padStart(3, '0')}`,
    position: `QA-${String(index + 1).padStart(3, '0')}`,
    area: `去敏测试区-${(index % 4) + 1}`,
    aClass: 12 + (index % 8) * 2,
    aClassRaw: `${12 + (index % 8) * 2}A`,
    clampingForceTons: 80 + (index % 10) * 20,
    injectionCapacityG: 180 + (index % 12) * 45,
    tieBarXmm: 420 + (index % 5) * 40,
    tieBarYmm: 380 + (index % 5) * 40,
    processTags: index % 3 === 0 ? ['general', 'core_pull'] : ['general'],
    armCapabilities: index % 2 === 0 ? ['single', 'dual'] : ['single'],
    fixtureCapabilities: ['standard'],
    processRestrictions: [],
    equipmentDetails: { fixtureSource: 'B0_DEIDENTIFIED_FIXTURE' },
    remarks: '仅用于 B0 测试，不含生产资料',
    machineType: 'B0_TEST_MACHINE',
    specialMachineType: '',
    status: 'available',
    normalizationStatus: 'COMPLETE',
    revision: 1,
  }))

  const molds: MoldRecord[] = Array.from({ length: machineCount }, (_, index) => ({
    id: `b0-mold-${index + 1}`,
    moldNo: `QA-MOLD-${String(index + 1).padStart(3, '0')}`,
    name: `去敏测试模具-${String(index + 1).padStart(3, '0')}`,
    aClass: 12 + (index % 8) * 2,
    aClassRaw: `${12 + (index % 8) * 2}A`,
    netWeightG: 35 + (index % 20) * 4,
    grossWeightG: 42 + (index % 20) * 5,
    requiredArmType: index % 2 === 0 ? 'single' : 'single / dual',
    requiredFixtureType: 'standard',
    materialCode: `QA-MAT-${(index % 6) + 1}`,
    materialName: `去敏测试物料-${(index % 6) + 1}`,
    colorProfile: `测试色-${(index % 8) + 1}`,
    processRequirements: [],
    specialMachineType: '',
    normalizationStatus: 'COMPLETE',
  }))

  const orders: OrderRecord[] = []
  const tasks: ScheduleTaskRecord[] = []
  const machineSequences = Array.from({ length: machineCount }, () => 0)

  for (let index = 0; index < taskCount; index += 1) {
    const machineIndex = index % machineCount
    const moldIndex = (index * 17 + Math.floor(random() * machineCount)) % machineCount
    const sequence = ++machineSequences[machineIndex]!
    const orderQuantity = 600 + (index % 24) * 125
    const completionRatio = sequence === 1 ? 0.35 : (index % 5) * 0.08
    const completedQuantity = Math.floor(orderQuantity * completionRatio)
    const startMinutes = machineIndex * 7 + (sequence - 1) * 240
    const durationMinutes = 150 + (index % 7) * 30
    const orderId = `b0-order-${index + 1}`
    const taskId = `b0-task-${index + 1}`

    orders.push({
      id: orderId,
      orderNo: `QA-ORDER-${String(index + 1).padStart(5, '0')}`,
      itemNo: `QA-ITEM-${String((index % 400) + 1).padStart(4, '0')}`,
      productName: `去敏测试产品-${String((index % 120) + 1).padStart(3, '0')}`,
      moldId: molds[moldIndex]!.id,
      moldDefinitionId: null,
      moldOutputSpecId: null,
      orderQuantity,
      sourceCompletedQuantity: completedQuantity,
      completedQuantity,
      outstandingQuantity: orderQuantity - completedQuantity,
      completionRate: completedQuantity / orderQuantity,
      deliveryStartDate: '2026-08-10',
      deliveryDueDate: `2026-08-${String(12 + (index % 16)).padStart(2, '0')}`,
      deliverySlackDays: (index % 13) - 5,
      priorityCode: index % 19 === 0 ? 'CRITICAL' : index % 7 === 0 ? 'URGENT' : 'NORMAL',
      materialReadinessStatus: index % 23 === 0 ? 'partial' : 'ready',
      warehouseText: `去敏仓位-${(index % 12) + 1}`,
      remark: index % 31 === 0 ? 'B0 去敏异常样本' : '',
      sourceType: 'B0_TEST_FIXTURE',
      status: 'SCHEDULED',
      lineage: {
        automation: machineIndex % 2 === 0 ? '全自动' : '半自动',
        marker: index % 17 === 0 ? 'QA' : '',
        source_mold_no: molds[moldIndex]!.moldNo,
        set_quantity: orderQuantity,
        color_name: molds[moldIndex]!.colorProfile,
        color_powder_code: `QA-COLOR-${(index % 8) + 1}`,
        material_name: molds[moldIndex]!.materialName,
        whole_shot_net_weight_g: molds[moldIndex]!.netWeightG,
        total_gross_weight: molds[moldIndex]!.grossWeightG,
        order_date: '2026-08-10',
        setup_time: `${index % 3}h`,
        spray: index % 6 === 0 ? '是' : '否',
      },
      revision: 1,
    })

    tasks.push({
      id: taskId,
      planId: 'B0-BASELINE-PLAN',
      machineId: machines[machineIndex]!.id,
      orderId,
      moldId: molds[moldIndex]!.id,
      sequence,
      status: sequence === 1 ? 'RUNNING' : 'QUEUED',
      plannedStart: fixedDateTime(startMinutes),
      plannedFinish: fixedDateTime(startMinutes + durationMinutes),
      targetQuantity: Math.min(orderQuantity - completedQuantity, 1_200),
      reportedQuantity: sequence === 1 ? Math.min(completedQuantity, 400) : 0,
      sourceSheetName: 'B0_DEIDENTIFIED_FIXTURE',
      sourceRow: index + 2,
      locked: sequence === 1,
      manualOverrideReason: '',
      activeExecution: true,
      estimatedStart: fixedDateTime(startMinutes),
      estimatedFinish: fixedDateTime(startMinutes + durationMinutes),
      estimatedRemainingShifts: Math.max(1, Math.ceil((orderQuantity - completedQuantity) / 1_200)),
      deliverySlackDays: (index % 13) - 5,
      revision: 1,
      setupMinutes: (index % 3) * 30,
      productionMinutes: durationMinutes,
      plannedDowntimeMinutes: 0,
      changeoverType: index % 4 === 0 ? 'MOLD' : 'NONE',
      origin: 'B0_TEST_FIXTURE',
      stableOrderKey: `b0-stable-order-${index + 1}`,
      stableRowKey: `b0-stable-row-${index + 1}`,
    })
  }

  return {
    metadata: {
      fixtureVersion: schedulingBaselineFixtureVersion,
      seed,
      machineCount,
      taskCount,
      containsProductionData: false,
    },
    machines,
    molds,
    orders,
    tasks,
    plan: {
      id: 'B0-BASELINE-PLAN',
      status: 'PUBLISHED',
      revision: 14,
      ruleRevision: 7,
      businessDate: '2026-08-10',
      basedOnPlanId: '',
      basedOnEventSequence: 0,
      basedOnReportWatermark: 0,
      exportBindingSource: 'SYSTEM_STANDARD',
      calculationVersion: 'B0_TEST_FIXTURE',
    },
  }
}

export function createBusinessSchedulingBaselineFixture() {
  return createSchedulingBaselineFixture(76, 1_500)
}

export function createStressSchedulingBaselineFixture() {
  return createSchedulingBaselineFixture(120, 5_000)
}

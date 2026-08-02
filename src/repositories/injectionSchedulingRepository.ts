import axios from 'axios'
import {
  injectionSchedulingApi,
  type InjectionSchedulingApi,
  type InjectionSchedulingImportBatchDto,
  type InjectionSchedulingMachineDto,
  type InjectionSchedulingMoldDto,
  type InjectionSchedulingOrderDto,
  type InjectionSchedulingTaskDto,
} from '@/api/injectionScheduling'
import { getApiErrorMessage } from '@/lib/http'
import type {
  AssignBacklogResult,
  BacklogOrder,
  ConstraintCheck,
  InjectionFactoryId,
  InjectionMachine,
  InjectionSchedulingSnapshot,
  MachineCandidate,
  MoldDimensions,
  SaveShiftReportResult,
  SchedulingTask,
  ShiftReportInput,
} from '@/types/injectionScheduling'

export class FactoryDatasetNotFoundError extends Error {
  constructor(factoryId: InjectionFactoryId) {
    super(`注塑排产 Mock 数据集不存在：${factoryId}`)
    this.name = 'FactoryDatasetNotFoundError'
  }
}

export class OptimisticConflictError extends Error {
  readonly entityId: string
  readonly currentRevision: number

  constructor(entityId: string, currentRevision: number) {
    super(`数据版本冲突：${entityId} 当前版本为 ${currentRevision}`)
    this.name = 'OptimisticConflictError'
    this.entityId = entityId
    this.currentRevision = currentRevision
  }
}

export interface InjectionSchedulingRepository {
  getSnapshot(factoryId: InjectionFactoryId): Promise<InjectionSchedulingSnapshot>
  saveShiftReport(
    factoryId: InjectionFactoryId,
    taskId: string,
    expectedRevision: number,
    input: ShiftReportInput,
  ): Promise<SaveShiftReportResult>
  assignBacklogOrder(
    factoryId: InjectionFactoryId,
    backlogOrderId: string,
    machineId: string,
    expectedRevision: number,
    overrideReason?: string,
  ): Promise<AssignBacklogResult>
  evaluateBacklogOrder(
    factoryId: InjectionFactoryId,
    backlogOrderId: string,
  ): Promise<BacklogOrder>
  simulateExternalTaskUpdate(factoryId: InjectionFactoryId, taskId: string): Promise<void>
  previewImport(
    factoryId: InjectionFactoryId,
    file: File,
  ): Promise<InjectionSchedulingImportBatchDto>
  confirmImport(
    factoryId: InjectionFactoryId,
    batch: InjectionSchedulingImportBatchDto,
    input: {
      businessDate: string
      planStatus: InjectionSchedulingSnapshot['planStatus']
      planRevision: number
      acknowledgedBlockingIssueIds: string[]
    },
  ): Promise<InjectionSchedulingImportBatchDto>
}

const HUAXING: InjectionFactoryId = 'huaxing'
const PLAN_DATE = '2026-07-31'

function machine(
  id: string,
  code: string,
  machineClass: string,
  tonnage: number,
  shotCapacityGrams: number,
  platen: [number, number],
  armCapability: '单臂' | '双臂',
  processNote = '',
  loadPercent = 72,
): InjectionMachine {
  return {
    id,
    factoryId: HUAXING,
    code,
    zone: code.startsWith('旧') ? '老车间' : '新车间',
    machineClass,
    tonnage,
    shotCapacityGrams,
    platen: { width: platen[0], height: platen[1] },
    armCapability,
    machineType: tonnage >= 150 ? '高速' : '普通',
    processNote,
    loadPercent,
  }
}

const primaryMachines: InjectionMachine[] = [
  machine('old-2', '旧2', '32A', 320, 617, [680, 680], '双臂', '抽芯不行', 92),
  machine('old-3', '旧3', '32A', 320, 617, [680, 680], '单臂', 'PC 螺杆', 100),
  machine('old-9', '旧9', '18A', 200, 289, [520, 500], '双臂', '', 86),
  machine('old-12', '旧12', '12A', 150, 228, [450, 450], '双臂', '抽芯不行', 74),
]

const machineClasses = [
  { code: '5A', tonnage: 90, shot: 113, platen: [400, 350] as [number, number] },
  { code: '7A', tonnage: 120, shot: 156, platen: [420, 400] as [number, number] },
  { code: '12A', tonnage: 150, shot: 228, platen: [450, 450] as [number, number] },
  { code: '18A', tonnage: 200, shot: 289, platen: [520, 500] as [number, number] },
  { code: '24A', tonnage: 260, shot: 357, platen: [580, 560] as [number, number] },
  { code: '32A', tonnage: 320, shot: 617, platen: [680, 680] as [number, number] },
  { code: '60A', tonnage: 600, shot: 1260, platen: [900, 850] as [number, number] },
]

const generatedMachines = Array.from({ length: 65 }, (_, index) => {
  const spec = machineClasses[index % machineClasses.length]
  const isOld = index < 32
  const number = isOld ? index + 13 : index - 19
  return machine(
    `${isOld ? 'old' : 'new'}-${number}`,
    `${isOld ? '旧' : '新'}${number}`,
    spec.code,
    spec.tonnage,
    spec.shot,
    spec.platen,
    index % 3 === 0 ? '单臂' : '双臂',
    index % 17 === 0 ? 'PVC 螺杆' : '',
    48 + ((index * 11) % 51),
  )
})

const huaxingMachines = [...primaryMachines, ...generatedMachines]

function task(input: Partial<SchedulingTask> & Pick<SchedulingTask, 'id' | 'machineId' | 'sequence' | 'moldCode' | 'orderNo'>): SchedulingTask {
  return {
    factoryId: HUAXING,
    status: input.sequence === 0 ? 'RUNNING' : 'QUEUED',
    priority: 'NORMAL',
    originalMarker: input.sequence === 0 ? '▲' : '',
    productName: '注塑件',
    itemNo: 'ITEM-01',
    orderQuantity: 2400,
    completedQuantity: 0,
    shiftTarget: 1600,
    shiftCompleted: 0,
    downtimeHours: 0,
    exceptionType: '',
    color: '原色',
    colorHex: '#d8d7cf',
    material: 'PP 5100NA',
    shotNetWeightGrams: 48,
    deliveryDate: '2026-08-10',
    plannedStart: '2026-07-31 14:03',
    plannedEnd: '2026-08-01 16:05',
    slackDays: 6,
    armRequirement: '单臂',
    fixtureRequirement: '吸盘',
    moldDimensions: { length: 300, width: 280, height: 360 },
    warehouseOwner: '',
    note: '',
    fitDecision: 'PASS',
    fitScore: 84,
    sourceRow: null,
    revision: 1,
    updatedAt: '2026-07-31 16:18',
    ...input,
  }
}

const primaryTasks: SchedulingTask[] = [
  task({ id: 't-gt-145', machineId: 'old-2', sequence: 0, moldCode: 'GT1214', productName: '自卸车、消防车车轮/座椅', orderNo: 'FFD442145', itemNo: 'DTK01R', orderQuantity: 3528, completedQuantity: 3410, shiftTarget: 1400, color: '黑色', colorHex: '#171a1d', material: 'PP 5100NA', shotNetWeightGrams: 379, deliveryDate: '2026-07-24', plannedEnd: '2026-07-31 16:05', slackDays: -10.7, armRequirement: '双臂', moldDimensions: { length: 550, width: 450, height: 850 }, fitDecision: 'REVIEW_REQUIRED', fitScore: 86, sourceRow: 6 }),
  task({ id: 't-gt-174', machineId: 'old-2', sequence: 1, moldCode: 'GT1214', productName: '自卸车、消防车车轮/座椅', orderNo: 'FFD442174', itemNo: 'GT1283', orderQuantity: 1505, shiftTarget: 1400, color: '黑色', colorHex: '#171a1d', material: 'PP 5100NA', shotNetWeightGrams: 379, deliveryDate: '2026-07-24', plannedStart: '2026-07-31 16:05', plannedEnd: '2026-08-01 17:53', slackDays: -11.8, armRequirement: '双臂', moldDimensions: { length: 550, width: 450, height: 850 }, fitDecision: 'REVIEW_REQUIRED', fitScore: 92, sourceRow: 7, note: '同模同色连续' }),
  task({ id: 't-gt-178', machineId: 'old-2', sequence: 2, moldCode: 'GT1214', productName: '自卸车、消防车车轮/座椅', orderNo: 'FFD442178', itemNo: 'DTK01R', orderQuantity: 2505, shiftTarget: 1400, color: '黑色', colorHex: '#171a1d', material: 'PP 5100NA', shotNetWeightGrams: 379, deliveryDate: '2026-07-31', plannedStart: '2026-08-01 17:53', plannedEnd: '2026-08-03 12:49', slackDays: -6.5, armRequirement: '双臂', moldDimensions: { length: 550, width: 450, height: 850 }, fitDecision: 'REVIEW_REQUIRED', fitScore: 90, sourceRow: 8, note: '含 1 天机/模故障预留' }),
  task({ id: 't-pamt-791', machineId: 'old-3', sequence: 0, moldCode: 'PAMT-01M-01', productName: '水箱', orderNo: 'BJB250791', itemNo: '9560', priority: 'CRITICAL', orderQuantity: 30000, completedQuantity: 23765, shiftTarget: 1400, color: '透明', colorHex: '#e8f1f2', material: 'PC HS152R', shotNetWeightGrams: 384, deliveryDate: '2026-06-05', plannedEnd: '2026-08-05 00:57', slackDays: -64, armRequirement: '单臂', moldDimensions: { length: 650, width: 450, height: 550 }, fitDecision: 'REVIEW_REQUIRED', fitScore: 88, sourceRow: 14, note: '有复模' }),
  task({ id: 't-pamt-1245', machineId: 'old-3', sequence: 1, moldCode: 'PAMT-01M-01', productName: '水箱', orderNo: 'BJB251245', itemNo: '9560', priority: 'CRITICAL', orderQuantity: 60000, shiftTarget: 1400, color: '透明', colorHex: '#e8f1f2', material: 'PC HS152R', shotNetWeightGrams: 384, deliveryDate: '2026-08-23', plannedStart: '2026-08-06 00:57', plannedEnd: '2026-09-17 21:31', slackDays: -29.9, armRequirement: '单臂', moldDimensions: { length: 650, width: 450, height: 550 }, fitDecision: 'REVIEW_REQUIRED', fitScore: 94, sourceRow: 15, note: '同模同色连续 · 有复模' }),
  task({ id: 't-mnvn-002', machineId: 'old-9', sequence: 0, moldCode: 'MNVN-19M-06', productName: '包装底座', orderNo: 'DG002', itemNo: '77794', priority: 'CRITICAL', originalMarker: '特急▲', orderQuantity: 100000, completedQuantity: 12210, shiftTarget: 3800, color: '黄色', colorHex: '#f5d94f', material: '1#PP AV161', shotNetWeightGrams: 55.45, deliveryDate: '2026-08-24', plannedEnd: '2026-08-23 16:31', slackDays: -2.7, armRequirement: '双臂', moldDimensions: { length: 400, width: 350, height: 450 }, fitScore: 96, sourceRow: 24, note: '特急订单' }),
  task({ id: 't-mnvn-repair', machineId: 'old-9', sequence: 1, moldCode: 'MNVN-19M-06', productName: '包装底座（补数）', orderNo: '啤机补数', itemNo: '77794', orderQuantity: 1680, shiftTarget: 3800, color: '黄色', colorHex: '#f5d94f', material: '1#PP AV161', shotNetWeightGrams: 55.45, deliveryDate: '2026-08-24', plannedStart: '2026-08-27 16:31', plannedEnd: '2026-08-28 03:08', slackDays: -7.1, armRequirement: '双臂', moldDimensions: { length: 400, width: 350, height: 450 }, fitScore: 98, sourceRow: 25, note: '同模同色补数' }),
  task({ id: 't-bbt-273', machineId: 'old-12', sequence: 0, moldCode: 'BBT 45849-03', productName: '枪顶左右盖', orderNo: 'BJB251273', itemNo: '45841', priority: 'URGENT', orderQuantity: 1901, completedQuantity: 100, shiftTarget: 4000, color: '蓝色', colorHex: '#3d72c5', material: 'ABS KF-740', shotNetWeightGrams: 44, deliveryDate: '2026-08-07', plannedEnd: '2026-08-01 00:52', slackDays: 3, armRequirement: '单臂', moldDimensions: { length: 300, width: 300, height: 400 }, fitDecision: 'REVIEW_REQUIRED', fitScore: 91, sourceRow: 35 }),
  task({ id: 't-cup-268', machineId: 'old-12', sequence: 1, moldCode: 'T01-BL006-00600000', productName: '大杯盖', orderNo: 'BJB251268', itemNo: 'F12-BL028', priority: 'URGENT', originalMarker: '▲', orderQuantity: 756, shiftTarget: 3000, color: '绿色', colorHex: '#4d9d65', material: 'ABS KF-740', shotNetWeightGrams: 30.2, deliveryDate: '2026-08-05', plannedStart: '2026-08-01 00:52', plannedEnd: '2026-08-01 06:55', slackDays: 0.7, armRequirement: '单臂', moldDimensions: { length: 320, width: 400, height: 350 }, fitDecision: 'REVIEW_REQUIRED', fitScore: 87, sourceRow: 36, note: '同材料，颜色由蓝转绿' }),
  task({ id: 't-pipe-278', machineId: 'old-12', sequence: 2, moldCode: 'T01-BL008-00200000', productName: '外螺纹管/三通接头/尾盖', orderNo: 'BJB251278', itemNo: 'BL033', priority: 'CRITICAL', originalMarker: '▲', orderQuantity: 3010, shiftTarget: 2600, color: '绿色', colorHex: '#4d9d65', material: 'ABS KF-740', shotNetWeightGrams: 20.6, deliveryDate: '2026-07-24', plannedStart: '2026-08-01 07:47', plannedEnd: '2026-08-02 11:32', slackDays: -12.5, armRequirement: '单臂', moldDimensions: { length: 390, width: 350, height: 350 }, fitDecision: 'REVIEW_REQUIRED', fitScore: 89, sourceRow: 37, note: '交期已过，建议前移' }),
  task({ id: 't-inner-278', machineId: 'old-12', sequence: 3, moldCode: 'T01-BL008-00300000', productName: '内螺纹管', orderNo: 'BJB251278', itemNo: 'BL033', priority: 'CRITICAL', originalMarker: '▲', orderQuantity: 3010, shiftTarget: 2600, color: '绿色', colorHex: '#4d9d65', material: 'ABS KF-740', shotNetWeightGrams: 3.96, deliveryDate: '2026-07-24', plannedStart: '2026-08-03 11:32', plannedEnd: '2026-08-04 15:19', slackDays: -14.6, armRequirement: '双臂', moldDimensions: null, fitDecision: 'REVIEW_REQUIRED', fitScore: 71, sourceRow: 38, note: '模具尺寸资料缺失，必须人工复核' }),
]

function generatedTask(machineEntry: InjectionMachine, sequence: number, globalIndex: number): SchedulingTask {
  // Together with the nine overdue and two due-soon Excel sample rows above,
  // this deterministic distribution reproduces the prototype's 158 / 19 risk summary.
  const overdue = globalIndex <= 149
  const dueSoon = globalIndex >= 150 && globalIndex <= 166
  const moldCode = `HX-${String((globalIndex % 87) + 1).padStart(3, '0')}-M`
  const orderQuantity = 1200 + ((globalIndex * 337) % 8800)
  const completed = sequence === 0 ? Math.round(orderQuantity * ((globalIndex % 7) / 10)) : 0
  const shotWeight = Math.min(machineEntry.shotCapacityGrams * 0.72, 24 + (globalIndex % 180))
  return task({
    id: `generated-${globalIndex}`,
    machineId: machineEntry.id,
    sequence,
    moldCode,
    productName: `华兴注塑件 ${String((globalIndex % 42) + 1).padStart(2, '0')}`,
    orderNo: `HX26${String(440000 + globalIndex)}`,
    itemNo: `ITEM-${String((globalIndex % 63) + 1).padStart(3, '0')}`,
    priority: overdue ? 'CRITICAL' : dueSoon ? 'URGENT' : 'NORMAL',
    orderQuantity,
    completedQuantity: completed,
    shiftTarget: 1200 + ((globalIndex % 8) * 350),
    color: ['黑色', '绿色', '蓝色', '透明', '原色'][globalIndex % 5],
    colorHex: ['#171a1d', '#4d9d65', '#3d72c5', '#e8f1f2', '#d8d7cf'][globalIndex % 5],
    material: ['ABS KF-740', 'PP 5100NA', 'POM F30-03', 'PC HS152R'][globalIndex % 4],
    shotNetWeightGrams: Number(shotWeight.toFixed(1)),
    deliveryDate: overdue ? '2026-07-29' : dueSoon ? '2026-08-02' : '2026-08-12',
    plannedStart: sequence === 0 ? `${PLAN_DATE} 14:03` : `2026-08-${String(1 + (sequence % 8)).padStart(2, '0')} 08:00`,
    plannedEnd: `2026-08-${String(2 + (sequence % 12)).padStart(2, '0')} 18:00`,
    slackDays: overdue ? -((globalIndex % 18) + 0.4) : dueSoon ? 2.2 : 8.4,
    armRequirement: globalIndex % 4 === 0 ? '双臂' : '单臂',
    moldDimensions: globalIndex % 11 === 0 ? null : { length: 260 + (globalIndex % 180), width: 240 + (globalIndex % 150), height: 320 + (globalIndex % 220) },
    fitDecision: globalIndex % 11 === 0 ? 'REVIEW_REQUIRED' : 'PASS',
    fitScore: 72 + (globalIndex % 27),
    sourceRow: 40 + globalIndex,
  })
}

const generatedTasks: SchedulingTask[] = []
let generatedIndex = 1
for (const [machineIndex, machineEntry] of generatedMachines.entries()) {
  const count = machineIndex < 51 ? 4 : 3
  for (let sequence = 0; sequence < count; sequence += 1) {
    generatedTasks.push(generatedTask(machineEntry, sequence, generatedIndex))
    generatedIndex += 1
  }
}

function check(
  key: ConstraintCheck['key'],
  label: string,
  decision: ConstraintCheck['decision'],
  detail: string,
): ConstraintCheck {
  return { key, label, decision, detail }
}

function candidate(
  machineId: string,
  rank: number,
  score: number,
  decision: MachineCandidate['decision'],
  resultLabel: string,
  explanation: string,
  warning: string,
  constraints: ConstraintCheck[],
): MachineCandidate {
  const machineEntry = huaxingMachines.find((entry) => entry.id === machineId)
  if (!machineEntry) throw new Error(`Mock 候选机台不存在：${machineId}`)
  return { machineId, machineCode: machineEntry.code, rank, score, decision, resultLabel, explanation, warning, constraints, ruleSetRevision: 1 }
}

const passCommon = [
  check('robot-arm', '机械手能力', 'PASS', '双臂能力可覆盖单臂要求；能力按集合判断。'),
  check('fixture', '夹具要求', 'PASS', '机台与模具均为吸盘方案。'),
]

const primaryBacklog: BacklogOrder[] = [
  {
    id: 'backlog-bbt', factoryId: HUAXING, orderNo: 'BJB251305', itemNo: '45841', moldCode: 'BBT 45849-03', productName: '枪顶左右盖（追加单）', quantity: 8000, deliveryDate: '2026-08-08', color: '蓝色', material: 'ABS KF-740', shotNetWeightGrams: 44, armRequirement: '单臂', fixtureRequirement: '吸盘', moldDimensions: { length: 300, width: 300, height: 400 }, note: '原型模拟待排单', revision: 1,
    candidates: [
      candidate('old-12', 1, 96, 'PASS', '优先', '同模连续；44/228g；安装面 300×300 / 450×450；双臂能力覆盖单臂需求。', '当前队列含逾期任务，需人工决定插单位置。', [check('mold-size', '模具安装面', 'PASS', '300×300 小于机台 450×450。'), check('shot-capacity', '射胶容量', 'PASS', '44g 小于 228g；安全系数待业务确认。'), ...passCommon]),
      candidate('new-18', 2, 88, 'PASS', '可排', '12A / 228g / 450×450 / 单臂，硬约束通过。', '换模一次，预计增加转模时间。', [check('mold-size', '模具安装面', 'PASS', '尺寸通过。'), check('shot-capacity', '射胶容量', 'PASS', '44g 小于 228g。'), ...passCommon]),
    ],
  },
  {
    id: 'backlog-gt', factoryId: HUAXING, orderNo: 'FFD442209', itemNo: 'DTK01R', moldCode: 'GT1214', productName: '自卸车车轮/座椅（追加单）', quantity: 5000, deliveryDate: '2026-08-12', color: '黑色', material: 'PP 5100NA', shotNetWeightGrams: 379, armRequirement: '双臂', fixtureRequirement: '吸盘', moldDimensions: { length: 550, width: 450, height: 850 }, note: '原型模拟待排单', revision: 1,
    candidates: [
      candidate('old-2', 1, 98, 'PASS', '优先', '同模同色连续；379/617g；安装面 550×450 / 680×680；双臂一致。', '现有队列交期已超，需人工决定同模批次内的插入位置。', [check('mold-size', '模具安装面', 'PASS', '550×450 小于机台 680×680。'), check('shot-capacity', '射胶容量', 'PASS', '379g 小于 617g；安全系数待业务确认。'), check('robot-arm', '机械手能力', 'PASS', '双臂要求与机台一致。'), check('fixture', '夹具要求', 'PASS', '吸盘要求一致。')]),
      candidate('old-31', 2, 42, 'FAIL', '不适配', '24A / 357g，小于整啤净重 379g。', '射胶容量硬约束失败，禁止确认排入。', [check('mold-size', '模具安装面', 'PASS', '安装面可容纳。'), check('shot-capacity', '射胶容量', 'FAIL', '379g 大于机台 357g，硬约束失败。'), check('robot-arm', '机械手能力', 'PASS', '双臂要求通过。'), check('fixture', '夹具要求', 'PASS', '吸盘要求一致。')]),
      candidate('new-36', 3, 76, 'PASS', '可排', '60A / 1260g / 双臂，硬约束通过。', '机台明显偏大，产能利用率与机会成本较差。', [check('mold-size', '模具安装面', 'PASS', '安装面充足。'), check('shot-capacity', '射胶容量', 'PASS', '379g 小于 1260g。'), check('robot-arm', '机械手能力', 'PASS', '双臂要求通过。'), check('fixture', '夹具要求', 'PASS', '吸盘要求一致。')]),
    ],
  },
  {
    id: 'backlog-pamt', factoryId: HUAXING, orderNo: 'BJB251322', itemNo: '9560', moldCode: 'PAMT-01M-01', productName: '水箱', quantity: 12000, deliveryDate: '2026-08-20', color: '透明', material: 'PC HS152R', shotNetWeightGrams: 384, armRequirement: '单臂', fixtureRequirement: '吸盘', moldDimensions: { length: 650, width: 450, height: 550 }, note: '原型模拟待排单', revision: 1,
    candidates: [
      candidate('old-3', 1, 97, 'PASS', '优先', 'PC 螺杆、同模同色连续；384/617g；安装面 650×450 / 680×680。', '当前旧3排程已跨至 9 月，需评估复模并行。', [check('mold-size', '模具安装面', 'PASS', '650×450 小于机台 680×680。'), check('shot-capacity', '射胶容量', 'PASS', '384g 小于 617g。'), check('robot-arm', '机械手能力', 'PASS', '单臂要求一致。'), check('process', '工艺条件', 'PASS', '旧3 标记为 PC 螺杆。')]),
      candidate('old-2', 2, 72, 'REVIEW_REQUIRED', '需复核', '32A / 617g / 680×680，尺寸与重量通过。', '旧2 备注抽芯不行；PC 螺杆条件待确认。', [check('mold-size', '模具安装面', 'PASS', '尺寸通过。'), check('shot-capacity', '射胶容量', 'PASS', '384g 小于 617g。'), check('robot-arm', '机械手能力', 'PASS', '双臂能力覆盖单臂。'), check('process', '工艺条件', 'REVIEW_REQUIRED', 'PC 螺杆与抽芯能力待现场确认。')]),
    ],
  },
]

const fillerBacklog = Array.from({ length: 20 }, (_, index): BacklogOrder => ({
  id: `backlog-generated-${index + 1}`,
  factoryId: HUAXING,
  orderNo: `WAIT-${String(index + 1).padStart(3, '0')}`,
  itemNo: `WAIT-ITEM-${index + 1}`,
  moldCode: `WAIT-MOLD-${String(index + 1).padStart(2, '0')}`,
  productName: `待排注塑件 ${index + 1}`,
  quantity: 1600 + index * 240,
  deliveryDate: `2026-08-${String(8 + (index % 15)).padStart(2, '0')}`,
  color: ['黑色', '蓝色', '绿色'][index % 3],
  material: ['PP 5100NA', 'ABS KF-740'][index % 2],
  shotNetWeightGrams: 32 + index * 2,
  armRequirement: index % 4 === 0 ? '双臂' : '单臂',
  fixtureRequirement: '吸盘',
  moldDimensions: index % 7 === 0 ? null : { length: 280, width: 260, height: 360 },
  note: index % 7 === 0 ? '模具尺寸未补齐' : 'Mock 待排订单',
  revision: 1,
  candidates: [
    candidate(generatedMachines[index].id, 1, index % 7 === 0 ? 65 : 88, index % 7 === 0 ? 'REVIEW_REQUIRED' : 'PASS', index % 7 === 0 ? '需复核' : '可排', index % 7 === 0 ? '缺少模具 L/W/H，不能自动判定安装面。' : '硬约束通过，队列负荷适中。', index % 7 === 0 ? '必须补齐尺寸或由有权限人员人工确认。' : '仍需人工确认插入顺序。', [check('mold-size', '模具安装面', index % 7 === 0 ? 'REVIEW_REQUIRED' : 'PASS', index % 7 === 0 ? 'L/W/H 缺失。' : '尺寸通过。'), check('shot-capacity', '射胶容量', 'PASS', '净重低于机台容量。'), ...passCommon]),
  ],
}))

function createHuaxingSnapshot(): InjectionSchedulingSnapshot {
  const tasks = [...primaryTasks, ...generatedTasks]
  return {
    factoryId: HUAXING,
    factoryName: '华兴',
    sourceMode: 'mock',
    sourceLabel: '华兴啤机日排版表1.xlsx · 只读抽样建模',
    planVersion: '草案 r18',
    planId: 'mock-plan-huaxing',
    planStatus: 'DRAFT',
    planRevision: 18,
    businessDate: PLAN_DATE,
    pollingRevision: 18,
    generatedAt: '2026-07-31 16:18',
    machines: huaxingMachines,
    tasks,
    backlogOrders: [...primaryBacklog, ...fillerBacklog],
    summary: {
      availableMachines: 69,
      totalMachines: 75,
      scheduledTasks: tasks.length,
      overdueTasks: tasks.filter((entry) => entry.slackDays < 0 && entry.status !== 'DONE').length,
      dueSoonTasks: tasks.filter((entry) => entry.slackDays >= 0 && entry.slackDays <= 3 && entry.status !== 'DONE').length,
      remainingQuantity: tasks.reduce((total, entry) => total + Math.max(0, entry.orderQuantity - entry.completedQuantity), 0),
      // The 41.7% figure represents the 1,956-row mold-library readiness sample in the source prototype,
      // not merely the subset of tasks rendered in this workbench.
      moldDimensionCompleteness: 41.7,
      backlogOrders: primaryBacklog.length + fillerBacklog.length,
    },
  }
}

function clone<T>(value: T): T {
  return structuredClone(value)
}

export class MockInjectionSchedulingRepository implements InjectionSchedulingRepository {
  private readonly snapshots = new Map<InjectionFactoryId, InjectionSchedulingSnapshot>([
    [HUAXING, createHuaxingSnapshot()],
  ])

  async getSnapshot(factoryId: InjectionFactoryId): Promise<InjectionSchedulingSnapshot> {
    const snapshot = this.snapshots.get(factoryId)
    if (!snapshot) throw new FactoryDatasetNotFoundError(factoryId)
    return clone(snapshot)
  }

  async saveShiftReport(
    factoryId: InjectionFactoryId,
    taskId: string,
    expectedRevision: number,
    input: ShiftReportInput,
  ): Promise<SaveShiftReportResult> {
    const snapshot = this.requireSnapshot(factoryId)
    const taskEntry = snapshot.tasks.find((entry) => entry.id === taskId && entry.factoryId === factoryId)
    if (!taskEntry) throw new Error(`任务不存在或不属于当前厂区：${taskId}`)
    if (taskEntry.revision !== expectedRevision) throw new OptimisticConflictError(taskId, taskEntry.revision)

    taskEntry.shiftCompleted = Math.max(0, Math.round(input.shiftCompleted))
    taskEntry.completedQuantity = Math.max(0, Math.min(taskEntry.orderQuantity, Math.round(input.cumulativeCompleted)))
    taskEntry.shiftTarget = Math.max(1, Math.round(input.shiftTarget))
    taskEntry.downtimeHours = Math.max(0, Number(input.downtimeHours || 0))
    taskEntry.exceptionType = input.exceptionType?.trim() ?? ''
    taskEntry.status = input.status
    taskEntry.note = input.remark.trim()
    taskEntry.revision += 1
    taskEntry.updatedAt = '2026-07-31 16:30'
    this.refreshSummary(snapshot)

    return { task: clone(taskEntry), auditMessage: `本班回报已保存 · revision ${taskEntry.revision}` }
  }

  async assignBacklogOrder(
    factoryId: InjectionFactoryId,
    backlogOrderId: string,
    machineId: string,
    expectedRevision: number,
  ): Promise<AssignBacklogResult> {
    const snapshot = this.requireSnapshot(factoryId)
    const backlog = snapshot.backlogOrders.find((entry) => entry.id === backlogOrderId && entry.factoryId === factoryId)
    if (!backlog) throw new Error(`待排订单不存在或不属于当前厂区：${backlogOrderId}`)
    if (backlog.revision !== expectedRevision) throw new OptimisticConflictError(backlogOrderId, backlog.revision)
    const selected = backlog.candidates.find((entry) => entry.machineId === machineId)
    if (!selected) throw new Error(`候选机台不属于该订单：${machineId}`)
    if (selected.decision === 'FAIL') throw new Error('硬约束失败的机台禁止确认排入')

    backlog.revision += 1
    backlog.note = `${backlog.note} · 已选 ${selected.machineCode}，等待确认队列位置`
    return { backlogOrder: clone(backlog), auditMessage: `${backlog.orderNo} 已加入 ${selected.machineCode} 排程草案` }
  }

  async evaluateBacklogOrder(factoryId: InjectionFactoryId, backlogOrderId: string) {
    const snapshot = this.requireSnapshot(factoryId)
    const backlog = snapshot.backlogOrders.find((entry) => entry.id === backlogOrderId)
    if (!backlog) throw new Error(`待排订单不存在：${backlogOrderId}`)
    return clone(backlog)
  }

  async simulateExternalTaskUpdate(factoryId: InjectionFactoryId, taskId: string): Promise<void> {
    const snapshot = this.requireSnapshot(factoryId)
    const taskEntry = snapshot.tasks.find((entry) => entry.id === taskId && entry.factoryId === factoryId)
    if (!taskEntry) throw new Error(`任务不存在或不属于当前厂区：${taskId}`)
    taskEntry.revision += 1
    taskEntry.updatedAt = '2026-07-31 16:29'
  }

  async previewImport(): Promise<InjectionSchedulingImportBatchDto> {
    throw new Error('Mock 仓储不执行真实 Excel 导入')
  }

  async confirmImport(): Promise<InjectionSchedulingImportBatchDto> {
    throw new Error('Mock 仓储不执行真实 Excel 导入确认')
  }

  private requireSnapshot(factoryId: InjectionFactoryId) {
    const snapshot = this.snapshots.get(factoryId)
    if (!snapshot) throw new FactoryDatasetNotFoundError(factoryId)
    return snapshot
  }

  private refreshSummary(snapshot: InjectionSchedulingSnapshot) {
    snapshot.summary.scheduledTasks = snapshot.tasks.length
    snapshot.summary.remainingQuantity = snapshot.tasks.reduce(
      (total, entry) => total + Math.max(0, entry.orderQuantity - entry.completedQuantity),
      0,
    )
  }
}

const factoryNames: Record<InjectionFactoryId, string> = {
  huaxing: '华兴',
  'huakang-a': '华康 A',
  'huakang-b': '华康 B',
  'huakang-c': '华康 C',
  'huakang-d': '华康 D',
  huadeng: '华登',
}

function requestId(prefix: string) {
  const random = globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)
  return `${prefix}-${Date.now()}-${random}`
}

function machineArmCapability(machine: InjectionSchedulingMachineDto): '单臂' | '双臂' {
  const capabilities = machine.robot_capabilities.join(' ').toLocaleLowerCase()
  return capabilities.includes('双') || capabilities.includes('dual') ? '双臂' : '单臂'
}

function moldArmRequirement(mold: InjectionSchedulingMoldDto | undefined): '单臂' | '双臂' {
  const requirement = mold?.required_arm_type.toLocaleLowerCase() ?? ''
  return requirement.includes('双') || requirement.includes('dual') ? '双臂' : '单臂'
}

function colorHex(value: string) {
  const palette = ['#111827', '#2563eb', '#059669', '#dc2626', '#7c3aed', '#d97706', '#64748b']
  const hash = Array.from(value).reduce((total, character) => total + character.charCodeAt(0), 0)
  return palette[hash % palette.length]
}

function taskStatus(status: InjectionSchedulingTaskDto['execution_status']): SchedulingTask['status'] {
  if (status === 'COMPLETED') return 'DONE'
  if (status === 'CANCELLED') return 'BLOCKED'
  return status
}

function reportStatus(status: SchedulingTask['status']): 'QUEUED' | 'RUNNING' | 'BLOCKED' | 'COMPLETED' {
  return status === 'DONE' ? 'COMPLETED' : status
}

function machineLoadPercent(tasks: InjectionSchedulingTaskDto[]) {
  const scheduledHours = tasks.reduce((total, task) => {
    const start = Date.parse(task.planned_start)
    const finish = Date.parse(task.planned_finish)
    return total + (Number.isFinite(start) && Number.isFinite(finish) ? Math.max(0, finish - start) / 3_600_000 : 0)
  }, 0)
  return Math.min(100, Math.round(scheduledHours / 24 * 100))
}

function moldDimensions(mold: InjectionSchedulingMoldDto | undefined): MoldDimensions | null {
  if (!mold?.length_mm || !mold.width_mm || !mold.height_mm) return null
  return { length: mold.length_mm, width: mold.width_mm, height: mold.height_mm }
}

function mapTask(
  task: InjectionSchedulingTaskDto,
  order: InjectionSchedulingOrderDto | undefined,
  mold: InjectionSchedulingMoldDto | undefined,
): SchedulingTask {
  const color = mold?.color_profile || '未填写'
  return {
    id: task.id,
    factoryId: task.factory_id as InjectionFactoryId,
    machineId: task.machine_id,
    sequence: task.sequence_no,
    status: taskStatus(task.execution_status),
    priority: order?.priority_code ?? 'NORMAL',
    originalMarker: '',
    moldCode: mold?.mold_no || order?.mold_id || '未关联模具',
    productName: order?.product_name || mold?.name || '未填写产品名称',
    orderNo: order?.order_no || task.order_id,
    itemNo: order?.item_no || '',
    orderQuantity: order?.order_quantity ?? 0,
    completedQuantity: order?.completed_quantity ?? task.reported_quantity,
    shiftTarget: task.shift_target_quantity,
    shiftCompleted: 0,
    downtimeHours: 0,
    exceptionType: '',
    color,
    colorHex: colorHex(color),
    material: mold?.material_name || mold?.material_code || '未填写',
    shotNetWeightGrams: mold?.whole_shot_net_weight_g ?? 0,
    deliveryDate: order?.delivery_due_date || '—',
    plannedStart: task.planned_start,
    plannedEnd: task.planned_finish,
    slackDays: task.delivery_slack_days ?? 999,
    armRequirement: moldArmRequirement(mold),
    fixtureRequirement: mold?.required_fixture_type || '未填写',
    moldDimensions: moldDimensions(mold),
    warehouseOwner: order?.warehouse_text || '',
    note: order?.remark || task.manual_override_reason,
    fitDecision: 'REVIEW_REQUIRED',
    fitScore: 0,
    sourceRow: task.source_row,
    revision: task.revision,
    updatedAt: task.updated_at,
  }
}

function mapBacklogOrder(
  factoryId: InjectionFactoryId,
  order: InjectionSchedulingOrderDto,
  mold: InjectionSchedulingMoldDto | undefined,
): BacklogOrder {
  return {
    id: order.id,
    factoryId,
    orderNo: order.order_no,
    itemNo: order.item_no,
    moldCode: mold?.mold_no || order.mold_id || '未关联模具',
    productName: order.product_name || mold?.name || '未填写产品名称',
    quantity: order.outstanding_quantity,
    deliveryDate: order.delivery_due_date || '—',
    color: mold?.color_profile || '未填写',
    material: mold?.material_name || mold?.material_code || '未填写',
    shotNetWeightGrams: mold?.whole_shot_net_weight_g ?? 0,
    armRequirement: moldArmRequirement(mold),
    fixtureRequirement: mold?.required_fixture_type || '未填写',
    moldDimensions: moldDimensions(mold),
    note: order.remark || '等待阶段 5 候选机台匹配',
    candidates: [],
    revision: order.revision,
  }
}

function constraintKey(ruleCode: string): ConstraintCheck['key'] {
  if (ruleCode.includes('DIMENSION') || ruleCode.includes('THICKNESS')) return 'mold-size'
  if (ruleCode.includes('SHOT')) return 'shot-capacity'
  if (ruleCode.includes('ARM')) return 'robot-arm'
  if (ruleCode.includes('FIXTURE')) return 'fixture'
  return 'process'
}

function mapCandidates(results: Awaited<ReturnType<InjectionSchedulingApi['evaluateMatches']>>['results']): MachineCandidate[] {
  return results.map((result, index) => {
    const constraints: ConstraintCheck[] = [
      ...result.hard_failures.map((reason) => ({
        key: constraintKey(reason.rule_code),
        label: reason.label,
        decision: 'FAIL' as const,
        detail: reason.detail,
      })),
      ...result.warnings.map((reason) => ({
        key: constraintKey(reason.rule_code),
        label: reason.label,
        decision: 'REVIEW_REQUIRED' as const,
        detail: reason.detail,
      })),
    ]
    if (!constraints.length) {
      constraints.push({ key: 'process', label: '全部硬约束', decision: 'PASS', detail: '后端规则引擎未发现硬失败或待复核项。' })
    }
    const scoreExplanation = result.score_breakdown
      .filter((entry) => entry.delta !== 0)
      .map((entry) => `${entry.label} ${entry.delta >= 0 ? '+' : ''}${entry.delta}`)
      .join('；')
    return {
      machineId: result.machine_id,
      machineCode: result.machine_code,
      rank: index + 1,
      score: result.score ?? 0,
      decision: result.decision,
      resultLabel: result.decision === 'PASS' ? '可排' : result.decision === 'REVIEW_REQUIRED' ? '需主管复核' : '硬约束失败',
      explanation: [result.explanation, scoreExplanation].filter(Boolean).join(' '),
      warning: result.warnings.map((entry) => entry.detail).join('；') || result.hard_failures.map((entry) => entry.detail).join('；'),
      constraints,
      ruleSetRevision: result.rule_set_revision,
    }
  })
}

export class HttpInjectionSchedulingRepository implements InjectionSchedulingRepository {
  private readonly snapshots = new Map<InjectionFactoryId, InjectionSchedulingSnapshot>()

  constructor(private readonly api: InjectionSchedulingApi = injectionSchedulingApi) {}

  async getSnapshot(factoryId: InjectionFactoryId): Promise<InjectionSchedulingSnapshot> {
    const [machineResponse, moldResponse, backlogResponse, planResponse] = await Promise.all([
      this.api.listMachines(factoryId),
      this.api.listMolds(factoryId),
      this.api.getBacklog(factoryId),
      this.api.getCurrentPlan(factoryId),
    ])
    const plan = planResponse.plan
    const planTasks = plan?.tasks ?? []
    const orderMap = new Map((plan?.orders ?? []).map((order) => [order.id, order]))
    const moldMap = new Map(moldResponse.items.map((mold) => [mold.id, mold]))
    const tasks = planTasks.map((task) => mapTask(
      task,
      orderMap.get(task.order_id),
      moldMap.get(task.mold_id ?? orderMap.get(task.order_id)?.mold_id ?? ''),
    ))
    const tasksByMachine = new Map<string, InjectionSchedulingTaskDto[]>()
    for (const task of planTasks) {
      const entries = tasksByMachine.get(task.machine_id) ?? []
      entries.push(task)
      tasksByMachine.set(task.machine_id, entries)
    }
    const machines = machineResponse.items.map<InjectionMachine>((machine) => ({
      id: machine.id,
      factoryId,
      code: machine.machine_code,
      zone: [machine.area, machine.position].filter(Boolean).join(' · '),
      machineClass: machine.machine_class || '未分类',
      tonnage: machine.clamping_force_tons ?? 0,
      shotCapacityGrams: machine.injection_capacity_g ?? 0,
      platen: { width: machine.platen_x_mm ?? 0, height: machine.platen_y_mm ?? 0 },
      armCapability: machineArmCapability(machine),
      machineType: machine.machine_type || 'standard',
      processNote: machine.process_restrictions.join('、'),
      loadPercent: machineLoadPercent(tasksByMachine.get(machine.id) ?? []),
    }))
    const backlogOrders = backlogResponse.items.map((order) => mapBacklogOrder(
      factoryId,
      order,
      moldMap.get(order.mold_id ?? ''),
    ))
    const completeMolds = moldResponse.items.filter((mold) => mold.data_quality_status === 'complete').length
    const planStatus = plan?.status ?? 'NONE'
    const snapshot: InjectionSchedulingSnapshot = {
      factoryId,
      factoryName: factoryNames[factoryId],
      sourceMode: 'live',
      sourceLabel: '正式数据库 · Excel 导入批次可追溯',
      planVersion: plan ? `${plan.status === 'DRAFT' ? '草案' : plan.status === 'PUBLISHED' ? '正式' : '归档'} r${plan.revision}` : '尚未建立计划',
      planId: plan?.id ?? '',
      planStatus,
      planRevision: plan?.revision ?? 0,
      businessDate: plan?.business_date ?? new Date().toISOString().slice(0, 10),
      pollingRevision: planResponse.polling_revision,
      generatedAt: plan?.updated_at ?? new Date().toISOString(),
      machines,
      tasks,
      backlogOrders,
      summary: {
        availableMachines: new Set(tasks.map((task) => task.machineId)).size,
        totalMachines: machines.length,
        scheduledTasks: tasks.length,
        overdueTasks: tasks.filter((task) => task.status !== 'DONE' && task.slackDays < 0).length,
        dueSoonTasks: tasks.filter((task) => task.status !== 'DONE' && task.slackDays >= 0 && task.slackDays <= 3).length,
        remainingQuantity: tasks.reduce((total, task) => total + Math.max(0, task.orderQuantity - task.completedQuantity), 0),
        moldDimensionCompleteness: moldResponse.items.length ? completeMolds / moldResponse.items.length * 100 : 0,
        backlogOrders: backlogOrders.length,
      },
    }
    this.snapshots.set(factoryId, snapshot)
    return snapshot
  }

  async saveShiftReport(
    factoryId: InjectionFactoryId,
    taskId: string,
    expectedRevision: number,
    input: ShiftReportInput,
  ): Promise<SaveShiftReportResult> {
    const snapshot = this.snapshots.get(factoryId)
    if (!snapshot || snapshot.planStatus !== 'PUBLISHED') {
      throw new Error('只有已发布计划的执行中任务可以提交生产回报')
    }
    try {
      await this.api.saveShiftReport(taskId, {
        factory_id: factoryId,
        expected_revision: expectedRevision,
        request_id: requestId('shift-report'),
        business_date: snapshot.businessDate,
        shift_code: new Date().getHours() >= 20 || new Date().getHours() < 8 ? 'NIGHT' : 'DAY',
        quantity_mode: 'CUMULATIVE',
        reported_quantity: input.cumulativeCompleted,
        shift_target_quantity: input.shiftTarget,
        downtime_minutes: Math.round(input.downtimeHours * 60),
        exception_code: input.exceptionType,
        exception_detail: input.remark,
        reported_status: reportStatus(input.status),
      })
      const refreshed = await this.getSnapshot(factoryId)
      const task = refreshed.tasks.find((entry) => entry.id === taskId)
      if (!task) throw new Error('生产回报已保存，但刷新后未找到对应任务')
      return { task, auditMessage: `本班回报已保存 · revision ${task.revision}` }
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 409) {
        const detail = error.response.data?.detail
        const currentRevision = typeof detail === 'object' && detail && 'current_revision' in detail
          ? Number(detail.current_revision)
          : expectedRevision
        throw new OptimisticConflictError(taskId, currentRevision)
      }
      throw new Error(getApiErrorMessage(error))
    }
  }

  async evaluateBacklogOrder(factoryId: InjectionFactoryId, backlogOrderId: string) {
    const snapshot = this.snapshots.get(factoryId)
    const backlog = snapshot?.backlogOrders.find((entry) => entry.id === backlogOrderId)
    if (!snapshot || !backlog) throw new Error('待排订单不存在或正式快照尚未加载')
    try {
      const evaluation = await this.api.evaluateMatches(factoryId, backlogOrderId)
      backlog.candidates = mapCandidates(evaluation.results)
      return structuredClone(backlog)
    } catch (error) {
      throw new Error(getApiErrorMessage(error))
    }
  }

  async assignBacklogOrder(
    factoryId: InjectionFactoryId,
    backlogOrderId: string,
    machineId: string,
    expectedRevision: number,
    overrideReason = '',
  ): Promise<AssignBacklogResult> {
    const snapshot = this.snapshots.get(factoryId)
    const backlog = snapshot?.backlogOrders.find((entry) => entry.id === backlogOrderId)
    if (!snapshot || !backlog) throw new Error('待排订单不存在或正式快照尚未加载')
    if (snapshot.planStatus !== 'DRAFT' || !snapshot.planId) throw new Error('请先创建或导入计划草案，再确认候选机台')
    if (backlog.revision !== expectedRevision) throw new OptimisticConflictError(backlog.id, backlog.revision)
    const candidate = backlog.candidates.find((entry) => entry.machineId === machineId)
    if (!candidate) throw new Error('候选结果已失效，请重新计算')
    if (candidate.decision === 'FAIL') throw new Error('硬约束失败的机台禁止排入草案')
    if (candidate.decision === 'REVIEW_REQUIRED' && !overrideReason.trim()) {
      throw new Error('资料待复核的候选必须填写人工覆盖原因')
    }
    try {
      await this.api.confirmSuggestion(snapshot.planId, {
        factory_id: factoryId,
        order_id: backlog.id,
        machine_id: machineId,
        expected_plan_revision: snapshot.planRevision,
        expected_rule_revision: candidate.ruleSetRevision,
        request_id: requestId('match-confirm'),
        override_reason: overrideReason.trim(),
      })
      return {
        backlogOrder: { ...structuredClone(backlog), note: `${backlog.note} · 已确认 ${candidate.machineCode}` },
        auditMessage: `${backlog.orderNo} 已加入 ${candidate.machineCode} 排程草案`,
      }
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 409) {
        const detail = error.response.data?.detail
        const currentRevision = typeof detail === 'object' && detail && 'current_revision' in detail
          ? Number(detail.current_revision)
          : snapshot.planRevision
        if (typeof detail === 'object' && detail && 'current_revision' in detail) {
          throw new OptimisticConflictError(snapshot.planId, currentRevision)
        }
      }
      throw new Error(getApiErrorMessage(error))
    }
  }

  async simulateExternalTaskUpdate(): Promise<void> {
    throw new Error('正式数据模式不提供模拟并发更新')
  }

  async previewImport(factoryId: InjectionFactoryId, file: File) {
    try {
      return await this.api.previewImport(factoryId, file, 0, requestId('import-preview'))
    } catch (error) {
      throw new Error(getApiErrorMessage(error))
    }
  }

  async confirmImport(
    factoryId: InjectionFactoryId,
    batch: InjectionSchedulingImportBatchDto,
    input: {
      businessDate: string
      planStatus: InjectionSchedulingSnapshot['planStatus']
      planRevision: number
      acknowledgedBlockingIssueIds: string[]
    },
  ) {
    try {
      const mergeDraft = input.planStatus === 'DRAFT'
      return await this.api.confirmImport(batch.id, {
        factory_id: factoryId,
        expected_revision: batch.revision,
        expected_plan_revision: mergeDraft ? input.planRevision : 0,
        request_id: requestId('import-confirm'),
        confirm_mode: mergeDraft ? 'merge_draft' : 'create_draft',
        business_date: input.businessDate,
        acknowledged_blocking_issue_ids: input.acknowledgedBlockingIssueIds,
      })
    } catch (error) {
      throw new Error(getApiErrorMessage(error))
    }
  }
}

export const injectionSchedulingRepository: InjectionSchedulingRepository = import.meta.env.MODE === 'test'
  ? new MockInjectionSchedulingRepository()
  : new HttpInjectionSchedulingRepository()

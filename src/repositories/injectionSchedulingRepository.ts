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
  ): Promise<AssignBacklogResult>
  simulateExternalTaskUpdate(factoryId: InjectionFactoryId, taskId: string): Promise<void>
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
  return { machineId, machineCode: machineEntry.code, rank, score, decision, resultLabel, explanation, warning, constraints }
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

  async simulateExternalTaskUpdate(factoryId: InjectionFactoryId, taskId: string): Promise<void> {
    const snapshot = this.requireSnapshot(factoryId)
    const taskEntry = snapshot.tasks.find((entry) => entry.id === taskId && entry.factoryId === factoryId)
    if (!taskEntry) throw new Error(`任务不存在或不属于当前厂区：${taskId}`)
    taskEntry.revision += 1
    taskEntry.updatedAt = '2026-07-31 16:29'
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

export const injectionSchedulingRepository = new MockInjectionSchedulingRepository()

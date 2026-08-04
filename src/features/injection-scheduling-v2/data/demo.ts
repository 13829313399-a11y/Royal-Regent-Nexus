import type { AuditEvent, MachineRecord, MoldRecord, OrderRecord, ScheduleTaskRecord } from '../types'

export const demoMachines: MachineRecord[] = [
  ['m-old2', '旧2', '旧2', 32, 617, ['双臂'], ['吸盘', '夹子'], ['不可抽芯'], 'running'],
  ['m-old3', '旧3', '旧3', 32, 617, ['单臂'], ['吸盘'], ['PC 螺杆'], 'running'],
  ['m-old9', '旧9', '旧9', 18, 289, ['双臂'], ['吸盘', '夹子'], [], 'running'],
  ['m-old12', '旧12', '旧12', 12, 228, ['双臂', '单臂'], ['吸盘'], ['不可抽芯'], 'running'],
  ['m-new25', '新25', '25', 12, 217, ['双臂', '单臂'], ['吸盘', '夹子'], [], 'running'],
  ['m-new27', '新27', '27', 12, 217, ['双臂', '单臂'], ['吸盘', '夹子'], [], 'maintenance'],
].map(([id, code, position, aClass, injectionCapacityG, armCapabilities, fixtureCapabilities, processRestrictions, status]) => ({
  id: String(id), code: String(code), position: String(position), area: '注塑车间', aClass: Number(aClass), aClassRaw: `${aClass}A`,
  injectionCapacityG: Number(injectionCapacityG), armCapabilities: armCapabilities as string[], fixtureCapabilities: fixtureCapabilities as string[],
  processRestrictions: processRestrictions as string[], machineType: 'standard', specialMachineType: '', status: status as MachineRecord['status'], normalizationStatus: 'COMPLETE',
}))

const moldSeed = [
  ['mo-1', 'GT1214', '自卸车车轮/座椅', 32, 379, '双臂', '吸盘', 'PP 5100NA', '黑色'],
  ['mo-2', 'PAMT-01M-01', '水箱', 32, 384, '单臂', '吸盘', 'PC HS152R', '透明'],
  ['mo-3', 'MNVN-19M-06', '包装底座', 14, 55.45, '双臂', '吸盘', '1#PP AV161', '黄色'],
  ['mo-4', 'BBT 45849-03', '枪顶左右盖', 7, 44, '单臂', '吸盘', 'ABS KF-740', '蓝色'],
  ['mo-5', 'T01-JS001-00800000', '过滤漏斗', 7, 21, '双臂', '吸盘', 'ABS KF-740', '浅蓝'],
  ['mo-6', '20 383 5003-003', '自行车支撑架', 14, 5.6, '单臂', '夹子', '1#PP AV161', '蓝色'],
]
export const demoMolds: MoldRecord[] = moldSeed.map(([id, moldNo, name, aClass, netWeightG, requiredArmType, requiredFixtureType, materialName, colorProfile]) => ({
  id: String(id), moldNo: String(moldNo), name: String(name), aClass: Number(aClass), aClassRaw: `${aClass}A`, netWeightG: Number(netWeightG), grossWeightG: Number(netWeightG) * 1.08,
  requiredArmType: String(requiredArmType), requiredFixtureType: String(requiredFixtureType), materialCode: '', materialName: String(materialName), colorProfile: String(colorProfile),
  processRequirements: id === 'mo-6' ? ['抽芯'] : [], specialMachineType: '', normalizationStatus: id === 'mo-6' ? 'REVIEW_REQUIRED' : 'COMPLETE',
}))

const orderSeed = [
  ['o-1', 'FFD442145', 'DTK01R', '自卸车、消防车车轮/座椅', 'mo-1', 3528, 3410, '2026-07-24', -14.5, 'CRITICAL', 'ready'],
  ['o-2', 'FFD442174', 'GT1283', '自卸车、消防车车轮/座椅', 'mo-1', 1505, 0, '2026-07-24', -15.6, 'NORMAL', 'ready'],
  ['o-3', 'BJB250791', '9560', '水箱', 'mo-2', 30000, 23765, '2026-06-05', -67.9, 'URGENT', 'partial'],
  ['o-4', 'DG002', '77794', '包装底座', 'mo-3', 100000, 12210, '2026-08-24', -6.5, 'CRITICAL', 'ready'],
  ['o-5', 'BJB251273', '45841', '枪顶左右盖', 'mo-4', 1901, 100, '2026-08-07', -0.9, 'NORMAL', 'ready'],
  ['o-6', 'BJB251275', 'F12-JS002-C0050000', '过滤漏斗', 'mo-5', 1505, 420, '2026-07-24', -15, 'URGENT', 'ready'],
  ['o-7', 'BJB251280', '20 383 7021', '自行车支撑架', 'mo-6', 2700, 0, '2026-08-17', 2.2, 'URGENT', 'blocked'],
  ['o-8', 'BJB251146', '57520', '水樽左右壳', null, 2400, 0, '2026-05-20', -76, 'CRITICAL', 'partial'],
] as const
export const demoOrders: OrderRecord[] = orderSeed.map(([id, orderNo, itemNo, productName, moldId, quantity, completed, due, slack, priority, readiness], index) => ({
  id, orderNo, itemNo, productName, moldId, orderQuantity: quantity, sourceCompletedQuantity: completed, completedQuantity: completed, outstandingQuantity: quantity - completed,
  completionRate: quantity ? completed / quantity : 0, deliveryStartDate: '', deliveryDueDate: due, deliverySlackDays: slack,
  priorityCode: priority, materialReadinessStatus: readiness, warehouseText: index % 2 ? '四楼刘杰' : '李诗收',
  remark: id === 'o-7' ? '需要抽芯能力复核' : '', status: index >= 6 ? 'BACKLOG' : 'SCHEDULED',
  lineage: { set_quantity: quantity * 2, powder: index % 2 ? '49215' : '黑种', order_date: '2026-07-18', spray: index === 3 ? '是' : '否' }, revision: 1,
}))

export const demoTasks: ScheduleTaskRecord[] = [
  ['t-1', 'm-old2', 'o-1', 'mo-1', 1, 'RUNNING', '2026-08-04 09:42', '2026-08-04 11:44', 1400, 630],
  ['t-2', 'm-old2', 'o-2', 'mo-1', 2, 'QUEUED', '2026-08-04 11:44', '2026-08-05 13:32', 1400, 0],
  ['t-3', 'm-old3', 'o-3', 'mo-2', 1, 'RUNNING', '2026-08-04 09:42', '2026-08-08 20:36', 1400, 520],
  ['t-4', 'm-old9', 'o-4', 'mo-3', 1, 'RUNNING', '2026-08-04 09:42', '2026-08-27 12:10', 3800, 920],
  ['t-5', 'm-old12', 'o-5', 'mo-4', 1, 'RUNNING', '2026-08-04 09:42', '2026-08-04 20:28', 4000, 470],
  ['t-6', 'm-new25', 'o-6', 'mo-5', 1, 'RUNNING', '2026-08-04 09:42', '2026-08-04 22:04', 2700, 420],
].map(([id, machineId, orderId, moldId, sequence, status, plannedStart, plannedFinish, targetQuantity, reportedQuantity]) => ({
  id: String(id), planId: 'DEMO-PLAN', machineId: String(machineId), orderId: String(orderId), moldId: String(moldId), sequence: Number(sequence), status: status as ScheduleTaskRecord['status'],
  plannedStart: String(plannedStart), plannedFinish: String(plannedFinish), targetQuantity: Number(targetQuantity), reportedQuantity: Number(reportedQuantity),
  sourceSheetName: '啤机部排机表', sourceRow: Number(sequence) + 6, locked: status === 'RUNNING', manualOverrideReason: '',
  activeExecution: true, estimatedStart: String(plannedStart), estimatedFinish: String(plannedFinish), estimatedRemainingShifts: 1,
  deliverySlackDays: null, revision: 1,
}))

export const demoEvents: AuditEvent[] = [
  { id: 'ev-4', sequence: 4, eventType: 'AUTO_SCHEDULE_PREVIEWED', entityType: 'plan', entityId: 'DEMO-PLAN', entityRevision: 7, requestId: 'demo-4', actorName: '啤机文员 · 张敏', createdAt: '2026-08-04 10:18', detail: { assigned: 8, review: 2, score: 91 } },
  { id: 'ev-3', sequence: 3, eventType: 'PLAN_PUBLISHED', entityType: 'plan', entityId: 'DEMO-PLAN', entityRevision: 6, requestId: 'demo-3', actorName: 'PMC · 陈伟', createdAt: '2026-08-04 09:42', detail: { assigned: 26, review: 3, score: 87 } },
  { id: 'ev-2', sequence: 2, eventType: 'PLAN_IMPORTED', entityType: 'plan', entityId: 'DEMO-PLAN', entityRevision: 5, requestId: 'demo-2', actorName: '啤机文员 · 张敏', createdAt: '2026-08-03 16:26', detail: { assigned: 18, review: 1, score: 89 } },
]

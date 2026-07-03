import type { FactoryContextId, ProductionFactoryContextId } from '@/data/enterpriseMock'
import {
  applyCostPreviewToItems,
  buildCompletionGate,
  isExternalMoldingSampleOrder,
} from '@/lib/moldingSampleBusiness'
import {
  moldingSampleMaterialPrices,
  moldingSampleRmbToHkdRate,
} from '@/data/moldingSampleCostMock'
import type {
  MoldingSampleAuditLog,
  MoldingSampleItem,
  MoldingSampleOrder,
  MoldingSampleProblem,
  MoldingSampleRequisition,
  MoldingSampleStatus,
  MoldingSampleWorkflowRecord,
} from '@/types/moldingSample'

const fallbackFactoryId: ProductionFactoryContextId = 'huakang-a'
const moldingSampleFactoryIds: ProductionFactoryContextId[] = [
  'huakang-a',
  'huakang-b',
  'huadeng',
  'huaxing',
]

function isMoldingSampleFactoryId(factoryId: string): factoryId is ProductionFactoryContextId {
  return moldingSampleFactoryIds.includes(factoryId as ProductionFactoryContextId)
}

function createOrder(input: Omit<MoldingSampleOrder, 'order_type' | 'created_at' | 'updated_at'> & Partial<Pick<MoldingSampleOrder, 'order_type' | 'created_at' | 'updated_at'>>): MoldingSampleOrder {
  return {
    order_type: '啤办',
    created_at: `${input.date} 09:30`,
    updated_at: `${input.date} 09:30`,
    ...input,
  }
}

function createItem(input: Omit<MoldingSampleItem, 'sort_order' | 'gross_weight_g' | 'required_material_kg' | 'mold_return_time' | 'completion_time' | 'notes' | 'receipt_no' | 'collected_weight_kg' | 'actual_weight_kg' | 'actual_amount_hkd' | 'injection_cost' | 'injection_cost_hkd' | 'exchange_rate_at_save'> & Partial<Pick<MoldingSampleItem, 'sort_order' | 'gross_weight_g' | 'required_material_kg' | 'mold_return_time' | 'completion_time' | 'notes' | 'receipt_no' | 'collected_weight_kg' | 'actual_weight_kg' | 'actual_amount_hkd' | 'injection_cost' | 'injection_cost_hkd' | 'exchange_rate_at_save'>>): MoldingSampleItem {
  return {
    sort_order: 1,
    gross_weight_g: null,
    required_material_kg: null,
    mold_return_time: '',
    completion_time: '',
    notes: '',
    receipt_no: '',
    collected_weight_kg: null,
    actual_weight_kg: null,
    actual_amount_hkd: null,
    injection_cost: null,
    injection_cost_hkd: null,
    exchange_rate_at_save: null,
    ...input,
  }
}

function createAudit(
  order: MoldingSampleOrder,
  index: number,
  action: string,
  actorName: string,
  fromStatus: MoldingSampleStatus,
  toStatus: MoldingSampleStatus,
  reason: string,
): MoldingSampleAuditLog {
  return {
    id: `${order.id}-audit-${String(index).padStart(3, '0')}`,
    order_id: order.id,
    action,
    actor_name: actorName,
    actor_role: action.includes('经理') ? '经理' : action.includes('主管') ? '主管' : '工程部',
    decision: action.includes('驳回') ? '驳回' : action.includes('重提') ? '重提' : action.includes('提交') ? '提交' : '通过',
    from_status: fromStatus,
    to_status: toStatus,
    reason,
    created_at: `${order.date} ${String(9 + index).padStart(2, '0')}:15`,
    tone: action.includes('驳回') ? 'red' : action.includes('经理') ? 'blue' : 'teal',
  }
}

function createRequisitions(order: MoldingSampleOrder, items: MoldingSampleItem[]): MoldingSampleRequisition[] {
  if (isExternalMoldingSampleOrder(order)) {
    return []
  }

  return items.slice(0, 2).map((item, index) => ({
    id: `${order.id}-req-${index + 1}`,
    req_number: `LL-${order.date.replaceAll('-', '')}-${String(index + 1).padStart(3, '0')}`,
    date: order.date,
    order_id: order.id,
    order_number: order.order_number,
    material: item.material,
    requested_weight_kg: item.required_material_kg,
    applicant: order.eng_name,
    notes: item.color,
    inventory_batch_id: '',
    inventory_batch_no: '',
    status: item.collected_weight_kg ? '已出库' : '待出库',
    issued_at: item.collected_weight_kg ? `${order.date} 15:20` : '',
    created_at: `${order.date} 09:00`,
    updated_at: `${order.date} 09:00`,
  }))
}

function createRecord(
  factoryId: ProductionFactoryContextId,
  order: MoldingSampleOrder,
  items: MoldingSampleItem[],
  auditLogs: MoldingSampleAuditLog[],
  problems: MoldingSampleProblem[] = [],
): MoldingSampleWorkflowRecord {
  const isExternalOrder = isExternalMoldingSampleOrder(order)
  const costedItems = applyCostPreviewToItems(
    items,
    moldingSampleMaterialPrices,
    moldingSampleRmbToHkdRate,
    isExternalOrder,
  )

  return {
    factory_id: factoryId,
    order,
    items: costedItems,
    audit_logs: auditLogs,
    requisitions: createRequisitions(order, costedItems),
    problems,
  }
}

const huakangAOrder = createOrder({
  id: 'BP-62437',
  factory_id: 'huakang-a',
  order_number: '62437',
  doc_number: 'W-G026-00',
  product_name: '链条枪',
  client_name: 'BuzzBee',
  date: '2026-04-09',
  stage: 'T0',
  workshop: 'A车间',
  send_to: '',
  supervisor: '李主管',
  eng_name: '肖科',
  reason: '见客样办，枪身不可刮花，颜色要对办，工程订色粉。',
  status: '待审核',
  reject_reason: '',
  completed_date: '',
})

const huakangAItems: MoldingSampleItem[] = [
  createItem({
    id: 'BP-62437-001',
    order_id: huakangAOrder.id,
    sort_order: 1,
    mold_id: 'BBT62450-A-01',
    mold_name: '左右枪身A款',
    machine_type: '待工程确认',
    material: 'HIPS 425',
    color: '深绿色 / PMS 2272C',
    pigment_no: '71139',
    quantity: '1/1',
    shoot_qty: 30,
    mold_return_time: '2026-04-13',
    completion_time: '2026-04-13',
  }),
  createItem({
    id: 'BP-62437-002',
    order_id: huakangAOrder.id,
    sort_order: 2,
    mold_id: 'BBT62450-A-02',
    mold_name: 'A款装饰件',
    machine_type: '待工程确认',
    material: 'ABS 740',
    color: '暗蓝色 / PMS 2935C',
    pigment_no: '71120',
    quantity: '1/1',
    shoot_qty: 30,
    mold_return_time: '2026-04-13',
    completion_time: '2026-04-13',
  }),
  createItem({
    id: 'BP-62437-003',
    order_id: huakangAOrder.id,
    sort_order: 3,
    mold_id: 'BBT62450-A-02-2',
    mold_name: '手柄饰件',
    machine_type: '待工程确认',
    material: 'ABS 740',
    color: '暗蓝色 / PMS 2935C',
    pigment_no: '71120',
    quantity: '1/1',
    shoot_qty: 30,
    mold_return_time: '2026-04-13',
    completion_time: '2026-04-13',
  }),
  createItem({
    id: 'BP-62437-004',
    order_id: huakangAOrder.id,
    sort_order: 4,
    mold_id: 'BBT62450-B-01',
    mold_name: '左右枪身B款',
    machine_type: '待工程确认',
    material: 'HIPS 425',
    color: '暗蓝色 / PMS 2935C',
    pigment_no: '70039',
    quantity: '1/1',
    shoot_qty: 30,
    mold_return_time: '2026-04-13',
    completion_time: '2026-04-13',
  }),
  createItem({
    id: 'BP-62437-005',
    order_id: huakangAOrder.id,
    sort_order: 5,
    mold_id: 'BBT62450-B-02',
    mold_name: 'B款装饰件',
    machine_type: '待工程确认',
    material: 'ABS 740',
    color: '深绿色 / PMS 2272C',
    pigment_no: '70040',
    quantity: '1/1',
    shoot_qty: 30,
    mold_return_time: '2026-04-13',
    completion_time: '2026-04-13',
  }),
  createItem({
    id: 'BP-62437-006',
    order_id: huakangAOrder.id,
    sort_order: 6,
    mold_id: 'BBT62450-04',
    mold_name: '拉环',
    machine_type: '待工程确认',
    material: 'PP AV161',
    color: '深蓝色 / PMS 7694C',
    pigment_no: '71137',
    quantity: '1/1',
    shoot_qty: 30,
    mold_return_time: '2026-04-13',
    completion_time: '2026-04-13',
  }),
  createItem({
    id: 'BP-62437-007',
    order_id: huakangAOrder.id,
    sort_order: 7,
    mold_id: 'BBT62659-01',
    mold_name: '左右枪身',
    machine_type: '待工程确认',
    material: 'HIPS 425',
    color: '暗蓝色 / PMS 2935C',
    pigment_no: '70039',
    quantity: '1/1',
    shoot_qty: 30,
    mold_return_time: '2026-04-13',
    completion_time: '2026-04-13',
  }),
  createItem({
    id: 'BP-62437-008',
    order_id: huakangAOrder.id,
    sort_order: 8,
    mold_id: 'BBT62659-01',
    mold_name: '左右枪身',
    machine_type: '待工程确认',
    material: 'HIPS 425',
    color: '深绿色 / PMS 2272C',
    pigment_no: '71139',
    quantity: '1/1',
    shoot_qty: 30,
    mold_return_time: '2026-04-13',
    completion_time: '2026-04-13',
  }),
  createItem({
    id: 'BP-62437-009',
    order_id: huakangAOrder.id,
    sort_order: 9,
    mold_id: 'BBT62659-02',
    mold_name: '左右手柄',
    machine_type: '待工程确认',
    material: 'ABS 740',
    color: '暗蓝色 / PMS 2935C',
    pigment_no: '71120',
    quantity: '1/1',
    shoot_qty: 30,
    mold_return_time: '2026-04-13',
    completion_time: '2026-04-13',
  }),
  createItem({
    id: 'BP-62437-010',
    order_id: huakangAOrder.id,
    sort_order: 10,
    mold_id: 'BBT62659-02',
    mold_name: '左右手柄',
    machine_type: '待工程确认',
    material: 'ABS 740',
    color: '深绿色 / PMS 2272C',
    pigment_no: '70040',
    quantity: '1/1',
    shoot_qty: 30,
    mold_return_time: '2026-04-13',
    completion_time: '2026-04-13',
  }),
  createItem({
    id: 'BP-62437-011',
    order_id: huakangAOrder.id,
    sort_order: 11,
    mold_id: 'BBT62659-03',
    mold_name: '左右枪身装饰件',
    machine_type: '待工程确认',
    material: 'ABS 740',
    color: '暗蓝色 / PMS 2935C',
    pigment_no: '71120',
    quantity: '1/1',
    shoot_qty: 30,
    mold_return_time: '2026-04-13',
    completion_time: '2026-04-13',
  }),
  createItem({
    id: 'BP-62437-012',
    order_id: huakangAOrder.id,
    sort_order: 12,
    mold_id: 'BBT62659-03',
    mold_name: '左右枪身装饰件',
    machine_type: '待工程确认',
    material: 'ABS 740',
    color: '深绿色 / PMS 2272C',
    pigment_no: '70040',
    quantity: '1/1',
    shoot_qty: 30,
    mold_return_time: '2026-04-13',
    completion_time: '2026-04-13',
  }),
  createItem({
    id: 'BP-62437-013',
    order_id: huakangAOrder.id,
    sort_order: 13,
    mold_id: 'BBT62659-04',
    mold_name: '左右枪身长装饰件',
    machine_type: '待工程确认',
    material: 'PP AV161',
    color: '暗蓝色 / PMS 2935C',
    pigment_no: '71120',
    quantity: '1/1',
    shoot_qty: 30,
    mold_return_time: '2026-04-13',
    completion_time: '2026-04-13',
  }),
  createItem({
    id: 'BP-62437-014',
    order_id: huakangAOrder.id,
    sort_order: 14,
    mold_id: 'BBT62659-04',
    mold_name: '左右枪身长装饰件',
    machine_type: '待工程确认',
    material: 'PP AV161',
    color: '深绿色 / PMS 2272C',
    pigment_no: '70040',
    quantity: '1/1',
    shoot_qty: 30,
    mold_return_time: '2026-04-13',
    completion_time: '2026-04-13',
  }),
]

const huakangBOrder = createOrder({
  id: 'BP-73120',
  factory_id: 'huakang-b',
  order_number: '73120',
  doc_number: 'W-G041-00',
  product_name: '双色泡泡枪',
  client_name: 'FunPlay',
  date: '2026-04-12',
  stage: 'EP',
  workshop: 'B车间',
  send_to: '',
  supervisor: '陈主管',
  eng_name: '林工',
  reason: '客户要求确认透明件和外壳配色，优先安排试啤。',
  status: '待经理审核',
  reject_reason: '',
  completed_date: '',
})

const huakangBItems: MoldingSampleItem[] = [
  createItem({
    id: 'BP-73120-001',
    order_id: huakangBOrder.id,
    sort_order: 1,
    mold_id: 'FP73120-01',
    mold_name: '透明水箱',
    machine_type: '200T',
    material: 'PC 110',
    color: '透明',
    pigment_no: 'N/A',
    quantity: '1/1',
    shoot_qty: 20,
    gross_weight_g: 96,
    required_material_kg: 1.92,
    mold_return_time: '2026-04-13',
    completion_time: '2026-04-15',
  }),
  createItem({
    id: 'BP-73120-002',
    order_id: huakangBOrder.id,
    sort_order: 2,
    mold_id: 'FP73120-02',
    mold_name: '左右外壳',
    machine_type: '180T',
    material: 'ABS 757',
    color: '浅紫色',
    pigment_no: '80122',
    quantity: '1/1',
    shoot_qty: 20,
    gross_weight_g: 74,
    required_material_kg: 1.48,
    mold_return_time: '2026-04-13',
    completion_time: '2026-04-15',
  }),
]

const huadengOrder = createOrder({
  id: 'BP-90818',
  factory_id: 'huadeng',
  order_number: '90818',
  doc_number: 'W-G052-00',
  product_name: '飞盘发射器',
  client_name: 'Spark Toys',
  date: '2026-04-16',
  stage: 'FEP',
  workshop: '模厂',
  send_to: '发至模厂',
  supervisor: '何主管',
  eng_name: '周工',
  reason: '模厂直接出办给工程确认，内部啤机部不参与生产。',
  status: '已完成',
  reject_reason: '',
  completed_date: '2026-04-17',
})

const huadengItems: MoldingSampleItem[] = [
  createItem({
    id: 'BP-90818-001',
    order_id: huadengOrder.id,
    sort_order: 1,
    mold_id: 'HD90818-01',
    mold_name: '发射盘',
    machine_type: '模厂',
    material: 'ABS 747',
    color: '橙色',
    pigment_no: '90210',
    quantity: '1/1',
    shoot_qty: 15,
    gross_weight_g: 112,
    required_material_kg: 1.68,
    collected_weight_kg: 1.7,
    mold_return_time: '2026-04-16',
    completion_time: '2026-04-17',
  }),
  createItem({
    id: 'BP-90818-002',
    order_id: huadengOrder.id,
    sort_order: 2,
    mold_id: 'HD90818-02',
    mold_name: '手柄',
    machine_type: '模厂',
    material: '70% ABS 750W + 30% ABS抽粒',
    color: '白色',
    pigment_no: 'N/A',
    quantity: '1/1',
    shoot_qty: 15,
    gross_weight_g: 66,
    required_material_kg: 0.99,
    collected_weight_kg: 1.05,
    mold_return_time: '2026-04-16',
    completion_time: '2026-04-17',
  }),
]

const huaxingOrder = createOrder({
  id: 'BP-56206',
  factory_id: 'huaxing',
  order_number: '56206',
  doc_number: 'W-G063-00',
  product_name: '软弹枪配色',
  client_name: 'Prime Kids',
  date: '2026-04-20',
  stage: 'PP',
  workshop: 'A车间',
  send_to: '',
  supervisor: '黄主管',
  eng_name: '梁工',
  reason: 'PP 前最后一次颜色确认，需同步补录啤办费。',
  status: '生产中',
  reject_reason: '',
  completed_date: '',
})

const huaxingItems: MoldingSampleItem[] = [
  createItem({
    id: 'BP-56206-001',
    order_id: huaxingOrder.id,
    sort_order: 1,
    mold_id: 'PK56206-01',
    mold_name: '左右枪身',
    machine_type: '180T',
    material: 'HIPS 425',
    color: '军绿色',
    pigment_no: '91220',
    quantity: '1/1',
    shoot_qty: 25,
    gross_weight_g: 91,
    required_material_kg: 2.28,
    receipt_no: 'LL-20260420-001',
    collected_weight_kg: 2.4,
    actual_weight_kg: 2.18,
    injection_cost: 120,
    mold_return_time: '2026-04-20',
    completion_time: '2026-04-22',
  }),
  createItem({
    id: 'BP-56206-002',
    order_id: huaxingOrder.id,
    sort_order: 2,
    mold_id: 'PK56206-02',
    mold_name: '弹匣',
    machine_type: '120T',
    material: 'POM 900P',
    color: '黑色',
    pigment_no: 'B-01',
    quantity: '1/1',
    shoot_qty: 25,
    gross_weight_g: 41,
    required_material_kg: 1.03,
    receipt_no: 'LL-20260420-002',
    collected_weight_kg: 1.1,
    actual_weight_kg: null,
    injection_cost: null,
    mold_return_time: '2026-04-20',
    completion_time: '2026-04-22',
    notes: '待啤机部补实际用料',
  }),
]

export const moldingSampleFactoryRecords: Record<ProductionFactoryContextId, MoldingSampleWorkflowRecord> = {
  'huakang-a': createRecord(
    'huakang-a',
    huakangAOrder,
    huakangAItems,
    [
      createAudit(huakangAOrder, 1, '工程提交主管审核', huakangAOrder.eng_name, '待审核', '待审核', '工程开单完成，等待主管审核。'),
    ],
  ),
  'huakang-b': createRecord(
    'huakang-b',
    huakangBOrder,
    huakangBItems,
    [
      createAudit(huakangBOrder, 1, '工程提交主管审核', huakangBOrder.eng_name, '待审核', '待审核', '工程开单完成。'),
      createAudit(huakangBOrder, 2, '主管通过', huakangBOrder.supervisor, '待审核', '待经理审核', '主管确认用料和交期。'),
    ],
  ),
  huadeng: createRecord(
    'huadeng',
    huadengOrder,
    huadengItems,
    [
      createAudit(huadengOrder, 1, '工程提交主管审核', huadengOrder.eng_name, '待审核', '待审核', '外发模厂单提交审核。'),
      createAudit(huadengOrder, 2, '主管通过', huadengOrder.supervisor, '待审核', '待经理审核', '主管确认模厂分支。'),
      createAudit(huadengOrder, 3, '经理通过', '王经理', '待经理审核', '已完成', '外厂单经理通过后自动完成。'),
    ],
  ),
  huaxing: createRecord(
    'huaxing',
    huaxingOrder,
    huaxingItems,
    [
      createAudit(huaxingOrder, 1, '工程提交主管审核', huaxingOrder.eng_name, '待审核', '待审核', 'PP 配色啤办提交。'),
      createAudit(huaxingOrder, 2, '主管通过', huaxingOrder.supervisor, '待审核', '待经理审核', '主管确认。'),
      createAudit(huaxingOrder, 3, '经理通过', '王经理', '待经理审核', '待生产', '内部单进入啤机部。'),
      createAudit(huaxingOrder, 4, '开始处理', '啤机部', '待生产', '生产中', '啤机部开始回填生产数据。'),
    ],
    [
      {
        id: 'BP-56206-problem-001',
        factory_id: 'huaxing',
        order_type: 'injection',
        order_id: huaxingOrder.id,
        order_number: huaxingOrder.order_number,
        description: '弹匣明细缺实际用料，完成前需补录。',
        reported_by: '啤机部',
        status: '待处理',
        created_at: '2026-04-21 11:10',
        resolved_at: '',
      },
    ],
  ),
}

export function getMoldingSampleRecord(factoryId: FactoryContextId | string | undefined) {
  const resolvedFactoryId = factoryId && isMoldingSampleFactoryId(factoryId)
    ? factoryId
    : fallbackFactoryId

  return moldingSampleFactoryRecords[resolvedFactoryId]
}

export function getMoldingSampleModuleStats(factoryId: FactoryContextId | string | undefined) {
  const record = getMoldingSampleRecord(factoryId)
  const completionGate = buildCompletionGate(record.order, record.items)
  const externalLabel = isExternalMoldingSampleOrder(record.order) ? '外厂' : '内部'
  const blockedCount = completionGate.missing_item_ids.length

  return `${record.order.status} · ${externalLabel} · 明细 ${record.items.length}${blockedCount ? ` · 卡点 ${blockedCount}` : ''}`
}

export function getMoldingSampleProductionTaskStats(factoryId: FactoryContextId | string | undefined) {
  const record = getMoldingSampleRecord(factoryId)

  if (isExternalMoldingSampleOrder(record.order)) {
    return `${record.order.status} · 外厂路径 · 不进啤机`
  }

  const completionGate = buildCompletionGate(record.order, record.items)
  const notificationLabel = ['待审核', '待经理审核'].includes(record.order.status)
    ? '已通知'
    : record.order.status === '待生产'
      ? '待执行'
      : record.order.status

  return `${notificationLabel} · 明细 ${record.items.length}${completionGate.missing_item_ids.length ? ` · 待回填 ${completionGate.missing_item_ids.length}` : ''}`
}

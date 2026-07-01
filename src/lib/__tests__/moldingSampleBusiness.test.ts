import assert from 'node:assert/strict'
import {
  applyCostPreviewToItems,
  buildCompletionGate,
  buildMoldingSampleReportSummary,
  calculateMoldingSampleItemCosts,
  canEditMoldingSampleOrder,
  createDefaultMoldingSampleOrder,
  generateRequisitionNumber,
  getMoldingSampleStatusTransition,
  isExternalMoldingSampleOrder,
  isMoldingSampleLocked,
  normalizeMaterialName,
  resolveMaterialPrice,
} from '../moldingSampleBusiness.js'
import type { MoldingSampleItem, MoldingSampleOrder } from '../../types/moldingSample.js'

const baseOrder: MoldingSampleOrder = {
  id: 'BP-TEST',
  factory_id: 'huakang-a',
  order_number: '62437',
  doc_number: 'W-G026-00',
  product_name: '链条枪',
  client_name: 'BuzzBee',
  date: '2026-04-09',
  stage: 'T0',
  order_type: '啤办',
  workshop: 'A车间',
  send_to: '',
  supervisor: '李主管',
  eng_name: '肖科',
  reason: '见客样办，颜色要对办。',
  status: '待审核',
  reject_reason: '',
  completed_date: '',
  created_at: '2026-04-09 09:30',
  updated_at: '2026-04-09 09:30',
}

const baseItem: MoldingSampleItem = {
  id: 'BP-TEST-001',
  order_id: 'BP-TEST',
  sort_order: 1,
  mold_id: 'M-001',
  mold_name: '左右枪身',
  machine_type: '160T',
  material: 'HIPS 425',
  color: '深绿色',
  pigment_no: '71139',
  quantity: '1/1',
  shoot_qty: 30,
  gross_weight_g: 82,
  required_material_kg: 2.46,
  mold_return_time: '2026-04-10',
  completion_time: '2026-04-13',
  notes: '',
  receipt_no: '',
  collected_weight_kg: null,
  actual_weight_kg: null,
  actual_amount_hkd: null,
  injection_cost: null,
  injection_cost_hkd: null,
  exchange_rate_at_save: null,
}

const prices = [
  { material: 'HIPS425', unit_price: 5.5, notes: '经理价' },
  { material: 'ABS 740', unit_price: 8, notes: '经理价' },
  { material: 'ABS 750W', unit_price: 8.6, notes: '经理价' },
]

const defaultedOrder = createDefaultMoldingSampleOrder({
  id: 'BP-NEW',
  product_name: '新产品',
  client_name: '客户',
  date: '2026-07-01',
  workshop: 'A车间',
  supervisor: '李主管',
  eng_name: '工程师',
})

assert.equal(defaultedOrder.status, '待审核')
assert.equal(defaultedOrder.order_type, '啤办')

assert.equal(isMoldingSampleLocked({ ...baseOrder, status: '待审核' }), false)
assert.equal(isMoldingSampleLocked({ ...baseOrder, status: '已驳回' }), false)
assert.equal(isMoldingSampleLocked({ ...baseOrder, status: '待经理审核' }), true)
assert.equal(canEditMoldingSampleOrder({ ...baseOrder, status: '生产中' }, '工程部'), false)
assert.equal(canEditMoldingSampleOrder({ ...baseOrder, status: '生产中' }, '经理'), true)

assert.deepEqual(
  getMoldingSampleStatusTransition({
    order: baseOrder,
    action: '主管通过',
    actor_role: '主管',
    actor_name: '李主管',
  }),
  { allowed: true, next_status: '待经理审核', completed_date: '' },
)

assert.deepEqual(
  getMoldingSampleStatusTransition({
    order: { ...baseOrder, status: '待经理审核' },
    action: '经理通过',
    actor_role: '经理',
    actor_name: '经理',
  }),
  { allowed: true, next_status: '待生产', completed_date: '' },
)

const externalTransition = getMoldingSampleStatusTransition({
  order: { ...baseOrder, status: '待经理审核', send_to: '发至模厂' },
  action: '经理通过',
  actor_role: '经理',
  actor_name: '经理',
  today: '2026-07-01',
})
assert.deepEqual(externalTransition, {
  allowed: true,
  next_status: '已完成',
  completed_date: '2026-07-01',
})

const rejectedTransition = getMoldingSampleStatusTransition({
  order: baseOrder,
  action: '主管驳回',
  actor_role: '主管',
  actor_name: '李主管',
  reason: '资料不齐',
})
assert.deepEqual(rejectedTransition, {
  allowed: true,
  next_status: '已驳回',
  completed_date: '',
  reject_reason: '资料不齐',
})

assert.equal(isExternalMoldingSampleOrder({ ...baseOrder, send_to: '发至湖南' }), true)
assert.equal(isExternalMoldingSampleOrder({ ...baseOrder, workshop: '模厂' }), true)

const blockedGate = buildCompletionGate(baseOrder, [
  baseItem,
  { ...baseItem, id: 'BP-TEST-002', mold_id: 'M-002', actual_weight_kg: 1.2 },
])
assert.equal(blockedGate.can_complete, false)
assert.deepEqual(blockedGate.missing_item_ids, ['BP-TEST-001'])
assert.match(blockedGate.message, /BP-TEST-001/)

const passingGate = buildCompletionGate(baseOrder, [
  { ...baseItem, actual_weight_kg: 1.1 },
  { ...baseItem, id: 'BP-TEST-002', actual_weight_kg: 1.2 },
])
assert.equal(passingGate.can_complete, true)

assert.equal(normalizeMaterialName('PP(EP３３２K)-90度'), 'ppep332k90°')
assert.equal(resolveMaterialPrice('HIPS-425', prices)?.unit_price, 5.5)
assert.equal(resolveMaterialPrice('30% ABS抽粒 + 70% ABS 750W', prices)?.material, 'ABS 750W')
assert.equal(resolveMaterialPrice('70% 未知料 + 30% ABS 750W', prices), null)

const costedItem = calculateMoldingSampleItemCosts(
  { ...baseItem, actual_weight_kg: 2, injection_cost: 100 },
  prices,
  1.08,
  false,
)
assert.equal(costedItem.actual_amount_hkd, 24.25)
assert.equal(costedItem.injection_cost_hkd, 108)
assert.equal(costedItem.exchange_rate_at_save, 1.08)

const externalCostedItem = calculateMoldingSampleItemCosts(
  { ...baseItem, collected_weight_kg: 2.6, required_material_kg: 2.46, injection_cost: 100 },
  prices,
  1.08,
  true,
)
assert.equal(externalCostedItem.actual_weight_kg, 2.6)
assert.equal(externalCostedItem.actual_amount_hkd, 31.53)
assert.equal(externalCostedItem.injection_cost_hkd, null)

const previewItems = applyCostPreviewToItems(
  [
    { ...baseItem, actual_weight_kg: 2, actual_amount_hkd: null, injection_cost: 100 },
    { ...baseItem, id: 'BP-TEST-002', actual_weight_kg: 3, actual_amount_hkd: 88, injection_cost: 120 },
  ],
  prices,
  1.08,
  false,
)
assert.equal(previewItems[0].actual_amount_hkd, 24.25)
assert.equal(previewItems[1].actual_amount_hkd, 88)
assert.equal(previewItems[1].injection_cost_hkd, 129.6)

const internalSummary = buildMoldingSampleReportSummary(
  { ...baseOrder, status: '已完成', completed_date: '2026-07-01' },
  [
    { ...baseItem, actual_weight_kg: 2, actual_amount_hkd: 24.25, injection_cost: 100, injection_cost_hkd: 108 },
    { ...baseItem, id: 'BP-TEST-002', material: '未知料', actual_weight_kg: 1, actual_amount_hkd: null, injection_cost: null, injection_cost_hkd: null },
  ],
)
assert.equal(internalSummary.total_material_cost, 24.25)
assert.equal(internalSummary.total_injection_cost, 108)
assert.equal(internalSummary.total_cost, 132.25)
assert.equal(internalSummary.has_missing_price, true)
assert.equal(internalSummary.has_missing_injection_cost, true)
assert.deepEqual(internalSummary.missing_price_item_ids, ['BP-TEST-002'])

const externalSummary = buildMoldingSampleReportSummary(
  { ...baseOrder, send_to: '发至模厂', workshop: '模厂', status: '已完成', completed_date: '2026-07-01' },
  [
    { ...baseItem, actual_weight_kg: 2.6, actual_amount_hkd: 31.53, injection_cost: null, injection_cost_hkd: null },
  ],
)
assert.equal(externalSummary.total_material_cost, 31.53)
assert.equal(externalSummary.total_injection_cost, 0)
assert.equal(externalSummary.total_cost, 31.53)
assert.equal(externalSummary.has_missing_injection_cost, false)

assert.equal(
  generateRequisitionNumber('2026-07-01', [
    { req_number: 'LL-20260701-001' },
    { req_number: 'LL-20260701-002' },
    { req_number: 'LL-20260630-009' },
  ]),
  'LL-20260701-003',
)

import assert from 'node:assert/strict'
import {
  buildManualMoldingSampleCreateRequest,
  createManualMoldingSampleLineDraft,
  createManualMoldingSampleMaterialComponentDraft,
  createManualMoldingSampleOrderDraft,
} from '../moldingSampleManualCreate.js'

const draft = createManualMoldingSampleOrderDraft({
  factory_id: 'huakang-a',
  order_date: '2026-04-09',
  supervisor: '李主管',
  eng_name: '肖科',
})

Object.assign(draft, {
  id: 'BP-62437',
  product_no: '62437',
  doc_number: 'W-G026-00',
  client_name: 'BuzzBee',
  product_name: '链条枪',
  stage: 'T0',
  workshop: 'A车间',
  send_to: '内部',
  reason: '见客样办，枪身不可刮花，颜色要对办，工程订色粉。',
})

draft.items = [
  createManualMoldingSampleLineDraft({
    customer_mold_id: 'BBT62450-A-01',
    mold_name: '左右枪身A款',
    mold_dimensions: '650 × 450 × 380 mm', mold_presence_status: 'in_factory', mold_return_time: '2026-04-12',
    material: 'HIPS 425',
    color: '深绿色',
    pms: '2272C',
    pigment_no: '71139',
    quantity: '1/1',
    shoot_qty: '30',
    required_material_kg: '2.48',
    required_date: '2026-04-13',
  }),
  createManualMoldingSampleLineDraft({
    customer_mold_id: 'BBT62450-A-02',
    mold_name: 'A款装饰件',
    material: 'ABS 740',
    color: '暗蓝色',
    pms: 'PMS 2935C',
    pigment_no: '71120',
    quantity: '1/1',
    shoot_qty: '30',
    required_date: '2026-04-13',
    notes: '按客样办',
  }),
]

const result = buildManualMoldingSampleCreateRequest(draft, 'huakang-a')

assert.deepEqual(result.errors, [])
assert.equal(result.payload?.order.id, 'BP-62437')
assert.equal(result.payload?.order.factory_id, 'huakang-a')
assert.equal(result.payload?.order.production_factory_id, 'huakang-a')
assert.equal(result.payload?.order.production_assigned_at, '')
assert.equal(result.payload?.order.production_assigned_by, '')
assert.equal(result.payload?.order.production_assignment_version, 0)
assert.equal(result.payload?.order.order_number, '62437')
assert.equal(result.payload?.order.doc_number, 'W-G026-00')
assert.equal(result.payload?.order.client_name, 'BuzzBee')
assert.equal(result.payload?.order.product_name, '链条枪')
assert.equal(result.payload?.order.date, '2026-04-09')
assert.equal(result.payload?.order.stage, 'T0')
assert.equal(result.payload?.order.order_type, '啤办')
assert.equal(result.payload?.order.workshop, 'A车间')
assert.equal(result.payload?.order.send_to, '')
assert.equal(result.payload?.order.supervisor, '李主管')
assert.equal(result.payload?.order.eng_name, '肖科')
assert.equal(result.payload?.order.reason, '见客样办，枪身不可刮花，颜色要对办，工程订色粉。')
assert.equal(result.payload?.order.status, '待审核')
assert.equal(result.payload?.order.created_at, '')
assert.equal(result.payload?.order.updated_at, '')
assert.deepEqual(result.payload?.items[0]?.material_components, [
  { material: 'HIPS 425', source_type: 'virgin', ratio_percent: 100 },
])
assert.equal(result.payload?.items[0]?.material_usage_type, 'production')

assert.deepEqual(result.payload?.items.map((item) => ({
  id: item.id,
  order_id: item.order_id,
  sort_order: item.sort_order,
  mold_id: item.mold_id,
  mold_name: item.mold_name,
  mold_dimensions: item.mold_dimensions,
  mold_presence_status: item.mold_presence_status,
  machine_type: item.machine_type,
  material: item.material,
  color: item.color,
  pigment_no: item.pigment_no,
  quantity: item.quantity,
  shoot_qty: item.shoot_qty,
  gross_weight_g: item.gross_weight_g,
  required_material_kg: item.required_material_kg,
  mold_return_time: item.mold_return_time,
  completion_time: item.completion_time,
  notes: item.notes,
})), [
  {
    id: 'BP-62437-001',
    order_id: 'BP-62437',
    sort_order: 1,
    mold_id: 'BBT62450-A-01',
    mold_name: '左右枪身A款',
    mold_dimensions: '650 × 450 × 380 mm', mold_presence_status: 'in_factory', machine_type: '',
    material: 'HIPS 425',
    color: '深绿色 / PMS 2272C',
    pigment_no: '71139',
    quantity: '1/1',
    shoot_qty: 30,
    gross_weight_g: null,
    required_material_kg: 2.48,
    mold_return_time: '2026-04-12',
    completion_time: '2026-04-13',
    notes: '',
  },
  {
    id: 'BP-62437-002',
    order_id: 'BP-62437',
    sort_order: 2,
    mold_id: 'BBT62450-A-02',
    mold_name: 'A款装饰件',
    mold_dimensions: '', mold_presence_status: 'unknown', machine_type: '',
    material: 'ABS 740',
    color: '暗蓝色 / PMS 2935C',
    pigment_no: '71120',
    quantity: '1/1',
    shoot_qty: 30,
    gross_weight_g: null,
    required_material_kg: null,
    mold_return_time: '',
    completion_time: '2026-04-13',
    notes: '按客样办',
  },
])

const invalid = createManualMoldingSampleOrderDraft({
  factory_id: 'huakang-a',
  order_date: '2026-04-09',
  supervisor: '',
  eng_name: '',
})

const invalidResult = buildManualMoldingSampleCreateRequest(invalid, 'huakang-a')

assert.equal(invalidResult.payload, null)
assert.match(invalidResult.errors.join('；'), /产品编号/)
assert.match(invalidResult.errors.join('；'), /客户名称/)
assert.match(invalidResult.errors.join('；'), /主管/)
assert.match(invalidResult.errors.join('；'), /至少填写一条明细/)
assert.doesNotMatch(invalidResult.errors.join('；'), /文件编号/)

const mixedDraft = createManualMoldingSampleOrderDraft({
  product_no: 'MIX-001',
  client_name: '测试客户',
  product_name: '混料测试',
  order_date: '2026-07-15',
  supervisor: '主管',
  eng_name: '工程师',
  items: [createManualMoldingSampleLineDraft({
    customer_mold_id: 'MIX-MOLD-01',
    mold_name: '混料模具',
    material: '',
    material_components: [
      createManualMoldingSampleMaterialComponentDraft({ material: 'ABS', source_type: 'virgin', ratio_percent: '80' }),
      createManualMoldingSampleMaterialComponentDraft({ material: 'PVC', source_type: 'runner', ratio_percent: '20' }),
    ],
    material_usage_type: 'trial',
    color: '本色',
    quantity: '1',
    shoot_qty: '10',
    required_material_kg: '10',
    required_date: '2026-07-16',
  })],
})
const mixedResult = buildManualMoldingSampleCreateRequest(mixedDraft)
assert.deepEqual(mixedResult.errors, [])
assert.equal(mixedResult.payload?.items[0]?.material, '80%ABS + 20%PVC水口料')
assert.deepEqual(mixedResult.payload?.items[0]?.material_components, [
  { material: 'ABS', source_type: 'virgin', ratio_percent: 80 },
  { material: 'PVC', source_type: 'runner', ratio_percent: 20 },
])
assert.equal(mixedResult.payload?.items[0]?.material_usage_type, 'trial')

mixedDraft.items[0]!.material_components[1]!.ratio_percent = '10'
const invalidRatioResult = buildManualMoldingSampleCreateRequest(mixedDraft)
assert.equal(invalidRatioResult.payload, null)
assert.match(invalidRatioResult.errors.join('；'), /原料比例合计必须等于 100%/)

const huakangCDefault = createManualMoldingSampleOrderDraft({ factory_id: 'huakang-c' })
const huakangDDefault = createManualMoldingSampleOrderDraft({ factory_id: 'huakang-d' })
assert.equal(huakangCDefault.production_factory_id, 'huakang-a')
assert.equal(huakangDDefault.production_factory_id, 'huakang-b')
assert.equal(createManualMoldingSampleOrderDraft({
  factory_id: 'huakang-c',
  production_factory_id: 'huakang-b',
}).production_factory_id, 'huakang-b')
assert.equal(createManualMoldingSampleOrderDraft({
  factory_id: 'huaxing',
  production_factory_id: 'huakang-a',
}).production_factory_id, 'huaxing')
assert.equal(createManualMoldingSampleOrderDraft({
  factory_id: 'huakang-c',
  production_factory_id: 'huakang-a',
  send_to: '发至湖南',
}).production_factory_id, null)

const validHuakangCDraft = {
  ...draft,
  factory_id: 'huakang-c',
  production_factory_id: 'huakang-b',
}
const validHuakangCResult = buildManualMoldingSampleCreateRequest(validHuakangCDraft)
assert.deepEqual(validHuakangCResult.errors, [])
assert.equal(validHuakangCResult.payload?.order.factory_id, 'huakang-c')
assert.equal(validHuakangCResult.payload?.order.production_factory_id, 'huakang-b')

const missingHuakangCTargetResult = buildManualMoldingSampleCreateRequest({
  ...validHuakangCDraft,
  production_factory_id: null,
})
assert.equal(missingHuakangCTargetResult.payload, null)
assert.match(missingHuakangCTargetResult.errors.join('；'), /必须选择华康A或华康B/)

const invalidHuakangCTargetResult = buildManualMoldingSampleCreateRequest({
  ...validHuakangCDraft,
  production_factory_id: 'huaxing',
})
assert.equal(invalidHuakangCTargetResult.payload, null)
assert.match(invalidHuakangCTargetResult.errors.join('；'), /只能由华康A、华康B承接生产/)

const invalidSelfFactoryTargetResult = buildManualMoldingSampleCreateRequest({
  ...draft,
  production_factory_id: 'huakang-b',
})
assert.equal(invalidSelfFactoryTargetResult.payload, null)
assert.match(invalidSelfFactoryTargetResult.errors.join('；'), /只能由华康A承接生产/)

const externalHuakangCResult = buildManualMoldingSampleCreateRequest({
  ...validHuakangCDraft,
  production_factory_id: null,
  send_to: '发至湖南',
})
assert.deepEqual(externalHuakangCResult.errors, [])
assert.equal(externalHuakangCResult.payload?.order.production_factory_id, null)

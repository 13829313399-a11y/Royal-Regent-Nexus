import assert from 'node:assert/strict'
import {
  buildManualMoldingSampleCreateRequest,
  createManualMoldingSampleLineDraft,
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
    material: 'HIPS 425',
    color: '深绿色',
    pms: '2272C',
    pigment_no: '71139',
    quantity: '1/1',
    shoot_qty: '30',
    gross_weight_g: '82.5',
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
assert.equal(result.payload?.order.created_at, '2026-04-09 09:00')

const noFileNumberDraft = createManualMoldingSampleOrderDraft({
  ...draft,
  doc_number: '',
})
const noFileNumberResult = buildManualMoldingSampleCreateRequest(noFileNumberDraft, 'huakang-a')

assert.deepEqual(noFileNumberResult.errors, [])
assert.equal(noFileNumberResult.payload?.order.doc_number, '')

assert.deepEqual(result.payload?.items.map((item) => ({
  id: item.id,
  order_id: item.order_id,
  sort_order: item.sort_order,
  mold_id: item.mold_id,
  mold_name: item.mold_name,
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
    machine_type: '待工程确认',
    material: 'HIPS 425',
    color: '深绿色 / PMS 2272C',
    pigment_no: '71139',
    quantity: '1/1',
    shoot_qty: 30,
    gross_weight_g: 82.5,
    required_material_kg: 2.48,
    mold_return_time: '2026-04-13',
    completion_time: '2026-04-13',
    notes: '',
  },
  {
    id: 'BP-62437-002',
    order_id: 'BP-62437',
    sort_order: 2,
    mold_id: 'BBT62450-A-02',
    mold_name: 'A款装饰件',
    machine_type: '待工程确认',
    material: 'ABS 740',
    color: '暗蓝色 / PMS 2935C',
    pigment_no: '71120',
    quantity: '1/1',
    shoot_qty: 30,
    gross_weight_g: null,
    required_material_kg: null,
    mold_return_time: '2026-04-13',
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
assert.match(invalidResult.errors.join('；'), /单据编号/)
assert.match(invalidResult.errors.join('；'), /产品编号/)
assert.match(invalidResult.errors.join('；'), /客户名称/)
assert.match(invalidResult.errors.join('；'), /主管/)
assert.match(invalidResult.errors.join('；'), /至少填写一条明细/)
assert.doesNotMatch(invalidResult.errors.join('；'), /文件编号/)

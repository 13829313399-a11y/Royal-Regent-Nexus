import assert from 'node:assert/strict'
import { createMoldingSampleApi, resolveMoldingSampleAccess } from '../moldingSample.js'

assert.deepEqual(resolveMoldingSampleAccess({
  read_source: 'cross',
  can_view_cost: false,
}), {
  read_source: 'cross',
  can_view_cost: false,
  read_only: true,
})

assert.deepEqual(resolveMoldingSampleAccess({
  read_source: 'cross_operate',
  can_view_cost: false,
}), {
  read_source: 'cross_operate',
  can_view_cost: false,
  read_only: false,
})

const calls: Array<{ method: string, url: string, data?: unknown, config?: unknown }> = []

const client = {
  async get(url: string, config?: unknown) {
    calls.push({ method: 'get', url, config })
    return { data: { url } }
  },
  async post(url: string, data?: unknown, config?: unknown) {
    calls.push({ method: 'post', url, data, config })
    return { data: { url, data } }
  },
  async patch(url: string, data?: unknown) {
    calls.push({ method: 'patch', url, data })
    return { data: { url, data } }
  },
  async put(url: string, data?: unknown) {
    calls.push({ method: 'put', url, data })
    return { data: { url, data } }
  },
  async delete(url: string) {
    calls.push({ method: 'delete', url })
    return { data: { url } }
  },
}

const api = createMoldingSampleApi(client as Parameters<typeof createMoldingSampleApi>[0])

assert.deepEqual(await api.listOrders(), { url: '/injection' })
assert.deepEqual(await api.listOrders('huadeng'), { url: '/injection?factory_id=huadeng' })
assert.deepEqual(await api.getBoardSummary('huaxing', ' 头盔 客户 '), {
  url: '/injection/board/summary?factory_id=huaxing&q=%E5%A4%B4%E7%9B%94+%E5%AE%A2%E6%88%B7',
})
assert.deepEqual(await api.getBoardSummary('huadeng', '   '), {
  url: '/injection/board/summary?factory_id=huadeng',
})
assert.deepEqual(await api.listBoardPage({
  factoryId: 'huaxing',
  status: '待审核',
  query: ' 黑色 模具 ',
  page: 2,
  pageSize: 5,
}), {
  url: '/injection/board/page?factory_id=huaxing&status=%E5%BE%85%E5%AE%A1%E6%A0%B8&q=%E9%BB%91%E8%89%B2+%E6%A8%A1%E5%85%B7&page=2&page_size=5',
})
assert.deepEqual(await api.listBoardPage({
  factoryId: 'huadeng',
  status: '已完成',
  query: '\t',
  page: 1,
  pageSize: 5,
}), {
  url: '/injection/board/page?factory_id=huadeng&status=%E5%B7%B2%E5%AE%8C%E6%88%90&page=1&page_size=5',
})
assert.deepEqual(await api.getOrder('BP-1'), { url: '/injection/BP-1' })

await api.createOrder({
  order: {
    id: 'BP-1',
    product_name: '链条枪',
    client_name: 'BuzzBee',
    date: '2026-07-01',
    workshop: 'A车间',
    supervisor: '李主管',
    eng_name: '肖科',
  },
  items: [],
})

await api.updateStatus('BP-1', {
  action: '主管通过',
})

await api.editOrder('BP-1', {
  order: {
    id: 'BP-1',
    product_name: '链条枪改',
    client_name: 'BuzzBee',
    date: '2026-07-01',
    workshop: 'A车间',
    supervisor: '李主管',
    eng_name: '肖科',
  },
  items: [{ id: 'BP-1-001', mold_name: '左右枪身' }],
})

await api.deleteOrder('BP-1')

const importBuffer = new ArrayBuffer(4)
await api.exportOrderExcel('BP-1')
await api.exportOrdersExcel(['BP-1', 'BP-2'])
await api.downloadEngineeringImportTemplate('huadeng')
await api.importOrderExcel(importBuffer, { order_id: 'BP-2', factory_id: 'huadeng' })
await api.previewOrderExcel(importBuffer, { factory_id: 'huadeng' })

await api.listSensitiveAuditLogs()

await api.listNotifications({
  target_module: 'production_molding_sample_task',
  factory_id: 'huakang-a',
  status: '未读',
})

await api.updateNotification('N-BP-1', {
  status: '已读',
})

await api.listProblems({
  order_id: 'BP-1',
  status: '待处理',
})

await api.createProblem({
  order_id: 'BP-1',
  description: '左枪身缩水，需工程确认胶口。',
})

await api.updateProblemStatus('P-BP-1', {
  status: '已解决',
})

await api.updateItems('BP-1', {
  items: [
    {
      id: 'BP-1-001',
      actual_weight_kg: 2,
      injection_cost: 100,
    },
  ],
})

await api.upsertTrialReport('BP-1', 'BP-1-001', {
  data: {
    mold_supplier: '华兴模具厂',
    sample_category: '',
    material_name: 'HIPS 425',
    material_shots: '30',
    material_weight: '',
    color: '深绿色',
    color_code: '71139',
    color_shots: '',
    color_weight: '',
    virgin_material_shots: '',
    virgin_material_weight: '',
    runner_material_shots: '',
    runner_material_weight: '',
    water_ratio: '',
    water_shots: '',
    water_material_weight: '',
    water_weight: '',
    special_requirements: '',
    front_mold_water: '冻水',
    rear_mold_water: '热水',
    other_trial_requirement: '',
    other_trial_requirement_note: '',
    baking_time_hours: '',
    mold_condition: '已在本厂',
    expected_return_time: '',
    gross_weight: '',
    net_weight: '',
    plastic_model: '160T',
    machine_model: '海天',
    machine_no: 'A-08',
    cooling_time: '',
    holding_time: '',
    cycle_time: '',
    injection_speed: '',
    ejector_count: '',
    cushion_pressure: '',
    clamping_force: '',
    high_pressure: '',
    low_pressure: '',
    pressure_stage_1: '',
    pressure_stage_2: '',
    pressure_stage_3: '',
    pressure_stage_4: '',
    barrel_temperature_head: '',
    barrel_temperature_middle: '',
    barrel_temperature_end: '',
    molding_mode: '全自动',
    mold_issues: ['困气'],
    part_issues: [],
    issue_notes: '',
    trial_summary: '首件正常。',
    trial_round: '1',
    verdict: '合格试模',
    tester_name: '啤机部文员',
    tester_date: '2026-07-14',
    molding_supervisor_name: '',
    molding_supervisor_date: '',
    engineer_name: '',
    engineer_date: '',
  },
})

await api.getMaterialPrices('huadeng')

await api.updateMaterialPrices({
  prices: [{ material: 'HIPS 425', unit_price: 6, notes: '新经理价' }],
  rmb_to_hkd_rate: 1.1,
})

await api.listRequisitions('BP-1')
await api.listInventoryBatches('HIPS 425')
await api.listInventoryMovements({ batch_id: 'BATCH-1', material: 'HIPS 425' })

await api.createInventoryBatch({
  material: 'HIPS 425',
  batch_no: 'HIPS-20260701-A',
  location: 'A-01',
  initial_weight_kg: 3,
})

await api.createRequisition({
  date: '2026-07-01',
  order_id: 'BP-1',
  material: 'HIPS 425',
  requested_weight_kg: 2.46,
  notes: '左右枪身试啤领料',
})

await api.updateRequisitionStatus('REQ-1', {
  status: '已出库',
  issued_at: '2026-07-01 15:30',
  inventory_batch_id: 'BATCH-1',
})

await api.deleteRequisition('REQ-1')

assert.deepEqual(calls.map((call) => `${call.method} ${call.url}`), [
  'get /injection',
  'get /injection?factory_id=huadeng',
  'get /injection/board/summary?factory_id=huaxing&q=%E5%A4%B4%E7%9B%94+%E5%AE%A2%E6%88%B7',
  'get /injection/board/summary?factory_id=huadeng',
  'get /injection/board/page?factory_id=huaxing&status=%E5%BE%85%E5%AE%A1%E6%A0%B8&q=%E9%BB%91%E8%89%B2+%E6%A8%A1%E5%85%B7&page=2&page_size=5',
  'get /injection/board/page?factory_id=huadeng&status=%E5%B7%B2%E5%AE%8C%E6%88%90&page=1&page_size=5',
  'get /injection/BP-1',
  'post /injection',
  'patch /injection/BP-1/status',
  'put /injection/BP-1',
  'delete /injection/BP-1',
  'get /injection/BP-1/export-excel',
  'get /injection/export-excel?order_ids=BP-1&order_ids=BP-2',
  'get /injection/import-excel-template?factory_id=huadeng',
  'post /injection/import-excel?order_id=BP-2&factory_id=huadeng',
  'post /injection/import-excel-preview?factory_id=huadeng',
  'get /sensitive-audit-logs',
  'get /molding-sample-notifications?target_module=production_molding_sample_task&factory_id=huakang-a&status=%E6%9C%AA%E8%AF%BB',
  'patch /molding-sample-notifications/N-BP-1',
  'get /problems?order_id=BP-1&status=%E5%BE%85%E5%A4%84%E7%90%86',
  'post /problems',
  'patch /problems/P-BP-1',
  'patch /injection/BP-1/items',
  'put /injection/BP-1/trial-reports/BP-1-001',
  'get /material-prices?factory_id=huadeng',
  'post /manager-update-prices',
  'get /requisitions?order_id=BP-1',
  'get /inventory-batches?material=HIPS+425',
  'get /inventory-movements?batch_id=BATCH-1&material=HIPS+425',
  'post /inventory-batches',
  'post /requisitions',
  'patch /requisitions/REQ-1/status',
  'delete /requisitions/REQ-1',
])

const allPayloadText = JSON.stringify(calls.map((call) => call.data))
for (const sensitiveKey of ['pin', 'reviewer_name', 'reviewer_role', 'actor_name', 'actor_role']) {
  assert.equal(new RegExp(`"${sensitiveKey}"\\s*:`).test(allPayloadText), false)
}

assert.deepEqual(calls.find((call) => call.url === '/injection/BP-1/status')?.data, {
  action: '主管通过',
})
assert.deepEqual(calls.find((call) => call.method === 'put' && call.url === '/injection/BP-1')?.data, {
  order: {
    id: 'BP-1',
    product_name: '链条枪改',
    client_name: 'BuzzBee',
    date: '2026-07-01',
    workshop: 'A车间',
    supervisor: '李主管',
    eng_name: '肖科',
  },
  items: [{ id: 'BP-1-001', mold_name: '左右枪身' }],
})
assert.equal(calls.find((call) => call.url === '/injection/import-excel?order_id=BP-2&factory_id=huadeng')?.data, importBuffer)
assert.equal(calls.find((call) => call.url === '/injection/import-excel-preview?factory_id=huadeng')?.data, importBuffer)
assert.deepEqual(calls.find((call) => call.url === '/manager-update-prices')?.data, {
  prices: [{ material: 'HIPS 425', unit_price: 6, notes: '新经理价' }],
  rmb_to_hkd_rate: 1.1,
})
assert.deepEqual(calls.find((call) => call.url === '/molding-sample-notifications/N-BP-1')?.data, {
  status: '已读',
})
assert.deepEqual(calls.find((call) => call.url === '/problems')?.data, {
  order_id: 'BP-1',
  description: '左枪身缩水，需工程确认胶口。',
})
assert.deepEqual(calls.find((call) => call.url === '/problems/P-BP-1')?.data, {
  status: '已解决',
})
assert.equal(calls.find((call) => call.url === '/injection/BP-1/trial-reports/BP-1-001')?.data instanceof Object, true)

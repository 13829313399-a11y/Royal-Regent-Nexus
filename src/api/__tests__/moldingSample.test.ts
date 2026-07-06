import assert from 'node:assert/strict'
import { createMoldingSampleApi } from '../moldingSample.js'

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
await api.importOrderExcel(importBuffer, { order_id: 'BP-2', factory_id: 'huadeng' })

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
  'get /injection/BP-1',
  'post /injection',
  'patch /injection/BP-1/status',
  'put /injection/BP-1',
  'delete /injection/BP-1',
  'get /injection/BP-1/export-excel',
  'post /injection/import-excel?order_id=BP-2&factory_id=huadeng',
  'get /sensitive-audit-logs',
  'get /molding-sample-notifications?target_module=production_molding_sample_task&factory_id=huakang-a&status=%E6%9C%AA%E8%AF%BB',
  'patch /molding-sample-notifications/N-BP-1',
  'get /problems?order_id=BP-1&status=%E5%BE%85%E5%A4%84%E7%90%86',
  'post /problems',
  'patch /problems/P-BP-1',
  'patch /injection/BP-1/items',
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
assert.equal(allPayloadText.includes('pin'), false)
assert.equal(allPayloadText.includes('reviewer_name'), false)
assert.equal(allPayloadText.includes('reviewer_role'), false)
assert.equal(allPayloadText.includes('actor_name'), false)
assert.equal(allPayloadText.includes('actor_role'), false)

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

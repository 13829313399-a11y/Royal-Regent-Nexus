import assert from 'node:assert/strict'
import { createMoldingSampleApi } from '../moldingSample.js'

const calls: Array<{ method: string, url: string, data?: unknown }> = []

const client = {
  async get(url: string) {
    calls.push({ method: 'get', url })
    return { data: { url } }
  },
  async post(url: string, data?: unknown) {
    calls.push({ method: 'post', url, data })
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
assert.deepEqual(await api.getRoles(), { url: '/roles' })

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
  reviewer_name: '李主管',
  reviewer_role: '主管',
  pin: '1234',
})

await api.editOrder('BP-1', {
  actor_name: '肖科',
  actor_role: '工程部',
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

await api.deleteOrder('BP-1', {
  actor_name: '肖科',
  actor_role: '工程部',
})

await api.verifyPin({
  name: '王经理',
  role: '经理',
  pin: '1234',
})

await api.changePin({
  name: '王经理',
  role: '经理',
  old_pin: '1234',
  new_pin: '6789',
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
  manager_name: '王经理',
  manager_pin: '6789',
})

assert.deepEqual(calls.map((call) => `${call.method} ${call.url}`), [
  'get /injection',
  'get /injection/BP-1',
  'get /roles',
  'post /injection',
  'patch /injection/BP-1/status',
  'put /injection/BP-1',
  'delete /injection/BP-1?actor_name=%E8%82%96%E7%A7%91&actor_role=%E5%B7%A5%E7%A8%8B%E9%83%A8',
  'post /verify-pin',
  'post /change-pin',
  'patch /injection/BP-1/items',
  'post /manager-update-prices',
])

assert.deepEqual(calls.find((call) => call.url === '/injection/BP-1/status')?.data, {
  action: '主管通过',
  reviewer_name: '李主管',
  reviewer_role: '主管',
  pin: '1234',
})
assert.deepEqual(calls.find((call) => call.method === 'put' && call.url === '/injection/BP-1')?.data, {
  actor_name: '肖科',
  actor_role: '工程部',
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
assert.deepEqual(calls.find((call) => call.url === '/manager-update-prices')?.data, {
  prices: [{ material: 'HIPS 425', unit_price: 6, notes: '新经理价' }],
  rmb_to_hkd_rate: 1.1,
  manager_name: '王经理',
  manager_pin: '6789',
})

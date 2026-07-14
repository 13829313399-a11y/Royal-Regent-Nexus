import assert from 'node:assert/strict'
import { createRawMaterialApi } from '../rawMaterial.js'

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
}

const api = createRawMaterialApi(client)

assert.deepEqual(await api.list('huaxing'), {
  url: '/raw-materials?factory_id=huaxing',
})

await api.create({
  factory_id: 'huaxing',
  material_code: 'RM-NEW-001',
  material_name: '工程新增 PP',
  category: 'PP',
  unit: 'KG',
  safety_stock_kg: 50,
})

await api.update('RM-ENG-001', {
  material_name: '工程更新 PP 料',
  category: 'PP',
  unit: 'KG',
  unit_price_hkd_per_lb: 6.25,
  safety_stock_kg: 60,
})

assert.deepEqual(calls.map((call) => `${call.method} ${call.url}`), [
  'get /raw-materials?factory_id=huaxing',
  'post /raw-materials',
  'patch /raw-materials/RM-ENG-001',
])
assert.deepEqual(calls[1].data, {
  factory_id: 'huaxing',
  material_code: 'RM-NEW-001',
  material_name: '工程新增 PP',
  category: 'PP',
  unit: 'KG',
  safety_stock_kg: 50,
})
assert.deepEqual(calls[2].data, {
  material_name: '工程更新 PP 料',
  category: 'PP',
  unit: 'KG',
  unit_price_hkd_per_lb: 6.25,
  safety_stock_kg: 60,
})

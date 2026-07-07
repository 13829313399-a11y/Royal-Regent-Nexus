import { describe, expect, it } from 'vitest'
import {
  calculateExpectedMaterialAmountHkd,
  resolveMaterialPrice,
} from '../moldingSampleBusiness'
import type { MoldingSampleItem } from '@/types/moldingSample'

const baseItem: MoldingSampleItem = {
  id: 'ITEM-001',
  order_id: 'BP-EXPECTED-001',
  sort_order: 1,
  mold_id: 'MOLD-001',
  mold_name: '测试模具',
  machine_type: '160T',
  production_machine: '',
  material: 'PP（AV161）',
  color: '黑色',
  pigment_no: 'PMS 黑色',
  quantity: '2',
  shoot_qty: 30,
  gross_weight_g: 11,
  required_material_kg: 15,
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
}

const rawMaterialPrices = [
  { material: '1#PP AV161', unit_price: 4.6, notes: '原料资料' },
]

describe('molding sample expected material cost', () => {
  it('matches PP material aliases and calculates expected HKD material cost from kg and HKD/lb price', () => {
    expect(resolveMaterialPrice('PP（AV161）', rawMaterialPrices)?.unit_price).toBe(4.6)
    expect(calculateExpectedMaterialAmountHkd(baseItem, rawMaterialPrices)).toBe(152.12)
  })
})

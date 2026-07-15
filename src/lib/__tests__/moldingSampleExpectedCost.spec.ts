import { describe, expect, it } from 'vitest'
import {
  calculateMaterialCostBreakdown,
  calculateExpectedMaterialAmountHkd,
  normalizeMaterialComponents,
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

  const mixturePrices = [
    { material: 'ABS', unit_price: 8 },
    { material: 'PVC', unit_price: 5 },
  ]

  it('charges same-grade runner material at the ABS price for the full 10kg', () => {
    const components = normalizeMaterialComponents('80%ABS+20%水口料')
    expect(components).toEqual([
      { material: 'ABS', source_type: 'virgin', ratio_percent: 80 },
      { material: 'ABS', source_type: 'runner', ratio_percent: 20 },
    ])
    expect(calculateMaterialCostBreakdown({ components, totalWeightKg: 10, prices: mixturePrices })).toMatchObject({
      components: [
        { material: 'ABS', source_type: 'virgin', weight_kg: 8, unit_price: 8, amount_hkd: 141.1 },
        { material: 'ABS', source_type: 'runner', weight_kg: 2, unit_price: 8, amount_hkd: 35.27 },
      ],
      total_amount_hkd: 176.37,
      weighted_unit_price: 8,
    })
  })

  it('charges ABS and PVC runner components at their own prices', () => {
    const components = normalizeMaterialComponents('80%ABS+20%PVC水口料')
    const breakdown = calculateMaterialCostBreakdown({ components, totalWeightKg: 10, prices: mixturePrices })

    expect(breakdown.components).toEqual([
      { material: 'ABS', source_type: 'virgin', ratio_percent: 80, weight_kg: 8, unit_price: 8, amount_hkd: 141.1 },
      { material: 'PVC', source_type: 'runner', ratio_percent: 20, weight_kg: 2, unit_price: 5, amount_hkd: 22.05 },
    ])
    expect(breakdown.total_amount_hkd).toBe(163.15)
    expect(resolveMaterialPrice('80%ABS+20%PVC水口料', mixturePrices)?.unit_price).toBe(7.4)
  })

  it('returns null when any component price is missing', () => {
    const components = normalizeMaterialComponents('80%ABS+20%PVC')
    expect(calculateMaterialCostBreakdown({
      components,
      totalWeightKg: 10,
      prices: [{ material: 'ABS', unit_price: 8 }],
    }).total_amount_hkd).toBeNull()
    expect(resolveMaterialPrice('80%ABS+20%PVC', [{ material: 'ABS', unit_price: 8 }])).toBeNull()
  })

  it('strictly accepts only complete legacy compositions totaling 100 percent', () => {
    expect(normalizeMaterialComponents('100%ABS')).toEqual([
      { material: 'ABS', source_type: 'virgin', ratio_percent: 100 },
    ])
    expect(resolveMaterialPrice('100%ABS', mixturePrices)?.unit_price).toBe(8)

    for (const invalidComposition of [
      '80%ABS+PVC',
      '80%ABS+30%PVC',
      '0%ABS+100%PVC',
      '80%ABS+20%PVC+',
    ]) {
      expect(normalizeMaterialComponents(invalidComposition)).toEqual([])
      expect(resolveMaterialPrice(invalidComposition, mixturePrices)).toBeNull()
    }
  })

  it('still calculates material fees for trial usage', () => {
    expect(calculateExpectedMaterialAmountHkd({
      ...baseItem,
      material: '80%ABS+20%PVC水口料',
      material_components: normalizeMaterialComponents('80%ABS+20%PVC水口料'),
      material_usage_type: 'trial',
      required_material_kg: 10,
    }, mixturePrices)).toBe(163.15)
  })
})

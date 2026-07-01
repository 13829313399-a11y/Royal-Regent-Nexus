import type { MoldingSampleMaterialPrice } from '@/lib/moldingSampleBusiness'

export const moldingSampleRmbToHkdRate = 1.08

export const moldingSampleMaterialPrices: MoldingSampleMaterialPrice[] = [
  { material: 'HIPS 425', unit_price: 5.5, notes: '经理默认价' },
  { material: 'ABS 740', unit_price: 8, notes: '经理默认价' },
  { material: 'PP AV161', unit_price: 4.3, notes: '经理默认价' },
  { material: 'ABS 757', unit_price: 8.2, notes: '经理默认价' },
  { material: 'PC 110', unit_price: 9.6, notes: '经理默认价' },
  { material: 'POM 900P', unit_price: 10.5, notes: '经理默认价' },
  { material: 'ABS 747', unit_price: 8.1, notes: '经理默认价' },
  { material: 'POM 100P', unit_price: 10.3, notes: '经理默认价' },
  { material: 'PP K8003', unit_price: 4.8, notes: '经理默认价' },
  { material: 'ABS 750W', unit_price: 8.6, notes: '混合料匹配示例' },
]

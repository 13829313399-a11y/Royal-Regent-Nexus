// The customer supplies ABS/TPR/PP/POM/C-ABS rates. PVC/TPE are corroborated by
// the source resin costs and quote multiplier (rounded to HKD/kg, two decimals).
// Rates belong to the customer, not a SKU or an individual hand-filled example.
export const YINHUI_MATERIAL_PRICES_HKD_KG = { ABS: 15.65, TPR: 18.8, PP: 12.6, POM: 34.07, 'C-ABS': 24, PVC: 17.16, TPE: 15.9 } as const
// Customer-supplied layout families, never saved quotation amounts or MOQ values.
export const YINHUI_PROFILES = {
  standard: { label: '机器人 / 标准六表', file: 'yinhui-customer-quote-template.bin', product: '', packaging: 'Window Box' },
  '81283': { label: '81283 活动环', file: 'yinhui-81283-template.bin', product: 'ACTIVE RING', packaging: 'Closed Box' },
  '88636': { label: '88636 Rescue Bear', file: 'yinhui-88636-template.bin', product: 'Rescue Polar Bear', packaging: 'Color Box (S)' },
  '89115': { label: '89115 Pee Pee Puppy', file: 'yinhui-89115-template.bin', product: 'Pee Pee Puppy', packaging: 'Closed Box' },
  '89275': { label: '89275 Kneading Kitten', file: 'yinhui-89275-template.bin', product: 'Kneading Kitten', packaging: 'Open tray box' },
  '89127': { label: '89127 MUSCLE CLASH 开窗盒', file: 'yinhui-89127-template.bin', product: 'MUSCLE CLASH', packaging: 'Window Box' },
} as const
export type YinhuiProfileId = keyof typeof YINHUI_PROFILES
export function yinhuiProfileForModel(model: string): YinhuiProfileId {
  return Object.hasOwn(YINHUI_PROFILES, model) ? model as YinhuiProfileId : 'standard'
}
export function yinhuiTemplateUrl(profile: YinhuiProfileId = 'standard') { return `/templates/${YINHUI_PROFILES[profile].file}` }

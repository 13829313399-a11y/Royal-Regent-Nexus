import type { Data } from '@/api/indonesiaMaterials'
import { clone, materialDefaults, materialFields } from './forms'

export const importFields = [
  { key: 'item_no', label: '成品货号' }, ...materialFields,
  { key: 'image_data', label: '物料图片列' },
  { key: 'piece_usage', label: '单件用量（非送货数量）' },
]
export function sourceUsages(group: Data, productId: string): string[] {
  return [...new Set<string>(group.sources.filter((row: Data) => row.product_ids?.includes(productId) && row.source.piece_usage)
    .map((row: Data) => String(row.source.piece_usage)))]
}
export function incomingMaterial(group: Data, sourceIndex: number): Data {
  const result = { ...clone(materialDefaults), ...clone(group.existing?.data || {}) }
  // New unknown units/currency must be confirmed, not inferred from historical shipment quantities.
  if (!group.existing) Object.assign(result, { customs_unit: '', unit: '', currency: '' })
  const source = group.sources.find((row: Data) => row.index === sourceIndex)?.source || {}
  for (const field of materialFields) {
    const value = source[field.key]
    if (value !== undefined && value !== '') result[field.key] = field.key === 'procurement_days' ? Number(value) : value
  }
  if (source.image_data) result.image_data = source.image_data
  if (group.existing?.data.code) result.code = group.existing.data.code
  result.billing_mode = 'automatic'
  return result
}
export function importChoices(groups: Data[]): Data[] {
  return groups.map(group => {
    const sourceIndex = group.sources.length === 1 ? group.sources[0].index : -1
    return { group: group.index, selected: !group.blocked, source_index: sourceIndex,
      decision: group.existing ? '' : 'import', material: incomingMaterial(group, sourceIndex),
      recipes: group.products.map((product: Data) => {
        const usages = sourceUsages(group, product.id)
        return { product_id: product.id, decision: product.existing_usage ? 'keep' : 'import',
          usage: product.existing_usage || (usages.length === 1 ? usages[0] : '') }
      }) }
  })
}
export function importPayload(choices: Data[]) {
  return { choices: choices.filter(choice => choice.selected).map(choice => ({ group: choice.group,
    source_index: choice.source_index, decision: choice.decision,
    material: choice.decision === 'import' ? Object.fromEntries(Object.keys(materialDefaults).map(key => [key, choice.material[key]])) : null,
    recipes: choice.recipes.map((r: Data) => ({ product_id: r.product_id, decision: r.decision, usage: r.decision === 'keep' ? null : r.usage })) })) }
}

import type { Data } from '@/api/indonesiaMaterials'
import { clone, materialDefaults, materialFields } from './forms'

export const masterParserRevision = 'shipment-layout-images-v3'

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
  const present = (key: string) => source[key] !== undefined && source[key] !== ''
  const changedUnit = present('customs_unit') && group.existing && String(source.customs_unit).toUpperCase() !== String(group.existing.data.customs_unit).toUpperCase()
  // A source price must not inherit an unrelated old currency or pricing unit.
  if (present('price')) {
    result.currency = source.currency || ''; result.customs_unit = source.customs_unit || ''
  } else if (!group.existing || present('currency') || changedUnit) {
    result.price = ''; result.currency = source.currency || ''
  }
  if (source.image_data) result.image_data = source.image_data
  if (group.existing?.data.code) result.code = group.existing.data.code
  result.billing_mode = 'automatic'
  return result
}
export function restoreImportEdits(previousGroups: Data[], previousChoices: Data[], nextGroups: Data[]): Data[] {
  const next = importChoices(nextGroups)
  const sourceKey = (row: Data) => JSON.stringify([row.source_sheet, row.source_row, row.source.name, row.source.specification || ''])
  nextGroups.forEach((group, index) => {
    const old = previousGroups.find(item => item.sources.some((row: Data) => group.sources.some((fresh: Data) => sourceKey(row) === sourceKey(fresh))))
    const entered = old && previousChoices.find(item => item.group === old.index)
    if (!old || !entered) return
    const target = next[index]!
    target.selected = !group.blocked && entered.selected
    const oldSource = old.sources.find((row: Data) => row.index === entered.source_index)
    const newSource = oldSource && group.sources.find((row: Data) => sourceKey(row) === sourceKey(oldSource))
    if (!newSource) return
    target.source_index = newSource.index
    target.material = incomingMaterial(group, newSource.index)
    const baseline = incomingMaterial(old, oldSource.index)
    for (const field of Object.keys(materialDefaults)) {
      if (entered.material[field] === undefined) continue
      // Older drafts could contain an automatically inherited price/currency.
      const inheritedPricing = ['price', 'currency', 'customs_unit'].includes(field) && target.material[field] === '' &&
        String(entered.material[field] ?? '') === String(old.existing?.data[field] ?? '')
      const legacyDefaultPrice = field === 'price' && !entered.defaultsRevision && !old.existing && !oldSource.source.price &&
        String(entered.material.price) === String(materialDefaults.price)
      if (!inheritedPricing && !legacyDefaultPrice && String(entered.material[field] ?? '') !== String(baseline[field] ?? '')) target.material[field] = clone(entered.material[field])
    }
    if (group.existing?.data.code) target.material.code = group.existing.data.code
    // Changed masters require a fresh duplicate decision, even when edits survive.
    if (old.existing?.id === group.existing?.id && old.existing?.version === group.existing?.version) target.decision = entered.decision
    const oldRecipes = importChoices([old])[0]!.recipes
    for (const recipe of target.recipes) {
      const edit = entered.recipes.find((row: Data) => row.product_id === recipe.product_id)
      const before = oldRecipes.find((row: Data) => row.product_id === recipe.product_id)
      if (edit?.decision === 'import' && before && (before.decision !== 'import' || String(edit.usage) !== String(before.usage))) {
        recipe.decision = 'import'; recipe.usage = edit.usage
      }
    }
  })
  return next
}
export function importChoices(groups: Data[]): Data[] {
  return groups.map(group => {
    const sourceIndex = group.sources.length === 1 ? group.sources[0].index : -1
    return { group: group.index, selected: !group.blocked, source_index: sourceIndex, defaultsRevision: masterParserRevision,
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

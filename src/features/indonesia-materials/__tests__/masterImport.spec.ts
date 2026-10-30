import { describe, expect, it } from 'vitest'
import { importChoices, incomingMaterial, importPayload, sourceUsages, restoreImportEdits } from '../masterImport'
import { materialDefaults } from '../forms'

describe('master material comparison and per-product usage', () => {
  const group = { index: 0, blocked: '', existing: null, products: [{ id: 'p1' }, { id: 'p2' }], sources: [
    { index: 1, product_ids: ['p1'], source: { item_no: '40149', name: '共用件', piece_usage: '2' } },
    { index: 2, product_ids: ['p2'], source: { item_no: '40379', name: '共用件', piece_usage: '3' } },
  ] }
  it('keeps each product usage independent when material source data is shared', () => {
    const [choice] = importChoices([group])
    expect(choice!.source_index).toBe(-1)
    expect(choice!.recipes.map((r: { usage: string }) => r.usage)).toEqual(['2', '3'])
    expect(sourceUsages(group, 'p1')).toEqual(['2'])
  })
  it('does not infer missing or ambiguous usage or customs unit from quantities', () => {
    const source = { ...group, sources: [...group.sources, { index: 3, product_ids: ['p1'], source: { item_no: '40149', name: '共用件', piece_usage: '4' } }] }
    expect(importChoices([source])[0]!.recipes[0].usage).toBe('')
    const missing = { ...group, sources: [{ index: 1, product_ids: ['p1'], source: { quantity: '8000', unit: 'pcs' } }] }
    expect(importChoices([missing])[0]!.recipes[0].usage).toBe('')
    expect(incomingMaterial(missing, 1).customs_unit).toBe('')
  })
  it('merges only present material values and keeps originals including images', () => {
    const g = { ...group, existing: { data: { ...materialDefaults, code: 'ORIGINAL', name: '旧名称', specification: '10*20', image_data: 'image', procurement_days: 20 } },
      sources: [{ index: 1, source: { name: '新名称', specification: '', code: '' } }] }
    expect(incomingMaterial(g, 1)).toMatchObject({ code: 'ORIGINAL', name: '新名称', specification: '10*20', image_data: 'image', procurement_days: 20 })
    const choice = importChoices([g])[0]!
    choice.decision = 'keep'
    expect(importPayload([choice]).choices[0]!.material).toBeNull()
  })
  it('takes the selected source photo only when adopting imported details', () => {
    const g = { ...group, existing: { data: { ...materialDefaults, code: 'M', image_data: 'old-photo' } },
      sources: [{ index: 1, source: { image_data: 'new-photo' } }, { index: 2, source: { name: 'no photo' } }] }
    expect(incomingMaterial(g, 1).image_data).toBe('new-photo')
    expect(incomingMaterial(g, 2).image_data).toBe('old-photo')
    const choice = importChoices([g])[0]!
    choice.source_index = 1; choice.decision = 'import'; choice.material = incomingMaterial(g, 1)
    expect(importPayload([choice]).choices[0]!.material!.image_data).toBe('new-photo')
    choice.decision = 'keep'
    expect(importPayload([choice]).choices[0]!.material).toBeNull()
  })
  it('keeps missing codes blank and offers a source code only for a blank saved code', () => {
    const g = { ...group, sources: [{ index: 1, source: { name: '无编码物料', unit: 'pcs' } }] }
    expect(incomingMaterial(g, 1).code).toBe('')
    const existing = { ...g, existing: { data: { ...materialDefaults, code: '' } }, sources: [{ index: 1, source: { code: 'NEW-CODE' } }] }
    const choice = importChoices([existing])[0]!
    expect(choice.decision).toBe('')
    expect(choice.material.code).toBe('NEW-CODE')
    choice.decision = 'keep'
    expect(importPayload([choice]).choices[0]!.material).toBeNull()
    expect(incomingMaterial({ ...existing, existing: { data: { ...materialDefaults, code: 'ORIGINAL' } } }, 1).code).toBe('ORIGINAL')
  })
  it('does not combine new price, currency or pricing unit with an incompatible old set', () => {
    const old = { data: { ...materialDefaults, customs_unit: 'PCE', price: '2', currency: 'USD' } }
    const incoming = (source: object) => incomingMaterial({ ...group, existing: old, sources: [{ index: 1, source }] }, 1)
    expect(incoming({ price: '12.75', customs_unit: 'KGM' })).toMatchObject({ price: '12.75', customs_unit: 'KGM', currency: '' })
    expect(incoming({ price: '12.75', currency: 'USD' }).customs_unit).toBe('')
    expect(incoming({ customs_unit: 'KGM' })).toMatchObject({ price: '', currency: '', customs_unit: 'KGM' })
    expect(incoming({ currency: 'HKD' }).price).toBe('')
    expect(incoming({ customs_unit: 'pce' })).toMatchObject({ price: '2', currency: 'USD' })
    expect(incoming({ price: '0', customs_unit: 'KGM', currency: 'HKD' })).toMatchObject({ price: '0', currency: 'HKD' })
    expect(incoming({ name: '只更名称' })).toMatchObject({ price: '2', currency: 'USD', customs_unit: 'PCE' })
  })
  it('rereads new fields while retaining typed values, exclusions and independent usages', () => {
    const before = { ...group, products: [{ id: 'p1' }], sources: [{ index: 1, source_sheet: '明细', source_row: 3,
      product_ids: ['p1'], source: { item_no: 'ITEM', name: '袖子*2', price: '12.75' } }] }
    const edits = importChoices([before]); edits[0]!.material.supplier = '已填供应商'; edits[0]!.recipes[0].usage = '3'; edits[0]!.selected = false
    const after = { ...before, sources: [{ ...before.sources[0]!, index: 8, source: { ...before.sources[0]!.source, customs_unit: 'KGM', unit: 'PCS', piece_usage: '2' } }] }
    const [restored] = restoreImportEdits([before], edits, [after])
    expect(restored!.material).toMatchObject({ supplier: '已填供应商', customs_unit: 'KGM', unit: 'PCS' })
    expect(restored!.recipes[0].usage).toBe('3'); expect(restored!.selected).toBe(false); expect(restored!.source_index).toBe(8)
    expect(edits[0]!.material.customs_unit).toBe('')
    expect(restoreImportEdits([before], importChoices([before]), [after])[0]!.recipes[0].usage).toBe('2')
  })
  it('adds a newly compressed source photo while preserving manually chosen photos and the old draft', () => {
    const before = { ...group, sources: [{ index: 1, source_sheet: '明细', source_row: 3, source: { name: '线材' } }] }
    const after = { ...before, sources: [{ ...before.sources[0]!, source: { name: '线材', image_data: 'compressed-photo' } }] }
    const edits = importChoices([before])
    expect(restoreImportEdits([before], edits, [after])[0]!.material.image_data).toBe('compressed-photo')
    expect(edits[0]!.material.image_data).toBe('')
    edits[0]!.material.image_data = 'manual-photo'
    expect(restoreImportEdits([before], edits, [after])[0]!.material.image_data).toBe('manual-photo')
    expect(edits[0]!.material.image_data).toBe('manual-photo')
  })
  it('requires a new decision on changed master versions and does not carry inherited old pricing', () => {
    const old = { ...group, existing: { id: 'm', version: 1, data: { ...materialDefaults, customs_unit: 'PCE', price: '2', currency: 'USD' } },
      sources: [{ index: 1, source_sheet: '明细', source_row: 3, source: { name: '袖子*2', customs_unit: 'KGM' } }] }
    const edits = importChoices([old]); edits[0]!.decision = 'import'
    Object.assign(edits[0]!.material, { price: '2', currency: 'USD' }) // old UI inherited these implicitly
    const changed = { ...old, existing: { ...old.existing, version: 2 } }
    const [restored] = restoreImportEdits([old], edits, [changed])
    expect(restored!.decision).toBe(''); expect(restored!.material).toMatchObject({ price: '', currency: '' })
  })
  it('does not mistake legacy automatic zero for an edit or overwrite a newly fixed business code', () => {
    const old = { ...group, sources: [{ index: 1, source_sheet: '明细', source_row: 3, source: { name: '袖子*2' } }] }
    const edits = importChoices([old]); delete edits[0]!.defaultsRevision; edits[0]!.material.price = '0'; edits[0]!.material.code = 'USER-CODE'
    const next = { ...old, existing: { id: 'newly-created', version: 1, data: { ...materialDefaults, code: 'SAVED-CODE' } },
      sources: [{ ...old.sources[0]!, source: { name: '袖子*2', price: '12.75', currency: 'USD', customs_unit: 'KGM' } }] }
    const [restored] = restoreImportEdits([old], edits, [next])
    expect(restored!.material).toMatchObject({ price: '12.75', code: 'SAVED-CODE' })
    expect(restored!.decision).toBe('')
    expect(edits[0]!.material.code).toBe('USER-CODE')
    const currentEdits = importChoices([old]); currentEdits[0]!.material.price = '0'
    expect(restoreImportEdits([old], currentEdits, [next])[0]!.material.price).toBe('0')
  })
})

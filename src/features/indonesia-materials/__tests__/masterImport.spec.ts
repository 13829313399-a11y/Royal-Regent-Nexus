import { describe, expect, it } from 'vitest'
import { importChoices, incomingMaterial, importPayload, sourceUsages } from '../masterImport'
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
})

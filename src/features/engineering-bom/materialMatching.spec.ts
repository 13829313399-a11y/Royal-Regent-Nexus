import { describe, expect, it } from 'vitest'
import { newNode, type Material } from './api'
import { applyMaterialMatches, materialMatches } from './materialMatching'

const material = (): Material => ({ id: 'm1', code: '04-01-00001', name: '裁片', version: 2, status: 'ACTIVE',
  data: { unit: '套', engineering: { group: '04-01', department: '裁床', attribute: '自制', approval: 'APPROVED' } } })
const node = () => ({ ...newNode(), key: 'n1', source_code: '04-01-00001', source_name: '裁片', unit: '套',
  source: { '物料属性': '自制', row: '12', sheet: '原始表' }, review_required: true, review_note: '原核对依据',
  parent: 'root', numerator: '0.0297', denominator: '2', process: '车缝', exempt_loss: true, note: '保留备注' })
const selection = { row: 1, key: 'n1', material_id: 'm1', material_version: 2 }

describe('unmatched material selection', () => {
  it('applies explicitly selected rows without changing any source, quantity, process or review fields', () => {
    const original = node(), untouched = { ...node(), key: 'n2' }, pinned = { ...node(), key: 'pinned', material_id: 'm1', material_version: 1 }
    const nodes = [original, untouched, pinned], result = applyMaterialMatches(nodes, [material()], [selection])
    expect(result[0]).toEqual({ ...original, material_id: 'm1', material_version: 2 })
    expect(result[1]).toEqual(untouched); expect(result[2]).toEqual(pinned)
    expect(original.material_id).toBe(''); expect(materialMatches(nodes, [material()])).toHaveLength(2)
  })
  it('does not merge identical codes or match a different source attribute', () => {
    const rows = materialMatches([node(), { ...node(), key: 'subcontract', source: { '物料属性': '委外' } }, { ...node(), key: 'same' }], [material()])
    expect(rows).toHaveLength(3); expect(rows[0]!.material?.id).toBe('m1')
    expect(rows[1]!.material).toBeNull(); expect(rows[1]!.issue).toContain('来源属性')
    expect(rows[2]!.material?.id).toBe('m1')
  })
  it.each([
    ['name', { name: '其他名称' }], ['unit', { data: { ...material().data, unit: '码' } }],
    ['inactive', { status: 'INACTIVE' }], ['pending', { data: { ...material().data, engineering: { ...material().data.engineering!, approval: 'DRAFT' } } }],
  ])('rejects %s mismatches', (_, update) => {
    expect(materialMatches([node()], [{ ...material(), ...update }])[0]!.material).toBeNull()
  })
  it('requires unique codes and unique occurrence keys, and never guesses missing code', () => {
    expect(materialMatches([node()], [material(), { ...material(), id: 'another' }])[0]!.issue).toContain('多个候选')
    expect(materialMatches([node(), node()], [material()]).every(row => !row.material)).toBe(true)
    expect(materialMatches([{ ...node(), source_code: '' }], [material()])[0]!.material).toBeNull()
  })
  it('shows a candidate with explicit attribute when the source did not provide one', () => {
    const result = materialMatches([{ ...node(), source: {} }], [material()])[0]!
    expect(result.sourceAttribute).toBe(''); expect(result.material?.data.engineering?.attribute).toBe('自制')
  })
  it('rejects stale candidates, moved rows, fixed rows and duplicate selection atomically', () => {
    const original = [node()]
    expect(() => applyMaterialMatches(original, [{ ...material(), version: 3 }], [selection])).toThrow('已变化')
    expect(() => applyMaterialMatches([{ ...node(), key: 'different' }], [material()], [selection])).toThrow('已变化')
    expect(() => applyMaterialMatches([{ ...node(), material_id: 'already' }], [material()], [selection])).toThrow('已变化')
    expect(() => applyMaterialMatches(original, [material()], [selection, selection])).toThrow()
    expect(() => applyMaterialMatches(original, [material()], [selection, { ...selection, row: 99 }])).toThrow()
    expect(original[0]!.material_id).toBe('')
  })
})

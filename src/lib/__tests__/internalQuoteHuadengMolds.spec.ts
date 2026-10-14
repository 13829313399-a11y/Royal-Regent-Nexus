import { describe, expect, it } from 'vitest'
import { huadengLaborJob, injectionLaborOwner, linkEngineeringMolding } from '../internalQuoteMoldLinkage'
import { rebaseEngineeringMolding } from '../internalQuoteMoldingSync'
import { validateMoldSplit } from '../internalQuoteMoldSplit'
import { normalizeInternalQuotePayload, type EngineeringPayload, type MoldingPayload } from '../internalQuoteSectionPayload'

const normalizeEngineering = (value: Record<string, unknown>) => normalizeInternalQuotePayload('engineering', value) as unknown as EngineeringPayload
const molding = (value: Record<string, unknown> = {}) => normalizeInternalQuotePayload('molding', value) as unknown as MoldingPayload
const source = () => normalizeEngineering({ molds: [{ mold_id: 'm', molding_profile: 'huadeng_parts_v1', item: '模具', mold_no: 'M01', net_weight_g: 999, machine_code: '18A', target_output: 100,
  parts: [2, 3, 5, 7].map((weight, index) => ({ part_id: `p${index}`, name: '同名', unit_net_weight_g: weight, output_count: 6, quantity: 2, material_type: index === 1 ? 'GPPS' : 'ABS', remark: index === 2 ? '转水口' : '', source_row: index + 12, image_attachment_ids: [`image${index}`] })) }] })

describe('explicit Huadeng part mapping', () => {
  it.each([undefined, '', '  ', 0, '0.0', 250])('inherits only absent/zero capacity, preserving positive values: %s', value => {
    const engineering = source()
    engineering.molds[0]!.parts[0]!.target_output = value
    const normalized = normalizeEngineering(engineering as unknown as Record<string, unknown>)
    expect(validateMoldSplit(normalized.molds[0]!.parts)).toBe('')
    const result = linkEngineeringMolding(normalized, molding(), 'huadeng')
    expect(result.injection_lines[0]!.target_output).toBe(value === 250 ? 250 : 100)
    expect(result.injection_lines[0]!.engineering_linkage_conflict).toBeUndefined()
  })

  it.each([-1, 'abc', 'NaN', 'Infinity'])('retains and rejects invalid child capacity, without inheriting a price: %s', value => {
    const engineering = source()
    const previous = linkEngineeringMolding(engineering, molding(), 'huadeng')
    engineering.molds[0]!.parts[0]!.target_output = value
    const normalized = normalizeEngineering(engineering as unknown as Record<string, unknown>)
    expect(normalized.molds[0]!.parts[0]!.target_output).toBe(value)
    expect(validateMoldSplit(normalized.molds[0]!.parts)).toContain('产能')
    const result = linkEngineeringMolding(normalized, previous, 'huadeng')
    expect(result.injection_lines[0]!.target_output).not.toBe(100)
    expect(result.injection_lines[0]!.engineering_linkage_conflict).toBe(true)
  })
  it('retains source values/images, generates stable per-part rows and only two jobs', () => {
    const engineering = source()
    const payload = linkEngineeringMolding(engineering, molding(), 'huadeng')
    expect(payload.injection_lines.map(row => row.net_weight_g)).toEqual([2, 3, 5, 7])
    expect(payload.injection_lines.map(row => row.material)).toEqual(['ABS', 'GPPS', 'ABS', 'ABS'])
    expect(payload.injection_lines.map(row => row.quantity)).toEqual([1, 1, 1, 1])
    expect(payload.injection_lines.map(row => injectionLaborOwner(row, payload.injection_lines, 'huadeng'))).toEqual([true, false, true, false])
    expect(new Set(payload.injection_lines.map(row => huadengLaborJob(row, 'huadeng'))).size).toBe(2)
    expect(new Set(payload.injection_lines.map(row => row.line_id)).size).toBe(4)
    expect(payload.injection_lines[1]!.image_attachment_ids).toEqual(['image1'])
    expect(molding(payload as unknown as Record<string, unknown>)).toEqual(payload)
    expect(normalizeEngineering(engineering as unknown as Record<string, unknown>)).toEqual(engineering)
  })

  it('requires factory and explicit profile, with no ghost shared job for all transfers', () => {
    const engineering = source()
    expect(linkEngineeringMolding(engineering, molding()).injection_lines).toHaveLength(1)
    expect(linkEngineeringMolding(engineering, molding(), 'huakang-b').injection_lines).toHaveLength(1)
    for (const part of engineering.molds[0]!.parts) part.remark = '转水口'
    const payload = linkEngineeringMolding(engineering, molding(), 'huadeng')
    expect(new Set(payload.injection_lines.map(row => huadengLaborJob(row, 'huadeng'))).size).toBe(4)
    delete engineering.molds[0]!.molding_profile
    expect(linkEngineeringMolding(engineering, molding(), 'huadeng').injection_lines).toHaveLength(1)
  })

  it('keeps manual selections through reorder and detached suppression through source edits', () => {
    const engineering = source()
    const before = linkEngineeringMolding(engineering, molding(), 'huadeng')
    Object.assign(before.injection_lines[0]!, { grade: 'saved-grade', machine_code: '24A', remark: 'manual' })
    before.injection_lines[1]!.engineering_sync_disabled = true
    before.injection_lines[1]!.net_weight_g = 8
    engineering.molds[0]!.parts.reverse()
    engineering.molds[0]!.parts[3]!.name = 'renamed'
    const after = linkEngineeringMolding(engineering, before, 'huadeng')
    expect(after.injection_lines.find(row => row.engineering_part_id === 'p0')).toMatchObject({ item: 'renamed', grade: 'saved-grade', machine_code: '24A', remark: 'manual' })
    expect(after.injection_lines.find(row => row.engineering_part_id === 'p1')).toEqual(before.injection_lines[1])
    engineering.molds[0]!.parts = engineering.molds[0]!.parts.filter(part => part.part_id !== 'p0')
    const removed = linkEngineeringMolding(engineering, after, 'huadeng')
    expect(removed.injection_lines.find(row => row.engineering_part_id === 'p0')?.engineering_source_missing).toBe(true)
  })

  it('rebases a multi-part group without conflating mold aliases or discarding unsaved remarks', () => {
    const engineering = source()
    const before = linkEngineeringMolding(engineering, molding(), 'huadeng')
    const local = structuredClone(before)
    local.injection_lines[1]!.remark = 'unsaved'
    engineering.molds[0]!.parts.reverse()
    engineering.molds[0]!.parts[2]!.unit_net_weight_g = 9
    const incoming = linkEngineeringMolding(engineering, before, 'huadeng')
    const after = rebaseEngineeringMolding(before as unknown as Record<string, unknown>, incoming as unknown as Record<string, unknown>, local as unknown as Record<string, unknown>, engineering) as unknown as MoldingPayload
    expect(after).toBeDefined()
    expect(after.injection_lines.find(row => row.engineering_part_id === 'p1')).toMatchObject({ net_weight_g: 9, remark: 'unsaved' })
    expect(after.injection_lines).toHaveLength(4)
  })
})

import { describe, expect, it } from 'vitest'
import { linkEngineeringMolding, normalizeEngineeringMoldIdentities } from '../internalQuoteMoldLinkage'
import { moldingMaterialOptions, selectedMoldingMaterial } from '../internalQuoteMoldingReferences'
import { normalizeInternalQuotePayload, type EngineeringPayload, type MoldingPayload } from '../internalQuoteSectionPayload'

const engineering = (molds: unknown[]) => normalizeInternalQuotePayload('engineering', { molds }) as unknown as EngineeringPayload
const molding = (injection_lines: unknown[] = []) => normalizeInternalQuotePayload('molding', { injection_lines }) as unknown as MoldingPayload

describe('stable whole mold linkage', () => {
  it('retains the group cost once and carries real children after rename/reorder', () => {
    const source = normalizeEngineeringMoldIdentities(engineering([{ mold_id: 'm1', item: '外壳', mold_no: 'A', net_weight_g: 100, parts: [{ part_id: 'p1', name: '左', unit_net_weight_g: 40 }, { part_id: 'p2', name: '右', unit_net_weight_g: 60 }] }]))
    const first = linkEngineeringMolding(source, molding())
    source.molds[0]!.mold_no = 'B'
    source.molds[0]!.parts.reverse()
    const next = linkEngineeringMolding(source, first)
    expect(next.injection_lines).toHaveLength(1)
    expect(next.injection_lines[0]).toMatchObject({ line_id: 'injection:m1', mold_no: 'B', net_weight_g: 100, cost_scope: 'whole_mold', engineering_parts: [{ part_id: 'p2', unit_net_weight_g: 60 }, { part_id: 'p1', unit_net_weight_g: 40 }] })
    expect(first.injection_lines[0]!.mold_no).toBe('A')
  })
  it('preserves orphan department work for explicit resolution and keeps independent rows', () => {
    const linked = linkEngineeringMolding(engineering([{ mold_id: 'm1', item: '外壳' }]), molding([{ item: '独立', engineering_sync_disabled: true }]))
    const removed = linkEngineeringMolding(engineering([]), linked)
    expect(removed.injection_lines).toHaveLength(2)
    expect(removed.injection_lines[0]!.engineering_source_missing).toBe(true)
    expect(removed.injection_lines[1]!.item).toBe('独立')
  })
  it('never matches opaque ABS to transparent ABS or substitutes an unknown grade', () => {
    const references = [{ material: 'ABS', grade: '750', priceHkdLb: 8 }, { material: '透明ABS', grade: '750', priceHkdLb: 12 }, { material: '1#PP', grade: '7032 E3', priceHkdLb: 6.8 }]
    expect(selectedMoldingMaterial({ material: 'PP', grade: '7032 E3' }, references)?.material).toBe('1#PP')
    expect(moldingMaterialOptions({ material: 'ABS', grade: '' }, references)).toHaveLength(1)
    expect(selectedMoldingMaterial({ material: 'ABS', grade: 'unknown' }, references)).toBeUndefined()
    expect(selectedMoldingMaterial({ material: 'ABS', grade: '' }, references)).toBeUndefined()
  })
  it('keeps detached values and suppression identity through reload, source edits and deletion', () => {
    const source = engineering([{ mold_id: 'm1', item: '外壳', mold_no: 'A', net_weight_g: 100, parts: [{ part_id: 'p1', name: '左' }] }])
    const draft = linkEngineeringMolding(source, molding())
    const detached = draft.injection_lines[0]!
    detached.engineering_sync_disabled = true
    detached.engineering_synced_fields = []
    detached.engineering_parts = []
    delete detached.cost_scope
    detached.item = '独立外壳'
    detached.net_weight_g = 77
    const expected = JSON.parse(JSON.stringify(detached))
    const reloaded = molding(JSON.parse(JSON.stringify(draft.injection_lines)))
    source.molds[0]!.item = '改名'
    source.molds[0]!.mold_no = 'B'
    source.molds[0]!.net_weight_g = 999
    source.molds[0]!.parts[0]!.name = '新部件'
    const refreshed = linkEngineeringMolding(source, reloaded)
    expect(refreshed.injection_lines).toHaveLength(1)
    expect(refreshed.injection_lines[0]).toMatchObject(expected)
    expect(refreshed.injection_lines[0]!.engineering_parts).toEqual([])
    expect(refreshed.injection_lines[0]!.cost_scope).toBeUndefined()
    refreshed.injection_lines[0]!.engineering_source_missing = true
    const removed = linkEngineeringMolding(engineering([]), refreshed)
    expect(removed.injection_lines[0]!.engineering_source_missing).toBeUndefined()
    const added = linkEngineeringMolding(engineering([{ mold_id: 'm2', item: '新模具' }]), removed)
    expect(added.injection_lines).toHaveLength(2)
    expect(added.injection_lines.map((row) => row.line_id)).toEqual(['injection:m2', 'injection:m1'])
    expect(added.injection_lines[1]).toMatchObject(expected)
  })
  it('matches detached stable mold identity and keeps copies without source identity independent', () => {
    const source = engineering([{ mold_id: 'm1', item: '外壳', mold_no: 'A' }])
    const detached = molding([{ line_id: 'kept', engineering_mold_id: 'm1', engineering_source_key: 'legacy-key', engineering_sync_disabled: true, item: '独立', net_weight_g: 77, engineering_parts: [] }])
    expect(linkEngineeringMolding(source, detached).injection_lines).toEqual(detached.injection_lines)
    const linked = linkEngineeringMolding(source, molding())
    linked.injection_lines.push(molding([{ line_id: 'manual-copy', engineering_sync_disabled: true, item: '复制', mold_no: 'A', net_weight_g: 77 }]).injection_lines[0]!)
    source.molds[0]!.item = '改名'
    const refreshed = linkEngineeringMolding(source, linked)
    expect(refreshed.injection_lines).toHaveLength(2)
    expect(refreshed.injection_lines[0]!.item).toBe('改名')
    expect(refreshed.injection_lines[1]).toMatchObject({ line_id: 'manual-copy', item: '复制', net_weight_g: 77 })
  })
  it('migrates a genuine detached legacy source key when stable IDs are first allocated', () => {
    const legacy = engineering([{ mold_no: 'M1', item: '外壳', net_weight_g: 100 }])
    const draft = linkEngineeringMolding(legacy, molding())
    const row = draft.injection_lines[0]!
    expect(row.engineering_mold_id).toBeUndefined()
    expect(row.engineering_source_key).toBe('mold-no:M1#1')
    Object.assign(row, { line_id: 'legacy-line', engineering_sync_disabled: true, engineering_synced_fields: [], engineering_parts: [], item: '独立', net_weight_g: 77 })
    const adopted = normalizeEngineeringMoldIdentities(legacy)
    const savedEngineering = engineering(JSON.parse(JSON.stringify(adopted.molds)))
    expect(savedEngineering.molds[0]!.legacy_source_key).toBe('mold-no:M1#1')
    const saved = linkEngineeringMolding(savedEngineering, molding(JSON.parse(JSON.stringify(draft.injection_lines))))
    expect(saved.injection_lines).toHaveLength(1)
    expect(saved.injection_lines[0]).toMatchObject({ line_id: 'legacy-line', engineering_mold_id: adopted.molds[0]!.mold_id, engineering_source_key: `mold-id:${adopted.molds[0]!.mold_id}`, item: '独立', net_weight_g: 77, engineering_parts: [] })
    const withoutLineId = molding(JSON.parse(JSON.stringify(draft.injection_lines)))
    delete withoutLineId.injection_lines[0]!.line_id
    expect(linkEngineeringMolding(savedEngineering, withoutLineId).injection_lines[0]!.line_id).toBe(`injection:${adopted.molds[0]!.mold_id}`)
    savedEngineering.molds[0]!.mold_no = 'renamed'
    savedEngineering.molds[0]!.net_weight_g = 999
    const renamed = linkEngineeringMolding(savedEngineering, saved)
    expect(renamed.injection_lines).toEqual(saved.injection_lines)
    expect(linkEngineeringMolding(engineering([]), renamed).injection_lines).toEqual(saved.injection_lines)
    const manual = molding([{ line_id: 'copy', mold_no: 'M1', item: '独立', engineering_sync_disabled: true }])
    expect(linkEngineeringMolding(adopted, manual).injection_lines).toHaveLength(2)
  })
  it('blocks duplicate legacy associations without inventing replacement rows and clears resolved conflicts', () => {
    const adopted = normalizeEngineeringMoldIdentities(engineering([{ mold_no: 'M1', item: '外壳' }]))
    const first = { line_id: 'legacy-1', engineering_source_key: 'mold-no:M1#1', engineering_sync_disabled: true, item: '独立1' }
    const second = { ...first, line_id: 'legacy-2', item: '独立2' }
    const ambiguous = linkEngineeringMolding(adopted, molding([first, second]))
    expect(ambiguous.injection_lines.map((row) => row.line_id)).toEqual(['legacy-1', 'legacy-2'])
    expect(ambiguous.injection_lines.every((row) => row.engineering_linkage_conflict)).toBe(true)
    const reloaded = molding(JSON.parse(JSON.stringify(ambiguous.injection_lines)))
    expect(reloaded.injection_lines.every((row) => row.engineering_linkage_conflict)).toBe(true)
    const resolved = linkEngineeringMolding(adopted, molding([reloaded.injection_lines[0]]))
    expect(resolved.injection_lines).toHaveLength(1)
    expect(resolved.injection_lines[0]!.engineering_linkage_conflict).toBeUndefined()
    const duplicateAliases = engineering([{ ...adopted.molds[0], mold_id: 'a' }, { ...adopted.molds[0], mold_id: 'b' }])
    const conflict = linkEngineeringMolding(duplicateAliases, molding([first]))
    expect(conflict.injection_lines).toHaveLength(1)
    expect(conflict.injection_lines[0]!.engineering_linkage_conflict).toBe(true)
    expect(linkEngineeringMolding(engineering([]), conflict).injection_lines[0]!.engineering_linkage_conflict).toBeUndefined()
    const stable = linkEngineeringMolding(adopted, molding()).injection_lines[0]!
    const mixed = linkEngineeringMolding(adopted, molding([first, stable]))
    expect(mixed.injection_lines).toHaveLength(2)
    expect(mixed.injection_lines.every((row) => row.engineering_linkage_conflict)).toBe(true)
  })
})

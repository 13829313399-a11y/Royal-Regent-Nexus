import { describe, expect, it } from 'vitest'
import { rebaseEngineeringMolding } from '../internalQuoteMoldingSync'

describe('whole-mold projection into an open molding draft', () => {
  const parent = { engineering_source_key: 'mold-no:1#1', item: '上/下', net_weight_g: 50, quantity: 1, grade: '750SW', remark: '' }
  const group = (name: string, weight: number) => ({ ...parent,
    item: name, net_weight_g: weight, engineering_parts: [{ name: '上', unit_net_weight_g: 0 }, { name: '下', unit_net_weight_g: 0 }],
    cost_scope: 'whole_mold', engineering_synced_fields: ['item', 'net_weight_g', 'quantity'] })
  const baseline = { injection_lines: [parent], blow_lines: [] }
  it('shows descriptive children once while retaining unsaved grade/remark and manual rows', () => {
    const local = { ...baseline, injection_lines: [{ ...parent, grade: 'PA757', remark: '正在填写' }, { item: '手工' }] }
    const incoming = { ...baseline, injection_lines: [group('上下壳', 50)] }
    const result = rebaseEngineeringMolding(baseline, incoming, local)!
    expect(result.injection_lines).toEqual([
      { ...group('上下壳', 50), grade: 'PA757', remark: '正在填写' }, { item: '手工' },
    ])
  })
  it('does not hide a concurrent department edit', () => {
    const incoming = { ...baseline, injection_lines: [{ ...group('上', 10), remark: '其他人修改' }] }
    expect(rebaseEngineeringMolding(baseline, incoming, baseline)).toBeUndefined()
  })
  it('retains removed-source work for explicit resolution instead of deleting it', () => {
    const first = group('模一', 10), second = { ...group('模二', 20), engineering_source_key: 'mold-no:2#1' }
    const before = { ...baseline, injection_lines: [first, second] }
    const local = { ...baseline, injection_lines: [{ ...first, remark: '上' }, { ...second, remark: '下' }] }
    expect(rebaseEngineeringMolding(before, { ...before, injection_lines: [second] }, local)?.injection_lines)
      .toEqual([{ ...second, remark: '下' }, { ...first, remark: '上', engineering_source_missing: true }])
  })
  it('adopts only the explicit legacy association, retaining detached values and same-named manual rows', () => {
    const detached = { ...parent, engineering_sync_disabled: true, engineering_synced_fields: [], engineering_parts: [], line_id: 'local-line', item: '独立', net_weight_g: 77 }
    const manual = { item: '独立', net_weight_g: 88 }
    const local = { ...baseline, injection_lines: [detached, manual] }
    const incoming = { ...baseline, injection_lines: [{ ...group('新名', 999), engineering_source_key: 'mold-id:m1', engineering_mold_id: 'm1', line_id: 'injection:m1' }] }
    const result = rebaseEngineeringMolding(baseline, incoming, local, { molds: [{ mold_id: 'm1', legacy_source_key: parent.engineering_source_key }] })!
    expect(result.injection_lines).toEqual([{ ...detached, engineering_source_key: 'mold-id:m1', engineering_mold_id: 'm1' }, manual])
    const removed = rebaseEngineeringMolding(incoming, { ...incoming, injection_lines: [] }, result)
    expect(removed?.injection_lines).toEqual(result.injection_lines)
  })
  it('rejects ambiguous legacy rows rather than selecting one or duplicating prices', () => {
    const duplicate = { ...baseline, injection_lines: [parent, { ...parent, remark: '另一个' }] }
    const incoming = { ...baseline, injection_lines: [{ ...group('新名', 50), engineering_source_key: 'mold-id:m1', engineering_mold_id: 'm1' }] }
    expect(rebaseEngineeringMolding(duplicate, incoming, duplicate, { molds: [{ mold_id: 'm1', legacy_source_key: parent.engineering_source_key }] })).toBeUndefined()
  })
  it('preserves stable line identity and local edits through source rename, reorder and new sources', () => {
    const first = { ...parent, engineering_mold_id: 'm1', line_id: 'stable', engineering_source_key: 'mold-id:m1' }
    const before = { ...baseline, injection_lines: [first] }
    const local = { ...before, injection_lines: [{ ...first, remark: '未保存' }] }
    const changed = { ...first, item: '改名', engineering_synced_fields: ['item'], engineering_parts: [{ name: '子件' }] }
    const added = { ...group('新模', 0), engineering_source_key: 'mold-id:m2', engineering_mold_id: 'm2' }
    expect(rebaseEngineeringMolding(before, { ...before, injection_lines: [added, changed] }, local)?.injection_lines)
      .toEqual([added, { ...changed, remark: '未保存' }])
  })
})

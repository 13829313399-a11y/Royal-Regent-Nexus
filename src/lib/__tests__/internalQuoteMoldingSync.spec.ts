import { describe, expect, it } from 'vitest'
import { rebaseEngineeringMolding } from '../internalQuoteMoldingSync'

describe('engineering child projection into an open molding draft', () => {
  const parent = { engineering_source_key: 'mold-no:1#1', item: '上/下', net_weight_g: 50, quantity: 1, grade: '750SW', remark: '' }
  const child = (name: string, weight: number) => ({ ...parent, engineering_source_key: `mold-no:1#1/part:["${name}",1]`,
    item: name, net_weight_g: weight, engineering_synced_fields: ['item', 'net_weight_g', 'quantity'] })
  const baseline = { injection_lines: [parent], blow_lines: [] }
  it('shows new children immediately while retaining unsaved machine/grade/remark and manual rows', () => {
    const local = { ...baseline, injection_lines: [{ ...parent, grade: 'PA757', remark: '正在填写' }, { item: '手工' }] }
    const incoming = { ...baseline, injection_lines: [child('上', 10), child('下', 20)] }
    const result = rebaseEngineeringMolding(baseline, incoming, local)!
    expect(result.injection_lines).toEqual([
      { ...child('上', 10), grade: 'PA757', remark: '正在填写' },
      { ...child('下', 20), grade: 'PA757', remark: '正在填写' }, { item: '手工' },
    ])
  })
  it('does not hide a concurrent department edit', () => {
    const incoming = { ...baseline, injection_lines: [{ ...child('上', 10), remark: '其他人修改' }] }
    expect(rebaseEngineeringMolding(baseline, incoming, baseline)).toBeUndefined()
  })
  it('retains sibling input ownership across reorders and removes deleted source children', () => {
    const first = child('上', 10), second = child('下', 20)
    const before = { ...baseline, injection_lines: [first, second] }
    const local = { ...baseline, injection_lines: [{ ...first, remark: '上' }, { ...second, remark: '下' }] }
    expect(rebaseEngineeringMolding(before, { ...before, injection_lines: [second] }, local)?.injection_lines)
      .toEqual([{ ...second, remark: '下' }])
  })
})

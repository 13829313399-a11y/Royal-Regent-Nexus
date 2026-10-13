import { describe, expect, it } from 'vitest'
import { newMoldSplitPart, prepareMoldSplit, validateMoldSplit } from '../internalQuoteMoldSplit'
import { normalizeInternalQuotePayload, type EngineeringPayload } from '../internalQuoteSectionPayload'

const mold = (value: Record<string, unknown>) => (normalizeInternalQuotePayload('engineering', { molds: [value] }) as unknown as EngineeringPayload).molds[0]!

describe('staged mold splitting', () => {
  it('does not split ordinary saves and inherits each original mold count in the explicit draft', () => {
    const source = mold({ item: '上壳/下壳', cavity: '4', quantity: 2, net_weight_g: 100 })
    expect(source.parts).toEqual([])
    const parts = prepareMoldSplit(source)
    expect(parts).toHaveLength(2)
    expect(parts.every(part => part.id && part.output_count === 4 && part.quantity === 2 && part.unit_net_weight_g === 0)).toBe(true)
    expect(source.parts).toEqual([])
  })

  it('retains saved and manually added children without sharing mutable state', () => {
    const source = mold({ cavity: '4', quantity: 2, parts: [{ name: '手工件', output_count: 8, quantity: 3, unit_net_weight_g: 12 }] })
    const parts = prepareMoldSplit(source)
    expect(parts).toEqual(source.parts)
    parts[0]!.quantity = 7
    expect(source.parts[0]!.quantity).toBe(3)
    expect(newMoldSplitPart(source)).toMatchObject({ output_count: 4, quantity: 2 })
  })

  it('requires complete positive weights and integer production counts', () => {
    const part = newMoldSplitPart(mold({ cavity: '4', quantity: 2 }), '上壳')
    expect(validateMoldSplit([part])).toContain('净重')
    part.unit_net_weight_g = 0.5
    expect(validateMoldSplit([part])).toBe('')
    part.output_count = 1.5
    expect(validateMoldSplit([part])).toContain('出模数')
    part.output_count = 4
    part.quantity = 0
    expect(validateMoldSplit([part])).toContain('套数')
    expect(validateMoldSplit([])).toContain('至少')
  })
})

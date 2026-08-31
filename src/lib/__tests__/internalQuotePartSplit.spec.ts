import { describe, expect, it } from 'vitest'
import { previewEngineeringMoldPartSplit, splitEngineeringMoldPartNames, type EngineeringMoldPartRow } from '../internalQuoteSectionPayload'

const vectors: [string, string[]][] = [
  ['粉色蝴蝶结前后', ['粉色蝴蝶结前', '粉色蝴蝶结后']],
  ['粉色蝴蝶结前/后', ['粉色蝴蝶结前', '粉色蝴蝶结后']],
  ['黑色前／后壳', ['黑色前壳', '黑色后壳']],
  ['前后壳', ['前壳', '后壳']],
  ['前/后壳（黑色）', ['前壳（黑色）', '后壳（黑色）']],
  ['前后壳（红/蓝）', ['前壳（红/蓝）', '后壳（红/蓝）']],
  ['前/后壳（红/蓝）', ['前壳（红/蓝）', '后壳（红/蓝）']],
  ['外壳(红/蓝)/支架【黑/白】', ['外壳(红/蓝)', '支架【黑/白】']],
  ['前壳/后盖', ['前壳', '后盖']],
  ['黑色前壳/白色后壳', ['黑色前壳', '白色后壳']],
  ['左右前枪身（橙色）', ['左前枪身（橙色）', '右前枪身（橙色）']],
  ['左/右手', ['左手', '右手']],
  ['泵杆/击锤/扣机/配件(7件)', ['泵杆', '击锤', '扣机', '配件(7件)']],
  ['前后左右壳', ['前后左右壳']],
  [' 黑色前/后壳 / 黑色眼睛 / ', ['黑色前壳', '黑色后壳', '黑色眼睛']],
  ['', []],
]
function part(name: string, price = 2.5): EngineeringMoldPartRow {
  return { name, color: '粉色', process: '电镀', process_unit_price_hkd: price, unit_net_weight_g: 15, output_count: 2, quantity: 1 }
}
describe('engineering part names and safe resplitting', () => {
  it.each(vectors)('splits %s consistently with export', (name, expected) => expect(splitEngineeringMoldPartNames(name)).toEqual(expected))
  it('repairs a unique legacy bare direction without losing its entered fields', () => {
    const front = part('粉色蝴蝶结前')
    const back = part('后', 7)
    const result = previewEngineeringMoldPartSplit('粉色蝴蝶结前/后', [front, back])
    expect(result.retainedCount).toBe(0)
    expect(result.rows[0]!.part).toBe(front)
    expect(result.rows[1]!.part).toEqual({ ...back, name: '粉色蝴蝶结后' })
    expect(back.name).toBe('后')
  })
  it('retains unmatched manual names and does not copy their amounts to new rows', () => {
    const manual = part('手工指定名', 10)
    const result = previewEngineeringMoldPartSplit('前后壳', [manual])
    expect(result.rows.map(({ status }) => status)).toEqual(['added', 'added', 'retained'])
    expect(result.rows[2]!.part).toBe(manual)
    expect(result.rows.reduce((sum, { part }) => sum + part.process_unit_price_hkd, 0)).toBe(10)
  })
  it('does not assign ambiguous shorthand data to either of two different backs', () => {
    const result = previewEngineeringMoldPartSplit('壳前/后/蝴蝶结前/后', [part('后')])
    expect(result.retainedCount).toBe(1)
    expect(result.rows.slice(0, 4).every(({ status }) => status === 'added')).toBe(true)
  })
  it('preserves distinct duplicate rows once each during repeated splitting', () => {
    const existing = [part('配件', 2), part('配件', 3)]
    const result = previewEngineeringMoldPartSplit('配件/配件', existing)
    expect(result.rows.map(({ part }) => part)).toEqual(existing)
    expect(result.retainedCount).toBe(0)
  })
})

import { describe, expect, it } from 'vitest'
import { splitEngineeringMoldPartNames } from '../internalQuoteSectionPayload'

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
describe('engineering part names', () => {
  it.each(vectors)('splits %s consistently with export', (name, expected) => expect(splitEngineeringMoldPartNames(name)).toEqual(expected))
})

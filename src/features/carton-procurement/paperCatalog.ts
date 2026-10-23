/** Confirmed paper names and the material/flute list supplied by the warehouse. */
export const standardPaperTypes = [
  { code: 'BOX-01', name: '普通箱', card: false },
  { code: 'BOX-02', name: '半翼箱', card: false },
  { code: 'CARD-01', name: '平卡', card: true },
  { code: 'CARD-02', name: '刀卡', card: true },
  { code: 'CARD-03', name: '压线卡', card: true },
  { code: 'CARD-04', name: '啤卡', card: true },
] as const
const single = ['B33', 'B3B', 'A3B', 'A3A', 'W3B', 'W3A', 'L3H', 'L4H', 'L+K', 'K3K', 'K3A', 'L+H', 'B9B', 'A9B', 'W9B', 'A9A', 'T+B', 'B150B']
const double = ['A=A', 'A=B', 'B=B', 'K=K', 'K535A', 'A33+A', 'A33+B', 'B33+B', 'H575A', 'L+H+H', 'R+3+R', 'A+3+A', 'A+35A', 'H3B3H', 'R535R']
export const paperQualities = [...single.map(name => ({ name, flute: '单坑' })), ...double.map(name => ({ name, flute: '双坑' }))]
const key = (value: string) => value.normalize('NFKC').replace(/\s/g, '').toUpperCase()
export const paperFlute = (value: string) => paperQualities.find(row => key(row.name) === key(value))?.flute ?? ''
export const paperStandard = (value: string) => standardPaperTypes.find(row => key(row.name) === key(value))
// Old names remain exact historical identities. Do not rename or merge their stock.
export const isCardPaper = (value: string) => !!paperStandard(value)?.card || ['卡纸', '隔卡'].includes(key(value))
export const dimensionLabel = (unit: string) => ({ cm: '厘米（cm）', mm: '毫米（mm）', in: 'inch', inch: 'inch' })[unit.trim().toLowerCase()] || (unit ? `原单位：${unit}` : '未注明尺寸单位')

/** Display only: neither the stored specification nor its original unit is changed. */
export function dimensionReference(specification: string, unit: string, preferredUnit?: 'cm' | 'inch' | 'mm'): string {
  const factor = ({ cm: 1, mm: 0.1, in: 2.54, inch: 2.54 })[unit.trim().toLowerCase()]
  if (!factor) return '请明确选择尺寸单位'
  const match = specification.normalize('NFKC').trim().match(/^(\d+(?:\.\d+)?)\s*[*×xX]\s*(\d+(?:\.\d+)?)(?:\s*[*×xX]\s*(\d+(?:\.\d+)?))?\s*(cm|厘米|mm|毫米|inches|inch|in|英寸)?\s*$/i)
  if (!match) return '非规则规格按原文保留；换算需完整的长×宽或长×宽×高'
  const embedded = match[4]?.toLowerCase()
  const embeddedFactor = embedded ? ({ cm: 1, '厘米': 1, mm: 0.1, '毫米': 0.1, in: 2.54, inch: 2.54, inches: 2.54, '英寸': 2.54 })[embedded] : undefined
  if (embeddedFactor != null && embeddedFactor !== factor) return '原规格单位与所选单位不一致，请核对'
  const dimensions = match.slice(1, 4).filter((x): x is string => x !== undefined).map(Number)
  if (dimensions.some(value => !Number.isFinite(value) || value <= 0)) return '请核对尺寸数字'
  const format = (value: number) => Number(value.toFixed(4)).toString()
  if (preferredUnit) {
    const targetFactor = { cm: 1, inch: 2.54, mm: 0.1 }[preferredUnit]
    return `${dimensions.map(value => format(value * factor / targetFactor)).join(' × ')} ${preferredUnit}（换算参考）`
  }
  return `${dimensions.map(value => format(value * factor)).join(' × ')} cm / ${dimensions.map(value => format(value * factor / 2.54)).join(' × ')} inch（换算参考）`
}

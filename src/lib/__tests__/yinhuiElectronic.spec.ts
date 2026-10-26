import { describe, expect, it } from 'vitest'
import { isYinhuiIc, readYinhuiElectronicSources, splitYinhuiElectronicRow, splitYinhuiLegacyElectronics } from '../customerPriceConverters/yinhuiElectronic'
import { readYinhuiSource } from '../customerPriceConverters/yinhuiSource'
import { createXlsxWorkbook, type XlsxParsedSheet } from '../customerPriceConverters/xlsxLite'

function sheet(): XlsxParsedSheet {
  return { name: '電子 報價', cellFillIds: [], rows: [
    ['产品编号：88052-TX 客户：华兴'],
    ['零件名称', '规格', '用量', '单价RMB', '合计RMB'],
    ['IC', 'IC,OTP,BURN,PMS152', 1, .5, .5],
    ['电阻', 'RES 0603', 2, .01, .02],
    ['产品编号：88052-RX 客户：华兴'],
    ['零件名称', '规格', '用量', '单价HKD', '合计HKD'],
    ['IC', 'IC,DRIVER,SA8301', 2, .1, .2],
    ['IC', 'IC,OTP,JTP', 1, .7, .7],
  ] }
}

describe('Yinhui supplier IC source evidence', () => {
  const main: XlsxParsedSheet = { name: '明细', cellFillIds: [], rows: [['汇率'], [.84]] }
  const parents = () => [
    { description: 'TX 遥控器*2pcs', quantity: 2, amountHkd: 6.295, internalHkd: 5, source: '明细!D1' },
    { description: 'RX 主机电子*2pcs', quantity: 2, amountHkd: 11.464, internalHkd: 9, source: '明细!D2' },
  ]
  it('uses the confirmed IC formula once and multiplies chip and assembly quantities', () => {
    const rows = splitYinhuiLegacyElectronics(parents(), [sheet()], main, '88052')
    expect(rows).toHaveLength(5)
    expect(rows[1]!.quantity).toBe(2)
    expect(rows[1]!.amountHkd / rows[1]!.quantity).toBeCloseTo(.5 / .84 * 1.08 / .96, 12)
    expect(rows[3]!.quantity).toBe(4)
    expect(rows[3]!.amountHkd).toBeCloseTo(.1 * 4 * 1.08 / .96, 12)
    expect(rows.reduce((total, row) => total + row.amountHkd, 0)).toBeCloseTo(17.759, 12)
    expect(rows.reduce((total, row) => total + row.internalHkd, 0)).toBeCloseTo(14, 12)
  })
  it('rejects duplicate groups, unmatched models, ambiguous parents and missing FX', () => {
    expect(() => splitYinhuiLegacyElectronics(parents(), [sheet(), sheet()], main, '88052')).toThrow(/唯一/)
    expect(() => splitYinhuiLegacyElectronics(parents(), [sheet()], main, '88490')).toThrow(/型号/)
    expect(() => splitYinhuiLegacyElectronics([...parents(), parents()[0]!], [sheet()], main, '88052')).toThrow(/唯一/)
    expect(() => splitYinhuiLegacyElectronics(parents(), [sheet()], { ...main, rows: [] }, '88052')).toThrow(/汇率/)
  })
  it('retains unmatched parents and never deducts another group after a failure', () => {
    const source = sheet(); source.rows[7]![3] = 70; source.rows[7]![4] = 70
    const input = parents(); const original = structuredClone(input)
    expect(() => splitYinhuiLegacyElectronics(input, [source], main, '88052')).toThrow(/超过/)
    expect(input).toEqual(original)
    expect(splitYinhuiLegacyElectronics(input, [], main, '88052')).toEqual(original)
  })
  it('places chips after their parent and preserves both totals without mutating inputs', () => {
    const parent = { description: 'TX (2PCS)', quantity: 2, amountHkd: 6.295, internalHkd: 5, source: 'main!D1' }
    const chips = [{ description: 'IC,OTP', quantity: 2, amountHkd: 1.281, internalHkd: 1, source: 'electronic!E3' }]
    const rows = splitYinhuiElectronicRow(parent, chips)
    expect(rows.map(r => r.description)).toEqual(['TX (2PCS)', 'IC,OTP'])
    expect(rows.reduce((total, row) => total + row.amountHkd, 0)).toBe(parent.amountHkd)
    expect(rows.reduce((total, row) => total + row.internalHkd, 0)).toBe(parent.internalHkd)
    expect(parent.amountHkd).toBe(6.295)
    expect(() => splitYinhuiElectronicRow(parent, [{ ...chips[0]!, amountHkd: 7 }])).toThrow(/超过/)
    expect(parent.amountHkd).toBe(6.295)
  })
  it('keeps TX/RX identities, currencies, quantities and source cells separate', () => {
    const groups = readYinhuiElectronicSources([sheet()])
    expect(groups).toHaveLength(2)
    expect(groups[0]).toMatchObject({ model: '88052', role: 'TX', chips: [{ quantity: 1, amount: .5, currency: 'RMB', source: '電子 報價!E3' }] })
    expect(groups[1]).toMatchObject({ model: '88052', role: 'RX', chips: [{ quantity: 2, amount: .2, currency: 'HKD' }, { quantity: 1, amount: .7 }] })
  })
  it('loads electronic source rows beyond the discovery preview', () => {
    const source = sheet()
    source.rows.splice(2, 0, ...Array.from({ length: 90 }, () => []))
    const bytes = createXlsxWorkbook([source])
    const parsed = readYinhuiSource(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer)
    expect(readYinhuiElectronicSources(parsed.sheets)[0]!.chips[0]!.source).toBe('電子 報價!E93')
  })
  it.each(['IC', 'ic,driver', 'ＩＣ，OTP'])('recognizes %s', name => expect(isYinhuiIc(name)).toBe(true))
  it.each(['MIC', 'MICROPHONE', 'PCB IC SOCKET', 'ICICLE'])('does not mistake %s for an IC part', name => expect(isYinhuiIc(name)).toBe(false))
  it.each([null, '', '#VALUE!', -1, true])('rejects invalid IC price %s', price => {
    const source = sheet(); source.rows[2]![3] = price
    expect(() => readYinhuiElectronicSources([source])).toThrow(/IC 单价/)
  })
  it('accepts zero and numeric text but rejects contradictory line totals', () => {
    const source = sheet(); source.rows[2]!.splice(2, 3, '2', '0', '0')
    expect(readYinhuiElectronicSources([source])[0]!.chips[0]).toMatchObject({ quantity: 2, amount: 0 })
    source.rows[2]![4] = 1
    expect(() => readYinhuiElectronicSources([source])).toThrow(/用量×单价/)
  })
  it('does not guess unspecified or mismatched currency', () => {
    const source = sheet(); source.rows[1]![3] = '单价'
    expect(() => readYinhuiElectronicSources([source])).toThrow(/币种/)
    source.rows[1]![3] = '单价HKD'
    expect(() => readYinhuiElectronicSources([source])).toThrow(/币种/)
  })
})

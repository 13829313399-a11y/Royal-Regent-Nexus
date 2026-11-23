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
  it('retains an unpriced parent while splitting only the known group and still rejects duplicate sources', () => {
    const input = parents().map((row, i) => i === 0 ? { ...row, pricePending: true, amountHkd: 0, internalHkd: 0 } : row)
    const result = splitYinhuiLegacyElectronics(input, [sheet()], main, '88052')
    expect(result).toHaveLength(4)
    expect(result[0]).toEqual(input[0])
    expect(result.slice(1).map(row => row.description)).toEqual(['RX 主机电子*2pcs', 'IC,DRIVER,SA8301', 'IC,OTP,JTP'])
    expect(result.reduce((total, row) => total + row.amountHkd, 0)).toBeCloseTo(input[1]!.amountHkd, 12)
    expect(() => splitYinhuiLegacyElectronics(input, [sheet(), sheet()], main, '88052')).toThrow(/唯一/)
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
  it.each(['红外', '紅外'])('reads %s descriptions without losing the model or TX/RX group', label => {
    const source = sheet()
    source.rows[0] = [`产品名称:迷你腊肠狗 产品编号：88052-${label} TX 客户：华兴 报价日期：2026/10/24`]
    source.rows[4] = [`產品編號：88052-${label} RX 客戶：华兴`]
    expect(readYinhuiElectronicSources([source]).map(g => [g.model, g.role])).toEqual([['88052', 'TX'], ['88052', 'RX']])
    const input = parents().reverse()
    const result = splitYinhuiLegacyElectronics(input, [source], main, '88052')
    expect(result.map(r => r.source)).toEqual(['明细!D2', '電子 報價!E7', '電子 報價!E8', '明细!D1', '電子 報價!E3'])
    expect(result.slice(0, 3).reduce((sum, r) => sum + r.amountHkd, 0)).toBeCloseTo(input[0]!.amountHkd, 12)
    expect(result.slice(3).reduce((sum, r) => sum + r.amountHkd, 0)).toBeCloseTo(input[1]!.amountHkd, 12)
  })
  it.each(['88052-A-红外 TX', '880520-红外 TX', '88052-改版 TX', '88052-红外 TX/RX', '88052-红外 TX2', '88052-红外'])('does not discard conflicting or ambiguous identity %s', identity => {
    const source = sheet()
    source.rows[0] = [`产品编号：${identity} 客户：华兴`]
    expect(() => splitYinhuiLegacyElectronics(parents(), [source], main, '88052')).toThrow(/型号|唯一/)
  })
  it('keeps real model suffixes and excludes roles in other title fields', () => {
    const source = sheet()
    source.rows[0] = ['产品名称:RX 测试 产品编号：88052-A-红外 TX 客户：RX 报价日期：2026/10/24']
    expect(readYinhuiElectronicSources([source])[0]).toMatchObject({ model: '88052-A', role: 'TX' })
    source.rows[0] = ['产品编号：88052 客户：TX']
    expect(readYinhuiElectronicSources([source])[0]).toMatchObject({ model: '88052', role: '' })
  })
  it('loads electronic source rows beyond the discovery preview', () => {
    const source = sheet()
    source.rows.splice(2, 0, ...Array.from({ length: 90 }, () => []))
    const bytes = createXlsxWorkbook([source])
    const parsed = readYinhuiSource(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer)
    expect(readYinhuiElectronicSources(parsed.sheets)[0]!.chips[0]!.source).toBe('電子 報價!E93')
  })
  it('loads separate TX/RX quote tabs in full and matches their ICs to the correct BOM rows', () => {
    const rows = sheet().rows
    const tx = { name: '电子TX报价', rows: rows.slice(0, 4) }
    const rx = { name: '電子（ｒｘ）報價', rows: [...rows.slice(4, 6), ...Array.from({ length: 80 }, () => []), ...rows.slice(6)] }
    const bytes = createXlsxWorkbook([rx, { ...tx, name: 'USB报价' }, tx])
    const parsed = readYinhuiSource(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer)
    const result = splitYinhuiLegacyElectronics(parents(), parsed.sheets, main, '88052')
    expect(result.map(row => row.source)).toEqual([
      '明细!D1', '电子TX报价!E3', '明细!D2', '電子（ｒｘ）報價!E83', '電子（ｒｘ）報價!E84',
    ])
  })
  describe('RFID controller and TAG card quotations', () => {
    const quote = (product: string, model: string): XlsxParsedSheet => ({
      name: '电子报价', cellFillIds: [], rows: [
        [`产品名称：${product}  产品编号：${model}  客户：银辉`],
        ['零件名称', '规格', '用量', '单价HKD', '合计HKD'],
        ['IC', `IC,${product}`, 1, .5, .5],
      ],
    })
    const input = [
      { description: '电子（RFID指令器)', quantity: 1, internalHkd: 2, amountHkd: 3, source: 'main!D64' },
      { description: '卡牌*26pcs', quantity: 26, internalHkd: 20, amountHkd: 26, source: 'main!D65' },
    ]
    const controller = quote('RFID指令器', '87768')
    const cards = () => quote('TAG小卡片（单个）', '87768-TAG')
    it('uses the component identities regardless of tab and BOM order', () => {
      const grouped = splitYinhuiLegacyElectronics([...input].reverse(), [controller, cards()], main, '87768')
      expect(grouped.map(row => [row.description, row.quantity])).toEqual([
        ['卡牌*26pcs', 26], ['IC,TAG小卡片(单个)', 26], ['电子（RFID指令器)', 1], ['IC,RFID指令器', 1],
      ])
      expect(grouped[0]!.amountHkd + grouped[1]!.amountHkd).toBeCloseTo(26, 10)
      expect(grouped[2]!.amountHkd + grouped[3]!.amountHkd).toBeCloseTo(3, 10)
      expect(splitYinhuiLegacyElectronics(input, [cards(), controller], main, '87768').map(r => r.description))
        .toEqual([input[0]!.description, 'IC,RFID指令器', input[1]!.description, 'IC,TAG小卡片(单个)'])
    })
    it('reopens a temporary card grouping label while keeping the original supplier model authoritative', () => {
      const source = cards()
      source.rows[1]!.push('备注', '仅用于导入分组的产品编号：87768-RX')
      const legacyRows = [input[0]!, { ...input[1]!, description: '卡牌〔导入分组 RX〕*26pcs' }]
      expect(splitYinhuiLegacyElectronics(legacyRows, [source, controller], main, '87768')[3]!.quantity).toBe(26)
      source.rows[0] = ['产品名称：TAG小卡片（单个） 产品编号：87769-TAG']
      expect(() => splitYinhuiLegacyElectronics(legacyRows, [source, controller], main, '87768')).toThrow(/型号/)
      source.rows[0] = ['产品名称：TAG小卡片（单个） 产品编号： 客户：银辉']
      expect(() => splitYinhuiLegacyElectronics(legacyRows, [source, controller], main, '87768')).toThrow(/型号/)
    })
    it.each(['877680-TAG', '87768-A-TAG', '87768-TAG2', '87768-TAG-X'])('preserves the full identity of %s', model => {
      expect(() => splitYinhuiLegacyElectronics(input, [quote('TAG小卡片（单个）', model)], main, '87768')).toThrow(/型号/)
    })
    it('preserves an exact standalone TAG SKU and rejects contradictory, missing or duplicate component evidence', () => {
      const generic = { ...input[1]!, description: '电子总成' }
      expect(splitYinhuiLegacyElectronics([generic], [cards()], main, '87768-TAG')).toHaveLength(2)
      expect(() => splitYinhuiLegacyElectronics([generic], [cards()], main, '87768')).toThrow(/唯一/)
      expect(() => splitYinhuiLegacyElectronics([input[0]!], [cards()], main, '87768')).toThrow(/唯一/)
      expect(() => splitYinhuiLegacyElectronics([input[0]!], [quote('通用电子', '87768')], main, '87768')).toThrow(/唯一/)
      expect(() => splitYinhuiLegacyElectronics([...input, input[1]!], [cards()], main, '87768')).toThrow(/唯一/)
      expect(() => splitYinhuiLegacyElectronics(input, [cards(), cards()], main, '87768')).toThrow(/唯一/)
    })
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

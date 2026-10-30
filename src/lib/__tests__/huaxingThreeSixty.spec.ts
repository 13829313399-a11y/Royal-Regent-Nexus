import { describe, expect, it } from 'vitest'
import { readFileSync, writeFileSync } from 'node:fs'
import { strFromU8, unzipSync } from 'fflate'
import { parseXlsxWorkbook } from '../customerPriceConverters/xlsxLite'
import { calculateHuaxing360, convertHuaxing360InternalQuote, huaxing360Problems, selectHuaxing360Route, validateHuaxing360Export } from '../customerPriceConverters/huaxingThreeSixty'
import { createHuaxing360Workbook } from '../customerPriceConverters/huaxingThreeSixtyWorkbook'

import { huaxing360TestPricing as pricing, huaxing360TestSource as fixture, huaxing360TestReady as ready } from './fixtures/huaxing360Source'

describe('Huaxing 360 independent temporary route', () => {
  it('blocks drafts imported under a previous mapping after a live update', () => {
    const result = ready(convertHuaxing360InternalQuote(fixture(), 'internal.xlsx', pricing()))
    result.mappingVersion = 'previous'
    expect(() => createHuaxing360Workbook(result)).toThrow('报客映射已更新，请重新导入内部报价')
  })
  it('uses original costs once and freezes a distinct factory/customer profile', () => {
    const settings = pricing(); const result = ready(convertHuaxing360InternalQuote(fixture(), 'internal.xlsx', settings))
    expect(calculateHuaxing360(result).plastic[0]?.totalUsd).toBeCloseTo(.155, 10)
    const before = calculateHuaxing360(result).finalUsd
    settings.materials[0]!.price = 999; settings.rates.hkd_usd = 9; settings.rates.testing_allocation_qty = 1
    expect(calculateHuaxing360(result).finalUsd).toBe(before)
    expect(() => convertHuaxing360InternalQuote(fixture(), 'wrong.xlsx', { ...pricing(), factory_id: 'huakang-a' })).toThrow('厂区不一致')
    expect(() => convertHuaxing360InternalQuote(fixture(), 'wrong.xlsx', { ...pricing(), customer_id: 'three-sixty' })).toThrow('厂区不一致')
  })
  it('keeps missing amounts and unknown categories blocking until explicit review', () => {
    const r = ready(convertHuaxing360InternalQuote(fixture({ blank: true, unknown: true }), 'internal.xlsx', pricing()))
    expect(huaxing360Problems(r).join()).toContain('请选择费用类别')
    expect(huaxing360Problems(r).join()).toContain('明确输入0')
    expect(() => createHuaxing360Workbook(r)).toThrow()
    r.costs[0]!.category = 'purchase'; r.costs[1]!.amountHkd = 0
    expect(huaxing360Problems(r)).toEqual([])
    expect(r.costs[0]!.quantity).toBe(2)
    expect(calculateHuaxing360(r).costs[0]!.totalUsd).toBe(2)
  })
  it('rejects ambiguous sheets, P4 structures, missing cached amounts and prices', () => {
    expect(() => convertHuaxing360InternalQuote(fixture({ multiple: true }), 'a.xlsx', pricing())).toThrow('多张')
    expect(() => convertHuaxing360InternalQuote(fixture({ p4: true }), 'a.xlsx', pricing())).toThrow('内部报价台文件')
    const bad = ready(convertHuaxing360InternalQuote(fixture({ missingCache: true }), 'a.xlsx', pricing()))
    bad.costs[1]!.amountHkd = 0
    expect(() => validateHuaxing360Export(bad)).toThrow('公式无缓存')
    const settings = pricing(); settings.materials = settings.materials.filter(p => p.material !== 'PP')
    expect(huaxing360Problems(convertHuaxing360InternalQuote(fixture(), 'a.xlsx', settings)).join()).toContain('缺少 USD/kg 料价：PP')
  })
  it('uses independent fee allocation and validates optional metadata', () => {
    const r = ready(convertHuaxing360InternalQuote(fixture(), 'a.xlsx', pricing()))
    expect(calculateHuaxing360(r).fees[0]?.perUnitUsd).toBe(.1)
    expect(r.review.fees[0]?.sourceAllocation).toBe(50000)
    selectHuaxing360Route(r, '6'); expect(r.review.confirmed).toBe(false)
    expect(calculateHuaxing360(r).fees[0]?.perUnitUsd).toBe(.1)
    r.review.quoteDate = '2026-02-31'; r.review.toolingCount = -1; r.review.quantityPerContainer = 0
    expect(huaxing360Problems(r)).toEqual(expect.arrayContaining(['请填写有效报价日期', '模具数量须为非负整数或留空', '每柜数量须为正整数或留空']))
  })
  it('maps updated purchased, PCB and labor sections without inventing customer-sample costs', () => {
    const source = fixture({ costs: [
      { category: '马达', description: '前马达' }, { category: '电池', description: '锂电池' }, { category: '油漆', description: '油漆' },
      { category: '吸塑', description: 'USB吸塑及AA电池吸塑' }, { category: '利宝', description: '车面利宝' },
      { category: '利宝', description: '纸箱利宝' }, { category: '其他外购', description: '说明书' },
      { category: '电子', description: 'TX发射线路板' }, { category: '电子', description: 'RX接收线路板' },
      { category: '移印工', description: '车身移印人工' }, { category: '喷油工', description: '车轮喷油人工' },
    ] })
    const result = ready(convertHuaxing360InternalQuote(source, 'internal.xlsx', pricing()))
    expect(result.issues).toEqual([])
    expect(result.costs.map(c => c.category)).toEqual(['purchase', 'purchase', 'purchase', 'purchase', 'purchase', 'packaging', 'packaging', 'electronic', 'electronic', 'labor', 'labor', 'labor'])
    const sheet = parseXlsxWorkbook(createHuaxing360Workbook(result).buffer as ArrayBuffer, { includeFormulas: true }).sheets[0]!
    expect(sheet.rows[116]?.[1]).toBe('RX接收线路板')
    expect(sheet.rows[144]?.[1]).toBe('TX发射线路板')
    expect(sheet.rows[199]?.[1]).toBe('车身移印人工')
    expect(sheet.rows[202]?.[1]).toBe('车轮喷油人工')
    expect(sheet.rows[210]?.[1]).toBe('包装人工')
    for (const r of [117, 145, 200, 203]) expect(sheet.rows[r - 1]?.[15]).toBe(2)
    expect(sheet.rows[18]?.[14]).toBeCloseTo(calculateHuaxing360(result).finalUsd, 10)
    expect(sheet.rows.flat()).not.toContain('2.4G IC(SOP16)AD')
  })
  it('uses explicit source piece counts without treating dimensions or prices as quantities', () => {
    const result = ready(convertHuaxing360InternalQuote(fixture({ costs: [
      { category: '纸箱', description: '防割板2PCS(8*3寸）' },
      { category: '电池', description: '電池（手制兩粒）' },
      { category: '电池', description: '380mAH 锂电 3.7V(1PCS)' },
      { category: '纸箱', description: '纸箱（8*3寸）' },
      { category: '五金', description: '螺丝 (4PCS)' }, // Explicit E=2 wins over conflicting text.
    ] }), 'internal.xlsx', pricing()))
    expect(result.costs.slice(0, 5).map(c => c.quantity)).toEqual([2, 2, 1, 1, 2])
    expect(calculateHuaxing360(result).costs.slice(0, 5).map(c => c.totalUsd)).toEqual([2, 2, 2, 2, 2])
  })
  it('expands plastic and purchased sections, preserves formulas/caches and exports no private/source tables or stale sample', () => {
    const r = ready(convertHuaxing360InternalQuote(fixture({ plastic: 35, purchase: 35 }), 'a.xlsx', pricing()))
    const first = createHuaxing360Workbook(r); const second = createHuaxing360Workbook(r)
    const workbook = parseXlsxWorkbook(first.buffer as ArrayBuffer, { includeFormulas: true })
    expect(workbook.sheets.map(s => s.name)).toEqual(['Breakdown'])
    const s = workbook.sheets[0]!
    expect(s.rows[40]?.[11]).toBeCloseTo(calculateHuaxing360(r).finalUsd, 10)
    expect(s.rows[43]?.[11]).toBe('NIL') // Original customer formula for zero tooling cost.
    expect(s.cellFormulas?.L44).toBe('IF(SUM(L43:M43)=0,"NIL",SUM(L39,L40,L43))')
    expect(parseXlsxWorkbook(second.buffer as ArrayBuffer).sheets[0]?.rows[43]?.[11]).toBe(s.rows[43]?.[11])
    expect(s.rows.flat().filter(v => typeof v === 'string' && /^外壳/.test(v))).toHaveLength(35)
    expect(s.rows.flat().filter(v => typeof v === 'string' && /^螺丝/.test(v))).toHaveLength(35)
    expect(s.cellFormulas?.L35).toBe('L34*M35')
    const zip = unzipSync(first); const all = Object.values(zip).map(bytes => strFromU8(bytes)).join('')
    expect(all).toContain('frozen-huaxing-360'); expect(all).not.toContain('ABS GP22=ABS'); expect(all).not.toContain('Wong Kin On'); expect(all).not.toContain('Polaris'); expect(all).not.toContain('#REF!'); expect(Object.keys(zip).some(k => /externalLink|comments|sharedStrings/.test(k))).toBe(false)
  })
})

const localFile = process.env.HUAXING_360_SOURCE
describe.skipIf(!localFile)('provided Polaris source acceptance (local only)', () => {
  it('matches independently calculated raw-cost golden and generates a review output', () => {
    const r = convertHuaxing360InternalQuote(Uint8Array.from(readFileSync(localFile!)).buffer, 'Polaris内部.xlsx', pricing())
    expect(r.issues).toEqual([]); expect(r.plastic).toHaveLength(25)
    expect(r.plastic.reduce((sum, p) => sum + p.weightG, 0)).toBeCloseTo(625.87, 8)
    expect(r.plastic.filter(p => /输出牙|左套件|包装扣|马达盖/.test(p.description)).map(p => p.weightG)).toEqual([6.02, 3.5, 5, 1])
    expect(r.plastic.filter(p => ['扇牙', '后双联牙'].includes(p.description)).map(p => p.weightG)).toEqual([.85, .85])
    expect(r.costs.filter(c => c.amountHkd === null).map(c => c.source)).toEqual(['D41', 'D74'])
    ready(r); r.costs.filter(c => c.amountHkd === null).forEach(c => { c.amountHkd = 0 })
    const c = calculateHuaxing360(r)
    expect(c.plastic.reduce((a, p) => a + p.totalUsd, 0)).toBeCloseTo(1.51763534, 10)
    expect(c.materialUsd).toBeCloseTo(5.542278053731296, 10); expect(c.laborUsd).toBeCloseTo(2.7534245009224896, 10)
    expect(c.exFactoryUsd).toBeCloseTo(9.457100912305316, 10); expect(c.finalUsd).toBeCloseTo(10.332559144205353, 10)
    expect(r.costs.find(c => c.source === 'D79')?.amountHkd).not.toBe(r.costs.find(c => c.source === 'D80')?.amountHkd)
    expect(r.costs.find(c => c.source === 'D80')?.quantity).toBe(2)
    expect(r.costs.find(c => c.source === 'D76')?.quantity).toBe(2)
    const bytes = createHuaxing360Workbook(r)
    const zip = unzipSync(bytes)
    expect(Object.keys(zip).filter(path => path.startsWith('xl/media/'))).toEqual(['xl/media/logo.png', 'xl/media/product.png'])
    expect(zip['xl/media/product.png']).toEqual(r.image?.bytes)
    expect([r.image?.width, r.image?.height]).toEqual([361, 263])
    const picture = new DOMParser().parseFromString(strFromU8(zip['xl/drawings/drawing1.xml']!), 'application/xml').getElementsByTagNameNS('*', 'oneCellAnchor')[0]!
    const extent = picture.getElementsByTagNameNS('*', 'ext')[0]!
    expect(Number(extent.getAttribute('cx')) / Number(extent.getAttribute('cy'))).toBeCloseTo(361 / 263, 5)
    expect(Number(extent.getAttribute('cy'))).toBe(1457325)
    const output = parseXlsxWorkbook(bytes.buffer as ArrayBuffer, { includeFormulas: true }).sheets[0]!
    expect(output.rows[39]?.[8]).toBe(100000)
    expect(output.rows[21]?.[14]).toBeCloseTo(c.finalUsd, 10)
    expect(output.rows[18]?.[14]).toBeCloseTo(c.finalUsd - .18, 10)
    expect(output.cellFormulas?.L40).toBe('E40/I40')
    expect(output.cellFormulas?.L41).toBe('E41/I41')
    expect(output.cellFormulas?.O19).toBe('L42')
    expect(output.cellFormulas?.O22).toBe('L45')
    expect(c.fees.map(fee => fee.perUnitUsd)).toEqual([.18, 11000 / 150000, .1])
    expect(output.rows[91 + 1]?.[9]).toBeCloseTo(625.87, 8) // Added fee row shifts plastic total from 92 to 93.
    for (const p of c.plastic) {
      const row = output.rows.findIndex(row => row[1] === p.description) + 1
      expect(output.rows[row - 1]?.[8]).toBe(p.weightG)
      expect(output.cellFormulas?.[`J${row}`]).toBe(`I${row}`)
    }
    expect(output.rows.flat().join(' ')).not.toMatch(/不含模具费|does not include tooling|150,000可退|2\.4G IC/)
    const serviceCardIndex = output.rows.findIndex(row => row[1] === '橙色服务卡')
    expect(output.cellFormulas?.[`P${serviceCardIndex + 1}`]).toBe(`L${serviceCardIndex + 1}*O${serviceCardIndex + 1}`)
    const carton = output.rows.find(row => row[1] === r.costs.find(cost => cost.source === 'D79')?.description)!
    expect([carton[6], carton[8], carton[9]]).toEqual(r.carton.dimensions)
    expect(carton[10]).toBe(r.carton.quantity)
    for (const cost of c.costs) expect(output.rows.flat().filter(value => value === cost.description)).toHaveLength(1)
    if (process.env.HUAXING_360_OUTPUT) writeFileSync(process.env.HUAXING_360_OUTPUT, bytes)
  }, 15000)
})

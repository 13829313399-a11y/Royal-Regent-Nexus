import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { createYinhuiDraft, correctYinhuiDraft, loadYinhuiDraft, saveYinhuiDraft, selectYinhuiToolCandidate, setYinhuiDraftMoq } from '../customerPriceConverters/yinhuiDraft'
import { parseYinhuiMoq, validateYinhuiExport, yinhuiTotals } from '../customerPriceConverters/yinhui'
import { createYinhuiCustomerQuoteWorkbook } from '../customerPriceConverters/yinhuiTemplate'
import { draftSource } from './fixtures/yinhuiDraftSource'
import { createXlsxWorkbook, parseXlsxWorkbook } from '../customerPriceConverters/xlsxLite'

describe('Silverlit draft import', () => {
  it('reopens older translated drafts with source Chinese and preserves new reviewed names', () => {
    const parsed = parseXlsxWorkbook(draftSource(false))
    parsed.sheets[0]!.rows[17]![2] = '螺丝 Φ2.0x6PB 黑色（2PCS）'
    const bytes = createXlsxWorkbook(parsed.sheets)
    const draft = createYinhuiDraft(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), '银辉81209.xlsx')
    const totals = yinhuiTotals(draft.result.quoteData)
    const saved = JSON.parse(saveYinhuiDraft(draft))
    delete saved.bomLanguage
    saved.review.names.mechanical[0].description = 'Screw Φ2.0x6PB Black (2PCS)'
    const restored = loadYinhuiDraft(JSON.stringify(saved))
    expect(restored.result.quoteData.mechanical[0]?.description).toBe('螺丝 Φ2.0x6PB 黑色（2PCS）')
    expect(yinhuiTotals(restored.result.quoteData)).toEqual(totals)
    restored.result.quoteData.mechanical[0]!.description = '螺丝 Φ2.0x6PB 黑色（2PCS）已核对'
    const reopened = loadYinhuiDraft(saveYinhuiDraft(restored))
    expect(reopened.result.quoteData.mechanical[0]?.description).toBe(restored.result.quoteData.mechanical[0]?.description)
    expect(yinhuiTotals(reopened.result.quoteData)).toEqual(totals)
    expect(new Uint8Array(reopened.buffer)).toEqual(bytes)
  })
  it.each([['5K', 5000], ['5 k pcs', 5000], ['5,000', 5000], ['２万件', 20000], ['2.5千', 2500], [5000, 5000]])('reads MOQ %s', (input, expected) => expect(parseYinhuiMoq(input)).toBe(expected))
  it.each(['', '5-10K', '5,00', '-5K', '0', '1.2', 'NaN', '#VALUE!', true])('does not guess ambiguous MOQ %s', value => expect(() => parseYinhuiMoq(value)).toThrow())
  it('collects independent errors, keeps known data and blocks direct export even with acknowledgement', () => {
    const draft = createYinhuiDraft(draftSource(), '银辉81209.xlsx')
    expect(draft.result.quoteData.importIssues).toHaveLength(3)
    expect(draft.result.quoteData.importIssues?.map(i => i.source)).toEqual(expect.arrayContaining(['明细 · MOQ', '明细!D18', '明细!D19']))
    expect(draft.result.quoteData.tools[0]?.weightG).toBe(9.12)
    expect(draft.result.sheets[0]?.name).toContain('草稿')
    expect(() => validateYinhuiExport(draft.result.quoteData)).toThrow()
    const bytes = readFileSync('public/templates/yinhui-customer-quote-template.bin')
    expect(() => createYinhuiCustomerQuoteWorkbook(draft.result, bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), { missingMaterialPricesConfirmed: true })).toThrow()
  })
  it('applies confirmed source readings, recalculates and retains originals across save/reopen', () => {
    const original = draftSource()
    const draft = createYinhuiDraft(original, '银辉81209.xlsx')
    const fixed = correctYinhuiDraft(draft, [{ sheet: '明细', cell: 'L19', value: '5K' }, { sheet: '明细', cell: 'D18', value: 1 }, { sheet: '明细', cell: 'E19', value: 2.2 }])
    expect(fixed.result.quoteData.importIssues).toHaveLength(0)
    expect(fixed.result.quoteData.moq).toBe(5000)
    expect(fixed.result.quoteData.mechanical[0]?.amountHkd).toBe(1.1)
    fixed.result.quoteData.tools[0]!.description = 'Cover'
    fixed.result.quoteData.stage = 'Reviewed'
    const restored = loadYinhuiDraft(saveYinhuiDraft(fixed))
    expect(restored.result.quoteData.stage).toBe('Reviewed')
    expect(restored.result.quoteData.importIssues).toHaveLength(0)
    expect(yinhuiTotals(restored.result.quoteData)).toEqual(yinhuiTotals(fixed.result.quoteData))
    expect(new Uint8Array(restored.buffer)).toEqual(new Uint8Array(original))
    expect(draft.result.quoteData.importIssues).toHaveLength(3)
  })
  it('retains unresolved issues after reopening and ignores invented saved totals and issue flags', () => {
    const saved = JSON.parse(saveYinhuiDraft(createYinhuiDraft(draftSource(), '银辉81209.xlsx')))
    saved.review.importIssues = []; saved.review.assemblyHkd = 999; saved.review.internalTotalHkd = 999
    const restored = loadYinhuiDraft(JSON.stringify(saved))
    expect(restored.result.quoteData.importIssues).toHaveLength(3)
    expect(restored.result.quoteData.assemblyHkd).toBe(0)
    expect(() => validateYinhuiExport(restored.result.quoteData)).toThrow()
    saved.customer = 'disney'
    expect(() => loadYinhuiDraft(JSON.stringify(saved))).toThrow(/华兴银辉/)
  })
  it('recognizes a late compact tool list and selecting identifiers does not alter costing', () => {
    const draft = createYinhuiDraft(draftSource(false), '银辉81209.xlsx')
    expect(draft.candidates).toEqual([{ source: 'TOOL PLAN!48', moldNo: 'NA123', partNo: '', description: 'Cover' }])
    const before = yinhuiTotals(draft.result.quoteData)
    selectYinhuiToolCandidate(draft, 0, 'TOOL PLAN!48')
    expect(draft.result.quoteData.tools[0]?.moldNo).toBe('NA123')
    expect(yinhuiTotals(draft.result.quoteData)).toEqual(before)
  })
  it('manual MOQ completion resolves only MOQ, never outstanding cost errors', () => {
    const draft = createYinhuiDraft(draftSource(), '银辉81209.xlsx')
    setYinhuiDraftMoq(draft.result, '2万')
    expect(draft.result.quoteData.moq).toBe(20000)
    expect(draft.result.quoteData.importIssues).toHaveLength(2)
    const restored = loadYinhuiDraft(saveYinhuiDraft(draft))
    expect(restored.result.quoteData.importIssues).toHaveLength(2)
    expect(restored.result.quoteData.moq).toBe(20000)
    expect(() => correctYinhuiDraft(draft, [{ sheet: '明细', cell: 'D20', value: 9 }])).toThrow(/只能补正/)
  })
  it.each(['', '料价'])('cannot omit a cost row by clearing or reclassifying it to %s', category => {
    const draft = createYinhuiDraft(draftSource(), '银辉81209.xlsx')
    const fixed = correctYinhuiDraft(draft, [{ sheet: '明细', cell: 'B18', value: category }, { sheet: '明细', cell: 'B19', value: category }, { sheet: '明细', cell: 'L19', value: 5000 }])
    expect(fixed.result.quoteData.importIssues?.some(i => i.message.includes('不能清空'))).toBe(true)
    expect(() => validateYinhuiExport(fixed.result.quoteData)).toThrow()
  })
  it('does not disable a quoted-price cross-check when its value is cleared or changed to match internal cost', () => {
    const draft = createYinhuiDraft(draftSource(), '银辉81209.xlsx')
    for (const changes of [[{ sheet: '明细', cell: 'E19', value: '' }], [{ sheet: '明细', cell: 'D19', value: 8 }]]) {
      const fixed = correctYinhuiDraft(draft, changes)
      expect(fixed.result.quoteData.importIssues?.some(i => i.source === '明细!D19')).toBe(true)
    }
  })
  it('keeps a manually invalid MOQ pending across save/reopen, including uppercase extensions', () => {
    const draft = createYinhuiDraft(draftSource(false), '银辉81209.XLSX')
    setYinhuiDraftMoq(draft.result, '5-10K')
    const restored = loadYinhuiDraft(saveYinhuiDraft(draft))
    expect(restored.result.quoteData.moq).toBe(0)
    expect(() => validateYinhuiExport(restored.result.quoteData)).toThrow(/MOQ/)
  })
  it.each([null, '#VALUE!', -100, '100'])('preserves a mold-price row with value %s, requiring valid cost before export', price => {
    const parsed = parseXlsxWorkbook(draftSource(false))
    const bytes = createXlsxWorkbook([...parsed.sheets, { name: '模具报价', rows: [['81209'], ['', 'M1', 'Cover', null, null, null, null, null, null, price]] }])
    const draft = createYinhuiDraft(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), '银辉81209.xlsx')
    if (price === '100') expect(yinhuiTotals(draft.result.quoteData).tooling).toBe(100)
    else {
      expect(draft.result.quoteData.importIssues?.some(i => i.source === '模具报价!J2')).toBe(true)
      const fixed = correctYinhuiDraft(draft, [{ sheet: '模具报价', cell: 'J2', value: 100 }])
      expect(yinhuiTotals(fixed.result.quoteData).tooling).toBe(100)
      expect(fixed.result.quoteData.importIssues).toHaveLength(0)
    }
  })
  it('cannot clear the only available molding cost while correcting material', () => {
    const parsed = parseXlsxWorkbook(draftSource(false))
    parsed.sheets[0]!.rows[8]![3] = '#VALUE!'
    parsed.sheets[0]!.rows[8]![9] = null
    parsed.sheets[0]!.rows[8]![11] = 1.1
    const bytes = createXlsxWorkbook(parsed.sheets)
    const draft = createYinhuiDraft(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), '银辉81209.xlsx')
    const fixed = correctYinhuiDraft(draft, [{ sheet: '明细', cell: 'D9', value: 'ABS' }, { sheet: '明细', cell: 'L9', value: '' }])
    expect(fixed.result.quoteData.importIssues?.some(i => i.message.includes('有效的报客啤工'))).toBe(true)
    expect(() => validateYinhuiExport(fixed.result.quoteData)).toThrow()
  })
})

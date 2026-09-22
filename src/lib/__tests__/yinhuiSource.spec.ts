import { describe, expect, it } from 'vitest'
import { draftSource } from './fixtures/yinhuiDraftSource'
import { createXlsxWorkbook, parseXlsxWorkbook, type XlsxParsedSheet } from '../customerPriceConverters/xlsxLite'
import { createYinhuiDraft, correctYinhuiDraft, loadYinhuiDraft, saveYinhuiDraft } from '../customerPriceConverters/yinhuiDraft'
import { buildYinhuiRecognitionTasks } from '../customerPriceConverters/yinhuiRecognition'
import { validateYinhuiExport, yinhuiTotals } from '../customerPriceConverters/yinhui'

function source(change: (sheets: XlsxParsedSheet[]) => void, broken = false) {
  const sheets = parseXlsxWorkbook(draftSource(broken)).sheets
  change(sheets)
  const bytes = createXlsxWorkbook(sheets)
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
}
describe('Silverlit source discovery', () => {
  it.each(['明细 ', '　內部明細＋', '明细（不含AAA）', '内部报价 2026版'])('finds %s without changing source names, costs or AI lineage', name => {
    const data = source(sheets => { sheets[0]!.name = name; sheets[1]!.name = 'TOOL  PLAN +' })
    const draft = createYinhuiDraft(data, '银辉81209.xlsx')
    expect(yinhuiTotals(draft.result.quoteData)).toEqual(yinhuiTotals(createYinhuiDraft(draftSource(false), '银辉81209.xlsx').result.quoteData))
    expect(draft.candidates[0]?.source).toBe('TOOL  PLAN +!48')
    const task = buildYinhuiRecognitionTasks(draft).tasks.find(t => t.kind === 'tool_match')!
    expect(task.source.sheet).toBe(name)
    expect(task.choices[0]?.evidence[0]?.sheet).toBe('TOOL  PLAN +')
    expect(new Uint8Array(loadYinhuiDraft(saveYinhuiDraft(draft)).buffer)).toEqual(new Uint8Array(data))
  })
  it('discovers unnamed-layout sheets from header content and accepts benign header formatting', () => {
    const draft = createYinhuiDraft(source(sheets => {
      sheets[0]!.name = '86889 核价记录'
      sheets[0]!.rows[7]![2] = ' 名\n称 '
      sheets[0]!.rows[7]![3] = ' 膠料 '
      sheets[0]!.rows[7]![4] = '料重（Ｇ）'
      sheets[1]!.name = '最新模组资料'
    }), '银辉.xlsx')
    expect(draft.result.quoteData.moq).toBe(5000)
    expect(draft.candidates[0]?.source).toBe('最新模组资料!48')
  })
  it('retains original spaced names when correcting costs and reopening a saved draft', () => {
    const original = source(sheets => { sheets[0]!.name = '明细 '; sheets[1]!.name = 'TOOL  PLAN +' }, true)
    const draft = createYinhuiDraft(original, '银辉81209.xlsx')
    const fixed = correctYinhuiDraft(draft, [{sheet:'明细 ',cell:'D18',value:1},{sheet:'明细 ',cell:'E19',value:2.2},{sheet:'明细 ',cell:'L19',value:5000}])
    const restored = loadYinhuiDraft(saveYinhuiDraft(fixed))
    expect(restored.result.quoteData.importIssues).toHaveLength(0)
    expect(restored.overrides.every(o => o.sheet === '明细 ')).toBe(true)
    expect(restored.result.quoteData.mechanical[0]?.source).toBe('明细 !D18')
    expect(yinhuiTotals(restored.result.quoteData)).toEqual(yinhuiTotals(fixed.result.quoteData))
  })
  it('reports all competing main sheets instead of choosing the exact name or first sheet', () => {
    const data = source(sheets => { sheets.push({...structuredClone(sheets[0]!),name:'核价副本'}) })
    expect(() => createYinhuiDraft(data,'银辉.xlsx')).toThrow(/多张.*“明细”.*“核价副本”/)
  })
  it('rejects competing Tool Plans instead of silently combining costs', () => {
    const data = source(sheets => { sheets.push({...structuredClone(sheets[1]!),name:'Tool Plan（TX）'}) })
    expect(() => createYinhuiDraft(data,'银辉.xlsx')).toThrow(/多张.*Tool Plan/)
  })
  it('rejects competing normalized mold quotation sheets without omitting either cost', () => {
    const data = source(sheets => {
      sheets.push({name:'模具报价',rows:[['81209'],[null,'NA123','Cover',null,null,null,null,null,null,100]],cellFillIds:[]})
      sheets.push({name:'模具报价 +',rows:[['81209'],[null,'NA123','Cover',null,null,null,null,null,null,200]],cellFillIds:[]})
    })
    expect(() => createYinhuiDraft(data,'银辉.xlsx')).toThrow(/多张模具报价页.*“模具报价”.*“模具报价 \+”/)
  })
  it('does not use a similarly named supplier sheet as an internal quotation', () => {
    const data = source(sheets => { sheets[0]!.name = '对外报价单'; sheets[0]!.rows[14]![3] = '单价' })
    expect(() => createYinhuiDraft(data,'银辉.xlsx')).toThrow(/未找到内部明细/)
  })
  it('still requires a Silverlit customer identifier on the selected quote or filename', () => {
    const data = source(sheets => { sheets[0]!.rows[6]![0] = '#81209 Another Customer'; sheets[1]!.rows[0] = ['银辉历史备注'] })
    expect(() => createYinhuiDraft(data,'Other.xlsx')).toThrow(/客户标识/)
  })
  it('keeps monetary conflicts blocking export after fuzzy discovery', () => {
    const draft = createYinhuiDraft(source(sheets => { sheets[0]!.name = '明细 '; sheets[0]!.rows[8]![11] = 2 }), '银辉.xlsx')
    expect(draft.result.quoteData.importIssues?.some(i => i.message.includes('报客啤工'))).toBe(true)
    expect(() => validateYinhuiExport(draft.result.quoteData)).toThrow(/报客啤工/)
  })
  it('reads the wide Tool Plan by explicit HK mold and net-weight headers, ignoring gross weight', () => {
    const draft = createYinhuiDraft(source(sheets => {
      const rows: XlsxParsedSheet['rows'] = []
      rows[3] = ['大陸模號\nMold No.','HK模號\nMold No.','零件名稱\nDescription','物料編號\nPart No.','膠料\nMaterial',null,'出模數\nCavity','產品用量\nQty/Toy']
      rows[3]![17] = '單件重量\nNet(g)'; rows[3]![19] = '每啤膠重\nPlastic Wt(g)'
      rows[4] = ['NA123','HK123','Cover','P1','ABS',null,1,1]
      rows[4]![17] = 9.12; rows[4]![19] = 999
      sheets[1] = {name:'TOOL  PLAN +',rows,cellFillIds:[]}
    }), '银辉.xlsx')
    expect(draft.result.quoteData.tools).toMatchObject([{moldNo:'HK123',partNo:'P1',weightG:9.12,usage:1,cavity:1}])
    expect(draft.candidates[0]).toMatchObject({moldNo:'HK123',partNo:'P1',source:'TOOL  PLAN +!5'})
    expect(draft.result.manualReviewReasons).toHaveLength(0)
  })
  it('limits discovery reads without moving cell addresses or truncating normal reads', () => {
    const data = source(sheets => { sheets[0]!.rows[999] = ['last'] })
    const preview = parseXlsxWorkbook(data,{maxRows:80,valuesOnly:true})
    expect(preview.sheets[0]!.rows.length).toBeLessThanOrEqual(80)
    expect(preview.sheets[0]!.rows[7]?.[2]).toBe('名称')
    expect(parseXlsxWorkbook(data).sheets[0]!.rows[999]?.[0]).toBe('last')
  })
})

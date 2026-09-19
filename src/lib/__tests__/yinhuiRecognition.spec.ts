import { describe, expect, it } from 'vitest'
import { draftSource } from './fixtures/yinhuiDraftSource'
import { createYinhuiDraft, loadYinhuiDraft, saveYinhuiDraft } from '../customerPriceConverters/yinhuiDraft'
import { applyYinhuiRecognition, buildYinhuiRecognitionTasks, validateYinhuiRecognition } from '../customerPriceConverters/yinhuiRecognition'
import { createXlsxWorkbook, parseXlsxWorkbook } from '../customerPriceConverters/xlsxLite'

function changedSource(kind: 'header' | 'cost') {
  const sheets = parseXlsxWorkbook(draftSource(false)).sheets
  if (kind === 'header') sheets[1]!.rows[46] = ['Tool ID', '图片', '部件品名', '出模数', '模具材料', '产品材料']
  else { sheets[0]!.rows[17]![1] = '特殊采购'; sheets[0]!.rows[17]![2] = 'M3螺钉' }
  const bytes = createXlsxWorkbook(sheets)
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}
describe('Silverlit bounded AI choices', () => {
  it.each(['内部明细', '內部明細', '明细（开窗盒）'])('uses the authoritative main sheet for %s', name => {
    const sheets = parseXlsxWorkbook(draftSource(false)).sheets
    sheets[0]!.name = name
    if (name.includes('开窗盒')) {
      sheets[0]!.rows[6]![0] = '#89127 银辉'
      const sealed = structuredClone(sheets[0]!)
      sealed.name = '明细（密封盒）'
      sealed.rows[8]![2] = 'SEALED BOX ONLY'
      sheets.unshift(sealed)
    }
    const bytes = createXlsxWorkbook(sheets)
    const draft = createYinhuiDraft(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer, '银辉.xlsx')
    const tasks = buildYinhuiRecognitionTasks(draft).tasks.filter(t => t.kind === 'tool_match')
    expect(tasks).toHaveLength(1)
    expect(tasks[0]!.source.sheet).toBe(name)
    expect(JSON.stringify(tasks)).not.toContain('SEALED BOX ONLY')
  })
  it('sends names with cell evidence, applies only identifiers and preserves existing source errors', () => {
    const draft = createYinhuiDraft(draftSource(), '银辉81209.xlsx')
    const { tasks } = buildYinhuiRecognitionTasks(draft)
    const task = tasks.find(t => t.kind === 'tool_match')!
    expect(task.source).toEqual({ sheet: '明细', cell: 'C9', text: 'Cover' })
    expect(task.choices[0]!.evidence[0]!.cell).toBe('C48')
    expect(JSON.stringify(tasks)).not.toMatch(/9\.12|1\.1|amountHkd|laborHkd|weightG|D18|E19|L19/)
    const before = structuredClone(draft.result.quoteData)
    applyYinhuiRecognition(draft, task, { task_id: task.id, choice_id: task.choices[0]!.id, reason: '原表对应' })
    expect(draft.result.quoteData.tools[0]!.moldNo).toBe('NA123')
    before.tools[0]!.moldNo = 'NA123'
    expect(draft.result.quoteData).toEqual(before)
  })
  it('accepts a confirmed unfamiliar Tool Plan header, persists it, and retains costs', () => {
    const draft = createYinhuiDraft(changedSource('header'), '银辉81209.xlsx')
    expect(draft.candidates).toHaveLength(0)
    const task = buildYinhuiRecognitionTasks(draft).tasks.find(t => t.kind === 'header')!
    expect(task.choices.find(c => c.id === 'A47|C47')).toBeDefined()
    const next = applyYinhuiRecognition(draft, task, { task_id: task.id, choice_id: 'A47|C47', reason: 'Tool ID 对应模号，部件品名对应描述' })
    expect(next.result).toBe(draft.result)
    expect(next.candidates[0]!.moldNo).toBe('NA123')
    const loaded = loadYinhuiDraft(saveYinhuiDraft(next))
    expect(loaded.headerMappings).toEqual(next.headerMappings)
    expect(loaded.candidates).toEqual(next.candidates)
    expect(loaded.result.quoteData.tools).toEqual(draft.result.quoteData.tools)
    const saved = JSON.parse(saveYinhuiDraft(next))
    saved.headerMappings[0].descriptionCell = 'D18'
    expect(() => loadYinhuiDraft(JSON.stringify(saved))).toThrow('表头映射')
  })
  it('reclassifies only an unknown cost label, then reparses and verifies original amounts', () => {
    const draft = createYinhuiDraft(changedSource('cost'), '银辉81209.xlsx')
    const task = buildYinhuiRecognitionTasks(draft).tasks.find(t => t.kind === 'cost_category')!
    expect(task.source.cell).toBe('B18')
    expect(task.context[0]!.cell).toBe('C18')
    const next = applyYinhuiRecognition(draft, task, { task_id: task.id, choice_id: '五金', reason: '螺钉为五金' })
    expect(next.overrides).toEqual([{ sheet: '明细', cell: 'B18', value: '五金' }])
    expect(next.result.quoteData.mechanical[0]!.amountHkd).toBe(1.1)
    expect(next.result.quoteData.mechanical[0]!.internalHkd).toBe(1)
    expect(next.result.quoteData.importIssues).toHaveLength(0)
    expect(() => applyYinhuiRecognition(next, task, { task_id: task.id, choice_id: '五金', reason: '过期结果' })).toThrow('草稿已变化')
  })
  it('rejects invented, reordered and missing candidates and never applies a null suggestion', () => {
    const draft = createYinhuiDraft(draftSource(false), '银辉81209.xlsx')
    const task = buildYinhuiRecognitionTasks(draft).tasks.find(t => t.kind === 'tool_match')!
    for (const item of [{ task_id: task.id, choice_id: 'made-up', reason: '猜测' }, { task_id: 'other', choice_id: null, reason: '未知' }]) {
      expect(() => validateYinhuiRecognition({ items: [item], engine: '', model: '' }, [task])).toThrow()
    }
    expect(() => validateYinhuiRecognition({ items: [], engine: '', model: '' }, [task])).toThrow()
    expect(() => applyYinhuiRecognition(draft, task, { task_id: task.id, choice_id: null, reason: '有歧义' })).toThrow('没有可靠建议')
    expect(draft.result.quoteData.tools[0]!.moldNo).toBe('')
  })
})

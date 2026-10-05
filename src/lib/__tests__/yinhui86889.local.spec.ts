import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, it } from 'vitest'
import { createYinhuiDraft, loadYinhuiDraft, saveYinhuiDraft } from '../customerPriceConverters/yinhuiDraft'
import { buildYinhuiRecognitionTasks } from '../customerPriceConverters/yinhuiRecognition'
import { validateYinhuiExport, yinhuiTotals } from '../customerPriceConverters/yinhui'

const directory = process.env.YINHUI_DRAFT_SAMPLE_DIR
it.skipIf(!directory)('imports the original 86889 spaced/suffixed sheets into a traceable draft and retains monetary conflicts', () => {
  const name = '银辉 86889 对战恐龙报价明细(不含AAA).xlsx'
  const original = readFileSync(join(directory!, name))
  const draft = createYinhuiDraft(original.buffer.slice(original.byteOffset, original.byteOffset + original.byteLength), name)
  expect(draft.result.quoteData).toMatchObject({model:'86889',moq:50000})
  expect(draft.candidates.length).toBeGreaterThan(20)
  expect(draft.candidates[0]).toMatchObject({source:'TOOL  PLAN +!5',moldNo:'TS868890100',description:'透明罩'})
  expect(draft.result.manualReviewReasons?.join(' ')).not.toContain('未识别到完整的零件号')
  expect(draft.result.quoteData.importIssues?.filter(i => i.message.includes('报客啤工')).map(i => i.source)).toEqual([18,19,20,21,22].map(row => `明细 !C${row}:L${row}`))
  expect(() => validateYinhuiExport(draft.result.quoteData)).toThrow(/报客啤工/)
  const tasks = buildYinhuiRecognitionTasks(draft).tasks.filter(t => t.kind === 'tool_match')
  expect(tasks.length).toBeGreaterThan(0)
  expect(tasks.every(t => t.source.sheet === '明细 ' && t.choices.every(c => c.evidence.every(e => e.sheet === 'TOOL  PLAN +')))).toBe(true)
  expect(JSON.stringify(tasks)).not.toMatch(/amountHkd|weightG|laborHkd|internalHkd/)
  const restored = loadYinhuiDraft(saveYinhuiDraft(draft))
  expect(restored.result.quoteData.importIssues).toEqual(draft.result.quoteData.importIssues)
  expect(yinhuiTotals(restored.result.quoteData)).toEqual(yinhuiTotals(draft.result.quoteData))
  expect(Buffer.from(restored.buffer).equals(original)).toBe(true)
  expect(readFileSync(join(directory!, name)).equals(original)).toBe(true)
}, 120000)

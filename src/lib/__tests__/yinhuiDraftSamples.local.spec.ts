import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, it } from 'vitest'
import { convertYinhuiInternalQuote, yinhuiTotals } from '../customerPriceConverters/yinhui'
import { createYinhuiDraft } from '../customerPriceConverters/yinhuiDraft'
import { createYinhuiCustomerQuoteWorkbook } from '../customerPriceConverters/yinhuiTemplate'
import { parseXlsxWorkbook } from '../customerPriceConverters/xlsxLite'
import { buildYinhuiRecognitionTasks } from '../customerPriceConverters/yinhuiRecognition'

const directory = process.env.YINHUI_DRAFT_SAMPLE_DIR
it.skipIf(!directory)('imports the two September source workbooks into review without changing their files', () => {
  const report = []
  for (const name of ['银辉81282报价明细20260910.xlsx', '银辉81209报价明细20260904.xlsx']) {
    const original = readFileSync(join(directory!, name))
    const result = convertYinhuiInternalQuote(original.buffer.slice(original.byteOffset, original.byteOffset + original.byteLength), name, { draft: true })
    report.push({ name, moq: result.quoteData.moq, issues: result.quoteData.importIssues, review: result.manualReviewReasons, totals: yinhuiTotals(result.quoteData), tools: result.quoteData.tools })
    expect(result.quoteData.moq).toBe(name.includes('81282') ? 5000 : 20000)
    expect(result.quoteData.tools.length).toBeGreaterThan(0)
    expect(result.quoteData.tools.reduce((n, t) => n + t.weightG, 0)).toBeCloseTo(name.includes('81282') ? 395.84 : 63.74, 6)
    expect(yinhuiTotals(result.quoteData).injection).toBeCloseTo((name.includes('81282') ? 3.09777398459384 : 1.23) * 1.1 / .96, 6)
    const draft = createYinhuiDraft(original.buffer.slice(original.byteOffset, original.byteOffset + original.byteLength), name)
    expect(draft.candidates.some(c => c.moldNo && c.description)).toBe(true)
    const recognition = buildYinhuiRecognitionTasks(draft)
    expect(recognition.tasks.filter(t => t.kind === 'tool_match').length).toBeGreaterThan(0)
    expect(JSON.stringify(recognition.tasks)).not.toMatch(/amountHkd|weightG|laborHkd|internalHkd|freight/)
    for (const task of recognition.tasks.filter(t => t.kind === 'tool_match')) {
      expect(task.source.cell).toMatch(/^C\d+$/)
      expect(task.choices.length).toBeLessThanOrEqual(80)
      expect(task.choices.every(c => c.evidence.length)).toBe(true)
    }
    // Supply English Tool Plan labels; export original Chinese BOM descriptions.
    const exportResult = structuredClone(result)
    exportResult.quoteData.productName = 'Test Product'
    for (const group of ['tools'] as const) {
      exportResult.quoteData[group]?.forEach((line, i) => { if (/[\u3400-\u9fff]/.test(line.description)) line.description = `Test Item ${i + 1}` })
    }
    const template = readFileSync('public/templates/yinhui-customer-quote-template.bin')
    const generated = createYinhuiCustomerQuoteWorkbook(exportResult, template.buffer.slice(template.byteOffset, template.byteOffset + template.byteLength), { missingMaterialPricesConfirmed: true })
    const output = parseXlsxWorkbook(generated.buffer.slice(generated.byteOffset, generated.byteOffset + generated.byteLength))
    const cells = output.sheets.flatMap(sheet => sheet.rows.flat())
    for (const group of ['plastic', 'mechanical', 'electronic', 'fabric', 'packagingRows'] as const) {
      for (const line of result.quoteData[group] || []) expect(cells).toContain(line.description)
    }
    expect(output.sheets[0]!.rows[31]![9]).toBeCloseTo(yinhuiTotals(result.quoteData).exFactory, 6)
    if (name.includes('81209')) expect(output.sheets[0]!.rows.flat().join(' ')).toContain('PRICE PENDING')
    expect(readFileSync(join(directory!, name))).toEqual(original)
  }
  if (process.env.YINHUI_DRAFT_REPORT) writeFileSync(process.env.YINHUI_DRAFT_REPORT, JSON.stringify(report, null, 2))
}, 120000)

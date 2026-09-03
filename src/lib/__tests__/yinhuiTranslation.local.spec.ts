import { createHash } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import { it, expect } from 'vitest'
import { convertYinhuiInternalQuote, validateYinhuiExport, yinhuiTotals } from '../customerPriceConverters/yinhui'
import { hasChineseQuoteText, pendingYinhuiDescriptions, translateYinhuiDescriptions, yinhuiDescriptionRows } from '../customerPriceConverters/yinhuiTranslation'
import { createYinhuiCustomerQuoteWorkbook } from '../customerPriceConverters/yinhuiTemplate'
import { YINHUI_PROFILES } from '../customerPriceConverters/yinhuiProfiles'
import { parseXlsxWorkbook } from '../customerPriceConverters/xlsxLite'

const source = process.env.YINHUI_TRANSLATION_SAMPLE
const output = process.env.YINHUI_TRANSLATION_OUTPUT
const translations = process.env.YINHUI_TRANSLATION_RESULTS
const buffer = (bytes: Uint8Array) => bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength) as ArrayBuffer
it.skipIf(!source || !output)('extracts only customer-facing Chinese names from the supplied quote for offline translation QA', () => {
  const data = convertYinhuiInternalQuote(buffer(readFileSync(source!)),source!).quoteData
  const texts = [...new Set([data.productName,data.packaging,...yinhuiDescriptionRows(data).map(row => row.description)].filter(hasChineseQuoteText))]
  writeFileSync(`${output}/translation-input.json`,JSON.stringify(texts,null,2))
  writeFileSync(`${output}/baseline.json`,JSON.stringify({model:data.model,totals:yinhuiTotals(data),count:texts.length},null,2))
  expect(texts.length).toBeGreaterThan(0)
})
it.skipIf(!source || !output || !translations)('validates actual offline translations and exports without changing costs, specs or the source file', async () => {
  const input = readFileSync(source!)
  const hash = createHash('sha256').update(input).digest('hex')
  const result = convertYinhuiInternalQuote(buffer(input),source!)
  const before = yinhuiTotals(result.quoteData)
  const numeric = () => JSON.stringify(yinhuiDescriptionRows(result.quoteData).map(({description:_d,originalDescription:_o,...rest})=>rest))
  const originalNumeric = numeric()
  const response = JSON.parse(readFileSync(translations!,'utf8'))
  await translateYinhuiDescriptions(result.quoteData,async texts => {
    expect(texts).toEqual(response.items.map((item: {source:string})=>item.source))
    return response
  })
  expect(pendingYinhuiDescriptions(result.quoteData)).toBe(0)
  expect(yinhuiTotals(result.quoteData)).toEqual(before)
  expect(numeric()).toBe(originalNumeric)
  validateYinhuiExport(result.quoteData)
  const template = buffer(readFileSync(`public/templates/${YINHUI_PROFILES[result.quoteData.templateId || 'standard'].file}`))
  const bytes = createYinhuiCustomerQuoteWorkbook(result,template,{missingMaterialPricesConfirmed:true})
  const parsed = parseXlsxWorkbook(buffer(bytes))
  expect(parsed.sheets[0]?.rows[31]?.[9]).toBeCloseTo(before.exFactory,6)
  expect(parsed.sheets[0]?.rows[5]?.[2]).toContain('PRICE PENDING')
  writeFileSync(`${output}/银辉89218-英文映射验收.xlsx`,bytes)
  writeFileSync(`${output}/verified.json`,JSON.stringify({model:result.quoteData.model,translated:response.items.length,remaining:pendingYinhuiDescriptions(result.quoteData),totals:before,sourceSha256:hash},null,2))
  expect(createHash('sha256').update(readFileSync(source!)).digest('hex')).toBe(hash)
},30000)

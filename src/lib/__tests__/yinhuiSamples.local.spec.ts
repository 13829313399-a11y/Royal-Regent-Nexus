import { readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { expect, it } from 'vitest'
import { convertYinhuiInternalQuote, validateYinhuiExport, yinhuiTotals } from '../customerPriceConverters/yinhui'
import { createYinhuiCustomerQuoteWorkbook, sanitizeYinhuiTemplate } from '../customerPriceConverters/yinhuiTemplate'
import { YINHUI_PROFILES } from '../customerPriceConverters/yinhuiProfiles'
import { parseXlsxWorkbook } from '../customerPriceConverters/xlsxLite'

const source = process.env.YINHUI_SAMPLE_DIR
const output = process.env.YINHUI_TEST_OUTPUT
function buffer(b: Uint8Array) { return b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength) as ArrayBuffer }
it.skipIf(!source || !output)('runs the locally supplied Silverlit workbooks without changing the originals', () => {
  const report: Array<Record<string,unknown>> = []
  const samples = readdirSync(source!).filter(n => n.startsWith('银辉') && n.endsWith('.xlsx'))
  expect(samples.length).toBeGreaterThan(0)
  const hash = (name: string) => createHash('sha256').update(readFileSync(`${source}/${name}`)).digest('hex')
  const sourceHashes = samples.map(hash)
  const baseline = new Map<string, unknown>()
  if (process.env.YINHUI_REFRESH_TEMPLATES === '1') {
    for (const [id, profile] of Object.entries(YINHUI_PROFILES)) {
      if (id === 'standard') continue
      const name = readdirSync(source!).find(n => n.startsWith('Breakdown') && (id === '89127' ? n.includes('MUSCLE CLASH') : id === '89275' ? n.includes('Kneading Kitten') : id === '89115' ? n.includes('Pee Pee Puppy') : n.includes(id)))
      if (!name) continue
      writeFileSync(`public/templates/${profile.file}`,sanitizeYinhuiTemplate(buffer(readFileSync(`${source}/${name}`))))
    }
  }
  for (const round of [1,2,3]) for (const name of round === 2 ? [...samples].reverse() : samples) {
    const entry: Record<string,unknown> = {file:name,round}
    try {
      const result = convertYinhuiInternalQuote(buffer(readFileSync(`${source}/${name}`)), name)
      if (round === 1) baseline.set(name,result.quoteData)
      else expect(result.quoteData).toEqual(baseline.get(name))
      const originalTotal = yinhuiTotals(result.quoteData).exFactory
      if (round === 3) result.quoteData.assemblyHkd += .125
      entry.data = result.quoteData; entry.warnings = result.warnings; entry.totals = yinhuiTotals(result.quoteData)
      if (result.quoteData.image) entry.data = {...result.quoteData,image:{extension:result.quoteData.image.extension,length:result.quoteData.image.bytes.length}}
      validateYinhuiExport(result.quoteData)
      const template = buffer(readFileSync(`public/templates/${YINHUI_PROFILES[result.quoteData.templateId || 'standard'].file}`))
      const generated = createYinhuiCustomerQuoteWorkbook(result,template)
      const cached = parseXlsxWorkbook(buffer(generated)).sheets[0]!.rows
      expect(cached[31]?.[9]).toBeCloseTo(originalTotal + (round === 3 ? .125 : 0),6)
      expect(cached[33]?.[9]).toBeCloseTo(originalTotal + (round === 3 ? .125 : 0) + result.quoteData.freightLclHkd!,6)
      if (round === 1) writeFileSync(`${output}/${name}`,generated)
      entry.status = 'exported'
    } catch (e) { entry.status = 'blocked'; entry.error = e instanceof Error ? e.message : String(e) }
    report.push(entry)
    console.log(round,name,entry.status,entry.error || '')
  }
  writeFileSync(`${output}/conversion-report.json`,JSON.stringify(report.filter(r => r.round === 1),null,2))
  writeFileSync(`${output}/rounds-report.json`,JSON.stringify(report.map(({data: _data, ...r}) => r),null,2))
  expect(samples.map(hash)).toEqual(sourceHashes)
  expect(report.filter(r => r.status !== 'exported')).toEqual([])
}, 120000)

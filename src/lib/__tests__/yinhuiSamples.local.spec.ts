import { readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { expect, it } from 'vitest'
import { convertYinhuiInternalQuote, validateYinhuiExport, yinhuiMaterialPrice, yinhuiTotals } from '../customerPriceConverters/yinhui'
import { createYinhuiCustomerQuoteWorkbook, sanitizeYinhuiTemplate } from '../customerPriceConverters/yinhuiTemplate'
import { YINHUI_PROFILES } from '../customerPriceConverters/yinhuiProfiles'
import { parseXlsxWorkbook } from '../customerPriceConverters/xlsxLite'
import { strFromU8, unzipSync } from 'fflate'

const source = process.env.YINHUI_SAMPLE_DIR
const output = process.env.YINHUI_TEST_OUTPUT
const additional = process.env.YINHUI_ADDITIONAL_SAMPLE
const correctedTemplate = process.env.YINHUI_88753_TEMPLATE
function buffer(b: Uint8Array) { return b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength) as ArrayBuffer }
it.skipIf(!correctedTemplate || process.env.YINHUI_REFRESH_TEMPLATES !== '1')('sanitizes the supplied 88753 layout without retaining customer sample values', () => {
  writeFileSync(`public/templates/${YINHUI_PROFILES['88753'].file}`,sanitizeYinhuiTemplate(buffer(readFileSync(correctedTemplate!))))
})
it.skipIf(!process.env.YINHUI_KITTEN_TEMPLATE || process.env.YINHUI_REFRESH_TEMPLATES !== '1')('extends the supplied 89275 mechanical section for separate contact rows', () => {
  writeFileSync(`public/templates/${YINHUI_PROFILES['89275'].file}`,sanitizeYinhuiTemplate(buffer(readFileSync(process.env.YINHUI_KITTEN_TEMPLATE!)),{mechanicalCapacity:13}))
})
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
      writeFileSync(`public/templates/${profile.file}`,sanitizeYinhuiTemplate(buffer(readFileSync(`${source}/${name}`)),{mechanicalCapacity:id === '89275' ? 13 : undefined}))
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

it.skipIf(!source || !output)('checks C-ABS and explicitly acknowledged missing prices in all supplied layout families', () => {
  const report: Array<Record<string, unknown>> = []
  for (const name of readdirSync(source!).filter(n => n.startsWith('银辉') && n.endsWith('.xlsx'))) {
    const input = readFileSync(`${source}/${name}`)
    const sourceHash = createHash('sha256').update(input).digest('hex')
    const result = convertYinhuiInternalQuote(buffer(input), name)
    const item = result.quoteData.tools.find(row => row.weightG > 0)!
    const index = result.quoteData.tools.indexOf(item)
    const original = yinhuiTotals(result.quoteData).exFactory
    const oldCost = item.weightG * yinhuiMaterialPrice(result.quoteData, item.material)! / 1000
    const template = buffer(readFileSync(`public/templates/${YINHUI_PROFILES[result.quoteData.templateId || 'standard'].file}`))
    const templateZip = unzipSync(new Uint8Array(template))
    const structure = (bytes: Uint8Array, summary = false) => {
      const doc = new DOMParser().parseFromString(strFromU8(bytes), 'application/xml')
      return {
        cells: Array.from(doc.getElementsByTagName('c')).map(cell => [cell.getAttribute('r'), cell.getAttribute('s'), summary && cell.getAttribute('r') === 'J32' ? undefined : cell.getElementsByTagName('f')[0]?.outerHTML]),
        geometry: ['cols','mergeCells','pageMargins','pageSetup'].map(tag => doc.getElementsByTagName(tag)[0]?.outerHTML),
        rows: Array.from(doc.getElementsByTagName('row')).map(row => [row.getAttribute('r'), row.getAttribute('ht')]),
      }
    }
    for (const resin of ['C-ABS', 'UNPRICED-RESIN']) {
      item.material = resin
      const missing = resin === 'UNPRICED-RESIN'
      if (missing) expect(() => createYinhuiCustomerQuoteWorkbook(result, template)).toThrow(/请确认/)
      const generated = createYinhuiCustomerQuoteWorkbook(result, template, {missingMaterialPricesConfirmed:missing})
      const parsed = parseXlsxWorkbook(buffer(generated))
      expect(parsed.sheets[4]?.rows[index + 7]?.[14]).toBe(missing ? '' : 24)
      expect(parsed.sheets[0]?.rows[31]?.[9]).toBeCloseTo(original - oldCost + (missing ? 0 : item.weightG * 24 / 1000), 6)
      expect(String(parsed.sheets[0]?.rows[5]?.[2] || '').includes('PRICE PENDING')).toBe(missing)
      const generatedZip = unzipSync(generated)
      expect(generatedZip['xl/styles.xml']).toEqual(templateZip['xl/styles.xml'])
      for (let sheet = 1; sheet <= 6; sheet++) {
        const key = `xl/worksheets/sheet${sheet}.xml`
        expect(structure(generatedZip[key]!, sheet === 1)).toEqual(structure(templateZip[key]!, sheet === 1))
      }
      writeFileSync(`${output}/${result.quoteData.templateId}-${resin}-export.xlsx`, generated)
      report.push({file:name,profile:result.quoteData.templateId,resin,status:'passed',knownSubtotalHkd:parsed.sheets[0]?.rows[31]?.[9]})
    }
    expect(createHash('sha256').update(readFileSync(`${source}/${name}`)).digest('hex')).toBe(sourceHash)
  }
  writeFileSync(`${output}/material-price-report.json`, JSON.stringify(report,null,2))
}, 120000)

it.skipIf(!additional || !output)('converts an additional compact Tool Plan sample deterministically without changing its workbook', () => {
  const input = readFileSync(additional!)
  const sourceHash = createHash('sha256').update(input).digest('hex')
  let baseline: unknown
  for (const round of [1,2,3]) {
    const result = convertYinhuiInternalQuote(buffer(input), additional!.split(/[\\/]/).pop()!)
    const comparable = {...result.quoteData,image:result.quoteData.image ? {extension:result.quoteData.image.extension,hash:createHash('sha256').update(result.quoteData.image.bytes).digest('hex')} : null}
    if (round === 1) baseline = comparable
    else expect(comparable).toEqual(baseline)
    expect(result.quoteData).toMatchObject({model:'88753',templateId:'88753',packaging:'Gift Box'})
    expect(result.quoteData.tools).toHaveLength(50)
    expect(result.quoteData.tools.filter(row => row.weightG > 0)).toHaveLength(10)
    expect(result.quoteData.tools.reduce((total,row) => total + row.weightG,0)).toBeCloseTo(183.3,8)
    expect(result.quoteData.tools.reduce((total,row) => total + row.toolingHkd,0)).toBe(639000)
    expect(result.quoteData.tools.filter(row => row.material === 'TPR')).toMatchObject([{description:'輪胎',usage:2,cavity:12,weightG:1.4}])
    expect(result.quoteData.tools.filter(row => row.description === '輪轂')).toMatchObject([{material:'ABS',usage:2,cavity:12,weightG:2.4}])
    expect(result.quoteData.plastic).toEqual([])
    expect(result.quoteData.mechanical).toEqual(expect.arrayContaining([
      expect.objectContaining({description:'Frosted PC Sheet  0.5*14*25  (1PCS)'}),
      expect.objectContaining({description:'Printed PVC Sheet  0.3*57.8*115MM (1PCS)'}),
    ]))
    expect(result.quoteData.mechanical).toHaveLength(30)
    expect(result.quoteData.mechanical.filter(row => /AAA Battery .*Contact/.test(row.description))).toMatchObject([
      {description:'AAA Battery Positive Contact(2PCS)',quantity:2},
      {description:'AAA Battery Negative Contact(2PCS)',quantity:2},
      {description:'AAA Battery Positive-Negative Contact(2PCS)',quantity:2},
    ])
    expect(result.quoteData.documentFees).toMatchObject([{amountHkd:.18539692}])
    expect(result.quoteData.packagingRows.some(row => /Customs/.test(row.description))).toBe(false)
    expect(result.quoteData.electronic).toHaveLength(6)
    expect(result.quoteData.electronic.find(row => row.description === 'TXPCBA')).toMatchObject({quantity:1})
    expect(result.quoteData.freightFclHkd).toBeCloseTo(.281129149685833,12)
    expect(result.quoteData.freightLclHkd).toBeCloseTo(.612424154496133,12)
    expect(yinhuiTotals(result.quoteData).exFactory).toBeCloseTo(76.2117507013597,8)
    expect(yinhuiTotals(result.quoteData).missingMaterialPrices).toEqual([])
    result.quoteData.productName = 'GOAL GO BOT'
    expect([
      ...result.quoteData.plastic,
      ...result.quoteData.mechanical,
      ...result.quoteData.electronic,
      ...(result.quoteData.fabric || []),
      ...result.quoteData.packagingRows,
    ].filter(row => /[\u3400-\u9fff]/.test(row.description)).map(row => row.description)).toEqual([])
    validateYinhuiExport(result.quoteData)
    const template = buffer(readFileSync(`public/templates/${YINHUI_PROFILES['88753'].file}`))
    const generated = createYinhuiCustomerQuoteWorkbook(result,template)
    const templateZip = unzipSync(new Uint8Array(template)); const generatedZip = unzipSync(generated)
    expect(generatedZip['xl/styles.xml']).toEqual(templateZip['xl/styles.xml'])
    const structure = (bytes: Uint8Array, summary = false) => {
      const doc = new DOMParser().parseFromString(strFromU8(bytes), 'application/xml')
      return {
        cells:Array.from(doc.getElementsByTagName('c')).map(cell => [cell.getAttribute('r'),cell.getAttribute('s'),summary && cell.getAttribute('r') === 'J32' ? undefined : cell.getElementsByTagName('f')[0]?.outerHTML]),
        geometry:['cols','mergeCells','pageMargins','pageSetup'].map(tag => doc.getElementsByTagName(tag)[0]?.outerHTML),
        rows:Array.from(doc.getElementsByTagName('row')).map(row => [row.getAttribute('r'),row.getAttribute('ht')]),
      }
    }
    for (let sheet = 1; sheet <= 6; sheet++) expect(structure(generatedZip[`xl/worksheets/sheet${sheet}.xml`]!, sheet === 1)).toEqual(structure(templateZip[`xl/worksheets/sheet${sheet}.xml`]!, sheet === 1))
    const cached = parseXlsxWorkbook(buffer(generated)).sheets[0]!.rows
    expect(cached[31]?.[9]).toBeCloseTo(yinhuiTotals(result.quoteData).exFactory,6)
    expect(cached[31]?.[7]).toBe(.18539692)
    expect(cached[29]?.[9]).toBeCloseTo(76.0263537813597,8)
    if (round === 1) writeFileSync(`${output}/银辉88753-报客价-映射复测.xlsx`,generated)
  }
  expect(createHash('sha256').update(readFileSync(additional!)).digest('hex')).toBe(sourceHash)
}, 120000)

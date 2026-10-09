import type { CustomerPricingSettings } from '@/lib/customerPriceConverters/pricingSettings'
import { readFileSync } from 'node:fs'
import { strFromU8, unzipSync } from 'fflate'
import { describe, expect, it } from 'vitest'
import { buildYinhuiCustomerQuoteFileName, convertYinhuiInternalQuote, convertYinhuiP4InternalQuote, isYinhuiCustomer, validateYinhuiExport, yinhuiMaterialPrice, yinhuiTotals } from '@/lib/customerPriceConverters/yinhui'
import { createYinhuiCustomerQuoteWorkbook, sanitizeYinhuiTemplate, YINHUI_SHEET_NAMES } from '@/lib/customerPriceConverters/yinhuiTemplate'
import { createXlsxWorkbook, parseXlsxWorkbook, type XlsxCellInput } from '@/lib/customerPriceConverters/xlsxLite'
import { P4_SECTION_CODES, type P4InternalQuoteArtifact } from '@/lib/customerPriceConverters/p4Artifact'
import { YINHUI_PROFILES } from '@/lib/customerPriceConverters/yinhuiProfiles'

function buffer(bytes: Uint8Array) { return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer }
const template = buffer(readFileSync('public/templates/yinhui-customer-quote-template.bin'))
function legacy(options: { material?: string; internal?: number | string; category?: string; fileModel?: string } = {}) {
  const rows: XlsxCellInput[][] = []
  const row = (r: number, values: Record<number, XlsxCellInput>) => { rows[r - 1] = rows[r - 1] || []; for (const [c, value] of Object.entries(values)) rows[r - 1]![Number(c)] = value }
  row(10, { 0: '#00012 Sample Robot (Window Box) 银辉' })
  row(11, { 2: '名称', 3: '料型', 4: '料重(G)' })
  row(12, { 2: 'Body*1', 3: options.material || 'ABS', 4: 100, 11: 2 })
  row(25, { 3: '出厂价' })
  row(26, { 1: '料价', 2: '料', 3: 1, 10: '彩盒（CM）：', 11: 10, 12: 20, 13: 30 })
  row(27, { 1: '啤工', 2: '啤工', 3: 1, 10: '裝箱尺碼：', 11: 20, 12: 21, 13: 22 })
  row(28, { 1: '装配工', 2: 'Assembly', 3: 3, 4: 3.3, 10: '装箱：', 11: 4 })
  row(29, { 1: options.category || '五金', 2: '螺丝M2(2PCS)', 3: options.internal ?? 1, 4: 1.1, 10: 'MOQ:', 11: 5000 })
  row(30, { 1: '纸箱', 2: 'Outer Carton', 3: 2, 4: 2.2 })
  row(31, { 1: '装配工', 2: '成品包装', 3: 1, 4: 1.1 })
  row(32, { 1: '油漆', 2: '油漆', 3: 2, 4: 2.2 })
  row(33, { 1: '吸塑', 2: '吸塑', 3: 1 })
  row(34, { 2: '×', 3: 1.1 }); row(35, { 2: '÷', 3: 1 })
  row(38, { 1: '电池', 2: 'Battery (2PCS)', 3: 5, 6: 5.25 })
  row(39, { 1: '彩盒/内咭', 2: '彩盒', 3: 1, 6: 1.05 })
  row(40, { 2: '×', 3: 1.05 }); row(41, { 2: '÷', 3: 1 })
  row(43, { 2: '报关费用/文件费/操作费用：', 3: .1 }); row(44, { 4: 'FCL', 5: 'LCL' }); row(45, { 4: 1.2, 5: 2.3 }); row(46, { 2: '出厂价', 3: 30 })
  return buffer(createXlsxWorkbook([
    { name: '明细', rows },
    { name: 'Tool PLan', rows: [[], [], [], ['M01', 'Body', 'PART-001', options.material || 'ABS', '', 1, 1, 100, 30, 30, 2000, 2000, 100]] },
    { name: '供应商报价', rows: [['PRIVATE SUPPLIER', '采购利润', 'contact@example.invalid']] },
  ]))
}
function formulaAndStyle(bytes: ArrayBuffer) {
  const zip = unzipSync(new Uint8Array(bytes))
  return YINHUI_SHEET_NAMES.map((_, i) => {
    const doc = new DOMParser().parseFromString(strFromU8(zip[`xl/worksheets/sheet${i + 1}.xml`]!), 'application/xml')
    const formula = Array.from(doc.getElementsByTagName('c')).filter(c => c.getElementsByTagName('f').length && !(i === 0 && c.getAttribute('r') === 'J32')).map(c => [c.getAttribute('r'), new XMLSerializer().serializeToString(c.getElementsByTagName('f')[0]!)])
    const style = Array.from(doc.getElementsByTagName('c')).map(c => [c.getAttribute('r'), c.getAttribute('s')])
    const geometry = ['cols', 'mergeCells', 'pageMargins', 'pageSetup'].map(name => doc.getElementsByTagName(name)[0]?.outerHTML)
    const heights = Array.from(doc.getElementsByTagName('row')).map(r => [r.getAttribute('r'), r.getAttribute('ht'), r.getAttribute('customHeight')])
    return { formula, style, geometry, heights }
  })
}
function changedLegacy(change: (sheets: ReturnType<typeof parseXlsxWorkbook>['sheets']) => void) {
  const parsed = parseXlsxWorkbook(legacy())
  change(parsed.sheets)
  return buffer(createXlsxWorkbook(parsed.sheets))
}
function p4(): P4InternalQuoteArtifact {
  const sections = Object.fromEntries<P4InternalQuoteArtifact['sections']['engineering']>(P4_SECTION_CODES.map(code => [code, {code,name:code,status:'approved',revision:1,calculationStatus:'valid',dependencyStatus:'current',calculationHash:'hash',isRequired:true,payload:{},calculation:{line_breakdown:[],totals:{total_hkd:0}}}])) as P4InternalQuoteArtifact['sections']
  sections.sales.payload = { shipping: { markup_x:1.1,misc_ratio:0 }, cartons:[{length_in:10,width_in:10,height_in:10,qty_per_carton:4}],color_box_size_cm:{length:10,width:10,height:10} }
  sections.sales.calculation = {line_breakdown:[{kind:'carton',per_piece_hkd:2},{kind:'packaging_material',item:'Color Box',quantity:1,amount_hkd:1},{kind:'tax',amount_hkd:12}],totals:{freight_options:[{route_key:'yt40',per_piece_hkd:1},{route_key:'yt_lcl',per_piece_hkd:2}]}}
  sections.molding.calculation = {line_breakdown:[{kind:'injection',item:'Body',mold_no:'M01',material:'ABS',quantity:1,cavity:1,net_weight_g:100,molding_cost_hkd:2,amount_hkd:3}],totals:{total_hkd:3}}
  sections.assembly.calculation = {line_breakdown:[{kind:'assembly_manual_total',category:'assembly',amount_hkd_pcs:2}],totals:{total_hkd:2}}
  sections.engineering.calculation = {line_breakdown:[{kind:'material',category:'hardware',item:'Screw',quantity:2,amount_hkd:1,markup_override:1.2}],totals:{total_hkd:1}}
  return {templateVersion:'internal-quote-p4-v2',structuredDataSchemaVersion:'internal-quote-structured-data-v1',quoteNo:'IQ-1',versionLabel:'V1',customer:'银辉',quantity:5000,productName:'Sample Robot',factoryAndWorkshop:'huaxing/华兴',formulaVersion:'v1',referenceSnapshotId:'ref1',referenceSnapshot:{fx:{rmb_hkd:.85}},sections}
}

describe('Silverlit temporary independent mapping', () => {
  it('uses maintained material, labor and detail rates once for each conversion', () => {
    const definition = JSON.parse(readFileSync('shared/customerPriceDefaults.json', 'utf8')).yinhui
    const pricing: CustomerPricingSettings = { factory_id: 'huaxing', customer_id: 'yinhui', revision: 1, snapshot_id: 'y1', materials: definition.materials, rates: Object.fromEntries(Object.entries(definition.rates).map(([k,v]) => [k,(v as {value:number}).value])), texts: {}, updated_at: '', updated_by_name: '' }
    pricing.materials.find(m => m.material === 'ABS')!.price = 20
    pricing.rates.material_multiplier = 1.1; pricing.rates.injection_multiplier = 1.3; pricing.rates.detail_multiplier = 1.2
    const before = convertYinhuiP4InternalQuote(p4(), 'a.xlsx').quoteData
    const after = convertYinhuiP4InternalQuote(p4(), 'a.xlsx', pricing).quoteData
    expect(yinhuiMaterialPrice(after, 'ABS')).toBe(22)
    expect(after.tools[0]!.laborHkd).toBeCloseTo(before.tools[0]!.laborHkd * 1.3)
    expect(after.mechanical[0]!.amountHkd).toBeCloseTo(before.mechanical[0]!.amountHkd * 1.2)
    expect(convertYinhuiP4InternalQuote(p4(), 'b.xlsx').quoteData.mechanical).toEqual(before.mechanical)
  })

  it('preserves Chinese BOM descriptions from approved P4 data through export', () => {
    const artifact = p4()
    artifact.productName = '#00012 Sample Robot'
    const lines = artifact.sections.engineering.calculation.line_breakdown as Array<Record<string, unknown>>
    lines[0]!.item = '螺丝 Φ2.0x6PB 黑色（2PCS）'
    const result = convertYinhuiP4InternalQuote(artifact, '银辉00012.xlsx')
    expect(result.quoteData.mechanical[0]).toMatchObject({ description: '螺丝 Φ2.0x6PB 黑色（2PCS）', quantity: 2, amountHkd: 1.2 })
    const output = parseXlsxWorkbook(buffer(createYinhuiCustomerQuoteWorkbook(result, template)))
    expect(output.sheets[2]!.rows.flat()).toContain('螺丝 Φ2.0x6PB 黑色（2PCS）')
    expect(output.sheets[0]!.rows[31]![9]).toBeCloseTo(yinhuiTotals(result.quoteData).exFactory, 6)
  }, 15000)
  it('maps source amounts and quantities, uses Silverlit resin prices, and routes packing separately', () => {
    const result = convertYinhuiInternalQuote(legacy(), '银辉00012.xlsx'); const d = result.quoteData
    expect(d.model).toBe('00012'); expect(d.moq).toBe(5000)
    expect(d.mechanical[0]).toMatchObject({quantity:2,amountHkd:1.1,description:'螺丝M2(2PCS)'})
    expect(d.electronic[0]?.amountHkd).toBe(5.25)
    expect(d.assemblyHkd).toBeCloseTo(3.3,8); expect(d.packagingLaborHkd).toBe(1.1)
    expect(d.packagingRows[0]?.description).toBe('彩盒')
    expect(yinhuiTotals(d).plastic).toBe(1.565)
    expect(d.freightFclHkd).toBe(1.2); expect(d.freightLclHkd).toBe(2.3)
    expect(yinhuiTotals(d).exFactory).toBeCloseTo(20.965, 6)
  })
  it('preserves customer formulas and formatting except the approved H32 fee term in J32', () => {
    const result = convertYinhuiInternalQuote(legacy(), '银辉00012.xlsx')
    const out = buffer(createYinhuiCustomerQuoteWorkbook(result, template))
    expect(formulaAndStyle(out)).toEqual(formulaAndStyle(template))
    expect(unzipSync(new Uint8Array(out))['xl/styles.xml']).toEqual(unzipSync(new Uint8Array(template))['xl/styles.xml'])
    const read = parseXlsxWorkbook(out)
    expect(read.sheets.map(s => s.name)).toEqual(YINHUI_SHEET_NAMES)
    expect(read.sheets[2]!.rows.flat()).toContain('螺丝M2(2PCS)')
    expect(read.sheets[1]!.rows[32]!.slice(1, 5)).toEqual(['彩盒', 10, 20, 30])
    expect(read.sheets[0]?.rows[11]?.[0]).toBe(1)
    expect(read.sheets[0]?.rows[43]?.[16]).toBe('in')
    expect(read.sheets[0]?.rows[37]?.[3]).toBe('30 days')
    expect(read.sheets[0]?.rows[31]?.[9]).toBeCloseTo(yinhuiTotals(result.quoteData).exFactory,6)
    expect(parseXlsxWorkbook(out, {includeFormulas:true}).sheets[0]?.cellFormulas?.J32).toBe('J30-J31+H32')
    expect(read.sheets[0]?.rows[31]?.[7]).toBe(.1)
    expect(read.sheets[0]?.rows[29]?.[9]).toBeCloseTo(20.865,6)
    expect(read.sheets[1]?.rows.flat().join(' ')).not.toContain('Documents / Customs Fee')
    expect(read.sheets[0]?.rows[33]?.[9]).toBeCloseTo(yinhuiTotals(result.quoteData).lcl!,6)
    expect(read.sheets[3]?.rows[65]?.[10]).toBe(0)
    expect(read.sheets[0]?.rows[32]?.[8]).toBe('#DIV/0!') // the unfilled original route, not a changed formula
  }, 15_000)
  it('does not export source supplier sheets, sample product data, comments or external links', () => {
    const result = convertYinhuiInternalQuote(legacy(), '银辉00012.xlsx')
    const out = unzipSync(createYinhuiCustomerQuoteWorkbook(result, template))
    expect(Object.keys(out).join(' ')).not.toMatch(/comments|externalLink|sharedStrings|vmlDrawing|calcChain/)
    const content = Object.values(out).map(bytes => strFromU8(bytes)).join('\n')
    expect(content).not.toMatch(/PRIVATE SUPPLIER|contact@example|Robo Rapidfire|88538|88528|采购利润/)
    expect(sanitizeYinhuiTemplate(template)).toBeTruthy()
  })
  it.each([['missing cache', {internal:'#VALUE!'}],['invalid resin cell', {material:'#VALUE!'}],['unmapped cost', {category:'电镀'}]])('blocks %s instead of silently using zero', (_, options) => {
    expect(() => convertYinhuiInternalQuote(legacy(options), '银辉00012.xlsx')).toThrow()
  })
  it.each([['ABS',15.65],['TPR',18.8],['PP',12.6],['POM',34.07],['C-ABS',24],[' c – abs料 ',24]] as const)('applies the supplied %s price to the material cell and 100g cost', (resin, price) => {
    const result = convertYinhuiInternalQuote(legacy({material:resin}), '银辉00012.xlsx')
    const output = buffer(createYinhuiCustomerQuoteWorkbook(result, template))
    const rows = parseXlsxWorkbook(output).sheets[4]!.rows
    expect(rows[7]?.[14]).toBe(price)
    expect(rows[7]?.[15]).toBeCloseTo(price / 10, 8)
    expect(yinhuiTotals(result.quoteData).missingMaterialPrices).toEqual([])
    expect(buildYinhuiCustomerQuoteFileName(result)).not.toContain('待补料价')
  })
  it.each(['standard','88636','89115','89275'] as const)('exports unpriced resin with an explicit acknowledgement and blank price in %s', profile => {
    const result = convertYinhuiInternalQuote(legacy({material:'PA'}), '银辉00012.xlsx')
    result.quoteData.templateId = profile
    result.quoteData.stage = 'R0'
    const variant = buffer(readFileSync(`public/templates/${YINHUI_PROFILES[profile].file}`))
    expect(result.warnings.join(' ')).toMatch(/缺少银辉报客料价：PA/)
    expect(result.sheets[0]?.name).toContain('待补料价')
    expect(yinhuiMaterialPrice(result.quoteData, 'PA')).toBeNull()
    expect(yinhuiTotals(result.quoteData).exFactory).toBeCloseTo(19.4, 6)
    expect(() => validateYinhuiExport(result.quoteData)).not.toThrow()
    expect(() => createYinhuiCustomerQuoteWorkbook(result, variant)).toThrow(/请确认/)
    const output = buffer(createYinhuiCustomerQuoteWorkbook(result, variant, {missingMaterialPricesConfirmed:true}))
    const parsed = parseXlsxWorkbook(output)
    expect(parsed.sheets[4]?.rows[7]?.[8]).toBe('PA')
    expect(parsed.sheets[4]?.rows[7]?.[14]).toBe('') // unknown is blank, never an internal/other-customer price or a zero price
    const toolXml = new DOMParser().parseFromString(strFromU8(unzipSync(new Uint8Array(output))['xl/worksheets/sheet5.xml']!), 'application/xml')
    const priceCell = Array.from(toolXml.getElementsByTagName('c')).find(cell => cell.getAttribute('r') === 'O8')!
    expect(priceCell.childNodes).toHaveLength(0)
    expect(parsed.sheets[4]?.rows[7]?.[15]).toBe(0) // original formula evaluates the still-blank price
    expect(parsed.sheets[0]?.rows[5]?.[2]).toBe('R0 / PRICE PENDING')
    expect(parsed.sheets[0]?.rows[31]?.[9]).toBeCloseTo(19.4, 6)
    expect(formulaAndStyle(output)).toEqual(formulaAndStyle(variant))
    expect(unzipSync(new Uint8Array(output))['xl/styles.xml']).toEqual(unzipSync(new Uint8Array(variant))['xl/styles.xml'])
    expect(buildYinhuiCustomerQuoteFileName(result)).toContain('-待补料价.xlsx')
    result.quoteData.freightLclHkd = null
    expect(() => createYinhuiCustomerQuoteWorkbook(result, variant, {missingMaterialPricesConfirmed:true})).toThrow(/运费/)
  })
  it('keeps known material costs and deduplicates repeated missing resin warnings', () => {
    const input = changedLegacy(sheets => {
      sheets.splice(1,1)
      sheets[0]!.rows[12] = [null,null,'Cover*1','PA',20,null,null,null,null,null,null,1]
      sheets[0]!.rows[13] = [null,null,'Handle*1','PA',30,null,null,null,null,null,null,1]
    })
    const result = convertYinhuiInternalQuote(input, '银辉00012.xlsx')
    expect(yinhuiTotals(result.quoteData)).toMatchObject({plastic:1.565,missingMaterialPrices:['PA']})
    const output = parseXlsxWorkbook(buffer(createYinhuiCustomerQuoteWorkbook(result, template, {missingMaterialPricesConfirmed:true})))
    expect(output.sheets[4]?.rows[7]?.[14]).toBe(15.65)
    expect(output.sheets[4]?.rows[8]?.[14]).toBe('')
    expect(output.sheets[4]?.rows[9]?.[14]).toBe('')
    expect(result.warnings.filter(w => w.startsWith('缺少银辉报客料价：'))).toHaveLength(1)
  })
  it('accepts Chinese BOM names and zero freight while requiring valid names and explicit freight', () => {
    const d = convertYinhuiInternalQuote(legacy(), '银辉00012.xlsx').quoteData
    d.freightLclHkd = null; expect(() => validateYinhuiExport(d)).toThrow(/运费/)
    d.freightLclHkd = 0; expect(() => validateYinhuiExport(d)).not.toThrow()
    d.mechanical[0]!.description = '螺丝（2PCS）'; expect(() => validateYinhuiExport(d)).not.toThrow()
    d.mechanical[0]!.description = '#VALUE!'; expect(() => validateYinhuiExport(d)).toThrow(/BOM 物料名称/)
    d.mechanical[0]!.description = ''; expect(() => validateYinhuiExport(d)).toThrow(/BOM 物料名称/)
  })
  it('uses main-sheet molding groups without inventing part IDs and applies the selected resin table', () => {
    const input = changedLegacy(sheets => {
      sheets.splice(1, 1)
      sheets[0]!.rows[9]![0] = '#88636 Rescue Bear 银辉'
      sheets[0]!.rows[11]![2] = 'Body*1/Cover*2'
      sheets[0]!.rows[11]![3] = 'TPE'
    })
    const d = convertYinhuiInternalQuote(input, '银辉88636.xlsx').quoteData
    expect(d.templateId).toBe('88636')
    expect(d.tools).toMatchObject([
      { moldNo:'',partNo:'',description:'Body',usage:1,weightG:100,laborHkd:2 },
      { moldNo:'',partNo:'',description:'Cover',usage:2,weightG:0,laborHkd:0 },
    ])
    expect(yinhuiTotals(d).plastic).toBe(1.59)
    expect(yinhuiTotals(convertYinhuiInternalQuote(legacy({material:'TPE'}), '银辉00012.xlsx').quoteData).plastic).toBe(1.59)
  })
  it.each(Object.keys(YINHUI_PROFILES) as Array<keyof typeof YINHUI_PROFILES>)('uses the same customer resin prices in layout %s', profile => {
    const d = convertYinhuiInternalQuote(legacy({material:'PVC'}), '银辉00012.xlsx').quoteData
    d.templateId = profile
    expect(yinhuiTotals(d).plastic).toBeCloseTo(1.716, 8)
    d.tools[0]!.material = 'PP'
    expect(yinhuiTotals(d).plastic).toBe(1.26)
  })
  it('selects the window-box sheet independently of order and reconciles duplicate cm/in dimensions', () => {
    const build = (reverse: boolean, ambiguous = false, duplicate = false) => changedLegacy(sheets => {
      const main = sheets[0]!
      main.name = '明细 (开窗盒)'; main.rows[9]![0] = '#89127 MUSCLE CLASH 银辉'
      main.rows[26]![11] = 50.8; main.rows[26]![12] = 53.34; main.rows[26]![13] = 55.88
      main.rows[29]![10] = '裝箱尺碼：'; main.rows[29]![11] = ambiguous ? 999 : 20; main.rows[29]![12] = 21; main.rows[29]![13] = 22
      const closed = structuredClone(main)
      closed.name = duplicate ? '明细（开窗盒）' : '明细（密封盒）'
      closed.rows[28]![11] = 123
      sheets.splice(reverse ? 1 : 0,0,closed)
    })
    const a = convertYinhuiInternalQuote(build(false), '银辉89127.xlsx').quoteData
    const b = convertYinhuiInternalQuote(build(true), '银辉89127.xlsx').quoteData
    expect(a).toEqual(b)
    expect(a).toMatchObject({model:'89127',packaging:'Window Box',moq:5000,cartonCm:[50.8,53.34,55.88]})
    expect(() => convertYinhuiInternalQuote(build(false,true), '银辉89127.xlsx')).toThrow(/外箱尺寸/)
    expect(() => convertYinhuiInternalQuote(build(false,false,true), '银辉89127.xlsx')).toThrow(/唯一确认/)
  })
  it('blocks inconsistent internal quoted columns instead of guessing which amount is right', () => {
    const input = changedLegacy(sheets => { sheets[0]!.rows[28]![4] = 7 })
    expect(() => convertYinhuiInternalQuote(input,'银辉00012.xlsx')).toThrow(/报客金额与内部金额/)
    const injection = changedLegacy(sheets => { sheets[0]!.rows[11]![9] = 2; sheets[0]!.rows[11]![11] = 3 })
    expect(() => convertYinhuiInternalQuote(injection,'银辉00012.xlsx')).toThrow(/报客啤工与内部啤工/)
  })
  it('takes a side-by-side packaging block from carton formula dependencies, including when it is on the right', () => {
    const parsed = parseXlsxWorkbook(legacy())
    const rows: XlsxCellInput[][] = parsed.sheets[0]!.rows
    rows[26]![15] = '裝箱尺碼：'; rows[26]![16] = 15; rows[26]![17] = 16; rows[26]![18] = 17
    rows[27]![15] = '装箱：'; rows[27]![16] = 8
    rows[28]![15] = 'MOQ:'; rows[28]![16] = 6000
    rows[25]![15] = '彩盒（CM）：'; rows[25]![16] = 10; rows[25]![17] = 11; rows[25]![18] = 12
    rows[29]![3] = {formula:'Q27*R27*S27/2040',value:2}
    const input = () => buffer(createXlsxWorkbook([{name:'明细',rows},parsed.sheets[1]!]))
    const d = convertYinhuiInternalQuote(input(),'银辉00012.xlsx').quoteData
    expect(d.cartonCm).toEqual([15,16,17].map(v => v*2.54))
    expect(d.cartonPack).toBe(8); expect(d.moq).toBe(6000); expect(d.colorBoxCm).toEqual([10,11,12])
    rows[29]![3] = 2
    expect(() => convertYinhuiInternalQuote(input(),'银辉00012.xlsx')).toThrow(/并列外箱方案/)
  })
  it('derives piece usage and cavities from a matching mold plan instead of copying fractional sets into cavities', () => {
    const input = changedLegacy(sheets => {
      sheets.splice(1,1)
      sheets[0]!.rows[11]![2] = 'Body*1/Cover*1'; sheets[0]!.rows[11]![7] = .5
      sheets.push({name:'模具报价',cellFillIds:[],rows:[['#00012'],[null,'M01','Body*1/Cover*1',null,null,null,'ABS',2,.5,72000]]})
    })
    const d = convertYinhuiInternalQuote(input,'银辉00012.xlsx').quoteData
    expect(d.tools).toMatchObject([{usage:2,cavity:1,weightG:100,toolingHkd:72000},{usage:2,cavity:1,weightG:0}])
    expect(yinhuiTotals(d).plastic).toBe(1.565)
  })
  it('detects compact Tool Plan columns and splits one two-material mold into separately matched injection lines', () => {
    const input = changedLegacy(sheets => {
      sheets[0]!.rows[11]![2] = 'Body*1'; sheets[0]!.rows[11]![3] = 'ABS'; sheets[0]!.rows[11]![4] = 100
      sheets[0]!.rows[12] = [null,null,'Cover*1','TPR',20,null,null,null,null,null,null,3]
      sheets[1] = {name:'TOOL PLAN',cellFillIds:[],rows:[
        [],[null,'模號','中文名稱','編號',null,'出模量',null,'單個膠件重量 (g)','膠料'],[],
        [null,'Mold No.','Chinese Name',null,null,'Cavity',' / up','Plastic Wt (g)','Material'],[],
        [null,'NA1XXX','Body','P1',null,2,2,100,'ABS'],
        [null,null,'Cover','P2',null,2,2,20,'TPR'],
      ]}
      sheets.push({name:'模具报价',cellFillIds:[],rows:[['#00012'],[],[null,'M01','Body*2/Cover*2',null,null,null,'ABS',4,2,500]]})
    })
    const result = convertYinhuiInternalQuote(input,'银辉00012.xlsx')
    expect(result.quoteData.tools).toMatchObject([
      {moldNo:'NA1XXX',partNo:'P1',description:'Body',usage:1,cavity:2,weightG:100,material:'ABS',toolingHkd:500},
      {moldNo:'',partNo:'P2',description:'Cover',usage:1,cavity:2,weightG:20,material:'TPR',toolingHkd:0},
    ])
    expect(result.warnings.join(' ')).toMatch(/模具报价 M01 与 Tool Plan NA1XXX 编号不同/)
  })
  it('keeps a zero Qty/Toy Tool Plan row used for a plugged mold cavity', () => {
    const input = changedLegacy(sheets => {
      sheets[1]!.rows.push(['Repeated part alias','Plugged cavity','/',null,'',1,0,100,30,30,2000,2000,10])
    })
    const tools = convertYinhuiInternalQuote(input, '银辉00012.xlsx').quoteData.tools
    expect(tools).toMatchObject([
      {description:'Body',usage:1,weightG:100},
      {description:'Plugged cavity',usage:0,weightG:0},
    ])
  })
  it('retains the 89127 constant-multiplier formulas without doubling the already cumulative source weight', () => {
    const result = convertYinhuiInternalQuote(legacy(), '银辉00012.xlsx')
    result.quoteData.templateId = '89127'
    const item = result.quoteData.tools[0]!
    result.quoteData.tools = Array.from({length:25},(_,i) => ({...item,weightG:i === 0 ? 197 : i === 4 ? 164 : i === 6 ? 108 : 0,laborHkd:i ? 0 : 2}))
    const variant = buffer(readFileSync(`public/templates/${YINHUI_PROFILES['89127'].file}`))
    const out = buffer(createYinhuiCustomerQuoteWorkbook(result,variant))
    expect(formulaAndStyle(out)).toEqual(formulaAndStyle(variant))
    const rows = parseXlsxWorkbook(out).sheets[4]!.rows
    expect(rows[7]?.[7]).toBe(197); expect(rows[11]?.[6]).toBe(82); expect(rows[13]?.[6]).toBe(54)
    result.quoteData.tools[0]!.weightG = 198
    expect(() => createYinhuiCustomerQuoteWorkbook(result,variant)).toThrow(/料重公式/)
  })
  it('adds carton components and fabric, preserves individual battery contacts, and retains compound quantities', () => {
    const input = changedLegacy(sheets => {
      const rows = sheets[0]!.rows
      rows[28]![2] = '螺丝M2(2*2PCS)'
      rows[35] = [null,'纸箱','Cutting Guard',.3,null,null,.315]
      rows[36] = [null,'车衣','车缝（89275）',2,null,null,2.1]
      rows[37] = [null,'电子','电子（89275）',5,null,null,5.25]
      rows[31] = [null,'五金','AA电池正片(1PCS)',.1,.11]
      rows[32] = [null,'五金','AA电池负片(1PCS)',.2,.22]
    })
    const d = convertYinhuiInternalQuote(input, '银辉00012.xlsx').quoteData
    expect(d.carton.amountHkd).toBe(2.515)
    expect(d.fabric).toMatchObject([{description:'车缝（89275）',quantity:1,amountHkd:2.1}])
    expect(d.electronic).toMatchObject([{description:'电子（89275）',quantity:1,amountHkd:5.25}])
    expect(d.mechanical[0]?.quantity).toBe(4)
    expect(d.mechanical.filter(r => /AA电池[正负]片/.test(r.description))).toMatchObject([
      {description:'AA电池正片(1PCS)',quantity:1,amountHkd:.11,source:'明细!D32'},
      {description:'AA电池负片(1PCS)',quantity:1,amountHkd:.22,source:'明细!D33'},
    ])
  })
  it('routes PC and PVC sheet parts to mechanical without changing their source amounts', () => {
    const input = changedLegacy(sheets => {
      const rows = sheets[0]!.rows
      rows[28]![1] = '五金'; rows[28]![2] = '磨砂PC片 0.5*14*25 (1PCS)'; rows[28]![3] = .15; rows[28]![4] = .165
      rows[31] = [null,'五金','印花PVC片 0.3*57.8*115MM (1PCS)',.43,.473]
    })
    const d = convertYinhuiInternalQuote(input, '银辉00012.xlsx').quoteData
    expect(d.mechanical).toMatchObject([
      {description:'磨砂PC片 0.5*14*25 (1PCS)',quantity:1,amountHkd:.165},
      {description:'印花PVC片 0.3*57.8*115MM (1PCS)',quantity:1,amountHkd:.473},
    ])
    expect(d.plastic).toEqual([])
  })
  it('separates an in-block customs fee from packaging, applies its multiplier once, and keeps freight unchanged', () => {
    const input = changedLegacy(sheets => {
      const rows = sheets[0]!.rows
      rows[32] = [null,'报关费','报关费用/文件费/操作费用：',.15,.165]
      rows[42] = []
      rows[24]![4] = '盐田柜'; rows[24]![5] = '盐田散'
      rows[25] = [null,'运费','Freight',0,.2,.3]
    })
    const result = convertYinhuiInternalQuote(input,'银辉00012.xlsx')
    expect(result.quoteData.documentFees).toMatchObject([{amountHkd:.165,internalHkd:.15,source:'明细!D33'}])
    expect(result.quoteData.packagingRows.some(r => /Customs/.test(r.description))).toBe(false)
    expect(result.quoteData.freightFclHkd).toBeCloseTo(.22,8)
    const parsed = parseXlsxWorkbook(buffer(createYinhuiCustomerQuoteWorkbook(result,template)))
    expect(parsed.sheets[0]?.rows[31]?.[7]).toBe(.165)
    expect(parsed.sheets[0]?.rows[31]?.[9]).toBeCloseTo(19.93,8)
    expect(parsed.sheets[0]?.rows[29]?.[9]).toBeCloseTo(19.765,8)
    expect(result.sheets[0]?.details.find(r => r.description === 'Documents / Customs Fee')?.customerPriceHkd).toBe(.165)
    result.quoteData.documentFees![0]!.amountHkd = -1
    expect(() => validateYinhuiExport(result.quoteData)).toThrow(/金额/)
  })
  it('uses the 88753 customer layout for 30 mechanical lines and both battery information rows', () => {
    const result = convertYinhuiInternalQuote(legacy(),'银辉00012.xlsx')
    result.quoteData.templateId = '88753'
    result.quoteData.mechanical = Array.from({length:30},(_,i) => ({description:`Part ${i+1}`,source:`test!${i}`,quantity:1,amountHkd:.1,internalHkd:.09}))
    result.quoteData.electronic.push({description:'Rechargeable Battery',source:'test',quantity:1,amountHkd:2,internalHkd:1,isBattery:true})
    result.quoteData.adaptor = 'not included'; result.quoteData.tryMe = 'NO'
    const variant = buffer(readFileSync(`public/templates/${YINHUI_PROFILES['88753'].file}`))
    const out = buffer(createYinhuiCustomerQuoteWorkbook(result,variant))
    const read = parseXlsxWorkbook(out)
    expect(read.sheets[2]?.rows[47]?.[1]).toBe('Part 30')
    expect(read.sheets[2]?.rows[17]?.[10]).toBeCloseTo(3,8)
    expect(read.sheets[0]?.rows[56]?.[5]).toBe('Battery (2PCS)')
    expect(read.sheets[0]?.rows[57]?.[5]).toBe('Rechargeable Battery')
    expect(read.sheets[0]?.rows[58]?.[3]).toBe('not included')
    expect(read.sheets[0]?.rows[59]?.[3]).toBe('NO')
    expect(formulaAndStyle(out)).toEqual(formulaAndStyle(variant))
    expect(() => createYinhuiCustomerQuoteWorkbook(result,template)).toThrow(/容量/)
    const clean = parseXlsxWorkbook(buffer(sanitizeYinhuiTemplate(variant)))
    expect(clean.sheets[0]?.rows[57]?.[5]).not.toContain('Battery 4PCS')
  })
  it('extends mechanical rows with matching styles and updates subtotal, shared and cross-sheet formulas', () => {
    const expanded = buffer(sanitizeYinhuiTemplate(template,{mechanicalCapacity:29}))
    const result = convertYinhuiInternalQuote(legacy(),'银辉00012.xlsx')
    result.quoteData.mechanical = Array.from({length:29},(_,i) => ({description:`Part ${i+1}`,source:'test',quantity:2,amountHkd:.1,internalHkd:.09}))
    const output = buffer(createYinhuiCustomerQuoteWorkbook(result,expanded))
    const read = parseXlsxWorkbook(output,{includeFormulas:true})
    expect(read.sheets[2]?.rows[17]?.[10]).toBeCloseTo(2.9,8)
    expect(read.sheets[2]?.cellFormulas?.K18).toBe('SUM(J19:J47)')
    expect(read.sheets[2]?.cellFormulas?.J47).toBe('I47*H47')
    expect(read.sheets[0]?.cellFormulas?.H15).toBe("'BOM (1)'!K48")
    expect(read.sheets[0]?.rows[31]?.[9]).toBeCloseTo(yinhuiTotals(result.quoteData).exFactory,8)
    expect(formulaAndStyle(output)).toEqual(formulaAndStyle(expanded))
  })
  it('treats a trailing long parenthesized number as a model reference, not BOM quantity', () => {
    const input = changedLegacy(sheets => {
      sheets[0]!.rows[31] = [null,'电子','TX盒子（88753）',5,5.5]
    })
    expect(convertYinhuiInternalQuote(input, '银辉00012.xlsx').quoteData.electronic).toMatchObject([
      {description:'TX盒子（88753）',quantity:1,amountHkd:5.5},
      {description:'Battery (2PCS)',quantity:2,amountHkd:5.25},
    ])
  })
  it('ignores copied cost aliases and machine-cycle numbers instead of treating them as quoted prices', () => {
    const input = changedLegacy(sheets => {
      const rows = sheets[0]!.rows
      for (let r = 27; r <= 32; r++) rows[r]![4] = rows[r]![3]!
      rows[11]![9] = 2; rows[11]![11] = 86400
    })
    const d = convertYinhuiInternalQuote(input, '银辉00012.xlsx').quoteData
    expect(d.tools[0]?.laborHkd).toBe(2.2)
    expect(d.assemblyHkd).toBeCloseTo(3.3, 8)
    expect(d.carton.amountHkd).toBe(2.2)
  })
  it('rejects a freight amount smaller than the separately included document fee', () => {
    const input = changedLegacy(sheets => {
      const rows = sheets[0]!.rows
      rows[24]![4] = '盐田柜'
      rows[25] = [null,'运费','Freight',0,.01]
    })
    expect(() => convertYinhuiInternalQuote(input, '银辉00012.xlsx')).toThrow(/运费扣除/)
  })
  it('does not mistake a later subtotal and final FCL/LCL prices for document fee and freight', () => {
    const input = changedLegacy(sheets => {
      const rows = sheets[0]!.rows
      rows[24]![4] = '盐田柜'; rows[24]![5] = '盐田散'
      rows[25] = [null,'运费','Freight',0,.2,.3]
      rows[42] = [] // no independently labelled document/customs fee
      rows[43] = [null,null,null,null,'FCL','LCL']
      rows[44] = [null,null,'电子部分小计',33.89,9.8,9.9]
    })
    const d = convertYinhuiInternalQuote(input, '银辉00012.xlsx').quoteData
    expect(d.freightFclHkd).toBeCloseTo(.22, 8)
    expect(d.freightLclHkd).toBeCloseTo(.33, 8)
    expect(d.packagingRows.some(r => r.description === 'Documents / Customs Fee')).toBe(false)
  })
  it.each(['88636','89115','89275'] as const)('retains the %s variant formulas and layout while recalculating changed costs', (profile) => {
    const result = convertYinhuiInternalQuote(legacy(), '银辉00012.xlsx')
    result.quoteData.templateId = profile
    result.quoteData.fabric = [{description:'车缝（89275）',source:'test',quantity:1,amountHkd:2,internalHkd:1}]
    const variant = buffer(readFileSync(`public/templates/${YINHUI_PROFILES[profile].file}`))
    const out = buffer(createYinhuiCustomerQuoteWorkbook(result, variant))
    expect(formulaAndStyle(out)).toEqual(formulaAndStyle(variant))
    expect(unzipSync(new Uint8Array(out))['xl/styles.xml']).toEqual(unzipSync(new Uint8Array(variant))['xl/styles.xml'])
    expect(parseXlsxWorkbook(out).sheets[0]?.rows[31]?.[9]).toBeCloseTo(yinhuiTotals(result.quoteData).exFactory, 6)
  })
  it('blocks changed weights when the 81283 reference formula contains a fixed weight constant', () => {
    const result = convertYinhuiInternalQuote(legacy(), '银辉00012.xlsx')
    result.quoteData.templateId = '81283'
    const variant = buffer(readFileSync(`public/templates/${YINHUI_PROFILES['81283'].file}`))
    expect(() => createYinhuiCustomerQuoteWorkbook(result,variant)).toThrow(/料重公式/)
  })
  it('can skip huge formatted-only sheets and cells without moving cached values or formulas', () => {
    const input = buffer(createXlsxWorkbook([
      {name:'明细',rows:[['text',null,{formula:'1+2',value:3}],[],[null,'last']]},
      {name:'Unused',rows:[['private']]},
    ]))
    const selected = parseXlsxWorkbook(input,{sheetNames:['明细'],valuesOnly:true})
    expect(selected.sheets).toEqual(parseXlsxWorkbook(input).sheets.filter(s => s.name === '明细'))
    expect(selected.sheets[0]?.rows[0]?.[2]).toBe(3)
    expect(selected.sheets[0]?.rows[2]?.[1]).toBe('last')
  })
  it('maps approved P4 calculations including manual assembly and detached multipliers', () => {
    const result = convertYinhuiP4InternalQuote(p4(), 'approved.xlsx')
    expect(result.quoteData.mechanical[0]?.amountHkd).toBe(1.2)
    expect(result.quoteData.assemblyHkd).toBe(2.2)
    expect(result.quoteData.freightFclHkd).toBe(1.1)
    expect(result.quoteData.internalTotalHkd).toBeCloseTo(10, 6)
    result.quoteData.model = 'P4-001'
    const output = createYinhuiCustomerQuoteWorkbook(result, template)
    expect(parseXlsxWorkbook(buffer(output)).sheets[0]?.rows[31]?.[9]).toBeCloseTo(yinhuiTotals(result.quoteData).exFactory,6)
  })
  it.each(['C-ABS','PA'])('uses the same priced or unpriced %s flow for approved P4 input', resin => {
    const artifact = p4()
    ;(artifact.sections.molding.calculation.line_breakdown as Array<Record<string,unknown>>)[0]!.material = resin
    const result = convertYinhuiP4InternalQuote(artifact, 'approved.xlsx')
    result.quoteData.model = 'P4-001'
    const missing = resin === 'PA'
    expect(yinhuiTotals(result.quoteData).missingMaterialPrices).toEqual(missing ? ['PA'] : [])
    if (missing) expect(() => createYinhuiCustomerQuoteWorkbook(result, template)).toThrow(/请确认/)
    const output = parseXlsxWorkbook(buffer(createYinhuiCustomerQuoteWorkbook(result, template, {missingMaterialPricesConfirmed:missing})))
    expect(output.sheets[4]?.rows[7]?.[14]).toBe(missing ? '' : 24)
    expect(output.sheets[0]?.rows[31]?.[9]).toBeCloseTo(missing ? 8.9 : 11.3, 6)
  })
  it('applies the corrected sheet and fee mapping to approved P4 quotes in the matching gift-box layout', () => {
    const artifact = p4()
    artifact.productName = 'GOAL GO BOT #88753'
    ;(artifact.sections.engineering.calculation.line_breakdown as unknown[]).push({kind:'material',category:'hardware',item:'Frosted PC Sheet',quantity:1,amount_hkd:.5})
    ;(artifact.sections.sales.calculation.line_breakdown as unknown[]).push({kind:'packaging_material',item:'Documents Fee',quantity:1,amount_hkd:.15})
    const result = convertYinhuiP4InternalQuote(artifact, 'approved.xlsx')
    expect(result.quoteData).toMatchObject({templateId:'88753',packaging:'Gift Box'})
    expect(result.quoteData.mechanical).toContainEqual(expect.objectContaining({description:'Frosted PC Sheet',amountHkd:.55}))
    expect(result.quoteData.documentFees).toMatchObject([{amountHkd:.165,source:'业务/Documents Fee'}])
    expect(yinhuiTotals(result.quoteData).packaging).toBeCloseTo(3.3,8)
    const giftTemplate = buffer(readFileSync('public/templates/yinhui-88753-template.bin'))
    const output = parseXlsxWorkbook(buffer(createYinhuiCustomerQuoteWorkbook(result, giftTemplate)))
    expect(output.sheets[0]?.rows[29]?.[9]).toBeCloseTo(11.015,8)
    expect(output.sheets[0]?.rows[31]?.[7]).toBe(.165)
    expect(output.sheets[0]?.rows[31]?.[9]).toBeCloseTo(11.18,8)
  })
  it('keeps P4 customer, factory and unsupported-cost boundaries explicit', () => {
    const a = p4(); a.customer = 'BuzzBee'; expect(() => convertYinhuiP4InternalQuote(a,'a.xlsx')).toThrow(/客户/)
    a.customer = '银辉'; a.factoryAndWorkshop = 'huakang-a'; expect(() => convertYinhuiP4InternalQuote(a,'a.xlsx')).toThrow(/华兴/)
    a.factoryAndWorkshop = 'huaxing'; a.sections.sewing.calculation.totals = {total_hkd:2}; expect(() => convertYinhuiP4InternalQuote(a,'a.xlsx')).toThrow(/尚未覆盖/)
    a.sections.sewing.calculation.totals = {total_hkd:0}
    ;(a.sections.sales.calculation.line_breakdown as unknown[]).push({kind:'sales_testing_fee',total_usd:500,reference_only:true})
    expect(() => convertYinhuiP4InternalQuote(a,'a.xlsx')).toThrow(/测试费/)
    const b = p4(); b.sections.sales.calculation.totals = {additional_tax_hkd:2}
    expect(() => convertYinhuiP4InternalQuote(b,'b.xlsx')).toThrow(/附加税/)
    expect(isYinhuiCustomer('Silverlit')).toBe(true)
  })
})

import { describe, expect, it } from 'vitest'
import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { strFromU8, unzipSync } from 'fflate'
import { createDickieMapping, normalizeDickieMold } from '../dickieQuote'
import { normalizeInternalQuotePayload } from '../internalQuoteSectionPayload'
import { combineDickieV2, convertDickieV2, createDickieV2Workbook } from '../customerPriceConverters/dickieV2'
import { convertDickyInternalQuote, createDickyCustomerQuoteWorkbook } from '../customerPriceConverters/dicky'
import { prepareP4CustomerConversion } from '../customerPriceConverters/p4CustomerAdapter'
import { P4_ARTIFACT_TEMPLATE_VERSION, P4_SECTION_CODES, P4_STRUCTURED_DATA_SCHEMA_VERSION, type P4InternalQuoteArtifact } from '../customerPriceConverters/p4Artifact'
import { createXlsxWorkbook, parseXlsxWorkbook, type XlsxCellInput } from '../customerPriceConverters/xlsxLite'

const buffer = (bytes: Uint8Array) => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
function fixture() {
  const mapping = createDickieMapping()
  Object.assign(mapping, { quote_date: '2026-09-11', revision: 'A', item_number: '203747022', item_name: { zh: '城市巴士', en: 'Volvo City Bus' }, inner_pack: 1,
    customer_carton_enabled: true, customer_carton_cm: { length: 44.5, width: 36.5, height: 40 } })
  Object.assign(mapping.offers[0]!, { label: { zh: '中国正常价', en: 'China normal' }, moq: 5000, route_40: 'hk40', route_20: 'hk20', route_lcl: 'hk5t' })
  const artifact: P4InternalQuoteArtifact = {
    templateVersion: P4_ARTIFACT_TEMPLATE_VERSION, structuredDataSchemaVersion: P4_STRUCTURED_DATA_SCHEMA_VERSION,
    quoteNo: 'D-1', versionLabel: 'V1', customer: 'Dickie', quantity: 5000, productName: '城市巴士', factoryAndWorkshop: 'huaxing/华兴', formulaVersion: 'F1', referenceSnapshotId: 'R1', referenceSnapshot: {}, sections: {} as P4InternalQuoteArtifact['sections'],
    customerMapping: { version: 'dickie-v2', quote_id: 'IQ1', quote_no: 'D-1', version_label: 'V1', customer: 'Dickie', factory_id: 'huaxing', formula_version: 'F1', reference_snapshot_id: 'R1',
      prices: ['hk40', 'hk20', 'hk5t'].map((key, i) => ({ moq: 5000, route_key: key, price_hkd: [24.2, 24.5, 25.1][i], lift_hkd: 0 })) },
  }
  P4_SECTION_CODES.forEach(code => { artifact.sections[code] = { code, name: code, status: 'approved', revision: 1, calculationStatus: 'valid', dependencyStatus: 'current', calculationHash: `${code}-hash`, isRequired: true, payload: {}, calculation: { calculation_hash: `${code}-hash`, formula_version: 'F1', reference_snapshot_id: 'R1' } } })
  artifact.sections.sales.payload = { product_size_in: { length: 10, width: 4, height: 5 }, color_box_size_in: { length: 12, width: 5, height: 7 }, cartons: [{ length_in: 20, width_in: 15, height_in: 15, qty_per_carton: 6 }], shipping: { markup_tiers: [{ moq: 5000, markup_x: 1.16 }] }, customer_quote_fields: { dickie: { mapping } } }
  return { artifact, mapping }
}
function workbook(artifact: P4InternalQuoteArtifact) {
  const rows: XlsxCellInput[][] = [[], ['结构版本', P4_STRUCTURED_DATA_SCHEMA_VERSION], ['记录类型', '分段代码', '分段名称', '状态', 'revision', '计算状态', '依赖状态', '计算hash', '分片序号', '分片总数', 'JSON分片', '是否参与']]
  const add = (type: string, code: string, value: unknown) => rows.push([type, code, code, 'approved', 1, 'valid', 'current', `${code}-hash`, 1, 1, JSON.stringify(value), '是'])
  add('reference_snapshot', 'quote', {})
  add('customer_mapping', 'quote', artifact.customerMapping)
  for (const code of P4_SECTION_CODES) { add('payload', code, artifact.sections[code].payload); add('calculation', code, artifact.sections[code].calculation) }
  return buffer(createXlsxWorkbook([{ name: '报价明细', rows: [['PRIVATE SUPPLIER COST 9999'], ['城市巴士报价']] }, { name: '审批与版本', rows: [[], ['模板版本', P4_ARTIFACT_TEMPLATE_VERSION, '公式版本', 'F1'], ['参考快照', 'R1'], ['导出阶段', 'P4 最终业务放行'], ['边界说明', '最终业务放行完成，可交接客价转换台']] }, { name: '结构化数据', rows }]))
}

describe('Dickie approved internal quote mapping', () => {
  it.skipIf(!process.env.DICKIE_V2_SAMPLE_DIR)('converts the actual server-exported random demonstration', () => {
    const dir = process.env.DICKIE_V2_SAMPLE_DIR!
    const source = new Uint8Array(readFileSync(join(dir, 'Dickie-演示内部报价.xlsx')))
    const handoff = JSON.parse(readFileSync(join(dir, 'sample-handoff.json'), 'utf8'))
    const prepared = prepareP4CustomerConversion(buffer(source), handoff.file_name, 'dicky', {
      quoteNo: handoff.quote_no, versionLabel: handoff.version_label, customer: handoff.customer,
      formulaVersion: handoff.artifact_manifest.formula_version, referenceSnapshotId: handoff.artifact_manifest.reference_snapshot_id,
    })
    if (prepared.customerId !== 'dicky') throw new Error('Unexpected customer mapping')
    const result = prepared.result
    expect(result.v2Data!.products[0]!.offers).toHaveLength(3)
    expect(result.v2Data!.products[0]!.molds).toHaveLength(3)
    expect(result.v2Data!.products[0]!.image?.bytes.length).toBeGreaterThan(100)
    const output = createDickyCustomerQuoteWorkbook(result)
    const sheets = parseXlsxWorkbook(buffer(output)).sheets
    expect(sheets.map(s => s.name)).toEqual(['Quotation', '总表'])
    for (const p of result.v2Data!.products) for (const o of p.offers) for (const price of o.prices) {
      expect(sheets[0]!.rows.flat()).toContain(price)
      expect(sheets[1]!.rows.flat()).toContain(price)
    }
    writeFileSync(join(dir, 'Dickie-演示报客价.xlsx'), output)
    writeFileSync(join(dir, 'sample-result.json'), JSON.stringify(result.v2Data, null, 2))
  })
  it('reuses authoritative route prices and packing, keeps customer carton override separate', () => {
    const { artifact } = fixture()
    const result = convertDickieV2(artifact, 'bus.xlsx').v2Data!.products[0]!
    expect(result.offers[0]!.prices).toEqual([24.2, 24.5, 25.1])
    expect(result.dimensions).toBe('30.48 × 12.7 × 17.78')
    expect(result.cartonDimensions).toBe('44.5 × 36.5 × 40')
    expect(result.cartonCbm).toBe(.065)
    expect((artifact.sections.sales.payload.cartons as { length_in: number }[])[0]!.length_in).toBe(20)
  })
  it('supports product millimetres, confirmed price and ordered rounded adjustments', () => {
    const { artifact, mapping } = fixture()
    mapping.dimension_source = 'product'; mapping.dimension_unit = 'mm'
    Object.assign(mapping.offers[0]!, { price_source: 'confirmed', confirmed_40: 25, confirmed_20: 26, confirmed_lcl: 27, confirmed_reference: 'PRIVATE EMAIL', adjustments: [{ label: '地区', percent: 3, amount_hkd: 0 }, { label: '淡季', percent: -8, amount_hkd: -.1 }] })
    const result = convertDickieV2(artifact, 'bus.xlsx')
    expect(result.v2Data!.products[0]!.dimensions).toBe('254 × 101.6 × 127')
    expect(result.v2Data!.products[0]!.offers[0]!.prices).toEqual([23.6, 24.6, 25.5])
    const xml = Object.values(unzipSync(createDickyCustomerQuoteWorkbook(result))).map(b => strFromU8(b)).join('')
    expect(xml).not.toContain('PRIVATE EMAIL')
  })
  it.each(['missing-price', 'disabled-tier', 'lifting', 'missing-reference', 'invalid-date', 'missing-translation', 'factory', 'stale-reference'])('blocks incomplete or inconsistent input: %s', problem => {
    const { artifact, mapping } = fixture()
    if (problem === 'missing-price') artifact.customerMapping!.prices = []
    if (problem === 'disabled-tier') artifact.sections.sales.payload.shipping = { markup_tiers: [{ moq: 5000, include_in_output: false }] }
    if (problem === 'lifting') (artifact.customerMapping!.prices as { lift_hkd: number }[])[0]!.lift_hkd = .1
    if (problem === 'missing-reference') Object.assign(mapping.offers[0]!, { price_source: 'confirmed', confirmed_40: 20, confirmed_20: 21, confirmed_lcl: 22 })
    if (problem === 'invalid-date') mapping.quote_date = '2026-02-30'
    if (problem === 'missing-translation') mapping.remarks = [{ zh: '含电池', en: '' }]
    if (problem === 'factory') artifact.customerMapping!.factory_id = 'huakang_a'
    if (problem === 'stale-reference') artifact.customerMapping!.reference_snapshot_id = 'old'
    expect(() => convertDickieV2(artifact, 'bad.xlsx')).toThrow(/Dickie/)
  })
  it('roundtrips supplemental payload without changing common costs', () => {
    const { artifact, mapping } = fixture()
    const sales = normalizeInternalQuotePayload('sales', artifact.sections.sales.payload)
    expect(sales.customer_quote_fields.dickie.mapping).toEqual(mapping)
    const extra = normalizeDickieMold({ included: true, parts_en: 'Body', customer_price_hkd: 12000 })
    const engineering = normalizeInternalQuotePayload('engineering', { molds: [{ item: '车身', cost_rmb: 8000, dickie_export: extra }] })
    expect(engineering.molds[0]!.dickie_export).toEqual(extra)
    expect(engineering.molds[0]!.cost_rmb).toBe(8000)
  })
  it('accepts standalone controlled upload and handoff with identical results; leaks no source sheets', () => {
    const { artifact } = fixture(), bytes = workbook(artifact)
    const manual = convertDickyInternalQuote(bytes, 'released.xlsx')
    const handoff = prepareP4CustomerConversion(bytes, 'released.xlsx', 'dicky', { quoteNo: 'D-1', versionLabel: 'V1', customer: 'Dickie' })
    expect(handoff.result).toEqual(manual)
    const out = createDickyCustomerQuoteWorkbook(manual)
    const sheets = parseXlsxWorkbook(buffer(out)).sheets
    expect(sheets.map(s => s.name)).toEqual(['Quotation', '总表'])
    expect(sheets[0]!.rows.flat()).toContain('203747022\nVolvo City Bus')
    expect(sheets[1]!.rows.flat()).toContain('203747022\n城市巴士')
    expect(sheets[0]!.rows.flat()).toContain(24.2)
    expect(sheets[1]!.rows.flat()).toContain(24.2)
    expect(sheets[0]!.rows.flat().join(' ')).not.toContain('MOLD QUOTATION')
    const text = Object.values(unzipSync(out)).map(b => strFromU8(b)).join('')
    expect(text).not.toContain('PRIVATE SUPPLIER')
    expect(text).not.toContain('customer_mapping')
    expect(() => prepareP4CustomerConversion(bytes, 'x.xlsx', 'dicky', { customer: '银辉' })).toThrow()
  })
  it('exports 42 molds and repeated IDs in separate groups, with no 38-row truncation', () => {
    const { artifact, mapping } = fixture()
    mapping.include_molds = true
    mapping.first_shot = { zh: '45天', en: '45 days' }; mapping.finish = { zh: '75天', en: '75 days' }; mapping.lead_time_basis = { zh: '收到批准后', en: 'After approval' }
    artifact.sections.engineering.payload.molds = Array.from({ length: 42 }, (_, i) => ({ mold_no: `M${i % 21 + 1}`, chinese_name: `车身${i}`, material_type: 'ABS', mold_size: '30*35*30', mold_base_material: 'NAK80', cavity: '2', quantity: 1, cost_rmb: 77777,
      dickie_export: { included: true, parts_en: `Body ${i}`, group: { zh: i < 21 ? '车型甲' : '车型乙', en: i < 21 ? 'Car A' : 'Car B' }, customer_price_hkd: 10000 } }))
    const result = convertDickieV2(artifact, 'molds.xlsx')
    const sheet = parseXlsxWorkbook(buffer(createDickyCustomerQuoteWorkbook(result))).sheets[0]!
    expect(sheet.rows.flat()).toContain('Body 41')
    expect(sheet.rows.flat()).toContain(420000)
    expect(sheet.rows.flat()).not.toContain(77777)
    ;(artifact.sections.engineering.payload.molds as { mold_no: string }[])[1]!.mold_no = 'M1'
    expect(() => convertDickieV2(artifact, 'molds.xlsx')).toThrow('同组模号重复')
  })
  it('combines multiple products and rejects repeated identity or mismatched document headers', () => {
    const a = fixture(), b = fixture()
    b.artifact.customerMapping!.quote_id = 'IQ2'; b.mapping.item_number = 'SECOND'
    const first = convertDickieV2(a.artifact, '1.xlsx'), second = convertDickieV2(b.artifact, '2.xlsx')
    const merged = combineDickieV2([first, second])
    const sheet = parseXlsxWorkbook(buffer(createDickyCustomerQuoteWorkbook(merged))).sheets[1]!
    expect(sheet.rows.flat()).toContain('SECOND\n城市巴士')
    expect(() => combineDickieV2([first, first])).toThrow('重复合并')
    second.v2Data!.products[0]!.mapping.company = 'asia'
    expect(() => combineDickieV2([first, second])).toThrow('须一致')
  })
  it('writes valid drawing XML when carrying a product image and literal formula-like text', () => {
    const { artifact, mapping } = fixture()
    mapping.item_name.en = '=DO_NOT_EVALUATE'
    const result = convertDickieV2(artifact, 'image.xlsx')
    result.v2Data!.products[0]!.image = { bytes: new Uint8Array([1, 2, 3]), extension: 'png' }
    const zip = unzipSync(createDickieV2Workbook(result.v2Data!))
    for (const [name, bytes] of Object.entries(zip).filter(([p]) => p.endsWith('.xml') || p.endsWith('.rels'))) {
      expect(new DOMParser().parseFromString(strFromU8(bytes), 'application/xml').querySelector('parsererror'), name).toBeNull()
    }
    expect(strFromU8(zip['xl/worksheets/sheet1.xml']!)).not.toContain('<f>')
    expect(Object.keys(zip).filter(p => p.startsWith('xl/media/'))).toHaveLength(2)
    expect(strFromU8(zip['xl/drawings/drawing1.xml']!)).toContain('<xdr:col>10</xdr:col>')
  })
  it('preserves the supplied customer template layout, typography, colours and typed prices', () => {
    const { artifact, mapping } = fixture()
    mapping.remarks = [{ zh: '按客人样办', en: 'Based on customer sample' }]
    const zip = unzipSync(createDickyCustomerQuoteWorkbook(convertDickieV2(artifact, 'source.xlsx')))
    const xml = (path: string) => new DOMParser().parseFromString(strFromU8(zip[path]!), 'application/xml')
    const styles = xml('xl/styles.xml')
    const xfs = styles.querySelector('cellXfs')!.children
    const fonts = styles.querySelector('fonts')!.children
    const fills = styles.querySelector('fills')!.children
    for (const path of ['xl/worksheets/sheet1.xml', 'xl/worksheets/sheet2.xml']) {
      const sheet = xml(path)
      const cell = (ref: string) => sheet.querySelector(`c[r="${ref}"]`)!
      const style = (ref: string) => xfs[Number(cell(ref).getAttribute('s'))]!
      const font = (ref: string) => fonts[Number(style(ref).getAttribute('fontId'))]!
      expect(font('A1').querySelector('name')!.getAttribute('val')).toBe('宋体')
      expect(font('A2').querySelector('name')!.getAttribute('val')).toBe('Times New Roman')
      expect(font('A2').querySelector('sz')!.getAttribute('val')).toBe('14')
      expect(font('A1').querySelector('color')!.getAttribute('rgb')).toBe('FFFF0000')
      expect(fills[Number(style('A1').getAttribute('fillId'))]!.querySelector('fgColor')!.getAttribute('indexed')).toBe('42')
      expect(style('A1').querySelector('alignment')!.getAttribute('horizontal')).toBe('center')
      expect(font('A6').querySelector('u')).not.toBeNull()
      expect(font('A6').querySelector('color')!.getAttribute('rgb')).toBe('FF0000FF')
      expect(cell('C11').textContent).toBe('Units per Carton')
      expect(cell('K11').textContent).toBe('Image\n(图片)')
      expect(sheet.querySelector('row[r="12"]')!.getAttribute('ht')).toBe('70')
      expect(cell('H12').querySelector('v')!.textContent).toBe('24.2')
      const formatId = style('H12').getAttribute('numFmtId')
      expect(styles.querySelector(`numFmt[numFmtId="${formatId}"]`)!.getAttribute('formatCode')).toBe('"HK$"0.0')
      const discount = Array.from(sheet.querySelectorAll('c')).find(c => c.textContent?.includes('5%'))!
      const discountXf = xfs[Number(discount.getAttribute('s'))]!
      const yellow = fills[Number(discountXf.getAttribute('fillId'))]!.querySelector('fgColor')!
      expect(yellow.getAttribute('indexed') === '13' || yellow.getAttribute('rgb') === 'FFFFFF00').toBe(true)
      const merges = Array.from(sheet.querySelectorAll('mergeCell')).map(m => m.getAttribute('ref'))
      expect(merges).toContain('A1:K1')
      expect(merges).toContain('A6:K6')
      const priceCells = Array.from(sheet.querySelectorAll('c')).filter(c => ['4.8', '8.5', '5.8', '5.1'].includes(c.querySelector('v')?.textContent || ''))
      expect(priceCells.map(c => c.getAttribute('r')![0])).toEqual(['C', 'F', 'C', 'F'])
    }
    expect(xml('xl/worksheets/sheet2.xml').querySelector('col[min="2"]')!.getAttribute('width')).toBe('20.125')
    expect(Object.keys(zip).some(p => /externalLink|comments|vbaProject/.test(p))).toBe(false)
  })
})

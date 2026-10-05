import { normalizeInternalQuotePayload } from '../internalQuoteSectionPayload'
import { readFileSync, writeFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { strFromU8, unzipSync } from 'fflate'
import { convertBuzzBeeP4InternalQuote, buildBuzzBeeCustomerQuoteFileName } from '../customerPriceConverters/buzzbee'
import { createBuzzBeeTemplateWorkbook, buzzBeeTemplateProfiles } from '../customerPriceConverters/buzzbeeTemplate'
import { P4_SECTION_CODES, type P4InternalQuoteArtifact } from '../customerPriceConverters/p4Artifact'
import { stampPricingReference, type CustomerPricingSettings } from '../customerPriceConverters/pricingSettings'
import layouts from '../customerPriceConverters/buzzbeeTemplateLayouts.json'

function settings(): CustomerPricingSettings {
  const d = JSON.parse(readFileSync('shared/customerPriceDefaults.json', 'utf8')).buzzbee
  return { factory_id: 'huaxing', customer_id: 'buzzbee', revision: 1, snapshot_id: 'private-reference-1', materials: d.materials, rates: Object.fromEntries(Object.entries(d.rates).map(([k, v]) => [k, (v as {value:number}).value])), texts: {}, updated_at: '', updated_by_name: '' }
}
function artifact(): P4InternalQuoteArtifact {
  const sections = Object.fromEntries(P4_SECTION_CODES.map(code => [code, { code, name: code, status: 'approved', revision: 1, calculationStatus: 'valid', dependencyStatus: 'current', calculationHash: 'hash', isRequired: true, payload: {}, calculation: { line_breakdown: [], totals: { total_hkd: 0 } } }])) as P4InternalQuoteArtifact['sections']
  sections.molding.payload = { injection_lines: [{ item: '测试面壳', material: 'ABS', net_weight_g: 100, quantity: 3, sets: 2 }] }
  sections.molding.calculation = { line_breakdown: [{ kind: 'injection', molding_cost_hkd: 2, material_cost_hkd: 1 }] }
  sections.engineering.calculation = { line_breakdown: [
    { kind: 'material', item: '螺丝', quantity: 2, amount_hkd: 2 },
    { kind: 'material', item: '软子弹', quantity: 4, amount_hkd: 4 },
    { kind: 'material', item: '子弹吸塑', quantity: 1, amount_hkd: 3 },
  ] }
  sections.electronic.calculation = { quote_groups: [{ name: '声光组件整组', totals: { total_hkd: 12 }, line_breakdown: [{ item: 'IC', amount_hkd: 8 }, { item: '电阻', amount_hkd: 1 }] }], totals: { total_hkd: 12 } }
  sections.painting.calculation = { line_breakdown: [{ kind: 'painting_quick_labor', amount_hkd: 2 }, { kind: 'painting_quick_paint', amount_hkd: 1 }, { kind: 'painting_quick_paint_tax', amount_hkd: .13 }] }
  sections.assembly.calculation = { totals: { assembly_hkd: 3, packaging_hkd: 1 } }
  sections.sewing.calculation = { totals: { clothes_hkd: 2 } }
  sections.sales.payload = { cartons: [{ length_in: 10, width_in: 12, height_in: 14, qty_per_carton: 4 }], customer_quote_fields: { buzzbee: { color_box_tiers: [{ quote_price_hkd: 8, moq: 'MOQ3000' }, { quote_price_hkd: 6, moq: 'MOQ5000' }] } } }
  sections.sales.calculation = { line_breakdown: [{ kind: 'carton', per_piece_hkd: 2, cuft: 10*12*14/1728 }, { kind: 'packaging_material', category: 'color_box_inner_card', item: '彩盒', amount_hkd: 99 }] }
  return { templateVersion: 'internal-quote-p4-v2', structuredDataSchemaVersion: 'internal-quote-structured-data-v1', quoteNo: 'IQ-TEST', quoteDate: '2026-09-02', versionLabel: 'R2', customer: 'BuzzBee', quantity: 3000, productName: '测试产品', factoryAndWorkshop: 'huaxing/华兴', formulaVersion: 'v1', referenceSnapshotId: 'ref1', referenceSnapshot: {}, sections }
}
function xml(bytes: Uint8Array, path = 'xl/worksheets/sheet1.xml') { return strFromU8(unzipSync(bytes)[path]!) }
function cell(doc: Document, ref: string) { return Array.from(doc.getElementsByTagName('c')).find(c => c.getAttribute('r') === ref)! }
function document(bytes: Uint8Array) { return new DOMParser().parseFromString(xml(bytes), 'application/xml') }

describe('BuzzBee maintained pricing and original templates', () => {
  it('retains explicit BuzzBee input mapping and template fields across save normalization', () => {
    const sales = normalizeInternalQuotePayload('sales', { customer_quote_fields: { buzzbee: { template_profile: 'laser', notes: '客户功能说明', color_box_tiers: [{ quote_price_hkd: 10, moq: '3000' }] } } })
    expect(sales.customer_quote_fields.buzzbee).toMatchObject({ template_profile: 'laser', notes: '客户功能说明', color_box_tiers: [{ quote_price_hkd: 10, moq: '3000' }] })
    expect(normalizeInternalQuotePayload('molding', { injection_lines: [{ material: 'C-ABS', buzzbee_material: 'C-ABS镜片' }] }).injection_lines[0]).toMatchObject({ material: 'C-ABS', buzzbee_material: 'C-ABS镜片' })
  })
  it('uses whole-set weights, internal molding labor, grouped electronics and the agreed fee sequence', () => {
    const p = settings(); p.rates.injection_multiplier = 1.2
    const result = convertBuzzBeeP4InternalQuote(artifact(), 'approved.xlsx', p)
    const d = result.sheets[0]!.quoteData
    expect(d.injectionRows[0]).toMatchObject({ weight: 100, pricePerKg: 16.7, amount: 1.67, beer: 7.2 })
    expect(d.purchaseRows.find(r => r.desc === '声光组件整组')).toMatchObject({ qty: 1, amount: 12.6 })
    expect(d.purchaseRows.map(r => r.desc)).not.toContain('IC')
    expect(d.purchaseRows.find(r => r.desc === '子弹吸塑')?.amount).toBe(3.15)
    expect(d.purchaseRows.find(r => r.desc === '纸箱')?.amount).toBe(2.06)
    expect(d.purchaseRows.find(r => r.desc.includes('车衣'))?.amount).toBe(2.1)
    expect(d.additionalParts).toHaveLength(1)
    expect(d.additionalTotal).toBe(4.2)
    expect(d.breakdown.process).toBeCloseTo(7.13)
    expect(d.breakdown.tran).toBe(0)
    expect(d.breakdown.total).toBe(Math.round(d.breakdown.sub * 1.1 * 100) / 100)
    expect(d.exftyCost).toBe(d.breakdown.total + 4.2)
    expect(d.usd).toBe(d.exftyCost / 7.75)
    expect(d.colorBox).toMatchObject({ price1: 8, fsc1: 2.06 })
    expect(buildBuzzBeeCustomerQuoteFileName(result)).toBe('R2 RR ITEM 测试产品（2026-09-02）.xlsx')
    const other = settings(); other.rates.detail_multiplier = 1; other.materials.find(m => m.material === 'ABS')!.price = 20
    expect(convertBuzzBeeP4InternalQuote(artifact(), 'other.xlsx', other).sheets[0]!.quoteData.injectionAmount).toBe(2)
    expect(d.injectionAmount).toBe(1.67)
    expect(d.purchaseRows.find(r => r.desc === '螺丝')?.amount).toBe(2.1)
  })
  it('requires explicitly maintained material names and never infers special lens prices from product names', () => {
    const a = artifact(); a.productName = '警察眼镜'
    const row = (a.sections.molding.payload.injection_lines as Array<Record<string, unknown>>)[0]!
    row.material = 'C-ABS'; row.buzzbee_material = 'C-ABS镜片'
    const p = settings()
    expect(convertBuzzBeeP4InternalQuote(a, 'a.xlsx', p).sheets[0]!.quoteData.injectionRows[0]!.pricePerKg).toBe(23.1)
    row.buzzbee_material = '未维护材料'
    expect(() => convertBuzzBeeP4InternalQuote(a, 'a.xlsx', p)).toThrow(/材料|料价/)
  })
  it('keeps fractional purchase usage amounts intact', () => {
    const a = artifact()
    a.sections.engineering.calculation.line_breakdown = [{ kind: 'material', item: '丝带', quantity: .5, amount_hkd: 10 }]
    const d = convertBuzzBeeP4InternalQuote(a, 'a.xlsx', settings()).sheets[0]!.quoteData
    expect(d.purchaseRows.find(r => r.desc === '丝带')).toMatchObject({ qty: .5, price: 21, amount: 10.5 })
  })
  for (const profile of buzzBeeTemplateProfiles) it(`preserves ${profile.id} styles, geometry, image anchor and formulas`, () => {
    const p = settings(), result = convertBuzzBeeP4InternalQuote(artifact(), 'a.xlsx', p), d = result.sheets[0]!.quoteData
    d.templateProfile = profile.id
    d.image = { extension: 'png', bytes: Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jZ1kAAAAASUVORK5CYII='), c => c.charCodeAt(0)) }
    if (profile.id === 'laser') d.notes = '测试功能说明\n第二行说明'
    const template = new Uint8Array(readFileSync(`public/templates/buzzbee-${profile.id}-template.bin`))
    const output = stampPricingReference(createBuzzBeeTemplateWorkbook(result, template), p)
    expect(xml(output, 'xl/styles.xml')).toBe(xml(template, 'xl/styles.xml'))
    const before = document(template), after = document(output)
    for (const name of ['cols', 'mergeCells', 'pageMargins', 'pageSetup']) expect(after.getElementsByTagName(name)[0]?.outerHTML).toBe(before.getElementsByTagName(name)[0]?.outerHTML)
    for (const ref of ['A4', 'C7', 'G7', 'J35', 'J37']) expect(cell(after, ref).getAttribute('s')).toBe(cell(before, ref).getAttribute('s'))
    expect(cell(after, 'E7').getElementsByTagName('f')[0]!.textContent).toBe('C7*D7/1000')
    expect(cell(after, 'J37').getElementsByTagName('f')[0]!.textContent).toBe('ROUND(J34+J35,2)')
    expect(cell(after, 'J46').getElementsByTagName('f')[0]!.textContent).toBe('J44/7.75')
    const layout = layouts[profile.id]
    expect(cell(after, `F${layout.colorFirst}`).getElementsByTagName('f')[0]!.textContent).toBe(`8/B${layout.dimensionHeader + 6}`)
    const anchor = new DOMParser().parseFromString(xml(output, 'xl/drawings/drawing1.xml'), 'application/xml')
    const originalAnchor = new DOMParser().parseFromString(layout.drawing, 'application/xml')
    expect(anchor.documentElement.textContent).toBe(originalAnchor.documentElement.textContent)
    const zip = unzipSync(output)
    expect(zip['xl/media/product1.png']).toEqual(d.image.bytes)
    expect(xml(output, 'docProps/custom.xml')).toContain('private-reference-1')
    expect(xml(output, 'docProps/custom.xml')).not.toMatch(/materials|rates|16\.7/)
    expect(Object.keys(zip)).not.toContain('xl/sharedStrings.xml')
    expect(xml(output)).not.toMatch(/心形爆炸|杨|Cowboy|Laser|供应商/)
    if (process.env.BUZZBEE_VERIFY_DIR) writeFileSync(`${process.env.BUZZBEE_VERIFY_DIR}/${profile.id}.xlsx`, output)
  })
  it('extends injection, purchase and additional rows without omitting them from totals', () => {
    const result = convertBuzzBeeP4InternalQuote(artifact(), 'a.xlsx', settings()), d = result.sheets[0]!.quoteData
    d.injectionRows = Array.from({length:22}, (_,i) => ({ ...d.injectionRows[0]!, name:`M${i}` }))
    d.purchaseRows = Array.from({length:40}, (_,i) => ({ ...d.purchaseRows[0]!, desc:`P${i}` }))
    d.additionalParts = Array.from({length:3}, (_,i) => ({ ...d.additionalParts[0]!, desc:`子弹${i}` }))
    const output = createBuzzBeeTemplateWorkbook(result, new Uint8Array(readFileSync('public/templates/buzzbee-standard-template.bin')))
    const doc = document(output)
    const f = (r:string) => cell(doc,r).getElementsByTagName('f')[0]!.textContent
    expect(f('E29')).toBe('SUM(E7:E28)')
    expect(f('D73')).toBe('SUM(D33:D72)')
    expect(f('J50')).toBe('SUM(J41:J49)')
    const refs = Array.from(doc.getElementsByTagName('c')).map(c => c.getAttribute('r'))
    expect(new Set(refs).size).toBe(refs.length)
    if (process.env.BUZZBEE_VERIFY_DIR) writeFileSync(`${process.env.BUZZBEE_VERIFY_DIR}/expanded.xlsx`, output)
  })
})

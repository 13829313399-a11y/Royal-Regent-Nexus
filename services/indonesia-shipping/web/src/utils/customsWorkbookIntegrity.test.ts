import { readFileSync, writeFileSync } from 'node:fs'
import { expect, it } from 'vitest'
import JSZip from 'jszip'
import * as XLSX from 'xlsx-js-style'
import { DOMParser, XMLSerializer } from '@xmldom/xmldom'
import { buildCustomsWorkbook, refreshCategoryAmountCaches } from './customsExport'

const ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
const template = (name: string) => Uint8Array.from(readFileSync(new URL(`../../public/${name}`, import.meta.url))).buffer
const indonesia = template('template-customs.xlsx')

async function worksheetParts(zip: JSZip) {
  const parser = new DOMParser()
  const workbook = parser.parseFromString((await zip.file('xl/workbook.xml')!.async('string')).replace(/^\uFEFF/, ''), 'application/xml')
  const rels = parser.parseFromString((await zip.file('xl/_rels/workbook.xml.rels')!.async('string')).replace(/^\uFEFF/, ''), 'application/xml')
  const targets = new Map(Array.from(rels.getElementsByTagName('Relationship')).map(node => [node.getAttribute('Id'), node.getAttribute('Target')!]))
  return new Map(Array.from(workbook.getElementsByTagNameNS(ns, 'sheet')).map(sheet => {
    const target = targets.get(sheet.getAttribute('r:id'))!
    return [sheet.getAttribute('name')!, target.startsWith('/') ? target.slice(1) : target.startsWith('xl/') ? target : `xl/${target}`]
  }))
}
const xmlAttributes = (node: Element) => Object.fromEntries(Array.from(node.attributes)
  .filter(attribute => attribute.name !== 'r:id').map(attribute => [attribute.name, attribute.value]))

async function withScopedNames(buffer: ArrayBuffer) {
  const zip = await JSZip.loadAsync(buffer)
  const doc = new DOMParser().parseFromString(await zip.file('xl/workbook.xml')!.async('string'), 'application/xml')
  const sheets = Array.from(doc.getElementsByTagNameNS(ns, 'sheet')).map(sheet => sheet.getAttribute('name')!)
  const names = doc.getElementsByTagNameNS(ns, 'definedNames')[0]
  const add = (name: string, ref: string, scope?: number) => {
    const item = doc.createElementNS(ns, 'definedName')
    item.setAttribute('name', name)
    if (scope != null) item.setAttribute('localSheetId', String(scope))
    item.textContent = ref
    names.appendChild(item)
  }
  const driver = sheets.indexOf('司机资料')
  const sourceSheets = Array.from(doc.getElementsByTagNameNS(ns, 'sheet'))
  sourceSheets[driver].setAttribute('state', 'hidden')
  sourceSheets[1].setAttribute('state', 'hidden') // Renaming the main sheet must keep its metadata attached.
  add('QA_Driver', "'司机资料'!$A$1", driver)
  add('_xlnm.Print_Area', "'司机资料'!$A$1:$E$5", driver)
  add('_xlnm.Print_Titles', "'司机资料'!$1:$2", driver)
  add('QA_MissingSheet', "'Removed worksheet'!$A$1")
  add('QA_InvalidScope', '1', 999)
  const removed = sheets.indexOf('出货地址')
  if (removed >= 0) add('QA_Removed', '1', removed)
  zip.file('xl/workbook.xml', new XMLSerializer().serializeToString(doc))
  return zip.generateAsync({ type: 'arraybuffer' })
}

it.each([
  ['rri', 'RRI', false], ['rrm', 'RRM', false], ['rrm', 'RRM', true], ['', 'RRI', false],
] as const)('真实模板 %s / %s / 印尼=%s 导出保留有效名称并同步打印范围和金额缓存', async (kind, customer, indo) => {
  const buffer = await withScopedNames(kind ? template(`template-customs-${kind}.xlsx`) : indonesia)
  const base = { currency: 'US$', qty_per_carton: '10', bl_head: indo ? 'PT QA Indonesia' : '', customs_company: '甲报关公司' }
  const items = [
    { ...base, material_id: 1, qty: 30, kg: 30, price: 2.5, purchase_charge_ratio: 0.96, cartons: 3, supplier: '甲供应商', contract_no: 'QA-C1' },
    { ...base, material_id: 2, qty: 10, kg: 10, price: 4, cartons: 1, supplier: '乙供应商', contract_no: 'QA-C1' },
    { ...base, material_id: 3, qty: 20, kg: 20, price: 2.5, purchase_charge_ratio: 0.96, cartons: 2, supplier: '甲供应商', contract_no: 'QA-C2', customs_company: '乙报关公司' },
  ]
  const materials = new Map(items.map(item => [item.material_id, {
    id: item.material_id, name_zh: `验收物料${item.material_id}`, name_en: `QA Material ${item.material_id}`,
    product_code: `QA-${item.material_id}`, unit_kg: 'PCE', net_per_pc: 0.1, weight_per_carton: 1.2,
    length: 20, width: 10, height: 5,
  }]))
  const result = await buildCustomsWorkbook({ templateBuffer: buffer, indonesiaTemplateBuffer: indonesia,
    items, materials, productHs: new Map(), images: new Map(), form: { customer, containerNo: "QA-O'NEIL", rate: 1 } })
  const bytes = await result.arrayBuffer()
  const zip = await JSZip.loadAsync(bytes)
  const doc = new DOMParser().parseFromString(await zip.file('xl/workbook.xml')!.async('string'), 'application/xml')
  const sheetNames = Array.from(doc.getElementsByTagNameNS(ns, 'sheet')).map(sheet => sheet.getAttribute('name')!)
  const names = Array.from(doc.getElementsByTagNameNS(ns, 'definedName'))
  const driverIndex = sheetNames.indexOf('司机资料')
  const outputSheets = Array.from(doc.getElementsByTagNameNS(ns, 'sheet'))
  expect(outputSheets[driverIndex].getAttribute('state')).toBe('hidden')
  expect(outputSheets[sheetNames.indexOf("QA-O'NEIL")].getAttribute('state')).toBe('hidden')
  const reserved = outputSheets.find(sheet => sheet.getAttribute('name') === 'WpsReserved_CellImgList')
  if (reserved && kind) expect(reserved.getAttribute('state')).toBe('veryHidden')
  if (reserved && !kind) expect(reserved.getAttribute('state') || 'visible').toBe('visible')
  for (const defined of names) {
    expect(defined.textContent).not.toContain('#REF!')
    expect(defined.textContent).not.toMatch(/WHSU\d+/)
    const scope = defined.getAttribute('localSheetId')
    if (scope != null && scope !== '') expect(Number(scope)).toBeLessThan(sheetNames.length)
  }
  for (const [name, ref] of [
    ['QA_Driver', "'司机资料'!$A$1"], ['_xlnm.Print_Area', "'司机资料'!$A$1:$E$5"], ['_xlnm.Print_Titles', "'司机资料'!$1:$2"],
  ]) {
    const defined = names.find(item => item.getAttribute('name') === name && item.getAttribute('localSheetId') === String(driverIndex))
    expect(defined?.textContent).toBe(ref)
  }
  expect(names.some(item => /^QA_(MissingSheet|InvalidScope|Removed)$/.test(item.getAttribute('name') || ''))).toBe(false)
  const areas = names.filter(item => item.getAttribute('name') === '_xlnm.Print_Area')
  for (const area of areas) {
    const owner = sheetNames[Number(area.getAttribute('localSheetId'))]
    expect(area.textContent?.startsWith(`'${owner.replace(/'/g, "''")}'!`) || area.textContent?.startsWith(`${owner}!`)).toBe(true)
  }
  if (kind) {
    expect(areas.some(area => area.textContent?.startsWith("'QA-O''NEIL'!"))).toBe(true)
    expect(areas.some(area => area.textContent?.startsWith("'装箱单'!"))).toBe(true)
  }
  const wb = XLSX.read(bytes, { type: 'array', cellFormula: true })
  const reservedIndex = wb.SheetNames.indexOf('WpsReserved_CellImgList')
  if (reservedIndex >= 0) expect(wb.Workbook?.Sheets?.[reservedIndex].Hidden || 0).toBe(kind ? 2 : 0)
  const main = wb.Sheets["QA-O'NEIL"]
  // Two invoice groups, with one supplier spread over noncontiguous rows.
  expect(main.AB4).toMatchObject({ f: 'SUM(AA4:AA5)', v: 112 })
  expect(main.AB6).toMatchObject({ f: 'SUM(AA6)', v: 48 })
  expect(main.AQ4).toMatchObject({ f: 'SUM(AP4,AP6)', v: 120 })
  expect(main.AQ5).toMatchObject({ f: 'SUM(AP5)', v: 40 })
  expect(main.L8).toMatchObject({ f: 'SUM(L4:L6)', v: 60 })
  expect(main.Q8.v).toBeCloseTo(6)
  expect(main.P8.v).toBeCloseTo(7.2)
  expect(main.AT8.v).toBe(6)
  expect(wb.Sheets['司机资料']).toBeDefined()
}, 60000)

// Native Excel validates the ordered worksheet children, unlike permissive XML readers.
const worksheetOrder = ('sheetPr dimension sheetViews sheetFormatPr cols sheetData sheetCalcPr sheetProtection protectedRanges scenarios autoFilter sortState dataConsolidate customSheetViews mergeCells phoneticPr conditionalFormatting dataValidations hyperlinks printOptions pageMargins pageSetup headerFooter rowBreaks colBreaks customProperties cellWatches ignoredErrors smartTags drawing legacyDrawing legacyDrawingHF picture oleObjects controls webPublishItems tableParts extLst').split(' ')

it.each(['rri', 'rrm', 'indonesia'].flatMap(kind => ['single', 'multiple', 'empty'].map(scenario => [kind, scenario])))
('native Excel structure and category caches: %s / %s', async (kind, scenario) => {
  const items = scenario === 'empty' ? [] : [
    { material_id: 1, qty: 30, kg: 30, price: 2.4, currency: 'US$', cartons: 3, supplier: 'QA Supplier', customs_company: 'QA Company' },
    ...(scenario === 'multiple' ? [
      { material_id: 2, qty: 10, kg: 10, price: 4, currency: 'US$', cartons: 1, supplier: 'QA Supplier', customs_company: 'QA Company' },
      { material_id: 3, qty: 5, kg: 5, price: 2, currency: 'US$', cartons: 1, supplier: 'QA Supplier', customs_company: 'QA Company' },
    ] : []),
  ]
  const materials = new Map(items.map(item => [item.material_id, {
    id: item.material_id, name_zh: `QA Material ${item.material_id}`, product_code: `QA-${item.material_id}`,
    category: item.material_id === 2 ? '工具' : '纸箱类', unit_kg: 'PCE', net_per_pc: 0.1,
    weight_per_carton: 1.2, length: 20, width: 10, height: 5,
  }]))
  const templateBuffer = kind === 'indonesia' ? indonesia : template(`template-customs-${kind}.xlsx`)
  const originalCategory = XLSX.read(templateBuffer, { type: 'array', cellFormula: true }).Sheets['类别金额']
  const output = await buildCustomsWorkbook({
    templateBuffer,
    items, materials, productHs: new Map(), images: new Map(),
    form: { customer: kind === 'rrm' ? 'RRM' : 'RRI', containerNo: 'QA-RRI-1109', rate: 1 },
  })
  const bytes = await output.arrayBuffer()
  const zip = await JSZip.loadAsync(bytes)
  const styles = new DOMParser().parseFromString(await zip.file('xl/styles.xml')!.async('string'), 'application/xml')
  const borderOrder = ['start', 'end', 'left', 'right', 'top', 'bottom', 'diagonal', 'vertical', 'horizontal']
  for (const border of Array.from(styles.getElementsByTagNameNS(ns, 'border'))) {
    const edges = Array.from(border.childNodes).filter(node => node.nodeType === 1).map(node => node.localName!)
    const positions = edges.map(edge => borderOrder.indexOf(edge))
    expect(positions, `${kind}: border ${edges.join(', ')}`).toEqual([...positions].sort((a, b) => a - b))
  }
  for (const path of Object.keys(zip.files).filter(path => /^xl\/worksheets\/sheet\d+\.xml$/.test(path))) {
    const xml = await zip.file(path)!.async('string')
    expect(xml, `${kind}: ${path} retains its cell table`).not.toContain('<!--nexus-print-cell-table-->')
    const root = new DOMParser().parseFromString(xml, 'application/xml').documentElement!
    const children = Array.from(root.childNodes).filter(node => node.nodeType === 1).map(node => node.localName)
    const order = children.map(tag => worksheetOrder.indexOf(tag!)).filter(index => index >= 0)
    expect(order, `${kind}: ${path} (${children.join(', ')})`).toEqual([...order].sort((a, b) => a - b))
    for (const merges of Array.from(root.getElementsByTagNameNS(ns, 'mergeCells')))
      expect(merges.getElementsByTagNameNS(ns, 'mergeCell').length, `${kind}: ${path} must omit empty mergeCells`).toBeGreaterThan(0)
  }
  if (scenario === 'single') {
    const originalZip = await JSZip.loadAsync(templateBuffer)
    const originals = await worksheetParts(originalZip), outputs = await worksheetParts(zip)
    const adaptiveNames = ['销售合同', '装箱单 (2)', '草稿大单-1', '司机资料']
    const oldMain = [...originals.keys()].find(name => !outputs.has(name))!
    for (const [sourceName, sourcePath] of originals) {
      const name = sourceName === oldMain ? 'QA-RRI-1109' : sourceName
      if (adaptiveNames.includes(name) || !outputs.has(name)) continue
      const parser = new DOMParser()
      const original = parser.parseFromString((await originalZip.file(sourcePath)!.async('string')).replace(/^\uFEFF/, ''), 'application/xml')
      const output = parser.parseFromString(await zip.file(outputs.get(name)!)!.async('string'), 'application/xml')
      for (const tag of ['pageSetup', 'pageSetUpPr', 'printOptions', 'pageMargins', 'rowBreaks', 'colBreaks']) {
        const expected = original.getElementsByTagNameNS(ns, tag)[0]
        if (!expected) continue
        const actual = output.getElementsByTagNameNS(ns, tag)[0]
        expect(actual, `${kind}: preserve ${name} ${tag}`).toBeDefined()
        expect(xmlAttributes(actual as unknown as Element)).toEqual(xmlAttributes(expected as unknown as Element))
      }
      expect(output.getElementsByTagNameNS(ns, 'pageSetup')[0]?.hasAttributeNS('http://schemas.openxmlformats.org/officeDocument/2006/relationships', 'id') || false).toBe(false)
    }
    for (const name of ['销售合同', '装箱单 (2)', '草稿大单-1', '司机资料']) {
      if (!originals.has(name) || !outputs.has(name)) continue
      const parser = new DOMParser()
      const original = parser.parseFromString((await originalZip.file(originals.get(name)!)!.async('string')).replace(/^\uFEFF/, ''), 'application/xml')
      const output = parser.parseFromString(await zip.file(outputs.get(name)!)!.async('string'), 'application/xml')
      for (const tag of ['pageSetup', 'pageSetUpPr', 'printOptions', 'rowBreaks']) {
        const expected = original.getElementsByTagNameNS(ns, tag)[0]
        if (!expected) continue
        const actual = output.getElementsByTagNameNS(ns, tag)[0]
        expect(actual, `${kind}: ${name} ${tag}`).toBeDefined()
        const expectedAttributes = xmlAttributes(expected as unknown as Element)
        if (tag === 'pageSetup') {
          delete expectedAttributes.scale
          expectedAttributes.fitToWidth = '1'
          expectedAttributes.fitToHeight = '0'
        } else if (tag === 'pageSetUpPr') expectedAttributes.fitToPage = '1'
        expect(xmlAttributes(actual as unknown as Element)).toEqual(expectedAttributes)
      }
      expect(xmlAttributes(output.getElementsByTagNameNS(ns, 'pageSetup')[0] as unknown as Element)).toMatchObject({ fitToWidth: '1', fitToHeight: '0' })
      expect(output.getElementsByTagNameNS(ns, 'pageSetup')[0].hasAttribute('scale')).toBe(false)
      expect(output.getElementsByTagNameNS(ns, 'pageSetUpPr')[0].getAttribute('fitToPage')).toBe('1')
      expect(output.getElementsByTagNameNS(ns, 'colBreaks').length).toBe(0)
      expect(output.getElementsByTagNameNS(ns, 'pageSetup')[0]?.hasAttributeNS('http://schemas.openxmlformats.org/officeDocument/2006/relationships', 'id') || false).toBe(false)
      if (kind === 'rri' && name === '销售合同')
        expect(xmlAttributes(output.getElementsByTagNameNS(ns, 'pageSetup')[0] as unknown as Element)).toMatchObject({ paperSize: '9', orientation: 'portrait' })
    }
  }
  const wb = XLSX.read(bytes, { type: 'array', cellFormula: true })
  const category = wb.Sheets['类别金额']
  expect(category).toBeDefined()
  const expected = new Map<string, number>([['纸箱类', scenario === 'empty' ? 0 : scenario === 'multiple' ? 82 : 72], ['工具', scenario === 'multiple' ? 40 : 0]])
  let cachedTotal = 0
  const seen = new Set<string>()
  for (let row = 4; row <= 18; row++) {
    if (!originalCategory[`C${row}`]?.f) continue // RRM deliberately leaves C6 blank.
    expect(category[`C${row}`].f).toContain('SUMIFS(')
    const originalRanges = originalCategory[`C${row}`].f!.match(/\$?(?:AA|I)\$?4:\$?(?:AA|I)\$?\d+/g)
    if (originalRanges) expect(category[`C${row}`].f!.match(/\$?(?:AA|I)\$?4:\$?(?:AA|I)\$?\d+/g)).toEqual(originalRanges)
    const label = String(category[`B${row}`].v)
    seen.add(label)
    expect(category[`C${row}`].v, `${kind}: ${label}`).toBeCloseTo(expected.get(label) || 0)
    cachedTotal += Number(category[`C${row}`].v)
  }
  expect(seen.has('纸箱类') && seen.has('工具')).toBe(true)
  const total = scenario === 'empty' ? 0 : scenario === 'multiple' ? 122 : 72
  expect(cachedTotal).toBe(total)
  if (originalCategory.C19?.f) expect(category.C19).toMatchObject({ f: originalCategory.C19.f, v: total })
  else expect(category.C19).toBeUndefined() // Keep the legacy template's original layout.
  if (kind === 'rri' && scenario === 'single' && process.env.INDONESIA_CUSTOMS_QA_OUTPUT)
    writeFileSync(process.env.INDONESIA_CUSTOMS_QA_OUTPUT, Buffer.from(bytes))
  if (kind === 'indonesia' && scenario === 'single' && process.env.INDONESIA_CUSTOMS_QA_LEGACY_OUTPUT)
    writeFileSync(process.env.INDONESIA_CUSTOMS_QA_LEGACY_OUTPUT, Buffer.from(bytes))
}, 60000)

it.each([997, 998, 10000])('keeps legacy category SUMIFS ranges and caches consistent for %s details', count => {
  // Exercise the real template's formulas independently of its separate
  // 33-line supplier-document capacity rule.
  const wb = XLSX.read(indonesia, { type: 'array', cellFormula: true })
  const main: XLSX.WorkSheet = {}
  for (let index = 0; index < count; index++) {
    main[`I${index + 4}`] = { t: 's', v: '纸箱类' }
    main[`AA${index + 4}`] = { t: 'n', v: 1 }
  }
  refreshCategoryAmountCaches(wb, main, count)
  const category = wb.Sheets['类别金额']
  const row = Array.from({ length: 15 }, (_, index) => index + 4).find(row => category[`B${row}`]?.v === '纸箱类')!
  const cell = category[`C${row}`]
  expect(cell.v).toBe(count)
  expect(cell.f).toContain(`!$AA$4:$AA$${Math.max(1000, count + 3)}`)
  expect(cell.f).toContain(`!$I$4:$I$${Math.max(1000, count + 3)}`)
  // Independently evaluate the written formula's bounded source range.
  const last = Number(/\$AA\$4:\$AA\$(\d+)/.exec(cell.f!)![1])
  let recalculated = 0
  for (let source = 4; source <= last; source++)
    if (main[`I${source}`]?.v === '纸箱类') recalculated += Number(main[`AA${source}`]?.v) || 0
  expect(recalculated).toBe(cell.v)
}, 60000)

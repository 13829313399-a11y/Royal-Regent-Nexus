import { describe, expect, it } from 'vitest'
import JSZip from 'jszip'
import * as XLSX from 'xlsx-js-style'
import { DOMParser, XMLSerializer } from '@xmldom/xmldom'
import { applyPurchaseContractPrintLayout, buildPurchaseContractWorkbook, combinePurchaseContracts, setPurchaseContractLineAmounts } from './purchaseContractWorkbook'

const ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
const parse = (xml: string) => new DOMParser().parseFromString(xml, 'application/xml')
const serialize = (node: Parameters<XMLSerializer['serializeToString']>[0]) => new XMLSerializer().serializeToString(node)

function contract() {
  const rows: (string | number)[][] = Array.from({ length: 26 }, () => [])
  rows[0] = ['QA COMPANY']
  rows[3] = ['购销合同']
  rows[5] = ['合同编号：QA-PO-1109']
  rows[8] = ['货号', '货品名称', '规格型号', '数量', '单位', '单价', '金额', '备注', '英文名称', '物料编码']
  rows[9] = ['QA-PRODUCT', '验收物料', 'QA', 120, 'PCE', 2.5, 300, '验收', 'QA Material', 'QA-CODE']
  rows[25] = ['QA SIGNATURE']
  const ws = XLSX.utils.aoa_to_sheet(rows)
  setPurchaseContractLineAmounts(ws, 10, 120, 300, 2, 'PCE')
  ws['!cols'] = [12, 22, 16, 10, 8, 20, 13, 18, 32, 16].map(wch => ({ wch }))
  ws['!rows'] = rows.map((_, index) => ({ hpt: index === 9 ? 45 : 24 }))
  ws['!merges'] = [0, 3, 25].map(row => ({ s: { r: row, c: 0 }, e: { r: row, c: 7 } }))
  ws.I10.s = ws.J10.s = { fill: { fgColor: { rgb: 'FFFF00' } } }
  ws.A1.s = { font: { sz: 22, bold: true }, alignment: { horizontal: 'center' } }
  return ws
}

function single(name = '购销合同') {
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, contract(), name)
  return wb
}

async function inspect(buffer: ArrayBuffer) {
  const zip = await JSZip.loadAsync(buffer)
  const workbook = parse(await zip.file('xl/workbook.xml')!.async('string'))
  const sheets = await Promise.all(Array.from(workbook.getElementsByTagNameNS(ns, 'sheet')).map(async (_, index) => parse(await zip.file(`xl/worksheets/sheet${index + 1}.xml`)!.async('string'))))
  const names = Array.from(workbook.getElementsByTagNameNS(ns, 'definedName'))
  return { zip, workbook, sheets, names }
}

describe('采购合同打印', () => {
  it('单张合同全部 A:J 列横向一页，保留纵向自动分页、金额、黄色辅助字段与样式', async () => {
    const wb = single()
    const original = await inspect(XLSX.write(wb, { type: 'array', bookType: 'xlsx' }))
    // SheetJS mutates style objects while serializing; compare two fresh equivalent books.
    const blob = await buildPurchaseContractWorkbook(single())
    const buffer = await blob.arrayBuffer()
    const exported = await inspect(buffer)
    const doc = exported.sheets[0]
    const setup = doc.getElementsByTagNameNS(ns, 'pageSetup')[0]
    expect(setup.getAttribute('paperSize')).toBe('9')
    expect(setup.getAttribute('orientation')).toBe('landscape')
    expect(setup.getAttribute('fitToWidth')).toBe('1')
    expect(setup.getAttribute('fitToHeight')).toBe('0')
    expect(doc.getElementsByTagNameNS(ns, 'pageSetUpPr')[0].getAttribute('fitToPage')).toBe('1')
    expect(exported.names.map(name => [name.getAttribute('localSheetId'), name.textContent])).toEqual([['0', "'购销合同'!$A$1:$J$26"]])
    // Compare serialized business sections rather than merely checking helper outputs.
    for (const tag of ['sheetData', 'cols', 'mergeCells']) {
      expect(serialize(doc.getElementsByTagNameNS(ns, tag)[0])).toBe(serialize(original.sheets[0].getElementsByTagNameNS(ns, tag)[0]))
    }
    expect(await exported.zip.file('xl/styles.xml')!.async('string')).toBe(await original.zip.file('xl/styles.xml')!.async('string'))
    const sheet = XLSX.read(buffer, { type: 'array', cellStyles: true }).Sheets['购销合同']
    expect([sheet.D10.v, sheet.F10.v, sheet.G10.v, sheet.G10.f]).toEqual([120, 2.5, 300, 'ROUND(D10*F10,2)'])
    expect([sheet.I10.v, sheet.J10.v]).toEqual(['QA Material', 'QA-CODE'])
    expect(sheet.I10.s.fgColor.rgb).toBe('FFFF00')
  })

  it('按主体合并的长表包含全部合同并继续纵向分页，不把整张表压成一页', async () => {
    const wb = combinePurchaseContracts([
      { entity: 'HSY', ws: contract() }, { entity: 'HD_GLOBAL', ws: contract() },
      { entity: 'HSY', ws: contract() }, { entity: 'HSY', ws: contract() },
    ])
    const buffer = await (await buildPurchaseContractWorkbook(wb)).arrayBuffer()
    const result = await inspect(buffer)
    expect(result.names.map(name => [name.getAttribute('localSheetId'), name.textContent])).toEqual([
      ['0', "'华登全球'!$A$1:$J$26"], ['1', "'华胜益'!$A$1:$J$82"],
    ])
    for (const doc of result.sheets) {
      expect(doc.getElementsByTagNameNS(ns, 'pageSetup')[0].getAttribute('fitToWidth')).toBe('1')
      expect(doc.getElementsByTagNameNS(ns, 'pageSetup')[0].getAttribute('fitToHeight')).toBe('0')
    }
    const sheet = XLSX.read(buffer, { type: 'array' }).Sheets['华胜益']
    expect([sheet.G10.v, sheet.G38.v, sheet.G66.v]).toEqual([300, 300, 300])
    expect(sheet.G66.f).toBe('ROUND(D66*F66,2)')
    expect(sheet.J66.v).toBe('QA-CODE')
    expect(sheet.A82.v).toBe('QA SIGNATURE')
  })

  it('更新已有打印设置且保持有效名称、工作表关联与重复应用的稳定性', async () => {
    const wb = single("QA O'NEIL")
    wb.Workbook = { Names: [
      { Name: '_xlnm.Print_Area', Sheet: 0, Ref: "'QA O''NEIL'!$A$1:$H$26" },
      { Name: '_xlnm.Print_Titles', Sheet: 0, Ref: "'QA O''NEIL'!$9:$9" },
      { Name: 'QA_Amount', Ref: "'QA O''NEIL'!$G$10" },
    ] }
    const zip = await JSZip.loadAsync(XLSX.write(wb, { type: 'array', bookType: 'xlsx' }))
    const sheet = parse(await zip.file('xl/worksheets/sheet1.xml')!.async('string'))
    const setup = sheet.createElementNS(ns, 'pageSetup')
    setup.setAttribute('scale', '75'); setup.setAttribute('orientation', 'portrait')
    sheet.documentElement!.appendChild(setup)
    const footer = sheet.createElementNS(ns, 'headerFooter')
    sheet.documentElement!.appendChild(footer)
    zip.file('xl/worksheets/contract.xml', serialize(sheet))
    zip.remove('xl/worksheets/sheet1.xml')
    zip.file('xl/_rels/workbook.xml.rels', (await zip.file('xl/_rels/workbook.xml.rels')!.async('string')).replace('worksheets/sheet1.xml', 'worksheets/contract.xml'))
    const once = await applyPurchaseContractPrintLayout(await zip.generateAsync({ type: 'arraybuffer' }))
    const twice = await applyPurchaseContractPrintLayout(once)
    const result = await JSZip.loadAsync(twice)
    const xml = parse(await result.file('xl/worksheets/contract.xml')!.async('string'))
    expect(xml.getElementsByTagNameNS(ns, 'pageSetup')).toHaveLength(1)
    expect(xml.getElementsByTagNameNS(ns, 'pageSetup')[0].hasAttribute('scale')).toBe(false)
    expect(xml.getElementsByTagNameNS(ns, 'pageMargins')).toHaveLength(1)
    const tags = Array.from(xml.documentElement!.childNodes).filter(node => node.nodeType === 1).map(node => node.nodeName)
    expect(tags.indexOf('sheetPr')).toBeLessThan(tags.indexOf('sheetData'))
    expect(tags.indexOf('pageMargins')).toBeLessThan(tags.indexOf('pageSetup'))
    expect(tags.indexOf('pageSetup')).toBeLessThan(tags.indexOf('headerFooter'))
    const names = Array.from(parse(await result.file('xl/workbook.xml')!.async('string')).getElementsByTagNameNS(ns, 'definedName'))
    expect(names.map(name => [name.getAttribute('name'), name.textContent])).toEqual([
      ['_xlnm.Print_Titles', "'QA O''NEIL'!$9:$9"], ['QA_Amount', "'QA O''NEIL'!$G$10"], ['_xlnm.Print_Area', "'QA O''NEIL'!$A$1:$J$26"],
    ])
    const firstZip = await JSZip.loadAsync(once)
    expect(await result.file('xl/worksheets/contract.xml')!.async('string')).toBe(await firstZip.file('xl/worksheets/contract.xml')!.async('string'))
    expect(await result.file('xl/workbook.xml')!.async('string')).toBe(await firstZip.file('xl/workbook.xml')!.async('string'))
  })
})

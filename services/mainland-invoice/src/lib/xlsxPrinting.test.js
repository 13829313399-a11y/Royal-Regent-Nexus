import { describe, expect, it } from 'vitest'
import * as XLSX from 'xlsx'
import JSZip from 'jszip'
import { XlsxPackage, normalizeSheetPrint } from './xlsxPackage.js'
import { mergeWorkbookBuffers, reorderWorkbookSheets } from './mergeBooks.js'

const sheetXml = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetPr><pageSetUpPr fitToPage="false"/></sheetPr><sheetData><row r="1"><c r="A1"><v>12.5</v></c></row></sheetData><pageMargins left="0" right="0" top="0" bottom="0" header="0" footer="0"/><pageSetup scale="85" paperSize="9" fitToWidth="0" fitToHeight="0"/></worksheet>'

async function template() {
  const book = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(book, XLSX.utils.aoa_to_sheet([[12.5]]), 'Template')
  return XlsxPackage.load(XLSX.write(book, { type: 'array', bookType: 'xlsx' }))
}

describe('generated invoice print settings', () => {
  it('keeps worksheet-property order when adding print setup', () => {
    const xml = normalizeSheetPrint(sheetXml.replace('<pageSetUpPr fitToPage="false"/>', '<tabColor rgb="FF000000"/><outlinePr summaryBelow="1"/>'))
    expect(xml).toContain('<outlinePr summaryBelow="1"/><pageSetUpPr fitToPage="1"/></sheetPr>')
  })

  it('updates paired XML elements without adding duplicate print properties', () => {
    const input = sheetXml.replace('<pageSetUpPr fitToPage="false"/>', '<pageSetUpPr fitToPage="false"></pageSetUpPr>')
      .replace('fitToHeight="0"/>', 'fitToHeight="0"></pageSetup>')
    const xml = normalizeSheetPrint(input)
    expect(xml.match(/<pageSetUpPr\b/g)).toHaveLength(1)
    expect(xml.match(/<pageSetup\b/g)).toHaveLength(1)
    expect(xml).toContain('<pageSetUpPr fitToPage="1"></pageSetUpPr>')
    expect(xml).toContain('fitToWidth="1" fitToHeight="1"></pageSetup>')
  })

  it.each([true, false])('preserves existing sheet bytes and writes valid print names (existing calcPr: %s)', async (existingCalc) => {
    const pkg = await template()
    pkg.workbookXml = pkg.workbookXml.replace(/<calcPr\b[^>]*\/>/g, '')
    if (existingCalc) pkg.workbookXml = pkg.workbookXml.replace('</workbook>', '<calcPr calcId="1"/></workbook>')
    const original = await pkg.zip.file('xl/worksheets/sheet1.xml').async('string')
    pkg.addSheet({ name: "O'Brien", sheetXml, printArea: '$A$1:$J$37' })
    pkg.addSheet({ name: 'Fixed label', sheetXml, printFit: false, definedNames: false })
    const zip = await JSZip.loadAsync(await pkg.save({ fullCalcOnLoad: true }))
    const wb = await zip.file('xl/workbook.xml').async('string')
    expect(wb).toContain('name="_xlnm.Print_Area"')
    expect(wb).toContain('&apos;O&apos;&apos;Brien&apos;!$A$1:$J$37')
    expect(wb.indexOf('</definedNames>')).toBeLessThan(wb.indexOf('<calcPr'))
    expect(await zip.file('xl/worksheets/sheet1.xml').async('string')).toBe(original)
    expect(await zip.file('xl/worksheets/sheet2.xml').async('string')).toContain('fitToPage="1"')
    expect(await zip.file('xl/worksheets/sheet2.xml').async('string')).toContain('fitToHeight="1"')
    expect(await zip.file('xl/worksheets/sheet3.xml').async('string')).toBe(sheetXml)
  })

  it('keeps built-in print areas through workbook merging and index-based sorting', async () => {
    const base = await template()
    const extra = await template()
    await extra.stripAllSheets()
    extra.addSheet({ name: 'Second', sheetXml, printArea: '$A$1:$J$37' })
    const merged = await mergeWorkbookBuffers([await base.save(), await extra.save()])
    const sorted = await reorderWorkbookSheets(merged.buffer, (_name, index) => [-index])
    const pkg = await XlsxPackage.load(sorted)
    expect(pkg.getSheetNames()).toEqual(['Second', 'Template'])
    expect(pkg.workbookXml).toMatch(/localSheetId="0" name="_xlnm.Print_Area"[^>]*>&apos;Second&apos;!\$A\$1:\$J\$37/)
  })
})

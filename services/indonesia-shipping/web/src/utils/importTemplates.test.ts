import { readFileSync } from 'node:fs'
import { DOMParser } from '@xmldom/xmldom'
import { describe, expect, it } from 'vitest'
import JSZip from 'jszip'
import * as XLSX from 'xlsx'
import { parseShipmentWorkbook } from './shipmentImport'
import { importEngineeringFile } from './engineeringImport'
import { parseIndonesiaMaterials } from './indonesiaMaterialImport'

const templates = ['engineering', 'tools', 'quotes', 'shipments'] as const
function template(kind: typeof templates[number]) {
  return readFileSync(new URL(`../../public/import-templates/${kind}.xlsx`, import.meta.url))
}

describe('downloadable import forms', () => {
  it.each(templates)('%s contains only workbook layout and cell data', async kind => {
    const zip = await JSZip.loadAsync(template(kind))
    for (const path of Object.keys(zip.files)) {
      if (kind === 'shipments' && path === 'xl/metadata.xml') {
        expect(await zip.file(path)!.async('string')).toContain('dynamicArrayProperties')
        continue
      }
      expect(path).toMatch(/^(?:\[Content_Types\]\.xml|_rels\/\.rels|xl\/(?:workbook\.xml|styles\.xml|sharedStrings\.xml|theme\/theme1\.xml|worksheets\/sheet\d+\.xml|_rels\/workbook\.xml\.rels))$/)
      if (path.endsWith('.rels')) expect(await zip.file(path)!.async('string')).not.toContain('TargetMode="External"')
    }
  })

  it.each([
    ['shipments', 1502, 7, 'F9', '_xlfn.HSTACK(', 'F9:L9'],
    ['engineering', 145, 3, 'C6', "'C1排模表'!F5", null],
    ['quotes', 76, 1, 'F81', '*1.09/7.2', null],
    ['tools', 8, 1, 'T2', 'S2*J2', null],
  ] as const)('keeps the source formula cells and references in %s', async (kind, total, sheet, address, expression, span) => {
    const zip = await JSZip.loadAsync(template(kind))
    let count = 0
    for (const part of zip.file(/^xl\/worksheets\/sheet\d+\.xml$/)) {
      const document = new DOMParser().parseFromString(await part.async('string'), 'application/xml')
      count += document.getElementsByTagName('f').length
      if (part.name !== `xl/worksheets/sheet${sheet}.xml`) continue
      const cell = Array.from(document.getElementsByTagName('c')).find(c => c.getAttribute('r') === address)
      const formula = cell?.getElementsByTagName('f').item(0)
      expect(formula?.textContent).toContain(expression)
      if (span) {
        expect(formula?.getAttribute('ref')).toBe(span)
        expect(formula?.getAttribute('t')).toBe('array')
        expect(cell?.getAttribute('cm')).toBe('1')
      }
      if (kind === 'quotes') expect(formula?.textContent).toContain('公式输入')
    }
    expect(count).toBe(total)
  })

  it('accepts a new line in the original bilingual shipping layout', () => {
    const wb = XLSX.read(template('shipments'), { type: 'buffer' })
    expect(parseShipmentWorkbook(wb).rows).toHaveLength(0)
    const ws = wb.Sheets['走货明细']
    ws.D4 = { t: 's', v: 'QA-001' }
    ws.F4 = { t: 's', v: '测试支架' }
    ws.L4 = { t: 'n', v: 12 }
    const parsed = parseShipmentWorkbook(wb)
    expect(parsed.rows).toHaveLength(1)
    expect(parsed.rows[0].item).toMatchObject({ qty: 12, material_snapshot: { name_zh: '测试支架' } })
  })

  it('imports one BOM item from the engineering form with a new customer and SKU', async () => {
    const bytesOfTemplate = Uint8Array.from(template('engineering')).buffer
    await expect(importEngineeringFile({ arrayBuffer: async () => bytesOfTemplate } as File)).rejects.toThrow('产品编号')
    const wb = XLSX.read(bytesOfTemplate, { type: 'array' })
    for (const name of ['C1排模表', 'F2外购清单']) {
      wb.Sheets[name].A3 = { t: 's', v: '客户名称：测试客户    产品名称：测试产品    产品编号：QA-001' }
    }
    const sheet = wb.Sheets['F2外购清单']
    sheet.C5 = { t: 's', v: '测试支架' }
    sheet.J5 = { t: 'n', v: 2 }
    const bytes = XLSX.write(wb, { type: 'array', bookType: 'xlsx' }) as ArrayBuffer
    const result = await importEngineeringFile({ arrayBuffer: async () => bytes } as File)
    expect(result).toMatchObject({ code: 'QA-001', customer: '测试客户' })
    expect(result.materials.map(row => row.name_zh)).toEqual(['测试支架'])
  })

  it('reads the tools form and keeps the new tool associated with its SKU', () => {
    const wb = XLSX.read(template('tools'), { type: 'buffer' })
    expect(parseIndonesiaMaterials(wb, true).groups).toHaveLength(0)
    const ws = wb.Sheets.Sheet1
    ws.D2 = { t: 's', v: 'QA-001' }
    ws.E2 = { t: 's', v: '测试模具' }
    const parsed = parseIndonesiaMaterials(wb, true)
    expect(parsed.groups.flatMap(group => group.materials)).toMatchObject([{ name_zh: '测试模具', related_product_code: 'QA-001' }])
  })

  it('preserves both supplier quote formats with no historical quote rows', () => {
    const wb = XLSX.read(template('quotes'), { type: 'buffer' })
    const standard = XLSX.utils.sheet_to_json<unknown[]>(wb.Sheets['标准格式'], { header: 1, blankrows: false })
    const tiers = XLSX.utils.sheet_to_json<unknown[]>(wb.Sheets['阶梯多列格式'], { header: 1, blankrows: false })
    expect(standard).toEqual([['供应商', '货号', '物料名称', '规格', '起订量', '单价']])
    expect(tiers).toHaveLength(2)
    expect(tiers[1]).toContain('1K')
  })
})

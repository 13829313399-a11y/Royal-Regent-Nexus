import { describe, expect, it } from 'vitest'
import { strToU8, zipSync } from 'fflate'
import {
  extractExcelSheetNames,
  MAX_DOCUMENT_TRANSLATION_FILE_SIZE_BYTES,
  validateTranslationDocument,
} from '../documentTranslationUtils'


describe('document translation upload validation', () => {
  it.each(['订单.xlsx', '宏表.xlsm', '说明.docx'])('accepts supported Office file %s', (name) => {
    expect(validateTranslationDocument(new File(['office'], name))).toBe('')
  })

  it('rejects legacy binary Excel because exact OOXML formatting cannot be preserved', () => {
    expect(validateTranslationDocument(new File(['legacy'], '订单.xls'))).toContain('.xlsx')
  })

  it('rejects documents over the size limit', () => {
    const oversized = new File([new Uint8Array(MAX_DOCUMENT_TRANSLATION_FILE_SIZE_BYTES + 1)], '订单.docx')
    expect(validateTranslationDocument(oversized)).toContain('20MB')
  })

  it('reads worksheet names from Excel without loading worksheet contents', async () => {
    const workbookXml = `<?xml version="1.0" encoding="UTF-8"?>
      <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
        <sheets>
          <sheet name="报价单" sheetId="1" />
          <sheet name="生产计划 &amp; 排期" sheetId="2" />
        </sheets>
      </workbook>`
    const bytes = zipSync({ 'xl/workbook.xml': strToU8(workbookXml) })
    const file = new File([bytes], '订单.xlsx')

    await expect(extractExcelSheetNames(file)).resolves.toEqual(['报价单', '生产计划 & 排期'])
  })

  it('reports a readable error when the Excel workbook structure is invalid', async () => {
    const file = new File([zipSync({ 'xl/not-workbook.xml': strToU8('<invalid />') })], '损坏.xlsx')

    await expect(extractExcelSheetNames(file)).rejects.toThrow('无法读取 Excel 工作表列表')
  })
})

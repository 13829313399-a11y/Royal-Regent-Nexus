import { strFromU8, unzipSync } from 'fflate'


export const MAX_DOCUMENT_TRANSLATION_FILE_SIZE_BYTES = 20 * 1024 * 1024

const SUPPORTED_EXTENSIONS = ['.xlsx', '.xlsm', '.docx'] as const
const SPREADSHEET_NAMESPACE = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'

export function validateTranslationDocument(file: File) {
  const lowerName = file.name.toLowerCase()
  if (!SUPPORTED_EXTENSIONS.some((extension) => lowerName.endsWith(extension))) {
    return '只支持上传 .xlsx、.xlsm 或 .docx 文件。'
  }
  if (file.size <= 0) return 'Office 文档不能为空。'
  if (file.size > MAX_DOCUMENT_TRANSLATION_FILE_SIZE_BYTES) return '单个 Office 文档不可超过 20MB。'
  return ''
}

export async function extractExcelSheetNames(file: File): Promise<string[]> {
  if (!/\.xls[xm]$/i.test(file.name)) return []

  try {
    const archive = unzipSync(new Uint8Array(await file.arrayBuffer()), {
      filter: entry => entry.name === 'xl/workbook.xml',
    })
    const workbookXml = archive['xl/workbook.xml']
    if (!workbookXml) throw new Error('missing workbook.xml')

    const document = new DOMParser().parseFromString(strFromU8(workbookXml), 'application/xml')
    if (document.getElementsByTagName('parsererror').length) throw new Error('invalid workbook.xml')

    const sheetNames = Array.from(document.getElementsByTagNameNS(SPREADSHEET_NAMESPACE, 'sheet'))
      .map(sheet => sheet.getAttribute('name')?.trim() ?? '')
      .filter(Boolean)
    if (!sheetNames.length) throw new Error('missing sheets')
    return sheetNames
  }
  catch {
    throw new Error('无法读取 Excel 工作表列表，请确认文件未损坏或加密。')
  }
}

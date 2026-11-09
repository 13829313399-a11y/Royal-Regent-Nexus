import * as XLSX from 'xlsx'

// Invoice engines use Excel date serials, not JS Dates. SheetJS 0.20 converts
// date-formatted numbers in sheet_to_json even with raw:true. Hide only those
// formats in a shallow read view; leave workbook cells/styles/formulas intact.
export function invoiceRows(sheet) {
  if (!sheet) return []
  const plain = cell => cell?.t === 'n' && cell.z && XLSX.SSF.is_date(cell.z)
    ? { ...cell, z: undefined } : cell
  const view = { ...sheet }
  for (const key of Object.keys(view)) {
    if (!key.startsWith('!')) view[key] = plain(view[key])
  }
  if (sheet['!data']) view['!data'] = sheet['!data'].map(row => row?.map(plain))
  return XLSX.utils.sheet_to_json(view, { header: 1, defval: null, raw: true })
}

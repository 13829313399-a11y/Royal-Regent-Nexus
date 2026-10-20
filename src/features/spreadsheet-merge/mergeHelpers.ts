import type { MergeTable, SpreadsheetCell } from '@/api/spreadsheetMerge'

export const MAX_SHEET_FILE_BYTES = 64 * 1024 * 1024
export function validateSpreadsheetFile(file: File) {
  if (!/\.(xlsx|csv)$/i.test(file.name)) return '请选择 XLSX 或 CSV 表格。'
  if (!file.size) return '文件不能为空。'
  if (file.size > MAX_SHEET_FILE_BYTES) return '单份文件不能超过 64 MiB。'
  return ''
}
export function extractMergeTable(name: string, rows: SpreadsheetCell[][], headerRow: number): MergeTable | null {
  if (!Number.isInteger(headerRow) || headerRow < 1 || headerRow > rows.length) return null
  const header = rows[headerRow - 1] ?? []
  const width = Math.max(header.length, ...rows.slice(headerRow).map(row => row.length), 0)
  if (!width) return null
  return { name: name.slice(0, 255), header_row: headerRow, headers: Array.from({ length: width }, (_, index) => String(header[index] ?? '').trim() || `未命名列 ${index + 1}`), rows: rows.slice(headerRow) }
}
export function sameNameMapping(primary: string[], secondary: string[]) {
  const normalize = (value: string) => value.normalize('NFKC').trim().toLocaleLowerCase()
  const normalizedPrimary = primary.map(normalize)
  const normalizedSecondary = secondary.map(normalize)
  return normalizedSecondary.map((name, source) => {
    const target = normalizedPrimary.indexOf(name)
    return target >= 0 && normalizedPrimary.lastIndexOf(name) === target && normalizedSecondary.indexOf(name) === source && normalizedSecondary.lastIndexOf(name) === source
      && !name.startsWith('未命名列 ') ? target : -1
  })
}
export function cellText(value: SpreadsheetCell | undefined) {
  return value === null || value === undefined ? '' : String(value)
}
export function columnLabel(index: number) {
  let value = index + 1, label = ''
  while (value > 0) { value--; label = String.fromCharCode(65 + value % 26) + label; value = Math.floor(value / 26) }
  return label
}
export function saveSpreadsheetBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

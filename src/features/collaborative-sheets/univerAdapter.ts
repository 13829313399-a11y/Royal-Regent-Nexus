import type { ICellData, IObjectMatrixPrimitiveType, IStyleData, IWorkbookData, Nullable } from '@univerjs/core'
import type { FillCell, FillChange, FillSheet, FillTaskDetail, SheetValue } from '@/api/collaborativeSheets'
import { canFill, columnName, coordinates, rangeBounds } from './grid'

export const TRIAL_SHEET_ID = 'original-sheet'
export const VALUE_MUTATION = 'sheet.mutation.set-range-values'

export function cellAt(sheet: FillSheet, row: number, column: number): FillCell {
  return sheet.cells.find(c => c.row === row && c.column === column)
    ?? { address: `${columnName(column)}${row + 1}`, row, column, value: null, display: '', formula: false, style: {} }
}

export function validateScalar(value: unknown, address: string): asserts value is SheetValue {
  if (value !== null && typeof value !== 'string' && typeof value !== 'boolean' && (typeof value !== 'number' || !Number.isFinite(value))) throw new Error(`${address} 只能填写文字、数字或是 / 否。`)
  if (typeof value === 'string' && (value.length > 2000 || value.trimStart().startsWith('=') || /[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(value))) throw new Error(`${address} 内容过长、包含公式或不支持的字符，本次修改未写入。`)
}

/** One atomic draft path shared by the original editor, paste and the trial canvas. */
export function stageFillChanges(task: FillTaskDetail, pending: FillChange[], batch: FillChange[]): FillChange[] {
  if (batch.length > 500) throw new Error('一次最多填写 500 格，请分批填写并保存。')
  const next = new Map(pending.map(c => [`${c.sheet}:${c.address}`, c]))
  for (const change of batch) {
    const sheet = task.workbook.sheets.find(s => s.index === change.sheet), position = coordinates(change.address)
    if (!sheet || !position || !canFill(task, sheet, ...position)) throw new Error(`${change.address} 是公式、合并区域内部或未授权单元格，本次修改未写入。`)
    validateScalar(change.value, change.address)
    const key = `${change.sheet}:${change.address}`
    if (change.value === (sheet.cells.find(c => c.address === change.address)?.value ?? null)) next.delete(key)
    else next.set(key, change)
  }
  if (next.size > 500) throw new Error('待保存内容超过 500 格，请先保存现有填写，再继续填写。')
  return [...next.values()]
}

export function scalarCell(value: SheetValue): ICellData {
  return { v: typeof value === 'boolean' ? Number(value) : value, t: typeof value === 'number' ? 2 : typeof value === 'boolean' ? 3 : 1, f: null, p: null }
}

export function originalStyle(cell: FillCell): IStyleData {
  const css = cell.style
  const style: IStyleData = {
    ff: String(css.fontFamily ?? 'Arial'), fs: parseFloat(String(css.fontSize ?? 11)),
    bl: css.fontWeight === 'bold' ? 1 : 0, it: css.fontStyle === 'italic' ? 1 : 0,
    ht: ({ left: 1, center: 2, right: 3, justify: 4 } as const)[String(css.textAlign) as 'left'] ?? 1,
    vt: ({ top: 1, middle: 2, center: 2, bottom: 3 } as const)[String(css.verticalAlign) as 'top'] ?? 2,
    tb: 3,
  }
  if (css.color) style.cl = { rgb: String(css.color) }
  if (css.backgroundColor) style.bg = { rgb: String(css.backgroundColor) }
  if (cell.number_format && !cell.formula) style.n = { pattern: cell.number_format }
  for (const [side, key] of [['Top', 't'], ['Right', 'r'], ['Bottom', 'b'], ['Left', 'l']] as const) {
    const border = css[`border${side}`]
    if (border) { style.bd ??= {}; style.bd[key] = { s: 1, cl: { rgb: String(border).split(' ').at(-1) ?? '#9ca3af' } } }
  }
  return style
}

/** Formulas are deliberately represented by cached display text, never executable formulas. */
export function trialWorkbook(task: FillTaskDetail, sheet: FillSheet, changes: FillChange[]): Partial<IWorkbookData> {
  const cellData: IObjectMatrixPrimitiveType<ICellData> = {}
  const pending = new Map(changes.filter(c => c.sheet === sheet.index).map(c => [c.address, c.value]))
  for (const cell of sheet.cells) {
    const value = cell.image ? '图片（选中预览）' : cell.formula ? cell.display : pending.has(cell.address) ? pending.get(cell.address)! : cell.value
    ;(cellData[cell.row] ??= {})[cell.column] = { ...scalarCell(value), s: originalStyle(cell) }
  }
  for (const change of changes.filter(c => c.sheet === sheet.index)) {
    const position = coordinates(change.address)
    if (position) { const [row, column] = position; (cellData[row] ??= {})[column] = { ...cellData[row]?.[column], ...scalarCell(change.value) } }
  }
  return {
    id: `fill-${task.id}-${sheet.index}`, name: task.title, sheetOrder: [TRIAL_SHEET_ID],
    sheets: { [TRIAL_SHEET_ID]: {
      id: TRIAL_SHEET_ID, name: sheet.name, rowCount: sheet.rows, columnCount: sheet.columns,
      defaultRowHeight: 25, defaultColumnWidth: 100, cellData,
      mergeData: sheet.merges.flatMap(range => { const b = rangeBounds(range); return b ? [{ startRow: b[0], startColumn: b[1], endRow: b[2], endColumn: b[3] }] : [] }),
      rowData: Object.fromEntries(Array.from({ length: sheet.rows }, (_, row) => [row, { h: sheet.row_heights[String(row)] ?? 25, ia: 0 }])),
      columnData: Object.fromEntries(Object.entries(sheet.column_widths).map(([column, width]) => [column, { w: width }])),
    } },
  }
}

export function mutationChanges(sheet: FillSheet, matrix: IObjectMatrixPrimitiveType<Nullable<ICellData>>): FillChange[] {
  const batch: FillChange[] = []
  for (const r of Object.keys(matrix)) for (const c of Object.keys(matrix[Number(r)]!)) {
    const cell = matrix[Number(r)]![Number(c)]
    const row = Number(r), column = Number(c), address = `${columnName(column)}${row + 1}`
    if (!Number.isInteger(row) || !Number.isInteger(column)) throw new Error('无法识别单元格位置。')
    if (cell?.f || cell?.si) throw new Error('试用编辑器仅支持填写数值和文字，公式保持只读。')
    // Rich text is flattened to plain text, matching the native scalar overlay contract.
    let value: unknown = cell?.p?.body?.dataStream?.replace(/\r\n$/, '') ?? cell?.v ?? null
    if (cell?.t === 3 && value !== null) value = Boolean(value)
    validateScalar(value, address)
    batch.push({ sheet: sheet.index, address, value })
  }
  return batch
}

const allowedSheetCommands = new Set([
  'set-range-values', 'clear-selection-content', 'auto-clear-content', 'select-range',
  'move-selection', 'move-selection-enter-tab', 'expand-selection', 'select-all',
  'scroll-to-cell', 'scroll-view', 'scroll-view-reset', 'set-scroll-relative',
  'set-zoom-ratio', 'set-zoom-ratio-from-toolbar', 'change-zoom-ratio', 'set-worksheet-activate',
])
export function blockedTrialCommand(id: string): boolean {
  if (id.startsWith('sheet.command.')) return !allowedSheetCommands.has(id.slice('sheet.command.'.length))
  if (id.startsWith('sheet.mutation.')) return id !== VALUE_MUTATION && id !== 'sheet.mutation.set-worksheet-row-auto-height'
  return false
}

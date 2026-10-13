import type { FillSheet, FillTaskDetail, SheetValue } from '@/api/collaborativeSheets'

export function columnName(index: number): string {
  let name = ''
  for (let n = index + 1; n > 0; n = Math.floor((n - 1) / 26)) {
    name = String.fromCharCode(65 + ((n - 1) % 26)) + name
  }
  return name
}
export function coordinates(address: string): [number, number] | null {
  const match = /^([A-Z]+)([1-9]\d*)$/.exec(address.toUpperCase())
  if (!match) return null
  let column = 0
  for (const ch of match[1]!) column = column * 26 + ch.charCodeAt(0) - 64
  return [Number(match[2]) - 1, column - 1]
}
export function rangeBounds(range: string): [number, number, number, number] | null {
  const [first, last] = range.toUpperCase().split(':')
  const a = coordinates(first ?? ''), b = coordinates(last ?? first ?? '')
  if (!a || !b || a[0] > b[0] || a[1] > b[1]) return null
  return [a[0], a[1], b[0], b[1]]
}
export function canFill(task: FillTaskDetail, sheet: FillSheet, row: number, column: number): boolean {
  if (task.status !== 'open') return false
  if (sheet.cells.find(c => c.row === row && c.column === column)?.formula) return false
  if (row < 0 || column < 0 || row >= sheet.rows || column >= sheet.columns) return false
  if (sheet.merges.some(range => {
    const b = rangeBounds(range)
    return b && row >= b[0] && row <= b[2] && column >= b[1] && column <= b[3] && (row !== b[0] || column !== b[1])
  })) return false
  return task.editable_ranges.some(g => {
    const bounds = rangeBounds(g.range)
    return g.sheet === sheet.index && bounds && row >= bounds[0] && column >= bounds[1]
      && row <= bounds[2] && column <= bounds[3]
  })
}
export function parseInput(value: string, kind: 'auto' | 'text' | 'number' | 'boolean'): SheetValue {
  if (value === '') return null
  if (kind === 'auto') {
    if (value.startsWith("'")) return value.slice(1)
    const raw = value.trim()
    if (/^(true|false)$/i.test(raw)) return raw.toLowerCase() === 'true'
    if (/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)%$/.test(raw)) {
      const percent = Number(raw.slice(0, -1)) / 100
      if (Number.isFinite(percent)) return percent
    }
    const significant = raw.replace(/^[+-]?0*|[^0-9]/g, '').length
    return /^[+-]?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(raw) && significant <= 15 && Number.isFinite(Number(raw)) ? Number(raw) : value
  }
  if (kind === 'number') {
    if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value.trim()) || !Number.isFinite(Number(value))) {
      throw new Error('请输入有效数字。编号、带单位或前导零的内容请选择“文字”。')
    }
    return Number(value)
  }
  if (kind === 'boolean') return value === 'true'
  return value
}

/** Excel's plain clipboard format quotes fields containing tabs/newlines. */
export function clipboardRows(text: string): string[][] {
  const rows: string[][] = []; let row: string[] = [], field = '', quoted = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]!
    if (c === '"' && (quoted || field === '')) {
      if (quoted && text[i + 1] === '"') { field += '"'; i++ } else quoted = !quoted
    } else if (!quoted && (c === '\t' || c === '\n' || c === '\r')) {
      row.push(field); field = ''
      if (c !== '\t') { rows.push(row); row = []; if (c === '\r' && text[i + 1] === '\n') i++ }
    } else field += c
  }
  if (quoted) throw new Error('粘贴内容的引号不完整，请重新复制。')
  if (field || row.length || !rows.length) { row.push(field); rows.push(row) }
  return rows
}
export function clipboardText(value: SheetValue): string {
  const text = value === null ? '' : typeof value === 'boolean' ? (value ? 'TRUE' : 'FALSE') : String(value)
  return /[\t\r\n"]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

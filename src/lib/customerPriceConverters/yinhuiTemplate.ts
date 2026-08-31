import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'
import { createXlsxWorkbook, excelDateSerial, parseXlsxWorkbook } from './xlsxLite'
import { validateYinhuiExport, yinhuiTotals, yinhuiMaterialPrice, YINHUI_HKD_USD, type YinhuiConversionResult, type YinhuiCostRow } from './yinhui'

export interface YinhuiProductImage { bytes: Uint8Array; extension: 'png' | 'jpg' }
export const YINHUI_SHEET_NAMES = ['SUM(總計)', '包裝價', 'BOM (1)', 'BOM (2)', 'TOOL PLAN (1)', 'TOOL PLAN (2)']
const NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
const REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
const xml = (value: string) => new DOMParser().parseFromString(value, 'application/xml')
const serialize = (doc: Document) => strToU8(new XMLSerializer().serializeToString(doc))
const elements = (root: Document | Element, name: string) => Array.from(root.getElementsByTagNameNS('*', name))
function column(ref: string) { return ref.replace(/\d/g, '').split('').reduce((a, c) => a * 26 + c.charCodeAt(0) - 64, 0) }
function resolve(base: string, path: string) {
  const result: string[] = []
  for (const part of (path.startsWith('/') ? path.slice(1) : `${base.slice(0, base.lastIndexOf('/') + 1)}${path}`).split('/')) {
    if (part === '..') result.pop()
    else if (part && part !== '.') result.push(part)
  }
  return result.join('/')
}
function relationships(zip: Record<string, Uint8Array>, path: string) {
  const name = path.slice(path.lastIndexOf('/') + 1)
  const relPath = path.slice(0, path.lastIndexOf('/') + 1) + '_rels/' + name + '.rels'
  return elements(xml(strFromU8(zip[relPath] || new Uint8Array())), 'Relationship').filter((r) => r.getAttribute('TargetMode') !== 'External')
}
export function extractYinhuiProductImage(buffer: ArrayBuffer, sheetName: string): YinhuiProductImage | undefined {
  const zip = unzipSync(new Uint8Array(buffer))
  const workbook = xml(strFromU8(zip['xl/workbook.xml']!))
  const sheet = elements(workbook, 'sheet').find((s) => s.getAttribute('name') === sheetName)
  const target = relationships(zip, 'xl/workbook.xml').find((r) => r.getAttribute('Id') === sheet?.getAttribute('r:id'))?.getAttribute('Target')
  if (!target) return
  const sheetPath = resolve('xl/workbook.xml', target)
  const drawing = relationships(zip, sheetPath).find((r) => r.getAttribute('Type') === `${REL}/drawing`)
  if (!drawing) return
  const drawingPath = resolve(sheetPath, drawing.getAttribute('Target') || '')
  if (!zip[drawingPath]) return
  // Only the main sheet's largest embedded picture is eligible; never copy supplier sheets or drawings wholesale.
  const pictures = elements(xml(strFromU8(zip[drawingPath]!)), 'pic').map((pic) => {
    const ext = elements(pic, 'ext')[0]
    return { pic, area: Number(ext?.getAttribute('cx')) * Number(ext?.getAttribute('cy')) }
  }).sort((a, b) => b.area - a.area)
  const imageId = elements(pictures[0]?.pic || workbook, 'blip')[0]?.getAttribute('r:embed')
  const relation = relationships(zip, drawingPath).find((r) => r.getAttribute('Id') === imageId && r.getAttribute('Type') === `${REL}/image`)
  if (!relation) return
  const imagePath = resolve(drawingPath, relation.getAttribute('Target') || '')
  const bytes = zip[imagePath]
  if (!bytes || bytes.length > 10_000_000) return
  if (bytes[0] === 137 && bytes[1] === 80 && bytes[2] === 78 && bytes[3] === 71) return { bytes, extension: 'png' }
  if (bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255) return { bytes, extension: 'jpg' }
}

// Template extraction is deliberately a label whitelist. All sample inputs, formula caches,
// pictures, comments, names, links and private OOXML parts are excluded from the public asset.
function templateLayout(parsed: ReturnType<typeof parseXlsxWorkbook>) {
  const bom = [2, 3].map(index => {
    const rows = parsed.sheets[index]!.rows
    const find = (pattern: RegExp) => {
      const found = rows.findIndex(row => pattern.test(String(row?.[1] || '').trim())) + 1
      if (!found) throw new Error(`银辉模板缺少 ${pattern.source} 区域`)
      return found
    }
    return { plastic: find(/^PLASTIC MATERIAL$/i), mechanical: find(/^MECHANICAL MAT'L$/i), electronic: find(/^ELECTRICAL MAT'L$/i), fabric: find(/^FABRIC COST$/i), labor: find(/^LABOUR COST$/i), subtotal: find(/^SUB TOTAL/i), markup: find(/^MARK-UP$/i), total: find(/^GRAND TOTAL/i) }
  })
  const tools = [4, 5].map(index => {
    const end = parsed.sheets[index]!.rows.findIndex(row => /^TOTAL\s*:/i.test(String(row?.[3] || '').trim())) + 1
    if (!end) throw new Error('银辉模板缺少 Tool Plan TOTAL 行')
    return end
  })
  return { bom, tools }
}
function keepStatic(sheet: number, ref: string, layout: ReturnType<typeof templateLayout>) {
  const r = Number(ref.match(/\d+/)?.[0]); const c = column(ref)
  if (sheet === 0) return new Set(['M1', 'A2', 'N2', 'A3', 'G3', 'A4', 'G4', 'A5', 'G5', 'A6', 'G6', 'A7', 'G7', 'A8', 'G8', 'N13', 'N20', 'B38', 'D38', 'B39', 'B41', 'I41', 'J41', 'K41', 'Q44', 'Q45', 'Q46', 'B48', 'B52', 'B54', 'D54', 'B56', 'B57', 'B58', 'B59', 'A57', 'A58', 'A59', 'F58', 'F18', 'F25', 'F29']).has(ref)
    || ((r === 9 || r === 10) && c <= 13) || (c <= 2 && r >= 11 && r <= 36) || (c === 2 && r >= 42 && r <= 46) || (c === 12 && r >= 42 && r <= 46) || (c <= 2 && r >= 49 && r <= 51)
  if (sheet === 1) return ['A2', 'M2', 'A3', 'H3', 'A4', 'D4', 'H4', 'A5', 'D5'].includes(ref) || r === 7
    || (c <= 2 && [9, 10, 31, 32].includes(r)) || (c === 2 && [23, 24, 25, 45, 46, 47].includes(r))
    || (c === 5 && [26, 27, 28, 48, 49, 50].includes(r)) || (c === 1 && (r === 26 || r === 48))
  if (sheet === 2 || sheet === 3) {
    const area = layout.bom[sheet - 2]!
    const headings = Object.values(area)
    const laborStart = area.labor + 1; const markupStart = area.markup + 1
    return ['A2', 'M2', 'A3', 'I3', 'A4', 'D4', 'I4', 'A5', 'D5'].includes(ref) || r === 7
      || (c <= 2 && headings.includes(r)) || (c === 2 && r >= laborStart && r <= laborStart + 11)
      || ([2, 4].includes(c) && r >= markupStart && r <= markupStart + 3)
  }
  return ['A2', 'B3', 'L3', 'B4', 'F4', 'L4', 'B5', 'F5'].includes(ref) || r === 7 || ref === `D${layout.tools[sheet - 4]}`
}
export function sanitizeYinhuiTemplate(buffer: ArrayBuffer) {
  const source = unzipSync(new Uint8Array(buffer))
  const parsed = parseXlsxWorkbook(buffer)
  const layout = templateLayout(parsed)
  if (parsed.sheets.map((s) => s.name).join('|') !== YINHUI_SHEET_NAMES.join('|')) throw new Error('银辉模板的六张工作表与已确认版式不一致')
  const output = unzipSync(createXlsxWorkbook(YINHUI_SHEET_NAMES.map((name) => ({ name, rows: [] }))))
  output['xl/styles.xml'] = source['xl/styles.xml']!
  if (source['xl/theme/theme1.xml']) {
    output['xl/theme/theme1.xml'] = source['xl/theme/theme1.xml']
    output['xl/_rels/workbook.xml.rels'] = strToU8(strFromU8(output['xl/_rels/workbook.xml.rels']!).replace('</Relationships>', `<Relationship Id="customerTheme" Type="${REL}/theme" Target="theme/theme1.xml"/></Relationships>`))
    output['[Content_Types].xml'] = strToU8(strFromU8(output['[Content_Types].xml']!).replace('</Types>', '<Override PartName="/xl/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/></Types>'))
  }
  const workbookDoc = xml(strFromU8(output['xl/workbook.xml']!))
  const originalWorkbook = xml(strFromU8(source['xl/workbook.xml']!))
  const names = elements(originalWorkbook, 'definedName').filter((n) => ['_xlnm.Print_Area', '_xlnm.Print_Titles'].includes(n.getAttribute('name') || '') && !/\[/.test(n.textContent || ''))
  if (names.length) {
    const defined = workbookDoc.createElementNS(NS, 'definedNames')
    for (const name of names) defined.append(name.cloneNode(true))
    workbookDoc.documentElement.insertBefore(defined, elements(workbookDoc, 'calcPr')[0] || null)
  }
  output['xl/workbook.xml'] = serialize(workbookDoc)
  const sharedStrings = source['xl/sharedStrings.xml'] ? elements(xml(strFromU8(source['xl/sharedStrings.xml'])), 'si') : []
  YINHUI_SHEET_NAMES.forEach((_, index) => {
    const path = `xl/worksheets/sheet${index + 1}.xml`
    const doc = xml(strFromU8(source[path]!))
    const allowed = ['sheetPr', 'dimension', 'sheetViews', 'sheetFormatPr', 'cols', 'sheetData', 'mergeCells', 'printOptions', 'pageMargins', 'pageSetup']
    for (const child of Array.from(doc.documentElement.children)) if (!allowed.includes(child.localName)) child.remove()
    for (const el of elements(doc, 'pageSetup')) el.removeAttribute('r:id')
    for (const cell of elements(doc, 'c')) {
      const ref = cell.getAttribute('r') || ''
      const row = Number(ref.match(/\d+/)?.[0]) - 1
      const value = parsed.sheets[index]?.rows[row]?.[column(ref) - 1]
      const formula = elements(cell, 'f')[0]?.cloneNode(true)
      const inlineSource = elements(cell, 'is')[0]?.cloneNode(true)
      const stringIndex = cell.getAttribute('t') === 's' ? Number(elements(cell, 'v')[0]?.textContent) : -1
      cell.replaceChildren(); cell.removeAttribute('t')
      if (formula) {
        cell.append(formula)
        const v = doc.createElementNS(NS, 'v'); v.textContent = '0'; cell.append(v)
      } else if (keepStatic(index, ref, layout) && typeof value === 'number') {
        const v = doc.createElementNS(NS, 'v'); v.textContent = String(value); cell.append(v)
      } else if (keepStatic(index, ref, layout) && typeof value === 'string') {
        cell.setAttribute('t', 'inlineStr')
        if (inlineSource) cell.append(inlineSource)
        else {
          const inline = doc.createElementNS(NS, 'is')
          if (sharedStrings[stringIndex]) for (const child of Array.from(sharedStrings[stringIndex]!.childNodes)) inline.append(child.cloneNode(true))
          else { const t = doc.createElementNS(NS, 't'); t.textContent = value; inline.append(t) }
          cell.append(inline)
        }
      }
    }
    output[path] = serialize(doc)
  })
  return zipSync(output)
}

type FormulaValue = number | string | boolean | { error: string } | FormulaValue[]
function isError(value: FormulaValue): value is { error: string } { return typeof value === 'object' && !Array.isArray(value) }
function translatedFormula(formula: string, from: string, to: string) {
  const dx = column(to) - column(from); const dy = Number(to.match(/\d+/)?.[0]) - Number(from.match(/\d+/)?.[0])
  return formula.replace(/(\$?)([A-Z]{1,3})(\$?)(\d+)/g, (_, absC: string, col: string, absR: string, row: string) => {
    let n = column(col) + (absC ? 0 : dx); let letters = ''
    while (n > 0) { n--; letters = String.fromCharCode(65 + n % 26) + letters; n = Math.floor(n / 26) }
    return `${absC}${letters}${absR}${Number(row) + (absR ? 0 : dy)}`
  })
}
function formulaMap(doc: Document) {
  const shared = new Map<string, { ref: string; text: string }>()
  for (const c of elements(doc, 'c')) {
    const f = elements(c, 'f')[0]
    if (f?.getAttribute('t') === 'shared' && f.textContent) shared.set(f.getAttribute('si') || '', { ref: c.getAttribute('r')!, text: f.textContent })
  }
  return new Map(elements(doc, 'c').flatMap((c) => {
    const f = elements(c, 'f')[0]; if (!f) return []
    const ref = c.getAttribute('r')!; const parent = shared.get(f.getAttribute('si') || '')
    const expression = f.textContent || (parent ? translatedFormula(parent.text, parent.ref, ref) : '')
    if (!expression) throw new Error(`银辉模板共享公式损坏：${ref}`)
    return [[ref, expression] as const]
  }))
}

// Small, non-eval interpreter for this fixed customer template. It refreshes cached results
// only; the original <f> nodes stay byte-for-byte equivalent, including shared formulas.
function recalculateTemplate(zip: Record<string, Uint8Array>) {
  const docs = YINHUI_SHEET_NAMES.map((_, i) => xml(strFromU8(zip[`xl/worksheets/sheet${i + 1}.xml`]!)))
  const cells = docs.map((doc) => new Map(elements(doc, 'c').map((c) => [c.getAttribute('r')!, c])))
  const formulas = docs.map(formulaMap)
  const cache = new Map<string, FormulaValue>(); const visiting = new Set<string>()
  const valueAt = (sheet: number, ref: string): FormulaValue => {
    ref = ref.replace(/\$/g, '')
    const key = `${sheet}!${ref}`
    if (cache.has(key)) return cache.get(key)!
    if (visiting.has(key)) throw new Error(`银辉模板存在循环公式 ${key}`)
    visiting.add(key)
    const cell = cells[sheet]?.get(ref); const expression = formulas[sheet]?.get(ref)
    let value: FormulaValue = 0
    if (expression) value = evaluate(expression, sheet)
    else if (cell?.getAttribute('t') === 'inlineStr') value = elements(cell, 't').map((t) => t.textContent).join('')
    else value = cell ? Number(elements(cell, 'v')[0]?.textContent || 0) : 0
    visiting.delete(key); cache.set(key, value); return value
  }
  const evaluate = (expression: string, sheet: number): FormulaValue => {
    const tokens = expression.match(/(?:'[^']+'|[\p{L}_][\p{L}\d_.]*)!\$?[A-Z]{1,3}\$?\d+|\$?[A-Z]{1,3}\$?\d+|"(?:[^"]|"")*"|\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?|[A-Z_]+|<>|<=|>=|[+*/(),:=<>%-]/gu) || []
    let at = 0
    const number = (v: FormulaValue) => typeof v === 'number' ? v : v === true ? 1 : Number(v) || 0
    const readRef = (token: string) => {
      const split = token.lastIndexOf('!')
      const target = split < 0 ? sheet : YINHUI_SHEET_NAMES.indexOf(token.slice(0, split).replace(/^'|'$/g, ''))
      if (target < 0) throw new Error(`银辉模板引用了未配置工作表：${token}`)
      return { sheet: target, ref: token.slice(split + 1).replace(/\$/g, '') }
    }
    const atom = (): FormulaValue => {
      const token = tokens[at++] || ''
      if (token === '+' || token === '-') { const v = atom(); return isError(v) ? v : number(v) * (token === '-' ? -1 : 1) }
      if (token === '(') { const v = compare(); if (tokens[at++] !== ')') throw new Error('银辉公式括号无效'); return v }
      if (token.startsWith('"')) return token.slice(1, -1).replace(/""/g, '"')
      if (/^\d/.test(token)) return Number(token)
      if (tokens[at] === '(') {
        at++; const args: FormulaValue[] = []
        if (tokens[at] !== ')') do { args.push(compare()); if (tokens[at] !== ',') break; at++ } while (at < tokens.length)
        if (tokens[at++] !== ')') throw new Error('银辉公式参数无效')
        if (token === 'IF') return isError(args[0]!) ? args[0]! : args[0] ? args[1]! : args[2]!
        if (token === 'ISERROR') return isError(args[0]!)
        if (token === 'IFERROR') return isError(args[0]!) ? args[1]! : args[0]!
        if (token === 'SUM') {
          const flat = args.flat(3) as FormulaValue[]; const error = flat.find(isError)
          return error || flat.reduce<number>((a, b) => a + (typeof b === 'number' ? b : 0), 0)
        }
        throw new Error(`银辉模板出现未验证公式函数 ${token}`)
      }
      if (/\$?[A-Z]{1,3}\$?\d+$/.test(token)) {
        const start = readRef(token)
        if (tokens[at] !== ':') return valueAt(start.sheet, start.ref)
        at++; const end = readRef(tokens[at++] || '')
        const values: FormulaValue[] = []
        for (let r = Number(start.ref.match(/\d+/)?.[0]); r <= Number(end.ref.match(/\d+/)?.[0]); r++) {
          for (let c = column(start.ref); c <= column(end.ref); c++) values.push(valueAt(start.sheet, `${String.fromCharCode(64 + c)}${r}`))
        }
        return values
      }
      throw new Error(`银辉模板出现未验证公式内容 ${token}`)
    }
    const op = (a: FormulaValue, b: FormulaValue, operator: string): FormulaValue => {
      if (isError(a)) return a; if (isError(b)) return b
      const x = number(a); const y = number(b)
      if (operator === '+') return x + y; if (operator === '-') return x - y; if (operator === '*') return x * y
      if (operator === '/') return y === 0 ? { error: '#DIV/0!' } : x / y
      if (operator === '=') return x === y; if (operator === '<>') return x !== y
      if (operator === '<') return x < y; if (operator === '>') return x > y
      return operator === '<=' ? x <= y : x >= y
    }
    const product = (): FormulaValue => { let a = atom(); while (['*', '/'].includes(tokens[at] || '')) { const operator = tokens[at++]!; a = op(a, atom(), operator) } return a }
    const add = (): FormulaValue => { let a = product(); while (['+', '-'].includes(tokens[at] || '')) { const operator = tokens[at++]!; a = op(a, product(), operator) } return a }
    const compare = (): FormulaValue => { let a = add(); while (['=', '<>', '<', '>', '<=', '>='].includes(tokens[at] || '')) { const operator = tokens[at++]!; a = op(a, add(), operator) } return a }
    const result = compare()
    if (at !== tokens.length) throw new Error(`银辉模板公式未完整解析：${expression}`)
    return result
  }
  docs.forEach((doc, sheet) => {
    for (const [ref] of formulas[sheet]!) {
      const cell = cells[sheet]!.get(ref)!; const value = valueAt(sheet, ref)
      elements(cell, 'v').forEach((v) => v.remove()); elements(cell, 'is').forEach((v) => v.remove()); cell.removeAttribute('t')
      const v = doc.createElementNS(NS, 'v')
      if (isError(value)) { cell.setAttribute('t', 'e'); v.textContent = value.error }
      else if (typeof value === 'string') { cell.setAttribute('t', 'str'); v.textContent = value }
      else v.textContent = String(value === true ? 1 : value === false ? 0 : value)
      cell.append(v)
    }
    zip[`xl/worksheets/sheet${sheet + 1}.xml`] = serialize(doc)
  })
}

function writer(zip: Record<string, Uint8Array>, index: number) {
  const path = `xl/worksheets/sheet${index + 1}.xml`
  const doc = xml(strFromU8(zip[path]!))
  const sheetData = elements(doc, 'sheetData')[0]!
  const cells = new Map(elements(doc, 'c').map((c) => [c.getAttribute('r'), c]))
  const rows = new Map(elements(doc, 'row').map((r) => [Number(r.getAttribute('r')), r]))
  const mergedInteriors = new Set<string>()
  for (const merge of elements(doc, 'mergeCell')) {
    const [start, end] = (merge.getAttribute('ref') || '').split(':')
    if (!start || !end) continue
    for (let r = Number(start.match(/\d+/)?.[0]); r <= Number(end.match(/\d+/)?.[0]); r++) for (let c = column(start); c <= column(end); c++) {
      const ref = `${String.fromCharCode(64 + c)}${r}`
      if (ref !== start) mergedInteriors.add(ref)
    }
  }
  const set = (ref: string, value: string | number | null) => {
    if (mergedInteriors.has(ref)) {
      if (value === null || value === '' || value === 'pc') return
      throw new Error(`银辉写入位置 ${YINHUI_SHEET_NAMES[index]}!${ref} 位于合并格内部，不能破坏原客表格式`)
    }
    let cell = cells.get(ref)
    if (!cell && (value === 'pc' || value === '' || value === null || value === 0)) return
    if (!cell) {
      const rowNumber = Number(ref.match(/\d+/)?.[0]); let row = rows.get(rowNumber)
      if (!row) {
        row = doc.createElementNS(NS, 'row'); row.setAttribute('r', String(rowNumber))
        sheetData.insertBefore(row, Array.from(sheetData.children).find((r) => Number(r.getAttribute('r')) > rowNumber) || null); rows.set(rowNumber, row)
      }
      cell = doc.createElementNS(NS, 'c'); cell.setAttribute('r', ref)
      row.insertBefore(cell, Array.from(row.children).find((c) => column(c.getAttribute('r') || '') > column(ref)) || null); cells.set(ref, cell)
    }
    // Formula XML (including shared-formula attributes) belongs to the customer's template.
    // Never replace it with a converter-generated formula.
    const formula = elements(cell, 'f')[0]?.cloneNode(true)
    cell.replaceChildren(); cell.removeAttribute('t')
    if (formula) cell.append(formula)
    if (typeof value === 'string') {
      cell.setAttribute('t', 'inlineStr'); const is = doc.createElementNS(NS, 'is'); const t = doc.createElementNS(NS, 't'); t.textContent = value; is.append(t); cell.append(is)
    } else if (typeof value === 'number') {
      if (!Number.isFinite(value)) throw new Error(`银辉输出 ${ref} 不是有效数字`)
      const v = doc.createElementNS(NS, 'v'); v.textContent = String(value); cell.append(v)
    }
  }
  return { set, doc, has: (ref: string) => cells.has(ref), save: () => { zip[path] = serialize(doc) } }
}
export function createYinhuiCustomerQuoteWorkbook(result: YinhuiConversionResult, template: ArrayBuffer, options: { missingMaterialPricesConfirmed?: boolean } = {}) {
  const d = result.quoteData
  validateYinhuiExport(d)
  const total = yinhuiTotals(d)
  const pricePending = total.missingMaterialPrices.length > 0
  if (pricePending && !options.missingMaterialPricesConfirmed) throw new Error(`缺少银辉报客料价：${total.missingMaterialPrices.join('、')}。请确认单价留空、合计暂未包含这些料价后再导出。`)
  const layout = templateLayout(parseXlsxWorkbook(template))
  const first = layout.bom[0]!
  for (const [label, count, capacity] of [
    ['Tool Plan', d.tools.length, layout.tools[0]! - 8],
    ['塑料外购', d.plastic.length, first.mechanical - first.plastic - 2],
    ['五金', d.mechanical.length, first.electronic - first.mechanical - 1],
    ['电子', d.electronic.length, first.fabric - first.electronic - 1],
    ['车缝', (d.fabric || []).length, first.labor - first.fabric - 1],
    ['包装', d.packagingRows.length, 12],
  ] as const) if (count > capacity) throw new Error(`银辉${label}有 ${count} 行，超过该客表 ${capacity} 行容量，不能截断明细`)
  const zip = unzipSync(sanitizeYinhuiTemplate(template))
  const date = excelDateSerial(new Date(`${d.quoteDate}T12:00:00Z`))
  const summary = writer(zip, 0); const s = summary.set
  s('C3', 'Royal Regent Products International Ltd'); s('H3', date)
  s('C4', d.productName); s('C5', d.model); s('C6', pricePending ? [d.stage, 'PRICE PENDING'].filter(Boolean).join(' / ') : d.stage); s('H5', d.packaging); s('H6', d.moq); s('K11', YINHUI_HKD_USD)
  ;[total.plastic, total.mechanical, total.electronic, total.fabric, total.labour, 0].forEach((v, i) => s(`H${13 + i}`, v))
  for (let r = 20; r <= 25; r++) s(`H${r}`, 0)
  s('H27', total.packaging); s('H28', d.packagingLaborHkd); s('H29', 0)
  s('G12', 1); s('G19', 0); s('G26', 1)
  for (const [r, freight] of [[34, d.freightLclHkd!], [36, d.freightFclHkd!]]) { s(`G${r}`, 1); s(`H${r}`, freight!) }
  d.colorBoxCm.forEach((v, i) => s(`${['I', 'J', 'K'][i]}44`, v))
  d.cartonCm.forEach((v, i) => s(`${['I', 'J', 'K'][i]}46`, v)); s('H46', d.cartonPack)
  s('H49', total.tooling); s('H50', 0); s('H52', total.tooling)
  const battery = d.electronic.filter(r => r.isBattery).map(r => r.description).join('; ')
  s('D57', battery ? 'included' : 'not included'); s('F57', battery); s('D58', d.adaptor); s('D59', d.tryMe)
  summary.save()
  const rowCosts = (set: typeof s, list: YinhuiCostRow[], start: number, count: number, reserved: number[] = []) => {
    if (list.length > count - reserved.length) throw new Error('银辉明细超过原模板可填写行数，不能覆盖合并格或截断明细')
    let itemIndex = 0
    for (let i = 0; i < count; i++) {
      const r = start + i; const line = reserved.includes(r) ? undefined : list[itemIndex++]
      set(`A${r}`, i + 1); set(`B${r}`, line?.description || ''); set(`G${r}`, line ? 'pc' : '')
      set(`H${r}`, line?.quantity ?? null); set(`I${r}`, line ? line.amountHkd / line.quantity : null)
      set(`J${r}`, line?.amountHkd || 0)
    }
  }
  const packaging = writer(zip, 1); const p = packaging.set
  p('B3', 'Royal Regent Products International Ltd'); p('I3', date); p('B4', d.model); p('B5', d.productName)
  p('D31', d.packaging); p('D32', d.cartonPack); p('D10', d.cartonPack)
  const packReserved = elements(packaging.doc, 'mergeCell').some(m => m.getAttribute('ref') === 'I33:I34') ? [34] : []
  rowCosts(p, [], 11, 12); rowCosts(p, d.packagingRows, 33, 12, packReserved)
  const colorIndex = d.packagingRows.findIndex(r => /color box/i.test(r.description))
  if (colorIndex >= 0) d.colorBoxCm.forEach((v, i) => p(`${['C', 'D', 'E'][i]}${33 + colorIndex}`, v))
  d.cartonCm.forEach((v, i) => p(`${['C', 'D', 'E'][i]}47`, v))
  p('H47', 1); p('I47', d.carton.amountHkd); p('G47', 'pc'); p('J47', d.carton.amountHkd)
  p('K49', d.packagingLaborHkd); p('K48', 0); p('K50', 0)
  packaging.save()
  for (const second of [false, true]) {
    const w = writer(zip, second ? 3 : 2); const b = w.set; const area = layout.bom[second ? 1 : 0]!
    b('B3', 'Royal Regent Products International Ltd'); b('J3', date); b('B4', d.model); b('B5', d.productName)
    const molded = second ? 0 : total.plastic - d.plastic.reduce((a, r) => a + r.amountHkd, 0)
    b(`B${area.plastic + 1}`, 'Injection Plastic'); b(`G${area.plastic + 1}`, 'g')
    b(`H${area.plastic + 1}`, second ? 0 : d.tools.reduce((a, r) => a + r.weightG, 0))
    b(`I${area.plastic + 1}`, molded); b(`J${area.plastic + 1}`, molded)
    rowCosts(b, second ? [] : d.plastic, area.plastic + 2, area.mechanical - area.plastic - 2)
    rowCosts(b, second ? [] : d.mechanical, area.mechanical + 1, area.electronic - area.mechanical - 1)
    rowCosts(b, second ? [] : d.electronic, area.electronic + 1, area.fabric - area.electronic - 1)
    rowCosts(b, second ? [] : d.fabric || [], area.fabric + 1, area.labor - area.fabric - 1)
    b(`J${area.labor + 1}`, second ? 0 : total.injection)
    for (const [offset, amount] of [[2, d.assemblyHkd], [8, d.sprayingHkd]]) {
      b(`H${area.labor + offset!}`, second ? 0 : 1); b(`I${area.labor + offset!}`, second ? 0 : amount!); b(`J${area.labor + offset!}`, second ? 0 : amount!)
    }
    w.save()
  }
  for (const second of [false, true]) {
    const w = writer(zip, second ? 5 : 4); const t = w.set; const end = layout.tools[second ? 1 : 0]!
    const formulas = formulaMap(w.doc)
    t('C3', 'Royal Regent Products International Ltd'); t('M3', date); t('C4', d.model); t('C5', d.productName)
    for (let r = 8; r < end; r++) {
      const item = second ? undefined : d.tools[r - 8]
      if (item) {
        if (w.has(`A${r}`)) t(`A${r}`, r - 7)
        t(`B${r}`, item.moldNo); t(`C${r}`, item.partNo); t(`D${r}`, item.description)
        const weightFormula = (formulas.get(`H${r}`) || '').replace(/[$\s]/g, '')
        const constantFactor = weightFormula.match(new RegExp(`^(?:G${r}\\*([0-9.]+)|([0-9.]+)\\*G${r})$`))
        const divisor = constantFactor ? Number(constantFactor[1] || constantFactor[2]) : weightFormula.includes(`F${r}`) ? item.cavity : weightFormula.includes(`E${r}`) ? item.usage : 1
        if (item.weightG > 0 && divisor <= 0) throw new Error(`银辉 Tool Plan 第 ${r} 行原重量公式要求有效用量/出模数`)
        t(`E${r}`, item.usage); t(`F${r}`, item.cavity); t(`G${r}`, divisor ? item.weightG / divisor : 0)
        t(`I${r}`, item.material); t(`N${r}`, item.laborHkd)
        if (w.has(`O${r}`) || item.weightG > 0) t(`O${r}`, yinhuiMaterialPrice(d, item.material))
        t(`R${r}`, item.toolingHkd)
      }
      const plasticCost = item ? item.weightG * (yinhuiMaterialPrice(d, item.material) ?? 0) / 1000 : 0
      t(`H${r}`, item?.weightG || 0); t(`P${r}`, plasticCost); t(`Q${r}`, plasticCost + (item?.laborHkd || 0))
    }
    for (const [col, value] of [['E', d.tools.reduce((a,r) => a + r.usage, 0)], ['H', d.tools.reduce((a,r) => a + r.weightG, 0)], ['N', total.injection], ['P', total.plastic - d.plastic.reduce((a,r) => a + r.amountHkd, 0)], ['R', total.tooling]] as const) t(`${col}${end}`, second ? 0 : value)
    w.save()
  }
  if (d.image) {
    const ext = d.image.extension
    zip[`xl/media/product.${ext}`] = new Uint8Array(d.image.bytes)
    zip['xl/drawings/drawing1.xml'] = strToU8(`<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="${REL}"><xdr:twoCellAnchor><xdr:from><xdr:col>9</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>2</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from><xdr:to><xdr:col>12</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>8</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to><xdr:pic><xdr:nvPicPr><xdr:cNvPr id="1" name="Product image"/><xdr:cNvPicPr><a:picLocks noChangeAspect="1"/></xdr:cNvPicPr></xdr:nvPicPr><xdr:blipFill><a:blip r:embed="image"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill><xdr:spPr><a:xfrm><a:off x="7400000" y="540000"/><a:ext cx="3200000" cy="1400000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr></xdr:pic><xdr:clientData/></xdr:twoCellAnchor></xdr:wsDr>`)
    const rels = (body: string) => strToU8(`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${body}</Relationships>`)
    zip['xl/drawings/_rels/drawing1.xml.rels'] = rels(`<Relationship Id="image" Type="${REL}/image" Target="../media/product.${ext}"/>`)
    zip['xl/worksheets/_rels/sheet1.xml.rels'] = rels(`<Relationship Id="product" Type="${REL}/drawing" Target="../drawings/drawing1.xml"/>`)
    zip['xl/worksheets/sheet1.xml'] = strToU8(strFromU8(zip['xl/worksheets/sheet1.xml']!).replace('</worksheet>', `<drawing xmlns:r="${REL}" r:id="product"/></worksheet>`))
    zip['[Content_Types].xml'] = strToU8(strFromU8(zip['[Content_Types].xml']!).replace('</Types>', `<Default Extension="${ext}" ContentType="image/${ext === 'jpg' ? 'jpeg' : 'png'}"/><Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/></Types>`))
  }
  // Formula caches are refreshed below without changing the customer's formula expressions.
  recalculateTemplate(zip)
  const output = zipSync(zip)
  const checked = parseXlsxWorkbook(output.buffer.slice(output.byteOffset, output.byteOffset + output.byteLength) as ArrayBuffer)
  for (let r = 8; r < layout.tools[0]!; r++) {
    const actualWeight = Number(checked.sheets[4]?.rows[r - 1]?.[7] || 0)
    if (Math.abs(actualWeight - (d.tools[r - 8]?.weightG || 0)) > .000001) throw new Error(`银辉 TOOL PLAN (1)!H${r} 原料重公式结果与内部料重不一致；为保留原公式已阻止输出，请核对模板中的固定数值`)
  }
  const actual = Number(checked.sheets[0]?.rows[31]?.[9])
  if (!Number.isFinite(actual) || Math.abs(actual - total.exFactory) > .000001) throw new Error(`银辉原模板公式结果 ${actual} 与映射合计 ${total.exFactory} 不一致，已阻止输出，请核对映射位置`)
  return output
}

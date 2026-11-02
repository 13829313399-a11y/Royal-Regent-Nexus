import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'
import template from './huaxingThreeSixtyTemplate.json'
import { createXlsxWorkbook } from './xlsxLite'
import { stampPricingReference } from './pricingSettings'
import { calculateHuaxing360, validateHuaxing360Export, type H360Category, type Huaxing360Result } from './huaxingThreeSixty'

const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
type Cell = { style: number; inline?: string; formula?: string; value?: string | number; localFormula?: boolean }
type Row = { origin: number; copyFrom?: number; attrs: Record<string, string>; cells: Record<string, Cell> }
const columns = Array.from({ length: 30 }, (_, i) => i < 26 ? String.fromCharCode(65 + i) : `A${String.fromCharCode(65 + i - 26)}`)
const isColorBox = (description: string) => /彩盒/.test(description)
const isCarton = (description: string) => /^(?:纸箱|紙箱|外箱)(?:\s*[（(]|\s*$)/.test(description)

/** Updated RZR native layout; source costs remain authoritative. Only current data can add rows. */
export function createHuaxing360Workbook(result: Huaxing360Result): Uint8Array {
  validateHuaxing360Export(result)
  const calc = calculateHuaxing360(result), review = result.review
  const sourceRows = template.rows as unknown as Array<{ attrs: Record<string, string>; cells: Record<string, Cell> }>
  const rows: Row[] = sourceRows.map(r => ({ origin: Number(r.attrs.r), attrs: { ...r.attrs }, cells: structuredClone(r.cells) }))
  const original = (r: number) => rows.find(row => row.origin === r)!
  const cloneBefore = (before: number, from: number) => {
    const source = original(from)
    const row: Row = { origin: 0, copyFrom: from, attrs: { ...source.attrs }, cells: structuredClone(source.cells) }
    rows.splice(rows.indexOf(original(before)), 0, row)
    return row
  }
  const costs = (category: H360Category) => calc.costs.filter(c => c.category === category)
  const testing = calc.fees.filter(f => /测试费/.test(f.description))
  const tooling = calc.fees.filter(f => /模具费/.test(f.description))
  const otherFees = calc.fees.filter(f => !/测试费|模具费/.test(f.description))
  const otherFeeRow = otherFees.length ? cloneBefore(41, 40) : null
  if (otherFeeRow) for (const c of columns.slice(13)) otherFeeRow.cells[c] = { style: original(42).cells[c]?.style ?? 0 }
  const comments = (result.pricing.texts.comments ?? '').replace(/\r/g, '').split('\n')
  const commentRows = Array.from({ length: 7 }, (_, i) => original(53 + i))
  while (commentRows.length < comments.length) commentRows.push(cloneBefore(60, 56))
  const plasticRows = Array.from({ length: 29 }, (_, i) => original(63 + i))
  while (plasticRows.length < calc.plastic.length) plasticRows.push(cloneBefore(92, 89))
  const slots: Record<H360Category, Row[]> = {
    purchase: Array.from({ length: 13 }, (_, i) => original(97 + i)),
    // Original PCB blocks share amount cells vertically. Use only their visible anchors.
    electronic: [117, 118, 119, 120, 121, 145, 146].map(original),
    fabric: [161, 162, 163, 164].map(original),
    packaging: [172, 175, 176, 177, 178, 179].map(original),
    others: [187, 188, 189].map(original),
    labor: Array.from({ length: 14 }, (_, i) => original(199 + i)),
  }
  const extend: Record<H360Category, [number, number]> = { purchase: [110, 109], electronic: [153, 117], fabric: [166, 164], packaging: [181, 175], others: [191, 189], labor: [213, 206] }
  for (const category of Object.keys(slots) as H360Category[]) {
    const items = costs(category)
    // Dimension rows belong only to their matching item, including when a quotation lacks that item.
    const reservedEmpty = category === 'packaging' ? 2 - Number(items.some(c => isColorBox(c.description))) - Number(items.some(c => isCarton(c.description))) : 0
    while (slots[category].length < items.length + reservedEmpty) slots[category].push(cloneBefore(...extend[category]))
  }
  const rowNumber = (row: Row) => rows.indexOf(row) + 1
  const mapped = (r: number) => rowNumber(original(r))
  const moveFormula = (formula: string) => formula.replace(/(\$?[A-Z]{1,3})(\$?)(\d+)\b/g, (_, col, absolute, row) => `${col}${absolute}${mapped(Number(row))}`)
  const set = (row: Row, col: string, value: string | number, formula?: string) => {
    row.cells[col] = { style: row.cells[col]?.style ?? 0, value, ...(formula ? { formula, localFormula: true } : {}) }
  }
  const put = (ref: string, value: string | number, formula?: string) => set(original(Number(ref.match(/\d+/)![0])), ref.match(/[A-Z]+/)![0], value, formula)
  const formulaAt = (ref: string, value: string | number, formula: string) => put(ref, value, moveFormula(formula))

  put('C7', review.brand); put('D10', review.firstEtd); put('C12', review.productName)
  put('O7', result.pricing.texts.vendor_name ?? ''); put('O10', review.preparedBy)
  put('O12', Date.parse(`${review.quoteDate}T00:00:00Z`) / 86400000 + 25569)
  put('O14', review.revision); put('O16', review.moq!)
  if (review.toolingCount !== null) put('O23', review.toolingCount)
  put('G48', result.carton.quantity)
  if (review.quantityPerContainer !== null) put('L48', review.quantityPerContainer)
  put('L49', result.freight.find(f => f.key === review.route)?.label ?? '')
  put('P47', result.pricing.rates.hkd_usd!)
  put('O48', '匯率1美元=港幣')
  comments.forEach((line, i) => set(commentRows[i]!, 'A', line))
  // Dimensions retain their original packaging fields; commercial comments stay in the comments area.
  result.colorBox.forEach((n, i) => put(`${['C', 'D', 'E'][i]}173`, n))
  result.carton.dimensions.forEach((n, i) => put(`${['G', 'I', 'J'][i]}179`, n))
  put('K179', result.carton.quantity)
  calc.plastic.forEach((p, i) => {
    const row = plasticRows[i]!, r = rowNumber(row)
    set(row, 'A', p.moldNo); set(row, 'B', p.description); set(row, 'E', p.material); set(row, 'G', p.up)
    // I holds the source's whole-set weight; the original J=I formula must never multiply it by Up.
    set(row, 'I', p.weightG); set(row, 'J', p.weightG, `I${r}`)
    set(row, 'K', p.price!); set(row, 'L', p.totalUsd, `J${r}*K${r}/1000`)
    set(row, 'M', p.machine); set(row, 'P', p.moldingUsd)
  })
  const writeCost = (row: Row, cost: (typeof calc.costs)[number], index: number, category: H360Category) => {
    const r = rowNumber(row), quantityColumn = category === 'labor' ? 'M' : 'L'
    set(row, 'A', index + (category === 'labor' ? 2 : 1)); set(row, 'B', cost.description)
    set(row, quantityColumn, cost.quantity); set(row, 'O', cost.totalUsd / cost.quantity)
    set(row, 'P', cost.totalUsd, `${quantityColumn}${r}*O${r}`)
    if (category === 'labor') set(row, 'N', '每套產品')
  }
  for (const category of Object.keys(slots) as H360Category[]) {
    const used = new Set<Row>()
    const preferredRow = (cost: (typeof calc.costs)[number]): Row | undefined => {
      if (category === 'packaging') {
        if (isColorBox(cost.description)) return original(172)
        if (isCarton(cost.description)) return original(179)
      } else if (category === 'electronic') {
        if (/RX|接收/i.test(cost.description)) return original(117)
        if (/TX|发射|發射/i.test(cost.description)) return original(145)
      } else if (category === 'labor') {
        const label = `${cost.description} ${cost.originalCategory}`
        const target = ([
          [/真空|电镀|電鍍/, 199], [/移印/, 200], [/片模/, 201], [/夹模|夾模/, 202], [/喷油|噴油|喷漆|噴漆/, 203],
          [/丝印|絲印/, 204], [/电子|電子/, 205], [/包装|包裝/, 211], [/装配|裝配/, 206], [/裁剪/, 207],
          [/车缝|車縫|缝制|縫製/, 208], [/手缝|手縫/, 209], [/木材|切割/, 210], [/车发|車髮|梳发|梳髮/, 212],
        ] as Array<[RegExp, number]>).find(([pattern]) => pattern.test(label))?.[1]
        if (target) return original(target)
      }
    }
    // Reserve dimension/specific labor rows before assigning general items to remaining slots.
    const ordered = costs(category).map((cost, index) => ({ cost, index, preferred: preferredRow(cost) }))
      .sort((a, b) => Number(!!b.preferred) - Number(!!a.preferred))
    ordered.forEach(({ cost, index, preferred }) => {
      const row = preferred && !used.has(preferred) ? preferred : slots[category].find(r => !used.has(r) && (category !== 'packaging' || ![172, 179].includes(r.origin)))!
      used.add(row); writeCost(row, cost, index, category)
    })
    slots[category].filter(row => category === 'labor' || used.has(row)).forEach((row, i) => set(row, 'A', i + (category === 'labor' ? 2 : 1)))
  }
  put('A197', 1); put('B197', 'MOLDING LABOR\u00a0啤塑人工'); put('N197', '每套產品')
  formulaAt('P197', calc.plastic.reduce((a, p) => a + p.moldingUsd, 0), 'P92')
  const totals: Array<[number, number, number, string]> = [[92, 63, 91, 'L'], [111, 97, 110, 'P'], [154, 116, 153, 'P'], [167, 160, 166, 'P'], [182, 172, 181, 'P'], [192, 187, 191, 'P'], [214, 197, 213, 'P']]
  for (const [total, start, end, col] of totals) {
    const last = total === 92 ? mapped(total) - 1 : mapped(end)
    put(`${col}${total}`, 0, `SUM(${col}${mapped(start)}:${col}${last})`)
  }
  put('J92', 0, `SUM(J${mapped(63)}:J${mapped(92) - 1})`)
  put('P92', 0, `SUM(P${mapped(63)}:P${mapped(92) - 1})`)
  put('M35', result.pricing.rates.scrap_rate!); put('M36', result.pricing.rates.markup_rate!); put('P36', result.pricing.rates.markup_rate!)
  if (result.pricing.rates.scrap_include_labor !== 1) {
    formulaAt('L35', calc.scrapUsd, 'L32*M35')
    formulaAt('O35', calc.scrapUsd, 'O32*P35')
  }
  put('L38', calc.freightUsd)
  for (const [ref, fees, allocationKey] of [['40', testing, 'testing_allocation_qty'], ['43', tooling, 'tooling_allocation_qty']] as const) {
    put(`E${ref}`, fees.reduce((n, f) => n + f.totalUsd!, 0)); put(`I${ref}`, result.pricing.rates[allocationKey]!)
  }
  if (otherFeeRow) {
    const r = rowNumber(otherFeeRow)
    set(otherFeeRow, 'C', 'Other Charges 其他費用 :')
    set(otherFeeRow, 'E', otherFees.reduce((n, f) => n + f.totalUsd!, 0)); set(otherFeeRow, 'I', result.pricing.rates.sample_allocation_qty!)
    set(otherFeeRow, 'L', 0, `E${r}/I${r}`)
    put('L41', 0, `SUM(L${mapped(39)}:M${r})`)
    // Preserve the original NIL convention for a quotation without tooling charges.
    put('L44', 0, `IF(SUM(L${mapped(43)}:M${mapped(43)})=0,"NIL",SUM(L${mapped(39)},L${mapped(40)}:L${r},L${mapped(43)}))`)
  }
  for (const r of [27, 28, 30, 31, 33, 34, 36, 37, 39, 41, 42, 44, 48, 49]) put(`AD${r}`, 0)
  const merges = template.merges.map(moveFormula)
  for (const row of rows.filter(r => r.copyFrom)) {
    const source = row.copyFrom!, target = rowNumber(row)
    for (const merge of template.merges) {
      const match = merge.match(/^([A-Z]+)(\d+):([A-Z]+)(\d+)$/)!
      if (Number(match[2]) === source && Number(match[4]) === source && (row !== otherFeeRow || match[1]! <= 'M')) merges.push(`${match[1]}${target}:${match[3]}${target}`)
    }
  }
  const cells = new Map<string, Cell>()
  rows.forEach((row, i) => Object.entries(row.cells).forEach(([col, cell]) => {
    if (cell.formula && !cell.localFormula) cell.formula = moveFormula(cell.formula)
    cells.set(`${col}${i + 1}`, cell)
  }))
  recalculate(cells)
  const xmlRows = rows.map((row, i) => {
    const attrs = { ...row.attrs, r: String(i + 1) }
    return `<row ${Object.entries(attrs).map(([k, v]) => `${k}="${esc(v)}"`).join(' ')}>${Object.entries(row.cells).map(([col, cell]) => {
      const ref = `${col}${i + 1}`, style = `r="${ref}" s="${cell.style}"`
      if (cell.formula) return `<c ${style}${typeof cell.value === 'string' ? ' t="str"' : ''}><f>${esc(cell.formula)}</f><v>${esc(String(cell.value ?? 0))}</v></c>`
      if (typeof cell.value === 'number') return `<c ${style}><v>${cell.value}</v></c>`
      if (typeof cell.value === 'string') return `<c ${style} t="inlineStr"><is><t xml:space="preserve">${esc(cell.value)}</t></is></c>`
      return cell.inline ? `<c ${style} t="inlineStr">${cell.inline}</c>` : `<c ${style}/>`
    }).join('')}</row>`
  }).join('')
  const zip = unzipSync(createXlsxWorkbook([{ name: 'Breakdown', rows: [] }]))
  zip['xl/styles.xml'] = strToU8(template.styles); zip['xl/theme/theme1.xml'] = strToU8(template.theme)
  zip['xl/media/logo.png'] = Uint8Array.from(atob(template.logo), c => c.charCodeAt(0))
  const drawing = new DOMParser().parseFromString(template.drawing, 'application/xml')
  const anchors = Array.from(drawing.documentElement.children)
  if (!result.image) anchors[1]!.remove()
  else {
    zip[`xl/media/product.${result.image.extension}`] = new Uint8Array(result.image.bytes)
    const product = anchors[1]!, transform = product.getElementsByTagNameNS('*', 'xfrm')[0]!
    const extent = transform.getElementsByTagNameNS('*', 'ext')[0]!
    const frameWidth = Number(extent.getAttribute('cx')), frameHeight = Number(extent.getAttribute('cy'))
    const ratio = result.image.width / result.image.height
    if (Number.isFinite(ratio) && ratio > 0 && Math.abs(ratio / (frameWidth / frameHeight) - 1) > .005) {
      const width = Math.round(Math.min(frameWidth, frameHeight * ratio)), height = Math.round(Math.min(frameHeight, frameWidth / ratio))
      extent.setAttribute('cx', String(width)); extent.setAttribute('cy', String(height))
      // The native product anchor already uses one-cell behavior. Keep its exact top-left,
      // but use an explicit extent so a different source photo fits without stretching.
      const ns = product.namespaceURI!, fitted = drawing.createElementNS(ns, 'xdr:oneCellAnchor')
      const from = product.getElementsByTagNameNS('*', 'from')[0]!, size = drawing.createElementNS(ns, 'xdr:ext')
      size.setAttribute('cx', String(width)); size.setAttribute('cy', String(height))
      fitted.append(from, size, product.getElementsByTagNameNS('*', 'pic')[0]!, product.getElementsByTagNameNS('*', 'clientData')[0]!)
      product.replaceWith(fitted)
    }
  }
  zip['xl/drawings/drawing1.xml'] = strToU8(new XMLSerializer().serializeToString(drawing))
  zip['xl/drawings/_rels/drawing1.xml.rels'] = strToU8(`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/logo.png"/>${result.image ? `<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/product.${result.image.extension}"/>` : ''}</Relationships>`)
  zip['xl/worksheets/_rels/sheet1.xml.rels'] = strToU8('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/></Relationships>')
  zip['xl/_rels/workbook.xml.rels'] = strToU8(strFromU8(zip['xl/_rels/workbook.xml.rels']!).replace('</Relationships>', '<Relationship Id="rIdTheme" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/></Relationships>'))
  zip['[Content_Types].xml'] = strToU8(strFromU8(zip['[Content_Types].xml']!).replace('</Types>', '<Default Extension="png" ContentType="image/png"/><Default Extension="jpeg" ContentType="image/jpeg"/><Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/><Override PartName="/xl/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/></Types>'))
  zip['xl/worksheets/sheet1.xml'] = strToU8(`<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><dimension ref="A1:AD${rows.length}"/><sheetViews><sheetView workbookViewId="0"/></sheetViews>${template.sheetFormatPr}${template.cols}<sheetData>${xmlRows}</sheetData><mergeCells count="${merges.length}">${merges.map(ref => `<mergeCell ref="${ref}"/>`).join('')}</mergeCells>${template.pageMargins}${template.pageSetup}${template.headerFooter}<drawing r:id="rId1"/></worksheet>`)
  return stampPricingReference(zipSync(zip), result.pricing)
}

/** Bounded evaluator for the trusted original template's SUM/IF/arithmetic formulas, never user text. */
function recalculate(cells: Map<string, Cell>) {
  type Value = number | string | Value[]
  const complete = new Set<string>(), visiting = new Set<string>()
  const numeric = (v: Value): number => typeof v === 'number' ? v : 0
  const sum = (v: Value): number => Array.isArray(v) ? v.reduce<number>((n, item) => n + sum(item), 0) : numeric(v)
  const evaluateCell = (reference: string): Value => {
    const ref = reference.replace(/\$/g, ''), cell = cells.get(ref)
    if (!cell?.formula) return cell?.value ?? 0
    if (complete.has(ref)) return cell.value ?? 0
    if (visiting.has(ref)) throw new Error(`客表公式循环引用：${ref}`)
    visiting.add(ref)
    const tokens = cell.formula.match(/"[^"]*"|\$?[A-Z]{1,3}\$?\d+|[A-Z]+|\d*\.?\d+|[()+*/,:=<>-]/g) ?? []
    let i = 0
    const expression = (minimum = 0): Value => {
      let value: Value
      const token = tokens[i++]!
      if (token === '(') { value = expression(); if (tokens[i++] !== ')') throw new Error('公式括号不完整') }
      else if (token === '-') value = -numeric(expression(4))
      else if (/^"/.test(token)) value = token.slice(1, -1)
      else if (/^(SUM|IF)$/.test(token)) {
        if (tokens[i++] !== '(') throw new Error('公式函数不完整')
        const args: Value[] = []
        do { args.push(expression()) } while (tokens[i] === ',' && ++i)
        if (tokens[i++] !== ')') throw new Error('公式函数参数不完整')
        value = token === 'SUM' ? sum(args) : args[0] ? args[1]! : args[2]!
      } else if (/^\$?[A-Z]+\$?\d+$/.test(token)) {
        if (tokens[i] === ':') {
          i++; const end = tokens[i++]!
          const startRow = Number(token.match(/\d+/)![0]), endRow = Number(end.match(/\d+/)![0])
          const startCol = columns.indexOf(token.match(/[A-Z]+/)![0]), endCol = columns.indexOf(end.match(/[A-Z]+/)![0])
          value = []
          for (let r = startRow; r <= endRow; r++) for (let c = startCol; c <= endCol; c++) value.push(evaluateCell(`${columns[c]}${r}`))
        } else value = evaluateCell(token)
      } else { value = Number(token); if (!Number.isFinite(value)) throw new Error(`不支持的原版公式：${cell.formula}`) }
      while (true) {
        const op = tokens[i] ?? '', priority = ({ '=': 1, '>': 1, '<': 1, '+': 2, '-': 2, '*': 3, '/': 3 } as Record<string, number>)[op] ?? 0
        if (!priority || priority < minimum) break
        i++; const right = numeric(expression(priority + 1)), left = numeric(value)
        value = op === '+' ? left + right : op === '-' ? left - right : op === '*' ? left * right : op === '/' ? left / right : Number(op === '=' ? left === right : op === '>' ? left > right : left < right)
      }
      return value
    }
    const value = expression()
    if (i !== tokens.length || Array.isArray(value) || (typeof value === 'number' && !Number.isFinite(value))) throw new Error(`客表公式计算失败：${ref}`)
    cell.value = value; visiting.delete(ref); complete.add(ref); return value
  }
  for (const [ref, cell] of cells) if (cell.formula) evaluateCell(ref)
}

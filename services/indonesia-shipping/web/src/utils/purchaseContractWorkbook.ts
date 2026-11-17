import * as XLSX from 'xlsx-js-style'
import JSZip from 'jszip'
import { DOMParser, XMLSerializer } from '@xmldom/xmldom'
import type { PoEntity } from './poNumber'

const companySheets: [PoEntity, string][] = [
  ['HD_INDUSTRY', '华登实业'], ['HD_GLOBAL', '华登全球'], ['HSY', '华胜益'],
]

/** Match Excel's 15 significant digits, then round cents halfway away from zero. */
export function roundPurchaseContractAmount(amount: number): number {
  if (!Number.isFinite(amount)) return amount
  const sign = amount < 0 ? -1 : 1
  const magnitude = Number(Math.abs(amount).toPrecision(15))
  // At this scale the 15-digit value has no fractional cents; avoid exponent overflow.
  if (magnitude >= 1e15) return sign * magnitude
  const [coefficient, exponent = '0'] = String(magnitude).split('e')
  const cents = Math.round(Number(`${coefficient}e${Number(exponent) + 2}`))
  return sign * cents / 100
}

/** 数量沿用单位精度，按原金额反算单价，避免数量舍入改变金额。 */
export function setPurchaseContractLineAmounts(ws: XLSX.WorkSheet, row: number, quantity: number, amount: number, quantityDigits: number, unit?: string) {
  const exportQuantity = Number(quantity.toFixed(quantityDigits))
  const exportAmount = roundPurchaseContractAmount(amount)
  const price = exportQuantity !== 0 ? exportAmount / exportQuantity : 0
  const isKilogram = ['KGM', 'KG', '千克', '公斤'].includes(String(unit || '').trim().toUpperCase())
  ws[`D${row}`] = { ...ws[`D${row}`], t: 'n', v: exportQuantity, z: isKilogram ? '0.00' : `0.${'#'.repeat(quantityDigits)}` }
  // 数量舍入为零时无法反算单价；留空单价并保留原金额，不产生除零或错误的零金额。
  ws[`F${row}`] = exportQuantity === 0 && exportAmount !== 0
    ? { ...ws[`F${row}`], t: 's', v: '', f: undefined }
    : { ...ws[`F${row}`], t: 'n', v: price, z: '0.0000' } // 仅显示四位，计算保留完整单价。
  ws[`G${row}`] = {
    ...ws[`G${row}`], t: 'n', v: exportAmount,
    f: exportQuantity === 0 && exportAmount !== 0 ? undefined : `ROUND(D${row}*F${row},2)`, z: '0.00',
  }
}

/** 公司抬头 22 号、购销合同标题 18 号，其余 12 号；全部加粗。合并前逐单应用。 */
export function formatPurchaseContractFonts(ws: XLSX.WorkSheet) {
  for (const [address, cell] of Object.entries(ws)) {
    if (address.startsWith('!')) continue
    const size = address === 'A1' ? 22 : address === 'A4' ? 18 : 12
    cell.s = { ...cell.s, font: { ...cell.s?.font, sz: size, bold: true } }
  }
}

/** 合计/大写按采购合同样表定位；sumRow 为从 0 开始的行号，不改金额或公式。 */
export function formatPurchaseContractTotals(ws: XLSX.WorkSheet, sumRow: number) {
  const upperRow = sumRow + 1
  ws['!merges'] ||= []
  ws['!merges'].push(
    { s: { r: sumRow, c: 4 }, e: { r: sumRow, c: 5 } },
    { s: { r: sumRow, c: 6 }, e: { r: sumRow, c: 7 } },
    { s: { r: upperRow, c: 6 }, e: { r: upperRow, c: 7 } },
  )
  for (const [row, column] of [[sumRow, 4], [sumRow, 6], [upperRow, 4], [upperRow, 5], [upperRow, 6]]) {
    const cell = ws[XLSX.utils.encode_cell({ r: row, c: column })]
    if (!cell) continue
    cell.s = { ...cell.s, alignment: {
      ...cell.s?.alignment, horizontal: row === upperRow && column === 6 ? 'left' : 'center',
      vertical: 'center', wrapText: true,
    } }
  }
  // Merged cells do not reliably auto-fit in Excel/WPS; reserve enough height for
  // long Chinese amounts without widening the item table or auxiliary columns.
  const text = String(ws[XLSX.utils.encode_cell({ r: upperRow, c: 6 })]?.v || '')
  const textWidth = Array.from(text).reduce((width, char) => width + (char.charCodeAt(0) > 255 ? 2 : 1), 0)
  const width = (ws['!cols']?.[6]?.wch || 13) + (ws['!cols']?.[7]?.wch || 18) - 2
  ws['!rows'] ||= []
  ws['!rows'][sumRow] = { ...ws['!rows'][sumRow], hpt: Math.max(ws['!rows'][sumRow]?.hpt || 0, 24) }
  ws['!rows'][upperRow] = { ...ws['!rows'][upperRow], hpt: Math.max(24, Math.ceil(textWidth / width) * 18 + 6) }
}

/** 拼接系统生成的独立合同（公式仅引用合同内 D/F/G 列），保留样式和合并区域。 */
export function combinePurchaseContracts(contracts: { entity: PoEntity; ws: XLSX.WorkSheet }[]) {
  const wb = XLSX.utils.book_new()
  for (const [entity, name] of companySheets) {
    const group = contracts.filter(contract => contract.entity === entity)
    if (!group.length) continue
    const sheet: XLSX.WorkSheet = { '!merges': [], '!rows': [] }
    let offset = 0
    let lastCol = 0
    for (const { ws } of group) {
      const range = XLSX.utils.decode_range(ws['!ref'] || 'A1')
      lastCol = Math.max(lastCol, range.e.c)
      sheet['!cols'] ||= ws['!cols']?.map(col => ({ ...col }))
      for (const address of Object.keys(ws)) {
        if (address.startsWith('!')) continue
        const pos = XLSX.utils.decode_cell(address)
        const cell = { ...ws[address] }
        if (cell.f && offset) {
          cell.f = cell.f.replace(/(\$?[A-Z]{1,3})(\$?)(\d+)/g,
            (_: string, col: string, absolute: string, row: string) => `${col}${absolute}${Number(row) + offset}`)
        }
        sheet[XLSX.utils.encode_cell({ r: pos.r + offset, c: pos.c })] = cell
      }
      for (const merge of ws['!merges'] || []) {
        sheet['!merges']!.push({ s: { ...merge.s, r: merge.s.r + offset }, e: { ...merge.e, r: merge.e.r + offset } })
      }
      ws['!rows']?.forEach((row, index) => { sheet['!rows']![index + offset] = { ...row } })
      offset += range.e.r + 3 // 两张合同之间空两行，不合并各自金额。
    }
    sheet['!ref'] = XLSX.utils.encode_range({ s: { r: 0, c: 0 }, e: { r: offset - 3, c: lastCol } })
    XLSX.utils.book_append_sheet(wb, sheet, name)
  }
  return wb
}

/** SheetJS does not serialize fit-to-page settings; add them without rewriting cells/styles. */
export async function applyPurchaseContractPrintLayout(buffer: ArrayBuffer | Uint8Array): Promise<ArrayBuffer> {
  const zip = await JSZip.loadAsync(buffer)
  const ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
  const relationshipNs = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
  const parser = new DOMParser(), serializer = new XMLSerializer()
  const workbook = parser.parseFromString(await zip.file('xl/workbook.xml')!.async('string'), 'application/xml')
  const rels = parser.parseFromString(await zip.file('xl/_rels/workbook.xml.rels')!.async('string'), 'application/xml')
  const targets = new Map(Array.from(rels.getElementsByTagName('Relationship')).map(node => [node.getAttribute('Id'), node.getAttribute('Target')!]))
  let names = workbook.getElementsByTagNameNS(ns, 'definedNames')[0]
  if (!names) {
    names = workbook.createElementNS(ns, 'definedNames')
    const afterNames = new Set(['calcPr', 'oleSize', 'customWorkbookViews', 'pivotCaches', 'smartTagPr', 'smartTagTypes', 'webPublishing', 'fileRecoveryPr', 'webPublishObjects', 'extLst'])
    const following = Array.from(workbook.documentElement!.childNodes).find(node => node.nodeType === 1 && afterNames.has(node.localName || ''))
    workbook.documentElement!.insertBefore(names, following || null)
  }
  for (const [index, sheet] of Array.from(workbook.getElementsByTagNameNS(ns, 'sheet')).entries()) {
    const target = targets.get(sheet.getAttributeNS(relationshipNs, 'id'))
    if (!target) throw new Error('采购合同工作表缺少文件关联')
    const pathParts = (target.startsWith('/') ? target.slice(1) : `xl/${target}`).split('/')
    const normalizedParts: string[] = []
    for (const part of pathParts) {
      if (part === '..') normalizedParts.pop()
      else if (part && part !== '.') normalizedParts.push(part)
    }
    const path = normalizedParts.join('/')
    const part = zip.file(path)
    if (!part) throw new Error('采购合同工作表文件不存在')
    const doc = parser.parseFromString(await part.async('string'), 'application/xml')
    const root = doc.documentElement!
    let properties = doc.getElementsByTagNameNS(ns, 'sheetPr')[0]
    if (!properties) {
      properties = doc.createElementNS(ns, 'sheetPr')
      root.insertBefore(properties, root.firstChild)
    }
    let fit = properties.getElementsByTagNameNS(ns, 'pageSetUpPr')[0]
    if (!fit) { fit = doc.createElementNS(ns, 'pageSetUpPr'); properties.appendChild(fit) }
    fit.setAttribute('fitToPage', '1')
    fit.setAttribute('autoPageBreaks', '1')

    const afterSetup = new Set(['headerFooter', 'rowBreaks', 'colBreaks', 'customProperties', 'cellWatches', 'ignoredErrors', 'smartTags', 'drawing', 'legacyDrawing', 'legacyDrawingHF', 'picture', 'oleObjects', 'controls', 'webPublishItems', 'tableParts', 'extLst'])
    let setup = doc.getElementsByTagNameNS(ns, 'pageSetup')[0]
    if (!setup) {
      setup = doc.createElementNS(ns, 'pageSetup')
      const following = Array.from(root.childNodes).find(node => node.nodeType === 1 && afterSetup.has(node.localName || ''))
      root.insertBefore(setup, following || null)
    }
    setup.setAttribute('paperSize', '9') // A4
    setup.setAttribute('orientation', 'landscape')
    setup.setAttribute('fitToWidth', '1')
    setup.setAttribute('fitToHeight', '0') // 多张合同沿纵向自然分页，不能压缩为一页。
    setup.removeAttribute('scale')
    let margins = doc.getElementsByTagNameNS(ns, 'pageMargins')[0]
    if (!margins) { margins = doc.createElementNS(ns, 'pageMargins'); root.insertBefore(margins, setup) }
    for (const [key, value] of Object.entries({ left: 0.25, right: 0.25, top: 0.35, bottom: 0.35, header: 0.15, footer: 0.15 })) margins.setAttribute(key, String(value))

    // A:H is the formal contract; retain the yellow I:J English-name/code fields in print too.
    const dimension = doc.getElementsByTagNameNS(ns, 'dimension')[0]?.getAttribute('ref')
    if (!dimension) throw new Error('采购合同工作表缺少有效范围')
    const range = XLSX.utils.decode_range(dimension)
    const lastCell = `$${XLSX.utils.encode_col(range.e.c)}$${range.e.r + 1}`
    for (const existing of Array.from(names.getElementsByTagNameNS(ns, 'definedName'))) {
      if (existing.getAttribute('name') === '_xlnm.Print_Area' && existing.getAttribute('localSheetId') === String(index)) names.removeChild(existing)
    }
    const printArea = workbook.createElementNS(ns, 'definedName')
    printArea.setAttribute('name', '_xlnm.Print_Area')
    printArea.setAttribute('localSheetId', String(index))
    printArea.textContent = `'${sheet.getAttribute('name')!.replace(/'/g, "''")}'!$A$1:${lastCell}`
    names.appendChild(printArea)
    zip.file(path, serializer.serializeToString(doc))
  }
  zip.file('xl/workbook.xml', serializer.serializeToString(workbook))
  return zip.generateAsync({ type: 'arraybuffer' })
}

export async function buildPurchaseContractWorkbook(wb: XLSX.WorkBook): Promise<Blob> {
  const buffer = XLSX.write(wb, { type: 'array', bookType: 'xlsx' }) as ArrayBuffer
  return new Blob([await applyPurchaseContractPrintLayout(buffer)], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
}

/** Call only after the caller's final export-session validation. */
export function downloadPurchaseContractWorkbook(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  try { link.click() } finally {
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
}

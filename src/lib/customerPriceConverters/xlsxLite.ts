import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'

export type XlsxCellValue = string | number | boolean | null | undefined

export interface XlsxParsedSheet {
  name: string
  rows: XlsxCellValue[][]
  cellFillIds: number[][]
}

export interface XlsxParsedWorkbook {
  sheets: XlsxParsedSheet[]
}

export interface XlsxCellObject {
  value?: XlsxCellValue
  formula?: string
  style?: number
}

export type XlsxCellInput = XlsxCellValue | XlsxCellObject

export interface XlsxOutputSheet {
  name: string
  rows: XlsxCellInput[][]
  cols?: number[]
  merges?: string[]
}

export const XLSX_STYLE = {
  default: 0,
  title: 1,
  bold: 2,
  border: 3,
  borderCn: 4,
  number3: 5,
  number3Bold: 6,
  date: 7,
  centerBorder: 8,
  boldBorder: 9,
  number2: 10,
  number0: 11,
  number1: 12,
  itemTitle: 13,
} as const

const XML_HEADER = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'

function parseXml(xml: string) {
  return new DOMParser().parseFromString(xml, 'application/xml')
}

function escapeXml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function escapeAttr(value: string) {
  return escapeXml(value).replace(/"/g, '&quot;')
}

function getZipText(zip: Record<string, Uint8Array>, path: string) {
  const file = zip[path]
  return file ? strFromU8(file) : ''
}

function normalizeWorksheetTarget(target: string) {
  const normalized = target.replace(/\\/g, '/').replace(/^\/+/, '')
  return normalized.startsWith('xl/') ? normalized : `xl/${normalized}`
}

function getElementText(element: Element) {
  return Array.from(element.getElementsByTagName('t'))
    .map((item) => item.textContent ?? '')
    .join('')
}

function readSharedStrings(zip: Record<string, Uint8Array>) {
  const xml = getZipText(zip, 'xl/sharedStrings.xml')
  if (!xml) {
    return [] as string[]
  }

  const document = parseXml(xml)
  return Array.from(document.getElementsByTagName('si')).map((item) => getElementText(item))
}

function readCellStyleFillIds(zip: Record<string, Uint8Array>) {
  const xml = getZipText(zip, 'xl/styles.xml')
  if (!xml) {
    return [0]
  }

  const document = parseXml(xml)
  const cellXfs = document.getElementsByTagName('cellXfs')[0]
  if (!cellXfs) {
    return [0]
  }

  return Array.from(cellXfs.getElementsByTagName('xf')).map((item) => {
    const fillId = Number(item.getAttribute('fillId') ?? 0)
    return Number.isFinite(fillId) ? fillId : 0
  })
}

function columnNameToIndex(columnName: string) {
  return columnName.split('').reduce((total, char) => total * 26 + char.charCodeAt(0) - 64, 0) - 1
}

function columnIndexToName(columnIndex: number) {
  let index = columnIndex + 1
  let name = ''

  while (index > 0) {
    const remainder = (index - 1) % 26
    name = String.fromCharCode(65 + remainder) + name
    index = Math.floor((index - 1) / 26)
  }

  return name
}

function readCellValue(cell: Element, sharedStrings: string[]): XlsxCellValue {
  const type = cell.getAttribute('t')

  if (type === 'inlineStr') {
    return getElementText(cell).trim()
  }

  const rawValue = cell.getElementsByTagName('v')[0]?.textContent ?? ''

  if (type === 's') {
    return sharedStrings[Number(rawValue)] ?? ''
  }

  if (type === 'b') {
    return rawValue === '1'
  }

  if (type === 'str') {
    return rawValue.trim()
  }

  const trimmed = rawValue.trim()
  if (/^-?\d+(?:\.\d+)?(?:e[+-]?\d+)?$/i.test(trimmed)) {
    return Number(trimmed)
  }

  return trimmed
}

function resolveWorksheetTargets(zip: Record<string, Uint8Array>) {
  const workbookXml = getZipText(zip, 'xl/workbook.xml')
  const relationsXml = getZipText(zip, 'xl/_rels/workbook.xml.rels')

  if (!workbookXml) {
    throw new Error('没有读取到 Excel 工作簿结构')
  }

  const workbook = parseXml(workbookXml)
  const relations = relationsXml ? parseXml(relationsXml) : null
  const relationMap = new Map<string, string>()

  if (relations) {
    Array.from(relations.getElementsByTagName('Relationship')).forEach((item) => {
      const id = item.getAttribute('Id')
      const target = item.getAttribute('Target')
      if (id && target) {
        relationMap.set(id, target)
      }
    })
  }

  return Array.from(workbook.getElementsByTagName('sheet')).map((sheet, index) => {
    const relationId = sheet.getAttribute('r:id') ?? ''
    const target = relationMap.get(relationId) ?? `worksheets/sheet${index + 1}.xml`

    return {
      name: sheet.getAttribute('name') ?? `Sheet${index + 1}`,
      path: normalizeWorksheetTarget(target),
    }
  })
}

export function parseXlsxWorkbook(buffer: ArrayBuffer): XlsxParsedWorkbook {
  const zip = unzipSync(new Uint8Array(buffer))
  const sharedStrings = readSharedStrings(zip)
  const cellStyleFillIds = readCellStyleFillIds(zip)
  const sheets = resolveWorksheetTargets(zip).map((sheet) => {
    const worksheetXml = getZipText(zip, sheet.path)
    if (!worksheetXml) {
      throw new Error(`没有读取到工作表：${sheet.name}`)
    }

    const worksheet = parseXml(worksheetXml)
    const rows: XlsxCellValue[][] = []
    const cellFillIds: number[][] = []

    Array.from(worksheet.getElementsByTagName('row')).forEach((row, fallbackRowIndex) => {
      const rowIndex = Number(row.getAttribute('r') ?? fallbackRowIndex + 1) - 1
      const cells: XlsxCellValue[] = rows[rowIndex] ?? []
      const fills: number[] = cellFillIds[rowIndex] ?? []

      Array.from(row.getElementsByTagName('c')).forEach((cell) => {
        const reference = cell.getAttribute('r') ?? ''
        const columnName = reference.match(/[A-Z]+/)?.[0]
        const columnIndex = columnName ? columnNameToIndex(columnName) : cells.length
        cells[columnIndex] = readCellValue(cell, sharedStrings)
        const styleId = Number(cell.getAttribute('s') ?? 0)
        fills[columnIndex] = cellStyleFillIds[styleId] ?? 0
      })

      rows[rowIndex] = cells
      cellFillIds[rowIndex] = fills
    })

    return {
      name: sheet.name,
      rows,
      cellFillIds,
    }
  })

  return { sheets }
}

function sanitizeSheetName(name: string, usedNames: Set<string>) {
  const base = (name || '报客')
    .replace(/[\[\]:*?/\\]/g, '_')
    .slice(0, 31) || '报客'
  let next = base
  let counter = 2

  while (usedNames.has(next)) {
    const suffix = ` (${counter})`
    counter += 1
    next = `${base.slice(0, 31 - suffix.length)}${suffix}`
  }

  usedNames.add(next)
  return next
}

function normalizeCell(cell: XlsxCellInput): XlsxCellObject {
  if (cell && typeof cell === 'object' && !Array.isArray(cell) && ('value' in cell || 'formula' in cell || 'style' in cell)) {
    return cell as XlsxCellObject
  }

  return { value: cell as XlsxCellValue }
}

function cellToXml(rowIndex: number, columnIndex: number, input: XlsxCellInput) {
  const cell = normalizeCell(input)
  const value = cell.value
  const style = typeof cell.style === 'number' ? ` s="${cell.style}"` : ''
  const reference = `${columnIndexToName(columnIndex)}${rowIndex + 1}`
  const formula = cell.formula ? `<f>${escapeXml(cell.formula)}</f>` : ''

  if (value === null || value === undefined || value === '') {
    return formula || style ? `<c r="${reference}"${style}>${formula}</c>` : ''
  }

  if (typeof value === 'number') {
    return `<c r="${reference}"${style}>${formula}<v>${Number.isFinite(value) ? value : 0}</v></c>`
  }

  if (typeof value === 'boolean') {
    return `<c r="${reference}" t="b"${style}>${formula}<v>${value ? 1 : 0}</v></c>`
  }

  return `<c r="${reference}" t="inlineStr"${style}>${formula}<is><t xml:space="preserve">${escapeXml(String(value))}</t></is></c>`
}

function measureSheet(rows: XlsxCellInput[][]) {
  let maxRow = rows.length
  let maxCol = 1

  rows.forEach((row, rowIndex) => {
    let hasCell = false
    row.forEach((cell, columnIndex) => {
      const normalized = normalizeCell(cell)
      if (normalized.value !== null && normalized.value !== undefined && normalized.value !== '' || normalized.formula || normalized.style) {
        hasCell = true
        maxCol = Math.max(maxCol, columnIndex + 1)
      }
    })
    if (hasCell) {
      maxRow = Math.max(maxRow, rowIndex + 1)
    }
  })

  return {
    maxRow: Math.max(maxRow, 1),
    maxCol,
  }
}

function renderWorksheet(sheet: XlsxOutputSheet) {
  const { maxRow, maxCol } = measureSheet(sheet.rows)
  const dimension = `A1:${columnIndexToName(maxCol - 1)}${maxRow}`
  const cols = sheet.cols?.length
    ? `<cols>${sheet.cols.map((width, index) => `<col min="${index + 1}" max="${index + 1}" width="${width}" customWidth="1"/>`).join('')}</cols>`
    : ''
  const sheetData = sheet.rows.map((row, rowIndex) => {
    const cells = row
      .map((cell, columnIndex) => cellToXml(rowIndex, columnIndex, cell))
      .filter(Boolean)
      .join('')

    return cells ? `<row r="${rowIndex + 1}">${cells}</row>` : ''
  }).filter(Boolean).join('')
  const merges = sheet.merges?.length
    ? `<mergeCells count="${sheet.merges.length}">${sheet.merges.map((ref) => `<mergeCell ref="${escapeAttr(ref)}"/>`).join('')}</mergeCells>`
    : ''

  return `${XML_HEADER}<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><dimension ref="${dimension}"/><sheetViews><sheetView workbookViewId="0" showGridLines="1"/></sheetViews>${cols}<sheetData>${sheetData}</sheetData>${merges}</worksheet>`
}

function renderWorkbook(sheetNames: string[]) {
  return `${XML_HEADER}<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>${sheetNames.map((name, index) => `<sheet name="${escapeAttr(name)}" sheetId="${index + 1}" r:id="rId${index + 1}"/>`).join('')}</sheets></workbook>`
}

function renderWorkbookRels(sheetCount: number) {
  const worksheets = Array.from({ length: sheetCount }, (_, index) =>
    `<Relationship Id="rId${index + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${index + 1}.xml"/>`,
  ).join('')

  return `${XML_HEADER}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${worksheets}<Relationship Id="rId${sheetCount + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`
}

function renderContentTypes(sheetCount: number) {
  const worksheets = Array.from({ length: sheetCount }, (_, index) =>
    `<Override PartName="/xl/worksheets/sheet${index + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`,
  ).join('')

  return `${XML_HEADER}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>${worksheets}<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>`
}

function renderRootRels() {
  return `${XML_HEADER}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>`
}

function renderStyles() {
  return `${XML_HEADER}<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><numFmts count="5"><numFmt numFmtId="164" formatCode="0.000_ "/><numFmt numFmtId="165" formatCode="[$-409]d\\-mmm\\-yyyy;@"/><numFmt numFmtId="166" formatCode="0.00"/><numFmt numFmtId="167" formatCode="0"/><numFmt numFmtId="168" formatCode="0.0"/></numFmts><fonts count="5"><font><sz val="11"/><name val="Calibri"/></font><font><sz val="10"/><name val="Arial"/></font><font><b/><sz val="10"/><name val="Arial"/></font><font><b/><sz val="12"/><name val="Arial"/></font><font><sz val="9"/><name val="宋体"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left style="thin"><color auto="1"/></left><right style="thin"><color auto="1"/></right><top style="thin"><color auto="1"/></top><bottom style="thin"><color auto="1"/></bottom><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="14"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1"/><xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/><xf numFmtId="0" fontId="1" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1"/><xf numFmtId="0" fontId="4" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1"/><xf numFmtId="164" fontId="1" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyNumberFormat="1"/><xf numFmtId="164" fontId="2" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyNumberFormat="1"/><xf numFmtId="165" fontId="1" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyNumberFormat="1"/><xf numFmtId="0" fontId="1" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf><xf numFmtId="0" fontId="2" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1"/><xf numFmtId="166" fontId="1" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyNumberFormat="1"/><xf numFmtId="167" fontId="1" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyNumberFormat="1"/><xf numFmtId="168" fontId="1" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyNumberFormat="1"/><xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment horizontal="center" vertical="top"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles><dxfs count="0"/><tableStyles count="0" defaultTableStyle="TableStyleMedium9" defaultPivotStyle="PivotStyleMedium4"/></styleSheet>`
}

function renderCoreProps() {
  const now = new Date().toISOString()
  return `${XML_HEADER}<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:creator>Royal Regent Nexus</dc:creator><cp:lastModifiedBy>Royal Regent Nexus</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">${now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">${now}</dcterms:modified></cp:coreProperties>`
}

function renderAppProps(sheetNames: string[]) {
  return `${XML_HEADER}<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Royal Regent Nexus</Application><DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop><HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Worksheets</vt:lpstr></vt:variant><vt:variant><vt:i4>${sheetNames.length}</vt:i4></vt:variant></vt:vector></HeadingPairs><TitlesOfParts><vt:vector size="${sheetNames.length}" baseType="lpstr">${sheetNames.map((name) => `<vt:lpstr>${escapeXml(name)}</vt:lpstr>`).join('')}</vt:vector></TitlesOfParts><Company>Royal Regent</Company><LinksUpToDate>false</LinksUpToDate><SharedDoc>false</SharedDoc><HyperlinksChanged>false</HyperlinksChanged><AppVersion>16.0300</AppVersion></Properties>`
}

export function createXlsxWorkbook(sheets: XlsxOutputSheet[]) {
  const usedNames = new Set<string>()
  const normalizedSheets = sheets.map((sheet) => ({
    ...sheet,
    name: sanitizeSheetName(sheet.name, usedNames),
  }))
  const files: Record<string, Uint8Array> = {
    '[Content_Types].xml': strToU8(renderContentTypes(normalizedSheets.length)),
    '_rels/.rels': strToU8(renderRootRels()),
    'docProps/app.xml': strToU8(renderAppProps(normalizedSheets.map((sheet) => sheet.name))),
    'docProps/core.xml': strToU8(renderCoreProps()),
    'xl/workbook.xml': strToU8(renderWorkbook(normalizedSheets.map((sheet) => sheet.name))),
    'xl/_rels/workbook.xml.rels': strToU8(renderWorkbookRels(normalizedSheets.length)),
    'xl/styles.xml': strToU8(renderStyles()),
  }

  normalizedSheets.forEach((sheet, index) => {
    files[`xl/worksheets/sheet${index + 1}.xml`] = strToU8(renderWorksheet(sheet))
  })

  return zipSync(files)
}

export function excelDateSerial(date: Date) {
  const epoch = Date.UTC(1899, 11, 30)
  return (Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) - epoch) / 86400000
}

import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'
import layouts from './buzzbeeTemplateLayouts.json'
import { excelDateSerial } from './xlsxLite'
import type { BuzzBeeConversionResult } from './buzzbee'
import { pricingRate } from './pricingSettings'

export type BuzzBeeTemplateProfile = keyof typeof layouts
export const BUZZBEE_CUSTOMER_TEMPLATE_URL = '/templates/buzzbee-standard-template.bin'
export const buzzBeeTemplateProfiles = [
  { id: 'standard', label: '标准版（心形公仔）' }, { id: 'space', label: '太空套装版' },
  { id: 'cowboy', label: '牛仔紧凑版' }, { id: 'cowboy_extended', label: '牛仔扩展版' },
  { id: 'police', label: '警察服饰版' }, { id: 'laser', label: '激光枪版（含说明区）' },
] as const
export function buzzBeeTemplateUrl(profile: string = 'standard') {
  if (!Object.hasOwn(layouts, profile)) throw new Error('未知 BuzzBee 报客版式')
  return `/templates/buzzbee-${profile}-template.bin`
}
const NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
const REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
const parse = (s: string) => new DOMParser().parseFromString(s, 'application/xml')
const els = (root: Element | Document, name: string) => Array.from(root.getElementsByTagNameNS('*', name))
const serialize = (d: Document) => strToU8(new XMLSerializer().serializeToString(d))
const column = (s: string) => s.replace(/\d/g, '').split('').reduce((n, c) => n * 26 + c.charCodeAt(0) - 64, 0)

export function createBuzzBeeTemplateWorkbook(result: BuzzBeeConversionResult, template: ArrayBuffer | Uint8Array): Uint8Array {
  if (!result.sheets.length) throw new Error('没有 BuzzBee 报客数据')
  const zip = unzipSync(template instanceof Uint8Array ? template : new Uint8Array(template))
  const original = strFromU8(zip['xl/worksheets/sheet1.xml']!)
  if (!original) throw new Error('BuzzBee 原版模板缺少报价页')
  let content = strFromU8(zip['[Content_Types].xml']!)
  const workbook = parse(strFromU8(zip['xl/workbook.xml']!))
  const sheetsElement = els(workbook, 'sheets')[0]!
  sheetsElement.replaceChildren()
  const sheetRelations: string[] = []
  const usedNames = new Set<string>()
  for (const [index, sheet] of result.sheets.entries()) {
    const d = sheet.quoteData
    const profile = d.templateProfile || 'standard'
    if (!Object.hasOwn(layouts, profile)) throw new Error('未知 BuzzBee 报客版式')
    const layout = layouts[profile as BuzzBeeTemplateProfile]
    const doc = parse(original)
    // Verify the selected layout, rather than silently filling a different original.
    if (!els(doc, 'c').some(c => c.getAttribute('r') === `D${layout.purchaseTotal}` && els(c, 'f').length)) throw new Error('所选版式与模板文件不一致')
    const data = els(doc, 'sheetData')[0]!
    const injectionExtra = Math.max(0, d.injectionRows.length - 18)
    const additionalExtra = Math.max(0, d.additionalParts.length - 1)
    const purchaseExtra = Math.max(0, d.purchaseRows.length - (layout.purchaseTotal - 29) - additionalExtra)
    const shift = (r: number) => r + (r >= 25 ? injectionExtra : 0) + (r >= 44 ? additionalExtra : 0) + (r >= layout.purchaseTotal ? purchaseExtra : 0)
    const reference = (s: string) => s.replace(/(\$?[A-Z]{1,3}\$?)(\d+)/g, (_, col: string, row: string) => `${col}${shift(Number(row))}`)
    const prototypes = new Map(els(doc, 'row').map(row => [Number(row.getAttribute('r')), row.cloneNode(true) as Element]))
    for (const row of els(doc, 'row')) {
      row.setAttribute('r', String(shift(Number(row.getAttribute('r')))))
      for (const cell of els(row, 'c')) {
        cell.setAttribute('r', reference(cell.getAttribute('r')!))
        for (const formula of els(cell, 'f')) formula.textContent = reference(formula.textContent || '')
      }
    }
    for (const [at, count, source] of [[25, injectionExtra, 24], [44, additionalExtra, 43], [layout.purchaseTotal, purchaseExtra, layout.purchaseTotal - 1]]) {
      const prototype = prototypes.get(source!)!
      const before = els(doc, 'row').find(row => Number(row.getAttribute('r')) === shift(at!))!
      for (let i = 0; i < count!; i++) {
        const row = prototype.cloneNode(true) as Element
        const target = shift(at!) - count! + i
        row.setAttribute('r', String(target))
        for (const cell of els(row, 'c')) {
          cell.setAttribute('r', cell.getAttribute('r')!.replace(/\d+/, String(target)))
          cell.removeAttribute('t'); cell.replaceChildren()
        }
        data.insertBefore(row, before)
      }
    }
    for (const merge of els(doc, 'mergeCell')) merge.setAttribute('ref', reference(merge.getAttribute('ref')!))
    for (const dimension of els(doc, 'dimension')) dimension.setAttribute('ref', reference(dimension.getAttribute('ref')!))
    const put = (address: string, value: string | number | undefined | null, formula?: string) => {
      const n = Number(address.replace(/[A-Z]/g, ''))
      let row = els(data, 'row').find(r => Number(r.getAttribute('r')) === n)
      if (!row) { row = doc.createElementNS(NS, 'row'); row.setAttribute('r', String(n)); const next = els(data, 'row').find(r => Number(r.getAttribute('r')) > n); data.insertBefore(row, next || null) }
      let cell = els(row, 'c').find(c => c.getAttribute('r') === address)
      if (!cell) { cell = doc.createElementNS(NS, 'c'); cell.setAttribute('r', address); const next = els(row, 'c').find(c => column(c.getAttribute('r')!) > column(address)); row.insertBefore(cell, next || null) }
      cell.removeAttribute('t'); cell.replaceChildren()
      if (formula) { const f = doc.createElementNS(NS, 'f'); f.textContent = formula; cell.appendChild(f) }
      if (typeof value === 'number') { if (!Number.isFinite(value)) throw new Error(`BuzzBee ${address} 计算结果无效`); const v = doc.createElementNS(NS, 'v'); v.textContent = String(value); cell.appendChild(v) }
      else if (value !== undefined && value !== null && value !== '') { cell.setAttribute('t', 'inlineStr'); const is = doc.createElementNS(NS, 'is'); const t = doc.createElementNS(NS, 't'); t.setAttribute('xml:space', 'preserve'); t.textContent = value; is.appendChild(t); cell.appendChild(is) }
    }
    const set = (address: string, value: string | number | undefined | null, formula?: string) => put(reference(address), value, formula ? reference(formula) : undefined)
    if (d.quoteDate !== undefined && !/^\d{4}-\d{2}-\d{2}$/.test(d.quoteDate)) throw new Error('BuzzBee 缺少新建报价日期，请重新导出已放行的内部报价')
    set('G1', excelDateSerial(d.quoteDate ? new Date(`${d.quoteDate}T12:00:00`) : new Date()))
    set('G2', d.revision || 'R0'); set('A4', `ltem:${d.productName}`)
    for (let i = 0; i < 18 + injectionExtra; i++) {
      const r = 7 + i, item = d.injectionRows[i]
      for (const [c, v] of [['A', item?.name], ['B', item?.material], ['C', item?.weight], ['D', item?.pricePerKg], ['F', item?.setsPerShot], ['G', item?.beer]] as const) put(`${c}${r}`, v)
      put(`E${r}`, item?.amount ?? 0, `C${r}*D${r}/1000${pricingRate(d.pricing, 'material_multiplier', 1) === 1 ? '' : `*${pricingRate(d.pricing, 'material_multiplier', 1)}`}`)
      put(`I${r}`, null)
    }
    set('C25', d.injectionWeight, 'SUM(C7:C24)'); set('E25', d.injectionAmount, 'SUM(E7:E24)'); set('G25', d.injectionBeer, 'SUM(G7:G24)'); set('I25', 0, 'SUM(I7:I24)')
    // Expanded injection sums must include all inserted rows.
    for (const [c, v] of [['C', d.injectionWeight], ['E', d.injectionAmount], ['G', d.injectionBeer]] as const) put(`${c}${shift(25)}`, v, `SUM(${c}7:${c}${24 + injectionExtra})`)
    for (let r = shift(29), i = 0; r < shift(layout.purchaseTotal); r++, i++) {
      const item = d.purchaseRows[i]
      put(`A${r}`, item?.desc); put(`B${r}`, item?.qty); put(`C${r}`, item?.price); put(`D${r}`, item?.amount ?? 0, `B${r}*C${r}`)
    }
    put(`D${shift(layout.purchaseTotal)}`, d.purchaseSubTotal, `SUM(D${shift(29)}:D${shift(layout.purchaseTotal) - 1})`)
    const breakdown = d.breakdown
    set('J28', breakdown.plastic, 'E25'); set('J29', breakdown.injection, 'G25'); set('J30', breakdown.purchase, `D${layout.purchaseTotal}`)
    set('G28', null); set('G29', null); set('G30', 0); set('G32', 0, 'SUM(G28:G30)'); set('J31', 0, 'G32')
    set('G35', breakdown.spray); set('G36', null); set('G37', breakdown.assembly); set('G38', null); set('G39', breakdown.process, 'SUM(G34:G38)')
    set('J32', breakdown.process, 'G39'); set('J34', breakdown.sub, 'SUM(J28:J33)'); set('J35', breakdown.po, `J34*${pricingRate(d.pricing, 'po_rate', 0.1)}`); set('J37', breakdown.total, 'ROUND(J34+J35,2)')
    for (let i = 0; i < Math.max(1, d.additionalParts.length); i++) { const r = shift(43) + i, item = d.additionalParts[i]; put(`F${r}`, item?.desc); put(`H${r}`, item?.qty); put(`I${r}`, item?.price); put(`J${r}`, item?.amount || 0, `H${r}*I${r}`) }
    put(`J${shift(44)}`, d.exftyCost, `SUM(J${shift(37)}:J${shift(44) - 1})`)
    set('J46', d.usd, `J44/${pricingRate(d.pricing, 'hkd_usd', 7.75)}`)
    // Historical sample RMB rate was a manually entered value with no approved input.
    set('I48', layout.purchaseTotal === 48 ? undefined : null); set('J48', null)
    const carton = layout.dimensionHeader + 3
    set(`B${carton}`, d.box.length); set(`C${carton}`, d.box.width); set(`D${carton}`, d.box.height)
    set(`B${carton + 3}`, d.box.pcsPerCarton); set(`C${carton + 3}`, d.box.cube, `B${carton}*C${carton}*D${carton}/1728`)
    for (const [i, price, moq] of [[0, d.colorBox.price1, d.colorBox.moq1], [1, d.colorBox.price2, d.colorBox.moq2]] as const) {
      const r = layout.colorFirst + i
      const value = price / (d.box.pcsPerCarton || 1)
      set(`F${r}`, value, `${price}/B${carton + 3}`); set(`G${r}`, value * pricingRate(d.pricing, 'fsc_multiplier', 1.03), `F${r}*${pricingRate(d.pricing, 'fsc_multiplier', 1.03)}`); set(`H${r}`, moq)
    }
    if (d.notes) {
      if (profile !== 'laser') throw new Error('已填写功能说明，请选择含说明区的激光枪版式')
      set('F55', d.notes)
    }
    const sheetNumber = index + 1
    if (d.image) {
      const drawing = parse(layout.drawing)
      for (const r of els(drawing, 'row')) r.textContent = String(shift(Number(r.textContent) + 1) - 1)
      zip[`xl/drawings/drawing${sheetNumber}.xml`] = serialize(drawing)
      zip[`xl/media/product${sheetNumber}.${d.image.extension}`] = new Uint8Array(d.image.bytes)
      zip[`xl/drawings/_rels/drawing${sheetNumber}.xml.rels`] = strToU8(`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="${REL}/image" Target="../media/product${sheetNumber}.${d.image.extension}"/></Relationships>`)
      zip[`xl/worksheets/_rels/sheet${sheetNumber}.xml.rels`] = strToU8(`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="${REL}/drawing" Target="../drawings/drawing${sheetNumber}.xml"/></Relationships>`)
      const marker = doc.createElementNS(NS, 'drawing'); marker.setAttributeNS(REL, 'r:id', 'rId1'); doc.documentElement.appendChild(marker)
      content = content.replace('</Types>', `<Override PartName="/xl/drawings/drawing${sheetNumber}.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/></Types>`)
      if (!content.includes(`Extension="${d.image.extension}"`)) content = content.replace('</Types>', `<Default Extension="${d.image.extension}" ContentType="image/${d.image.extension === 'jpg' ? 'jpeg' : 'png'}"/></Types>`)
    }
    zip[`xl/worksheets/sheet${sheetNumber}.xml`] = serialize(doc)
    if (sheetNumber > 1) content = content.replace('</Types>', `<Override PartName="/xl/worksheets/sheet${sheetNumber}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>`)
    let name = sheet.productName.replace(/[\\/:*?\[\]]/g, '_').slice(0, 31) || 'Quotation'
    if (usedNames.has(name)) name = `${name.slice(0, 25)}-${sheetNumber}`
    usedNames.add(name)
    const entry = workbook.createElementNS(NS, 'sheet'); entry.setAttribute('name', name); entry.setAttribute('sheetId', String(sheetNumber)); entry.setAttributeNS(REL, 'r:id', `sheet${sheetNumber}`); sheetsElement.appendChild(entry)
    sheetRelations.push(`<Relationship Id="sheet${sheetNumber}" Type="${REL}/worksheet" Target="worksheets/sheet${sheetNumber}.xml"/>`)
  }
  zip['xl/workbook.xml'] = serialize(workbook)
  zip['xl/_rels/workbook.xml.rels'] = strToU8(`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${sheetRelations.join('')}<Relationship Id="styles" Type="${REL}/styles" Target="styles.xml"/><Relationship Id="theme" Type="${REL}/theme" Target="theme/theme1.xml"/></Relationships>`)
  zip['[Content_Types].xml'] = strToU8(content)
  return zipSync(zip)
}

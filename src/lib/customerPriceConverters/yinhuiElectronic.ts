import type { XlsxParsedSheet } from './xlsxLite'
import { yinhuiHeaderKey, yinhuiSheetKey } from './yinhuiSource'
import type { YinhuiCostRow } from './yinhui'

const text = (value: unknown) => String(value ?? '').normalize('NFKC').trim()
export const isYinhuiIc = (value: unknown) => /^IC(?:$|[^A-Z0-9])/i.test(text(value))
export const isYinhuiElectronicSheet = (name: string) => /^(?:电子|電子)报价/.test(yinhuiSheetKey(name))

export interface YinhuiIcSource {
  description: string
  quantity: number
  unitPrice: number
  amount: number
  currency: 'RMB' | 'HKD'
  source: string
}
export interface YinhuiElectronicSource {
  model: string
  role: 'TX' | 'RX' | ''
  source: string
  chips: YinhuiIcSource[]
}

// Business-confirmed IC price already includes its tax/profit treatment.
// Do not apply the parent electronics or customer-detail markup a second time.
export function yinhuiIcCost(chip: YinhuiIcSource, fx: number, parentQuantity = 1): YinhuiCostRow {
  if (!Number.isFinite(fx) || fx <= 0) throw new Error('银辉 IC 缺少有效人民币/港币汇率，不能猜测换算')
  const quantity = chip.quantity * parentQuantity
  const internalHkd = chip.unitPrice / (chip.currency === 'RMB' ? fx : 1) * quantity
  return { description: chip.description, originalDescription: chip.description, source: chip.source,
    quantity, internalHkd, amountHkd: internalHkd * 1.08 / .96 }
}

function sourceFx(main: XlsxParsedSheet) {
  const values: unknown[] = []
  main.rows.slice(0, 80).forEach((row, r) => row?.forEach((v, c) => {
    if (/^(?:汇率|匯率|rmb\/hkd)$/.test(yinhuiHeaderKey(v))) values.push(main.rows[r + 1]?.[c])
  }))
  if (values.length !== 1 || !Number.isFinite(Number(values[0])) || Number(values[0]) <= 0 || typeof values[0] === 'boolean')
    throw new Error('银辉 IC 无法唯一读取原表人民币/港币汇率，请核对汇率标题及下方数值')
  return Number(values[0])
}

const roleOf = (value: string) => text(value).toUpperCase().match(/(?:^|[^A-Z0-9])(TX|RX)(?=$|[^A-Z0-9])/)?.[1] || ''

export function splitYinhuiLegacyElectronics(rows: YinhuiCostRow[], sheets: XlsxParsedSheet[], main: XlsxParsedSheet, model: string): YinhuiCostRow[] {
  const groups = readYinhuiElectronicSources(sheets)
  if (!groups.length) return rows
  const replacements = new Map<YinhuiCostRow, YinhuiCostRow[]>()
  let fx: number | undefined
  for (const group of groups) {
    if (group.model !== model) throw new Error(`银辉 ${group.source}：电子报价型号 ${group.model || '缺失'} 与当前 ${model} 不一致，无法拆分 IC`)
    const candidates = rows.filter(row => !row.isBattery && !isYinhuiIc(row.description)
      && (group.role ? roleOf(row.description) === group.role : !roleOf(row.description)))
    if (candidates.length !== 1 || replacements.has(candidates[0]!))
      throw new Error(`银辉 ${group.source}：IC 无法唯一对应 ${group.role || '电子'} 报价，不能按顺序或跨组扣价`)
    const parent = candidates[0]!
    const chips = group.chips.filter(chip => chip.quantity > 0).map(chip => {
      if (chip.currency === 'RMB') fx ??= sourceFx(main)
      return yinhuiIcCost(chip, fx ?? 1, parent.quantity)
    })
    replacements.set(parent, splitYinhuiElectronicRow(parent, chips))
  }
  return rows.flatMap(row => replacements.get(row) || [row])
}

/** Split already-priced children atomically, retaining every cent in the parent group. */
export function splitYinhuiElectronicRow(parent: YinhuiCostRow, chips: YinhuiCostRow[]): YinhuiCostRow[] {
  const sum = (key: 'amountHkd' | 'internalHkd') => chips.reduce((total, row) => total + row[key], 0)
  for (const row of [parent, ...chips]) {
    if (![row.amountHkd, row.internalHkd, row.quantity].every(value => Number.isFinite(value) && value >= 0)
      || (row.quantity === 0 && (row.amountHkd !== 0 || row.internalHkd !== 0)))
      throw new Error(`银辉 ${row.source}：电子拆分金额或用量无效`)
  }
  const amountHkd = parent.amountHkd - sum('amountHkd')
  const internalHkd = parent.internalHkd - sum('internalHkd')
  if (amountHkd < -1e-8 || internalHkd < -1e-8) throw new Error(`银辉 ${parent.source}：IC 金额超过所属电子报价，不能扣成负数`)
  return [{ ...parent, amountHkd: Math.max(0, amountHkd), internalHkd: Math.max(0, internalHkd) }, ...chips]
}

function number(value: unknown, source: string, label: string) {
  const result = Number(value)
  if (typeof value === 'boolean' || value == null || text(value) === '' || !Number.isFinite(result) || result < 0)
    throw new Error(`银辉 ${source}：IC ${label}缺少有效非负数，请核对电子报价原表`)
  return result
}
const column = (index: number) => {
  let result = ''
  for (let n = index + 1; n; n = Math.floor((n - 1) / 26)) result = String.fromCharCode(65 + (n - 1) % 26) + result
  return result
}

/** Read each supplier quotation separately; never attach ICs by sheet order. */
export function readYinhuiElectronicSources(sheets: XlsxParsedSheet[]): YinhuiElectronicSource[] {
  const groups: YinhuiElectronicSource[] = []
  for (const sheet of sheets.filter(s => isYinhuiElectronicSheet(s.name))) {
    let identity = ''
    let group: YinhuiElectronicSource | undefined
    let columns: { kind: number; description: number; quantity: number; unit: number; amount: number; currency: 'RMB' | 'HKD' } | undefined
    for (const [index, row] of sheet.rows.entries()) {
      if (!row) continue
      const title = row.map(text).join(' ')
      const model = title.match(/产品编号|產品編號|产品型号|產品型號/)
      if (model) {
        identity = title.slice(model.index! + model[0].length).match(/^\s*[:：#]?\s*([\w-]+)/)?.[1] || ''
        group = undefined; columns = undefined
      }
      const keys = row.map(yinhuiHeaderKey)
      const kind = keys.findIndex(v => /^(?:零件|物料)名[称稱]$/.test(v))
      const description = keys.findIndex(v => /^(?:规格|規格|specification)$/.test(v))
      const quantity = keys.findIndex(v => /^(?:用量|数量|數量|qty)$/.test(v))
      if (kind >= 0 && description >= 0 && quantity >= 0) {
        const unit = keys.findIndex(v => /^(?:单价|單價)(?:rmb|hkd)$/.test(v))
        const amount = keys.findIndex(v => /^(?:合计|合計|金额|金額)(?:rmb|hkd)$/.test(v))
        const currency = unit >= 0 && keys[unit]!.endsWith('hkd') ? 'HKD' : 'RMB'
        if (unit < 0 || amount < 0 || !keys[amount]!.endsWith(currency.toLowerCase())) {
          columns = undefined
          group = undefined
        } else {
          const match = identity.match(/^(.+?)[-_](TX|RX)$/i)
          group = { model: match?.[1] || identity, role: (match?.[2]?.toUpperCase() || '') as YinhuiElectronicSource['role'], source: `${sheet.name}!${index + 1}`, chips: [] }
          groups.push(group)
          columns = { kind, description, quantity, unit, amount, currency }
        }
        continue
      }
      const ic = columns ? isYinhuiIc(row[columns.kind]) || isYinhuiIc(row[columns.description]) : row.some(isYinhuiIc)
      if (!ic) continue
      if (!group || !columns) throw new Error(`银辉 ${sheet.name}!${index + 1}：IC 明细缺少明确的币种、用量或金额表头，请核对电子报价原表`)
      const source = `${sheet.name}!${column(columns.amount)}${index + 1}`
      const descriptionText = text(row[columns.description])
      if (!descriptionText) throw new Error(`银辉 ${source}：IC 规格缺失，请核对电子报价原表`)
      const qty = number(row[columns.quantity], source, '用量')
      const unitPrice = number(row[columns.unit], source, '单价')
      const amount = number(row[columns.amount], source, '金额')
      if ((qty === 0 && amount !== 0) || Math.abs(qty * unitPrice - amount) > .005) throw new Error(`银辉 ${source}：IC 用量×单价与金额不一致，请核对电子报价原表`)
      group.chips.push({ description: descriptionText, quantity: qty, unitPrice, amount, currency: columns.currency, source })
    }
  }
  return groups.filter(group => group.chips.length)
}

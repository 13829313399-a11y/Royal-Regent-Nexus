import { createRandomUuid } from './randomUuid'
import { splitEngineeringMoldPartNames, type EngineeringMoldPartRow, type EngineeringMoldRow } from './internalQuoteSectionPayload'

export interface EngineeringMoldSplitChange {
  index: number
  original: string
  parts: EngineeringMoldPartRow[]
}

export function newMoldSplitPart(row: EngineeringMoldRow, name = ''): EngineeringMoldPartRow {
  const count = (value: unknown) => Number.isFinite(Number(value)) && Number(value) > 0 ? Number(value) : 0
  const id = createRandomUuid()
  return { id, part_id: id, name, color: row.color || '', process: '', process_unit_price_hkd: 0,
    unit_net_weight_g: 0, output_count: count(row.cavity), quantity: count(row.quantity) }
}

export function prepareMoldSplit(row: EngineeringMoldRow): EngineeringMoldPartRow[] {
  if (row.parts.length) return row.parts.map(part => ({ ...part }))
  const names = splitEngineeringMoldPartNames(row.item || row.chinese_name)
  return (names.length ? names : ['']).map(name => newMoldSplitPart(row, name))
}

export function validateMoldSplit(parts: EngineeringMoldPartRow[]): string {
  if (!parts.length) return '请至少保留一个配件。'
  for (const [index, part] of parts.entries()) {
    if (!part.name.trim()) return `第 ${index + 1} 个配件请填写名称。`
    if (!Number.isFinite(Number(part.unit_net_weight_g)) || Number(part.unit_net_weight_g) < 0)
      return `第 ${index + 1} 个配件的净重须为非负数。`
    for (const [field, label] of [['output_count', '出模数'], ['quantity', '套数']] as const) {
      if (!Number.isInteger(Number(part[field])) || Number(part[field]) < 0)
        return `第 ${index + 1} 个配件的${label}须为非负整数。`
    }
  }
  return ''
}

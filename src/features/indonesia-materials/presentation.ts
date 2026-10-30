import type { BoardOrder, Data } from '@/api/indonesiaMaterials'

export function hasReceiptRisk(order: BoardOrder) {
  return order.status !== 'complete' && order.demands.some(demand => demand.risk === 'late')
}
export function needsPlanningData(order: BoardOrder) {
  return ['missing_master', 'missing_parameters'].includes(order.planning_status || order.status)
}
export function readyMaterials(order: BoardOrder) {
  return order.demands.filter(demand => /^0(?:\.0+)?$/.test(demand.shortage)).length
}

// Add frozen server decimal strings without changing their precision or recalculating prices.
function decimal(value: unknown) {
  const text = String(value)
  if (!/^-?\d+(?:\.\d+)?$/.test(text)) throw new Error('出货快照包含无效数值')
  const [integer = '0', fraction = ''] = text.split('.')
  return { value: BigInt(integer + fraction), scale: fraction.length }
}
export function sumText(values: unknown[]): string {
  const numbers = values.map(decimal)
  const scale = Math.max(0, ...numbers.map(number => number.scale))
  const total = numbers.reduce((sum, number) => sum + number.value * 10n ** BigInt(scale - number.scale), 0n)
  const digits = (total < 0n ? -total : total).toString().padStart(scale + 1, '0')
  return `${total < 0n ? '-' : ''}${scale ? `${digits.slice(0, -scale)}.${digits.slice(-scale)}` : digits}`
}
export function fixedText(value: unknown, places = 2) {
  const number = decimal(value)
  const negative = number.value < 0n
  let absolute = negative ? -number.value : number.value
  if (number.scale > places) {
    const divisor = 10n ** BigInt(number.scale - places)
    absolute = (absolute + divisor / 2n) / divisor
  } else absolute *= 10n ** BigInt(places - number.scale)
  const digits = absolute.toString().padStart(places + 1, '0')
  return `${negative && absolute ? '-' : ''}${places ? `${digits.slice(0, -places)}.${digits.slice(-places)}` : digits}`
}

export interface ShipmentMaterialRow {
  id: string; code: string; name: string; unit: string; items: string[]; contracts: string[]
  normal: string; spare: string; net: string; carton: string; gross: string
  groupLabels: string[]; cartons: number; cbm: string; span: number
}
export interface ShipmentSummary {
  rows: ShipmentMaterialRow[]; suppliers: { name: string; currency: string; materials: number; amount: string }[] | null
  net: string; carton: string; gross: string; cartons: number; cbm: string
}
export function confirmedShipmentSummary(data: Data): ShipmentSummary | null {
  if (data.status !== 'confirmed' || !data.snapshot_lines?.length || !data.packing_totals) return null
  const sources: Data[] = data.snapshot_lines
  const materials = new Map<string, Data[]>()
  const sourceCodes = new Map<string, string>()
  for (const line of sources) {
    const code = String(line.supply?.material_id || line.supply?.material_snapshot?.id ||
      `legacy:${JSON.stringify([line.material.code, line.material.name, line.material.specification].map(value => String(value || '')))}`)
    materials.set(code, [...(materials.get(code) ?? []), line])
    sourceCodes.set(line.allocation_id, code)
  }
  const parents = new Map([...materials.keys()].map(code => [code, code]))
  function parent(code: string): string {
    const next = parents.get(code)!
    return next === code ? code : parent(next)
  }
  const groups: Data[] = data.packing_totals.groups ?? []
  for (const group of groups) {
    const codes = [...new Set<string>(group.items.map((item: Data) => sourceCodes.get(item.allocation_id)).filter(Boolean))]
    for (const code of codes.slice(1)) parents.set(parent(code), parent(codes[0]!))
  }
  const components = new Map<string, string[]>()
  for (const code of materials.keys()) components.set(parent(code), [...(components.get(parent(code)) ?? []), code])
  const rows: ShipmentMaterialRow[] = []
  for (const codes of components.values()) {
    const connected = groups.filter(group => group.items.some((item: Data) => codes.includes(sourceCodes.get(item.allocation_id)!)))
    codes.forEach((code, index) => {
      const lines = materials.get(code)!
      const weight = (key: string) => sumText(lines.map(line => data.packing_totals.lines[line.allocation_id]?.[key]))
      rows.push({
        id: code, code: String(lines[0]!.material.code), name: lines[0]!.material.name, unit: lines[0]!.material.unit,
        items: [...new Set(lines.map(line => String(line.item_no)))], contracts: [...new Set(lines.map(line => String(line.contract_no)))],
        normal: sumText(lines.map(line => line.normal_quantity)), spare: sumText(lines.map(line => line.spare_quantity)),
        net: weight('net_weight_kg'), carton: weight('carton_weight_kg'), gross: weight('gross_weight_kg'),
        groupLabels: connected.map(group => String(group.label)), cartons: connected.reduce((sum, group) => sum + Number(group.cartons), 0),
        cbm: sumText(connected.map(group => group.total_cbm)), span: index === 0 ? codes.length : 0,
      })
    })
  }
  return {
    // Frozen by the same calculation that created the immutable Excel. Legacy snapshots do not invent a subtotal.
    rows, suppliers: Array.isArray(data.supplier_summary) ? data.supplier_summary : null,
    net: sumText(rows.map(row => row.net)), carton: sumText(rows.map(row => row.carton)), gross: sumText(rows.map(row => row.gross)),
    cartons: data.packing_totals.cartons, cbm: data.packing_totals.cbm,
  }
}

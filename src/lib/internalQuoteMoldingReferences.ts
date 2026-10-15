import { normalizeInternalQuotePayload, type MoldingPayload } from './internalQuoteSectionPayload'
import type { InternalQuoteSectionCode } from '@/types/internalQuoteDesk'

export type MoldingMaterialSelection = { material: string; grade: string }
export type MoldingMaterialReference = { material: string; grade: string; priceHkdLb: number }
export type MoldingMachineReference = { range: string; machine: string; shiftPriceHkd: number }

export function normalizedReferenceToken(value: unknown) {
  return String(value ?? '').normalize('NFKC').trim().replace(/\s+/g, '').toUpperCase()
}
export function moldingMaterialFamily(value: unknown) {
  const token = normalizedReferenceToken(value)
  return token === '1#PP' ? 'PP' : token
}
export function moldingMaterialReferences(snapshot?: Record<string, unknown>): MoldingMaterialReference[] {
  const source = snapshot?.material_prices
  if (!source || typeof source !== 'object' || Array.isArray(source)) return []
  return Object.entries(source).flatMap(([key, value]) => {
    const separator = key.indexOf('|')
    const material = (separator >= 0 ? key.slice(0, separator) : key).trim()
    const grade = (separator >= 0 ? key.slice(separator + 1) : '').trim()
    const priceHkdLb = Number(value)
    return material && grade && Number.isFinite(priceHkdLb) ? [{ material, grade, priceHkdLb }] : []
  })
}
export function moldingMachineReferences(snapshot?: Record<string, unknown>): MoldingMachineReference[] {
  const source = snapshot?.machine_prices
  if (!Array.isArray(source)) return []
  return source.flatMap((value) => {
    if (!value || typeof value !== 'object') return []
    const row = value as Record<string, unknown>
    const range = String(row.range ?? '').trim()
    const machine = String(row.machine ?? '').trim()
    const shiftPriceHkd = Number(row.shift_price_hkd)
    return range && Number.isFinite(shiftPriceHkd) ? [{ range, machine, shiftPriceHkd }] : []
  })
}
export function moldingMaterialOptions(row: MoldingMaterialSelection, references: MoldingMaterialReference[]) {
  const hint = normalizedReferenceToken(row.material) || normalizedReferenceToken(row.grade)
  if (!hint) return references
  return references.filter((item) => moldingMaterialFamily(item.material) === moldingMaterialFamily(hint))
}
export function selectedMoldingMaterial(row: MoldingMaterialSelection, references: MoldingMaterialReference[]) {
  const material = normalizedReferenceToken(row.material)
  const grade = normalizedReferenceToken(row.grade)
  if (!material || !grade) return undefined
  const exact = references.filter((item) => normalizedReferenceToken(item.material) === material && normalizedReferenceToken(item.grade) === grade)
  if (exact.length) return exact.length === 1 ? exact[0] : undefined
  if (grade) {
    const matches = references.filter((item) => normalizedReferenceToken(item.grade) === grade && moldingMaterialFamily(item.material) === moldingMaterialFamily(material))
    if (matches.length === 1) return matches[0]
  }
  return undefined
}
function machineCodeValue(value: unknown) {
  const match = normalizedReferenceToken(value).match(/^(\d+(?:\.\d+)?)A?$/)
  return match ? Number(match[1]) : undefined
}
export function selectedMoldingMachine(row: { machine_code: string; machine_name: string }, references: MoldingMachineReference[]) {
  const code = normalizedReferenceToken(row.machine_code)
  const name = normalizedReferenceToken(row.machine_name)
  const exact = references.find((item) => normalizedReferenceToken(item.range) === code || (name && normalizedReferenceToken(item.machine) === name))
  if (exact) return exact
  const numeric = machineCodeValue(row.machine_code)
  if (numeric === undefined) return undefined
  return references.find((item) => {
    const [start, end = start] = item.range.split('-', 2)
    const lower = machineCodeValue(start)
    const upper = machineCodeValue(end)
    return lower !== undefined && upper !== undefined && numeric >= lower && numeric <= upper
  })
}
export function canonicalizeMoldingReferences(payload: MoldingPayload, snapshot?: Record<string, unknown>) {
  const materials = moldingMaterialReferences(snapshot)
  const machines = moldingMachineReferences(snapshot)
  for (const row of [...payload.injection_lines, ...payload.blow_lines]) {
    // Fill an omitted grade only when this resin family has one frozen choice.
    // An explicitly entered, unknown grade still requires resolution.
    const candidates = normalizedReferenceToken(row.material) && !normalizedReferenceToken(row.grade)
      ? moldingMaterialOptions(row, materials) : []
    const material = selectedMoldingMaterial(row, materials) ?? (candidates.length === 1 ? candidates[0] : undefined)
    if (material) {
      if (row.material !== material.material) row.material = material.material
      if (row.grade !== material.grade) row.grade = material.grade
    }
  }
  for (const row of payload.injection_lines) {
    const machine = selectedMoldingMachine(row, machines)
    if (machine) {
      if (row.machine_code !== machine.range) row.machine_code = machine.range
      if (!row.machine_name) row.machine_name = machine.machine
    }
  }
}

// Establish both the editable draft and its saved baseline using exactly the
// same reference canonicalization that the form applies after user selection.
export function normalizeInternalQuoteDraft(code: InternalQuoteSectionCode, value: Record<string, unknown>, snapshot?: Record<string, unknown>) {
  const normalized = normalizeInternalQuotePayload(code, value)
  if (code === 'molding') canonicalizeMoldingReferences(normalized as unknown as MoldingPayload, snapshot)
  return normalized
}

import { normalizeInternalQuotePayload, type EngineeringPayload, type EngineeringMoldRow, type InjectionRow, type MoldingPayload } from './internalQuoteSectionPayload'
import { moldingMaterialFamily, normalizedReferenceToken as token } from './internalQuoteMoldingReferences'
import { createRandomUuid } from './randomUuid'

const genericMaterials = new Set(['ABS', '透明ABS', 'HIPS', 'GP', 'PP', '1#PP', '透明PP', 'POM', 'PVC', 'LDPE', 'HDPE', 'TPR', 'K料', 'PC料'])
const text = (value: unknown) => String(value ?? '').trim()
const newId = (prefix: string) => `${prefix}-${createRandomUuid()}`
const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T

type PartSource = EngineeringMoldRow & { part_source_id?: string; invalid_part_target?: boolean }

function engineeringSourceKeys(molds: PartSource[]): string[] {
  const occurrences = new Map<string, number>()
  return molds.map((mold, index) => {
    if (mold.mold_id) return `mold-id:${mold.mold_id}${mold.part_source_id ? `/part-id:${mold.part_source_id}` : ''}`
    const base = token(mold.mold_no) ? `mold-no:${token(mold.mold_no)}`
      : mold.source_row ? `source-row:${mold.source_row}`
        : token(mold.item || mold.chinese_name) ? `name:${token(mold.item || mold.chinese_name)}` : `index:${index + 1}`
    const count = (occurrences.get(base) ?? 0) + 1
    occurrences.set(base, count)
    return `${base}#${count}`
  })
}

/** Only call for editable drafts. Returns a copy; existing stable IDs survive edits/reordering. */
export function normalizeEngineeringMoldIdentities(payload: EngineeringPayload): EngineeringPayload {
  const result = clone(payload)
  const molds = new Set<string>()
  const parts = new Set<string>()
  const previousKeys = engineeringSourceKeys(result.molds)
  for (const [index, mold] of result.molds.entries()) {
    if (!mold.mold_id) {
      mold.legacy_source_key = previousKeys[index]!
      mold.mold_id = newId('mold')
    } else if (molds.has(mold.mold_id)) {
      mold.mold_id = newId('mold')
      delete mold.legacy_source_key
    }
    molds.add(mold.mold_id)
    for (const part of mold.parts) {
      if (!part.part_id || parts.has(part.part_id)) part.part_id = newId('part')
      parts.add(part.part_id)
    }
  }
  return result
}

/** Projects explicit children as descriptive detail; cost stays once on the whole mold. */
export function linkEngineeringMolding(engineering: EngineeringPayload, molding: MoldingPayload, factoryId = ''): MoldingPayload {
  const molds: PartSource[] = engineering.molds.flatMap(mold => {
    if (factoryId !== 'huadeng' || mold.molding_profile !== 'huadeng_parts_v1') return [mold]
    return mold.parts.map(part => ({ ...mold, parts: [], legacy_source_key: '', part_source_id: part.part_id,
      item: part.name, chinese_name: part.name, material: part.material || '', material_type: part.material_type || '',
      color: part.color, net_weight_g: part.unit_net_weight_g, cavity: String(part.output_count), quantity: part.quantity,
      machine_code: part.machine_code || mold.machine_code,
      target_output: !text(part.target_output) || Number(part.target_output) === 0 ? mold.target_output : Number(part.target_output),
      invalid_part_target: !Number.isFinite(Number(part.target_output ?? 0)) || Number(part.target_output) < 0,
      remark: part.remark || '', source_row: part.source_row || 0, image_attachment_ids: part.image_attachment_ids || [],
    }))
  })
  const result = clone(molding)
  const existing = result.injection_lines
  const used = new Set<number>()
  const keys = engineeringSourceKeys(molds)
  const legacyKeys = molds.map((mold, index) => mold.mold_id ? mold.legacy_source_key ?? '' : keys[index]!)
  const linked: InjectionRow[] = []
  for (const [moldIndex, mold] of molds.entries()) {
    const key = keys[moldIndex]!
    const legacyKey = legacyKeys[moldIndex]!
    const legacyMatches = existing.map((row, i) => ({ row, i })).filter(({ row }) => legacyKey && !row.engineering_mold_id && row.engineering_source_key === legacyKey)
    const associatedMatches = existing.map((row, i) => ({ row, i })).filter(({ row, i }) => legacyMatches.some((match) => match.i === i) || row.engineering_source_key === key || (mold.mold_id && row.engineering_mold_id === mold.mold_id && text(row.engineering_part_id) === text(mold.part_source_id)))
    if (legacyMatches.length && (associatedMatches.length > 1 || legacyKeys.filter((value) => value === legacyKey).length > 1)) {
      for (const { row, i } of associatedMatches) {
        if (used.has(i)) continue
        row.engineering_linkage_conflict = true
        linked.push(row)
        used.add(i)
      }
      continue
    }
    let index = existing.findIndex((row, i) => !used.has(i) && row.engineering_source_key === key)
    if (index < 0 && mold.mold_id) index = existing.findIndex((row, i) => !used.has(i) && row.engineering_mold_id === mold.mold_id && text(row.engineering_part_id) === text(mold.part_source_id))
    if (index < 0 && legacyMatches.length === 1 && !used.has(legacyMatches[0]!.i)) index = legacyMatches[0]!.i
    if (index < 0 && !mold.part_source_id && token(mold.mold_no)) {
      const matches = existing.map((row, i) => ({ row, i })).filter(({ row, i }) => !used.has(i) && !row.engineering_sync_disabled && !row.engineering_mold_id && token(row.mold_no) === token(mold.mold_no))
      if (matches.length === 1 && molds.filter((item) => token(item.mold_no) === token(mold.mold_no)).length === 1) index = matches[0]!.i
    }
    if (index < 0 && !mold.part_source_id && token(mold.item || mold.chinese_name)) {
      const matches = existing.map((row, i) => ({ row, i })).filter(({ row, i }) => !used.has(i) && !row.engineering_sync_disabled && !row.engineering_mold_id && (!token(mold.mold_no) || !token(row.mold_no) || token(mold.mold_no) === token(row.mold_no)) && token(row.item) === token(mold.item || mold.chinese_name))
      if (matches.length === 1 && molds.filter((item) => token(item.item || item.chinese_name) === token(mold.item || mold.chinese_name)).length === 1) index = matches[0]!.i
    }
    const row: InjectionRow = index >= 0 ? existing[index]! : (normalizeInternalQuotePayload('molding', {
      injection_loss_rate_percent: molding.injection_loss_rate_percent,
      injection_lines: [{ quantity: 1, sets: 0 }],
    }) as unknown as MoldingPayload).injection_lines[0]!
    if (index >= 0) used.add(index)
    delete row.engineering_linkage_conflict
    if (mold.mold_id && legacyMatches.some((match) => match.i === index)) {
      row.engineering_mold_id = mold.mold_id
      row.engineering_source_key = key
      row.line_id ||= `injection:${mold.mold_id}`
    }
    // A detached row retains its source identity only to suppress replacement.
    if (row.engineering_sync_disabled) {
      delete row.engineering_source_missing
      linked.push(row)
      continue
    }
    if (mold.mold_id) {
      row.engineering_mold_id = mold.mold_id
      row.line_id ||= `injection:${mold.mold_id}${mold.part_source_id ? `:${mold.part_source_id}` : ''}`
    }
    row.cost_scope = mold.part_source_id ? 'huadeng_part' : 'whole_mold'
    if (mold.part_source_id) {
      row.engineering_part_id = mold.part_source_id
      row.engineering_remark = mold.remark
      row.engineering_source_row = mold.source_row
      row.image_attachment_ids = clone(mold.image_attachment_ids)
      row.engineering_labor_mode = mold.remark.includes('转水口') ? 'transfer' : 'shared'
      row.labor_job_id = `mold-id:${mold.mold_id}/job:${row.engineering_labor_mode === 'transfer' ? mold.part_source_id : 'shared'}`
      if (index < 0) row.remark = mold.remark
    }
    row.engineering_parts = clone(mold.parts)
    delete row.engineering_source_missing
    row.engineering_source_key = key
    const previousSynced = new Set(row.engineering_synced_fields ?? [])
    const synced: string[] = []
    row.engineering_synced_fields = synced
    const syncText = (field: keyof InjectionRow, value: unknown) => {
      if (text(value)) { (row as unknown as Record<string, unknown>)[field] = text(value); synced.push(field) }
      else if (previousSynced.has(field)) (row as unknown as Record<string, unknown>)[field] = ''
    }
    const syncPositive = (field: keyof InjectionRow, value: unknown) => {
      if (Number(value) > 0) { (row as unknown as Record<string, unknown>)[field] = Number(value); synced.push(field) }
      else if (previousSynced.has(field)) (row as unknown as Record<string, unknown>)[field] = 0
    }
    syncText('item', mold.item || mold.chinese_name)
    syncText('mold_no', mold.mold_no)
    syncText('disney_mold_no', mold.disney_mold_no)
    syncText('pricing_component_id', mold.pricing_component_id)
    const material = token(mold.material), grade = token(mold.material_type)
    const generic = genericMaterials.has(material) && !grade ? mold.material
      : genericMaterials.has(grade) && !material ? mold.material_type
        : genericMaterials.has(material) && genericMaterials.has(grade) && moldingMaterialFamily(material) === moldingMaterialFamily(grade)
          ? (material.length >= grade.length ? mold.material : mold.material_type) : mold.part_source_id && !material ? mold.material_type : ''
    if (generic) {
      if (!row.grade || moldingMaterialFamily(generic) !== moldingMaterialFamily(row.material)) {
        syncText('material', generic); row.grade = ''
      }
    } else { syncText('material', mold.material); syncText('grade', mold.material_type) }
    syncText('color', mold.color)
    syncPositive('net_weight_g', mold.net_weight_g)
    syncText('cavity', mold.cavity)
    syncPositive('sets', mold.quantity)
    if (mold.part_source_id) syncPositive('quantity', 1)
    if (text(mold.machine_code)) {
      const raw = token(mold.machine_code)
      const numeric = /^\d+(?:\.\d+)?A?$/.test(raw) ? Number(raw.replace(/A$/, '')) : undefined
      const bounds = token(row.machine_code).split('-', 2).map((bound) => /^\d+(?:\.\d+)?A?$/.test(bound) ? Number(bound.replace(/A$/, '')) : NaN)
      if (!(mold.part_source_id && row.machine_code && row.engineering_machine_hint === (numeric === undefined ? mold.machine_code : `${numeric}A`)) && !(numeric !== undefined && Number.isFinite(bounds[0]) && numeric >= bounds[0]! && numeric <= (bounds[1] ?? bounds[0]!))) {
        if (row.machine_code) row.machine_name = ''
        row.machine_code = numeric === undefined ? mold.machine_code : `${numeric}A`
      }
      synced.push('machine_code')
    } else if (previousSynced.has('machine_code')) {
      row.machine_code = ''
      row.machine_name = ''
    }
    if (mold.part_source_id) {
      const raw = token(mold.machine_code)
      row.engineering_machine_hint = /^\d+(?:\.\d+)?A?$/.test(raw) ? `${Number(raw.replace(/A$/, ''))}A` : mold.machine_code
    }
    if (mold.part_source_id) {
      row.target_output = Number.isFinite(mold.target_output) ? mold.target_output : 0
      synced.push('target_output')
      if (mold.invalid_part_target) row.engineering_linkage_conflict = true
    } else syncPositive('target_output', mold.target_output)
    syncPositive('cycle_time_seconds', mold.cycle_time_seconds)
    linked.push(row)
  }
  existing.forEach((row, index) => {
    if (used.has(index)) return
    delete row.engineering_linkage_conflict
    if (row.engineering_sync_disabled) delete row.engineering_source_missing
    else if (row.engineering_source_key) row.engineering_source_missing = true
    linked.push(row)
  })
  result.injection_lines = linked
  return result
}

/** Job identity is derived from source IDs; detached/copied rows cost independently. */
export function huadengLaborJob(row: InjectionRow, factoryId?: string): string {
  if (factoryId !== 'huadeng' || row.cost_scope !== 'huadeng_part' || row.engineering_sync_disabled || !row.engineering_mold_id || !row.engineering_part_id) return ''
  return `mold-id:${row.engineering_mold_id}/job:${row.engineering_labor_mode === 'transfer' ? row.engineering_part_id : 'shared'}`
}
export function injectionLaborOwner(row: InjectionRow, rows: InjectionRow[], factoryId?: string): boolean {
  const job = huadengLaborJob(row, factoryId)
  return !job || rows.find(candidate => huadengLaborJob(candidate, factoryId) === job) === row
}

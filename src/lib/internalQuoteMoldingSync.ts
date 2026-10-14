type Row = Record<string, unknown>
type Payload = Record<string, unknown>
type EngineeringIdentities = { molds?: Array<{ mold_id?: string; legacy_source_key?: string }> }

const text = (value: unknown) => String(value || '')
const equal = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)
const associated = (row: Row) => Boolean(row.engineering_source_key || row.engineering_mold_id)
const fields = (row: Row) => Array.isArray(row.engineering_synced_fields) ? row.engineering_synced_fields as string[] : []

/** Rebase Engineering changes only; competing department edits remain conflicts. */
export function rebaseEngineeringMolding(
  baseline: Payload, incoming: Payload, local: Payload, engineering?: EngineeringIdentities,
): Payload | undefined {
  if (equal(baseline, incoming)) return local
  if (!equal({ ...baseline, injection_lines: [] }, { ...incoming, injection_lines: [] })) return
  const before = (baseline.injection_lines ?? []) as Row[]
  const after = (incoming.injection_lines ?? []) as Row[]
  const draft = (local.injection_lines ?? []) as Row[]
  if (!equal(before.filter(row => !associated(row)), after.filter(row => !associated(row)))) return
  const aliases = (row: Row) => {
    const values = new Set<string>()
    if (row.line_id) values.add(`line:${text(row.line_id)}`)
    if (row.engineering_source_key) values.add(`source:${text(row.engineering_source_key)}`)
    if (row.engineering_mold_id) values.add(`mold:${text(row.engineering_mold_id)}`)
    for (const mold of engineering?.molds ?? []) {
      if (mold.mold_id && (row.engineering_mold_id === mold.mold_id
        || row.engineering_source_key === `mold-id:${mold.mold_id}`)) {
        if (mold.legacy_source_key) values.add(`source:${mold.legacy_source_key}`)
      }
    }
    return values
  }
  const matches = (row: Row, candidates: Row[]) => {
    const identity = aliases(row)
    return candidates.filter(candidate => [...aliases(candidate)].some(value => identity.has(value)))
  }
  const used = new Set<Row>()
  const projected: Row[] = []
  for (const row of after.filter(associated)) {
    const previous = matches(row, before.filter(associated))
    if (previous.length > 1) return // Never guess among competing legacy associations.
    const old = previous[0]
    const candidates = matches(old ?? row, draft.filter(associated))
    if (candidates.length > 1) return
    const current = candidates[0]
    const owned = new Set(['line_id', 'engineering_mold_id', 'engineering_source_key', 'engineering_synced_fields',
      'engineering_parts', 'engineering_source_missing', 'engineering_linkage_conflict', 'cost_scope',
      ...fields(old ?? {}), ...fields(row)])
    if (old) {
      for (const field of new Set([...Object.keys(old), ...Object.keys(row)])) {
        if (!owned.has(field) && !equal(old[field], row[field])) return
      }
    }
    if (old && !current) continue // Retain explicit local deletion until ordinary save.
    if (current) used.add(current)
    const merged = current ? { ...current } : { ...row }
    if (current?.engineering_sync_disabled === true) {
      // A local detach suppresses replacement. Only adopt the proven identity;
      // Engineering edits cannot restore parts or replace local cost inputs.
      if (row.engineering_mold_id) merged.engineering_mold_id = row.engineering_mold_id
      if (row.engineering_source_key) merged.engineering_source_key = row.engineering_source_key
      if (!merged.line_id && row.line_id) merged.line_id = row.line_id
      delete merged.engineering_source_missing
    } else {
      for (const field of owned) {
        if (field === 'line_id' && merged.line_id) continue
        if (!old || !equal(old[field], row[field])) {
          if (Object.prototype.hasOwnProperty.call(row, field)) merged[field] = row[field]
          else delete merged[field]
        }
      }
    }
    projected.push(merged)
  }
  for (const row of draft) {
    if (used.has(row)) continue
    // Removed sources retain all local work for explicit deletion/detachment.
    const retained = { ...row }
    if (associated(row) && row.engineering_sync_disabled !== true) retained.engineering_source_missing = true
    else delete retained.engineering_source_missing
    projected.push(retained)
  }
  return { ...local, injection_lines: projected }
}

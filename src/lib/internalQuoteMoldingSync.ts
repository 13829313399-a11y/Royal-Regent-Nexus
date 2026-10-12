type Row = Record<string, unknown>
type Payload = Record<string, unknown>

const key = (row: Row) => String(row.engineering_source_key || '')
const parentKey = (value: string) => value.split('/part:')[0]!
const equal = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)

/** Rebase only engineering-owned changes; concurrent department edits still conflict. */
export function rebaseEngineeringMolding(baseline: Payload, incoming: Payload, local: Payload): Payload | undefined {
  if (equal(baseline, incoming)) return local
  if (!equal({ ...baseline, injection_lines: [] }, { ...incoming, injection_lines: [] })) return
  const before = baseline.injection_lines as Row[]
  const after = incoming.injection_lines as Row[]
  const draft = local.injection_lines as Row[]
  const oldByKey = new Map(before.filter(row => key(row)).map(row => [key(row), row]))
  const localByKey = new Map(draft.filter(row => key(row)).map(row => [key(row), row]))
  if (!equal(before.filter(row => !key(row)), after.filter(row => !key(row)))) return
  const projected: Row[] = []
  for (const row of after.filter(row => key(row))) {
    const source = key(row)
    const legacyMatches = before.filter(candidate => key(candidate).startsWith(`${parentKey(source)}/part:[`)
      && candidate.item === row.item)
    const old = oldByKey.get(source) ?? oldByKey.get(source.replace('/part:id:legacy-name:', '/part:'))
      ?? (legacyMatches.length === 1 ? legacyMatches[0] : undefined) ?? oldByKey.get(parentKey(source))
    const current = localByKey.get(source) ?? (old ? localByKey.get(key(old)) : undefined)
    const owned = new Set(['engineering_source_key', 'engineering_synced_fields',
      ...(Array.isArray(row.engineering_synced_fields) ? row.engineering_synced_fields as string[] : [])])
    if (old) {
      for (const field of new Set([...Object.keys(old), ...Object.keys(row)])) {
        if (!owned.has(field) && !equal(old[field], row[field])) return
      }
    }
    if (old && !current) continue // Retain a local deletion until the normal save reconciles it.
    const merged = current ? { ...current } : { ...row }
    for (const field of owned) {
      if (!old || source !== key(old) || !equal(old[field], row[field])) merged[field] = row[field]
    }
    projected.push(merged)
  }
  return { ...local, injection_lines: [...projected, ...draft.filter(row => !key(row))] }
}

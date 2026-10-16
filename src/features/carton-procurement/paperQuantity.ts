export interface PaperQuantityRule {
  mode: 'PACKING' | 'PER_CARTON'
  carton_line_no?: number | null
  per_carton_quantity?: number | string | null
  manual_quantity?: number | string | null
}
export interface QuantityPaper {
  usage_quantity: number | string | null
  quantity_rule?: PaperQuantityRule | null
  packaging_type?: string
}
export interface PaperDemand { automatic: number; actual: number; error: string }
// Decimal inputs are kept as integer fractions so 3 / 0.1 cannot round to 31.
function fraction(value: number | string | null): [bigint, bigint] | null {
  const raw = String(value ?? 0).trim().replace(/^\./, '0.')
  const match = raw.match(/^\+?(\d+)(?:\.(\d*))?(?:e([+-]?\d+))?$/i)
  if (!match || !Number.isFinite(Number(raw))) return null
  const scale = (match[2]?.length ?? 0) - Number(match[3] ?? 0)
  if (Math.abs(scale) > 30 || raw.length > 60) return null
  const digits = BigInt(match[1]! + (match[2] ?? ''))
  return scale >= 0 ? [digits, 10n ** BigInt(scale)] : [digits * 10n ** BigInt(-scale), 1n]
}
function roundedDemand(a: number | string | null, b: number | string | null, multiply = false) {
  const left = fraction(a), right = fraction(b)
  if (!left || !right || !right[0]) return 0
  const n = left[0] * right[multiply ? 0 : 1], d = left[1] * right[multiply ? 1 : 0]
  return Number((n + d - 1n) / d)
}

/** Calculate every parent first. References belong to this complete ordered list. */
export function paperDemands(products: number | string | null, lines: QuantityPaper[]): PaperDemand[] {
  const result = lines.map(() => ({ automatic: 0, actual: 0, error: '' }))
  const finish = (i: number, automatic: number, error = '') => {
    const manual = lines[i]!.quantity_rule?.manual_quantity
    const actual = manual == null ? automatic : Number(manual)
    result[i] = { automatic, actual, error: error || (manual === '' || !Number.isFinite(actual) || actual < 0 || actual >= 1e14 ? '请填写有效纸品数量' : '') }
  }
  lines.forEach((line, i) => {
    if (line.quantity_rule?.mode === 'PER_CARTON') return
    const packing = Number(line.usage_quantity)
    const valid = packing > 0 && fraction(line.usage_quantity) !== null
    finish(i, valid ? roundedDemand(products || 0, line.usage_quantity) : 0, valid ? '' : '请填写每箱装产品数')
  })
  lines.forEach((line, i) => {
    const rule = line.quantity_rule
    if (rule?.mode !== 'PER_CARTON') return
    const parent = Number(rule.carton_line_no) - 1
    const amount = Number(rule.per_carton_quantity)
    const valid = Number.isInteger(parent) && parent >= 0 && parent !== i && !!lines[parent] && lines[parent]!.quantity_rule?.mode !== 'PER_CARTON'
    const error = !valid ? '请选择对应纸箱' : !(amount > 0) || !fraction(rule.per_carton_quantity ?? null) ? '请填写每箱配套用量' : result[parent]!.error
    finish(i, error ? 0 : roundedDemand(result[parent]!.actual, rule.per_carton_quantity ?? null, true), error)
  })
  return result
}

export function reusableQuantityRule(rule?: PaperQuantityRule | null) {
  return rule ? { ...rule, manual_quantity: null } : null
}

export function quantityRuleLabel(line: QuantityPaper) {
  const rule = line.quantity_rule
  return rule?.mode === 'PER_CARTON' ? `配第 ${rule.carton_line_no ?? '未选'} 项 · 每箱 ${rule.per_carton_quantity ?? '未填'}` : `每箱装 ${line.usage_quantity ?? '未填'} 个产品`
}

export function referencesAfterRemoval(rule: PaperQuantityRule | null | undefined, removedIndex: number) {
  if (rule?.mode !== 'PER_CARTON' || rule.carton_line_no == null) return rule
  return { ...rule, carton_line_no: rule.carton_line_no === removedIndex + 1 ? null : rule.carton_line_no > removedIndex + 1 ? rule.carton_line_no - 1 : rule.carton_line_no }
}

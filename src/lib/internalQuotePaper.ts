export interface QuotePaperPrice { key: string; name: string; price_factor_hkd: string; remark: string }
export interface PaperSelection { paper_material_key?: string }
export function quotePaperPrices(snapshot?: Record<string, unknown>): QuotePaperPrice[] {
  return Array.isArray(snapshot?.paper_prices) ? snapshot.paper_prices.filter((r): r is QuotePaperPrice => Boolean(r && typeof r === 'object' && typeof r.key === 'string' && typeof r.name === 'string')) : []
}
export function selectedPaperFactor(row: PaperSelection, fallback: unknown, snapshot?: Record<string, unknown>) {
  const key = row.paper_material_key?.trim()
  if (!key) return Number(fallback)
  const matches = quotePaperPrices(snapshot).filter(p => p.key === key)
  return matches.length === 1 ? Number(matches[0]!.price_factor_hkd) : 0
}
export function paperRowsError(rows: QuotePaperPrice[]) {
  if (rows.length > 100) return '纸材最多 100 项'
  if (rows.some(r => !r.name.trim() || !r.price_factor_hkd.trim() || !Number.isFinite(Number(r.price_factor_hkd)) || Number(r.price_factor_hkd) <= 0)) return '请填写纸材名称和大于 0 的 HKD 系数'
  if (new Set(rows.map(r => r.name.trim().toLocaleLowerCase())).size !== rows.length) return '纸材名称不能重复'
  return ''
}

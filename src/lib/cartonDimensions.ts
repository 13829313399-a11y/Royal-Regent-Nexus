// Formatting only: never use a displayed legacy default to rewrite a stock key.
export function cartonDimensionParts(specification: string, unit?: string | null) {
  const text = specification.trim()
  const match = text.match(/\s*(?:\[(cm|in|inch|inches|mm|ft|m)\]|(cm|inches|inch|in|mm|ft|m|英寸|英吋|厘米|公分|毫米|″|"))$/i)
  const suffix = match && !(match.index! > 0 && /\p{L}/u.test(match[0][0]!) && /\p{L}/u.test(text[match.index! - 1]!)) ? match : null
  const aliases: Record<string, string> = { inch: 'in', inches: 'in', 英寸: 'in', 英吋: 'in', '″': 'in', '"': 'in', 厘米: 'cm', 公分: 'cm', 毫米: 'mm' }
  const explicit = unit?.trim().toLowerCase() || (suffix?.[1] || suffix?.[2])?.toLowerCase() || 'cm'
  return { specification: suffix ? text.slice(0, suffix.index).trim() : text, unit: aliases[explicit] || explicit }
}

export function formatCartonSpecification(specification: string, unit?: string | null) {
  if (!specification.trim()) return ''
  const parts = cartonDimensionParts(specification, unit)
  return `${parts.specification} ${parts.unit}`
}

export const UNORDERED_CUSTOMER_CODE = '__UNORDERED__'

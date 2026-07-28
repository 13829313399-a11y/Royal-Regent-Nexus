import type { InternalQuote, InternalQuoteSectionCode } from '@/types/internalQuoteDesk'

export type InternalQuoteComparisonState =
  | 'valid'
  | 'not_applicable'
  | 'not_participating'
  | 'invalid'

export interface InternalQuoteComparisonValue {
  quoteId: string
  amountHkd: number | null
  deltaFromBaselineHkd: number | null
  state: InternalQuoteComparisonState
}

export interface InternalQuoteComparisonRow {
  code: InternalQuoteSectionCode
  label: string
  values: InternalQuoteComparisonValue[]
  minimumHkd: number | null
  maximumHkd: number | null
  gapHkd: number | null
}

export interface InternalQuoteComparisonResult {
  baselineQuoteId: string
  rows: InternalQuoteComparisonRow[]
}

const sectionDefinitions: Array<{ code: InternalQuoteSectionCode; label: string }> = [
  { code: 'sales', label: '业务部' },
  { code: 'engineering', label: '工程部' },
  { code: 'electronic', label: '电子部' },
  { code: 'molding', label: '啤机部' },
  { code: 'painting', label: '喷油部' },
  { code: 'slush', label: '搪胶部' },
  { code: 'sewing', label: '车缝部' },
  { code: 'hair', label: '车发部' },
  { code: 'assembly', label: '装配部' },
]

function sectionValue(quote: InternalQuote, code: InternalQuoteSectionCode) {
  const section = quote.sections.find((item) => item.code === code)
  if (!section?.isRequired) return { amountHkd: null, state: 'not_participating' as const }
  if (section.status === 'not_applicable') return { amountHkd: 0, state: 'not_applicable' as const }
  if (
    section.calculationStatus !== 'valid'
    || section.dependencyStatus !== 'current'
    || !Number.isFinite(section.totalHkd)
  ) {
    return { amountHkd: null, state: 'invalid' as const }
  }
  return { amountHkd: section.totalHkd, state: 'valid' as const }
}

function comparisonRow(
  quotes: InternalQuote[],
  code: InternalQuoteSectionCode,
  label: string,
): InternalQuoteComparisonRow {
  const rawValues = quotes.map((quote) => sectionValue(quote, code))
  const baselineAmount = rawValues[0]?.amountHkd ?? null
  const values = rawValues.map((value, index) => ({
    quoteId: quotes[index].id,
    amountHkd: value.amountHkd,
    deltaFromBaselineHkd: baselineAmount == null || value.amountHkd == null
      ? null
      : value.amountHkd - baselineAmount,
    state: value.state,
  }))
  const amounts = values
    .map((value) => value.amountHkd)
    .filter((amount): amount is number => amount != null)
  const minimumHkd = amounts.length ? Math.min(...amounts) : null
  const maximumHkd = amounts.length ? Math.max(...amounts) : null
  return {
    code,
    label,
    values,
    minimumHkd,
    maximumHkd,
    gapHkd: amounts.length >= 2 ? maximumHkd! - minimumHkd! : null,
  }
}

export function buildInternalQuoteComparison(quotes: InternalQuote[]): InternalQuoteComparisonResult {
  const sectionRows = sectionDefinitions
    .map(({ code, label }) => comparisonRow(quotes, code, label))
    .filter((row) => row.values.some((value) => value.state !== 'not_participating'))
  return {
    baselineQuoteId: quotes[0]?.id ?? '',
    rows: sectionRows,
  }
}

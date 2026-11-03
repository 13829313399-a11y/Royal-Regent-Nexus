import type { ApiInternalQuoteAlternative } from '@/api/internalQuote'

interface WorkingVersions { lastQuoteId: string; lastRootId: string; products: Record<string, string> }
const empty = (): WorkingVersions => ({ lastQuoteId: '', lastRootId: '', products: {} })
const key = (userId: string, factory: string, document: string) => `internal-quote-working-v1:${JSON.stringify([userId, factory, document])}`

export function readWorkingVersions(userId: string, factory: string, document: string): WorkingVersions {
  if (!userId || !factory || !document) return empty()
  try {
    const value = JSON.parse(localStorage.getItem(key(userId, factory, document)) || 'null')
    if (!value || typeof value.lastQuoteId !== 'string' || typeof value.lastRootId !== 'string' || !value.products || typeof value.products !== 'object' || Array.isArray(value.products)) return empty()
    return { lastQuoteId: value.lastQuoteId, lastRootId: value.lastRootId,
      products: Object.fromEntries(Object.entries(value.products).filter((entry): entry is [string, string] => typeof entry[1] === 'string')) }
  } catch { return empty() }
}

export function rememberWorkingVersion(userId: string, quote: {
  id: string; factoryId: string; documentQuoteId?: string; productRootId?: string
  versionArchived?: boolean; documentArchive?: unknown; status: string
}) {
  if (!userId || quote.versionArchived || quote.documentArchive || quote.status === 'archived') return
  const document = quote.documentQuoteId || quote.id, root = quote.productRootId || quote.id
  const previous = readWorkingVersions(userId, quote.factoryId, document)
  const next = { lastQuoteId: quote.id, lastRootId: root, products: { ...previous.products, [root]: quote.id } }
  try { localStorage.setItem(key(userId, quote.factoryId, document), JSON.stringify(next)) } catch { /* Optional device preference; never blocks quote work. */ }
}

/** An unavailable remembered/group member requires a choice, never a silent original-version fallback. */
export function chooseWorkingVersion(options: ApiInternalQuoteAlternative[], currentId: string, groupId: string | undefined, rememberedId: string | undefined, defaultId: string) {
  const requested = options.some(row => row.quote_id === currentId) ? currentId : groupId || rememberedId || defaultId
  return options.some(row => row.quote_id === requested && !row.archived) ? requested : ''
}

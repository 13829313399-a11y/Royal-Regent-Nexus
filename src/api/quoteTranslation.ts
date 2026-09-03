import { http } from '@/lib/http'

export interface QuoteTranslationResponse {
  items: Array<{ source: string; translation: string; needs_review: boolean }>
  warning: string
  engine: 'local'
}

export async function translateQuoteDescriptions(texts: string[], factoryId: string, signal?: AbortSignal) {
  const response = await http.post<QuoteTranslationResponse>('/pricing/translate-descriptions', {
    factory_id: factoryId, customer_id: 'yinhui', texts,
  }, { signal, timeout: 120000 })
  return response.data
}

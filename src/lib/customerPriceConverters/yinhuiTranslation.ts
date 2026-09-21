import type { YinhuiQuoteData } from './yinhui'
import type { QuoteTranslationResponse } from '@/api/quoteTranslation'

export const hasChineseQuoteText = (text: string) => /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/.test(text)

export function yinhuiDescriptionRows(data: YinhuiQuoteData) {
  // BOM descriptions retain source Chinese; only Tool Plan names need translation.
  return data.tools
}
export function pendingYinhuiDescriptions(data: YinhuiQuoteData) {
  return [data.productName, data.packaging, ...yinhuiDescriptionRows(data).map(row => row.description)].filter(hasChineseQuoteText).length
}

/** Only captured text fields can be updated; numeric/formula/source fields are never sent. */
export async function translateYinhuiDescriptions(
  data: YinhuiQuoteData,
  translate: (texts: string[]) => Promise<QuoteTranslationResponse>,
  isCurrent: () => boolean = () => true,
) {
  const fields = [
    ...(['productName', 'packaging'] as const).map(key => ({ get: () => data[key], set: (value: string) => { data[key] = value } })),
    ...yinhuiDescriptionRows(data).map(row => ({ get: () => row.description, set: (value: string) => { row.originalDescription ||= row.description; row.description = value } })),
  ].map(field => ({ ...field, source: field.get() })).filter(field => hasChineseQuoteText(field.source))
  if (!fields.length) return { translated: 0, remaining: 0, warning: '' }
  const texts = [...new Set(fields.map(field => field.source))]
  const response = await translate(texts)
  if (!isCurrent()) return { translated: 0, remaining: fields.length, warning: '' }
  if (response?.engine !== 'local' || !Array.isArray(response.items) || response.items.length !== texts.length) throw new Error('自动翻译返回格式不正确，已保留原文。')
  const values = new Map<string, string>()
  for (const [i, item] of response.items.entries()) {
    if (item.source !== texts[i] || typeof item.translation !== 'string' || !item.translation.trim() || item.translation.length > 6000) throw new Error('自动翻译结果与原文不对应，已保留原文。')
    // Every non-CJK segment (specification, code, dimension, unit, punctuation)
    // must still appear in order, and no new number may be introduced.
    let offset = 0
    const normalizedTranslation = item.translation.replace(/[ \t]+/g, ' ')
    for (const literal of item.source.split(/[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+/).map(s => s.trim()).filter(Boolean)) {
      const normalizedLiteral = literal.replace(/[ \t]+/g, ' ')
      const found = normalizedTranslation.indexOf(normalizedLiteral, offset)
      if (found < 0) throw new Error('自动翻译改变了规格或型号，已保留原文，请核对。')
      offset = found + normalizedLiteral.length
    }
    if (JSON.stringify(item.source.match(/\d+(?:\.\d+)?/g)) !== JSON.stringify(item.translation.match(/\d+(?:\.\d+)?/g))) throw new Error('自动翻译改变了数字，已保留原文，请核对。')
    values.set(item.source, item.translation)
  }
  let translated = 0
  for (const field of fields) {
    // A delayed response must not overwrite a manual correction made meanwhile.
    if (field.get() !== field.source) continue
    const value = values.get(field.source)!
    if (value !== field.source) { field.set(value); translated++ }
  }
  return { translated, remaining: pendingYinhuiDescriptions(data), warning: response.warning || '' }
}

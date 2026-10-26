import { onBeforeUnmount } from 'vue'
import { registerAssistantSelection } from '@/features/assistant/selection'
import type { ContextSelection } from '@/features/assistant/v2'
import { internalQuoteSectionDefinitions } from '@/data/internalQuoteDeskConfig'

export const quoteDepartments = [...new Set(internalQuoteSectionDefinitions.flatMap(section => section.departments))]
export const quoteFactories = ['huaxing', 'huadeng', 'huakang-a', 'huakang-b', 'huakang-c', 'huakang-d']

export function quoteSelection(factory: string, ids: string[], filters: ContextSelection['filters'] = {}): ContextSelection {
  const invalid = !quoteFactories.includes(factory) ? '请选择明确的报价厂区。'
    : ids.length > 10 || ids.some(id => !id || id.length > 64 || id !== id.trim()) || new Set(ids).size !== ids.length
      ? '请核对原报价版本；一次最多带入10条不同记录。'
      : (typeof filters.keyword === 'string' && filters.keyword.length > 128) || (typeof filters.customer === 'string' && filters.customer.length > 128)
        ? '报价搜索词和客户条件最多128字，请缩短后带入。' : filters.scope_error
  if (invalid) return { selection_id: 'quote-unavailable', resources: [], filters: { factory_id: factory, scope_error: String(invalid) } }
  return { selection_id: ids.length ? 'quote-selected-versions' : 'quote-list-scope',
    resources: ids.map(id => ({ module_id: 'internal-quote', resource_type: 'quote', resource_id: id })),
    filters: { ...filters, factory_id: factory } }
}

export function useQuoteAssistantSelection(read: () => ContextSelection) {
  onBeforeUnmount(registerAssistantSelection('internal-quote', read))
}

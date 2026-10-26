import { computed } from 'vue'
import type { Draft, DraftScope, PageContext } from './types'
import { assistantSelection } from './selection'

// Scope is an intent snapshot, never authorization. The server re-reads each ID.
export function useDraftScope(draft: () => Draft, page: () => PageContext | null, title: () => string) {
  const current = (): DraftScope => ({ page: page(), title: title(), selection: assistantSelection(page()?.module_id) })
  const scope = computed(() => draft().scope ?? current())
  const freeze = () => draft().scope ??= JSON.parse(JSON.stringify(current())) as DraftScope
  const changed = computed(() => !!draft().scope?.page && JSON.stringify(draft().scope?.page) !== JSON.stringify(page()))
  function adopt() { draft().scope = JSON.parse(JSON.stringify(current())) as DraftScope }
  function includeCurrent() {
    const next = JSON.parse(JSON.stringify(current())) as DraftScope
    const bound = draft().scope
    if (bound?.selection && next.selection && JSON.stringify(bound.page) === JSON.stringify(next.page)) {
      const key = (r: typeof next.selection.resources[number]) => `${r.module_id}:${r.resource_type}:${r.resource_id}`
      const records = new Map(bound.selection.resources.map(r => [key(r), r]))
      next.selection.resources.forEach(r => records.set(key(r), r))
      if (records.size > 10) return '本轮最多带入 10 条记录，请先移除不需要的记录。'
      next.selection.resources = [...records.values()]
    }
    draft().scope = next
    return ''
  }
  function removePage() { draft().scope = { page: null, title: '自由交流', selection: null } }
  function removeSelection(index?: number) {
    const bound = freeze()
    if (index === undefined) bound.selection = null
    else if (bound.selection) bound.selection.resources.splice(index, 1)
  }
  return { scope, freeze, changed, adopt, includeCurrent, removePage, removeSelection }
}

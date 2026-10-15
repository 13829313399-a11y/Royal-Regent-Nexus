import { onScopeDispose, ref, watch } from 'vue'
import { cartonMovementHistoryApi, type CartonHistoryMovement, type CartonMovementHistoryQuery } from '@/api/cartonMovementHistory'
import { getApiErrorMessage } from '@/lib/http'

export function useCartonMovementHistory(
  query: () => CartonMovementHistoryQuery | null,
  refreshKey: () => unknown = () => '',
) {
  const items = ref<CartonHistoryMovement[]>([])
  const total = ref(0)
  const loading = ref(false)
  const error = ref('')
  let generation = 0

  async function reload() {
    const currentGeneration = ++generation
    const request = query()
    // Clear prior scope/filter/page immediately, so a late response cannot
    // expose an old account or factory's history or leave stale correction actions.
    items.value = []
    total.value = 0
    error.value = ''
    loading.value = Boolean(request)
    if (!request) return
    try {
      const page = await cartonMovementHistoryApi.list({ ...request })
      if (currentGeneration !== generation) return
      items.value = page.items
      total.value = page.total
    } catch (failure) {
      if (currentGeneration !== generation) return
      error.value = getApiErrorMessage(failure)
    } finally {
      if (currentGeneration === generation) loading.value = false
    }
  }

  watch([query, refreshKey], () => { void reload() }, { immediate: true, deep: true })
  onScopeDispose(() => { generation++ })
  return { items, total, loading, error, reload }
}

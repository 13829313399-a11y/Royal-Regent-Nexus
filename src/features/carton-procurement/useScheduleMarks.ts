import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { cartonScheduleMarksApi, type ScheduleMarksWorkspace } from '@/api/cartonScheduleMarks'
import { getApiErrorMessage } from '@/lib/http'

export function useScheduleMarks(scope: () => { factory: string; batch: string; viewer: string; enabled: boolean }) {
  const data = ref<ScheduleMarksWorkspace | null>(null), loading = ref(false), error = ref('')
  const context = computed(() => JSON.stringify(scope()))
  let sequence = 0, controller: AbortController | undefined
  async function refresh() {
    const original = context.value, current = scope(), token = ++sequence
    controller?.abort(); controller = new AbortController()
    data.value = null; error.value = ''; loading.value = false
    if (!current.enabled || !current.batch) return
    loading.value = true
    try {
      const result = await cartonScheduleMarksApi.get(current.factory, current.batch, controller.signal)
      if (token !== sequence || context.value !== original) return
      if (result.factory_id !== current.factory || result.batch_id !== current.batch) throw new Error('箱唛资料范围与当前排期不一致，请重新读取。')
      data.value = result
    } catch (cause) { if (token === sequence && context.value === original) error.value = getApiErrorMessage(cause) }
    finally { if (token === sequence) loading.value = false }
  }
  watch(context, refresh, { immediate: true, flush: 'sync' })
  const key = (sheet?: string, row?: number) => JSON.stringify([sheet || '', row || 0])
  const rows = computed(() => new Map(data.value?.rows.map(row => [key(row.source_sheet, row.source_row), row]) ?? []))
  const find = (row: { sourceSheet?: string; sourceRow?: number }) => rows.value.get(key(row.sourceSheet, row.sourceRow))
  const focus = () => { if (scope().enabled) void refresh() }
  window.addEventListener('focus', focus)
  onBeforeUnmount(() => { sequence++; controller?.abort(); window.removeEventListener('focus', focus) })
  return { data, loading, error, refresh, find }
}

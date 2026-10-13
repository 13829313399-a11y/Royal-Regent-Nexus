import { computed, onBeforeUnmount, onMounted, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { directoryApi, type DirectoryMembersParams, type DirectoryMember, type DirectoryStateCounts } from '@/api/directory'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'

export function useDirectoryQuery(params: MaybeRefOrGetter<DirectoryMembersParams>, enabled: MaybeRefOrGetter<boolean> = true) {
  const auth = useAuthStore(), items = ref<DirectoryMember[]>([]), total = ref(0), totalPages = ref(0)
  const counts = ref<DirectoryStateCounts>({ online: 0, away: 0, offline: 0 }), loading = ref(false), error = ref(''), stale = ref(false)
  const owner = computed(() => `${auth.currentUser?.id ?? ''}:${auth.currentUser?.identity?.employment_epoch ?? 1}`)
  let disposed = false, sequence = 0, controller: AbortController | undefined, timer: ReturnType<typeof setTimeout> | undefined, foreground = false
  const canPoll = () => !disposed && toValue(enabled) && document.visibilityState === 'visible' && navigator.onLine !== false
  function cancel() { sequence++; controller?.abort(); clearTimeout(timer); loading.value = false; foreground = false }
  async function load(background = false) {
    if (disposed || !toValue(enabled) || (background && foreground)) return
    controller?.abort(); clearTimeout(timer); controller = new AbortController()
    const seq = ++sequence, key = owner.value, request = controller
    foreground = !background; if (!background || !items.value.length) loading.value = true
    try {
      const result = await directoryApi.getMembers({ ...toValue(params) }, request.signal)
      if (disposed || seq !== sequence || key !== owner.value) return
      items.value = result.items; total.value = result.total; totalPages.value = result.total_pages; counts.value = result.state_counts; error.value = ''; stale.value = false
    } catch (caught) {
      if (disposed || seq !== sequence || key !== owner.value || request.signal.aborted) return
      error.value = getApiErrorMessage(caught); stale.value = items.value.length > 0
    } finally {
      if (!disposed && seq === sequence && key === owner.value) { loading.value = false; foreground = false; if (canPoll()) timer = setTimeout(() => void load(true), 45_000) }
    }
  }
  function resume() { clearTimeout(timer); if (canPoll()) void load(true) }
  watch(() => JSON.stringify(toValue(params)), () => { if (toValue(enabled)) void load() })
  watch(() => toValue(enabled), open => { cancel(); if (open) void load() }, { immediate: true })
  watch(owner, () => { cancel(); items.value = []; total.value = 0; counts.value = { online: 0, away: 0, offline: 0 }; error.value = ''; stale.value = false; if (toValue(enabled)) void load() })
  onMounted(() => { document.addEventListener('visibilitychange', resume); window.addEventListener('focus', resume); window.addEventListener('online', resume); window.addEventListener('offline', resume) })
  onBeforeUnmount(() => { disposed = true; cancel(); document.removeEventListener('visibilitychange', resume); window.removeEventListener('focus', resume); window.removeEventListener('online', resume); window.removeEventListener('offline', resume) })
  return { items, total, totalPages, counts, loading, error, stale, load, cancel }
}

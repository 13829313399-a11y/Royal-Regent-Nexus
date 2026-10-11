import { onBeforeUnmount, onMounted, ref } from 'vue'
import { authApi, type PasswordResetClaimResponse } from '@/api/auth'
export function usePasswordResetClaim() {
  const claim = ref<PasswordResetClaimResponse | null>(null)
  const refreshing = ref(false)
  const refreshError = ref('')
  let disposed = false
  let generation = 0
  let pending: Promise<void> | null = null
  let timer: ReturnType<typeof setTimeout> | undefined
  function schedule() {
    clearTimeout(timer)
    if (!disposed && document.visibilityState === 'visible' && claim.value?.status === 'pending') timer = setTimeout(() => { void refresh() }, 15_000)
  }
  function refresh(): Promise<void> {
    if (disposed) return Promise.resolve()
    if (pending) return pending
    const current = generation
    refreshing.value = true
    pending = (async () => {
      try {
        const result = await authApi.getPasswordResetClaim()
        if (disposed || current !== generation) return
        claim.value = result
        refreshError.value = ''
      } catch {
        if (!disposed && current === generation) refreshError.value = '状态刷新失败，稍后重试'
      } finally {
        if (!disposed && current === generation) { refreshing.value = false; pending = null; schedule() }
      }
    })()
    return pending
  }
  function visibility() {
    clearTimeout(timer)
    if (document.visibilityState === 'hidden') { generation++; pending = null; refreshing.value = false }
    else void refresh()
  }
  onMounted(() => { document.addEventListener('visibilitychange', visibility); void refresh() })
  onBeforeUnmount(() => { disposed = true; generation++; clearTimeout(timer); document.removeEventListener('visibilitychange', visibility) })
  return { claim, refreshing, refreshError, refresh }
}

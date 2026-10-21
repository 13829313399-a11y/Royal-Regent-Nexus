import { ref, watch } from 'vue'
import { http } from '@/lib/http'
import { getAuthenticationGeneration } from '@/lib/authenticationGeneration'

// Read projections refresh independently of mounted editors and their drafts.
const revision = ref(0)
export function invalidateCuttingWorkspace() { revision.value++ }
export function watchCuttingWorkspace(refresh: () => void) {
  return watch(revision, refresh)
}
export function trackCuttingWrites() {
  const id = http.interceptors.response.use(response => {
    const { method, url = '', authenticationGeneration } = response.config
    const isWrite = ['post', 'put', 'delete', 'patch'].includes(method?.toLowerCase() ?? '')
    const queryOnly = /[/-](?:preview|download|basis)$/.test(url) || url.includes('/cutover/')
    const abandoned = url.endsWith('/recover') && response.data?.state !== 'committed'
    if (isWrite && url.startsWith('/cutting-operations/') && !queryOnly && !abandoned &&
        authenticationGeneration === getAuthenticationGeneration()) invalidateCuttingWorkspace()
    return response
  })
  return () => http.interceptors.response.eject(id)
}

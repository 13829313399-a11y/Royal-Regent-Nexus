import type { Pinia } from 'pinia'
import type { Router } from 'vue-router'
import { setForbiddenHandler, setUnauthorizedHandler } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'
import { getAuthenticationGeneration } from '@/lib/authenticationGeneration'

function isSessionProbeRequest(error: { config?: { url?: unknown } }) {
  const requestUrl = error.config?.url
  if (typeof requestUrl !== 'string') {
    return false
  }

  const requestPath = requestUrl.split('?')[0]
  return requestPath === '/auth/me' || requestPath.endsWith('/auth/me')
    || /\/auth\/(login|register|password-reset-requests|password-reset-claim)(\/|$)/.test(requestPath)
}

export function installUnauthorizedSessionHandler(router: Router, pinia: Pinia) {
  let redirectingToLogin = false
  let refreshing: Promise<unknown> | null = null
  let refreshingOwner = ''

  setUnauthorizedHandler((error) => {
    const currentRoute = router.currentRoute.value
    if (
      currentRoute.name === 'login'
      || currentRoute.meta.requiresAuth === false
      || redirectingToLogin
      || isSessionProbeRequest(error)
    ) {
      return
    }

    const authStore = useAuthStore(pinia)
    authStore.clearSession()

    redirectingToLogin = true
    const redirect = currentRoute.fullPath && currentRoute.fullPath !== '/login' ? currentRoute.fullPath : '/'

    void router
      .replace({
        name: 'login',
        query: { redirect },
      })
      .finally(() => {
        redirectingToLogin = false
      })
  })

  setForbiddenHandler((error) => {
    if (isSessionProbeRequest(error)) return
    const detail = (error as { response?: { data?: { detail?: { code?: string } } } }).response?.data?.detail
    if (detail?.code === 'COLLABORATION_INELIGIBLE') return
    const authStore = useAuthStore(pinia)
    if (authStore.isAuthenticated) {
      const owner = `${getAuthenticationGeneration()}:${authStore.currentUser?.id ?? ''}:${authStore.currentUser?.identity?.employment_epoch ?? 0}`
      if (refreshing && refreshingOwner === owner) return
      refreshingOwner = owner
      const request = authStore.refreshSession()
      refreshing = request
      void request.finally(() => { if (refreshing === request) refreshing = null })
    }
  })
}

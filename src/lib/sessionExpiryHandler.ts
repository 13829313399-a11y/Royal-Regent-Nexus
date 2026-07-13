import type { Pinia } from 'pinia'
import type { Router } from 'vue-router'
import { setForbiddenHandler, setUnauthorizedHandler } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'

function isSessionProbeRequest(error: { config?: { url?: unknown } }) {
  const requestUrl = error.config?.url
  if (typeof requestUrl !== 'string') {
    return false
  }

  const requestPath = requestUrl.split('?')[0]
  return requestPath === '/auth/me' || requestPath.endsWith('/auth/me')
}

export function installUnauthorizedSessionHandler(router: Router, pinia: Pinia) {
  let redirectingToLogin = false

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
    const authStore = useAuthStore(pinia)
    if (authStore.isAuthenticated) {
      void authStore.refreshSession()
    }
  })
}

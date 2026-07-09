import type { Pinia } from 'pinia'
import type { Router } from 'vue-router'
import { setUnauthorizedHandler } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'

export function installUnauthorizedSessionHandler(router: Router, pinia: Pinia) {
  let redirectingToLogin = false

  setUnauthorizedHandler(() => {
    const authStore = useAuthStore(pinia)
    authStore.clearSession()

    const currentRoute = router.currentRoute.value
    if (currentRoute.name === 'login' || redirectingToLogin) {
      return
    }

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
}

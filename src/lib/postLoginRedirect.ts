import type { Router } from 'vue-router'

const DASHBOARD_PATH = '/'

export function resolvePostLoginRedirect(router: Router, redirect: unknown) {
  if (
    typeof redirect !== 'string'
    || !redirect.startsWith('/')
    || redirect.startsWith('//')
    || redirect.startsWith('/\\')
  ) {
    return DASHBOARD_PATH
  }

  const destination = router.resolve(redirect)
  return destination.meta.requiresAuth === false ? DASHBOARD_PATH : destination.fullPath
}

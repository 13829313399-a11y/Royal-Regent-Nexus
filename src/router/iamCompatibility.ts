import type { RouteLocationNormalized } from 'vue-router'
export function legacyIamAccountTarget(
  to: Pick<RouteLocationNormalized, 'query' | 'hash'>,
  enabled: boolean,
) {
  if (!enabled || typeof to.query.person === 'string') return
  const oldTab =
    typeof to.query.tab === 'string' &&
    ['users', 'password-reset', 'pending'].includes(to.query.tab)
  if (oldTab || (!to.query.tab && typeof to.query.request_id === 'string'))
    return { path: '/system/users/registration', query: to.query, hash: to.hash, replace: true }
}

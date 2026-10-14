import type { RouteLocationNormalized } from 'vue-router'
import type { LocationQueryRaw } from 'vue-router'

const single = (value: unknown) => typeof value === 'string' ? value : undefined
const safeId = (value: string | undefined) => value && /^[\p{L}\p{N}_.-]{1,160}$/u.test(value) ? value : undefined
const taskPattern = /^(position|registration|password-reset|identity-change):[\p{L}\p{N}_.-]{1,160}$/u
/** A pure compatibility adapter. No lookup, draft creation or authority inference. */
export function consolidatedIamTarget(
  to: Pick<RouteLocationNormalized, 'path' | 'query' | 'hash'>,
  enabled: boolean,
) {
  if (!enabled || !/^\/system\/(users(?:\/|$)|iam\/(?:roles|permissions|requests|audit)$)/.test(to.path)) return
  const input = to.query
  if (input.route_error) return
  const fail = (code: string) => ({ path: '/system/users', query: { route_error: code }, replace: true as const })
  for (const name of ['task', 'item', 'person', 'request_id', 'panel', 'source', 'view', 'tab'])
    if (Array.isArray(input[name])) return fail('ambiguous')
  const task = single(input.task), item = single(input.item), person = single(input.person), request = single(input.request_id)
  if ((task && !taskPattern.test(task)) || (item && !taskPattern.test(item)) ||
      (person && !safeId(person)) || (request && !safeId(request))) return fail('invalid')
  const access = to.path.match(/^\/system\/users\/([^/]+)\/access$/)
  if (access && !safeId(access[1])) return fail('invalid')
  let targetTask = task || item
  if (task && item && task !== item) return fail('conflict')
  if (request) {
    const kind = input.tab === 'password-reset' ? 'password-reset' : to.path.endsWith('/requests') ? 'identity-change' : 'registration'
    const requestedTask = `${kind}:${request}`
    if (targetTask && targetTask !== requestedTask) return fail('conflict')
    targetTask = requestedTask
  }
  if (targetTask && (person || access)) return fail('conflict')
  if (access && person && access[1] !== person) return fail('conflict')
  const query: LocationQueryRaw = {}
  // Search text can include personal information: keep it in component memory, not the URL.
  for (const key of ['factory', 'org', 'kind', 'state', 'page', 'limit', 'from_at', 'to_at']) {
    const value = single(input[key])
    if (value && value.length <= 160 && !/[<>\r\n]/.test(value)) query[key] = value
  }
  let path = to.path
  if (path.endsWith('/permissions') || input.tab === 'packages') path = '/system/iam/roles'
  else if (path.endsWith('/requests') && !targetTask || input.tab === 'history') {
    path = '/system/iam/audit'
    query.source = input.tab === 'history' ? 'position' : 'identity-change'
  }
  if (path === '/system/iam/roles') {
    if (safeId(single(input.role))) query.role = single(input.role)
  } else if (path === '/system/iam/audit') {
    const source = single(input.source) || single(query.source)
    if (source && !['position', 'registration', 'password-reset', 'identity-change', 'audit'].includes(source)) return fail('invalid')
    if (source) query.source = source
    if (person) query.person = person
    if (targetTask) query.task = targetTask
  } else {
    path = '/system/users'
    const personId = access?.[1] || person
    const isPeople = !!personId || ['people', 'users'].includes(single(input.tab) || '') || input.view === 'people' || to.path.endsWith('/advanced')
    query.view = targetTask ? 'todo' : isPeople ? 'people' : 'todo'
    if (personId) {
      query.person = personId
      const panel = access ? 'exceptions' : to.path.endsWith('/advanced') ? 'advanced' : single(input.panel) || 'profile'
      if (!['profile', 'exceptions', 'account', 'advanced'].includes(panel)) return fail('invalid')
      query.panel = panel
    }
    if (targetTask) query.task = targetTask
    if (input.tab === 'password-reset') query.kind = 'password-reset'
  }
  const same = path === to.path && Object.keys(input).length === Object.keys(query).length && Object.entries(query).every(([k, v]) => input[k] === v)
  if (!same) return { path, query, hash: to.hash, replace: true as const }
}
export function legacyIamAccountTarget(
  to: Pick<RouteLocationNormalized, 'query' | 'hash'>,
  enabled: boolean,
  positionWorkbench = false,
) {
  if (!enabled || typeof to.query.person === 'string') return
  if (positionWorkbench && to.query.tab !== 'password-reset' && to.query.tab !== 'users') return
  const oldTab =
    typeof to.query.tab === 'string' &&
    ['users', 'password-reset', 'pending'].includes(to.query.tab)
  if (oldTab || (!to.query.tab && typeof to.query.request_id === 'string'))
    return { path: '/system/users/registration', query: to.query, hash: to.hash, replace: true }
}

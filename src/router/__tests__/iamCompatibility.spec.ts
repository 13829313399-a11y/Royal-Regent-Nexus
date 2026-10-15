import { expect, it, vi } from 'vitest'
import { legacyIamAccountTarget } from '../iamCompatibility'
it.each([
  { tab: 'users' },
  { tab: 'password-reset', request_id: 'r' },
  { tab: 'pending' },
  { request_id: 'r' },
])('moves the old account deep link without losing parameters: %j', (query) => {
  expect(
    legacyIamAccountTarget({ query: { ...query, factory: 'f' }, hash: '#request' }, true),
  ).toEqual({
    path: '/system/users/registration',
    query: { ...query, factory: 'f' },
    hash: '#request',
    replace: true,
  })
})
it('keeps person links, unknown parameters and the disabled flag on the original path', () => {
  for (const query of [{ person: 'p', tab: 'users' }, { tab: 'unknown' }, { q: 'name' }, {}])
    expect(legacyIamAccountTarget({ query, hash: '' }, true)).toBeUndefined()
  expect(legacyIamAccountTarget({ query: { tab: 'users' }, hash: '' }, false)).toBeUndefined()
})
it('keeps new workbench deep links and preserves old password and account tabs', () => {
  for (const query of [{ tab: 'pending', item: 'position:p' }, { tab: 'history' }, { request_id: 'r' }])
    expect(legacyIamAccountTarget({ query, hash: '' }, true, true)).toBeUndefined()
  expect(legacyIamAccountTarget({ query: { tab: 'password-reset', request_id: 'r' }, hash: '' }, true, true)?.path).toBe('/system/users/registration')
})
it.each([['', false], ['false', false], ['true', true]])('requires explicit position UI activation: %s', async (value, enabled) => {
  vi.resetModules()
  vi.stubEnv('VITE_POSITION_WORKBENCH_ENABLED', value)
  try {
    const { positionWorkbenchEnabled } = await import('@/components/iam/workspace/iam-navigation')
    expect(positionWorkbenchEnabled).toBe(enabled)
  } finally {
    vi.unstubAllEnvs()
    vi.resetModules()
  }
})

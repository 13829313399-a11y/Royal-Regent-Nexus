import { expect, it } from 'vitest'
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

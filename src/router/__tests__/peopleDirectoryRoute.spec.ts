import { describe, expect, it } from 'vitest'
import { router } from '@/router'

describe('people directory route', () => {
  it('is available to every authenticated session without a business permission gate', () => {
    const route = router.getRoutes().find((item) => item.name === 'people-directory')
    expect(route?.path).toBe('/people')
    expect(route?.meta).toMatchObject({ title: '成员目录', requiresAuth: true })
    expect(route?.meta.permissions).toBeUndefined()
    expect(route?.meta.enforcePermissions).toBeUndefined()
  })
})

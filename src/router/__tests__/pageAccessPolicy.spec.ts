import { describe, expect, it, vi } from 'vitest'
import {
  hasRoutePermissions,
  pageAccessPolicy,
  shouldEnforcePagePermissions,
  shouldRedirectForbiddenPageToHome,
  shouldShowPageNavigation,
  type PageAccessPolicy,
} from '@/config/pageAccessPolicy'

const protectedRouteMeta = {
  requiresAuth: true,
  enforcePermissions: true,
  permissions: ['system:user_manage'],
}

describe('global authenticated page access policy', () => {
  it('checks each permitted department within the same factory and does not change the single-department default', () => {
    const can = vi.fn((_permissions: string[], factory?: string, department?: string) => factory === 'huaxing' && department === 'pmc-warehouse')
    const meta = { permissionFactoryId: 'huaxing', permissionDepartments: ['sales-business', 'pmc-warehouse'] }
    expect(hasRoutePermissions(meta, ['indonesia_material:read'], can)).toBe(true)
    expect(can.mock.calls.map(call => call.slice(1))).toEqual([['huaxing', 'sales-business'], ['huaxing', 'pmc-warehouse']])
    expect(hasRoutePermissions({ ...meta, permissionFactoryId: 'huadeng' }, ['indonesia_material:read'], can)).toBe(false)
    expect(hasRoutePermissions({ permissionDepartment: 'sales-business' }, ['indonesia_material:read'], can)).toBe(false)
    expect(hasRoutePermissions({ permissionDepartments: [] }, ['indonesia_material:read'], can)).toBe(false)
  })
  it('currently allows logged-in users to enter protected pages and see their navigation', () => {
    const can = vi.fn(() => false)

    expect(pageAccessPolicy.allowAuthenticatedReadOnlyAccess).toBe(true)
    expect(shouldEnforcePagePermissions(protectedRouteMeta)).toBe(false)
    expect(shouldShowPageNavigation(['system:user_manage'], can)).toBe(true)
    expect(shouldRedirectForbiddenPageToHome()).toBe(true)
    expect(can).not.toHaveBeenCalled()
  })

  it('can restore the previous page-level permission gate through one policy switch', () => {
    const restrictedPolicy: Readonly<PageAccessPolicy> = {
      allowAuthenticatedReadOnlyAccess: false,
    }

    expect(shouldEnforcePagePermissions(protectedRouteMeta, restrictedPolicy)).toBe(true)
    expect(shouldEnforcePagePermissions({
      ...protectedRouteMeta,
      allowAuthenticatedReadOnly: true,
    }, restrictedPolicy)).toBe(false)
    expect(shouldShowPageNavigation(
      ['system:user_manage'],
      () => false,
      restrictedPolicy,
    )).toBe(false)
    expect(shouldRedirectForbiddenPageToHome(restrictedPolicy)).toBe(false)
  })

  it('always enforces explicitly strict safety-sensitive module routes', () => {
    expect(shouldEnforcePagePermissions({
      ...protectedRouteMeta,
      strictPermissions: true,
      permissions: ['three_d_printing:read'],
    })).toBe(true)
  })
})

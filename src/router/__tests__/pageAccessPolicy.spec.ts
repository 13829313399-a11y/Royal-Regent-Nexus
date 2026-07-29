import { describe, expect, it, vi } from 'vitest'
import {
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

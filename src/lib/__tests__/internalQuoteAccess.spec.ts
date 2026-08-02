import { describe, expect, it } from 'vitest'
import {
  canEditAllInternalQuoteSections,
  canReviewInternalQuoteSections,
  isForeignFactory,
  isInternalQuoteReadOnly,
} from '@/lib/internalQuoteAccess'

function accessChecker(options: { primaryFactory: string; canRead: boolean; canOperate: boolean }) {
  return {
    currentUser: {
      profile: {
        primary_factory_id: options.primaryFactory,
      },
    },
    can: (permission: string) => permission === 'internal_quote:read' && options.canRead,
    canAny: () => options.canOperate,
  }
}

describe('internal quote cross-section edit boundary', () => {
  function checker(allowedPermission: string) {
    return {
      currentUser: { id: 'editor', profile: { primary_factory_id: 'huaxing' } },
      can: (permission: string, factoryId?: string, department?: string) => (
        permission === allowedPermission
        && factoryId === 'huaxing'
        && department === (permission.includes('sales') ? 'sales-business' : 'engineering')
      ),
      canAny: () => false,
    }
  }

  it('allows business and engineering edit roles to fill every quote section', () => {
    expect(canEditAllInternalQuoteSections(checker('internal_quote:sales_edit'), 'huaxing')).toBe(true)
    expect(canEditAllInternalQuoteSections(checker('internal_quote:engineering_edit'), 'huaxing')).toBe(true)
  })

  it('does not promote a department-only editor to cross-section edit', () => {
    expect(canEditAllInternalQuoteSections(checker('internal_quote:molding_edit'), 'huaxing')).toBe(false)
  })
})

describe('internal quote read-only presentation boundary', () => {
  it('does not label a home-factory responsibility department as read-only when it can edit a section', () => {
    const checker = accessChecker({ primaryFactory: 'huaxing', canRead: true, canOperate: true })

    expect(isInternalQuoteReadOnly(checker, 'huaxing')).toBe(false)
    expect(isForeignFactory(checker, 'huaxing')).toBe(false)
  })

  it('labels a fixed sales user foreign quote as cross-factory read-only', () => {
    const checker = accessChecker({ primaryFactory: 'huaxing', canRead: true, canOperate: false })

    expect(isInternalQuoteReadOnly(checker, 'huadeng')).toBe(true)
    expect(isForeignFactory(checker, 'huadeng')).toBe(true)
  })

  it('distinguishes a home-factory view-only account from cross-factory read-only access', () => {
    const checker = accessChecker({ primaryFactory: 'huaxing', canRead: true, canOperate: false })

    expect(isInternalQuoteReadOnly(checker, 'huaxing')).toBe(true)
    expect(isForeignFactory(checker, 'huaxing')).toBe(false)
  })
})

describe('internal quote selected reviewer boundary', () => {
  function reviewerChecker(userId: string, allowed: boolean, selfReviewAllowed = false) {
    return {
      currentUser: { id: userId, profile: { primary_factory_id: 'huaxing' } },
      can: (permission: string, factoryId?: string, department?: string) => (
        (permission === 'internal_quote:sales_review' ? allowed : selfReviewAllowed)
        && ['internal_quote:sales_review', 'internal_quote:self_review'].includes(permission)
        && factoryId === 'huaxing'
        && department === 'sales-business'
      ),
      canAny: () => false,
    }
  }

  it('allows the selected business reviewer to review every department section', () => {
    expect(canReviewInternalQuoteSections(
      reviewerChecker('selected-reviewer', true),
      'huaxing',
      'selected-reviewer',
    )).toBe(true)
  })

  it('rejects other supervisors and selected users without sales review permission', () => {
    expect(canReviewInternalQuoteSections(
      reviewerChecker('other-supervisor', true),
      'huaxing',
      'selected-reviewer',
    )).toBe(false)
    expect(canReviewInternalQuoteSections(
      reviewerChecker('selected-reviewer', false),
      'huaxing',
      'selected-reviewer',
    )).toBe(false)
  })

  it('allows a personally authorized owner only on quotes created by that same user', () => {
    expect(canReviewInternalQuoteSections(
      reviewerChecker('independent-owner', false, true),
      'huaxing',
      'independent-owner',
      'independent-owner',
    )).toBe(true)
    expect(canReviewInternalQuoteSections(
      reviewerChecker('independent-owner', false, true),
      'huaxing',
      'independent-owner',
      'another-creator',
    )).toBe(false)
  })
})

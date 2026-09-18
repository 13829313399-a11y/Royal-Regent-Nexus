import { describe, expect, it } from 'vitest'
import {
  canEditAllInternalQuoteSections,
  canReviewInternalQuoteSections,
  canReviewWholeInternalQuote,
  canWithdrawInternalQuote,
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
      currentUser: { id: userId, profile: { primary_factory_id: 'huaxing', primary_department: 'sales-business' } },
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

  it.each(['engineer', 'selected-reviewer'])('allows the selected whole reviewer who submitted a quote created by %s', (creator) => {
    const quote = { moduleVersion: 'v3', factoryId: 'huaxing', businessOwnerId: 'selected-reviewer',
      createdById: creator, finalSubmittedById: 'selected-reviewer' }
    const checker = reviewerChecker('selected-reviewer', true, false)
    expect(canReviewWholeInternalQuote(checker, quote)).toBe(true)
    expect(canReviewWholeInternalQuote(reviewerChecker('other-reviewer', true), quote)).toBe(false)
    expect(canReviewWholeInternalQuote(reviewerChecker('selected-reviewer', false), quote)).toBe(false)
    expect(canReviewWholeInternalQuote(checker, { ...quote, factoryId: 'huadeng' })).toBe(false)
    expect(canReviewWholeInternalQuote(checker, { ...quote, moduleVersion: 'v2' })).toBe(false)
    checker.currentUser.profile.primary_department = 'engineering'
    expect(canReviewWholeInternalQuote(checker, quote)).toBe(false)
  })

  it('keeps whole-review self-only access limited to personally created quotes', () => {
    const checker = reviewerChecker('selected-reviewer', false, true)
    const quote = { moduleVersion: 'v3', factoryId: 'huaxing', businessOwnerId: 'selected-reviewer', createdById: 'engineer' }
    expect(canReviewWholeInternalQuote(checker, quote)).toBe(false)
    expect(canReviewWholeInternalQuote(checker, { ...quote, createdById: 'selected-reviewer' })).toBe(true)
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

  it.each(['engineering', 'management', 'production', '*'])('rejects %s personnel even with review or self-review access', (department) => {
    const checker = reviewerChecker('selected', true, true)
    checker.currentUser.profile.primary_department = department
    expect(canReviewInternalQuoteSections(checker, 'huaxing', 'selected', 'selected')).toBe(false)
  })

  it('requires explicit Sales membership for legacy users without a department profile', () => {
    const checker = reviewerChecker('selected', true)
    const legacy = { ...checker, currentUser: { id: 'selected', grants: [{ department: '*' }] } }
    expect(canReviewInternalQuoteSections(legacy, 'huaxing', 'selected')).toBe(false)
    legacy.currentUser.grants = [{ department: 'sales-business' }]
    expect(canReviewInternalQuoteSections(legacy, 'huaxing', 'selected')).toBe(true)
  })
})

describe('internal quote creator withdrawal boundary', () => {
  const quote = { moduleVersion: 'v3', status: 'final_pending', createdById: 'creator', factoryId: 'huaxing' }
  const checker = {
    currentUser: { id: 'creator' },
    can: (permission: string, factory?: string) => permission === 'internal_quote:create' && factory === 'huaxing',
    canAny: () => false,
  }

  it('allows the creator to withdraw before review without reviewer permission', () => {
    expect(canWithdrawInternalQuote(checker, quote)).toBe(true)
    expect(canWithdrawInternalQuote({ ...checker, currentUser: { id: 'reviewer' } }, quote)).toBe(false)
    expect(canWithdrawInternalQuote({ ...checker, can: () => false }, quote)).toBe(false)
    expect(canWithdrawInternalQuote(checker, { ...quote, factoryId: 'huadeng' })).toBe(false)
  })

  it.each(['drafting', 'fully_approved', 'released', 'exported', 'rejected', 'archived'])('does not allow withdrawal in %s', (status) => {
    expect(canWithdrawInternalQuote(checker, { ...quote, status })).toBe(false)
  })

  it('keeps the legacy section workflow unchanged', () => {
    expect(canWithdrawInternalQuote(checker, { ...quote, moduleVersion: 'v2' })).toBe(false)
  })
})

import { describe, expect, it } from 'vitest'
import {
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

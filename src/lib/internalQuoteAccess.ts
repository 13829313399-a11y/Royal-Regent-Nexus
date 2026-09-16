const internalQuoteOperatePermissions = [
  'internal_quote:create',
  'internal_quote:clone',
  'internal_quote:header_edit',
  'internal_quote:reference_manage',
  'internal_quote:engineering_edit',
  'internal_quote:engineering_review',
  'internal_quote:molding_edit',
  'internal_quote:molding_review',
  'internal_quote:painting_edit',
  'internal_quote:painting_review',
  'internal_quote:electronic_edit',
  'internal_quote:electronic_review',
  'internal_quote:sewing_edit',
  'internal_quote:sewing_review',
  'internal_quote:slush_edit',
  'internal_quote:slush_review',
  'internal_quote:assembly_edit',
  'internal_quote:assembly_review',
  'internal_quote:sales_edit',
  'internal_quote:sales_review',
  'internal_quote:final_submit',
  'internal_quote:final_approve',
  'internal_quote:export',
  'internal_quote:archive',
] as const

interface InternalQuoteAccessChecker {
  currentUser: {
    id?: string
    profile?: { primary_factory_id: string; primary_department?: string } | null
    grants?: { department: string }[]
  } | null
  can: (permission: string, factoryId?: string, department?: string) => boolean
  canAny: (permissions: string[], factoryId?: string, department?: string) => boolean
}

function isSalesQuoteReviewer(authStore: InternalQuoteAccessChecker) {
  const department = authStore.currentUser?.profile?.primary_department?.trim()
  return department
    ? department === 'sales-business'
    : Boolean(authStore.currentUser?.grants?.some((grant) => grant.department === 'sales-business'))
}

export function canReviewInternalQuoteSections(
  authStore: InternalQuoteAccessChecker,
  factoryId: string,
  businessOwnerId: string,
  createdById = '',
) {
  return Boolean(
    businessOwnerId
    && authStore.currentUser?.id === businessOwnerId
    && isSalesQuoteReviewer(authStore)
    && (
      authStore.can('internal_quote:sales_review', factoryId, 'sales-business')
      || (
        createdById === authStore.currentUser?.id
        && authStore.can('internal_quote:self_review', factoryId, 'sales-business')
      )
    ),
  )
}

export function canReviewWholeInternalQuote(
  authStore: InternalQuoteAccessChecker,
  quote: { moduleVersion: string; factoryId: string; businessOwnerId: string; createdById: string },
) {
  // Whole review follows the selected reviewer's access, including when they submitted it.
  return quote.moduleVersion === 'v3' && canReviewInternalQuoteSections(
    authStore, quote.factoryId, quote.businessOwnerId, quote.createdById,
  )
}

export function canWithdrawInternalQuote(
  authStore: InternalQuoteAccessChecker,
  quote: { moduleVersion: string; status: string; createdById: string; factoryId: string },
) {
  return Boolean(quote.createdById)
    && quote.moduleVersion === 'v3'
    && quote.status === 'final_pending'
    && quote.createdById === authStore.currentUser?.id
    && ['sales-business', 'engineering'].some((department) =>
      authStore.can('internal_quote:create', quote.factoryId, department),
    )
}

export function canEditAllInternalQuoteSections(
  authStore: InternalQuoteAccessChecker,
  factoryId: string,
) {
  return Boolean(factoryId) && (
    authStore.can('internal_quote:sales_edit', factoryId, 'sales-business')
    || authStore.can('internal_quote:engineering_edit', factoryId, 'engineering')
  )
}

export function canOperateInternalQuote(
  authStore: InternalQuoteAccessChecker,
  factoryId: string,
) {
  return Boolean(factoryId) && authStore.canAny([...internalQuoteOperatePermissions], factoryId)
}

export function isInternalQuoteReadOnly(
  authStore: InternalQuoteAccessChecker,
  factoryId: string,
) {
  return Boolean(factoryId)
    && authStore.can('internal_quote:read', factoryId)
    && !canOperateInternalQuote(authStore, factoryId)
}

export function isForeignFactory(
  authStore: InternalQuoteAccessChecker,
  factoryId: string,
) {
  const primaryFactoryId = authStore.currentUser?.profile?.primary_factory_id
  return Boolean(
    factoryId
    && primaryFactoryId
    && primaryFactoryId !== '*'
    && primaryFactoryId !== factoryId,
  )
}

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
  currentUser: { id?: string; profile?: { primary_factory_id: string } | null } | null
  can: (permission: string, factoryId?: string, department?: string) => boolean
  canAny: (permissions: string[], factoryId?: string, department?: string) => boolean
}

export function canReviewInternalQuoteSections(
  authStore: InternalQuoteAccessChecker,
  factoryId: string,
  businessOwnerId: string,
) {
  return Boolean(
    businessOwnerId
    && authStore.currentUser?.id === businessOwnerId
    && authStore.can('internal_quote:sales_review', factoryId, 'sales-business'),
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

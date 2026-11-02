import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { router } from '@/router'
import { useAuthStore } from '@/stores/auth'
import { hasRoutePermissions, shouldEnforcePagePermissions } from '@/config/pageAccessPolicy'

describe('supplier portal factory scope', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it.each(['/carton-supplier', '/carton-supplier/carton-mark'])(
    'keeps an unrelated factory deny out of %s while preserving the current deny', (path) => {
      const store = useAuthStore()
      store.hasEffectiveAccessSnapshot = true
      store.effectiveAccess = [
        { permission_code: 'carton_supplier:read', factory_id: '*', department: '*',
          effect: 'allow', allowed: true, source_type: 'user_override', source_ids: ['supplier-global'] },
        { permission_code: 'carton_supplier:read', factory_id: 'huaxing', department: '*',
          effect: 'deny', allowed: false, source_type: 'user_override', source_ids: ['other-factory'] },
      ]
      const meta = router.resolve(path).meta
      const permissions = ['carton_supplier:read']
      expect(shouldEnforcePagePermissions(meta)).toBe(true)
      expect(hasRoutePermissions(meta, permissions, store.canAny, 'huadeng')).toBe(true)
      expect(hasRoutePermissions(meta, permissions, store.canAny, 'huaxing')).toBe(false)
      expect(hasRoutePermissions(meta, permissions, store.canAny)).toBe(false)
      store.effectiveAccess.push({ permission_code: permissions[0]!, factory_id: '*', department: '*',
        effect: 'deny', allowed: false, source_type: 'user_override', source_ids: ['revoked'] })
      expect(hasRoutePermissions(meta, permissions, store.canAny, 'huadeng')).toBe(false)
    },
  )
})

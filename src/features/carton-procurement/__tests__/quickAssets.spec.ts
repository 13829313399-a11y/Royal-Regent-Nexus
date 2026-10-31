import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { canQuickAsset, suggestedContract, uploadDepartments, viewerKey } from '../quickAssets'
import { quickSession, supplierQuickSession } from '@/components/__tests__/cartonQuickAssetFixtures'

describe('quick asset departmental affordances', () => {
  beforeEach(() => setActivePinia(createPinia()))
  it.each(['sales-business', 'pmc-warehouse', 'carton'] as const)('keeps an unrestricted %s position in its actual department', department => {
    const auth = useAuthStore(); auth.applySession(quickSession([department]))
    for (const d of ['sales-business', 'pmc-warehouse', 'carton'] as const) {
      for (const action of ['read', 'manage', 'confirm'] as const) expect(canQuickAsset(auth, 'huaxing', d, action)).toBe(d === department)
    }
    expect(canQuickAsset(auth, 'huakang-a', department, 'manage')).toBe(false)
    expect(uploadDepartments(auth, 'huaxing', 'sales')).toEqual([department])
  })
  it('requires explicit internal departments even when supplier overrides are global', () => {
    const auth = useAuthStore(); auth.applySession(supplierQuickSession())
    expect(uploadDepartments(auth, 'huaxing', 'supplier')).toEqual(['supplier'])
    expect(uploadDepartments(auth, 'huaxing', 'sales')).toEqual([])
    expect(canQuickAsset(auth, 'huaxing', 'supplier', 'confirm')).toBe(false)
    expect(canQuickAsset(auth, 'ALL', 'supplier', 'manage')).toBe(false)
  })
  it('preserves explicit multi-department scopes and gives denies priority', () => {
    const auth = useAuthStore(); auth.applySession(quickSession(['sales-business', 'pmc-warehouse']))
    expect(uploadDepartments(auth, 'huaxing', 'warehouse')).toEqual(['sales-business', 'pmc-warehouse'])
    auth.effectiveAccess.push({ permission_code: 'carton_asset:manage', factory_id: 'huaxing', department: 'pmc-warehouse',
      effect: 'deny', allowed: false, source_type: 'user_override', source_ids: ['deny'] })
    expect(uploadDepartments(auth, 'huaxing', 'warehouse')).toEqual(['sales-business'])
    const old = viewerKey(auth); auth.applySession({ ...quickSession(['sales-business', 'pmc-warehouse']), effective_access: auth.effectiveAccess })
    expect(viewerKey(auth)).toBe(old)
    auth.authorizationVersion++; expect(viewerKey(auth)).not.toBe(old)
  })
  it('does not infer new grants from the profile or a pinned role lacking the permission', () => {
    const auth = useAuthStore(), session = quickSession()
    session.grants[0]!.permissions = []; session.effective_access = []; auth.applySession(session)
    expect(uploadDepartments(auth, 'huaxing', 'sales')).toEqual([])
  })
  it.each([
    ['4500222793_正唛2.jpg', true, '4500222793'], ['QUICK-1234.pdf', true, 'QUICK-1234'],
    ['IMG_20261029.jpg', true, ''], ['photo.png', true, ''],
    ['合同号：QUICK-1234\n请按附件制作', false, 'QUICK-1234'], ['CONTRACT NO: ABC-1234', false, 'ABC-1234'],
    ['合同号：ABC-1234 合同号：DEF-5678', false, ''], ['普通说明，不含合同号', false, ''],
  ])('suggests conservatively from %s', (value, filename, expected) => {
    expect(suggestedContract(value as string, filename as boolean)).toBe(expected)
  })
})

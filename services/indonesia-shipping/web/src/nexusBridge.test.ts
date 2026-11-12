import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiBase, nexusBase, publicAsset } from './deployment'
import { canManageLegacyDatabase, canManageLegacyUsers, getStoredSession, isAdminSession, saveSession, type AuthSession } from './auth/permissions'

function embedded() {
  vi.stubGlobal('document', { querySelector: () => ({ content: '/api/indonesia-shipping/huaxing/app/' }) })
}
afterEach(() => { if (nexusBase()) saveSession(null); vi.unstubAllGlobals() })

describe('Nexus deployment and session adapter', () => {
  it('keeps nested routes, APIs and all workbook assets inside the explicit factory gateway', () => {
    embedded()
    expect(nexusBase()).toBe('/api/indonesia-shipping/huaxing/app')
    expect(apiBase('./')).toBe('/api/indonesia-shipping/huaxing/app/api')
    for (const asset of ['template-customs.xlsx', 'template-customs-rri.xlsx', 'template-customs-rrm.xlsx'])
      expect(publicAsset('./', asset)).toBe(`/api/indonesia-shipping/huaxing/app/${asset}`)
  })
  it('ignores legacy stored bearer sessions and keeps Nexus identity only in memory', () => {
    embedded()
    const storage = { getItem: vi.fn(() => JSON.stringify({ token: 'legacy-bearer' })), setItem: vi.fn(), removeItem: vi.fn() }
    vi.stubGlobal('localStorage', storage)
    expect(getStoredSession()).toBeNull()
    const session = { nexus: true, identity: 'id', displayName: '测试', userbqrpower: '000000001', usereditpower: '000000000' } as AuthSession
    saveSession(session)
    expect(getStoredSession()).toEqual(session)
    expect(storage.getItem).not.toHaveBeenCalled()
    expect(storage.setItem).not.toHaveBeenCalled()
    saveSession(null)
    expect(getStoredSession()).toBeNull()
  })
  it('does not infer Nexus administration from all business bits', () => {
    const session = { nexus: true, token: '', displayName: '测试', userbqrpower: '111111111', usereditpower: '111111111' }
    expect(isAdminSession(session)).toBe(false)
    const stale = { ...session, usersManage: true }
    expect(isAdminSession(stale)).toBe(false)
    expect(canManageLegacyUsers(stale)).toBe(false)
    expect(canManageLegacyUsers({ ...session, databaseManage: true })).toBe(false)
    expect(isAdminSession({ ...session, databaseManage: true })).toBe(false)
    expect(canManageLegacyDatabase({ ...session, databaseManage: true })).toBe(false)
    expect(canManageLegacyUsers({ ...session, nexus: false })).toBe(true)
    expect(canManageLegacyDatabase({ ...session, nexus: false })).toBe(true)
  })
  it('cannot restore database administration with legacy session fields on an embedded deployment', () => {
    embedded()
    const session = { token: '', displayName: '测试', databaseManage: true, userbqrpower: '111111111', usereditpower: '111111111' }
    expect(isAdminSession(session)).toBe(false)
    expect(canManageLegacyDatabase(session)).toBe(false)
  })
})

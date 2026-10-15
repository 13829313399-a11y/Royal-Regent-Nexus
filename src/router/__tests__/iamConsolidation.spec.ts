import { expect, it, vi } from 'vitest'
import type { LocationQuery } from 'vue-router'
import { consolidatedIamTarget } from '../iamCompatibility'
import { workspaceCapabilities } from '@/features/identity-management/workspace/contracts'
const normalize = (url: string, enabled = true) => {
  const parsed = new URL(url, 'http://localhost')
  const query: LocationQuery = {}
  for (const [key,value] of parsed.searchParams) query[key] = query[key] ? [String(query[key]), value] : value
  const result = consolidatedIamTarget({path: parsed.pathname, query, hash: parsed.hash}, enabled)
  return result || { path: parsed.pathname, query }
}
it.each([
  ['/system/users?person=P', '/system/users', {view:'people',person:'P',panel:'profile'}],
  ['/system/users?person=P&panel=manage', '/system/users', {view:'people',person:'P',panel:'manage'}],
  ['/system/users?tab=people', '/system/users', {view:'people'}],
  ['/system/users?tab=users', '/system/users', {view:'people'}],
  ['/system/users/position-reviews?item=position:R', '/system/users', {view:'todo',task:'position:R'}],
  ['/system/users/registration?tab=password-reset&request_id=R', '/system/users', {view:'todo',task:'password-reset:R',kind:'password-reset'}],
  ['/system/users/registration?request_id=R', '/system/users', {view:'todo',task:'registration:R'}],
  ['/system/users/P/access', '/system/users', {view:'people',person:'P',panel:'exceptions'}],
  ['/system/users/advanced?person=P', '/system/users', {view:'people',person:'P',panel:'advanced'}],
  ['/system/iam/requests', '/system/iam/audit', {source:'identity-change'}],
  ['/system/users?tab=history&item=registration:R', '/system/iam/audit', {source:'position',task:'registration:R'}],
  ['/system/iam/audit', '/system/iam/audit', {}],
  ['/system/iam/roles', '/system/iam/roles', {}],
  ['/system/users?tab=packages', '/system/iam/roles', {}],
])('normalizes %s and remains stable on refresh', (input,path,query) => {
  expect(normalize(input)).toMatchObject({path,query})
  const canonical = `${path}?${new URLSearchParams(query as Record<string,string>)}`
  expect(normalize(canonical)).toMatchObject({path,query})
  expect(consolidatedIamTarget({ path,query,hash:'' }, true)).toBeUndefined()
})
it.each(['?task=position:A&item=registration:B','?task=position:A&person=B','?task=position:A&request_id=B','?task=unknown:R','?person=a&person=b','?person=../a'])('rejects ambiguous or malformed targets %s', query => {
  expect(normalize('/system/users'+query).query).toHaveProperty('route_error')
})
it('retains legacy entry points when consolidation is disabled', () => {
  const input='/system/users/registration?tab=password-reset&request_id=R'
  expect(normalize(input,false)).toEqual({path:'/system/users/registration',query:{tab:'password-reset',request_id:'R'}})
})
it.each(['system:user_manage','system:access_manage','system:permission_catalog_read','system:audit_read'])('keeps %s independent', permission => {
  const caps=workspaceCapabilities(p=>p===permission)
  expect(Object.values(caps).filter(Boolean)).toHaveLength(1)
})
it.each([
  ['true','true','true',true],['false','true','true',false],['','true','true',false],['true','false','true',false],['true','true','false',false],
])('gates consolidation with all prerequisite flags %s %s %s', async (merged,identity,position,expected) => {
  vi.resetModules(); vi.stubEnv('VITE_IAM_CONSOLIDATED_UI_ENABLED',merged);vi.stubEnv('VITE_IAM_IDENTITY_UI_ENABLED',identity);vi.stubEnv('VITE_POSITION_WORKBENCH_ENABLED',position)
  try { expect((await import('@/components/iam/workspace/iam-navigation')).consolidatedIamEnabled).toBe(expected) }
  finally {vi.unstubAllEnvs();vi.resetModules()}
})

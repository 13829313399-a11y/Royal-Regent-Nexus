import { describe,expect,it,beforeEach } from 'vitest'
import { createPinia,setActivePinia } from 'pinia'
import { ContextFence } from '../contracts'
import { pasteQuantities,quantityError } from '../reconciliation'
import { useAuthStore } from '@/stores/auth'
import type { AuthMeResponse } from '@/api/auth'
describe('UV acceptance contracts',()=>{
  beforeEach(()=>setActivePinia(createPinia()))
  it('rejects late completions after identity or factory changes',()=>{const fence=new ContextFence();const old=fence.begin();fence.clear();const current=fence.begin();expect(old.controller.signal.aborted).toBe(true);expect(fence.current(old)).toBe(false);expect(fence.current(current)).toBe(true)})
  it('previews spreadsheet rows and never coerces a missing quantity into zero',()=>{const rows=pasteQuantities('120\t114\t6\t0\t0\n10\t9\t0\t0\t0\n5\t5\t\t0\t0');expect(rows[0]?.error).toBe('');expect(rows[1]?.error).toContain('不一致');expect(rows[2]?.error).toContain('整数');expect(quantityError({processed:1,good:1.1,rework:0,scrap:0,pending:0})).toContain('整数')})
  it.each(['legacy','shadow','enforce'] as const)('requires canonical scoped decisions even in %s mode',mode=>{
    const store=useAuthStore();const session:AuthMeResponse={id:'qa',username:'qa',display_name:'Synthetic',roles:['admin'],permissions:['uv_ops:read'],factory_scopes:['*'],department_scopes:['*'],grants:[{role_id:'admin',role_code:'admin',role_name:'admin',factory_id:'*',department:'*',permissions:['uv_ops:read']}],authz_mode:mode,force_password_change:false}
    store.applySession(session);expect(store.can('uv_ops:read','huakang-a','production')).toBe(false)
    store.applySession({...session,effective_access:[{permission_code:'uv_ops:read',factory_id:'huakang-a',department:'production',effect:'allow',allowed:true,source_type:'role_binding',source_ids:['qa']}]})
    expect(store.can('uv_ops:read','huakang-a','production')).toBe(true)
    for(const factory of ['group','huakang-b','huaxing',undefined])expect(store.can('uv_ops:read',factory,'production')).toBe(false)
    expect(store.can('uv_ops:read','huakang-a','qa')).toBe(false)
    store.effectiveAccess.push({permission_code:'uv_ops:read',factory_id:'huakang-a',department:'production',effect:'deny',allowed:false,source_type:'user_override',source_ids:['deny']})
    expect(store.can('uv_ops:read','huakang-a','production')).toBe(false)
  })
})

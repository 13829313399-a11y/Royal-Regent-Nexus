import { effectScope, nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import type { AxiosResponse } from 'axios'
const callbacks=vi.hoisted(()=>({handler:undefined as undefined|((r:AxiosResponse)=>AxiosResponse),eject:vi.fn()}))
vi.mock('@/lib/http',()=>({http:{interceptors:{response:{
  use:(handler:(r:AxiosResponse)=>AxiosResponse)=>{callbacks.handler=handler;return 7},
  eject:callbacks.eject,
}}}}))
vi.mock('@/lib/authenticationGeneration',()=>({getAuthenticationGeneration:()=>4}))
import { trackCuttingWrites, watchCuttingWorkspace } from '../workspaceRefresh'

describe('cutting successful-write refresh',()=>{
  it('refreshes consumers only for confirmed writes in the current session',async()=>{
    const scope=effectScope(),refresh=vi.fn()
    scope.run(()=>watchCuttingWorkspace(refresh))
    const stop=trackCuttingWrites()
    const response=(url:string,data:unknown={},method='post',authenticationGeneration=4)=>({config:{url,method,authenticationGeneration},data}) as AxiosResponse
    callbacks.handler!(response('/cutting-operations/orders/line/usage/post'))
    await nextTick();expect(refresh).toHaveBeenCalledTimes(1)
    for(const r of [
      response('/cutting-operations/exports/preview'),
      response('/cutting-operations/payment-preview'),
      response('/cutting-operations/settlement-preview'),
      response('/cutting-operations/orders/line/usage-operations/recover',{state:'abandoned'}),
      response('/cutting-operations/orders/line/reports/post',{},'post',3),
      response('/cutting-operations/workspace/inventory',{},'get'),
      response('/other-module/save'),
    ])callbacks.handler!(r)
    await nextTick();expect(refresh).toHaveBeenCalledTimes(1)
    callbacks.handler!(response('/cutting-operations/orders/line/usage-operations/recover',{state:'committed'}))
    await nextTick();expect(refresh).toHaveBeenCalledTimes(2)
    stop();expect(callbacks.eject).toHaveBeenCalledWith(7)
    scope.stop()
  })
})

import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import AssistantConnection from '../AssistantConnection.vue'
import { assistantApi } from '../api'
import type { Capabilities } from '../types'

afterEach(() => vi.restoreAllMocks())
const capabilities = (admin = false): Capabilities => ({enabled:true,configuration_status:'configured',schema_status:'ready',
  connection_status:'verified',verified_at:'2020-01-01',provider:'synthetic',model:'synthetic',help_status:'ready',profiles:[],
  diagnostics_available:admin,status_label:'模型已配置',search:{configured:true,verification:'verified',verified_at:'2020-01-01',supported_modes:['off','auto'],
    supported_protocols:['dashscope_multimodal'],verified_combinations:[],source_return:true,inline_citations:true,page_fetch:false,last_result:null,last_success:null,last_failure:null}})
describe('connection diagnostics', () => {
  it('separates historical verification from execution and hides admin details', () => {
    const w = mount(AssistantConnection, {props:{capabilities:capabilities()}})
    expect(w.text()).toContain('历史验证不代表实时健康')
    expect(w.text()).toContain('暂无本人的执行记录')
    expect(w.find('button').exists()).toBe(false)
    w.unmount()
  })
  it('discards in-flight administrator metadata when access changes', async () => {
    let resolve!: (v:Record<string,unknown>) => void
    vi.spyOn(assistantApi,'diagnostics').mockReturnValue(new Promise(r => { resolve=r }))
    const w = mount(AssistantConnection, {props:{capabilities:capabilities(true)}})
    await w.get('button').trigger('click')
    await w.setProps({capabilities:capabilities(false)})
    resolve({process_id:12345}); await flushPromises()
    expect(w.find('pre').exists()).toBe(false)
    w.unmount()
  })
})

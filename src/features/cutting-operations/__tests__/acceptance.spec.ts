import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import Notice from '../CuttingAcceptanceNotice.vue'
import { acceptanceSamples } from '../acceptanceSamples'
afterEach(()=>{vi.unstubAllEnvs();vi.unstubAllGlobals()})
const router=createRouter({history:createMemoryHistory(),routes:[{path:'/:pathMatch(.*)*',component:{template:'<div />'}}]})
describe('isolated acceptance navigation',()=>{
  it('does not fetch or display local metadata in a normal build or on the login notice',async()=>{
    const fetch=vi.fn();vi.stubGlobal('fetch',fetch);vi.stubEnv('VITE_CUTTING_ACCEPTANCE_RELEASE','')
    const normal=mount(Notice,{props:{showSamples:true}});await flushPromises()
    expect(normal.find('aside').exists()).toBe(false);expect(fetch).not.toHaveBeenCalled();normal.unmount()
    vi.stubEnv('VITE_CUTTING_ACCEPTANCE_RELEASE','test-release')
    const login=mount(Notice);await flushPromises()
    expect(login.text()).toContain('数据库副本');expect(login.find('details').exists()).toBe(false);expect(fetch).not.toHaveBeenCalled();login.unmount()
  })
  it('retries metadata failure, links explicit sample dates and clears navigation when access is hidden',async()=>{
    vi.stubEnv('VITE_CUTTING_ACCEPTANCE_RELEASE','test-release')
    const fetch=vi.fn().mockRejectedValueOnce(new Error('暂时无法读取')).mockResolvedValue({ok:true,json:async()=>({release:'test-release',links:[{label:'样本日看板',workspace:'dashboard',day:'2026-10-21'}]})})
    vi.stubGlobal('fetch',fetch)
    const view=mount(Notice,{props:{showSamples:true},global:{plugins:[router]}});await flushPromises()
    expect(view.text()).toContain('暂时无法读取');await view.get('button').trigger('click');await flushPromises()
    expect(view.get('a').attributes('href')).toContain('day=2026-10-21')
    expect(fetch).toHaveBeenLastCalledWith('/cutting-acceptance-samples.json',expect.objectContaining({credentials:'omit',cache:'no-store'}))
    await view.setProps({showSamples:false});expect(view.find('a').exists()).toBe(false);view.unmount()
  })
  it('rejects mismatched releases, arbitrary destinations, repeated query values and invalid calendar dates',()=>{
    const value=(row:object,release='r')=>({release,links:[{label:'合成样本',workspace:'closing',...row}]})
    expect(()=>acceptanceSamples(value({},'old'),'r')).toThrow()
    expect(()=>acceptanceSamples(value({workspace:'https://example.com'}),'r')).toThrow()
    expect(()=>acceptanceSamples(value({day:'2026-02-30'}),'r')).toThrow()
    expect(()=>acceptanceSamples(value({month:['2026-09']}),'r')).toThrow()
  })
})

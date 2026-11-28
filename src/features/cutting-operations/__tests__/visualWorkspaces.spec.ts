import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import Card from '../CuttingVisualCard.vue'
import Views from '../CuttingWorkViews.vue'
import { CUTTING_MAIN_WORKSPACES, cuttingMainWorkspace, CUTTING_BASE } from '../navigation'
import { cuttingOperationsRoutes } from '../routes'
let wrapper:VueWrapper
afterEach(()=>wrapper?.unmount())
describe('cutting visual workspace contracts',()=>{
  it('groups legacy production and material-cost links into five owning workspaces',()=>{
    expect(CUTTING_MAIN_WORKSPACES.map(w=>w.path)).toEqual(['dashboard','materials','closing','master','activity'])
    expect(cuttingMainWorkspace(`${CUTTING_BASE}/reporting`)).toBe('dashboard')
    expect(cuttingMainWorkspace(`${CUTTING_BASE}/planning`)).toBe('dashboard')
    expect(cuttingMainWorkspace(`${CUTTING_BASE}/costs`)).toBe('closing')
  })
  it('redirects legacy costs without losing order, month or cost-event version trace',async()=>{
    const router=createRouter({history:createMemoryHistory(),routes:cuttingOperationsRoutes})
    await router.push({path:`${CUTTING_BASE}/costs`,query:{factory:'huakang-c',line_id:'line-1',month:'2026-09',cost_view:'history',focus_kind:'cost_event',focus_id:'price-v2'}})
    expect(router.currentRoute.value.path).toBe(`${CUTTING_BASE}/closing`)
    expect(router.currentRoute.value.query).toMatchObject({factory:'huakang-c',view:'costs',line_id:'line-1',month:'2026-09',cost_view:'history',focus_id:'price-v2'})
  })
  it('retains selected order and cutoff through production subviews and clears only order focus on returning to tasks',async()=>{
    const router=createRouter({history:createMemoryHistory(),routes:[{path:'/:pathMatch(.*)*',component:{template:'<div />'}}]})
    await router.push({path:`${CUTTING_BASE}/planning`,query:{factory:'huakang-c',line_id:'line-1',day:'2026-10-18',task_day:'2026-10-15',month:'2026-10',focus_kind:'task',focus_id:'task-2'}})
    wrapper=mount(Views,{props:{active:'planning'},global:{plugins:[router]}});await flushPromises()
    await wrapper.findAll('a')[2]!.trigger('click');await flushPromises()
    expect(router.currentRoute.value.query).toMatchObject({line_id:'line-1',day:'2026-10-18',task_day:'2026-10-15',focus_id:'task-2',reporting_view:'records'})
    await wrapper.findAll('a')[0]!.trigger('click');await flushPromises()
    expect(router.currentRoute.value.query).toMatchObject({factory:'huakang-c',day:'2026-10-15'})
    expect(router.currentRoute.value.query.line_id).toBeUndefined()
    expect(router.currentRoute.value.query.focus_id).toBeUndefined()
  })
  it('keeps unknown progress absent and exposes a real detail action',async()=>{
    wrapper=mount(Card,{props:{title:'缺少核定依据',value:'待核定'}})
    expect(wrapper.find('[role="meter"]').exists()).toBe(false)
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('detail')).toHaveLength(1)
  })
  it('keeps overproduction in text and bounds the visual meter without changing the value',()=>{
    wrapper=mount(Card,{props:{title:'完成',value:'120 / 100',progress:120}})
    expect(wrapper.text()).toContain('120 / 100')
    expect(wrapper.get('[role="meter"]').attributes('aria-valuenow')).toBe('100')
  })
  it('does not emit detail for unavailable financial domains',async()=>{
    wrapper=mount(Card,{props:{title:'付款核销',unavailable:true}})
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('detail')).toBeUndefined()
  })
})

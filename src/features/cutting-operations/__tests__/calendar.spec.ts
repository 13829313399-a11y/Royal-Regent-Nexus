import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import CuttingCalendarEditor from '../CuttingCalendarEditor.vue'
import type { WorkCalendarData } from '../api'
import { taskInput, type PlanTask, type PlanTaskInput } from '../planning'
import CuttingPlanSummary from '../CuttingPlanSummary.vue'
import CuttingPlanEditor from '../CuttingPlanEditor.vue'
import type { OrderData } from '../ordersApi'
import { cuttingApi, type MasterRecord } from '../api'
describe('resource calendar configuration', () => {
  it('starts with explicit fallback and keeps exception dates in the resource draft', async () => {
    const wrapper = mount(defineComponent({ components: { CuttingCalendarEditor }, setup() { return { cal: ref<WorkCalendarData | null>(null) } }, template: '<CuttingCalendarEditor v-model="cal" />' }))
    expect(wrapper.text()).toContain('默认周一至周六工作、周日休息')
    await wrapper.get('button').trigger('click')
    expect(wrapper.findAll('input[type="checkbox"]').filter(i => (i.element as HTMLInputElement).checked)).toHaveLength(6)
    await wrapper.findAll('button').find(b => b.text() === '增加休息／调休／加班日期')!.trigger('click')
    await wrapper.get('input[type="date"]').setValue('2026-10-18')
    await wrapper.get('select').setValue('true')
    expect((wrapper.vm as unknown as { cal: WorkCalendarData }).cal.exceptions[0]).toMatchObject({ day: '2026-10-18', working: true })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await wrapper.findAll('button').find(b => b.text() === '清除资源日历')!.trigger('click')
    expect(wrapper.find('input[type="date"]').exists()).toBe(true)
    confirm.mockReturnValue(true)
    await wrapper.findAll('button').find(b => b.text() === '清除资源日历')!.trigger('click')
    expect(wrapper.text()).toContain('尚未配置')
    confirm.mockRestore(); wrapper.unmount()
  })
})


it('keeps historical expected issue dates separate from actual evidence', () => {
  const legacy = { task_id: 'old', name: '旧任务', resource_id: 'r1', resource_version: 1, resource: { data: { name: '旧资源' } }, target_sets: 50, materials: [], readiness_basis: '旧预计', expected_issue_date: '2026-10-12', prerequisite_date: null, prerequisite_basis: '', days: [], planned_sets: 0, unplanned_sets: 50 } as unknown as PlanTask
  const input=taskInput(legacy)
  expect(input.actual_issue_date).toBeNull()
  expect(input.actual_issue_reference).toBe('')
  expect(input).not.toHaveProperty('expected_issue_date')
  expect(input.preparation_workdays).toBe(3)
  const wrapper=mount(CuttingPlanSummary,{ props:{ title:'历史',plan:{version:1,tasks:[legacy],allocated_sets:50,unallocated_sets:0,actor_id:'old',created_at:'',reason:'旧计划'} } })
  expect(wrapper.text()).toContain('实际领料：未登记')
  expect(wrapper.text()).toContain('历史预计领料：2026-10-12')
  wrapper.unmount()
})


it('retains prerequisite requirements independently of a cleared estimated date', () => {
  const legacy={ task_id:'old', name:'old', resource_id:'r',resource_version:1,target_sets:50,materials:[],readiness_basis:'', prerequisite_date:'2026-10-12',prerequisite_basis:'贴合',days:[] } as unknown as PlanTask
  const input=taskInput(legacy)
  expect(input.prerequisite_required).toBe(true)
  input.prerequisite_date=null
  expect(input.prerequisite_required).toBe(true)
  expect(input.date_basis).toBe('estimated')
})

it('edits task preparation independently of date basis and preserves zero in saved input', async () => {
  const task: PlanTaskInput={ task_id:'t', name:'本厂', resource_id:'r',resource_version:1,target_sets:50,materials:[],readiness_basis:'已核对',
    preparation_workdays:3,date_basis:'estimated',actual_issue_date:null,actual_issue_reference:'',prerequisite_date:null,prerequisite_basis:'',days:[] }
  const wrapper=mount(CuttingPlanEditor,{ props:{ data:{ target_sets:50,batches:[],bom:{data:{requirements:[]}} } as unknown as OrderData,modelValue:[task] } })
  const preparation=wrapper.findAll('label').find(l => l.text().startsWith('供数准备工作日'))!.get('input')
  await preparation.setValue(0)
  expect(wrapper.text()).not.toContain('准备周期调整原因')
  await wrapper.get('select').setValue('actual')
  const input=taskInput(task)
  expect(input.preparation_workdays).toBe(0)
  expect(input.date_basis).toBe('actual')
  expect(wrapper.text()).toContain('3 个工作日为默认建议')
  wrapper.unmount()
  const summary=mount(CuttingPlanSummary,{ props:{ title:'已发布',plan:{version:2,tasks:[{...task,resource:{data:{name:'本厂'}},planned_sets:0,unplanned_sets:50}],allocated_sets:50,unallocated_sets:0,actor_id:'planner',created_at:'',reason:'调整'} as unknown as import('../planning').ProductionPlan } })
  expect(summary.text()).toContain('供数准备周期：0 个工作日')
  summary.unmount()
})

it('changes executor while keeping task identity, prerequisites and plan, and clears old actual evidence',async()=>{
  const t:PlanTaskInput={task_id:'kept',name:'原本厂任务',resource_id:'r1',resource_version:1,target_sets:50,preparation_workdays:1,prerequisite_required:true,
    materials:[],readiness_basis:'原批',actual_issue_date:'2026-10-12',actual_issue_reference:'原厂领料',prerequisite_date:'2026-10-12',prerequisite_basis:'必须贴合',actual_prerequisite_date:'2026-10-12',actual_prerequisite_reference:'原厂贴合',days:[{day:'2026-10-15',sets:50}]}
  const r={id:'r2',code:'R2',version:1,status:'active',kind:'resource',data:{name:'外发裁剪厂',execution:'outsourced',preparation_workdays:5,calendar:null}} as unknown as MasterRecord
  const search=vi.spyOn(cuttingApi,'list').mockResolvedValue({data:[r],page:1,page_size:50,total:1})
  const w=mount(CuttingPlanEditor,{props:{data:{target_sets:50,batches:[],bom:{data:{requirements:[]}}} as unknown as OrderData,modelValue:[t]}})
  await w.findAll('button').find(b=>b.text()==='查本厂／外发资源')!.trigger('click');await import('@vue/test-utils').then(m=>m.flushPromises())
  await w.findAll('button').find(b=>b.text()==='替换为：外发裁剪厂 V1')!.trigger('click')
  expect(t).toMatchObject({task_id:'kept',resource_id:'r2',prerequisite_required:true,preparation_workdays:1,date_basis:'estimated',actual_issue_date:null,actual_prerequisite_date:null,prerequisite_date:'2026-10-12',days:[{day:'2026-10-15',sets:50}]})
  search.mockRestore();w.unmount()
})

it('takes resource default preparation only for new tasks',async()=>{
  const r={id:'r',code:'R',version:1,status:'active',data:{name:'已备料组',preparation_workdays:0}} as unknown as MasterRecord
  const search=vi.spyOn(cuttingApi,'list').mockResolvedValue({data:[r],page:1,page_size:50,total:1}),tasks:PlanTaskInput[]=[]
  const w=mount(CuttingPlanEditor,{props:{data:{target_sets:50,batches:[],bom:{data:{requirements:[]}}} as unknown as OrderData,modelValue:tasks}})
  await w.findAll('button').find(b=>b.text()==='查本厂／外发资源')!.trigger('click');await import('@vue/test-utils').then(m=>m.flushPromises())
  await w.findAll('button').find(b=>b.text()==='增加任务：R · 已备料组 V1')!.trigger('click')
  expect(tasks[0]?.preparation_workdays).toBe(0)
  search.mockRestore();w.unmount()
})

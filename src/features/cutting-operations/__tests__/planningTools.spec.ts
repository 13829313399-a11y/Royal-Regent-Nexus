import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { generateDailyPlan, copyDailyPlan } from '../planningTools'
import CuttingDailyPlanTools from '../CuttingDailyPlanTools.vue'
import CuttingPlanDiff from '../CuttingPlanDiff.vue'
import type { PlanTaskInput, ProductionPlan } from '../planning'
const task = (): PlanTaskInput => ({ task_id:'t1',name:'本厂裁剪',resource_id:'r1',resource_version:1,target_sets:12,preparation_workdays:3,materials:[],readiness_basis:'核对',actual_issue_date:null,actual_issue_reference:'',prerequisite_date:null,prerequisite_basis:'',days:[] })
describe('batch daily planning',()=>{
  it('skips Sunday, respects exceptions and caps the last day to the target',()=>{
    expect(generateDailyPlan('2026-10-16','2026-10-20',5,12,null)).toEqual([{day:'2026-10-16',sets:5},{day:'2026-10-17',sets:5},{day:'2026-10-19',sets:2}])
    expect(generateDailyPlan('2026-10-17','2026-10-19',5,10,{weekdays:[1,2,3,4,5,6],basis:'测试',exceptions:[{day:'2026-10-17',working:false,reason:'休息'},{day:'2026-10-18',working:true,reason:'调休'}]})).toEqual([{day:'2026-10-18',sets:5},{day:'2026-10-19',sets:5}])
  })
  it('supports partial plans and append without duplicate dates',()=>{
    expect(generateDailyPlan('2026-10-16','2026-10-19',5,20,null,['2026-10-16'])).toEqual([{day:'2026-10-17',sets:5},{day:'2026-10-19',sets:5}])
  })
  it.each([['2026-02-30','2026-03-01',1,5],['2026-10-20','2026-10-16',1,5],['2026-01-01','2028-01-01',1,5],['2026-10-16','2026-10-20',1.5,5],['2026-10-16','2026-10-20',1,0]])('rejects invalid generation inputs', (start,end,sets,remaining)=>{
    expect(()=>generateDailyPlan(start as string,end as string,sets as number,remaining as number,null)).toThrow()
  })
  it('copies daily quantities in order using the destination calendar and target',()=>{
    expect(copyDailyPlan([{day:'2026-10-15',sets:3},{day:'2026-10-14',sets:5}],'2026-10-18',7,null)).toEqual([{day:'2026-10-19',sets:5},{day:'2026-10-20',sets:2}])
  })
  it('never mutates the task before explicit preview application, and clears stale previews',async()=>{
    const t=task(),w=mount(CuttingDailyPlanTools,{props:{task:t,calendar:null,sources:[t]}})
    const dates=w.findAll('input[type=date]')
    await dates[0]!.setValue('2026-10-16');await dates[1]!.setValue('2026-10-20');await w.get('input[type=number]').setValue(5)
    await w.findAll('button').find(b=>b.text()==='生成预览')!.trigger('click')
    expect(t.days).toEqual([]);expect(w.text()).toContain('2026-10-19：2 套')
    await w.get('input[type=number]').setValue(4)
    expect(w.text()).not.toContain('确认应用预览')
    await w.findAll('button').find(b=>b.text()==='生成预览')!.trigger('click')
    await w.findAll('button').find(b=>b.text()==='确认应用预览')!.trigger('click')
    expect(t.days).toHaveLength(3);expect(t.days.reduce((n,d)=>n+d.sets,0)).toBe(12)
    w.unmount()
  })
  it('requires confirmation before replacing existing daily entries',async()=>{
    const t=task();t.days=[{day:'2026-10-15',sets:12}]
    const w=mount(CuttingDailyPlanTools,{props:{task:t,calendar:null,sources:[t]}})
    await w.findAll('input[type=date]')[0]!.setValue('2026-10-16');await w.findAll('input[type=date]')[1]!.setValue('2026-10-20')
    await w.findAll('button').find(b=>b.text()==='生成预览')!.trigger('click')
    const confirm=vi.spyOn(window,'confirm').mockReturnValue(false)
    await w.findAll('button').find(b=>b.text()==='确认应用预览')!.trigger('click')
    expect(t.days).toEqual([{day:'2026-10-15',sets:12}]);confirm.mockRestore();w.unmount()
  })
  it('invalidates copied previews when source entries change or the source is removed',async()=>{
    const t=task(),origin={...task(),task_id:'source',name:'来源任务',days:[{day:'2026-10-15',sets:12}]}
    const w=mount(CuttingDailyPlanTools,{props:{task:t,calendar:null,sources:[origin,t]}})
    await w.findAll('input[type=date]')[0]!.setValue('2026-10-16')
    await w.findAll('select')[1]!.setValue('source')
    await w.findAll('button').find(b=>b.text()==='复制到开始日期并预览')!.trigger('click')
    expect(w.text()).toContain('确认应用预览')
    await w.setProps({sources:[{...origin,days:[{day:'2026-10-15',sets:5}]},t]})
    expect(w.text()).not.toContain('确认应用预览')
    await w.findAll('button').find(b=>b.text()==='复制到开始日期并预览')!.trigger('click')
    expect(w.text()).toContain('确认应用预览')
    await w.setProps({sources:[t]})
    expect(w.text()).not.toContain('确认应用预览');expect(t.days).toEqual([])
    w.unmount()
  })
})
it('shows changed quantities, preparation days and dates before publication',()=>{
  const previous={version:2,tasks:[{...task(),resource:{data:{name:'本厂'}},days:[{day:'2026-10-15',sets:12}]}]} as unknown as ProductionPlan
  const next={...task(),preparation_workdays:1,days:[{day:'2026-10-14',sets:12}]}
  const w=mount(CuttingPlanDiff,{props:{previous,tasks:[next]}})
  expect(w.text()).toContain('准备工作日');expect(w.text()).toContain('日计划 2026-10-14');expect(w.text()).toContain('日计划 2026-10-15');expect(w.text()).toContain('移除')
  w.unmount()
})

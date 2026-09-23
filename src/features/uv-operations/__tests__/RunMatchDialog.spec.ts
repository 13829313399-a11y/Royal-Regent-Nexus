import {describe,it,expect,vi} from 'vitest'
import {ref} from 'vue'
import {flushPromises,mount} from '@vue/test-utils'
import RunMatchDialog from '../components/RunMatchDialog.vue'
const command=vi.fn(async()=>({}))
const w={contextVersion:ref(1),load:vi.fn(async()=>{}),can:()=>true,command,explain:String,
  items:(name:string)=>name==='tasks'?[{id:'REWORK',version:1,code:'R-001',parent_task_id:'ROOT',batches:[{id:'BOUND-BATCH',task_id:'ROOT',quantity:6,version:1}]}]:[]}
vi.mock('../workspace',()=>({useUvWorkspace:()=>w,UvError:class extends Error{status=500}}))
describe('UV rework run reconciliation',()=>{
  it('offers the bound parent batch and submits the rework task allocation',async()=>{
    HTMLDialogElement.prototype.showModal=vi.fn()
    HTMLDialogElement.prototype.close=vi.fn()
    const wrapper=mount(RunMatchDialog,{props:{run:null},global:{stubs:{CollectionFooter:true}}})
    await wrapper.setProps({run:{id:'RUN',version:1,native_job_id:'SYNTHETIC'}});await flushPromises()
    const selects=wrapper.findAll('select')
    await selects[0]!.setValue('REWORK')
    expect(selects[1]!.findAll('option').map(x=>x.attributes('value'))).toEqual(['','BOUND-BATCH'])
    await selects[1]!.setValue('BOUND-BATCH')
    await wrapper.get('input[placeholder="1,2,3"]').setValue('1,2')
    await wrapper.get('textarea').setValue('合成返工运行归属核对')
    await wrapper.get('form').trigger('submit');await flushPromises()
    expect(command).toHaveBeenCalledWith('runs/RUN/match',expect.objectContaining({allocations:[expect.objectContaining({task_id:'REWORK',batch_id:'BOUND-BATCH',slots:[1,2]})]}),expect.any(String))
    expect(wrapper.emitted('saved')).toHaveLength(1)
    wrapper.unmount()
  })
})

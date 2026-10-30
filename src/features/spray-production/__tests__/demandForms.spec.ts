import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import DemandPage from '../pages/DemandPage.vue'

const w = {
  assistantView: ref<string|null>(null), dirty: ref(false), saveDraft: ref<(() => Promise<boolean>)|null>(null),
  businessDate: ref('2026-10-26'), factory: ref('huaxing'), contextVersion: ref(1), passportId: ref<string|null>(null), totals: { demands: 1 },
  can: () => true, items: vi.fn(), command: vi.fn(), load: vi.fn(), confirmDiscard: vi.fn(),
  explain: (error: unknown) => (error as Error).message,
}
vi.mock('../usePage', () => ({ useSprayPage: () => w }))
const order = { id: 'D1', document_no:'SYN-D1', counterparty:'合成委托方', status:'confirmed', version:3,
  lines:[{id:'L1',item_no:'00017',part:'左件',color:'灰',quantity:'100',received:'0',unit:'件',due_date:'2026-11-01',priority:0,route_id:null}] }
let view: VueWrapper
beforeEach(() => {
  w.dirty.value=false;w.saveDraft.value=null;w.passportId.value=null;w.contextVersion.value=1
  w.items.mockImplementation(key=>key==='demands'?[order]:[])
  w.command.mockReset();w.load.mockReset();w.confirmDiscard.mockReset()
  view=mount(DemandPage,{global:{stubs:{RouterLink:{template:'<a><slot /></a>'},WorkspaceState:true,
    WorkspaceDialog:{props:['open','title'],template:'<section v-if="open" :aria-label="title"><button @click="$emit(\'close\')">关闭表单</button><slot/><slot name="footer"/></section>'}}}})
})
afterEach(()=>view.unmount())
const button=(label:string)=>view.findAll('button').find(node=>node.text()===label)!

it('asks before discarding amendments, retains cancelled values, and clears only accepted edits', async()=>{
  await button('变更').trigger('click')
  const form=view.get('[aria-label="订单变更"]')
  await form.get('input').setValue('101')
  expect(w.dirty.value).toBe(true)
  w.confirmDiscard.mockResolvedValueOnce(false)
  await button('关闭表单').trigger('click');await flushPromises()
  expect(w.confirmDiscard).toHaveBeenCalledWith('放弃当前订单变更？')
  expect((form.get('input').element as HTMLInputElement).value).toBe('101')
  expect(w.dirty.value).toBe(true)
  w.confirmDiscard.mockResolvedValueOnce(true)
  await button('关闭表单').trigger('click');await flushPromises()
  expect(view.find('[aria-label="订单变更"]').exists()).toBe(false)
  expect(w.dirty.value).toBe(false);expect(w.command).not.toHaveBeenCalled()
})

it('starts a clean new form after discard, without inheriting source factory or a phantom dirty state', async()=>{
  await button('登记需求').trigger('click')
  expect(w.dirty.value).toBe(false)
  await view.get('#spray-demand-form select').setValue('huakang-b')
  expect(w.dirty.value).toBe(true)
  w.confirmDiscard.mockResolvedValue(true)
  await button('取消').trigger('click');await flushPromises()
  await button('登记需求').trigger('click')
  expect((view.get('#spray-demand-form select').element as HTMLSelectElement).value).toBe('')
  expect(w.dirty.value).toBe(false)
})

it('locks amendment fields and keeps the form while a write is in flight; repeated submit has one command', async()=>{
  let resolve!:(value:unknown)=>void
  w.command.mockImplementation(()=>new Promise(done=>{resolve=done}))
  await button('变更').trigger('click')
  const form=view.get('[aria-label="订单变更"] form')
  await form.get('textarea').setValue('合成保存测试')
  await form.trigger('submit');await form.trigger('submit')
  expect(w.command).toHaveBeenCalledTimes(1)
  expect(form.get('fieldset').attributes('disabled')).toBeDefined()
  await button('关闭表单').trigger('click')
  expect(view.text()).toContain('保存仍在进行')
  expect(w.confirmDiscard).not.toHaveBeenCalled()
  expect(w.command).toHaveBeenCalledWith('demands/D1/amend',expect.objectContaining({quantity:'100',reason:'合成保存测试'}),3)
  resolve({id:'D1'});await flushPromises()
  expect(view.find('[aria-label="订单变更"]').exists()).toBe(false)
  expect(w.load).toHaveBeenCalledWith(['demands'])
})

it('locks new-demand fields and suppresses repeated draft submissions without losing the form on failure', async()=>{
  let reject!:(error:unknown)=>void
  w.command.mockImplementation(()=>new Promise((_,fail)=>{reject=fail}))
  await button('登记需求').trigger('click')
  await view.get('#spray-demand-form input').setValue('SYN-PENDING')
  await button('保存草稿').trigger('click')
  await view.get('#spray-demand-form').trigger('submit')
  expect(w.command).toHaveBeenCalledTimes(1)
  expect(view.get('#spray-demand-form fieldset').attributes('disabled')).toBeDefined()
  await button('取消').trigger('click')
  expect(w.confirmDiscard).not.toHaveBeenCalled()
  reject(new Error('结果待核对'));await flushPromises()
  expect(view.text()).toContain('结果待核对')
  expect((view.get('#spray-demand-form input').element as HTMLInputElement).value).toBe('SYN-PENDING')
  expect(view.get('#spray-demand-form fieldset').attributes('disabled')).toBeUndefined()
})

it.each(['context','dispose'])('never restores a saved source after a %s boundary during the follow-up refresh', async boundary=>{
  let finish!:()=>void
  w.command.mockResolvedValue({id:'old-demand'})
  w.load.mockImplementation(()=>new Promise<void>(resolve=>{finish=resolve}))
  await button('登记需求').trigger('click')
  await button('保存草稿').trigger('click');await flushPromises()
  if(boundary==='context')w.contextVersion.value++
  else view.unmount()
  finish();await flushPromises()
  expect(w.passportId.value).toBeNull()
})

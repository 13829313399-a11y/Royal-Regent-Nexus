import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Component from '../CartonMaterialCorrectionDialog.vue'
import { materialCorrectionApi as api, type CorrectionContext, type MaterialCorrection } from '@/api/cartonMaterialCorrection'
const mocks = vi.hoisted(() => ({ auth: {} as { currentUser?: { id: string }; authorizationVersion?: number; can?: typeof vi.fn }, can: vi.fn(() => true) }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => mocks.auth }))
vi.mock('@/api/cartonMaterialCorrection', () => ({ materialCorrectionApi: { context: vi.fn(), supplierList: vi.fn(), create: vi.fn(), act: vi.fn() } }))
vi.mock('@/lib/http', () => ({ getApiErrorMessage: (e: Error) => e.message }))
const before = { packaging_type: '普通箱', paper_quality: 'B3B', specification: '13.5*11.125*16.125', dimension_unit: 'cm' }
const row: MaterialCorrection = { id:'MC1', factory_id:'huaxing', order_id:'O1', order_no:'ORDER-1', contract_no:'C1', item_no:'I1', order_line_id:'L1', issue_id:'P1', document_no:'PO1', before, after:{ ...before, dimension_unit:'inch' }, reason:'尺寸单位录入错误', status:'PENDING', revision:1, created_by_name:'仓库', created_at:'2026-10-15', resolved_by_name:'', resolved_at:'', response_note:'', corrected_document_no:'' }
const context: CorrectionContext = { order_no:'ORDER-1', factory_id:'huaxing', revision:2, issue_id:'P1', status:'PENDING_SUPPLIER', lines:[{ id:'L1', ...before }], records:[] }
beforeEach(() => {
  vi.resetAllMocks(); mocks.can.mockReturnValue(true)
  mocks.auth = reactive({ currentUser:{ id:'U1' }, authorizationVersion:1, can:mocks.can })
  vi.mocked(api.context).mockResolvedValue(structuredClone(context))
  vi.mocked(api.supplierList).mockResolvedValue([structuredClone(row)])
})
async function ready(supplier=false) {
 const w=mount(Component,{props:{ factoryId:'huaxing', orderNo:'ORDER-1', supplier, recordId:supplier?'MC1':undefined }})
 await flushPromises();return w
}
describe('bilateral material correction', () => {
 it('sends a narrow correction retaining literal size and order revision', async()=>{
  vi.mocked(api.create).mockResolvedValue(row)
  const w=await ready();await w.get('[aria-label="更正后尺寸单位"]').setValue('inch');await w.get('[aria-label="纸品更正原因"]').setValue('尺寸单位录入错误')
  await w.get('form').trigger('submit');await flushPromises()
  expect(api.create).toHaveBeenCalledWith('ORDER-1',expect.objectContaining({ expected_revision:2, issue_id:'P1', order_line_id:'L1', after:row.after }),expect.any(AbortSignal))
  expect(Object.keys(vi.mocked(api.create).mock.calls[0]![1].after).sort()).toEqual(['dimension_unit','packaging_type','paper_quality','specification'])
  expect(w.emitted('changed')).toHaveLength(1);w.unmount()
 })
 it('requires an explicit unit when the historical order did not record one', async()=>{
  vi.mocked(api.context).mockResolvedValue({...context,lines:[{id:'L1',...before,dimension_unit:''}]})
  const w=await ready();expect(w.get<HTMLSelectElement>('[aria-label="更正后尺寸单位"]').element.value).toBe('')
  expect(w.text()).toContain('单位未填写');w.unmount()
 })
 it('requires supplier acknowledgement but permits returning with no explanation', async()=>{
  vi.mocked(api.act).mockResolvedValue({...row,status:'RETURNED'})
  const w=await ready(true)
  const approve=()=>w.findAll('button').find(b=>b.text()==='同意更正并生效')!
  await approve().trigger('click');expect(api.act).not.toHaveBeenCalled();expect(w.get('[role="alert"]').text()).toContain('勾选')
  await w.findAll('button').find(b=>b.text()==='退回仓库核实')!.trigger('click');await flushPromises()
  expect(api.act).toHaveBeenCalledWith('MC1',expect.objectContaining({action:'RETURN',verified:false,note:''}),true,expect.any(AbortSignal));w.unmount()
 })
 it('approves only the displayed revision after explicit verification', async()=>{
  vi.mocked(api.act).mockResolvedValue({...row,status:'APPROVED'})
  const w=await ready(true);expect(w.text()).toContain('13.5*11.125*16.125')
  await w.get('input[type="checkbox"]').setValue(true)
  await w.findAll('button').find(b=>b.text()==='同意更正并生效')!.trigger('click');await flushPromises()
  expect(api.act).toHaveBeenCalledWith('MC1',expect.objectContaining({action:'APPROVE',verified:true,expected_revision:1,note:''}),true,expect.any(AbortSignal));w.unmount()
 })
 it.each(['', '  ', '填错'])('defaults blank reasons while retaining short reasons: %j', async(value)=>{
  vi.mocked(api.create).mockResolvedValue(row)
  const w=await ready()
  const reason=w.get<HTMLTextAreaElement>('[aria-label="纸品更正原因"]')
  expect(reason.element.value).toBe('填错了');expect(reason.element.required).toBe(false)
  await w.get('[aria-label="更正后尺寸单位"]').setValue('inch');await reason.setValue(value)
  await w.get('form').trigger('submit');await flushPromises()
  expect(api.create).toHaveBeenCalledWith('ORDER-1',expect.objectContaining({reason:value.trim()||'填错了'}),expect.any(AbortSignal));w.unmount()
 })
 it('allows warehouse withdrawal with an optional note but requires verification', async()=>{
  vi.mocked(api.context).mockResolvedValue({...context,records:[row]})
  vi.mocked(api.act).mockResolvedValue({...row,status:'WITHDRAWN'})
  const w=await ready();const withdraw=w.findAll('button').find(b=>b.text()==='撤回申请')!
  await withdraw.trigger('click');expect(api.act).not.toHaveBeenCalled()
  await w.get('input[type="checkbox"]').setValue(true);await withdraw.trigger('click');await flushPromises()
  expect(api.act).toHaveBeenCalledWith('MC1',expect.objectContaining({action:'WITHDRAW',note:'',verified:true}),false,expect.any(AbortSignal));w.unmount()
 })
 it('freezes uncertain requests and retries the identical body', async()=>{
  vi.mocked(api.create).mockRejectedValueOnce(new Error('网络中断')).mockResolvedValueOnce(row)
  const w=await ready();await w.get('[aria-label="更正后尺寸单位"]').setValue('inch');await w.get('[aria-label="纸品更正原因"]').setValue('尺寸单位录入错误');await w.get('form').trigger('submit');await flushPromises()
  const first=JSON.parse(JSON.stringify(vi.mocked(api.create).mock.calls[0]![1]))
  expect(w.get<HTMLInputElement>('[aria-label="更正后规格"]').element.disabled).toBe(true)
  await w.findAll('button').find(b=>b.text()==='按原请求重试')!.trigger('click');await flushPromises()
  expect(vi.mocked(api.create).mock.calls[1]![1]).toEqual(first);w.unmount()
 })
 it('discards late data when the account changes and prevents read-only writes',async()=>{
  let resolve!: (value:CorrectionContext)=>void
  vi.mocked(api.context).mockReturnValueOnce(new Promise(done=>{resolve=done})).mockResolvedValue({...context,lines:[]})
  const w=mount(Component,{props:{factoryId:'huaxing',orderNo:'ORDER-1'}})
  mocks.auth.currentUser={id:'U2'};mocks.can.mockReturnValue(false);mocks.auth.authorizationVersion=2;await flushPromises()
  resolve(context);await flushPromises();expect(w.findAll('option')).toHaveLength(4)
  expect(w.get<HTMLInputElement>('[aria-label="更正后规格"]').element.disabled).toBe(true)
  await w.get('form').trigger('submit');expect(api.create).not.toHaveBeenCalled();w.unmount()
 })
})

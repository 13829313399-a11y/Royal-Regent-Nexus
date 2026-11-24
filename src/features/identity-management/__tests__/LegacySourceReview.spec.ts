import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import LegacySourceReview from '../LegacySourceReview.vue'

const api = vi.hoisted(() => ({ person: vi.fn(), draft: vi.fn(), preview: vi.fn(), commit: vi.fn(), change: vi.fn() }))
const studioApi = vi.hoisted(() => ({ legacyPreview:vi.fn(),commit:vi.fn(),receipt:vi.fn() }))
vi.mock('@/api/accessStudio', () => ({accessStudioApi:studioApi}))
vi.mock('@/api/identity', () => ({ identityApi: api }))
beforeEach(() => {
  vi.resetAllMocks()
  api.person.mockResolvedValue({ id:'p', identity_version:1, authorization_version:1, primary_factory_id:'huakang-a',
    primary_department:'engineering', position:'工程师', role_bindings:[{id:'b',state:'active',role_name:'工程师',factory_id:'huakang-a'}],overrides:[] })
  api.draft.mockResolvedValue({id:'draft',revision:1,state:'draft'})
  api.preview.mockResolvedValue({high_risk:false,requires_approval:false,permission_diffs:{added:[],removed:[]}})
  api.change.mockResolvedValue({id:'draft',revision:1,state:'draft'})
})
async function setup(studio = false) {
  const wrapper = mount(LegacySourceReview, {props:{userId:'p', studio},global:{stubs:{RouterLink:true}}})
  await flushPromises(); await wrapper.get('select').setValue('assignment')
  await wrapper.get('button').trigger('click'); await flushPromises()
  return wrapper
}
it('requires explicit confirmation of missing legacy organization, department and title', async () => {
  api.person.mockResolvedValue({id:'p',identity_version:0,authorization_version:1,primary_factory_id:'',primary_department:'',position:'',role_bindings:[],overrides:[]})
  studioApi.legacyPreview.mockResolvedValue({preview_token:'proof',high_risk:false,requires_approval:false,permission_diffs:{added:[],removed:[]}})
  const catalog={organizations:[{id:'f',name:'甲厂',status:'active',kind:'factory',factory_id:'f',departments:[{code:'d',name:'工程部'}]}],writes_enabled:true,scheduling_enabled:false,authz_mode:'enforce'}
  const w = mount(LegacySourceReview,{props:{userId:'p',studio:true,catalog}})
  await flushPromises()
  expect(w.findAll('select').map(el => el.element.value)).toEqual(['',''])
  expect(w.get('button').attributes('disabled')).toBeDefined()
  await w.findAll('select')[0]!.setValue('f')
  await w.findAll('select')[1]!.setValue('d')
  await w.get('input').setValue('工程师')
  await w.get('button').trigger('click'); await flushPromises()
  expect(studioApi.legacyPreview.mock.calls[0]?.[1].new_assignment).toMatchObject({org_unit_id:'f',department_code:'d',official_position_title:'工程师'})
  expect(api.draft).not.toHaveBeenCalled()
  w.unmount()
})
it('accounts for every enabled legacy allowance and omits revoked or suspended historical allowances', async () => {
  api.person.mockResolvedValue({id:'p',identity_version:2,authorization_version:3,primary_factory_id:'f',primary_department:'engineering',position:'工程师',role_bindings:[],
    overrides:[
      {id:'expired',permission_code:'task:view',effect:'allow',state:'active',valid_until:'2020-01-01',factory_id:'f',department:'engineering'},
      {id:'retired',permission_code:'task:edit',effect:'allow',state:'revoked',factory_id:'f',department:'engineering'},
      {id:'paused',permission_code:'task:edit',effect:'allow',state:'suspended',factory_id:'f',department:'engineering'},
    ]})
  studioApi.legacyPreview.mockResolvedValue({preview_token:'proof',high_risk:false,requires_approval:false,permission_diffs:{added:[],removed:[]}})
  const wrapper = mount(LegacySourceReview,{props:{userId:'p',studio:true}})
  await flushPromises()
  expect(wrapper.findAll('input[type=checkbox]')).toHaveLength(1)
  await wrapper.get('input[type=checkbox]').setValue(true)
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(studioApi.legacyPreview.mock.calls[0]?.[1].exception_decisions).toEqual([{override_id:'expired',decision:'keep_original_scope'}])
  wrapper.unmount()
})
it('uses a transient legacy preview and queries the studio receipt on a lost reversal-free confirmation', async () => {
  studioApi.legacyPreview.mockResolvedValue({preview_token:'legacy-proof',high_risk:false,requires_approval:false,permission_diffs:{added:[],removed:[]}})
  studioApi.commit.mockRejectedValue(new Error('connection lost'))
  studioApi.receipt.mockResolvedValue({status:'committed',result:{decision:'applied'}})
  const wrapper = await setup(true)
  expect(api.draft).not.toHaveBeenCalled()
  expect(studioApi.legacyPreview.mock.calls[0]?.[1]).toMatchObject({request_type:'confirm_identity',binding_dispositions:[{binding_id:'b',source:'assignment'}]})
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(studioApi.receipt.mock.calls[0]?.[0]).toBe(studioApi.commit.mock.calls[0]?.[2])
  expect(wrapper.emitted('saved')).toHaveLength(1)
  wrapper.unmount()
})
it.each([false,true])('separates a pending independent review from the second step, including lost replies (%s)', async lost => {
  studioApi.legacyPreview.mockResolvedValue({preview_token:'proof',high_risk:false,requires_approval:true,permission_diffs:{added:[],removed:[]}})
  const pending = {decision:'pending_approval',change_id:'confirm-1'}
  if (lost) { studioApi.commit.mockRejectedValue(new Error('offline')); studioApi.receipt.mockResolvedValue({status:'committed',result:pending}) }
  else studioApi.commit.mockResolvedValue(pending)
  const wrapper = await setup(true)
  expect(wrapper.get('button').text()).toContain('提交来源核实复核')
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('等待独立复核')
  expect(wrapper.emitted('saved')).toBeUndefined()
  expect(wrapper.emitted('locked')?.at(-1)).toEqual([false])
  api.change.mockResolvedValue({state:'applied'})
  await wrapper.findAll('button').find(b=>b.text()==='核对复核结果')!.trigger('click'); await flushPromises()
  expect(api.change).toHaveBeenCalledWith('confirm-1')
  expect(wrapper.emitted('saved')).toHaveLength(1)
  wrapper.unmount()
})
it('unlocks the workbench after successful no-drift confirmation', async () => {
  api.commit.mockResolvedValue({state:'applied'})
  const wrapper = await setup()
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(wrapper.emitted('saved')).toHaveLength(1)
  expect(wrapper.emitted('locked')?.at(-1)).toEqual([false])
  wrapper.unmount()
})
it('unlocks and requires a new preview after definite expiry, but retains uncertain command', async () => {
  api.commit.mockRejectedValueOnce({response:{status:410,data:{detail:'预览过期'}}})
  const wrapper = await setup()
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(wrapper.get('select').attributes('disabled')).toBeUndefined()
  expect(wrapper.get('button').text()).toBe('核实是否保持原权限')
  await wrapper.get('button').trigger('click'); await flushPromises()
  api.commit.mockRejectedValue(new Error('connection lost'))
  await wrapper.get('button').trigger('click'); await flushPromises()
  const command = api.commit.mock.calls.at(-1)?.[2]
  expect(wrapper.get('select').attributes('disabled')).toBeDefined()
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(api.commit.mock.calls.at(-1)?.[2]).toBe(command)
  wrapper.unmount()
})

it('requires a separate acknowledgement for high-risk source-only confirmation', async () => {
  studioApi.legacyPreview.mockResolvedValue({ preview_token: 'proof', high_risk: true, requires_approval: false,
    permission_diffs: { added: [], removed: [], source_changed: [{ permission_code: 'system:audit_read', factory_id: 'huakang-a', department: '' }] } })
  studioApi.commit.mockResolvedValue({ decision: 'applied' })
  const wrapper = await setup(true)
  expect(wrapper.get('button').attributes('disabled')).toBeDefined()
  await wrapper.get('input[type=checkbox]').setValue(true)
  await wrapper.get('button').trigger('click')
  await flushPromises()
  expect(studioApi.commit.mock.calls[0]?.[1]).toMatchObject({ risk_acknowledged: true, preview_token: 'proof' })
  expect(wrapper.emitted('saved')).toHaveLength(1)
  wrapper.unmount()
})

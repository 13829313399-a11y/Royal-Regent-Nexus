import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import LegacySourceReview from '../LegacySourceReview.vue'

const api = vi.hoisted(() => ({ person: vi.fn(), draft: vi.fn(), preview: vi.fn(), commit: vi.fn(), change: vi.fn() }))
vi.mock('@/api/identity', () => ({ identityApi: api }))
beforeEach(() => {
  vi.resetAllMocks()
  api.person.mockResolvedValue({ id:'p', identity_version:1, authorization_version:1, primary_factory_id:'huakang-a',
    primary_department:'engineering', position:'工程师', role_bindings:[{id:'b',state:'active',role_name:'工程师',factory_id:'huakang-a'}],overrides:[] })
  api.draft.mockResolvedValue({id:'draft',revision:1,state:'draft'})
  api.preview.mockResolvedValue({high_risk:false,requires_approval:false,permission_diffs:{added:[],removed:[]}})
  api.change.mockResolvedValue({id:'draft',revision:1,state:'draft'})
})
async function setup() {
  const wrapper = mount(LegacySourceReview, {props:{userId:'p'}})
  await flushPromises(); await wrapper.get('select').setValue('assignment')
  await wrapper.get('button').trigger('click'); await flushPromises()
  return wrapper
}
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

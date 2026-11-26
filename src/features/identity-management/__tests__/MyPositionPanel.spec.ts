import { mount, flushPromises, DOMWrapper } from '@vue/test-utils'
import { createRouter, createMemoryHistory, RouterView } from 'vue-router'
import { beforeEach, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import MyPositionPanel from '../MyPositionPanel.vue'

const api = vi.hoisted(() => ({ profile: vi.fn(), catalog: vi.fn(), history: vi.fn(), edit: vi.fn(), submit: vi.fn(), withdraw: vi.fn() }))
const feature = vi.hoisted(() => ({ enabled: false }))
vi.mock('@/components/iam/workspace/iam-navigation', () => ({ get iamStudioEnabled() { return feature.enabled } }))
vi.mock('@/api/positionReviews', () => ({ positionReviewsApi: api, positionStatus: { pending: '待处理' } }))
const auth = reactive({ currentUser: { id: 'employee', identity: { employment_epoch: 1 } }, refreshSession: vi.fn() })
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
beforeEach(() => {
  feature.enabled = false
  vi.resetAllMocks()
  auth.currentUser.id = 'employee'
  api.profile.mockResolvedValue({ can_submit: true, official_position: { org_unit_id: 'huakang-a', department_code: 'engineering', position: '工程师' }, open_review: null, effective_permission_summary: [] })
  api.catalog.mockResolvedValue({ organizations: [{ id: 'huakang-a', name: '华康A', kind: 'factory', status: 'active', departments: [{ code: 'engineering', name: '工程部' }] }] })
  api.history.mockResolvedValue({ items: [], total: 0 })
})
it('requires a reason in the new dialog, protects drafts and observes returned applications without losing edits', async () => {
  feature.enabled = true
  vi.useFakeTimers({toFake:['setInterval','clearInterval']})
  const declared = {org_unit_id:'huakang-a', department_code:'engineering', position:'工程师', note:''}
  const row = {id:'self-review', revision:1, origin:'employee', status:'pending', declaration:declared}
  const profile = {can_submit:true, open_review:row, official_position:declared, effective_permission_summary:[],
    current_packages:[{binding_id:'a',role_id:'pack',role_name:'工程',description:'工程资料核对'}],
    effective_business_factories:[{id:'huakang-a',name:'华康A'}],
    reference_packages:[{role_id:'ref-pack',name:'工程经理',description:'核对图纸',department_code:'engineering'}]}
  api.profile.mockResolvedValue(profile)
  api.history.mockResolvedValue({items:[row],total:1})
  const router = createRouter({history:createMemoryHistory(), routes:[
    {path:'/account/position',component:MyPositionPanel}, {path:'/',component:{template:'<main>工作台</main>'}},
  ]})
  await router.push('/account/position')
  const wrapper = mount(RouterView, {attachTo:document.body, global:{plugins:[router]}})
  try {
    await flushPromises()
    expect(wrapper.get('.self-identity').text()).toContain('工程资料核对')
    expect(wrapper.get('.self-factory-list').text()).toContain('华康A')
    await wrapper.get('.self-edit button').trigger('click'); await flushPromises()
    const dialog = new DOMWrapper(document.querySelector<HTMLElement>('[role="dialog"]')!)
    expect(dialog.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    await dialog.get('[aria-label="筛选参考职位"]').setValue('核对图纸')
    expect(dialog.get('.iams-references label').text()).toContain('工程经理')
    await dialog.get('.iams-references input[type="checkbox"]').setValue(true)
    await dialog.get('[aria-label="筛选参考职位"]').setValue('无匹配')
    expect(dialog.get('.iams-references').text()).toContain('没有匹配的公开参考职位')
    expect(dialog.get('.iams-references').text()).toContain('已选 1 / 3')
    await dialog.get('textarea').setValue('申请核对新岗位')
    const nav = router.push('/')
    await flushPromises()
    await dialog.get('[role="alertdialog"] button').trigger('click')
    await nav
    expect(router.currentRoute.value.path).toBe('/account/position')
    const returned = {...row, revision:2, status:'returned', review_comment:'请补充部门'}
    api.profile.mockResolvedValue({...profile,open_review:returned})
    api.history.mockResolvedValue({items:[returned],total:1})
    await vi.advanceTimersByTimeAsync(30000)
    await flushPromises()
    expect(api.history).toHaveBeenCalledWith(1,1)
    expect((dialog.get('textarea').element as HTMLTextAreaElement).value).toBe('申请核对新岗位')
    expect(dialog.text()).toContain('此申请已由其他人处理')
    expect(dialog.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('请补充部门')
    expect(api.edit).not.toHaveBeenCalled()
  } finally { wrapper.unmount(); vi.useRealTimers() }
})
async function setup() {
  const wrapper = mount(MyPositionPanel, { attachTo: document.body, global: { stubs: { RouterLink: true } } })
  await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === '修改岗位')!.trigger('click')
  await flushPromises()
  return wrapper
}
it('cancels without submitting and restores focus to the edit entry', async () => {
  const wrapper = await setup()
  expect(document.activeElement).toBe(wrapper.get('input').element)
  await wrapper.get('input').setValue('取消的草稿')
  const cancel = wrapper.findAll('button').find(button => button.text() === '取消')!
  // In a real browser implicit Enter dispatches the first submit button.
  expect(cancel.attributes('type')).toBe('button')
  await cancel.trigger('click'); await flushPromises()
  expect(api.submit).not.toHaveBeenCalled()
  expect(document.activeElement?.textContent).toContain('修改岗位')
  wrapper.unmount()
})
it('submits the form and moves keyboard focus to the saved result', async () => {
  api.submit.mockResolvedValue({ message: '岗位更新已提交' })
  const wrapper = await setup()
  await wrapper.get('input').setValue('新岗位')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.submit).toHaveBeenCalledWith(expect.objectContaining({ position: '新岗位' }))
  expect(wrapper.find('form').exists()).toBe(false)
  expect(document.activeElement).toBe(wrapper.get('[role="status"]').element)
  wrapper.unmount()
})
it('retains the draft and focuses the error when the source changed', async () => {
  api.submit.mockRejectedValue({ isAxiosError: true, response: { status: 409, data: { detail: '申报已变化，请重新核对' } } })
  const wrapper = await setup()
  await wrapper.get('input').setValue('需要保留的草稿')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(wrapper.get('input').element.value).toBe('需要保留的草稿')
  expect(document.activeElement).toBe(wrapper.get('[role="alert"]').element)
  expect(wrapper.get('[role="alert"]').text()).toContain('申报已变化')
  wrapper.unmount()
})
it('discards an old viewer error when identity changes during the conflict reload', async () => {
  api.submit.mockRejectedValue({ isAxiosError: true, response: { status: 409, data: { detail: '旧身份错误' } } })
  const wrapper = await setup()
  let resolve!: (value: unknown) => void
  api.profile.mockReturnValueOnce(new Promise(r => { resolve = r }))
  await wrapper.get('input').setValue('旧身份草稿')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  auth.currentUser.id = 'different-employee'
  await flushPromises()
  const focused = document.activeElement
  resolve({ can_submit: true, official_position: { position: '旧人员岗位' }, effective_permission_summary: [] })
  await flushPromises()
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  expect(wrapper.text()).not.toContain('旧身份错误')
  expect(document.activeElement).toBe(focused)
  wrapper.unmount()
})

import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import StudioPerson from '../studio/StudioPerson.vue'

const api = vi.hoisted(() => ({
  person: vi.fn(),
  effective: vi.fn(),
  preview: vi.fn(),
  commit: vi.fn(),
  receipt: vi.fn(),
  listRoles: vi.fn(),
  packageAbilities: vi.fn(),
}))
vi.mock('@/api/iam', async original => ({...await original<object>(), iamApi:api}))
vi.mock('@/api/accessStudio', () => ({ accessStudioApi: api }))
vi.mock('@/api/identity', async (original) => ({ ...(await original<object>()), identityApi: api }))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ currentUser: { id: 'admin' }, can: () => true, authorizationVersion: 1 }),
}))
const assignment = {
  id: 'main',
  org_unit_id: 'factory',
  org_name: '甲厂',
  department_code: 'engineering',
  official_position_title: '工程师',
  is_primary: true,
}
const person = {
  id: 'target',
  username: 'worker',
  display_name: '已有员工',
  status: 'active',
  identity_mode: 'v2',
  employment_status: 'active',
  identity_version: 4,
  authorization_version: 11,
  primary_assignment: assignment,
  active_assignments_summary: [assignment],
  assignments: [assignment],
  role_bindings: [],
  overrides: [],
}
const currentPackage = {
  binding_id: 'old-binding',
  role_id: 'engineer',
  role_name: '工程师',
  factory_id: 'factory',
  factory_ceiling: ['factory'],
  department: 'engineering',
  role_version_id: 'old-version',
  assignment_id: 'main',
  version_outdated: true,
  source_type: 'assignment',
}
const catalog = {
  organizations: [],
  writes_enabled: true,
  studio_writes_enabled: true,
  scheduling_enabled: false,
  authz_mode: 'enforce',
}
enableAutoUnmount(afterEach)
beforeEach(() => {
  vi.useFakeTimers()
  vi.resetAllMocks()
  api.packageAbilities.mockResolvedValue({})
  api.person.mockResolvedValue(person)
  api.effective.mockResolvedValue({ current_packages: [currentPackage], effective_permissions_grouped: [] })
  api.preview.mockResolvedValue({
    preview_token: 'token',
    expires_at: '2025-01-01T00:05:00Z',
    server_now: '2025-01-01T00:00:00Z',
    allowed_to_commit: true,
    permission_diffs: { added: [], removed: [], retained: [], source_changed: [] },
    high_risk: false,
    requires_empty_confirmation: false,
    requires_approval: false,
    explicit_denials: [],
  })
})
afterEach(() => vi.useRealTimers())
async function open(props: Partial<InstanceType<typeof StudioPerson>['$props']> = {}) {
  const wrapper = mount(StudioPerson, {
    attachTo: document.body,
    props: { personId: 'target', tab: 'packages', panel: 'profile', catalog, ...props },
    global: {
      stubs: {
        IamDialogSurface: { template: '<section><slot name="navigation"/><slot/></section>' },
        AccessExplanation: true,
        DelegationEditor: true,
        StudioTimeline: true,
      },
    },
  })
  await flushPromises()
  return wrapper
}
it('browses an outdated binding and the other tabs without any mutation or preview', async () => {
  const w = await open()
  expect(w.text()).toContain('正在使用旧版')
  await w.get('summary').trigger('click')
  for (const tab of ['effective', 'timeline', 'packages']) await w.setProps({ tab })
  await vi.advanceTimersByTimeAsync(500)
  expect(api.preview).not.toHaveBeenCalled()
  expect(api.commit).not.toHaveBeenCalled()
  expect(api.person).toHaveBeenCalledTimes(1)
})
it('adopts a requested package only after the administrator stages it and ties explicit edits to the original review', async () => {
  const review = {item_key:'position:request',source_revision:'r1',status:'pending',studio_writes_enabled:true,available_actions:['preview'], declaration:{
    org_unit_id:'factory',department_code:'engineering',position:'高级工程师',requested_role_ids:['requested-role'],requested_factory_ids:['factory']}}
  const org = {id:'factory',name:'甲厂',kind:'factory',factory_id:'factory',status:'active',departments:[{code:'engineering',name:'工程'}]}
  const role = {role_id:'requested-role',name:'工程主管',department:'engineering'}
  api.listRoles.mockResolvedValue([{id:'requested-role',name:'工程主管',position_department:'engineering'}])
  const w = await open({review:review as never,panel:'manage',catalog:{...catalog,organizations:[org]},referencePackages:[role as never]})
  const button = (s:string) => w.findAll('button').find(b=>b.text()===s)!
  expect(w.text()).toContain('员工申请参考')
  expect(api.preview).not.toHaveBeenCalled()
  await button('采用为待核对方案').trigger('click'); await flushPromises()
  expect(api.preview).not.toHaveBeenCalled()
  await button('加入待确认方案').trigger('click')
  await w.get('textarea').setValue('已核对员工申请')
  await vi.advanceTimersByTimeAsync(380)
  expect(api.preview.mock.lastCall?.[1]).toMatchObject({position_review:{item_key:'position:request',expected_source_revision:'r1',confirmed_profile:{org_unit_id:'factory',department_code:'engineering',position:'高级工程师'}},
    remove_binding_ids:[], upgrade_binding_ids:[], add_packages:[{role_id:'requested-role',department:'engineering',factory_scope:{kind:'selected',factory_ids:['factory']}}]})
})
it('keeps package details readable while the independent studio write switch is off', async () => {
  const w = await open()
  await w.setProps({ catalog: { ...catalog, studio_writes_enabled: false } })
  expect(w.text()).toContain('新版人工办理已关闭')
  expect(w.text()).toContain('正在使用旧版')
  expect(w.text()).not.toContain('调整职位与权限')
  expect(api.preview).not.toHaveBeenCalled()
})
it('previews only a title correction and resolves network uncertainty with the original command', async () => {
  const w = await open()
  const button = (s: string) => w.findAll('button').find((b) => b.text() === s)!
  await button('调整职位与权限').trigger('click')
  await w.get('input[maxlength="128"]').setValue('高级工程师')
  await w.get('textarea').setValue('人事核实职位文字')
  await vi.advanceTimersByTimeAsync(360)
  expect(api.preview).toHaveBeenCalledWith('target', {
    reason: '人事核实职位文字',
    base_identity_version: 4,
    base_authorization_version: 11,
    source_assignment_id: 'main',
    official_position_title: '高级工程师',
    add_packages: [],
    remove_binding_ids: [],
    upgrade_binding_ids: [],
  })
  api.commit.mockRejectedValueOnce(new Error('offline'))
  await button('确认本次变更').trigger('click')
  await flushPromises()
  expect(w.text()).toContain('提交结果待确认')
  expect(document.activeElement).toBe(w.get('[role="alert"]').element)
  expect(w.emitted('locked')?.at(-1)).toEqual([true])
  api.receipt.mockResolvedValue({ status: 'not_observed', result: null })
  await button('查询提交回执').trigger('click')
  await flushPromises()
  api.commit.mockResolvedValue({
    command_id: 'key',
    status: 'committed',
    decision: 'applied',
    message: '岗位已更正',
  })
  await button('使用原命令重试').trigger('click')
  await flushPromises()
  expect(api.commit.mock.calls[1]).toEqual(api.commit.mock.calls[0])
  expect(api.receipt.mock.calls[0]?.[0]).toEqual(api.commit.mock.calls[0]?.[2])
  expect(w.emitted('saved')).toHaveLength(1)
  expect(w.text()).toContain('岗位已更正')
})
it('requires an explicit upgrade and blocks submission after a server conflict', async () => {
  const w = await open()
  const button = (s: string) => w.findAll('button').find((b) => b.text() === s)!
  await button('调整职位与权限').trigger('click')
  await button('升级到当前版本').trigger('click')
  api.preview.mockRejectedValueOnce({ response: { status: 409, data: { detail: '版本发生变化' } } })
  await w.get('textarea').setValue('主动升级旧版')
  await vi.advanceTimersByTimeAsync(360)
  expect(api.preview.mock.calls[0]?.[1]).toMatchObject({
    upgrade_binding_ids: ['old-binding'],
    remove_binding_ids: [],
    add_packages: [],
  })
  expect(w.text()).toContain('重新读取人员版本')
  expect(document.activeElement).toBe(w.get('[role="alert"]').element)
  expect(button('确认本次变更')).toBeUndefined()
  await button('重新读取人员版本').trigger('click')
  await flushPromises()
  expect(api.commit).not.toHaveBeenCalled()
  expect(api.person).toHaveBeenCalledTimes(2)
})
it('stages only the selected ceiling and cancels unconfirmed changes', async () => {
  const second = { id: 'next', name: '乙厂', kind: 'factory', status: 'active', factory_id: 'next', departments: [{ code: 'engineering', name: '工程' }] }
  const w = await open({ catalog: { ...catalog, organizations: [second] } })
  const button = (s: string) => w.findAll('button').find(b => b.text() === s)!
  await button('调整职位与权限').trigger('click')
  await button('调整此绑定的厂区上限').trigger('click')
  await w.get('input[type="checkbox"][value="next"]').setValue(true)
  await w.get('textarea').setValue('核对这个绑定')
  await vi.advanceTimersByTimeAsync(360)
  expect(api.preview).not.toHaveBeenCalled()
  await button('加入本次变更').trigger('click')
  await vi.advanceTimersByTimeAsync(360)
  expect(api.preview.mock.lastCall?.[1]).toMatchObject({scope_updates: [{binding_id: 'old-binding', factory_ids: ['factory', 'next']}], remove_binding_ids: [], upgrade_binding_ids: []})
  await button('撤销本次厂区变更').trigger('click')
  await vi.advanceTimersByTimeAsync(360)
  expect(button('确认本次变更').attributes('disabled')).toBeDefined()
  expect(api.commit).not.toHaveBeenCalled()
})
it('previews the specific secondary assignment without creating a formal draft', async () => {
  api.person.mockResolvedValue({...person, active_assignments_summary: [assignment, { ...assignment, id: 'secondary', is_primary: false }]})
  const w = await open()
  const button = (s: string) => w.findAll('button').find(b => b.text() === s)!
  await button('结束此兼任').trigger('click')
  expect(w.text()).toContain('办理对象 · 已有员工')
  await w.get('textarea').setValue('明确结束所选兼任')
  await vi.advanceTimersByTimeAsync(360)
  expect(api.preview.mock.lastCall?.[1]).toMatchObject({request_type:'end_assignment', source_assignment_id:'secondary', target_user_id:'target'})
  expect(api.commit).not.toHaveBeenCalled()
})
it('finds a package by an included capability and shows its contents without staging it', async () => {
  api.listRoles.mockResolvedValue([{ id: 'r-one', name: '装配方案' }, { id: 'r-two', name: '仓管方案' }])
  api.packageAbilities.mockResolvedValue({
    'r-one': [{ code: 'assembly:review', name: '核准装配' }],
    'r-two': [{ code: 'storage:read', name: '读取库位' }],
  })
  const w = await open()
  const button = (s: string) => w.findAll('button').find(b => b.text() === s)!
  await button('调整职位与权限').trigger('click')
  await button('添加权限包').trigger('click')
  await flushPromises()
  await w.get('input[type="search"]').setValue('读取库位')
  expect(button('装配方案')).toBeUndefined()
  await button('仓管方案').trigger('click')
  expect(w.text()).toContain('读取库位 · storage:read')
  await vi.advanceTimersByTimeAsync(360)
  expect(api.preview).not.toHaveBeenCalled()
  expect(api.commit).not.toHaveBeenCalled()
})

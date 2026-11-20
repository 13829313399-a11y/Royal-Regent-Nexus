import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import PositionWorkbench from '../PositionWorkbench.vue'
import type { WorkspaceTask } from '../workspace/contracts'

const api = vi.hoisted(() => ({ tasks: vi.fn(), catalog: vi.fn() }))
vi.mock('@/components/iam/workspace/iam-navigation', async original => ({ ...await original<object>(), iamStudioEnabled: true }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ currentUser: { id: 'reviewer' }, authorizationVersion: 1, can: () => true }) }))
vi.mock('@/api/identity', async original => ({ ...await original<object>(), identityApi: api }))
vi.mock('@/api/iamWorkspace', () => ({ iamWorkspaceApi: api }))

const registration: WorkspaceTask = {
  key: 'registration:first', kind: 'registration', source_id: 'first', source_revision: '1',
  subject: { user_id: 'person', display_name: '审核测试员', username: 'test.person' },
  org_unit_id: 'f1', department: 'engineering', current_position: '', proposed_position: '工程技术员',
  raw_status: 'pending', state: 'actionable', created_at: '2026-05-08T04:00:00Z', available_actions: ['preview'], blocked_reasons: [],
}

async function openInbox(desktop: boolean, path = '/system/users?view=inbox') {
  vi.stubGlobal('matchMedia', () => ({ matches: desktop }))
  api.catalog.mockResolvedValue({ organizations: [] })
  api.tasks.mockImplementation(async ({ kind }) => ({
    items: !kind || kind === 'registration' ? [registration] : [], actionable_total: 1, visible_total: 1,
    bucket_counts: { registration: 1, position: 0, 'password-reset': null, 'identity-change': null }, partial: true,
    coverage: [{ kind: 'password-reset', state: 'not_authorized' }, { kind: 'identity-change', state: 'unavailable' }],
  }))
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/system/users', component: PositionWorkbench }] })
  await router.push(path)
  const wrapper = mount(RouterView, { global: { plugins: [router], stubs: {
    PositionReviewPane: { name:'PositionReviewPane', props: ['itemKey'], emits: ['back','saved','locked'], template: '<section>{{ itemKey }}<button @click="$emit(\'back\')">返回队列</button></section>' },
  } } })
  await flushPromises()
  return { router, wrapper }
}

afterEach(() => { vi.unstubAllGlobals(); vi.resetAllMocks() })

it('shows authorized bucket counts, opens the first item on desktop and clears the detail for an empty track', async () => {
  const { router, wrapper } = await openInbox(true)
  const tracks = wrapper.findAll('.iam2-queues button')
  expect(tracks.map(track => track.get('strong').text())).toEqual(['1', '0', '无查看权限', '暂不可用'])
  expect(tracks[2]!.attributes('disabled')).toBeDefined()
  expect(router.currentRoute.value.query.task).toBe(registration.key)
  await tracks[1]!.trigger('click')
  await flushPromises()
  expect(router.currentRoute.value.query.kind).toBe('position')
  expect(router.currentRoute.value.query.task).toBeUndefined()
  expect(api.tasks).toHaveBeenCalledTimes(2)
  wrapper.unmount()
})

it('retains a direct selection even when it is outside the current queue', async () => {
  const { router, wrapper } = await openInbox(true, '/system/users?view=inbox&task=registration:linked')
  expect(router.currentRoute.value.query.task).toBe('registration:linked')
  wrapper.unmount()
})
it('keeps an uncertain item selected and advances in the same filter after confirmed success', async () => {
  const { router, wrapper } = await openInbox(true, '/system/users?view=inbox&kind=registration&task=registration:first')
  const pane = wrapper.getComponent({name:'PositionReviewPane'})
  pane.vm.$emit('locked', true)
  pane.vm.$emit('saved', {status:'not_observed'})
  pane.vm.$emit('saved', {status:'committed',item_key:'registration:another'})
  await flushPromises()
  expect(router.currentRoute.value.query.task).toBe(registration.key)
  api.tasks.mockResolvedValue({items:[{...registration, key:'registration:next'}], visible_total: 1, actionable_total:1, coverage:[], partial:false})
  pane.vm.$emit('locked', false)
  pane.vm.$emit('saved', {status:'committed', message:'已确认', item_key:registration.key})
  await flushPromises()
  expect(router.currentRoute.value.query).toMatchObject({kind:'registration', task:'registration:next'})
  wrapper.unmount()
})

it('starts with the list on mobile and reopens a previously selected item after returning', async () => {
  const { router, wrapper } = await openInbox(false)
  expect(router.currentRoute.value.query.task).toBeUndefined()
  const row = wrapper.get('.iam2-task-card')
  await row.trigger('click'); await flushPromises()
  await wrapper.get('.iw-workspace > section button').trigger('click')
  expect(wrapper.get('.iw-workspace').classes()).not.toContain('has-detail')
  await row.trigger('click'); await flushPromises()
  expect(wrapper.get('.iw-workspace').classes()).toContain('has-detail')
  wrapper.unmount()
})

import { shallowMount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
vi.mock('@/components/layout/AppShell.vue', () => ({ default: { name: 'AppShell', template: '<main />' } }))
vi.mock('@/components/layout/DeploymentNotice.vue', () => ({ default: { name: 'DeploymentNotice', template: '<span />' } }))
vi.mock('@/features/assistant/AssistantHost.vue', () => ({ default: { name: 'AssistantHost', template: '<span />' } }))
vi.mock('@/features/collaboration/CollaborationHost.vue', () => ({ default: { name: 'CollaborationHost', template: '<span />' } }))
vi.mock('@/features/work-center/WorkCenterHost.vue', () => ({ default: { name: 'WorkCenterHost', template: '<span />' } }))
import App from '@/App.vue'
import { useAuthStore } from '@/stores/auth'
const user = { id: 'qa', username: 'qa', display_name: '测试', roles: [], permissions: [], grants: [], factory_scopes: [], department_scopes: [], force_password_change: true }
describe('private global host authentication boundary', () => {
  it('mounts hosts only after required password change and removes them during confirmation', async () => {
    const pinia = createPinia(); setActivePinia(pinia)
    const auth = useAuthStore(); const wrapper = shallowMount(App, { global: { plugins: [pinia] } })
    const hosts = () => wrapper.findAll('assistant-host-stub, collaboration-host-stub, work-center-host-stub')
    expect(hosts()).toHaveLength(0)
    auth.applySession(user); await flushPromises(); expect(hosts()).toHaveLength(0)
    auth.applySession({ ...user, force_password_change: false }); await flushPromises(); expect(hosts()).toHaveLength(3)
    const original = hosts()[0]!.element
    auth.applySession({ ...user, force_password_change: false }); await flushPromises(); expect(hosts()[0]!.element).toBe(original)
    auth.isConfirmingSession = true; await flushPromises(); expect(hosts()).toHaveLength(0)
    auth.clearSession(); auth.isConfirmingSession = false; await flushPromises(); expect(hosts()).toHaveLength(0)
    wrapper.unmount()
  })
})

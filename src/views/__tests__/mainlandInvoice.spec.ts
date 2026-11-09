import { mount } from '@vue/test-utils'
import { reactive, nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MainlandInvoiceView from '@/views/MainlandInvoiceView.vue'
import { readFileSync } from 'node:fs'

const state = vi.hoisted(() => ({ can: vi.fn(), app: undefined as any, auth: undefined as any }))
vi.mock('@/stores/app', () => ({ useAppStore: () => state.app }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => state.auth }))
vi.mock('@/components/modules/sales/SalesModuleWorkbench.vue', () => ({ default: { template: '<main><slot /></main>' } }))

beforeEach(() => {
  state.app = reactive({ activeFactory: { id: 'huakang-a' }, setActiveDepartment: vi.fn() })
  state.can.mockReturnValue(true)
  state.auth = reactive({ can: state.can, currentUser: { id: 'user-a', identity: { employment_epoch: 1 } } })
})
describe('business invoice factory workspace', () => {
  it('sets business department and checks exact factory scope', () => {
    const wrapper = mount(MainlandInvoiceView)
    expect(state.app.setActiveDepartment).toHaveBeenCalledWith('sales-business')
    expect(state.can).toHaveBeenCalledWith('mainland_invoice:generate', 'huakang-a', 'sales-business')
    expect(wrapper.get('iframe').attributes('src')).toBe('/mainland-invoice/?factory_id=huakang-a')
  })
  it('replaces the iframe on factory switch, discarding old results', async () => {
    const wrapper = mount(MainlandInvoiceView)
    const original = wrapper.get('iframe').element
    state.app.activeFactory.id = 'huakang-d'
    await nextTick()
    expect(wrapper.get('iframe').element).not.toBe(original)
    expect(wrapper.get('iframe').attributes('src')).toContain('huakang-d')
  })
  it('replaces the iframe on account and employment changes within the same factory', async () => {
    const wrapper = mount(MainlandInvoiceView)
    const original = wrapper.get('iframe').element
    state.auth.currentUser.id = 'user-b'
    await nextTick()
    const changed = wrapper.get('iframe').element
    expect(changed).not.toBe(original)
    state.auth.currentUser.identity.employment_epoch = 2
    await nextTick()
    expect(wrapper.get('iframe').element).not.toBe(changed)
  })
  it('does not render unsupported factories or grantless users', async () => {
    state.app.activeFactory.id = 'group'
    const wrapper = mount(MainlandInvoiceView)
    expect(wrapper.find('iframe').exists()).toBe(false)
    state.app.activeFactory.id = 'huakang-a'
    state.can.mockReturnValue(false)
    await nextTick()
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.text()).toContain('没有本厂区')
  })
  it('registers only the business entrance with strict page permissions', () => {
    const router = readFileSync('src/router/index.ts', 'utf8')
    const index = router.indexOf("path: '/modules/sales-business/mainland-invoice'")
    expect(index).toBeLessThan(router.indexOf("path: '/modules/:department/:module'"))
    expect(router.slice(index, index + 500)).toContain('strictPermissions: true')
    const source = readFileSync('src/data/enterpriseMock.ts', 'utf8')
    expect(source.match(/id: 'mainland-invoice'/g)).toHaveLength(1)
  })
})

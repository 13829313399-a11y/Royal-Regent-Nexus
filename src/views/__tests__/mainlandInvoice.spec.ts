import { mount, RouterLinkStub } from '@vue/test-utils'
import { reactive, nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MainlandInvoiceView from '@/views/MainlandInvoiceView.vue'
import { readFileSync } from 'node:fs'

const state = vi.hoisted(() => ({ can: vi.fn(), app: undefined as any, auth: undefined as any }))
vi.mock('@/stores/app', () => ({ useAppStore: () => state.app }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => state.auth }))
const mountView = () => mount(MainlandInvoiceView, { global: { stubs: { RouterLink: RouterLinkStub, AccountMenu: true } } })

beforeEach(() => {
  const factory = { id: 'huakang-a', shortName: '华康A' }
  state.app = reactive({ activeFactory: factory, activeProductionFactory: factory, setActiveDepartment: vi.fn() })
  state.can.mockReturnValue(true)
  state.auth = reactive({ can: state.can, currentUser: { id: 'user-a', identity: { employment_epoch: 1 } } })
})
describe('accounting invoice factory workspace', () => {
  it('sets accounting department and checks exact factory scope', () => {
    const wrapper = mountView()
    expect(state.app.setActiveDepartment).toHaveBeenCalledWith('accounting')
    expect(state.can).toHaveBeenCalledWith('mainland_invoice:generate', 'huakang-a', 'accounting')
    expect(wrapper.get('iframe').attributes('src')).toBe('/mainland-invoice/?factory_id=huakang-a')
    const links = wrapper.findAllComponents(RouterLinkStub)
    expect(links.map(link => link.text())).toEqual(['返回会计部', '会计部模块中心'])
    expect(links.every(link => link.props('to') === '/modules/accounting?factory=huakang-a')).toBe(true)
  })
  it('replaces the iframe on factory switch, discarding old results', async () => {
    const wrapper = mountView()
    const original = wrapper.get('iframe').element
    state.app.activeFactory.id = 'huakang-d'
    await nextTick()
    expect(wrapper.get('iframe').element).not.toBe(original)
    expect(wrapper.get('iframe').attributes('src')).toContain('huakang-d')
  })
  it('replaces the iframe on account and employment changes within the same factory', async () => {
    const wrapper = mountView()
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
    const wrapper = mountView()
    expect(wrapper.find('iframe').exists()).toBe(false)
    state.app.activeFactory.id = 'huakang-a'
    state.can.mockReturnValue(false)
    await nextTick()
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.text()).toContain('没有本厂区')
  })
  it('registers accounting with strict permissions and redirects old bookmarks with factory context', () => {
    const router = readFileSync('src/router/index.ts', 'utf8')
    const index = router.indexOf("path: '/modules/accounting/mainland-invoice'")
    expect(index).toBeGreaterThanOrEqual(0)
    expect(index).toBeLessThan(router.indexOf("path: '/modules/:department/:module'"))
    expect(router.slice(index, index + 500)).toContain('strictPermissions: true')
    expect(router.slice(index, index + 500)).toContain("permissionDepartment: 'accounting'")
    expect(router).toContain("path: '/modules/sales-business/mainland-invoice'")
    expect(router).toContain("redirect: to => ({ name: 'mainland-invoice', query: to.query, hash: to.hash })")
    const source = readFileSync('src/data/enterpriseMock.ts', 'utf8')
    expect(source.match(/id: 'mainland-invoice'/g)).toHaveLength(1)
  })
})

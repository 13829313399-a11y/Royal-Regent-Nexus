import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAppStore } from '@/stores/app'
import ShippingManagementView from '../ShippingManagementView.vue'

const routeState = vi.hoisted(() => ({
  path: '/modules/pmc-warehouse/shipping-management',
  name: 'shipping-management',
  params: {} as Record<string, string>,
  query: {} as Record<string, string>,
}))
const replaceMock = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  RouterLink: {
    name: 'RouterLink',
    props: ['to'],
    template: '<a :href="typeof to === \'string\' ? to : \'\'"><slot /></a>',
  },
  useRoute: () => routeState,
  useRouter: () => ({ replace: replaceMock }),
}))

function mountView(factory: 'huaxing' | 'huadeng' | 'huakang-a' | 'huakang-b' | 'huakang-d' | 'huakang-c' | 'group') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useAppStore()
  store.setActiveFactory(factory)
  const wrapper = mount(ShippingManagementView, {
    global: { plugins: [pinia], stubs: { AccountMenu: true } },
  })
  return { store, wrapper }
}

const rows = (wrapper: ReturnType<typeof mountView>['wrapper']) => wrapper.findAll('tbody tr')

describe('shipping order management workspace', () => {
  beforeEach(() => {
    routeState.query = {}
    replaceMock.mockReset()
  })

  it('lists factory-scoped orders with the newest departure date first', async () => {
    const { wrapper } = mountView('huaxing')

    expect(wrapper.text()).toContain('船务管理')
    expect(wrapper.text()).toContain('工厂货期排单')
    expect(wrapper.text()).toContain('共 12 条')
    expect(rows(wrapper)).toHaveLength(10)
    expect(rows(wrapper)[0]!.text()).toContain('1001')
    expect(rows(wrapper)[0]!.text()).toContain('SHZ8265013')
    expect(rows(wrapper)[0]!.text()).toContain('美国 · 洛杉矶')
    const cards = wrapper.findAll('[aria-label="船务作业"] button')
    expect(cards).toHaveLength(4)
    expect(cards[0]!.text()).toContain('SO排出货表')
    expect(cards[0]!.text()).toContain('按 SO 汇总出货明细')
    expect(cards[1]!.text()).toContain('车的排出货表')
    expect(cards[1]!.text()).toContain('按车汇总交仓出货明细')
    expect(cards[2]!.text()).toContain('补料')
    expect(cards[2]!.text()).toContain('SI 截止前补料与配补料提醒')
    expect(cards[3]!.text()).toContain('通关一体化资料')
    expect(cards[3]!.text()).toContain('报关单 / 装箱单 / 发票')

    wrapper.unmount()
  })

  it('switches the whole order catalog with the active factory', async () => {
    const { store, wrapper } = mountView('huaxing')
    expect(wrapper.text()).toContain('SHZ8265013')

    store.setActiveFactory('huadeng')
    await nextTick()

    expect(wrapper.text()).toContain('共 10 条')
    expect(wrapper.text()).toContain('HDX77500')
    expect(wrapper.text()).not.toContain('SHZ8265013')
    expect((wrapper.get('select[aria-label="切换厂区"]').element as HTMLSelectElement).value).toBe('huadeng')

    wrapper.unmount()
  })

  it('filters live by keyword, port, container type, status and departure range', async () => {
    const { wrapper } = mountView('huaxing')
    const input = wrapper.get('input[aria-label="搜索货号或货名"]')

    expect(input.attributes('placeholder')).toBe('搜索货号或货名')
    expect(wrapper.text()).toContain('共 12 条')
    expect(wrapper.findAll('button').some((button) => button.text().trim() === '搜索')).toBe(false)

    await input.setValue('15754')
    expect(wrapper.text()).toContain('共 4 条')
    expect(rows(wrapper)).toHaveLength(4)

    await input.setValue('链条枪')
    expect(rows(wrapper)).toHaveLength(4)

    await input.setValue('ZZZ999')
    expect(rows(wrapper)).toHaveLength(0)
    expect(wrapper.text()).toContain('没有匹配的出货单')
    await wrapper.findAll('button').find((button) => button.text().includes('清空筛选'))!.trigger('click')
    expect(wrapper.text()).toContain('共 12 条')

    await wrapper.get('select[aria-label="筛选港口"]').setValue('蛇口')
    expect(rows(wrapper)).toHaveLength(1)
    expect(rows(wrapper)[0]!.text()).toContain('1009')
    await wrapper.get('select[aria-label="筛选港口"]').setValue('')

    await wrapper.get('select[aria-label="筛选柜型"]').setValue('1*20GP')
    expect(wrapper.text()).toContain('共 3 条')
    await wrapper.get('select[aria-label="筛选柜型"]').setValue('')

    await wrapper.get('select[aria-label="筛选状态"]').setValue('已取消')
    expect(rows(wrapper)).toHaveLength(1)
    expect(rows(wrapper)[0]!.text()).toContain('1012')
    await wrapper.get('select[aria-label="筛选状态"]').setValue('')

    await wrapper.get('input[aria-label="开航日期起"]').setValue('2000-01-01')
    await wrapper.get('input[aria-label="开航日期止"]').setValue('2000-12-31')
    expect(rows(wrapper)).toHaveLength(0)
    expect(wrapper.text()).toContain('没有匹配的出货单')

    await wrapper.findAll('button').find((button) => button.text().includes('清空筛选'))!.trigger('click')
    expect(wrapper.text()).toContain('共 12 条')

    wrapper.unmount()
  })

  it('paginates through the order list without row selection', async () => {
    const { wrapper } = mountView('huaxing')
    const next = () => wrapper.get('button[aria-label="下一页"]')
    const previous = () => wrapper.get('button[aria-label="上一页"]')

    expect(wrapper.text()).toContain('第 1 / 2 页')
    expect(wrapper.findAll('input[type="checkbox"]')).toHaveLength(0)

    await next().trigger('click')
    expect(rows(wrapper)).toHaveLength(2)
    expect(rows(wrapper)[0]!.text()).toContain('1011')
    expect(rows(wrapper)[1]!.text()).toContain('1005')
    expect(wrapper.text()).toContain('第 2 / 2 页')

    await previous().trigger('click')
    expect(rows(wrapper)).toHaveLength(10)
    expect(wrapper.text()).toContain('第 1 / 2 页')

    wrapper.unmount()
  })

  it('opens the order detail from the SO link and closes with Escape', async () => {
    const { wrapper } = mountView('huaxing')

    await wrapper.get('button[aria-label="查看 SO SHZ8265013"]').trigger('click')
    await nextTick()

    const dialog = document.body.querySelector('[role="dialog"]')
    expect(dialog).toBeTruthy()
    expect(dialog!.textContent).toContain('Shipment Order')
    expect(dialog!.textContent).toContain('C260304887')
    expect(dialog!.textContent).toContain('美国 · 洛杉矶')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(document.body.querySelector('[role="dialog"]')).toBeNull()

    wrapper.unmount()
  })

  it('keeps entry cards, refresh and row actions explicit previews', async () => {
    const { wrapper } = mountView('huaxing')

    await wrapper.findAll('button').find((button) => button.text().includes('刷新'))!.trigger('click')
    expect(wrapper.text()).toContain('已刷新 · 共 12 条')

    await wrapper.findAll('button').find((button) => button.attributes('aria-label') === 'SO排出货表')!.trigger('click')
    expect(wrapper.text()).toContain('界面预览：SO排出货表尚未接入后端接口')

    await wrapper.findAll('button').find((button) => button.attributes('aria-label') === '车的排出货表')!.trigger('click')
    expect(wrapper.text()).toContain('界面预览：车的排出货表尚未接入后端接口')

    await rows(wrapper)[0]!.findAll('button').find((button) => button.text() === '修改')!.trigger('click')
    expect(wrapper.text()).toContain('界面预览：修改出货单 SHZ8265013（1001）尚未接入后端接口')

    await rows(wrapper)[0]!.findAll('button').find((button) => button.text() === '柜单')!.trigger('click')
    expect(wrapper.text()).toContain('界面预览：柜单 SHZ8265013尚未接入后端接口')

    wrapper.unmount()
  })

  it('keeps unsupported factories out of the shipping workspace', () => {
    const { wrapper } = mountView('huakang-c')

    expect(wrapper.text()).toContain('暂未开通船务管理')
    expect(wrapper.find('[role="tablist"]').exists()).toBe(false)

    wrapper.unmount()
  })

  it('switches the workspace factory from the header selector', async () => {
    const { wrapper } = mountView('huaxing')

    await wrapper.get('select[aria-label="切换厂区"]').setValue('huakang-d')

    expect(wrapper.text()).toContain('共 5 条')
    expect(wrapper.text()).toContain('KDX10245')
    expect(wrapper.text()).not.toContain('SHZ8265013')

    wrapper.unmount()
  })

  it('keeps warehouse dispatch and master data tabs factory-scoped', async () => {
    const { store, wrapper } = mountView('huaxing')

    await wrapper.findAll('[role="tab"]').find((tab) => tab.text().includes('交仓分车'))!.trigger('click')
    expect(wrapper.text()).toContain('35 CBM')
    store.setActiveFactory('huakang-b')
    await nextTick()
    expect(wrapper.text()).toContain('超出 35 CBM')

    await wrapper.findAll('[role="tab"]').find((tab) => tab.text().includes('基础资料'))!.trigger('click')
    expect(wrapper.text()).toContain('客户与柜号序列')
    expect(wrapper.text()).toContain('CEPIA')

    wrapper.unmount()
  })
})

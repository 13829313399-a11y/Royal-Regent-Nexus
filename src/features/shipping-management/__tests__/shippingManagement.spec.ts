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

describe('shipping management workspace', () => {
  beforeEach(() => {
    routeState.query = {}
    replaceMock.mockReset()
  })

  it('shows the current factory tasks and the four shipment gates', async () => {
    const { wrapper } = mountView('huaxing')

    expect(wrapper.text()).toContain('船务管理')
    expect((wrapper.get('select[aria-label="切换厂区"]').element as HTMLSelectElement).value).toBe('huaxing')
    expect(wrapper.text()).toContain('界面预览')
    expect(wrapper.text()).toContain('128-1')
    expect(wrapper.text()).toContain('SHZ8265013')
    expect(wrapper.text()).toContain('装船 / 出货日')
    expect(wrapper.text()).toContain('SI 截止')
    expect(wrapper.text()).toContain('截关 / 截数期')
    expect(wrapper.text()).toContain('验货通过')
    expect(wrapper.text()).not.toContain('HD-064-1')

    wrapper.unmount()
  })

  it('switches the whole task catalog with the active factory', async () => {
    const { store, wrapper } = mountView('huaxing')
    expect(wrapper.text()).toContain('ZURU')

    store.setActiveFactory('huadeng')
    await nextTick()

    expect(wrapper.text()).toContain('当前厂区')
    expect((wrapper.get('select[aria-label="切换厂区"]').element as HTMLSelectElement).value).toBe('huadeng')
    expect(wrapper.text()).toContain('064-1')
    expect(wrapper.text()).toContain('MOOSE')
    expect(wrapper.text()).not.toContain('128-1')
    expect(wrapper.text()).not.toContain('SHZ8265013')

    wrapper.unmount()
  })

  it('keeps unsupported factories out of the shipping workspace', async () => {
    const { wrapper } = mountView('huakang-c')

    expect(wrapper.text()).toContain('暂未开通船务管理')
    expect(wrapper.text()).not.toContain('走柜任务')
    expect(wrapper.find('[role="tablist"]').exists()).toBe(false)

    wrapper.unmount()
  })

  it('opens the selected task detail with items and totals', async () => {
    const { wrapper } = mountView('huaxing')

    const waitingTask = wrapper.findAll('button').find((button) => button.text().includes('130-1'))
    expect(waitingTask).toBeTruthy()
    await waitingTask!.trigger('click')

    expect(wrapper.text()).toContain('等待客户通知')
    expect(wrapper.text()).toContain('待客户通知')
    expect(wrapper.text()).toContain('15754')
    expect(wrapper.text()).toContain('合计 CBM')

    wrapper.unmount()
  })

  it('lists warehouse trips against the 35 CBM cap and flags overloads', async () => {
    const { store, wrapper } = mountView('huaxing')

    const dispatchTab = wrapper.findAll('[role="tab"]').find((tab) => tab.text().includes('交仓分车'))
    expect(dispatchTab).toBeTruthy()
    await dispatchTab!.trigger('click')

    expect(wrapper.text()).toContain('35 CBM')
    expect(wrapper.text()).toContain('车1')
    expect(wrapper.text()).toContain('18.4')

    store.setActiveFactory('huakang-b')
    await nextTick()
    expect(wrapper.text()).toContain('超出 35 CBM')
    expect(wrapper.text()).toContain('38.5')

    wrapper.unmount()
  })

  it('shows factory-scoped master data and keeps preview actions explicit', async () => {
    const { wrapper } = mountView('huaxing')

    const masterTab = wrapper.findAll('[role="tab"]').find((tab) => tab.text().includes('基础资料'))
    await masterTab!.trigger('click')

    expect(wrapper.text()).toContain('客户与柜号序列')
    expect(wrapper.text()).toContain('ZURU')
    expect(wrapper.text()).toContain('盐田')
    expect(wrapper.text()).toContain('Dong Guan Xingxin Plastic Products Co., Ltd.')

    await wrapper.findAll('[role="tab"]')[0]!.trigger('click')
    const exportButton = wrapper.findAll('button').find((button) => button.text().includes('导出走柜表'))
    await exportButton!.trigger('click')
    expect(wrapper.text()).toContain('界面预览：导出走柜表尚未接入后端接口')

    wrapper.unmount()
  })

  it('breaks the completed KPI into SO / 补料 / 舱单 completion', () => {
    const { wrapper } = mountView('huakang-a')

    expect(wrapper.text()).toContain('SO已完成 3')
    expect(wrapper.text()).toContain('补料已完成 2')
    expect(wrapper.text()).toContain('舱单已完成 1')
    expect(wrapper.text()).toContain('单据进度')

    wrapper.unmount()
  })

  it('switches the workspace factory from the header selector', async () => {
    const { wrapper } = mountView('huaxing')

    await wrapper.get('select[aria-label="切换厂区"]').setValue('huadeng')

    expect((wrapper.get('select[aria-label="切换厂区"]').element as HTMLSelectElement).value).toBe('huadeng')
    expect(wrapper.text()).toContain('064-1')
    expect(wrapper.text()).not.toContain('128-1')

    wrapper.unmount()
  })

  it('exposes SO export, customs pack and SI supplement quick actions', async () => {
    const { wrapper } = mountView('huakang-a')

    expect(wrapper.text()).toContain('快捷作业')
    expect(wrapper.text()).toContain('SO排出货表')
    expect(wrapper.text()).toContain('通关一体化资料')
    expect(wrapper.text()).toContain('补料')
    expect(wrapper.text()).toContain('舱单')

    const customs = wrapper.findAll('button').find((button) => button.text().includes('通关一体化资料'))
    expect(customs).toBeTruthy()
    await customs!.trigger('click')
    expect(wrapper.text()).toContain('界面预览：通关一体化资料（当前 SO KAX55102）尚未接入后端接口')

    const manifest = wrapper.findAll('button').find((button) => button.text().includes('舱单'))
    await manifest!.trigger('click')
    expect(wrapper.text()).toContain('界面预览：舱单（当前 SO KAX55102）尚未接入后端接口')

    const supplement = wrapper.findAll('button').find((button) => button.text().includes('补料'))
    await supplement!.trigger('click')
    expect(wrapper.text()).toContain('界面预览：补料（当前 SO KAX55102）尚未接入后端接口')

    wrapper.unmount()
  })
})

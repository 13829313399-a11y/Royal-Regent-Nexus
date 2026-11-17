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

type Factory = 'huaxing' | 'huadeng' | 'huakang-a' | 'huakang-b' | 'huakang-d' | 'huakang-c' | 'group'

function mountView(factory: Factory) {
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

async function openMenu(wrapper: ReturnType<typeof mountView>['wrapper'], label: string) {
  const button = wrapper.findAll('aside[aria-label="船务系统菜单"] button').find((entry) => entry.text().includes(label))
  expect(button).toBeTruthy()
  await button!.trigger('click')
}

async function mountOrders(factory: Factory = 'huaxing') {
  const context = mountView(factory)
  await openMenu(context.wrapper, '工厂排期单')
  return context
}

describe('shipping order management workspace', () => {
  beforeEach(() => {
    routeState.query = {}
    replaceMock.mockReset()
  })

  it('opens the email import page by default with upload, mailbox and record blocks', async () => {
    const { wrapper } = mountView('huaxing')

    expect(wrapper.find('[role="tablist"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('将邮件或扫描件拖到此处，或点击上传（支持多封）')
    expect(wrapper.text()).toContain('解析邮件（0封）')
    expect(wrapper.text()).toContain('AI自动解析')
    expect(wrapper.text()).toContain('从邮箱直接导入')
    expect(wrapper.text()).toContain('保存并连接')
    expect(wrapper.text()).toContain('解析记录（0）')
    expect(wrapper.text()).toContain('查看员 admin')
    for (const item of ['邮件导入', '工厂排期单', '货号映射', '厂商映射', '一键出货', '卡板据统计', '提箱柜核对', '用户管理']) {
      expect(wrapper.text()).toContain(item)
    }

    expect(wrapper.text()).not.toContain('SHZ8265013 出货通知')
    await wrapper.findAll('button').find((button) => button.text().includes('解析记录（0）'))!.trigger('click')
    expect(wrapper.text()).toContain('SHZ8265013 出货通知')

    expect(wrapper.text()).toContain('立即同步')
    expect(wrapper.text()).toContain('每天 08:00–23:00 每小时自动收件（华兴 / 华登 / 华康A / 华康B / 华康D）')

    for (const label of ['码头', 'FROM', 'TO', '国家', '航次', '订仓号', '柜S/O', '船名', '发货商', '合同号', '合同后四位', '截止日期']) {
      expect(wrapper.text()).toContain(label)
    }
    expect(wrapper.text()).toContain('Packing List 明细')
    expect(wrapper.text()).toContain('确认创建出货单')
    await wrapper.findAll('button').find((button) => button.text().includes('确认创建出货单'))!.trigger('click')
    expect(wrapper.text()).toContain('请先上传并解析邮件或附件，再创建单据。')

    wrapper.unmount()
  })

  it('navigates from the sidebar to orders, master data and previews', async () => {
    const { wrapper } = mountView('huaxing')

    await openMenu(wrapper, '工厂排期单')
    expect(wrapper.text()).toContain('工厂货期排单')
    expect(rows(wrapper)).toHaveLength(10)

    await openMenu(wrapper, '货号映射')
    expect(wrapper.text()).toContain('货号映射管理')
    expect(wrapper.text()).toContain('9389')

    await openMenu(wrapper, '厂商映射')
    expect(wrapper.text()).toContain('客户与柜号序列')
    expect(wrapper.text()).toContain('下一柜号')

    await openMenu(wrapper, '一键出货')
    expect(wrapper.text()).toContain('每日新增出货资料')

    await openMenu(wrapper, '邮件导入')
    expect(wrapper.text()).toContain('将邮件或扫描件拖到此处')

    wrapper.unmount()
  })

  it('renders the code mapping page with search, customer filter and row actions', async () => {
    const { wrapper } = mountView('huaxing')
    await openMenu(wrapper, '货号映射')

    expect(wrapper.text()).toContain('货号映射管理')
    expect(wrapper.text()).toContain('9389')
    expect(wrapper.text()).toContain('全能足球6个/箱')
    expect(rows(wrapper)).toHaveLength(12)
    for (const column of ['每箱毛重（kg）', '每箱净重（kg）', '玩具类别', '来源', '客户', '状态']) {
      expect(wrapper.text()).toContain(column)
    }

    await wrapper.get('input[aria-label="搜索货号或货名"]').setValue('10201')
    await wrapper.findAll('button').find((button) => button.text().trim() === '搜索')!.trigger('click')
    expect(rows(wrapper)).toHaveLength(1)
    expect(rows(wrapper)[0]!.text()).toContain('全能足球')

    await wrapper.findAll('button').find((button) => button.text().trim() === '重置')!.trigger('click')
    expect(rows(wrapper)).toHaveLength(12)

    await wrapper.findAll('button').find((button) => button.text().trim() === 'ZURU')!.trigger('click')
    expect(rows(wrapper)).toHaveLength(2)

    await wrapper.findAll('button').find((button) => button.text().trim() === '编辑')!.trigger('click')
    expect(wrapper.text()).toContain('界面预览：编辑货号映射 10201尚未接入后端接口')

    wrapper.unmount()
  })

  it('lists factory-scoped orders with the newest departure date first', async () => {
    const { wrapper } = await mountOrders('huaxing')

    expect(wrapper.text()).toContain('船务管理')
    expect(wrapper.text()).toContain('工厂货期排单')
    expect(wrapper.text()).toContain('共 12 条')
    expect(rows(wrapper)).toHaveLength(10)
    expect(rows(wrapper)[0]!.text()).toContain('1001')
    expect(rows(wrapper)[0]!.text()).toContain('SHZ8265013')
    expect(rows(wrapper)[0]!.text()).toContain('美国 · 洛杉矶')
    expect(wrapper.find('[aria-label="船务指标"]').exists()).toBe(false)

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
    const { store, wrapper } = await mountOrders('huaxing')
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
    const { wrapper } = await mountOrders('huaxing')
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
    const { wrapper } = await mountOrders('huaxing')
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
    const { wrapper } = await mountOrders('huaxing')

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
    const { wrapper } = await mountOrders('huaxing')

    await wrapper.findAll('button').find((button) => button.text().includes('刷新'))!.trigger('click')
    expect(wrapper.text()).toContain('已刷新 · 共 12 条')

    await rows(wrapper)[0]!.findAll('button').find((button) => button.text() === '修改')!.trigger('click')
    expect(wrapper.text()).toContain('界面预览：修改出货单 SHZ8265013（1001）尚未接入后端接口')

    await rows(wrapper)[0]!.findAll('button').find((button) => button.text() === '柜单')!.trigger('click')
    expect(wrapper.text()).toContain('界面预览：柜单 SHZ8265013尚未接入后端接口')

    await wrapper.findAll('button').find((button) => button.attributes('aria-label') === 'SO排出货表')!.trigger('click')
    expect(wrapper.text()).toContain('SO 出货表')
    await wrapper.findAll('button').find((button) => button.text().includes('返回工厂排期单'))!.trigger('click')
    expect(wrapper.text()).toContain('工厂货期排单')

    await wrapper.findAll('button').find((button) => button.attributes('aria-label') === '车的排出货表')!.trigger('click')
    expect(wrapper.text()).toContain('车的排出货表')
    expect(wrapper.text()).toContain('盐田仓 CFS')

    wrapper.unmount()
  })

  it('keeps unsupported factories out of the shipping workspace', () => {
    const { wrapper } = mountView('huakang-c')

    expect(wrapper.text()).toContain('暂未开通船务管理')
    expect(wrapper.find('aside[aria-label="船务系统菜单"]').exists()).toBe(false)

    wrapper.unmount()
  })

  it('switches the workspace factory from the header selector', async () => {
    const { wrapper } = await mountOrders('huaxing')

    await wrapper.get('select[aria-label="切换厂区"]').setValue('huakang-d')

    expect(wrapper.text()).toContain('共 5 条')
    expect(wrapper.text()).toContain('KDX10245')
    expect(wrapper.text()).not.toContain('SHZ8265013')

    wrapper.unmount()
  })
})

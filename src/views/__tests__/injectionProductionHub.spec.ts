import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it } from 'vitest'
import MachineTimelineBoard from '@/components/modules/production/injection-schedule/MachineTimelineBoard.vue'
import UnscheduledOrderTable from '@/components/modules/production/injection-schedule/UnscheduledOrderTable.vue'
import { getInjectionPreviewDataset } from '@/data/injectionScheduleMock'
import InjectionProductionHubView from '@/views/InjectionProductionHubView.vue'

describe('injection production hub preview dataset', () => {
  it('preserves the verified Huaxing snapshot boundary without fake dates', () => {
    const dataset = getInjectionPreviewDataset('huaxing')
    const assignedOrderIds = new Set(dataset.tasks.map((task) => task.orderId))
    const unscheduledOrders = dataset.orders.filter((order) => !assignedOrderIds.has(order.id))

    expect(dataset.mode).toBe('preview')
    expect(dataset.publishable).toBe(false)
    expect(dataset.businessDate).toBe('2026-07-21')
    expect(dataset.machines).toHaveLength(76)
    expect(dataset.machines.filter((machine) => machine.workshop === 'old')).toHaveLength(39)
    expect(dataset.machines.filter((machine) => machine.workshop === 'new')).toHaveLength(37)
    expect(unscheduledOrders).toHaveLength(34)
    expect(unscheduledOrders.reduce((sum, order) => sum + order.outstandingShots, 0)).toBe(76498)

    for (const order of unscheduledOrders) {
      expect(order.factoryId).toBe('huaxing')
      expect(order.sourceWorkbookRow).not.toBeNull()
      expect(order.outstandingShots).toBeGreaterThan(0)
      expect(order.deliveryDueAt ?? '').not.toMatch(/^18(?:99)|^1900/)
    }
  })

  it('returns an explicit independent empty preview for other factories', () => {
    for (const factoryId of ['huakang-a', 'huakang-c', 'huadeng'] as const) {
      const dataset = getInjectionPreviewDataset(factoryId)
      expect(dataset.factoryId).toBe(factoryId)
      expect(dataset.machines).toEqual([])
      expect(dataset.molds).toEqual([])
      expect(dataset.orders).toEqual([])
      expect(dataset.tasks).toEqual([])
    }
  })
})

describe('injection production hub virtualization', () => {
  const dataset = getInjectionPreviewDataset('huaxing')

  it('windows the 76-machine timeline instead of mounting every row', () => {
    const wrapper = mount(MachineTimelineBoard, {
      props: {
        machines: dataset.machines,
        tasks: dataset.tasks,
        orders: dataset.orders,
        molds: dataset.molds,
        selectedOrder: dataset.orders[0],
        planBaseAt: dataset.planBaseAt,
      },
    })

    const region = wrapper.get('[role="region"]')
    expect(region.attributes('aria-label')).toContain('机台七日排程时间轴')
    expect(wrapper.text()).toContain('已载入 76 台机')
    expect(wrapper.findAll('.machine-row').length).toBeGreaterThan(0)
    expect(wrapper.findAll('.machine-row').length).toBeLessThan(30)
  })

  it('keeps a 1500-order table inside a bounded DOM window', () => {
    const seedOrders = dataset.orders
    const scaledOrders = Array.from({ length: 1500 }, (_, index) => {
      const seed = seedOrders[index % seedOrders.length]
      return {
        ...seed,
        id: `${seed.id}-scale-${index}`,
        orderNo: `${seed.orderNo}-${String(index + 1).padStart(4, '0')}`,
      }
    })

    const wrapper = mount(UnscheduledOrderTable, {
      props: {
        orders: scaledOrders,
        molds: dataset.molds,
        planBaseAt: dataset.planBaseAt,
      },
    })

    expect(wrapper.get('table').attributes('aria-rowcount')).toBe('1501')
    expect(wrapper.findAll('.order-row').length).toBeGreaterThan(0)
    expect(wrapper.findAll('.order-row').length).toBeLessThan(40)
    expect(wrapper.text()).toContain('虚拟窗口支持 1,500+ 订单')
  })

  it('resets a deep virtual window when search narrows the result set', async () => {
    const seedOrders = dataset.orders
    const scaledOrders = Array.from({ length: 1500 }, (_, index) => {
      const seed = seedOrders[index % seedOrders.length]
      return {
        ...seed,
        id: `${seed.id}-reset-${index}`,
        orderNo: index === 0 ? 'UNIQUE-FIRST-ORDER' : `${seed.orderNo}-reset-${index}`,
      }
    })
    const wrapper = mount(UnscheduledOrderTable, {
      props: {
        orders: scaledOrders,
        molds: dataset.molds,
        planBaseAt: dataset.planBaseAt,
      },
    })
    const viewport = wrapper.get('.orders-table-scroll')
    const viewportElement = viewport.element as HTMLElement
    viewportElement.scrollTop = 56 * 1200
    await viewport.trigger('scroll')

    await wrapper.get('input[name="order-search"]').setValue('UNIQUE-FIRST-ORDER')

    expect(viewportElement.scrollTop).toBe(0)
    expect(wrapper.get('table').attributes('aria-rowcount')).toBe('2')
    expect(wrapper.text()).toContain('UNIQUE-FIRST-ORDER')
  })

  it('separates blocking, warning, and source-only quality information', async () => {
    const baseOrder = dataset.orders[0]
    const sourceFlags = [
      '机型要求来自计划表自由文本：7A',
      'Excel 待排记录：未生成计划开始/完成时间',
    ]
    const sourceOnlyOrder = {
      ...baseOrder,
      id: 'quality-source-only',
      orderNo: 'QUALITY-SOURCE',
      sourceWorkbookRow: 88,
      dataQualityFlags: sourceFlags,
    }
    const warningOrder = {
      ...baseOrder,
      id: 'quality-warning',
      orderNo: 'QUALITY-WARNING',
      sourceWorkbookRow: 89,
      dataQualityFlags: [...sourceFlags, '计划表备注：签板（喷油）'],
    }
    const blockingOrder = {
      ...baseOrder,
      id: 'quality-blocking',
      orderNo: 'QUALITY-BLOCKING',
      sourceWorkbookRow: 90,
      dataQualityFlags: [...sourceFlags, '计划表备注：堵啤'],
    }
    const wrapper = mount(UnscheduledOrderTable, {
      props: {
        orders: [sourceOnlyOrder, warningOrder, blockingOrder],
        molds: dataset.molds,
        planBaseAt: dataset.planBaseAt,
      },
    })
    const qualitySelect = wrapper.get('select[name="quality-filter"]')

    expect(wrapper.text()).toContain('计划表备注：堵啤')
    expect(wrapper.text()).toContain('阻断 1 · 警告 0 · 来源 2 · 计划表第 90 行')

    await qualitySelect.setValue('blocking')
    expect(wrapper.get('table').attributes('aria-rowcount')).toBe('2')
    expect(wrapper.text()).toContain('QUALITY-BLOCKING')
    expect(wrapper.text()).not.toContain('QUALITY-WARNING')

    await qualitySelect.setValue('warning')
    expect(wrapper.get('table').attributes('aria-rowcount')).toBe('2')
    expect(wrapper.text()).toContain('QUALITY-WARNING')
    expect(wrapper.text()).not.toContain('QUALITY-BLOCKING')

    await qualitySelect.setValue('source')
    expect(wrapper.get('table').attributes('aria-rowcount')).toBe('4')

    await qualitySelect.setValue('ready')
    expect(wrapper.get('table').attributes('aria-rowcount')).toBe('3')
    expect(wrapper.text()).toContain('QUALITY-SOURCE')
    expect(wrapper.text()).toContain('QUALITY-WARNING')
    expect(wrapper.text()).not.toContain('QUALITY-BLOCKING')
  })

  it('filters the pending pool by machine class, color, arm, and due range', async () => {
    const assignedOrderIds = new Set(dataset.tasks.map((task) => task.orderId))
    const pendingOrders = dataset.orders.filter((order) => !assignedOrderIds.has(order.id))
    const moldById = new Map(dataset.molds.map((mold) => [mold.id, mold]))
    const machineClass = moldById.get(pendingOrders[0].moldId)?.recommendedMachineClass
    const color = pendingOrders.find((order) => order.colorName)?.colorName
    expect(machineClass).toBeTruthy()
    expect(color).toBeTruthy()

    const wrapper = mount(UnscheduledOrderTable, {
      props: {
        orders: pendingOrders,
        molds: dataset.molds,
        planBaseAt: dataset.planBaseAt,
      },
    })
    const expectRowCount = (count: number) => {
      expect(wrapper.get('table').attributes('aria-rowcount')).toBe(String(count > 0 ? count + 1 : 2))
    }

    await wrapper.get('select[name="machine-class-filter"]').setValue(machineClass!)
    expectRowCount(pendingOrders.filter(
      (order) => moldById.get(order.moldId)?.recommendedMachineClass === machineClass,
    ).length)
    await wrapper.get('select[name="machine-class-filter"]').setValue('all')

    await wrapper.get('select[name="color-filter"]').setValue(color!)
    expectRowCount(pendingOrders.filter((order) => order.colorName === color).length)
    await wrapper.get('select[name="color-filter"]').setValue('all')

    await wrapper.get('select[name="arm-filter"]').setValue('unconfirmed')
    expectRowCount(pendingOrders.filter((order) => order.armRequirement === null).length)
    expect(wrapper.text()).toContain('半自动 / 待确认')
    await wrapper.get('select[name="arm-filter"]').setValue('all')

    const businessTime = Date.parse(dataset.planBaseAt)
    await wrapper.get('select[name="due-filter"]').setValue('overdue')
    expectRowCount(pendingOrders.filter((order) => {
      if (!order.deliveryDueAt) return false
      return Math.ceil((Date.parse(order.deliveryDueAt) - businessTime) / 86_400_000) < 0
    }).length)
    await wrapper.get('select[name="due-filter"]').setValue('missing')
    expectRowCount(pendingOrders.filter((order) => !order.deliveryDueAt).length)

    expect(wrapper.text()).toContain('候选校验')
    expect(wrapper.text()).toContain('优先级按 2026-07-21 快照交期推导')
    expect(wrapper.text()).not.toMatch(/1899|1900/)
  })
})

describe('injection production hub runtime', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('opens the dedicated Huaxing workspace and keeps preview/publish boundaries visible', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/modules/production/injection-production-hub',
          component: InjectionProductionHubView,
        },
        {
          path: '/modules/production',
          component: { template: '<div>生产部模块中心</div>' },
        },
      ],
    })
    await router.push('/modules/production/injection-production-hub?factory=huaxing')
    await router.isReady()

    const wrapper = mount(InjectionProductionHubView, {
      global: {
        plugins: [router],
        stubs: {
          AccountMenu: true,
          Teleport: true,
        },
      },
    })

    expect(wrapper.text()).toContain('注塑排产中枢')
    expect(wrapper.text()).toContain('Excel 快照预览 · 非发布计划')
    expect(wrapper.text()).toContain('机台排程时间轴')
    expect(wrapper.text()).toContain('待排订单池')
    expect(wrapper.text()).not.toMatch(/1899|1900/)

    const publishButton = wrapper.findAll('button').find((button) => button.text().includes('发布前置条件'))
    expect(publishButton).toBeDefined()
    await publishButton!.trigger('click')
    expect(wrapper.text()).toContain('当前不能发布计划')
    expect(wrapper.text()).toContain('尚未接入正式数据库、权限、版本锁和审计')
  })

  it('keeps missing hard-constraint data behind an explicit manual-preview confirmation', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/modules/production/injection-production-hub',
          component: InjectionProductionHubView,
        },
        {
          path: '/modules/production',
          component: { template: '<div />' },
        },
      ],
    })
    await router.push('/modules/production/injection-production-hub?factory=huaxing')
    await router.isReady()

    const wrapper = mount(InjectionProductionHubView, {
      global: {
        plugins: [router],
        stubs: {
          AccountMenu: true,
          Teleport: true,
        },
      },
    })

    const ordersNav = wrapper.findAll('button').find((button) => button.text().trim() === '待排订单')
    await ordersNav!.trigger('click')
    expect(wrapper.text()).toContain('未排 34')
    expect(wrapper.text()).toContain('欠 76,498')
    expect(wrapper.text()).toContain('已超期')
    expect(wrapper.text()).toContain('7 天内到期')
    const inspectButton = wrapper.findAll('button').find((button) => button.text().includes('校验候选'))
    await inspectButton!.trigger('click')

    expect(wrapper.text()).toContain('匹配解释')
    expect(wrapper.text()).toContain('硬约束尚未全部通过，本候选未进入自动评分')

    const manualPreviewButton = wrapper.findAll('button').find(
      (button) => button.text().includes('人工确认本地预排'),
    )
    expect(manualPreviewButton).toBeDefined()
    expect(manualPreviewButton!.attributes('disabled')).toBeUndefined()
    await manualPreviewButton!.trigger('click')

    expect(wrapper.text()).toContain('资料缺失，需人工确认')
    expect(wrapper.text()).toContain('不能自动推荐或自动发布')

    const confirmButton = wrapper.findAll('.hub-dialog footer button').find(
      (button) => button.text().trim() === '人工确认本地预排',
    )
    expect(confirmButton!.attributes('disabled')).toBeDefined()
    await wrapper.find('.hub-dialog textarea').setValue('已核对模具尺寸，工程资料明日回填')
    const enabledConfirmButton = wrapper.findAll('.hub-dialog footer button').find(
      (button) => button.text().trim() === '人工确认本地预排',
    )
    expect((enabledConfirmButton!.element as HTMLButtonElement).disabled).toBe(false)
    await enabledConfirmButton!.trigger('click')
    expect(wrapper.text()).toContain('已人工确认本地预排')
    expect(wrapper.text()).toContain('未保存到服务器')
  })

  it('separates machine master data from editable local rule previews', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/modules/production/injection-production-hub',
          component: InjectionProductionHubView,
        },
        {
          path: '/modules/production',
          component: { template: '<div />' },
        },
      ],
    })
    await router.push('/modules/production/injection-production-hub?factory=huaxing')
    await router.isReady()

    const wrapper = mount(InjectionProductionHubView, {
      global: {
        plugins: [router],
        stubs: {
          AccountMenu: true,
          Teleport: true,
        },
      },
    })

    const mastersNav = wrapper.findAll('button').find((button) => button.text().trim() === '机台·模具')
    await mastersNav!.trigger('click')
    expect(wrapper.text()).toContain('华兴机台主数据')
    expect(wrapper.text()).toContain('抽芯不行')
    expect(wrapper.text()).toContain('机台主数据')
    expect(wrapper.text()).toContain('模具主数据')
    expect(wrapper.text()).toContain('颜色/材料矩阵')
    expect(wrapper.text()).toContain('班次与停机日历')
    expect(wrapper.text()).toContain('评分权重')
    expect(wrapper.text()).toContain('导入映射')

    const rulesNav = wrapper.findAll('button').find((button) => button.text().trim() === '规则配置')
    await rulesNav!.trigger('click')
    expect(wrapper.text()).toContain('仅在硬约束全部通过后计算')
    expect(wrapper.find('input[aria-label="货期紧迫度权重"]').element).toHaveProperty('value', '35')
    expect(wrapper.find('input[aria-label="拆单惩罚权重"]').element).toHaveProperty('value', '-12')
  })

  it('does not leak Huaxing data into another factory query', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/modules/production/injection-production-hub',
          component: InjectionProductionHubView,
        },
        {
          path: '/modules/production',
          component: { template: '<div />' },
        },
      ],
    })
    await router.push('/modules/production/injection-production-hub?factory=huakang-c')
    await router.isReady()

    const wrapper = mount(InjectionProductionHubView, {
      global: {
        plugins: [router],
        stubs: {
          AccountMenu: true,
          Teleport: true,
        },
      },
    })

    expect(wrapper.text()).toContain('当前厂区暂无注塑排产快照')
    expect(wrapper.text()).toContain('不会跨厂区混用')
    expect(wrapper.text()).not.toContain('1,864,396')
  })
})

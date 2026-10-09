import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { warehouseOperationsRoutes } from '../routes'
import { WAREHOUSES, WAREHOUSE_HOME, warehousePath } from '../navigation'

vi.mock('@/components/layout/AccountMenu.vue', () => ({ default: { template: '<span>当前账号</span>' } }))
const api = vi.hoisted(() => ({ lines: vi.fn().mockResolvedValue({ total: 0, items: [] }), imports: vi.fn().mockResolvedValue([]), apply: vi.fn() }))
vi.mock('@/api/fabricProcurement', () => ({ fabricProcurementApi: api }))
const receivingApi = vi.hoisted(() => ({ receipts: vi.fn().mockResolvedValue({ total: 0, items: [] }), stock: vi.fn().mockResolvedValue({ total: 0, items: [] }) }))
vi.mock('@/api/fabricMaster', () => ({ fabricMasterApi: { list: vi.fn().mockResolvedValue({ items: [], total: 0, can_manage: true }), candidates: vi.fn().mockResolvedValue([]) } }))
vi.mock('@/api/fabricReceiving', () => ({ fabricReceivingApi: receivingApi, materialCategoryLabels: { FABRIC: '布料', ACCESSORY: '辅料', THREAD: '线' } }))
vi.mock('@/api/warehouseOperations', () => ({ warehouseOperationsApi: { workspace: vi.fn().mockResolvedValue({ revision: 0, stock: [], documents: [], permissions: { read: true, operate: true, quality: false, correct: false } }), post: vi.fn() } }))
let wrapper: VueWrapper | undefined
beforeEach(() => { vi.spyOn(window, 'scrollTo').mockImplementation(() => {}) })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; document.body.innerHTML = ''; vi.restoreAllMocks() })

async function open(path: string) {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    ...warehouseOperationsRoutes,
    { path: WAREHOUSE_HOME, component: { template: '<div>仓管首页</div>' } },
  ] })
  await router.push(path)
  await router.isReady()
  wrapper = mount(RouterView, { attachTo: document.body, global: { plugins: [router] } })
  await flushPromises()
  return router
}

describe('warehouse framework navigation', () => {
  it('restores the mobile view after cancelling a dirty master dialog navigation', async () => {
    const router = await open(`${WAREHOUSE_HOME}/fabric-warehouse/master?factory=huakang-c&view=locations`)
    await wrapper!.findAll('button').find(button => button.text().includes('添加仓库'))!.trigger('click'); await flushPromises()
    const body = new DOMWrapper(document.body)
    await body.get('[aria-label="仓库名称"]').setValue('未保存仓库')
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await wrapper!.get('[aria-label="选择业务分区"]').setValue('partners'); await flushPromises()
    expect(confirm).toHaveBeenCalled()
    expect(router.currentRoute.value.query.view).toBe('locations')
    expect(wrapper!.get<HTMLSelectElement>('[aria-label="选择业务分区"]').element.value).toBe('locations')
    confirm.mockReturnValue(true)
    await body.findAll('button').find(button => button.text() === '关闭')!.trigger('click'); await flushPromises()
    await wrapper!.get('[aria-label="选择业务分区"]').setValue('partners'); await flushPromises()
    expect(wrapper!.get('fieldset').attributes('disabled')).toBeUndefined()
  })
  it('keeps the fabric header search aligned with fallback and remembered receipt views', async () => {
    const router = await open(`${WAREHOUSE_HOME}/fabric-warehouse/receipts?factory=huakang-c&view=invalid`)
    expect(wrapper!.find('.fabric-header-search input').exists()).toBe(true)
    expect(wrapper!.find('input[aria-label="采购单号筛选"]').exists()).toBe(false)
    await router.push(`${WAREHOUSE_HOME}/fabric-warehouse/receipts?factory=huakang-c&view=history`); await flushPromises()
    expect(wrapper!.find('.fabric-header-search input').exists()).toBe(false)
    await router.push(`${WAREHOUSE_HOME}/fabric-warehouse/receipts?factory=huakang-c`); await flushPromises()
    expect(wrapper!.find('.fabric-header-search input').exists()).toBe(false)
    await router.push(`${WAREHOUSE_HOME}/fabric-warehouse/receipts?factory=huakang-c&view=import-review&source=all`); await flushPromises()
    expect(wrapper!.find('.fabric-header-search input').exists()).toBe(true)
    await router.push(`${WAREHOUSE_HOME}/semi-finished-warehouse/receipts?factory=huakang-c`); await flushPromises()
    expect(wrapper!.find('.fabric-header-search input').exists()).toBe(false)
  })
  it('previews entered receipt details without posting, protects dismissal and clears discarded values', async () => {
    await open(`${WAREHOUSE_HOME}/fabric-warehouse/overview?factory=huakang-c`)
    const body = new DOMWrapper(document.body)
    const previewButton = () => wrapper!.findAll('button').find(button => button.text() === '预览收料单')!
    await previewButton().trigger('click'); await flushPromises()
    await body.get('input[aria-label="物料编码"]').setValue('000123')
    await body.get('input[aria-label="本次实收数量"]').setValue('12.5')
    await body.findAll('button').find(button => button.text() === '查看填写内容')!.trigger('click')
    expect(body.get('[role="dialog"]').text()).toContain('000123')
    expect(body.get('[role="dialog"]').text()).toContain('12.5')
    expect(body.get('[role="dialog"]').text()).toContain('不生成正式单据')
    expect(api.apply).not.toHaveBeenCalled()
    await body.get('[aria-label="关闭单据预览"]').trigger('click')
    expect(body.get('[role="alert"]').text()).toContain('清空')
    await body.findAll('button').find(button => button.text() === '继续查看')!.trigger('click')
    expect(body.get('[role="dialog"]').text()).toContain('000123')
    await body.get('[aria-label="关闭单据预览"]').trigger('click')
    await body.findAll('button').find(button => button.text() === '关闭并清空')!.trigger('click'); await flushPromises()
    expect(body.find('[role="dialog"]').exists()).toBe(false)
    await previewButton().trigger('click'); await flushPromises()
    expect(body.get<HTMLInputElement>('input[aria-label="物料编码"]').element.value).toBe('')
  })

  it('guards leaving a filled preview, then opens the other warehouse with its own fields', async () => {
    const router = await open(`${WAREHOUSE_HOME}/fabric-warehouse/overview?factory=huakang-c`)
    const body = new DOMWrapper(document.body)
    await wrapper!.findAll('button').find(button => button.text() === '预览发料单')!.trigger('click'); await flushPromises()
    await body.get('input[aria-label="物料编码"]').setValue('FAB-001')
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const destination = `${WAREHOUSE_HOME}/semi-finished-warehouse/receipts?factory=huakang-c`
    await router.push(destination); await flushPromises()
    expect(router.currentRoute.value.path).toContain('/fabric-warehouse/overview')
    expect(body.get<HTMLInputElement>('input[aria-label="物料编码"]').element.value).toBe('FAB-001')
    confirm.mockReturnValue(true)
    await router.push(destination); await flushPromises()
    expect(body.find('[role="dialog"]').exists()).toBe(false)
    await wrapper!.findAll('button').find(button => button.text() === '预览收料单')!.trigger('click'); await flushPromises()
    expect(body.find('input[aria-label="物料编码"]').exists()).toBe(false)
    expect(body.get<HTMLInputElement>('input[aria-label="产品 / 款式"]').element.value).toBe('')
    expect(body.get('[role="dialog"]').text()).toContain('加工任务 / 原发出单')
    expect(body.get('[role="dialog"]').text()).toContain('加工状态')
    expect(api.apply).not.toHaveBeenCalled()
  })

  it('guards route changes when only a repeatable allocation row is filled', async () => {
    const router = await open(`${WAREHOUSE_HOME}/fabric-warehouse/overview?factory=huakang-c`)
    const body = new DOMWrapper(document.body)
    await wrapper!.findAll('button').find(button => button.text() === '预览发料单')!.trigger('click'); await flushPromises()
    await body.get('fieldset[aria-label="用料分配 1"] input[aria-label="放产单号"]').setValue('FC-0001')
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const destination = `${WAREHOUSE_HOME}/fabric-warehouse/inventory?factory=huakang-c`
    await router.push(destination); await flushPromises()
    expect(confirm).toHaveBeenCalledOnce()
    expect(router.currentRoute.value.path).toContain('/overview')
    expect(body.get<HTMLInputElement>('input[aria-label="放产单号"]').element.value).toBe('FC-0001')
    confirm.mockReturnValue(true)
    await router.push(destination); await flushPromises()
    expect(body.find('[role="dialog"]').exists()).toBe(false)
    expect(api.apply).not.toHaveBeenCalled()
  })

  it('retains an explicitly entered zero and protects a numeric-only preview from accidental dismissal', async () => {
    await open(`${WAREHOUSE_HOME}/fabric-warehouse/overview?factory=huakang-c`)
    const body = new DOMWrapper(document.body)
    await wrapper!.findAll('button').find(button => button.text() === '预览收料单')!.trigger('click'); await flushPromises()
    await body.get('input[aria-label="本次实收数量"]').setValue('0')
    await body.findAll('button').find(button => button.text() === '查看填写内容')!.trigger('click')
    const term = body.findAll('dt').find(row => row.text() === '本次实收数量')!
    expect(term.element.nextElementSibling?.textContent).toBe('0')
    await body.get('[aria-label="关闭单据预览"]').trigger('click')
    expect(body.get('[role="alert"]').text()).toContain('清空')
    expect(api.apply).not.toHaveBeenCalled()
  })

  it.each(WAREHOUSES)('$title opens all sections and subviews without implying posted business data', async warehouse => {
    const router = await open(`${WAREHOUSE_HOME}/${warehouse.id}?factory=huakang-c`)
    expect(router.currentRoute.value.path).toBe(warehousePath(warehouse))
    expect(router.currentRoute.value.meta.requiresAuth).toBe(true)
    expect(wrapper!.findAll('.warehouse-rail a')).toHaveLength(warehouse.sections.length)
    for (const section of warehouse.sections) {
      await wrapper!.findAll('.warehouse-rail a').find(link => link.text() === section.title)!.trigger('click')
      await flushPromises()
      expect(wrapper!.get('h1').text()).toBe(section.title)
      for (const [index, view] of section.views.entries()) {
        if (section.views.length > 1) {
          await wrapper!.findAll('.warehouse-tabs button')[index]!.trigger('click')
          await flushPromises()
        }
        if (wrapper!.find('.fabric-procurement').exists()) {
          expect(wrapper!.text()).toContain('采购历史不增加库存')
          expect(wrapper!.find('fieldset[disabled]').exists()).toBe(false)
          continue
        }
        if (wrapper!.find('.warehouse-operations-live').exists()) {
          expect(wrapper!.text()).toMatch(/暂无|还没有实际入库记录/)
          expect(wrapper!.find('tbody').text()).toBe('')
          continue
        }
        if (wrapper!.find('.fabric-receiving-records').exists()) {
          expect(wrapper!.text()).toContain('不含历史库存期初')
          expect(wrapper!.text()).toContain('还没有实际入库记录')
          continue
        }
        if (wrapper!.find('.fabric-master-workspace').exists()) {
          expect(wrapper!.text()).toContain('基础资料已启用')
          expect(wrapper!.findAll('button').some(button => button.text().includes(view.id === 'locations' ? '添加仓库' : '新增资料'))).toBe(true)
          continue
        }
        if (wrapper!.find('.fabric-source-placeholder').exists()) {
          expect(wrapper!.text()).toContain('待接入')
          continue
        }
        expect(wrapper!.get('.warehouse-table-heading h2, .stock-heading h2').text()).toBe(view.title)
        expect(wrapper!.findAll('th').map(th => th.text())).toEqual(view.columns)
        expect(wrapper!.get('.warehouse-empty').text()).toContain('不代表实际数量为零')
        for (const button of wrapper!.findAll('.warehouse-actions button')) expect(button.attributes('disabled')).toBeDefined()
      }
    }
    await wrapper!.get('.warehouse-back').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe(`${WAREHOUSE_HOME}?factory=huakang-c`)
  })

  it('concentrates fabric receiving in five tabs and keeps purchasing outside warehouse navigation', async () => {
    await open(`${WAREHOUSE_HOME}/fabric-warehouse/receipts?factory=huakang-c`)
    expect(wrapper!.findAll('.warehouse-rail a')).toHaveLength(7)
    expect(wrapper!.findAll('.warehouse-rail a').map(link => link.text())).not.toContain('订单管理')
    expect(wrapper!.findAll('.warehouse-tabs button').map(button => button.text())).toEqual(['订单导入', '待收料', '送货单扫描', '入库记录', '采购接口'])
    expect(wrapper!.get('.warehouse-tabs button[aria-pressed=true]').text()).toBe('待收料')
    expect(api.lines).toHaveBeenLastCalledWith('PENDING', '', 0, 'OUTSTANDING', expect.objectContaining({ sort: 'OVERDUE' }))
    await wrapper!.findAll('.warehouse-tabs button').find(button => button.text() === '订单导入')!.trigger('click')
    await flushPromises()
    expect(wrapper!.find('input[type=file]').exists()).toBe(true)
    await wrapper!.findAll('.fabric-import-lookups a').find(link => link.text() === '全部已导入来源（含历史）')!.trigger('click')
    await flushPromises()
    expect(wrapper!.get('.warehouse-table-heading h2, .stock-heading h2').text()).toBe('已导入采购订单')
    expect(api.lines).toHaveBeenLastCalledWith('ALL', '', 0, undefined, expect.any(Object))
    await wrapper!.findAll('.warehouse-tabs button').find(button => button.text() === '订单导入')!.trigger('click')
    await flushPromises()
    expect(wrapper!.find('input[type=file]').exists()).toBe(true)
    await wrapper!.findAll('.fabric-import-lookups a').find(link => link.text() === '查看已回料历史参考')!.trigger('click')
    await flushPromises()
    expect(api.lines).toHaveBeenLastCalledWith('RETURNED', '', 0, undefined, expect.any(Object))
    expect(wrapper!.get('.warehouse-table-heading h2, .stock-heading h2').text()).toBe('已回料历史参考')
    await wrapper!.findAll('.warehouse-tabs button').find(button => button.text() === '入库记录')!.trigger('click')
    await flushPromises()
    expect(wrapper!.find('.fabric-procurement').exists()).toBe(false)
    expect(wrapper!.get('.fabric-receiving-records').text()).toContain('实际入库记录')
    expect(receivingApi.receipts).toHaveBeenLastCalledWith('', 0)
  })

  it.each([
    ['demand', 'pending', undefined, '采购待收料'],
    ['purchases', 'import-review', 'all', '已导入采购订单'],
    ['purchase-history', 'import-review', 'returned', '已回料历史参考'],
  ])('redirects the former fabric orders view %s to receiving', async (oldView, view, source, title) => {
    const router = await open(`${WAREHOUSE_HOME}/fabric-warehouse/orders?factory=huakang-c&view=${oldView}`)
    expect(router.currentRoute.value.path).toBe(`${WAREHOUSE_HOME}/fabric-warehouse/receipts`)
    expect(router.currentRoute.value.query.factory).toBe('huakang-c')
    expect(router.currentRoute.value.query.view).toBe(view)
    expect(router.currentRoute.value.query.source).toBe(source)
    expect(wrapper!.get('.warehouse-table-heading h2, .stock-heading h2').text()).toBe(title)
  })

  it('keeps the former orders redirect inside the explicit warehouse factory boundary', async () => {
    const router = await open(`${WAREHOUSE_HOME}/fabric-warehouse/orders?factory=huakang-d&view=purchases`)
    expect(router.currentRoute.value.path).toBe(WAREHOUSE_HOME)
    expect(wrapper!.find('.warehouse-shell').exists()).toBe(false)
  })

  it('switches warehouses and resets the selected inventory view', async () => {
    const router = await open(`${WAREHOUSE_HOME}/fabric-warehouse/inventory?factory=huakang-c`)
    await wrapper!.findAll('.warehouse-tabs button').find(button => button.text() === '出库记录')!.trigger('click')
    await flushPromises()
    expect(wrapper!.get('.warehouse-table-heading h2, .stock-heading h2').text()).toBe('出库记录')
    await wrapper!.get(`.warehouse-switch a[href="${WAREHOUSE_HOME}/semi-finished-warehouse/overview?factory=huakang-c"]`).trigger('click')
    await flushPromises()
    expect(wrapper!.get('.warehouse-brand').text()).toContain('半成品仓')
    await router.push(`${WAREHOUSE_HOME}/semi-finished-warehouse/inventory?factory=huakang-c`)
    await flushPromises()
    expect(wrapper!.get('.warehouse-table-heading h2, .stock-heading h2').text()).toBe('库存台账')
    expect(wrapper!.text()).toContain('加工发出与在外')
    expect(wrapper!.text()).toContain('包装交接')
    expect(wrapper!.findAll('th').map(th => th.text())).toContain('加工状态')
  })

  it('restores a section view after navigating away and supports refresh, shared URLs and browser back', async () => {
    const router = await open(`${WAREHOUSE_HOME}/semi-finished-warehouse/inventory?factory=huakang-c&view=packaging`)
    expect(wrapper!.get('.warehouse-table-heading h2, .stock-heading h2').text()).toBe('包装交接')
    await wrapper!.findAll('.warehouse-rail a').find(link => link.text() === '订单管理')!.trigger('click')
    await flushPromises()
    await wrapper!.findAll('.warehouse-rail a').find(link => link.text() === '库存管理')!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.view).toBe('packaging')
    expect(wrapper!.get('.warehouse-table-heading h2, .stock-heading h2').text()).toBe('包装交接')
    await wrapper!.get('.warehouse-mobile-view select').setValue('movements')
    await flushPromises()
    expect(router.currentRoute.value.query.view).toBe('movements')
    router.back()
    await flushPromises()
    expect(wrapper!.get('.warehouse-table-heading h2, .stock-heading h2').text()).toBe('包装交接')
    const sharedUrl = router.currentRoute.value.fullPath
    wrapper!.unmount()
    wrapper = undefined
    await open(sharedUrl)
    expect(wrapper!.get('.warehouse-table-heading h2, .stock-heading h2').text()).toBe('包装交接')
  })

  it.each(['not-a-view', 'packaging&view=stock'])('falls back safely for an unknown or ambiguous view: %s', async view => {
    await open(`${WAREHOUSE_HOME}/semi-finished-warehouse/inventory?factory=huakang-c&view=${view}`)
    expect(wrapper!.get('.warehouse-table-heading h2, .stock-heading h2').text()).toBe('库存台账')
  })

  it.each(WAREHOUSES)('$title pending links open the exact business view without creating records', async warehouse => {
    const router = await open(`${warehousePath(warehouse)}?factory=huakang-c`)
    const destinations = wrapper!.findAll('.warehouse-shortcuts a').map(link => link.attributes('href'))
    for (const [index, pending] of warehouse.pending.entries()) {
      await router.push(destinations[index]!)
      await flushPromises()
      expect(router.currentRoute.value.path).toBe(warehousePath(warehouse, pending.section))
      expect(router.currentRoute.value.query.view).toBe(pending.view)
      if (wrapper!.find('.fabric-procurement').exists()) {
        expect(wrapper!.get('.warehouse-table-heading h2, .stock-heading h2').text()).toBe('采购待收料')
        expect(wrapper!.text()).toContain('当前跟进范围没有记录')
        continue
      }
      if (wrapper!.find('.warehouse-operations-live').exists()) {
        expect(wrapper!.text()).toMatch(/暂无|还没有实际入库记录/)
        expect(wrapper!.find('tbody').text()).toBe('')
        continue
      }
      expect(wrapper!.get('.warehouse-table-heading h2, .stock-heading h2').text()).toBe(warehouse.sections.find(section => section.path === pending.section)!.views.find(view => view.id === pending.view)!.title)
      expect(wrapper!.get('fieldset').attributes('disabled')).toBeDefined()
      expect(wrapper!.text()).toContain('业务记录未接入')
      expect(wrapper!.find('tbody')!.text()).toBe('')
    }
  })

  it.each(['', '?factory=group', '?factory=huakang-d', '?factory=huaxing', '?factory=huakang-c&factory=huakang-d'])(
    'does not open a Huakang C warehouse for missing or ambiguous context: %s', async query => {
      const router = await open(`${WAREHOUSE_HOME}/fabric-warehouse/receipts${query}`)
      expect(router.currentRoute.value.path).toBe(WAREHOUSE_HOME)
      expect(wrapper!.find('.warehouse-shell').exists()).toBe(false)
    },
  )
  it('rechecks factory changes on the mounted workspace', async () => {
    const router = await open(`${WAREHOUSE_HOME}/semi-finished-warehouse/inventory?factory=huakang-c`)
    await router.push(`${WAREHOUSE_HOME}/semi-finished-warehouse/inventory?factory=huakang-d`)
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe(`${WAREHOUSE_HOME}?factory=huakang-d`)
    expect(wrapper!.find('.warehouse-shell').exists()).toBe(false)
  })
})

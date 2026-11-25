import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { warehouseOperationsRoutes } from '../routes'
import { WAREHOUSES, WAREHOUSE_HOME, warehousePath } from '../navigation'
import { warehouseOperationsApi, type WarehouseDocument, type WarehouseOperationsWorkspace } from '@/api/warehouseOperations'

vi.mock('@/components/layout/AccountMenu.vue', () => ({ default: { template: '<span>当前账号</span>' } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ currentUser: { id: 'warehouse' }, authorizationVersion: 1 }) }))
const api = vi.hoisted(() => ({
  lines: vi.fn().mockResolvedValue({ total: 0, items: [] }),
  groups: vi.fn().mockResolvedValue({ total: 0, line_total: 0, groups: [] }),
  imports: vi.fn().mockResolvedValue([]),
  apply: vi.fn(),
}))
vi.mock('@/api/fabricProcurement', () => ({ fabricProcurementApi: api }))
vi.mock('@/api/materialHandover', () => ({ handoverApi: () => ({ pendingDeliveries: vi.fn().mockResolvedValue({ total: 0, items: [], stock_totals: [] }) }) }))
const receivingApi = vi.hoisted(() => ({ receipts: vi.fn().mockResolvedValue({ total: 0, items: [] }), stock: vi.fn().mockResolvedValue({ total: 0, items: [] }) }))
vi.mock('@/api/fabricMaster', () => ({ fabricMasterApi: { list: vi.fn().mockResolvedValue({ items: [], total: 0, can_manage: true }), candidates: vi.fn().mockResolvedValue([]) } }))
vi.mock('@/api/fabricReceiving', () => ({ fabricReceivingApi: receivingApi, materialCategoryLabels: { FABRIC: '布料', ACCESSORY: '辅料', THREAD: '线' } }))
vi.mock('@/api/warehouseOperations', () => ({ warehouseOperationsApi: { orderSummary: vi.fn().mockResolvedValue({ rows: [], details: [], totals: [], suppliers: [], basis: '仅已记收发', version: 'test' }), monthly: vi.fn().mockResolvedValue({ parties: [], summary: [], totals: [], details: [], basis: '按业务月份核对', version: 'test' }), workspace: vi.fn().mockResolvedValue({ revision: 0, stock: [], documents: [], order_progress: [], permissions: { read: true, operate: true, quality: false, correct: false } }), post: vi.fn() } }))
vi.mock('@/api/fabricInventorySetup', () => ({ fabricInventorySetupApi: { workspace: vi.fn().mockResolvedValue({ openings: [], counts: [], permissions: { read: true, operate: true, correct: false } }) } }))
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
  it('puts fabric activity search in the shell, isolates other searches and leaves semi activity unchanged', async () => {
    const router = await open(`${WAREHOUSE_HOME}/fabric-warehouse/activity?factory=huakang-c&view=all`)
    expect(wrapper!.get('h1').classes()).toContain('sr-only')
    expect(wrapper!.find('.warehouse-page-heading').exists()).toBe(false)
    expect(wrapper!.find('.fabric-activity-log input[type=search]').exists()).toBe(false)
    await wrapper!.get('[aria-label="查找布料仓操作日志"]').setValue('查找原单')
    await router.push(`${WAREHOUSE_HOME}/fabric-warehouse/exceptions?factory=huakang-c`); await flushPromises()
    expect(wrapper!.get<HTMLInputElement>('[aria-label="查找异常单据与物料"]').element.value).toBe('')
    await router.push(`${WAREHOUSE_HOME}/fabric-warehouse/activity?factory=huakang-c`); await flushPromises()
    expect(wrapper!.get<HTMLInputElement>('[aria-label="查找布料仓操作日志"]').element.value).toBe('查找原单')
    await router.push(`${WAREHOUSE_HOME}/semi-finished-warehouse/activity?factory=huakang-c`); await flushPromises()
    expect(wrapper!.find('.fabric-activity-log').exists()).toBe(false)
    expect(wrapper!.find('[aria-label="查找仓库收发"]').exists()).toBe(true)
  })
  it('falls back from the retired fabric missing-data view and keeps exception search separate from inventory', async () => {
    const router = await open(`${WAREHOUSE_HOME}/fabric-warehouse/exceptions?factory=huakang-c&view=missing`)
    expect(wrapper!.findAll('.warehouse-tabs button').map(button => button.text())).toEqual(['单据更正', '受限库存'])
    expect(wrapper!.get('.warehouse-tabs button[aria-pressed=true]').text()).toBe('单据更正')
    expect(wrapper!.find('[aria-label="查找仓库收发"]').exists()).toBe(false)
    await wrapper!.get('[aria-label="查找异常单据与物料"]').setValue('冲销原因')
    await router.push(`${WAREHOUSE_HOME}/fabric-warehouse/exceptions?factory=huakang-c&view=holds`); await flushPromises()
    expect(wrapper!.find('.stock-search').exists()).toBe(false)
    expect(wrapper!.get<HTMLInputElement>('[aria-label="查找异常单据与物料"]').element.value).toBe('冲销原因')
    await router.push(`${WAREHOUSE_HOME}/fabric-warehouse/inventory?factory=huakang-c&view=stock`); await flushPromises()
    expect(wrapper!.get<HTMLInputElement>('[aria-label="查找库存物料与单据"]').element.value).toBe('')
    await router.push(`${WAREHOUSE_HOME}/semi-finished-warehouse/exceptions?factory=huakang-c`); await flushPromises()
    expect(wrapper!.findAll('.warehouse-tabs button').map(button => button.text())).toEqual(['收发差异', '待补资料', '受限库存'])
  })
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
  it.each(['invalid', 'delivery-scan'])('keeps the fabric header search aligned with fallback and remembered receipt views: %s', async view => {
    const router = await open(`${WAREHOUSE_HOME}/fabric-warehouse/receipts?factory=huakang-c&view=${view}`)
    expect(wrapper!.find('.fabric-header-search input').exists()).toBe(true)
    expect(wrapper!.get('.warehouse-tabs button[aria-pressed=true]').text()).toBe('待收料')
    expect(wrapper!.find('input[aria-label="采购单号筛选"]').exists()).toBe(false)
    await router.push(`${WAREHOUSE_HOME}/fabric-warehouse/receipts?factory=huakang-c&view=history`); await flushPromises()
    expect(wrapper!.get('.fabric-header-search input').attributes('aria-label')).toBe('查找实际入库记录')
    expect(wrapper!.find('.receipt-records-search').exists()).toBe(false)
    await router.push(`${WAREHOUSE_HOME}/fabric-warehouse/receipts?factory=huakang-c`); await flushPromises()
    expect(wrapper!.get('.fabric-header-search input').attributes('aria-label')).toBe('查找实际入库记录')
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
        if (wrapper!.find('.fabric-dashboard, .semi-dashboard').exists()) {
          expect(wrapper!.text()).toContain('今日待办')
          expect(wrapper!.find('.warehouse-operations-live').exists()).toBe(false)
          continue
        }
        if (section.views.length > 1) {
          if (warehouse.id === 'fabric-warehouse' && section.path === 'inventory') await wrapper!.get('[aria-label="选择业务分区"]').setValue(view.id)
          else await wrapper!.findAll('.warehouse-tabs button')[index]!.trigger('click')
          await flushPromises()
        }
        if (wrapper!.find('.fabric-procurement').exists()) {
          if (view.id === 'pending') {
            expect(wrapper!.text()).toContain('按供应商和物料查看待收与复期')
            expect(wrapper!.findAll('a').map(link => link.text())).toContain('送货单入库')
          } else {
            expect(wrapper!.text()).toContain('采购历史不增加库存')
          }
          expect(wrapper!.find('fieldset[disabled]').exists()).toBe(false)
          continue
        }
        if (wrapper!.find('.fabric-subcontract').exists()) {
          expect(wrapper!.get('.fabric-subcontract').attributes('aria-label')).toBe(view.id === 'processors' ? '加工厂资料' : '布料仓委外加工')
          continue
        }
        if (wrapper!.find('.fabric-activity-log').exists()) {
          expect(wrapper!.get('.activity-heading h2').text()).toBe('操作日志')
          expect(wrapper!.text()).toContain('暂无操作日志')
          continue
        }
        if (wrapper!.find('.warehouse-operations-live').exists()) {
          expect(wrapper!.text()).toMatch(/暂无|还没有实际入库记录/)
          expect(wrapper!.find('tbody').text()).toBe('')
          continue
        }
        if (wrapper!.find('.fabric-receiving-records').exists()) {
          expect(wrapper!.text()).toContain('期初、退料、调仓和盘点不计入本页')
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
        if (wrapper!.find('.semi-locations').exists()) {
          expect(wrapper!.get('.semi-locations h2').text()).toBe(view.title)
          expect(wrapper!.get('.semi-locations .warehouse-empty').text()).toContain('建档不会增加库存')
          // Operating permission alone must not permit master-data changes.
          expect(wrapper!.findAll('.semi-locations button').find(button => button.text() === '新增仓库 / 仓位')!.attributes('disabled')).toBeDefined()
          continue
        }
        if (wrapper!.find('.inventory-setup').exists()) {
          expect(wrapper!.get('.setup-heading h2').text()).toBe(view.title)
          expect(wrapper!.text()).not.toContain('当前栏目尚待建设')
          continue
        }
        if (wrapper!.find('.fabric-order-summary').exists()) {
          expect(wrapper!.get('.fabric-order-summary h2').text()).toBe(view.title)
          expect(wrapper!.text()).toContain('当前条件下没有已登记记录')
          expect(wrapper!.get('.order-modes').text()).toContain('调整明细')
          continue
        }
        if (wrapper!.find('.fabric-monthly').exists()) {
          expect(wrapper!.get('.fabric-monthly h2').text()).toBe(view.title)
          expect(wrapper!.text()).toContain('实时数量核对 · 未关账')
          expect(wrapper!.text()).toContain('裁床接口领料 · 待接入')
          expect(wrapper!.find('.warehouse-empty').exists()).toBe(false)
          continue
        }
        if (wrapper!.find('.fabric-closing-pending').exists()) {
          expect(wrapper!.text()).toContain('正式月结确认与历史版本尚未开放')
          expect(wrapper!.find('.warehouse-list-toolbar').exists()).toBe(false)
          expect(wrapper!.get('[aria-label="月结记录关键字筛选"]').attributes('disabled')).toBeDefined()
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

  it('concentrates fabric receiving in four tabs with optional scanning from pending receipts', async () => {
    await open(`${WAREHOUSE_HOME}/fabric-warehouse/receipts?factory=huakang-c`)
    expect(wrapper!.findAll('.warehouse-rail a')).toHaveLength(7)
    expect(wrapper!.findAll('.warehouse-rail a').map(link => link.text())).not.toContain('订单管理')
    expect(wrapper!.findAll('.warehouse-tabs button').map(button => button.text())).toEqual(['订单导入', '待收料', '入库记录', '采购接口'])
    expect(wrapper!.get('.warehouse-tabs button[aria-pressed=true]').text()).toBe('待收料')
    const entryLinks = wrapper!.findAll('.fabric-receiving-actions a')
    expect(entryLinks.map(link => [link.text(), link.attributes('href')])).toEqual([
      ['送货单入库', '/modules/pmc-warehouse/material-handover?factory=huakang-c&tab=documents'],
      ['扫码入库', '/modules/pmc-warehouse/material-handover?factory=huakang-c&tab=scan'],
    ])
    expect(api.apply).not.toHaveBeenCalled()
    expect(api.lines).toHaveBeenLastCalledWith('PENDING', '', 0, 'OUTSTANDING', expect.objectContaining({ sort: 'OVERDUE' }))
    await wrapper!.findAll('.warehouse-tabs button').find(button => button.text() === '订单导入')!.trigger('click')
    await flushPromises()
    expect(wrapper!.find('input[type=file]').exists()).toBe(true)
    expect(wrapper!.find('.fabric-receiving-actions').exists()).toBe(false)
    expect(wrapper!.text()).not.toContain('查看未齐料与变更提醒')
    expect(wrapper!.get('.fabric-import-archive').attributes('open')).toBeUndefined()
    await wrapper!.get('.fabric-import-archive summary').trigger('click')
    await wrapper!.findAll('.fabric-import-lookups a').find(link => link.text() === '查找全部采购资料')!.trigger('click')
    await flushPromises()
    expect(wrapper!.get('.warehouse-table-heading h2, .stock-heading h2').text()).toBe('已导入采购订单')
    expect(api.lines).toHaveBeenLastCalledWith('ALL', '', 0, undefined, expect.any(Object))
    await wrapper!.findAll('.warehouse-tabs button').find(button => button.text() === '订单导入')!.trigger('click')
    await flushPromises()
    expect(wrapper!.find('input[type=file]').exists()).toBe(true)
    await wrapper!.get('.fabric-import-archive summary').trigger('click')
    await wrapper!.findAll('.fabric-import-lookups a').find(link => link.text() === '采购表已回料记录')!.trigger('click')
    await flushPromises()
    expect(api.lines).toHaveBeenLastCalledWith('RETURNED', '', 0, undefined, expect.any(Object))
    expect(wrapper!.get('.warehouse-table-heading h2, .stock-heading h2').text()).toBe('采购表已回料记录')
    expect(wrapper!.get('.warehouse-table-heading p').text()).toContain('不代表仓库实际入库或当前库存')
    await wrapper!.findAll('.warehouse-tabs button').find(button => button.text() === '入库记录')!.trigger('click')
    await flushPromises()
    expect(wrapper!.find('.fabric-procurement').exists()).toBe(false)
    expect(wrapper!.get('.fabric-receiving-records').text()).toContain('实际入库记录')
    expect(receivingApi.receipts).toHaveBeenLastCalledWith('', 0, expect.objectContaining({ sort: 'RECEIPT_DESC' }))
  })

  it.each([
    ['demand', 'pending', undefined, '采购待收料'],
    ['purchases', 'import-review', 'all', '已导入采购订单'],
    ['purchase-history', 'import-review', 'returned', '采购表已回料记录'],
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
    await wrapper!.findAll('.warehouse-tabs button').find(button => button.text() === '收发记录')!.trigger('click')
    await flushPromises()
    await wrapper!.get('[aria-label="收发业务类型"]').setValue('ISSUE')
    await flushPromises()
    expect(wrapper!.get('.warehouse-table-heading h2, .stock-heading h2').text()).toBe('收发记录')
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

  it('uses one record list while retaining deep links and one header search across views', async () => {
    const router = await open(`${WAREHOUSE_HOME}/fabric-warehouse/inventory?factory=huakang-c&view=transfers`)
    const filters = [
      wrapper!.get('.fabric-header-search input'),
      wrapper!.get('[aria-label="收发业务类型"]'),
      wrapper!.get('[aria-label="收发单据状态"]'),
      wrapper!.get('[aria-label="收发记录排序"]'),
      wrapper!.get('[aria-label="选择业务分区"]'),
    ]
    const filterIds = filters.map(field => field.attributes('id'))
    expect(filterIds.every(Boolean)).toBe(true)
    expect(new Set(filterIds).size).toBe(filters.length)
    expect(filters.map(field => field.attributes('name'))).toEqual(['inventory_q', 'record_kind', 'record_state', 'record_sort', 'warehouse_view'])
    expect(wrapper!.findAll('.warehouse-tabs button').map(button => button.text())).toEqual(['库存台账', '委外加工', '订单收发汇总', '收发记录', '领料申请', '期初库存', '库存盘点'])
    expect(wrapper!.get('.warehouse-tabs button[aria-pressed=true]').text()).toBe('收发记录')
    expect(wrapper!.find('.fabric-inventory-record-tabs').exists()).toBe(false)
    expect(wrapper!.get<HTMLSelectElement>('[aria-label="收发业务类型"]').element.value).toBe('TRANSFER')
    expect(wrapper!.get('.warehouse-table-heading h2').text()).toBe('收发记录')
    expect(wrapper!.findAll('[aria-label="选择业务分区"] option').map(option => option.text())).toEqual(['库存台账', '委外加工', '订单收发汇总', '收发记录', '领料申请', '期初库存', '库存盘点'])
    expect(wrapper!.find('[aria-label="查找仓库收发"]').exists()).toBe(false)
    await wrapper!.get('.fabric-header-search input').setValue('布料')
    await router.push(`${WAREHOUSE_HOME}/fabric-warehouse/inventory?factory=huakang-c&view=stock`); await flushPromises()
    expect(wrapper!.find('.stock-search').exists()).toBe(false)
    expect(wrapper!.get<HTMLInputElement>('.fabric-header-search input').element.value).toBe('布料')
    expect(wrapper!.find('.fabric-inventory-record-tabs').exists()).toBe(false)
    await router.push(`${WAREHOUSE_HOME}/fabric-warehouse/inventory?factory=huakang-c&view=order-summary`); await flushPromises()
    expect(wrapper!.find('[aria-label="订单收发关键字"]').exists()).toBe(false)
    expect(wrapper!.get<HTMLInputElement>('.fabric-header-search input').element.value).toBe('布料')
  })

  it.each([['issues', 'ISSUE'], ['transfers', 'TRANSFER'], ['returns', 'RETURN']])('opens legacy %s as a filter and allows clearing or sharing the selected type', async (oldView, kind) => {
    const router = await open(`${WAREHOUSE_HOME}/fabric-warehouse/inventory?factory=huakang-c&view=${oldView}`)
    expect(wrapper!.get<HTMLSelectElement>('[aria-label="收发业务类型"]').element.value).toBe(kind)
    expect(wrapper!.get('.warehouse-tabs button[aria-pressed=true]').text()).toBe('收发记录')
    await wrapper!.get('[aria-label="收发业务类型"]').setValue('RECEIPT'); await flushPromises()
    expect(router.currentRoute.value.query).toMatchObject({factory:'huakang-c',view:'movements',kind:'RECEIPT'})
    await router.push(`${WAREHOUSE_HOME}/fabric-warehouse/inventory?factory=huakang-c&view=movements&kind=RETURN`); await flushPromises()
    expect(wrapper!.get<HTMLSelectElement>('[aria-label="收发业务类型"]').element.value).toBe('RETURN')
    const reset = wrapper!.findAll('button').find(button => button.text() === '重置筛选')!
    const inventorySearch = wrapper!.get<HTMLInputElement>('[aria-label="查找库存物料与单据"]')
    await inventorySearch.setValue('布料')
    reset.element.focus()
    await reset.trigger('click'); await flushPromises()
    expect(router.currentRoute.value.query.kind).toBeUndefined()
    expect(wrapper!.get<HTMLSelectElement>('[aria-label="收发业务类型"]').element.value).toBe('')
    expect(inventorySearch.element.value).toBe('')
    expect(document.activeElement).toBe(inventorySearch.element)
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

  it('opens exact semi dashboard sources and counts only outstanding handoffs', async () => {
    const released = {
      id: 'RELEASE-1', sequence: 1, kind: 'SEMI_RELEASE', business_date: '2026-11-10', occurred_at: '', actor_name: '仓库',
      data: { item_name: '测试头部', item_code: 'ITEM-1', production_no: 'PLAN-1', part: '头', label_code: '2606HK',
        source_no: '原放产单', source_line: '2', unit: '件', quantity: '20', allocations: [] },
    } as WarehouseDocument
    const extraRelease = { ...released, id: 'RELEASE-2', data: { ...released.data, item_name: '测试身体', part: '身体' } }
    const sent = {
      ...released, id: 'SEND-1', kind: 'PROCESS_SEND', consumed_quantity: '12', returned_quantity: '3',
      data: { ...released.data, source_no: '原加工发出单', counterparty: '加工组' },
      batch_snapshot: { unit: '件' },
    } as WarehouseDocument
    const pack = {
      ...released, id: 'PACK-1', kind: 'PACK_SEND', received_quantity: '3.4', returned_quantity: '1.1',
      data: { ...released.data, source_no: '原包装交接单', counterparty: '包装组', quantity: '6.5', unit: '对' },
    } as WarehouseDocument
    const row = { release_id: released.id, received: '10', pending_receipt: '10', extra_received: '0', stock: [], processing: [], packaging: [], document_ids: [] }
    const data: WarehouseOperationsWorkspace = {
      revision: 8, stock: [], permissions: { read: true, operate: true, quality: false, correct: false },
      documents: [pack, { ...pack, id: 'PACK-CLOSED', received_quantity: '5.4' }, { ...pack, id: 'PACK-VOID', reversed: true }, sent, released, extraRelease],
      order_progress: [row, { ...row, release_id: extraRelease.id, received: '23', pending_receipt: '0', extra_received: '3' }],
    }
    const workspace = vi.mocked(warehouseOperationsApi.workspace)
    workspace.mockResolvedValueOnce({ ...data, order_progress: undefined })
    const router = await open(`${WAREHOUSE_HOME}/semi-finished-warehouse/overview?factory=huakang-c`)
    expect(wrapper!.findAll('.warehouse-todo')[0]!.text()).toContain('放产进度不可用')
    expect(wrapper!.findAll('.warehouse-todo')[0]!.find('.warehouse-todo-count').exists()).toBe(false)
    expect(wrapper!.findAll('.warehouse-todo')[1]!.text()).toContain('在外 8 件')
    workspace.mockResolvedValueOnce(data)
    await wrapper!.findAll('.warehouse-dashboard-actions button').find(button => button.text() === '刷新')!.trigger('click')
    await flushPromises()
    const panels = wrapper!.findAll('.warehouse-todo')
    expect(panels.map(panel => panel.get('h3').text())).toEqual(['待收货', '加工在外', '包装待签收', '实收超计划'])
    expect(panels.map(panel => panel.get('.warehouse-todo-count').text())).toEqual(['1 项', '1 笔', '1 笔', '1 项'])
    expect(panels[1]!.text()).toContain('在外 8 件')
    expect(panels[2]!.text()).toContain('待签 2.0 对')
    const [receipt, processing, packaging, extra] = panels.map(panel => panel.get('.warehouse-todo-row').attributes('href'))
    const body = new DOMWrapper(document.body)

    workspace.mockResolvedValueOnce(data)
    await router.push(receipt!); await flushPromises()
    expect(router.currentRoute.value.query).toMatchObject({ view: 'pending', release: released.id })
    expect(body.get('[role="dialog"]').text()).toContain('原放产单 / 2')
    expect(wrapper!.get('tbody').text()).not.toContain('测试身体')

    workspace.mockResolvedValueOnce(data)
    await router.push(processing!); await flushPromises()
    expect(router.currentRoute.value.query).toMatchObject({ view: 'processing', followup: 'pending', record: sent.id })
    expect(body.get('[role="dialog"]').text()).toContain('原加工发出单')

    workspace.mockResolvedValueOnce(data)
    await router.push(packaging!); await flushPromises()
    expect(wrapper!.get('tbody').findAll('tr')).toHaveLength(1)
    expect(body.get('[role="dialog"]').text()).toContain('原包装交接单')
    await body.get('[role="dialog"]').findAll('button').find(button => button.text() === '代录签收')!.trigger('click')
    const original = body.get<HTMLSelectElement>('form [aria-label="关联原单"]')
    expect(original.element.value).toBe(pack.id)
    expect(original.element.disabled).toBe(true)
    await body.get('form').findAll('button').find(button => button.text() === '关闭')!.trigger('click')

    workspace.mockResolvedValueOnce(data)
    await router.push(extra!); await flushPromises()
    expect(router.currentRoute.value.query).toMatchObject({ view: 'progress', receipt_progress: 'extra', release: extraRelease.id })
    expect(wrapper!.get('tbody').text()).toContain('超收 3 件')
    expect(body.get('[role="dialog"]').text()).toContain('测试身体')
    expect(warehouseOperationsApi.post).not.toHaveBeenCalled()
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

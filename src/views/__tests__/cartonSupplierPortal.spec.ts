import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Blob as NodeBlob } from 'node:buffer'
import { reactive } from 'vue'
import CartonSupplierView from '../CartonSupplierView.vue'
import CartonSupplierReceiving from '@/components/CartonSupplierReceiving.vue'
import CartonSupplierMarkTemplatesView from '../CartonSupplierMarkTemplatesView.vue'
import CartonReceiptAllocations from '@/components/CartonReceiptAllocations.vue'
import CartonActionNotice from '@/components/CartonActionNotice.vue'
import type { PortalWorkspace, SupplierMarkAsset } from '@/api/cartonSupplierPortal'
import type { SpecialRequest } from '@/api/cartonSpecialRequests'
import type { SupplierChangeTask } from '@/api/cartonSupplierChanges'
import type { MaterialCorrection } from '@/api/cartonMaterialCorrection'
import CartonSupplierChangeTasks from '@/components/CartonSupplierChangeTasks.vue'
import CartonPriceReviews from '@/components/CartonPriceReviews.vue'
import type { CartonPriceReview } from '@/api/cartonPriceReviews'
const changesApi = vi.hoisted(() => ({ list: vi.fn(), respond: vi.fn() }))
vi.mock('@/api/cartonSupplierChanges', () => ({ cartonSupplierChangesApi: changesApi }))
const specialApi = vi.hoisted(() => ({ factories: vi.fn(), list: vi.fn(), detail: vi.fn() }))
vi.mock('@/api/cartonSpecialRequests', () => ({ cartonSpecialRequestsApi: specialApi }))
const unifiedApi = vi.hoisted(() => ({ list: vi.fn(), receive: vi.fn(), dispatch: vi.fn() }))
vi.mock('@/api/cartonUnifiedDeliveries', async importOriginal => ({ ...await importOriginal<typeof import('@/api/cartonUnifiedDeliveries')>(), cartonUnifiedDeliveriesApi: unifiedApi }))
const priceApi = vi.hoisted(() => ({ list: vi.fn(), propose: vi.fn(), decide: vi.fn() }))
vi.mock('@/api/cartonPriceReviews', () => ({ cartonPriceReviewsApi: priceApi }))
const api = vi.hoisted(() => ({ acknowledgeCancellation: vi.fn(), changeNonArrival: vi.fn(), memberships: vi.fn(), workspace: vi.fn(), accept: vi.fn(), acceptBatch: vi.fn(), ship: vi.fn(), previewDeliveryImport: vi.fn(), confirmDeliveryImport: vi.fn(), receiptOptions: vi.fn(), linkReceipt: vi.fn(), receive: vi.fn(), linkSampleReceipt: vi.fn(), linkShipmentLine: vi.fn(), members: vi.fn(), member: vi.fn(), upload: vi.fn(), download: vi.fn(), markAssets: vi.fn(), markUploadOrders: vi.fn(), uploadMarkAssets: vi.fn(), markChecks: vi.fn(), createMarkCheck: vi.fn(), downloadMarkCheck: vi.fn(), previewMarkCheckUrl: vi.fn(), downloadMarkAsset: vi.fn(), previewMarkAssetUrl: vi.fn(), markTemplates: vi.fn(), downloadMarkDocument: vi.fn(), previewMarkPdfUrl: vi.fn(), documents: vi.fn(), activity: vi.fn(), activityPage: vi.fn(), exportDocuments: vi.fn(), exportOrderImport: vi.fn() }))
const router = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn() }))
const routeState = vi.hoisted(() => ({ query: { factory: 'huaxing', shipment: undefined } as Record<string, string | undefined> }))
const can = vi.hoisted(() => vi.fn((_permission: string, _factory?: string, _department?: string) => true))
type TestUser = { id: string; display_name: string; identity?: { effective_context_key: string; employment_epoch: number } }
const authState = reactive({ currentUser: { id: 'supplier-test', display_name: '供应商' } as TestUser | null,
  authorizationVersion: 1, sessionVersion: 1, authzMode: 'legacy' })
vi.mock('@/api/cartonSupplierPortal', () => ({ cartonSupplierPortalApi: api }))
vi.mock('@/api/cartonPositions', () => ({ cartonPositionsApi: { locations: vi.fn(async () => [{ id: 'BIN-A', factory_id: 'huaxing', warehouse: 'A', bin_code: '01', label: 'A / 01', status: 'ACTIVE' }]) } }))
vi.mock('@/api/cartonProcurement', () => ({ cartonProcurementApi: { listCustomers: vi.fn(async () => [{ customer_code: 'DICKIE', customer_name: 'Dickie', status: 'ACTIVE' }]) } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ can: (permission: string, factory?: string, department?: string) => {
  void authState.sessionVersion
  return authState.currentUser !== null && can(permission, factory, department)
},
  get currentUser() { return authState.currentUser }, get authorizationVersion() { return authState.authorizationVersion },
  get sessionVersion() { return authState.sessionVersion }, get authzMode() { return authState.authzMode } }) }))
vi.mock('@/stores/app', () => ({ useAppStore: () => ({ activeProductionFactory: { id: 'huaxing' } }) }))
vi.mock('vue-router', () => ({ useRoute: () => routeState, useRouter: () => router, RouterLink: { name: 'RouterLink', props: ['to'], template: '<a><slot /></a>' } }))
function fixture(): PortalWorkspace {
  return { factory_id: 'huaxing', supplier_name: '河源东康', orders: [{ id: 'ORDER-A', order_no: 'ORDER-A', customer_name: 'Dickie', contract_no: 'SC-A', customer_po: 'PO-A', item_no: 'ITEM-A', product_name: '产品', status: 'PENDING_SUPPLIER', issue_id: 'ISSUE-A', document_no: 'ORDER-A-P00', order_date: '2026-09-10', planned_date: '2026-09-25', awaiting_issue: false, attachments: [], lines: ['外箱', '平卡'].map((name, index) => ({ id: `LINE-${index}`, line_no: index+1, child_no: `ORDER-A/0${index+1}`, packaging_type: name, paper_quality: 'A33', specification: '10*20', dimension_unit: 'cm', unit: index ? '张' : '个', required_quantity: '100', received_quantity: '0', in_transit_quantity: '0', remaining_to_ship: '100', accepted: true, commitment_revision: 1, promised_date: '2026-09-25' })) }], shipments: [{ id: 'SHIP-A', delivery_note_no: 'DN-A', delivery_date: '2026-09-21', status: 'SENT', revision: 1, created_at: '', confirmed_at: '', acceptance_date: null, acceptance_lines: [], lines: [0,1].map(index => ({ id: `SL-${index}`, order_line_id: `LINE-${index}`, order_no: 'ORDER-A', contract_no: 'SC-A', customer_po: 'PO-A', item_no: 'ITEM-A', customer_name: 'Dickie', child_no: `ORDER-A/0${index+1}`, packaging_type: index ? '平卡' : '外箱', paper_quality: 'A33', specification: '10*20', unit: '个', quantity: '10', unit_price: '2', delivery_unit_price: '2', currency: 'CNY' })) }] }
}
const options = { global: { stubs: { AccountMenu: true, NotificationCenter: true, RouterLink: { template: '<a><slot /></a>' }, CartonReceiptAllocations: true } } }

describe('supplier order carton-mark access', () => {
  function mark(id: string, overrides: Partial<SupplierMarkAsset> = {}): SupplierMarkAsset {
    return { id, revision: 1, file_name: `${id}.pdf`, kind: 'pdf', size_bytes: 400,
      contract_number: 'SC-A', created_at: '2026-10-16',
      orders: [{ id: 'ORDER-A', issue_id: 'ISSUE-A', customer_name: 'Dickie', contract_no: 'SC-A', customer_po: 'PO-A', item_no: 'ITEM-A' }], ...overrides }
  }
  const badge = (wrapper: ReturnType<typeof mount>, order = 'ORDER-A') => wrapper.get(`[aria-label="查看订单 ${order} 箱唛资料"]`)

  it('opens the matching originals from the ledger and existing detail action without loading them on hover', async () => {
    const pdf = mark('print'), excel = mark('source', { file_name: 'source.xlsx', kind: 'excel' })
    const other = mark('other-order', { orders: [{ ...pdf.orders[0]!, id: 'ORDER-B' }] })
    const obsolete = mark('old-issue', { orders: [{ ...pdf.orders[0]!, issue_id: 'OLD' }] })
    api.markAssets.mockResolvedValue([pdf, excel, other, obsolete])
    api.downloadMarkAsset.mockRejectedValueOnce(new Error('请稍后重试'))
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.get('thead').text()).toContain('箱唛资料')
    expect(badge(wrapper).text()).toBe('已绑定 2 份')
    expect(api.markAssets).toHaveBeenCalledTimes(1)
    const detail = wrapper.get('[aria-label="查看订单 ORDER-A 明细"]')
    await detail.trigger('mouseenter'); await flushPromises()
    expect(wrapper.find('[data-testid="supplier-order-marks"]').exists()).toBe(false)
    expect(api.markAssets).toHaveBeenCalledTimes(1)
    await detail.trigger('mouseleave')
    await badge(wrapper).trigger('click'); await flushPromises()
    const files = wrapper.get('[data-testid="supplier-order-marks"]')
    expect(files.text()).toContain('print.pdf')
    expect(files.text()).toContain('source.xlsx')
    expect(files.text()).not.toContain('other-order.pdf')
    expect(files.text()).not.toContain('old-issue.pdf')
    expect(files.get('[aria-label="预览 print.pdf"]').attributes('href')).toBe('/api/preview.pdf')
    expect(files.find('[aria-label="预览 source.xlsx"]').exists()).toBe(false)
    await files.get('[aria-label="下载 print.pdf"]').trigger('click'); await flushPromises()
    expect(api.downloadMarkAsset).toHaveBeenCalledWith('print', 'huaxing', expect.any(AbortSignal))
    expect(files.get('[role="alert"]').text()).toContain('请稍后重试')
    await wrapper.get('[aria-label="关闭供应商订单明细"]').trigger('click')
    await detail.trigger('click'); await flushPromises()
    expect(wrapper.get('[data-testid="supplier-order-marks"]').text()).toContain('print.pdf')
    expect(api.uploadMarkAssets).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('counts files per factory and current issue, keeping historical-only associations distinct from unbound', async () => {
    api.memberships.mockResolvedValue([{ factory_id: 'huaxing' }, { factory_id: 'huakang-a' }])
    api.workspace.mockImplementation(async factory => {
      const data = fixture(); data.factory_id = factory
      data.orders[0]!.id = factory === 'huaxing' ? 'ORDER-A' : 'ORDER-B'
      data.orders[0]!.order_no = data.orders[0]!.id
      return data
    })
    api.markAssets.mockImplementation(async factory => factory === 'huaxing'
      ? [mark('history', { workflow: { status: 'HISTORY', version: 1 } as SupplierMarkAsset['workflow'] })]
      : [mark('other-factory'), mark('old-version', { orders: [{ ...mark('x').orders[0]!, id: 'ORDER-B', issue_id: 'OLD' }] })])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(badge(wrapper).text()).toBe('仅历史资料 1 份')
    expect(badge(wrapper, 'ORDER-B').text()).toBe('未绑定')
    await badge(wrapper).trigger('click'); await flushPromises()
    const files = wrapper.get('[data-testid="supplier-order-marks"]')
    expect(files.find('[aria-label="下载 history.pdf"]').exists()).toBe(false)
    await files.findAll('button').find(button => button.text().includes('历史版本'))!.trigger('click')
    expect(files.find('[aria-label="下载 history.pdf"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('keeps order rows usable while mark lookup is pending or fails, and recovers on refresh', async () => {
    let reject!: (error: Error) => void
    api.markAssets.mockReturnValueOnce(new Promise((_resolve, fail) => { reject = fail }))
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(badge(wrapper).text()).toBe('查询中…')
    reject(new Error('资料服务暂不可用')); await flushPromises()
    expect(badge(wrapper).text()).toBe('资料查询失败')
    expect(badge(wrapper).attributes('title')).toContain('资料服务暂不可用')
    api.markAssets.mockResolvedValue([mark('recovered')])
    await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click'); await flushPromises()
    expect(badge(wrapper).text()).toBe('已绑定 1 份')
    wrapper.unmount()
  })

  it('discards late mark metadata after logout', async () => {
    let resolve!: (assets: SupplierMarkAsset[]) => void
    api.markAssets.mockReturnValueOnce(new Promise(done => { resolve = done }))
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    const signal = api.markAssets.mock.calls[0]![1] as AbortSignal
    authState.currentUser = null; authState.sessionVersion++; await flushPromises()
    expect(signal.aborted).toBe(true)
    resolve([mark('private-file')]); await flushPromises()
    expect(wrapper.find('[aria-label="查看订单 ORDER-A 箱唛资料"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('已绑定')
    wrapper.unmount()
  })
})

describe('supplier workspace shared header search', () => {
  async function tab(wrapper: ReturnType<typeof mount>, label: string) {
    await wrapper.get('nav[aria-label="供应商协同功能"]').findAll('button').find(button => button.text().includes(label))!.trigger('click')
    await flushPromises()
  }
  const keyword = (wrapper: ReturnType<typeof mount>) => wrapper.get<HTMLInputElement>('input[aria-label="顶部搜索"]')

  it('filters orders from the separate header search row and clears it with the original toolbar', async () => {
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(keyword(wrapper).element.closest('header')).not.toBeNull()
    expect(wrapper.findAll('header input')).toHaveLength(1)
    expect(wrapper.findAll('input[aria-label="顶部搜索"]')).toHaveLength(1)
    await keyword(wrapper).setValue('UNMATCHED')
    expect(wrapper.find('[aria-label="查看订单 ORDER-A 明细"]').exists()).toBe(false)
    await wrapper.findAll('button').find(button => button.text() === '清空筛选')!.trigger('click')
    expect(keyword(wrapper).element.value).toBe('')
    expect(wrapper.find('[aria-label="查看订单 ORDER-A 明细"]').exists()).toBe(true)
    expect(api.acceptBatch).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps separate keywords through tab navigation and routine same-account refresh', async () => {
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await keyword(wrapper).setValue('SC-A')
    await tab(wrapper, '发货与仓库反馈')
    expect(keyword(wrapper).element.value).toBe('')
    expect(wrapper.find('[aria-label="顶部搜索"]').exists()).toBe(true)
    await keyword(wrapper).setValue('DN-A')
    await tab(wrapper, '采购单与送货单')
    expect(keyword(wrapper).element.value).toBe('')
    expect(wrapper.find('[aria-label="顶部搜索"]').exists()).toBe(true)
    await keyword(wrapper).setValue('DOCUMENT')
    await tab(wrapper, '操作日志')
    expect(keyword(wrapper).element.value).toBe('')
    expect(wrapper.find('[aria-label="顶部搜索"]').exists()).toBe(true)
    await keyword(wrapper).setValue('供应商')
    await tab(wrapper, '订单管理')
    authState.currentUser = { ...authState.currentUser!, display_name: '供应商新显示名' }
    authState.sessionVersion++
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click'); await flushPromises()
    expect(keyword(wrapper).element.value).toBe('SC-A')
    await tab(wrapper, '发货与仓库反馈'); expect(keyword(wrapper).element.value).toBe('DN-A')
    await tab(wrapper, '采购单与送货单'); expect(keyword(wrapper).element.value).toBe('DOCUMENT')
    await tab(wrapper, '操作日志'); expect(keyword(wrapper).element.value).toBe('供应商')
    wrapper.unmount()
  })

  it.each([
    ['account', () => { authState.currentUser = { id: 'other-user', display_name: '其他人' } }],
    ['logout', () => { authState.currentUser = null }],
    ['authorization version', () => { authState.authorizationVersion++ }],
    ['authorization mode', () => { authState.authzMode = 'enforce' }],
    ['identity context', () => { authState.currentUser!.identity!.effective_context_key = 'new-context' }],
    ['employment epoch', () => { authState.currentUser!.identity!.employment_epoch++ }],
    ['permission revocation', () => { can.mockReturnValue(false) }],
  ] as [string, () => void][])('clears or hides each page keyword after a real %s change', async (_label, change) => {
    authState.currentUser!.identity = { effective_context_key: 'original', employment_epoch: 1 }
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    for (const label of ['订单管理', '发货与仓库反馈', '采购单与送货单', '操作日志']) {
      await tab(wrapper, label); await keyword(wrapper).setValue(`private-${label}`)
    }
    change(); authState.sessionVersion++; await flushPromises()
    for (const label of ['订单管理', '发货与仓库反馈', '采购单与送货单', '操作日志']) {
      await tab(wrapper, label)
      expect(wrapper.findAll<HTMLInputElement>('input').every(input => !input.element.value.startsWith('private-'))).toBe(true)
    }
    wrapper.unmount()
  })

  it('clears shipment keywords and local filters without changing the selected sort', async () => {
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await tab(wrapper, '发货与仓库反馈')
    await keyword(wrapper).setValue('UNMATCHED')
    await wrapper.get('[aria-label="送货单排序"]').setValue('ASC')
    expect(wrapper.text()).toContain('暂无符合条件的发货单')
    await wrapper.findAll('button').find(button => button.text() === '清除筛选')!.trigger('click')
    expect(keyword(wrapper).element.value).toBe('')
    expect(wrapper.get<HTMLSelectElement>('[aria-label="送货单排序"]').element.value).toBe('ASC')
    expect(wrapper.text()).toContain('DN-A')
    expect(api.confirmDeliveryImport).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('uses the document keyword to filter the original rows and clears it with document filters', async () => {
    api.documents.mockResolvedValue(['DOC-A', 'DOC-B'].map((document_no, index) => ({ id: `ISSUE-${index}`, kind: 'PURCHASE', factory_id: 'huaxing', document_no, document_type: 'FIRST', date: '2026-09-25', created_at: '', status: '已生成', replenishment: false, export_count: 0, orders: [], lines: [] })))
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await tab(wrapper, '采购单与送货单')
    await keyword(wrapper).setValue('DOC-B')
    expect(wrapper.find('[aria-label="查看单据 DOC-A 明细"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="查看单据 DOC-B 明细"]').exists()).toBe(true)
    await wrapper.findAll('button').find(button => button.text() === '清空筛选')!.trigger('click')
    expect(keyword(wrapper).element.value).toBe('')
    expect(wrapper.find('[aria-label="查看单据 DOC-A 明细"]').exists()).toBe(true)
    expect(api.exportDocuments).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('queries the supplier audit API from the local field after debounce and clears it through audit filters', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const wrapper = mount(CartonSupplierView, options)
    try {
      await flushPromises(); await tab(wrapper, '操作日志')
      await keyword(wrapper).setValue('DN-A')
      await vi.advanceTimersByTimeAsync(200); await flushPromises()
      expect(api.activityPage).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'DN-A', offset: 0, limit: 50 }))
      await wrapper.findAll('button').find(button => button.text() === '清除筛选')!.trigger('click')
      expect(keyword(wrapper).element.value).toBe('')
      await vi.advanceTimersByTimeAsync(200); await flushPromises()
      expect(api.activityPage).toHaveBeenLastCalledWith(expect.objectContaining({ search: '', offset: 0 }))
    } finally { wrapper.unmount(); vi.useRealTimers() }
  })

  it('cancels an audit query on logout without a page-reset request under the obsolete scope', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    api.activityPage.mockResolvedValue({ items: [], total: 101, limit: 50, offset: 0 })
    const wrapper = mount(CartonSupplierView, options)
    try {
      await flushPromises(); await tab(wrapper, '操作日志')
      await keyword(wrapper).setValue('private-reference')
      await vi.advanceTimersByTimeAsync(200); await flushPromises()
      await wrapper.findAll('button').find(button => button.text() === '下一页')!.trigger('click'); await flushPromises()
      expect(api.activityPage).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'private-reference', offset: 50 }))
      await keyword(wrapper).setValue('next-private-reference')
      const requestCount = api.activityPage.mock.calls.length
      authState.currentUser = null; authState.sessionVersion++; await flushPromises()
      await vi.advanceTimersByTimeAsync(200); await flushPromises()
      expect(wrapper.find('input[aria-label="搜索供应商操作日志"]').exists()).toBe(false)
      expect(api.activityPage).toHaveBeenCalledTimes(requestCount)
    } finally { wrapper.unmount(); vi.useRealTimers() }
  })
})

describe('supplier purchase acceptance reminders', () => {
  it.each(['PENDING', 'PARTIAL', 'HISTORICAL', 'MANUAL'])('requires an explicit export decision for %s documents', async status => {
    const purchase = { id: 'ISSUE-A', kind: 'PURCHASE', factory_id: 'huaxing', document_no: 'DOC-A', document_type: 'FIRST',
      date: '2026-09-25', created_at: '', status: '已生成', replenishment: false, export_count: 0, orders: [], lines: [],
      supplier_acceptance: { status, label: '接单需核实', accepted_line_count: 0, total_line_count: 2 } }
    api.documents.mockResolvedValue([purchase])
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '采购单与送货单')!.trigger('click'); await flushPromises()
    expect(wrapper.get('[aria-label="DOC-A 接单状态"]').text()).toContain('接单需核实')
    await wrapper.get('[aria-label="选择单据 DOC-A"]').setValue(true)
    const exporter = wrapper.findAll('button').find(button => button.text().startsWith('导出东康导入模板'))!
    await exporter.trigger('click'); await flushPromises()
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('导出不会自动接单'))
    expect(api.exportOrderImport).not.toHaveBeenCalled()
    confirm.mockReturnValue(true)
    await exporter.trigger('click'); await flushPromises()
    expect(api.exportOrderImport).toHaveBeenCalledWith([purchase], true)
    wrapper.unmount(); confirm.mockRestore()
  })

  it('shows accepted date differences and warns immediately when entering a new promise', async () => {
    const work = fixture()
    work.orders[0]!.lines[0]!.promised_date = '2026-09-27'
    work.orders[0]!.lines[1]!.accepted = false
    api.workspace.mockResolvedValue(work)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.text()).toContain('较我方计划 2026-09-25 延后 2 天')
    await wrapper.get('[aria-label="确认订单 ORDER-A 接单"]').trigger('click')
    await wrapper.get('[aria-label="ORDER-A/02 承诺交期"]').setValue('2026-09-24')
    expect(wrapper.text()).toContain('较我方计划 2026-09-25 提前 1 天')
    expect(api.accept).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
const guideOptions = { global: { stubs: { ...options.global.stubs,
  CartonSupplierMonthlyReview: true,
  CartonUsageGuide: { name: 'CartonUsageGuide', props: ['audience', 'factoryName'], emits: ['close', 'supplierNavigate'], template: '<section data-testid="supplier-usage-guide" />' },
} } }
it('opens supplier published price corrections from monthly review in the exact factory and clears the panel on actor change', async () => {
  routeState.query.settlement_view = undefined
  const w = mount(CartonSupplierView, { global: { stubs: { ...guideOptions.global.stubs, CartonPriceCorrectionDialog: true, CartonSupplierChangeTasks: true } } }); await flushPromises()
  try {
    await w.findAll('button').find(row => row.text() === '月结对账')!.trigger('click'); await flushPromises()
    w.findComponent({ name: 'CartonSupplierMonthlyReview' }).vm.$emit('prices', 'huaxing'); await flushPromises()
    const panel = w.findComponent({ name: 'CartonPriceCorrectionDialog' }); expect(panel.props('factoryId')).toBe('huaxing'); expect(panel.props('internal')).not.toBe(true); expect(panel.props('factories')).toMatchObject([{ factory_id: 'huaxing' }])
    authState.currentUser = { id: 'another-supplier', display_name: '其他供应商' }; await flushPromises()
    expect(w.findComponent({ name: 'CartonPriceCorrectionDialog' }).exists()).toBe(false)
  } finally { w.unmount(); routeState.query.settlement_view = undefined }
})
it('opens supplier payable receipts with the authorized factory list and an independent keyword', async () => {
  routeState.query.settlement_view = undefined
  const w = mount(CartonSupplierView, { global: { stubs: { ...guideOptions.global.stubs, CartonSupplierReturns: true, CartonSupplierChangeTasks: true, CartonPayables: true } } }); await flushPromises()
  try {
    await w.findAll('button').find(row => row.text() === '月结对账')!.trigger('click'); await flushPromises()
    await w.findAll('button').find(row => row.text() === '应付与收款')!.trigger('click'); await flushPromises()
    const panel = w.findComponent({ name: 'CartonPayables' })
    expect(panel.props('internal')).toBe(false); expect(panel.props('factories')).toMatchObject([{ factory_id: 'huaxing' }])
    expect(router.replace).toHaveBeenCalledWith({ query: expect.objectContaining({ settlement_view: 'payables' }) })
    await w.get('[aria-label="顶部搜索"]').setValue('BANK-RECEIVED1'); expect(panel.props('search')).toBe('BANK-RECEIVED1')
    await w.findAll('button').find(row => row.text() === '双方月结对账')!.trigger('click'); await flushPromises()
    expect(w.findComponent({ name: 'CartonSupplierMonthlyReview' }).props('search')).toBe('')
  } finally { w.unmount(); routeState.query.settlement_view = undefined }
})
it('discovers return collaboration from supplier todos and keeps the return search separate from monthly review', async () => {
  const wrapper = mount(CartonSupplierView, { global: { stubs: { ...guideOptions.global.stubs, CartonSupplierReturns: true, CartonSupplierChangeTasks: true } } }); await flushPromises()
  await wrapper.findAll('button').find(item => item.text() === '查看退货签收与退款待办 →')!.trigger('click'); await flushPromises()
  expect(wrapper.get('[aria-label="供应商月结子页面"]').text()).toContain('退货签收与退款')
  const panel = wrapper.findComponent({ name: 'CartonSupplierReturns' })
  expect(panel.exists()).toBe(true); expect(panel.props('factories')).toMatchObject([{ factory_id: 'huaxing' }])
  expect(router.replace).toHaveBeenCalledWith({ query: expect.objectContaining({ settlement_view: 'returns' }) })
  await wrapper.get('[aria-label="顶部搜索"]').setValue('RETURN-SEARCH')
  expect(panel.props('search')).toBe('RETURN-SEARCH')
  await wrapper.findAll('button').find(item => item.text() === '双方月结对账')!.trigger('click'); await flushPromises()
  expect(wrapper.findComponent({ name: 'CartonSupplierMonthlyReview' }).props('search')).toBe('')
  wrapper.unmount()
})
beforeEach(() => { routeState.query.shipment = undefined; vi.resetAllMocks(); can.mockReturnValue(true); api.memberships.mockResolvedValue([{ factory_id: 'huaxing', supplier_name: '河源东康' }]); api.workspace.mockResolvedValue(fixture()); api.members.mockResolvedValue([]); api.ship.mockResolvedValue({ id: 'NEW' }); api.previewDeliveryImport.mockResolvedValue({ filename: '送货明细表.xlsx', sha256: 'abc', row_count: 1, groups: [{ factory_id: 'huaxing', destination: '华兴', delivery_note_no: 'DN-NEW', delivery_date: '2026-09-24', ready: true, issues: [], rows: [{ source_sheet: '送货明细', source_row: 2, contract_no: 'SC-A', item_no: 'ITEM-A', packaging_type: '外箱', paper_quality: 'A33', specification: '10*20', delivered_quantity: 4, order_no: 'ORDER-A', child_no: 'ORDER-A/01', order_line_id: 'LINE-0', issue_id: 'ISSUE-A', status: 'READY', reason: '已匹配' }] }] }); api.confirmDeliveryImport.mockResolvedValue({ shipments: [{ id: 'NEW' }] }); api.acceptBatch.mockResolvedValue({ order_ids: [] }); api.documents.mockResolvedValue([]); api.activityPage.mockResolvedValue({ items: [{ id: 'ACT1', factory_id: 'huaxing', action: '送货单已登记', created_at: '2026-09-25', reference_no: 'DN-1', actor_name: '供应商' }], total: 1, limit: 50, offset: 0 }); api.activity.mockResolvedValue([]); api.exportDocuments.mockResolvedValue(undefined); api.exportOrderImport.mockResolvedValue(undefined); api.receiptOptions.mockResolvedValue([]); api.linkReceipt.mockResolvedValue({ id: 'SHIP-A' }); api.receive.mockResolvedValue({ id: 'SHIP-A' }); api.linkSampleReceipt.mockResolvedValue({ receipt_line_id: 'RL-SAMPLE', order_line_id: 'LINE-0', order_no: 'ORDER-A', quantity: '4' }); api.markUploadOrders.mockResolvedValue([]); api.uploadMarkAssets.mockResolvedValue([]); api.markAssets.mockResolvedValue([]); api.markChecks.mockResolvedValue([]); api.previewMarkCheckUrl.mockReturnValue("/api/check.pdf"); api.previewMarkAssetUrl.mockReturnValue('/api/preview.pdf'); api.markTemplates.mockResolvedValue([]); api.previewMarkPdfUrl.mockReturnValue('/api/preview.pdf') })

beforeEach(() => {
  unifiedApi.list.mockImplementation(async (factory: string) => {
    await Promise.resolve()
    const callIndex = api.workspace.mock.calls.findLastIndex(call => call[0] === factory)
    const data = await api.workspace.mock.results[callIndex]?.value || fixture()
    return { items: (data.shipments || []).map((formal: PortalWorkspace['shipments'][number]) => ({ ...formal, id: `FORMAL:${formal.id}`, factory_id: factory, formal, special: [], receipts: formal.acceptance_history || [], lines: formal.lines.map(line => ({ ...line, source_kind: 'FORMAL', receivable_quantity: line.receivable_quantity ?? line.quantity })), can_operate: true })), total: data.shipments?.length || 0 }
  })
})
beforeEach(() => {
  routeState.query.factory = 'huaxing'; delete routeState.query.special_request
  priceApi.list.mockResolvedValue([])
  priceApi.decide.mockResolvedValue({})
  changesApi.list.mockResolvedValue({ items: [], pending_count: 0, overdue_count: 0, disputed_count: 0 })
  changesApi.respond.mockResolvedValue({})
  specialApi.factories.mockResolvedValue([])
  specialApi.list.mockResolvedValue({ items: [], total: 0, can_create: false })
  authState.currentUser = { id: 'supplier-test', display_name: '供应商' }
  authState.authorizationVersion = 1; authState.sessionVersion = 1; authState.authzMode = 'legacy'
})

describe('combined supplier order ledger', () => {
  function special(patch: Partial<SpecialRequest> = {}): SpecialRequest {
    return { id: 'SPECIAL-1', request_no: 'SP-1', factory_id: 'huaxing', kind: 'SAMPLE', title: '', requester_name: '需求员工',
      status: 'SENT', revision: 2, current_version_id: 'V1', quote_version_id: '', pricing_kind: 'PENDING_QUOTE', promised_date: '',
      supplier_confirmation: { version_id: 'V1', status: 'ACCEPTED', promised_date: '2026-10-25', reason: '', responded_at: '', responded_by: '' },
      customer_code: '', customer_name: '', workshop_id: '', purpose: '', required_date: '2026-10-25', created_at: '2026-10-19 12:00:00',
      lines: [{ id: 'L1', packaging_type: '样板外箱', paper_quality: 'A=B', specification: '10*20*30', dimension_unit: 'cm', quantity: '5', unit: '个', item_no: '' }],
      shipments: [], attachments: [], messages: [], history: [], permissions: { can_ship: true }, ...patch }
  }
  function supply(items: SpecialRequest[]) {
    specialApi.factories.mockResolvedValue([{ factory_id: 'huaxing', supplier_name: '河源东康' }])
    specialApi.list.mockResolvedValue({ items, total: items.length, can_create: true })
    specialApi.detail.mockImplementation(async (_factory, id) => items.find(item => item.id === id))
  }
  it('shows purchases, samples and miscellaneous requests in one table with a type filter', async () => {
    supply([special(), special({ id: 'MISC', request_no: 'SP-MISC', kind: 'WORKSHOP_MISC' })])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.find('[aria-label="供应商订单类型"]').exists()).toBe(false)
    expect(wrapper.get('tbody').text()).toContain('SC-A')
    expect(wrapper.get('tbody').text()).toContain('SP-1')
    expect(wrapper.get('tbody').text()).toContain('SP-MISC')
    expect(wrapper.findAll('[data-testid="supplier-special-order-row"]').every(row => row.text().includes('已确认接单'))).toBe(true)
    expect(wrapper.get('tbody').text()).toContain('正单')
    await wrapper.get('[aria-label="查看订单 ORDER-A 明细"]').trigger('mouseenter')
    expect(wrapper.find('[data-testid="supplier-order-detail-overlay"]').exists()).toBe(true)
    await wrapper.get('[aria-label="供应商订单类型筛选"]').setValue('SAMPLE')
    expect(wrapper.find('[data-testid="supplier-order-detail-overlay"]').exists()).toBe(false)
    expect(wrapper.get('tbody').text()).toContain('SP-1')
    expect(wrapper.get('tbody').text()).not.toContain('SP-MISC')
    expect(wrapper.find('[aria-label="查看订单 ORDER-A 明细"]').exists()).toBe(false)
    await wrapper.get('[aria-label="供应商订单类型筛选"]').setValue('WORKSHOP_MISC')
    expect(wrapper.get('tbody').text()).toContain('SP-MISC')
    await wrapper.get('[aria-label="供应商订单类型筛选"]').setValue('PURCHASE')
    expect(wrapper.get('tbody').text()).toContain('SC-A')
    expect(wrapper.findAll('[data-testid="supplier-special-order-row"]')).toHaveLength(0)
    wrapper.unmount()
  })
  it('shares keyword, customer, state and date filters and opens detail without a second list', async () => {
    supply([special({ customer_name: '样板客户' })])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('[aria-label="供应商订单客户筛选"]').setValue('样板客户')
    expect(wrapper.find('[aria-label="查看订单 ORDER-A 明细"]').exists()).toBe(false)
    expect(wrapper.get('tbody').text()).toContain('SP-1')
    await wrapper.get('[aria-label="供应商订单状态筛选"]').setValue('ACCEPTED')
    expect(wrapper.get('tbody').text()).toContain('SP-1')
    await wrapper.get('[aria-label="下单日期开始"]').setValue('2026-10-20')
    expect(wrapper.text()).toContain('没有符合当前筛选条件的订单')
    await wrapper.findAll('button').find(button => button.text() === '清空筛选')!.trigger('click')
    await wrapper.get('[aria-label="查看订单 SP-1 明细"]').trigger('click'); await flushPromises()
    expect(wrapper.get('[data-testid="supplier-order-detail-overlay"] [role="dialog"]').attributes('aria-modal')).toBe('true')
    expect(wrapper.findAll('button').some(button => ['加入统一送货单', '新建送货单'].includes(button.text()))).toBe(false)
    expect(wrapper.find('[aria-label="搜索特殊申请"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="供应商报价表单"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('keeps purchases available and reports a failed special request read', async () => {
    supply([]); specialApi.list.mockRejectedValue(new Error('特殊记录暂不可读'))
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.get('tbody').text()).toContain('SC-A')
    expect(wrapper.text()).toContain('特殊记录暂不可读')
    wrapper.unmount()
  })
  it('does not present historical supplier gifts as internally locked sample orders', async () => {
    supply([special({ kind: 'SUPPLIER_GIFT', status: 'READY', request_no: 'GIFT-OLD' })])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    const row = wrapper.get('[data-testid="supplier-special-order-row"]')
    expect(row.text()).toContain('待送货')
    expect(row.text()).not.toContain('已确认锁定')
    await wrapper.get('[aria-label="供应商订单状态筛选"]').setValue('ACCEPTED')
    expect(wrapper.findAll('[data-testid="supplier-special-order-row"]')).toHaveLength(0)
    await wrapper.get('[aria-label="供应商订单状态筛选"]').setValue('WAITING_SHIPMENT')
    expect(wrapper.get('[data-testid="supplier-special-order-row"]').text()).toContain('GIFT-OLD')
    wrapper.unmount()
  })
  it('filters real sample and miscellaneous states together with the business kind', async () => {
    supply([special(), special({ id: 'PARTIAL', request_no: 'SP-PARTIAL', kind: 'WORKSHOP_MISC', status: 'PARTIALLY_RECEIVED' }),
      special({ id: 'READY', request_no: 'SP-READY', status: 'READY' })])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('[aria-label="供应商订单状态筛选"]').setValue('PARTIALLY_RECEIVED')
    expect(wrapper.get('tbody').text()).toContain('SP-PARTIAL')
    expect(wrapper.get('[data-testid="supplier-special-order-row"]').text()).toContain('部分收料 · 待送货')
    expect(wrapper.get('tbody').text()).not.toContain('SP-READY')
    await wrapper.get('[aria-label="供应商订单类型筛选"]').setValue('SAMPLE')
    expect(wrapper.findAll('[data-testid="supplier-special-order-row"]')).toHaveLength(0)
    await wrapper.get('[aria-label="供应商订单状态筛选"]').setValue('ACCEPTED')
    expect(wrapper.get('tbody').text()).toContain('SP-READY')
    expect(wrapper.get('[data-testid="supplier-special-order-row"]').text()).toContain('已确认接单')
    expect(wrapper.get('tbody').text()).not.toContain('SP-PARTIAL')
    expect(wrapper.find('[aria-label="查看订单 ORDER-A 明细"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('reports purchase membership failure while leaving authorized special orders available', async () => {
    supply([special()]); api.memberships.mockRejectedValue(new Error('采购范围读取失败'))
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.text()).toContain('采购订单服务厂区读取失败：采购范围读取失败')
    expect(wrapper.get('tbody').text()).toContain('SP-1')
    expect(api.workspace).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('keeps the sample filter in a loading state until its independent read completes', async () => {
    supply([])
    let resolve!: (value: { items: SpecialRequest[]; total: number; can_create: boolean }) => void
    specialApi.list.mockReturnValue(new Promise(done => { resolve = done }))
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('[aria-label="供应商订单类型筛选"]').setValue('SAMPLE')
    expect(wrapper.get('tbody').text()).toContain('正在读取订单')
    expect(wrapper.get('tbody').text()).not.toContain('没有符合')
    resolve({ items: [special()], total: 1, can_create: true }); await flushPromises()
    expect(wrapper.get('tbody').text()).toContain('SP-1')
    wrapper.unmount()
  })
  it('reveals selected purchase orders even while a different type is filtered', async () => {
    const purchase = fixture(); purchase.orders[0]!.lines.forEach(line => { line.accepted = false })
    api.workspace.mockResolvedValue(purchase); supply([special()])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('[aria-label="选择订单 ORDER-A"]').setValue(true)
    await wrapper.get('[aria-label="供应商订单类型筛选"]').setValue('SAMPLE')
    expect(wrapper.text()).toContain('筛选外 1 张')
    await wrapper.findAll('button').find(button => button.text() === '查看已选')!.trigger('click')
    expect(wrapper.get('tbody').text()).toContain('SC-A')
    expect(wrapper.get('tbody').text()).not.toContain('SP-1')
    wrapper.unmount()
  })
  it('opens a notification in its explicit factory even while another factory is filtered', async () => {
    const target = special({ id: 'OTHER-FACTORY', factory_id: 'huakang-a', request_no: 'SP-HK' })
    supply([target])
    specialApi.factories.mockResolvedValue([{ factory_id: 'huaxing' }, { factory_id: 'huakang-a' }])
    specialApi.list.mockImplementation(async factory => ({ items: factory === 'huakang-a' ? [target] : [], total: factory === 'huakang-a' ? 1 : 0, can_create: true }))
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('[aria-label="供应商订单厂区筛选"]').setValue('huaxing')
    routeState.query.factory = 'huakang-a'; routeState.query.special_request = 'OTHER-FACTORY'
    await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click'); await flushPromises()
    expect(specialApi.detail).toHaveBeenCalledWith('huakang-a', 'OTHER-FACTORY', true, expect.any(AbortSignal))
    wrapper.unmount()
  })
})

describe('delivery drafts across authorization refreshes', () => {
  function refreshSameSession() {
    authState.currentUser = { ...authState.currentUser!, display_name: '更新后的姓名' }
    authState.sessionVersion++
  }
  const boundaryChanges: [string, () => void][] = [
    ['account', () => { authState.currentUser = { id: 'other-user', display_name: '其他人' } }],
    ['logout', () => { authState.currentUser = null }],
    ['authorization version', () => { authState.authorizationVersion++ }],
    ['authorization mode', () => { authState.authzMode = 'enforce' }],
    ['identity context', () => { authState.currentUser!.identity = { effective_context_key: 'new-context', employment_epoch: 1 } }],
    ['employment epoch', () => { authState.currentUser!.identity = { effective_context_key: 'original', employment_epoch: 2 } }],
    ['permission revocation', () => { can.mockReturnValue(false) }],
  ]
  async function openImport() {
    const wrapper = mount(CartonSupplierView, options)
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '导入送货单')!.trigger('click')
    const input = wrapper.get('input[type="file"]')
    const file = new File(['excel'], '送货明细表.xlsx')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    return { wrapper, file }
  }

  it('preserves deep-linked warehouse quantities, price, date, reason and bins after same-account refresh', async () => {
    const wrapper = mount(CartonSupplierReceiving, { ...options, props: { factoryId: 'huaxing', shipmentId: 'SHIP-A' } })
    await flushPromises()
    await wrapper.get('[aria-label="SL-0 实收"]').setValue(6)
    await wrapper.get('[aria-label="SL-0 差异原因"]').setValue('短收四件待核实')
    await wrapper.get('[aria-label="发货验收日期"]').setValue('2026-09-22')
    await wrapper.findAll('button').filter(button => button.text() === '此项未到')[1]!.trigger('click')
    wrapper.findAllComponents(CartonReceiptAllocations)[0]!.vm.$emit('update:modelValue', [{ location_id: 'BIN-A', quantity: 6 }])
    refreshSameSession(); await flushPromises()
    expect(api.workspace).toHaveBeenCalledTimes(1)
    expect(api.receiptOptions).toHaveBeenCalledTimes(1)
    expect(wrapper.get<HTMLInputElement>('[aria-label="SL-0 实收"]').element.value).toBe('6')
    await wrapper.get('[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.receive).toHaveBeenCalledWith('SHIP-A', expect.objectContaining({ acceptance_date: '2026-09-22', lines: [
      expect.objectContaining({ received_quantity: 6, unit_price: 2, price_action: 'MATCH', difference_reason: '短收四件待核实', location_allocations: [{ location_id: 'BIN-A', quantity: 6 }] }),
      expect.objectContaining({ received_quantity: 0 }),
    ] }))
    wrapper.unmount()
  })

  it('keeps warehouse submission pending and handles its result across a same-account refresh', async () => {
    let finish!: (value: { id: string }) => void
    api.receive.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = mount(CartonSupplierReceiving, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '核实实际收到')!.trigger('click'); await flushPromises()
    for (const input of wrapper.findAll('input[aria-label$=" 实收"]')) await input.setValue(0)
    for (const input of wrapper.findAll('input[aria-label$=" 差异原因"]')) await input.setValue('货物尚未实际送到')
    await wrapper.get('[role="dialog"]').trigger('submit')
    refreshSameSession(); await flushPromises()
    await wrapper.get('[role="dialog"]').trigger('submit')
    expect(api.receive).toHaveBeenCalledTimes(1)
    finish({ id: 'SHIP-A' }); await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('[role="status"]').text()).toContain('仓库核实已保存')
    wrapper.unmount()
  })

  it.each(boundaryChanges)('clears warehouse drafts and discards old receipt candidates after %s changes', async (_name, change) => {
    authState.currentUser!.identity = { effective_context_key: 'original', employment_epoch: 1 }
    let fail!: (reason: Error) => void
    api.receiptOptions.mockImplementationOnce(() => new Promise((_resolve, reject) => { fail = reject }))
    const wrapper = mount(CartonSupplierReceiving, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '核实实际收到')!.trigger('click')
    await wrapper.get('[aria-label="SL-0 实收"]').setValue(6)
    change(); authState.sessionVersion++; await flushPromises()
    fail(new Error('旧账号的查询错误')); await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('旧账号的查询错误')
    expect(api.receive).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('preserves import file, selected notes and registration mode across a same-account refresh', async () => {
    const preview = await api.previewDeliveryImport()
    preview.groups[0].receipt_link_ready = true
    api.previewDeliveryImport.mockResolvedValue(preview)
    const { wrapper, file } = await openImport(); await flushPromises()
    const mode = wrapper.get('[role="dialog"]').findAll('select')[0]!
    await mode.setValue('EXISTING_RECEIPT')
    await wrapper.get('[aria-label="确认送货单 DN-NEW"]').setValue(false)
    refreshSameSession(); await flushPromises()
    expect(wrapper.get<HTMLInputElement>('[aria-label="确认送货单 DN-NEW"]').element.checked).toBe(false)
    expect(wrapper.get<HTMLSelectElement>('[role="dialog"] select').element.value).toBe('EXISTING_RECEIPT')
    await wrapper.get('[aria-label="确认送货单 DN-NEW"]').setValue(true)
    await wrapper.findAll('button').find(button => button.text().startsWith('确认 1 张送货单'))!.trigger('click'); await flushPromises()
    expect(api.confirmDeliveryImport).toHaveBeenCalledWith(file, preview, [{ factory_id: 'huaxing', delivery_note_no: 'DN-NEW', registration_mode: 'EXISTING_RECEIPT' }])
    wrapper.unmount()
  })

  it('finishes an in-flight import preview and confirmation across same-account refreshes', async () => {
    const preview = await api.previewDeliveryImport()
    let previewDone!: (value: typeof preview) => void
    let confirmDone!: (value: { shipments: { id: string }[] }) => void
    api.previewDeliveryImport.mockImplementationOnce(() => new Promise(resolve => { previewDone = resolve }))
    api.confirmDeliveryImport.mockImplementationOnce(() => new Promise(resolve => { confirmDone = resolve }))
    const { wrapper } = await openImport()
    refreshSameSession(); await flushPromises()
    previewDone(preview); await flushPromises()
    const submit = wrapper.findAll('button').find(button => button.text() === '确认 1 张送货单发货')!
    expect(submit.attributes('disabled')).toBeUndefined()
    await submit.trigger('click')
    refreshSameSession(); await flushPromises()
    expect(submit.attributes('disabled')).toBeDefined()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    confirmDone({ shipments: [{ id: 'NEW' }] }); await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('已提交 1 张供应商送货单')
    expect(api.confirmDeliveryImport).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it.each(boundaryChanges)('discards pending import preview after %s changes', async (_name, change) => {
    authState.currentUser!.identity = { effective_context_key: 'original', employment_epoch: 1 }
    const preview = await api.previewDeliveryImport()
    let finish!: (value: typeof preview) => void
    api.previewDeliveryImport.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const { wrapper } = await openImport()
    change(); authState.sessionVersion++; await flushPromises()
    finish(preview); await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('DN-NEW')
    expect(api.confirmDeliveryImport).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

describe('late supplier documents use existing warehouse receipts', () => {
  it('allows viewing other customer shipments without receiving, linking or reversing them', async () => {
    const work = fixture()
    const sent = work.shipments[0]!
    sent.can_operate = false
    work.shipments.push({ ...sent, id: 'SHIP-POSTED', delivery_note_no: 'DN-POSTED', status: 'RECEIVED', receipt_id: 'RECEIPT-OTHER', receipt_status: 'POSTED' })
    api.workspace.mockResolvedValue(work)
    const wrapper = mount(CartonSupplierReceiving, { ...options, props: { factoryId: 'huaxing', responsibilityScope: 'ALL' } })
    await flushPromises()
    expect(api.workspace).toHaveBeenCalledWith('huaxing', true, 'ALL')
    expect(wrapper.text()).toContain('DN-A')
    expect(wrapper.text()).not.toContain('核实实际收到')
    expect(wrapper.text()).not.toContain('关联已入库记录')
    await wrapper.findAll('button').find(button => button.text() === '已核实记录')!.trigger('click')
    expect(wrapper.text()).toContain('DN-POSTED')
    expect(wrapper.find('[aria-label="冲销送货单 DN-POSTED 的收料"]').exists()).toBe(false)
    expect(api.receive).not.toHaveBeenCalled()
    expect(api.linkReceipt).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  const originalReceipt = { id: 'RECEIPT-1', revision: 3, status: 'POSTED', receipt_no: 'RCPT-1', delivery_note_no: 'MANUAL-1',
    delivery_date: '2026-09-20', acceptance_date: '2026-09-21', lines: [{ order_line_id: 'LINE-0', contract_no: 'SC-A', item_no: 'ITEM-A',
      packaging_type: '外箱', paper_quality: 'A33', specification: '10*20', received_quantity: '10', damaged_quantity: '0', rejected_quantity: '0',
      unusable_quantity: '0', effective_quantity: '10', unit: '个', unit_price: '2', currency: 'CNY' }] }

  it('links a late note with both revisions and never calls receive', async () => {
    const work = fixture(); work.shipments[0]!.requires_receipt_link = true
    api.workspace.mockResolvedValue(work); api.receiptOptions.mockResolvedValue([originalReceipt])
    const wrapper = mount(CartonSupplierReceiving, { ...options, props: { factoryId: 'huaxing' } }); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '关联已入库记录')!.trigger('click'); await flushPromises()
    const form = wrapper.get('form[aria-label="关联已入库记录"]')
    expect(form.text()).toContain('原验收日期 2026-09-21')
    await form.get('input[type="radio"]').setValue(true)
    await form.get('input[aria-label="后补凭证关联原因"]').setValue('已手工入库后补凭证')
    await form.trigger('submit'); await flushPromises()
    expect(api.linkReceipt).toHaveBeenCalledWith('SHIP-A', { factory_id: 'huaxing', expected_revision: 1, receipt_id: 'RECEIPT-1', expected_receipt_revision: 3, reason: '已手工入库后补凭证' })
    expect(api.receive).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('库存和月结未重复记账')
    wrapper.unmount()
  })

  it('does not offer a new receipt for an unmatched late document', async () => {
    const work = fixture(); work.shipments[0]!.requires_receipt_link = true; api.workspace.mockResolvedValue(work)
    const wrapper = mount(CartonSupplierReceiving, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '关联已入库记录')!.trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('没有可关联的原收料')
    expect(wrapper.findAll('button').some(button => button.text() === '核实实际收到')).toBe(false)
    expect(wrapper.findAll('button').find(button => button.text() === '确认关联，不重复入库')!.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('discards candidate results when the factory changes', async () => {
    let resolve!: (rows: typeof originalReceipt[]) => void
    api.receiptOptions.mockImplementation(() => new Promise(result => { resolve = result }))
    const wrapper = mount(CartonSupplierReceiving, { ...options, props: { factoryId: 'huaxing' } }); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '关联已入库记录')!.trigger('click')
    await wrapper.setProps({ factoryId: 'huakang-a' }); resolve([originalReceipt]); await flushPromises()
    expect(wrapper.find('form[aria-label="关联已入库记录"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('RCPT-1'); expect(api.linkReceipt).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('lets a completed-order original file be submitted as a late document', async () => {
    const preview = await api.previewDeliveryImport()
    preview.groups[0].ready = false; preview.groups[0].receipt_link_ready = true; preview.groups[0].existing_receipt_count = 1
    api.previewDeliveryImport.mockResolvedValue(preview)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '导入送货单')!.trigger('click')
    const input = wrapper.get('input[type="file"]')
    const file = new File(['source'], 'late.xlsx')
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change'); await flushPromises()
    expect(wrapper.text()).toContain('后补凭证 · 仅关联已有入库')
    await wrapper.findAll('button').find(button => button.text().includes('确认 1 张送货单'))!.trigger('click'); await flushPromises()
    expect(api.confirmDeliveryImport).toHaveBeenCalledWith(file, preview, [{ factory_id: 'huaxing', delivery_note_no: 'DN-NEW', registration_mode: 'EXISTING_RECEIPT' }])
    expect(api.ship).not.toHaveBeenCalled(); wrapper.unmount()
  })
})

describe('supplier usage guide entry', () => {
  it('opens and closes without changing order filters or submitting business actions', async () => {
    const wrapper = mount(CartonSupplierView, guideOptions); await flushPromises()
    await wrapper.get('input[aria-label="顶部搜索"]').setValue('ITEM-A')
    await wrapper.get('button[aria-label="打开供应商协同使用教程"]').trigger('click'); await flushPromises()
    const guide = wrapper.findComponent({ name: 'CartonUsageGuide' })
    expect(guide.props()).toMatchObject({ audience: 'supplier', factoryName: '河源东康' })
    guide.vm.$emit('close'); await flushPromises()
    expect(wrapper.find('[data-testid="supplier-usage-guide"]').exists()).toBe(false)
    expect(wrapper.get<HTMLInputElement>('input[aria-label="顶部搜索"]').element.value).toBe('ITEM-A')
    for (const action of [api.accept, api.acceptBatch, api.confirmDeliveryImport, api.ship, api.receive]) expect(action).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('navigates to supplier documents and carton marks through existing read-only entries', async () => {
    const wrapper = mount(CartonSupplierView, guideOptions); await flushPromises()
    await wrapper.get('button[aria-label="打开供应商协同使用教程"]').trigger('click'); await flushPromises()
    wrapper.findComponent({ name: 'CartonUsageGuide' }).vm.$emit('supplierNavigate', 'supplier-documents'); await flushPromises()
    expect(wrapper.find('input[aria-label="顶部搜索"]').exists()).toBe(true)
    expect(api.documents).toHaveBeenCalledWith('huaxing')
    await wrapper.get('button[aria-label="打开供应商协同使用教程"]').trigger('click'); await flushPromises()
    wrapper.findComponent({ name: 'CartonUsageGuide' }).vm.$emit('supplierNavigate', 'supplier-carton-mark'); await flushPromises()
    expect(router.push).toHaveBeenCalledWith('/carton-supplier/carton-mark')
    expect(api.confirmDeliveryImport).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps the guide available for a supplier who can only read', async () => {
    can.mockImplementation(permission => permission === 'carton_supplier:read')
    const wrapper = mount(CartonSupplierView, guideOptions); await flushPromises()
    await wrapper.get('button[aria-label="打开供应商协同使用教程"]').trigger('click'); await flushPromises()
    wrapper.findComponent({ name: 'CartonUsageGuide' }).vm.$emit('supplierNavigate', 'supplier-settlements'); await flushPromises()
    expect(wrapper.findComponent({ name: 'CartonSupplierMonthlyReview' }).exists()).toBe(true)
    await wrapper.get('[aria-label="顶部搜索"]').setValue('DN-HEADER')
    expect(wrapper.findComponent({ name: 'CartonSupplierMonthlyReview' }).props('search')).toBe('DN-HEADER')
    expect(api.acceptBatch).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

describe('supplier carton mark templates', () => {
  it('selects a shared Excel into the supplier PDF form without opening the internal warehouse page', async () => {
    routeState.query.factory = 'huaxing'
    api.markAssets.mockResolvedValue([{ id: 'excel-a', revision: 4, file_name: '客人.xlsx', kind: 'excel', size_bytes: 400,
      contract_number: 'SC-A', created_at: '2026-10-05', orders: [{ id: 'ORDER-A', issue_id: 'ISSUE-A', customer_name: 'Dickie', customer_po: 'PO-A', contract_no: 'SC-A', item_no: 'ITEM-A' }] }])
    const wrapper = mount(CartonSupplierMarkTemplatesView, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '选择 Excel 并上传 PDF 核对')!.trigger('click'); await flushPromises()
    expect(wrapper.get('[aria-label="供应商 Excel / PDF 核对"]').isVisible()).toBe(true)
    expect(wrapper.get('[aria-label="核对关联采购订单"]').element).toHaveProperty('value', 'ORDER-A')
    expect(wrapper.get('[aria-label="供应商 Excel / PDF 核对"]').text()).toContain('客人.xlsx')
    expect(wrapper.text()).not.toContain('维护客户')
    expect(wrapper.text()).not.toContain('返回PMC')
    expect(api.markChecks).toHaveBeenCalledWith('huaxing', expect.any(AbortSignal))
    authState.currentUser = { id: 'supplier-test', display_name: '供应商新头像' }
    await flushPromises()
    expect(wrapper.find('[aria-label="核对关联采购订单"]').exists()).toBe(true)
    authState.authorizationVersion++
    await flushPromises()
    expect(wrapper.find('[aria-label="核对关联采购订单"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('defaults to all service factories and can switch to a single factory', async () => {
    routeState.query.factory = ''
    api.memberships.mockResolvedValue([{ factory_id: 'huaxing', supplier_name: '河源东康' }, { factory_id: 'huakang-a', supplier_name: '河源东康' }])
    api.markAssets.mockImplementation(async scope => [{ id: `file-${scope}`, file_name: `${scope}.pdf`, kind: 'pdf', size_bytes: 400,
      contract_number: 'SC-A', created_at: '2026-10-05', orders: [] }])
    const wrapper = mount(CartonSupplierMarkTemplatesView, options); await flushPromises()
    expect(wrapper.get<HTMLSelectElement>('select[aria-label="箱唛资料厂区"]').element.value).toBe('ALL')
    expect(api.markAssets.mock.calls.map(call => call[0])).toEqual(['huaxing', 'huakang-a'])
    expect(wrapper.text()).toContain('2 份资料')
    expect(wrapper.text()).toContain('huaxing.pdf')
    expect(wrapper.text()).toContain('huakang-a.pdf')
    await wrapper.get('select[aria-label="箱唛资料厂区"]').setValue('huaxing'); await flushPromises()
    expect(wrapper.text()).toContain('1 份资料')
    expect(wrapper.text()).not.toContain('huakang-a.pdf')
    await wrapper.get('select[aria-label="箱唛资料厂区"]').setValue('ALL'); await flushPromises()
    expect(wrapper.text()).toContain('2 份资料')
    wrapper.unmount(); routeState.query.factory = 'huaxing'
  })

  it('removes revoked-factory files and falls back to all remaining service factories on refresh', async () => {
    api.memberships.mockResolvedValueOnce([{ factory_id: 'huaxing', supplier_name: '河源东康' }, { factory_id: 'huakang-a', supplier_name: '河源东康' }])
      .mockResolvedValue([{ factory_id: 'huakang-a', supplier_name: '河源东康' }])
    api.markAssets.mockImplementation(async scope => [{ id: `file-${scope}`, file_name: `${scope}.pdf`, kind: 'pdf', size_bytes: 400,
      contract_number: 'SC-A', created_at: '2026-10-05', orders: [] }])
    const wrapper = mount(CartonSupplierMarkTemplatesView, options); await flushPromises()
    expect(wrapper.text()).toContain('huaxing.pdf')
    await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click'); await flushPromises()
    expect(wrapper.get<HTMLSelectElement>('select[aria-label="箱唛资料厂区"]').element.value).toBe('ALL')
    expect(wrapper.text()).not.toContain('huaxing.pdf')
    expect(wrapper.text()).toContain('huakang-a.pdf')
    expect(api.markAssets).toHaveBeenLastCalledWith('huakang-a', expect.any(AbortSignal))
    wrapper.unmount()
  })

  it('explains the loss of the last service factory and recovers after access is restored', async () => {
    const factories = [{ factory_id: 'huaxing', supplier_name: '河源东康' }]
    api.memberships.mockResolvedValueOnce(factories).mockResolvedValueOnce([]).mockResolvedValue(factories)
    api.markAssets.mockResolvedValue([{ id: 'file-a', file_name: 'print.pdf', kind: 'pdf', size_bytes: 400,
      contract_number: 'SC-A', created_at: '2026-10-05', orders: [] }])
    const wrapper = mount(CartonSupplierMarkTemplatesView, options); await flushPromises()
    expect(wrapper.text()).toContain('print.pdf')
    await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click'); await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain('暂无已授权服务厂区')
    expect(wrapper.text()).not.toContain('print.pdf')
    expect(api.markAssets).toHaveBeenCalledTimes(1)
    await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click'); await flushPromises()
    expect(wrapper.find('[role=alert]').exists()).toBe(false)
    expect(wrapper.get<HTMLSelectElement>('select[aria-label="箱唛资料厂区"]').element.value).toBe('ALL')
    expect(wrapper.text()).toContain('print.pdf')
    wrapper.unmount()
  })
  it('recovers from an unauthorized factory parameter when a service factory is selected', async () => {
    routeState.query.factory = 'unauthorized'
    const wrapper = mount(CartonSupplierMarkTemplatesView, options); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('没有所选厂区的资料库权限')
    expect(api.markAssets).not.toHaveBeenCalled()
    await wrapper.get('select[aria-label="箱唛资料厂区"]').setValue('huaxing'); await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(api.markAssets).toHaveBeenCalledWith('huaxing', expect.any(AbortSignal))
    wrapper.unmount(); routeState.query.factory = 'huaxing'
  })
  it('discovers a newly ordering service factory when refreshed', async () => {
    routeState.query.factory = ''
    const factories = [
      { factory_id: 'huaxing', supplier_name: '河源东康' },
      { factory_id: 'huakang-a', supplier_name: '河源东康' },
    ]
    api.memberships.mockResolvedValueOnce([factories[0]]).mockResolvedValue(factories)
    const wrapper = mount(CartonSupplierMarkTemplatesView, options); await flushPromises()
    expect(wrapper.get('select[aria-label="箱唛资料厂区"]').findAll('option')).toHaveLength(2)
    await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click'); await flushPromises()
    expect(wrapper.get('select[aria-label="箱唛资料厂区"]').findAll('option').map(option => option.attributes('value'))).toEqual(['ALL', 'huaxing', 'huakang-a'])
    expect(wrapper.get<HTMLSelectElement>('select[aria-label="箱唛资料厂区"]').element.value).toBe('ALL')
    expect(api.markAssets).toHaveBeenCalledWith('huakang-a', expect.any(AbortSignal))
    wrapper.unmount(); routeState.query.factory = 'huaxing'
  })
  it('lists scoped source files with PDF preview and authenticated download', async () => {
    api.markAssets.mockResolvedValue([{ id: 'mark-1', file_name: 'print.pdf', kind: 'pdf', size_bytes: 400, contract_number: 'SC-A', created_at: '2026-09-21', orders: [{ id: 'ORDER-A', customer_name: 'Dickie', customer_po: 'PO-A', contract_no: 'SC-A', item_no: 'ITEM-A' }] }]); api.downloadMarkAsset.mockRejectedValueOnce(new Error('下载失败，请重试'))
    const wrapper = mount(CartonSupplierMarkTemplatesView, options); await flushPromises()
    expect(api.markAssets).toHaveBeenCalledWith('huaxing', expect.any(AbortSignal))
    expect(wrapper.text()).toContain('Dickie · SC-A · ITEM-A')
    expect(wrapper.text()).toContain('箱唛资料库')
    expect(wrapper.get('a[aria-label="预览 print.pdf"]').attributes('href')).toBe('/api/preview.pdf')
    await wrapper.get('button[aria-label="下载 print.pdf"]').trigger('click'); await flushPromises()
    expect(api.downloadMarkAsset).toHaveBeenCalledWith('mark-1', 'huaxing', expect.any(AbortSignal))
    expect(wrapper.get('[role="alert"]').text()).toContain('下载失败')
    expect(wrapper.find('[aria-label="供应商批量选择箱唛原文件"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="批量选择箱唛原文件"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('does not request templates when the account has no supplier membership', async () => {
    api.memberships.mockResolvedValue([])
    const wrapper = mount(CartonSupplierMarkTemplatesView, options); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('暂无已授权服务厂区')
    expect(api.markAssets).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

describe('supplier batches and document desk', () => {
  it.each([false, true])('shows a confirmed batch and makes direct-export failure visible=%s', async (exportFails) => {
    const merged = {
      id: 'CPB-TEST', kind: 'PURCHASE' as const, factory_id: 'huaxing',
      document_no: 'CG-260929-BATCH', document_type: 'INITIAL', date: '2026-09-29',
      created_at: '2026-09-29T08:00:00+08:00', status: '已生成', replenishment: false,
      export_count: 0, is_batch: true,
      source_documents: ['A', 'B'].map(suffix => ({ id: `I-${suffix}`, document_no: `ORDER-${suffix}-P00`, order_no: `ORDER-${suffix}` })),
      orders: ['A', 'B'].map(suffix => ({ order_no: `ORDER-${suffix}`, customer_name: 'Dickie',
        contract_no: `SC-${suffix}`, customer_po: `PO-${suffix}`, item_no: `ITEM-${suffix}`,
        product_name: `产品${suffix}`, order_date: '2026-09-29', planned_date: '2026-10-10' })),
      lines: ['A', 'B'].map(suffix => ({ order_no: `ORDER-${suffix}`, child_no: `ORDER-${suffix}/01`,
        source_document_no: `ORDER-${suffix}-P00`, packaging_type: '外箱', paper_quality: 'A33',
        specification: '10*20*30', unit: '个', before_quantity: '0', change_quantity: '100', quantity: '100' })),
    }
    api.documents.mockResolvedValue([merged])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text().includes('采购单与送货单'))!.trigger('click'); await flushPromises()
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
    expect(wrapper.get('tbody tr').text()).toContain('合并采购单')
    expect(wrapper.get('tbody tr').text()).toContain('2 张订单')
    await wrapper.get('input[aria-label="顶部搜索"]').setValue('ORDER-B-P00')
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
    await wrapper.get('button[aria-label="查看单据 CG-260929-BATCH 明细"]').trigger('click'); await flushPromises()
    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.text()).toContain('合并采购单 · CG-260929-BATCH')
    for (const suffix of ['A', 'B']) {
      expect(dialog.text()).toContain(`SC-${suffix}`)
      expect(dialog.text()).toContain(`ITEM-${suffix}`)
      expect(dialog.text()).toContain(`原采购单 ORDER-${suffix}-P00`)
    }
    api.documents.mockResolvedValue([{ ...merged, export_count: 1 }])
    if (exportFails) api.exportDocuments.mockRejectedValueOnce(new Error('下载连接断开'))
    await dialog.findAll('button').find(button => button.text() === '导出这张采购单')!.trigger('click'); await flushPromises()
    expect(api.exportDocuments).toHaveBeenCalledWith([merged])
    if (exportFails) {
      expect(dialog.get('[role="alert"]').text()).toContain('下载连接断开')
      expect(wrapper.get('[aria-label="CG-260929-BATCH 导出 0 次"]').text()).toBe('0')
      await dialog.findAll('button').find(button => button.text() === '导出这张采购单')!.trigger('click'); await flushPromises()
    }
    expect(dialog.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.get('[aria-label="CG-260929-BATCH 导出 1 次"]').text()).toBe('1')
    wrapper.unmount()
  })

  it('shows only actions covered by edit or approve permission', async () => {
    can.mockImplementation(permission => permission === 'carton_supplier:read')
    let wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.text()).not.toContain('导入送货单')
    expect(wrapper.text()).not.toContain('批量确认接单')
    expect(wrapper.get('input[aria-label="选择订单 ORDER-A"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()

    can.mockImplementation(permission => ['carton_supplier:read', 'carton_supplier:edit'].includes(permission))
    wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.text()).toContain('导入送货单')
    expect(wrapper.text()).not.toContain('批量确认接单')
    wrapper.unmount()

    const pending = fixture()
    pending.orders[0]!.lines.forEach(line => { line.accepted = false })
    api.workspace.mockResolvedValue(pending)
    can.mockImplementation(permission => ['carton_supplier:read', 'carton_supplier:approve'].includes(permission))
    wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.find('button[aria-label="确认订单 ORDER-A 接单"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('导入送货单')
    wrapper.unmount()
  })
  it('shows business-date delivery reminders without NaN for invalid dates or completed orders', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-09-23T04:00:00Z'))
    try {
      const data = fixture()
      const source = data.orders[0]!
      const variant = (id: string, plannedDate: string, status = source.status) => {
        const order = structuredClone(source)
        order.id = id
        order.order_no = id
        order.planned_date = plannedDate
        order.status = status
        order.lines.forEach((line, index) => { line.id = `${id}-${index}`; line.child_no = `${id}/0${index + 1}` })
        return order
      }
      data.orders = [
        variant('OVERDUE', '2026-09-20'), variant('TODAY', '2026-09-23'),
        variant('TOMORROW', '2026-09-24'), variant('SOON', '2026-09-26'),
        variant('LATER', '2026-09-27'), variant('INVALID', '2026-02-30'),
        variant('COMPLETED', '2026-09-20', 'COMPLETED'),
      ]
      api.workspace.mockResolvedValue(data)
      const wrapper = mount(CartonSupplierView, options); await flushPromises()
      expect(wrapper.findAll('table')[0]!.find('thead').text()).toContain('交期提醒')
      const rowText = (id: string) => wrapper.findAll('table')[0]!.findAll('tbody tr')
        .find(row => row.find(`button[aria-label="查看订单 ${id} 明细"]`).exists())!.text()
      expect(rowText('OVERDUE')).toContain('已逾期 3 天')
      expect(rowText('TODAY')).toContain('今日交期')
      expect(rowText('TOMORROW')).toContain('明日交期')
      expect(rowText('SOON')).toContain('剩 3 天')
      expect(rowText('LATER')).toContain('距交期 4 天')
      expect(rowText('INVALID')).toContain('交期待确认')
      expect(rowText('COMPLETED')).toContain('交付已完成')
      expect(wrapper.text()).not.toContain('NaN')
      wrapper.unmount()
    } finally {
      vi.useRealTimers()
    }
  })

  it('shows selected orders even when the current filters hide them', async () => {
    const data = fixture()
    const second = structuredClone(data.orders[0]!)
    second.id = 'ORDER-B'
    second.order_no = 'ORDER-B'
    second.customer_name = 'BUZZ'
    second.lines.forEach((line, index) => { line.id = `B-LINE-${index}`; line.child_no = `ORDER-B/0${index + 1}` })
    data.orders.push(second)
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('input[aria-label="选择订单 ORDER-A"]').setValue(true)
    await wrapper.get('select[aria-label="供应商订单客户筛选"]').setValue('BUZZ')
    expect(wrapper.find('input[aria-label="选择订单 ORDER-A"]').exists()).toBe(false)
    await wrapper.findAll('button').find(button => button.text() === '查看已选')!.trigger('click')
    expect(wrapper.find('input[aria-label="选择订单 ORDER-A"]').exists()).toBe(true)
    await wrapper.get('input[aria-label="选择订单 ORDER-A"]').setValue(false)
    expect(wrapper.text()).toContain('已选 0 张订单')
    wrapper.unmount()
  })

  it('keeps another paper\'s unsaved promised date after one paper is accepted', async () => {
    const data = fixture()
    data.orders[0]!.lines.forEach(line => { line.accepted = false; line.commitment_revision = 0 })
    api.workspace.mockImplementation(async () => structuredClone(data))
    api.accept.mockImplementation(async () => { data.orders[0]!.lines[0]!.accepted = true })
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('button[aria-label="确认订单 ORDER-A 接单"]').trigger('click')
    await wrapper.get('input[aria-label="ORDER-A/02 承诺交期"]').setValue('2026-10-05')
    await wrapper.get('input[aria-label="ORDER-A/01 承诺交期"]').setValue('2026-10-01')
    await wrapper.get('[role="dialog"]').findAll('button').find(button => button.text() === '确认接单')!.trigger('click'); await flushPromises()
    expect(wrapper.get<HTMLInputElement>('input[aria-label="ORDER-A/02 承诺交期"]').element.value).toBe('2026-10-05')
    wrapper.unmount()
  })

  it('reports the completed factory if a later factory rejects a batch', async () => {
    const first = fixture()
    first.orders[0]!.lines.forEach(line => { line.accepted = false; line.commitment_revision = 0 })
    const second = structuredClone(first)
    second.factory_id = 'huakang-a'
    second.orders[0]!.id = 'ORDER-K'
    second.orders[0]!.order_no = 'ORDER-K'
    second.orders[0]!.lines.forEach((line, index) => { line.id = `K-LINE-${index}`; line.child_no = `ORDER-K/0${index + 1}` })
    api.memberships.mockResolvedValue([
      { factory_id: 'huaxing', supplier_name: '河源东康' },
      { factory_id: 'huakang-a', supplier_name: '河源东康' },
    ])
    api.workspace.mockImplementation(async (scope: string) => structuredClone(scope === 'huaxing' ? first : second))
    api.acceptBatch.mockImplementation(async (scope: string) => {
      if (scope === 'huakang-a') throw { isAxiosError: true, message: 'Request failed with status code 409', response: { status: 409, data: { detail: '版本已变更，请刷新后重新确认承诺交期' } } }
      first.orders[0]!.lines.forEach(line => { line.accepted = true })
      return { order_ids: ['ORDER-A'] }
    })
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('input[aria-label="全选当前筛选订单"]').setValue(true)
    await wrapper.findAll('button').find(button => button.text() === '批量确认接单')!.trigger('click')
    await wrapper.findAll('button').find(button => button.text() === '确认所选订单接单')!.trigger('click'); await flushPromises()
    expect(api.acceptBatch.mock.calls.map(call => call[0])).toEqual(['huaxing', 'huakang-a'])
    expect(wrapper.get('[role="alert"]').text()).toContain('已完成 华兴')
    expect(wrapper.get('[role="alert"]').text()).toContain('版本已变更')
    expect(wrapper.get('[role="dialog"]').text()).toContain('ORDER-K')
    expect(wrapper.findComponent(CartonActionNotice).props('message')).toContain('版本已变更，请刷新后重新确认承诺交期')
    wrapper.unmount()
  })

  it.each(['request', 'refresh'] as const)('keeps the precise single acceptance %s outcome visible', async (stage) => {
    const data = fixture()
    data.orders[0]!.lines.forEach(line => { line.accepted = false; line.commitment_revision = 0 })
    api.workspace.mockResolvedValue(data)
    api.accept.mockResolvedValue(undefined)
    const wrapper = mount(CartonSupplierView, { global: { stubs: { ...options.global.stubs, Teleport: true } } }); await flushPromises()
    await wrapper.get('button[aria-label="确认订单 ORDER-A 接单"]').trigger('click')
    const reason = stage === 'request' ? '采购单版本已更新，请核对后接单' : '供应商台账暂不可读取'
    const failure = { isAxiosError: true, message: 'Request failed with status code 409', response: { status: 409, data: { detail: reason } } }
    if (stage === 'request') api.accept.mockRejectedValueOnce(failure)
    else api.workspace.mockRejectedValueOnce(failure)
    await wrapper.get('[role="dialog"]').findAll('button').find(button => button.text() === '确认接单')!.trigger('click'); await flushPromises()
    const notice = wrapper.findComponent(CartonActionNotice)
    expect(notice.get('[role="alert"]').text()).toContain(reason)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(stage === 'request')
    if (stage === 'refresh') {
      expect(notice.text()).toContain('已确认接单，但列表刷新失败')
      expect(notice.text()).toContain('勿重复接单')
    }
    expect(api.accept).toHaveBeenCalledTimes(1)
    await notice.get('button[aria-label="关闭操作提醒"]').trigger('click')
    expect(notice.find('[role="alert"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('confirms multiple selected orders while offering delivery import', async () => {
    const data = fixture()
    const first = data.orders[0]!
    first.lines.forEach(line => { line.accepted = false; line.commitment_revision = 0 })
    const second = structuredClone(first)
    second.id = 'ORDER-B'
    second.order_no = 'ORDER-B'
    second.lines.forEach((line, index) => { line.id = `B-LINE-${index}`; line.child_no = `ORDER-B/0${index + 1}` })
    data.orders.push(second)
    api.workspace.mockImplementation(async () => structuredClone(data))
    api.acceptBatch.mockImplementation(async (_factory: string, lines: { order_line_id: string }[]) => {
      for (const order of data.orders) for (const line of order.lines) {
        if (lines.some(item => item.order_line_id === line.id)) line.accepted = true
      }
      return { order_ids: data.orders.map(order => order.id) }
    })
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.findAll('table')[0]!.find('thead').text()).toContain('送货进度')
    await wrapper.get('input[aria-label="全选当前筛选订单"]').setValue(true)
    expect(wrapper.text()).toContain('导入送货单')
    await wrapper.findAll('button').find(button => button.text() === '批量确认接单')!.trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('2 张订单')
    await wrapper.findAll('button').find(button => button.text() === '确认所选订单接单')!.trigger('click')
    await flushPromises()
    expect(api.acceptBatch).toHaveBeenCalledTimes(1)
    expect(api.acceptBatch.mock.calls[0]?.[0]).toBe('huaxing')
    expect(api.acceptBatch.mock.calls[0]?.[1]).toHaveLength(4)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('将所选订单加入发货')
    wrapper.unmount()
  })

  it('filters, inspects and exports selected purchase and delivery documents', async () => {
    const rows = [
      { id: 'I-1', kind: 'PURCHASE', factory_id: 'huaxing', document_no: 'PO-1', document_type: 'INITIAL', date: '2026-09-21', created_at: '2026-09-21T10:00:00', status: '已生成', replenishment: false, export_count: 0,
        orders: [{ order_no: 'ORDER-A', customer_name: 'Dickie', contract_no: 'SC-A', customer_po: 'PO-A', item_no: 'ITEM-A', product_name: '产品', order_date: '2026-09-10', planned_date: '2026-09-25' }],
        lines: [{ order_no: 'ORDER-A', child_no: 'ORDER-A/01', packaging_type: '外箱', paper_quality: 'A33', specification: '10*20', unit: '个', before_quantity: '0', change_quantity: '100', quantity: '100' }] },
      { id: 'S-1', kind: 'DELIVERY', factory_id: 'huaxing', document_no: 'DN-1', document_type: 'DELIVERY', date: '2026-09-22', created_at: '2026-09-22T10:00:00', status: 'SENT', replenishment: false, export_count: 0,
        orders: [{ order_no: 'ORDER-A', customer_name: 'Dickie', contract_no: 'SC-A', customer_po: 'PO-A', item_no: 'ITEM-A', product_name: '', order_date: '', planned_date: '' }],
        lines: [{ order_no: 'ORDER-A', child_no: 'ORDER-A/01', packaging_type: '外箱', paper_quality: 'A33', specification: '10*20', unit: '个', quantity: '10', received_quantity: '0' }] },
    ]
    api.documents.mockResolvedValue(rows)
    api.activityPage.mockResolvedValue({ items: [{ id: 'ACT1', factory_id: 'huaxing', action: '送货单已登记', created_at: '2026-09-25', reference_no: 'DN-1', actor_name: '供应商' }], total: 1, limit: 50, offset: 0 }); api.activity.mockResolvedValue([{ id: 'LOG-1', factory_id: 'huaxing', created_at: '2026-09-22T10:00:00', action: '送货单已登记', reference_no: 'DN-1', actor_name: '供应商' }])
    const wrapper = mount(CartonSupplierView, { ...options, attachTo: document.body }); await flushPromises()
    expect(wrapper.findAll('a').some(link => link.text().includes('箱唛资料库'))).toBe(true)
    await wrapper.findAll('button').find(button => button.text().includes('采购单与送货单'))!.trigger('click'); await flushPromises()
    expect(api.documents).toHaveBeenCalledWith('huaxing')
    expect(wrapper.text()).toContain('PO-1')
    expect(wrapper.text()).toContain('DN-1')
    expect(wrapper.get('thead').text()).toContain('导出次数')
    expect(wrapper.get('[aria-label="PO-1 导出 0 次"]').text()).toBe('0')
    await wrapper.get('select[aria-label="单据类型筛选"]').setValue('PURCHASE')
    expect(wrapper.text()).toContain('PO-1')
    expect(wrapper.text()).not.toContain('DN-1')
    await wrapper.get('select[aria-label="单据类型筛选"]').setValue('')
    await wrapper.get('input[aria-label="全选当前筛选单据"]').setValue(true)
    expect(wrapper.text()).toContain('已选 2 张单据 · 1 张订单')
    expect(wrapper.findAll('button').filter(button => button.text().includes('导出所选'))).toHaveLength(0)
    await wrapper.findAll('button').find(button => button.text().includes('预览并导出'))!.trigger('click')
    const mergedPreview = wrapper.get('[role="dialog"]')
    await flushPromises()
    expect(document.activeElement?.getAttribute('aria-label')).toBe('关闭合并预览')
    expect(wrapper.get('header').attributes('inert')).toBeDefined()
    expect(mergedPreview.text()).toContain('2 张单据 / 1 张订单')
    expect(mergedPreview.text()).toContain('PO-1')
    expect(mergedPreview.text()).toContain('DN-1')
    expect(mergedPreview.text()).toContain('发货 10 · 到货 0')
    const dialogExport = mergedPreview.findAll('button').find(button => button.text().includes('导出所选'))!
    ;(dialogExport.element as HTMLElement).focus()
    await mergedPreview.trigger('keydown', { key: 'Tab' })
    expect(document.activeElement?.getAttribute('aria-label')).toBe('关闭合并预览')
    api.documents.mockResolvedValue(rows.map(row => ({ ...row, export_count: 1 })))
    await dialogExport.trigger('click'); await flushPromises()
    expect(api.exportDocuments).toHaveBeenCalledWith(expect.arrayContaining(rows))
    expect(api.documents).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[aria-label="PO-1 导出 1 次"]').text()).toBe('1')
    expect(wrapper.get('[aria-label="DN-1 导出 1 次"]').text()).toBe('1')
    await wrapper.get('button[aria-label="关闭合并预览"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('header').attributes('inert')).toBeUndefined()
    const detailButton = wrapper.get('button[aria-label="查看单据 DN-1 明细"]')
    await detailButton.trigger('mouseenter')
    expect(wrapper.get('[role="dialog"]').text()).toContain('悬停预览')
    expect(wrapper.get('[role="dialog"]').attributes('inert')).toBeDefined()
    await detailButton.trigger('mouseleave')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await detailButton.trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="dialog"]').attributes('aria-modal')).toBe('true')
    expect(document.activeElement?.getAttribute('aria-label')).toBe('关闭单据明细')
    expect(wrapper.get('[role="dialog"]').text()).toContain('SC-A')
    expect(wrapper.get('[role="dialog"]').text()).toContain('外箱')
    await wrapper.get('button[aria-label="关闭单据明细"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await wrapper.findAll('button').find(button => button.text() === '操作日志')!.trigger('click'); await flushPromises()
    expect(api.activityPage).toHaveBeenCalledWith(expect.objectContaining({ factory_id: '', limit: 50, offset: 0 }))
    expect(wrapper.text()).toContain('送货单已登记')
    wrapper.unmount()
  })

  it('exports only selected purchase issues in the supplier ERP import format', async () => {
    const purchase = { id: 'ISSUE-1', kind: 'PURCHASE', factory_id: 'huaxing', document_no: 'PO-1',
      document_type: 'INITIAL', date: '2026-09-24', created_at: '2026-09-24T10:00:00', status: '已生成',
      replenishment: false, export_count: 0, orders: [], lines: [], supplier_acceptance: { status: 'ACCEPTED', label: '供应商已接单', total_line_count: 2, accepted_line_count: 2 } }
    const delivery = { ...purchase, id: 'SHIP-1', kind: 'DELIVERY', document_no: 'DN-1' }
    api.documents.mockResolvedValue([purchase, delivery])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text().includes('采购单与送货单'))!.trigger('click'); await flushPromises()
    await wrapper.get('input[aria-label="全选当前筛选单据"]').setValue(true)
    await wrapper.findAll('button').find(button => button.text().includes('导出东康导入模板'))!.trigger('click')
    await flushPromises()
    expect(api.exportOrderImport).toHaveBeenCalledWith([purchase], false)
    expect(api.exportDocuments).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('filters whole mixed documents by any real business kind and combines document category', async () => {
    const base = { factory_id: 'huaxing', document_type: 'DELIVERY', date: '2026-09-24',
      created_at: '2026-09-24T10:00:00', status: 'SENT', replenishment: false, export_count: 0, orders: [] }
    const line = { order_no: '', child_no: '', packaging_type: '外箱', paper_quality: '', specification: '', unit: '个', quantity: '10' }
    const order = { order_no: '', customer_name: '', contract_no: '', customer_po: '', item_no: '', product_name: '', order_date: '', planned_date: '' }
    const mixed = { ...base, id: 'MIXED', kind: 'DELIVERY', document_no: 'DN-MIXED',
      orders: [{ ...order, order_kind: 'REGULAR', order_no: 'ORDER-MIX', contract_no: 'SC-MIX' }, { ...order, order_kind: 'SAMPLE', order_no: 'SP-SAMPLE' }, { ...order, order_kind: 'MISC', order_no: 'SP-MISC', contract_no: ' ' }],
      lines: [{ ...line, order_kind: 'REGULAR' }, { ...line, order_kind: 'SAMPLE' }, { ...line, order_kind: 'MISC' }] }
    api.documents.mockResolvedValue([mixed,
      { ...base, id: 'REGULAR', kind: 'PURCHASE', document_no: 'PO-REGULAR', lines: [{ ...line, order_kind: 'REGULAR' }] },
      { ...base, id: 'UNKNOWN', kind: 'DELIVERY', document_no: 'DN-UNKNOWN', lines: [{ ...line, order_kind: 'UNKNOWN' }] }])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text().includes('采购单与送货单'))!.trigger('click'); await flushPromises()
    const type = wrapper.get('[aria-label="单据业务类型筛选"]')
    for (const kind of ['SAMPLE', 'MISC']) {
      await type.setValue(kind)
      expect(wrapper.get('tbody').text()).toContain('DN-MIXED')
      expect(wrapper.get('tbody').text()).toContain('3 张订单 · SC-MIX')
      expect(wrapper.get('tbody').text()).not.toContain('SC-MIX、')
      expect(wrapper.get('tbody').text()).not.toContain('PO-REGULAR')
      expect(wrapper.get('tbody').text()).not.toContain('DN-UNKNOWN')
    }
    await wrapper.get('[aria-label="单据类型筛选"]').setValue('PURCHASE')
    expect(wrapper.get('tbody').text()).not.toContain('DN-MIXED')
    await type.setValue('REGULAR')
    expect(wrapper.get('tbody').text()).toContain('PO-REGULAR')
    await wrapper.get('[aria-label="单据类型筛选"]').setValue('')
    await type.setValue('UNKNOWN')
    expect(wrapper.get('tbody').text()).toContain('DN-UNKNOWN')
    expect(wrapper.get('tbody').text()).not.toContain('DN-MIXED')
    await wrapper.findAll('button').find(button => button.text() === '清空筛选')!.trigger('click')
    expect((type.element as HTMLSelectElement).value).toBe('')
    expect(wrapper.get('tbody').text()).toContain('DN-MIXED')
    await type.setValue('SAMPLE')
    await wrapper.get('input[aria-label="全选当前筛选单据"]').setValue(true)
    await wrapper.findAll('button').find(button => button.text().includes('预览并导出'))!.trigger('click')
    await wrapper.get('[role="dialog"]').findAll('button').find(button => button.text().includes('导出所选'))!.trigger('click')
    await flushPromises()
    expect(api.exportDocuments).toHaveBeenCalledWith([mixed])
    wrapper.unmount()
  })

  it('keeps same-number orders from different factories separate in the merged preview', async () => {
    api.memberships.mockResolvedValue([
      { factory_id: 'huaxing', supplier_name: '河源东康' },
      { factory_id: 'huakang-a', supplier_name: '河源东康' },
    ])
    api.documents.mockImplementation(async (factoryId: string) => [{
      id: `ISSUE-${factoryId}`, kind: 'PURCHASE', factory_id: factoryId,
      document_no: `PO-${factoryId}`, document_type: 'INITIAL', date: '2026-09-24',
      created_at: '2026-09-24T10:00:00', status: '已生成', replenishment: false,
      orders: [{ order_no: 'SHARED-NO', customer_name: '客户', contract_no: 'SC-1', customer_po: '', item_no: 'ITEM-1', product_name: '', order_date: '', planned_date: '' }],
      lines: [{ order_no: 'SHARED-NO', child_no: 'SHARED-NO/01', packaging_type: '外箱', paper_quality: 'A33', specification: '10*20', unit: '个', before_quantity: '0', change_quantity: '10', quantity: '10' }],
    }])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text().includes('采购单与送货单'))!.trigger('click'); await flushPromises()
    await wrapper.get('input[aria-label="全选当前筛选单据"]').setValue(true)
    expect(wrapper.text()).toContain('已选 2 张单据 · 2 张订单')
    await wrapper.findAll('button').find(button => button.text().includes('预览并导出'))!.trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('2 张单据 / 2 张订单')
    wrapper.unmount()
  })

  it('stops selection at the 100-document export limit', async () => {
    api.documents.mockResolvedValue(Array.from({ length: 101 }, (_, index) => ({
      id: `ISSUE-${index}`, kind: 'PURCHASE', factory_id: 'huaxing', document_no: `PO-${index}`,
      document_type: 'INITIAL', date: '2026-09-24', created_at: '2026-09-24T10:00:00',
      status: '已生成', replenishment: false, orders: [], lines: [],
    })))
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text().includes('采购单与送货单'))!.trigger('click'); await flushPromises()
    await wrapper.get('input[aria-label="全选当前筛选单据"]').setValue(true)
    expect(wrapper.get('[role="alert"]').text()).toContain('一次最多选择 100 张单据')
    expect(wrapper.text()).toContain('已选 0 张单据')
    expect(api.exportDocuments).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
describe('supplier collaboration entry', () => {
  it('shows the business order date without the order number and previews details before pinning them', async () => {
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    const ledger = wrapper.findAll('table')[0]!
    expect(ledger.find('thead').text()).toContain('下单日期')
    expect(ledger.find('thead').text()).not.toContain('客户 / 订单')
    expect(ledger.find('tbody').text()).toContain('2026-09-10')
    expect(ledger.find('tbody').text()).not.toContain('ORDER-A')
    const button = wrapper.get('button[aria-label="查看订单 ORDER-A 明细"]')
    await button.trigger('mouseenter')
    expect(wrapper.get('[role="dialog"]').text()).toContain('悬停预览')
    expect(wrapper.get('[role="dialog"]').attributes('inert')).toBeDefined()
    await button.trigger('mouseleave')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await button.trigger('click')
    expect(wrapper.get('[role="dialog"]').attributes('aria-modal')).toBe('true')
    expect(wrapper.get('[role="dialog"]').attributes('inert')).toBeUndefined()
    await button.trigger('mouseleave')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('filters issued orders by acceptance, warehouse confirmation, completion and cancellation stage', async () => {
    const data = fixture()
    const source = data.orders[0]!
    const variant = (id: string) => {
      const order = structuredClone(source)
      order.id = id
      order.order_no = id
      order.lines = order.lines.map((line, index) => ({ ...line, id: `${id}-${index}`, child_no: `${id}/0${index + 1}` }))
      return order
    }
    const pending = variant('ORDER-PENDING'); pending.lines[0]!.accepted = false
    const accepted = variant('ORDER-ACCEPTED')
    const waiting = variant('ORDER-WAITING'); waiting.status = 'PARTIALLY_RECEIVED'; waiting.lines[0]!.received_quantity = '5'; waiting.lines[0]!.remaining_to_ship = '95'
    const inTransit = variant('ORDER-TRANSIT'); inTransit.status = 'PARTIALLY_RECEIVED'; inTransit.lines[0]!.in_transit_quantity = '5'; inTransit.lines[0]!.remaining_to_ship = '95'
    const completed = variant('ORDER-COMPLETE'); completed.status = 'COMPLETED'
    const cancelled = variant('ORDER-CANCEL'); cancelled.status = 'CANCELLED'
    const unissued = variant('ORDER-UNISSUED'); unissued.awaiting_issue = true
    data.orders = [cancelled, completed, inTransit, accepted, waiting, pending, unissued]
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    const rows = () => wrapper.findAll('table')[0]!.findAll('tbody tr')
    const filter = wrapper.get('select[aria-label="供应商订单状态筛选"]')
    expect(rows()[0]!.find('button[aria-label="查看订单 ORDER-PENDING 明细"]').exists()).toBe(true)
    expect(rows()[1]!.find('button[aria-label="查看订单 ORDER-WAITING 明细"]').exists()).toBe(true)
    for (const [value, id, label] of [
      ['PENDING_ACCEPTANCE', 'ORDER-PENDING', '待接单'],
      ['WAITING_SHIPMENT', 'ORDER-WAITING', '待送货'],
      ['ACCEPTED', 'ORDER-ACCEPTED', '已确认接单'],
      ['RECEIPT_PENDING', 'ORDER-TRANSIT', '待仓库验收'],
      ['COMPLETED', 'ORDER-COMPLETE', '已完成'],
      ['CANCELLED', 'ORDER-CANCEL', '已取消'],
      ['PENDING_ISSUE', 'ORDER-UNISSUED', '变更待生成'],
    ]) {
      await filter.setValue(value)
      expect(rows()).toHaveLength(1)
      expect(rows()[0]!.get(`button[aria-label="查看订单 ${id} 明细"]`)).toBeDefined()
      expect(rows()[0]!.text()).toContain(label)
      if (value === 'COMPLETED' || value === 'CANCELLED') {
        expect(rows()[0]!.get(`input[aria-label="选择订单 ${id}"]`).attributes('disabled')).toBeDefined()
      }
    }
    wrapper.unmount()
  })
  it('shows all authorized factories together while filtering locally and dispatching to each target factory', async () => {
    const serviceFactories = [
      { factory_id: 'huaxing', supplier_name: '河源东康' },
      { factory_id: 'huakang-a', supplier_name: '河源东康' },
    ]
    api.memberships.mockResolvedValue(serviceFactories)
    const other = fixture()
    other.factory_id = 'huakang-a'
    other.orders[0]!.id = 'ORDER-K'
    other.orders[0]!.order_no = 'ORDER-K'
    other.orders[0]!.lines = other.orders[0]!.lines.map((line, index) => ({ ...line, id: `K-LINE-${index}`, child_no: `ORDER-K/0${index + 1}` }))
    other.shipments[0]!.id = 'SHIP-K'
    other.shipments[0]!.delivery_note_no = 'DN-K'
    api.workspace.mockImplementation(async (scope: string) => scope === 'huakang-a' ? other : fixture())
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    const factoryFilter = wrapper.get('select[aria-label="供应商订单厂区筛选"]')
    expect(factoryFilter.findAll('option').map(option => option.attributes('value'))).toEqual(['', 'huaxing', 'huakang-a'])
    expect(wrapper.text()).toContain('服务厂区：2 个 · 订单合并展示')
    expect(wrapper.get('input[aria-label="选择订单 ORDER-K"]')).toBeDefined()
    expect(wrapper.get('input[aria-label="选择订单 ORDER-A"]')).toBeDefined()
    await wrapper.get('input[aria-label="选择订单 ORDER-A"]').setValue(true)
    await wrapper.get('button[aria-label="查看订单 ORDER-A 明细"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('A33'); expect(wrapper.get('[role="dialog"]').text()).toContain('10*20 cm')
    expect(wrapper.find('input[aria-label="选择发货 ORDER-A/01"]').exists()).toBe(false)
    await wrapper.get('button[aria-label="关闭供应商订单明细"]').trigger('click')
    await factoryFilter.setValue('huakang-a'); await flushPromises()
    expect(api.workspace).toHaveBeenCalledWith('huaxing')
    expect(api.workspace).toHaveBeenCalledWith('huakang-a')
    expect(router.replace).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('已选 1 张订单')
    expect(wrapper.get('input[aria-label="选择订单 ORDER-K"]')).toBeDefined()
    expect(wrapper.find('input[aria-label="选择订单 ORDER-A"]').exists()).toBe(false)
    await factoryFilter.setValue(''); await flushPromises()
    await wrapper.findAll('button').find(button => button.text().includes('发货与仓库反馈'))!.trigger('click')
    expect(wrapper.get('select[aria-label="供应商发货厂区筛选"]').element).toHaveProperty('value', '')
    expect(wrapper.text()).toContain('DN-K')
    expect(wrapper.text()).toContain('DN-A')
    wrapper.unmount()
  })
  it('keeps completed orders visible but excludes them from individual and bulk selection', async () => {
    const data = fixture()
    const second = structuredClone(data.orders[0]!)
    second.id = 'ORDER-B'
    second.order_no = 'ORDER-B'
    second.customer_name = 'BUZZ'
    second.contract_no = 'SC-B'
    second.item_no = 'ITEM-B'
    second.status = 'COMPLETED'
    second.lines = second.lines.map((line, index) => ({ ...line, id: `B-LINE-${index}`, child_no: `ORDER-B/0${index + 1}`, remaining_to_ship: '0' }))
    data.orders.push(second)
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    const ledgerRows = () => wrapper.findAll('table')[0]!.findAll('tbody tr')

    await wrapper.get('input[aria-label="顶部搜索"]').setValue('SC-A')
    expect(ledgerRows()).toHaveLength(1)
    await wrapper.get('input[aria-label="全选当前筛选订单"]').setValue(true)
    await wrapper.get('input[aria-label="顶部搜索"]').setValue('SC-B')
    expect(ledgerRows()).toHaveLength(1)
    expect(wrapper.get('input[aria-label="选择订单 ORDER-B"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('input[aria-label="全选当前筛选订单"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('已选 1 张订单')
    await wrapper.get('select[aria-label="供应商订单状态筛选"]').setValue('COMPLETED')
    expect(ledgerRows()).toHaveLength(1)
    await wrapper.findAll('button').find(button => button.text() === '清空筛选')!.trigger('click')
    expect(ledgerRows()).toHaveLength(2)
    await wrapper.get('input[aria-label="全选当前筛选订单"]').setValue(true)
    expect(wrapper.text()).toContain('已选 1 张订单')
    expect((wrapper.get('input[aria-label="全选当前筛选订单"]').element as HTMLInputElement).checked).toBe(true)
    await wrapper.findAll('button').find(button => button.text() === '查看已选')!.trigger('click')
    expect(ledgerRows()).toHaveLength(1)
    expect(ledgerRows()[0]!.get('button[aria-label="查看订单 ORDER-A 明细"]')).toBeDefined()
    data.orders[0]!.status = 'COMPLETED'
    await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('已选 0 张订单')
    expect(wrapper.get('input[aria-label="全选当前筛选订单"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
  it('filters by inclusive carton order dates and keeps the issued customer PO value', async () => {
    const data = fixture()
    const later = structuredClone(data.orders[0]!)
    later.id = 'ORDER-LATER'
    later.order_no = 'ORDER-LATER'
    later.order_date = '2026-09-20'
    later.customer_po = ''
    later.lines = later.lines.map((line, index) => ({ ...line, id: `LATER-${index}` }))
    data.orders.push(later)
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    const rows = () => wrapper.findAll('table')[0]!.findAll('tbody tr')
    expect(rows()).toHaveLength(2)
    expect(rows()[0]!.text()).toContain('客户 PO PO-A')
    expect(rows()[1]!.text()).toContain('客户 PO 纸箱订单未填写')
    await wrapper.get('input[aria-label="下单日期开始"]').setValue('2026-09-20')
    expect(rows()).toHaveLength(1)
    expect(rows()[0]!.text()).toContain('2026-09-20')
    await wrapper.get('input[aria-label="下单日期结束"]').setValue('2026-09-20')
    expect(rows()).toHaveLength(1)
    await wrapper.findAll('button').find(button => button.text() === '清空筛选')!.trigger('click')
    expect(rows()).toHaveLength(2)
    expect(wrapper.get<HTMLInputElement>('input[aria-label="下单日期开始"]').element.value).toBe('')
    wrapper.unmount()
  })
  it('does not strand reduced zero-demand paper in the pending-acceptance stage', async () => {
    const data = fixture()
    data.orders[0]!.lines[0]!.required_quantity = '0'
    data.orders[0]!.lines[0]!.remaining_to_ship = '0'
    data.orders[0]!.lines[0]!.accepted = false
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.find('button[aria-label="确认订单 ORDER-A 接单"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('导入送货单')
    await wrapper.get('button[aria-label="查看订单 ORDER-A 明细"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('需求已归零')
    await wrapper.get('button[aria-label="关闭供应商订单明细"]').trigger('click')
    wrapper.unmount()
  })
  it('closes acceptance when the last positive-demand paper is confirmed beside a zero-demand row', async () => {
    const data = fixture()
    data.orders[0]!.lines[0]!.required_quantity = '0'
    data.orders[0]!.lines[0]!.remaining_to_ship = '0'
    data.orders[0]!.lines[0]!.accepted = false
    data.orders[0]!.lines[1]!.accepted = false
    api.workspace.mockImplementation(async () => structuredClone(data))
    api.accept.mockImplementation(async () => { data.orders[0]!.lines[1]!.accepted = true })
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('button[aria-label="确认订单 ORDER-A 接单"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('需求已归零 · 无需接单')
    expect(wrapper.get('[role="dialog"]').findAll('button').filter(button => button.text() === '确认接单')).toHaveLength(1)
    await wrapper.get('[role="dialog"]').findAll('button').find(button => button.text() === '确认接单')!.trigger('click'); await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('导入送货单')
    wrapper.unmount()
  })
  it('keeps shipment feedback searchable on its own tab', async () => {
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text().includes('发货与仓库反馈'))!.trigger('click')
    expect(wrapper.text()).toContain('DN-A')
    await wrapper.get('input[aria-label="顶部搜索"]').setValue('UNMATCHED')
    expect(wrapper.text()).toContain('暂无符合条件的发货单')
    expect(wrapper.text()).not.toContain('DN-A')
    wrapper.unmount()
  })
  it('shows one price review panel with an explicit factory selector', async () => {
    api.memberships.mockResolvedValue([{ factory_id: 'huaxing', supplier_name: '河源东康' }, { factory_id: 'huadeng', supplier_name: '河源东康' }])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text().includes('发货与仓库反馈'))!.trigger('click'); await flushPromises()
    await wrapper.get('[aria-label="供应商协同分类"]').findAll('button').find(button => button.text().startsWith('收料核价'))!.trigger('click')
    const selector = wrapper.get<HTMLSelectElement>('[aria-label="供应商核价厂区"]')
    expect(selector.element.value).toBe('huaxing')
    expect(selector.text()).toContain('华兴'); expect(selector.text()).toContain('华登')
    expect(wrapper.findAllComponents({ name: 'CartonPriceReviews' })).toHaveLength(1)
    await selector.setValue('huadeng'); await flushPromises()
    expect(wrapper.findComponent({ name: 'CartonPriceReviews' }).props('factoryId')).toBe('huadeng')
    await wrapper.get('[aria-label="供应商发货厂区筛选"]').setValue('huaxing'); await flushPromises()
    expect(wrapper.findComponent({ name: 'CartonPriceReviews' }).props('factoryId')).toBe('huaxing')
    wrapper.unmount()
  })
  it('shows an unbound account message without requesting an arbitrary factory workspace', async () => {
    api.memberships.mockResolvedValue([])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('暂无可查看的服务厂区')
    expect(api.workspace).not.toHaveBeenCalled(); wrapper.unmount()
  })
  it('previews the supplier file and confirms selected matched notes', async () => {
    const preview = await api.previewDeliveryImport()
    preview.groups[0].rows[0].unit_price = 3.75
    api.previewDeliveryImport.mockResolvedValue(preview)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '导入送货单')!.trigger('click')
    const input = wrapper.get<HTMLInputElement>('input[type="file"]')
    const file = new File(['excel'], '送货明细表.xlsx')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change'); await flushPromises()
    expect(api.previewDeliveryImport).toHaveBeenCalledWith(file)
    expect(wrapper.get('[role="dialog"]').text()).toContain('DN-NEW')
    expect(wrapper.get('[role="dialog"]').text()).toContain('送货单价')
    expect(wrapper.get('[role="dialog"]').text()).toContain('3.75')
    await wrapper.findAll('button').find(button => button.text() === '确认 1 张送货单发货')!.trigger('click'); await flushPromises()
    expect(api.confirmDeliveryImport).toHaveBeenCalledWith(file, expect.objectContaining({ sha256: 'abc' }), [{ factory_id: 'huaxing', delivery_note_no: 'DN-NEW' }])
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('新发货由仓库验收')
    expect(wrapper.text()).toContain('已匹配手工收料的后补原单采用供应商价')
    expect(wrapper.text()).toContain('其他后补凭证由仓库关联，不重复入库')
    expect(api.ship).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('keeps unmatched supplier notes visible but unavailable for confirmation', async () => {
    const response = await api.previewDeliveryImport()
    response.groups[0].ready = false
    response.groups[0].rows[0].status = 'BLOCKED'
    response.groups[0].rows[0].reason = '客户料号为空，不能安全匹配订单'
    api.previewDeliveryImport.mockResolvedValue(response)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '导入送货单')!.trigger('click')
    const input = wrapper.get<HTMLInputElement>('input[type="file"]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['excel'], '送货明细表.xlsx')] })
    await input.trigger('change'); await flushPromises()
    expect(wrapper.get('[role="dialog"]').text()).toContain('客户料号为空')
    expect(wrapper.get('input[aria-label="确认送货单 DN-NEW"]').attributes('disabled')).toBeDefined()
    expect(api.confirmDeliveryImport).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('reports persisted supplier delivery before a failed workspace refresh', async () => {
    const wrapper = mount(CartonSupplierView, { global: { stubs: { ...options.global.stubs, Teleport: true } } }); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '导入送货单')!.trigger('click')
    const input = wrapper.get<HTMLInputElement>('input[type="file"]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['excel'], '送货明细表.xlsx')] })
    await input.trigger('change'); await flushPromises()
    api.workspace.mockRejectedValueOnce({ isAxiosError: true, message: 'Request failed with status code 503', response: { status: 503, data: { detail: '送货台账查询服务暂不可用' } } })
    await wrapper.findAll('button').find(button => button.text() === '确认 1 张送货单发货')!.trigger('click'); await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    const notice = wrapper.findComponent(CartonActionNotice)
    expect(notice.text()).toContain('发货已保存，但列表刷新失败：送货台账查询服务暂不可用')
    expect(notice.text()).toContain('勿重复发货')
    expect(api.confirmDeliveryImport).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
  it('routes a complete no-order candidate to warehouse review without calling it a formal order', async () => {
    const response = await api.previewDeliveryImport()
    response.groups[0].rows[0].status = 'AD_HOC_REVIEW'
    response.groups[0].rows[0].order_no = ''
    response.groups[0].rows[0].child_no = ''
    response.groups[0].rows[0].reason = '未找到正式订单；仓库必须核实是否为确需入库的样板箱或送错货'
    api.previewDeliveryImport.mockResolvedValue(response)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '导入送货单')!.trigger('click')
    const input = wrapper.get<HTMLInputElement>('input[type="file"]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['excel'], '送货明细表.xlsx')] })
    await input.trigger('change'); await flushPromises()
    expect(wrapper.get('[role="dialog"]').text()).toContain('含仓库待核实无单纸品')
    expect(wrapper.get('[role="dialog"]').text()).toContain('无单待仓库核实')
    expect(wrapper.get('input[aria-label="确认送货单 DN-NEW"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })
  it('requires a commitment before dispatch and sends the issued version and expected revision', async () => {
    const data = fixture(); data.orders[0]!.lines[0]!.accepted = false
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('button[aria-label="查看订单 ORDER-A 明细"]').trigger('click')
    expect(wrapper.find('input[aria-label="选择发货 ORDER-A/01"]').exists()).toBe(false)
    await wrapper.get('button[aria-label="关闭供应商订单明细"]').trigger('click')
    expect(wrapper.text()).toContain('导入送货单')
    await wrapper.get('button[aria-label="确认订单 ORDER-A 接单"]').trigger('click')
    await wrapper.get('input[aria-label="ORDER-A/01 承诺交期"]').setValue('2026-09-28')
    await wrapper.get('[role="dialog"]').findAll('button').find(button => button.text() === '确认接单')!.trigger('click'); await flushPromises()
    expect(api.accept).toHaveBeenCalledWith(expect.objectContaining({ id: 'LINE-0', commitment_revision: 1 }), expect.objectContaining({ issue_id: 'ISSUE-A' }), 'huaxing', '2026-09-28'); wrapper.unmount()
  })
})
describe('internal supplier collaboration', () => {
  it('keeps a new operation locked when an older A factory request finishes after A to B to A', async () => {
    let oldFinish: (value: object) => void = () => {}, newFinish: (value: object) => void = () => {}
    api.receive.mockImplementationOnce(() => new Promise(resolve => { oldFinish = resolve }))
      .mockImplementationOnce(() => new Promise(resolve => { newFinish = resolve }))
    const wrapper = mount(CartonSupplierReceiving, { ...options, props: { factoryId: 'huaxing' } }); await flushPromises()
    const submitZero = async () => {
      await wrapper.findAll('button').find(button => button.text() === '核实实际收到')!.trigger('click')
      for (const input of wrapper.findAll('input[aria-label$=" 实收"]')) await input.setValue(0)
      await wrapper.get('form').trigger('submit'); await flushPromises()
    }
    await submitZero()
    await wrapper.setProps({ factoryId: 'huakang-a' }); await flushPromises()
    await wrapper.setProps({ factoryId: 'huaxing' }); await flushPromises()
    await submitZero()
    oldFinish({ id: 'OLD' }); await flushPromises()
    expect(wrapper.get('form').findAll('button').at(-1)!.attributes('disabled')).toBeDefined()
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.receive).toHaveBeenCalledTimes(2)
    newFinish({ id: 'NEW' }); await flushPromises()
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.findAll('button').find(button => button.text() === '刷新')!.attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })
  it('replaces the retired attachment uploads with a focused receiving workspace', async () => {
    const wrapper = mount(CartonSupplierReceiving, options); await flushPromises()
    expect(wrapper.find('[aria-label="供应商收货工作区"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('订单资料 / PDF')
    expect(wrapper.find('input[type="file"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('待核实 1')
    wrapper.unmount()
  })

  it('offers reversal only for posted receipts and emits the original receipt identifier', async () => {
    const data = fixture()
    data.shipments[0]!.status = 'RECEIVED'
    data.shipments[0]!.receipt_id = 'CTR-POSTED'
    data.shipments[0]!.receipt_status = 'POSTED'
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierReceiving, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '已核实记录')!.trigger('click')
    await wrapper.get('[aria-label="冲销送货单 DN-A 的收料"]').trigger('click')
    expect(wrapper.emitted('reverse')).toEqual([['CTR-POSTED']])
    expect(api.receive).not.toHaveBeenCalled()
    wrapper.unmount()
    can.mockImplementation(permission => permission === 'carton_procurement:read')
    const readOnly = mount(CartonSupplierReceiving, options); await flushPromises()
    await readOnly.findAll('button').find(button => button.text() === '已核实记录')!.trigger('click')
    expect(readOnly.find('[aria-label="冲销送货单 DN-A 的收料"]').exists()).toBe(false)
    readOnly.unmount()
  })
  it('requires a reason before correcting reversed receipt and carries it with the original note', async () => {
    const data = fixture()
    data.shipments[0]!.status = 'RECEIPT_REVERSED'
    data.shipments[0]!.requires_correction = true
    data.shipments[0]!.receipt_status = 'REVERSED'
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierReceiving, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '更正原单验收')!.trigger('click')
    for (const input of wrapper.findAll('input[aria-label$=" 实收"]')) await input.setValue(0)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.receive).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请填写至少四字更正原因')
    await wrapper.get('input[aria-label="送货单验收更正原因"]').setValue('重核原单实际收到')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.receive).toHaveBeenCalledWith('SHIP-A', expect.objectContaining({ correction_reason: '重核原单实际收到', expected_revision: 1 }))
    wrapper.unmount()
  })

  it('requires customer and explicit paper selection to link a no-order delivery before receiving', async () => {
    const data = fixture()
    data.orders[0]!.customer_code = 'DICKIE'
    data.orders[0]!.revision = 3
    data.shipments[0]!.lines = [{ ...data.shipments[0]!.lines[0]!, id: 'UNMATCHED', source_type: 'AD_HOC_REVIEW', order_line_id: null }]
    api.workspace.mockResolvedValue(data)
    api.linkShipmentLine.mockResolvedValue(data.shipments[0])
    const wrapper = mount(CartonSupplierReceiving, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '核实实际收到')!.trigger('click'); await flushPromises()
    expect(wrapper.get('button[aria-label="UNMATCHED 验收确认关联"]').attributes('disabled')).toBeDefined()
    await wrapper.get('select[aria-label="UNMATCHED 验收关联客户"]').setValue('DICKIE')
    const target = wrapper.get('select[aria-label="UNMATCHED 验收关联订单"]')
    expect(target.findAll('option').map(option => option.attributes('value'))).toEqual(['', 'LINE-0'])
    await target.setValue('LINE-0')
    await wrapper.get('input[aria-label="UNMATCHED 验收关联原因"]').setValue('核对补建的正式订单')
    await wrapper.get('button[aria-label="UNMATCHED 验收确认关联"]').trigger('click'); await flushPromises()
    expect(api.linkShipmentLine).toHaveBeenCalledWith('SHIP-A', 'UNMATCHED', {
      factory_id: 'huaxing', customer_code: 'DICKIE', order_line_id: 'LINE-0',
      expected_revision: 1, expected_order_revision: 3, reason: '核对补建的正式订单',
    })
    expect(api.receive).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('links a posted sample to a later formal line through an explicit warehouse action', async () => {
    const data = fixture()
    data.orders[0]!.customer_code = 'DICKIE'
    data.orders[0]!.revision = 3
    data.shipments[0]!.status = 'RECEIVED'
    data.shipments[0]!.receipt_status = 'POSTED'
    data.shipments[0]!.sample_receipts = [{ receipt_line_id: 'RL-SAMPLE', customer_code: 'DICKIE',
      customer_name: 'Dickie', contract_no: 'SAMPLE-1', item_no: 'ITEM-A', packaging_type: '外箱',
      paper_quality: 'A33', specification: '10*20', unit: '个', quantity: '4', linked_order_line_id: '' }]
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierReceiving, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '已核实记录')!.trigger('click')
    await wrapper.get('select[aria-label="RL-SAMPLE 关联正式订单"]').setValue('LINE-0')
    await wrapper.get('input[aria-label="RL-SAMPLE 关联原因"]').setValue('样板箱转正式订单')
    await wrapper.findAll('button').find(button => button.text() === '关联后续订单')!.trigger('click'); await flushPromises()
    expect(api.linkSampleReceipt).toHaveBeenCalledWith('RL-SAMPLE', {
      factory_id: 'huaxing', order_line_id: 'LINE-0', expected_order_revision: 3, reason: '样板箱转正式订单',
    })
    expect(wrapper.text()).toContain('不重复过账')
    wrapper.unmount()
  })
  it('requires explicit classification before receiving unmatched deliveries', async () => {
    const data = fixture()
    data.shipments[0]!.lines = [{ id: 'SL-SAMPLE', order_line_id: null, source_type: 'AD_HOC_REVIEW',
      order_no: '', contract_no: 'SAMPLE-1', customer_po: '', item_no: 'SAMPLE-BOX', customer_name: '',
      child_no: '', packaging_type: '外箱', paper_quality: 'A33+B', specification: '18*12.5*17.25 cm',
      unit: '个', quantity: '4', unit_price: '2.5', currency: 'CNY' }]
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierReceiving, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '核实实际收到')!.trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('无正式订单 · 仓库必须核实')
    await wrapper.get('[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.receive).not.toHaveBeenCalled()
    expect(wrapper.get('[role="dialog"]').text()).toContain('正单请先补建或关联订单')
    expect(wrapper.get('select[aria-label="SL-SAMPLE 无单处理结论"]').findAll('option').map(option => option.attributes('value'))).toContain('SAMPLE')
    expect(wrapper.text()).toContain('样板单、杂单和免费赠送可在下方选择类型直接验收入库')
    wrapper.unmount()
  })
  it('uses read-only supplier original prices without warehouse price review', async () => {
    const data = fixture()
    data.shipments[0]!.lines[0]!.delivery_unit_price = '3.75'
    data.shipments[0]!.lines[1]!.delivery_unit_price = '4'
    data.shipments[0]!.lines[1]!.currency = 'HKD'
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierReceiving, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '核实实际收到')!.trigger('click')
    expect(wrapper.get<HTMLInputElement>('[aria-label="SL-0 入库单价"]').element.value).toBe('3.75')
    expect(wrapper.get<HTMLInputElement>('[aria-label="SL-1 入库单价"]').element.value).toBe('4')
    expect(wrapper.get('[aria-label="SL-0 入库单价"]').attributes('readonly')).toBeDefined()
    expect(wrapper.find('[aria-label="SL-0 价格核对"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('opens only the matching pending delivery note from a notification link', async () => {
    routeState.query.shipment = 'SHIP-A'
    const wrapper = mount(CartonSupplierReceiving, options); await flushPromises()
    expect(wrapper.find('notification-center-stub').exists()).toBe(false)
    expect(wrapper.get('[role="dialog"]').text()).toContain('核实送货单 DN-A')
    await wrapper.get('[role="dialog"]').findAll('button').find(button => button.text() === '取消')!.trigger('click')
    await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click'); await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('does not render the retired supplier account authorization form', async () => {
    const wrapper = mount(CartonSupplierReceiving, options); await flushPromises()
    expect(wrapper.text()).not.toContain('供应商协同账号授权')
    expect(wrapper.find('input[aria-label="绑定供应商登录名"]').exists()).toBe(false)
    expect(api.members).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('hides privileged member and attachment controls for a receipt-only warehouse operator', async () => {
    can.mockImplementation(permission => ['carton_procurement:read', 'carton_procurement:receipt_write', 'carton_procurement:inventory_write'].includes(permission))
    const wrapper = mount(CartonSupplierReceiving, options); await flushPromises()
    expect(wrapper.text()).not.toContain('供应商协同账号授权')
    expect(wrapper.find('input[type="file"]').exists()).toBe(false)
    expect(api.members).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('核实实际收到'); wrapper.unmount()
  })
  it('allows explicit all-zero non-arrival with reasons and closes a successful confirmation before refresh', async () => {
    const wrapper = mount(CartonSupplierReceiving, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '核实实际收到')!.trigger('click')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="SL-0 实收"]').element.value).toBe('10')
    for (const input of wrapper.findAll('input[aria-label$=" 实收"]')) await input.setValue(0)
    for (const input of wrapper.findAll('input[aria-label$=" 差异原因"]')) await input.setValue('货物尚未实际送到')
    await wrapper.get('[aria-label="未收余货处理"]').setValue('CLOSE')
    expect(wrapper.get('[role="dialog"]').text()).toContain('确认未收余货不再送')
    api.workspace.mockRejectedValueOnce(new Error('台账刷新失败'))
    await wrapper.get('[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.receive).toHaveBeenCalledWith('SHIP-A', expect.objectContaining({ expected_revision: 1, lines: [expect.objectContaining({ shipment_line_id: 'SL-0', received_quantity: 0, difference_reason: '货物尚未实际送到' }), expect.objectContaining({ shipment_line_id: 'SL-1', received_quantity: 0 })] }))
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('[role="status"]').text()).toContain('仓库核实已保存'); wrapper.unmount()
  })
  it('retains partial quantities and differences on atomic receipt failure', async () => {
    api.receive.mockRejectedValue(new Error('单价或仓位无效，本次未入库'))
    const wrapper = mount(CartonSupplierReceiving, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '核实实际收到')!.trigger('click')
    await wrapper.get('input[aria-label="SL-0 实收"]').setValue(6)
    await wrapper.get('input[aria-label="SL-0 差异原因"]').setValue('短收四件待核实')
    await wrapper.findAll('button').filter(button => button.text() === '此项未到')[1]!.trigger('click')
    wrapper.findAllComponents(CartonReceiptAllocations)[0]!.vm.$emit('update:modelValue', [{ location_id: 'BIN-A', quantity: 6 }])
    await wrapper.get('[role="dialog"]').trigger('submit'); await flushPromises()
    expect(wrapper.get<HTMLInputElement>('input[aria-label="SL-0 实收"]').element.value).toBe('6')
    expect(wrapper.get('[role="dialog"]').text()).toContain('本次未入库'); wrapper.unmount()
  })
  it('requires complete valid allocations for positive effective receipts before sending', async () => {
    const wrapper = mount(CartonSupplierReceiving, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '核实实际收到')!.trigger('click')
    await wrapper.get('input[aria-label="SL-0 实收"]').setValue(6)
    await wrapper.findAll('button').filter(button => button.text() === '此项未到')[1]!.trigger('click')
    for (const input of wrapper.findAll('input[aria-label$="差异原因"]')) await input.setValue('本次到货差异待核实')
    await wrapper.get('[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.receive).not.toHaveBeenCalled()
    expect(wrapper.get('[role="dialog"]').text()).toContain('必须选择有效仓位')
    const allocations = wrapper.findAllComponents(CartonReceiptAllocations)[0]!
    allocations.vm.$emit('update:modelValue', [{ location_id: 'BIN-A', quantity: 5 }])
    await wrapper.get('[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.receive).not.toHaveBeenCalled()
    expect(wrapper.get('[role="dialog"]').text()).toContain('合计必须等于')
    allocations.vm.$emit('update:modelValue', [{ location_id: 'unknown-bin', quantity: 6 }])
    await wrapper.get('[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.receive).not.toHaveBeenCalled()
    allocations.vm.$emit('update:modelValue', [{ location_id: 'BIN-A', quantity: 6 }])
    await wrapper.get('[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.receive).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false); wrapper.unmount()
  })
})


describe('supplier collaboration workbench', () => {
  const category = (wrapper: ReturnType<typeof mount>, label: string) => wrapper.get('[aria-label="供应商协同分类"]').findAll('button').find(button => button.text().startsWith(label))!
  function task(kind: SupplierChangeTask['source_kind'], id: string): SupplierChangeTask {
    return { source_kind: kind, source_id: id, factory_id: 'huaxing', order_id: 'ORDER-A', order_no: 'ORDER-A', document_no: id, expected_revision: 4,
      status: 'PENDING', is_cancellation: false, read: false, read_at: '', reason: '', responded_by: '', responded_at: '', promised_date: '', planned_date: '2026-10-25', before_date: '',
      created_at: '2026-10-20', age_days: 0, overdue: false, action: 'APPEND', responsibility: 'OWN', lines: [], material_changed: false, pending: true, can_respond: true }
  }
  function correction(id: string, status: MaterialCorrection['status']): MaterialCorrection {
    return { id, status, factory_id: 'huaxing', order_id: 'ORDER-A', order_no: 'ORDER-A', contract_no: `SC-${id}`, item_no: 'ITEM-A', order_line_id: 'LINE-0', issue_id: 'ISSUE-A', document_no: 'ORDER-A-P00',
      before: { packaging_type: '外箱', paper_quality: 'A33', specification: '10*20', dimension_unit: 'cm' }, after: { packaging_type: '外箱', paper_quality: 'A44', specification: '10*20', dimension_unit: 'cm' },
      revision: 1, reason: '纸质需核实', created_at: '2026-10-20', created_by_name: '仓库', resolved_at: '', resolved_by_name: '', response_note: '', corrected_document_no: '' }
  }
  it('uses one response instance for all categories, retaining drafts and separating initial B acceptance from saved B promises', async () => {
    const data = fixture(), regular = task('REGULAR', 'TASK-REGULAR'), special = task('SPECIAL', 'TASK-SPECIAL'), replacement = task('REPLENISHMENT', 'TASK-B01')
    changesApi.list.mockResolvedValue({ items: [regular, special, replacement], pending_count: 3, overdue_count: 0, disputed_count: 0 })
    data.orders[0]!.replenishment_sources = ['B1', 'B2'].map((issue_id, index) => ({ issue_id, document_no: `PROMISE-${issue_id}`, responsibility: 'OWN', planned_date: '2026-10-25', lines: [{ ...data.orders[0]!.lines[0]!, accepted: index === 1 }] }))
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    const instance = wrapper.getComponent(CartonSupplierChangeTasks).element
    expect(category(wrapper, '订单与变更').text()).toContain('2 项待确认')
    expect(category(wrapper, '补单接单与交期').text()).toContain('1 项待确认')
    expect(category(wrapper, '订单与变更').attributes('aria-expanded')).toBe('false')
    await category(wrapper, '订单与变更').trigger('click')
    await wrapper.get('[aria-label="TASK-REGULAR承诺交期"]').setValue('2026-10-28')
    await wrapper.get('[aria-label="TASK-REGULAR异议说明"]').setValue('请先核对规格')
    await category(wrapper, '补单接单与交期').trigger('click')
    expect(wrapper.getComponent(CartonSupplierChangeTasks).isVisible()).toBe(true)
    expect(wrapper.find('[aria-label="TASK-B01异议说明"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="TASK-REGULAR异议说明"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="PROMISE-B1 确认补单接单"]').exists()).toBe(false)
    expect(wrapper.get('[aria-label="PROMISE-B2 保存补单承诺"]').isVisible()).toBe(true)
    await wrapper.get('[aria-label="PROMISE-B2 补单承诺交期"]').setValue('2026-10-29')
    await category(wrapper, '纸品资料更正').trigger('click')
    await category(wrapper, '订单与变更').trigger('click')
    expect(wrapper.getComponent(CartonSupplierChangeTasks).element).toBe(instance)
    expect(changesApi.list).toHaveBeenCalledTimes(1)
    expect((wrapper.get('[aria-label="TASK-REGULAR承诺交期"]').element as HTMLInputElement).value).toBe('2026-10-28')
    expect((wrapper.get('[aria-label="TASK-REGULAR异议说明"]').element as HTMLTextAreaElement).value).toBe('请先核对规格')
    await category(wrapper, '补单接单与交期').trigger('click')
    expect((wrapper.get('[aria-label="PROMISE-B2 补单承诺交期"]').element as HTMLInputElement).value).toBe('2026-10-29')
    wrapper.unmount()
  })
  it('keeps completed correction history reachable above the ledger without supplier More or repeated row history actions', async () => {
    const data = fixture(); data.orders[0]!.material_corrections = [correction('PENDING', 'PENDING'), correction('PAST', 'APPROVED')]
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierView, { global: { stubs: { ...options.global.stubs, CartonMaterialCorrectionDialog: true } } }); await flushPromises()
    const update = wrapper.get('[aria-label="更新订单 ORDER-A 承诺交期"]')
    expect(update.element.nextElementSibling?.getAttribute('aria-label')).toBe('查看订单 ORDER-A 明细')
    expect(wrapper.find('[aria-label="ORDER-A 更多操作"]').exists()).toBe(false)
    expect(wrapper.findAll('button').some(button => button.text() === '更正记录')).toBe(false)
    await category(wrapper, '纸品资料更正').trigger('click')
    const material = wrapper.get('[aria-label="纸品资料更正待办"]')
    expect(material.text()).toContain('SC-PENDING'); expect(material.text()).not.toContain('SC-PAST')
    await material.findAll('button').find(button => button.text().startsWith('已处理记录'))!.trigger('click')
    expect(material.text()).toContain('SC-PAST'); expect(material.text()).not.toContain('SC-PENDING')
    await material.findAll('button').find(button => button.text() === '查看更正记录')!.trigger('click')
    expect(wrapper.getComponent({ name: 'CartonMaterialCorrectionDialog' }).props()).toMatchObject({ factoryId: 'huaxing', recordId: 'PAST', supplier: true })
    wrapper.unmount()
  })
  it('shows only on orders while the separate cancellation alert remains available in other supplier pages', async () => {
    const data = fixture(); data.orders[0]!.status = 'CANCELLED'; data.orders[0]!.cancellation_notice = { issue_id: 'CANCEL', order_revision: 4, issued: true, acknowledged: false, acknowledged_at: '' }
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierView, guideOptions); await flushPromises()
    expect(wrapper.get('[aria-label="供应商协同工作台"]').isVisible()).toBe(true)
    await wrapper.get('nav[aria-label="供应商协同功能"]').findAll('button').find(button => button.text() === '月结对账')!.trigger('click'); await flushPromises()
    expect(wrapper.find('[aria-label="供应商月结子页面"]').exists()).toBe(true)
    expect(wrapper.get('[aria-label="供应商协同工作台"]').attributes('style')).toContain('display: none')
    expect(wrapper.get('[aria-label="待确认取消通知"]').isVisible()).toBe(true)
    wrapper.unmount()
  })
  it('restricts changes reads to published membership factories while retaining published special-only factories', async () => {
    api.memberships.mockResolvedValue([{ factory_id: 'huaxing' }, { factory_id: 'huakang-a' }])
    specialApi.factories.mockResolvedValue([{ factory_id: 'huaxing' }, { factory_id: 'huakang-a' }, { factory_id: 'huakang-b' }])
    api.workspace.mockImplementation(async factory => ({ ...fixture(), factory_id: factory, orders: factory === 'huaxing' ? fixture().orders : [] }))
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.getComponent(CartonSupplierChangeTasks).props('factories')).toEqual([{ factory_id: 'huaxing' }, { factory_id: 'huakang-a' }])
    expect(changesApi.list.mock.calls.map(call => call[0])).toEqual(['huakang-a', 'huaxing'])
    expect(changesApi.list).not.toHaveBeenCalledWith('huakang-b', expect.anything(), expect.anything())
    wrapper.unmount()
  })
  it('labels unavailable task reads and membership discovery as errors instead of zero pending work', async () => {
    changesApi.list.mockRejectedValue(new Error('无权读取该厂区'))
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(category(wrapper, '订单与变更').text()).toContain('暂不可用')
    expect(category(wrapper, '补单接单与交期').text()).toContain('暂不可用')
    expect(wrapper.get('[aria-label="供应商变更待办"]').text()).toContain('无权读取该厂区')
    wrapper.unmount()
    api.memberships.mockRejectedValue(new Error('服务厂区读取失败'))
    specialApi.factories.mockResolvedValue([{ factory_id: 'huaxing' }])
    const failedDiscovery = mount(CartonSupplierView, options); await flushPromises()
    expect(category(failedDiscovery, '订单与变更').text()).toContain('暂不可用')
    expect(failedDiscovery.get('[aria-label="供应商协同工作台"]').text()).toContain('版本回执服务厂区读取失败')
    expect(failedDiscovery.get('[aria-label="供应商变更待办"]').isVisible()).toBe(false)
    failedDiscovery.unmount()
  })
  it('retries membership discovery from material errors and clears stale failure after a valid empty membership result', async () => {
    api.memberships.mockRejectedValueOnce(new Error('厂区读取失败')).mockResolvedValueOnce([])
    specialApi.factories.mockResolvedValue([{ factory_id: 'huaxing' }])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await category(wrapper, '纸品资料更正').trigger('click')
    expect(category(wrapper, '纸品资料更正').text()).toContain('暂不可用')
    const material = wrapper.get('[aria-label="纸品资料更正待办"]')
    await material.findAll('button').find(button => button.text() === '重新读取')!.trigger('click'); await flushPromises()
    expect(api.memberships).toHaveBeenCalledTimes(2)
    expect(category(wrapper, '纸品资料更正').text()).toContain('0 项待处理')
    expect(material.text()).toContain('当前没有待处理的资料更正')
    expect(material.text()).not.toContain('读取失败')
    expect(category(wrapper, '订单与变更').text()).toContain('0 项待确认')
    wrapper.unmount()
  })
  it('keeps read-only supplier roles from editing ordinary or accepted B promises', async () => {
    can.mockImplementation(permission => permission !== 'carton_supplier:approve')
    const data = fixture()
    data.orders[0]!.replenishment_sources = [{ issue_id: 'B1', document_no: 'READONLY-B1', responsibility: 'OWN', planned_date: '2026-10-25', lines: [data.orders[0]!.lines[0]!] }]
    api.workspace.mockResolvedValue(data)
    changesApi.list.mockResolvedValue({ items: [{ ...task('REPLENISHMENT', 'READONLY-TASK'), can_respond: false }], pending_count: 1, overdue_count: 0, disputed_count: 0 })
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.find('[aria-label="更新订单 ORDER-A 承诺交期"]').exists()).toBe(false)
    await category(wrapper, '补单接单与交期').trigger('click')
    expect(wrapper.text()).toContain('请由有供应商接单确认权限的人员明确回应')
    expect(wrapper.find('[aria-label="READONLY-TASK承诺交期"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="READONLY-B1 保存补单承诺"]').exists()).toBe(false)
    expect(api.acceptBatch).not.toHaveBeenCalled(); expect(changesApi.respond).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it.each(['COMPLETED', 'CANCELLED', 'PENDING_SUPPLIER'])('does not expose ordinary promise editing for %s without active accepted demand', async status => {
    const data = fixture(); data.orders[0]!.status = status
    if (status === 'PENDING_SUPPLIER') for (const line of data.orders[0]!.lines) line.required_quantity = '0'
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.find('[aria-label="更新订单 ORDER-A 承诺交期"]').exists()).toBe(false)
    wrapper.unmount()
  })
})

describe('unified supplier acceptance', () => {
  function source(patch: Partial<SpecialRequest> = {}): SpecialRequest {
    return { id: 'SP-ID', request_no: 'SP-ACCEPT', factory_id: 'huaxing', kind: 'SAMPLE', title: '', requester_name: '员工', status: 'SENT', revision: 7,
      current_version_id: 'SPECIAL-V7', quote_version_id: '', pricing_kind: 'PENDING_QUOTE', promised_date: '', customer_code: '', customer_name: '样板客户', workshop_id: '', purpose: '', required_date: '2026-10-25', created_at: '2026-10-19',
      lines: ['外箱', '平卡'].map((packaging_type, index) => ({ id: `SP-L${index}`, packaging_type, paper_quality: 'A33', specification: '10*20', dimension_unit: 'cm', quantity: '10', unit: '个', item_no: 'ITEM-SP' })),
      shipments: [], attachments: [], messages: [], history: [], permissions: {},
      supplier_confirmation: { status: 'PENDING', version_id: 'SPECIAL-V7', promised_date: '', reason: '', responded_by: '', responded_at: '' }, ...patch }
  }
  function supply(rows: SpecialRequest[]) {
    specialApi.factories.mockResolvedValue([{ factory_id: 'huaxing', supplier_name: '河源东康' }])
    specialApi.list.mockImplementation(async () => ({ items: structuredClone(rows), total: rows.length, can_create: false }))
    specialApi.detail.mockImplementation(async (_factory, id) => structuredClone(rows.find(row => row.id === id)))
  }
  const button = (wrapper: ReturnType<typeof mount>, label: string) => wrapper.findAll('button').find(row => row.text() === label)!
  const category = (wrapper: ReturnType<typeof mount>, label: string) => wrapper.get('[aria-label="供应商协同分类"]').findAll('button').find(row => row.text().startsWith(label))!
  it('starts with only category summaries and retains the task instance and drafts when collapsed again', async () => {
    const row = { source_kind: 'SPECIAL', source_id: 'TASK', factory_id: 'huaxing', order_no: 'SP-ACCEPT', document_no: 'TASK-SP', expected_revision: 7, status: 'PENDING', planned_date: '2026-10-25', created_at: '2026-10-20', pending: true, can_respond: true, lines: [] }
    changesApi.list.mockResolvedValue({ items: [row] })
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    const content = wrapper.get('#supplier-collaboration-content'), instance = wrapper.getComponent(CartonSupplierChangeTasks).element
    expect(content.attributes('style')).toContain('display: none')
    expect(category(wrapper, '订单与变更').attributes('aria-expanded')).toBe('false')
    await category(wrapper, '订单与变更').trigger('click')
    await wrapper.get('[aria-label="TASK-SP承诺交期"]').setValue('2026-10-29')
    await category(wrapper, '订单与变更').trigger('click')
    expect(content.attributes('style')).toContain('display: none')
    await category(wrapper, '订单与变更').trigger('click')
    expect(wrapper.getComponent(CartonSupplierChangeTasks).element).toBe(instance)
    expect(wrapper.get<HTMLInputElement>('[aria-label="TASK-SP承诺交期"]').element.value).toBe('2026-10-29')
    expect(changesApi.list).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
  it.each(['SAMPLE', 'WORKSHOP_MISC'] as const)('accepts every paper in one current %s version and updates its same-version promise', async kind => {
    const row = source({ kind }); supply([row])
    changesApi.respond.mockImplementation(async body => {
      row.supplier_confirmation = { status: 'ACCEPTED', version_id: body.source_id, promised_date: body.promised_date, reason: '', responded_at: '', responded_by: '供应商' }
      return { responded_at: '', responded_by: '供应商' }
    })
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    const accept = wrapper.get('[aria-label="确认订单 SP-ACCEPT 接单"]')
    expect(accept.element.nextElementSibling?.getAttribute('aria-label')).toBe('查看订单 SP-ACCEPT 明细')
    expect(wrapper.get('[aria-label="供应商工作统计"]').text()).toContain('待接单1')
    await accept.trigger('click'); await flushPromises()
    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.findAll('input[type="date"]')).toHaveLength(1)
    expect(dialog.text()).toContain('外箱'); expect(dialog.text()).toContain('平卡')
    await wrapper.get('[aria-label="SP-ACCEPT 整单承诺交期"]').setValue('2026-10-28')
    await dialog.findAll('button').find(row => row.text() === '确认接单')!.trigger('click'); await flushPromises()
    expect(changesApi.respond.mock.calls[0]![0]).toMatchObject({ factory_id: 'huaxing', source_kind: 'SPECIAL', source_id: 'SPECIAL-V7', expected_revision: 7, action: 'ACCEPT', promised_date: '2026-10-28' })
    expect(changesApi.respond.mock.calls[0]![0].request_id).toMatch(/^[0-9a-f-]{36}$/)
    expect(api.accept).not.toHaveBeenCalled()
    await wrapper.get('[aria-label="更新订单 SP-ACCEPT 承诺交期"]').trigger('click'); await flushPromises()
    await wrapper.get('[aria-label="SP-ACCEPT 整单承诺交期"]').setValue('2026-10-30')
    await wrapper.get('[role="dialog"]').findAll('button').find(row => row.text() === '保存承诺交期')!.trigger('click'); await flushPromises()
    expect(changesApi.respond.mock.calls[1]![0]).toMatchObject({ source_id: 'SPECIAL-V7', expected_revision: 7, promised_date: '2026-10-30' })
    expect(changesApi.respond.mock.calls[1]![0].request_id).not.toBe(changesApi.respond.mock.calls[0]![0].request_id)
    expect(wrapper.get('[data-testid="supplier-special-order-row"]').text()).toContain('承诺 2026-10-30')
    wrapper.unmount()
  })
  it('treats stale confirmation and disputes as pending, using only a current accepted promise for date filtering', async () => {
    const stale = source({ supplier_confirmation: { ...source().supplier_confirmation!, version_id: 'OLD', status: 'ACCEPTED', promised_date: '2026-10-28' } })
    supply([stale])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    const status = wrapper.get('[aria-label="供应商订单状态筛选"]')
    expect(status.findAll('option').map(option => option.attributes('value'))).not.toEqual(expect.arrayContaining(['SENT', 'QUOTED', 'READY']))
    expect(status.text()).not.toContain('已确认锁定')
    expect(wrapper.get('[data-testid="supplier-special-order-row"]').text()).toContain('待接单')
    await wrapper.get('[aria-label="供应商订单状态筛选"]').setValue('PENDING_ACCEPTANCE')
    expect(wrapper.get('tbody').text()).toContain('SP-ACCEPT')
    await wrapper.get('[aria-label="供应商订单日期口径"]').setValue('PROMISED')
    await wrapper.get('[aria-label="下单日期开始"]').setValue('2026-10-28')
    expect(wrapper.get('tbody').text()).not.toContain('SP-ACCEPT')
    wrapper.unmount()
  })
  it.each(['COMPLETED', 'CANCELLED', 'SUPPLIER_ORIGIN', 'DENIED'] as const)('keeps %s sources from supplier promise actions', async state => {
    const row = source(state === 'SUPPLIER_ORIGIN' ? { origin: 'SUPPLIER_EXTRA' } : state === 'DENIED' ? {} : { status: state })
    if (state === 'DENIED') can.mockImplementation((permission, factory) => !(permission === 'carton_supplier:approve' && factory === 'huaxing'))
    supply([row])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.find('[aria-label="确认订单 SP-ACCEPT 接单"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="更新订单 SP-ACCEPT 承诺交期"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="查看订单 SP-ACCEPT 明细"]').exists()).toBe(true)
    wrapper.unmount()
  })
  it('uses typed source selection across filters even when a special and ordinary source share an ID', async () => {
    supply([source({ id: 'ORDER-A' }), source({ id: 'MISC', request_no: 'SP-MISC', kind: 'WORKSHOP_MISC' })])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('[aria-label="全选当前筛选订单"]').setValue(true)
    expect(wrapper.text()).toContain('已选 3 张订单')
    await wrapper.get('[aria-label="供应商订单类型筛选"]').setValue('SAMPLE')
    expect(wrapper.text()).toContain('筛选外 2 张')
    await button(wrapper, '查看已选').trigger('click')
    expect(wrapper.find('[aria-label="选择订单 ORDER-A"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="选择订单 SP-ACCEPT"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="选择订单 SP-MISC"]').exists()).toBe(true)
    await wrapper.get('[aria-label="选择订单 SP-ACCEPT"]').setValue(false)
    expect(wrapper.get<HTMLInputElement>('[aria-label="选择订单 ORDER-A"]').element.checked).toBe(true)
    wrapper.unmount()
  })
  it('retains only failures after mixed independent saves and retries the same special body without repeating successes', async () => {
    const data = fixture(); data.orders[0]!.lines.forEach(line => { line.accepted = false })
    api.workspace.mockResolvedValue(data)
    supply([source(), source({ id: 'MISC', request_no: 'SP-MISC', kind: 'WORKSHOP_MISC', current_version_id: 'MISC-V7', supplier_confirmation: { ...source().supplier_confirmation!, version_id: 'MISC-V7' } })])
    changesApi.respond.mockResolvedValueOnce({}).mockRejectedValueOnce(new Error('网络结果未确认')).mockResolvedValueOnce({})
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('[aria-label="全选当前筛选订单"]').setValue(true)
    await button(wrapper, '批量确认接单').trigger('click'); await flushPromises()
    await wrapper.get('[aria-label="批量接单 SP-MISC 整单承诺交期"]').setValue('2026-10-29')
    await button(wrapper, '确认所选订单接单').trigger('click'); await flushPromises()
    expect(api.acceptBatch).toHaveBeenCalledTimes(1)
    expect(changesApi.respond).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('已完成 华兴')
    expect(wrapper.text()).toContain('SP-ACCEPT')
    expect(wrapper.text()).toContain('已选 1 张订单')
    expect(wrapper.get<HTMLInputElement>('[aria-label="批量接单 SP-MISC 整单承诺交期"]').element.value).toBe('2026-10-29')
    expect(wrapper.get('[aria-label="批量接单 SP-MISC 整单承诺交期"]').attributes('disabled')).toBeDefined()
    const original = changesApi.respond.mock.calls[1]![0]
    await button(wrapper, '确认所选订单接单').trigger('click'); await flushPromises()
    expect(changesApi.respond.mock.calls[2]![0]).toEqual(original)
    expect(api.acceptBatch).toHaveBeenCalledTimes(1)
    expect(changesApi.respond.mock.calls.filter(call => call[0].source_id === 'SPECIAL-V7')).toHaveLength(1)
    expect(wrapper.text()).toContain('已选 0 张订单')
    wrapper.unmount()
  })
  it('retains special selection, date and retry body after a failed refresh and blocks writes until the source is read again', async () => {
    const row = source(); supply([row])
    changesApi.respond.mockRejectedValueOnce(new Error('网络结果未确认')).mockResolvedValueOnce({})
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('[aria-label="供应商订单类型筛选"]').setValue('SAMPLE')
    await wrapper.get('[aria-label="全选当前筛选订单"]').setValue(true)
    await button(wrapper, '批量确认接单').trigger('click'); await flushPromises()
    await wrapper.get('[aria-label="批量接单 SP-ACCEPT 整单承诺交期"]').setValue('2026-10-29')
    specialApi.list.mockRejectedValueOnce(new Error('后续读取失败'))
    await button(wrapper, '确认所选订单接单').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('后续读取失败')
    expect(wrapper.text()).toContain('已选 1 张订单')
    expect(wrapper.get<HTMLInputElement>('[aria-label="批量接单 SP-ACCEPT 整单承诺交期"]').element.value).toBe('2026-10-29')
    const frozen = changesApi.respond.mock.calls[0]![0]
    await button(wrapper, '确认所选订单接单').trigger('click'); await flushPromises()
    expect(changesApi.respond).toHaveBeenCalledTimes(1)
    await button(wrapper, '刷新').trigger('click'); await flushPromises()
    await button(wrapper, '确认所选订单接单').trigger('click'); await flushPromises()
    expect(changesApi.respond.mock.calls[1]![0]).toEqual(frozen)
    wrapper.unmount()
  })
  it('invalidates an open special draft after a new requirement and clears private drafts on identity change', async () => {
    const row = source(); supply([row])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('[aria-label="确认订单 SP-ACCEPT 接单"]').trigger('click'); await flushPromises()
    await wrapper.get('[aria-label="SP-ACCEPT 整单承诺交期"]').setValue('2026-10-29')
    row.current_version_id = 'SPECIAL-V8'; row.revision = 8
    await button(wrapper, '刷新').trigger('click'); await flushPromises()
    expect(wrapper.find('[aria-label="SP-ACCEPT 整单承诺交期"]').exists()).toBe(false)
    await wrapper.get('[aria-label="确认订单 SP-ACCEPT 接单"]').trigger('click'); await flushPromises()
    expect(wrapper.get<HTMLInputElement>('[aria-label="SP-ACCEPT 整单承诺交期"]').element.value).toBe('2026-10-25')
    await wrapper.get('[aria-label="SP-ACCEPT 整单承诺交期"]').setValue('2026-10-30')
    authState.currentUser = { id: 'other-supplier', display_name: '其他人' }; await flushPromises()
    expect(wrapper.find('[aria-label="SP-ACCEPT 整单承诺交期"]').exists()).toBe(false)
    expect(changesApi.respond).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('retains an unknown request across same-version revision advance, then releases it only after the exact revision rejection', async () => {
    const row = source(); supply([row])
    changesApi.respond.mockRejectedValueOnce(new Error('网络结果未确认')).mockRejectedValueOnce({ isAxiosError: true, response: { status: 409, data: { detail: '订单修订已变化，请刷新后重新核对' } } }).mockResolvedValueOnce({})
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('[aria-label="确认订单 SP-ACCEPT 接单"]').trigger('click'); await flushPromises()
    await wrapper.get('[aria-label="SP-ACCEPT 整单承诺交期"]').setValue('2026-10-29')
    await wrapper.get('[role="dialog"]').findAll('button').find(row => row.text() === '确认接单')!.trigger('click'); await flushPromises()
    const frozen = changesApi.respond.mock.calls[0]![0]
    row.revision = 8
    await button(wrapper, '刷新').trigger('click'); await flushPromises()
    await wrapper.get('[aria-label="确认订单 SP-ACCEPT 接单"]').trigger('click'); await flushPromises()
    expect(wrapper.get('[aria-label="SP-ACCEPT 整单承诺交期"]').attributes('disabled')).toBeDefined()
    await button(wrapper, '重试原接单提交').trigger('click'); await flushPromises()
    expect(changesApi.respond.mock.calls[1]![0]).toEqual(frozen)
    expect(wrapper.get('[aria-label="SP-ACCEPT 整单承诺交期"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[role="dialog"]').text()).toContain('原提交未记录成功回执')
    await wrapper.get('[role="dialog"]').findAll('button').find(row => row.text() === '确认接单')!.trigger('click'); await flushPromises()
    expect(changesApi.respond.mock.calls[2]![0]).toMatchObject({ source_id: 'SPECIAL-V7', expected_revision: 8, promised_date: '2026-10-29' })
    expect(changesApi.respond.mock.calls[2]![0].request_id).not.toBe(frozen.request_id)
    wrapper.unmount()
  })
  it('requires explicit history reconciliation before replacing an unknown command with a new requirement version', async () => {
    const row = source(); supply([row])
    changesApi.respond.mockRejectedValueOnce(new Error('网络结果未确认')).mockResolvedValueOnce({})
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('[aria-label="确认订单 SP-ACCEPT 接单"]').trigger('click'); await flushPromises()
    await wrapper.get('[role="dialog"]').findAll('button').find(row => row.text() === '确认接单')!.trigger('click'); await flushPromises()
    const previous = changesApi.respond.mock.calls[0]![0]
    row.current_version_id = 'SPECIAL-V8'; row.revision = 8
    await button(wrapper, '刷新').trigger('click'); await flushPromises()
    await wrapper.get('[aria-label="确认订单 SP-ACCEPT 接单"]').trigger('click'); await flushPromises()
    expect(wrapper.get('[role="dialog"]').text()).toContain('采购版本已替换')
    expect(button(wrapper, '重试原接单提交').attributes('disabled')).toBeDefined()
    expect(changesApi.respond).toHaveBeenCalledTimes(1)
    await button(wrapper, '已核对历史回执，处理当前版本').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('旧版本不视为已同意')
    await wrapper.get('[role="dialog"]').findAll('button').find(row => row.text() === '确认接单')!.trigger('click'); await flushPromises()
    expect(changesApi.respond.mock.calls[1]![0]).toMatchObject({ source_id: 'SPECIAL-V8', expected_revision: 8 })
    expect(changesApi.respond.mock.calls[1]![0].request_id).not.toBe(previous.request_id)
    wrapper.unmount()
  })
  it('keeps the special acceptance dialog keyboard-dismissible and restores its row trigger', async () => {
    supply([source()])
    const wrapper = mount(CartonSupplierView, { ...options, attachTo: document.body }); await flushPromises()
    const trigger = wrapper.get<HTMLButtonElement>('[aria-label="确认订单 SP-ACCEPT 接单"]')
    trigger.element.focus(); await trigger.trigger('click'); await flushPromises()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); await flushPromises()
    expect(wrapper.find('[aria-label="SP-ACCEPT 整单承诺交期"]').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
    wrapper.unmount()
  })
})

describe('supplier receipt pricing entry', () => {
  function priceRow(id = 'PRICE-1', factory = 'huaxing', patch: Partial<CartonPriceReview> = {}): CartonPriceReview {
    return { id, factory_id: factory, receipt_line_id: `RL-${id}`, shipment_id: 'SHIP-A', shipment_line_id: 'SL-0', source_kind: 'REGULAR', status: 'PROPOSED', revision: 2,
      original_unit_price: null, proposed_unit_price: '3', effective_unit_price: null, original_free_confirmed: false, currency: 'CNY', document_no: id,
      item_no: 'ITEM-A', packaging_type: '外箱', specification: '10*20', unit: '个', quantity: '6', receipt_status: 'POSTED', reason: '收料待核价', locked: false, actionable: true, history: [], ...patch }
  }
  const priceCategory = (wrapper: ReturnType<typeof mount>) => wrapper.get('[aria-label="供应商协同分类"]').findAll('button').find(button => button.text().startsWith('收料核价'))!
  async function tab(wrapper: ReturnType<typeof mount>, label: string) { await wrapper.get('nav[aria-label="供应商协同功能"]').findAll('button').find(button => button.text().includes(label))!.trigger('click'); await flushPromises() }
  it('places a single retained price editor above both order and shipment-feedback content', async () => {
    priceApi.list.mockResolvedValue([priceRow()])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    const workbench = wrapper.get('[aria-label="供应商协同工作台"]'), editor = wrapper.getComponent(CartonPriceReviews).element
    expect(priceCategory(wrapper).text()).toContain('华兴 · 缺价/异议 1 项')
    expect(priceCategory(wrapper).attributes('aria-expanded')).toBe('false')
    expect(wrapper.get('#supplier-collaboration-content').attributes('style')).toContain('display: none')
    expect(wrapper.findAllComponents(CartonPriceReviews)).toHaveLength(1)
    expect(workbench.element.contains(editor)).toBe(true)
    await priceCategory(wrapper).trigger('click')
    await wrapper.get('[aria-label="PRICE-1 核价原因"]').setValue('请按本批实物核对')
    await priceCategory(wrapper).trigger('click')
    await tab(wrapper, '发货与仓库反馈')
    expect(workbench.attributes('style') || '').not.toContain('display: none')
    expect(priceCategory(wrapper).attributes('aria-expanded')).toBe('false')
    expect(wrapper.findAllComponents(CartonPriceReviews)).toHaveLength(1)
    expect(wrapper.getComponent(CartonPriceReviews).element).toBe(editor)
    const feedback = wrapper.findAll('section').find(section => section.find('h2').exists() && section.find('h2').text() === '发货与仓库反馈')!
    expect(workbench.element.compareDocumentPosition(feedback.element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    await priceCategory(wrapper).trigger('click')
    expect(wrapper.get<HTMLInputElement>('[aria-label="PRICE-1 核价原因"]').element.value).toBe('请按本批实物核对')
    await tab(wrapper, '订单管理')
    expect(wrapper.getComponent(CartonPriceReviews).element).toBe(editor)
    expect(priceApi.list).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
  it('retains failed-write details and the same retry identity across disclosure and page switches', async () => {
    priceApi.list.mockResolvedValue([priceRow()]); priceApi.decide.mockRejectedValueOnce(new Error('网络中断，结果待核实')).mockResolvedValueOnce({})
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await priceCategory(wrapper).trigger('click')
    await wrapper.get('[aria-label="PRICE-1 核价原因"]').setValue('已核实本批单价')
    await wrapper.getComponent(CartonPriceReviews).findAll('button').find(button => button.text() === '确认本批价格')!.trigger('click'); await flushPromises()
    const original = priceApi.decide.mock.calls[0]![1]
    await priceCategory(wrapper).trigger('click')
    expect(priceCategory(wrapper).text()).toContain('华兴 · 处理待核对')
    expect(wrapper.get('[aria-label="供应商协同工作台"]').text()).toContain('网络中断，结果待核实')
    await tab(wrapper, '发货与仓库反馈'); await priceCategory(wrapper).trigger('click')
    expect(wrapper.get<HTMLInputElement>('[aria-label="PRICE-1 核价原因"]').element.value).toBe('已核实本批单价')
    expect(wrapper.getComponent(CartonPriceReviews).get('[role="alert"]').text()).toContain('网络中断')
    await wrapper.getComponent(CartonPriceReviews).findAll('button').find(button => button.text() === '确认本批价格')!.trigger('click'); await flushPromises()
    expect(priceApi.decide.mock.calls[1]![1]).toEqual(original)
    wrapper.unmount()
  })
  it('names the selected factory and treats reading and failures as distinct from its zero count', async () => {
    api.memberships.mockResolvedValue([{ factory_id: 'huaxing' }, { factory_id: 'huadeng' }])
    let reject!: (reason: Error) => void
    priceApi.list.mockResolvedValueOnce([priceRow()]).mockImplementationOnce(() => new Promise((_done, fail) => { reject = fail })).mockResolvedValueOnce([])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(priceCategory(wrapper).text()).toContain('华兴 · 缺价/异议 1 项')
    await priceCategory(wrapper).trigger('click')
    await wrapper.get('[aria-label="供应商核价厂区"]').setValue('huadeng'); await flushPromises()
    expect(priceCategory(wrapper).text()).toContain('华登 · 读取中')
    expect(priceCategory(wrapper).text()).not.toContain('0 项')
    reject(new Error('该厂区核价读取失败')); await flushPromises()
    expect(priceCategory(wrapper).text()).toContain('华登 · 读取失败')
    expect(priceCategory(wrapper).text()).not.toContain('0 项')
    await wrapper.getComponent(CartonPriceReviews).findAll('button').find(button => button.text() === '刷新核价')!.trigger('click'); await flushPromises()
    expect(priceCategory(wrapper).text()).toContain('华登 · 缺价/异议 0 项')
    expect(priceCategory(wrapper).text()).not.toContain('全部厂区')
    wrapper.unmount()
  })
  it('clears drafts and errors on an actual factory or viewer change and retains supplier approval boundaries', async () => {
    api.memberships.mockResolvedValue([{ factory_id: 'huaxing' }, { factory_id: 'huadeng' }])
    priceApi.list.mockImplementation(async factory => [priceRow('PRICE-1', factory)])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await priceCategory(wrapper).trigger('click')
    await wrapper.get('[aria-label="PRICE-1 核价原因"]').setValue('第一厂区草稿')
    await wrapper.get('[aria-label="供应商核价厂区"]').setValue('huadeng'); await flushPromises()
    expect(wrapper.get<HTMLInputElement>('[aria-label="PRICE-1 核价原因"]').element.value).toBe('')
    await wrapper.get('[aria-label="PRICE-1 核价原因"]').setValue('第二厂区草稿')
    authState.currentUser = { id: 'other-supplier', display_name: '其他供应商' }; await flushPromises()
    expect(wrapper.find('[aria-label="PRICE-1 核价原因"]').exists()).toBe(false)
    can.mockImplementation(permission => !permission.endsWith(':approve'))
    await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click'); await flushPromises()
    await priceCategory(wrapper).trigger('click')
    expect(wrapper.getComponent(CartonPriceReviews).text()).toContain('供应商原单价')
    expect(wrapper.getComponent(CartonPriceReviews).findAll('button').some(button => ['确认本批价格', '退回核实'].includes(button.text()))).toBe(false)
    expect(priceApi.decide).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('keeps known-price corrections separate and opens the original receipt batch from a full-correction link', async () => {
    priceApi.list.mockResolvedValue([priceRow('KNOWN', 'huaxing', { need_full_correction: true, can_propose: false })])
    const wrapper = mount(CartonSupplierView, { global: { stubs: { ...options.global.stubs, CartonPriceCorrectionDialog: true } } }); await flushPromises()
    await priceCategory(wrapper).trigger('click')
    const panel = wrapper.get('[aria-label="供应商价格核对厂区"]')
    expect(panel.text()).toContain('缺价与异议核对')
    expect(panel.findAll('button').some(button => button.text() === '收料单价更正 / 待办')).toBe(true)
    await panel.findAll('button').find(button => button.text() === '前往完整单价更正')!.trigger('click'); await flushPromises()
    expect(wrapper.getComponent({ name: 'CartonPriceCorrectionDialog' }).props()).toMatchObject({ factoryId: 'huaxing', receiptLineId: 'RL-KNOWN', internal: false })
    expect(priceApi.decide).not.toHaveBeenCalled(); expect(priceApi.propose).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

describe('supplier cancellation and correction handoffs', () => {
  it('allows a current accepted paper promise to be updated without resetting the planned date', async () => {
    api.accept.mockResolvedValue(fixture().orders[0])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('[aria-label="更新订单 ORDER-A 承诺交期"]').trigger('click')
    await wrapper.get('[aria-label="ORDER-A/01 承诺交期"]').setValue('2026-09-28')
    await wrapper.get('[role="dialog"]').findAll('button').find(button => button.text() === '保存承诺交期')!.trigger('click')
    await flushPromises()
    expect(api.accept).toHaveBeenCalledWith(expect.objectContaining({ id: 'LINE-0', commitment_revision: 1 }), expect.objectContaining({ issue_id: 'ISSUE-A', planned_date: '2026-09-25' }), 'huaxing', '2026-09-28')
    wrapper.unmount()
  })

  it('shows pending cancellation above the ledger and confirms the exact issue', async () => {
    const data = fixture(); data.orders[0]!.status = 'CANCELLED'
    data.orders[0]!.cancellation_notice = { issue_id: 'CANCEL-R', order_revision: 3, issued: true, acknowledged: false, acknowledged_at: '' }
    api.workspace.mockResolvedValue(data); api.acknowledgeCancellation.mockResolvedValue(data.orders[0])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    const banner = wrapper.get('[aria-label="待确认取消通知"]')
    expect(banner.text()).toContain('SC-A')
    await banner.find('button').trigger('click'); await flushPromises()
    expect(api.acknowledgeCancellation).toHaveBeenCalledWith(expect.objectContaining({ id: 'ORDER-A', cancellation_notice: expect.objectContaining({ issue_id: 'CANCEL-R', order_revision: 3 }) }), 'huaxing')
    expect(wrapper.find('[aria-label="更新订单 ORDER-A 承诺交期"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('omits the redundant top acceptance shortcuts', async () => {
    const wrapper = mount(CartonSupplierReceiving, { ...options, props: { factoryId: 'huaxing', shipmentId: 'SHIP-A' } }); await flushPromises()
    const labels = wrapper.get('[role="dialog"]').findAll('button').map(button => button.text())
    for (const text of ['本次未到', '暂未到货，继续待收', '整单拒收退回']) expect(labels).not.toContain(text)
    expect(api.receive).not.toHaveBeenCalled(); wrapper.unmount()
  })

  it('provides a reasoned reopen action for a mistaken final non-arrival', async () => {
    const data = fixture(); data.shipments[0]!.status = 'NOT_RECEIVED'; data.shipments[0]!.revision = 2
    api.workspace.mockResolvedValue(data); api.changeNonArrival.mockResolvedValue({ ...data.shipments[0], status: 'SENT', revision: 3 })
    const wrapper = mount(CartonSupplierReceiving, { ...options, props: { factoryId: 'huaxing' } }); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '已核实记录')!.trigger('click')
    await wrapper.findAll('button').find(button => button.text() === '更正未到货，重新待收')!.trigger('click')
    const dialog = wrapper.get('[aria-label="更正未到货反馈"]')
    await dialog.get('textarea').setValue('原未到货反馈有误')
    await dialog.trigger('submit'); await flushPromises()
    expect(api.changeNonArrival).toHaveBeenCalledWith('SHIP-A', 'reopen', { factory_id: 'huaxing', expected_revision: 2, reason: '原未到货反馈有误' })
    expect(api.receive).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})


it('requires explicit ambiguous order selection and a fresh preview before dispatch', async () => {
  const candidate = { order_line_id: 'LINE-0', issue_id: 'ISSUE-A', order_revision: 4, order_no: 'ORDER-A', customer_po: 'PO-A', document_no: 'P00', planned_date: '2026-09-25', status: 'PENDING_SUPPLIER', required_quantity: '100', remaining_to_ship: '100', child_no: 'ORDER-A/01', unit: '个' }
  const row = { source_sheet: '送货明细', source_row: 2, contract_no: 'SC-A', item_no: 'ITEM-A', packaging_type: '外箱', paper_quality: 'A33', specification: '10*20', delivered_quantity: 5, order_no: '', child_no: '', order_line_id: '', issue_id: '', order_revision: 0, status: 'BLOCKED', reason: '匹配到多张订单', candidates: [candidate, { ...candidate, order_line_id: 'LINE-B', order_no: 'ORDER-B', customer_po: 'PO-B' }] }
  const blocked = { filename: '送货.xlsx', sha256: 'abc', row_count: 1, groups: [{ factory_id: 'huaxing', destination: '华兴', delivery_note_no: 'DN-CHOOSE', delivery_date: '2026-09-24', ready: false, issues: [], rows: [row] }] }
  const ready = { ...blocked, groups: [{ ...blocked.groups[0], ready: true, rows: [{ ...row, status: 'READY', order_line_id: 'LINE-0', issue_id: 'ISSUE-A', order_revision: 4, order_no: 'ORDER-A', child_no: 'ORDER-A/01' }] }] }
  api.previewDeliveryImport.mockResolvedValueOnce(blocked).mockResolvedValueOnce(ready)
  const wrapper = mount(CartonSupplierView, options); await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === '导入送货单')!.trigger('click')
  const file = new File(['excel'], '送货.xlsx'); const input = wrapper.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: [file] }); await input.trigger('change'); await flushPromises()
  await wrapper.get('[aria-label="送货明细 第2行对应订单"]').setValue('LINE-0|ISSUE-A')
  expect(wrapper.text()).toContain('订单选择已改变')
  await wrapper.findAll('button').find(button => button.text() === '重新校验订单选择')!.trigger('click'); await flushPromises()
  const choices = [{ source_sheet: '送货明细', source_row: 2, order_line_id: 'LINE-0', issue_id: 'ISSUE-A', order_revision: 4 }]
  expect(api.previewDeliveryImport).toHaveBeenLastCalledWith(file, choices)
  await wrapper.findAll('button').find(button => button.text() === '确认 1 张送货单发货')!.trigger('click'); await flushPromises()
  expect(api.confirmDeliveryImport).toHaveBeenCalledWith(file, ready, [{ factory_id: 'huaxing', delivery_note_no: 'DN-CHOOSE' }], choices)
  wrapper.unmount()
})

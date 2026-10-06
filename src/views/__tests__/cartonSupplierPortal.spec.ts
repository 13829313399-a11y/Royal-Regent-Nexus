import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Blob as NodeBlob } from 'node:buffer'
import CartonSupplierView from '../CartonSupplierView.vue'
import CartonSupplierReceiving from '@/components/CartonSupplierReceiving.vue'
import CartonSupplierMarkTemplatesView from '../CartonSupplierMarkTemplatesView.vue'
import CartonReceiptAllocations from '@/components/CartonReceiptAllocations.vue'
import CartonActionNotice from '@/components/CartonActionNotice.vue'
import type { PortalWorkspace } from '@/api/cartonSupplierPortal'
const api = vi.hoisted(() => ({ memberships: vi.fn(), workspace: vi.fn(), accept: vi.fn(), acceptBatch: vi.fn(), ship: vi.fn(), previewDeliveryImport: vi.fn(), confirmDeliveryImport: vi.fn(), receiptOptions: vi.fn(), linkReceipt: vi.fn(), receive: vi.fn(), linkSampleReceipt: vi.fn(), linkShipmentLine: vi.fn(), members: vi.fn(), member: vi.fn(), upload: vi.fn(), download: vi.fn(), markAssets: vi.fn(), downloadMarkAsset: vi.fn(), previewMarkAssetUrl: vi.fn(), markTemplates: vi.fn(), downloadMarkDocument: vi.fn(), previewMarkPdfUrl: vi.fn(), documents: vi.fn(), activity: vi.fn(), activityPage: vi.fn(), exportDocuments: vi.fn(), exportOrderImport: vi.fn() }))
const router = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn() }))
const routeState = vi.hoisted(() => ({ query: { factory: 'huaxing', shipment: undefined as string | undefined } }))
const can = vi.hoisted(() => vi.fn((_permission: string) => true))
vi.mock('@/api/cartonSupplierPortal', () => ({ cartonSupplierPortalApi: api }))
vi.mock('@/api/cartonPositions', () => ({ cartonPositionsApi: { locations: vi.fn(async () => [{ id: 'BIN-A', factory_id: 'huaxing', warehouse: 'A', bin_code: '01', label: 'A / 01', status: 'ACTIVE' }]) } }))
vi.mock('@/api/cartonProcurement', () => ({ cartonProcurementApi: { listCustomers: vi.fn(async () => [{ customer_code: 'DICKIE', customer_name: 'Dickie', status: 'ACTIVE' }]) } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ can }) }))
vi.mock('@/stores/app', () => ({ useAppStore: () => ({ activeProductionFactory: { id: 'huaxing' } }) }))
vi.mock('vue-router', () => ({ useRoute: () => routeState, useRouter: () => router, RouterLink: { name: 'RouterLink', props: ['to'], template: '<a><slot /></a>' } }))
function fixture(): PortalWorkspace {
  return { factory_id: 'huaxing', supplier_name: '河源东康', orders: [{ id: 'ORDER-A', order_no: 'ORDER-A', customer_name: 'Dickie', contract_no: 'SC-A', customer_po: 'PO-A', item_no: 'ITEM-A', product_name: '产品', status: 'PENDING_SUPPLIER', issue_id: 'ISSUE-A', document_no: 'ORDER-A-P00', order_date: '2026-09-10', planned_date: '2026-09-25', awaiting_issue: false, attachments: [], lines: ['外箱', '平卡'].map((name, index) => ({ id: `LINE-${index}`, line_no: index+1, child_no: `ORDER-A/0${index+1}`, packaging_type: name, paper_quality: 'A33', specification: '10*20', dimension_unit: 'cm', unit: index ? '张' : '个', required_quantity: '100', received_quantity: '0', in_transit_quantity: '0', remaining_to_ship: '100', accepted: true, commitment_revision: 1, promised_date: '2026-09-25' })) }], shipments: [{ id: 'SHIP-A', delivery_note_no: 'DN-A', delivery_date: '2026-09-21', status: 'SENT', revision: 1, created_at: '', confirmed_at: '', acceptance_date: null, acceptance_lines: [], lines: [0,1].map(index => ({ id: `SL-${index}`, order_line_id: `LINE-${index}`, order_no: 'ORDER-A', contract_no: 'SC-A', customer_po: 'PO-A', item_no: 'ITEM-A', customer_name: 'Dickie', child_no: `ORDER-A/0${index+1}`, packaging_type: index ? '平卡' : '外箱', paper_quality: 'A33', specification: '10*20', unit: '个', quantity: '10', unit_price: '2', currency: 'CNY' })) }] }
}
const options = { global: { stubs: { AccountMenu: true, NotificationCenter: true, RouterLink: { template: '<a><slot /></a>' }, CartonReceiptAllocations: true } } }
const guideOptions = { global: { stubs: { ...options.global.stubs,
  CartonSupplierMonthlyReview: true,
  CartonUsageGuide: { name: 'CartonUsageGuide', props: ['audience', 'factoryName'], emits: ['close', 'supplierNavigate'], template: '<section data-testid="supplier-usage-guide" />' },
} } }
beforeEach(() => { routeState.query.shipment = undefined; vi.resetAllMocks(); can.mockReturnValue(true); api.memberships.mockResolvedValue([{ factory_id: 'huaxing', supplier_name: '河源东康' }]); api.workspace.mockResolvedValue(fixture()); api.members.mockResolvedValue([]); api.ship.mockResolvedValue({ id: 'NEW' }); api.previewDeliveryImport.mockResolvedValue({ filename: '送货明细表.xlsx', sha256: 'abc', row_count: 1, groups: [{ factory_id: 'huaxing', destination: '华兴', delivery_note_no: 'DN-NEW', delivery_date: '2026-09-24', ready: true, issues: [], rows: [{ source_sheet: '送货明细', source_row: 2, contract_no: 'SC-A', item_no: 'ITEM-A', packaging_type: '外箱', paper_quality: 'A33', specification: '10*20', delivered_quantity: 4, order_no: 'ORDER-A', child_no: 'ORDER-A/01', order_line_id: 'LINE-0', issue_id: 'ISSUE-A', status: 'READY', reason: '已匹配' }] }] }); api.confirmDeliveryImport.mockResolvedValue({ shipments: [{ id: 'NEW' }] }); api.acceptBatch.mockResolvedValue({ order_ids: [] }); api.documents.mockResolvedValue([]); api.activityPage.mockResolvedValue({ items: [{ id: 'ACT1', factory_id: 'huaxing', action: '送货单已登记', created_at: '2026-09-25', reference_no: 'DN-1', actor_name: '供应商' }], total: 1, limit: 50, offset: 0 }); api.activity.mockResolvedValue([]); api.exportDocuments.mockResolvedValue(undefined); api.exportOrderImport.mockResolvedValue(undefined); api.receiptOptions.mockResolvedValue([]); api.linkReceipt.mockResolvedValue({ id: 'SHIP-A' }); api.receive.mockResolvedValue({ id: 'SHIP-A' }); api.linkSampleReceipt.mockResolvedValue({ receipt_line_id: 'RL-SAMPLE', order_line_id: 'LINE-0', order_no: 'ORDER-A', quantity: '4' }); api.markAssets.mockResolvedValue([]); api.previewMarkAssetUrl.mockReturnValue('/api/preview.pdf'); api.markTemplates.mockResolvedValue([]); api.previewMarkPdfUrl.mockReturnValue('/api/preview.pdf') })

describe('late supplier documents use existing warehouse receipts', () => {
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
    await wrapper.get('input[aria-label="搜索供应商订单"]').setValue('ITEM-A')
    await wrapper.get('button[aria-label="打开供应商协同使用教程"]').trigger('click'); await flushPromises()
    const guide = wrapper.findComponent('[data-testid="supplier-usage-guide"]')
    expect(guide.props()).toMatchObject({ audience: 'supplier', factoryName: '河源东康' })
    guide.vm.$emit('close'); await flushPromises()
    expect(wrapper.find('[data-testid="supplier-usage-guide"]').exists()).toBe(false)
    expect(wrapper.get<HTMLInputElement>('input[aria-label="搜索供应商订单"]').element.value).toBe('ITEM-A')
    for (const action of [api.accept, api.acceptBatch, api.confirmDeliveryImport, api.ship, api.receive]) expect(action).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('navigates to supplier documents and carton marks through existing read-only entries', async () => {
    const wrapper = mount(CartonSupplierView, guideOptions); await flushPromises()
    await wrapper.get('button[aria-label="打开供应商协同使用教程"]').trigger('click'); await flushPromises()
    wrapper.findComponent('[data-testid="supplier-usage-guide"]').vm.$emit('supplierNavigate', 'supplier-documents'); await flushPromises()
    expect(wrapper.get('input[aria-label="搜索供应商单据"]').exists()).toBe(true)
    expect(api.documents).toHaveBeenCalledWith('huaxing')
    await wrapper.get('button[aria-label="打开供应商协同使用教程"]').trigger('click'); await flushPromises()
    wrapper.findComponent('[data-testid="supplier-usage-guide"]').vm.$emit('supplierNavigate', 'supplier-carton-mark'); await flushPromises()
    expect(router.push).toHaveBeenCalledWith('/carton-supplier/carton-mark')
    expect(api.confirmDeliveryImport).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps the guide available for a supplier who can only read', async () => {
    can.mockImplementation(permission => permission === 'carton_supplier:read')
    const wrapper = mount(CartonSupplierView, guideOptions); await flushPromises()
    await wrapper.get('button[aria-label="打开供应商协同使用教程"]').trigger('click'); await flushPromises()
    wrapper.findComponent('[data-testid="supplier-usage-guide"]').vm.$emit('supplierNavigate', 'supplier-settlements'); await flushPromises()
    expect(wrapper.findComponent({ name: 'CartonSupplierMonthlyReview' }).exists()).toBe(true)
    expect(api.acceptBatch).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

describe('supplier carton mark templates', () => {
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
    expect(wrapper.get('[role=alert]').text()).toContain('暂无可查看的已下单厂区')
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
    expect(wrapper.get('[role="alert"]').text()).toContain('没有此供应商可查看')
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
    expect(wrapper.text()).toContain('Dickie · ITEM-A')
    expect(wrapper.text()).toContain('箱唛资料库')
    expect(wrapper.get('a[aria-label="预览 print.pdf"]').attributes('href')).toBe('/api/preview.pdf')
    await wrapper.get('button[aria-label="下载 print.pdf"]').trigger('click'); await flushPromises()
    expect(api.downloadMarkAsset).toHaveBeenCalledWith('mark-1', 'huaxing', expect.any(AbortSignal))
    expect(wrapper.get('[role="alert"]').text()).toContain('下载失败')
    expect(wrapper.find('input[type="file"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('does not request templates when the account has no supplier membership', async () => {
    api.memberships.mockResolvedValue([])
    const wrapper = mount(CartonSupplierMarkTemplatesView, options); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('暂无可查看的已下单厂区')
    expect(api.markAssets).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

describe('supplier batches and document desk', () => {
  it.each([false, true])('shows a confirmed batch and makes direct-export failure visible=%s', async (exportFails) => {
    const merged = {
      id: 'CPB-TEST', kind: 'PURCHASE' as const, factory_id: 'huaxing',
      document_no: 'CG-260929-BATCH', document_type: 'INITIAL', date: '2026-09-29',
      created_at: '2026-09-29T08:00:00+08:00', status: '已发行', replenishment: false,
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
    await wrapper.get('input[aria-label="搜索供应商单据"]').setValue('ORDER-B-P00')
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
    expect(wrapper.get('input[aria-label="选择订单 ORDER-A"]').exists()).toBe(true)
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
      { id: 'I-1', kind: 'PURCHASE', factory_id: 'huaxing', document_no: 'PO-1', document_type: 'INITIAL', date: '2026-09-21', created_at: '2026-09-21T10:00:00', status: '已发行', replenishment: false, export_count: 0,
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
    expect(mergedPreview.text()).toContain('发货 10 · 实收 0')
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
      document_type: 'INITIAL', date: '2026-09-24', created_at: '2026-09-24T10:00:00', status: '已发行',
      replenishment: false, export_count: 0, orders: [], lines: [] }
    const delivery = { ...purchase, id: 'SHIP-1', kind: 'DELIVERY', document_no: 'DN-1' }
    api.documents.mockResolvedValue([purchase, delivery])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text().includes('采购单与送货单'))!.trigger('click'); await flushPromises()
    await wrapper.get('input[aria-label="全选当前筛选单据"]').setValue(true)
    await wrapper.findAll('button').find(button => button.text().includes('导出东康导入模板'))!.trigger('click')
    await flushPromises()
    expect(api.exportOrderImport).toHaveBeenCalledWith([purchase])
    expect(api.exportDocuments).not.toHaveBeenCalled()
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
      created_at: '2026-09-24T10:00:00', status: '已发行', replenishment: false,
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
      status: '已发行', replenishment: false, orders: [], lines: [],
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
      ['RECEIPT_PENDING', 'ORDER-TRANSIT', '送货待确定'],
      ['COMPLETED', 'ORDER-COMPLETE', '已完成'],
      ['CANCELLED', 'ORDER-CANCEL', '已取消'],
      ['PENDING_ISSUE', 'ORDER-UNISSUED', '变更待发行'],
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
    expect(wrapper.get('[role="dialog"]').text()).toContain('A33 · 10*20 cm')
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

    await wrapper.get('input[aria-label="搜索供应商订单"]').setValue('SC-A')
    expect(ledgerRows()).toHaveLength(1)
    await wrapper.get('input[aria-label="全选当前筛选订单"]').setValue(true)
    await wrapper.get('input[aria-label="搜索供应商订单"]').setValue('SC-B')
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
    await wrapper.get('input[aria-label="送货单关键字"]').setValue('UNMATCHED')
    expect(wrapper.text()).toContain('暂无符合条件的发货单')
    expect(wrapper.text()).not.toContain('DN-A')
    wrapper.unmount()
  })
  it('shows an unbound account message without requesting an arbitrary factory workspace', async () => {
    api.memberships.mockResolvedValue([])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('暂无可查看的已下单厂区')
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
    expect(wrapper.text()).toContain('新发货由仓库验收，后补凭证由仓库关联原入库')
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
      await wrapper.findAll('button').find(button => button.text() === '整单未到')!.trigger('click')
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
    expect(wrapper.get('[aria-label="供应商收货工作区"]').exists()).toBe(true)
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
    await wrapper.findAll('button').find(button => button.text() === '整单未到')!.trigger('click')
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
    expect(wrapper.get('button[aria-label="UNMATCHED 确认收货前关联"]').attributes('disabled')).toBeDefined()
    await wrapper.get('select[aria-label="UNMATCHED 关联客户"]').setValue('DICKIE')
    const target = wrapper.get('select[aria-label="UNMATCHED 收货前关联订单"]')
    expect(target.findAll('option').map(option => option.attributes('value'))).toEqual(['', 'LINE-0'])
    await target.setValue('LINE-0')
    await wrapper.get('input[aria-label="UNMATCHED 收货前关联原因"]').setValue('核对补建的正式订单')
    await wrapper.get('button[aria-label="UNMATCHED 确认收货前关联"]').trigger('click'); await flushPromises()
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
  it('requires an explicit warehouse decision before a no-order sample can be posted', async () => {
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
    expect(wrapper.get('[role="dialog"]').text()).toContain('必须选')
    await wrapper.get('select[aria-label="SL-SAMPLE 无单处理结论"]').setValue('SAMPLE')
    await wrapper.get('select[aria-label="SL-SAMPLE 样板箱客户"]').setValue('DICKIE')
    await wrapper.get('input[aria-label="SL-SAMPLE 样板箱用途"]').setValue('客户打板确认')
    await wrapper.get('input[aria-label="SL-SAMPLE 样板箱需求人"]').setValue('纸箱部')
    wrapper.findComponent(CartonReceiptAllocations).vm.$emit('update:modelValue', [{ location_id: 'BIN-A', quantity: 4 }])
    await wrapper.get('[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.receive).toHaveBeenCalledWith('SHIP-A', expect.objectContaining({ lines: [expect.objectContaining({
      no_order_decision: 'SAMPLE', customer_code: 'DICKIE', sample_purpose: '客户打板确认', requested_by: '纸箱部',
    })] }))
    wrapper.unmount()
  })
  it('prefills the warehouse price from the supplier delivery sheet and shows the purchase price difference', async () => {
    const data = fixture()
    data.shipments[0]!.lines[0]!.delivery_unit_price = '3.75'
    data.shipments[0]!.lines[1]!.delivery_unit_price = '4'
    data.shipments[0]!.lines[1]!.currency = 'HKD'
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierReceiving, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '核实实际收到')!.trigger('click')
    expect(wrapper.findAll<HTMLInputElement>('input[type="number"][step="0.000001"]')[0]!.element.value).toBe('3.75')
    expect(wrapper.findAll<HTMLInputElement>('input[type="number"][step="0.000001"]')[1]!.element.value).toBe('2')
    expect(wrapper.get('[role="dialog"]').text()).toContain('送货单 CNY 3.75 · 采购单 CNY 2')
    expect(wrapper.get('[role="dialog"]').text()).toContain('采购单为 HKD，已带采购单价')
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
    await wrapper.findAll('button').find(button => button.text() === '整单未到')!.trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('确认整单未收到并退回')
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

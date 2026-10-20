import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import CartonMarkAssetLibrary from '../CartonMarkAssetLibrary.vue'
import type { CartonMarkAsset, CartonMarkAssetUploadResult } from '@/api/cartonMark'

const api = vi.hoisted(() => ({ listAssets: vi.fn(), uploadAssets: vi.fn(), bindAsset: vi.fn(), downloadAsset: vi.fn(), archiveAsset: vi.fn(), bindingOrders: vi.fn(), savePhotoGroup: vi.fn(), ungroupPhotos: vi.fn(), classifyAsset: vi.fn(), assetClassificationHistory: vi.fn(), shareRecipients: vi.fn(), setAssetSharing: vi.fn(), bindingTargets: vi.fn(), proposeAssetBindings: vi.fn(), confirmAssetBinding: vi.fn(), bindSpecialAsset: vi.fn() }))
const supplierApi = vi.hoisted(() => ({ markAssets: vi.fn(), previewMarkAssetUrl: vi.fn(), downloadMarkAsset: vi.fn() }))
vi.mock('@/api/cartonMark', () => ({ cartonMarkApi: api }))
vi.mock('@/api/cartonSupplierPortal', () => ({ cartonSupplierPortalApi: supplierApi }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => authState }))
const authState = reactive({ currentUser: { id: 'warehouse-user', name: '仓管' }, authorizationVersion: 1, can: () => true })
const asset: CartonMarkAsset = {
  id: 'CMA-test', factory_id: 'huaxing', file_name: '4500222793.pdf', kind: 'pdf', size_bytes: 500,
  sha256: 'sha', contract_number: '4500222793', bound_order_id: null, recognition_source: 'filename',
  candidates: ['4500222793'], warning: '', binding_status: 'BOUND', revision: 1,
  orders: [{ id: 'order-a', order_no: 'CTR-a', contract_no: '4500222793', customer_name: 'ZURU', item_no: '100369' }],
  created_at: '2026-10-05', created_by_name: '仓管',
}
beforeEach(() => {
  vi.clearAllMocks()
  authState.currentUser = { id: 'warehouse-user', name: '仓管' }
  authState.authorizationVersion = 1
  api.shareRecipients.mockResolvedValue([{ id: 'supplier-a', name: '东康' }])
  api.bindingTargets.mockResolvedValue([])
  api.listAssets.mockResolvedValue([asset])
  api.bindingOrders.mockResolvedValue(asset.orders)
  api.assetClassificationHistory.mockResolvedValue([])
})

describe('carton-mark source repository', () => {
  it('requires an explicit shared supplier when there are several and supports internal-only upload', async () => {
    api.shareRecipients.mockResolvedValue([{ id: 'a', name: '供应商甲' }, { id: 'b', name: '供应商乙' }])
    api.uploadAssets.mockResolvedValue([])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', uploadOnly: true } }); await flushPromises()
    const file = new File(['pdf'], '未绑定.pdf'), input = wrapper.get('input[type=file]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] }); await input.trigger('change')
    const submit = () => wrapper.findAll('button').find(row => row.text().startsWith('上传入库'))!.trigger('click')
    await submit(); await flushPromises()
    expect(api.uploadAssets).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请选择共享给哪家供应商')
    await wrapper.get('[aria-label="上传资料共享范围"]').setValue('INTERNAL')
    await submit(); await flushPromises()
    expect(api.uploadAssets).toHaveBeenCalledWith('huaxing', [file], expect.any(AbortSignal), [{ status: 'DRAFT', note: '', sharing_mode: 'INTERNAL', supplier_id: undefined }])
    wrapper.unmount()
  })

  it('shows and downloads supplier shared files without pretending they have an order', async () => {
    supplierApi.markAssets.mockResolvedValue([{ ...asset, orders: [], binding_status: 'UNBOUND', sharing_mode: 'SUPPLIER', shared_supplier_name: '东康' }])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', supplier: true, readOnly: true } }); await flushPromises()
    const row = wrapper.get(`[data-asset-id="${asset.id}"]`)
    expect(row.text()).toContain('未关联订单')
    expect(row.text()).toContain('共享给 东康')
    expect(row.find('[aria-label^="下载"]').exists()).toBe(true)
    expect(row.text()).not.toContain('已关联采购订单')
    wrapper.unmount()
  })

  it('submits supplier order binding as a pending proposal and never confirms it', async () => {
    supplierApi.markAssets.mockResolvedValue([{ ...asset, orders: [], binding_status: 'UNBOUND' }])
    api.bindingTargets.mockResolvedValue([{ order_id: 'order-b', order_kind: 'REGULAR', order_no: 'CTR-b', contract_no: 'B', customer_name: 'ZURU', item_no: 'I', revision: 2, lines: [] }])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', supplier: true, readOnly: true } }); await flushPromises()
    await wrapper.findAll('button').find(row => row.text() === '绑定到订单')!.trigger('click'); await flushPromises()
    await wrapper.get('[aria-label="箱唛绑定订单"]').setValue('order-b')
    await wrapper.findAll('button').find(row => row.text() === '提交绑定，待我方确认')!.trigger('click'); await flushPromises()
    expect(api.proposeAssetBindings).toHaveBeenCalledWith('huaxing', expect.objectContaining({ id: asset.id, revision: 1 }), ['order-b'], expect.any(AbortSignal))
    expect(api.confirmAssetBinding).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('binds a sample to the selected paper and discards a late target list after factory change', async () => {
    const target = { order_id: 'sample-a', order_kind: 'SAMPLE', order_no: 'SP-a', contract_no: '', customer_name: '', item_no: 'I', revision: 3, lines: [{ id: 'line-a', label: '外箱 · I' }] }
    api.bindingTargets.mockResolvedValue([target])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing' } }); await flushPromises()
    await wrapper.findAll('button').find(row => row.text() === '绑定到订单')!.trigger('click'); await flushPromises()
    await wrapper.get('[aria-label="箱唛绑定订单"]').setValue('sample-a')
    await wrapper.findAll('button').find(row => row.text() === '绑定此订单')!.trigger('click'); await flushPromises()
    expect(api.bindSpecialAsset).toHaveBeenCalledWith('huaxing', target, 'line-a', asset, expect.any(String), false, expect.any(AbortSignal))
    let finish!: (rows: unknown[]) => void
    api.bindingTargets.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await wrapper.findAll('button').find(row => row.text() === '绑定到订单')!.trigger('click')
    await wrapper.setProps({ factoryId: 'huakang-a' }); await flushPromises()
    finish([target]); await flushPromises()
    expect(wrapper.find('[aria-label="选择使用箱唛的订单"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps sample links distinct from ordinary QC order identities and filters them', async () => {
    api.listAssets.mockResolvedValue([{ ...asset, orders: [], binding_status: 'UNBOUND', special_orders: [{ order_id: 's', order_no: 'SP-s', order_kind: 'SAMPLE', line_id: 'line', attachment_id: 'file', confirmed: false }] }])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing' } }); await flushPromises()
    await wrapper.get('[aria-label="箱唛关联订单类型"]').setValue('SAMPLE')
    expect(wrapper.text()).toContain('样板 · SP-s · 本单待确认使用')
    await wrapper.get('[aria-label="箱唛关联订单类型"]').setValue('REGULAR')
    expect(wrapper.find(`[data-asset-id="${asset.id}"]`).exists()).toBe(false)
    wrapper.unmount()
  })
  it('refreshes an order-specific supplier list when its issued version changes and discards the old response', async () => {
    let finishOld!: (assets: unknown[]) => void
    supplierApi.markAssets.mockReturnValueOnce(new Promise(resolve => { finishOld = resolve }))
    const order = { ...asset.orders[0]!, issue_id: 'new-issue' }
    supplierApi.markAssets.mockResolvedValueOnce([{ ...asset, file_name: 'current.pdf', orders: [order, { ...order, id: 'other-order', contract_no: 'OTHER-CONTRACT' }] }])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', supplier: true, readOnly: true, orderId: 'order-a', supplierIssueId: 'old-issue' } })
    await flushPromises()
    const signal = supplierApi.markAssets.mock.calls[0]![1] as AbortSignal
    await wrapper.setProps({ supplierIssueId: 'new-issue' }); await flushPromises()
    expect(signal.aborted).toBe(true)
    expect(wrapper.text()).toContain('current.pdf')
    expect(wrapper.text()).not.toContain('OTHER-CONTRACT')
    finishOld([{ ...asset, file_name: 'old.pdf', orders: [{ ...order, issue_id: 'old-issue' }] }]); await flushPromises()
    expect(wrapper.text()).toContain('current.pdf')
    expect(wrapper.text()).not.toContain('old.pdf')
    wrapper.unmount()
  })

  it('uploads per-file classifications and keeps failed file choices for retry', async () => {
    const files = [new File(['a'], '已确认.pdf'), new File(['b'], '制作中.pdf')]
    api.uploadAssets.mockResolvedValue([{ file_name: files[0]!.name, status: 'created', asset }, { file_name: files[1]!.name, status: 'failed', message: '文件损坏' }])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', uploadOnly: true } }); await flushPromises()
    const input = wrapper.get('input[type=file]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: files }); await input.trigger('change')
    await wrapper.get('[aria-label="已确认.pdf 上传分类 1"]').setValue('READY')
    await wrapper.get('[aria-label="已确认.pdf 资料备注 1"]').setValue('客户邮件确认')
    await wrapper.findAll('button').find(button => button.text().startsWith('上传入库'))!.trigger('click'); await flushPromises()
    expect(api.uploadAssets).toHaveBeenCalledWith('huaxing', files, expect.any(AbortSignal), [
      { status: 'READY', note: '客户邮件确认', sharing_mode: 'SUPPLIER', supplier_id: 'supplier-a' }, { status: 'DRAFT', note: '', sharing_mode: 'SUPPLIER', supplier_id: 'supplier-a' },
    ])
    expect(wrapper.find('[aria-label="已确认.pdf 上传分类 1"]').exists()).toBe(false)
    expect(wrapper.get<HTMLSelectElement>('[aria-label="制作中.pdf 上传分类 1"]').element.value).toBe('DRAFT')
    wrapper.unmount()
  })

  it('filters file states separately from order binding and saves a versioned confirmation', async () => {
    const workflow = { status: 'PENDING' as const, note: '', version: 2, previous_asset_id: 'old', superseded_by_asset_id: '', updated_by_name: '', updated_at: '', confirmed_by_name: '', confirmed_at: '', confirmation_note: '' }
    const pending = { ...asset, workflow }
    const old = { ...asset, id: 'old', file_name: '旧稿.pdf', workflow: { ...workflow, status: 'HISTORY' as const, version: 1 } }
    api.listAssets.mockResolvedValue([pending, old])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', checkEnabled: true } }); await flushPromises()
    expect(wrapper.find('[data-asset-id="old"]').exists()).toBe(false)
    await wrapper.get('[aria-label="箱唛资料分类"]').findAll('button').find(b => b.text().startsWith('历史版本'))!.trigger('click')
    expect(wrapper.find('[data-asset-id="old"]').exists()).toBe(true)
    expect(wrapper.get('[data-asset-id="old"]').text()).not.toContain('用于PDF核对')
    expect(wrapper.get('[data-asset-id="old"]').text()).not.toContain('提交人工审核')
    expect(wrapper.text()).not.toContain('选择 Excel / PDF 核对')
    expect(wrapper.find(`[data-asset-id="${asset.id}"]`).exists()).toBe(false)
    await wrapper.get('[aria-label="箱唛资料分类"]').findAll('button').find(b => b.text().startsWith('待确认'))!.trigger('click')
    await wrapper.get(`[aria-label="修改 ${asset.file_name} 状态"]`).trigger('click'); await flushPromises()
    await wrapper.get('[aria-label="箱唛资料状态"]').setValue('READY')
    await wrapper.get('[aria-label="箱唛资料状态备注"]').setValue('客户邮件同意 V2')
    api.classifyAsset.mockResolvedValue({ ...pending, revision: 2, workflow: { ...workflow, status: 'READY' } })
    await wrapper.get('[aria-label="修改箱唛资料状态"] form').trigger('submit'); await flushPromises()
    expect(api.classifyAsset).toHaveBeenCalledWith('huaxing', pending, 'READY', '客户邮件同意 V2', expect.any(AbortSignal))
    expect(wrapper.find('[aria-label="修改箱唛资料状态"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('uploads a linked revision as pending and clears its draft on scope changes', async () => {
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing' } }); await flushPromises()
    await wrapper.get(`[aria-label="上传 ${asset.file_name} 修改稿"]`).trigger('click')
    const file = new File(['pdf'], '修改.pdf')
    const input = wrapper.get('input[type=file]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] }); await input.trigger('change')
    expect(wrapper.get('[aria-label="修改.pdf 上传分类 1"]').text()).not.toContain('已确认可用')
    api.uploadAssets.mockResolvedValue([{ file_name: file.name, status: 'failed', message: '版本变化' }])
    await wrapper.findAll('button').find(button => button.text().startsWith('上传入库'))!.trigger('click'); await flushPromises()
    expect(api.uploadAssets).toHaveBeenCalledWith('huaxing', [file], expect.any(AbortSignal), [{ status: 'PENDING', note: '', previous_asset_id: asset.id, previous_revision: 1 }])
    await wrapper.setProps({ factoryId: 'huakang-a' }); await flushPromises()
    expect(wrapper.text()).not.toContain('上传修改稿：')
    expect(wrapper.find('[aria-label="修改.pdf 上传分类 1"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('uses the workspace search without clearing it on mount or a scope change, and keeps standalone search', async () => {
    const other = { ...asset, id: 'other', file_name: '另一份箱唛.pdf', contract_number: 'OTHER', orders: [] }
    api.listAssets.mockResolvedValue([asset, other])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', search: '100369' } }); await flushPromises()
    expect(wrapper.find('[aria-label="搜索箱唛资料"]').exists()).toBe(false)
    expect(wrapper.text()).toContain(asset.file_name)
    expect(wrapper.text()).not.toContain(other.file_name)
    expect(wrapper.emitted('update:search')).toBeUndefined()
    await wrapper.findAll('button').find(button => button.text() === '清除筛选')!.trigger('click')
    expect(wrapper.emitted('update:search')).toEqual([['']])
    await wrapper.setProps({ search: '' })
    expect(wrapper.text()).toContain(other.file_name)
    await wrapper.setProps({ factoryId: 'huakang-a', search: '另一份' }); await flushPromises()
    expect(wrapper.emitted('update:search')).toEqual([['']])
    expect(wrapper.text()).toContain(other.file_name)
    expect(wrapper.text()).not.toContain(asset.file_name)
    wrapper.unmount()
    api.listAssets.mockResolvedValue([{ ...asset, file_name: '未命名.pdf', contract_number: '', orders: [{ ...asset.orders[0]!, contract_no: 'SHARED-CONTRACT' }] }])
    const shared = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', search: 'SHARED-CONTRACT' } }); await flushPromises()
    expect(shared.text()).toContain('未命名.pdf')
    shared.unmount()
    api.listAssets.mockResolvedValue([asset, other])
    const standalone = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing' } }); await flushPromises()
    await standalone.get('[aria-label="搜索箱唛资料"]').setValue('100369')
    expect(standalone.text()).not.toContain(other.file_name)
    standalone.unmount()
  })
  it('opens PDF generation with the authorized Excel factory and revision', async () => {
    const excel = { ...asset, kind: 'excel' as const, file_name: 'source.xlsx' }
    supplierApi.markAssets.mockResolvedValue([excel])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', supplier: true, readOnly: true, supplierCheckEnabled: true } }); await flushPromises()
    await wrapper.get('[aria-label="由 source.xlsx 生成 PDF"]').trigger('click')
    expect(wrapper.emitted('supplierGeneratePdf')?.[0]?.[0]).toMatchObject({ id: asset.id, factory_id: 'huaxing', revision: 1 })
    wrapper.unmount()
  })
  it('lets the warehouse explicitly remove soft-deleted targets from a shared original', async () => {
    const shared = { ...asset, contract_number: '', recognition_source: 'manual_orders', bound_order_ids: ['order-a', 'deleted'] }
    api.listAssets.mockResolvedValue([shared])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing' } }); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '关联设置')!.trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('1 个原关联订单已取消或删除')
    await wrapper.findAll('button').find(button => button.text() === '移除失效关联')!.trigger('click')
    await wrapper.findAll('button').find(button => button.text() === '保存关联')!.trigger('click'); await flushPromises()
    expect(api.bindAsset).toHaveBeenCalledWith('huaxing', shared, '', '', expect.any(AbortSignal), ['order-a'])
    wrapper.unmount()
  })
  it('rejects a disjoint Excel/PDF pair offered by a multi-order source group', async () => {
    const second = { ...asset.orders[0]!, id: 'order-b', contract_no: 'CONTRACT-002' }
    const shared = { ...asset, id: 'shared-excel', kind: 'excel' as const, orders: [...asset.orders, second] }
    const excel = { ...asset, id: 'narrow-excel', kind: 'excel' as const }
    const pdf = { ...asset, id: 'other-pdf', orders: [second] }
    api.listAssets.mockResolvedValue([shared, excel, pdf])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', checkEnabled: true } }); await flushPromises()
    await wrapper.get('[aria-label="选择合同 4500222793、CONTRACT-002 的 Excel / PDF 核对文件"]').trigger('click')
    await wrapper.get('[aria-label="仓库核对 Excel"]').setValue(excel.id)
    await wrapper.findAll('button').find(button => button.text() === '带入 Excel / PDF 核对')!.trigger('click')
    expect(wrapper.emitted('useSources')).toBeUndefined()
    expect(wrapper.text()).toContain('没有共同的关联订单')
    wrapper.unmount()
  })
  it('binds one original to explicitly selected contracts without sending a conflicting single binding', async () => {
    const second = { ...asset.orders[0]!, id: 'order-b', order_no: 'CTR-b', contract_no: 'CONTRACT-002' }
    api.bindingOrders.mockResolvedValue([...asset.orders, second])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing' } }); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '关联设置')!.trigger('click'); await flushPromises()
    await wrapper.get('[aria-label="关联多个合同"]').setValue(true)
    await wrapper.get('[aria-label="关联订单 CTR-a"]').setValue(true)
    await wrapper.get('[aria-label="关联订单 CTR-b"]').setValue(true)
    await wrapper.findAll('button').find(button => button.text() === '保存关联')!.trigger('click'); await flushPromises()
    expect(api.bindAsset).toHaveBeenCalledWith('huaxing', asset, '', '', expect.any(AbortSignal), ['order-a', 'order-b'])
    wrapper.unmount()
  })
  it('carries a supplier Excel/PDF pair with only common issued orders and no warehouse write', async () => {
    const order = { ...asset.orders[0]!, issue_id: 'issue-a', customer_po: 'PO-A' }
    const excel = { ...asset, id: 'excel-own', kind: 'excel' as const, file_name: 'source.xlsx', orders: [order, { ...order, id: 'order-2' }] }
    const pdf = { ...asset, orders: [order] }
    supplierApi.markAssets.mockResolvedValue([excel, pdf])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: '', supplierFactories: ['huakang-b'], supplier: true, readOnly: true, supplierCheckEnabled: true } }); await flushPromises()
    await wrapper.get('[aria-label="选择合同 4500222793 的 Excel / PDF 核对文件"]').trigger('click')
    await wrapper.findAll('button').find(button => button.text() === '带入 Excel / PDF 核对')!.trigger('click')
    expect(wrapper.emitted('supplierSources')?.[0]?.[0]).toEqual([{ ...excel, factory_id: 'huakang-b', orders: [order] }, { ...pdf, factory_id: 'huakang-b' }])
    expect(wrapper.emitted('useSources')).toBeUndefined(); expect(api.bindAsset).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('pairs a multi-contract Excel with a PDF for one of its selected orders', async () => {
    const second = { ...asset.orders[0]!, id: 'order-b', contract_no: 'CONTRACT-002', issue_id: 'issue-b' }
    const common = { ...asset.orders[0]!, issue_id: 'issue-a' }
    const excel = { ...asset, id: 'excel-shared', kind: 'excel' as const, orders: [common, second] }
    const pdf = { ...asset, orders: [common] }
    supplierApi.markAssets.mockResolvedValue([excel, pdf])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', supplier: true, readOnly: true, supplierCheckEnabled: true } }); await flushPromises()
    await wrapper.get('[aria-label="选择合同 4500222793、CONTRACT-002 的 Excel / PDF 核对文件"]').trigger('click')
    expect(wrapper.get('[aria-label="仓库核对 PDF"]').element).toHaveProperty('value', pdf.id)
    await wrapper.findAll('button').find(button => button.text() === '带入 Excel / PDF 核对')!.trigger('click')
    expect(wrapper.emitted('supplierSources')?.[0]?.[0]).toEqual([{ ...excel, factory_id: 'huaxing', orders: [common] }, { ...pdf, factory_id: 'huaxing' }])
    wrapper.unmount()
  })

  it('selects a supplier Excel with its factory and issued order without enabling warehouse writes', async () => {
    const excel = { ...asset, kind: 'excel' as const, file_name: 'customer.xlsx', revision: 3,
      orders: asset.orders.map(order => ({ ...order, issue_id: 'issue-a', customer_po: 'PO-A' })) }
    supplierApi.markAssets.mockResolvedValue([excel])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huakang-b', supplier: true, readOnly: true, supplierCheckEnabled: true } }); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '选择 Excel 并上传 PDF 核对')!.trigger('click')
    expect(wrapper.emitted('supplierExcel')?.[0]?.[0]).toMatchObject({ id: excel.id, factory_id: 'huakang-b', revision: 3, orders: [{ issue_id: 'issue-a' }] })
    expect(wrapper.text()).not.toContain('上传入库')
    expect(wrapper.text()).not.toContain('关联设置')
    expect(api.listAssets).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('selects the explicit Excel/PDF pair across list filters without running a check', async () => {
    const excel = { ...asset, id: 'excel', kind: 'excel' as const, file_name: 'source.xlsx' }
    const newerPdf = { ...asset, id: 'pdf-new', file_name: 'revised.pdf' }
    api.listAssets.mockResolvedValue([asset, excel, newerPdf, { ...asset, id: 'photo', kind: 'image', file_name: 'photo.jpg' }])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', checkEnabled: true } }); await flushPromises()
    await wrapper.get('[aria-label="箱唛文件类型"]').setValue('pdf')
    await wrapper.get('[aria-label="选择合同 4500222793 的 Excel / PDF 核对文件"]').trigger('click')
    expect(wrapper.get('[aria-label="仓库核对 Excel"]').element).toHaveProperty('value', 'excel')
    expect(wrapper.get('[aria-label="仓库核对 PDF"]').element).toHaveProperty('value', '')
    expect(wrapper.get('[aria-label="选择仓库核对文件"]').text()).not.toContain('photo.jpg')
    const confirm = wrapper.findAll('button').find(button => button.text() === '带入 Excel / PDF 核对')!
    expect(confirm.attributes('disabled')).toBeDefined()
    await wrapper.get('[aria-label="仓库核对 PDF"]').setValue(newerPdf.id)
    await confirm.trigger('click')
    expect(wrapper.emitted('useSources')?.[0]).toEqual([[excel, newerPdf]])
    expect(api.downloadAsset).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('clears the source picker when the factory changes and hides it in read-only views', async () => {
    const excel = { ...asset, id: 'excel', kind: 'excel' as const, file_name: 'source.xlsx' }
    api.listAssets.mockResolvedValue([asset, excel])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', checkEnabled: true } }); await flushPromises()
    await wrapper.get('[aria-label="选择合同 4500222793 的 Excel / PDF 核对文件"]').trigger('click')
    api.listAssets.mockResolvedValue([])
    await wrapper.setProps({ factoryId: 'huakang-a' }); await flushPromises()
    expect(wrapper.find('[aria-label="选择仓库核对文件"]').exists()).toBe(false)
    expect(wrapper.emitted('useSources')).toBeUndefined()
    wrapper.unmount()
    api.listAssets.mockResolvedValue([asset, excel])
    const reader = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', checkEnabled: true, readOnly: true } }); await flushPromises()
    expect(reader.find('[aria-label="选择合同 4500222793 的 Excel / PDF 核对文件"]').exists()).toBe(false)
    reader.unmount()
  })

  it('binds an unnamed photo by searching all local orders and filling its contract', async () => {
    const photo: CartonMarkAsset = { ...asset, kind: 'image', file_name: '微信图片.png', contract_number: '', orders: [], binding_status: 'UNBOUND' }
    api.listAssets.mockResolvedValue([photo])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing' } }); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '关联设置')!.trigger('click'); await flushPromises()
    await wrapper.get('[aria-label="搜索可关联订单"]').setValue('100369')
    await wrapper.get('[aria-label="选择关联订单"]').setValue('order-a')
    await wrapper.findAll('button').find(button => button.text() === '保存关联')!.trigger('click'); await flushPromises()
    expect(api.bindAsset).toHaveBeenCalledWith('huaxing', photo, '4500222793', 'order-a', expect.any(AbortSignal), undefined)
    wrapper.unmount()
  })

  it('creates an unnamed photo group, binds the whole group and dissolves it without file changes', async () => {
    const photos: CartonMarkAsset[] = ['手机照片.png', '微信图片.png'].map((name, i) => ({ ...asset, id: `photo-${i}`, kind: 'image', file_name: name, contract_number: '', orders: [], binding_status: 'UNBOUND' }))
    api.listAssets.mockResolvedValue(photos)
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing' } }); await flushPromises()
    for (const checkbox of wrapper.findAll('input[aria-label^="选择照片"]')) await checkbox.setValue(true)
    await wrapper.findAll('button').find(button => button.text() === '组成照片组')!.trigger('click'); await flushPromises()
    expect(wrapper.get('[aria-label="关联箱唛资料"]').text()).toContain('2 张照片')
    const grouped = photos.map(photo => ({ ...photo, photo_group_id: 'group-1', revision: 2 }))
    api.listAssets.mockResolvedValue(grouped)
    await wrapper.findAll('button').find(button => button.text() === '保存照片组')!.trigger('click'); await flushPromises()
    expect(api.savePhotoGroup).toHaveBeenCalledWith('huaxing', photos, '', '', undefined, expect.any(AbortSignal), undefined)
    await wrapper.findAll('button').find(button => button.text() === '整组关联')!.trigger('click'); await flushPromises()
    await wrapper.get('[aria-label="选择关联订单"]').setValue('order-a')
    await wrapper.findAll('button').find(button => button.text() === '保存照片组')!.trigger('click'); await flushPromises()
    expect(api.savePhotoGroup).toHaveBeenLastCalledWith('huaxing', grouped, '4500222793', 'order-a', 'group-1', expect.any(AbortSignal), undefined)
    vi.spyOn(window, 'confirm').mockReturnValueOnce(true)
    await wrapper.findAll('button').find(button => button.text() === '解除分组')!.trigger('click'); await flushPromises()
    expect(api.ungroupPhotos).toHaveBeenCalledWith('huaxing', 'group-1', grouped, expect.any(AbortSignal))
    wrapper.unmount()
  })

  it('selects the entire existing group including filtered photos and shows a supplier group gallery', async () => {
    const photos = ['正面.png', '侧面.png'].map((name, i) => ({ ...asset, id: `group-photo-${i}`, kind: 'image' as const, file_name: name, photo_group_id: 'group-1' }))
    api.listAssets.mockResolvedValue(photos)
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing' } }); await flushPromises()
    await wrapper.get('[aria-label="搜索箱唛资料"]').setValue('正面')
    await wrapper.get('input[aria-label^="选择照片"]').setValue(true)
    expect(wrapper.text()).toContain('已选 2 张照片')
    await wrapper.findAll('button').find(button => button.text() === '整组关联')!.trigger('click'); await flushPromises()
    expect(wrapper.get('[aria-label="关联箱唛资料"]').text()).toContain('侧面.png')
    wrapper.unmount()
    supplierApi.markAssets.mockResolvedValue(photos)
    supplierApi.previewMarkAssetUrl.mockImplementation((id, scope) => `/api/${scope}/${id}.png`)
    const supplier = mount(CartonMarkAssetLibrary, { props: { factoryId: '', supplier: true, supplierFactories: ['huaxing', 'huakang-a'] } }); await flushPromises()
    await supplier.findAll('button').find(button => button.text() === '查看照片组')!.trigger('click')
    expect(supplier.get('[aria-label="箱唛照片组预览"]').findAll('img')).toHaveLength(2)
    expect(supplier.text()).not.toContain('整组关联')
    expect(supplier.text()).not.toContain('解除分组')
    expect(supplier.find('[aria-label^="选择照片"]').exists()).toBe(false)
    supplier.unmount()
  })

  it('discards delayed binding orders and group previews on a factory change', async () => {
    const photo = { ...asset, kind: 'image' as const, photo_group_id: 'group-1' }
    let finish: (orders: CartonMarkAsset['orders']) => void = () => {}
    api.bindingOrders.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    api.listAssets.mockResolvedValue([photo])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing' } }); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '整组关联')!.trigger('click')
    await wrapper.findAll('button').find(button => button.text() === '查看照片组')!.trigger('click')
    api.listAssets.mockResolvedValue([])
    await wrapper.setProps({ factoryId: 'huakang-a' }); finish(asset.orders); await flushPromises()
    expect(wrapper.find('[aria-label="关联箱唛资料"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="箱唛照片组预览"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('uploads and previews photos, filters by image and keeps photos out of the Excel/PDF check', async () => {
    const photo: CartonMarkAsset = { ...asset, id: 'CMA-photo', file_name: '4500222793_正唛.jpg', kind: 'image' }
    api.listAssets.mockResolvedValue([photo, asset])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', checkEnabled: true } })
    await flushPromises()
    const input = wrapper.get('input[type=file]')
    expect(input.attributes('accept')).toContain('.jpg,.jpeg,.png,.webp')
    await wrapper.get('select[aria-label="箱唛文件类型"]').setValue('image')
    expect(wrapper.findAll('li.mark-library-columns')).toHaveLength(1)
    expect(wrapper.text()).toContain('4500222793_正唛.jpg')
    expect(wrapper.get('a').attributes('href')).toContain('CMA-photo/document')
    expect(wrapper.text()).not.toContain('用于PDF核对')
    expect(wrapper.text()).not.toContain('用于Excel核对')
    const file = new File(['photo'], photo.file_name, { type: 'image/jpeg' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    api.uploadAssets.mockResolvedValue([{ file_name: file.name, status: 'created', message: '', asset: photo }])
    await wrapper.findAll('button').find(b => b.text().includes('上传入库'))!.trigger('click')
    await flushPromises()
    expect(api.uploadAssets).toHaveBeenCalledWith('huaxing', [file], expect.any(AbortSignal), [{ status: 'DRAFT', note: '', sharing_mode: 'SUPPLIER', supplier_id: 'supplier-a' }])
    expect(wrapper.text()).toContain('已入库')
    wrapper.unmount()
  })

  it('allows suppliers to preview and filter photos within their service factory', async () => {
    supplierApi.markAssets.mockResolvedValue([{ ...asset, id: 'photo', file_name: '4500222793.png', kind: 'image' }, asset])
    supplierApi.previewMarkAssetUrl.mockReturnValue('/api/huaxing/photo/document?preview=true')
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', supplier: true } })
    await flushPromises()
    await wrapper.get('select[aria-label="箱唛文件类型"]').setValue('image')
    expect(wrapper.findAll('li.mark-library-columns')).toHaveLength(1)
    expect(wrapper.get('a').attributes('href')).toBe('/api/huaxing/photo/document?preview=true')
    expect(supplierApi.previewMarkAssetUrl).toHaveBeenCalledWith('photo', 'huaxing')
    expect(wrapper.find('input[type=file]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('combines supplied service factories and keeps preview and download scoped to each file', async () => {
    supplierApi.markAssets.mockImplementation(async scope => [{ ...asset, id: `asset-${scope}` }])
    supplierApi.previewMarkAssetUrl.mockImplementation((id, scope) => `/api/${scope}/${id}.pdf`)
    supplierApi.downloadMarkAsset.mockRejectedValue(new Error('测试下载'))
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: '', supplier: true, supplierFactories: ['huaxing', 'huakang-a'] } }); await flushPromises()
    expect(supplierApi.markAssets.mock.calls.map(call => call[0])).toEqual(['huaxing', 'huakang-a'])
    expect(api.listAssets).not.toHaveBeenCalled()
    expect(wrapper.findAll('li.mark-library-columns')).toHaveLength(2)
    const huakang = wrapper.findAll('li.mark-library-columns').find(row => row.text().includes('华康A'))!
    expect(huakang.get('a').attributes('href')).toBe('/api/huakang-a/asset-huakang-a.pdf')
    await huakang.get('[aria-label^="下载"]').trigger('click'); await flushPromises()
    expect(supplierApi.downloadMarkAsset).toHaveBeenCalledWith('asset-huakang-a', 'huakang-a', expect.any(AbortSignal))
    expect(wrapper.find('input[type=file]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('cancels aggregate results when the authorized service-factory list changes', async () => {
    const finish: ((assets: object[]) => void)[] = []
    supplierApi.markAssets.mockImplementationOnce(() => new Promise(resolve => finish.push(resolve)))
      .mockImplementationOnce(() => new Promise(resolve => finish.push(resolve))).mockResolvedValueOnce([])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: '', supplier: true, supplierFactories: ['huaxing', 'huakang-a'] } })
    const oldSignal = supplierApi.markAssets.mock.calls[0]![1] as AbortSignal
    await wrapper.setProps({ supplierFactories: ['huaxing'] })
    finish.forEach(resolve => resolve([asset])); await flushPromises()
    expect(oldSignal.aborted).toBe(true)
    expect(wrapper.findAll('li.mark-library-columns')).toHaveLength(0)
    expect(wrapper.text()).not.toContain(asset.file_name)
    expect(supplierApi.markAssets).toHaveBeenLastCalledWith('huaxing', expect.any(AbortSignal))
    wrapper.unmount()
  })

  it('shows a failed factory and clears stale files instead of presenting a partial aggregate as complete', async () => {
    supplierApi.markAssets.mockResolvedValue([{ ...asset }])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: '', supplier: true, supplierFactories: ['huaxing', 'huakang-a'] } }); await flushPromises()
    expect(wrapper.findAll('li.mark-library-columns')).toHaveLength(2)
    supplierApi.markAssets.mockImplementation(async scope => {
      if (scope === 'huakang-a') throw new Error('账号无权访问此厂区')
      return [asset]
    })
    await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click'); await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain('华康A：账号无权访问此厂区')
    expect(wrapper.findAll('li.mark-library-columns')).toHaveLength(0)
    expect(wrapper.text()).not.toContain('暂无可查看')
    wrapper.unmount()
  })
  it('uses only supplier endpoints and hides upload, binding and QC controls', async () => {
    supplierApi.markAssets.mockResolvedValue([{ id: asset.id, file_name: asset.file_name, kind: 'pdf',
      size_bytes: 500, contract_number: asset.contract_number, created_at: asset.created_at,
      orders: [{ ...asset.orders[0], customer_po: 'PO-A' }] }])
    supplierApi.previewMarkAssetUrl.mockReturnValue('/api/scoped.pdf')
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', supplier: true } }); await flushPromises()
    expect(supplierApi.markAssets).toHaveBeenCalledWith('huaxing', expect.any(AbortSignal))
    expect(api.listAssets).not.toHaveBeenCalled()
    expect(wrapper.get('a').attributes('href')).toBe('/api/scoped.pdf')
    expect(wrapper.find('input[type=file]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('关联设置')
    expect(wrapper.text()).not.toContain('用于PDF核对')
    expect(wrapper.text()).not.toContain('CTR-a')
    await wrapper.get('select[aria-label="箱唛文件类型"]').setValue('excel')
    expect(wrapper.findAll('li.mark-library-columns')).toHaveLength(0)
    expect(wrapper.text()).toContain('没有符合筛选条件')
    wrapper.unmount()
  })

  it('rejects late supplier file results after the destination factory changes', async () => {
    let finish: (assets: object[]) => void = () => {}
    supplierApi.markAssets.mockImplementationOnce(() => new Promise(resolve => { finish = resolve })).mockResolvedValueOnce([])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', supplier: true } })
    await wrapper.setProps({ factoryId: 'huakang-a' })
    finish([{ ...asset, orders: [] }]); await flushPromises()
    expect(wrapper.findAll('li.mark-library-columns')).toHaveLength(0)
    expect(wrapper.text()).not.toContain(asset.file_name)
    wrapper.unmount()
  })
  it('uploads multiple files, reports each outcome and retains only failed files for retry', async () => {
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', checkEnabled: true } })
    await flushPromises()
    const files = [new File(['pdf'], '4500222793.pdf'), new File(['bad'], 'broken.pdf')]
    const input = wrapper.get('input[type=file]')
    expect(input.attributes('multiple')).toBeDefined()
    Object.defineProperty(input.element, 'files', { configurable: true, value: files })
    await input.trigger('change')
    api.uploadAssets.mockResolvedValue([{ file_name: files[0]!.name, status: 'created', message: '', asset },
      { file_name: files[1]!.name, status: 'failed', message: 'PDF 损坏', asset: null }])
    await wrapper.findAll('button').find(b => b.text().includes('上传入库'))!.trigger('click')
    await flushPromises()
    expect(api.uploadAssets).toHaveBeenCalledWith('huaxing', files, expect.any(AbortSignal), files.map(() => ({ status: 'DRAFT', note: '', sharing_mode: 'SUPPLIER', supplier_id: 'supplier-a' })))
    expect(wrapper.text()).toContain('PDF 损坏')
    expect(wrapper.text()).toContain('上传入库（1）')
    await wrapper.findAll('button').find(b => b.text() === '用于PDF核对')!.trigger('click')
    expect(wrapper.emitted('use')?.[0]).toEqual([asset])
    wrapper.unmount()
  })

  it('preserves an upload and its per-file results across an unchanged account refresh', async () => {
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', uploadOnly: true } })
    await flushPromises()
    const files = [new File(['pdf'], '4500222793.pdf'), new File(['bad'], 'broken.pdf')]
    const input = wrapper.get('input[type=file]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: files })
    await input.trigger('change')
    let finish!: (results: CartonMarkAssetUploadResult[]) => void
    api.uploadAssets.mockImplementationOnce(() => new Promise<CartonMarkAssetUploadResult[]>(resolve => { finish = resolve }))
    await wrapper.findAll('button').find(button => button.text().includes('上传入库'))!.trigger('click')
    const signal = api.uploadAssets.mock.calls[0]![2] as AbortSignal

    authState.currentUser = { ...authState.currentUser, name: '仓管刷新' }
    await flushPromises()
    expect(signal.aborted).toBe(false)
    expect(wrapper.text()).toContain('处理中…')
    expect(wrapper.text()).toContain('broken.pdf')

    finish([{ file_name: files[0]!.name, status: 'created', message: '', asset },
      { file_name: files[1]!.name, status: 'failed', message: 'PDF 损坏', asset: null }])
    await flushPromises()
    authState.currentUser = { ...authState.currentUser }
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain('已入库')
    expect(wrapper.get('[role="status"]').text()).toContain('PDF 损坏')
    expect(wrapper.text()).toContain('上传入库（1）')
    expect(api.uploadAssets).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it.each(['account', 'authorization'])('cancels an upload when the %s changes', async boundary => {
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', uploadOnly: true } })
    await flushPromises()
    const input = wrapper.get('input[type=file]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['pdf'], '4500222793.pdf')] })
    await input.trigger('change')
    let finish!: (results: CartonMarkAssetUploadResult[]) => void
    api.uploadAssets.mockImplementationOnce(() => new Promise<CartonMarkAssetUploadResult[]>(resolve => { finish = resolve }))
    await wrapper.findAll('button').find(button => button.text().includes('上传入库'))!.trigger('click')
    const signal = api.uploadAssets.mock.calls[0]![2] as AbortSignal

    if (boundary === 'account') authState.currentUser = { id: 'other-user', name: '其他仓管' }
    else authState.authorizationVersion += 1
    await flushPromises()
    expect(signal.aborted).toBe(true)
    finish([{ file_name: '4500222793.pdf', status: 'created', message: '', asset }])
    await flushPromises()
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('4500222793.pdf')
    wrapper.unmount()
  })

  it('supports optional contract correction with optimistic revision and explicit order choice', async () => {
    api.listAssets.mockResolvedValue([{ ...asset, binding_status: 'AMBIGUOUS' }])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing' } })
    await flushPromises()
    await wrapper.findAll('button').find(b => b.text() === '关联设置')!.trigger('click')
    await wrapper.get('[aria-label="关联箱唛资料"] select').setValue('order-a')
    api.bindAsset.mockResolvedValue(asset)
    await wrapper.findAll('button').find(b => b.text() === '保存关联')!.trigger('click')
    await flushPromises()
    expect(api.bindAsset).toHaveBeenCalledWith('huaxing', expect.objectContaining({ revision: 1 }), '4500222793', 'order-a', expect.any(AbortSignal), undefined)
    wrapper.unmount()
  })

  it('discards results from a previous factory and cancels its requests', async () => {
    let finish: (assets: CartonMarkAsset[]) => void = () => {}
    api.listAssets.mockImplementationOnce(() => new Promise<CartonMarkAsset[]>(resolve => { finish = resolve }))
      .mockResolvedValueOnce([])
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing' } })
    const previousSignal = api.listAssets.mock.calls[0]![2] as AbortSignal
    await wrapper.setProps({ factoryId: 'huakang' })
    finish([asset])
    await flushPromises()
    expect(previousSignal.aborted).toBe(true)
    expect(wrapper.findAll('li.mark-library-columns')).toHaveLength(0)
    expect(api.listAssets).toHaveBeenLastCalledWith('huakang', undefined, expect.any(AbortSignal))
    wrapper.unmount()
  })

  it('shows only the selected order documents without write actions', async () => {
    const wrapper = mount(CartonMarkAssetLibrary, { props: { factoryId: 'huaxing', orderId: 'order-a', readOnly: true } })
    await flushPromises()
    expect(api.listAssets).toHaveBeenCalledWith('huaxing', 'order-a', expect.any(AbortSignal))
    expect(wrapper.text()).toContain(asset.file_name)
    expect(wrapper.find('input[type=file]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('关联设置')
    wrapper.unmount()
  })
})

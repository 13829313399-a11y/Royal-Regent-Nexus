import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CartonSupplierMarkCheck from '../CartonSupplierMarkCheck.vue'
import type { SupplierMarkAsset, SupplierMarkCheck } from '@/api/cartonSupplierPortal'

const api = vi.hoisted(() => ({ markChecks: vi.fn(), createMarkCheck: vi.fn(), downloadMarkCheck: vi.fn(), previewMarkCheckUrl: vi.fn() }))
const access = reactive({ edit: true, read: true, authorizationVersion: 1 })
vi.mock('@/api/cartonSupplierPortal', () => ({ cartonSupplierPortalApi: api }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ currentUser: { id: 'supplier' }, get authorizationVersion() { return access.authorizationVersion }, can: (code: string) => code.endsWith(':edit') ? access.edit : access.read }) }))
const source: SupplierMarkAsset & { factory_id: string } = { id: 'excel-b', revision: 3, factory_id: 'huakang-b',
  file_name: '客人箱唛.xlsx', kind: 'excel', size_bytes: 123, contract_number: 'C-B', created_at: '2026-10-07',
  orders: [{ id: 'order-b', issue_id: 'issue-b', customer_name: 'ZURU', customer_po: 'PO-B', contract_no: 'C-B', item_no: 'I-B' }] }
const record: SupplierMarkCheck = { id: 'check-b', factory_id: 'huakang-b', customer_name: 'ZURU', po: 'PO-B', item: 'I-B',
  contract_number: 'C-B', version: 1, check_status: '发现差异', manual_released: false, qc_ready: false,
  order_id: 'order-b', issue_id: 'issue-b', excel_asset_id: 'excel-b', excel_file_name: '客人箱唛.xlsx', pdf_file_name: '印刷.pdf', created_at: '2026-10-07',
  check_result: { excel_file_name: '客人箱唛.xlsx', pdf_file_name: '印刷.pdf', summary: { overall_status: '发现差异', pass_count: 0, changed_count: 1, missing_count: 0, unexpected_count: 0, review_count: 0 }, excel_items: [], pdf_items: [], extraction: [],
    comparisons: [{ status: 'changed', expected: 'ITEM 100', actual: 'ITEM 101', expected_location: 'A1', actual_location: '第1页', note: '货号不同' }] } }
beforeEach(() => {
  vi.resetAllMocks(); access.edit = true; access.read = true; access.authorizationVersion = 1
  api.markChecks.mockResolvedValue([]); api.createMarkCheck.mockResolvedValue(record); api.previewMarkCheckUrl.mockReturnValue('/api/supplier/check.pdf')
})
async function choosePdf(wrapper: ReturnType<typeof mount>, file = new File(['%PDF-1.4'], '印刷.pdf', { type: 'application/pdf' })) {
  const input = wrapper.get('[aria-label="供应商印刷 PDF"]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
  await input.trigger('change'); return file
}

describe('supplier carton-mark PDF checks', () => {
  it('shows a missing customer PO explicitly rather than copying the contract number', async () => {
    const wrapper = mount(CartonSupplierMarkCheck, { props: { factoryIds: ['huakang-b'], source: null, refreshKey: 1 } })
    await flushPromises(); await wrapper.setProps({ source: { ...source, orders: source.orders.map(order => ({ ...order, customer_po: '' })) } }); await flushPromises()
    expect(wrapper.text()).toContain('C-B / 采购单未填写')
    expect(wrapper.text()).not.toContain('C-B / C-B')
    expect(api.createMarkCheck).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('uses a selected authorized library PDF without uploading it again', async () => {
    const wrapper = mount(CartonSupplierMarkCheck, { props: { factoryIds: ['huakang-b'], source: null, refreshKey: 1 } })
    await flushPromises()
    const pdfSource = { ...source, id: 'pdf-b', kind: 'pdf' as const, revision: 7, file_name: '已上传.pdf' }
    await wrapper.setProps({ source, pdfSource }); await flushPromises()
    expect(wrapper.text()).toContain('已从资料库选择 PDF：已上传.pdf')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.createMarkCheck).toHaveBeenCalledWith({ factory_id: 'huakang-b', order_id: 'order-b', issue_id: 'issue-b', excel_asset_id: 'excel-b', expected_revision: 3, pdf_asset_id: 'pdf-b', expected_pdf_revision: 7 })
    wrapper.unmount()
  })
  it('blocks stored PDF from another order or factory and allows replacing it with a local PDF', async () => {
    const wrapper = mount(CartonSupplierMarkCheck, { props: { factoryIds: ['huakang-b'], source: null, refreshKey: 1 } })
    await flushPromises()
    await wrapper.setProps({ source, pdfSource: { ...source, id: 'foreign', kind: 'pdf', factory_id: 'huaxing' } }); await flushPromises()
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.createMarkCheck).not.toHaveBeenCalled()
    const file = await choosePdf(wrapper); await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.createMarkCheck.mock.calls[0]![0]).toMatchObject({ print_pdf: file })
    expect(wrapper.emitted('clearPdfSource')).toBeDefined()
    wrapper.unmount()
  })
  it('submits the selected issued order and source revision, then retains failed results for correction', async () => {
    const wrapper = mount(CartonSupplierMarkCheck, { props: { factoryIds: ['huaxing', 'huakang-b'], source: null, refreshKey: 1 } })
    await flushPromises(); await wrapper.setProps({ source }); await flushPromises()
    expect(wrapper.find('input[type="text"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('C-B / PO-B')
    const file = await choosePdf(wrapper)
    api.markChecks.mockImplementation(async scope => scope === 'huakang-b' ? [record] : [])
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.createMarkCheck).toHaveBeenCalledWith({ factory_id: 'huakang-b', order_id: 'order-b', issue_id: 'issue-b', excel_asset_id: 'excel-b', expected_revision: 3, print_pdf: file })
    expect(wrapper.text()).toContain('暂不能用于 QC')
    expect(wrapper.text()).toContain('ITEM 100')
    expect(wrapper.text()).toContain('ITEM 101')
    expect(wrapper.findAll('a')[0]!.attributes('href')).toBe('/api/supplier/check.pdf')
    expect(wrapper.text()).not.toContain('人工放行按钮')
    wrapper.unmount()
  })
  it('requires explicit order selection when an Excel has multiple own orders', async () => {
    const wrapper = mount(CartonSupplierMarkCheck, { props: { factoryIds: ['huakang-b'], source: null, refreshKey: 1 } })
    await wrapper.setProps({ source: { ...source, orders: [...source.orders, { ...source.orders[0]!, id: 'order-2', issue_id: 'issue-2', item_no: 'I-2' }] } }); await flushPromises()
    expect(wrapper.get('[aria-label="核对关联采购订单"]').element).toHaveProperty('value', '')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[aria-label="核对关联采购订单"]').setValue('order-2')
    await choosePdf(wrapper)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.createMarkCheck.mock.calls[0]![0]).toMatchObject({ order_id: 'order-2', issue_id: 'issue-2' })
    wrapper.unmount()
  })
  it('allows readers to view failed history but hides upload, and clears sensitive results on revocation', async () => {
    access.edit = false; api.markChecks.mockResolvedValue([record])
    const wrapper = mount(CartonSupplierMarkCheck, { props: { factoryIds: ['huakang-b'], source, refreshKey: 1 } }); await flushPromises()
    expect(wrapper.text()).toContain('上传 PDF 需要供应商协同的编辑权限')
    expect(wrapper.text()).toContain('发现差异')
    expect(wrapper.find('input[type="file"]').exists()).toBe(false)
    access.read = false; access.authorizationVersion++; await flushPromises()
    expect(wrapper.text()).not.toContain('ZURU')
    expect(api.createMarkCheck).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('rejects non-PDF selections and preserves a clear error when a write fails', async () => {
    const wrapper = mount(CartonSupplierMarkCheck, { props: { factoryIds: ['huakang-b'], source: null, refreshKey: 1 } })
    await wrapper.setProps({ source }); await flushPromises()
    await choosePdf(wrapper, new File(['excel'], 'wrong.xlsx'))
    expect(wrapper.get('[role="alert"]').text()).toContain('PDF 文件')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    await choosePdf(wrapper)
    api.createMarkCheck.mockRejectedValue(new Error('资料版本已变更'))
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('资料版本已变更')
    expect(wrapper.get('[role="alert"]').text()).toContain('确认是否已保存')
    wrapper.unmount()
  })
  it('discards late records and upload responses after factory context changes', async () => {
    let finish!: (record: SupplierMarkCheck) => void
    api.createMarkCheck.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const wrapper = mount(CartonSupplierMarkCheck, { props: { factoryIds: ['huakang-b'], source: null, refreshKey: 1 } })
    await wrapper.setProps({ source }); await flushPromises(); await choosePdf(wrapper)
    await wrapper.get('form').trigger('submit')
    await wrapper.setProps({ source: null, factoryIds: ['huaxing'] }); await flushPromises()
    finish(record); await flushPromises()
    expect(wrapper.text()).not.toContain('核对已保存')
    expect(wrapper.text()).not.toContain('C-B')
    expect(wrapper.emitted('clearSource')).toBeDefined()
    wrapper.unmount()
  })
})

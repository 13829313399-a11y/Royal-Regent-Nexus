import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CartonSupplierMarkPdf from '../CartonSupplierMarkPdf.vue'

const api = vi.hoisted(() => ({ markUploadOrders: vi.fn(), uploadMarkAssets: vi.fn(), generateMarkPdf: vi.fn(), downloadMarkAsset: vi.fn(), markLayouts: vi.fn() }))
const access = reactive({ edit: true, authorizationVersion: 1 })
vi.mock('@/api/cartonSupplierPortal', () => ({ cartonSupplierPortalApi: api }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ currentUser: { id: 'supplier' }, get authorizationVersion() { return access.authorizationVersion }, can: (code: string) => code.endsWith(':edit') ? access.edit : true }) }))
const order = { id: 'order-a', issue_id: 'issue-a', customer_name: 'BUZZ', contract_no: '4500222793', customer_po: '', item_no: '100369', document_no: '采购-A', order_date: '2026-10-10' }
const source = { id: 'excel', revision: 2, factory_id: 'huaxing', file_name: 'customer.xlsx', kind: 'excel' as const, size_bytes: 50, contract_number: order.contract_no, created_at: '', orders: [order] }
const pdf = { ...source, id: 'pdf', revision: 1, kind: 'pdf' as const, file_name: 'customer_生成.pdf' }
beforeEach(() => {
  vi.resetAllMocks(); access.edit = true; access.authorizationVersion = 1
  api.markLayouts.mockResolvedValue([{ id: 'layout-a', name: 'BUZZ箱唛', version: 1 }]); api.markUploadOrders.mockResolvedValue([order]); api.generateMarkPdf.mockResolvedValue({ asset: pdf, page_count: 1, warnings: [] })
  api.downloadMarkAsset.mockResolvedValue(new Blob(['pdf'], { type: 'application/pdf' }))
  URL.createObjectURL = vi.fn(() => 'blob:preview'); URL.revokeObjectURL = vi.fn()
})
function submit(wrapper: ReturnType<typeof mount>) { return wrapper.findAll('button').find(button => button.text() === '生成 PDF')!.trigger('click') }
async function choose(wrapper: ReturnType<typeof mount>, file: File) {
  const input = wrapper.get('[aria-label="选择生成 PDF 的 Excel"]'); Object.defineProperty(input.element, 'files', { configurable: true, value: [file] }); await input.trigger('change')
}

describe('supplier Excel PDF generation', () => {
  it('generates from the stored source, previews and passes its exact pair to the existing check flow', async () => {
    const wrapper = mount(CartonSupplierMarkPdf, { props: { factoryIds: ['huaxing'], source } }); await flushPromises()
    expect(wrapper.text()).toContain('PO 未填写'); expect(wrapper.find('[aria-label="PDF 生成订单"]').exists()).toBe(false)
    await submit(wrapper); await flushPromises()
    expect(api.generateMarkPdf).toHaveBeenCalledWith({ factory_id: 'huaxing', order_id: order.id, issue_id: order.issue_id, excel_asset_id: source.id, expected_revision: 2, layout_id: 'layout-a' }, expect.any(AbortSignal))
    expect(api.uploadMarkAssets).not.toHaveBeenCalled(); expect(wrapper.get('iframe').attributes('src')).toBe('blob:preview')
    expect(wrapper.text()).toContain('待核对 / 审核')
    await wrapper.findAll('button').find(button => button.text() === '用 Excel / PDF 核对')!.trigger('click')
    expect(wrapper.emitted('check')?.[0]?.[0]).toEqual([source, pdf])
    wrapper.unmount(); expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:preview')
  })
  it('blocks generation until the customer has a saved layout', async () => {
    api.markLayouts.mockResolvedValue([])
    const wrapper = mount(CartonSupplierMarkPdf, { props: { factoryIds: ['huaxing'], source } }); await flushPromises()
    expect(wrapper.text()).toContain('先用历史稿确认一次')
    await submit(wrapper); expect(api.generateMarkPdf).not.toHaveBeenCalled(); wrapper.unmount()
  })
  it('uploads once and retains the saved Excel for conversion retries', async () => {
    api.uploadMarkAssets.mockResolvedValue([{ status: 'created', asset: source }])
    api.generateMarkPdf.mockRejectedValueOnce(new Error('引擎不可用'))
    const wrapper = mount(CartonSupplierMarkPdf, { props: { factoryIds: ['huaxing'], source: null } }); await flushPromises()
    const file = new File(['excel'], 'source.xlsx'); await choose(wrapper, file); await submit(wrapper); await flushPromises()
    expect(api.uploadMarkAssets.mock.calls[0]!.slice(0, 3)).toEqual(['huaxing', [file], order])
    expect(wrapper.text()).toContain('引擎不可用'); await submit(wrapper); await flushPromises()
    expect(api.uploadMarkAssets).toHaveBeenCalledTimes(1); expect(api.generateMarkPdf).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
  it('requires explicit selection when an Excel is shared across orders or factories', async () => {
    const second = { ...order, id: 'order-b', issue_id: 'issue-b', document_no: '采购-B' }
    api.markUploadOrders.mockResolvedValue([order, second])
    const wrapper = mount(CartonSupplierMarkPdf, { props: { factoryIds: ['huaxing', 'huakang-b'], source: { ...source, orders: [order, second] } } }); await flushPromises()
    await submit(wrapper); expect(api.generateMarkPdf).not.toHaveBeenCalled()
    await wrapper.get('[aria-label="PDF 生成订单"]').setValue(second.id); await flushPromises(); await submit(wrapper); await flushPromises()
    expect(api.generateMarkPdf.mock.calls[0]![0]).toMatchObject({ order_id: second.id, issue_id: second.issue_id, factory_id: 'huaxing' })
    wrapper.unmount()
    const blank = mount(CartonSupplierMarkPdf, { props: { factoryIds: ['huaxing', 'huakang-b'], source: null } }); await flushPromises()
    expect(blank.get('[aria-label="PDF 生成厂区"]').element).toHaveProperty('value', '')
    blank.unmount()
  })
  it('discards late results and clears previews and drafts on scope or permission changes', async () => {
    let finish!: (value: unknown) => void
    api.generateMarkPdf.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const wrapper = mount(CartonSupplierMarkPdf, { props: { factoryIds: ['huaxing'], source } }); await flushPromises(); await submit(wrapper)
    await wrapper.setProps({ factoryIds: ['huakang-b'], source: null }); await flushPromises()
    finish({ asset: pdf, page_count: 1, warnings: [] }); await flushPromises()
    expect(wrapper.find('iframe').exists()).toBe(false); expect(wrapper.emitted('saved')).toBeUndefined(); expect(wrapper.text()).not.toContain(source.file_name)
    access.edit = false; access.authorizationVersion++; await flushPromises()
    expect(wrapper.text()).toContain('没有此厂区的资料提交权限')
    wrapper.unmount()
  })
})

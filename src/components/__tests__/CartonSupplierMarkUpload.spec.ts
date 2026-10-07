import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CartonSupplierMarkUpload from '../CartonSupplierMarkUpload.vue'

const api = vi.hoisted(() => ({ markUploadOrders: vi.fn(), uploadMarkAssets: vi.fn() }))
const access = reactive({ edit: true, authorizationVersion: 1 })
vi.mock('@/api/cartonSupplierPortal', () => ({ cartonSupplierPortalApi: api }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ currentUser: { id: 'supplier' }, get authorizationVersion() { return access.authorizationVersion }, can: (code: string) => code.endsWith(':edit') ? access.edit : true }) }))
const order = { id: 'order-b', issue_id: 'issue-b', customer_name: 'BUZZ', contract_no: '4500222793', customer_po: 'PO', item_no: 'I-B', document_no: '采购-B-P01', order_date: '2026-10-07' }
beforeEach(() => { vi.resetAllMocks(); access.edit = true; access.authorizationVersion = 1; api.markUploadOrders.mockResolvedValue([order]); api.uploadMarkAssets.mockResolvedValue([]) })
async function choose(wrapper: ReturnType<typeof mount>, files: File[]) {
  const input = wrapper.get('[aria-label="供应商批量选择箱唛原文件"]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: files }); await input.trigger('change')
}
function submit(wrapper: ReturnType<typeof mount>) { return wrapper.findAll('button').find(button => button.text().startsWith('上传并自动关联'))!.trigger('click') }
describe('supplier batch mark upload', () => {
  it('accepts Excel, PDF and images together, keeping only failed files for retry', async () => {
    const wrapper = mount(CartonSupplierMarkUpload, { props: { factoryIds: ['huakang-b'] } }); await flushPromises()
    expect(wrapper.get('[aria-label="供应商箱唛上传订单"]').text()).toContain('采购-B-P01')
    const files = [new File(['excel'], '4500222793.xlsx'), new File(['pdf'], '4500222793.pdf'), new File(['image'], 'photo.jpg')]
    api.uploadMarkAssets.mockResolvedValue([{ file_name: files[0]!.name, status: 'created', message: '', asset: { orders: [order] } }, { file_name: files[1]!.name, status: 'duplicate', message: '', asset: null }, { file_name: files[2]!.name, status: 'failed', message: '请选择订单后重试', asset: null }])
    await choose(wrapper, files); await submit(wrapper); await flushPromises()
    expect(api.uploadMarkAssets.mock.calls[0]!.slice(0, 3)).toEqual(['huakang-b', files, undefined])
    expect(wrapper.text()).toContain('请选择订单后重试'); expect(wrapper.emitted('uploaded')).toHaveLength(1)
    expect(wrapper.text()).toContain('已绑定：华康B · BUZZ · 合同 4500222793 · PO PO · ITEM I-B')
    await wrapper.get('[aria-label="供应商箱唛上传订单"]').setValue(order.id)
    expect(wrapper.get('[aria-label="供应商箱唛绑定信息"]').text()).toContain('绑定客户BUZZ')
    expect(wrapper.get('[aria-label="供应商箱唛绑定信息"]').text()).toContain('货号 / ITEMI-B')
    await submit(wrapper); await flushPromises()
    expect(api.uploadMarkAssets.mock.calls[1]!.slice(0, 3)).toEqual(['huakang-b', [files[2]], order])
    wrapper.unmount()
  })
  it('requires a destination when listing all factories and never guesses one', async () => {
    const wrapper = mount(CartonSupplierMarkUpload, { props: { factoryIds: ['huaxing', 'huakang-b'] } }); await flushPromises()
    expect(api.markUploadOrders).not.toHaveBeenCalled()
    await choose(wrapper, [new File(['pdf'], 'a.pdf')]); await submit(wrapper); await flushPromises()
    expect(api.uploadMarkAssets).not.toHaveBeenCalled()
    await wrapper.get('[aria-label="供应商箱唛上传厂区"]').setValue('huakang-b'); await flushPromises()
    expect(api.markUploadOrders).toHaveBeenCalledWith('huakang-b', expect.any(AbortSignal))
    wrapper.unmount()
  })
  it('rejects oversized batches and preserves a retryable error on network failure', async () => {
    const wrapper = mount(CartonSupplierMarkUpload, { props: { factoryIds: ['huakang-b'] } }); await flushPromises()
    await choose(wrapper, Array.from({ length: 51 }, () => new File(['pdf'], 'a.pdf')))
    expect(wrapper.text()).toContain('每批最多 50')
    expect(api.uploadMarkAssets).not.toHaveBeenCalled()
    const file = new File(['pdf'], 'a.pdf'); await choose(wrapper, [file])
    api.uploadMarkAssets.mockRejectedValue(new Error('请求中断')); await submit(wrapper); await flushPromises()
    expect(wrapper.text()).toContain('请刷新资料库确认'); expect(wrapper.text()).toContain(file.name)
    wrapper.unmount()
  })
  it('clears drafts on scope or permission changes and discards late upload outcomes', async () => {
    let finish!: (value: unknown[]) => void
    api.uploadMarkAssets.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const wrapper = mount(CartonSupplierMarkUpload, { props: { factoryIds: ['huakang-b'] } }); await flushPromises()
    await choose(wrapper, [new File(['pdf'], 'secret.pdf')]); await submit(wrapper)
    await wrapper.setProps({ factoryIds: ['huaxing'] }); await flushPromises()
    finish([{ file_name: 'secret.pdf', status: 'created', message: '', asset: null }]); await flushPromises()
    expect(wrapper.text()).not.toContain('secret.pdf'); expect(wrapper.emitted('uploaded')).toBeUndefined()
    access.edit = false; access.authorizationVersion++; await flushPromises()
    expect(wrapper.find('input[type="file"]').exists()).toBe(false)
    wrapper.unmount()
  })
})

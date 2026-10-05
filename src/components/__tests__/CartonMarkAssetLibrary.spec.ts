import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CartonMarkAssetLibrary from '../CartonMarkAssetLibrary.vue'
import type { CartonMarkAsset } from '@/api/cartonMark'

const api = vi.hoisted(() => ({ listAssets: vi.fn(), uploadAssets: vi.fn(), bindAsset: vi.fn(), downloadAsset: vi.fn(), archiveAsset: vi.fn() }))
const supplierApi = vi.hoisted(() => ({ markAssets: vi.fn(), previewMarkAssetUrl: vi.fn(), downloadMarkAsset: vi.fn() }))
vi.mock('@/api/cartonMark', () => ({ cartonMarkApi: api }))
vi.mock('@/api/cartonSupplierPortal', () => ({ cartonSupplierPortalApi: supplierApi }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ can: () => true }) }))
const asset: CartonMarkAsset = {
  id: 'CMA-test', factory_id: 'huaxing', file_name: '4500222793.pdf', kind: 'pdf', size_bytes: 500,
  sha256: 'sha', contract_number: '4500222793', bound_order_id: null, recognition_source: 'filename',
  candidates: ['4500222793'], warning: '', binding_status: 'BOUND', revision: 1,
  orders: [{ id: 'order-a', order_no: 'CTR-a', contract_no: '4500222793', customer_name: 'ZURU', item_no: '100369' }],
  created_at: '2026-10-05', created_by_name: '仓管',
}
beforeEach(() => {
  vi.clearAllMocks()
  api.listAssets.mockResolvedValue([asset])
})

describe('carton-mark source repository', () => {
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
    await huakang.get('button').trigger('click'); await flushPromises()
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
    expect(api.uploadAssets).toHaveBeenCalledWith('huaxing', files, expect.any(AbortSignal))
    expect(wrapper.text()).toContain('PDF 损坏')
    expect(wrapper.text()).toContain('上传入库（1）')
    await wrapper.findAll('button').find(b => b.text() === '用于PDF核对')!.trigger('click')
    expect(wrapper.emitted('use')?.[0]).toEqual([asset])
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
    expect(api.bindAsset).toHaveBeenCalledWith('huaxing', expect.objectContaining({ revision: 1 }), '4500222793', 'order-a', expect.any(AbortSignal))
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

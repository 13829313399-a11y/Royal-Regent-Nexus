import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CartonMarkAssetLibrary from '../CartonMarkAssetLibrary.vue'
import type { CartonMarkAsset } from '@/api/cartonMark'

const api = vi.hoisted(() => ({ listAssets: vi.fn(), uploadAssets: vi.fn(), bindAsset: vi.fn(), downloadAsset: vi.fn(), archiveAsset: vi.fn(), bindingOrders: vi.fn(), savePhotoGroup: vi.fn(), ungroupPhotos: vi.fn() }))
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
  api.bindingOrders.mockResolvedValue(asset.orders)
})

describe('carton-mark source repository', () => {
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
    expect(api.bindAsset).toHaveBeenCalledWith('huaxing', photo, '4500222793', 'order-a', expect.any(AbortSignal))
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
    expect(api.savePhotoGroup).toHaveBeenCalledWith('huaxing', photos, '', '', undefined, expect.any(AbortSignal))
    await wrapper.findAll('button').find(button => button.text() === '整组关联')!.trigger('click'); await flushPromises()
    await wrapper.get('[aria-label="选择关联订单"]').setValue('order-a')
    await wrapper.findAll('button').find(button => button.text() === '保存照片组')!.trigger('click'); await flushPromises()
    expect(api.savePhotoGroup).toHaveBeenLastCalledWith('huaxing', grouped, '4500222793', 'order-a', 'group-1', expect.any(AbortSignal))
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
    expect(supplier.find('input[type="checkbox"]').exists()).toBe(false)
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
    expect(api.uploadAssets).toHaveBeenCalledWith('huaxing', [file], expect.any(AbortSignal))
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

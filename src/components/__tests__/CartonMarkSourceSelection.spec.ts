import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CartonMarkCheckPanel from '../modules/qa/CartonMarkCheckPanel.vue'
import type { CartonMarkAsset } from '@/api/cartonMark'

const api = vi.hoisted(() => ({ listTemplates: vi.fn(), listCustomers: vi.fn(), downloadAsset: vi.fn(), createTemplate: vi.fn() }))
vi.mock('@/api/cartonMark', () => ({ cartonMarkApi: api }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { department: 'pmc-warehouse' } }) }))
vi.mock('@/stores/app', () => ({ useAppStore: () => ({ activeProductionFactory: { id: 'huaxing', shortName: '华兴' } }) }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ can: () => true, currentUser: { display_name: '仓管' } }) }))

function asset(id: string, kind: 'pdf' | 'excel' = 'pdf'): CartonMarkAsset {
  return { id, factory_id: 'huaxing', file_name: `${id}.${kind === 'pdf' ? 'pdf' : 'xlsx'}`, kind,
    size_bytes: 3, sha256: id, contract_number: id, bound_order_id: null, recognition_source: 'filename',
    candidates: [id], warning: '', binding_status: 'BOUND', revision: 1,
    orders: [{ id: 'order', order_no: 'order', contract_no: id, customer_name: 'ZURU', item_no: '100369' }],
    created_at: '2026-10-05', created_by_name: '仓管' }
}
beforeEach(() => {
  vi.clearAllMocks()
  api.listTemplates.mockResolvedValue([])
  api.listCustomers.mockResolvedValue([{ id: 'ZURU', name: 'ZURU' }])
  api.downloadAsset.mockResolvedValue(new Blob(['file']))
  api.createTemplate.mockRejectedValue(new Error('test: inspect submitted sources'))
})

describe('saved carton-mark source selection', () => {
  it('keeps both concurrent file types and fills metadata from the last requested source', async () => {
    const wrapper = mount(CartonMarkCheckPanel, { props: { workspaceMode: 'warehouse' } })
    await flushPromises()
    await wrapper.get('input[placeholder="例如：HT-2026-001"]').setValue('OLD-CONTRACT')
    let finishExcel: (blob: Blob) => void = () => {}
    let finishPdf: (blob: Blob) => void = () => {}
    api.downloadAsset.mockImplementationOnce(() => new Promise<Blob>(resolve => { finishExcel = resolve }))
      .mockImplementationOnce(() => new Promise<Blob>(resolve => { finishPdf = resolve }))
    const excel = wrapper.vm.useLibraryAsset(asset('excel-A', 'excel'))
    const pdf = wrapper.vm.useLibraryAsset(asset('pdf-B'))
    finishExcel(new Blob(['excel']))
    await excel
    finishPdf(new Blob(['pdf']))
    await pdf
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(api.createTemplate).toHaveBeenCalledWith(expect.objectContaining({
      contractNumber: 'pdf-B', excelAssetId: 'excel-A', pdfAssetId: 'pdf-B',
    }))
    wrapper.unmount()
  })
  it('ignores a late response after a newer source of the same type has been selected', async () => {
    const wrapper = mount(CartonMarkCheckPanel, { props: { workspaceMode: 'warehouse' } })
    await flushPromises()
    let finishA: (blob: Blob) => void = () => {}
    api.downloadAsset.mockImplementationOnce(() => new Promise<Blob>(resolve => { finishA = resolve }))
    const earlier = wrapper.vm.useLibraryAsset(asset('A'))
    await wrapper.vm.useLibraryAsset(asset('B'))
    finishA(new Blob(['A']))
    await earlier
    expect(wrapper.text()).toContain('B.pdf')
    expect(wrapper.text()).not.toContain('A.pdf')
    await wrapper.vm.useLibraryAsset(asset('excel', 'excel'))
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(api.createTemplate).toHaveBeenCalledWith(expect.objectContaining({ pdfAssetId: 'B', excelAssetId: 'excel' }))
    wrapper.unmount()
  })

  it('blocks submission while replacing a source and lets manual selection cancel the pending source ID', async () => {
    const wrapper = mount(CartonMarkCheckPanel, { props: { workspaceMode: 'warehouse' } })
    await flushPromises()
    await wrapper.vm.useLibraryAsset(asset('old'))
    await wrapper.vm.useLibraryAsset(asset('excel', 'excel'))
    let finish: (blob: Blob) => void = () => {}
    api.downloadAsset.mockImplementationOnce(() => new Promise<Blob>(resolve => { finish = resolve }))
    const pending = wrapper.vm.useLibraryAsset(asset('late'))
    await flushPromises()
    expect(wrapper.get('button[type=submit]').attributes('disabled')).toBeDefined()
    await wrapper.get('form').trigger('submit')
    expect(api.createTemplate).not.toHaveBeenCalled()
    const file = new File(['local'], 'manual.pdf', { type: 'application/pdf' })
    const input = wrapper.findAll('input[type=file]').find(input => input.attributes('accept')?.includes('application/pdf'))!
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    finish(new Blob(['late']))
    await pending
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(api.createTemplate).toHaveBeenCalledWith(expect.objectContaining({ pdfAssetId: undefined, printPdf: file }))
    expect(wrapper.text()).not.toContain('late.pdf')
    wrapper.unmount()
  })
})

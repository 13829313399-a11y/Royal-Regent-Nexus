import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import CartonSupplierMarkLayout from '../CartonSupplierMarkLayout.vue'

const api = vi.hoisted(() => ({ previewLayoutReference: vi.fn(), previewSavedLayout: vi.fn(), saveMarkLayout: vi.fn() }))
vi.mock('@/api/cartonSupplierPortal', () => ({ cartonSupplierPortalApi: api }))
const order = { id: 'order', issue_id: 'issue', customer_name: 'BUZZ', contract_no: '4500222793', customer_po: '', item_no: 'ITEM', document_no: 'purchase', order_date: '' }
const config = { mode: 'front_side' as const, paper: 'A4' as const, font: 'Helvetica' as const, font_size: 11, front_percent: 55, front_copies: 2, side_copies: 2, barcode: 'Code128' as const, side_address: '', instructions: '', reference_page: 0, logo_region: null, stamp_region: null, field_cells: {} }
const current = { id: 'layout-1', factory_id: 'huaxing', customer_name: 'BUZZ', name: 'BUZZ箱唛', version: 1, reference_name: 'old.pdf', created_at: '', config }
const preview = { preview_data_url: 'data:image/png;base64,AA', page_width_mm: 297, page_height_mm: 210, page_count: 1, suggested_side_address: 'Confirmed address' }
beforeEach(() => { vi.resetAllMocks(); api.previewLayoutReference.mockResolvedValue(preview); api.previewSavedLayout.mockResolvedValue(preview); api.saveMarkLayout.mockResolvedValue(current) })
function saveButton(wrapper: ReturnType<typeof mount>) { return wrapper.findAll('button').find(button => button.text().startsWith('确认并保存'))! }
describe('customer layout version editor', () => {
  it('requires historical PDF and saves customer configuration with explicit V1 confirmation', async () => {
    const wrapper = mount(CartonSupplierMarkLayout, { props: { factory: 'huaxing', order, current: null } })
    expect(saveButton(wrapper).attributes('disabled')).toBeDefined()
    const input = wrapper.get('[aria-label="客户历史 PDF"]'), file = new File(['pdf'], 'old.pdf')
    Object.defineProperty(input.element, 'files', { value: [file] }); await input.trigger('change'); await flushPromises()
    expect(wrapper.get('img').attributes('src')).toBe(preview.preview_data_url)
    expect(wrapper.findAll('textarea')[0]!.element.value).toBe('Confirmed address')
    await saveButton(wrapper).trigger('click'); await flushPromises()
    expect(api.saveMarkLayout).toHaveBeenCalledWith('huaxing', order, 'BUZZ箱唛', expect.objectContaining({ mode: 'front_side', frame_style: 'original_red', side_address: 'Confirmed address' }), null, file, expect.any(AbortSignal))
    expect(wrapper.emitted('saved')?.[0]).toEqual([current]); wrapper.unmount()
  })
  it('reuses frozen historical reference and creates V2 without mutating V1', async () => {
    const wrapper = mount(CartonSupplierMarkLayout, { props: { factory: 'huaxing', order, current } }); await flushPromises()
    expect(saveButton(wrapper).text()).toContain('V2')
    expect((wrapper.get('[aria-label="客户排版模板"]').findAll('select')[2]!.element as HTMLSelectElement).value).toBe('plain')
    await wrapper.get('[aria-label="客户排版模板"]').findAll('select')[2]!.setValue('original_red')
    await wrapper.findAll('select')[0]!.setValue('front_only'); await saveButton(wrapper).trigger('click'); await flushPromises()
    expect(api.saveMarkLayout).toHaveBeenCalledWith('huaxing', order, current.name, expect.objectContaining({ mode: 'front_only', frame_style: 'original_red' }), current, null, expect.any(AbortSignal))
    expect(current.config.mode).toBe('front_side'); wrapper.unmount()
  })
  it('discards late preview after closing so another customer receives no stale draft', async () => {
    let finish!: (value: typeof preview) => void
    api.previewSavedLayout.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const wrapper = mount(CartonSupplierMarkLayout, { props: { factory: 'huaxing', order, current } }); wrapper.unmount()
    finish(preview); await flushPromises(); expect(wrapper.emitted('saved')).toBeUndefined()
  })
})

import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CartonMarkCheckPanel from '../modules/qa/CartonMarkCheckPanel.vue'
import type { CartonMarkTemplateRecordResponse } from '@/api/cartonMark'

const api = vi.hoisted(() => ({ listTemplates: vi.fn(), listCustomers: vi.fn(), downloadTemplateDocument: vi.fn(), batchAutoCheck: vi.fn() }))
vi.mock('@/api/cartonMark', () => ({ cartonMarkApi: api }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { department: 'qc' }, get query() { return context.query } }), RouterLink: { name: 'RouterLink', props: ['to'], template: '<a><slot /></a>' } }))
vi.mock('@/stores/app', () => ({ useAppStore: () => ({ get activeProductionFactory() { return { id: context.factory, shortName: '华兴' } } }) }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ can: () => context.allowed, currentUser: { display_name: 'QC' } }) }))
const context = reactive({ factory: 'huaxing', allowed: true, query: {} as Record<string, string> })
const template: CartonMarkTemplateRecordResponse = {
  id: 'T1', factory_id: 'huaxing', customer_name: 'ZURU', po: 'PO-1', item: '100369', contract_number: '4500222793', version: 2,
  check_status: '核对通过', check_result: { excel_file_name: 'source.xlsx', pdf_file_name: 'print.pdf', summary: { overall_status: '核对通过', pass_count: 1, changed_count: 0, missing_count: 0, unexpected_count: 0, review_count: 0 }, excel_items: [], pdf_items: [], comparisons: [], extraction: [] },
  excel_file_name: 'source.xlsx', excel_file_size: 10, pdf_file_name: 'print.pdf', pdf_file_size: 10,
  created_at: '2026-10-07', updated_at: '2026-10-07', created_by_name: '仓管', qc_ready: true,
  manual_released: false, manual_release_reason: '', manual_release_source_status: '', manual_released_by_name: '', manual_released_at: '',
}
beforeEach(() => {
  vi.clearAllMocks()
  context.factory = 'huaxing'; context.allowed = true; context.query = {}
  localStorage.clear()
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:photo')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  api.listTemplates.mockResolvedValue([structuredClone(template)])
  api.listCustomers.mockResolvedValue([{ id: 'ZURU', name: 'ZURU' }])
  api.downloadTemplateDocument.mockResolvedValue(new Blob(['pdf'], { type: 'application/pdf' }))
  api.batchAutoCheck.mockRejectedValue(new Error('test: inspect submitted photographs'))
})
afterEach(() => vi.restoreAllMocks())
async function chooseFiles(wrapper: ReturnType<typeof mount>, selector: string, files: File[]) {
  const input = wrapper.get(selector)
  Object.defineProperty(input.element, 'files', { configurable: true, value: files })
  await input.trigger('change')
}

describe('carton source check and QC workflow', () => {
  it('opens QC with the exact eligible template from the warehouse link', async () => {
    context.query = { factory: 'huaxing', template: 'T1' }
    const wrapper = mount(CartonMarkCheckPanel, { props: { workspaceMode: 'qc' } }); await flushPromises()
    expect(wrapper.get('[aria-label="选择箱唛模板"]').element).toHaveProperty('value', 'T1')
    expect(api.batchAutoCheck).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it.each(['unreleased', 'another factory'])('does not select a %s template from a deep link', async reason => {
    context.query = { factory: 'huaxing', template: 'T1' }
    api.listTemplates.mockResolvedValue([{ ...template, ...(reason === 'unreleased' ? { qc_ready: false, check_status: '发现差异' } : { factory_id: 'huakang-a' }) }])
    const wrapper = mount(CartonMarkCheckPanel, { props: { workspaceMode: 'qc' } }); await flushPromises()
    expect(wrapper.get('[aria-label="选择箱唛模板"]').element).toHaveProperty('value', '')
    expect(wrapper.text()).toContain('尚未通过核对或人工放行')
    expect(api.batchAutoCheck).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('selects a ready library card and clears photos when a refresh revokes its eligibility', async () => {
    const wrapper = mount(CartonMarkCheckPanel, { props: { workspaceMode: 'qc' } }); await flushPromises()
    await wrapper.get('[aria-label="选用模板 print.pdf"]').trigger('click'); await flushPromises()
    expect(wrapper.get('[aria-label="选择箱唛模板"]').element).toHaveProperty('value', 'T1')
    await chooseFiles(wrapper, '[aria-label="拍摄正唛照片"]', [new File(['image'], 'front.jpg', { type: 'image/jpeg' })])
    api.listTemplates.mockResolvedValue([{ ...template, qc_ready: false }])
    await wrapper.get('[aria-label="刷新箱唛核对资料"]').trigger('click'); await flushPromises()
    expect(wrapper.get('[aria-label="选择箱唛模板"]').element).toHaveProperty('value', '')
    expect(wrapper.text()).toContain('未选择正唛')
    expect(api.batchAutoCheck).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps a manually chosen template and its photos when refreshing an earlier warehouse deep link', async () => {
    context.query = { factory: 'huaxing', template: 'T1' }
    const newer = { ...template, id: 'T2', pdf_file_name: 'new-print.pdf', version: 3 }
    api.listTemplates.mockResolvedValue([template, newer])
    const wrapper = mount(CartonMarkCheckPanel, { props: { workspaceMode: 'qc' } }); await flushPromises()
    await wrapper.get('[aria-label="选用模板 new-print.pdf"]').trigger('click'); await flushPromises()
    await chooseFiles(wrapper, '[aria-label="拍摄正唛照片"]', [new File(['image'], 'front.jpg', { type: 'image/jpeg' })])
    await wrapper.get('[aria-label="刷新箱唛核对资料"]').trigger('click'); await flushPromises()
    expect(wrapper.get('[aria-label="选择箱唛模板"]').element).toHaveProperty('value', 'T2')
    expect(wrapper.text()).toContain('已选择 1 张正唛')
    wrapper.unmount()
  })

  it('appends camera photos, preserves the other side and uploads only on explicit verification', async () => {
    const wrapper = mount(CartonMarkCheckPanel, { props: { workspaceMode: 'qc' } }); await flushPromises()
    await wrapper.get('[aria-label="选用模板 print.pdf"]').trigger('click'); await flushPromises()
    const front = new File(['front'], 'front.jpg', { type: 'image/jpeg' })
    const side = new File(['side'], 'side.jpg', { type: 'image/jpeg' })
    const extra = new File(['extra'], 'extra.jpg', { type: 'image/jpeg' })
    expect(wrapper.get('[aria-label="拍摄正唛照片"]').attributes('capture')).toBe('environment')
    expect(wrapper.get('[aria-label="拍摄正唛照片"]').attributes('multiple')).toBeUndefined()
    expect(wrapper.findAll('input[type=file][multiple]')).toHaveLength(2)
    await chooseFiles(wrapper, '[aria-label="拍摄正唛照片"]', [front])
    await chooseFiles(wrapper, '[aria-label="拍摄侧唛照片"]', [side])
    await chooseFiles(wrapper, '[aria-label="拍摄正唛照片"]', [])
    await chooseFiles(wrapper, '[aria-label="拍摄正唛照片"]', [extra])
    expect(wrapper.text()).toContain('已选择 2 张正唛')
    expect(wrapper.text()).toContain('已选择 1 张侧唛')
    expect(wrapper.text()).toContain('框选箱唛区域')
    expect(api.batchAutoCheck).not.toHaveBeenCalled()
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.batchAutoCheck).toHaveBeenCalledWith(expect.objectContaining({ frontPhotos: [front, extra], sidePhotos: [side] }))
    wrapper.unmount()
  })

  it('removes camera access from readers and clears captured photos on factory change', async () => {
    context.query = { factory: 'huaxing', template: 'T1' }
    const wrapper = mount(CartonMarkCheckPanel, { props: { workspaceMode: 'qc' } }); await flushPromises()
    await chooseFiles(wrapper, '[aria-label="拍摄正唛照片"]', [new File(['front'], 'front.jpg', { type: 'image/jpeg' })])
    api.listTemplates.mockResolvedValue([])
    context.factory = 'huakang-a'; await flushPromises()
    expect(wrapper.text()).toContain('未选择正唛')
    api.listTemplates.mockResolvedValue([template])
    context.factory = 'huaxing'; await flushPromises()
    expect(wrapper.get('[aria-label="选择箱唛模板"]').element).toHaveProperty('value', 'T1')
    context.allowed = false; await flushPromises()
    expect(wrapper.find('[aria-label="拍摄正唛"]').exists()).toBe(false)
    expect(wrapper.get('[aria-label="拍摄正唛照片"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
})

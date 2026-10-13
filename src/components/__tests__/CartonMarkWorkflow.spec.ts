import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CartonMarkCheckPanel from '../modules/qa/CartonMarkCheckPanel.vue'
import type { CartonMarkTemplateRecordResponse, CartonMarkQcRecord } from '@/api/cartonMark'

const api = vi.hoisted(() => ({ listTemplates: vi.fn(), listCustomers: vi.fn(), downloadTemplateDocument: vi.fn(), createQcRecords: vi.fn(), listQcRecords: vi.fn(), qcAction: vi.fn(), downloadQcPhoto: vi.fn(), downloadQcTemplate: vi.fn(), manualReleaseTemplate: vi.fn() }))
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
const evidence: CartonMarkQcRecord = {
  id: 'QC-1', factory_id: 'huaxing', template_id: 'ARCHIVED', template_version: 1,
  template_snapshot: { pdf_file_name: 'confirmed-v1.pdf', check_status: '核对通过' },
  customer_name: 'ZURU', po: 'PO-1', item: '100369', contract_number: '4500222793',
  corrects_record_id: null, note: '现场照片', created_by_name: '另一手机 QC', created_at: '2026-10-10',
  revision: 1, status: '待复核', photos: [{ id: 'P1', side: 'front', file_name: 'front.png', size_bytes: 5, sha256: 'sha' }],
  events: [{ revision: 1, kind: 'AUTO_CHECK', status: '待复核', result: null, error: '待人工检查', note: '', actor_name: '另一手机 QC', created_at: '2026-10-10' }],
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
  api.listQcRecords.mockResolvedValue({ items: [], total: 0 })
  api.downloadQcPhoto.mockResolvedValue(new Blob(['photo'], { type: 'image/png' }))
  api.downloadQcTemplate.mockResolvedValue(new Blob(['original'], { type: 'application/pdf' }))
  api.createQcRecords.mockRejectedValue(new Error('test: inspect submitted photographs'))
})
afterEach(() => vi.restoreAllMocks())
async function chooseFiles(wrapper: ReturnType<typeof mount>, selector: string, files: File[]) {
  const input = wrapper.get(selector)
  Object.defineProperty(input.element, 'files', { configurable: true, value: files })
  await input.trigger('change')
}

describe('carton source check and QC workflow', () => {
  it('retains selected photos on save failure and retries with the same submission ID', async () => {
    const wrapper = mount(CartonMarkCheckPanel, { props: { workspaceMode: 'qc' } }); await flushPromises()
    await wrapper.get('[aria-label="选用模板 print.pdf"]').trigger('click'); await flushPromises()
    const photo = new File(['front'], 'front.jpg', { type: 'image/jpeg' })
    await chooseFiles(wrapper, '[aria-label="拍摄正唛照片"]', [photo])
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('服务端未确认保存')
    expect(wrapper.text()).toContain('已选择 1 张正唛')
    expect(localStorage.getItem('rr-carton-mark-photo-records')).toBeNull()
    const firstId = api.createQcRecords.mock.calls[0]?.[0].requestId
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.createQcRecords.mock.calls[1]?.[0].requestId).toBe(firstId)
    wrapper.unmount()
  })

  it('loads another device’s original photos and archived template version, then appends a review', async () => {
    api.listQcRecords.mockResolvedValue({ items: [structuredClone(evidence)], total: 1 })
    api.qcAction.mockResolvedValue({ ...structuredClone(evidence), status: '发现异常', revision: 2,
      events: [...evidence.events, { revision: 2, kind: 'REVIEW', status: '发现异常', result: null, error: '', note: '侧唛地址印错了', actor_name: 'QC', created_at: '2026-10-10' }] })
    const wrapper = mount(CartonMarkCheckPanel, { props: { workspaceMode: 'qc' } }); await flushPromises()
    expect(wrapper.text()).toContain('服务器留档 · 资料 V1 · 另一手机 QC')
    await wrapper.findAll('button').find(b => b.text() === '查看核验')!.trigger('click'); await flushPromises()
    expect(api.downloadQcPhoto).toHaveBeenCalledWith('huaxing', 'QC-1', 'P1', expect.any(AbortSignal))
    expect(api.downloadQcTemplate).toHaveBeenCalledWith('huaxing', 'QC-1', expect.any(AbortSignal))
    expect(api.downloadTemplateDocument).not.toHaveBeenCalled()
    await wrapper.get('#qc-review-note').setValue('侧唛地址印错了')
    await wrapper.findAll('button').find(b => b.text() === '确认发现异常')!.trigger('click'); await flushPromises()
    expect(api.qcAction).toHaveBeenCalledWith('huaxing', 'QC-1', expect.objectContaining({ expected_revision: 1, note: '侧唛地址印错了', action: '发现异常' }))
    expect(wrapper.text()).toContain('第 2 次 · 人工复核 · 发现异常')
    expect(wrapper.text()).toContain('第 1 次 · 自动核对')
    wrapper.unmount()
  })

  it('rejects obsolete factory history responses', async () => {
    let finish!: (value: { items: CartonMarkQcRecord[], total: number }) => void
    api.listQcRecords.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = mount(CartonMarkCheckPanel, { props: { workspaceMode: 'qc' } }); await flushPromises()
    context.factory = 'huakang-a'; await flushPromises()
    finish({ items: [structuredClone(evidence)], total: 1 }); await flushPromises()
    expect(wrapper.text()).not.toContain('另一手机 QC')
    wrapper.unmount()
  })
  it('opens QC with the exact eligible template from the warehouse link', async () => {
    context.query = { factory: 'huaxing', template: 'T1' }
    const wrapper = mount(CartonMarkCheckPanel, { props: { workspaceMode: 'qc' } }); await flushPromises()
    expect(wrapper.get('[aria-label="选择箱唛模板"]').element).toHaveProperty('value', 'T1')
    expect(api.createQcRecords).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it.each(['unreleased', 'another factory'])('does not select a %s template from a deep link', async reason => {
    context.query = { factory: 'huaxing', template: 'T1' }
    api.listTemplates.mockResolvedValue([{ ...template, ...(reason === 'unreleased' ? { qc_ready: false, check_status: '发现差异' } : { factory_id: 'huakang-a' }) }])
    const wrapper = mount(CartonMarkCheckPanel, { props: { workspaceMode: 'qc' } }); await flushPromises()
    expect(wrapper.get('[aria-label="选择箱唛模板"]').element).toHaveProperty('value', '')
    expect(wrapper.text()).toContain('尚未通过核对或人工放行')
    expect(api.createQcRecords).not.toHaveBeenCalled()
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
    expect(api.createQcRecords).not.toHaveBeenCalled()
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
    expect(api.createQcRecords).not.toHaveBeenCalled()
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.createQcRecords).toHaveBeenCalledWith(expect.objectContaining({ frontPhotos: [front, extra], sidePhotos: [side] }))
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


it('approves original-only sources directly without a checklist or reason dialog', async () => {
  const pending: CartonMarkTemplateRecordResponse = { ...template, qc_ready: false, manual_released: false, check_status: '需复核', excel_file_name: '', excel_file_size: 0,
    check_result: { ...template.check_result, review_method: 'manual_sources', review_note: '客户签样照片', source_assets: [{ id: 'IMG1', revision: 1, file_name: 'front.png', kind: 'image', sha256: 'sha' }] } }
  api.listTemplates.mockResolvedValue([pending])
  api.manualReleaseTemplate.mockResolvedValue({ ...pending, qc_ready: true, manual_released: true, manual_released_at: '2026-10-10', manual_released_by_name: '主管', manual_release_reason: '客户已签样确认此版本' })
  const wrapper = mount(CartonMarkCheckPanel, { props: { workspaceMode: 'warehouse' } }); await flushPromises()
  await wrapper.findAll('button').find(button => button.text().startsWith('ZURU'))!.trigger('click')
  expect(wrapper.text()).toContain('待人工审核')
  await wrapper.findAll('button').find(button => button.text() === '审核通过')!.trigger('click'); await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  expect(api.manualReleaseTemplate).toHaveBeenCalledWith('T1', 'huaxing', '')
  expect(wrapper.text()).toContain('人工审核通过')
  wrapper.unmount()
})

it('keeps image-reference QC manual and offers original photos without automatic rerun', async () => {
  const images = { review_method: 'manual_sources', source_assets: [{ id: 'IMG1', revision: 1, file_name: 'front.png', kind: 'image', sha256: 'sha' }] }
  api.listTemplates.mockResolvedValue([{ ...template, check_result: { ...template.check_result, ...images } }])
  api.listQcRecords.mockResolvedValue({ items: [{ ...structuredClone(evidence), template_snapshot: images,
    events: [{ ...evidence.events[0]!, kind: 'REVIEW', error: '' }] }], total: 1 })
  const wrapper = mount(CartonMarkCheckPanel, { props: { workspaceMode: 'qc' } }); await flushPromises()
  await wrapper.get('[aria-label="选用模板 print.pdf"]').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('图片资料暂仅支持人工对照')
  await chooseFiles(wrapper, '[aria-label="拍摄正唛照片"]', [new File(['front'], 'front.jpg', { type: 'image/jpeg' })])
  expect(wrapper.text()).toContain('保存照片待人工复核（1 张）')
  await wrapper.findAll('button').find(button => button.text() === '查看核验')!.trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('图片资料人工核验')
  expect(wrapper.text()).toContain('照片留档')
  expect(wrapper.text()).toContain('查看当时原稿：front.png')
  expect(wrapper.findAll('button').some(button => button.text().includes('重新自动核对'))).toBe(false)
  expect(wrapper.text()).toContain('确认核对通过')
  wrapper.unmount()
})

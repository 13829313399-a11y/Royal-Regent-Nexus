import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import type { ApiInternalQuoteSection, ApiInternalQuoteImportPreview } from '@/api/internalQuote'
import type { InternalQuoteSectionCode } from '@/types/internalQuoteDesk'
import InternalQuoteSectionEditor from '../InternalQuoteSectionEditor.vue'

vi.mock('vue-router', () => ({ onBeforeRouteLeave: vi.fn(), onBeforeRouteUpdate: vi.fn() }))

function setup(code: InternalQuoteSectionCode, payload: Record<string, unknown>) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useInternalQuoteDeskStore()
  const quote = { ...store.placeholderQuote, id: 'feedback-quote', factoryId: 'huakang-b', referenceSnapshot: {
    material_prices: { 'ABS|750SW': '8.5' },
    machine_prices: [{ range: '18A', machine: '180T', shift_price_hkd: '1890' }],
  } }
  const section = { ...quote.sections.find((row) => row.code === code)!, code, payload, status: 'draft' as const,
    revision: 5, updatedAt: 'saved', dependencies: [], warnings: [], attachments: [], lines: [] }
  const save = vi.spyOn(store, 'saveSection').mockImplementation(async (_id, _code, _revision, next) => (
    { revision: 5, payload: next } as ApiInternalQuoteSection
  ))
  vi.spyOn(store, 'previewSectionCost').mockResolvedValue(undefined)
  const wrapper = mount(InternalQuoteSectionEditor, {
    props: { quote, section, canEdit: true, canReview: false, canRemove: false, wholeQuoteReview: true },
    global: { plugins: [pinia], stubs: { InternalQuoteAttachmentPreview: true, teleport: true, DialogPortal: { template: "<div><slot /></div>" } } }, attachTo: document.body,
  })
  return { wrapper, save, section, store }
}

afterEach(() => { vi.restoreAllMocks(); document.body.innerHTML = '' })

const moldPreview = {
  batch_id: 'mold-preview', target_revision: 5, import_type: 'mold', source_file_name: '模具报价.xlsx',
  sheet_name: '01', header_row: 11, row_count: 1, warnings: [],
  diff_summary: { existing_rows: 0, imported_rows: 1, replace_result_rows: 1 },
} as unknown as ApiInternalQuoteImportPreview

async function chooseMoldFile(wrapper: ReturnType<typeof setup>['wrapper']) {
  const input = wrapper.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['xlsx'], '模具报价.xlsx')] })
  await input.trigger('change')
  await flushPromises()
}

describe('internal quote feedback regressions', () => {
  it.each(['engineering', 'molding', 'sales'] as const)('keeps an untouched %s form clean before import', async code => {
    const { wrapper } = setup(code, {})
    await flushPromises()
    expect(wrapper.vm.hasUnsavedChanges()).toBe(false)
    expect(wrapper.find('.dirty').exists()).toBe(false)
    wrapper.unmount()
  })

  it('previews and confirms a mold import with unsaved hardware without a separate save', async () => {
    const { wrapper, save, store } = setup('engineering', {})
    await wrapper.findAll('button').find(button => button.text() === '新增五金')!.trigger('click')
    await wrapper.get('[aria-label="五金零件名称"]').setValue('螺丝')
    expect(wrapper.vm.hasUnsavedChanges()).toBe(true)
    expect(wrapper.text()).toContain('此状态包含五金、辅助材料及模具的修改')
    const preview = vi.spyOn(store, 'previewImport').mockResolvedValue(moldPreview)
    const draft = wrapper.vm.getWholeQuoteDraft().payload
    const confirm = vi.spyOn(store, 'confirmImport').mockResolvedValue({ section: { revision: 6, payload: {
      ...draft, molds: [{ item: '新模具', cost_rmb: 49500 }],
      production_mold_costs: [{ item: '模具费用', cost_rmb: '49500', import_batch_id: 'mold-preview', mold_import_default_rmb: '49500' }],
    } } })
    await chooseMoldFile(wrapper)
    expect(preview.mock.calls[0]?.[3]).toEqual({ revision: 5, payload: draft })
    expect(save).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="save-department-draft"]').exists()).toBe(false)
    expect(wrapper.vm.hasUnsavedChanges()).toBe(true)
    expect(wrapper.get('.quote-import-preview').text()).toContain('将模具总价填入“模具费用”')
    await wrapper.findAll('button').find(button => button.text() === '确认导入')!.trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(wrapper.vm.getWholeQuoteDraft().payload).toMatchObject({ materials: [{ item: '螺丝' }], molds: [{ item: '新模具' }] })
    expect(wrapper.vm.hasUnsavedChanges()).toBe(false)
    expect(save).not.toHaveBeenCalled()
    const feeInput = wrapper.get('[aria-label="生产模具费用 RMB"]')
    expect((feeInput.element as HTMLInputElement).value).toBe('49500')
    await feeInput.setValue('50000')
    expect(wrapper.vm.getWholeQuoteDraft().payload.production_mold_costs).toEqual([
      { item: '模具费用', cost_rmb: 50000, import_batch_id: 'mold-preview', mold_import_default_rmb: '49500' },
    ])
    expect(wrapper.vm.hasUnsavedChanges()).toBe(true)
    wrapper.unmount()
  })

  it('retains the legacy association when editable Engineering receives its first stable ID', async () => {
    const engineering = setup('engineering', { molds: [{ mold_no: 'M1', item: '原外壳', parts: [] }] })
    const molding = setup('molding', { injection_lines: [{
      engineering_source_key: 'mold-no:M1#1', engineering_synced_fields: ['item'],
      item: '原外壳', mold_no: 'M1', material: 'ABS', grade: '750SW', net_weight_g: 100,
      sets: 1, target_output: 2000, machine_code: '18A', quantity: 1,
    }] })
    try {
      const detach = molding.wrapper.findAll('button').find(button => button.text() === '解除联动')!
      await detach.trigger('click')
      await molding.wrapper.get('.moldingInjectionTable textarea').setValue('独立补录壳')
      await engineering.wrapper.get('textarea[aria-label="模具名称"]').setValue('改名外壳')
      const source = engineering.wrapper.vm.getWholeQuoteDraft().payload
      expect(source).toMatchObject({ molds: [{ legacy_source_key: 'mold-no:M1#1' }] })
      await molding.wrapper.setProps({ engineeringPayload: source })
      expect(molding.wrapper.vm.getWholeQuoteDraft().payload).toMatchObject({ injection_lines: [{
        item: '独立补录壳', net_weight_g: 100, engineering_sync_disabled: true,
      }] })
      expect((molding.wrapper.vm.getWholeQuoteDraft().payload.injection_lines as unknown[])).toHaveLength(1)
    } finally {
      engineering.wrapper.unmount()
      molding.wrapper.unmount()
    }
  })

  it('projects renamed children and added molds into the molding draft without multiplying mold weight', async () => {
    const { wrapper } = setup('molding', { injection_lines: [{
      item: '外壳上/外壳下', mold_no: 'M01', material: 'ABS', grade: '750SW', net_weight_g: 485,
      sets: 1, target_output: 2000, machine_code: '18A', quantity: 2, remark: '啤机补录',
    }] })
    await wrapper.setProps({ engineeringPayload: { molds: [{
      mold_id: 'mold-one', mold_no: 'M01', item: '外壳上/外壳下', material_type: 'ABS', net_weight_g: 485,
      parts: [{ part_id: 'part-top', name: '外壳上', unit_net_weight_g: 200 }, { part_id: 'part-bottom', name: '外壳下', unit_net_weight_g: 285 }],
    }, { mold_id: 'mold-two', mold_no: 'M02', item: '新胶件', material_type: 'ABS', parts: [{ part_id: 'part-new', name: '新胶件' }] }] } })
    const lines = wrapper.vm.getWholeQuoteDraft().payload.injection_lines as Array<Record<string, unknown>>
    expect(lines).toHaveLength(2)
    expect(lines[0]).toMatchObject({ net_weight_g: 485, quantity: 2, target_output: 2000, remark: '啤机补录', cost_scope: 'whole_mold', engineering_parts: [{ name: '外壳上' }, { name: '外壳下' }] })
    expect(wrapper.text()).toContain('上方整模重量、料价及啤工只计一次')
    expect(wrapper.text()).toContain('新胶件')
    wrapper.unmount()
  })

  it('uploads a painting image into its row draft and preserves it across attachment refresh', async () => {
    const { wrapper, section, store } = setup('painting', { rows: [{ name: '透明盖', operations: {}, image_reference: '' }] })
    const upload = vi.spyOn(store, 'uploadAttachment').mockResolvedValue({ id: 'image-1', file_name: '透明盖.png' } as never)
    const input = wrapper.get('input[aria-label="喷油第 1 行添加图片"]')
    const file = new File(['image-bytes'], '透明盖.png', { type: 'image/png' })
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change'); await flushPromises()
    expect(upload).toHaveBeenCalledWith('feedback-quote', 'painting', file)
    expect(wrapper.vm.getWholeQuoteDraft().payload).toMatchObject({ rows: [{ name: '透明盖', image_attachment_ids: ['image-1'] }] })
    await wrapper.setProps({ section: { ...section, attachments: [{ id: 'image-1', fileName: '透明盖.png', contentType: 'image/png' } as never] } })
    expect(wrapper.find('.painting-row-images img').attributes('alt')).toBe('透明盖.png')
    await wrapper.get('[aria-label="移除喷油图片 透明盖.png"]').trigger('click')
    expect(wrapper.vm.getWholeQuoteDraft().payload).toMatchObject({ rows: [{ image_attachment_ids: [] }] })
    wrapper.unmount()
  })

  it('merges sidebar pricing into the same sales save snapshot without dropping department inputs', () => {
    const { wrapper } = setup('sales', { shipping: { markup_x: 1.20, misc_ratio: .02 }, remark: '保留业务资料' })
    const draft = wrapper.vm.getWholeQuoteDraft({
      markupTiers: [3000, 5000, 10000].map(moq => ({ moq, markup_x: moq === 10000 ? 1.12 : 1.20, include_in_output: true })),
      selectedMoq: 10000, activeMarkup: 1.12, miscRatio: .03,
    })
    expect(draft.payload).toMatchObject({ shipping: { markup_x: 1.12, selected_markup_moq: 10000, misc_ratio: .03, divisor: .97 } })
    expect(draft.localPayload).toMatchObject({ shipping: { markup_x: 1.20, misc_ratio: .02 } })
    wrapper.vm.acceptSavedPayload(draft.payload, draft.payload, 6, draft.localPayload)
    expect(wrapper.vm.hasUnsavedChanges()).toBe(false)
    expect(wrapper.vm.getWholeQuoteDraft().payload).toMatchObject({ shipping: { markup_x: 1.12, misc_ratio: .03 } })
    wrapper.unmount()
  })
  it.each([false, true])('saves Dickie additions on returned legacy quotes over HTTP (whole review: %s)', async wholeQuoteReview => {
    const cryptoSource = globalThis.crypto
    vi.stubGlobal('crypto', { getRandomValues: cryptoSource.getRandomValues.bind(cryptoSource) })
    const { wrapper, section, save } = setup('sales', {
      customer_quote_fields: { dickie: { client_name: '', product_rows: [] } },
    })
    try {
      await wrapper.setProps({
        quote: { ...wrapper.props('quote'), factoryId: 'huaxing', customer: 'Dickie', status: 'rejected' },
        section: { ...section, status: 'rejected' },
        wholeQuoteReview,
      })
      await wrapper.findAll('button').find(button => button.text() === '启用 Dickie 报客资料')!.trigger('click')
      await wrapper.get('[aria-label="Dickie 产品名称 English"]').setValue('Double-decker Bus')
      expect(wrapper.vm.hasUnsavedChanges()).toBe(true)
      await wrapper.vm.saveWholeQuoteDraft(false)
      expect(save).toHaveBeenCalledWith('feedback-quote', 'sales', 5, expect.objectContaining({
        customer_quote_fields: expect.objectContaining({ dickie: expect.objectContaining({
          mapping: expect.objectContaining({ version: 'dickie-v2', item_name: { zh: '', en: 'Double-decker Bus' } }),
        }) }),
      }), expect.anything(), false)
      expect(wrapper.vm.hasUnsavedChanges()).toBe(false)
    } finally {
      wrapper.unmount()
      vi.unstubAllGlobals()
    }
  })

  it.each(['cancel', 'failure'] as const)('keeps the unsaved form when import ends with %s', async outcome => {
    const { wrapper, save, store } = setup('engineering', { molds: [{ item: '原模具' }] })
    await wrapper.get('textarea[aria-label="模具名称"]').setValue('未保存模具')
    const before = wrapper.vm.getWholeQuoteDraft().payload
    vi.spyOn(store, 'previewImport').mockResolvedValue(moldPreview)
    const confirm = vi.spyOn(store, 'confirmImport').mockRejectedValue(new Error('导入失败，保留输入'))
    await chooseMoldFile(wrapper)
    if (outcome === 'cancel') await wrapper.get('[aria-label="关闭导入预览"]').trigger('click')
    else await wrapper.findAll('button').find(button => button.text() === '确认导入')!.trigger('click')
    await flushPromises()
    expect(wrapper.vm.getWholeQuoteDraft().payload).toEqual(before)
    expect(wrapper.vm.hasUnsavedChanges()).toBe(true)
    expect(save).not.toHaveBeenCalled()
    expect(confirm).toHaveBeenCalledTimes(outcome === 'cancel' ? 0 : 1)
    wrapper.unmount()
  })

  it('retains edits made while confirming an import and still accepts the imported molds', async () => {
    const { wrapper, store } = setup('engineering', { materials: [{ item: '螺丝', category: 'hardware', quantity: 2, unit_price_rmb: 1 }] })
    vi.spyOn(store, 'previewImport').mockResolvedValue(moldPreview)
    let complete!: (result: unknown) => void
    vi.spyOn(store, 'confirmImport').mockImplementation(() => new Promise(resolve => { complete = resolve }))
    await chooseMoldFile(wrapper)
    const submitted = wrapper.vm.getWholeQuoteDraft().payload
    await wrapper.findAll('button').find(button => button.text() === '确认导入')!.trigger('click')
    await wrapper.get('[aria-label="五金零件名称"]').setValue('请求期间修改')
    complete({ section: { revision: 6, payload: { ...submitted, molds: [{ item: '新模具' }] } } })
    await flushPromises()
    expect(wrapper.vm.getWholeQuoteDraft().payload).toMatchObject({ materials: [{ item: '请求期间修改' }], molds: [{ item: '新模具' }] })
    expect(wrapper.vm.hasUnsavedChanges()).toBe(true)
    wrapper.unmount()
  })

  it('adds an electronic quote on HTTP browsers without crypto.randomUUID', async () => {
    const cryptoSource = globalThis.crypto
    vi.stubGlobal('crypto', { getRandomValues: cryptoSource.getRandomValues.bind(cryptoSource) })
    const { wrapper } = setup('electronic', {})
    try {
      await wrapper.findAll('button').find((button) => button.text().includes('新增电子报价'))!.trigger('click')
      const groups = wrapper.vm.getWholeQuoteDraft().payload.quote_groups as Array<{ id: string }>
      expect(groups).toHaveLength(1)
      expect(groups[0]!.id).toMatch(/^electronic-[0-9a-f-]{36}$/)
    } finally {
      wrapper.unmount()
      vi.unstubAllGlobals()
    }
  })

  it('does not report automatic molding reference canonicalization as unsaved user input', async () => {
    const { wrapper } = setup('molding', { injection_lines: [{ item: '壳', material: 'ABS', grade: '750SW', machine_code: '18' }] })
    await flushPromises()
    expect(wrapper.vm.hasUnsavedChanges()).toBe(false)
    expect(wrapper.find('.dirty').exists()).toBe(false)
    expect(wrapper.vm.getWholeQuoteDraft().payload).toMatchObject({ injection_lines: [{ machine_code: '18A', machine_name: '180T' }] })
    wrapper.unmount()
  })

  it('marks deleted engineering sources while retaining all unsaved molding inputs', async () => {
    const surviving = { item: '主壳', engineering_source_key: 'mold-no:M01#1', engineering_synced_fields: ['item'] }
    const removed = { item: '已移除模具', engineering_source_key: 'source-row:22#1', engineering_synced_fields: ['item'] }
    const manual = { item: '手工行' }
    const { wrapper, section } = setup('molding', { injection_lines: [surviving, removed, manual] })
    const first = wrapper.findAll('.moldingInjectionTable tbody tr')[0]!
    const quantity = first.findAll('input[type="number"]').at(-1)!
    await quantity.setValue('3')
    expect(wrapper.vm.hasUnsavedChanges()).toBe(true)
    const before = wrapper.vm.getWholeQuoteDraft().payload.injection_lines as Record<string, unknown>[]
    await wrapper.setProps({ section: { ...section, revision: 6, payload: { injection_lines: [surviving, { ...removed, engineering_source_missing: true }, manual] } } })
    const after = wrapper.vm.getWholeQuoteDraft()
    expect(after.payload.injection_lines).toEqual([before[0], { ...before[1], engineering_source_missing: true }, before[2]])
    expect(wrapper.findAll('.moldingInjectionTable tbody tr[data-injection-index]')).toHaveLength(3)
    expect(wrapper.text()).toContain('工程源模具已移除')
    expect(wrapper.findAll('.moldingInjectionTable tbody tr')[0]!.findAll('input[type="number"]').at(-1)!.element).toBe(quantity.element)
    expect(after.revision).toBe(6)
    expect(wrapper.vm.hasUnsavedChanges()).toBe(true)
    expect(wrapper.text()).not.toContain('本页未保存输入已保留')
    wrapper.unmount()
  })

  it('acknowledges a saved missing-source warning without clearing retained inputs', async () => {
    const removed = { item: '待核对模具', engineering_source_key: 'source-row:23#1' }
    const { wrapper } = setup('molding', { injection_lines: [removed, { item: '手工行' }] })
    const submitted = wrapper.vm.getWholeQuoteDraft().payload
    wrapper.vm.acceptSavedPayload({ injection_lines: [{ ...removed, engineering_source_missing: true }, { item: '手工行' }] }, submitted, 6)
    await flushPromises()
    expect(wrapper.vm.getWholeQuoteDraft().payload.injection_lines).toMatchObject([{ ...removed, engineering_source_missing: true }, { item: '手工行' }])
    expect(wrapper.findAll('.moldingInjectionTable tbody tr[data-injection-index]')).toHaveLength(2)
    expect(wrapper.vm.hasUnsavedChanges()).toBe(false)
    wrapper.unmount()
  })

  it('keeps edits made during a molding save while applying missing-source warnings in its receipt', async () => {
    const { wrapper, save } = setup('molding', { injection_lines: [
      { item: '待核对模具', engineering_source_key: 'source-row:22#1' }, { item: '手工行' },
    ] })
    const submitted = wrapper.vm.getWholeQuoteDraft().payload
    let resolve!: (result: ApiInternalQuoteSection) => void
    save.mockReturnValueOnce(new Promise<ApiInternalQuoteSection>(done => { resolve = done }))
    const pending = wrapper.vm.saveWholeQuoteDraft(false)
    await wrapper.findAll('.moldingInjectionTable tbody tr')[1]!.get('textarea').setValue('保存期间修改')
    resolve({ revision: 6, payload: { ...submitted, injection_lines: [{ item: '待核对模具', engineering_source_key: 'source-row:22#1', engineering_source_missing: true }, { item: '手工行' }] } } as unknown as ApiInternalQuoteSection)
    await pending
    await flushPromises()
    expect(wrapper.vm.getWholeQuoteDraft().payload.injection_lines).toMatchObject([{ item: '待核对模具', engineering_source_missing: true }, { item: '保存期间修改' }])
    expect(wrapper.findAll('.moldingInjectionTable tbody tr[data-injection-index]')).toHaveLength(2)
    expect(wrapper.vm.hasUnsavedChanges()).toBe(true)
    wrapper.unmount()
  })

  it('edits the selected electronic quote without changing the other quote', async () => {
    const { wrapper } = setup('electronic', {
      quote_groups: [
        { id: 'first', name: '主板', components: [{ item: '第一组零件', quantity: 1, unit_price_rmb: 1, tax_rate_percent: 13, children: [] }], profit_rate_percent: 10 },
        { id: 'second', name: '遥控器', components: [{ item: '第二组零件', quantity: 1, unit_price_rmb: 2, tax_rate_percent: 13, children: [] }], bonding_rmb: 3, profit_rate_percent: 20 },
      ],
    })
    await flushPromises()
    await wrapper.get('.electronic-quote-group-controls select').setValue('second')
    await wrapper.get('input[aria-label="电子零件名称"]').setValue('已修改的第二组')
    const payload = wrapper.vm.getWholeQuoteDraft().payload as { quote_groups: Array<Record<string, unknown>> }
    expect(payload.quote_groups[0]).toMatchObject({ id: 'first', components: [{ item: '第一组零件' }], profit_rate_percent: 10 })
    expect(payload.quote_groups[1]).toMatchObject({ id: 'second', components: [{ item: '已修改的第二组' }], bonding_rmb: 3, profit_rate_percent: 20 })
    wrapper.unmount()
  })

  it('keeps an empty group wrapper after deleting the final electronic quote and recovers through import or a new quote', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const { wrapper, store } = setup('electronic', {
      quote_groups: [{ id: 'only', name: '唯一报价', components: [{ item: '零件', quantity: 1, unit_price_rmb: 1, tax_rate_percent: 13, children: [] }], profit_rate_percent: 10 }],
    })
    await flushPromises()
    await wrapper.get('.remove-electronic-group').trigger('click')
    expect(wrapper.vm.getWholeQuoteDraft().payload).toEqual({ quote_groups: [] })
    expect(wrapper.text()).toContain('暂无电子报价')
    const emptyPayload = wrapper.vm.getWholeQuoteDraft().payload
    wrapper.vm.acceptSavedPayload(emptyPayload, emptyPayload, 5)

    vi.spyOn(store, 'previewImport').mockResolvedValue({
      batch_id: 'electronic-batch', quote_id: 'feedback-quote', import_type: 'electronic', target_department: 'electronic',
      source_file_name: '电子报价单.xlsx', source_sha256: 'sha', source_size_bytes: 1, preview_schema_version: 'v1', target_revision: 5,
      sheet_name: '报价', header_row: 1, row_count: 2, payload_fragment: {}, diff_summary: { imported_rows: 2 }, warnings: [],
      status: 'previewed', created_by_name: '', created_at: '', confirm_mode: 'replace', confirmed_revision: 0, confirmed_by_name: '', confirmed_at: '',
    })
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [new File(['xlsx'], '电子报价单.xlsx')] })
    await input.trigger('change')
    await flushPromises()
    expect((wrapper.get('.electronic-import-target select').element as HTMLSelectElement).value).toBe('new')
    await wrapper.get('[aria-label="关闭导入预览"]').trigger('click')
    await wrapper.findAll('button').find((button) => button.text().includes('新增电子报价'))!.trigger('click')
    expect((wrapper.vm.getWholeQuoteDraft().payload as { quote_groups: unknown[] }).quote_groups).toHaveLength(1)
    wrapper.unmount()
  })

  it('retains a real name edit after an equivalent same-revision refresh', async () => {
    const { wrapper, section } = setup('engineering', { molds: [{ item: '粉色蝴蝶结前/后', parts: [{ name: '粉色蝴蝶结前' }, { name: '后' }] }] })
    const inputs = wrapper.findAll('textarea[aria-label="模具名称"]')
    await inputs[0]!.setValue('粉色蝴蝶结后')
    expect(wrapper.vm.hasUnsavedChanges()).toBe(true)
    await wrapper.setProps({ section: { ...section, payload: structuredClone(section.payload) } })
    expect((wrapper.findAll('textarea[aria-label="模具名称"]')[0]!.element as HTMLInputElement).value).toBe('粉色蝴蝶结后')
    expect(wrapper.vm.hasUnsavedChanges()).toBe(true)
    wrapper.unmount()
  })

  it('preserves child input identity when a preceding staged child is removed', async () => {
    const { wrapper } = setup('engineering', { molds: [{ item: '前/后', parts: [{ name: '前' }, { name: '后' }] }] })
    await wrapper.get('[aria-label="拆分第 1 行模具"]').trigger('click')
    await flushPromises()
    const second = wrapper.findAll('input[aria-label="模具子配件名称"]')[1]!.element
    await wrapper.findAll('.engineeringMoldParts tbody tr')[0]!.get('button').trigger('click')
    expect(wrapper.get('input[aria-label="模具子配件名称"]').element).toBe(second)
    wrapper.unmount()
  })

  it('requires a fresh preview only when the form changed after preview', async () => {
    const { wrapper } = setup('engineering', { molds: [{ parts: [{ name: '后' }] }] })
    const store = useInternalQuoteDeskStore()
    const preview = vi.spyOn(store, 'previewImport').mockResolvedValue(moldPreview)
    const confirm = vi.spyOn(store, 'confirmImport')
    await wrapper.get('textarea[aria-label="模具名称"]').setValue('手工修改')
    await chooseMoldFile(wrapper)
    expect(preview).toHaveBeenCalled()
    await wrapper.get('textarea[aria-label="模具名称"]').setValue('预览后再修改')
    await wrapper.findAll('button').find(button => button.text() === '确认导入')!.trigger('click')
    await flushPromises()
    expect(confirm).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('重新选择报价单预览后再确认')
    expect(wrapper.vm.hasUnsavedChanges()).toBe(true)
    wrapper.unmount()
  })

  it('keeps unsaved edits and the exit warning after a failed save', async () => {
    const { wrapper, save } = setup('engineering', { molds: [{ parts: [{ name: '后' }] }] })
    await wrapper.get('textarea[aria-label="模具名称"]').setValue('手工改名')
    save.mockRejectedValue(new Error('版本冲突'))
    await expect(wrapper.vm.saveWholeQuoteDraft()).rejects.toThrow('版本冲突')
    expect(wrapper.vm.hasUnsavedChanges()).toBe(true)
    expect((wrapper.get('textarea[aria-label="模具名称"]').element as HTMLInputElement).value).toBe('手工改名')
    wrapper.unmount()
  })

  it('acknowledges a no-op save and still warns for subsequent edits', async () => {
    const { wrapper } = setup('engineering', { molds: [{ parts: [{ name: '后' }] }] })
    await wrapper.get('textarea[aria-label="模具名称"]').setValue('手工改名')
    await wrapper.vm.saveWholeQuoteDraft(false)
    expect(wrapper.vm.hasUnsavedChanges()).toBe(false)
    const savedExit = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(savedExit)
    expect(savedExit.defaultPrevented).toBe(false)
    await wrapper.get('textarea[aria-label="模具名称"]').setValue('再次修改')
    const dirtyExit = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(dirtyExit)
    expect(dirtyExit.defaultPrevented).toBe(true)
    wrapper.unmount()
  })

  it('acknowledges a whole-product result even when no section prop changes', async () => {
    const { wrapper } = setup('engineering', { molds: [{ parts: [{ name: '后' }] }] })
    await wrapper.get('textarea[aria-label="模具名称"]').setValue('后件')
    const draft = wrapper.vm.getWholeQuoteDraft()
    wrapper.vm.acceptSavedPayload(draft.payload, draft.payload, 5)
    expect(wrapper.vm.hasUnsavedChanges()).toBe(false)
    expect(wrapper.vm.getWholeQuoteDraft().revision).toBe(5)
    wrapper.unmount()
  })

  it('does not acknowledge a later edit as saved while waiting for the response', async () => {
    const { wrapper, save } = setup('engineering', { molds: [{ parts: [{ name: '后' }] }] })
    await wrapper.get('textarea[aria-label="模具名称"]').setValue('第一次修改')
    const submitted = wrapper.vm.getWholeQuoteDraft().payload
    let resolve!: (result: ApiInternalQuoteSection) => void
    save.mockReturnValueOnce(new Promise<ApiInternalQuoteSection>((done) => { resolve = done }))
    const pending = wrapper.vm.saveWholeQuoteDraft(false)
    await wrapper.get('textarea[aria-label="模具名称"]').setValue('请求期间的新修改')
    resolve({ revision: 6, payload: submitted } as ApiInternalQuoteSection)
    await pending
    expect(wrapper.vm.hasUnsavedChanges()).toBe(true)
    expect((wrapper.get('textarea[aria-label="模具名称"]').element as HTMLInputElement).value).toBe('请求期间的新修改')
    wrapper.unmount()
  })

  it('preserves both a conflicting local draft and its old revision for optimistic locking', async () => {
    const { wrapper, section } = setup('engineering', { molds: [{ parts: [{ name: '后' }] }] })
    await wrapper.get('textarea[aria-label="模具名称"]').setValue('本地修改')
    await wrapper.setProps({ section: { ...section, revision: 6, payload: { molds: [{ parts: [{ name: '他人修改' }] }] } } })
    expect(wrapper.vm.getWholeQuoteDraft().revision).toBe(5)
    expect((wrapper.get('textarea[aria-label="模具名称"]').element as HTMLInputElement).value).toBe('本地修改')
    expect(wrapper.text()).toContain('本页未保存输入已保留')
    wrapper.unmount()
  })

  it('stages one mold with inherited counts, cancels without saving, then confirms only that mold', async () => {
    const { wrapper, save } = setup('engineering', { molds: [
      { item: '遥控器上壳/下壳', cavity: '4', quantity: 2, cycle_time_seconds: 30, material: 'legacy' },
      { item: '车轮', cavity: '8', quantity: 3 },
    ] })
    expect(wrapper.find('.engineeringMoldParts').exists()).toBe(false)
    const headers = wrapper.get('.engineeringMolds thead').findAll('th').map(cell => cell.text())
    for (const removed of ['模胚类型', '模具结构', '工艺', '材质', '周期 (秒)', '模具规格']) expect(headers).not.toContain(removed)
    const original = wrapper.vm.getWholeQuoteDraft().payload
    await wrapper.get('[aria-label="拆分第 1 行模具"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.engineering-mold-part-card')).toHaveLength(1)
    expect(wrapper.findAll('[aria-label="模具子配件出模数"]').map(input => (input.element as HTMLInputElement).value)).toEqual(['4', '4'])
    expect(wrapper.findAll('[aria-label="模具子配件套数"]').map(input => (input.element as HTMLInputElement).value)).toEqual(['2', '2'])
    expect(() => wrapper.vm.getWholeQuoteDraft()).toThrow('请先确认或取消')
    await wrapper.findAll('button').find(button => button.text() === '取消拆分')!.trigger('click')
    expect(save).not.toHaveBeenCalled()
    expect(wrapper.vm.getWholeQuoteDraft().payload).toEqual(original)
    expect(wrapper.vm.hasUnsavedChanges()).toBe(false)
    await wrapper.get('[aria-label="拆分第 1 行模具"]').trigger('click')
    await flushPromises()
    for (const input of wrapper.findAll('[aria-label="模具子配件净重"]')) await input.setValue('12')
    await wrapper.findAll('[aria-label="模具子配件套数"]')[0]!.setValue('5')
    await wrapper.findAll('button').find(button => button.text() === '确认拆分')!.trigger('click')
    await flushPromises()
    expect(save).toHaveBeenCalledTimes(1)
    expect(save.mock.calls[0]![3]).toMatchObject({ molds: [
      { cycle_time_seconds: 30, material: 'legacy', parts: [{ output_count: 4, quantity: 5, unit_net_weight_g: 12 }, { quantity: 2 }] },
      { parts: [] },
    ] })
    expect(wrapper.find('.mold-split-dialog').exists()).toBe(false)
    expect(wrapper.vm.hasUnsavedChanges()).toBe(false)
    await wrapper.get('[aria-label="拆分第 1 行模具"]').trigger('click')
    await flushPromises()
    expect((wrapper.findAll('[aria-label="模具子配件套数"]')[0]!.element as HTMLInputElement).value).toBe('5')
    wrapper.unmount()
  })

  it('validates every mold before a batch save and keeps staged input after failure', async () => {
    const { wrapper, save } = setup('engineering', { molds: [
      { item: '上/下', cavity: '4', quantity: 2 }, { item: '车轮', cavity: '8', quantity: 3 },
    ] })
    const original = wrapper.vm.getWholeQuoteDraft().payload
    await wrapper.findAll('button').find(button => button.text() === '全部拆分')!.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.engineering-mold-part-card')).toHaveLength(2)
    const confirm = () => wrapper.findAll('button').find(button => button.text() === '确认拆分')!.trigger('click')
    await wrapper.findAll('[aria-label="模具子配件名称"]')[0]!.setValue('')
    await confirm()
    expect(save).not.toHaveBeenCalled()
    expect(wrapper.get('.mold-split-error').text()).toContain('名称')
    await wrapper.findAll('[aria-label="模具子配件名称"]')[0]!.setValue('上')
    for (const input of wrapper.findAll('[aria-label="模具子配件净重"]')) await input.setValue('10')
    save.mockRejectedValueOnce(new Error('版本冲突'))
    await confirm()
    await flushPromises()
    expect(wrapper.get('.mold-split-error').text()).toContain('版本冲突')
    expect((wrapper.findAll('[aria-label="模具子配件净重"]')[0]!.element as HTMLInputElement).value).toBe('10')
    await wrapper.findAll('button').find(button => button.text() === '取消拆分')!.trigger('click')
    expect(wrapper.vm.getWholeQuoteDraft().payload).toEqual(original)
    await wrapper.findAll('button').find(button => button.text() === '全部拆分')!.trigger('click')
    await flushPromises()
    for (const input of wrapper.findAll('[aria-label="模具子配件净重"]')) await input.setValue('10')
    await confirm()
    await flushPromises()
    expect(save.mock.calls[1]![3]).toMatchObject({ molds: [
      { parts: [{ output_count: 4, quantity: 2 }, { output_count: 4, quantity: 2 }] },
      { parts: [{ output_count: 8, quantity: 3 }] },
    ] })
    expect(wrapper.vm.hasUnsavedChanges()).toBe(false)
    wrapper.unmount()
  })

  it('re-splits the current slash name without discarding matched IDs or manual child input', async () => {
    const { wrapper, save } = setup('engineering', { molds: [{
      item: '上壳/下壳', cavity: '4', quantity: 2, net_weight_g: 100,
      parts: [{ id: 'top', name: '上壳', unit_net_weight_g: 40, output_count: 4, quantity: 2 },
        { id: 'manual', name: '手工胶件', unit_net_weight_g: 7, output_count: 3, quantity: 1 }],
    }] })
    const original = wrapper.vm.getWholeQuoteDraft().payload
    await wrapper.get('[aria-label="拆分第 1 行模具"]').trigger('click')
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '按当前名称重新拆分')!.trigger('click')
    expect(wrapper.findAll('[aria-label="模具子配件名称"]').map(input => (input.element as HTMLInputElement).value)).toEqual(['上壳', '下壳', '手工胶件'])
    expect(wrapper.findAll('[aria-label="模具子配件净重"]').map(input => (input.element as HTMLInputElement).value)).toEqual(['40', '0', '7'])
    expect(wrapper.text()).toContain('保留 1 项原有手工胶件')
    expect(save).not.toHaveBeenCalled()
    await wrapper.findAll('button').find(button => button.text() === '取消拆分')!.trigger('click')
    expect(wrapper.vm.getWholeQuoteDraft().payload).toEqual(original)
    await wrapper.get('[aria-label="拆分第 1 行模具"]').trigger('click')
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '按当前名称重新拆分')!.trigger('click')
    await wrapper.findAll('button').find(button => button.text() === '确认拆分')!.trigger('click')
    await flushPromises()
    expect(save.mock.calls[0]![3]).toMatchObject({ molds: [{ net_weight_g: 100, parts: [
      { id: 'top', part_id: 'top', name: '上壳', unit_net_weight_g: 40 },
      { name: '下壳', unit_net_weight_g: 0, output_count: 4, quantity: 2 },
      { id: 'manual', part_id: 'manual', name: '手工胶件', unit_net_weight_g: 7 },
    ] }] })
    expect(wrapper.vm.hasUnsavedChanges()).toBe(false)
    wrapper.unmount()
  })

  it('clears a staged split when the editor switches to another quote', async () => {
    const { wrapper } = setup('engineering', { molds: [{ item: '上/下', cavity: '4', quantity: 2 }] })
    await wrapper.get('[aria-label="拆分第 1 行模具"]').trigger('click')
    await flushPromises()
    expect(wrapper.vm.hasUnsavedChanges()).toBe(true)
    await wrapper.setProps({ quote: { ...wrapper.props('quote'), id: 'another-quote' } })
    await flushPromises()
    expect(wrapper.find('.mold-split-dialog').exists()).toBe(false)
    expect(wrapper.vm.hasUnsavedChanges()).toBe(false)
    expect(wrapper.vm.getWholeQuoteDraft().payload).toMatchObject({ molds: [{ parts: [] }] })
    wrapper.unmount()
  })

  it('hides the injection cycle column while retaining its saved value', () => {
    const { wrapper } = setup('molding', { injection_lines: [{ item: '壳', cycle_time_seconds: 28 }] })
    expect(wrapper.get('.moldingInjectionTable thead').text()).not.toContain('周期')
    expect(wrapper.vm.getWholeQuoteDraft().payload).toMatchObject({ injection_lines: [{ cycle_time_seconds: 28 }] })
    wrapper.unmount()
  })
})

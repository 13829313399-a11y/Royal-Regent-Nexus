import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import type { ApiInternalQuoteSection } from '@/api/internalQuote'
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
    global: { plugins: [pinia], stubs: { InternalQuoteAttachmentPreview: true } }, attachTo: document.body,
  })
  return { wrapper, save, section, store }
}

afterEach(() => { vi.restoreAllMocks(); document.body.innerHTML = '' })

describe('internal quote feedback regressions', () => {
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
    const inputs = wrapper.findAll('input[aria-label="模具子配件名称"]')
    await inputs[1]!.setValue('粉色蝴蝶结后')
    expect(wrapper.vm.hasUnsavedChanges()).toBe(true)
    await wrapper.setProps({ section: { ...section, payload: structuredClone(section.payload) } })
    expect((wrapper.findAll('input[aria-label="模具子配件名称"]')[1]!.element as HTMLInputElement).value).toBe('粉色蝴蝶结后')
    expect(wrapper.vm.hasUnsavedChanges()).toBe(true)
    wrapper.unmount()
  })

  it('preserves the second name input DOM identity when the preceding child is removed', async () => {
    const { wrapper } = setup('engineering', { molds: [{ item: '前/后', parts: [{ name: '前' }, { name: '后' }] }] })
    const second = wrapper.findAll('input[aria-label="模具子配件名称"]')[1]!.element as HTMLInputElement
    second.focus()
    await wrapper.findAll('.engineeringMoldParts tbody tr')[0]!.get('button').trigger('click')
    expect(wrapper.get('input[aria-label="模具子配件名称"]').element).toBe(second)
    expect(document.activeElement).toBe(second)
    wrapper.unmount()
  })

  it('blocks a structured import before uploading when there are unsaved edits', async () => {
    const { wrapper } = setup('engineering', { molds: [{ parts: [{ name: '后' }] }] })
    const store = useInternalQuoteDeskStore()
    const preview = vi.spyOn(store, 'previewImport')
    await wrapper.get('input[aria-label="模具子配件名称"]').setValue('手工修改')
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [new File(['xlsx'], '报价.xlsx')] })
    await input.trigger('change')
    await flushPromises()
    expect(preview).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请先保存草稿，再重新选择报价单导入')
    expect(wrapper.vm.hasUnsavedChanges()).toBe(true)
    wrapper.unmount()
  })

  it('keeps unsaved edits and the exit warning after a failed save', async () => {
    const { wrapper, save } = setup('engineering', { molds: [{ parts: [{ name: '后' }] }] })
    await wrapper.get('input[aria-label="模具子配件名称"]').setValue('手工改名')
    save.mockRejectedValue(new Error('版本冲突'))
    await expect(wrapper.vm.saveWholeQuoteDraft()).rejects.toThrow('版本冲突')
    expect(wrapper.vm.hasUnsavedChanges()).toBe(true)
    expect((wrapper.get('input[aria-label="模具子配件名称"]').element as HTMLInputElement).value).toBe('手工改名')
    wrapper.unmount()
  })

  it('acknowledges a no-op save and still warns for subsequent edits', async () => {
    const { wrapper } = setup('engineering', { molds: [{ parts: [{ name: '后' }] }] })
    await wrapper.get('input[aria-label="模具子配件名称"]').setValue('手工改名')
    await wrapper.vm.saveWholeQuoteDraft(false)
    expect(wrapper.vm.hasUnsavedChanges()).toBe(false)
    const savedExit = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(savedExit)
    expect(savedExit.defaultPrevented).toBe(false)
    await wrapper.get('input[aria-label="模具子配件名称"]').setValue('再次修改')
    const dirtyExit = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(dirtyExit)
    expect(dirtyExit.defaultPrevented).toBe(true)
    wrapper.unmount()
  })

  it('acknowledges a whole-product result even when no section prop changes', async () => {
    const { wrapper } = setup('engineering', { molds: [{ parts: [{ name: '后' }] }] })
    await wrapper.get('input[aria-label="模具子配件名称"]').setValue('后件')
    const draft = wrapper.vm.getWholeQuoteDraft()
    wrapper.vm.acceptSavedPayload(draft.payload, draft.payload, 5)
    expect(wrapper.vm.hasUnsavedChanges()).toBe(false)
    expect(wrapper.vm.getWholeQuoteDraft().revision).toBe(5)
    wrapper.unmount()
  })

  it('does not acknowledge a later edit as saved while waiting for the response', async () => {
    const { wrapper, save } = setup('engineering', { molds: [{ parts: [{ name: '后' }] }] })
    await wrapper.get('input[aria-label="模具子配件名称"]').setValue('第一次修改')
    const submitted = wrapper.vm.getWholeQuoteDraft().payload
    let resolve!: (result: ApiInternalQuoteSection) => void
    save.mockReturnValueOnce(new Promise<ApiInternalQuoteSection>((done) => { resolve = done }))
    const pending = wrapper.vm.saveWholeQuoteDraft(false)
    await wrapper.get('input[aria-label="模具子配件名称"]').setValue('请求期间的新修改')
    resolve({ revision: 6, payload: submitted } as ApiInternalQuoteSection)
    await pending
    expect(wrapper.vm.hasUnsavedChanges()).toBe(true)
    expect((wrapper.get('input[aria-label="模具子配件名称"]').element as HTMLInputElement).value).toBe('请求期间的新修改')
    wrapper.unmount()
  })

  it('preserves both a conflicting local draft and its old revision for optimistic locking', async () => {
    const { wrapper, section } = setup('engineering', { molds: [{ parts: [{ name: '后' }] }] })
    await wrapper.get('input[aria-label="模具子配件名称"]').setValue('本地修改')
    await wrapper.setProps({ section: { ...section, revision: 6, payload: { molds: [{ parts: [{ name: '他人修改' }] }] } } })
    expect(wrapper.vm.getWholeQuoteDraft().revision).toBe(5)
    expect((wrapper.get('input[aria-label="模具子配件名称"]').element as HTMLInputElement).value).toBe('本地修改')
    expect(wrapper.text()).toContain('本页未保存输入已保留')
    wrapper.unmount()
  })

  it('previews resplitting, preserves prices and unmatched manual rows, and supports cancellation', async () => {
    const { wrapper } = setup('engineering', { molds: [{ item: '粉色蝴蝶结前/后', parts: [
      { name: '粉色蝴蝶结前', process_unit_price_hkd: 2, unit_net_weight_g: 10 },
      { name: '后', process_unit_price_hkd: 3, unit_net_weight_g: 15 },
      { name: '手工附件', process_unit_price_hkd: 4 },
    ] }] })
    const split = wrapper.findAll('button').find((button) => button.text() === '按名称拆分')!
    await split.trigger('click')
    const panel = wrapper.get('[aria-label="配件拆分预览"]')
    expect(panel.text()).toContain('原行无法匹配')
    expect(wrapper.vm.hasUnsavedChanges()).toBe(false)
    await panel.findAll('button').find((button) => button.text() === '取消拆分')!.trigger('click')
    expect(wrapper.find('[aria-label="配件拆分预览"]').exists()).toBe(false)
    await split.trigger('click')
    await wrapper.get('[aria-label="配件拆分预览"]').findAll('button').find((button) => button.text() === '确认拆分并保留数据')!.trigger('click')
    const names = wrapper.findAll('input[aria-label="模具子配件名称"]').map((input) => (input.element as HTMLInputElement).value)
    expect(names).toEqual(['粉色蝴蝶结前', '粉色蝴蝶结后', '手工附件'])
    expect(wrapper.find('input[aria-label="模具子配件加工内容"]').exists()).toBe(false)
    expect(wrapper.find('input[aria-label="模具子配件加工总单价 HKD"]').exists()).toBe(false)
    expect(wrapper.vm.getWholeQuoteDraft().payload).toMatchObject({ molds: [{ parts: [
      { process_unit_price_hkd: 2 },
      { process_unit_price_hkd: 3 },
      { process_unit_price_hkd: 4 },
    ] }] })
    expect(wrapper.vm.hasUnsavedChanges()).toBe(true)
    wrapper.unmount()
  })
})

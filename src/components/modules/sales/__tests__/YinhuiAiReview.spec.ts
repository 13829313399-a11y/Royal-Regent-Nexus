import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import YinhuiAiReview from '../YinhuiAiReview.vue'
import { createYinhuiDraft } from '@/lib/customerPriceConverters/yinhuiDraft'
import { draftSource } from '@/lib/__tests__/fixtures/yinhuiDraftSource'
import { createXlsxWorkbook, parseXlsxWorkbook } from '@/lib/customerPriceConverters/xlsxLite'
import { getQuoteRecognitionStatus, recognizeQuoteFields } from '@/api/quoteRecognition'
import type { RecognitionResponse } from '@/lib/customerPriceConverters/yinhuiRecognition'
vi.mock('@/api/quoteRecognition', () => ({ getQuoteRecognitionStatus: vi.fn(), recognizeQuoteFields: vi.fn() }))
const makeDraft = () => reactive(createYinhuiDraft(draftSource(false), '银辉81209.xlsx'))
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(getQuoteRecognitionStatus).mockResolvedValue({ available: true, message: '' })
  vi.mocked(recognizeQuoteFields).mockImplementation(async tasks => ({ engine: 'qwen', model: 'test', items: tasks.map(t => ({ task_id: t.id, choice_id: t.choices[0]!.id, reason: '名称对应' })) }))
})
describe('Silverlit AI review', () => {
  it('keeps a missing price pending until the user explicitly adopts an included-cost suggestion', async () => {
    const sheets = parseXlsxWorkbook(draftSource(false)).sheets
    sheets[0]!.rows[17]![1] = '包装'
    sheets[0]!.rows[17]![2] = '白咭由彩托搭'
    sheets[0]!.rows[17]![3] = null
    sheets[0]!.rows[17]![4] = 0
    const bytes = createXlsxWorkbook(sheets)
    const draft = reactive(createYinhuiDraft(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer, '银辉81209.xlsx'))
    vi.mocked(recognizeQuoteFields).mockImplementation(async tasks => ({ engine: 'qwen', model: 'test', items: tasks.map(t => ({ task_id: t.id, choice_id: t.kind === 'missing_amount' ? 'included' : null, reason: '原文注明由彩托搭，请确认费用已包含' })) }))
    const wrapper = mount(YinhuiAiReview, { props: { draft } })
    await wrapper.get('[data-testid="yinhui-ai-recognize"]').trigger('click')
    await flushPromises()
    expect(draft.result.quoteData.packagingRows[0]!.pricePending).toBe(true)
    expect(draft.overrides).toEqual([])
    expect(wrapper.text()).toContain('明细!C18')
    await wrapper.get('[data-testid="yinhui-ai-apply"]').trigger('click')
    const updated = wrapper.emitted('update:draft')![0]![0] as typeof draft
    expect(updated.overrides).toEqual([{ sheet: '明细', cell: 'D18', value: 0 }])
    expect(updated.result.quoteData.packagingRows[0]).toMatchObject({ amountHkd: 0, sourceAmountWasBlank: true })
    expect(updated.result.quoteData.packagingRows[0]!.pricePending).toBeUndefined()
    expect(wrapper.emitted('invalidate')).toHaveLength(1)
  })
  it('requires explicit application and invalidates confirmation without changing costs', async () => {
    const draft = makeDraft()
    const wrapper = mount(YinhuiAiReview, { props: { draft } })
    expect(getQuoteRecognitionStatus).not.toHaveBeenCalled()
    await wrapper.get('[data-testid="yinhui-ai-recognize"]').trigger('click')
    await flushPromises()
    expect(draft.result.quoteData.tools[0]!.moldNo).toBe('')
    expect(wrapper.text()).toContain('TOOL PLAN!C48')
    const labor = draft.result.quoteData.tools[0]!.laborHkd
    await wrapper.get('[data-testid="yinhui-ai-apply"]').trigger('click')
    expect(draft.result.quoteData.tools[0]!.moldNo).toBe('NA123')
    expect(draft.result.quoteData.tools[0]!.laborHkd).toBe(labor)
    expect(wrapper.emitted('invalidate')).toHaveLength(1)
    expect(wrapper.get('[data-testid="yinhui-ai-apply"]').attributes('disabled')).toBeDefined()
  })
  it.each(['replacement', 'manual', 'disabled', 'unmount'])('discards late results after %s', async change => {
    const draft = makeDraft()
    let finish!: (v: RecognitionResponse) => void
    vi.mocked(recognizeQuoteFields).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const wrapper = mount(YinhuiAiReview, { props: { draft } })
    await wrapper.get('[data-testid="yinhui-ai-recognize"]').trigger('click')
    await flushPromises()
    const [tasks, signal] = vi.mocked(recognizeQuoteFields).mock.calls[0]!
    if (change === 'replacement') await wrapper.setProps({ draft: makeDraft() })
    if (change === 'manual') draft.result.quoteData.tools[0]!.moldNo = 'MANUAL'
    if (change === 'disabled') await wrapper.setProps({ disabled: true })
    if (change === 'unmount') wrapper.unmount()
    await flushPromises()
    finish({ engine: 'qwen', model: 'test', items: tasks.map(t => ({ task_id: t.id, choice_id: t.choices[0]!.id, reason: '迟到结果' })) })
    await flushPromises()
    expect(signal!.aborted).toBe(true)
    expect(wrapper.find('[data-testid="yinhui-ai-apply"]').exists()).toBe(false)
    expect(draft.result.quoteData.tools[0]!.moldNo).toBe(change === 'manual' ? 'MANUAL' : '')
  })
  it('supports manual work while offline and never invokes an unconfigured model', async () => {
    vi.mocked(getQuoteRecognitionStatus).mockResolvedValue({ available: false, message: 'AI 识别尚未启用' })
    const wrapper = mount(YinhuiAiReview, { props: { draft: makeDraft() } })
    await wrapper.get('[data-testid="yinhui-ai-recognize"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('尚未启用')
    expect(recognizeQuoteFields).not.toHaveBeenCalled()
    expect(wrapper.emitted('update:draft')).toBeUndefined()
  })
  it('keeps an uncertain result unapplied', async () => {
    vi.mocked(recognizeQuoteFields).mockImplementation(async tasks => ({ engine: 'qwen', model: 'test', items: tasks.map(t => ({ task_id: t.id, choice_id: null, reason: '前后盖有歧义' })) }))
    const wrapper = mount(YinhuiAiReview, { props: { draft: makeDraft() } })
    await wrapper.get('[data-testid="yinhui-ai-recognize"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('前后盖有歧义')
    expect(wrapper.find('[data-testid="yinhui-ai-apply"]').exists()).toBe(false)
  })
})

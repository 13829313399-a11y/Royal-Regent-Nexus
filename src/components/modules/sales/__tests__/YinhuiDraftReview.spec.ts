import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import YinhuiDraftReview from '../YinhuiDraftReview.vue'
import YinhuiQuoteReview from '../YinhuiQuoteReview.vue'
import { createYinhuiDraft, type YinhuiDraft } from '@/lib/customerPriceConverters/yinhuiDraft'
import { draftSource } from '@/lib/__tests__/fixtures/yinhuiDraftSource'
vi.mock('@/api/quoteTranslation', () => ({ translateQuoteDescriptions: vi.fn() }))

describe('Silverlit draft controls', () => {
  it('shows all source errors, applies corrections and allows saving the rebuilt draft', async () => {
    const draft = createYinhuiDraft(draftSource(), '银辉81209.xlsx')
    const wrapper = mount(YinhuiDraftReview, { props: { draft } })
    expect(wrapper.text()).toContain('3 项原表问题')
    await wrapper.get('input[aria-label="补正 明细!L19"]').setValue('5K')
    await wrapper.get('input[aria-label="补正 明细!D18"]').setValue('1')
    await wrapper.get('input[aria-label="补正 明细!E19"]').setValue('2.2')
    expect(wrapper.get('[data-testid="yinhui-save-draft"]').attributes('disabled')).toBeDefined()
    expect(wrapper.emitted('invalidate')).toHaveLength(3)
    await wrapper.get('[data-testid="yinhui-apply-corrections"]').trigger('click')
    const rebuilt = wrapper.emitted('update:draft')![0]![0] as YinhuiDraft
    expect(rebuilt.result.quoteData.importIssues).toHaveLength(0)
    await wrapper.setProps({ draft: rebuilt })
    await wrapper.get('[data-testid="yinhui-save-draft"]').trigger('click')
    expect(wrapper.emitted('save')).toHaveLength(1)
  })
  it('selects source identifiers without changing costs and invalidates export confirmation', async () => {
    const draft = createYinhuiDraft(draftSource(false), '银辉81209.xlsx')
    const wrapper = mount(YinhuiDraftReview, { props: { draft } })
    const before = draft.result.quoteData.tools[0]!.laborHkd
    await wrapper.get('select[aria-label="模具对应 1"]').setValue('TOOL PLAN!48')
    expect(draft.result.quoteData.tools[0]!.moldNo).toBe('NA123')
    expect(draft.result.quoteData.tools[0]!.laborHkd).toBe(before)
    expect(wrapper.emitted('invalidate')).toHaveLength(1)
    await wrapper.setProps({ disabled: true })
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="yinhui-save-draft"]').attributes('disabled')).toBeDefined()
  })
  it('lists every output issue and completing MOQ never bypasses missing costs', async () => {
    const draft = createYinhuiDraft(draftSource(), '银辉81209.xlsx')
    const wrapper = mount(YinhuiQuoteReview, { props: { result: draft.result, confirmed: false } })
    await flushPromises()
    expect(wrapper.get('[data-testid="yinhui-export-issues"]').text()).toContain('明细!D18')
    expect(wrapper.get('[data-testid="yinhui-export-issues"]').text()).toContain('明细!D19')
    await wrapper.get('[data-testid="yinhui-moq"]').setValue('5K')
    expect(draft.result.quoteData.moq).toBe(5000)
    expect(wrapper.get('[data-testid="yinhui-confirm"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('草稿待补正')
  })
})

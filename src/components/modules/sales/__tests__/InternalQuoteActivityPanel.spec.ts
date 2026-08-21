import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import InternalQuoteActivityPanel from '@/components/modules/sales/internal-quote/InternalQuoteActivityPanel.vue'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import type { InternalQuote } from '@/types/internalQuoteDesk'

function quote(): InternalQuote {
  return {
    id: 'quote-fx-1',
    fxRmbHkd: 0.85,
    fxHkdUsd: 7.8,
    fxRmbUsd: 7.75,
    factoryPriceHkd: 100,
    quantity: 10000,
    targetCustomerPrice: '无',
    formulaVersion: 'rr2-2026-v1',
    referenceSnapshotId: 'IQREF-1',
    activities: [],
    comments: [],
    viewRecords: [],
  } as InternalQuote
}

describe('InternalQuoteActivityPanel reference FX editor', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('lets an authorized business user edit and emits normalized quote-scoped FX values', async () => {
    const wrapper = mount(InternalQuoteActivityPanel, {
      props: { quote: quote(), readOnly: true, canEditFx: true },
    })

    await wrapper.get('[data-testid="edit-reference-fx"]').trigger('click')
    expect(wrapper.get<HTMLInputElement>('[data-testid="fx-rmb-hkd"]').element.value).toBe('0.85')
    expect(wrapper.get<HTMLInputElement>('[data-testid="fx-hkd-usd"]').element.value).toBe('7.80')
    expect(wrapper.get('[data-testid="fx-rmb-hkd"]').attributes('step')).toBe('0.01')
    await wrapper.get('[data-testid="fx-rmb-hkd"]').setValue('0.9')
    await wrapper.get('[data-testid="fx-hkd-usd"]').setValue('7.9')
    await wrapper.get('[data-testid="save-reference-fx"]').trigger('click')

    expect(wrapper.emitted('updateFx')).toEqual([[{ rmbHkd: '0.90', hkdUsd: '7.90' }]])
  })

  it('hides editing from read-only users and rejects non-positive rates', async () => {
    const readOnly = mount(InternalQuoteActivityPanel, { props: { quote: quote(), readOnly: true } })
    expect(readOnly.find('[data-testid="edit-reference-fx"]').exists()).toBe(false)

    const editable = mount(InternalQuoteActivityPanel, { props: { quote: quote(), canEditFx: true } })
    await editable.get('[data-testid="edit-reference-fx"]').trigger('click')
    await editable.get('[data-testid="fx-rmb-hkd"]').setValue('0')
    expect(editable.text()).toContain('RMB→HKD汇率必须大于 0')
    expect(editable.get('[data-testid="save-reference-fx"]').attributes('disabled')).toBeDefined()
    await editable.get('[data-testid="fx-rmb-hkd"]').setValue('0.851')
    expect(editable.text()).toContain('RMB→HKD汇率最多保留 2 位小数')
  })

  it('shows live quote price, editable markup, saved cost baseline, and proximity color depth', async () => {
    const store = useInternalQuoteDeskStore()
    store.livePreviewQuoteId = 'quote-fx-1'
    store.livePreviewSectionCode = 'engineering'
    store.liveCostPreview = {
      quote_id: 'quote-fx-1',
      section_code: 'engineering',
      section_revision: 2,
      calculation_status: 'valid',
      calculation: { status: 'valid', totals: { total_hkd: '117.0000' } },
      warnings: [],
      saved_factory_price_hkd: '100.0000',
      preview_factory_price_hkd: '117.0000',
      delta_hkd: '17.0000',
      components_hkd: { hardware_hkd: '117.0000' },
      formula_version: 'rr2-2026-v1',
      reference_snapshot_id: 'IQREF-1',
      generated_at: '2026-07-19 12:00:00',
    }
    const liveQuote = quote()
    liveQuote.targetCustomerPrice = 'USD 20'

    const wrapper = mount(InternalQuoteActivityPanel, { props: { quote: liveQuote, canEditMarkup: true } })

    expect(wrapper.get('[data-testid="live-quote-hkd"]').text()).toBe('HKD 140.40')
    expect(wrapper.get('[data-testid="live-cost-hkd"]').text()).toBe('HKD 117.00')
    expect(wrapper.get<HTMLInputElement>('[data-testid="live-quote-markup-moq-0"]').element.value).toBe('3000')
    expect(wrapper.get<HTMLInputElement>('[data-testid="live-quote-markup-moq-1"]').element.value).toBe('5000')
    expect(wrapper.get<HTMLInputElement>('[data-testid="live-quote-markup-moq-2"]').element.value).toBe('10000')
    expect(wrapper.get<HTMLInputElement>('[data-testid="live-quote-markup-2"]').element.value).toBe('1.20')
    expect(wrapper.get('.quote-markup-tier-row.active').text()).toContain('本单采用')
    expect(wrapper.get<HTMLInputElement>('[data-testid="live-quote-misc"]').element.value).toBe('2.00')
    expect(wrapper.get('[data-testid="live-quote-settlement"]').text()).toBe('0.9800')
    expect(wrapper.text()).toContain('实时试算 · 未保存')
    expect(wrapper.text()).toContain('RMB 119.34')
    expect(wrapper.text()).toContain('USD 18.00')
    expect(wrapper.get('[data-testid="target-price-gap"]').text()).toContain('目标余量 USD 2.00')
    expect(wrapper.text()).toContain('已保存成本 HKD 100.00 · 成本变化 +17.00')

    await wrapper.get('[data-testid="live-quote-markup-2"]').setValue('1.33')
    expect(wrapper.get('[data-testid="live-quote-hkd"]').text()).toBe('HKD 155.61')
    expect(wrapper.get('[data-testid="target-price-gap"]').text()).toContain('目标余量 USD 0.05')
    expect(wrapper.get('.quote-live-cost').classes()).toContain('proximity-4')

    await wrapper.get('[data-testid="live-quote-markup-moq-2"]').setValue('12000')
    expect(wrapper.get('[data-testid="live-quote-hkd"]').text()).toBe('HKD 155.61')
    expect(wrapper.findAll('.quote-markup-tier-row')[2]!.classes()).toContain('active')
    await wrapper.get('[data-testid="select-quote-markup-tier-1"]').trigger('click')
    expect(wrapper.get('[data-testid="live-quote-hkd"]').text()).toBe('HKD 140.40')
    expect(wrapper.findAll('.quote-markup-tier-row')[1]!.classes()).toContain('active')
    await wrapper.get('[data-testid="live-quote-markup-1"]').setValue('1.50')
    expect(wrapper.get('[data-testid="target-price-gap"]').text()).toContain('已超目标 USD 2.50')
    expect(wrapper.get('.quote-live-cost').classes()).toContain('over')
    expect(wrapper.text()).toContain('跟客可主动选择本单采用的 MOQ 档')
  })

  it('saves normalized markup and misc ratio together for authorized users', async () => {
    const wrapper = mount(InternalQuoteActivityPanel, {
      props: { quote: quote(), readOnly: true, canEditMarkup: true },
    })
    const saveButton = wrapper.get('[data-testid="save-quote-markup"]')
    expect(saveButton.attributes('disabled')).toBeDefined()

    await wrapper.get('[data-testid="select-quote-markup-tier-0"]').trigger('click')
    await wrapper.get('[data-testid="output-quote-markup-tier-1"]').setValue(false)
    await wrapper.get('[data-testid="live-quote-markup-0"]').setValue('1.15')
    await wrapper.get('[data-testid="live-quote-misc"]').setValue('3.5')
    expect(wrapper.get('[data-testid="live-quote-settlement"]').text()).toBe('0.9650')
    expect(saveButton.attributes('disabled')).toBeUndefined()
    await saveButton.trigger('click')

    expect(wrapper.emitted('updateMarkup')).toEqual([[
      {
        markupTiers: [
          { moq: '3000', markup: '1.15', includeInOutput: true },
          { moq: '5000', markup: '1.20', includeInOutput: false },
          { moq: '10000', markup: '1.20', includeInOutput: true },
        ],
        selectedMoq: '3000',
        miscRatio: '0.0350',
      },
    ]])
  })

  it('validates markup precision, explains locked sales states, and hides persistence from viewers', async () => {
    const wrapper = mount(InternalQuoteActivityPanel, {
      props: { quote: quote(), canEditMarkup: true },
    })
    await wrapper.get('[data-testid="live-quote-markup-2"]').setValue('1.155')
    expect(wrapper.text()).toContain('码数最多保留 2 位小数')
    expect(wrapper.get('[data-testid="save-quote-markup"]').attributes('disabled')).toBeDefined()

    await wrapper.get('[data-testid="live-quote-markup-2"]').setValue('1.20')
    await wrapper.get('[data-testid="live-quote-misc"]').setValue('2.555')
    expect(wrapper.text()).toContain('杂项率最多保留 2 位小数')
    expect(wrapper.get('[data-testid="save-quote-markup"]').attributes('disabled')).toBeDefined()

    await wrapper.get('[data-testid="live-quote-misc"]').setValue('101')
    expect(wrapper.text()).toContain('杂项率必须大于等于 0% 且小于 100%')
    expect(wrapper.get('[data-testid="live-quote-settlement"]').text()).toBe('—')

    await wrapper.get('[data-testid="live-quote-misc"]').setValue('100')
    expect(wrapper.text()).toContain('杂项率必须大于等于 0% 且小于 100%')
    expect(wrapper.get('[data-testid="save-quote-markup"]').attributes('disabled')).toBeDefined()

    await wrapper.get('[data-testid="live-quote-misc"]').setValue('2.00')
    await wrapper.setProps({ markupBlockedReason: '请先重开业务部分段。' })
    await wrapper.get('[data-testid="live-quote-markup-2"]').setValue('1.15')
    expect(wrapper.text()).toContain('请先重开业务部分段')
    expect(wrapper.get('[data-testid="save-quote-markup"]').attributes('disabled')).toBeDefined()

    const viewer = mount(InternalQuoteActivityPanel, { props: { quote: quote() } })
    expect(viewer.find('[data-testid="save-quote-markup"]').exists()).toBe(false)
    for (const testId of ['live-quote-markup-moq-0', 'live-quote-markup-0', 'select-quote-markup-tier-0', 'live-quote-misc']) {
      expect(viewer.get(`[data-testid="${testId}"]`).attributes('disabled')).toBeDefined()
    }
  })
})

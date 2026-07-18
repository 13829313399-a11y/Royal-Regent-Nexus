import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import InternalQuoteActivityPanel from '@/components/modules/sales/internal-quote/InternalQuoteActivityPanel.vue'
import type { InternalQuote } from '@/types/internalQuoteDesk'

function quote(): InternalQuote {
  return {
    id: 'quote-fx-1',
    fxRmbHkd: 0.85,
    fxHkdUsd: 7.8,
    fxRmbUsd: 7.75,
    factoryPriceHkd: 100,
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
})

import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import type { InternalQuote } from '@/types/internalQuoteDesk'
import InternalQuoteCostHeadline from '../InternalQuoteCostHeadline.vue'
const quote = (extra = {}) => ({ pricingComplete: true, factoryPriceHkd: 12.54, fxRmbHkd: .85, fxHkdUsd: 7.78,
  sections: [{ isRequired: true, calculationStatus: 'valid', dependencyStatus: 'current' }], ...extra } as unknown as InternalQuote)
describe('complete quote cost headline', () => {
  it.each([
    { pricingComplete: false }, { pricingComplete: undefined },
    { incompleteSections: [{ sectionCode: 'molding', reason: '未匹配材料' }] },
    { formulaRecalculationRequired: true },
    { sections: [{ isRequired: true, calculationStatus: 'blocked', dependencyStatus: 'current' }] },
    { sections: [{ isRequired: true, calculationStatus: 'valid', dependencyStatus: 'stale' }] },
  ])('does not present a partial or stale cost as the complete total: %j', extra => {
    const w = mount(InternalQuoteCostHeadline, { props: { quote: quote(extra) } })
    expect(w.text()).toContain('待补全核价'); expect(w.text()).not.toContain('12.54'); w.unmount()
  })
  it('keeps an issued historical cost despite a newer formula', () => {
    const w = mount(InternalQuoteCostHeadline, { props: { quote: quote({ moduleVersion: 'v4', finalReleaseStatus: 'issued', formulaRecalculationRequired: true }) } })
    expect(w.text()).toContain('HKD 12.54'); w.unmount()
  })
  it('updates from incomplete to complete, including a valid zero', async () => {
    const w = mount(InternalQuoteCostHeadline, { props: { quote: quote({ pricingComplete: false }) } })
    await w.setProps({ quote: quote() }); expect(w.text()).toContain('HKD 12.54')
    await w.setProps({ quote: quote({ factoryPriceHkd: 0 }) }); expect(w.text()).toContain('HKD 0.00'); w.unmount()
  })
})

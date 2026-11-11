import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { InternalQuote } from '@/types/internalQuoteDesk'
const mocks = vi.hoisted(() => ({ store: { updateReferenceMaterials: vi.fn(), submitting: false, detailLoading: false, refreshWarning: '', refreshWarningQuoteId: '' }, can: vi.fn(() => true) }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ can: mocks.can }) }))
vi.mock('@/stores/internalQuoteDesk', () => ({ useInternalQuoteDeskStore: () => mocks.store }))
import PriceBasis from '../InternalQuotePriceBasis.vue'
const quote = { id: 'quote', headerRevision: 8, factoryId: 'huakang-b', factoryName: '华康B', versionLabel: 'A-V1', status: 'drafting', sections: [], referenceSnapshot: { material_prices: { 'C-PP|5090T': '7.80000000001' }, machine_prices: [], paper_prices: [{ key: 'ab', name: 'A=B', price_factor_hkd: '2.60', remark: '来源' }] } } as unknown as InternalQuote
let wrapper: ReturnType<typeof mount>
const button = (text: string) => wrapper.findAll('button').find(b => b.text() === text)!
beforeEach(() => { mocks.can.mockReturnValue(true); mocks.store.updateReferenceMaterials.mockReset(); mocks.store.updateReferenceMaterials.mockResolvedValue({}); mocks.store.refreshWarning = '' })
afterEach(() => wrapper?.unmount())
describe('quote adopted price table', () => {
  it('saves selected quote papers without changing exact material prices, then requests preview refresh', async () => {
    wrapper = mount(PriceBasis, { props: { quote } })
    await button('维护本报价纸材').trigger('click')
    await wrapper.get('input[aria-label="纸材系数 HKD"]').setValue('3.15')
    await button('保存本款纸材并重算').trigger('click'); await flushPromises()
    expect(mocks.store.updateReferenceMaterials).toHaveBeenCalledWith('quote', 8, [{ material: 'C-PP', grade: '5090T', price_hkd_lb: '7.80000000001' }], [{ key: 'ab', name: 'A=B', price_factor_hkd: '3.15', remark: '来源' }])
    expect(wrapper.emitted('saved')).toEqual([[]])
    expect(wrapper.text()).toContain('已保存')
  })
  it('keeps the edited catalog visible after a conflict', async () => {
    mocks.store.updateReferenceMaterials.mockRejectedValue(new Error('资料已更新，请重新核对'))
    wrapper = mount(PriceBasis, { props: { quote } })
    await button('维护本报价纸材').trigger('click')
    await wrapper.get('input[aria-label="纸材系数 HKD"]').setValue('3.15')
    await button('保存本款纸材并重算').trigger('click'); await flushPromises()
    expect(wrapper.get('input[aria-label="纸材系数 HKD"]').element).toHaveProperty('value', '3.15')
    expect(wrapper.get('[role="alert"]').text()).toContain('资料已更新')
    expect(wrapper.emitted('saved')).toBeUndefined()
  })
  it('blocks price maintenance while other edits are unsaved and in read-only contexts', async () => {
    wrapper = mount(PriceBasis, { props: { quote, hasUnsavedChanges: true } })
    expect(button('维护本报价纸材').attributes('disabled')).toBeDefined()
    await wrapper.setProps({ readOnly: true, hasUnsavedChanges: false })
    expect(button('维护本报价纸材')).toBeUndefined()
  })
})

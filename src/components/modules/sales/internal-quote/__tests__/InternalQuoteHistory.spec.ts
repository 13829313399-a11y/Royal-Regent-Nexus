import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { internalQuoteApi, type ApiInternalQuoteHistoryProduct } from '@/api/internalQuote'
import type { InternalQuoteCreatePayload } from '@/types/internalQuoteDesk'
import { normalizeInternalQuotePayload } from '@/lib/internalQuoteSectionPayload'
import InternalQuoteCreateDialog from '../InternalQuoteCreateDialog.vue'
import InternalQuoteHistoryPicker from '../InternalQuoteHistoryPicker.vue'

let wrapper: VueWrapper
afterEach(() => { wrapper?.unmount(); vi.restoreAllMocks() })
function source(id: string, jp = true): ApiInternalQuoteHistoryProduct {
  return { quote_id: id, quote_no: `OLD-${id}`, batch_quote_no: 'OLD-BATCH', product_name: `${id}款`, customer: jp ? 'JustPlay' : '普通客',
    region_code: 'indonesia', version_label: 'V2', status: 'fully_approved', qty: 5000, fingerprint: 'a'.repeat(64), is_justplay: jp,
    components: jp ? [{ id: 'main', name: '主体' }, { id: 'phone', name: '电话' }, { id: 'mirror', name: '镜子' }] : [],
    participating_sections: ['engineering', 'assembly', 'sales', 'electronic'], updated_at: '2026-09-02' }
}
async function createDialog(jp = true) {
  vi.spyOn(internalQuoteApi, 'historyProducts').mockResolvedValue({ items: [source('A', jp), source('B', jp)], total: 2 })
  wrapper = mount(InternalQuoteCreateDialog, { props: { open: true, mode: 'create', factoryId: 'huakang-b',
    customers: jp ? ['JustPlay', '普通客'] : ['普通客', 'JustPlay'], businessOwners: [{ id: 'owner', username: 'owner', displayName: '业务主管' }] },
    global: { stubs: { Teleport: true } } })
  await flushPromises()
  await wrapper.get('input[placeholder="例如 IQ-HX-2026-0716-06"]').setValue('NEW-HISTORY')
}
const button = (text: string) => wrapper.findAll('button').find(b => b.text() === text)!
const picker = () => wrapper.findComponent(InternalQuoteHistoryPicker)
async function submit() { await wrapper.get('.quote-primary-button').trigger('click'); return wrapper.emitted('confirm')?.at(-1)?.[0] as InternalQuoteCreatePayload }

describe('history product and component reuse', () => {
  it.each([false, true])('references multiple whole products and appends a manual product (JustPlay=%s)', async jp => {
    await createDialog(jp)
    await button('引用历史产品').trigger('click'); await flushPromises()
    const checkboxes = picker().findAll('.history-product input')
    await checkboxes[0]!.setValue(true); await checkboxes[1]!.setValue(true)
    await picker().get('.primary').trigger('click')
    expect(wrapper.findAll('.quote-product-row')).toHaveLength(2)
    await button('新增产品').trigger('click')
    await wrapper.findAll('.quote-product-name input')[2]!.setValue('手动F')
    const payload = await submit()
    expect(payload.quoteType).toBe('series')
    expect(payload.products?.map(p => p.productName)).toEqual(['A款', 'B款', '手动F'])
    expect(payload.products?.[0]?.regionCode).toBe('indonesia')
    expect(payload.products?.[0]?.historySource?.quote_id).toBe('A')
    expect(payload.products?.[2]?.historySource).toBeUndefined()
    expect(payload.products?.[2]?.componentSources).toBeUndefined()
    if (jp) expect(payload.products?.[0]?.componentSources?.map(s => s?.component_id)).toEqual(['main', 'phone', 'mirror'])
    else expect(payload.products?.[0]?.componentSources).toBeUndefined()
  })

  it('replaces the main component, combines accessories from another product, then removes the correct source', async () => {
    await createDialog()
    await wrapper.get('.quote-product-name input').setValue('组合X')
    await wrapper.get('[aria-label="第 1 款配件个数"]').setValue('0')
    await button('选择历史分项').trigger('click'); await flushPromises()
    await picker().findAll('.history-components input')[1]!.setValue(true)
    await picker().get('.primary').trigger('click')
    await button('引用历史配件').trigger('click'); await flushPromises()
    await picker().findAll('.history-components input')[4]!.setValue(true)
    await picker().findAll('.history-components input')[5]!.setValue(true)
    await picker().get('.primary').trigger('click')
    await wrapper.get('[aria-label="移除第 1 款配件 1"]').trigger('click')
    const payload = await submit()
    expect(payload.products?.[0]?.pricingComponents).toEqual(['电话', '镜子'])
    expect(payload.products?.[0]?.componentSources?.map(s => [s?.quote_id, s?.component_id])).toEqual([['A', 'phone'], ['B', 'mirror']])
    expect(payload.products?.[0]?.historySource).toBeUndefined()
  })

  it('allows whole JustPlay copy followed by accessory replacement without replacing shared packaging source', async () => {
    await createDialog()
    await button('引用历史产品').trigger('click'); await flushPromises()
    await picker().findAll('.history-product input')[0]!.setValue(true)
    await picker().get('.primary').trigger('click')
    await wrapper.findAll('button').filter(b => b.text() === '替换历史配件')[1]!.trigger('click'); await flushPromises()
    await picker().findAll('.history-components input')[4]!.setValue(true)
    await picker().get('.primary').trigger('click')
    const payload = await submit()
    expect(payload.products?.[0]?.historySource?.quote_id).toBe('A')
    expect(payload.products?.[0]?.componentSources?.map(s => s?.quote_id)).toEqual(['A', 'B', 'A'])
  })

  it('clears incompatible source selections when switching customer', async () => {
    await createDialog()
    await button('引用历史产品').trigger('click'); await flushPromises()
    await picker().findAll('.history-product input')[0]!.setValue(true)
    await picker().get('.primary').trigger('click')
    const customer = wrapper.findAll('select').find(s => s.find('option[value="普通客"]').exists())!
    await customer.setValue('普通客')
    const payload = await submit()
    expect(payload.products?.[0]?.historySource).toBeUndefined()
    expect(payload.products?.[0]?.componentSources).toBeUndefined()
    expect(payload.products?.[0]?.pricingComponents).toBeUndefined()
  })

  it('ignores stale requests after factory changes', async () => {
    let resolveOld!: (value: { items: ApiInternalQuoteHistoryProduct[]; total: number }) => void
    const old = new Promise<{ items: ApiInternalQuoteHistoryProduct[]; total: number }>(resolve => { resolveOld = resolve })
    vi.spyOn(internalQuoteApi, 'historyProducts').mockReturnValueOnce(old).mockResolvedValue({ items: [source('NEW')], total: 1 })
    wrapper = mount(InternalQuoteHistoryPicker, { props: { open: true, factoryId: 'huakang-b', customer: 'JustPlay', isJustPlay: true, kind: 'product', multiple: true }, global: { stubs: { Teleport: true } } })
    await wrapper.setProps({ factoryId: 'huaxing' }); await flushPromises()
    resolveOld({ items: [source('STALE')], total: 1 }); await flushPromises()
    expect(wrapper.text()).toContain('NEW款')
    expect(wrapper.text()).not.toContain('STALE款')
  })

  it('keeps selections from earlier pages when adding another historical product', async () => {
    vi.spyOn(internalQuoteApi, 'historyProducts').mockResolvedValueOnce({ items: [source('A')], total: 11 })
      .mockResolvedValueOnce({ items: [source('B')], total: 11 })
    wrapper = mount(InternalQuoteHistoryPicker, { props: { open: true, factoryId: 'huakang-b', customer: 'JustPlay', isJustPlay: true, kind: 'product', multiple: true }, global: { stubs: { Teleport: true } } })
    await flushPromises()
    await wrapper.get('.history-product input').setValue(true)
    await button('下一页').trigger('click'); await flushPromises()
    await wrapper.get('.history-product input').setValue(true)
    await wrapper.get('.primary').trigger('click')
    const chosen = wrapper.emitted('confirm')![0]![0] as Array<{ product: ApiInternalQuoteHistoryProduct }>
    expect(chosen.map(item => item.product.quote_id)).toEqual(['A', 'B'])
  })

  it('retains historical quick-paint allocation when normalizing editable department inputs', () => {
    const normalized = normalizeInternalQuotePayload('painting', { rows: [{ name: '快捷喷油', cost_allocation: 'direct',
      operations: { spray: { quantity: 1, unit_price_hkd: 2 }, paint: { quantity: 1, unit_price_hkd: 3.39 } } }] })
    expect(normalized).toMatchObject({ rows: [{ cost_allocation: 'direct', operations: { paint: { unit_price_hkd: 3.39 } } }] })
  })

  it('only selects departments that belong to the chosen component', async () => {
    await createDialog()
    vi.mocked(internalQuoteApi.historyProducts).mockResolvedValue({ items: [{ ...source('A'),
      participating_sections: ['engineering', 'assembly', 'sales', 'painting', 'electronic'],
      component_sections: { phone: ['electronic'] } }], total: 1 })
    await wrapper.get('.quote-product-name input').setValue('组合X')
    await button('引用历史配件').trigger('click'); await flushPromises()
    await picker().findAll('.history-components input')[1]!.setValue(true)
    await picker().get('.primary').trigger('click')
    const payload = await submit()
    expect(payload.participatingSections).toContain('electronic')
    expect(payload.participatingSections).not.toContain('painting')
  })
})

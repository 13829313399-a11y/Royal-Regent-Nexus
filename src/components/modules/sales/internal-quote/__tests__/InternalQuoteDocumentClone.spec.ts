import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, expect, it, vi } from 'vitest'
import { internalQuoteApi, type ApiInternalQuote } from '@/api/internalQuote'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import type { InternalQuoteCreatePayload } from '@/types/internalQuoteDesk'
import InternalQuoteCreateDialog from '../InternalQuoteCreateDialog.vue'

afterEach(() => vi.restoreAllMocks())
function setup(customer = 'Just Play', factoryId = 'huakang-b', ids = ['p1', 'p2', 'p3']) {
  setActivePinia(createPinia())
  const source = { ...useInternalQuoteDeskStore().placeholderQuote, id: 'p1', factoryId, customer,
    quoteNo: '75595', batchQuoteNo: '75595', businessOwnerId: 'sales-owner' }
  const apiQuote = (id: string) => ({ id, product_name: `产品${id}`, qty: 10000, region_code: '', header_revision: id.includes('v2') ? 12 : 4,
    version_label: id.includes('v2') ? 'A-V2' : 'V1.0', sections: [{ department: 'sales', payload: customer === 'Just Play' ? { pricing_mode: 'component',
      pricing_components: [{ id: 'component-01', name: '主体' }, { id: 'component-02', name: '包装盘' }] } : { packaging_materials: [] } }] } as ApiInternalQuote)
  vi.spyOn(internalQuoteApi, 'listBatchProducts').mockResolvedValue(ids.map(id => ({ quote_id: id, scenario_name: '原方案', version_label: 'V1.0', quote_type: ids.length === 1 ? 'single' : 'series' })) as never)
  vi.spyOn(internalQuoteApi, 'get').mockImplementation(async id => apiQuote(id))
  vi.spyOn(internalQuoteApi, 'listAlternatives').mockImplementation(async id => ({ items: [
    { quote_id: id, scenario_name: '原方案', version_label: 'V1.0' },
    { quote_id: `${id}-v2`, scenario_name: '原方案', version_label: 'A-V2' },
  ] } as never))
  const wrapper = mount(InternalQuoteCreateDialog, { props: { open: true, mode: 'clone', sourceQuote: source,
    factoryId, customers: [customer], businessOwners: [{ id: 'sales-owner', displayName: '业务负责人', username: 'owner' }] },
    global: { stubs: { Teleport: true } } })
  return wrapper
}

it.each([['Just Play', 'huakang-b'], ['普通客', 'huakang-b'], ['Mattel', 'huaxing']])('%s / %s loads all products and appends a blank product', async (customer, factoryId) => {
  const wrapper = setup(customer, factoryId)
  try {
    await flushPromises()
    expect(wrapper.findAll('.quote-product-name')).toHaveLength(3)
    expect(wrapper.findAll('.quote-remove-product')).toHaveLength(0)
    expect(wrapper.find('.quote-optional-segments').exists()).toBe(false)
    await wrapper.get('[aria-label="第 2 款复制来源版本"]').setValue('p2-v2'); await flushPromises()
    await wrapper.findAll('button').find(b => b.text() === '新增空白产品')!.trigger('click')
    expect(wrapper.findAll('.quote-product-name')).toHaveLength(4)
    await wrapper.findAll('.quote-product-name input')[3]!.setValue('新增产品')
    await wrapper.get('.quote-primary-button').trigger('click')
    const payload = wrapper.emitted('confirm')![0]![0] as InternalQuoteCreatePayload
    expect(payload.products?.map(p => p.cloneSourceQuoteId)).toEqual(['p1', 'p2-v2', 'p3', undefined])
    expect(payload.products?.[1]?.cloneSourceRevision).toBe(12)
    expect(payload.products?.[3]?.pricingComponents).toEqual(customer === 'Just Play' ? ['主体', '包装盘'] : undefined)
    if (customer !== 'Just Play') expect(wrapper.find('.quote-product-components').exists()).toBe(false)
    expect(payload.quoteNo).toBe('75595-COPY')
  } finally { wrapper.unmount() }
})

it('blocks confirmation when any source version cannot be loaded', async () => {
  const wrapper = setup()
  try {
    await flushPromises()
    vi.mocked(internalQuoteApi.get).mockRejectedValueOnce(new Error('来源版本读取失败'))
    await wrapper.get('[aria-label="第 2 款复制来源版本"]').setValue('p2-v2'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('来源版本读取失败')
    expect(wrapper.get('.quote-primary-button').attributes('disabled')).toBeDefined()
    await wrapper.get('.quote-primary-button').trigger('click')
    expect(wrapper.emitted('confirm')).toBeUndefined()
  } finally { wrapper.unmount() }
})


it('copies a single ordinary-customer product without requiring JustPlay components', async () => {
  const wrapper = setup('Mattel', 'huaxing', ['p1'])
  try {
    await flushPromises()
    await wrapper.get('.quote-primary-button').trigger('click')
    const payload = wrapper.emitted('confirm')![0]![0] as InternalQuoteCreatePayload
    expect(payload.quoteType).toBe('single')
    expect(payload.products).toHaveLength(1)
    expect(payload.products?.[0]).toMatchObject({ cloneSourceQuoteId: 'p1', cloneSourceRevision: 4 })
    expect(payload.products?.[0]?.pricingComponents).toBeUndefined()
    expect(wrapper.find('.quote-product-components').exists()).toBe(false)
  } finally { wrapper.unmount() }
})

import { mount, type VueWrapper } from '@vue/test-utils'
import { reactive } from 'vue'
import { describe, expect, it } from 'vitest'
import { createDickieMapping, DICKIE_FIXED_MATERIALS, DICKIE_FIXED_REMARKS } from '@/lib/dickieQuote'
import { normalizeInternalQuotePayload, defaultSalesFreightReferenceRoutes, type SalesPayload, type EngineeringPayload } from '@/lib/internalQuoteSectionPayload'
import InternalQuoteDickieSales from '../InternalQuoteDickieSales.vue'
import InternalQuoteDickieMolds from '../InternalQuoteDickieMolds.vue'
import InternalQuoteSectionForm from '../InternalQuoteSectionForm.vue'

const salesModel = () => reactive(normalizeInternalQuotePayload('sales', { shipping: { markup_tiers: [{ moq: 3000, markup_x: 1.2, include_in_output: true }, { moq: 5000, markup_x: 1.1, include_in_output: false }] } }) as SalesPayload)
const click = async (wrapper: VueWrapper, text: string) => { await wrapper.findAll('button').find(button => button.text() === text)!.trigger('click') }
const field = (wrapper: VueWrapper, label: string) => wrapper.get(`[aria-label="${label}"]`)

describe('Dickie supplemental forms', () => {
  it('requires explicit activation and renders fixed bilingual terms and materials without inputs', async () => {
    const sales = salesModel()
    const before = JSON.stringify(sales)
    const wrapper = mount(InternalQuoteDickieSales, { props: { sales, routes: defaultSalesFreightReferenceRoutes } })
    expect(JSON.stringify(sales)).toBe(before)
    for (const term of DICKIE_FIXED_REMARKS) { expect(wrapper.text()).toContain(term.zh); expect(wrapper.text()).toContain(term.en) }
    for (const material of DICKIE_FIXED_MATERIALS) expect(wrapper.text()).toContain(material.price.toFixed(1))
    expect(wrapper.find('.fixed-terms input').exists()).toBe(false)
    await click(wrapper, '启用 Dickie 报客资料')
    expect(sales.customer_quote_fields.dickie.mapping?.version).toBe('dickie-v2')
    await field(wrapper, 'Dickie 产品名称 English').setValue('Cable Car')
    await field(wrapper, 'Dickie 报价公司').setValue('asia')
    await field(wrapper, 'Dickie 使用客户外箱尺寸').setValue(true)
    await field(wrapper, 'Dickie 客户外箱长').setValue('43.5')
    expect(sales.customer_quote_fields.dickie.mapping).toMatchObject({ company: 'asia', item_name: { en: 'Cable Car' }, customer_carton_enabled: true, customer_carton_cm: { length: 43.5 } })
  })

  it('binds explicit tier/routes, confirmed prices, and ordered signed adjustments without calculating', async () => {
    const sales = salesModel()
    sales.customer_quote_fields.dickie.mapping = createDickieMapping()
    const wrapper = mount(InternalQuoteDickieSales, { props: { sales, routes: defaultSalesFreightReferenceRoutes } })
    const offer = sales.customer_quote_fields.dickie.mapping.offers[0]!
    expect(field(wrapper, 'Dickie 方案 1 MOQ').text()).toContain('5000 · 1.1 倍 · 不输出')
    await field(wrapper, 'Dickie 方案 1 MOQ').setValue('3000')
    await field(wrapper, "Dickie 方案 1 40' 路线").setValue(defaultSalesFreightReferenceRoutes[0]!.key)
    expect(offer.route_20).toBe('')
    await field(wrapper, 'Dickie 方案 1 价格来源').setValue('confirmed')
    await field(wrapper, "Dickie 方案 1 40' 已确认价 HKD").setValue('23.4')
    await field(wrapper, 'Dickie 方案 1 已确认价格依据').setValue('Customer email 2026-09-21')
    await click(wrapper, '新增方案 1 调整')
    await field(wrapper, 'Dickie 方案 1 调整 1 原因').setValue('Discount')
    await field(wrapper, 'Dickie 方案 1 调整 1 百分比').setValue('-5')
    await field(wrapper, 'Dickie 方案 1 调整 1 HKD').setValue('-0.2')
    await click(wrapper, '新增方案 1 调整')
    await field(wrapper, 'Dickie 方案 1 调整 2 原因').setValue('Packing')
    await field(wrapper, '上移方案 1 调整 2').trigger('click')
    expect(offer.adjustments.map(row => row.label)).toEqual(['Packing', 'Discount'])
    expect(offer.adjustments[1]).toEqual({ label: 'Discount', percent: -5, amount_hkd: -0.2 })
    expect(offer).toMatchObject({ moq: 3000, route_40: defaultSalesFreightReferenceRoutes[0]!.key, confirmed_40: 23.4, confirmed_reference: 'Customer email 2026-09-21' })
    await click(wrapper, '新增报价方案')
    expect(sales.customer_quote_fields.dickie.mapping.offers).toHaveLength(2)
    await click(wrapper, '删除方案 2')
    expect(sales.customer_quote_fields.dickie.mapping.offers).toHaveLength(1)
  })

  it('blocks activation and editing in read-only mode', async () => {
    const sales = salesModel()
    const wrapper = mount(InternalQuoteDickieSales, { props: { sales, routes: [], disabled: true } })
    await click(wrapper, '启用 Dickie 报客资料')
    expect(sales.customer_quote_fields.dickie.mapping).toBeUndefined()
    sales.customer_quote_fields.dickie.mapping = createDickieMapping()
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('fieldset').every(item => item.attributes('disabled') !== undefined)).toBe(true)
    expect(wrapper.findAll('button').every(item => item.attributes('disabled') !== undefined)).toBe(true)
    const before = JSON.stringify(sales)
    await click(wrapper, '新增报价方案')
    expect(JSON.stringify(sales)).toBe(before)
  })

  it('initializes mold supplements only on selection, retains shared facts, and preserves deselected details', async () => {
    const engineering = reactive(normalizeInternalQuotePayload('engineering', { molds: [{ mold_no: '001', chinese_name: '车壳', mold_size: '30x20x10', cavity: '1x2', quantity: 1, material_type: 'ABS', mold_base_material: 'P20' }] }) as EngineeringPayload)
    const mold = engineering.molds[0]!
    const before = JSON.stringify(mold)
    const wrapper = mount(InternalQuoteDickieMolds, { props: { molds: engineering.molds } })
    expect(JSON.stringify(mold)).toBe(before)
    expect(wrapper.text()).toContain('30x20x10')
    expect(wrapper.text()).toContain('ABS')
    await field(wrapper, 'Dickie 模具 1 纳入报客').setValue(true)
    await field(wrapper, 'Dickie 模具 1 英文部件名称').setValue('Car body')
    await field(wrapper, 'Dickie 模具 1 客户模价 HKD').setValue('25000')
    expect(field(wrapper, 'Dickie 模具 1 客户模号').attributes('placeholder')).toBe('001')
    await field(wrapper, 'Dickie 模具 1 纳入报客').setValue(false)
    expect(mold.dickie_export).toMatchObject({ included: false, parts_en: 'Car body', customer_price_hkd: 25000 })
    const { dickie_export: _supplement, ...facts } = mold
    expect(facts).toEqual(JSON.parse(before))
    await wrapper.setProps({ disabled: true })
    expect(field(wrapper, 'Dickie 模具 1 纳入报客').attributes('disabled')).toBeDefined()
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
  })

  it.each(['Dickie', ' Dicky '])('integrates the supplemental sales and mold forms for %s only', customer => {
    const sales = mount(InternalQuoteSectionForm, { props: { code: 'sales', customer, factoryId: 'huaxing', modelValue: salesModel() } })
    expect(sales.findComponent(InternalQuoteDickieSales).exists()).toBe(true)
    const engineering = mount(InternalQuoteSectionForm, { props: { code: 'engineering', customer, factoryId: 'huaxing', modelValue: normalizeInternalQuotePayload('engineering', {}) } })
    expect(engineering.findComponent(InternalQuoteDickieMolds).exists()).toBe(true)
  })
  it('keeps Yinhui outside the Dickie forms', () => {
    const wrapper = mount(InternalQuoteSectionForm, { props: { code: 'sales', customer: 'Yinhui', modelValue: salesModel() } })
    expect(wrapper.findComponent(InternalQuoteDickieSales).exists()).toBe(false)
  })
  it.each(['huakang-a', 'huadeng', undefined])('hides the Huaxing mapping in %s', factoryId => {
    const wrapper = mount(InternalQuoteSectionForm, { props: { code: 'sales', customer: 'Dickie', factoryId, modelValue: salesModel() } })
    expect(wrapper.findComponent(InternalQuoteDickieSales).exists()).toBe(false)
  })
})

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { translateQuoteDescriptions } from '@/api/quoteTranslation'
vi.mock('@/api/quoteTranslation',()=>({translateQuoteDescriptions:vi.fn()}))
import YinhuiQuoteReview from '../YinhuiQuoteReview.vue'
import type { YinhuiConversionResult } from '@/lib/customerPriceConverters/yinhui'
function fixture(): YinhuiConversionResult {
  return {sourceFileName:'input.xlsx',warnings:['型号冲突：请核对'],sheets:[],quoteData:{
    model:'0012',productName:'Robot',quoteDate:'2026-08-31',packaging:'Window Box',moq:5000,stage:'',adaptor:'',tryMe:'',freightLclHkd:0,freightFclHkd:2,colorBoxCm:[10,10,10],cartonCm:[20,20,20],cartonPack:4,
    tools:[],plastic:[],mechanical:[{description:'Screw',source:'工程/螺丝',quantity:2,amountHkd:1,internalHkd:.8}],electronic:[],packagingRows:[],carton:{description:'Outer Carton',source:'业务',quantity:1,amountHkd:1,internalHkd:.8},assemblyHkd:1,sprayingHkd:1,packagingLaborHkd:1,battery:'',internalTotalHkd:4,
  }}
}
describe('Silverlit export review', () => {
  beforeEach(()=>{ vi.mocked(translateQuoteDescriptions).mockReset() })
  it('automatically translates newly imported Chinese and disables confirmation while running', async () => {
    const result=fixture();result.quoteData.productName='配重塊 4.0mm'
    let resolve!: (value: Awaited<ReturnType<typeof translateQuoteDescriptions>>) => void
    vi.mocked(translateQuoteDescriptions).mockImplementation(()=>new Promise(r=>{resolve=r}))
    const wrapper=mount(YinhuiQuoteReview,{props:{result,confirmed:true}})
    expect(translateQuoteDescriptions).toHaveBeenCalledWith(['配重塊 4.0mm'],'huaxing',expect.any(AbortSignal))
    expect(wrapper.get('[data-testid="yinhui-confirm"]').attributes('disabled')).toBeDefined()
    resolve({engine:'local',warning:'',items:[{source:'配重塊 4.0mm',translation:'Counterweight 4.0mm',needs_review:false}]})
    await flushPromises()
    expect(result.quoteData.productName).toBe('Counterweight 4.0mm')
    expect(wrapper.text()).toContain('已自动翻译 1 项')
    expect(wrapper.get('[data-testid="yinhui-confirm"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.emitted('update:confirmed')?.at(-1)).toEqual([false])
  })
  it('preserves names on failure and allows retry', async () => {
    const result=fixture();result.quoteData.productName='配重塊'
    vi.mocked(translateQuoteDescriptions).mockRejectedValueOnce(new Error('服务未就绪')).mockResolvedValueOnce({engine:'local',warning:'',items:[{source:'配重塊',translation:'Counterweight',needs_review:false}]})
    const wrapper=mount(YinhuiQuoteReview,{props:{result,confirmed:false}})
    await flushPromises()
    expect(wrapper.text()).toContain('服务未就绪')
    expect(result.quoteData.productName).toBe('配重塊')
    await wrapper.get('[data-testid="yinhui-translate"]').trigger('click')
    await flushPromises()
    expect(result.quoteData.productName).toBe('Counterweight')
  })
  it('cancels stale work when the import is replaced or the component unmounts', async () => {
    const result=fixture();result.quoteData.productName='配重塊'
    let resolve!: (value: Awaited<ReturnType<typeof translateQuoteDescriptions>>) => void
    vi.mocked(translateQuoteDescriptions).mockImplementation(()=>new Promise(r=>{resolve=r}))
    const wrapper=mount(YinhuiQuoteReview,{props:{result,confirmed:false}})
    const signal=vi.mocked(translateQuoteDescriptions).mock.calls[0]![2]!
    await wrapper.setProps({result:fixture()})
    expect(signal.aborted).toBe(true)
    resolve({engine:'local',warning:'',items:[{source:'配重塊',translation:'Counterweight',needs_review:false}]})
    await flushPromises()
    expect(result.quoteData.productName).toBe('配重塊')
    wrapper.unmount()
  })
  it('does not run translation in a disabled or different-factory review', async () => {
    const result=fixture();result.quoteData.productName='配重塊'
    const wrapper=mount(YinhuiQuoteReview,{props:{result,confirmed:false,disabled:true}})
    expect(translateQuoteDescriptions).not.toHaveBeenCalled()
    await wrapper.setProps({disabled:false,factoryId:'huadeng'})
    expect(translateQuoteDescriptions).not.toHaveBeenCalled()
  })
  it('shows customs fees separately with source lineage and includes them once in the total', () => {
    const result=fixture()
    result.quoteData.documentFees=[{description:'Documents / Customs Fee',source:'明细!D91',quantity:1,amountHkd:.18539692,internalHkd:.16}]
    const wrapper=mount(YinhuiQuoteReview,{props:{result,confirmed:false}})
    expect(wrapper.text()).toContain('报关 / 文件费（总表 H32）')
    expect(wrapper.text()).toContain('明细!D91')
    expect(wrapper.text()).toContain('EX-FACTORY HKD 5.185397')
    expect(wrapper.get('[data-testid="yinhui-confirm"]').attributes('disabled')).toBeUndefined()
  })
  it('requires review again after changing a quotation field', async () => {
    const result=fixture(); const wrapper=mount(YinhuiQuoteReview,{props:{result,confirmed:true}})
    await wrapper.get('[data-testid="yinhui-model"]').setValue('0020')
    expect(result.quoteData.model).toBe('0020')
    expect(wrapper.emitted('update:confirmed')?.at(-1)).toEqual([false])
    expect(wrapper.text()).toContain('型号冲突')
  })
  it('blocks confirmation for missing freight or invalid BOM names but accepts Chinese', async () => {
    const result=fixture(); result.quoteData.freightLclHkd=null
    const wrapper=mount(YinhuiQuoteReview,{props:{result,confirmed:false}})
    expect(wrapper.get('[data-testid="yinhui-confirm"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="yinhui-freightLclHkd"]').setValue('0')
    expect(wrapper.get('[data-testid="yinhui-confirm"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('input[aria-label="五金 / 外购第 1 行物料名称"]').setValue('螺丝 Φ2.0x6PB 黑色（2PCS）')
    expect(wrapper.get('[data-testid="yinhui-confirm"]').attributes('disabled')).toBeUndefined()
    expect(translateQuoteDescriptions).not.toHaveBeenCalled()
    expect(wrapper.get('input[aria-label="五金 / 外购第 1 行物料名称"]').classes()).not.toContain('border-amber-500')
    await wrapper.get('input[aria-label="五金 / 外购第 1 行物料名称"]').setValue('#VALUE!')
    expect(wrapper.get('[data-testid="yinhui-confirm"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[role="alert"]').text()).toContain('BOM 物料名称')
  })
  it('locks the review controls when export permission is absent or export is in progress', () => {
    const wrapper=mount(YinhuiQuoteReview,{props:{result:fixture(),confirmed:false,disabled:true}})
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="yinhui-confirm"]').attributes('disabled')).toBeDefined()
  })
  it('warns about missing resin prices and allows acknowledgement without treating the subtotal as complete', async () => {
    const result = fixture()
    result.quoteData.tools = [{moldNo:'M1',partNo:'P1',description:'Body',usage:1,cavity:1,weightG:100,material:'PA',laborHkd:1,toolingHkd:0}]
    const wrapper = mount(YinhuiQuoteReview,{props:{result,confirmed:false}})
    expect(wrapper.get('[data-testid="yinhui-missing-prices"]').text()).toContain('PA')
    expect(wrapper.text()).toContain('已知成本小计（待补料价）')
    expect(wrapper.text()).toContain('我已知悉缺失料价将留空')
    expect(wrapper.text()).toContain('C-ABS 24')
    expect(wrapper.get('[data-testid="yinhui-confirm"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[data-testid="yinhui-confirm"]').setValue(true)
    expect(wrapper.emitted('update:confirmed')?.at(-1)).toEqual([true])
    await wrapper.setProps({confirmed:true})
    await wrapper.get('[data-testid="yinhui-model"]').setValue('0021')
    expect(wrapper.emitted('update:confirmed')?.at(-1)).toEqual([false])
  })
})

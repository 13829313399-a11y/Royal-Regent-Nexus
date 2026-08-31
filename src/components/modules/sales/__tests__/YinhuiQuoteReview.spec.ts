import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import YinhuiQuoteReview from '../YinhuiQuoteReview.vue'
import type { YinhuiConversionResult } from '@/lib/customerPriceConverters/yinhui'
function fixture(): YinhuiConversionResult {
  return {sourceFileName:'input.xlsx',warnings:['型号冲突：请核对'],sheets:[],quoteData:{
    model:'0012',productName:'Robot',quoteDate:'2026-08-31',packaging:'Window Box',moq:5000,stage:'',adaptor:'',tryMe:'',freightLclHkd:0,freightFclHkd:2,colorBoxCm:[10,10,10],cartonCm:[20,20,20],cartonPack:4,
    tools:[],plastic:[],mechanical:[{description:'Screw',source:'工程/螺丝',quantity:2,amountHkd:1,internalHkd:.8}],electronic:[],packagingRows:[],carton:{description:'Outer Carton',source:'业务',quantity:1,amountHkd:1,internalHkd:.8},assemblyHkd:1,sprayingHkd:1,packagingLaborHkd:1,battery:'',internalTotalHkd:4,
  }}
}
describe('Silverlit export review', () => {
  it('requires review again after changing a quotation field', async () => {
    const result=fixture(); const wrapper=mount(YinhuiQuoteReview,{props:{result,confirmed:true}})
    await wrapper.get('[data-testid="yinhui-model"]').setValue('0020')
    expect(result.quoteData.model).toBe('0020')
    expect(wrapper.emitted('update:confirmed')?.at(-1)).toEqual([false])
    expect(wrapper.text()).toContain('型号冲突')
  })
  it('blocks confirmation for missing freight or untranslated names', async () => {
    const result=fixture(); result.quoteData.freightLclHkd=null
    const wrapper=mount(YinhuiQuoteReview,{props:{result,confirmed:false}})
    expect(wrapper.get('[data-testid="yinhui-confirm"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="yinhui-freightLclHkd"]').setValue('0')
    expect(wrapper.get('[data-testid="yinhui-confirm"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('input[aria-label="五金 / 外购第 1 行英文描述"]').setValue('待翻译')
    expect(wrapper.get('[data-testid="yinhui-confirm"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[role="alert"]').text()).toContain('英文')
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

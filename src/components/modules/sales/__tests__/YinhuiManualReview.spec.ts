import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
vi.mock('@/api/quoteTranslation',()=>({translateQuoteDescriptions:vi.fn()}))
import YinhuiQuoteReview from '../YinhuiQuoteReview.vue'
import type { YinhuiConversionResult } from '@/lib/customerPriceConverters/yinhui'

function fixture(): YinhuiConversionResult {
  return {sourceFileName:'input.xlsx',warnings:[],manualReviewReasons:['注塑第 9 行无法与 Tool Plan 唯一匹配'],sheets:[],quoteData:{
    model:'0012',productName:'Robot',quoteDate:'2026-09-08',packaging:'Window Box',moq:5000,stage:'',adaptor:'',tryMe:'',freightLclHkd:0,freightFclHkd:2,colorBoxCm:[10,10,10],cartonCm:[20,20,20],cartonPack:4,
    tools:[{moldNo:'',partNo:'',description:'Body',usage:1,cavity:1,weightG:100,material:'ABS',laborHkd:1,toolingHkd:0}],plastic:[],mechanical:[],electronic:[],packagingRows:[],carton:{description:'Outer Carton',source:'业务',quantity:1,amountHkd:1,internalHkd:.8},assemblyHkd:1,sprayingHkd:1,packagingLaborHkd:1,battery:'',internalTotalHkd:4,
  }}
}

describe('Silverlit manual Tool Plan review',()=>{
  it('shows the non-blocking reasons and requires the existing explicit confirmation',async()=>{
    const wrapper=mount(YinhuiQuoteReview,{props:{result:fixture(),confirmed:false}})
    expect(wrapper.get('[data-testid="yinhui-manual-review"]').text()).toContain('只作提醒，不阻止导入或确认')
    expect(wrapper.get('[data-testid="yinhui-confirm"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('我已人工核对 Tool Plan 提醒及其金额影响，同意放行')
    await wrapper.get('[data-testid="yinhui-confirm"]').setValue(true)
    expect(wrapper.emitted('update:confirmed')?.at(-1)).toEqual([true])
  })
  it('keeps confirmation blocked while a fallback Tool Plan description is still Chinese',()=>{
    const result=fixture();result.quoteData.tools[0]!.description='透明面盖'
    const wrapper=mount(YinhuiQuoteReview,{props:{result,confirmed:false}})
    expect(wrapper.text()).toContain('请在核对区补全英文物料名称：透明面盖')
    expect(wrapper.get('[data-testid="yinhui-confirm"]').attributes('disabled')).toBeDefined()
  })
})

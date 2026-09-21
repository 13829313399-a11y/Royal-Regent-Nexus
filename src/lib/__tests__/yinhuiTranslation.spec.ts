import { describe, expect, it, vi } from 'vitest'
import type { YinhuiQuoteData } from '../customerPriceConverters/yinhui'
import type { QuoteTranslationResponse } from '@/api/quoteTranslation'
import { translateYinhuiDescriptions, pendingYinhuiDescriptions } from '../customerPriceConverters/yinhuiTranslation'

function fixture(): YinhuiQuoteData {
  return {model:'89218',productName:'Robot',quoteDate:'2026-09-03',packaging:'Window Box',moq:5000,stage:'核价',adaptor:'',tryMe:'',freightLclHkd:1,freightFclHkd:2,colorBoxCm:[10,10,10],cartonCm:[20,20,20],cartonPack:4,
    tools:[{moldNo:'中文模号',partNo:'A01',description:'配重塊 ABS 4.0mm (2PCS)',usage:2,cavity:4,weightG:3.5,material:'C-PP',laborHkd:1,toolingHkd:0}],plastic:[],mechanical:[{description:'配重塊 ABS 4.0mm (2PCS)',source:'明细!D46',quantity:2,amountHkd:.275,internalHkd:.24}],electronic:[],packagingRows:[],carton:{description:'Outer Carton',source:'业务',quantity:1,amountHkd:1,internalHkd:.8},assemblyHkd:1,sprayingHkd:1,packagingLaborHkd:1,battery:'',internalTotalHkd:4}
}
const response = (source: string, translation: string): QuoteTranslationResponse => ({engine:'local',warning:'',items:[{source,translation,needs_review:false}]})
describe('Yinhui automatic name translation', () => {
  it('leaves every BOM group unchanged while translating product, packaging and tools', async () => {
    const data = fixture()
    for (const group of ['plastic', 'electronic', 'fabric', 'packagingRows', 'documentFees'] as const) data[group] = [{ ...data.mechanical[0]! }]
    data.carton.description = '主纸箱'
    data.productName = '机器人'; data.packaging = '彩盒'
    const before = structuredClone(data)
    const translate = vi.fn(async (texts: string[]): Promise<QuoteTranslationResponse> => ({ engine: 'local', warning: '', items: texts.map(source => ({ source, translation: source === '机器人' ? 'Robot' : source === '彩盒' ? 'Color Box' : 'Counterweight ABS 4.0mm (2PCS)', needs_review: false })) }))
    expect(await translateYinhuiDescriptions(data, translate)).toMatchObject({ translated: 3, remaining: 0 })
    expect(translate).toHaveBeenCalledWith(['机器人', '彩盒', '配重塊 ABS 4.0mm (2PCS)'])
    for (const group of ['plastic', 'mechanical', 'electronic', 'fabric', 'packagingRows', 'documentFees', 'carton'] as const) expect(data[group]).toEqual(before[group])
  })
  it('sends deduplicated name text only and keeps commercial data and identifiers unchanged', async () => {
    const data=fixture();data.tools.push({...data.tools[0]!,partNo:'A02'})
    const before=structuredClone(data)
    const translate=vi.fn(async (texts:string[]) => response(texts[0]!,'Counterweight ABS 4.0mm (2PCS)'))
    const result=await translateYinhuiDescriptions(data,translate)
    expect(translate).toHaveBeenCalledWith(['配重塊 ABS 4.0mm (2PCS)'])
    expect(result).toMatchObject({translated:2,remaining:0})
    for (const row of data.tools) {row.description=row.originalDescription!;delete row.originalDescription}
    expect(data).toEqual(before)
  })
  it.each(['Counterweight ABS 5.0mm (2PCS)','Counterweight POM 4.0mm (2PCS)','Counterweight ABS 4.0mm (2PCS) 8',''])('rejects a changed specification or invalid result: %s', async translated => {
    const data=fixture();const before=structuredClone(data)
    await expect(translateYinhuiDescriptions(data,async texts => response(texts[0]!,translated))).rejects.toThrow(/翻译/)
    expect(data).toEqual(before)
  })
  it('keeps a failed or reordered batch atomic', async () => {
    const data=fixture()
    await expect(translateYinhuiDescriptions(data,async()=>response('wrong','Counterweight'))).rejects.toThrow(/对应/)
    expect(pendingYinhuiDescriptions(data)).toBe(1)
  })
  it('ignores a stale import response', async () => {
    const data=fixture();const before=structuredClone(data)
    await translateYinhuiDescriptions(data,async texts=>response(texts[0]!,'Counterweight ABS 4.0mm (2PCS)'),()=>false)
    expect(data).toEqual(before)
  })
  it('does not overwrite a manual edit made during inference', async () => {
    const data=fixture()
    await translateYinhuiDescriptions(data,async texts=>{
      data.tools[0]!.description='Manually checked Counterweight'
      return response(texts[0]!,'Counterweight ABS 4.0mm (2PCS)')
    })
    expect(data.tools[0]!.description).toBe('Manually checked Counterweight')
  })
  it('does not contact the server when only BOM names are Chinese', async () => {
    const data=fixture();data.tools[0]!.description='Counterweight'
    const translate=vi.fn()
    expect(await translateYinhuiDescriptions(data,translate)).toMatchObject({translated:0,remaining:0})
    expect(translate).not.toHaveBeenCalled()
  })
})

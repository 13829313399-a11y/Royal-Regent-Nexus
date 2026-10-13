import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import Monthly from '../MaterialHandoverMonthly.vue'
import type { handoverApi, HandoverMonthly } from '@/api/materialHandover'
let wrapper:VueWrapper|undefined
afterEach(()=>{wrapper?.unmount();wrapper=undefined})
const report=():HandoverMonthly=>({month:'2026-07',basis:'actual',version:'v1',closed:false,amounts_calculated:false,live:true,
  details:[{document_id:'D1',line_id:'L1',source_no:'DN-1',document_date:'2026-07-18',supplier_id:'SUP',supplier_name:'自己的供应商',item_code:'00012',item_name:'白布',unit:'码',declared:'40',prior_received:'15',month_received:'25',month_reversed:'15',month_net_received:'10',cumulative_received:'25',outstanding:'15',unit_price:'0',price_unit:'码',currency:'CNY',price_note:'免费补货',notes:[]}],
  summary:[],totals:[{unit:'码',month_received:'25',month_reversed:'15',month_net_received:'10'}],unlinked_receipts:[]})
describe('monthly quantity reconciliation',()=>{
  it('preserves zero reference prices and separates receipts from reversals',async()=>{
    const client={monthly:vi.fn().mockResolvedValue(report()),exportMonthly:vi.fn()} as unknown as ReturnType<typeof handoverApi>
    wrapper=mount(Monthly,{props:{client,external:true,suppliers:[]}});await flushPromises()
    expect(wrapper.text()).toContain('净实收 10');expect(wrapper.text()).toContain('免费补货')
    expect(wrapper.text()).not.toContain('未记录');expect(wrapper.find('[aria-label="对账供应商"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('不自动确定付款金额')
  })
  it('clears old supplier data on a new context and ignores a late response',async()=>{
    let resolve:(value:HandoverMonthly)=>void=()=>{}
    const old={monthly:vi.fn().mockReturnValue(new Promise<HandoverMonthly>(r=>{resolve=r}))} as unknown as ReturnType<typeof handoverApi>
    wrapper=mount(Monthly,{props:{client:old,external:true,suppliers:[]}})
    const next={monthly:vi.fn().mockResolvedValue({...report(),details:[],totals:[]})} as unknown as ReturnType<typeof handoverApi>
    await wrapper.setProps({client:next});await flushPromises();resolve(report());await flushPromises()
    expect(wrapper.text()).not.toContain('自己的供应商')
  })
})

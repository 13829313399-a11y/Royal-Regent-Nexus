import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import CuttingPeriodReview from '../CuttingPeriodReview.vue'
import CuttingClosingReport from '../CuttingClosingReport.vue'
import type { ClosingPreview } from '../closingApi'
import type { PeriodSnapshot, PeriodComparison, PeriodRow } from '../periodApi'

const order:ClosingPreview={line_id:'line-1',order_snapshot:{customer_name:'甲客户',reference_no:'ORDER-1',product_no:'P01',product_name_zh:'蓝色衣服'},month:'2026-10',start:'2026-10-01',end:'2026-10-31',through:'2026-10-31',generated_at:'保存时间',state:'preview',partial:false,basis:{order_version:1,plan_version:2,usage_revision:3,warehouse_revision:4},production:[],materials:[],issues:[{code:'period_wip_unconfirmed',message:'历史月末在制归属及结转尚未冻结',workspace:'costs',document_id:''}],production_documents:[],usage_documents:[],warehouse_documents:[],costs:{HKD:{normal:'6.25',loss:'1.56'}},pending_pricing:0}
const row:PeriodRow={issue_id:'issue-1',line_id:'line-1',context:{task_name:'任务A',resource_name:'本厂',item_name:'蓝布',unit:'米',root_batch_id:'batch-1'},opening_normal_quantity:'0',ending_normal_quantity:'2',opening_loss_quantity:'0',ending_loss_quantity:'0.5',opening_custody:'0',ending_custody:'1.5',opening_sets:0,ending_sets:10,carried_completed_quantity:null,opening_completed_quantity:'0',completed_quantity:'1.5',opening_wip_quantity:'0',ending_wip_quantity:'0.5',currency:'HKD',amounts:{ending_completed:'4.69',ending_wip:'1.56'},price:{version:2,actor:'采购',date:'保存时间',reason:'核对原批次',data:{entry:{unit_cost:'3.125',currency:'HKD',price_reference:'成本凭据A'}}}}
const snapshot:PeriodSnapshot={month:'2026-10',start:order.start,end:order.end,orders:[order],allocations:[row],costs:{HKD:{ending_completed:'4.69',ending_wip:'1.56'}},blockers:[],notices:[],previous_month:null,previous_lock_id:null,generated_at:'保存时间'}
const comparison:PeriodComparison={previous_id:'save-1',previous_version:1,previous_actor:'主管',previous_date:'先前时间',previous_reason:'首版核对',evidence_changed:false,partial_pricing:false,orders:[order],costs:{HKD:{period_normal:'0.00',period_completed:'0.94',ending_wip:'-0.94',period_loss:'0.00'}},rows:[{issue_id:'issue-1',line_id:'line-1',before:{...row,completed_quantity:'1.2'},after:row,quantity_delta:{completed_quantity:'0.3',ending_wip_quantity:'-0.3'},amount_delta:{ending_completed:'0.94',ending_wip:'-0.94'}}]}
async function router(){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/:pathMatch(.*)*',component:{template:'<div />'}}]});await router.push('/');await router.isReady();return router}

describe('monthly review details',()=>{
  it('filters by customer, order and product name while preserving whole-month comparison totals',async()=>{
    const wrapper=mount(CuttingPeriodReview,{props:{snapshot,comparison,query:''},global:{plugins:[await router()]}})
    for(const query of ['甲客户','order-1','蓝色衣服']){
      await wrapper.setProps({query});expect(wrapper.get('[aria-label="原实发完工与在制费用"] tbody').text()).toContain('issue-1')
    }
    await wrapper.setProps({query:'其他客户'})
    expect(wrapper.get('[aria-label="原实发完工与在制费用"] tbody').text()).toBe('')
    expect(wrapper.get('[aria-label="整月版本金额差异"]').text()).toContain('-0.94')
    expect(wrapper.text()).toContain('当前筛选范围暂无实发明细')
    await wrapper.setProps({query:''})
    expect(wrapper.text()).toContain('成本凭据A');expect(wrapper.text()).toContain('与上一编制版本 V1 比较')
    expect(wrapper.findAll('a').find(link=>link.text()==='issue-1')!.attributes('href')).toContain('focus_id=issue-1')
    wrapper.unmount()
  })
  it('distinguishes pending costs from known zero and displays partial comparison warnings',async()=>{
    const wrapper=mount(CuttingPeriodReview,{props:{snapshot:{...snapshot,allocations:[{...row,amounts:undefined,currency:undefined,price:null}]},comparison:{...comparison,partial_pricing:true,rows:[{...comparison.rows[0]!,before:null,amount_delta:null}]},query:''},global:{plugins:[await router()]}})
    expect(wrapper.get('[aria-label="原实发完工与在制费用"]').text()).toContain('待计价')
    expect(wrapper.text()).toContain('不代表完整费用变化');expect(wrapper.text()).toContain('不直接计算此行金额差额')
    wrapper.unmount()
  })
  it('renders legacy saved evidence without unfrozen or live-price wording',async()=>{
    const wrapper=mount(CuttingClosingReport,{props:{value:{...order,materials:[{issue_id:row.issue_id,context:row.context,price:row.price,opening_quantity:'0',issued_quantity:'4',unsigned_quantity:'0',received_quantity:'4',returned_quantity:'0',consumed_quantity:'2',loss_quantity:'0.5',ending_quantity:'1.5'}]},storedSnapshot:true},global:{plugins:[await router()]}})
    await wrapper.findAll('button').find(button=>button.text()==='本版本材料费用')!.trigger('click')
    expect(wrapper.text()).toContain('本版本保存单价')
    expect(wrapper.text()).not.toContain('尚未冻结');expect(wrapper.text()).not.toContain('当前归集待办');expect(wrapper.text()).not.toContain('当前单价');expect(wrapper.text()).not.toContain('当前计划版本')
    await wrapper.findAll('button').find(button=>button.text()==='来源及更正追溯')!.trigger('click')
    expect(wrapper.text()).toContain('取数时生效记录');expect(wrapper.text()).not.toContain('最新生效记录')
    await wrapper.findAll('button').find(button=>button.text()==='本版本材料费用')!.trigger('click')
    await wrapper.setProps({storedSnapshot:false})
    expect(wrapper.text()).toContain('当前单价');expect(wrapper.text()).toContain('当前归集待办')
    wrapper.unmount()
  })
})

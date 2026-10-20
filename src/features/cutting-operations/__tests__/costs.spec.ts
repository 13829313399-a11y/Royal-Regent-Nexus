vi.mock('../workspaceApi',()=>import('./workspaceFixtures'))
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import CuttingCostsPage from '../CuttingCostsPage.vue'
import { CUTTING_WORKSPACES } from '../navigation'
import { cuttingApi, type Access } from '../api'
import { ordersApi, type CuttingOrder } from '../ordersApi'
import { usageApi } from '../usageApi'
vi.mock('../api',async original=>({...await original<typeof import('../api')>(),cuttingApi:{access:vi.fn()}}))
vi.mock('../ordersApi',()=>({ordersApi:{list:vi.fn()}}))
vi.mock('../usageApi',()=>({usageApi:{read:vi.fn(),post:vi.fn(),recover:vi.fn()}}))
const rights:Access={enabled:true,schema_ready:true,usage_schema_ready:true,permissions:['read','cost_read']}
const order:CuttingOrder={line_id:'line',dispatch_id:'d',source_version:1,snapshot:{reference_no:'ORDER-1',product_no:'P1',customer_name:'合成客户'},received_at:'',needs_receipt:false,current:{version:1,actor_id:'a',created_at:'',reason:'',data:{order:{},dispatch_id:'d',bom:null,requisition:null,batches:[],purchase_reconciliation_required:false}}}
let wrapper:VueWrapper
async function open(){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:CuttingCostsPage,props:{workspace:CUTTING_WORKSPACES.find(w=>w.path==='costs')}}]});await router.push('/');await router.isReady();wrapper=mount(RouterView,{global:{plugins:[router]}});await flushPromises()}
beforeEach(()=>{vi.resetAllMocks();vi.mocked(cuttingApi.access).mockResolvedValue(rights);vi.mocked(ordersApi.list).mockResolvedValue({data:[order],total:1,page:1,page_size:50});vi.mocked(usageApi.read).mockResolvedValue({revision:0,issues:[],documents:[],amounts:{},pending_pricing:0})})
afterEach(()=>wrapper?.unmount())
describe('P3b cost workspace access and asynchronous navigation',()=>{
  it('removes old selectable rows while permission refresh is in flight',async()=>{
    await open();expect(wrapper.text()).toContain('ORDER-1')
    let resolve!:(v:Access)=>void;vi.mocked(cuttingApi.access).mockReturnValueOnce(new Promise(r=>resolve=r))
    await wrapper.findAll('form').at(-1)!.trigger('submit');await flushPromises()
    expect(wrapper.findAll('button').some(b=>b.text()==='查看耗用与费用')).toBe(false)
    resolve({...rights,permissions:['read']});await flushPromises()
    expect(wrapper.text()).toContain('单独授予成本查询权限');expect(usageApi.read).not.toHaveBeenCalled()
  })
  it('does not query business rows until migration and cost-read authority are ready',async()=>{
    vi.mocked(cuttingApi.access).mockResolvedValue({...rights,usage_schema_ready:false})
    await open();expect(wrapper.text()).toContain('0156');expect(ordersApi.list).not.toHaveBeenCalled()
  })
})

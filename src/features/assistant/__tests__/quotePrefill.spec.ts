import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import AssistantQuotePrefill from '../AssistantQuotePrefill.vue'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { internalQuoteApi } from '@/api/internalQuote'
import InternalQuoteHeaderDialog from '@/components/modules/sales/internal-quote/InternalQuoteHeaderDialog.vue'
import type { InternalQuote } from '@/types/internalQuoteDesk'
import type { AuthMeResponse } from '@/api/auth'
import type { ApiInternalQuote } from '@/api/internalQuote'
import { assistantApi } from '../api'
import { clearQuotePrefill, consumeQuotePrefill, invalidateQuotePrefill, prepareQuotePrefill, quotePrefillFor, quotePrefillTargets, type QuoteSuggestion } from '../quotePrefill'
import type { Message, Snapshot } from '../types'

const action={type:'open_record' as const,route_name:'internal-quote-collaboration',label:'打开原报价',params:{quoteId:'q'},query:{factory:'huakang-a'},resource:{module_id:'internal-quote',resource_type:'quote',resource_id:'q'}}
function answer():Message {return {id:'a',run_id:'r',seq:2,role:'assistant',status:'completed',help_citations:[],context_descriptor:null,created_at:1,content_parts:[{type:'text',text:'请核对数量。'},{type:'business_snapshot',result:{contract_version:3,tool_name:'get_internal_quote_overview',rows:[{id:'q',factory_id:'huakang-a',header_revision:7,quote_no:'合成报价',version_label:'A-V1',resource_ref:'internal-quote:quote:q'}]}},{type:'actions',items:[action]}]}}
const snapshot=():Snapshot=>({run_id:'r',session_id:'s',state:'completed',usage:{total_tokens:1},error_code:null,context_window:{},items:[answer()]})
const native={id:'q',factory_id:'huakang-a',header_revision:7,module_version:'v4',status:'drafting',version_archived:false,final_release_status:'draft'} as ApiInternalQuote
const suggestion:QuoteSuggestion={quoteId:'q',factoryId:'huakang-a',headerRevision:7,actionIndex:0,label:'合成报价',runId:'r',text:'核对原数量和单位。'}
let wrappers: ReturnType<typeof mount>[]=[]
beforeEach(()=>{
 vi.restoreAllMocks();setActivePinia(createPinia());clearQuotePrefill()
 useAuthStore().currentUser={id:'actor',identity:{employment_epoch:1,effective_context_key:'scope-a'}} as AuthMeResponse
 vi.spyOn(useAuthStore(),'can').mockReturnValue(true)
 vi.spyOn(assistantApi,'snapshot').mockImplementation(async()=>snapshot())
 vi.spyOn(assistantApi,'action').mockResolvedValue(action)
 vi.spyOn(internalQuoteApi,'get').mockResolvedValue(native)
})
afterEach(()=>{clearQuotePrefill();wrappers.forEach(w=>w.unmount());wrappers=[];document.body.innerHTML='';vi.useRealTimers()})

it('accepts only a server snapshot target with the matching registered original-record action',async()=>{
 const message=answer();expect(quotePrefillTargets(message)).toHaveLength(1)
 const target=quotePrefillTargets(message)[0]!
 await prepareQuotePrefill('r',target,'人工核对的备注')
 expect(quotePrefillFor('q','huakang-b')).toBeNull()
 const result=await consumeQuotePrefill('q','huakang-a',7,()=>true)
 expect(result.text).toBe('人工核对的备注');expect(quotePrefillFor('q','huakang-a')).toBeNull()
 expect(internalQuoteApi.get).toHaveBeenCalledOnce()
 message.content_parts=message.content_parts.filter(p=>p.type!=='actions');expect(quotePrefillTargets(message)).toEqual([])
})

it.each(['permission','revision','source','identity','archive'] as const)('blocks local handoff after %s changes',async change=>{
 const target=quotePrefillTargets(answer())[0]!
 await prepareQuotePrefill('r',target,'私有来源文字')
 if(change==='revision') vi.mocked(internalQuoteApi.get).mockResolvedValue({...native,header_revision:8})
 if(change==='archive') vi.mocked(internalQuoteApi.get).mockResolvedValue({...native,version_archived:true})
 if(change==='source') vi.mocked(assistantApi.snapshot).mockResolvedValue({...snapshot(),items:[{...answer(),unavailable:true}]})
 if(change==='identity') {useAuthStore().currentUser={id:'other',identity:{employment_epoch:1}} as AuthMeResponse;invalidateQuotePrefill()}
 await expect(consumeQuotePrefill('q','huakang-a',7,()=>change!=='permission')).rejects.toThrow()
 if(change==='identity') expect(quotePrefillFor('q','huakang-a')).toBeNull()
 if(change==='permission' || change==='identity' || change==='source') expect(internalQuoteApi.get).not.toHaveBeenCalled()
})

it('expires in memory and rejects a native read that completes after its scope changed',async()=>{
 vi.useFakeTimers();await prepareQuotePrefill('r',quotePrefillTargets(answer())[0]!,'临时建议')
 await vi.advanceTimersByTimeAsync(5*60_000);expect(quotePrefillFor('q','huakang-a')).toBeNull();vi.useRealTimers()
 await prepareQuotePrefill('r',quotePrefillTargets(answer())[0]!,'另一次建议')
 let resolve!:(q:ApiInternalQuote)=>void
 vi.mocked(internalQuoteApi.get).mockImplementation(()=>new Promise(done=>{resolve=done}))
 const consuming=consumeQuotePrefill('q','huakang-a',7,()=>true)
 await Promise.resolve();await Promise.resolve()
 useAuthStore().authorizationVersion++;invalidateQuotePrefill()
 resolve(native);await expect(consuming).rejects.toThrow('身份')
})

function dialog(remark='已有原备注',value=suggestion){
 const quote={id:'q',factoryId:'huakang-a',headerRevision:7,quoteNo:'合成报价',versionLabel:'A-V1',productName:'合成产品',customer:'合成客户',quantity:100,businessOwnerId:'owner',businessOwner:'负责人',targetCustomerPrice:'无',targetDate:'',remark} as InternalQuote
 const w=mount(InternalQuoteHeaderDialog,{attachTo:document.body,props:{open:true,quote,businessOwners:[{id:'owner',username:'owner',displayName:'负责人'}],customers:['合成客户'],assistantSuggestion:value}});wrappers.push(w);return {w,quote}
}
it('appends plain text only after the native confirmation and preserves original fields and submit flow',async()=>{
 const {w,quote}=dialog()
 const remark=()=>document.querySelector<HTMLTextAreaElement>('.quote-header-grid textarea')!.value
 expect(remark()).toBe('已有原备注');expect(w.emitted('confirm')).toBeUndefined()
 const append=[...document.querySelectorAll<HTMLButtonElement>('button')].find(b=>b.textContent==='追加到备注（未保存）')!
 append.click();await w.vm.$nextTick()
 expect(remark()).toBe('已有原备注\n\n核对原数量和单位。');expect(quote.remark).toBe('已有原备注');expect(append.disabled).toBe(true)
 expect(w.emitted('confirm')).toBeUndefined();expect(internalQuoteApi.get).not.toHaveBeenCalled()
 const save=[...document.querySelectorAll<HTMLButtonElement>('button')].find(b=>b.textContent==='保存报价资料')!
 save.click();await w.vm.$nextTick();expect(w.emitted('confirm')?.[0]?.[0]).toEqual(expect.objectContaining({revision:7,remark:'已有原备注\n\n核对原数量和单位。',qty:100}))
})
it('keeps the original remark when appending would overflow its native 4000-character limit',async()=>{
 const {w}=dialog('原'.repeat(3995))
 ;[...document.querySelectorAll<HTMLButtonElement>('button')].find(b=>b.textContent==='追加到备注（未保存）')!.click();await w.vm.$nextTick()
 expect(document.querySelector<HTMLTextAreaElement>('.quote-header-grid textarea')!.value).toBe('原'.repeat(3995))
 expect(document.body.textContent).toContain('4000字上限');expect(w.emitted('confirm')).toBeUndefined()
})
it('disables the local append and original save when the native form becomes read-only',async()=>{
 const {w}=dialog()
 await w.setProps({editable:false})
 const append=[...document.querySelectorAll<HTMLButtonElement>('button')].find(b=>b.textContent==='追加到备注（未保存）')!
 const save=[...document.querySelectorAll<HTMLButtonElement>('button')].find(b=>b.textContent==='保存报价资料')!
 expect(append.disabled).toBe(true);expect(save.disabled).toBe(true)
 expect(document.querySelector<HTMLTextAreaElement>('.quote-header-grid textarea')!.value).toBe('已有原备注')
})
it('hands back to an already open original route without treating duplicate navigation as a dirty-form refusal',async()=>{
 const router=createRouter({history:createMemoryHistory(),routes:[{path:'/quote/:quoteId',name:'internal-quote-collaboration',component:{template:'<div>原报价</div>'}}]})
 await router.push({name:'internal-quote-collaboration',params:{quoteId:'q'},query:{factory:'huakang-a'}});await router.isReady()
 const w=mount(AssistantQuotePrefill,{props:{message:answer()},global:{plugins:[router]}});wrappers.push(w)
 await w.get('button').trigger('click');await w.get('textarea').setValue('已核对的备注建议')
 await w.findAll('button').find(b=>b.text()==='打开原报价核对')!.trigger('click');await flushPromises()
 expect(w.emitted('prepared')).toHaveLength(1);expect(quotePrefillFor('q','huakang-a')?.text).toBe('已核对的备注建议')
 expect(internalQuoteApi.get).not.toHaveBeenCalled()
})
it('does not offer a native header handoff to an actor whose original page has no financial form access',()=>{
 vi.mocked(useAuthStore().can).mockImplementation(permission=>permission==='internal_quote:header_edit')
 const w=mount(AssistantQuotePrefill,{props:{message:answer()}});wrappers.push(w)
 expect(w.find('button').exists()).toBe(false)
})

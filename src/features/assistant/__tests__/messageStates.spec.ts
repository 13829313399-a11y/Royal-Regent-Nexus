import { expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { defineComponent, h, ref } from 'vue'
import AssistantMessage from '../AssistantMessage.vue'
import type { Message } from '../types'
import { assistantApi } from '../api'
import AssistantContext from '../AssistantContext.vue'

it('labels legacy help honestly while preserving the historical text',()=>{
  const router=createRouter({history:createMemoryHistory(),routes:[]})
  const message:Message={id:'legacy',run_id:'run',seq:2,role:'assistant',status:'completed',created_at:1,
    help_citations:[{id:'help',version:'v1'}],context_descriptor:null,help_verification:'legacy_version_only',content_parts:[{type:'text',text:'历史说明原文'}]}
  const w=mount(AssistantMessage,{props:{message},global:{plugins:[router]}})
  expect(w.text()).toContain('历史说明原文');expect(w.text()).toContain('未保存来源指纹');expect(w.text()).toContain('不会作为新回答的依据')
  w.unmount()
})

it('renders the persisted output-limit notice separately from exact model text after reload',()=>{
  const router=createRouter({history:createMemoryHistory(),routes:[]})
  const message:Message={id:'saved',run_id:'run',seq:2,role:'assistant',status:'completed',created_at:1,
    help_citations:[],context_descriptor:null,content_parts:[{type:'text',text:'原文保留[ref_'},{type:'run_notice',code:'output_limit',text:'回答达到模型输出上限，可能尚未完整。'}]}
  const w=mount(AssistantMessage,{props:{message},global:{plugins:[router]}})
  expect(w.get('.yl-markdown').text()).toBe('原文保留[ref_')
  expect(w.get('.yl-notice').text()).toContain('模型输出上限');w.unmount()
})

it('does not offer artifact/export/navigation actions for an unavailable answer',async()=>{
  const router=createRouter({history:createMemoryHistory(),routes:[]})
  const message: Message={id:'saved-answer',run_id:'run',seq:2,role:'assistant',status:'completed',created_at:1,help_citations:[],context_descriptor:null,unavailable:true,content_parts:[{type:'text',text:'资料已删除或授权已改变。'}]}
  const w=mount(AssistantMessage,{props:{message},global:{plugins:[router]}})
  expect(w.text()).toContain('资料已删除或授权已改变')
  expect(w.text()).not.toContain('导出 Markdown');expect(w.text()).not.toContain('保存成果')
  await w.setProps({message:{...message,unavailable:false}})
  await w.get('[aria-label="更多回答操作"]').trigger('keydown',{key:'ArrowDown'});await flushPromises()
  const labels=[...document.querySelectorAll('[role="menuitem"]')].map(el=>el.textContent)
  expect(labels).toContain('导出 Markdown');expect(labels).toContain('保存成果')
  w.unmount()
})

it('uses the actual business scope and keeps collapsed action indexes bound to the server',async()=>{
  const actions=Array.from({length:21},(_,i)=>({type:'open_record' as const,label:i===0?'打开当前事项列表':`打开事项 ${i}`,route_name:'notification-center',params:{},query:{entry:String(i)},resource:{module_id:'work-center',resource_type:'entry',resource_id:String(i)}}))
  const resolve=vi.spyOn(assistantApi,'action').mockResolvedValue(actions[20]!)
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/notifications',name:'notification-center',component:{template:'<div />'}}]})
  const message:Message={id:'saved',run_id:'run',seq:2,role:'assistant',status:'completed',created_at:1,help_citations:[],context_descriptor:{module_id:'work-center',route_name:'notification-center',factory_id:'huakang-a'},content_parts:[{type:'text',text:'共有 26 项未读事项。'},{type:'business_snapshot',result:{scope:{label:'本人全部授权范围 / 当前事项筛选'}}},{type:'actions',items:actions}]}
  const w=mount(AssistantMessage,{props:{message},global:{plugins:[router]}})
  expect(w.get('.yl-frozen-context').text()).toContain('本人全部授权范围')
  expect(w.get('.yl-more-actions').attributes('open')).toBeUndefined()
  expect(w.get('.yl-more-actions summary').text()).toBe('其余 18 个入口')
  await w.get('.yl-more-actions summary').trigger('click')
  await w.findAll('.yl-more-actions button')[17]!.trigger('click');await flushPromises()
  expect(resolve).toHaveBeenCalledWith('run',20)
  expect(router.currentRoute.value.query.entry).toBe('20')
  w.unmount();resolve.mockRestore()
})

it('labels the effective selected factory instead of the unrelated page factory',()=>{
  const w=mount(AssistantContext,{props:{changed:false,currentTitle:'事项工作台',scope:{page:{module_id:'work-center',route_name:'notification-center',factory_id:'huakang-a'},title:'事项工作台',selection:{selection_id:'filters',resources:[],filters:{factory_id:'authorized',unread_only:true}}}}})
  expect(w.get('[aria-label="查看本轮范围"]').text()).toContain('本人全部授权范围')
  expect(w.get('[aria-label="查看本轮范围"]').text()).not.toContain('华康A')
  w.unmount()
})

it('opens the server-authorized quote version and stays put when its source is revoked', async()=>{
  const action={type:'open_record' as const,label:'打开原报价',route_name:'internal-quote-collaboration',
    params:{quoteId:'original-version'},query:{factory:'huakang-a'},resource:{module_id:'internal-quote',resource_type:'quote',resource_id:'original-version'}}
  const resolve=vi.spyOn(assistantApi,'action').mockResolvedValue(action)
  const router=createRouter({history:createMemoryHistory(),routes:[
    {path:'/',component:{template:'<div />'}},
    {path:'/quotes/:quoteId/collaboration',name:'internal-quote-collaboration',component:{template:'<div />'}},
  ]})
  await router.push('/')
  const message:Message={id:'saved-quote',run_id:'quote-run',seq:2,role:'assistant',status:'completed',created_at:1,
    help_citations:[],context_descriptor:null,content_parts:[{type:'text',text:'原报价版本快照'},
      {type:'actions',items:[{...action,params:{quoteId:'client-cached-version'}}]}]}
  const w=mount(AssistantMessage,{props:{message},global:{plugins:[router]}})
  const open=w.findAll('button').find(b=>b.text()==='打开原报价')!
  try {
    await open.trigger('click');await flushPromises()
    expect(resolve).toHaveBeenCalledWith('quote-run',0)
    expect(router.currentRoute.value.fullPath).toBe('/quotes/original-version/collaboration?factory=huakang-a')
    await router.push('/')
    resolve.mockRejectedValueOnce(new Error('原报价版本已不可用，请重新查询。'))
    await open.trigger('click');await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/')
    expect(w.text()).toContain('原报价版本已不可用，请重新查询。')
  } finally { w.unmount();resolve.mockRestore() }
})

it('releases the assistant modal before navigating to an authorized original and retains it on resolver failure',async()=>{
  const action={type:'open_record' as const,label:'打开原记录',route_name:'original',params:{},query:{id:'server-authorized'},resource:{module_id:'uv-operations',resource_type:'task',resource_id:'original'}}
  const resolve=vi.spyOn(assistantApi,'action').mockResolvedValue(action)
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:{template:'<div />'}}]})
  await router.push('/')
  const collapsed=ref(false)
  const message:Message={id:'saved-original',run_id:'original-run',seq:2,role:'assistant',status:'completed',created_at:1,help_citations:[],context_descriptor:null,content_parts:[{type:'text',text:'原查询回答'},{type:'actions',items:[action]}]}
  const Parent=defineComponent({setup:()=>()=>h('div',[
    !collapsed.value && h('div',{'aria-modal':'true'},'助手模态'),
    h(AssistantMessage,{message,onNativeForm:()=>{collapsed.value=true}}),
  ])})
  const w=mount(Parent,{global:{plugins:[router]}})
  const navigate=vi.spyOn(router,'push').mockImplementation(async()=>{
    expect(w.find('[aria-modal="true"]').exists()).toBe(false)
  })
  try {
    const open=w.findAll('button').find(b=>b.text()==='打开原记录')!
    await open.trigger('click');await flushPromises()
    expect(resolve).toHaveBeenCalledWith('original-run',0)
    expect(navigate).toHaveBeenCalledWith({name:'original',params:{},query:{id:'server-authorized'}})
    expect(w.getComponent(AssistantMessage).emitted('nativeForm')).toHaveLength(1)
    collapsed.value=false;await flushPromises();navigate.mockClear()
    resolve.mockRejectedValueOnce(new Error('原记录授权已改变'))
    await open.trigger('click');await flushPromises()
    expect(navigate).not.toHaveBeenCalled()
    expect(w.find('[aria-modal="true"]').exists()).toBe(true)
    expect(w.getComponent(AssistantMessage).emitted('nativeForm')).toHaveLength(1)
    expect(w.text()).toContain('原记录授权已改变')
  } finally {w.unmount();navigate.mockRestore();resolve.mockRestore()}
})

it.each(['fallback','native-focus','assistant-focus','same-record','guard-cancel','native-modal'] as const)('gives an original a main focus fallback while respecting native focus and guards (%s)',async scenario=>{
  const app=document.createElement('div');app.id='app'
  const main=document.createElement('main'),button=document.createElement('button');button.textContent='原单操作';main.append(button);app.append(main);document.body.append(app)
  const assistant=document.createElement('div');assistant.className='yl-assistant'
  const oldButton=document.createElement('button');assistant.append(oldButton);document.body.append(assistant)
  const modal=document.createElement('div');modal.setAttribute('aria-modal','true');modal.getClientRects=()=>({length:1}) as DOMRectList
  if(scenario==='native-modal')document.body.append(modal)
  main.getClientRects=()=>({length:1}) as DOMRectList
  const action={type:'open_record' as const,label:'打开原记录',route_name:'original',params:{},query:{},resource:{module_id:'internal-quote',resource_type:'quote',resource_id:'original'}}
  const resolve=vi.spyOn(assistantApi,'action').mockResolvedValue(action)
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',name:'home',component:{template:'<div />'}},{path:'/original',name:'original',component:{template:'<div />'}}]})
  await router.push(scenario==='same-record'?'/original':'/')
  if(scenario==='guard-cancel')router.beforeEach(to=>to.name==='original'?false:true)
  const originalPush=router.push.bind(router)
  const navigate=vi.spyOn(router,'push').mockImplementation(async target=>{
    if(scenario==='native-focus')button.focus()
    if(scenario==='assistant-focus')oldButton.focus()
    if(scenario==='same-record'||scenario==='guard-cancel')return originalPush(target)
  })
  const message:Message={id:'saved-original',run_id:'original-run',seq:2,role:'assistant',status:'completed',created_at:1,help_citations:[],context_descriptor:null,content_parts:[{type:'text',text:'原回答'},{type:'actions',items:[action]}]}
  const w=mount(AssistantMessage,{props:{message},global:{plugins:[router]}})
  try {
    await w.findAll('button').find(b=>b.text()==='打开原记录')!.trigger('click');await flushPromises()
    expect(document.activeElement).toBe(['guard-cancel','native-modal'].includes(scenario)?document.body:scenario==='native-focus'?button:main)
  } finally {w.unmount();app.remove();assistant.remove();modal.remove();navigate.mockRestore();resolve.mockRestore()}
})

it('shows the readable injection scope while retaining raw native queries only in the frozen payload', async()=>{
  const w=mount(AssistantContext,{props:{changed:false,currentTitle:'注塑排期',scope:{page:{module_id:'injection-scheduling',route_name:'injection-scheduling',factory_id:'huakang-a'},title:'注塑排期',selection:{selection_id:'filters',resources:[],filters:{factory_id:'huakang-a',query_summary:'需求状态 = 待料；模号前缀 SYN-',filter_json:'{"field":"dispatch_state"}',search_json:'{"text":"SYN-"}',sort_json:'[]'}}}}})
  await w.get('[aria-label="查看本轮范围"]').trigger('click')
  expect(w.text()).toContain('列表范围')
  expect(w.text()).toContain('模号前缀 SYN-')
  expect(w.text()).not.toContain('dispatch_state')
  expect(w.text()).not.toContain('filter_json')
  w.unmount()
})

import { expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import AssistantBusinessFacts from '../AssistantBusinessFacts.vue'
import { businessFacts } from '../businessFacts'
import type { Message } from '../types'

const message = (): Message => ({
  id:'answer',run_id:'owned-run',seq:1,role:'assistant',status:'completed',created_at:1,help_citations:[],context_descriptor:null,
  content_parts:[{type:'text',text:'原始解释保持不变'},
    {type:'evidence',run_id:'owned-run',sources:[{kind:'business',run_id:'owned-run',source_id:'registered',tool_name:'get_injection_overview',title:'注塑需求'}]},
    {type:'business_snapshot',result:{contract_version:3,tool_name:'get_injection_overview',run_id:'owned-run',tool_call_id:'call',step_id:'step',status:'partial',
      source_refs:['registered'],scope:{module_id:'injection-scheduling',label:'华康 A / 已筛选需求'},as_of:'2026-10-26T18:28:10+08:00',observed_at:null,
      retrieved_at:'2026-10-26T18:28:11+08:00',timezone:'Asia/Shanghai',freshness:{state:'fresh'},total_count:3,returned_count:3,truncated:false,
      metrics:{held_count:{value:2,unit:'需求行',definition_id:'held',status:'known'},wait_material_count:{value:1,unit:'需求行',definition_id:'wait',status:'known'},
        remaining_material_kg:{value:'120.500000000000000001',unit:'kg',definition_id:'material',status:'known'},
        remaining_material_unknown_count:{value:0,unit:'需求行',definition_id:'unknown-count',status:'known'},
        warehouse_shortage_kg:{value:null,unit:'kg',definition_id:'warehouse',status:'unknown'},
        actual_delivery_late_count:{value:null,unit:'需求行',definition_id:'delivery',status:'unknown'}},
      definitions:{held:'非 READY，包含待料和其他原因，不等于缺料。',wait:'恰为 WAIT_MATERIAL，只是排产标记。',material:'预计生产用料，不是仓库缺口。',
        'unknown-count':'用料为空的需求行数。',warehouse:'未读取仓库可用量。',delivery:'未读取实际交货结果。'},unknown_fields:[{field:'warehouse_shortage_kg',reason:'库存来源未接入'}]}}],
})
const raw = (m: Message) => m.content_parts[2]!.result as Record<string, any>

it('renders held and WAIT independently, preserves exact decimals and distinguishes unknown from zero', () => {
  const m=message(), original=JSON.stringify(m)
  const panel=businessFacts(m)[0]!
  expect(panel.primary.find(x=>x.key==='held_count')).toMatchObject({label:'挂起（含待料）',value:'2'})
  expect(panel.primary.find(x=>x.key==='wait_material_count')).toMatchObject({label:'待料标记',value:'1'})
  expect(panel.primary.find(x=>x.key==='remaining_material_kg')?.value).toBe('120.500000000000000001')
  expect(panel.primary.find(x=>x.key==='warehouse_shortage_kg')?.value).toBe('未知')
  expect(panel.metrics.find(x=>x.key==='remaining_material_unknown_count')?.value).toBe('0')
  expect(panel.metrics.find(x=>x.key==='held_count')?.definition).toContain('不等于缺料')
  expect(JSON.stringify(m)).toBe(original)
})

it.each(['unavailable','user','other-run','other-tool','unregistered','ineligible','forbidden','failed','not_connected','legacy'])(
  'does not project stale or unregistered facts: %s', boundary => {
    const m=message(), r=raw(m), evidence=m.content_parts[1]!
    if(boundary==='unavailable') m.unavailable=true
    if(boundary==='user') m.role='user'
    if(boundary==='other-run') r.run_id='another-run'
    if(boundary==='other-tool') (evidence.sources as any[])[0].tool_name='get_my_work'
    if(boundary==='unregistered') r.source_refs.push('missing')
    if(boundary==='ineligible') (evidence.sources as any[])[0].citation_eligible=false
    if(['forbidden','failed','not_connected'].includes(boundary)) r.status=boundary
    if(boundary==='legacy') r.contract_version=2
    expect(businessFacts(m)).toEqual([])
  })

it('shows existing tool facts while explanation streams and removes them immediately when unavailable', async () => {
  const m=message();m.status='answering'
  const w=mount(AssistantBusinessFacts,{props:{message:m}})
  expect(w.find('section').exists()).toBe(true)
  await w.setProps({message:{...m,unavailable:true}})
  expect(w.find('section').exists()).toBe(false)
  w.unmount()
})

it('keeps mixed units as separate server metrics without totals or conversions', () => {
  const m=message(), r=raw(m)
  r.tool_name='get_carton_overview';r.scope.module_id='carton-procurement'
  ;(m.content_parts[1]!.sources as any[])[0].tool_name=r.tool_name
  r.metrics={'remaining_quantity[个]':{value:'400',unit:'个',definition_id:'paper',status:'known'},
    'remaining_quantity[套]':{value:'7',unit:'套',definition_id:'paper',status:'known'},
    available_quantity:{value:null,unit:'未确定',definition_id:'warehouse',status:'not_applicable'}}
  r.definitions.paper='按纸品原单位统计。'
  expect(businessFacts(m)[0]!.primary.map(x=>[x.value,x.unit])).toEqual([['400','个'],['7','套'],['不适用','未确定']])
})

it('keeps observation and query clocks independent and shows stale telemetry', () => {
  const m=message(), r=raw(m)
  r.tool_name='get_printer_status';r.scope.module_id='three-d-printing'
  ;(m.content_parts[1]!.sources as any[])[0].tool_name=r.tool_name
  r.freshness.state='stale';r.observed_at='2026-10-26T18:13:10+08:00'
  r.metrics={physically_stopped_count:{value:null,unit:'台',definition_id:'stopped',status:'unknown'}}
  r.definitions.stopped='过期遥测不能证明物理停机。'
  const w=mount(AssistantBusinessFacts,{props:{message:m}})
  expect(w.text()).toContain('观测已过期')
  expect(w.text()).toContain('设备观测：2026-10-26 18:13:10+08:00')
  expect(w.text()).toContain('数据时点：2026-10-26 18:28:10+08:00')
  expect(w.get('.yl-facts-grid dd').text()).toBe('未知 台')
  w.unmount()
})

it('escapes source fields, emits the existing source action and preserves the original response', async () => {
  const m=message();raw(m).scope.label='<script>bad()</script>'
  const w=mount(AssistantBusinessFacts,{props:{message:m}})
  expect(w.find('script').exists()).toBe(false)
  expect(w.text()).toContain('<script>bad()</script>')
  await w.get('button').trigger('click')
  expect(w.emitted('sources')).toHaveLength(1)
  expect(m.content_parts[0]!.text).toBe('原始解释保持不变')
  w.unmount()
})

it('rejects malformed metrics rather than coercing null, NaN, unsafe integers or unknowns to zero', () => {
  for(const value of [null,NaN,Infinity,Number.MAX_SAFE_INTEGER+1,'1e6','<b>4</b>']) {
    const m=message(), r=raw(m)
    r.metrics={held_count:{value,unit:'需求行',definition_id:'held',status:'known'}}
    expect(businessFacts(m)).toEqual([])
  }
})

it('labels an unknown unit explicitly and uses the existing factory name without altering the original scope or units', () => {
  const m=message(),r=raw(m)
  r.scope.label='huakang-a / 选中需求'
  r.metrics.warehouse_shortage_kg.unit='未确定'
  const before=JSON.stringify(r)
  const w=mount(AssistantBusinessFacts,{props:{message:m}})
  expect(w.get('.yl-facts-scope').text()).toBe('华康A / 选中需求')
  expect(w.text()).toContain('未知 单位未确定')
  expect(JSON.stringify(r)).toBe(before)
  w.unmount()
})

it('separates spray WIP, awaiting disposition, scrap and rework and exposes unknown financial metrics outside collapsed details', () => {
  const m=message(),r=raw(m)
  r.tool_name='get_spray_operations_snapshot';r.scope.module_id='spray-production'
  ;(m.content_parts[1]!.sources as any[])[0].tool_name=r.tool_name
  const values={finished:'150.000000',scrap:'10.000000',rework_current:'0',wip:'0',in_process:'140.000000',material_shortage:null,settled_amount:null}
  r.metrics=Object.fromEntries(Object.entries(values).map(([key,value])=>[key,{value,unit:value===null?'未明确':'件',status:value===null?'unknown':'known',definition_id:key}]))
  r.definitions=Object.fromEntries(Object.keys(values).map(key=>[key,`原定义 ${key}`]))
  const w=mount(AssistantBusinessFacts,{props:{message:m}})
  expect(w.get('.yl-facts-grid').text()).toContain('当前中间工序在制0 件')
  expect(w.get('.yl-facts-grid').text()).toContain('待最终处置库存140.000000 件')
  expect(w.get('.yl-facts-grid').text()).toContain('已生效生产报废10.000000 件')
  expect(w.get('.yl-facts-grid').text()).toContain('当前返工来源库存0 件')
  expect(w.get('.yl-facts-state').text()).toBe('结算金额：未知')
  expect(w.get('details').element.open).toBe(false)
  w.unmount()
})

it('renders registered business tool results with explicit cache and original clocks, without changing the response', () => {
  const m=message(),r=raw(m)
  const beforeText=m.content_parts[0]!.text
  m.content_parts[2]!.type='tool_result';m.content_parts[2]!.name=r.tool_name
  r.freshness={state:'fresh',cache_hit:true,cache_created_at:'2026-10-26T18:28:11+08:00'}
  r.retrieved_at='2026-10-26T18:28:21+08:00'
  const before=JSON.stringify(m)
  const w=mount(AssistantBusinessFacts,{props:{message:m}})
  expect(w.text()).toContain('缓存快照 · 含未知项')
  expect(w.text()).toContain('数据时点：2026-10-26 18:28:10+08:00')
  expect(w.text()).toContain('缓存创建：2026-10-26 18:28:11+08:00')
  expect(w.text()).toContain('读取时点：2026-10-26 18:28:21+08:00')
  expect(w.find('details').element.open).toBe(false)
  expect(JSON.stringify(m)).toBe(before)
  expect(m.content_parts[0]!.text).toBe(beforeText)
  w.unmount()
})

it('deduplicates a tool result also represented by a prequery snapshot and rejects mismatched tool names', () => {
  const m=message(),r=raw(m)
  m.content_parts.push({type:'tool_result',name:r.tool_name,result:structuredClone(r)})
  expect(businessFacts(m)).toHaveLength(1)
  m.content_parts.splice(2,1)
  m.content_parts[2]!.name='get_my_work'
  expect(businessFacts(m)).toEqual([])
})

it.each([{}, {cache_created_at:'not-a-time'}, {cache_created_at:'2026-10-26T18:28:11+08:00',cache_hit:'true'}])(
  'does not label malformed cache metadata as a fresh query: %j', changes => {
    const m=message(),r=raw(m)
    r.freshness={state:'fresh',cache_hit:true,...changes}
    expect(businessFacts(m)).toEqual([])
  })

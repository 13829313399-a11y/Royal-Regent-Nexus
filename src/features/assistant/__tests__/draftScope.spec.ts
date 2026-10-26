import { describe, expect, it } from 'vitest'
import { reactive, ref } from 'vue'
import { useDraftScope } from '../draftScope'
import { registerAssistantSelection } from '../selection'
import { searchUnavailable } from '../searchOptions'
import type { Capabilities, Draft, PageContext } from '../types'

describe('draft scope and explicit search choices',()=>{
  it('explicitly accumulates unique records only within the same page and factory',()=>{
    const draft=reactive<Draft>({text:'原问题',attachments:[],documents:[]})
    const page=ref<PageContext>({module_id:'injection-scheduling',route_name:'injection-scheduling',factory_id:'huakang-a'})
    const selected=ref('a')
    const unregister=registerAssistantSelection('injection-scheduling',()=>({selection_id:selected.value,resources:[{module_id:'injection-scheduling',resource_type:'demand',resource_id:selected.value}],filters:{factory_id:page.value.factory_id ?? null}}))
    try {
      const binding=useDraftScope(()=>draft,()=>page.value,()=> '注塑排产')
      binding.freeze();selected.value='b'
      expect(binding.scope.value.selection?.resources).toHaveLength(1)
      expect(binding.includeCurrent()).toBe('');binding.includeCurrent()
      expect(binding.scope.value.selection?.resources.map(r=>r.resource_id)).toEqual(['a','b'])
      binding.removeSelection(0)
      expect(binding.scope.value.selection?.resources.map(r=>r.resource_id)).toEqual(['b'])
      page.value={...page.value,factory_id:'huakang-b'};selected.value='c';binding.includeCurrent()
      expect(binding.scope.value.selection?.resources.map(r=>r.resource_id)).toEqual(['c'])
      expect(binding.scope.value.page?.factory_id).toBe('huakang-b')
      for(let i=0;i<9;i++){selected.value=String(i);binding.includeCurrent()}
      selected.value='overflow';expect(binding.includeCurrent()).toContain('10 条')
      expect(binding.scope.value.selection?.resources).toHaveLength(10)
    } finally {unregister()}
  })
  it('freezes identifiers and filters, permits per-record removal, and only adopts new scope explicitly',()=>{
    const draft=reactive<Draft>({text:'',attachments:[],documents:[]})
    const page=ref<PageContext|null>({module_id:'injection-scheduling',route_name:'injection-scheduling',factory_id:'huakang-a'})
    const source={selection_id:'selection-a',resources:[{module_id:'injection-scheduling',resource_type:'demand',resource_id:'a'},{module_id:'injection-scheduling',resource_type:'demand',resource_id:'b'}],filters:{status:'READY'}}
    const unregister=registerAssistantSelection('injection-scheduling',()=>source)
    try {
      const binding=useDraftScope(()=>draft,()=>page.value,()=>page.value?.factory_id || '')
      binding.freeze(); draft.text='原问题'
      binding.removeSelection(0)
      expect(source.resources).toHaveLength(2)
      expect(binding.scope.value.selection?.resources.map(r=>r.resource_id)).toEqual(['b'])
      page.value={...page.value!,factory_id:'huakang-b'}
      expect(binding.changed.value).toBe(true)
      expect(binding.scope.value.page?.factory_id).toBe('huakang-a')
      binding.adopt();expect(binding.scope.value.page?.factory_id).toBe('huakang-b')
      binding.removePage();expect(binding.scope.value).toEqual({page:null,title:'自由交流',selection:null})
      expect(draft.text).toBe('原问题')
    } finally { unregister() }
  })
  it('keeps each session draft separate and does not retain a previous identity scope',()=>{
    const drafts=reactive<Record<string,Draft>>({a:{text:'A',attachments:[],documents:[]},b:{text:'B',attachments:[],documents:[]}})
    const id=ref('a'), page=ref<PageContext|null>({module_id:'portal',route_name:'dashboard'})
    const binding=useDraftScope(()=>drafts[id.value]!,()=>page.value,()=> '门户')
    binding.freeze(); page.value=null; id.value='b'
    expect(binding.scope.value.page).toBeNull()
    id.value='a';expect(binding.scope.value.page?.module_id).toBe('portal')
    drafts.a={text:'',attachments:[],documents:[]};expect(binding.scope.value.page).toBeNull()
  })
  it('offers exact verified combinations without silently changing a user search or thinking choice',()=>{
    const caps={search:{supported_modes:['off','auto','on'],verified_combinations:[{input:'text',thinking:'auto'},{input:'text',thinking:'off'}]}} as Capabilities
    expect(searchUnavailable(caps,'auto','auto',false)).toBe('')
    expect(searchUnavailable(caps,'on','on',false)).toContain('尚未验证')
    expect(searchUnavailable(caps,'on','auto',true)).toContain('尚未验证')
    expect(searchUnavailable(null,'off','on',true)).toBe('')
    expect(searchUnavailable(null,'on','auto',false)).toContain('不可用')
  })
})

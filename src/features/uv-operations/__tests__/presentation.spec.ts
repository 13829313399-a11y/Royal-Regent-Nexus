import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { provideUvMotionPreference } from '../composables/useUvMotionPreference'
import { useUvSemanticChanges } from '../composables/useUvSemanticChanges'
import { useUvIndicator } from '../composables/useUvIndicator'
import { useUvReturnFocus } from '../composables/useUvReturnFocus'
import UvTabs from '../components/UvTabs.vue'
import UvPageFrame from '../components/UvPageFrame.vue'
import type { Entity } from '../contracts'
beforeEach(()=>{
 vi.stubGlobal('matchMedia',vi.fn(()=>Object.assign(new EventTarget(),{matches:false})))
 vi.stubGlobal('ResizeObserver',class{observe(){}disconnect(){}})
 vi.spyOn(document,'hidden','get').mockReturnValue(false)
})
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals();vi.useRealTimers();document.body.innerHTML=''})
it('does not highlight timestamps or initial rows; highlights semantic changes once and clears on motion off',async()=>{
 const rows=ref<Entity[]>([{id:'M',version:1,collection_health:'fresh',work_state:'running',current_run_id:'R'}])
 let changes!:Set<string>,motion!:ReturnType<typeof provideUvMotionPreference>
 const child=defineComponent({setup(){changes=useUvSemanticChanges(rows);return()=>h('div')}})
 const v=mount(defineComponent({setup(){motion=provideUvMotionPreference(()=>null);return()=>h(child)}}))
 await nextTick();expect(changes.size).toBe(0)
 for(let i=0;i<3;i++){rows.value=rows.value.map(r=>({...r,observed_at:String(i),version:i+2}));await nextTick();expect(changes.size).toBe(0)}
 rows.value=rows.value.map(r=>({...r,collection_health:'stale'}));await nextTick();expect([...changes]).toEqual(['M'])
 motion.setPreference('off');expect(changes.size).toBe(0);v.unmount()
})
it('cancels a queued indicator frame on hiding/unmount and coalesces resize requests',async()=>{
 const raf=vi.spyOn(window,'requestAnimationFrame').mockReturnValue(11),cancel=vi.spyOn(window,'cancelAnimationFrame')
 let indicator!:ReturnType<typeof useUvIndicator>
 const v=mount(defineComponent({setup(){const root=ref<HTMLElement|null>(null);indicator=useUvIndicator(root,()=> 'a');return()=>h('nav',{ref:root})}}))
 indicator.schedule();indicator.schedule();expect(raf).toHaveBeenCalledTimes(1)
 vi.spyOn(document,'hidden','get').mockReturnValue(true);document.dispatchEvent(new Event('visibilitychange'));expect(cancel).toHaveBeenCalledWith(11)
 indicator.schedule();expect(raf).toHaveBeenCalledTimes(1)
 v.unmount();indicator.schedule();expect(raf).toHaveBeenCalledTimes(1)
})
it('uses manual keyboard tab activation with complete panel associations',async()=>{
 Object.defineProperty(HTMLElement.prototype,'scrollIntoView',{configurable:true,value:vi.fn()})
 const v=mount(UvTabs,{attachTo:document.body,props:{modelValue:'a',tabs:[['a','甲'],['b','乙'],['c','丙']],label:'业务页签'}})
 await v.findAll('[role=tab]')[0]!.trigger('keydown',{key:'End'})
 expect(document.activeElement).toBe(v.findAll('[role=tab]')[2]!.element)
 expect(v.emitted('update:modelValue')).toBeUndefined()
 expect(v.findAll('[role=tab][tabindex="0"]')).toHaveLength(1)
 for(const tab of v.findAll('[role=tab]'))expect(document.getElementById(tab.attributes('aria-controls')!)).not.toBeNull()
 await v.findAll('[role=tab]')[2]!.trigger('click');expect(v.emitted('update:modelValue')).toEqual([['c']]);v.unmount()
})
it('finishes one initial reveal and never replays on visibility or preference return',async()=>{
 vi.useFakeTimers();let motion!:ReturnType<typeof provideUvMotionPreference>
 const v=mount(defineComponent({setup(){motion=provideUvMotionPreference(()=>null);return()=>h(UvPageFrame,{style:'--uv-motion-reveal:260ms;--uv-motion-reveal-max-delay:90ms'},()=>h('section','ready'))}}))
 await nextTick();await vi.advanceTimersByTimeAsync(350);expect(v.find('[data-uv-reveal]').exists()).toBe(false)
 motion.setPreference('off');await nextTick();motion.setPreference('system');await nextTick()
 expect(v.find('[data-uv-reveal]').exists()).toBe(false);v.unmount()
})
it('restores stable focus if a successful refresh later removes the original trigger',async()=>{
 vi.spyOn(HTMLElement.prototype,'getClientRects').mockReturnValue([{width:10,height:10}] as unknown as DOMRectList)
 let focus!:ReturnType<typeof useUvReturnFocus>
 const v=mount(defineComponent({setup(){focus=useUvReturnFocus(ref(null));return()=>h('main',{'data-uv-focus-fallback':'',tabindex:-1},[h('button','match')])}}),{attachTo:document.body})
 const button=v.get('button').element as HTMLElement;button.focus();focus.capture();focus.restore()
 button.remove();await nextTick();await nextTick();expect(document.activeElement).toBe(v.get('main').element)
 v.unmount()
})

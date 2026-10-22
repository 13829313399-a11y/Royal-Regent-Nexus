import { afterEach,it,expect,vi } from 'vitest'
import { mount,flushPromises,type VueWrapper } from '@vue/test-utils'
import ReadTarget from '../CuttingReadTarget.vue'
const target={month:'2026-09',id:'document-'+ 'a'.repeat(64),eventId:'historical-'+ 'b'.repeat(64)}
let wrapper:VueWrapper|undefined
const open=()=>wrapper=mount(ReadTarget,{props:{target,label:'外发结算',retryLabel:'重试原结算记录',readable:true}})
const button=(text:string)=>wrapper!.findAll('button').find(b=>b.text()===text)!
afterEach(()=>{wrapper?.unmount();wrapper=undefined;vi.useRealTimers();vi.unstubAllGlobals()})
it('copies only the explicitly chosen complete identifier and reports success',async()=>{
 const writeText=vi.fn().mockResolvedValue(undefined);vi.stubGlobal('navigator',{clipboard:{writeText}});open()
 expect(writeText).not.toHaveBeenCalled()
 await button('复制单据编号').trigger('click');await flushPromises();expect(writeText).toHaveBeenLastCalledWith(target.id);expect(wrapper!.text()).toContain('单据编号已复制')
 await button('复制历史版本编号').trigger('click');await flushPromises();expect(writeText).toHaveBeenLastCalledWith(target.eventId)
 expect(wrapper!.text()).toContain(target.eventId)
})
it.each([undefined,{writeText:vi.fn().mockRejectedValue(new Error('denied'))}])('offers manual copy when the clipboard is missing or rejects (%s)',async clipboard=>{
 vi.stubGlobal('navigator',{clipboard});open();await button('复制单据编号').trigger('click');await flushPromises()
 expect(wrapper!.text()).toContain('无法自动复制，请选中上方单据编号手动复制');expect(wrapper!.text()).not.toContain('已复制');expect(wrapper!.text()).toContain(target.id)
})
it('blocks copying when busy or no longer authorized and suppresses stale completion',async()=>{
 let resolve!:()=>void
 const writeText=vi.fn(()=>new Promise<void>(r=>resolve=r));vi.stubGlobal('navigator',{clipboard:{writeText}});open()
 await wrapper!.setProps({disabled:true});await button('复制单据编号').trigger('click');expect(writeText).not.toHaveBeenCalled()
 await wrapper!.setProps({disabled:false});await button('复制单据编号').trigger('click')
 await wrapper!.setProps({readable:false});resolve();await flushPromises();expect(wrapper!.text()).not.toContain('已复制');expect(button('复制历史版本编号').attributes('disabled')).toBeDefined()
})
it('does not show success for a replaced target or after unmount',async()=>{
 let resolve!:()=>void
 vi.stubGlobal('navigator',{clipboard:{writeText:()=>new Promise<void>(r=>resolve=r)}});open();await button('复制历史版本编号').trigger('click')
 await wrapper!.setProps({target:{...target,eventId:'different-event'}});resolve();await flushPromises();expect(wrapper!.text()).not.toContain('已复制')
 await button('复制单据编号').trigger('click');wrapper!.unmount();resolve();await flushPromises()
})
it('announces waiting immediately, prevents duplicate requests and keeps read retry available',async()=>{
 vi.useFakeTimers()
 const writeText=vi.fn(()=>new Promise<void>(()=>{}));vi.stubGlobal('navigator',{clipboard:{writeText}});open()
 await button('复制单据编号').trigger('click')
 expect(wrapper!.get('[role="status"]').text()).toBe('正在复制单据编号，请稍候…')
 expect(button('复制单据编号').attributes('disabled')).toBeDefined()
 expect(button('复制历史版本编号').attributes('disabled')).toBeDefined()
 await button('复制历史版本编号').trigger('click');expect(writeText).toHaveBeenCalledTimes(1)
 await button('重试原结算记录').trigger('click');expect(wrapper!.emitted('retry')).toHaveLength(1)
 await vi.advanceTimersByTimeAsync(9999);expect(wrapper!.text()).not.toContain('超时')
})
it.each(['resolve','reject'] as const)('offers manual copy after ten seconds and ignores late %s',async outcome=>{
 vi.useFakeTimers()
 let resolve!:()=>void,reject!:(error:Error)=>void
 vi.stubGlobal('navigator',{clipboard:{writeText:()=>new Promise<void>((ok,no)=>{resolve=ok;reject=no})}});open()
 await button('复制历史版本编号').trigger('click');await vi.advanceTimersByTimeAsync(10000)
 const fallback=wrapper!.get('[role="status"]').text()
 expect(fallback).toContain('复制等待超时，请选中上方历史版本编号手动复制')
 expect(wrapper!.text()).toContain(target.eventId)
 expect(button('复制单据编号').attributes('disabled')).toBeUndefined()
 expect(button('复制历史版本编号').attributes('disabled')).toBeUndefined()
 if(outcome==='resolve')resolve();else reject(new Error('late permission rejection'))
 await flushPromises();expect(wrapper!.get('[role="status"]').text()).toBe(fallback)
 expect(vi.getTimerCount()).toBe(0)
})
it('keeps a new copy active when the timed-out request completes',async()=>{
 vi.useFakeTimers()
 const pending:Array<()=>void>=[]
 const writeText=vi.fn(()=>new Promise<void>(ok=>pending.push(ok)))
 vi.stubGlobal('navigator',{clipboard:{writeText}});open()
 await button('复制单据编号').trigger('click');await vi.advanceTimersByTimeAsync(10000)
 await button('复制历史版本编号').trigger('click');pending[0]!();await flushPromises()
 expect(wrapper!.get('[role="status"]').text()).toBe('正在复制历史版本编号，请稍候…')
 expect(button('复制历史版本编号').attributes('disabled')).toBeDefined()
 pending[1]!();await flushPromises()
 expect(wrapper!.get('[role="status"]').text()).toBe('历史版本编号已复制。')
 expect(vi.getTimerCount()).toBe(0)
})
it.each(['target','permission','disabled','unmount'] as const)('clears the copy deadline on %s change',async change=>{
 vi.useFakeTimers()
 let resolve!:()=>void
 vi.stubGlobal('navigator',{clipboard:{writeText:()=>new Promise<void>(ok=>resolve=ok)}});open()
 await button('复制单据编号').trigger('click');expect(vi.getTimerCount()).toBe(1)
 if(change==='target')await wrapper!.setProps({target:{...target,id:'new-document'}})
 else if(change==='permission')await wrapper!.setProps({readable:false})
 else if(change==='disabled')await wrapper!.setProps({disabled:true})
 else wrapper!.unmount()
 expect(vi.getTimerCount()).toBe(0)
 resolve();await flushPromises();await vi.advanceTimersByTimeAsync(10000)
 if(change!=='unmount')expect(wrapper!.find('[role="status"]').exists()).toBe(false)
})

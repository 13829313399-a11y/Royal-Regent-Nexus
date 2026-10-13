import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import Print from '../HandoverOriginalPrint.vue'

const engine=vi.hoisted(()=>({getDocument:vi.fn(),GlobalWorkerOptions:{workerSrc:''}}))
vi.mock('pdfjs-dist',()=>engine)
let wrapper:VueWrapper|undefined
const draw=()=>({getViewport:({scale}:{scale:number})=>({width:595*scale,height:842*scale}),render:vi.fn().mockReturnValue({promise:Promise.resolve(),cancel:vi.fn()}),cleanup:vi.fn()})
beforeEach(()=>{
  vi.resetAllMocks()
  vi.spyOn(HTMLCanvasElement.prototype,'getContext').mockReturnValue({} as CanvasRenderingContext2D)
  vi.spyOn(HTMLCanvasElement.prototype,'toDataURL').mockReturnValue('data:image/png;base64,AA==')
})
afterEach(()=>{wrapper?.unmount();wrapper=undefined;vi.restoreAllMocks()})
const file=()=>({arrayBuffer:()=>Promise.resolve(new ArrayBuffer(1))} as Blob)
describe('all-page original printing',()=>{
  it('renders every page before marking ready and removes print styles on unmount',async()=>{
    const page=draw(),destroy=vi.fn().mockResolvedValue(undefined)
    engine.getDocument.mockReturnValue({promise:Promise.resolve({numPages:2,getPage:vi.fn().mockResolvedValue(page)}),destroy})
    wrapper=mount(Print,{props:{file:file(),token:'current'}});await flushPromises()
    expect(wrapper.findAll('img')).toHaveLength(2)
    expect(page.render).toHaveBeenCalledTimes(2)
    expect(wrapper.emitted('ready')).toEqual([['current']])
    expect(document.head.querySelector('[data-handover-original-print]')!.textContent).toContain('size:595pt 842pt')
    wrapper.unmount();wrapper=undefined
    expect(document.head.querySelector('[data-handover-original-print]')).toBeNull()
    expect(destroy).toHaveBeenCalled()
  })
  it('never marks a failed or over-sized PDF ready',async()=>{
    engine.getDocument.mockReturnValue({promise:Promise.resolve({numPages:41}),destroy:vi.fn().mockResolvedValue(undefined)})
    wrapper=mount(Print,{props:{file:file(),token:'large'}});await flushPromises()
    expect(wrapper.emitted('ready')).toBeUndefined()
    expect(wrapper.emitted('failed')?.[0]?.[0]).toBe('large')
    expect(wrapper.findAll('img')).toHaveLength(0)
  })
  it('does not expose or print an old PDF when the context changes during loading',async()=>{
    let resolve!:(value:unknown)=>void
    engine.getDocument.mockReturnValueOnce({promise:new Promise(done=>{resolve=done}),destroy:vi.fn().mockResolvedValue(undefined)})
    wrapper=mount(Print,{props:{file:file(),token:'old'}});await flushPromises()
    engine.getDocument.mockReturnValue({promise:Promise.resolve({numPages:1,getPage:vi.fn().mockResolvedValue(draw())}),destroy:vi.fn().mockResolvedValue(undefined)})
    await wrapper.setProps({file:file(),token:'new'});await flushPromises()
    resolve({numPages:1,getPage:vi.fn().mockResolvedValue(draw())});await flushPromises()
    expect(wrapper.emitted('ready')).toEqual([['new']])
    expect(wrapper.findAll('img')).toHaveLength(1)
  })
})

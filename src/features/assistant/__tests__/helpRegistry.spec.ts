import { describe, expect, it, vi } from 'vitest'
import { currentTargets, registerAssistantTarget, revealTarget } from '../anchors'
import { pageContext } from '../context'
describe('semantic help targets', () => {
  it('uses mapped route names and never accepts catchall or arbitrary selectors', () => {
    expect(pageContext('injection-scheduling','huaxing')?.module_id).toBe('injection-scheduling')
    expect(pageContext('nonexistent','huaxing')).toBeNull()
    expect(pageContext('uv-live','huakang-a')?.module_id).toBe('uv-operations')
  })
  it('reveals via the component contract, rejects hidden or missing elements', async () => {
    const element=document.createElement('button'); element.dataset.ylHelp='test.field';document.body.append(element)
    element.getClientRects=()=>({length:1}) as DOMRectList;element.scrollIntoView=vi.fn()
    vi.stubGlobal('matchMedia',()=>({matches:true}))
    const reveal=vi.fn(async()=>undefined), unregister=registerAssistantTarget({helpId:'test.field',element:()=>element,reveal})
    expect(currentTargets().get('test.field')).toBe(element)
    await expect(revealTarget('test.field')).resolves.toBe(element);expect(reveal).toHaveBeenCalledOnce()
    await expect(revealTarget('body > button')).rejects.toThrow('没有可见')
    unregister();element.remove(); await expect(revealTarget('test.field')).rejects.toThrow('没有可见')
    vi.unstubAllGlobals()
  })
})

import { describe, expect, it, vi } from 'vitest'
import { currentTargets, registerAssistantTarget, revealTarget } from '../anchors'
import { pageContext } from '../context'
import { guidanceProblem, verifyHelpTarget } from '../helpGuidance'
import type { HelpArticle } from '../types'
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
  it('refuses ambiguous targets instead of scrolling or clicking either one', async () => {
    const click = vi.fn()
    const elements = [1, 2].map(() => {
      const element = document.createElement('button'); element.dataset.ylHelp = 'duplicate'
      element.getClientRects = () => ({length:1}) as DOMRectList; element.scrollIntoView = vi.fn(); element.onclick = click
      document.body.append(element); return element
    })
    try {
      expect(currentTargets().has('duplicate')).toBe(false)
      await expect(revealTarget('duplicate')).rejects.toThrow('唯一')
      expect(click).not.toHaveBeenCalled()
      elements.forEach(element => expect(element.scrollIntoView).not.toHaveBeenCalled())
    } finally { elements.forEach(element => element.remove()) }
  })
  it('checks cancellation before a registered reveal and after asynchronous reveal', async () => {
    let current = false
    const reveal = vi.fn(async () => { current = false })
    const unregister = registerAssistantTarget({helpId:'cancelled',element:()=>null,reveal})
    try {
      await expect(revealTarget('cancelled', () => current)).rejects.toThrow('已停止')
      expect(reveal).not.toHaveBeenCalled()
      current = true
      await expect(revealTarget('cancelled', () => current)).rejects.toThrow('已停止')
      expect(reveal).toHaveBeenCalledOnce()
    } finally { unregister() }
  })
})

describe('versioned guide boundary', () => {
  const article: HelpArticle = { id:'field', module_id:'test', title:'数量', summary:'合成', content:'单位：件', anchor_id:'test.field', status:'verified', source_label:'合成', knowledge_version:'v1', route_names:['test-route'], factory_ids:['huaxing'], steps:[], verification:{fingerprint:'a',verified_commit:'synthetic',sources:[{path:'source.ts',symbol:'field',expected_sha256:'a',current_sha256:'a',matches:true}]} }
  const page = {module_id:'test',route_name:'test-route',factory_id:'huaxing'}
  it('requires the current route, factory, verified source and exact content fingerprint', () => {
    expect(() => verifyHelpTarget(article,article,page,'test.field')).not.toThrow()
    expect(guidanceProblem(article,{...page,factory_id:'huadeng'})).toContain('厂区')
    expect(guidanceProblem(article,{...page,route_name:'other'})).toContain('页面')
    expect(guidanceProblem({...article,status:'needs_review'},page)).toContain('停止定位')
    expect(guidanceProblem({...article,verification:undefined},page)).toContain('核对记录')
    expect(() => verifyHelpTarget(article,{...article,verification:{...article.verification!,fingerprint:'b'}},page,'test.field')).toThrow('版本已更新')
    expect(() => verifyHelpTarget(article,article,page,'unrelated.submit')).toThrow('已不在')
  })
})

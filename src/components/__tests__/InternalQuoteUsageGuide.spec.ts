import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Guide from '../InternalQuoteUsageGuide.vue'

function mountGuide() {
  return mount(Guide, {
    props: { factoryName: '华兴' },
    global: { stubs: {
      DialogPortal: { template: '<slot />' }, DialogOverlay: true,
      DialogContent: { template: '<section role="dialog"><slot /></section>' },
    } },
  })
}

afterEach(() => vi.restoreAllMocks())

describe('internal quote usage guide', () => {
  it('finds the relevant workflow without hiding the historical workflow distinction', async () => {
    const wrapper = mountGuide()
    expect(wrapper.text()).toContain('新报价直接输出')
    expect(wrapper.get('#internal-quote-guide-legacy').text()).toContain('原审核流程')
    await wrapper.get('input[aria-label="查找教程步骤"]').setValue('原文件作为参考附件')
    expect(wrapper.findAll('.internal-quote-guide-chapter')).toHaveLength(0)
    expect(wrapper.get('[role="status"]').text()).toContain('没有找到相关步骤')
    await wrapper.get('input[aria-label="查找教程步骤"]').setValue('电子部总额')
    expect(wrapper.find('#internal-quote-guide-import').exists()).toBe(true)
    expect(wrapper.find('#internal-quote-guide-create').exists()).toBe(false)
    wrapper.unmount()
  })

  it('prints all chapters after filtering the guide', async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {})
    const wrapper = mountGuide()
    await wrapper.get('input[aria-label="查找教程步骤"]').setValue('电子部总额')
    await wrapper.findAll('button').find(button => button.text() === '打印 / 保存 PDF')!.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.internal-quote-guide-chapter')).toHaveLength(11)
    expect(wrapper.get<HTMLInputElement>('input[type="search"]').element.value).toBe('')
    expect(print).toHaveBeenCalledOnce()
    wrapper.unmount()
  })

  it('reports unavailable diagrams instead of silently printing incomplete instructions', async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {})
    const wrapper = mountGuide()
    await wrapper.get('#internal-quote-guide-versions img').trigger('error')
    await wrapper.findAll('button').find(button => button.text() === '打印 / 保存 PDF')!.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[role="alert"]').map(row => row.text()).join(' ')).toContain('示意图未能完整加载')
    expect(print).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps checklist changes inside the guide and only emits close', async () => {
    const wrapper = mountGuide()
    await wrapper.get('input[type="checkbox"]').setValue(true)
    expect(wrapper.get<HTMLInputElement>('input[type="checkbox"]').element.checked).toBe(true)
    expect(wrapper.emitted('navigate')).toBeUndefined()
    await wrapper.get('button[aria-label="关闭使用教程"]').trigger('click')
    expect(wrapper.emitted('close')).toEqual([[]])
    wrapper.unmount()
  })
})

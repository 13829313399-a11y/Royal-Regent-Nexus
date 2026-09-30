import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Guide from '../CartonUsageGuide.vue'

function mountGuide(canReviewSupplierDeliveries = true) {
  return mount(Guide, {
    props: { factoryName: '华兴', canReviewSupplierDeliveries },
    global: { stubs: {
      DialogPortal: { template: '<slot />' }, DialogOverlay: true,
      DialogContent: { template: '<section role="dialog"><slot /></section>' },
    } },
  })
}

afterEach(() => vi.restoreAllMocks())

describe('carton usage guide interaction', () => {
  it('searches instructions and requests only the corresponding workspace', async () => {
    const wrapper = mountGuide()
    await wrapper.get('input[aria-label="查找教程步骤"]').setValue('导入历史库存')
    expect(wrapper.find('#carton-guide-opening').exists()).toBe(true)
    expect(wrapper.find('#carton-guide-master').exists()).toBe(false)
    await wrapper.findAll('button').find(button => button.text() === '打开期初库存')!.trigger('click')
    expect(wrapper.emitted('navigate')).toEqual([['opening-inventory']])
    wrapper.unmount()
  })

  it('prints the complete guide even after a reader filters chapters', async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {})
    const wrapper = mountGuide()
    await wrapper.get('input[aria-label="查找教程步骤"]').setValue('导入历史库存')
    await wrapper.findAll('button').find(button => button.text() === '打印 / 保存 PDF')!.trigger('click')
    await flushPromises()
    expect(wrapper.get<HTMLInputElement>('input[aria-label="查找教程步骤"]').element.value).toBe('')
    expect(wrapper.find('#carton-guide-master').exists()).toBe(true)
    expect(wrapper.find('#carton-guide-monthly').exists()).toBe(true)
    expect(print).toHaveBeenCalledOnce()
    wrapper.unmount()
  })

  it('explains failed images before printing and respects the receiving entry permission', async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {})
    const wrapper = mountGuide(false)
    expect(wrapper.findAll('button').some(button => button.text() === '打开本厂供应商待收')).toBe(false)
    await wrapper.get('#carton-guide-opening img').trigger('error')
    await wrapper.findAll('button').find(button => button.text() === '打印 / 保存 PDF')!.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[role="alert"]').map(row => row.text()).join(' ')).toContain('示意图未能完整加载')
    expect(print).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

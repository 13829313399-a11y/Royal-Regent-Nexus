import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import AiMessage from '@/features/ai-assistant/AiMessage.vue'
import AiRichText from '../presentation/AiRichText.vue'

describe('AI safe rich text', () => {
  it('renders headings, emphasis, lists, tables, code and quotes', () => {
    const wrapper = mount(AiRichText, {
      props: {
        source: '# 结论\n\n**重点**\n\n- 一\n- 二\n\n> 注意\n\n`code`\n\n| 单号 | 状态 |\n| --- | --- |\n| 001 | 完成 |',
      },
    })
    expect(wrapper.find('h1').text()).toBe('结论')
    expect(wrapper.find('strong').text()).toBe('重点')
    expect(wrapper.findAll('li')).toHaveLength(2)
    expect(wrapper.find('blockquote').text()).toBe('注意')
    expect(wrapper.find('code').text()).toBe('code')
    expect(wrapper.find('table').text()).toContain('001')
  })

  it('removes executable HTML, images, event handlers and unsafe links', () => {
    const wrapper = mount(AiRichText, {
      props: {
        source: '<script>alert(1)</script>\n<img src="x" onerror="alert(1)">\n[危险](javascript:alert(1))\n[内部](/modules/molding-sample)\n[安全](https://example.com)',
      },
    })
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.element.querySelector('[onerror]')).toBeNull()
    const links = wrapper.findAll('a')
    expect(links.find((item) => item.text() === '危险')?.attributes('href')).toBeUndefined()
    expect(links.find((item) => item.text() === '内部')?.attributes('href')).toBeUndefined()
    expect(links.find((item) => item.text() === '安全')?.attributes()).toMatchObject({
      href: 'https://example.com',
      rel: 'noopener noreferrer',
      target: '_blank',
    })
  })

  it('keeps partial streaming markdown inert and readable', async () => {
    const wrapper = mount(AiRichText, { props: { source: '**生成', streaming: true } })
    expect(wrapper.text()).toContain('**生成')
    await wrapper.setProps({ source: '**生成完成**', streaming: false })
    expect(wrapper.find('strong').text()).toBe('生成完成')
  })

  it('copies the original assistant text instead of rendered HTML', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    const wrapper = mount(AiMessage, {
      props: {
        message: {
          id: 'assistant-1',
          role: 'assistant',
          text: '**正式结论**',
          status: 'complete',
          createdAt: '2026-08-14T00:00:00Z',
        },
      },
    })
    await wrapper.get('button[aria-label="复制 AI 回复"]').trigger('click')
    expect(writeText).toHaveBeenCalledWith('**正式结论**')
  })
})

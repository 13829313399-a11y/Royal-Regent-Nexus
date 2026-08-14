import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { AIBusinessResult } from '@/features/ai-assistant/types'
import ResultRendererHost from '../presentation/ResultRendererHost.vue'

describe('AI result renderer host', () => {
  it('uses a safe text fallback for generic or unknown result kinds', () => {
    const result: AIBusinessResult = {
      id: 'result-safe-fallback',
      kind: 'generic',
      title: '无法识别的结构化结果',
      summary: '<img src=x onerror=alert(1)> 仅作为文本显示',
      sourceType: 'MODEL_INFERENCE',
      links: [],
    }
    const wrapper = mount(ResultRendererHost, {
      props: { results: [result], sources: [] },
    })
    expect(wrapper.get('[data-safe-result-fallback]').text()).toContain('<img src=x')
    expect(wrapper.find('img').exists()).toBe(false)
  })

  it('routes registered scheduling kinds through the domain compatibility renderer', () => {
    const result: AIBusinessResult = {
      id: 'result-plan-context',
      kind: 'plan_context',
      title: '当前计划',
      summary: '已按当前权限读取。',
      sourceType: 'FORMAL',
      links: [],
      planContext: {
        executionPublished: null,
        planningDraft: null,
      },
    }
    const wrapper = mount(ResultRendererHost, {
      props: { results: [result], sources: [] },
      global: { stubs: { RouterLink: true } },
    })
    expect(wrapper.get('[data-ai-business-results]').text()).toContain('当前计划')
    expect(wrapper.find('[data-safe-result-fallback]').exists()).toBe(false)
  })

  it('paginates large registered domain results without exposing unknown fields', async () => {
    const quotes = Array.from({ length: 7 }, (_, index) => ({
      quoteId: `quote-${index + 1}`,
      quoteNo: `Q-${String(index + 1).padStart(3, '0')}`,
      customer: `客户 ${index + 1}`,
      statusCode: 'DRAFT',
      statusLabel: '草稿',
      currentStageCode: 'DRAFT',
      currentStageLabel: '协作草稿',
      versionLabel: 'V1',
      updatedAt: '2026-08-14T08:00:00+08:00',
      navigationTarget: 'collaboration' as const,
    }))
    const result: AIBusinessResult = {
      id: 'result-large-quotes',
      kind: 'internal_quote_list',
      title: '内部报价',
      summary: '已按当前权限读取。',
      sourceType: 'FORMAL',
      links: [],
      internalQuote: { total: 12, returned: 7, limit: 7, offset: 0, quotes },
    }
    const wrapper = mount(ResultRendererHost, {
      props: { results: [result], sources: [] },
      global: { stubs: { RouterLink: true } },
    })

    expect(wrapper.text()).toContain('Q-001')
    expect(wrapper.text()).not.toContain('Q-007')
    expect(wrapper.text()).toContain('仍有更多正式数据')
    await wrapper.get('button[aria-label="下一页"]').trigger('click')
    expect(wrapper.text()).toContain('Q-007')
    expect(wrapper.text()).not.toContain('Q-001')
  })
})

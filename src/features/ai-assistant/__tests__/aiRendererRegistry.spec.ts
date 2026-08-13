import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import AiBusinessResultCard from '../AiBusinessResultCard.vue'
import { safeLinks } from '../renderers/contracts'
import { rendererRegistry } from '../renderers/registry'

function evidence(overrides: Record<string, unknown> = {}) {
  return {
    evidence_id: 'ev:1234567890abcdef',
    source_level: 'FORMAL_DOMAIN_SERVICE',
    source_name: 'internal_quote.list_summaries',
    factory_id: 'huaxing',
    as_of: '2026-08-12T10:00:00+08:00',
    entity_type: null,
    entity_id: null,
    entity_revision: null,
    content_hash: `sha256:${'a'.repeat(64)}`,
    truncated: false,
    cursor: null,
    access_policy: 'REAUTHORIZE_ON_OPEN',
    ...overrides,
  }
}

function internalQuoteData() {
  return {
    schema_version: 'internal-quote-summary-v1',
    result_type: 'internal_quote.summary_list',
    source_type: 'FORMAL',
    factory_id: 'huaxing',
    as_of: '2026-08-12T10:00:00+08:00',
    total: 1,
    limit: 10,
    offset: 0,
    returned: 1,
    truncated: false,
    quotes: [{
      quote_id: 'IQ-20260812-SAFE000001',
      quote_no: 'Q-0001',
      customer: '安全客户',
      status_code: 'final_reviewing',
      status_label: '待最终放行',
      current_stage_code: 'FINAL_REVIEW',
      current_stage_label: '等待负责跟客确认放行',
      version_label: 'V1',
      updated_at: '2026-08-12 10:00:00',
      navigation_target: 'summary',
    }],
  }
}

describe('AI Evidence v1 Renderer Registry', () => {
  it('renders versioned Knowledge as a separate cited guidance layer', async () => {
    const rendered = rendererRegistry.renderEnvelope({
      ok: true,
      tool_name: 'knowledge.search_module',
      data: {
        source_type: 'VERSIONED_MODULE_KNOWLEDGE',
        result_type: 'knowledge.search_results',
        schema_version: 'knowledge-search-v1',
        authority: 'PROCESS_GUIDANCE',
        conflict_policy: 'FORMAL_TOOL_WINS',
        query: 'DRAFT 和 PUBLISHED',
        evidence_missing: false,
        message: '已找到经过 Owner 审核且仍在有效期内的模块知识。',
        hits: [{
          score: 620,
          text_markdown: 'DRAFT 是规划草案；PUBLISHED 是当前执行计划。',
          citation: {
            knowledge_id: 'injection-scheduling',
            version: '1.1.0',
            section_id: 'status-boundary',
            source_path: 'docs/ai/modules/injection-scheduling.md',
            heading: '状态边界',
            reviewed_at: '2026-08-12',
            content_hash: `sha256:${'b'.repeat(64)}`,
          },
          deep_links: [{
            label: '打开注塑排产中枢',
            path: '/modules/production/injection-scheduling',
          }],
        }],
        truncated: false,
      },
      evidence: [evidence({
        source_level: 'VERSIONED_MODULE_KNOWLEDGE',
        source_name: 'knowledge.search_module',
        factory_id: null,
      })],
    })

    expect(rendered?.businessResult).toMatchObject({
      kind: 'knowledge_search',
      rendererStatus: 'registered',
      knowledgeSearch: {
        evidenceMissing: false,
        conflictPolicy: 'FORMAL_TOOL_WINS',
      },
    })
    expect(rendered?.sources.some((source) => source.level === 'MODULE_KNOWLEDGE')).toBe(true)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
    })
    await router.push('/')
    const wrapper = mount(AiBusinessResultCard, {
      props: {
        results: rendered?.businessResult ? [rendered.businessResult] : [],
        sources: rendered?.sources ?? [],
      },
      global: { plugins: [router] },
    })
    await router.isReady()

    expect(wrapper.get('[data-ai-knowledge-search]').text()).toContain(
      'injection-scheduling@1.1.0',
    )
    expect(wrapper.get('[data-ai-knowledge-search]').text()).toContain(
      '以正式业务工具为准',
    )
    expect(wrapper.get('[data-ai-knowledge-search] a').attributes('href')).toBe(
      '/modules/production/injection-scheduling',
    )
  })

  it('selects a registered Renderer by the exact schema/result pair and binds Evidence', async () => {
    const rendered = rendererRegistry.renderEnvelope({
      ok: true,
      tool_name: 'internal_quote.list_summaries',
      data: internalQuoteData(),
      error: null,
      metadata: {},
      evidence: [evidence()],
    })

    expect(rendered?.businessResult).toMatchObject({
      kind: 'internal_quote_list',
      rendererStatus: 'registered',
      evidence: [{
        evidenceId: 'ev:1234567890abcdef',
        sourceLevel: 'FORMAL_DOMAIN_SERVICE',
        factoryId: 'huaxing',
      }],
    })
    expect(rendered?.sources[0]).toMatchObject({ level: 'FORMAL', factoryId: 'huaxing' })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{
        path: '/quotes/:quoteId',
        name: 'internal-quote-summary',
        component: { template: '<div />' },
      }],
    })
    await router.push('/')
    const wrapper = mount(AiBusinessResultCard, {
      props: {
        results: rendered?.businessResult ? [rendered.businessResult] : [],
        sources: rendered?.sources ?? [],
      },
      global: { plugins: [router] },
    })
    await router.isReady()
    expect(wrapper.get('[data-ai-evidence]').text()).toContain('FORMAL_DOMAIN_SERVICE')
    expect(wrapper.get('[data-ai-evidence]').text()).toContain('厂区 huaxing')
    expect(wrapper.get('[data-ai-evidence]').text()).toContain('完整性：未截断')
  })

  it('uses an inert read-only fallback only for an unknown schema carrying valid Evidence', () => {
    const rendered = rendererRegistry.renderEnvelope({
      ok: true,
      tool_name: 'internal_quote.list_summaries',
      data: {
        ...internalQuoteData(),
        schema_version: 'internal-quote-summary-v99',
        payload: '<script>window.evil=true</script>',
        link: 'javascript:alert(1)',
        action: { type: 'APPLY', endpoint: 'https://evil.example' },
      },
      evidence: [evidence()],
    })

    expect(rendered?.businessResult).toMatchObject({
      kind: 'generic',
      title: '未注册结果（只读）',
      rendererStatus: 'safe_fallback',
      links: [],
    })
    expect(rendered?.businessResult?.actionConfirmation).toBeUndefined()
    expect(rendered?.businessResult?.summary).toContain('<script>')
  })

  it('fails closed for malformed Evidence, prototype pollution and unsafe links', () => {
    const malformed = rendererRegistry.renderEnvelope({
      ok: true,
      tool_name: 'internal_quote.list_summaries',
      data: { ...internalQuoteData(), schema_version: 'internal-quote-summary-v99' },
      evidence: [evidence({ password: 'secret' })],
    })
    const polluted = Object.create({ inherited: 'not-plain' })
    polluted.ok = true
    polluted.data = internalQuoteData()

    expect(malformed?.businessResult).toBeNull()
    expect(rendererRegistry.renderEnvelope(polluted)).toBeNull()
    expect(safeLinks([
      { label: '<img onerror=alert(1)>', route: 'javascript:alert(1)' },
      { label: 'evil', route: '/modules/evil', query: { __proto__: 'polluted' } },
      { label: 'external', route: 'https://evil.example' },
    ])).toEqual([])
    expect(({} as Record<string, unknown>).polluted).toBeUndefined()
  })

  it('preserves the v1 contract by ignoring unknown schemas without Evidence', () => {
    const rendered = rendererRegistry.renderEnvelope({
      ok: true,
      tool_name: 'future.tool',
      data: {
        schema_version: 'future-result-v9',
        result_type: 'future.unregistered',
        opaque: 'untrusted',
      },
      error: null,
      metadata: {},
    })

    expect(rendered?.businessResult).toBeNull()
  })
})

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import VisionComparisonCard from '../components/VisionComparisonCard.vue'
import { parseVisionTaskResult } from '../renderers/visionComparison'

const observationRow = {
  row_index: 1,
  order_no: '00123',
  order_no_confidence: 0.95,
  item_no: '0007',
  item_no_confidence: 0.95,
  mold_no: 'M-001',
  mold_no_confidence: 0.95,
  delivery_due_date: '2026-08-31',
  delivery_due_date_confidence: 0.95,
  outstanding_quantity: '120',
  outstanding_quantity_confidence: 0.95,
  row_confidence: 0.95,
  uncertain_fields: [],
}

const observation = {
  contract_version: '1' as const,
  domain: 'INJECTION_SCHEDULING_BACKLOG' as const,
  overall_confidence: 0.95,
  instructions_detected: true,
  unreadable_region_count: 0,
  rows: [observationRow],
}

const observationResult = {
  contract_version: '1' as const,
  result_type: 'vision.injection_backlog_observation.v1' as const,
  source_type: 'USER_PROVIDED' as const,
  factory_id: 'huaxing',
  source_artifact_id: `aiart-${'a'.repeat(32)}`,
  source_sha256: 'b'.repeat(64),
  as_of: '2026-08-12T08:00:00+00:00',
  provider: 'qwen',
  model: 'qwen3.7-plus',
  provider_call_count: 1 as const,
  tool_count: 0 as const,
  low_confidence_threshold: 0.8 as const,
  observation,
}

const formalItem = {
  order_id: 'order-1',
  order_no: '00123',
  item_no: '0007',
  product_name: '测试产品',
  mold_no: 'M-002',
  priority_code: 'NORMAL' as const,
  priority_business_label: '普通',
  delivery_due_date: '2026-08-31',
  order_quantity: 200,
  outstanding_quantity: 120,
  mold_enrichment_status: 'MATCHED',
  mold_enrichment_business_label: '共享资料已补齐',
  source_type: 'DEMAND_ORDER',
}

const comparisonResult = {
  contract_version: '1' as const,
  result_type: 'vision.injection_backlog_comparison.v1' as const,
  source_type: 'FORMAL' as const,
  factory_id: 'huaxing',
  observation_task_id: `aitask-${'c'.repeat(32)}`,
  source_artifact_id: `aiart-${'a'.repeat(32)}`,
  source_sha256: 'b'.repeat(64),
  observation_evidence: {
    evidence_id: 'vision:observation:test',
    source_level: 'USER_PROVIDED' as const,
    source_name: 'vision.observe_injection_backlog_image' as const,
    factory_id: 'huaxing',
    as_of: '2026-08-12T08:00:00+00:00',
    entity_type: null,
    entity_id: null,
    entity_revision: null,
    content_hash: `sha256:${'b'.repeat(64)}`,
    truncated: false,
    cursor: null,
    access_policy: 'REAUTHORIZE_ON_OPEN' as const,
  },
  observation,
  formal_backlog: {
    source_type: 'FORMAL' as const,
    factory_id: 'huaxing',
    as_of: '2026-08-12T17:00:00+08:00',
    source_scope: 'GLOBAL_BACKLOG' as const,
    source_business_label: '全局待排池',
    total: 31,
    limit: 20,
    offset: 0,
    returned: 1,
    truncated: true,
    items: [formalItem],
    entity_links: [{
      label: '打开注塑排产中枢',
      route: '/modules/production/injection-scheduling',
      query: { factory: 'huaxing' },
    }],
  },
  comparison_rows: [{
    status: 'DIFFERENT' as const,
    observation: observationRow,
    formal: formalItem,
    field_comparisons: [{
      field: 'mold_no' as const,
      observed: 'M-001',
      formal: 'M-002',
      status: 'DIFFERENT' as const,
    }],
    reason_code: 'FIELD_DIFFERENCE',
  }],
  matched_count: 0,
  different_count: 1,
  unconfirmed_count: 0,
  image_only_count: 0,
  formal_only_count: 0,
  no_write_performed: true as const,
}

describe('NIF-14 vision Observation and formal comparison renderer', () => {
  it('shows Stage A as USER_PROVIDED and requires an explicit compare click', async () => {
    const parsed = parseVisionTaskResult(observationResult)
    expect(parsed).not.toBeNull()
    const wrapper = mount(VisionComparisonCard, { props: { result: parsed! } })

    expect(wrapper.text()).toContain('USER_PROVIDED')
    expect(wrapper.text()).toContain('图片阶段 Tool=0')
    expect(wrapper.text()).toContain('疑似指令文本')
    expect(wrapper.text()).toContain('00123')
    expect(wrapper.text()).toContain('0007')
    expect(wrapper.text()).toContain('没有修改任何业务数据')
    const button = wrapper.get('button')
    expect(button.text()).toContain('同意读取并比较正式 Backlog')
    await button.trigger('click')
    expect(wrapper.emitted('compare')).toHaveLength(1)
  })

  it('shows separate formal authority, query time, truncation and differences', () => {
    const parsed = parseVisionTaskResult(comparisonResult)
    expect(parsed).not.toBeNull()
    const wrapper = mount(VisionComparisonCard, { props: { result: parsed! } })

    expect(wrapper.text()).toContain('USER_PROVIDED')
    expect(wrapper.text()).toContain('FORMAL_DOMAIN_SERVICE')
    expect(wrapper.text()).toContain('2026-08-12T17:00:00+08:00')
    expect(wrapper.text()).toContain('正式 Backlog 已截断')
    expect(wrapper.text()).toContain('1/31')
    expect(wrapper.text()).toContain('差异 1')
    expect(wrapper.text()).toContain('M-001')
    expect(wrapper.text()).toContain('正式数据已在 Stage B 重新鉴权并即时读取')
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('fails closed on unknown fields, malformed Evidence and inconsistent counts', () => {
    expect(parseVisionTaskResult({ ...observationResult, injected: true })).toBeNull()
    expect(parseVisionTaskResult({
      ...comparisonResult,
      observation_evidence: {
        ...comparisonResult.observation_evidence,
        source_level: 'FORMAL_DOMAIN_SERVICE',
      },
    })).toBeNull()
    expect(parseVisionTaskResult({ ...comparisonResult, different_count: 0 })).toBeNull()
  })
})

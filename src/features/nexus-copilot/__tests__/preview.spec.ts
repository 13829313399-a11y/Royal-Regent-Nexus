import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import PreviewCard from '@/features/nexus-copilot/components/PreviewCard.vue'
import {
  parsePreviewManifest,
  parseScenarioCompare,
  type AIPreviewManifest,
} from '@/features/nexus-copilot/renderers/preview'
import { parseWorkbookMappingProposal } from '@/features/injection-scheduling-v2/api/injectionSchedulingV2Api'

export function previewManifest(overrides: Partial<AIPreviewManifest> = {}): AIPreviewManifest {
  return {
    schema_version: 'ai-preview-manifest-v1',
    preview_id: 'isrun-preview-0001',
    preview_type: 'injection_scheduling.run',
    source_revision_hash: 'a'.repeat(64),
    factory_id: 'huaxing',
    input_hash: 'b'.repeat(64),
    assumptions: [{ key: 'plan_status', label: '计划切片', value: 'DRAFT' }],
    evidence_refs: [{
      evidence_id: 'preview:evidence-0001',
      source_level: 'FORMAL_DOMAIN_SERVICE',
      source_name: 'injection_scheduling.preview_run',
      factory_id: 'huaxing',
      as_of: '2026-08-12T09:00:00+08:00',
      entity_type: 'scheduling_preview_run',
      entity_id: 'isrun-preview-0001',
      entity_revision: 1,
      content_hash: `sha256:${'c'.repeat(64)}`,
      truncated: false,
      cursor: null,
      access_policy: 'REAUTHORIZE_ON_OPEN',
    }],
    created_by: 'planner-1',
    created_at: '2099-08-12T09:00:00+08:00',
    expires_at: '2099-08-12T09:30:00+08:00',
    status: 'READY',
    deterministic_service: true,
    can_propose_action: true,
    action_capability: 'CREATE_PROPOSAL_ONLY',
    no_write_performed: true,
    ...overrides,
  }
}

describe('NIF-15 generic Preview contracts', () => {
  it('renders a ready Preview as no-write and proposal-only', () => {
    const parsed = parsePreviewManifest(previewManifest())
    expect(parsed).not.toBeNull()
    const wrapper = mount(PreviewCard, { props: { manifest: parsed! } })
    expect(wrapper.text()).toContain('可供复核')
    expect(wrapper.text()).toContain('没有执行正式业务写入')
    expect(wrapper.text()).toContain('仅允许进入“创建 Proposal”流程')
    expect(wrapper.text()).not.toContain('已经执行')
  })

  it('blocks stale manifests and fails closed on unknown or inconsistent fields', () => {
    const stale = previewManifest({
      status: 'STALE',
      can_propose_action: false,
      action_capability: null,
    })
    const wrapper = mount(PreviewCard, { props: { manifest: stale } })
    expect(wrapper.text()).toContain('来源已变化')
    expect(wrapper.text()).toContain('不能继续创建有效 Action Proposal')
    expect(parsePreviewManifest({ ...previewManifest(), unregistered: true })).toBeNull()
    expect(parsePreviewManifest({ ...previewManifest(), status: 'EXPIRED' })).toBeNull()

    const expiredAtRuntime = parsePreviewManifest(previewManifest({
      created_at: '2000-01-01T00:00:00Z',
      expires_at: '2000-01-01T00:30:00Z',
    }))
    expect(expiredAtRuntime?.status).toBe('EXPIRED')
    expect(expiredAtRuntime?.can_propose_action).toBe(false)
  })

  it('validates Scenario Compare basis and workbook adapter metadata', () => {
    const comparison = {
      schema_version: 'ai-scenario-compare-v1',
      preview_type: 'injection_scheduling.run',
      preview_ids: ['isrun-preview-0001', 'isrun-preview-0002'],
      source_revision_hashes: ['a'.repeat(64)],
      comparable: true,
      comparison_basis: 'SAME_SOURCE_REVISION',
      warning: '同一来源版本，可比较。',
      no_write_performed: true,
    }
    expect(parseScenarioCompare(comparison)?.comparable).toBe(true)
    expect(parseScenarioCompare({ ...comparison, comparable: false })).toBeNull()
    expect(parseWorkbookMappingProposal({ proposal: [], preview_manifest: previewManifest({
      preview_type: 'workbook.mapping',
      preview_id: 'workbook-preview-0001',
      deterministic_service: false,
      can_propose_action: false,
      action_capability: null,
    }) }).preview_manifest?.preview_type).toBe('workbook.mapping')
    expect(() => parseWorkbookMappingProposal({
      proposal: [],
      preview_manifest: { ...previewManifest(), unexpected: true },
    })).toThrow('Preview 校验失败')
  })
})

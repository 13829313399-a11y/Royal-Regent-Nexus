import { webcrypto } from 'node:crypto'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpMocks = vi.hoisted(() => ({ post: vi.fn() }))

vi.mock('@/lib/http', () => ({
  http: { post: httpMocks.post },
}))

import {
  createArtifactTranslationTask,
  createVisionComparisonTask,
  createVisionObservationTask,
} from '@/api/aiTasks'

describe('Artifact Task creation contract', () => {
  beforeEach(() => {
    vi.stubGlobal('crypto', webcrypto)
    httpMocks.post.mockReset()
  })

  it('creates one keyed Preview step bound to the exact source Artifact hash', async () => {
    httpMocks.post.mockRejectedValue(new Error('stop after capture'))
    const artifactId = `aiart-${'a'.repeat(32)}`

    await expect(createArtifactTranslationTask({
      artifactId,
      artifactSha256: 'b'.repeat(64),
      factoryId: 'huaxing',
      direction: 'zh_to_en',
      selectedSheetNames: ['订单'],
      operationId: 'artifact-translation-operation-001',
    })).rejects.toThrow('stop after capture')

    expect(httpMocks.post).toHaveBeenCalledOnce()
    const [url, body] = httpMocks.post.mock.calls[0]!
    expect(url).toBe('/ai/tasks')
    expect(body).toMatchObject({
      task_type: 'PREVIEW',
      factory_scope: 'huaxing',
      primary_skill_id: 'files.document_translation',
      proposed_tool_names: ['artifacts.translate_document_local'],
      proposed_max_steps: 1,
      proposed_maximum_risk: 'PREVIEW_WITH_AUDIT',
      idempotency_key: 'artifact-translation-operation-001',
      steps: [{
        key: 'translate_document',
        kind: 'PREVIEW',
        tool_name: 'artifacts.translate_document_local',
        arguments: {
          factory_id: 'huaxing',
          artifact_id: artifactId,
          operation_id: 'artifact-translation-operation-001',
          direction: 'zh_to_en',
          selected_sheet_names: ['订单'],
        },
      }],
    })
    expect(body.input_hash).toMatch(/^[a-f0-9]{64}$/)
    expect(JSON.stringify(body)).not.toContain('document_file')
  })

  it('creates Stage A as one no-business-query image Observation task', async () => {
    httpMocks.post.mockRejectedValue(new Error('stop after capture'))
    const artifactId = `aiart-${'a'.repeat(32)}`
    const consent = {
      accepted: true as const,
      notice_version: 'aliyun-cn-beijing-image-v1' as const,
      provider: 'qwen' as const,
      region: 'cn-beijing' as const,
      classification: 'CONFIDENTIAL_BUSINESS' as const,
      content_class: 'IMAGE' as const,
      artifact_ids: [artifactId],
    }

    await expect(createVisionObservationTask({
      artifactId,
      factoryId: 'huaxing',
      consent,
      operationId: 'vision-observation-operation-001',
      pageContext: {
        route_name: 'injection-scheduling-v2',
        path: '/modules/production/injection-scheduling',
        factory_id: 'huaxing',
        module_id: 'injection-scheduling',
        selected_entity: null,
      },
    })).rejects.toThrow('stop after capture')

    const [url, body] = httpMocks.post.mock.calls[0]!
    expect(url).toBe('/ai/tasks')
    expect(body).toMatchObject({
      task_type: 'READ',
      factory_scope: 'huaxing',
      primary_skill_id: 'vision.screenshot_observation',
      proposed_tool_names: ['vision.observe_injection_backlog_image'],
      proposed_max_steps: 1,
      proposed_maximum_risk: 'READ_ONLY',
      idempotency_key: 'vision-observation-operation-001',
      steps: [{
        key: 'observe_image',
        kind: 'READ',
        tool_name: 'vision.observe_injection_backlog_image',
        arguments: {
          factory_id: 'huaxing',
          artifact_id: artifactId,
          operation_id: 'vision-observation-operation-001',
          consent,
        },
      }],
    })
    const serialized = JSON.stringify(body)
    expect(serialized).not.toContain('list_backlog')
    expect(serialized).not.toContain('prompt')
    expect(serialized).not.toContain('ocr')
  })

  it('creates Stage B only from the source Task id and a fixed scheduling context', async () => {
    httpMocks.post.mockRejectedValue(new Error('stop after capture'))
    const observationTaskId = `aitask-${'b'.repeat(32)}`

    await expect(createVisionComparisonTask({
      observationTaskId,
      factoryId: 'huaxing',
      operationId: 'vision-comparison-operation-001',
    })).rejects.toThrow('stop after capture')

    const [url, body] = httpMocks.post.mock.calls[0]!
    expect(url).toBe('/ai/tasks')
    expect(body).toMatchObject({
      task_type: 'READ',
      factory_scope: 'huaxing',
      primary_skill_id: 'vision.screenshot_observation',
      proposed_tool_names: ['vision.compare_injection_backlog'],
      page_context: {
        route_name: 'injection-scheduling-v2',
        path: '/modules/production/injection-scheduling',
        factory_id: 'huaxing',
        module_id: 'injection-scheduling',
      },
      steps: [{
        key: 'compare_formal_backlog',
        kind: 'READ',
        tool_name: 'vision.compare_injection_backlog',
        arguments: {
          factory_id: 'huaxing',
          observation_task_id: observationTaskId,
          operation_id: 'vision-comparison-operation-001',
        },
      }],
    })
    const argumentsObject = body.steps[0].arguments
    expect(Object.keys(argumentsObject).sort()).toEqual([
      'factory_id', 'observation_task_id', 'operation_id',
    ])
  })
})

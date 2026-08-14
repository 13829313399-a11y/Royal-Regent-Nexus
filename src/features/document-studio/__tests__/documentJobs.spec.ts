import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  upload: vi.fn(),
}))

vi.mock('@/lib/http', () => ({
  http: { get: mocks.get, post: mocks.post },
}))

vi.mock('@/api/aiArtifacts', () => ({
  uploadAIArtifact: mocks.upload,
}))

import {
  createDocumentJob,
  documentJobTypeForTool,
  getDocumentJobCapabilities,
  reviewDocumentJob,
} from '../api/documentJobs'

describe('document job facade client', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('keeps the five tool ids mapped to closed backend job types', () => {
    expect(documentJobTypeForTool('pdf-to-excel')).toBe('PDF_TO_EXCEL')
    expect(documentJobTypeForTool('pdf-to-word')).toBe('PDF_TO_WORD')
    expect(documentJobTypeForTool('word-to-pdf')).toBe('WORD_TO_PDF')
    expect(documentJobTypeForTool('pdf-translation')).toBe('PDF_TRANSLATION')
    expect(documentJobTypeForTool('pdf-split')).toBe('PDF_SPLIT')
  })

  it('reads default-off capabilities without inventing supported jobs', async () => {
    mocks.get.mockResolvedValueOnce({
      data: {
        contract_version: '1',
        available: false,
        artifact_upload_available: false,
        task_runtime_available: false,
        supported_job_types: [],
        legacy_fallback_job_types: ['PDF_TO_EXCEL', 'PDF_TO_WORD', 'PDF_SPLIT'],
      },
    })

    const capabilities = await getDocumentJobCapabilities()

    expect(capabilities.available).toBe(false)
    expect(capabilities.supported_job_types).toEqual([])
    expect(capabilities.legacy_fallback_job_types).toEqual([
      'PDF_TO_EXCEL',
      'PDF_TO_WORD',
      'PDF_SPLIT',
    ])
  })

  it('uploads once, preflights, then creates a hash-bound fixed task', async () => {
    mocks.upload.mockResolvedValueOnce({
      id: `aiart-${'a'.repeat(32)}`,
      sha256: 'b'.repeat(64),
    })
    mocks.post
      .mockResolvedValueOnce({
        data: {
          contract_version: '1',
          source_artifact_id: `aiart-${'a'.repeat(32)}`,
          source_sha256: 'b'.repeat(64),
          filename: '订单.pdf',
          detected_mime_type: 'application/pdf',
          size_bytes: 128,
          page_count: 2,
          native_text_pages: 2,
          scanned_pages: 0,
          route_decision: 'TASK_LOCAL',
          warnings: [],
        },
      })
      .mockResolvedValueOnce({
        data: {
          contract_version: '1',
          id: `docjob-${'c'.repeat(32)}`,
          task_id: `aitask-${'c'.repeat(32)}`,
          operation_id: `docop-${'d'.repeat(32)}`,
          factory_id: 'huaxing',
          source_artifact_id: `aiart-${'a'.repeat(32)}`,
          source_filename: '订单.pdf',
          job_type: 'PDF_SPLIT',
          processing_mode: 'LOCAL_PRIVATE',
          state: 'READY',
          revision: 1,
          created_at: '2026-08-14T09:00:00+08:00',
          updated_at: '2026-08-14T09:00:00+08:00',
          terminal_at: null,
          page_range: { contract_version: '1', kind: 'ALL', pages: [] },
          preflight: null,
          snapshot_artifact_id: null,
          result_artifact_id: null,
          quality_report_artifact_id: null,
          quality_report: null,
          failure_code: '',
        },
      })
    const stages: string[] = []

    const result = await createDocumentJob({
      file: new File(['pdf'], '订单.pdf', { type: 'application/pdf' }),
      factoryId: 'huaxing',
      toolId: 'pdf-split',
      splitMode: 'ranges',
      splitPageRanges: '1,2',
      onStage: stage => stages.push(stage),
    })

    expect(mocks.upload).toHaveBeenCalledTimes(1)
    expect(stages).toEqual(['UPLOADING', 'PREFLIGHTING', 'READY'])
    expect(mocks.post).toHaveBeenNthCalledWith(1, '/tools/document-jobs/preflight', expect.any(Object))
    expect(mocks.post).toHaveBeenNthCalledWith(2, '/tools/document-jobs', expect.objectContaining({
      source_sha256: 'b'.repeat(64),
      job_type: 'PDF_SPLIT',
      options: expect.objectContaining({
        split_mode: 'ranges',
        split_page_ranges: '1,2',
      }),
    }))
    expect(result.job.state).toBe('READY')

    mocks.post.mockResolvedValueOnce({ data: result.job })
    const replayStages: string[] = []
    const replay = await createDocumentJob({
      file: new File(['pdf'], '订单.pdf', { type: 'application/pdf' }),
      factoryId: 'huaxing',
      toolId: 'pdf-split',
      splitMode: 'ranges',
      splitPageRanges: '1,2',
      sourceArtifact: result.source,
      preflight: result.preflight,
      operationId: result.job.operation_id,
      onStage: stage => replayStages.push(stage),
    })

    expect(mocks.upload).toHaveBeenCalledTimes(1)
    expect(replayStages).toEqual(['READY'])
    expect(mocks.post).toHaveBeenCalledTimes(3)
    expect(replay.job.task_id).toBe(result.job.task_id)
  })

  it('submits every review decision with task and snapshot freshness bindings', async () => {
    const job = {
      contract_version: '1' as const,
      id: `docjob-${'a'.repeat(32)}`,
      task_id: `aitask-${'b'.repeat(32)}`,
      operation_id: `docop-${'c'.repeat(32)}`,
      factory_id: 'huaxing',
      source_artifact_id: `aiart-${'d'.repeat(32)}`,
      source_filename: 'review.pdf',
      job_type: 'PDF_TO_EXCEL' as const,
      processing_mode: 'LOCAL_PRIVATE' as const,
      state: 'REVIEW_REQUIRED' as const,
      revision: 4,
      created_at: '2026-08-14T09:00:00+08:00',
      updated_at: '2026-08-14T09:01:00+08:00',
      terminal_at: null,
      input_hash: 'e'.repeat(64),
      runtime_plan_hash: 'f'.repeat(64),
      snapshot_sha256: '1'.repeat(64),
    }
    const issue = {
      contract_version: '1' as const,
      issue_id: `docissue-${'2'.repeat(32)}`,
      severity: 'WARNING' as const,
      kind: 'LOW_CONFIDENCE_BLOCK',
      page_number: 1,
      target_id: 'p1-b1',
      original_value: 'O0',
      proposed_value: '00',
      confidence: 0.7,
      message: '请确认',
      options: ['ACCEPT', 'EDIT', 'MARK_UNKNOWN'] as const,
    }
    mocks.post.mockResolvedValueOnce({ data: { ...job, state: 'RUNNING', revision: 5 } })

    const result = await reviewDocumentJob({
      job,
      actions: [{ issue: { ...issue, options: [...issue.options] }, action: 'EDIT', replacementValue: '00' }],
    })

    expect(mocks.post).toHaveBeenCalledWith(
      `/tools/document-jobs/${job.task_id}/review`,
      expect.objectContaining({
        expected_revision: 4,
        expected_input_hash: job.input_hash,
        expected_runtime_plan_hash: job.runtime_plan_hash,
        patches: [expect.objectContaining({
          issue_id: issue.issue_id,
          replacement_value: '00',
          expected_snapshot_sha256: job.snapshot_sha256,
        })],
      }),
    )
    expect(result.state).toBe('RUNNING')
  })
})

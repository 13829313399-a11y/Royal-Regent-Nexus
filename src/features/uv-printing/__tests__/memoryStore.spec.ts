import { describe, expect, it } from 'vitest'
import { UvMemoryStore } from '../preview/memoryStore'

const scope = { factory_id: 'huakang-a' as const, business_date: '2026-09-13' }

describe('样例报工修订', () => {
  function reportInput(store: UvMemoryStore, operationId: string) {
    const job = store.snapshot().jobs.find((candidate) => candidate.id === 'DEMO-J-1012')!
    return {
      factory_id: 'huakang-a' as const,
      operation_id: operationId,
      expected_version: 0,
      business_date: '2026-09-13',
      shift: 'day' as const,
      shift_template_version_id: 'shift-template-v1-day',
      machine_id: job.machine_id,
      product_id: job.product_id!,
      process_version_id: job.process_version_id!,
      reported_qty: 10,
      good_qty: 10,
      defective_qty: 0,
      pending_qty: 0,
      semi_finished_qty: 0,
      worker_ids: [],
      notes: '样例生命周期回归',
      source_allocations: [{ job_id: job.id, piece_qty: 10, job_version: job.version }],
      evidence_job_ids: [job.id],
    }
  }

  it('草稿不占来源、不计汇总或工资；确认时才正式占用', async () => {
    const store = new UvMemoryStore()
    const beforeSummary = await store.summary(scope)
    const beforePayroll = await store.payrollPreview({ factory_id: 'huakang-a', date_from: '2026-09-13', date_to: '2026-09-13' })
    const draft = await store.createReport(reportInput(store, 'draft-lifecycle-1'))
    const jobBeforeConfirm = store.snapshot().jobs.find((job) => job.id === 'DEMO-J-1012')!
    const duringSummary = await store.summary(scope)

    expect(draft.data.entity.status).toBe('draft')
    expect((draft.data.entity as typeof draft.data.entity & { source_allocations?: unknown[] }).source_allocations).toHaveLength(1)
    expect(jobBeforeConfirm.available_piece_qty).toBe(24)
    expect(duringSummary.data.counts.good_qty).toBe(beforeSummary.data.counts.good_qty)
    const payroll = await store.payrollPreview({ factory_id: 'huakang-a', date_from: '2026-09-13', date_to: '2026-09-13' })
    expect(payroll.data).toEqual(beforePayroll.data)

    await store.confirmReport({ factory_id: 'huakang-a', operation_id: 'draft-confirm-1', expected_version: draft.data.entity.version, report_id: draft.data.entity.id })
    const jobAfterConfirm = store.snapshot().jobs.find((job) => job.id === 'DEMO-J-1012')!
    expect(jobAfterConfirm.available_piece_qty).toBe(14)
    expect((await store.summary(scope)).data.counts.good_qty).toBe(beforeSummary.data.counts.good_qty + 10)
  })

  it('两个草稿可引用同一来源，但先确认者占用后，后确认者因版本过期被拒绝', async () => {
    const store = new UvMemoryStore()
    const first = await store.createReport(reportInput(store, 'shared-source-draft-1'))
    const second = await store.createReport(reportInput(store, 'shared-source-draft-2'))
    await store.confirmReport({ factory_id: 'huakang-a', operation_id: 'shared-source-confirm-1', expected_version: first.data.entity.version, report_id: first.data.entity.id })

    await expect(store.confirmReport({
      factory_id: 'huakang-a', operation_id: 'shared-source-confirm-2', expected_version: second.data.entity.version, report_id: second.data.entity.id,
    })).rejects.toMatchObject({ status: 409 })
  })

  it('更正保留来源与质量证据；缩小数量不足以覆盖原分配时要求重新核对', async () => {
    const store = new UvMemoryStore()
    const draft = await store.createReport(reportInput(store, 'correction-source-draft'))
    const confirmed = await store.confirmReport({ factory_id: 'huakang-a', operation_id: 'correction-source-confirm', expected_version: draft.data.entity.version, report_id: draft.data.entity.id })
    const before = store.snapshot().jobs.find((job) => job.id === 'DEMO-J-1012')!.available_piece_qty
    const correction = reportInput(store, 'correction-source-command')
    correction.reported_qty = 8
    correction.good_qty = 8
    correction.source_allocations = []
    correction.evidence_job_ids = []

    await expect(store.correctReport({
      factory_id: 'huakang-a', operation_id: 'correction-source-command', expected_version: confirmed.data.entity.version, report_id: confirmed.data.entity.id,
      correction, reason: '测试缩小报工',
    })).rejects.toMatchObject({ status: 422 })
    expect(store.snapshot().jobs.find((job) => job.id === 'DEMO-J-1012')!.available_piece_qty).toBe(before)
    expect(store.snapshot().reports.find((report) => report.id === confirmed.data.entity.id)?.status).toBe('confirmed')

    const preserved = reportInput(store, 'correction-source-preserved')
    preserved.source_allocations = []
    preserved.evidence_job_ids = []
    const replacement = await store.correctReport({
      factory_id: 'huakang-a', operation_id: 'correction-source-preserved', expected_version: confirmed.data.entity.version, report_id: confirmed.data.entity.id,
      correction: preserved, reason: '保持原来源',
    })
    expect((replacement.data.entity as typeof replacement.data.entity & { source_allocations?: unknown[]; evidence_job_ids?: unknown[] }).source_allocations).toHaveLength(1)
    expect((replacement.data.entity as typeof replacement.data.entity & { evidence_job_ids?: unknown[] }).evidence_job_ids).toEqual(['DEMO-J-1012'])
    expect(store.snapshot().jobs.find((job) => job.id === 'DEMO-J-1012')!.available_piece_qty).toBe(before)
  })

  it('质量补录生成 corrected 修订，旧 confirmed 作废且日报不重复累计', async () => {
    const store = new UvMemoryStore()
    const original = store.snapshot().reports.find((report) => report.status === 'confirmed' && report.business_date === scope.business_date)
    expect(original).toBeDefined()
    const before = await store.dailyProjection(scope)

    const result = await store.updateQuality({
      factory_id: 'huakang-a', operation_id: 'quality-revision-1', expected_version: original!.version, report_id: original!.id,
      quality: {
        reported_qty: original!.reported_qty,
        good_qty: original!.good_qty,
        defective_qty: original!.defective_qty,
        pending_qty: original!.pending_qty,
        semi_finished_qty: original!.semi_finished_qty,
      },
      reason: '补录质检单',
    })
    const after = await store.dailyProjection(scope)
    const old = store.snapshot().reports.find((report) => report.id === original!.id)

    expect(old?.status).toBe('voided')
    expect(result.data.entity.status).toBe('corrected')
    expect(result.data.entity.replaces_report_id).toBe(original!.id)
    expect(after.data.items[0]).toMatchObject({
      good_qty: before.data.items[0]?.good_qty,
      defective_qty: before.data.items[0]?.defective_qty,
      reported_qty: before.data.items[0]?.reported_qty,
    })
  })
})

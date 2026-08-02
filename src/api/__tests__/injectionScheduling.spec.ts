import { describe, expect, it, vi } from 'vitest'
import { createInjectionSchedulingApi } from '@/api/injectionScheduling'

describe('injection scheduling api', () => {
  it('keeps every read request scoped to the selected factory', async () => {
    const get = vi.fn().mockResolvedValue({ data: { factory_id: 'huaxing', items: [] } })
    const api = createInjectionSchedulingApi({ get, post: vi.fn() })

    await api.listMachines('huaxing')
    await api.listMolds('huaxing')
    await api.getBacklog('huaxing')
    await api.getCurrentPlan('huaxing')

    expect(get).toHaveBeenNthCalledWith(1, '/injection-scheduling/machines', { params: { factory_id: 'huaxing' } })
    expect(get).toHaveBeenNthCalledWith(2, '/injection-scheduling/molds', { params: { factory_id: 'huaxing' } })
    expect(get).toHaveBeenNthCalledWith(3, '/injection-scheduling/backlog', { params: { factory_id: 'huaxing' } })
    expect(get).toHaveBeenNthCalledWith(4, '/injection-scheduling/plans/current', { params: { factory_id: 'huaxing' } })
  })

  it('uploads xlsx preview as multipart and confirms the exact batch', async () => {
    const batch = { id: 'batch-1', factory_id: 'huaxing', status: 'PREVIEW' }
    const post = vi.fn().mockResolvedValue({ data: batch })
    const api = createInjectionSchedulingApi({ get: vi.fn(), post })
    const file = new File(['xlsx'], '华兴计划.xlsx')

    await api.previewImport('huaxing', file, 0, 'preview-request-0001')
    const form = post.mock.calls[0]![1] as FormData
    expect(post.mock.calls[0]![0]).toBe('/injection-scheduling/imports/preview')
    expect(form.get('factory_id')).toBe('huaxing')
    expect(form.get('expected_revision')).toBe('0')
    expect(form.get('file')).toBe(file)
    expect(post.mock.calls[0]![2]).toEqual(expect.objectContaining({
      headers: expect.objectContaining({ 'X-Request-ID': 'preview-request-0001' }),
      timeout: 120_000,
    }))

    const payload = {
      factory_id: 'huaxing',
      expected_revision: 1,
      expected_plan_revision: 0,
      request_id: 'confirm-request-0001',
      confirm_mode: 'create_draft' as const,
      business_date: '2026-08-01',
      acknowledged_blocking_issue_ids: ['issue-1'],
    }
    await api.confirmImport('batch-1', payload)
    expect(post).toHaveBeenNthCalledWith(
      2,
      '/injection-scheduling/imports/batch-1/confirm',
      payload,
      { timeout: 120_000 },
    )
  })

  it('evaluates candidates and confirms a suggestion with both plan and rule revisions', async () => {
    const post = vi.fn().mockResolvedValue({ data: { results: [] } })
    const api = createInjectionSchedulingApi({ get: vi.fn(), post })

    await api.evaluateMatches('huaxing', 'order-1', ['machine-1'])
    expect(post).toHaveBeenNthCalledWith(
      1,
      '/injection-scheduling/matches/evaluate',
      { factory_id: 'huaxing', order_id: 'order-1', machine_ids: ['machine-1'] },
    )

    const payload = {
      factory_id: 'huaxing',
      order_id: 'order-1',
      machine_id: 'machine-1',
      expected_plan_revision: 3,
      expected_rule_revision: 7,
      request_id: 'match-confirm-0001',
      override_reason: '主管已核对模厚与夹具',
    }
    await api.confirmSuggestion('plan-1', payload)
    expect(post).toHaveBeenNthCalledWith(
      2,
      '/injection-scheduling/plans/plan-1/suggest',
      payload,
    )
  })
})

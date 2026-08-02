import { describe, expect, it, vi } from 'vitest'
import { HttpInjectionSchedulingRepository } from '@/repositories/injectionSchedulingRepository'

function createApi() {
  return {
    listMachines: vi.fn().mockResolvedValue({
      factory_id: 'huaxing',
      items: [{
        id: 'machine-1', factory_id: 'huaxing', machine_code: '旧2', area: '老车间', position: '2',
        machine_class: '32A', clamping_force_tons: 320, injection_capacity_g: 617,
        platen_x_mm: 680, platen_y_mm: 680, machine_type: '高速', robot_capabilities: ['双臂'],
        process_restrictions: ['抽芯不行'], status: 'available', revision: 1, updated_at: '2026-08-01 08:00',
      }],
    }),
    listMolds: vi.fn().mockResolvedValue({
      factory_id: 'huaxing',
      items: [{
        id: 'mold-1', factory_id: 'huaxing', mold_no: 'GT1214', name: '自卸车轮', length_mm: 550,
        width_mm: 450, height_mm: 850, recommended_machine_class: '32A', whole_shot_net_weight_g: 379,
        required_arm_type: '双臂', required_fixture_type: '吸盘', material_code: 'PP', material_name: 'PP 5100NA',
        color_profile: '黑色', data_quality_status: 'complete', revision: 1,
      }],
    }),
    getBacklog: vi.fn().mockResolvedValue({ factory_id: 'huaxing', items: [] }),
    getCurrentPlan: vi.fn().mockResolvedValue({
      factory_id: 'huaxing', polling_revision: 7,
      plan: {
        id: 'plan-1', factory_id: 'huaxing', business_date: '2026-08-01', status: 'DRAFT', revision: 3,
        updated_at: '2026-08-01 08:15',
        orders: [{
          id: 'order-1', factory_id: 'huaxing', order_no: '000123', item_no: '0045', product_name: '自卸车轮',
          mold_id: 'mold-1', order_quantity: 100, source_completed_quantity: 10, completed_quantity: 10,
          outstanding_quantity: 90, delivery_slack_days: 2, delivery_start_date: '2026-08-01',
          delivery_due_date: '2026-08-03', priority_code: 'URGENT', material_readiness_status: 'ready',
          warehouse_text: '007', remark: '正式订单', lineage: {}, status: 'SCHEDULED', revision: 2,
          updated_at: '2026-08-01 08:15',
        }],
        tasks: [{
          id: 'task-1', factory_id: 'huaxing', plan_id: 'plan-1', machine_id: 'machine-1', order_id: 'order-1',
          mold_id: 'mold-1', sequence_no: 1, execution_status: 'QUEUED', planned_start: '2026-08-01T08:00:00',
          planned_finish: '2026-08-01T16:00:00', shift_target_quantity: 40, reported_quantity: 10,
          delivery_slack_days: 2, manual_override_reason: '', source_sheet_name: '计划表', source_row: 5,
          revision: 1, updated_at: '2026-08-01 08:15',
        }],
      },
    }),
    saveShiftReport: vi.fn(),
    evaluateMatches: vi.fn(),
    confirmSuggestion: vi.fn(),
    previewImport: vi.fn(),
    confirmImport: vi.fn(),
  }
}

describe('HTTP injection scheduling repository', () => {
  it('maps formal plan orders, molds, machines and tasks without fabricating phase 5 candidates', async () => {
    const repository = new HttpInjectionSchedulingRepository(createApi() as never)
    const snapshot = await repository.getSnapshot('huaxing')

    expect(snapshot.sourceMode).toBe('live')
    expect(snapshot.planStatus).toBe('DRAFT')
    expect(snapshot.planRevision).toBe(3)
    expect(snapshot.tasks[0]).toEqual(expect.objectContaining({
      orderNo: '000123', itemNo: '0045', moldCode: 'GT1214', productName: '自卸车轮',
      material: 'PP 5100NA', fitDecision: 'REVIEW_REQUIRED', fitScore: 0,
    }))
    expect(snapshot.machines[0]).toEqual(expect.objectContaining({ code: '旧2', armCapability: '双臂' }))
    expect(snapshot.summary.scheduledTasks).toBe(1)
    expect(snapshot.summary.moldDimensionCompleteness).toBe(100)
  })

  it('chooses merge mode only when the current formal plan is a draft', async () => {
    const api = createApi()
    api.confirmImport.mockResolvedValue({ id: 'batch-1', status: 'CONFIRMED' })
    const repository = new HttpInjectionSchedulingRepository(api as never)
    const batch = { id: 'batch-1', revision: 1 } as never

    await repository.confirmImport('huaxing', batch, {
      businessDate: '2026-08-01', planStatus: 'DRAFT', planRevision: 3,
      acknowledgedBlockingIssueIds: ['issue-1'],
    })

    expect(api.confirmImport).toHaveBeenCalledWith('batch-1', expect.objectContaining({
      factory_id: 'huaxing', confirm_mode: 'merge_draft', expected_plan_revision: 3,
      acknowledged_blocking_issue_ids: ['issue-1'],
    }))
  })

  it('maps authoritative candidate reasons and requires a review override before confirmation', async () => {
    const api = createApi()
    api.getBacklog.mockResolvedValue({
      factory_id: 'huaxing',
      items: [{
        id: 'order-backlog', factory_id: 'huaxing', order_no: '000124', item_no: '0046',
        product_name: '追加单', mold_id: 'mold-1', order_quantity: 500, source_completed_quantity: 0,
        completed_quantity: 0, outstanding_quantity: 500, delivery_slack_days: 1,
        delivery_start_date: '2026-08-01', delivery_due_date: '2026-08-02', priority_code: 'URGENT',
        material_readiness_status: 'ready', warehouse_text: '', remark: '待排', lineage: {},
        status: 'BACKLOG', revision: 2, updated_at: '2026-08-01 09:00',
      }],
    })
    api.evaluateMatches.mockResolvedValue({
      factory_id: 'huaxing', order_id: 'order-backlog', mold_id: 'mold-1',
      rule_set_id: 'rules-1', rule_set_revision: 7,
      results: [{
        machine_id: 'machine-1', machine_code: '旧2', decision: 'REVIEW_REQUIRED', score: 82,
        hard_failures: [],
        warnings: [{ rule_code: 'MOLD_THICKNESS_UNCONFIRMED', label: '模厚范围', detail: '缺少机台模厚资料。' }],
        score_breakdown: [{ rule_code: 'same_mold', label: '同模连续', delta: 18, explanation: '队尾同模。' }],
        explanation: '旧2：资料待复核；规则 revision 7。', rule_set_id: 'rules-1', rule_set_revision: 7,
      }],
    })
    api.confirmSuggestion.mockResolvedValue({})
    const repository = new HttpInjectionSchedulingRepository(api as never)
    await repository.getSnapshot('huaxing')

    const backlog = await repository.evaluateBacklogOrder('huaxing', 'order-backlog')
    expect(backlog.candidates[0]).toEqual(expect.objectContaining({
      machineCode: '旧2', decision: 'REVIEW_REQUIRED', score: 82, ruleSetRevision: 7,
    }))
    expect(backlog.candidates[0]?.constraints[0]).toEqual(expect.objectContaining({
      key: 'mold-size', decision: 'REVIEW_REQUIRED',
    }))

    await expect(repository.assignBacklogOrder(
      'huaxing', backlog.id, 'machine-1', backlog.revision,
    )).rejects.toThrow('必须填写人工覆盖原因')

    await repository.assignBacklogOrder(
      'huaxing', backlog.id, 'machine-1', backlog.revision, '主管已核对模厚与夹具',
    )
    expect(api.confirmSuggestion).toHaveBeenCalledWith('plan-1', expect.objectContaining({
      expected_plan_revision: 3,
      expected_rule_revision: 7,
      override_reason: '主管已核对模厚与夹具',
    }))
  })
})

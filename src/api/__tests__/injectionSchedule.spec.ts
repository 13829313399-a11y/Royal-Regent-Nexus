import { describe, expect, it, vi } from 'vitest'
import {
  createInjectionScheduleApi,
  type InjectionScheduleHttpClient,
} from '@/api/injectionSchedule'
import type {
  InjectionMachineCreateInput,
  InjectionScheduleOperationRequest,
} from '@/types/injectionSchedule'

function client() {
  return {
    get: vi.fn(async () => ({ data: [] })),
    post: vi.fn(async () => ({ data: {} })),
    patch: vi.fn(async () => ({ data: {} })),
  } satisfies InjectionScheduleHttpClient
}

describe('injection schedule API adapter', () => {
  it('loads one factory workspace and normalizes the formal snake-case contract', async () => {
    const http = client()
    http.get.mockResolvedValueOnce({
      data: {
        mode: 'formal',
        factory_id: 'huaxing',
        workspace_revision: 7,
        active_version: {
          id: 'version-7',
          factory_id: 'huaxing',
          version_no: 7,
          base_version_id: 'version-6',
          plan_base_at: '2026-07-23T08:00:00+08:00',
        },
        tasks: [{
          id: 'task-1',
          factory_id: 'huaxing',
          version_id: 'version-7',
          machine_id: 'machine-1',
          sequence_no: 2,
          planned_qty: 18_000,
          planned_start_at: '2026-07-23T08:00:00+08:00',
          planned_finish_at: '2026-07-23T20:00:00+08:00',
          split_group_id: '',
          parent_task_id: '',
        }],
      },
    })
    const api = createInjectionScheduleApi(http)

    const workspace = await api.getWorkspace('hua xing', 'version-7')

    expect(http.get).toHaveBeenCalledWith(
      '/factories/hua%20xing/injection-schedule/workspace',
      { params: { version_id: 'version-7' } },
    )
    expect(workspace).toMatchObject({
      factoryId: 'huaxing',
      workspaceRevision: 7,
      activeVersion: {
        factoryId: 'huaxing',
        versionNo: 7,
        baseVersionId: 'version-6',
        planBaseAt: '2026-07-23T08:00:00+08:00',
      },
      tasks: [{
        factoryId: 'huaxing',
        versionId: 'version-7',
        machineId: 'machine-1',
        sequenceNo: 2,
        plannedQty: 18_000,
        plannedStartAt: '2026-07-23T08:00:00+08:00',
        plannedFinishAt: '2026-07-23T20:00:00+08:00',
        splitGroupId: '',
        parentTaskId: '',
      }],
    })
  })

  it('previews and confirms an immutable import batch without writing during preview', async () => {
    const http = client()
    http.post
      .mockResolvedValueOnce({
        data: {
          id: 'batch-1',
          factory_id: 'huaxing',
          status: 'previewed',
          revision: 3,
          source_file_name: '华兴啤机日排版表1.xlsx',
          summary: { machine_count: 76, error_count: 1 },
          issues: [{
            id: 'issue-1',
            factory_id: 'huaxing',
            batch_id: 'batch-1',
            source_sheet: '机台资料',
            source_row: 88,
            severity: 'warning',
            code: 'machine_class_missing',
            field_name: 'machine_class',
            blocking: true,
            raw_value: '',
            message: '机型待确认',
          }],
        },
      })
      .mockResolvedValueOnce({
        data: {
          id: 'batch-1',
          factory_id: 'huaxing',
          status: 'confirmed',
          revision: 4,
          confirm_reason: '确认导入华兴日排版',
        },
      })
    const api = createInjectionScheduleApi(http)
    const file = new File(
      ['xlsx'],
      '华兴啤机日排版表1.xlsx',
      { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
    )

    const preview = await api.previewImport('huaxing', file)
    const confirmed = await api.confirmImport('huaxing', preview.id, {
      expectedRevision: 3,
      mode: 'merge',
      businessDate: '2026-07-21',
      reason: '确认导入华兴日排版',
      resolutions: {
        'issue-1': {
          action: 'map',
          replacementValue: '7A',
          reason: '确认机型',
        },
      },
    })

    const previewCall = http.post.mock.calls[0]
    expect(previewCall[0]).toBe('/factories/huaxing/injection-schedule/imports')
    expect(previewCall[1]).toBeInstanceOf(FormData)
    expect((previewCall[1] as FormData).get('file')).toBe(file)
    expect(preview.summary.machineCount).toBe(76)
    expect(preview.issues[0]).toMatchObject({
      factoryId: 'huaxing',
      batchId: 'batch-1',
      sourceRow: 88,
      fieldName: 'machine_class',
      blocking: true,
    })
    expect(http.post).toHaveBeenNthCalledWith(
      2,
      '/factories/huaxing/injection-schedule/imports/batch-1/confirm',
      {
        expected_revision: 3,
        mode: 'merge',
        business_date: '2026-07-21',
        reason: '确认导入华兴日排版',
        resolutions: {
          'issue-1': {
            action: 'map',
            replacement_value: '7A',
            reason: '确认机型',
          },
        },
      },
    )
    expect(confirmed).toMatchObject({
      id: 'batch-1',
      factoryId: 'huaxing',
      status: 'confirmed',
      revision: 4,
      confirmReason: '确认导入华兴日排版',
    })
  })

  it('uses factory-scoped master create and revision-safe update endpoints', async () => {
    const http = client()
    const api = createInjectionScheduleApi(http)
    const machine = {
      machineCode: '旧2',
      machineName: '旧2号机',
      workshop: '啤机部',
      machineClass: '7A',
      tonnageT: 120,
      processType: '注塑',
      robotType: 'double',
      fixtureType: '',
      maxShotWeightG: 500,
      tieBarXMm: 450,
      tieBarYMm: 420,
      moldThicknessMinMm: 180,
      moldThicknessMaxMm: 420,
      openingStrokeMm: 520,
      ejectorStrokeMm: 160,
      status: 'available',
      availableAt: '2026-07-23T08:00:00+08:00',
      capabilities: [],
      materialRules: [],
      qualityStatus: 'verified',
    } satisfies InjectionMachineCreateInput

    await api.listMachines('huaxing')
    await api.createMachine('huaxing', machine)
    await api.updateMachine('huaxing', 'machine/old-2', 4, {
      maxShotWeightG: 520,
      status: 'maintenance',
    })

    expect(http.get).toHaveBeenCalledWith(
      '/factories/huaxing/injection-schedule/machines',
    )
    expect(http.post).toHaveBeenCalledWith(
      '/factories/huaxing/injection-schedule/machines',
      expect.objectContaining({
        machine_code: '旧2',
        machine_name: '旧2号机',
        max_shot_weight_g: 500,
        tie_bar_x_mm: 450,
        status: 'available',
      }),
    )
    expect(http.patch).toHaveBeenCalledWith(
      '/factories/huaxing/injection-schedule/machines/machine%2Fold-2',
      {
        expected_revision: 4,
        max_shot_weight_g: 520,
        status: 'maintenance',
      },
    )
  })

  it('sends one revision-safe command envelope with explicit manual confirmation', async () => {
    const http = client()
    const api = createInjectionScheduleApi(http)
    const input: InjectionScheduleOperationRequest = {
      expectedRevision: 9,
      reason: '调整急单并锁定',
      requestId: 'request-1',
      commands: [
        {
          type: 'move',
          taskId: 'task-1',
          machineId: 'machine-2',
          targetIndex: 1,
          reason: '降低交期风险',
          manualConfirmation: {
            confirmed: true,
            reason: '射胶量已由主管核对',
            constraintCodes: ['shot_capacity'],
          },
        },
        {
          type: 'lock',
          taskId: 'task-1',
          reason: '已确认开机',
          manualConfirmation: null,
        },
      ],
    }

    await api.executeOperations('huaxing', 'draft/9', input)

    expect(http.post).toHaveBeenCalledWith(
      '/factories/huaxing/injection-schedule/versions/draft%2F9/commands',
      {
        expected_revision: 9,
        reason: '调整急单并锁定',
        request_id: 'request-1',
        commands: [
          {
            type: 'move',
            task_id: 'task-1',
            machine_id: 'machine-2',
            target_index: 1,
            manual_confirmation: true,
            manual_confirmation_reason: '射胶量已由主管核对',
          },
          {
            type: 'lock',
            task_id: 'task-1',
            manual_confirmation: false,
            manual_confirmation_reason: '',
          },
        ],
      },
    )
  })

  it('covers draft create/load, validation, diff, publish, and historical clone paths', async () => {
    const http = client()
    const api = createInjectionScheduleApi(http)

    await api.createDraftVersion('huaxing', {
      name: '7月23日晚班草稿',
      businessDate: '2026-07-23',
      baseVersionId: 'published-17',
      planBaseAt: '2026-07-23T20:00:00+08:00',
    })
    await api.getVersion('huaxing', 'draft-18')
    await api.validateVersion('huaxing', 'draft-18', 2)
    await api.getVersionDiff('huaxing', 'draft-18', 'published-17')
    await api.getVersionDiff('huaxing', 'first-draft')
    await api.publishVersion('huaxing', 'draft-18', {
      expectedRevision: 2,
      validationRunId: 'validation-1',
      reason: '主管确认发布',
    })
    await api.cloneVersionAsDraft('huaxing', 'published-16', {
      name: '基于 V16 的恢复草稿',
      reason: '历史版本恢复演练',
    })

    expect(http.post).toHaveBeenCalledWith(
      '/factories/huaxing/injection-schedule/versions',
      {
        name: '7月23日晚班草稿',
        business_date: '2026-07-23',
        base_version_id: 'published-17',
        plan_base_at: '2026-07-23T20:00:00+08:00',
      },
    )
    expect(http.get).toHaveBeenCalledWith(
      '/factories/huaxing/injection-schedule/versions/draft-18',
    )
    expect(http.post).toHaveBeenCalledWith(
      '/factories/huaxing/injection-schedule/versions/draft-18/validate',
      { expected_revision: 2 },
    )
    expect(http.get).toHaveBeenCalledWith(
      '/factories/huaxing/injection-schedule/versions/draft-18/diff',
      { params: { against_version_id: 'published-17' } },
    )
    expect(http.get).toHaveBeenCalledWith(
      '/factories/huaxing/injection-schedule/versions/first-draft/diff',
    )
    expect(http.post).toHaveBeenCalledWith(
      '/factories/huaxing/injection-schedule/versions/draft-18/publish',
      {
        expected_revision: 2,
        validation_run_id: 'validation-1',
        reason: '主管确认发布',
      },
    )
    expect(http.post).toHaveBeenCalledWith(
      '/factories/huaxing/injection-schedule/versions/published-16/clone',
      { name: '基于 V16 的恢复草稿', reason: '历史版本恢复演练' },
    )
  })

  it('keeps Phase 3 recommendations and nested rule configuration on the exact wire contract', async () => {
    const http = client()
    const ruleDocument = {
      schema_version: 1,
      shot_safety_factor: 0.8,
      default_setup_hours: 1,
      minimum_task_hours: 2,
      allow_missing_data_in_draft_with_manual_confirmation: true,
      availability_calendar_verified_through: '2026-07-31T23:59:59+08:00',
      color_rank_dark_threshold: 6,
      scoring_weights: { due_date: 35, split_penalty: 8 },
      color_transition_matrix: [{ from_code: '*', to_code: '*', minutes: 20 }],
      material_transition_matrix: [{ from_code: '*', to_code: '*', minutes: 30 }],
      setup_minutes: [{
        machine_class: '*',
        same_mold_minutes: 0,
        mold_change_minutes: 60,
      }],
      unavailable_windows: [{
        scope: 'machine',
        machine_id: 'machine/2',
        start_at: '2026-07-24T08:00:00+08:00',
        end_at: '2026-07-24T12:00:00+08:00',
        reason: '计划保养',
      }],
    }
    http.get
      .mockResolvedValueOnce({
        data: {
          factory_id: 'huaxing',
          version_id: 'draft/18',
          version_revision: 2,
          order_id: 'order/2',
          order_revision: 4,
          planned_qty: 600,
          rule_config_revision: 3,
          current_rule_config_revision: 4,
          rule_config_hash: 'rules-hash',
          uses_version_rule_snapshot: true,
          generated_at: '2026-07-23T08:00:00+08:00',
          total_candidates: 1,
          eligible_count: 0,
          manual_review_count: 1,
          blocked_count: 0,
          candidates: [{
            rank: null,
            advisory_rank: 1,
            machine_id: 'machine/2',
            machine_code: '旧2',
            machine_name: '旧2号机',
            target_index: 1,
            status: 'manual_review',
            eligible: false,
            requires_manual_confirmation: true,
            auto_publish_allowed: false,
            hard_constraints: [],
            score: {
              total: 52,
              max_total: 100,
              advisory: true,
              breakdown: [],
              transition: {
                color_minutes: 20,
                setup_minutes_before: 60,
                setup_minutes_after: 15,
                replaced_setup_minutes: 10,
                setup_minutes_delta: 65,
              },
              estimated: { duration_hours: 8 },
            },
            recommendation_context_hash: 'context-hash',
          }],
        },
      })
      .mockResolvedValueOnce({
        data: {
          factory_id: 'huaxing',
          config: ruleDocument,
          revision: 3,
          updated_by: 'planner-1',
          updated_at: '2026-07-23T08:00:00+08:00',
        },
      })
    http.patch.mockResolvedValueOnce({
      data: {
        factory_id: 'huaxing',
        config: ruleDocument,
        revision: 4,
        updated_by: 'planner-1',
        updated_at: '2026-07-23T09:00:00+08:00',
      },
    })
    const api = createInjectionScheduleApi(http)

    const recommendation = await api.getRecommendations(
      'huaxing',
      'draft/18',
      'order/2',
      { limit: 20 },
    )
    const current = await api.getRuleConfig('huaxing')
    const saved = await api.updateRuleConfig('huaxing', {
      expectedRevision: current.revision,
      reason: '录入机台保养窗口',
      config: current.config,
    })

    expect(http.get).toHaveBeenNthCalledWith(
      1,
      '/factories/huaxing/injection-schedule/versions/draft%2F18/orders/order%2F2/recommendations',
      { params: { limit: 20 } },
    )
    expect(recommendation).toMatchObject({
      plannedQty: 600,
      usesVersionRuleSnapshot: true,
      candidates: [{
        status: 'manual_review',
        recommendationContextHash: 'context-hash',
        score: {
          advisory: true,
          transition: {
            colorMinutes: 20,
            setupMinutesBefore: 60,
            setupMinutesAfter: 15,
            replacedSetupMinutes: 10,
            setupMinutesDelta: 65,
          },
        },
      }],
    })
    expect(http.patch).toHaveBeenCalledWith(
      '/factories/huaxing/injection-schedule/rule-config',
      {
        expected_revision: 3,
        reason: '录入机台保养窗口',
        config: ruleDocument,
      },
    )
    expect(saved.revision).toBe(4)
    expect(saved.config.availabilityCalendarVerifiedThrough)
      .toBe('2026-07-31T23:59:59+08:00')
    expect(saved.config.unavailableWindows[0]).toMatchObject({
      machineId: 'machine/2',
      reason: '计划保养',
    })
  })

  it('rejects reasonless mutations before issuing a request', async () => {
    const http = client()
    const api = createInjectionScheduleApi(http)

    await expect(api.cloneVersionAsDraft('huaxing', 'v1', {
      name: '',
      reason: '   ',
    })).rejects.toThrow('排程变更原因不能为空')

    expect(http.post).not.toHaveBeenCalled()
  })

  it('keeps Phase 4 auto-draft, replan, and audited shift actuals on the exact wire contract', async () => {
    const http = client()
    http.get.mockResolvedValueOnce({ data: [] })
    const api = createInjectionScheduleApi(http)
    const autoContextHash = 'a'.repeat(64)
    const replanContextHash = 'b'.repeat(64)

    await api.generateAutoDraft('huaxing', 'draft/18', {
      expectedRevision: 7,
      reason: '生成本周自动排程草稿',
      name: '自动草稿 V18',
      orderIds: ['order/2'],
      planningHorizonEndAt: '2026-07-31T23:59:59+08:00',
      requestId: 'auto-request-1',
      dryRun: false,
      expectedContextHash: autoContextHash,
    })
    await api.replanVersion('huaxing', 'draft/18', {
      expectedRevision: 8,
      trigger: {
        type: 'machine_downtime',
        machineId: 'machine/23',
        startAt: '2026-07-25T08:00:00+08:00',
        endAt: '2026-07-25T16:00:00+08:00',
        reason: 'New23 临时停机',
      },
      scope: {
        freezeBeforeAt: '2026-07-25T08:00:00+08:00',
        maxAffectedMachines: 8,
        maxAffectedTasks: 120,
      },
      reason: 'New23 临时停机局部重排',
      requestId: 'replan-request-1',
      dryRun: false,
      expectedContextHash: replanContextHash,
    })
    await api.listActuals('huaxing', {
      versionId: 'draft/18',
      dateFrom: '2026-07-24',
      dateTo: '2026-07-25',
    })
    await api.writeActual('huaxing', {
      versionId: 'draft/18',
      taskId: 'task/1',
      orderId: 'order/2',
      machineId: 'machine/23',
      shiftDate: '2026-07-25',
      shift: 'day',
      source: 'manual',
      legacyShiftCode: 'A',
      targetQty: null,
      actualQty: 12_500,
      varianceReason: '',
      expectedVersionRevision: 9,
      expectedOrderRevision: 4,
      reason: '录入白班 A 实绩',
      requestId: 'actual-request-1',
    })
    await api.correctActual('huaxing', 'actual/1', {
      expectedRevision: 1,
      expectedVersionRevision: 10,
      expectedOrderRevision: 5,
      actualQty: 12_300,
      reason: '班组复核后更正',
      requestId: 'actual-correction-1',
    })

    expect(http.post).toHaveBeenNthCalledWith(
      1,
      '/factories/huaxing/injection-schedule/versions/draft%2F18/auto-draft',
      {
        expected_revision: 7,
        reason: '生成本周自动排程草稿',
        name: '自动草稿 V18',
        order_ids: ['order/2'],
        planning_horizon_end_at: '2026-07-31T23:59:59+08:00',
        request_id: 'auto-request-1',
        dry_run: false,
        expected_context_hash: autoContextHash,
      },
    )
    expect(http.post).toHaveBeenNthCalledWith(
      2,
      '/factories/huaxing/injection-schedule/versions/draft%2F18/replan',
      {
        expected_revision: 8,
        trigger: {
          type: 'machine_downtime',
          machine_id: 'machine/23',
          start_at: '2026-07-25T08:00:00+08:00',
          end_at: '2026-07-25T16:00:00+08:00',
          reason: 'New23 临时停机',
        },
        scope: {
          freeze_before_at: '2026-07-25T08:00:00+08:00',
          max_affected_machines: 8,
          max_affected_tasks: 120,
        },
        reason: 'New23 临时停机局部重排',
        request_id: 'replan-request-1',
        dry_run: false,
        expected_context_hash: replanContextHash,
      },
    )
    expect(http.get).toHaveBeenCalledWith(
      '/factories/huaxing/injection-schedule/actuals',
      {
        params: {
          version_id: 'draft/18',
          date_from: '2026-07-24',
          date_to: '2026-07-25',
        },
      },
    )
    expect(http.post).toHaveBeenNthCalledWith(
      3,
      '/factories/huaxing/injection-schedule/actuals',
      {
        version_id: 'draft/18',
        task_id: 'task/1',
        order_id: 'order/2',
        machine_id: 'machine/23',
        shift_date: '2026-07-25',
        shift: 'day',
        source: 'manual',
        legacy_shift_code: 'A',
        target_qty: null,
        actual_qty: 12_500,
        variance_reason: '',
        expected_version_revision: 9,
        expected_order_revision: 4,
        reason: '录入白班 A 实绩',
        request_id: 'actual-request-1',
      },
    )
    expect(http.patch).toHaveBeenCalledWith(
      '/factories/huaxing/injection-schedule/actuals/actual%2F1',
      {
        expected_revision: 1,
        expected_version_revision: 10,
        expected_order_revision: 5,
        actual_qty: 12_300,
        reason: '班组复核后更正',
        request_id: 'actual-correction-1',
      },
    )
  })

  it('rejects a Phase 4 apply before transport when no preview context hash is supplied', async () => {
    const http = client()
    const api = createInjectionScheduleApi(http)

    await expect(api.generateAutoDraft('huaxing', 'draft-18', {
      expectedRevision: 7,
      reason: '直接应用自动排程',
      dryRun: false,
    })).rejects.toThrow('必须先预览')
    await expect(api.replanVersion('huaxing', 'draft-18', {
      expectedRevision: 7,
      trigger: {
        type: 'urgent_order',
        orderId: 'order-1',
        reason: '急单',
      },
      scope: {
        maxAffectedMachines: 8,
        maxAffectedTasks: 120,
      },
      reason: '直接应用局部重排',
      dryRun: false,
    })).rejects.toThrow('必须先预览')

    expect(http.post).not.toHaveBeenCalled()
  })
})

import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MachineTimelineBoard from '@/components/modules/production/injection-schedule/MachineTimelineBoard.vue'
import Phase4DynamicSchedulingPanel from '@/components/modules/production/injection-schedule/Phase4DynamicSchedulingPanel.vue'
import ScheduleMasterEditor from '@/components/modules/production/injection-schedule/ScheduleMasterEditor.vue'
import ScheduleTaskInspector from '@/components/modules/production/injection-schedule/ScheduleTaskInspector.vue'
import ScheduleVersionPanel from '@/components/modules/production/injection-schedule/ScheduleVersionPanel.vue'
import UnscheduledOrderTable from '@/components/modules/production/injection-schedule/UnscheduledOrderTable.vue'
import { useAuthStore } from '@/stores/auth'
import type {
  InjectionAutomationResult,
  InjectionFormalScheduleTask,
  InjectionMachineRecord,
  InjectionMoldRecord,
  InjectionOrderRecommendationResponse,
  InjectionOrderRecord,
  InjectionPlanVersion,
  InjectionScheduleRuleConfigV3,
  InjectionScheduleWorkspace,
} from '@/types/injectionSchedule'
import InjectionProductionHubView from '@/views/InjectionProductionHubView.vue'

const apiMock = vi.hoisted(() => ({
  getWorkspace: vi.fn(),
  previewImport: vi.fn(),
  listImports: vi.fn(),
  getImport: vi.fn(),
  confirmImport: vi.fn(),
  listMachines: vi.fn(),
  createMachine: vi.fn(),
  updateMachine: vi.fn(),
  listMolds: vi.fn(),
  createMold: vi.fn(),
  updateMold: vi.fn(),
  listOrders: vi.fn(),
  createOrder: vi.fn(),
  updateOrder: vi.fn(),
  listVersions: vi.fn(),
  createDraftVersion: vi.fn(),
  getVersion: vi.fn(),
  executeOperations: vi.fn(),
  validateVersion: vi.fn(),
  getVersionDiff: vi.fn(),
  publishVersion: vi.fn(),
  cloneVersionAsDraft: vi.fn(),
  getRecommendations: vi.fn(),
  getRuleConfig: vi.fn(),
  updateRuleConfig: vi.fn(),
  generateAutoDraft: vi.fn(),
  replanVersion: vi.fn(),
  listActuals: vi.fn(),
  writeActual: vi.fn(),
  correctActual: vi.fn(),
}))

vi.mock('@/api/injectionSchedule', () => ({ injectionScheduleApi: apiMock }))

const now = '2026-07-23T08:00:00+08:00'

function version(overrides: Partial<InjectionPlanVersion> = {}): InjectionPlanVersion {
  return {
    id: 'version-draft-18',
    factoryId: 'huaxing',
    versionNo: 18,
    name: '7月23日人工草稿',
    status: 'draft',
    revision: 2,
    businessDate: '2026-07-23',
    planBaseAt: now,
    baseVersionId: 'version-published-17',
    sourceBatchId: 'batch-1',
    rulesSnapshot: {},
    dataHash: 'data-hash',
    validationHash: '',
    summary: { taskCount: 1 },
    createdAt: now,
    createdBy: 'planner-1',
    createdByName: '计划员',
    updatedAt: now,
    updatedBy: 'planner-1',
    publishedAt: '',
    publishedBy: '',
    publishedByName: '',
    publishReason: '',
    supersededAt: '',
    ...overrides,
  }
}

function machine(id: string, machineCode: string): InjectionMachineRecord {
  return {
    id,
    factoryId: 'huaxing',
    machineCode,
    machineName: `${machineCode}号机`,
    workshop: 'old',
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
    availableAt: now,
    capabilities: [],
    materialRules: [],
    qualityStatus: 'ready',
    provenance: {},
    sourceBatchId: 'batch-1',
    revision: 1,
    createdBy: 'planner-1',
    createdAt: now,
    updatedBy: 'planner-1',
    updatedAt: now,
  }
}

function mold(): InjectionMoldRecord {
  return {
    id: 'mold-1',
    factoryId: 'huaxing',
    moldCode: 'M-01',
    normalizedMoldCode: 'M-01',
    moldName: '外壳模',
    machineClass: '7A',
    robotType: 'double',
    fixtureType: '',
    lengthMm: 400,
    widthMm: 360,
    heightMm: 280,
    moldWeightKg: 300,
    grossShotWeightG: 220,
    cavities: 2,
    cycleSeconds: 40,
    requiredCapabilities: [],
    materialRules: [],
    qualityStatus: 'ready',
    provenance: {},
    sourceBatchId: 'batch-1',
    revision: 1,
    createdBy: 'planner-1',
    createdAt: now,
    updatedBy: 'planner-1',
    updatedAt: now,
  }
}

function order(id: string, orderNo: string): InjectionOrderRecord {
  return {
    id,
    factoryId: 'huaxing',
    naturalKey: orderNo,
    orderNo,
    productCode: `ITEM-${id}`,
    productName: `${orderNo}产品`,
    moldCode: 'M-01',
    color: '蓝色',
    pigment: 'BL',
    material: 'ABS',
    machineClass: '7A',
    orderQty: 1000,
    producedQty: 100,
    outstandingQty: 900,
    dailyTargetQty: 450,
    deliveryDueDate: '2026-07-28',
    priorityCode: 'P1',
    priorityFlag: 'P1',
    status: 'open',
    importedAssignedMachineCode: '',
    qualityStatus: 'ready',
    importedPlanStartAt: '',
    importedPlanFinishAt: '',
    sourceSheet: '计划表',
    sourceRow: 10,
    sourceValues: {},
    provenance: {},
    sourceBatchId: 'batch-1',
    revision: 1,
    createdBy: 'planner-1',
    createdAt: now,
    updatedBy: 'planner-1',
    updatedAt: now,
  }
}

function task(overrides: Partial<InjectionFormalScheduleTask> = {}): InjectionFormalScheduleTask {
  return {
    id: 'task-1',
    factoryId: 'huaxing',
    versionId: 'version-draft-18',
    orderId: 'order-1',
    orderNo: 'SO-001',
    productCode: 'ITEM-1',
    productName: 'SO-001产品',
    moldId: 'mold-1',
    moldCode: 'M-01',
    machineId: 'machine-1',
    machineCode: '旧1',
    sequenceNo: 0,
    plannedQty: 900,
    plannedStartAt: now,
    plannedFinishAt: '2026-07-23T16:00:00+08:00',
    setupHours: 0.5,
    durationHours: 7.5,
    locked: false,
    splitGroupId: '',
    parentTaskId: '',
    riskLevel: 'none',
    riskReasons: [],
    revision: 2,
    ...overrides,
  }
}

function workspace(overrides: Partial<InjectionScheduleWorkspace> = {}): InjectionScheduleWorkspace {
  const current = version()
  return {
    mode: 'formal',
    factoryId: 'huaxing',
    workspaceRevision: 2,
    activeVersion: current,
    versions: [
      current,
      version({
        id: 'version-published-17',
        versionNo: 17,
        name: '已发布 V17',
        status: 'published',
        revision: 1,
        baseVersionId: null,
      }),
    ],
    machines: [machine('machine-1', '旧1'), machine('machine-2', '旧2')],
    molds: [mold()],
    orders: [order('order-1', 'SO-001'), order('order-2', 'SO-002')],
    tasks: [task()],
    conflicts: [],
    ruleConfig: {
      factoryId: 'huaxing',
      config: {},
      revision: 1,
      updatedBy: 'planner-1',
      updatedAt: now,
    },
    ...overrides,
  }
}

function recommendationResponse(
  orderId = 'order-2',
  overrides: Partial<InjectionOrderRecommendationResponse> = {},
): InjectionOrderRecommendationResponse {
  return {
    factoryId: 'huaxing',
    versionId: 'version-draft-18',
    versionRevision: 2,
    orderId,
    orderRevision: 1,
    plannedQty: 900,
    ruleConfigRevision: 1,
    currentRuleConfigRevision: 1,
    ruleConfigHash: 'rules-hash',
    usesVersionRuleSnapshot: true as const,
    generatedAt: now,
    totalCandidates: 1,
    eligibleCount: 1,
    manualReviewCount: 0,
    blockedCount: 0,
    candidates: [{
      rank: 1,
      advisoryRank: null,
      machineId: 'machine-1',
      machineCode: '旧1',
      machineName: '旧1号机',
      targetIndex: 1,
      status: 'eligible' as const,
      eligible: true,
      requiresManualConfirmation: false,
      autoPublishAllowed: true,
      hardConstraints: [{
        code: 'shot_capacity',
        status: 'pass' as const,
        blocking: false,
        message: '安全射胶量通过',
        details: {},
      }],
      score: {
        total: 80,
        maxTotal: 100,
        advisory: false,
        breakdown: [],
        transition: {
          previousTaskId: 'task-1',
          nextTaskId: '',
          previousMoldCode: 'M-01',
          nextMoldCode: '',
          previousColor: '蓝色',
          previousColorRank: 4,
          targetColor: 'BL',
          targetColorRank: 5,
          nextColor: '',
          nextColorRank: null,
          previousMaterial: 'ABS',
          nextMaterial: '',
          sameMold: true,
          colorMinutes: 0,
          materialMinutes: 0,
          afterColorMinutes: 0,
          afterMaterialMinutes: 0,
          replacedColorMinutes: 0,
          replacedMaterialMinutes: 0,
          setupMinutesBefore: 0,
          setupMinutesAfter: 0,
          replacedSetupMinutes: 0,
          setupMinutesDelta: 0,
          colorMatrixMatch: 'same',
          materialMatrixMatch: 'same',
          afterColorMatrixMatch: 'none',
          afterMaterialMatrixMatch: 'none',
          replacedColorMatrixMatch: 'none',
          replacedMaterialMatrixMatch: 'none',
        },
        estimated: {
          slotStartAt: '2026-07-23T16:00:00+08:00',
          productionStartAt: '2026-07-23T16:00:00+08:00',
          finishAt: '2026-07-24T08:00:00+08:00',
          durationHours: 16,
          deliverySlackHours: 96,
          downstreamShiftMinutes: 0,
          skippedUnavailableWindows: [],
        },
      },
      recommendationContextHash: 'recommendation-context',
    }],
    ...overrides,
  }
}

function phase3RuleConfig(
  overrides: Partial<InjectionScheduleRuleConfigV3> = {},
): InjectionScheduleRuleConfigV3 {
  return {
    factoryId: 'huaxing',
    revision: 3,
    updatedBy: 'planner-1',
    updatedAt: now,
    config: {
      schemaVersion: 1,
      shotSafetyFactor: 0.8,
      defaultSetupHours: 1,
      minimumTaskHours: 2,
      allowMissingDataInDraftWithManualConfirmation: true,
      availabilityCalendarVerifiedThrough: '2026-07-31T23:59:59+08:00',
      colorRankDarkThreshold: 6,
      scoringWeights: {
        dueDate: 35,
        sequenceAffinity: 20,
        setupEfficiency: 15,
        colorTransition: 8,
        loadBalance: 7,
        downstreamPriority: 5,
        exactMatch: 5,
        splitPenalty: 3,
        specialHandlingPenalty: 2,
      },
      colorTransitionMatrix: [{ fromCode: '*', toCode: '*', minutes: 20 }],
      materialTransitionMatrix: [{ fromCode: '*', toCode: '*', minutes: 30 }],
      setupMinutes: [{
        machineClass: '*',
        sameMoldMinutes: 0,
        moldChangeMinutes: 60,
      }],
      unavailableWindows: [{
        scope: 'machine',
        machineId: 'machine-2',
        startAt: '2026-07-24T08:00:00+08:00',
        endAt: '2026-07-24T12:00:00+08:00',
        reason: '计划保养',
      }],
    },
    ...overrides,
  }
}

function phase4AutoResult(
  status: 'previewed' | 'applied',
  overrides: Partial<InjectionAutomationResult> = {},
): InjectionAutomationResult {
  const resultVersion = version({
    revision: status === 'applied' ? 3 : 2,
    updatedAt: '2026-07-25T09:00:00+08:00',
  })
  return {
    version: resultVersion,
    tasks: [task({
      id: 'task-auto-1',
      parentTaskId: 'task-1',
      source: 'auto',
      revision: status === 'applied' ? 3 : 2,
      plannedFinishAt: '2026-07-23T17:00:00+08:00',
    })],
    conflicts: [],
    affectedMachineIds: ['machine-1'],
    affectedOrderIds: ['order-1'],
    affectedTaskIds: ['task-auto-1'],
    run: {
      id: status === 'applied' ? 'run-auto-apply-1' : 'run-auto-preview-1',
      factoryId: 'huaxing',
      sourceVersionId: 'version-draft-18',
      resultVersionId: 'version-draft-18',
      triggerType: 'auto_draft',
      status,
      sourceRevision: 2,
      resultRevision: status === 'applied' ? 3 : 2,
      contextHash: 'a'.repeat(64),
      reason: '按当前交期生成自动草稿',
      requestId: status === 'applied' ? 'apply-request' : 'preview-request',
      affectedMachineIds: ['machine-1'],
      affectedOrderIds: ['order-1'],
      affectedTaskIds: ['task-auto-1'],
      impact: {
        consideredOrderCount: 2,
        scheduledOrderCount: 1,
        manualReviewOrderCount: 1,
        blockedOrderCount: 0,
        unscheduledOrderIds: ['order-2'],
        movedTaskCount: 1,
        etaDelayedTaskCount: 1,
        totalEtaShiftMinutes: 60,
        beforeTaskCount: 1,
        afterTaskCount: 1,
        rows: [{
          taskId: 'task-auto-1',
          sourceTaskId: 'task-1',
          orderId: 'order-1',
          machineIdBefore: 'machine-1',
          machineIdAfter: 'machine-1',
          sequenceNoBefore: 0,
          sequenceNoAfter: 0,
          plannedQtyBefore: 900,
          plannedQtyAfter: 900,
          plannedStartAtBefore: now,
          plannedStartAtAfter: now,
          plannedFinishAtBefore: '2026-07-23T16:00:00+08:00',
          plannedFinishAtAfter: '2026-07-23T17:00:00+08:00',
          setupHoursBefore: 0.5,
          setupHoursAfter: 0.5,
          etaShiftMinutes: 60,
          executionStatusBefore: 'planned',
          executionStatusAfter: 'planned',
        }],
      },
      createdBy: 'planner-1',
      createdByName: '计划员',
      createdAt: '2026-07-25T09:00:00+08:00',
    },
    ...overrides,
  }
}

async function mountFormalHub(permissions = [
  'injection_schedule:read',
  'injection_schedule:edit',
  'injection_schedule:publish',
  'injection_schedule:config',
], target = '/modules/production/injection-scheduling?factory=huaxing') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const authStore = useAuthStore()
  authStore.permissions = permissions
  authStore.factoryScopes = ['huaxing']
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{
      path: '/modules/production/injection-scheduling',
      component: InjectionProductionHubView,
    }],
  })
  await router.push(target)
  await router.isReady()
  const wrapper = mount(InjectionProductionHubView, {
    global: {
      plugins: [pinia, router],
      stubs: { AccountMenu: true },
    },
  })
  await flushPromises()
  return wrapper
}

describe('injection production hub Phase 2 integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.getWorkspace.mockResolvedValue(workspace())
    apiMock.getRecommendations.mockResolvedValue(recommendationResponse())
    apiMock.getRuleConfig.mockResolvedValue(phase3RuleConfig())
    apiMock.updateRuleConfig.mockResolvedValue(phase3RuleConfig({ revision: 4 }))
    apiMock.listActuals.mockResolvedValue([])
    apiMock.executeOperations.mockImplementation(async (
      _factoryId: string,
      _versionId: string,
      request: { commands: Array<Record<string, unknown>> },
    ) => {
      const command = request.commands[0]
      const moved = command?.type === 'move'
      return {
        version: version({ revision: 3 }),
        tasks: [task(moved
          ? {
              machineId: String(command.machineId),
              machineCode: '旧2',
              revision: 3,
            }
          : { revision: 3 })],
        conflicts: [],
        affectedMachineIds: moved ? ['machine-1', 'machine-2'] : ['machine-1'],
      }
    })
    apiMock.validateVersion.mockResolvedValue({
      id: 'validation-1',
      factoryId: 'huaxing',
      versionId: 'version-draft-18',
      versionRevision: 2,
      dataHash: 'data-hash',
      resultHash: 'result-hash',
      status: 'passed',
      blockingCount: 0,
      warningCount: 0,
      createdBy: 'planner-1',
      createdByName: '计划员',
      createdAt: now,
      items: [{
        id: 'validation-pass-1',
        runId: 'validation-1',
        versionId: 'version-draft-18',
        taskId: 'task-1',
        constraintCode: 'machine_status',
        status: 'pass',
        severity: 'info',
        blocking: false,
        message: '机台状态可用',
        details: {},
      }],
    })
    apiMock.getVersionDiff.mockResolvedValue({
      versionId: 'version-draft-18',
      againstVersionId: 'version-published-17',
      summary: {},
      items: [],
    })
  })

  it('opens the Phase 4 operations section directly from the route query without fallback writes', async () => {
    const wrapper = await mountFormalHub(
      undefined,
      '/modules/production/injection-scheduling?factory=huaxing&section=operations',
    )

    expect(wrapper.text()).toContain('自动草稿、局部重排与白夜班实绩')
    expect(wrapper.text()).toContain('白班（A）/ 夜班（B）实绩回写')
    expect(wrapper.text()).toContain('不代表 IoT 自动采集')
    expect(wrapper.text()).toContain('从当前草稿生成新草稿，不自动发布')
    expect(apiMock.listActuals).toHaveBeenCalledWith('huaxing', {
      versionId: 'version-draft-18',
    })
    expect(apiMock.generateAutoDraft).not.toHaveBeenCalled()
    expect(apiMock.replanVersion).not.toHaveBeenCalled()
    expect(apiMock.writeActual).not.toHaveBeenCalled()
  })

  it('uses the server priorityCode for formal order mapping even when raw priority text disagrees', async () => {
    apiMock.getWorkspace.mockResolvedValueOnce(workspace({
      orders: [{
        ...order('order-2', 'SO-002'),
        priorityCode: 'P3',
        priorityFlag: 'P0 特急（历史原始文字）',
      }],
    }))
    const wrapper = await mountFormalHub(
      undefined,
      '/modules/production/injection-scheduling?factory=huaxing&section=orders',
    )

    const formalOrders = wrapper.findComponent(UnscheduledOrderTable)
      .props('orders') as Array<{ priority: string }>
    expect(formalOrders).toHaveLength(1)
    expect(formalOrders[0]?.priority).toBe('P3')
  })

  it('keeps every Phase 4 endpoint disabled in a read-only operations view', async () => {
    const wrapper = await mountFormalHub(
      ['injection_schedule:read'],
      '/modules/production/injection-scheduling?factory=huaxing&section=operations',
    )

    expect(apiMock.listActuals).not.toHaveBeenCalled()
    expect(apiMock.generateAutoDraft).not.toHaveBeenCalled()
    expect(apiMock.replanVersion).not.toHaveBeenCalled()
    expect(apiMock.writeActual).not.toHaveBeenCalled()
    const writeButtons = wrapper.findAll('button').filter((button) => (
      button.text().includes('预览自动排程影响')
      || button.text().includes('预览局部重排影响')
      || button.text().includes('回写并滚动计算')
    ))
    expect(writeButtons).toHaveLength(3)
    expect(writeButtons.every((button) => button.attributes('disabled') !== undefined)).toBe(true)
  })

  it('previews Phase 4 automation without changing the workspace, then applies only after explicit confirmation', async () => {
    apiMock.generateAutoDraft
      .mockResolvedValueOnce(phase4AutoResult('previewed'))
      .mockResolvedValueOnce(phase4AutoResult('applied'))
    const wrapper = await mountFormalHub(
      undefined,
      '/modules/production/injection-scheduling?factory=huaxing&section=operations',
    )

    wrapper.findComponent(Phase4DynamicSchedulingPanel).vm.$emit(
      'generateAutoDraft',
      {
        reason: '按当前交期生成自动草稿',
        horizonEndAt: '',
      },
    )
    await flushPromises()

    expect(apiMock.generateAutoDraft).toHaveBeenCalledTimes(1)
    expect(apiMock.generateAutoDraft.mock.calls[0][2]).toMatchObject({
      expectedRevision: 2,
      dryRun: true,
    })
    expect(apiMock.generateAutoDraft.mock.calls[0][2]).not.toHaveProperty(
      'expectedContextHash',
    )
    expect(document.body.textContent).toContain('确认前不会创建或修改草稿')
    expect(wrapper.text()).toContain('Revision2')

    const confirmButton = Array.from(document.body.querySelectorAll('button')).find(
      (button) => button.textContent?.trim() === '确认应用到草稿',
    )
    expect(confirmButton).toBeTruthy()
    confirmButton!.click()
    await flushPromises()

    expect(apiMock.generateAutoDraft).toHaveBeenCalledTimes(2)
    expect(apiMock.generateAutoDraft.mock.calls[1][2]).toMatchObject({
      expectedRevision: 2,
      dryRun: false,
      expectedContextHash: 'a'.repeat(64),
    })
    expect(wrapper.text()).toContain('Revision3')
    expect(document.body.textContent).toContain('自动排程草稿已生成')
  })

  it('preserves source=auto when adapting formal tasks for the timeline', async () => {
    apiMock.getWorkspace.mockResolvedValueOnce(workspace({
      tasks: [task({ source: 'auto' })],
    }))
    const wrapper = await mountFormalHub()

    const timelineTasks = wrapper.findComponent(MachineTimelineBoard)
      .props('tasks') as Array<{ source: string }>
    expect(timelineTasks[0]?.source).toBe('auto')
  })

  it('records actuals from a published snapshot by switching only to the returned rolling draft', async () => {
    const published = version({
      id: 'version-published-18',
      status: 'published',
      revision: 4,
      baseVersionId: null,
      publishedAt: now,
      publishedBy: 'planner-1',
      publishedByName: '计划员',
    })
    const publishedTask = task({
      versionId: published.id,
      revision: published.revision,
    })
    apiMock.getWorkspace.mockResolvedValueOnce(workspace({
      activeVersion: published,
      versions: [published],
      tasks: [publishedTask],
    }))
    const rolling = version({
      id: 'version-draft-19',
      versionNo: 19,
      name: '已发布 V18（实绩滚动）',
      revision: 2,
      baseVersionId: published.id,
    })
    const rollingTask = task({
      id: 'task-rolling-1',
      versionId: rolling.id,
      parentTaskId: publishedTask.id,
      revision: rolling.revision,
      plannedQty: 800,
    })
    apiMock.writeActual.mockResolvedValueOnce({
      actual: {
        id: 'actual-1',
        factoryId: 'huaxing',
        versionId: rolling.id,
        taskId: rollingTask.id,
        sourceVersionId: published.id,
        sourceTaskId: publishedTask.id,
        orderId: 'order-1',
        machineId: 'machine-1',
        shiftDate: '2026-07-25',
        shift: 'night',
        source: 'manual',
        legacyShiftCode: 'B',
        targetQty: null,
        actualQty: 100,
        varianceQty: null,
        varianceReason: '',
        producedBaselineQty: 100,
        outstandingQtyBefore: 900,
        outstandingQtyAfter: 800,
        shortageQty: 800,
        requestId: 'actual-request-1',
        revision: 1,
        correctionCount: 0,
        createdBy: 'planner-1',
        createdByName: '计划员',
        createdAt: now,
        correctedBy: '',
        correctedByName: '',
        correctedAt: '',
      },
      updatedOrder: {
        ...order('order-1', 'SO-001'),
        producedQty: 200,
        outstandingQty: 800,
        revision: 2,
      },
      version: rolling,
      tasks: [rollingTask],
      projections: [],
      affectedMachineIds: ['machine-1'],
      idempotentReplay: false,
    })
    const wrapper = await mountFormalHub(
      undefined,
      '/modules/production/injection-scheduling?factory=huaxing&section=operations',
    )
    const panel = wrapper.findComponent(Phase4DynamicSchedulingPanel)

    expect(panel.props('canAutomate')).toBe(false)
    expect(panel.props('canWriteActuals')).toBe(true)
    panel.vm.$emit('writeActual', {
      taskId: publishedTask.id,
      shiftDate: '2026-07-25',
      shiftCode: 'night',
      actualQty: 100,
      reason: '录入夜班 B 实绩',
    })
    await flushPromises()

    expect(apiMock.writeActual).toHaveBeenCalledWith(
      'huaxing',
      expect.objectContaining({
        versionId: published.id,
        taskId: publishedTask.id,
        shift: 'night',
        source: 'manual',
        legacyShiftCode: 'B',
        expectedVersionRevision: published.revision,
      }),
    )
    expect(wrapper.text()).toContain('V19')
    expect(wrapper.text()).toContain('可编辑草稿')
    expect(document.body.textContent).toContain('发布快照没有改动')
    expect(document.body.textContent).toContain('页面已安全切换到滚动草稿 V19')
  })

  it('renders the authoritative draft and persists a cross-machine drag command', async () => {
    const wrapper = await mountFormalHub()

    expect(wrapper.text()).toContain('正式草稿 V18 · revision 2')
    expect(wrapper.text()).toContain('SO-002')
    expect(wrapper.text()).not.toContain('明确回退预览')

    wrapper.findComponent(MachineTimelineBoard).vm.$emit('scheduleDrop', {
      taskId: 'task-1',
      machineId: 'machine-2',
      beforeTaskId: null,
    })
    await flushPromises()

    expect(apiMock.executeOperations).toHaveBeenCalledOnce()
    expect(apiMock.executeOperations.mock.calls[0][2]).toMatchObject({
      expectedRevision: 2,
      commands: [{
        type: 'move',
        taskId: 'task-1',
        machineId: 'machine-2',
        targetIndex: 0,
      }],
    })
    expect(wrapper.text()).toContain('revision 3')
  })

  it('opens the task inspector and sends a reasoned lock operation', async () => {
    const wrapper = await mountFormalHub()
    wrapper.findComponent(MachineTimelineBoard).vm.$emit('inspectTask', 'task-1')
    await flushPromises()

    const inspector = wrapper.findComponent(ScheduleTaskInspector)
    expect(inspector.props('open')).toBe(true)
    inspector.vm.$emit('toggleLock', {
      taskId: 'task-1',
      locked: true,
      reason: '固定今日急单顺序',
    })
    await flushPromises()

    expect(apiMock.executeOperations.mock.calls[0][2]).toMatchObject({
      commands: [{
        type: 'lock',
        taskId: 'task-1',
        reason: '固定今日急单顺序',
      }],
    })
  })

  it('submits a cross-machine split as one atomic command', async () => {
    const wrapper = await mountFormalHub()
    wrapper.findComponent(MachineTimelineBoard).vm.$emit('inspectTask', 'task-1')
    await flushPromises()

    wrapper.findComponent(ScheduleTaskInspector).vm.$emit('split', {
      taskId: 'task-1',
      splitShots: 300,
      targetMachineId: 'machine-2',
      reason: '拆分急单到备用机台',
    })
    await flushPromises()

    expect(apiMock.executeOperations).toHaveBeenCalledOnce()
    expect(apiMock.executeOperations.mock.calls[0][2]).toMatchObject({
      expectedRevision: 2,
      commands: [{
        type: 'split',
        taskId: 'task-1',
        splitQty: 300,
        machineId: 'machine-2',
        targetIndex: 0,
      }],
    })
  })

  it('opens the order master editor and persists a revision-checked update', async () => {
    apiMock.updateOrder.mockResolvedValueOnce(order('order-1', 'SO-001'))
    const wrapper = await mountFormalHub()
    const mastersNav = wrapper.findAll('button').find(
      (button) => button.text().trim() === '机台·模具',
    )
    await mastersNav!.trigger('click')
    const orderTab = wrapper.findAll('button').find(
      (button) => button.text().trim() === '订单主数据',
    )
    await orderTab!.trigger('click')
    const editButton = wrapper.findAll('button').find(
      (button) => button.text().trim() === '编辑所选',
    )
    await editButton!.trigger('click')

    const editor = wrapper.findComponent(ScheduleMasterEditor)
    expect(editor.props('open')).toBe(true)
    editor.vm.$emit('saveOrder', {
      orderId: 'order-1',
      expectedRevision: 1,
      input: {
        orderNo: 'SO-001',
        productName: 'SO-001产品',
        moldCode: 'M-01',
        orderQty: 1000,
        producedQty: 100,
        deliveryDueDate: '2026-07-29',
      },
    })
    await flushPromises()

    expect(apiMock.updateOrder).toHaveBeenCalledWith(
      'huaxing',
      'order-1',
      1,
      expect.objectContaining({ deliveryDueDate: '2026-07-29' }),
    )
  })

  it('loads the real version panel and runs a server-side validation', async () => {
    const wrapper = await mountFormalHub()
    const versionsNav = wrapper.findAll('button').find(
      (button) => button.text().trim() === '计划版本',
    )
    await versionsNav!.trigger('click')

    const panel = wrapper.findComponent(ScheduleVersionPanel)
    expect(panel.exists()).toBe(true)
    expect(panel.text()).toContain('V18 · 7月23日人工草稿')
    expect(panel.text()).toContain('冲突待校验')
    panel.vm.$emit('validate', 'version-draft-18')
    await flushPromises()

    expect(apiMock.validateVersion).toHaveBeenCalledWith(
      'huaxing',
      'version-draft-18',
      2,
    )
    expect(wrapper.text()).toContain('V18已通过发布校验')
    expect(panel.text()).toContain('0 条冲突')
  })

  it('requires a separate review step between validation and publishing', async () => {
    const wrapper = await mountFormalHub()
    const versionsNav = wrapper.findAll('button').find(
      (button) => button.text().trim() === '计划版本',
    )
    await versionsNav!.trigger('click')

    const panel = wrapper.findComponent(ScheduleVersionPanel)
    expect(panel.text()).toContain('先校验并查看差异')
    panel.vm.$emit('publish', {
      versionId: 'version-draft-18',
      reason: '确认正式发布本版计划',
    })
    await flushPromises()

    expect(apiMock.validateVersion).toHaveBeenCalledOnce()
    expect(apiMock.getVersionDiff).toHaveBeenCalledOnce()
    expect(apiMock.publishVersion).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('本次操作不会直接发布')
    expect(panel.text()).toContain('进入发布确认')

    const published = version({
      status: 'published',
      validationHash: 'result-hash',
      publishedAt: now,
      publishedBy: 'planner-1',
      publishedByName: '计划员',
      publishReason: '确认正式发布本版计划',
    })
    apiMock.publishVersion.mockResolvedValueOnce(published)
    apiMock.getWorkspace.mockResolvedValueOnce(workspace({
      activeVersion: published,
      versions: [published],
      tasks: [task()],
    }))
    panel.vm.$emit('publish', {
      versionId: 'version-draft-18',
      reason: '确认正式发布本版计划',
    })
    await flushPromises()

    expect(apiMock.publishVersion).toHaveBeenCalledOnce()
  })

  it('refreshes master snapshots through one audited command and revalidates', async () => {
    apiMock.validateVersion.mockResolvedValueOnce({
      id: 'validation-after-refresh',
      factoryId: 'huaxing',
      versionId: 'version-draft-18',
      versionRevision: 3,
      dataHash: 'data-hash',
      resultHash: 'result-after-refresh',
      status: 'passed',
      blockingCount: 0,
      warningCount: 0,
      createdBy: 'planner-1',
      createdByName: '计划员',
      createdAt: now,
      items: [],
    })
    const wrapper = await mountFormalHub()
    const versionsNav = wrapper.findAll('button').find(
      (button) => button.text().trim() === '计划版本',
    )
    await versionsNav!.trigger('click')

    wrapper.findComponent(ScheduleVersionPanel).vm.$emit(
      'refreshMasters',
      'version-draft-18',
    )
    await flushPromises()

    expect(apiMock.executeOperations).toHaveBeenCalledOnce()
    expect(apiMock.executeOperations.mock.calls[0][2]).toMatchObject({
      expectedRevision: 2,
      commands: [{
        type: 'refresh_masters',
        reason: '计划员确认同步最新机台、模具和订单主数据',
      }],
    })
    expect(apiMock.validateVersion).toHaveBeenCalledWith(
      'huaxing',
      'version-draft-18',
      3,
    )
  })

  it('retries an unknown-data move only after an explicit audited confirmation', async () => {
    apiMock.executeOperations.mockRejectedValueOnce({
      isAxiosError: true,
      response: {
        status: 422,
        data: {
          detail: {
            code: 'manual_confirmation_required',
            message: '资料不足，只能在填写人工确认原因后保存到草稿',
            reasons: ['目标机台最大射胶量缺失'],
          },
        },
      },
    })
    const wrapper = await mountFormalHub()

    wrapper.findComponent(MachineTimelineBoard).vm.$emit('scheduleDrop', {
      taskId: 'task-1',
      machineId: 'machine-2',
      beforeTaskId: null,
    })
    await flushPromises()

    expect(document.body.textContent).toContain('目标机台最大射胶量缺失')
    const confirmButton = Array.from(document.body.querySelectorAll('button')).find(
      (button) => button.textContent?.trim() === '确认例外并重试',
    )
    expect(confirmButton?.disabled).toBe(true)
    const reasonInput = document.body.querySelector<HTMLTextAreaElement>(
      '.hub-dialog__manual-reason textarea',
    )
    reasonInput!.value = '已核对目标机台资料，安排当班补录'
    reasonInput!.dispatchEvent(new Event('input', { bubbles: true }))
    await flushPromises()
    expect(confirmButton?.disabled).toBe(false)
    confirmButton!.click()
    await flushPromises()

    expect(apiMock.executeOperations).toHaveBeenCalledTimes(2)
    expect(apiMock.executeOperations.mock.calls[1][2]).toMatchObject({
      expectedRevision: 2,
      commands: [{
        type: 'move',
        taskId: 'task-1',
        machineId: 'machine-2',
        manualConfirmation: {
          confirmed: true,
          reason: '已核对目标机台资料，安排当班补录',
          constraintCodes: [],
        },
      }],
    })
  })

  it('renders immutable task labels from the version snapshot instead of renamed masters', async () => {
    apiMock.getWorkspace.mockResolvedValueOnce(workspace({
      tasks: [task({
        orderNo: 'SO-SNAPSHOT',
        productName: '发布时产品名称',
        moldCode: 'M-SNAPSHOT',
        machineCode: '旧1-发布快照',
      })],
      orders: [{
        ...order('order-1', 'SO-CURRENT'),
        productName: '当前主数据产品名称',
        moldCode: 'M-CURRENT',
      }],
    }))

    const wrapper = await mountFormalHub()
    const boardText = wrapper.findComponent(MachineTimelineBoard).text()

    expect(boardText).toContain('SO-SNAPSHOT')
    expect(boardText).toContain('发布时产品名称')
    expect(boardText).toContain('M-SNAPSHOT')
    expect(boardText).not.toContain('当前主数据产品名称')
  })

  it('loads a first-draft diff against an empty version after validation', async () => {
    const firstDraft = version({
      id: 'version-draft-1',
      versionNo: 1,
      baseVersionId: null,
    })
    apiMock.getWorkspace.mockResolvedValueOnce(workspace({
      activeVersion: firstDraft,
      versions: [firstDraft],
      tasks: [task({ versionId: firstDraft.id })],
    }))
    apiMock.validateVersion.mockResolvedValueOnce({
      id: 'validation-first',
      factoryId: 'huaxing',
      versionId: firstDraft.id,
      versionRevision: firstDraft.revision,
      dataHash: firstDraft.dataHash,
      resultHash: 'result-first',
      status: 'passed',
      blockingCount: 0,
      warningCount: 0,
      createdBy: 'planner-1',
      createdByName: '计划员',
      createdAt: now,
      items: [],
    })
    apiMock.getVersionDiff.mockResolvedValueOnce({
      versionId: firstDraft.id,
      againstVersionId: null,
      summary: { added: 1 },
      items: [{
        orderId: 'order-1',
        orderNo: 'SO-001',
        changeType: 'added',
        before: null,
        after: {},
      }],
    })
    const wrapper = await mountFormalHub()
    const versionsNav = wrapper.findAll('button').find(
      (button) => button.text().trim() === '计划版本',
    )
    await versionsNav!.trigger('click')
    wrapper.findComponent(ScheduleVersionPanel).vm.$emit('validate', firstDraft.id)
    await flushPromises()

    expect(apiMock.getVersionDiff).toHaveBeenCalledWith(
      'huaxing',
      firstDraft.id,
      null,
    )
    expect(wrapper.findComponent(ScheduleVersionPanel).text()).toContain('对比 空版本')
  })

  it('uses camel-cased formal version rule snapshots instead of preview defaults', async () => {
    const formalVersion = version({
      rulesSnapshot: {
        shotSafetyFactor: 0.5,
        defaultSetupHours: 2,
        allowMissingDataInDraftWithManualConfirmation: false,
      },
    })
    apiMock.getWorkspace.mockResolvedValueOnce(workspace({
      activeVersion: formalVersion,
      versions: [formalVersion],
    }))
    const wrapper = await mountFormalHub()
    const ordersNav = wrapper.findAll('button').find(
      (button) => button.text().trim() === '待排订单',
    )
    await ordersNav!.trigger('click')
    wrapper.findComponent(UnscheduledOrderTable).vm.$emit('inspectMatch', 'order-2')
    await flushPromises()

    expect(wrapper.text()).toContain('安全射胶量 250g')
    expect(wrapper.text()).toContain('UNKNOWN 与 FAIL 均阻断排入')
  })

  it('renders superseded-version tasks as immutable', async () => {
    const historical = version({
      status: 'superseded',
      id: 'version-history-16',
      versionNo: 16,
    })
    apiMock.getWorkspace.mockResolvedValueOnce(workspace({
      activeVersion: historical,
      versions: [historical],
      tasks: [task({ versionId: historical.id })],
    }))
    const wrapper = await mountFormalHub()
    const taskButton = wrapper.findComponent(MachineTimelineBoard).find('.schedule-task')

    expect(taskButton.attributes('draggable')).toBe('false')
  })

  it('excludes completed, canceled, and zero-outstanding orders from the formal pending pool', async () => {
    apiMock.getWorkspace.mockResolvedValueOnce(workspace({
      orders: [
        order('order-1', 'SO-001'),
        order('order-2', 'SO-OPEN'),
        { ...order('order-3', 'SO-COMPLETED'), status: 'completed' },
        { ...order('order-4', 'SO-CANCELED'), status: 'canceled' },
        { ...order('order-5', 'SO-ZERO'), outstandingQty: 0 },
      ],
    }))

    const wrapper = await mountFormalHub()

    expect(wrapper.text()).toContain('SO-OPEN产品')
    expect(wrapper.text()).not.toContain('SO-COMPLETED产品')
    expect(wrapper.text()).not.toContain('SO-CANCELED产品')
    expect(wrapper.text()).not.toContain('SO-ZERO产品')
  })

  it('Phase 3 preserves server ranking, isolates UNKNOWN advisory scores, and keeps FAIL above UNKNOWN', async () => {
    const base = recommendationResponse().candidates[0]!
    const eligible = {
      ...base,
      machineId: 'machine-2',
      machineCode: '旧2',
      machineName: '旧2号机',
      rank: 1,
      score: {
        ...base.score!,
        breakdown: [{
          code: 'due_date',
          label: '货期紧迫度',
          weight: 35,
          rawScore: 0.8,
          weightedScore: 28,
          explanation: '交期余量较小',
        }],
        transition: {
          ...base.score!.transition,
          previousMoldCode: 'M-OLD',
          nextMoldCode: 'M-NEXT',
          previousColor: '白色',
          targetColor: 'PIG-BL',
          nextColor: '黑色',
          previousMaterial: 'PP',
          nextMaterial: 'PC',
          sameMold: false,
          afterColorMinutes: 12,
          afterMaterialMinutes: 6,
          replacedColorMinutes: 4,
          replacedMaterialMinutes: 3,
          setupMinutesBefore: 45,
          setupMinutesAfter: 20,
          replacedSetupMinutes: 10,
          setupMinutesDelta: 55,
          afterColorMatrixMatch: 'PIG-BL→黑色',
          afterMaterialMatrixMatch: 'ABS→PC',
          replacedColorMatrixMatch: '白色→黑色',
          replacedMaterialMatrixMatch: 'PP→PC',
        },
        estimated: {
          ...base.score!.estimated,
          slotStartAt: '2026-07-30T08:00:00+08:00',
          productionStartAt: '2026-07-30T08:45:00+08:00',
          skippedUnavailableWindows: [{
            startAt: '2026-07-29T00:00:00+08:00',
            endAt: '2026-07-30T08:00:00+08:00',
            reason: '整厂停产',
          }],
        },
      },
    }
    const manual = {
      ...base,
      machineId: 'machine-1',
      machineCode: '旧1',
      machineName: '旧1号机',
      rank: null,
      advisoryRank: 1,
      status: 'manual_review' as const,
      eligible: false,
      requiresManualConfirmation: true,
      autoPublishAllowed: false,
      hardConstraints: [{
        code: 'screw_compatibility',
        status: 'unknown' as const,
        blocking: true,
        message: '螺杆类型待确认',
        details: {},
      }],
      score: {
        ...base.score!,
        advisory: true,
        total: 42,
        breakdown: [{
          code: 'split_penalty',
          label: '拆单惩罚',
          weight: 8,
          rawScore: -0.625,
          weightedScore: -5,
          explanation: '订单已在另一台机续排',
        }],
      },
    }
    const blocked = {
      ...base,
      machineId: 'machine-3',
      machineCode: '旧3',
      machineName: '旧3号机',
      rank: null,
      advisoryRank: null,
      status: 'blocked' as const,
      eligible: false,
      requiresManualConfirmation: true,
      autoPublishAllowed: false,
      hardConstraints: [
        {
          code: 'machine_status',
          status: 'fail' as const,
          blocking: true,
          message: '机台停机',
          details: {},
        },
        {
          code: 'time_window',
          status: 'unknown' as const,
          blocking: true,
          message: '日历待核验',
          details: {},
        },
      ],
      score: null,
    }
    apiMock.getWorkspace.mockResolvedValueOnce(workspace({
      machines: [
        machine('machine-1', '旧1'),
        machine('machine-2', '旧2'),
        machine('machine-3', '旧3'),
      ],
    }))
    apiMock.getRecommendations.mockResolvedValueOnce(recommendationResponse('order-2', {
      ruleConfigRevision: 0,
      totalCandidates: 3,
      eligibleCount: 1,
      manualReviewCount: 1,
      blockedCount: 1,
      candidates: [eligible, manual, blocked],
    }))
    const wrapper = await mountFormalHub()
    await wrapper.findAll('button').find(
      (button) => button.text().trim() === '待排订单',
    )!.trigger('click')
    wrapper.findComponent(UnscheduledOrderTable).vm.$emit('inspectMatch', 'order-2')
    await flushPromises()

    expect(apiMock.getRecommendations).toHaveBeenCalledWith(
      'huaxing',
      'version-draft-18',
      'order-2',
      { limit: 100 },
    )
    expect(wrapper.findAll('.candidate-row')).toHaveLength(3)
    expect(wrapper.text()).toContain('历史来源 revision 未知')
    expect(wrapper.text()).not.toContain('规则 revision 0')
    const candidateText = wrapper.find('.candidate-list').text()
    expect(candidateText.indexOf('旧2')).toBeLessThan(candidateText.indexOf('旧1'))
    expect(candidateText.indexOf('旧1')).toBeLessThan(candidateText.indexOf('旧3'))
    expect(wrapper.text()).toContain('M-OLD')
    expect(wrapper.text()).toContain('M-NEXT')
    expect(wrapper.text()).toContain('PIG-BL')
    expect(wrapper.text()).toContain('前序 → 当前 45 分钟')
    expect(wrapper.text()).toContain('当前 → 后序 20 分钟')
    expect(wrapper.text()).toContain('当前→后序 12 分钟')
    expect(wrapper.text()).toContain('原前→后 4 分钟')
    expect(wrapper.text()).toContain('已跳过 1 个不可用窗口')
    expect(wrapper.text()).toContain('整厂停产')
    expect(wrapper.text()).toContain('建议占机')

    await wrapper.findAll('.candidate-row')[1]!.trigger('click')
    expect(wrapper.text()).toContain('螺杆兼容性')
    expect(wrapper.text()).toContain('隔离参考分')
    expect(wrapper.text()).toContain('拆单惩罚')
    expect(wrapper.text()).toContain('-5')

    await wrapper.findAll('.candidate-row')[2]!.trigger('click')
    expect(wrapper.text()).toContain('机台停机')
    expect(wrapper.text()).toContain('日历待核验')
    expect(wrapper.find('.match-toolbar__confirm').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.recommendation-badge').text()).toContain('当前不可排')
  })

  it('Phase 3 dimension usage uses the valid rotated mold orientation', async () => {
    apiMock.getWorkspace.mockResolvedValueOnce(workspace({
      machines: [
        {
          ...machine('machine-1', '旧1'),
          tieBarXMm: 350,
          tieBarYMm: 450,
        },
      ],
      molds: [{
        ...mold(),
        lengthMm: 400,
        widthMm: 300,
      }],
    }))

    const wrapper = await mountFormalHub()
    await wrapper.findAll('button').find(
      (button) => button.text().trim() === '待排订单',
    )!.trigger('click')
    wrapper.findComponent(UnscheduledOrderTable).vm.$emit('inspectMatch', 'order-2')
    await flushPromises()

    expect(wrapper.get('[aria-label="模具空间占用"]').attributes('aria-valuenow')).toBe('89')
  })

  it('Phase 3 keeps partially scheduled orders with their remaining quantity and lets the server choose plannedQty', async () => {
    apiMock.getWorkspace.mockResolvedValueOnce(workspace({
      tasks: [task({
        id: 'task-partial',
        orderId: 'order-2',
        orderNo: 'SO-002',
        plannedQty: 300,
      })],
    }))
    apiMock.getRecommendations.mockResolvedValueOnce(recommendationResponse('order-2', {
      plannedQty: 600,
    }))
    const wrapper = await mountFormalHub()
    await wrapper.findAll('button').find(
      (button) => button.text().trim() === '待排订单',
    )!.trigger('click')

    const pendingTable = wrapper.findComponent(UnscheduledOrderTable)
    expect(pendingTable.text()).toContain('SO-002')
    expect(pendingTable.text()).toContain('600')
    pendingTable.vm.$emit('inspectMatch', 'order-2')
    await flushPromises()

    expect(apiMock.getRecommendations).toHaveBeenCalledWith(
      'huaxing',
      'version-draft-18',
      'order-2',
      { limit: 100 },
    )
    expect(wrapper.text()).toContain('欠数600')
  })

  it('Phase 3 saves nested weights, matrices, and unavailable calendar windows with revision locking', async () => {
    const wrapper = await mountFormalHub()
    await wrapper.findAll('button').find(
      (button) => button.text().trim() === '规则配置',
    )!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('货期紧迫度')
    const manualToggle = wrapper.find<HTMLInputElement>(
      'input[aria-label="允许缺失资料人工确认"]',
    )
    expect(manualToggle.element.checked).toBe(true)
    await manualToggle.setValue(false)
    await wrapper.findAll('.master-toolbar nav button').find(
      (button) => button.text().trim() === '班次与停机日历',
    )!.trigger('click')
    await flushPromises()
    expect((
      wrapper.find('input[aria-label="停机窗口第1行原因"]').element as HTMLInputElement
    ).value).toBe('计划保养')
    expect(wrapper.find('input[aria-label="可用日历核验截止时间"]').element)
      .toBeInstanceOf(HTMLInputElement)

    await wrapper.find('.rule-save-panel input').setValue('录入本周保养窗口')
    await wrapper.findAll('.rule-save-panel button').find(
      (button) => button.text().includes('保存日历规则'),
    )!.trigger('click')
    await flushPromises()

    expect(apiMock.updateRuleConfig).toHaveBeenCalledWith('huaxing', {
      expectedRevision: 3,
      reason: '录入本周保养窗口',
      config: expect.objectContaining({
        allowMissingDataInDraftWithManualConfirmation: false,
        scoringWeights: expect.objectContaining({ dueDate: 35 }),
        colorTransitionMatrix: [{ fromCode: '*', toCode: '*', minutes: 20 }],
        materialTransitionMatrix: [{ fromCode: '*', toCode: '*', minutes: 30 }],
        unavailableWindows: [{
          scope: 'machine',
          machineId: 'machine-2',
          startAt: '2026-07-24T08:00:00+08:00',
          endAt: '2026-07-24T12:00:00+08:00',
          reason: '计划保养',
        }],
      }),
    })
    await wrapper.findAll('.master-toolbar nav button').find(
      (button) => button.text().trim() === '颜色/材料矩阵',
    )!.trigger('click')
    expect(wrapper.text()).toContain('颜色转换矩阵')
    expect(wrapper.text()).toContain('材料转换矩阵')
  })

  it('Phase 3 presents recommendation and rule actions as read-only without write permissions', async () => {
    const wrapper = await mountFormalHub(['injection_schedule:read'])
    await wrapper.findAll('button').find(
      (button) => button.text().trim() === '待排订单',
    )!.trigger('click')
    wrapper.findComponent(UnscheduledOrderTable).vm.$emit('inspectMatch', 'order-2')
    await flushPromises()

    const assignButton = wrapper.find('.match-toolbar__confirm')
    expect(assignButton.text()).toContain('只读：不可排入')
    expect((assignButton.element as HTMLButtonElement).disabled).toBe(true)

    await wrapper.findAll('button').find(
      (button) => button.text().trim() === '规则配置',
    )!.trigger('click')
    await flushPromises()
    const manualToggle = wrapper.find<HTMLInputElement>(
      'input[aria-label="允许缺失资料人工确认"]',
    )
    expect(manualToggle.attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('.rule-save-panel button').some(
      (button) => button.text().includes('保存规则'),
    )).toBe(false)
  })

  it('Phase 3 explains missing mold masters and missing plan versions instead of rendering a blank workspace', async () => {
    apiMock.getWorkspace.mockResolvedValueOnce(workspace({ molds: [] }))
    const missingMold = await mountFormalHub()
    await missingMold.findAll('button').find(
      (button) => button.text().trim() === '待排订单',
    )!.trigger('click')
    missingMold.findComponent(UnscheduledOrderTable).vm.$emit('inspectMatch', 'order-2')
    await missingMold.vm.$nextTick()
    expect(missingMold.text()).toContain('订单引用的模具主数据未匹配')
    expect(missingMold.text()).toContain('mold_master UNKNOWN')
    missingMold.unmount()

    apiMock.getWorkspace.mockResolvedValueOnce(workspace({
      activeVersion: null,
      versions: [],
      tasks: [],
    }))
    const missingVersion = await mountFormalHub()
    await missingVersion.findAll('button').find(
      (button) => button.text().trim() === '待排订单',
    )!.trigger('click')
    missingVersion.findComponent(UnscheduledOrderTable).vm.$emit('inspectMatch', 'order-2')
    await missingVersion.vm.$nextTick()
    expect(missingVersion.text()).toContain('尚无可用于推荐的计划版本')
    expect(missingVersion.text()).toContain('请先创建草稿或选择已有版本')
  })

  it('Phase 3 matches order mold codes with the same trim and case normalization as the service', async () => {
    apiMock.getWorkspace.mockResolvedValueOnce(workspace({
      orders: [
        order('order-1', 'SO-001'),
        { ...order('order-2', 'SO-002'), moldCode: '  m-01  ' },
      ],
    }))
    const wrapper = await mountFormalHub()
    await wrapper.findAll('button').find(
      (button) => button.text().trim() === '待排订单',
    )!.trigger('click')
    wrapper.findComponent(UnscheduledOrderTable).vm.$emit('inspectMatch', 'order-2')
    await flushPromises()

    expect(wrapper.text()).toContain('模具 M-01')
    expect(wrapper.text()).toContain('匹配解释')
    expect(wrapper.text()).not.toContain('订单引用的模具主数据未匹配')
  })

  it('Phase 3 renders recommendation loading, error, retry, and empty states without local fallback candidates', async () => {
    let rejectRecommendation!: (reason: unknown) => void
    apiMock.getRecommendations.mockReturnValueOnce(new Promise((_, reject) => {
      rejectRecommendation = reject
    }))
    const wrapper = await mountFormalHub()
    await wrapper.findAll('button').find(
      (button) => button.text().trim() === '待排订单',
    )!.trigger('click')
    wrapper.findComponent(UnscheduledOrderTable).vm.$emit('inspectMatch', 'order-2')
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('正在按当前版本计算候选机台')
    expect(wrapper.findAll('.candidate-row')).toHaveLength(0)

    rejectRecommendation({
      isAxiosError: true,
      response: { status: 500, data: { detail: '推荐服务暂不可用' } },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('候选推荐暂未生成')
    expect(wrapper.text()).toContain('推荐服务暂不可用')

    apiMock.getRecommendations.mockResolvedValueOnce(recommendationResponse('order-2', {
      totalCandidates: 0,
      eligibleCount: 0,
      manualReviewCount: 0,
      blockedCount: 0,
      candidates: [],
    }))
    await wrapper.find('.recommendation-request-state button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('当前没有候选机台')
    expect(wrapper.findAll('.candidate-row')).toHaveLength(0)
  })
})

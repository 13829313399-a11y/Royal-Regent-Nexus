import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  useInjectionScheduleStore,
} from '@/stores/injectionSchedule'
import type {
  InjectionFormalScheduleTask,
  InjectionImportBatch,
  InjectionMachineRecord,
  InjectionMoldRecord,
  InjectionOrderRecommendationResponse,
  InjectionOrderRecord,
  InjectionPlanVersion,
  InjectionScheduleOperationRequest,
  InjectionScheduleWorkspace,
} from '@/types/injectionSchedule'

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

const timestamp = '2026-07-23T08:00:00+08:00'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((done, fail) => {
    resolve = done
    reject = fail
  })
  return { promise, resolve, reject }
}

function version(
  factoryId = 'huaxing',
  overrides: Partial<InjectionPlanVersion> = {},
): InjectionPlanVersion {
  return {
    id: `${factoryId}-draft-18`,
    factoryId,
    versionNo: 18,
    name: '草稿 V18',
    status: 'draft',
    revision: 2,
    businessDate: '2026-07-23',
    planBaseAt: timestamp,
    baseVersionId: `${factoryId}-published-17`,
    sourceBatchId: '',
    rulesSnapshot: {},
    dataHash: 'data-hash-2',
    validationHash: '',
    summary: {},
    createdBy: 'planner-1',
    createdByName: '计划员',
    createdAt: timestamp,
    updatedBy: 'planner-1',
    updatedAt: timestamp,
    publishedBy: '',
    publishedByName: '',
    publishedAt: '',
    publishReason: '',
    supersededAt: '',
    ...overrides,
  }
}

function machine(
  id: string,
  code: string,
  factoryId = 'huaxing',
): InjectionMachineRecord {
  return {
    id,
    factoryId,
    machineCode: code,
    machineName: `${code}号机`,
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
    availableAt: timestamp,
    capabilities: [],
    materialRules: [],
    qualityStatus: 'verified',
    provenance: {},
    sourceBatchId: '',
    revision: 1,
    createdBy: 'planner-1',
    createdAt: timestamp,
    updatedBy: 'planner-1',
    updatedAt: timestamp,
  }
}

function mold(factoryId = 'huaxing'): InjectionMoldRecord {
  return {
    id: 'mold-1',
    factoryId,
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
    grossShotWeightG: 260,
    cavities: 2,
    cycleSeconds: 42,
    requiredCapabilities: [],
    materialRules: [],
    qualityStatus: 'verified',
    provenance: {},
    sourceBatchId: '',
    revision: 1,
    createdBy: 'planner-1',
    createdAt: timestamp,
    updatedBy: 'planner-1',
    updatedAt: timestamp,
  }
}

function order(factoryId = 'huaxing'): InjectionOrderRecord {
  return {
    id: 'order-1',
    factoryId,
    naturalKey: 'SO-001|P-01',
    orderNo: 'SO-001',
    productCode: 'P-01',
    productName: '外壳',
    moldCode: 'M-01',
    color: '黑色',
    pigment: '',
    material: 'ABS',
    machineClass: '7A',
    orderQty: 20_000,
    producedQty: 2_000,
    outstandingQty: 18_000,
    dailyTargetQty: 18_000,
    deliveryDueDate: '2026-07-25',
    priorityCode: 'P2',
    priorityFlag: '',
    status: 'open',
    importedAssignedMachineCode: '7A-01',
    qualityStatus: 'verified',
    importedPlanStartAt: timestamp,
    importedPlanFinishAt: '2026-07-24T08:00:00+08:00',
    sourceSheet: '排产',
    sourceRow: 8,
    sourceValues: {},
    provenance: {},
    sourceBatchId: '',
    revision: 1,
    createdBy: 'planner-1',
    createdAt: timestamp,
    updatedBy: 'planner-1',
    updatedAt: timestamp,
  }
}

function task(
  activeVersion: InjectionPlanVersion,
  factoryId = 'huaxing',
): InjectionFormalScheduleTask {
  return {
    id: 'task-1',
    factoryId,
    versionId: activeVersion.id,
    orderId: 'order-1',
    orderNo: 'SO-001',
    productCode: 'P-01',
    productName: '外壳',
    moldId: 'mold-1',
    moldCode: 'M-01',
    machineId: 'machine-1',
    machineCode: '7A-01',
    sequenceNo: 0,
    plannedQty: 18_000,
    plannedStartAt: timestamp,
    plannedFinishAt: '2026-07-24T08:00:00+08:00',
    setupHours: 1,
    durationHours: 24,
    locked: false,
    splitGroupId: '',
    parentTaskId: '',
    riskLevel: 'low',
    riskReasons: [],
    revision: activeVersion.revision,
  }
}

function formalWorkspace(factoryId = 'huaxing'): InjectionScheduleWorkspace {
  const activeVersion = version(factoryId)
  const hasRecords = factoryId === 'huaxing'
  return {
    mode: 'formal',
    factoryId,
    workspaceRevision: 3,
    activeVersion,
    versions: [activeVersion],
    machines: hasRecords
      ? [machine('machine-1', '7A-01'), machine('machine-2', '7A-02')]
      : [],
    molds: hasRecords ? [mold()] : [],
    orders: hasRecords ? [order()] : [],
    tasks: hasRecords ? [task(activeVersion)] : [],
    conflicts: [],
    ruleConfig: {
      factoryId,
      config: {},
      revision: 1,
      updatedBy: 'planner-1',
      updatedAt: timestamp,
    },
  }
}

function importBatch(
  overrides: Partial<InjectionImportBatch> = {},
): InjectionImportBatch {
  return {
    id: 'batch-1',
    factoryId: 'huaxing',
    sourceFileName: '华兴啤机日排版表1.xlsx',
    sourceContentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    sourceSizeBytes: 1024,
    sourceSha256: 'sha256',
    parserVersion: 'phase2-v1',
    detectedSheets: ['排产'],
    draftVersionId: '',
    status: 'previewed',
    revision: 3,
    businessDate: '2026-07-21',
    summary: { machineCount: 76, warningCount: 1 },
    preview: {},
    issues: [],
    createdBy: 'planner-1',
    createdByName: '计划员',
    createdAt: timestamp,
    confirmedBy: '',
    confirmedByName: '',
    confirmedAt: '',
    confirmReason: '',
    rejectedBy: '',
    rejectedByName: '',
    rejectedAt: '',
    rejectionReason: '',
    ...overrides,
  }
}

function moveRequest(expectedRevision = 2): InjectionScheduleOperationRequest {
  return {
    expectedRevision,
    reason: '跨机调整',
    requestId: 'request-1',
    commands: [{
      type: 'move',
      taskId: 'task-1',
      machineId: 'machine-2',
      targetIndex: 0,
      reason: '交期优先',
      manualConfirmation: null,
    }],
  }
}

function phase3Recommendation(
  contextHash: string,
  overrides: Partial<InjectionOrderRecommendationResponse> = {},
): InjectionOrderRecommendationResponse {
  return {
    factoryId: 'huaxing',
    versionId: 'huaxing-draft-18',
    versionRevision: 2,
    orderId: 'order-1',
    orderRevision: 1,
    plannedQty: 1000,
    ruleConfigRevision: 3,
    currentRuleConfigRevision: 3,
    ruleConfigHash: 'rules-hash',
    usesVersionRuleSnapshot: true,
    generatedAt: timestamp,
    totalCandidates: 1,
    eligibleCount: 1,
    manualReviewCount: 0,
    blockedCount: 0,
    candidates: [{
      rank: 1,
      advisoryRank: null,
      machineId: 'machine-1',
      machineCode: '7A-01',
      machineName: '7A-01',
      targetIndex: 1,
      status: 'eligible',
      eligible: true,
      requiresManualConfirmation: false,
      autoPublishAllowed: true,
      hardConstraints: [],
      score: null,
      recommendationContextHash: contextHash,
    }],
    ...overrides,
  }
}

describe('injection schedule store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    apiMock.getWorkspace.mockResolvedValue(formalWorkspace())
  })

  it('ignores an older factory response and retains only the newest formal workspace', async () => {
    const oldRequest = deferred<InjectionScheduleWorkspace>()
    apiMock.getWorkspace.mockImplementation((factoryId: string) => (
      factoryId === 'huaxing'
        ? oldRequest.promise
        : Promise.resolve(formalWorkspace('huadeng'))
    ))
    const store = useInjectionScheduleStore()

    const huaxingLoad = store.loadWorkspace('huaxing')
    const huadengWorkspace = await store.loadWorkspace('huadeng')
    oldRequest.resolve(formalWorkspace('huaxing'))
    const staleWorkspace = await huaxingLoad

    expect(huadengWorkspace?.factoryId).toBe('huadeng')
    expect(staleWorkspace).toBeUndefined()
    expect(store.factoryId).toBe('huadeng')
    expect(store.mode).toBe('formal')
    expect(store.formalWorkspace?.factoryId).toBe('huadeng')
  })

  it('uses preview fallback only when explicitly enabled and the formal API is unavailable', async () => {
    const store = useInjectionScheduleStore()
    apiMock.getWorkspace.mockRejectedValueOnce({
      response: { status: 503, data: { detail: 'service unavailable' } },
    })

    await store.loadWorkspace('huaxing', { allowPreviewFallback: true })

    expect(store.mode).toBe('preview')
    expect(store.previewWorkspace?.machines).toHaveLength(76)
    expect(store.formalWorkspace).toBeNull()

    apiMock.getWorkspace.mockRejectedValueOnce({
      response: { status: 403, data: { detail: 'forbidden' } },
    })
    await store.loadWorkspace('huaxing', { allowPreviewFallback: true })

    expect(store.mode).toBe('empty')
    expect(store.previewWorkspace).toBeNull()
    expect(store.formalWorkspace).toBeNull()
  })

  it('blocks every mutation while running in explicit preview fallback mode', async () => {
    const store = useInjectionScheduleStore()
    apiMock.getWorkspace.mockRejectedValueOnce({
      response: { status: 503, data: { detail: 'service unavailable' } },
    })
    await store.loadWorkspace('huaxing', { allowPreviewFallback: true })

    await expect(store.executeOperations(moveRequest()))
      .rejects.toThrow('当前不是正式排产工作区，禁止写入')
    expect(apiMock.executeOperations).not.toHaveBeenCalled()
  })

  it('shows an optimistic move then rolls it back and exposes a 409 revision conflict', async () => {
    const command = deferred<never>()
    apiMock.executeOperations.mockReturnValueOnce(command.promise)
    const store = useInjectionScheduleStore()
    await store.loadWorkspace('huaxing')

    const save = store.executeOperations(moveRequest())
    expect(store.formalWorkspace?.tasks[0].machineId).toBe('machine-2')
    expect(store.mutationPending).toBe(true)

    command.reject({
      response: {
        status: 409,
        data: {
          detail: {
            code: 'revision_conflict',
            message: '草稿已由其他计划员更新',
            current_revision: 3,
            expected_revision: 2,
            entity_id: 'huaxing-draft-18',
          },
        },
      },
    })
    await expect(save).rejects.toBeTruthy()

    expect(store.formalWorkspace?.tasks[0].machineId).toBe('machine-1')
    expect(store.revisionConflict).toEqual({
      code: 'revision_conflict',
      message: '草稿已由其他计划员更新',
      currentRevision: 3,
      expectedRevision: 2,
      entityId: 'huaxing-draft-18',
    })
    expect(store.errorMessage).toContain('服务端当前 revision 3')
    expect(store.mutationPending).toBe(false)
  })

  it('rolls back a rejected move and exposes every hard-constraint reason', async () => {
    apiMock.executeOperations.mockRejectedValueOnce({
      isAxiosError: true,
      message: 'Request failed with status code 422',
      response: {
        status: 422,
        data: {
          detail: {
            code: 'assignment_blocked',
            message: '目标机台与任务硬约束不兼容',
            reasons: ['要求双臂机械手，目标机台仅单臂', '目标机台缺少双抽芯能力'],
          },
        },
      },
    })
    const store = useInjectionScheduleStore()
    await store.loadWorkspace('huaxing')

    await expect(store.executeOperations(moveRequest())).rejects.toBeTruthy()

    expect(store.formalWorkspace?.tasks[0].machineId).toBe('machine-1')
    expect(store.errorMessage).toBe(
      '目标机台与任务硬约束不兼容：要求双臂机械手，目标机台仅单臂；目标机台缺少双抽芯能力',
    )
    expect(store.manualConfirmationRequirement).toBeNull()
  })

  it('distinguishes an unknown-data manual confirmation from a hard failure', async () => {
    apiMock.executeOperations.mockRejectedValueOnce({
      isAxiosError: true,
      response: {
        status: 422,
        data: {
          detail: {
            code: 'manual_confirmation_required',
            message: '资料不足，只能在填写人工确认原因后保存到草稿',
            reasons: ['机台最大射胶量缺失', '模具尺寸资料不完整'],
          },
        },
      },
    })
    const store = useInjectionScheduleStore()
    await store.loadWorkspace('huaxing')

    await expect(store.executeOperations(moveRequest())).rejects.toBeTruthy()

    expect(store.formalWorkspace?.tasks[0].machineId).toBe('machine-1')
    expect(store.manualConfirmationRequirement).toEqual({
      code: 'manual_confirmation_required',
      message: '资料不足，只能在填写人工确认原因后保存到草稿',
      reasons: ['机台最大射胶量缺失', '模具尺寸资料不完整'],
    })
    expect(store.errorMessage).toContain('机台最大射胶量缺失')
  })

  it('replaces optimistic tasks, validates the current revision, and refreshes after publish', async () => {
    const initial = formalWorkspace()
    const authoritativeTask = {
      ...initial.tasks[0],
      machineId: 'machine-2',
      machineCode: '7A-02',
      revision: 3,
    }
    const nextVersion = version('huaxing', {
      revision: 3,
      dataHash: 'data-hash-3',
    })
    apiMock.getWorkspace.mockResolvedValueOnce(initial)
    apiMock.executeOperations.mockResolvedValueOnce({
      version: nextVersion,
      tasks: [authoritativeTask],
      conflicts: [],
      affectedMachineIds: ['machine-1', 'machine-2'],
    })
    apiMock.validateVersion.mockResolvedValueOnce({
      id: 'validation-1',
      factoryId: 'huaxing',
      versionId: nextVersion.id,
      versionRevision: 3,
      dataHash: 'validated-data-hash-3',
      resultHash: 'result-hash-3',
      status: 'passed',
      blockingCount: 0,
      warningCount: 0,
      createdBy: 'planner-1',
      createdByName: '计划员',
      createdAt: '2026-07-23T09:00:00+08:00',
      items: [],
    })
    const published = version('huaxing', {
      revision: 4,
      status: 'published',
      dataHash: 'validated-data-hash-3',
      validationHash: 'result-hash-3',
      publishedAt: '2026-07-23T09:05:00+08:00',
      publishedBy: 'planner-1',
      publishedByName: '计划员',
      publishReason: '主管确认',
    })
    apiMock.publishVersion.mockResolvedValueOnce(published)
    apiMock.getWorkspace.mockResolvedValueOnce({
      ...initial,
      workspaceRevision: 4,
      activeVersion: published,
      versions: [published],
      tasks: [{ ...authoritativeTask, revision: 4 }],
    })
    const store = useInjectionScheduleStore()
    await store.loadWorkspace('huaxing')

    await store.saveDraft(moveRequest())
    expect(store.formalWorkspace?.tasks[0]).toMatchObject({
      machineId: 'machine-2',
      machineCode: '7A-02',
      revision: 3,
    })

    await store.validateActiveVersion(3)
    expect(apiMock.validateVersion).toHaveBeenCalledWith(
      'huaxing',
      nextVersion.id,
      3,
    )
    expect(store.activeVersion).toMatchObject({
      dataHash: 'validated-data-hash-3',
      validationHash: 'result-hash-3',
    })
    expect(store.canPublish).toBe(true)

    await store.publishActiveVersion({
      expectedRevision: 3,
      validationRunId: 'validation-1',
      reason: '主管确认',
    })
    expect(apiMock.getWorkspace).toHaveBeenLastCalledWith('huaxing', published.id)
    expect(store.activeVersion?.status).toBe('published')
    expect(store.validation).toBeNull()
  })

  it('rolls back an optimistic master update when the server rejects it', async () => {
    const update = deferred<never>()
    apiMock.updateMachine.mockReturnValueOnce(update.promise)
    const store = useInjectionScheduleStore()
    await store.loadWorkspace('huaxing')
    const original = store.formalWorkspace!.machines[0].maxShotWeightG

    const saving = store.updateMachine('machine-1', 1, { maxShotWeightG: 999 })
    expect(store.formalWorkspace?.machines[0].maxShotWeightG).toBe(999)
    update.reject(new Error('机台更新失败'))
    await expect(saving).rejects.toThrow('机台更新失败')

    expect(store.formalWorkspace?.machines[0].maxShotWeightG).toBe(original)
    expect(store.errorMessage).toBe('机台更新失败')
  })

  it('invalidates validation and diff after a master-data change succeeds', async () => {
    const store = useInjectionScheduleStore()
    await store.loadWorkspace('huaxing')
    const current = store.activeVersion!
    store.validation = {
      id: 'validation-before-master-change',
      factoryId: 'huaxing',
      versionId: current.id,
      versionRevision: current.revision,
      dataHash: current.dataHash,
      resultHash: 'result-before-master-change',
      status: 'passed',
      blockingCount: 0,
      warningCount: 0,
      createdBy: 'planner-1',
      createdByName: '计划员',
      createdAt: timestamp,
      items: [],
    }
    store.versionDiff = {
      versionId: current.id,
      againstVersionId: 'published-1',
      summary: {},
      items: [],
    }
    apiMock.updateMachine.mockResolvedValueOnce({
      ...store.formalWorkspace!.machines[0],
      maxShotWeightG: 999,
      revision: 2,
    })

    await store.updateMachine('machine-1', 1, { maxShotWeightG: 999 })

    expect(store.validation).toBeNull()
    expect(store.versionDiff).toBeNull()
  })

  it('keeps import preview separate and reloads the formal workspace after confirmation', async () => {
    const preview = importBatch()
    const confirmed = importBatch({
      status: 'confirmed',
      draftVersionId: 'huaxing-import-draft-19',
      revision: 4,
      confirmedAt: '2026-07-23T09:00:00+08:00',
      confirmedBy: 'planner-1',
      confirmedByName: '计划员',
      confirmReason: '确认导入华兴日排版',
    })
    apiMock.previewImport.mockResolvedValueOnce(preview)
    apiMock.confirmImport.mockResolvedValueOnce(confirmed)
    apiMock.getWorkspace
      .mockResolvedValueOnce(formalWorkspace())
      .mockResolvedValueOnce({
        ...formalWorkspace(),
        workspaceRevision: 4,
      })
    const store = useInjectionScheduleStore()
    await store.loadWorkspace('huaxing')
    const file = new File(['xlsx'], '排产.xlsx')

    await store.previewImport(file)
    expect(store.importBatch?.status).toBe('previewed')
    await store.confirmImport('batch-1', {
      expectedRevision: 3,
      mode: 'merge',
      businessDate: '2026-07-21',
      reason: '确认导入华兴日排版',
      resolutions: {},
    })

    expect(apiMock.confirmImport).toHaveBeenCalledWith('huaxing', 'batch-1', {
      expectedRevision: 3,
      mode: 'merge',
      businessDate: '2026-07-21',
      reason: '确认导入华兴日排版',
      resolutions: {},
    })
    expect(apiMock.getWorkspace).toHaveBeenLastCalledWith(
      'huaxing',
      'huaxing-import-draft-19',
    )
    expect(store.mode).toBe('formal')
    expect(store.previewWorkspace).toBeNull()
    expect(store.formalWorkspace?.workspaceRevision).toBe(4)
    expect(store.importBatch?.status).toBe('confirmed')
  })

  it('clones a historical version as a new draft and loads that draft explicitly', async () => {
    const cloned = version('huaxing', {
      id: 'huaxing-draft-from-v16',
      versionNo: 19,
      baseVersionId: 'huaxing-published-16',
      revision: 1,
    })
    apiMock.cloneVersionAsDraft.mockResolvedValueOnce(cloned)
    const clonedWorkspace = {
      ...formalWorkspace(),
      activeVersion: cloned,
      versions: [cloned],
      tasks: [],
    }
    apiMock.getWorkspace
      .mockResolvedValueOnce(formalWorkspace())
      .mockResolvedValueOnce(clonedWorkspace)
    const store = useInjectionScheduleStore()
    await store.loadWorkspace('huaxing')

    await store.cloneHistoricalAsDraft('huaxing-published-16', {
      name: '恢复 V16',
      reason: '从历史发布版创建新草稿',
    })

    expect(apiMock.cloneVersionAsDraft).toHaveBeenCalledWith(
      'huaxing',
      'huaxing-published-16',
      { name: '恢复 V16', reason: '从历史发布版创建新草稿' },
    )
    expect(apiMock.getWorkspace).toHaveBeenLastCalledWith(
      'huaxing',
      'huaxing-draft-from-v16',
    )
    expect(store.activeVersion?.id).toBe('huaxing-draft-from-v16')
  })

  it('Phase 3 discards a stale recommendation and rejects a mismatched version revision', async () => {
    const first = deferred<InjectionOrderRecommendationResponse>()
    const second = deferred<InjectionOrderRecommendationResponse>()
    apiMock.getRecommendations
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    const store = useInjectionScheduleStore()
    await store.loadWorkspace('huaxing')

    const olderLoad = store.loadRecommendations('order-1', { limit: 20 })
    const newestLoad = store.loadRecommendations('order-1', { limit: 20 })
    second.resolve(phase3Recommendation('newest-context'))
    await expect(newestLoad).resolves.toMatchObject({
      candidates: [{ recommendationContextHash: 'newest-context' }],
    })
    first.resolve(phase3Recommendation('stale-context'))
    await expect(olderLoad).resolves.toBeUndefined()

    expect(store.recommendation?.candidates[0]?.recommendationContextHash)
      .toBe('newest-context')

    const staleFailure = deferred<InjectionOrderRecommendationResponse>()
    apiMock.getRecommendations
      .mockReturnValueOnce(staleFailure.promise)
      .mockResolvedValueOnce(phase3Recommendation('newest-after-failure'))
    const staleFailedLoad = store.loadRecommendations('order-1', { limit: 20 })
    await store.loadRecommendations('order-1', { limit: 20 })
    staleFailure.reject(new Error('stale network failure'))
    await expect(staleFailedLoad).resolves.toBeUndefined()
    expect(store.errorMessage).toBe('')
    expect(store.recommendation?.candidates[0]?.recommendationContextHash)
      .toBe('newest-after-failure')

    apiMock.getRecommendations.mockResolvedValueOnce(phase3Recommendation(
      'wrong-revision',
      { versionRevision: 999 },
    ))
    await expect(store.loadRecommendations('order-1', { limit: 20 }))
      .rejects.toThrow('推荐结果与当前计划版本 revision 不一致')
    expect(store.recommendation).toBeNull()
  })

  it('Phase 4 keeps preview read-only, requires its context on apply, and aligns cloned tasks by parent id', async () => {
    const nextVersion = version('huaxing', {
      revision: 3,
      updatedAt: '2026-07-23T09:00:00+08:00',
    })
    const nextTask = {
      ...task(nextVersion),
      id: 'task-clone-1',
      parentTaskId: 'task-1',
      plannedFinishAt: '2026-07-24T12:00:00+08:00',
      source: 'auto' as const,
    }
    const contextHash = 'a'.repeat(64)
    const appliedResult = {
      version: nextVersion,
      tasks: [nextTask],
      conflicts: [],
      affectedMachineIds: ['machine-1'],
      affectedOrderIds: ['order-1'],
      affectedTaskIds: ['task-clone-1'],
      run: {
        id: 'run-auto-1',
        factoryId: 'huaxing',
        sourceVersionId: nextVersion.id,
        resultVersionId: nextVersion.id,
        triggerType: 'auto_draft',
        status: 'applied',
        sourceRevision: 2,
        resultRevision: 3,
        contextHash,
        reason: '生成本周自动排程草稿',
        requestId: 'auto-request-1',
        affectedMachineIds: ['machine-1'],
        affectedOrderIds: ['order-1'],
        affectedTaskIds: ['task-clone-1'],
        impact: {
          consideredOrderCount: 1,
          scheduledOrderCount: 1,
          manualReviewOrderCount: 0,
          blockedOrderCount: 0,
          unscheduledOrderIds: [],
          movedTaskCount: 1,
          etaDelayedTaskCount: 1,
          totalEtaShiftMinutes: 240,
          beforeTaskCount: 1,
          afterTaskCount: 1,
          rows: [{
            taskId: 'task-clone-1',
            sourceTaskId: 'task-1',
            orderId: 'order-1',
            machineIdBefore: 'machine-1',
            machineIdAfter: 'machine-1',
            sequenceNoBefore: 0,
            sequenceNoAfter: 0,
            plannedQtyBefore: 18_000,
            plannedQtyAfter: 18_000,
            plannedStartAtBefore: '2026-07-23T08:00:00+08:00',
            plannedStartAtAfter: '2026-07-23T08:00:00+08:00',
            plannedFinishAtBefore: '2026-07-24T08:00:00+08:00',
            plannedFinishAtAfter: '2026-07-24T12:00:00+08:00',
            setupHoursBefore: 1,
            setupHoursAfter: 1,
            etaShiftMinutes: 240,
            executionStatusBefore: 'planned',
            executionStatusAfter: 'planned',
          }],
        },
        createdBy: 'planner-1',
        createdByName: '计划员',
        createdAt: '2026-07-23T09:00:00+08:00',
      },
    }
    apiMock.generateAutoDraft
      .mockResolvedValueOnce({
        ...appliedResult,
        version: version('huaxing', { revision: 2 }),
        run: {
          ...appliedResult.run,
          id: 'run-auto-preview-1',
          status: 'previewed',
          resultRevision: 2,
        },
      })
      .mockResolvedValueOnce(appliedResult)
    const store = useInjectionScheduleStore()
    await store.loadWorkspace('huaxing')

    await store.generateAutoDraft({
      expectedRevision: 2,
      reason: '预览本周自动排程草稿',
      requestId: 'auto-preview-1',
      dryRun: true,
    })

    expect(store.activeVersion?.revision).toBe(2)
    expect(store.formalWorkspace?.tasks[0]?.id).toBe('task-1')
    expect(store.phase4Run?.status).toBe('previewed')

    await store.generateAutoDraft({
      expectedRevision: 2,
      reason: '生成本周自动排程草稿',
      requestId: 'auto-request-1',
      dryRun: false,
      expectedContextHash: contextHash,
    })

    expect(apiMock.generateAutoDraft).toHaveBeenNthCalledWith(
      2,
      'huaxing',
      nextVersion.id,
      expect.objectContaining({
        dryRun: false,
        expectedContextHash: contextHash,
      }),
    )
    expect(store.activeVersion?.revision).toBe(3)
    expect(store.formalWorkspace?.tasks[0]?.source).toBe('auto')
    expect(store.phase4Run?.id).toBe('run-auto-1')
    expect(store.automationProjections).toEqual([expect.objectContaining({
      taskId: 'task-clone-1',
      etaShiftMinutes: 240,
      plannedFinishAtBefore: '2026-07-24T08:00:00+08:00',
      plannedFinishAtAfter: '2026-07-24T12:00:00+08:00',
    })])
    expect(store.validation).toBeNull()
  })

  it('Phase 4 keeps shift actual idempotency and rolling projections authoritative', async () => {
    const currentWorkspace = formalWorkspace()
    const nextVersion = version('huaxing', { revision: 3 })
    const updatedOrder = {
      ...order(),
      producedQty: 2_500,
      outstandingQty: 17_500,
      revision: 2,
    }
    const actual = {
      id: 'actual-1',
      factoryId: 'huaxing',
      versionId: nextVersion.id,
      taskId: 'task-1',
      sourceVersionId: nextVersion.id,
      sourceTaskId: 'task-1',
      orderId: 'order-1',
      machineId: 'machine-1',
      shiftDate: '2026-07-25',
      shift: 'day' as const,
      source: 'manual' as const,
      legacyShiftCode: 'A' as const,
      targetQty: null,
      actualQty: 500,
      varianceQty: null,
      varianceReason: '',
      producedBaselineQty: 2_000,
      outstandingQtyBefore: 18_000,
      outstandingQtyAfter: 17_500,
      shortageQty: 17_500,
      requestId: 'actual-request-1',
      revision: 1,
      correctionCount: 0,
      createdBy: 'planner-1',
      createdByName: '计划员',
      createdAt: timestamp,
      correctedBy: '',
      correctedByName: '',
      correctedAt: '',
    }
    apiMock.getWorkspace.mockResolvedValueOnce(currentWorkspace)
    apiMock.writeActual.mockResolvedValueOnce({
      actual,
      updatedOrder,
      version: nextVersion,
      tasks: [task(nextVersion)],
      projections: [{
        taskId: 'task-1',
        orderId: 'order-1',
        machineId: 'machine-1',
        machineCode: '7A-01',
        plannedQtyBefore: 18_000,
        plannedQtyAfter: 17_500,
        plannedFinishAtBefore: '2026-07-24T08:00:00+08:00',
        plannedFinishAtAfter: '2026-07-24T07:20:00+08:00',
        etaShiftMinutes: -40,
        shortageQty: 17_500,
      }],
      affectedMachineIds: ['machine-1'],
      idempotentReplay: true,
    })
    const store = useInjectionScheduleStore()
    await store.loadWorkspace('huaxing')

    await store.writeActual({
      versionId: nextVersion.id,
      taskId: 'task-1',
      orderId: 'order-1',
      machineId: 'machine-1',
      shiftDate: '2026-07-25',
      shift: 'day',
      actualQty: 500,
      expectedVersionRevision: 2,
      expectedOrderRevision: 1,
      reason: '录入白班 A 实绩',
      requestId: 'actual-request-1',
    })

    expect(store.lastActualResult?.idempotentReplay).toBe(true)
    expect(store.shiftActuals).toEqual([actual])
    expect(store.actualProjections[0]).toMatchObject({
      etaShiftMinutes: -40,
      shortageQty: 17_500,
    })
    expect(store.formalWorkspace?.orders[0]).toMatchObject({
      producedQty: 2_500,
      outstandingQty: 17_500,
      revision: 2,
    })
    expect(store.activeVersion?.revision).toBe(3)
  })

  it('switches a published actual write to the immutable-source rolling draft returned by the server', async () => {
    const published = version('huaxing', {
      id: 'huaxing-published-18',
      versionNo: 18,
      name: '已发布 V18',
      status: 'published',
      revision: 4,
      baseVersionId: null,
      publishedAt: timestamp,
      publishedBy: 'planner-1',
      publishedByName: '计划员',
    })
    const publishedTask = task(published)
    const currentWorkspace = {
      ...formalWorkspace(),
      activeVersion: published,
      versions: [published],
      tasks: [publishedTask],
    }
    const rollingDraft = version('huaxing', {
      id: 'huaxing-draft-19',
      versionNo: 19,
      name: '已发布 V18（实绩滚动）',
      status: 'draft',
      revision: 2,
      baseVersionId: published.id,
    })
    const rollingTask = {
      ...task(rollingDraft),
      id: 'task-rolling-1',
      parentTaskId: publishedTask.id,
      plannedQty: 17_500,
    }
    const updatedOrder = {
      ...order(),
      producedQty: 2_500,
      outstandingQty: 17_500,
      revision: 2,
    }
    const actual = {
      id: 'actual-published-1',
      factoryId: 'huaxing',
      versionId: rollingDraft.id,
      taskId: rollingTask.id,
      sourceVersionId: published.id,
      sourceTaskId: publishedTask.id,
      orderId: 'order-1',
      machineId: 'machine-1',
      shiftDate: '2026-07-25',
      shift: 'night' as const,
      source: 'manual' as const,
      legacyShiftCode: 'B' as const,
      targetQty: null,
      actualQty: 500,
      varianceQty: null,
      varianceReason: '',
      producedBaselineQty: 2_000,
      outstandingQtyBefore: 18_000,
      outstandingQtyAfter: 17_500,
      shortageQty: 17_500,
      requestId: 'actual-published-request-1',
      revision: 1,
      correctionCount: 0,
      createdBy: 'planner-1',
      createdByName: '计划员',
      createdAt: timestamp,
      correctedBy: '',
      correctedByName: '',
      correctedAt: '',
    }
    apiMock.getWorkspace.mockResolvedValueOnce(currentWorkspace)
    apiMock.writeActual.mockResolvedValueOnce({
      actual,
      updatedOrder,
      version: rollingDraft,
      tasks: [rollingTask],
      projections: [],
      affectedMachineIds: ['machine-1'],
      idempotentReplay: false,
    })
    const store = useInjectionScheduleStore()
    await store.loadWorkspace('huaxing')

    await store.writeActual({
      versionId: published.id,
      taskId: publishedTask.id,
      orderId: 'order-1',
      machineId: 'machine-1',
      shiftDate: '2026-07-25',
      shift: 'night',
      source: 'manual',
      legacyShiftCode: 'B',
      actualQty: 500,
      expectedVersionRevision: published.revision,
      expectedOrderRevision: 1,
      reason: '录入夜班 B 实绩',
      requestId: 'actual-published-request-1',
    })

    expect(store.activeVersion).toMatchObject({
      id: rollingDraft.id,
      status: 'draft',
      baseVersionId: published.id,
    })
    expect(store.formalWorkspace?.versions).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: published.id, status: 'published', revision: 4 }),
      expect.objectContaining({ id: rollingDraft.id, status: 'draft' }),
    ]))
    expect(store.formalWorkspace?.tasks[0]).toMatchObject({
      id: rollingTask.id,
      parentTaskId: publishedTask.id,
    })
    expect(store.lastActualResult?.actual).toMatchObject({
      sourceVersionId: published.id,
      sourceTaskId: publishedTask.id,
      legacyShiftCode: 'B',
    })

    const correctedVersion = { ...rollingDraft, revision: 3 }
    apiMock.correctActual.mockResolvedValueOnce({
      actual: {
        ...actual,
        actualQty: 450,
        outstandingQtyAfter: 17_550,
        shortageQty: 17_550,
        revision: 2,
        correctionCount: 1,
      },
      updatedOrder: {
        ...updatedOrder,
        producedQty: 2_450,
        outstandingQty: 17_550,
        revision: 3,
      },
      version: correctedVersion,
      tasks: [{ ...rollingTask, revision: 3, plannedQty: 17_550 }],
      projections: [],
      affectedMachineIds: ['machine-1'],
      idempotentReplay: false,
    })

    await store.correctActual(actual.id, {
      expectedRevision: 1,
      expectedVersionRevision: rollingDraft.revision,
      expectedOrderRevision: updatedOrder.revision,
      actualQty: 450,
      reason: '夜班复核后更正',
      requestId: 'actual-published-correction-1',
    })

    expect(store.activeVersion?.revision).toBe(3)
    expect(store.lastActualResult?.actual).toMatchObject({
      sourceVersionId: published.id,
      versionId: rollingDraft.id,
      revision: 2,
      correctionCount: 1,
    })
  })
})

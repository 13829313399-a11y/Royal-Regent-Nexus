import { computed, ref, watch, type ComputedRef } from 'vue'
import type { Tone } from '@/data/enterpriseMock'

interface PendingOrderMachineRow {
  poolKey?: string
  orderNo: string
  productName?: string
  moldCode: string
  productCode?: string
  color?: string
  colorPowder?: string
  material?: string
  quantity?: string
  orderQuantity?: string
  producedQuantity?: string
  shortageQuantity?: string
  planTarget?: string
  dueDate?: string
  machineAdvice: string
  machineModel?: string
  armType?: string
  remark?: string
  moldSize?: string
  unitWeight?: string
  netWeight?: string
  remainingMaterialKg?: string
  issue: string
  tone: Tone
}

interface MoldMachineMappingRow {
  moldCode: string
  recommendedMachine: string
  backupMachine: string
}

interface InjectionWorkflowBridgeOptions {
  pendingOrders: ComputedRef<PendingOrderMachineRow[]>
  moldMachineMappingRows: ComputedRef<MoldMachineMappingRow[]>
  storageKey?: ComputedRef<string>
}

interface PersistedWorkflowDraft {
  selectedPendingOrderMachines?: Record<string, string>
  schedulingDraftGenerated?: boolean
  schedulingReviewRequested?: boolean
  schedulingDraftReleased?: boolean
  shiftReportDraftSubmitted?: boolean
  inboundWritebackDraftConfirmed?: boolean
}

export function useInjectionWorkflowBridge({
  pendingOrders,
  moldMachineMappingRows,
  storageKey,
}: InjectionWorkflowBridgeOptions) {
  const selectedPendingOrderMachines = ref<Record<string, string>>({})
  const schedulingDraftGenerated = ref(false)
  const schedulingReviewRequested = ref(false)
  const schedulingDraftReleased = ref(false)
  const shiftReportDraftSubmitted = ref(false)
  const inboundWritebackDraftConfirmed = ref(false)

  const getWorkflowStorage = () => {
    try {
      return typeof window === 'undefined' ? null : window.localStorage
    }
    catch {
      return null
    }
  }

  const applyPersistedDraft = (draft: PersistedWorkflowDraft) => {
    selectedPendingOrderMachines.value = draft.selectedPendingOrderMachines ?? {}
    schedulingDraftGenerated.value = Boolean(draft.schedulingDraftGenerated)
    schedulingReviewRequested.value = Boolean(draft.schedulingReviewRequested)
    schedulingDraftReleased.value = Boolean(draft.schedulingDraftReleased)
    shiftReportDraftSubmitted.value = Boolean(draft.shiftReportDraftSubmitted)
    inboundWritebackDraftConfirmed.value = Boolean(draft.inboundWritebackDraftConfirmed)
  }

  const restorePersistedDraft = (key: string) => {
    const storage = getWorkflowStorage()
    if (!storage) {
      return
    }

    try {
      const rawDraft = storage.getItem(key)
      if (!rawDraft) {
        applyPersistedDraft({})
        return
      }

      applyPersistedDraft(JSON.parse(rawDraft) as PersistedWorkflowDraft)
    }
    catch {
      storage.removeItem(key)
      applyPersistedDraft({})
    }
  }

  const persistDraft = (key: string) => {
    const storage = getWorkflowStorage()
    if (!storage) {
      return
    }

    const draft: PersistedWorkflowDraft = {
      selectedPendingOrderMachines: selectedPendingOrderMachines.value,
      schedulingDraftGenerated: schedulingDraftGenerated.value,
      schedulingReviewRequested: schedulingReviewRequested.value,
      schedulingDraftReleased: schedulingDraftReleased.value,
      shiftReportDraftSubmitted: shiftReportDraftSubmitted.value,
      inboundWritebackDraftConfirmed: inboundWritebackDraftConfirmed.value,
    }

    storage.setItem(key, JSON.stringify(draft))
  }

  if (storageKey) {
    restorePersistedDraft(storageKey.value)

    watch(storageKey, (key) => {
      restorePersistedDraft(key)
    })

    watch(
      [
        selectedPendingOrderMachines,
        schedulingDraftGenerated,
        schedulingReviewRequested,
        schedulingDraftReleased,
        shiftReportDraftSubmitted,
        inboundWritebackDraftConfirmed,
      ],
      () => persistDraft(storageKey.value),
      { deep: true },
    )
  }

  const getPendingOrderMachineKey = (row: Pick<PendingOrderMachineRow, 'orderNo' | 'moldCode' | 'poolKey'>) =>
    row.poolKey ?? `${row.orderNo}::${row.moldCode}`

  const resetDownstreamDrafts = () => {
    schedulingDraftGenerated.value = false
    schedulingReviewRequested.value = false
    schedulingDraftReleased.value = false
    shiftReportDraftSubmitted.value = false
    inboundWritebackDraftConfirmed.value = false
  }

  watch(
    () => pendingOrders.value
      .map((row) => `${getPendingOrderMachineKey(row)}::${row.machineAdvice}::${row.quantity ?? ''}::${row.dueDate ?? ''}`)
      .join('|'),
    () => resetDownstreamDrafts(),
  )

  const splitMachineOptions = (value = '') =>
    value
      .split('/')
      .map((item) => item.trim())
      .filter((item) =>
        item
        && !['待确认', '待系统推荐', '待补备选机台', '待补机台映射'].includes(item)
        && !item.includes('待补'),
      )

  const getPendingOrderMachineOptions = (row: PendingOrderMachineRow) => {
    const mapping = moldMachineMappingRows.value.find((item) => item.moldCode === row.moldCode)
    const options = [
      selectedPendingOrderMachines.value[getPendingOrderMachineKey(row)],
      row.machineAdvice,
      mapping?.recommendedMachine,
      mapping?.backupMachine,
    ].flatMap((item) => splitMachineOptions(item))

    return [...new Set(options)]
  }

  const getSelectedPendingOrderMachine = (row: PendingOrderMachineRow) => {
    const key = getPendingOrderMachineKey(row)
    const options = getPendingOrderMachineOptions(row)

    return selectedPendingOrderMachines.value[key] || options[0] || row.machineAdvice || '待确认'
  }

  const updateSelectedPendingOrderMachine = (row: PendingOrderMachineRow, selectedMachine: string) => {
    selectedPendingOrderMachines.value = {
      ...selectedPendingOrderMachines.value,
      [getPendingOrderMachineKey(row)]: selectedMachine,
    }
  }

  const markSchedulingDraftEdited = () => {
    schedulingDraftGenerated.value = true
    schedulingReviewRequested.value = false
    schedulingDraftReleased.value = false
    shiftReportDraftSubmitted.value = false
    inboundWritebackDraftConfirmed.value = false
  }

  const handlePendingOrderMachineChange = (row: PendingOrderMachineRow, event: Event) => {
    const target = event.target as HTMLSelectElement
    updateSelectedPendingOrderMachine(row, target.value)
    resetDownstreamDrafts()
  }

  const handleDraftMachineChange = (row: PendingOrderMachineRow, event: Event) => {
    const target = event.target as HTMLSelectElement
    updateSelectedPendingOrderMachine(row, target.value)
    markSchedulingDraftEdited()
  }

  const getPendingOrderStatusLabel = (row: PendingOrderMachineRow) =>
    selectedPendingOrderMachines.value[getPendingOrderMachineKey(row)] ? '已选机' : row.issue

  const getPendingOrderStatusTone = (row: PendingOrderMachineRow): Tone =>
    selectedPendingOrderMachines.value[getPendingOrderMachineKey(row)] ? 'green' : row.tone

  const parseDisplayInteger = (value = '') => {
    const parsed = Number(String(value).replace(/,/g, '').trim())

    return Number.isFinite(parsed) ? parsed : 0
  }

  const formatDisplayInteger = (value: number) => Math.max(0, Math.round(value)).toLocaleString('en-US')

  const formatDate = (date: Date) => {
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')

    return `${year}-${month}-${day}`
  }

  const estimateProductionWindow = (quantity = '', index = 0) => {
    const today = new Date()
    today.setHours(8, 0, 0, 0)

    const plannedQuantity = parseDisplayInteger(quantity)
    const queueOffsetDays = Math.floor(index / 4)
    const productionDays = Math.max(1, Math.ceil(plannedQuantity / 1800))
    const start = new Date(today)
    const completion = new Date(today)

    start.setDate(today.getDate() + queueOffsetDays)
    completion.setDate(today.getDate() + queueOffsetDays + productionDays)

    return {
      estimatedStartWindow: `${formatDate(start)} 08:00`,
      estimatedCompletionDate: formatDate(completion),
    }
  }

  const getMachineMapping = (row: PendingOrderMachineRow) =>
    moldMachineMappingRows.value.find((item) => item.moldCode === row.moldCode)

  const getRecommendationReason = (
    row: PendingOrderMachineRow,
    selectedMachine: string,
    confirmed: boolean,
  ) => {
    const mapping = getMachineMapping(row)

    if (confirmed) {
      return '计划员已人工确认机台，草稿按人工选择下发。'
    }

    if (mapping?.recommendedMachine === selectedMachine) {
      return '命中模具机台映射，优先采用推荐机台。'
    }

    if (mapping?.backupMachine === selectedMachine) {
      return '推荐机台不可用时，使用备选机台保留产能。'
    }

    if (splitMachineOptions(row.machineAdvice).includes(selectedMachine)) {
      return '沿用订单池中的历史推荐机型，待计划员复核。'
    }

    return '当前草稿按候选机台自动补位，提交前需人工确认。'
  }

  const getRecommendationBasis = (
    row: PendingOrderMachineRow,
    selectedMachine: string,
    confirmed: boolean,
  ) => {
    const mapping = getMachineMapping(row)
    const basis = [
      row.machineModel ? `机型：${row.machineModel}` : '',
      mapping?.recommendedMachine === selectedMachine ? '模具映射命中' : '',
      mapping?.backupMachine === selectedMachine ? '备选池命中' : '',
      confirmed ? '人工锁机' : '系统推荐',
      row.armType ? `机械手：${row.armType}` : '',
    ].filter(Boolean)

    return basis.length > 0 ? basis : ['待补推荐依据']
  }

  const getDraftRisk = (
    row: PendingOrderMachineRow,
    options: string[],
    selectedMachine: string,
    index: number,
  ) => {
    if (selectedMachine.includes('待') || row.issue.includes('待补')) {
      return {
        label: '资料待补',
        tone: 'red' as Tone,
        detail: row.issue || '缺少模具或机台映射，不能直接下发。',
      }
    }

    if (options.length <= 1) {
      return {
        label: '备选不足',
        tone: 'amber' as Tone,
        detail: '当前只有一个可选机台，审核时需确认停机和保养风险。',
      }
    }

    if (row.remark?.includes('喷油')) {
      return {
        label: '工艺确认',
        tone: 'amber' as Tone,
        detail: '订单带喷油或特殊工艺备注，下发前确认后工序衔接。',
      }
    }

    if (index > 0 && index % 4 === 0) {
      return {
        label: '换色确认',
        tone: 'amber' as Tone,
        detail: '排在换色节点附近，建议确认颜色切换顺序和洗机时间。',
      }
    }

    return {
      label: '低风险',
      tone: 'green' as Tone,
      detail: '机台候选和订单字段完整，可按草稿进入审核。',
    }
  }

  const getReviewHint = (confirmed: boolean, riskTone: Tone) => {
    if (riskTone === 'red') {
      return '退回补资料后再提交审核'
    }

    if (riskTone === 'amber') {
      return confirmed ? '主管复核风险后可通过' : '建议计划员先确认机台'
    }

    return confirmed ? '可直接提交主管审核' : '系统推荐可提交，建议抽查'
  }

  const getPriorityMeta = (index: number, row: PendingOrderMachineRow) => {
    if (row.issue.includes('插单') || index < 3) {
      return {
        label: '优先',
        tone: 'blue' as Tone,
      }
    }

    if (index < 8) {
      return {
        label: '本班',
        tone: 'teal' as Tone,
      }
    }

    return {
      label: '续排',
      tone: 'slate' as Tone,
    }
  }

  const pendingOrderMachineDraftRows = computed(() =>
    pendingOrders.value
      .map((row, index) => {
        const options = getPendingOrderMachineOptions(row)
        const selectedMachine = getSelectedPendingOrderMachine(row)
        const confirmed = Boolean(selectedPendingOrderMachines.value[getPendingOrderMachineKey(row)])
        const productionWindow = estimateProductionWindow(row.quantity, index)
        const risk = getDraftRisk(row, options, selectedMachine, index)
        const priority = getPriorityMeta(index, row)

        return {
          ...row,
          selectedMachine,
          machineOptions: options,
          sequence: index + 1,
          ...productionWindow,
          recommendationReason: getRecommendationReason(row, selectedMachine, confirmed),
          recommendationBasis: getRecommendationBasis(row, selectedMachine, confirmed),
          riskLabel: risk.label,
          riskTone: risk.tone,
          riskDetail: risk.detail,
          reviewHint: getReviewHint(confirmed, risk.tone),
          priorityLabel: priority.label,
          priorityTone: priority.tone,
          confirmState: confirmed ? '人工已确认' : '系统推荐',
          confirmTone: confirmed ? 'green' : row.tone,
          releaseState: schedulingDraftReleased.value
            ? '主管已通过'
            : schedulingReviewRequested.value
                ? '待主管审核'
                : schedulingDraftGenerated.value
                    ? '草稿已生成'
                    : '待智能排机',
          releaseTone: (
            schedulingDraftReleased.value
              ? 'green'
              : schedulingReviewRequested.value
                  ? 'amber'
                  : schedulingDraftGenerated.value
                      ? 'blue'
                      : 'slate'
          ) as Tone,
        }
      })
      .filter((row) => row.machineOptions.length > 0),
  )

  const schedulingDraftMetrics = computed(() => {
    const poolTotal = pendingOrders.value.length
    const total = pendingOrderMachineDraftRows.value.length
    const confirmed = pendingOrderMachineDraftRows.value.filter((row) => row.confirmState === '人工已确认').length
    const recommended = total - confirmed
    const machines = new Set(pendingOrderMachineDraftRows.value.map((row) => row.selectedMachine)).size

    return [
      {
        label: '可排订单',
        value: `${total}`,
        detail: poolTotal === total
          ? '来自当前订单池全部可排订单'
          : `当前订单池 ${poolTotal} 行，${total} 行已有候选机台`,
        tone: total > 0 ? 'teal' : 'slate',
      },
      { label: '人工已选机', value: `${confirmed}`, detail: '现场已确认的机台选择', tone: confirmed > 0 ? 'green' : 'slate' },
      { label: '系统推荐', value: `${recommended}`, detail: '未手动修改，按推荐机台进入草稿', tone: recommended > 0 ? 'amber' : 'green' },
      {
        label: '主管审核',
        value: `${machines}`,
        detail: schedulingDraftReleased.value
          ? '主管已审核并下发执行'
          : schedulingReviewRequested.value
              ? '草稿已提交主管审核'
              : schedulingDraftGenerated.value
                  ? '文员草稿待提交'
                  : '待点击智能排机',
        tone: schedulingDraftReleased.value ? 'green' : schedulingReviewRequested.value ? 'amber' : schedulingDraftGenerated.value ? 'blue' : 'slate',
      },
    ] satisfies { label: string; value: string; detail: string; tone: Tone }[]
  })

  const releasedExecutionRows = computed(() =>
    pendingOrderMachineDraftRows.value.slice(0, 12).map((row, index) => {
      const workshop = row.selectedMachine.includes('老车间')
        ? '老车间班组'
        : row.selectedMachine.includes('新车间')
            ? '新车间班组'
            : '注塑班组'
      const action = index % 3 === 0
        ? '核模具 / 上料 / 调机'
        : index % 3 === 1
            ? '换色确认 / 首件确认'
            : '续排生产 / 班次回报'

      return {
        sequence: row.sequence,
        orderNo: row.orderNo,
        productName: row.productName,
        moldCode: row.moldCode,
        color: row.color,
        material: row.material,
        quantity: row.quantity,
        selectedMachine: row.selectedMachine,
        estimatedStartWindow: row.estimatedStartWindow,
        estimatedCompletionDate: row.estimatedCompletionDate,
        workshop,
        action,
        feedbackState: schedulingDraftReleased.value ? '待班次回报' : schedulingReviewRequested.value ? '待主管审核' : '待提交审核',
        stateLabel: schedulingDraftReleased.value ? '已进入执行' : schedulingReviewRequested.value ? '待主管审核' : '未下发',
        stateTone: (schedulingDraftReleased.value ? 'blue' : schedulingReviewRequested.value ? 'amber' : 'slate') as Tone,
      }
    }),
  )

  const shiftReportDraftRows = computed(() =>
    releasedExecutionRows.value.slice(0, 10).map((row, index) => {
      const plannedQuantity = parseDisplayInteger(row.quantity)
      const reportRatio = index % 4 === 0 ? 0.62 : index % 3 === 0 ? 0.54 : 0.48
      const reportedQuantity = schedulingDraftReleased.value ? Math.round(plannedQuantity * reportRatio) : 0
      const shortageAfter = Math.max(0, plannedQuantity - reportedQuantity)
      const stateLabel = shiftReportDraftSubmitted.value
        ? '已提交回报'
        : schedulingDraftReleased.value
            ? '待提交回报'
            : '待下发执行'

      return {
        ...row,
        reportedQuantity: formatDisplayInteger(reportedQuantity),
        shortageAfter: formatDisplayInteger(shortageAfter),
        achievement: plannedQuantity > 0 ? `${Math.round((reportedQuantity / plannedQuantity) * 100)}%` : '0%',
        stateLabel,
        stateTone: (shiftReportDraftSubmitted.value ? 'green' : schedulingDraftReleased.value ? 'amber' : 'slate') as Tone,
      }
    }),
  )

  const shiftReportDraftMetrics = computed(() => {
    const total = shiftReportDraftRows.value.length
    const reported = shiftReportDraftRows.value.reduce((sum, row) => sum + parseDisplayInteger(row.reportedQuantity), 0)
    const shortageAfter = shiftReportDraftRows.value.reduce((sum, row) => sum + parseDisplayInteger(row.shortageAfter), 0)

    return [
      { label: '待回报任务', value: `${total}`, detail: schedulingDraftReleased.value ? '来自已下发执行单' : '等待排机下发', tone: schedulingDraftReleased.value ? 'blue' : 'slate' },
      { label: '本班回报预估', value: formatDisplayInteger(reported), detail: '按当前执行任务生成回报草稿', tone: reported > 0 ? 'teal' : 'slate' },
      { label: '回报后欠数', value: formatDisplayInteger(shortageAfter), detail: '提交后刷新待排池的预览值', tone: shortageAfter > 0 ? 'amber' : 'green' },
      { label: '日报状态', value: shiftReportDraftSubmitted.value ? '已提交' : '待提交', detail: shiftReportDraftSubmitted.value ? '可进入入库回写' : '等待班组确认数量', tone: shiftReportDraftSubmitted.value ? 'green' : 'amber' },
    ] satisfies { label: string; value: string; detail: string; tone: Tone }[]
  })

  const generateSchedulingDraft = () => {
    schedulingDraftGenerated.value = true
    schedulingReviewRequested.value = false
    schedulingDraftReleased.value = false
  }

  const submitSchedulingReview = () => {
    if (!schedulingDraftGenerated.value) {
      return
    }

    schedulingReviewRequested.value = true
    schedulingDraftReleased.value = false
    shiftReportDraftSubmitted.value = false
    inboundWritebackDraftConfirmed.value = false
  }

  const approveSchedulingDraft = () => {
    if (!schedulingDraftGenerated.value || !schedulingReviewRequested.value) {
      return
    }

    schedulingDraftReleased.value = true
    shiftReportDraftSubmitted.value = false
    inboundWritebackDraftConfirmed.value = false
  }

  const releaseSchedulingDraft = approveSchedulingDraft

  const submitShiftReportDraft = () => {
    if (!schedulingDraftReleased.value) {
      return
    }

    shiftReportDraftSubmitted.value = true
    inboundWritebackDraftConfirmed.value = false
  }

  const inboundWritebackDraftRows = computed(() =>
    shiftReportDraftRows.value.slice(0, 10).map((row, index) => {
      const ready = shiftReportDraftSubmitted.value
      const deliveryCode = `RK-${String(index + 1).padStart(3, '0')}-${row.orderNo.slice(-4)}`

      return {
        deliveryCode,
        orderNo: row.orderNo,
        moldCode: row.moldCode,
        selectedMachine: row.selectedMachine,
        inboundQty: row.reportedQuantity,
        shortageAfter: row.shortageAfter,
        warehouseStatus: inboundWritebackDraftConfirmed.value ? '已入库' : ready ? '待入库确认' : '待日报提交',
        erpStatus: inboundWritebackDraftConfirmed.value ? '已回写' : ready ? '待 ERP 回写' : '等待日报',
        schedulerStatus: inboundWritebackDraftConfirmed.value ? '已刷新' : ready ? '待刷新待排池' : '等待日报',
        stateLabel: inboundWritebackDraftConfirmed.value ? '已闭环' : ready ? '待确认回写' : '未就绪',
        stateTone: (inboundWritebackDraftConfirmed.value ? 'green' : ready ? 'amber' : 'slate') as Tone,
      }
    }),
  )

  const inboundWritebackDraftMetrics = computed(() => {
    const total = inboundWritebackDraftRows.value.length
    const inboundQty = inboundWritebackDraftRows.value.reduce((sum, row) => sum + parseDisplayInteger(row.inboundQty), 0)
    const shortageAfter = inboundWritebackDraftRows.value.reduce((sum, row) => sum + parseDisplayInteger(row.shortageAfter), 0)

    return [
      { label: '待入库记录', value: `${total}`, detail: shiftReportDraftSubmitted.value ? '来自已提交日报草稿' : '等待日报提交', tone: shiftReportDraftSubmitted.value ? 'blue' : 'slate' },
      { label: '入库数量', value: formatDisplayInteger(inboundQty), detail: '按班次回报生成入库草稿', tone: inboundQty > 0 ? 'teal' : 'slate' },
      { label: '刷新后欠数', value: formatDisplayInteger(shortageAfter), detail: '入库后同步排产池预览', tone: shortageAfter > 0 ? 'amber' : 'green' },
      { label: '回写状态', value: inboundWritebackDraftConfirmed.value ? '已闭环' : '待确认', detail: inboundWritebackDraftConfirmed.value ? '仓库 / ERP / 排产池已同步' : '等待仓库确认入库', tone: inboundWritebackDraftConfirmed.value ? 'green' : 'amber' },
    ] satisfies { label: string; value: string; detail: string; tone: Tone }[]
  })

  const confirmInboundWritebackDraft = () => {
    if (!shiftReportDraftSubmitted.value) {
      return
    }

    inboundWritebackDraftConfirmed.value = true
  }

  return {
    selectedPendingOrderMachines,
    schedulingDraftGenerated,
    schedulingReviewRequested,
    schedulingDraftReleased,
    shiftReportDraftSubmitted,
    inboundWritebackDraftConfirmed,
    getPendingOrderMachineKey,
    getPendingOrderMachineOptions,
    getSelectedPendingOrderMachine,
    handlePendingOrderMachineChange,
    handleDraftMachineChange,
    getPendingOrderStatusLabel,
    getPendingOrderStatusTone,
    pendingOrderMachineDraftRows,
    schedulingDraftMetrics,
    releasedExecutionRows,
    shiftReportDraftRows,
    shiftReportDraftMetrics,
    inboundWritebackDraftRows,
    inboundWritebackDraftMetrics,
    generateSchedulingDraft,
    submitSchedulingReview,
    approveSchedulingDraft,
    releaseSchedulingDraft,
    submitShiftReportDraft,
    confirmInboundWritebackDraft,
  }
}

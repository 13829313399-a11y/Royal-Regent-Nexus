import { computed, ref, watch, type ComputedRef } from 'vue'
import type { Tone } from '@/data/enterpriseMock'

interface PendingOrderMachineRow {
  poolKey?: string
  orderNo: string
  productName?: string
  moldCode: string
  color?: string
  material?: string
  quantity?: string
  dueDate?: string
  machineAdvice: string
  machineModel?: string
  armType?: string
  remark?: string
  moldSize?: string
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

  const pendingOrderMachineDraftRows = computed(() =>
    pendingOrders.value
      .map((row, index) => {
        const options = getPendingOrderMachineOptions(row)
        const selectedMachine = getSelectedPendingOrderMachine(row)
        const confirmed = Boolean(selectedPendingOrderMachines.value[getPendingOrderMachineKey(row)])

        return {
          ...row,
          selectedMachine,
          machineOptions: options,
          sequence: index + 1,
          confirmState: confirmed ? '人工已确认' : '系统推荐',
          confirmTone: confirmed ? 'green' : row.tone,
          releaseState: schedulingDraftReleased.value
            ? '已下发执行'
            : schedulingDraftGenerated.value
                ? '草稿已生成'
                : '待生成草稿',
          releaseTone: (
            schedulingDraftReleased.value
              ? 'green'
              : schedulingDraftGenerated.value
                  ? 'blue'
                  : 'amber'
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
        label: '待下发订单',
        value: `${total}`,
        detail: poolTotal === total
          ? '来自当前订单池全部可排订单'
          : `当前订单池 ${poolTotal} 行，${total} 行已有候选机台`,
        tone: total > 0 ? 'teal' : 'slate',
      },
      { label: '人工已选机', value: `${confirmed}`, detail: '现场已确认的机台选择', tone: confirmed > 0 ? 'green' : 'slate' },
      { label: '系统推荐', value: `${recommended}`, detail: '未手动修改，按推荐机台进入草稿', tone: recommended > 0 ? 'amber' : 'green' },
      {
        label: '占用机台',
        value: `${machines}`,
        detail: schedulingDraftReleased.value
          ? '已确认下发执行'
          : schedulingDraftGenerated.value
              ? '已生成排机草稿'
              : '待生成结果草稿',
        tone: schedulingDraftReleased.value ? 'green' : schedulingDraftGenerated.value ? 'blue' : 'amber',
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
        workshop,
        action,
        feedbackState: schedulingDraftReleased.value ? '待班次回报' : '待下发',
        stateLabel: schedulingDraftReleased.value ? '已进入执行' : '未下发',
        stateTone: (schedulingDraftReleased.value ? 'blue' : 'slate') as Tone,
      }
    }),
  )

  const parseDisplayInteger = (value = '') => {
    const parsed = Number(String(value).replace(/,/g, '').trim())

    return Number.isFinite(parsed) ? parsed : 0
  }

  const formatDisplayInteger = (value: number) => Math.max(0, Math.round(value)).toLocaleString('en-US')

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
    schedulingDraftReleased.value = false
  }

  const releaseSchedulingDraft = () => {
    if (!schedulingDraftGenerated.value) {
      return
    }

    schedulingDraftReleased.value = true
    shiftReportDraftSubmitted.value = false
    inboundWritebackDraftConfirmed.value = false
  }

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
    releaseSchedulingDraft,
    submitShiftReportDraft,
    confirmInboundWritebackDraft,
  }
}

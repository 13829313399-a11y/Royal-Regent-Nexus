import { computed } from 'vue'
import { isProductionFactoryContextId } from '@/data/enterpriseMock'
import { getInjectionFactoryData } from '@/factories/injection/dataRegistry'
import { useAppStore } from '@/stores/app'

export function useInjectionModuleData() {
  const appStore = useAppStore()

  const activeProductionFactoryId = computed(() =>
    isProductionFactoryContextId(appStore.activeProductionFactory.id)
      ? appStore.activeProductionFactory.id
      : 'huaxing',
  )

  const moduleData = computed(() => getInjectionFactoryData(activeProductionFactoryId.value))

  return {
    activeProductionFactoryId,
    moduleData,
    injectionSectionNav: computed(() => moduleData.value.sectionNav),
    injectionOverviewMetrics: computed(() => moduleData.value.overviewMetrics),
    injectionShiftSummaries: computed(() => moduleData.value.shiftSummaries),
    injectionMachineLoad: computed(() => moduleData.value.machineLoad),
    injectionColorTransitionRisks: computed(() => moduleData.value.colorTransitionRisks),
    injectionDataSourceStatus: computed(() => moduleData.value.dataSourceStatus),
    injectionExecutionTasks: computed(() => moduleData.value.executionTasks),
    injectionWorkflowStages: computed(() => moduleData.value.workflowStages),
    injectionDataCenterDatasets: computed(() => moduleData.value.dataCenterDatasets),
    injectionOrderSnapshotRows: computed(() => moduleData.value.orderSnapshotRows),
    injectionMachineProfileRows: computed(() => moduleData.value.machineProfileRows),
    injectionMoldTargetRows: computed(() => moduleData.value.moldTargetRows),
    injectionExecutionQueueRows: computed(() => moduleData.value.executionQueueRows),
    injectionExecutionRuleMetrics: computed(() => moduleData.value.executionRuleMetrics),
    injectionExecutionConstraintRows: computed(() => moduleData.value.executionConstraintRows),
    injectionExecutionCandidateRows: computed(() => moduleData.value.executionCandidateRows),
    injectionExecutionScheduleRows: computed(() => moduleData.value.executionScheduleRows),
    injectionManualActionRows: computed(() => moduleData.value.manualActionRows),
    injectionReportingMetrics: computed(() => moduleData.value.reportingMetrics),
    injectionShiftReportRows: computed(() => moduleData.value.shiftReportRows),
    injectionShiftReportTemplateGroups: computed(() => moduleData.value.shiftReportTemplateGroups),
    injectionWarehouseInboundRows: computed(() => moduleData.value.warehouseInboundRows),
    injectionWritebackRuleCards: computed(() => moduleData.value.writebackRuleCards),
    injectionConfigRuleCards: computed(() => moduleData.value.configRuleCards),
    injectionPendingOrderFieldGroups: computed(() => moduleData.value.pendingOrderFieldGroups),
    injectionPendingOrderValidationRules: computed(() => moduleData.value.pendingOrderValidationRules),
    injectionOrderImportTasks: computed(() => moduleData.value.orderImportTasks),
    injectionPendingOrderDetailRows: computed(() => moduleData.value.pendingOrderDetailRows),
    injectionMachineMasterRows: computed(() => moduleData.value.machineMasterRows),
    injectionMoldTargetDetailRows: computed(() => moduleData.value.moldTargetDetailRows),
    injectionMoldMachineMappingRows: computed(() => moduleData.value.moldMachineMappingRows),
    injectionShiftReportChecklistItems: computed(() => moduleData.value.shiftReportChecklistItems),
    injectionShiftHandoverRows: computed(() => moduleData.value.shiftHandoverRows),
    injectionInboundWritebackRows: computed(() => moduleData.value.inboundWritebackRows),
  }
}

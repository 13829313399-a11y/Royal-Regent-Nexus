<script setup lang="ts">
import { computed, ref } from 'vue'
import AutoSchedulePreviewDialog from '../../components/AutoSchedulePreviewDialog.vue'
import BacklogDock from '../../components/BacklogDock.vue'
import MachineGroupRow from '../../components/MachineGroupRow.vue'
import PublishPlanDialog from '../../components/PublishPlanDialog.vue'
import RevisionConflictDialog from '../../components/RevisionConflictDialog.vue'
import ScheduleRunHistory from '../../components/ScheduleRunHistory.vue'
import SchedulingCommandBar from '../../components/SchedulingCommandBar.vue'
import SchedulingTechnicalDetails from '../../components/SchedulingTechnicalDetails.vue'
import { formatPlanRevision } from '../../presentation/schedulingFormatters'
import { planTechnicalDetails } from '../../presentation/technicalDetails'
import type { AutoScheduleRunRecord, MachineRecord, OrderRecord, RevisionConflict, ScheduleGridRow, SchedulingPlanRecord } from '../../types'

const activeDialog = ref<'auto' | 'publish' | 'conflict' | null>(null)
const plan: SchedulingPlanRecord = {
  id: 'deidentified-plan', status: 'PUBLISHED', revision: 14, ruleRevision: 3, businessDate: '2026-08-10',
  exportProfileId: 'deidentified-profile', exportProfileRevision: 7, exportBindingSource: 'LEGACY_UNKNOWN', calculationVersion: 'qa-v1',
}
const machine: MachineRecord = {
  id: 'machine-demo', factoryId: 'huaxing', code: '测试机台-01', position: '01', area: '去敏车间', aClass: 12, aClassRaw: '12A',
  clampingForceTons: 120, injectionCapacityG: 200, tieBarXmm: 400, tieBarYmm: 400, processTags: [],
  armCapabilities: ['标准机械手'], fixtureCapabilities: ['标准夹具'], processRestrictions: [], equipmentDetails: {}, remarks: '',
  machineType: 'standard', specialMachineType: '', status: 'maintenance', normalizationStatus: 'COMPLETE', revision: 1,
}
const machineRow: ScheduleGridRow = {
  rowType: 'machine', id: machine.id, machine, status: machine.status, sequence: '', position: machine.position, machineCode: machine.code,
  automation: '', marker: '', moldA: '', moldNo: '', productName: '', orderNo: '', itemNo: '', setQuantity: '', orderQuantity: '',
  completedQuantity: '', outstandingQuantity: '', progress: 0, targetQuantity: '', shiftCompleted: '', sprueRatio: '', color: '', powder: '', material: '',
  netWeightG: '', grossWeightG: '', materialKg: '', unitPrice: '', ratio: '', orderDate: '', deliveryStart: '', deliveryDue: '', moldChangeRef: '',
  colorChangeRef: '', setupTime: '', downtime: '', exception: '', plannedStart: '', plannedFinish: '', planMonth: '', warehouseDate: '', slack: '',
  spray: '', productionDays: '', machineA: '', shotCapacity: '', fit: 'PASS', warehouse: '', remark: '', shipDate: '', arm: '', fixture: '',
  priority: '', materialReadiness: '',
}
const order: OrderRecord = {
  id: 'order-demo', orderNo: '去敏订单-001', itemNo: 'TEST-001', productName: '去敏测试件', moldId: null, moldDefinitionId: null,
  moldOutputSpecId: null, orderQuantity: 100,
  sourceCompletedQuantity: 0, completedQuantity: 0, outstandingQuantity: 100, completionRate: 0, deliveryStartDate: '2026-08-10',
  deliveryDueDate: '2026-08-18', deliverySlackDays: 8, priorityCode: 'CRITICAL', materialReadinessStatus: 'ready', warehouseText: '',
  remark: '', status: 'BACKLOG', sourceType: 'DEMAND_ORDER', lineage: { source_mold_no: 'TEST-MOLD' }, revision: 1,
}
const run: AutoScheduleRunRecord = {
  id: 'run-demo', factoryId: 'huaxing', planId: plan.id, expectedPlanRevision: 14, ruleRevision: 3,
  solverType: 'CP_SAT', requestedSolver: 'CP_SAT', solverVersion: 'qa-solver-v1', solverStatus: 'OPTIMAL', fallbackUsed: false, fallbackReason: '',
  scenarioGroupId: 'scenario-demo', scenarioName: '方案 A · 综合平衡', alternativeNo: 1, replayOfRunId: null,
  objectiveWeights: { tardinessWeight: 100, transitionWeight: 2, classGapWeight: 1.5, loadBalanceWeight: 25, existingTaskMoveCost: 40 },
  status: 'SUCCEEDED', horizonStart: '2026-08-10T08:00:00+08:00', horizonEnd: '2026-08-18T20:00:00+08:00',
  summary: { inputOrderCount: 1, scheduledCount: 1, reviewCount: 0, unassignedCount: 0, movedTaskCount: 0, localImprovementMoveCount: 0,
    frozenTaskCount: 0, overdue: { before: 1, after: 0, change: -1 }, moldChanges: { before: 2, after: 1, change: -1 },
    darkToLightChanges: { before: 1, after: 0, change: -1 }, machineLoads: [{ machineId: machine.id, machineCode: machine.code, scheduledMinutes: 240, loadRatio: .25 }],
    solverElapsedMs: 862, solverStatus: 'OPTIMAL', objectiveValue: 120, bestObjectiveBound: 120, fallbackUsed: false, fallbackReason: '' },
  errorDetail: '', createdByName: '去敏计划员', createdAt: '2026-08-10T16:42:00+08:00', appliedByName: '', appliedAt: '', assignments: [],
}
const conflict: RevisionConflict = {
  title: 'Task revision conflict', message: 'expected revision 13 but found revision 14',
  localValues: { status: 'RUNNING', targetQuantity: 90 }, serverValues: { status: 'QUEUED', targetQuantity: 80 }, retry: async () => {},
}
const technicalItems = computed(() => planTechnicalDetails({ plan, activeSlice: 'execution', eventSequence: 98 }))
</script>

<template>
  <main class="b1b-shell injection-scheduling-v2">
    <div class="b1b-heading">
      <strong>B1b 业务标签去敏验收夹具 · 不含生产数据</strong>
      <button type="button" @click="activeDialog = 'auto'">查看自动排期</button>
      <button type="button" @click="activeDialog = 'publish'">查看发布确认</button>
      <button type="button" @click="activeDialog = 'conflict'">查看版本冲突</button>
    </div>
    <section class="b1b-stage">
      <SchedulingCommandBar factory-id="huaxing" factory-name="去敏测试厂区" source-mode="live" source-message="正式数据库" sync-health="live"
        :refreshing="false" search="" last-synced-at="" plan-status="PUBLISHED" :pending-count="0" :saving="false" :can-save="false"
        :can-import="false" :can-export="false" :has-planning-draft="true" :can-publish="true" :publishing-plan="false"
        publish-disabled-reason="" save-message="" />
      <div class="b1b-workspace">
        <div class="b1b-workspace-header"><strong>主工作区计划状态</strong><span class="b1b-plan-chip">当前执行 · {{ formatPlanRevision(plan.revision) }}</span><span>排产草案 · 版本 15</span><SchedulingTechnicalDetails :items="technicalItems" /></div>
        <div class="b1b-table"><table><tbody><MachineGroupRow :row="machineRow" :collapsed="false" :top="0" :width="1180" :row-index="3" :column-count="16" :task-count="1" current-label="去敏测试任务" release-at="18:00" :drop-enabled="false" :drop-target="false" /></tbody></table></div>
        <BacklogDock :orders="[order]" :molds="[]" :open="true" :can-append="false" :can-edit-demand="false" append-disabled-reason="去敏夹具禁用业务操作" />
        <ScheduleRunHistory :runs="[run]" />
      </div>
    </section>
    <AutoSchedulePreviewDialog :open="activeDialog === 'auto'" :backlog-count="1" :machine-count="1" plan-status="DRAFT" :can-edit="true" :can-override="true" :run="run" :comparison-runs="[run]" :loading="false" error="" :orders="[order]" :machines="[machine]" @close="activeDialog = null" />
    <PublishPlanDialog :open="activeDialog === 'publish'" :plan="{ ...plan, status: 'DRAFT', revision: 15 }" :task-count="1" :can-publish="true" :publishing="false" error="" @close="activeDialog = null" />
    <RevisionConflictDialog :conflict="activeDialog === 'conflict' ? conflict : null" :loading="false" @close="activeDialog = null" />
  </main>
</template>

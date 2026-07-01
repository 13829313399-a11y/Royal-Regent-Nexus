<script setup lang="ts">
import {
  AlertTriangle,
  Boxes,
  ClipboardList,
  Database,
  Factory,
  FileText,
  Layers3,
  Package,
  RefreshCcw,
  ShieldAlert,
  SquareTerminal,
  Waypoints,
} from '@lucide/vue'
import { computed } from 'vue'
import ProgressMeter from '@/components/common/ProgressMeter.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import type { InjectionSectionId } from '@/data/injectionSchedulingMock'
import { useInjectionModuleData } from '@/factories/injection/useInjectionModuleData'

const props = defineProps<{
  activeSection: InjectionSectionId
}>()

const {
  injectionColorTransitionRisks,
  injectionConfigRuleCards,
  injectionDataCenterDatasets,
  injectionDataSourceStatus,
  injectionExecutionCandidateRows,
  injectionExecutionConstraintRows,
  injectionExecutionRuleMetrics,
  injectionExecutionScheduleRows,
  injectionExecutionTasks,
  injectionInboundWritebackRows,
  injectionMachineLoad,
  injectionMachineMasterRows,
  injectionMachineProfileRows,
  injectionMoldMachineMappingRows,
  injectionMoldTargetDetailRows,
  injectionMoldTargetRows,
  injectionOrderImportTasks,
  injectionOverviewMetrics,
  injectionPendingOrderDetailRows,
  injectionPendingOrderFieldGroups,
  injectionPendingOrderValidationRules,
  injectionReportingMetrics,
  injectionShiftHandoverRows,
  injectionShiftReportImportMappingRows,
  injectionShiftReportChecklistItems,
  injectionShiftReportRows,
  injectionShiftReportTemplateGroups,
  injectionShiftSummaries,
  injectionWarehouseInboundRows,
  injectionWritebackRuleCards,
  injectionWritebackKeyMatchRows,
  injectionWorkflowStages,
} = useInjectionModuleData()

const compactPendingOrders = computed(() => injectionPendingOrderDetailRows.value.slice(0, 18))
const compactCandidateRows = computed(() => injectionExecutionCandidateRows.value.slice(0, 8))
const compactScheduleRows = computed(() => injectionExecutionScheduleRows.value.slice(0, 8))
const compactMachineRows = computed(() => injectionMachineMasterRows.value.slice(0, 18))
const compactMachineProfiles = computed(() => injectionMachineProfileRows.value.slice(0, 8))
const compactMoldRows = computed(() => injectionMoldTargetDetailRows.value.slice(0, 16))
const compactMappingRows = computed(() => injectionMoldMachineMappingRows.value.slice(0, 10))

const panelTone = {
  green: 'bg-emerald-50 border-emerald-100',
  blue: 'bg-blue-50 border-blue-100',
  amber: 'bg-amber-50 border-amber-100',
  red: 'bg-red-50 border-red-100',
  teal: 'bg-teal-50 border-teal-100',
  slate: 'bg-slate-100 border-slate-200',
} as const

const workflowTone = {
  done: 'green',
  active: 'blue',
  pending: 'slate',
} as const
</script>

<template>
  <div class="space-y-6">
    <template v-if="props.activeSection === 'monthly-plan'">
      <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <article
          v-for="metric in injectionOverviewMetrics"
          :key="metric.label"
          class="rounded-2xl border border-slate-200 bg-white p-5"
        >
          <p class="text-sm text-slate-500">{{ metric.label }}</p>
          <p class="mt-4 text-3xl font-semibold tracking-tight text-slate-950">{{ metric.value }}</p>
          <p class="mt-3 text-xs leading-5 text-slate-500">{{ metric.detail }}</p>
        </article>
      </section>

      <div class="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <SectionPanel
          title="班次概览"
          subtitle="先看本月计划里最常用的班次执行、结转和预警，不把所有信息一股脑堆在首页。"
        >
          <div class="grid gap-4 lg:grid-cols-2">
            <article
              v-for="shift in injectionShiftSummaries"
              :key="shift.shift"
              class="rounded-2xl border border-slate-200 bg-white p-5"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="text-xs uppercase tracking-[0.22em] text-slate-500">{{ shift.date }}</p>
                  <h3 class="mt-2 text-lg font-semibold text-slate-950">{{ shift.shift }}</h3>
                </div>
                <StatusPill :label="`${shift.completion}%`" :tone="shift.completion >= 75 ? 'green' : 'amber'" />
              </div>
              <div class="mt-4">
                <ProgressMeter :value="shift.completion" :tone="shift.completion >= 75 ? 'green' : 'amber'" label="完成度" />
              </div>
              <div class="mt-4 grid gap-3 sm:grid-cols-2">
                <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">{{ shift.machineRunning }}</div>
                <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">{{ shift.carryOver }}</div>
              </div>
              <div class="mt-4 rounded-xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                {{ shift.alert }}
              </div>
            </article>
          </div>
        </SectionPanel>

        <SectionPanel
          title="重点动作"
          subtitle="首页只保留今天最值得处理的动作，不再塞满所有中后台内容。"
        >
          <div class="space-y-3">
            <article
              v-for="task in injectionExecutionTasks"
              :key="task.title"
              class="rounded-2xl border p-4"
              :class="panelTone[task.tone]"
            >
              <div class="flex items-start gap-3">
                <span class="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-white text-slate-700">
                  <AlertTriangle class="size-4" aria-hidden="true" />
                </span>
                <div>
                  <h3 class="font-semibold text-slate-950">{{ task.title }}</h3>
                  <p class="mt-2 text-sm leading-6 text-slate-600">{{ task.meta }}</p>
                </div>
              </div>
            </article>
          </div>

          <div class="mt-4 rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-5 py-4">
            <div class="flex items-center gap-3">
              <Boxes class="size-5 text-slate-500" aria-hidden="true" />
              <p class="text-sm leading-6 text-slate-600">
                月计划页只做“看全局 + 找风险”，真正操作下沉到订单导入、智能排机和排机结果。
              </p>
            </div>
          </div>
        </SectionPanel>
      </div>
    </template>

    <template v-else-if="props.activeSection === 'order-import'">
      <div class="grid gap-6 xl:grid-cols-[0.82fr_1.18fr]">
        <SectionPanel
          title="导入步骤"
          subtitle="先导订单，再做字段校验和人工补齐，流程尽量像工厂现场真实习惯。"
        >
          <div class="space-y-3">
            <article
              v-for="task in injectionOrderImportTasks"
              :key="task.step"
              class="rounded-2xl border p-4"
              :class="panelTone[task.tone]"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="flex items-center gap-3">
                  <span class="flex size-10 items-center justify-center rounded-2xl bg-white text-slate-700">
                    <ClipboardList class="size-4" aria-hidden="true" />
                  </span>
                  <div>
                    <h3 class="font-semibold text-slate-950">{{ task.step }}</h3>
                    <p class="mt-1 text-xs text-slate-500">{{ task.owner }}</p>
                  </div>
                </div>
                <StatusPill :label="task.status" :tone="task.tone" compact />
              </div>
              <p class="mt-4 text-sm leading-6 text-slate-600">{{ task.detail }}</p>
            </article>
          </div>
        </SectionPanel>

        <SectionPanel
          title="字段校验"
          subtitle="把高风险和缺字段直接放在导入旁边，工厂人员一进来就知道要先补什么。"
        >
          <div class="grid gap-4 md:grid-cols-2">
            <article
              v-for="rule in injectionPendingOrderValidationRules"
              :key="rule.label"
              class="rounded-2xl border border-slate-200 bg-white p-4"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="flex items-center gap-3">
                  <span class="flex size-10 items-center justify-center rounded-2xl bg-slate-100 text-slate-700">
                    <ShieldAlert class="size-4" aria-hidden="true" />
                  </span>
                  <div>
                    <h3 class="font-semibold text-slate-950">{{ rule.label }}</h3>
                    <p class="mt-1 text-xs text-slate-500">{{ rule.hit }}</p>
                  </div>
                </div>
                <StatusPill :label="rule.hit" :tone="rule.tone" compact />
              </div>
              <p class="mt-4 text-sm leading-6 text-slate-600">{{ rule.detail }}</p>
            </article>
          </div>
        </SectionPanel>
      </div>

      <SectionPanel
        title="订单池"
        subtitle="这里保留工厂最常看的几列，避免一屏表头太宽、太难用。"
      >
        <div class="overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
              <tr>
                <th class="pb-3 pr-4 font-medium">单号</th>
                <th class="pb-3 pr-4 font-medium">产品</th>
                <th class="pb-3 pr-4 font-medium">模具</th>
                <th class="pb-3 pr-4 font-medium">颜色 / 料型</th>
                <th class="pb-3 pr-4 font-medium">待排数量</th>
                <th class="pb-3 pr-4 font-medium">交期</th>
                <th class="pb-3 pr-4 font-medium">机台</th>
                <th class="pb-3 font-medium">状态</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in compactPendingOrders"
                :key="`${row.orderNo}-${row.moldCode}-${row.machineAdvice}`"
                class="border-b border-slate-100 align-top last:border-b-0"
              >
                <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.orderNo }}</td>
                <td class="py-4 pr-4 text-slate-600">
                  <div>{{ row.customer }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ row.productName }}</div>
                </td>
                <td class="py-4 pr-4 text-slate-600">{{ row.moldCode }}</td>
                <td class="py-4 pr-4 text-slate-600">
                  <div>{{ row.color }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ row.material }}</div>
                </td>
                <td class="py-4 pr-4 text-slate-600">{{ row.quantity }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.dueDate }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.machineAdvice }}</td>
                <td class="py-4">
                  <StatusPill :label="row.issue" :tone="row.tone" compact />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionPanel>

      <SectionPanel
        title="订单标准字段"
        subtitle="现场如果不知道要补什么，这里就是最简版字段说明。"
      >
        <div class="grid gap-4 xl:grid-cols-3">
          <article
            v-for="group in injectionPendingOrderFieldGroups"
            :key="group.title"
            class="rounded-2xl border border-slate-200 bg-white p-5"
          >
            <h3 class="font-semibold text-slate-950">{{ group.title }}</h3>
            <p class="mt-1 text-xs text-slate-500">{{ group.owner }}</p>
            <div class="mt-4 space-y-3">
              <article
                v-for="field in group.fields"
                :key="`${group.title}-${field.label}`"
                class="rounded-xl bg-slate-50 px-4 py-3"
              >
                <div class="flex items-center justify-between gap-3">
                  <p class="font-medium text-slate-900">{{ field.label }}</p>
                  <StatusPill :label="field.required ? '必填' : '建议'" :tone="field.required ? 'red' : 'blue'" compact />
                </div>
                <p class="mt-2 text-xs text-slate-500">来源：{{ field.source }}</p>
              </article>
            </div>
          </article>
        </div>
      </SectionPanel>
    </template>

    <template v-else-if="props.activeSection === 'smart-scheduling'">
      <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <article
          v-for="metric in injectionExecutionRuleMetrics"
          :key="metric.label"
          class="rounded-2xl border border-slate-200 bg-white p-5"
        >
          <p class="text-sm text-slate-500">{{ metric.label }}</p>
          <p class="mt-4 text-3xl font-semibold tracking-tight text-slate-950">{{ metric.value }}</p>
          <p class="mt-3 text-xs leading-5 text-slate-500">{{ metric.detail }}</p>
        </article>
      </section>

      <div class="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <SectionPanel
          title="候选机台"
          subtitle="这里只放推荐结果和阻塞原因，计划员点击进来就知道下一步该怎么排。"
        >
          <div class="space-y-4">
            <article
              v-for="row in compactCandidateRows"
              :key="`${row.orderNo}-${row.moldCode}`"
              class="rounded-2xl border border-slate-200 bg-white p-5"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="text-xs uppercase tracking-[0.2em] text-slate-500">{{ row.orderNo }}</p>
                  <h3 class="mt-2 text-lg font-semibold text-slate-950">{{ row.moldCode }}</h3>
                </div>
                <StatusPill :label="row.recommendedMachine" :tone="row.tone" compact />
              </div>
              <div class="mt-4 grid gap-3 md:grid-cols-2">
                <div class="rounded-xl bg-slate-50 px-4 py-3">
                  <p class="text-xs uppercase tracking-[0.2em] text-slate-500">备选机台</p>
                  <p class="mt-2 text-sm text-slate-900">{{ row.backupMachine }}</p>
                </div>
                <div class="rounded-xl bg-slate-50 px-4 py-3">
                  <p class="text-xs uppercase tracking-[0.2em] text-slate-500">当前阻塞</p>
                  <p class="mt-2 text-sm leading-6 text-slate-700">{{ row.blocker }}</p>
                </div>
              </div>
              <p class="mt-4 text-sm leading-6 text-slate-600">{{ row.reason }}</p>
            </article>
          </div>
        </SectionPanel>

        <SectionPanel
          title="设备拦截规则"
          subtitle="把工艺限制单独列出来，避免现场同事来回切页找原因。"
        >
          <div class="space-y-3">
            <article
              v-for="item in injectionExecutionConstraintRows"
              :key="item.machine"
              class="rounded-2xl border p-4"
              :class="panelTone[item.tone]"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <h3 class="font-semibold text-slate-950">{{ item.machine }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ item.workshop }} · {{ item.tonnage }} · {{ item.robot }}</p>
                </div>
                <StatusPill :label="item.tone === 'red' ? '硬拦截' : item.tone === 'amber' ? '需确认' : '可候选'" :tone="item.tone" compact />
              </div>
              <p class="mt-3 text-sm leading-6 text-slate-700">{{ item.limit }}</p>
              <p class="mt-2 text-xs leading-5 text-slate-500">{{ item.action }}</p>
            </article>
          </div>
        </SectionPanel>
      </div>

      <SectionPanel
        title="规则流程"
        subtitle="智能排机页只保留排机逻辑主链，让页面更像操作台，而不是汇报页。"
      >
        <div class="grid gap-4 xl:grid-cols-5">
          <article
            v-for="stage in injectionWorkflowStages"
            :key="stage.title"
            class="rounded-2xl border border-slate-200 bg-white p-4"
          >
            <div class="flex items-center justify-between gap-3">
              <h3 class="font-semibold text-slate-950">{{ stage.title }}</h3>
              <StatusPill
                :label="stage.state === 'done' ? '已完成' : stage.state === 'active' ? '进行中' : '待进入'"
                :tone="workflowTone[stage.state]"
                compact
              />
            </div>
            <p class="mt-3 text-xs text-slate-500">{{ stage.owner }}</p>
            <p class="mt-3 text-sm leading-6 text-slate-600">{{ stage.detail }}</p>
          </article>
        </div>
      </SectionPanel>
    </template>

    <template v-else-if="props.activeSection === 'scheduling-results'">
      <SectionPanel
        title="排机结果"
        subtitle="把排机结果和开机窗口放在一页，现场更容易直接往下执行。"
      >
        <div class="grid gap-4 xl:grid-cols-3">
          <article
            v-for="row in compactScheduleRows"
            :key="`${row.orderNo}-${row.machine}`"
            class="rounded-2xl border border-slate-200 bg-white p-5"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-xs uppercase tracking-[0.2em] text-slate-500">{{ row.orderNo }}</p>
                <h3 class="mt-2 text-lg font-semibold text-slate-950">{{ row.machine }}</h3>
              </div>
              <StatusPill :label="row.shiftPlan" :tone="row.tone" compact />
            </div>
            <div class="mt-4 space-y-3">
              <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">建议开机：{{ row.startWindow }}</div>
              <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">预计完工：{{ row.endWindow }}</div>
              <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">产出预估：{{ row.expectedOutput }}</div>
            </div>
            <p class="mt-4 text-sm leading-6 text-slate-600">{{ row.dependency }}</p>
          </article>
        </div>
      </SectionPanel>

      <div class="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <SectionPanel
          title="机台负载"
          subtitle="结果页只看当前排机结果占用了哪些机台，不再混太多策略说明。"
        >
          <div class="grid gap-4 md:grid-cols-2">
            <article
              v-for="machine in injectionMachineLoad"
              :key="machine.machine"
              class="rounded-2xl border border-slate-200 bg-white p-4"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <h3 class="font-semibold text-slate-950">{{ machine.machine }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ machine.mold }}</p>
                </div>
                <StatusPill :label="machine.queueDepth" :tone="machine.tone" compact />
              </div>
              <div class="mt-4">
                <ProgressMeter :value="machine.utilization" :tone="machine.tone" label="机台负载" />
              </div>
              <p class="mt-4 text-sm text-slate-600">{{ machine.material }}</p>
            </article>
          </div>
        </SectionPanel>

        <SectionPanel
          title="颜色切换"
          subtitle="只保留换色顺序风险，方便快速确认是否需要改机或调顺序。"
        >
          <div class="space-y-3">
            <article
              v-for="risk in injectionColorTransitionRisks"
              :key="risk.machine"
              class="rounded-2xl border border-slate-200 bg-white px-5 py-4"
            >
              <div class="flex items-center justify-between gap-3">
                <div>
                  <h3 class="font-semibold text-slate-950">{{ risk.machine }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ risk.route.join(' → ') }}</p>
                </div>
                <StatusPill :label="risk.risk" :tone="risk.tone" compact />
              </div>
            </article>
          </div>
        </SectionPanel>
      </div>
    </template>

    <template v-else-if="props.activeSection === 'daily-report'">
      <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <article
          v-for="metric in injectionReportingMetrics"
          :key="metric.label"
          class="rounded-2xl border border-slate-200 bg-white p-5"
        >
          <p class="text-sm text-slate-500">{{ metric.label }}</p>
          <p class="mt-4 text-3xl font-semibold tracking-tight text-slate-950">{{ metric.value }}</p>
          <p class="mt-3 text-xs leading-5 text-slate-500">{{ metric.detail }}</p>
        </article>
      </section>

      <div class="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <SectionPanel
          title="日报清单"
          subtitle="车间最常看的日报和回报动作统一放这页。"
        >
          <div class="space-y-3">
            <article
              v-for="item in injectionShiftReportChecklistItems"
              :key="item.title"
              class="rounded-2xl border p-4"
              :class="panelTone[item.tone]"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <h3 class="font-semibold text-slate-950">{{ item.title }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ item.owner }}</p>
                </div>
                <StatusPill :label="item.status" :tone="item.tone" compact />
              </div>
              <p class="mt-3 text-sm leading-6 text-slate-600">{{ item.detail }}</p>
            </article>
          </div>
        </SectionPanel>

        <SectionPanel
          title="录入模板"
          subtitle="先把车间每天必须回报的字段固定下来，后面接 Excel 或表单都直接复用这套结构。"
        >
          <div class="space-y-4">
            <article
              v-for="group in injectionShiftReportTemplateGroups"
              :key="group.title"
              class="rounded-2xl border border-slate-200 bg-white p-5"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <h3 class="font-semibold text-slate-950">{{ group.title }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ group.owner }}</p>
                </div>
                <StatusPill :label="`${group.fields.length} 项`" tone="blue" compact />
              </div>
              <div class="mt-4 grid gap-3">
                <article
                  v-for="field in group.fields"
                  :key="`${group.title}-${field.label}`"
                  class="rounded-xl bg-slate-50 px-4 py-3"
                >
                  <div class="flex items-center justify-between gap-3">
                    <p class="font-medium text-slate-900">{{ field.label }}</p>
                    <StatusPill :label="field.required ? '必填' : '选填'" :tone="field.required ? 'red' : 'blue'" compact />
                  </div>
                  <p class="mt-2 text-xs text-slate-500">来源：{{ field.source }}</p>
                  <p class="mt-2 text-sm leading-6 text-slate-600">{{ field.summary }}</p>
                </article>
              </div>
            </article>
          </div>
        </SectionPanel>
      </div>

      <SectionPanel
        title="班次交接"
        subtitle="交接记录单独放一块，避免和排机逻辑混在一起。"
      >
        <div class="grid gap-4 xl:grid-cols-2">
          <article
            v-for="row in injectionShiftHandoverRows"
            :key="`${row.shift}-${row.machine}-${row.orderNo}`"
            class="rounded-2xl border border-slate-200 bg-white p-4"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="flex items-center gap-3">
                <span class="flex size-10 items-center justify-center rounded-2xl bg-slate-100 text-slate-700">
                  <RefreshCcw class="size-4" aria-hidden="true" />
                </span>
                <div>
                  <h3 class="font-semibold text-slate-950">{{ row.shift }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ row.machine }} · {{ row.orderNo }}</p>
                </div>
              </div>
              <StatusPill :label="row.carryOverQty" :tone="row.tone" compact />
            </div>
            <p class="mt-3 text-sm leading-6 text-slate-600">{{ row.note }}</p>
          </article>
        </div>
      </SectionPanel>

      <SectionPanel
        title="班次日报表"
        subtitle="保留最常用日报字段，适合后面继续做真实录入表单。"
      >
        <div class="overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
              <tr>
                <th class="pb-3 pr-4 font-medium">机台</th>
                <th class="pb-3 pr-4 font-medium">操作员</th>
                <th class="pb-3 pr-4 font-medium">11H 目标</th>
                <th class="pb-3 pr-4 font-medium">实际</th>
                <th class="pb-3 pr-4 font-medium">差异</th>
                <th class="pb-3 font-medium">停机</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in injectionShiftReportRows"
                :key="`${row.machine}-${row.worker}`"
                class="border-b border-slate-100 last:border-b-0"
              >
                <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.machine }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.worker }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.target11h }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.actual }}</td>
                <td class="py-4 pr-4">
                  <StatusPill :label="row.variance" :tone="row.tone" compact />
                </td>
                <td class="py-4 text-slate-600">{{ row.downtime }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionPanel>

      <SectionPanel
        title="导入字段映射"
        subtitle="把车间 Excel 列和系统字段先对齐，后面接真实日报导入时就能直接套规则。"
      >
        <div class="overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
              <tr>
                <th class="pb-3 pr-4 font-medium">来源列</th>
                <th class="pb-3 pr-4 font-medium">系统字段</th>
                <th class="pb-3 pr-4 font-medium">示例</th>
                <th class="pb-3 pr-4 font-medium">规则</th>
                <th class="pb-3 font-medium">要求</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in injectionShiftReportImportMappingRows"
                :key="`${row.sourceColumn}-${row.targetField}`"
                class="border-b border-slate-100 align-top last:border-b-0"
              >
                <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.sourceColumn }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.targetField }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.sample }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.rule }}</td>
                <td class="py-4">
                  <StatusPill :label="row.required ? '必填' : '选填'" :tone="row.tone" compact />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionPanel>
    </template>

    <template v-else-if="props.activeSection === 'inbound-orders'">
      <div class="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <SectionPanel
          title="入库单"
          subtitle="入库页只做送货单、PMC 和状态闭环，不和日报、排机混在一起。"
        >
          <div class="overflow-x-auto">
            <table class="min-w-full text-left text-sm">
              <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
                <tr>
                  <th class="pb-3 pr-4 font-medium">送货单</th>
                  <th class="pb-3 pr-4 font-medium">单号</th>
                  <th class="pb-3 pr-4 font-medium">啤数</th>
                  <th class="pb-3 pr-4 font-medium">用料 KG</th>
                  <th class="pb-3 pr-4 font-medium">PMC</th>
                  <th class="pb-3 font-medium">状态</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in injectionWarehouseInboundRows"
                  :key="row.deliveryCode"
                  class="border-b border-slate-100 last:border-b-0"
                >
                  <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.deliveryCode }}</td>
                  <td class="py-4 pr-4 text-slate-600">{{ row.orderNo }}</td>
                  <td class="py-4 pr-4 text-slate-600">{{ row.shots }}</td>
                  <td class="py-4 pr-4 text-slate-600">{{ row.materialKg }}</td>
                  <td class="py-4 pr-4 text-slate-600">{{ row.pmc }}</td>
                  <td class="py-4">
                    <StatusPill :label="row.status" :tone="row.tone" compact />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </SectionPanel>

        <SectionPanel
          title="联动规则"
          subtitle="先把送货单入库后的状态机定清楚，后面接 ERP 或仓库表时就不会反复改逻辑。"
        >
          <div class="space-y-4">
            <article
              v-for="card in injectionWritebackRuleCards"
              :key="card.title"
              class="rounded-2xl border border-slate-200 bg-white p-5"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <h3 class="font-semibold text-slate-950">{{ card.title }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ card.owner }} · {{ card.trigger }}</p>
                </div>
                <StatusPill :label="card.status" :tone="card.tone" compact />
              </div>
              <p class="mt-4 text-sm leading-6 text-slate-600">{{ card.summary }}</p>
              <div class="mt-4 flex flex-wrap gap-2">
                <span
                  v-for="item in card.items"
                  :key="`${card.title}-${item}`"
                  class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600"
                >
                  {{ item }}
                </span>
              </div>
            </article>
          </div>
        </SectionPanel>
      </div>

      <SectionPanel
        title="入库回写"
        subtitle="真正影响第二天待排池刷新的，就是这张回写状态。"
      >
        <div class="grid gap-4 xl:grid-cols-2">
          <article
            v-for="row in injectionInboundWritebackRows"
            :key="`${row.deliveryCode}-${row.orderNo}`"
            class="rounded-2xl border border-slate-200 bg-white p-5"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <h3 class="font-semibold text-slate-950">{{ row.deliveryCode }} · {{ row.orderNo }}</h3>
                <p class="mt-1 text-xs text-slate-500">{{ row.owner }}</p>
              </div>
              <StatusPill :label="row.schedulerStatus" :tone="row.tone" compact />
            </div>
            <div class="mt-4 grid gap-3 sm:grid-cols-2">
              <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">入库数量：{{ row.inboundQty }}</div>
              <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">回写后欠数：{{ row.shortageAfter }}</div>
            </div>
            <div class="mt-4 flex flex-wrap gap-2">
              <span class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">仓库：{{ row.warehouseStatus }}</span>
              <span class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">ERP：{{ row.erpStatus }}</span>
              <span class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">排产池：{{ row.schedulerStatus }}</span>
            </div>
          </article>
        </div>
      </SectionPanel>

      <SectionPanel
        title="主键映射"
        subtitle="把日报、送货单、排产池之间怎么命中同一条业务记录说清楚，后面接接口时最不容易返工。"
      >
        <div class="overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
              <tr>
                <th class="pb-3 pr-4 font-medium">阶段</th>
                <th class="pb-3 pr-4 font-medium">业务主键</th>
                <th class="pb-3 pr-4 font-medium">来源主键</th>
                <th class="pb-3 pr-4 font-medium">目标记录</th>
                <th class="pb-3 pr-4 font-medium">阻塞</th>
                <th class="pb-3 font-medium">状态</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in injectionWritebackKeyMatchRows"
                :key="`${row.stage}-${row.sourceKey}`"
                class="border-b border-slate-100 align-top last:border-b-0"
              >
                <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.stage }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.businessKey }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.sourceKey }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.targetRecord }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.blocker }}</td>
                <td class="py-4">
                  <StatusPill :label="row.status" :tone="row.tone" compact />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionPanel>
    </template>

    <template v-else>
      <div class="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <SectionPanel
          title="数据底座"
          subtitle="基础资料页统一放机台、模具和历史数据，不再拆成很多菜单。"
        >
          <div class="space-y-3">
            <article
              v-for="dataset in injectionDataCenterDatasets"
              :key="dataset.name"
              class="rounded-2xl border border-slate-200 bg-white p-5"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <h3 class="font-semibold text-slate-950">{{ dataset.name }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ dataset.owner }} · {{ dataset.freshness }}</p>
                </div>
                <StatusPill :label="dataset.status" :tone="dataset.statusTone" compact />
              </div>
              <div class="mt-4">
                <ProgressMeter :value="dataset.completeness" :tone="dataset.statusTone" label="完整度" />
              </div>
              <p class="mt-4 text-sm leading-6 text-slate-600">{{ dataset.summary }}</p>
            </article>
          </div>
        </SectionPanel>

        <SectionPanel
          title="数据源状态"
          subtitle="主管和计划只需要在这一页知道哪些资料还不完整。"
        >
          <div class="space-y-3">
            <article
              v-for="source in injectionDataSourceStatus"
              :key="source.name"
              class="rounded-2xl border border-slate-200 bg-white p-5"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <h3 class="font-semibold text-slate-950">{{ source.name }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ source.freshness }}</p>
                </div>
                <StatusPill :label="source.status" :tone="source.statusTone" compact />
              </div>
              <p class="mt-4 text-sm leading-6 text-slate-600">{{ source.summary }}</p>
            </article>
          </div>
        </SectionPanel>
      </div>

      <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <article
          v-for="mold in injectionMoldTargetRows"
          :key="mold.moldCode"
          class="rounded-2xl border border-slate-200 bg-white p-5"
        >
          <div class="flex items-start justify-between gap-3">
            <div>
              <h3 class="font-semibold text-slate-950">{{ mold.moldCode }}</h3>
              <p class="mt-1 text-xs text-slate-500">{{ mold.source }}</p>
            </div>
            <StatusPill :label="mold.health" :tone="mold.tone" compact />
          </div>
          <div class="mt-4 grid gap-3">
            <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">24H：{{ mold.target24h }}</div>
            <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">11H：{{ mold.target11h }}</div>
          </div>
        </article>
      </section>

      <div class="grid gap-6 xl:grid-cols-[1.08fr_0.92fr]">
        <SectionPanel
          title="机台档案"
          subtitle="机台台账保留在基础资料页里，现场查资料更顺。"
        >
          <div class="overflow-x-auto">
            <table class="min-w-full text-left text-sm">
              <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
                <tr>
                  <th class="pb-3 pr-4 font-medium">机台</th>
                  <th class="pb-3 pr-4 font-medium">吨位 / 螺杆</th>
                  <th class="pb-3 pr-4 font-medium">机械手 / 车间</th>
                  <th class="pb-3 pr-4 font-medium">工艺范围</th>
                  <th class="pb-3 pr-4 font-medium">颜色策略</th>
                  <th class="pb-3 pr-4 font-medium">保养</th>
                  <th class="pb-3 font-medium">状态</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="machine in compactMachineRows"
                  :key="machine.machine"
                  class="border-b border-slate-100 last:border-b-0"
                >
                  <td class="py-4 pr-4 font-semibold text-slate-950">{{ machine.machine }}</td>
                  <td class="py-4 pr-4 text-slate-600">
                    <div>{{ machine.tonnage }}</div>
                    <div class="mt-1 text-xs text-slate-500">{{ machine.screw }}</div>
                  </td>
                  <td class="py-4 pr-4 text-slate-600">
                    <div>{{ machine.robot }}</div>
                    <div class="mt-1 text-xs text-slate-500">{{ machine.workshop }}</div>
                  </td>
                  <td class="py-4 pr-4 text-slate-600">{{ machine.processRange }}</td>
                  <td class="py-4 pr-4 text-slate-600">{{ machine.colorPolicy }}</td>
                  <td class="py-4 pr-4 text-slate-600">{{ machine.maintenance }}</td>
                  <td class="py-4">
                    <StatusPill :label="machine.status" :tone="machine.tone" compact />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </SectionPanel>

        <SectionPanel
          title="模具目标台账"
          subtitle="模具目标页只保留目标、节拍、优选机台和健康度这些关键管理字段。"
        >
          <div class="overflow-x-auto">
            <table class="min-w-full text-left text-sm">
              <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
                <tr>
                  <th class="pb-3 pr-4 font-medium">模具</th>
                  <th class="pb-3 pr-4 font-medium">客户 / 产品</th>
                  <th class="pb-3 pr-4 font-medium">穴数 / 节拍</th>
                  <th class="pb-3 pr-4 font-medium">24H / 11H</th>
                  <th class="pb-3 pr-4 font-medium">优选机台</th>
                  <th class="pb-3 font-medium">健康度</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="mold in compactMoldRows"
                  :key="`${mold.moldCode}-${mold.productName}`"
                  class="border-b border-slate-100 last:border-b-0"
                >
                  <td class="py-4 pr-4 font-semibold text-slate-950">{{ mold.moldCode }}</td>
                  <td class="py-4 pr-4 text-slate-600">
                    <div>{{ mold.customer }}</div>
                    <div class="mt-1 text-xs text-slate-500">{{ mold.productName }}</div>
                  </td>
                  <td class="py-4 pr-4 text-slate-600">
                    <div>{{ mold.cavity }}</div>
                    <div class="mt-1 text-xs text-slate-500">{{ mold.cycleTime }}</div>
                  </td>
                  <td class="py-4 pr-4 text-slate-600">
                    <div>{{ mold.target24h }}</div>
                    <div class="mt-1 text-xs text-slate-500">{{ mold.target11h }}</div>
                  </td>
                  <td class="py-4 pr-4 text-slate-600">{{ mold.preferredMachine }}</td>
                  <td class="py-4">
                    <StatusPill :label="mold.health" :tone="mold.tone" compact />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </SectionPanel>

      </div>

      <div class="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
        <SectionPanel
          title="机台卡片"
          subtitle="保留少量卡片方便扫一眼状态，但不再单独占一个菜单。"
        >
          <div class="space-y-3">
            <article
              v-for="machine in compactMachineProfiles"
              :key="machine.machine"
              class="rounded-2xl border border-slate-200 bg-white p-4"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="flex items-center gap-3">
                  <span class="flex size-10 items-center justify-center rounded-2xl bg-slate-100 text-slate-700">
                    <Factory class="size-4" aria-hidden="true" />
                  </span>
                  <div>
                    <h3 class="font-semibold text-slate-950">{{ machine.machine }}</h3>
                    <p class="mt-1 text-xs text-slate-500">{{ machine.tonnage }} · {{ machine.armType }} · {{ machine.workshop }}</p>
                  </div>
                </div>
                <StatusPill :label="machine.status" :tone="machine.tone" compact />
              </div>
              <p class="mt-4 text-sm leading-6 text-slate-600">{{ machine.fit }}</p>
            </article>
          </div>
        </SectionPanel>

        <SectionPanel
          title="模具映射与规则"
          subtitle="映射和规则留在基础资料页里集中维护，但只保留最必要的信息。"
        >
          <div class="grid gap-4 lg:grid-cols-[1.05fr_0.95fr]">
            <div class="space-y-3">
              <article
                v-for="row in compactMappingRows"
                :key="`${row.moldCode}-${row.recommendedMachine}`"
                class="rounded-2xl border border-slate-200 bg-white p-4"
              >
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <h3 class="font-semibold text-slate-950">{{ row.moldCode }}</h3>
                    <p class="mt-1 text-xs text-slate-500">{{ row.customer }} · {{ row.productName }}</p>
                  </div>
                  <StatusPill :label="row.status" :tone="row.tone" compact />
                </div>
                <div class="mt-4 grid gap-3">
                  <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">候选池：{{ row.candidatePool }}</div>
                  <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">主机台：{{ row.recommendedMachine }}</div>
                  <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">备选：{{ row.backupMachine }}</div>
                </div>
              </article>
            </div>

            <div class="space-y-3">
              <article
                v-for="card in injectionConfigRuleCards"
                :key="card.title"
                class="rounded-2xl border border-slate-200 bg-white p-5"
              >
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <h3 class="font-semibold text-slate-950">{{ card.title }}</h3>
                    <p class="mt-1 text-xs text-slate-500">{{ card.owner }}</p>
                  </div>
                  <StatusPill :label="card.status" :tone="card.tone" compact />
                </div>
                <p class="mt-4 text-sm leading-6 text-slate-600">{{ card.summary }}</p>
              </article>
            </div>
          </div>
        </SectionPanel>
      </div>
    </template>
  </div>
</template>

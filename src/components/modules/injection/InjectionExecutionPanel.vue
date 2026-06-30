<script setup lang="ts">
import { ArrowRight, PlayCircle, RefreshCw, ShieldAlert } from '@lucide/vue'
import ProgressMeter from '@/components/common/ProgressMeter.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import {
  injectionColorTransitionRisks,
  injectionExecutionConstraintRows,
  injectionExecutionQueueRows,
  injectionExecutionRuleMetrics,
  injectionMachineLoad,
  injectionManualActionRows,
  injectionWorkflowStages,
} from '@/data/injectionSchedulingMock'

const workflowTone = {
  done: 'green',
  active: 'blue',
  pending: 'slate',
} as const

const toneSurfaceClasses = {
  green: 'bg-emerald-50 border-emerald-100',
  blue: 'bg-blue-50 border-blue-100',
  amber: 'bg-amber-50 border-amber-100',
  red: 'bg-red-50 border-red-100',
  teal: 'bg-teal-50 border-teal-100',
  slate: 'bg-slate-100 border-slate-200',
} as const
</script>

<template>
  <div class="space-y-6">
    <SectionPanel
      title="排机执行链"
      subtitle="这块不再只是概念卡片，而是直接模拟真实排机员的工作顺序"
    >
      <div class="grid gap-4 xl:grid-cols-5">
        <article
          v-for="(stage, index) in injectionWorkflowStages"
          :key="stage.title"
          class="rounded-2xl border border-slate-200 bg-white p-4"
        >
          <div class="flex items-center justify-between gap-3">
            <StatusPill
              :label="stage.state === 'done' ? '已完成' : stage.state === 'active' ? '进行中' : '待进入'"
              :tone="workflowTone[stage.state]"
              compact
            />
            <ArrowRight v-if="index < injectionWorkflowStages.length - 1" class="size-4 text-slate-300" aria-hidden="true" />
          </div>
          <h3 class="mt-4 text-lg font-semibold text-slate-950">{{ stage.title }}</h3>
          <p class="mt-2 text-xs text-slate-500">{{ stage.owner }}</p>
          <p class="mt-4 text-sm leading-6 text-slate-600">{{ stage.detail }}</p>
        </article>
      </div>
    </SectionPanel>

    <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <article
        v-for="metric in injectionExecutionRuleMetrics"
        :key="metric.label"
        class="rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.03)]"
      >
        <p class="text-sm text-slate-500">{{ metric.label }}</p>
        <p class="mt-4 text-3xl font-semibold tracking-tight text-slate-950">{{ metric.value }}</p>
        <p class="mt-3 text-xs leading-5 text-slate-500">{{ metric.detail }}</p>
      </article>
    </section>

    <div class="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
      <SectionPanel
        title="待排与结果候选池"
        subtitle="把当前要排的订单、落在哪台机、缺什么条件全部放到同一张执行表里"
      >
        <div class="mb-4 rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-4 py-3 text-sm text-slate-600">
          这一屏现在已经接入真实设备台账约束。当前候选结果仍是演示订单，但机台选择条件已经开始参考真实
          `五轴双臂 / PC / PVC / 新购 / 注意机台` 分层。
        </div>
        <div class="overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
              <tr>
                <th class="pb-3 pr-4 font-medium">机台</th>
                <th class="pb-3 pr-4 font-medium">单号</th>
                <th class="pb-3 pr-4 font-medium">模具</th>
                <th class="pb-3 pr-4 font-medium">颜色</th>
                <th class="pb-3 pr-4 font-medium">24H 目标</th>
                <th class="pb-3 pr-4 font-medium">欠数</th>
                <th class="pb-3 font-medium">优先级</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in injectionExecutionQueueRows"
                :key="`${row.machine}-${row.orderNo}`"
                class="border-b border-slate-100 align-top last:border-b-0"
              >
                <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.machine }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.orderNo }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.moldName }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.color }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.target24h }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.shortage }}</td>
                <td class="py-4">
                  <StatusPill :label="row.priority" :tone="row.tone" compact />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionPanel>

      <SectionPanel
        title="机台拦截与候选限制"
        subtitle="这些不是排机后才发现的问题，而是候选机台阶段就该拦下来的真实设备约束"
      >
        <div class="space-y-4">
          <article
            v-for="item in injectionExecutionConstraintRows"
            :key="item.machine"
            class="rounded-2xl border p-4"
            :class="toneSurfaceClasses[item.tone]"
          >
            <div class="flex items-start justify-between gap-4">
              <div class="min-w-0">
                <div class="flex items-center gap-3">
                  <span class="flex size-10 items-center justify-center rounded-2xl bg-white text-slate-700">
                    <ShieldAlert class="size-4" aria-hidden="true" />
                  </span>
                  <div>
                    <h3 class="font-semibold text-slate-950">{{ item.machine }}</h3>
                    <p class="mt-1 text-xs text-slate-500">
                      {{ item.workshop }} · {{ item.tonnage }} · {{ item.robot }}
                    </p>
                  </div>
                </div>
                <p class="mt-4 text-sm leading-6 text-slate-700">{{ item.limit }}</p>
                <p class="mt-2 text-xs leading-5 text-slate-500">{{ item.action }}</p>
              </div>
              <StatusPill :label="item.tone === 'red' ? '硬拦截' : item.tone === 'amber' ? '需确认' : '可候选'" :tone="item.tone" compact />
            </div>
          </article>
        </div>
      </SectionPanel>
    </div>

    <div class="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
      <SectionPanel
        title="机台即时负载"
        subtitle="这块是未来拖拽排机和时间轴的前置版本，先让机台状态有清晰层次"
      >
        <div class="grid gap-4 md:grid-cols-2">
          <article
            v-for="machine in injectionMachineLoad"
            :key="machine.machine"
            class="rounded-2xl border border-slate-200 bg-white p-4"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <h3 class="text-lg font-semibold text-slate-950">{{ machine.machine }}</h3>
                <p class="mt-1 text-xs text-slate-500">{{ machine.mold }}</p>
              </div>
              <StatusPill :label="machine.queueDepth" :tone="machine.tone" />
            </div>
            <div class="mt-4">
              <ProgressMeter :value="machine.utilization" :tone="machine.tone" label="机台负载" />
            </div>
            <p class="mt-4 text-sm text-slate-600">{{ machine.material }}</p>
          </article>
        </div>
      </SectionPanel>

      <SectionPanel
        title="人工微调与执行动作"
        subtitle="系统先给候选结果，计划员和生产主管在这里处理真实冲突"
      >
        <div class="grid gap-4 md:grid-cols-2">
          <article class="rounded-2xl border border-slate-200 bg-[linear-gradient(180deg,rgba(15,23,42,0.98),rgba(30,41,59,0.98))] p-5 text-white">
            <div class="flex items-center gap-3">
              <span class="flex size-11 items-center justify-center rounded-2xl bg-white/10">
                <PlayCircle class="size-5" aria-hidden="true" />
              </span>
              <div>
                <h3 class="font-semibold">执行智能排机</h3>
                <p class="mt-1 text-xs text-slate-300">先跑结转优先、同套模、颜色顺序和机台适配，再给人工看候选结果</p>
              </div>
            </div>
            <div class="mt-5 space-y-3 text-sm text-slate-200">
              <div class="rounded-xl bg-white/5 px-4 py-3">勾选订单池与结转单</div>
              <div class="rounded-xl bg-white/5 px-4 py-3">读取机台限制与例外规则</div>
              <div class="rounded-xl bg-white/5 px-4 py-3">生成候选排机结果</div>
            </div>
          </article>

          <article class="rounded-2xl border border-slate-200 bg-white p-5">
            <div class="flex items-center gap-3">
              <span class="flex size-11 items-center justify-center rounded-2xl bg-amber-50 text-amber-700">
                <RefreshCw class="size-5" aria-hidden="true" />
              </span>
              <div>
                <h3 class="font-semibold text-slate-950">人工微调</h3>
                <p class="mt-1 text-xs text-slate-500">处理颜色逆序、目标缺失、特殊料型和注意机台冲突</p>
              </div>
            </div>
            <div class="mt-5 space-y-3 text-sm text-slate-700">
              <div class="rounded-xl bg-slate-50 px-4 py-3">换台</div>
              <div class="rounded-xl bg-slate-50 px-4 py-3">调顺序</div>
              <div class="rounded-xl bg-slate-50 px-4 py-3">锁定结果并下发</div>
            </div>
          </article>
        </div>

        <div class="mt-4 space-y-3">
          <article
            v-for="item in injectionManualActionRows"
            :key="item.title"
            class="rounded-2xl border border-slate-200 bg-slate-50 p-4"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="flex items-center gap-3">
                <span class="flex size-10 items-center justify-center rounded-2xl bg-white text-slate-700">
                  <ShieldAlert class="size-4" aria-hidden="true" />
                </span>
                <div>
                  <h3 class="font-semibold text-slate-950">{{ item.title }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ item.owner }}</p>
                </div>
              </div>
              <StatusPill :label="item.action" :tone="item.tone" compact />
            </div>
            <p class="mt-4 text-sm leading-6 text-slate-600">{{ item.reason }}</p>
          </article>
        </div>
      </SectionPanel>
    </div>

    <SectionPanel
      title="颜色切换预警"
      subtitle="真实机台约束已经接入后，颜色链就不再只是美观问题，而是直接影响换色风险和人工微调成本"
    >
      <div class="grid gap-4 lg:grid-cols-2">
        <article
          v-for="risk in injectionColorTransitionRisks"
          :key="risk.machine"
          class="rounded-2xl border border-slate-200 bg-white px-5 py-4"
        >
          <div class="flex items-center justify-between gap-3">
            <div>
              <p class="font-medium text-slate-900">{{ risk.machine }}</p>
              <p class="mt-1 text-xs text-slate-500">{{ risk.route.join(' → ') }}</p>
            </div>
            <StatusPill :label="risk.risk" :tone="risk.tone" compact />
          </div>
        </article>
      </div>
    </SectionPanel>
  </div>
</template>

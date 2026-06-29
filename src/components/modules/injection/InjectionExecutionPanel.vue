<script setup lang="ts">
import { ArrowRight, PlayCircle, RefreshCw, ShieldAlert } from '@lucide/vue'
import ProgressMeter from '@/components/common/ProgressMeter.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import {
  injectionColorTransitionRisks,
  injectionExecutionQueueRows,
  injectionMachineLoad,
  injectionManualActionRows,
  injectionWorkflowStages,
} from '@/data/injectionSchedulingMock'

const workflowTone = {
  done: 'green',
  active: 'blue',
  pending: 'slate',
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

    <div class="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
      <SectionPanel
        title="待排与结果候选池"
        subtitle="把当前要排的订单、落在哪台机、缺什么条件全部放到同一张执行表里"
      >
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
        title="人工干预清单"
        subtitle="这里就是计划员和生产主管真正会盯的一屏"
      >
        <div class="space-y-4">
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
        title="执行动作入口"
        subtitle="先把核心动作做成两个大入口，后续再接按钮行为和弹窗"
      >
        <div class="grid gap-4 md:grid-cols-2">
          <article class="rounded-2xl border border-slate-200 bg-[linear-gradient(180deg,rgba(15,23,42,0.98),rgba(30,41,59,0.98))] p-5 text-white">
            <div class="flex items-center gap-3">
              <span class="flex size-11 items-center justify-center rounded-2xl bg-white/10">
                <PlayCircle class="size-5" aria-hidden="true" />
              </span>
              <div>
                <h3 class="font-semibold">执行智能排机</h3>
                <p class="mt-1 text-xs text-slate-300">根据同模、颜色、结转和机台适配自动出结果</p>
              </div>
            </div>
            <div class="mt-5 space-y-3 text-sm text-slate-200">
              <div class="rounded-xl bg-white/5 px-4 py-3">勾选订单池与结转单</div>
              <div class="rounded-xl bg-white/5 px-4 py-3">锁定重点插单与限制条件</div>
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
                <p class="mt-1 text-xs text-slate-500">处理颜色逆序、目标缺失和重点插单冲突</p>
              </div>
            </div>
            <div class="mt-5 space-y-3 text-sm text-slate-700">
              <div class="rounded-xl bg-slate-50 px-4 py-3">换台</div>
              <div class="rounded-xl bg-slate-50 px-4 py-3">调顺序</div>
              <div class="rounded-xl bg-slate-50 px-4 py-3">锁定结果并下发</div>
            </div>
          </article>
        </div>

        <div class="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <h3 class="font-semibold text-slate-950">颜色切换预警</h3>
          <div class="mt-4 space-y-3">
            <article
              v-for="risk in injectionColorTransitionRisks"
              :key="risk.machine"
              class="rounded-xl border border-slate-200 bg-white px-4 py-3"
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
        </div>
      </SectionPanel>
    </div>
  </div>
</template>

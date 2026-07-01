<script setup lang="ts">
import { AlertTriangle, Database, PlayCircle, RefreshCw } from '@lucide/vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import ProgressMeter from '@/components/common/ProgressMeter.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import type { Tone } from '@/data/enterpriseMock'
import { useInjectionModuleData } from '@/factories/injection/useInjectionModuleData'

const toneTextClasses: Record<Tone, string> = {
  teal: 'text-teal-700',
  blue: 'text-blue-700',
  amber: 'text-amber-700',
  red: 'text-red-700',
  slate: 'text-slate-700',
  green: 'text-emerald-700',
}

const toneSurfaceClasses: Record<Tone, string> = {
  teal: 'bg-teal-50 border-teal-100',
  blue: 'bg-blue-50 border-blue-100',
  amber: 'bg-amber-50 border-amber-100',
  red: 'bg-red-50 border-red-100',
  slate: 'bg-slate-100 border-slate-200',
  green: 'bg-emerald-50 border-emerald-100',
}

const workflowTone = {
  done: 'green',
  active: 'blue',
  pending: 'slate',
} as const

const {
  injectionColorTransitionRisks,
  injectionDataSourceStatus,
  injectionExecutionTasks,
  injectionMachineLoad,
  injectionOverviewMetrics,
  injectionShiftSummaries,
  injectionWorkflowStages,
} = useInjectionModuleData()
</script>

<template>
  <div class="space-y-6">
    <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <article
        v-for="metric in injectionOverviewMetrics"
        :key="metric.label"
        class="rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.03)]"
      >
        <p class="text-sm text-slate-500">{{ metric.label }}</p>
        <div class="mt-4 flex items-end justify-between gap-4">
          <p class="text-4xl font-semibold tracking-tight text-slate-950">{{ metric.value }}</p>
          <span
            class="rounded-full px-2.5 py-1 text-xs font-semibold"
            :class="[toneSurfaceClasses[metric.tone], toneTextClasses[metric.tone]]"
          >
            {{ metric.detail.split('·')[0] }}
          </span>
        </div>
        <p class="mt-3 text-xs leading-5 text-slate-500">{{ metric.detail }}</p>
      </article>
    </section>

    <div class="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
      <SectionPanel
        title="班次驾驶舱"
        subtitle="先看白班 / 夜班的达成、结转和异常，再决定是否进入排机执行"
      >
        <div class="grid gap-4 lg:grid-cols-2">
          <article
            v-for="shift in injectionShiftSummaries"
            :key="shift.shift"
            class="rounded-2xl border border-slate-200 bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(248,250,252,0.98))] p-5"
          >
            <div class="flex items-start justify-between gap-4">
              <div>
                <p class="text-xs uppercase tracking-[0.24em] text-slate-500">{{ shift.date }}</p>
                <h3 class="mt-2 text-xl font-semibold text-slate-950">{{ shift.shift }}</h3>
              </div>
              <StatusPill :label="`${shift.completion}% 达成`" :tone="shift.completion >= 75 ? 'green' : 'amber'" />
            </div>

            <div class="mt-5">
              <ProgressMeter :value="shift.completion" :tone="shift.completion >= 75 ? 'green' : 'amber'" label="班次完成度" />
            </div>

            <div class="mt-5 grid gap-3 sm:grid-cols-2">
              <div class="rounded-xl bg-slate-50 px-4 py-3">
                <p class="text-xs uppercase tracking-[0.22em] text-slate-500">机台运行</p>
                <p class="mt-2 text-sm font-semibold text-slate-900">{{ shift.machineRunning }}</p>
              </div>
              <div class="rounded-xl bg-slate-50 px-4 py-3">
                <p class="text-xs uppercase tracking-[0.22em] text-slate-500">结转延续</p>
                <p class="mt-2 text-sm font-semibold text-slate-900">{{ shift.carryOver }}</p>
              </div>
            </div>

            <div class="mt-4 rounded-xl border border-amber-100 bg-amber-50 px-4 py-3">
              <p class="text-xs uppercase tracking-[0.22em] text-amber-700">提示</p>
              <p class="mt-2 text-sm leading-6 text-amber-900">{{ shift.alert }}</p>
            </div>
          </article>
        </div>
      </SectionPanel>

      <SectionPanel
        title="执行链路"
        subtitle="把订单入池到回报闭环拆成清晰阶段，方便继续接真实执行动作"
      >
        <div class="space-y-4">
          <article
            v-for="stage in injectionWorkflowStages"
            :key="stage.title"
            class="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <h3 class="font-semibold text-slate-950">{{ stage.title }}</h3>
                <p class="mt-1 text-xs text-slate-500">{{ stage.owner }}</p>
              </div>
              <StatusPill
                :label="stage.state === 'done' ? '已完成' : stage.state === 'active' ? '进行中' : '待进入'"
                :tone="workflowTone[stage.state]"
              />
            </div>
            <p class="mt-3 text-sm leading-6 text-slate-600">{{ stage.detail }}</p>
          </article>
        </div>
      </SectionPanel>
    </div>

    <div class="grid gap-6 xl:grid-cols-[1fr_1fr]">
      <SectionPanel
        title="机台负载热力"
        subtitle="用排队深度和机台负载先承接真实排产视角，后续可替换成甘特与拖拽排机"
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

            <div class="mt-4 rounded-xl bg-slate-50 px-4 py-3">
              <p class="text-xs uppercase tracking-[0.22em] text-slate-500">当前料型</p>
              <p class="mt-2 text-sm font-medium text-slate-900">{{ machine.material }}</p>
            </div>
          </article>
        </div>
      </SectionPanel>

      <SectionPanel
        title="颜色切换风险链"
        subtitle="把颜色顺序单独可视化，直接体现为什么排产不能只看待排数量"
      >
        <div class="space-y-4">
          <article
            v-for="risk in injectionColorTransitionRisks"
            :key="risk.machine"
            class="rounded-2xl border border-slate-200 bg-white p-4"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <h3 class="text-lg font-semibold text-slate-950">{{ risk.machine }}</h3>
                <p class="mt-1 text-xs text-slate-500">颜色顺序链</p>
              </div>
              <StatusPill :label="risk.risk" :tone="risk.tone" />
            </div>

            <div class="mt-4 flex flex-wrap items-center gap-2">
              <template v-for="(color, index) in risk.route" :key="`${risk.machine}-${color}-${index}`">
                <span class="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-700">{{ color }}</span>
                <span v-if="index < risk.route.length - 1" class="text-slate-300">→</span>
              </template>
            </div>
          </article>
        </div>
      </SectionPanel>
    </div>

    <div class="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
      <SectionPanel
        title="数据中心健康"
        subtitle="订单、机台、模具目标、历史数据库四类数据决定排产是否能越排越准"
      >
        <div class="space-y-4">
          <article
            v-for="source in injectionDataSourceStatus"
            :key="source.name"
            class="rounded-2xl border border-slate-200 bg-white p-4"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <h3 class="text-lg font-semibold text-slate-950">{{ source.name }}</h3>
                <p class="mt-1 text-xs text-slate-500">{{ source.freshness }}</p>
              </div>
              <StatusPill :label="source.status" :tone="source.statusTone" />
            </div>
            <p class="mt-4 text-sm leading-6 text-slate-600">{{ source.summary }}</p>
          </article>
        </div>
      </SectionPanel>

      <SectionPanel
        title="执行与人工干预队列"
        subtitle="这些是第一批最值得落到真实交互里的操作区"
      >
        <div class="grid gap-4 md:grid-cols-2">
          <article class="rounded-2xl border border-slate-200 bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(248,250,252,0.98))] p-5">
            <div class="flex items-center gap-3">
              <span class="flex size-11 items-center justify-center rounded-2xl bg-slate-950 text-white">
                <PlayCircle class="size-5" aria-hidden="true" />
              </span>
              <div>
                <h3 class="font-semibold text-slate-950">排机执行入口</h3>
                <p class="mt-1 text-xs text-slate-500">建议下一步接真实订单池、结转预览和排机按钮</p>
              </div>
            </div>
            <div class="mt-5 space-y-3">
              <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">1. 选待排订单</div>
              <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">2. 查看结转优先级</div>
              <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">3. 执行智能排机</div>
              <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">4. 进入人工微调</div>
            </div>
          </article>

          <article class="rounded-2xl border border-slate-200 bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(248,250,252,0.98))] p-5">
            <div class="flex items-center gap-3">
              <span class="flex size-11 items-center justify-center rounded-2xl bg-amber-100 text-amber-800">
                <RefreshCw class="size-5" aria-hidden="true" />
              </span>
              <div>
                <h3 class="font-semibold text-slate-950">人工干预池</h3>
                <p class="mt-1 text-xs text-slate-500">保留计划员和生产主管最常处理的异常事项</p>
              </div>
            </div>
            <div class="mt-5 space-y-3">
              <article
                v-for="task in injectionExecutionTasks"
                :key="task.title"
                class="rounded-xl border px-4 py-3"
                :class="toneSurfaceClasses[task.tone]"
              >
                <div class="flex items-start gap-3">
                  <AlertTriangle class="mt-0.5 size-4 shrink-0" :class="toneTextClasses[task.tone]" aria-hidden="true" />
                  <div>
                    <h4 class="text-sm font-semibold text-slate-900">{{ task.title }}</h4>
                    <p class="mt-1 text-xs leading-5 text-slate-600">{{ task.meta }}</p>
                  </div>
                </div>
              </article>
            </div>
          </article>
        </div>

        <div class="mt-4 rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-5 py-4">
          <div class="flex items-center gap-3">
            <Database class="size-5 text-slate-500" aria-hidden="true" />
            <p class="text-sm text-slate-600">
              这一页现在已经具备驾驶舱骨架。下一步最适合接入的是真实“待排订单、结转项、机台负载、模具目标缺失、颜色切换风险”数据。
            </p>
          </div>
        </div>
      </SectionPanel>
    </div>
  </div>
</template>

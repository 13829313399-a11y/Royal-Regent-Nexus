<script setup lang="ts">
import type { AIBusinessResult, AISourceSummary } from '@/features/ai-assistant/types'
import PreviewCard from '@/features/nexus-copilot/components/PreviewCard.vue'
import ResultFrame from '../ResultFrame.vue'

defineProps<{ result: AIBusinessResult; sources: AISourceSummary[] }>()

function numberOrDash(value: number | null | undefined) {
  return value === undefined || value === null ? '—' : String(value)
}

function percentageOrDash(value: number | null | undefined) {
  return value === undefined || value === null ? '—' : `${(value * 100).toFixed(1)}%`
}
</script>

<template>
  <ResultFrame :result="result">
    <div v-if="result.kind === 'plan_context' && result.planContext" class="mt-2 grid gap-2 sm:grid-cols-2">
      <section class="rounded-lg border border-emerald-200 bg-white p-2.5" data-plan-kind="published">
        <p class="text-[11px] font-bold text-emerald-700">当前执行 PUBLISHED</p>
        <template v-if="result.planContext.executionPublished">
          <p class="mt-1 text-[11px] text-slate-600">日期 {{ result.planContext.executionPublished.businessDate || '—' }} · 版本 {{ numberOrDash(result.planContext.executionPublished.revision) }}</p>
          <p class="mt-1 text-[11px] text-slate-600">任务 {{ numberOrDash(result.planContext.executionPublished.taskCount) }} · 运行中 {{ numberOrDash(result.planContext.executionPublished.runningCount) }}</p>
        </template>
        <p v-else class="mt-1 text-[11px] text-slate-500">当前没有已发布执行计划</p>
      </section>
      <section class="rounded-lg border border-amber-200 bg-white p-2.5" data-plan-kind="draft">
        <p class="text-[11px] font-bold text-amber-700">规划草案 DRAFT</p>
        <template v-if="result.planContext.planningDraft">
          <p class="mt-1 text-[11px] text-slate-600">日期 {{ result.planContext.planningDraft.businessDate || '—' }} · 版本 {{ numberOrDash(result.planContext.planningDraft.revision) }}</p>
          <p class="mt-1 text-[11px] text-slate-600">任务 {{ numberOrDash(result.planContext.planningDraft.taskCount) }}</p>
        </template>
        <p v-else class="mt-1 text-[11px] text-slate-500">当前没有规划草案</p>
      </section>
    </div>

    <dl v-if="result.kind === 'backlog' && result.backlog" class="mt-2 grid grid-cols-2 gap-2 rounded-lg border border-sky-200 bg-white p-2.5 text-[11px] sm:grid-cols-3">
      <div><dt class="text-slate-500">全部待排</dt><dd class="mt-0.5 font-bold text-slate-900">{{ numberOrDash(result.backlog.total) }}</dd></div>
      <div><dt class="text-slate-500">本次返回</dt><dd class="mt-0.5 font-bold text-slate-900">{{ numberOrDash(result.backlog.returned) }}</dd></div>
      <div class="col-span-2 sm:col-span-1"><dt class="text-slate-500">数据范围</dt><dd class="mt-0.5 break-words font-semibold text-slate-700">{{ result.backlog.sourceBusinessLabel || result.backlog.sourceScope || '当前已验证厂区' }}</dd></div>
    </dl>

    <section
      v-if="(result.kind === 'scheduling_preview' || result.kind === 'scheduling_comparison') && result.schedulingPreviews"
      class="mt-2 space-y-2"
      data-ai-scheduling-preview
    >
      <p class="rounded-lg border border-amber-300 bg-amber-50 px-2.5 py-2 text-[11px] font-bold text-amber-900">{{ result.schedulingPreviews.candidateLabel }}</p>
      <p v-if="result.schedulingPreviews.comparableSnapshot === false" class="rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-2 text-[11px] font-medium text-rose-800">{{ result.schedulingPreviews.comparisonWarning }}</p>
      <ul class="space-y-2">
        <li v-for="run in result.schedulingPreviews.runs" :key="run.runId" class="rounded-lg border border-sky-200 bg-white p-2.5">
          <div class="flex flex-wrap items-start justify-between gap-2">
            <div class="min-w-0">
              <p class="break-words text-xs font-bold text-slate-900">{{ run.scenarioName }} · 方案 {{ run.alternativeNo }}</p>
              <p class="mt-0.5 break-words text-[10px] text-slate-500">候选编号 {{ run.runId }} · 草案版本 {{ run.planRevision }}</p>
            </div>
            <span class="rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-bold text-sky-800">{{ run.actualSolver }} / {{ run.solverStatus }}</span>
          </div>
          <dl class="mt-2 grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4">
            <div><dt class="text-slate-500">已安排</dt><dd class="font-bold text-slate-900">{{ numberOrDash(run.metrics.scheduledCount) }}</dd></div>
            <div><dt class="text-slate-500">需复核</dt><dd class="font-bold text-slate-900">{{ numberOrDash(run.metrics.reviewCount) }}</dd></div>
            <div><dt class="text-slate-500">未安排</dt><dd class="font-bold text-slate-900">{{ numberOrDash(run.metrics.unassignedCount) }}</dd></div>
            <div><dt class="text-slate-500">平均负载</dt><dd class="font-bold text-slate-900">{{ percentageOrDash(run.metrics.loadRatioAverage) }}</dd></div>
            <div><dt class="text-slate-500">逾期变化</dt><dd class="font-bold text-slate-900">{{ numberOrDash(run.metrics.overdue.change) }}</dd></div>
            <div><dt class="text-slate-500">换模变化</dt><dd class="font-bold text-slate-900">{{ numberOrDash(run.metrics.moldChanges.change) }}</dd></div>
            <div><dt class="text-slate-500">计划版本</dt><dd class="font-bold text-slate-900">{{ run.planRevision }}</dd></div>
            <div><dt class="text-slate-500">规则版本</dt><dd class="font-bold text-slate-900">{{ run.ruleRevision }}</dd></div>
          </dl>
          <PreviewCard v-if="run.previewManifest" :manifest="run.previewManifest" />
          <details class="mt-2 text-[10px] text-slate-500">
            <summary class="cursor-pointer font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600">求解技术详情</summary>
            <p class="mt-1 break-all">请求 {{ run.requestedSolver }} · 实际 {{ run.actualSolver }} · {{ run.fallbackUsed ? '已使用安全回退' : '未使用回退' }}</p>
          </details>
        </li>
      </ul>
      <p class="text-[10px] leading-4 text-slate-500">指标来自已持久化 PREVIEW 候选。请在正式排产页面选择；此处不会 Apply 或 Publish。</p>
    </section>
  </ResultFrame>
</template>

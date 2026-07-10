<script setup lang="ts">
import { Download } from '@lucide/vue'
import {
  overviewMetrics,
} from '@/data/enterpriseMock'
import CrossFactoryTimeline from '@/components/dashboard/CrossFactoryTimeline.vue'
import FactoryHeatmap from '@/components/dashboard/FactoryHeatmap.vue'
import MetricCard from '@/components/dashboard/MetricCard.vue'
import ModuleHealthPanel from '@/components/dashboard/ModuleHealthPanel.vue'
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
      <div>
        <h1 class="text-3xl font-semibold tracking-tight text-slate-950">集团运营总览</h1>
        <p class="mt-2 text-sm text-slate-600">
          6 个厂区 · 5 个核心部门 · 统一模块入口与跨厂区事项
        </p>
      </div>

      <div class="flex flex-wrap gap-3">
        <button type="button" class="h-9 rounded-lg border border-slate-200 bg-white px-6 text-sm text-slate-700">
          本周
        </button>
        <button type="button" class="inline-flex h-9 items-center gap-2 rounded-lg bg-slate-950 px-6 text-sm font-semibold text-white">
          <Download class="size-4" aria-hidden="true" />
          导出报表
        </button>
      </div>
    </div>

    <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <MetricCard v-for="metric in overviewMetrics" :key="metric.label" :metric="metric" />
    </div>

    <div class="grid gap-6 xl:grid-cols-[1fr_350px]">
      <FactoryHeatmap />
      <CrossFactoryTimeline />
    </div>

    <ModuleHealthPanel />
  </div>
</template>

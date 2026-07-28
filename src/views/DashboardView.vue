<script setup lang="ts">
import { CalendarDays, Download } from '@lucide/vue'
import {
  overviewMetrics,
} from '@/data/enterpriseMock'
import CrossFactoryTimeline from '@/components/dashboard/CrossFactoryTimeline.vue'
import FactoryHeatmap from '@/components/dashboard/FactoryHeatmap.vue'
import MetricCard from '@/components/dashboard/MetricCard.vue'
import ModuleHealthPanel from '@/components/dashboard/ModuleHealthPanel.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { Button } from '@/components/ui/button'
</script>

<template>
  <div class="app-page dashboard-page space-y-6">
    <PageHeader
      eyebrow="Group Operations"
      title="集团运营总览"
      description="6 个厂区 · 5 个核心部门 · 统一模块入口与跨厂区事项"
    >
      <template #actions>
        <Button type="button" variant="outline">
          <CalendarDays class="size-4" aria-hidden="true" />
          本周
        </Button>
        <Button type="button">
          <Download class="size-4" aria-hidden="true" />
          导出报表
        </Button>
      </template>
    </PageHeader>

    <div class="dashboard-metrics reveal-grid grid gap-4">
      <MetricCard v-for="metric in overviewMetrics" :key="metric.label" :metric="metric" />
    </div>

    <div class="dashboard-primary-grid grid gap-6">
      <FactoryHeatmap />
      <CrossFactoryTimeline />
    </div>

    <ModuleHealthPanel />
  </div>
</template>

<style scoped>
.dashboard-page {
  container: dashboard-page / inline-size;
}

.dashboard-metrics {
  grid-template-columns: minmax(0, 1fr);
}

@container dashboard-page (min-width: 36rem) {
  .dashboard-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@container dashboard-page (min-width: 62rem) {
  .dashboard-metrics {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

@container dashboard-page (min-width: 68rem) {
  .dashboard-primary-grid {
    grid-template-columns: minmax(0, 1fr) minmax(300px, 350px);
  }
}
</style>

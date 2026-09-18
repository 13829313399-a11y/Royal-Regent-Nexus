<script setup lang="ts">
import { computed } from 'vue'
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
import { useAppStore } from '@/stores/app'
import '@/components/dashboard/styles/dashboard.css'

const appStore = useAppStore()

const heroTitle = computed(() =>
  appStore.activeFactoryId === 'group'
    ? '集团运营总览'
    : `${appStore.activeFactory.name} · 运营总览`,
)

/**
 * 首页四组展示数据仍来自静态示例数组，“本周”与“导出报表”也尚未接入业务请求。
 * 这里是真实的可用状态，只保留位置、图标和文案，不做假的筛选或下载反馈。
 */
const filterAndExportUnavailable = true

/** 与原有描述共用同一说明区域：桌面同排，窄屏自然换行，不新增加一条警告 Banner。 */
const sourceNote = '示例数据 · 筛选与导出暂未接入'
</script>

<template>
  <div class="dashboard-page-container">
    <div class="app-page dashboard-page space-y-6" data-dashboard-ui="jade-v2">
    <div class="dashboard-hero">
      <div class="dashboard-hero__art" aria-hidden="true" />
      <span class="dashboard-hero__breath" aria-hidden="true" />

      <PageHeader
        class="dashboard-hero__header"
        eyebrow="Group Operations"
        :title="heroTitle"
        description="6 个厂区 · 5 个核心部门 · 统一模块入口与跨厂区事项"
      >
        <template #actions>
          <div class="dashboard-hero__actions flex flex-wrap items-center gap-2.5">
            <p class="dashboard-hero__note">{{ sourceNote }}</p>
            <Button
              type="button"
              variant="outline"
              :disabled="filterAndExportUnavailable"
            >
              <CalendarDays class="size-4" aria-hidden="true" />
              本周
            </Button>
            <Button type="button" :disabled="filterAndExportUnavailable">
              <Download class="size-4" aria-hidden="true" />
              导出报表
            </Button>
          </div>
        </template>
      </PageHeader>
    </div>

    <div class="dashboard-metrics grid gap-4">
      <MetricCard
        v-for="(metric, index) in overviewMetrics"
        :key="metric.label"
        :metric="metric"
        :index="index"
      />
    </div>

    <div class="dashboard-primary-grid grid gap-6">
      <FactoryHeatmap :active-factory-id="appStore.activeFactoryId" />
      <CrossFactoryTimeline />
    </div>

    <ModuleHealthPanel />
    </div>
  </div>
</template>

<style scoped>
/*
 * 容器查询的作用对象只能是后代，元素不能查询自己的容器。
 * 以前把 container 直接写在 .dashboard-page 上，所有 @container 规则都不会命中的。
 * 这里保留原有断点数值和选择器文本，只把容器移到外层承载节点。
 */
.dashboard-page-container {
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

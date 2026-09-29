<script setup lang="ts">
import { moduleHealth } from '@/data/enterpriseMock'
import ProgressMeter from '@/components/common/ProgressMeter.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
</script>

<template>
  <SectionPanel
    class="dashboard-section dashboard-section--modules"
    title="模块健康度"
    subtitle="模块健康度示例 · 保留现有五组目录读数"
  >
    <div class="dashboard-module-grid grid gap-x-10 gap-y-4 md:grid-cols-2 xl:grid-cols-3">
      <div
        v-for="module in moduleHealth"
        :key="module.name"
        class="dashboard-module-row"
        role="group"
        :aria-label="`${module.name} 示例健康度 ${module.value}%`"
      >
        <span class="dashboard-module-row__name">{{ module.name }}</span>
        <ProgressMeter :value="module.value" :tone="module.tone" />
        <span class="dashboard-module-row__value">{{ module.value }}</span>
      </div>
    </div>
  </SectionPanel>
</template>

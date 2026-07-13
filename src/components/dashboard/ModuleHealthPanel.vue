<script setup lang="ts">
import { moduleHealth } from '@/data/enterpriseMock'
import ProgressMeter from '@/components/common/ProgressMeter.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
</script>

<template>
  <SectionPanel
    title="模块健康度"
    subtitle="用于判断哪些部门模块优先建设、优先优化"
  >
    <div class="grid gap-x-10 gap-y-4 md:grid-cols-2 xl:grid-cols-3">
      <div v-for="module in moduleHealth" :key="module.name" class="grid grid-cols-[76px_1fr] items-center gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-slate-50/80">
        <span class="text-sm font-medium text-slate-700">{{ module.name }}</span>
        <ProgressMeter :value="module.value" :tone="module.tone" />
      </div>
    </div>
  </SectionPanel>
</template>

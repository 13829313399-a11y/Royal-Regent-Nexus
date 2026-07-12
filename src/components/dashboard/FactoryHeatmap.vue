<script setup lang="ts">
import { factoryHeatmap } from '@/data/enterpriseMock'
import ProgressMeter from '@/components/common/ProgressMeter.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
</script>

<template>
  <SectionPanel
    title="厂区运行热力图"
    subtitle="按厂区查看工程、PMC、生产、QA、业务的模块状态"
  >
    <div class="grid gap-5 md:grid-cols-2">
      <article
        v-for="factory in factoryHeatmap"
        :key="factory.factoryId"
        class="surface-subtle rounded-xl p-5"
      >
        <div class="mb-4 flex items-start justify-between gap-4">
          <div>
            <h3 class="font-semibold text-slate-950">{{ factory.name }}</h3>
            <p class="mt-1 text-xs text-slate-500">{{ factory.metrics }}</p>
          </div>
          <StatusPill :label="factory.status" :tone="factory.statusTone" compact />
        </div>
        <ProgressMeter :value="factory.score" :tone="factory.statusTone" />
        <p class="mt-4 text-xs leading-5 text-slate-600">{{ factory.summary }}</p>
      </article>
    </div>
  </SectionPanel>
</template>

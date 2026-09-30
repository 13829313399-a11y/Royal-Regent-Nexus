<script setup lang="ts">
import { crossFactoryItems } from '@/data/enterpriseMock'
import SectionPanel from '@/components/common/SectionPanel.vue'
</script>

<template>
  <SectionPanel
    class="dashboard-section dashboard-section--timeline"
    title="跨厂区事项"
    subtitle="跨厂区事项示例 · 按 SLA 排序"
  >
    <ol class="dashboard-timeline">
      <li
        v-for="item in crossFactoryItems"
        :key="item.title"
        class="dashboard-timeline-item"
        :data-tone="item.tone"
      >
        <span class="dashboard-timeline-item__rail" data-timeline-rail aria-hidden="true">
          <span class="dashboard-timeline-item__dot" />
        </span>
        <div class="dashboard-timeline-item__body">
          <h3>{{ item.title }}</h3>
          <p>{{ item.meta }}</p>
        </div>
      </li>
    </ol>
  </SectionPanel>
</template>

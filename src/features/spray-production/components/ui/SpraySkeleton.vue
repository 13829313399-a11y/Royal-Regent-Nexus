<script setup lang="ts">
/* 加载骨架：形状接近最终内容（指标行 + 面板 + 列表行），
   在首屏读取本厂数据时替代纯文字占位，避免内容跳变。 */
withDefaults(defineProps<{ title?: string }>(), { title: '正在读取工单、批次与资源…' })
</script>

<template>
  <div class="spray-loading" role="status" :aria-label="title">
    <div class="spray-metrics-group" aria-hidden="true">
      <div v-for="index in 4" :key="index" class="spray-metric">
        <div class="spray-skeleton-line" style="width: 54px; height: 26px; border-radius: 8px" />
        <div class="spray-skeleton-line" style="width: 72px; margin-top: 8px" />
        <div class="spray-skeleton-line" style="width: 108px; margin-top: 6px; height: 8px" />
      </div>
    </div>
    <section v-for="panel in 2" :key="panel" class="spray-panel">
      <div class="spray-section-title">
        <div class="spray-skeleton-line" style="width: 168px; height: 16px" />
        <div class="spray-skeleton-line" style="width: 96px; height: 12px" />
      </div>
      <div class="spray-skeleton-row" v-for="row in 3" :key="row">
        <div class="spray-skeleton-line" :style="{ width: 42 + row * 12 + '%' }" />
        <div class="spray-skeleton-line" style="width: 76px" />
      </div>
    </section>
    <p class="spray-help">{{ title }}</p>
  </div>
</template>

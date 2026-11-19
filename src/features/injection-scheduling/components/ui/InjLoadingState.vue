<script setup lang="ts">
import { LoaderCircle } from '@lucide/vue';
defineProps<{ label?: string }>();
</script>
<template>
  <div class="inj-loading-state" role="status">
    <p><LoaderCircle class="inj-spin" />{{ label || '正在读取工作台…' }}</p>
    <div v-for="i in 6" :key="i" class="inj-skeleton" aria-hidden="true" />
  </div>
</template>

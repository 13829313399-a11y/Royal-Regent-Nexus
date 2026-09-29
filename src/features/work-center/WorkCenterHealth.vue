<script setup lang="ts">
import { computed } from 'vue'
import type { WorkSnapshot } from './types'
import { workHealth } from './health'
const props = defineProps<{ snapshot?: WorkSnapshot | null; syncing?: boolean }>()
defineEmits<{ retry: [] }>()
const health = computed(() => workHealth(props.snapshot))
</script>

<template>
  <div v-if="health" class="nc-health" :class="{ 'is-warning': health.warning }" :role="health.warning ? 'alert' : 'status'">
    <details>
      <summary>{{ health.title }}<span>查看说明</span></summary>
      <p>{{ health.description }}</p>
      <ul v-if="health.details.length"><li v-for="detail in health.details" :key="detail">{{ detail }}</li></ul>
    </details>
    <button v-if="health.warning" type="button" :disabled="syncing" @click="$emit('retry')">{{ syncing ? '正在同步…' : '重试同步' }}</button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { WorkSnapshot } from './types'
import { workHealth } from './health'
const props = defineProps<{ snapshot?: WorkSnapshot | null; syncing?: boolean }>()
defineEmits<{ retry: []; navigate: [] }>()
const health = computed(() => workHealth(props.snapshot))
</script>

<template>
  <div v-if="health" class="nc-health" :class="{ 'is-warning': health.warning }" :role="health.warning ? 'alert' : 'status'">
    <details>
      <summary>{{ health.title }}<span>查看说明</span></summary>
      <p>{{ health.description }}</p>
      <ul v-if="health.details.length"><li v-for="detail in health.details" :key="detail">{{ detail }}</li></ul>
    </details>
    <div v-if="health.retryable || health.verificationCount" class="nc-health-actions">
      <RouterLink v-if="health.verificationCount" :to="{ name: 'notification-center', query: { view: 'verification' } }" @click="$emit('navigate')">查看待核对事项</RouterLink>
      <button v-if="health.retryable" type="button" :disabled="syncing" @click="$emit('retry')">{{ syncing ? '正在同步…' : '重试同步' }}</button>
    </div>
  </div>
</template>

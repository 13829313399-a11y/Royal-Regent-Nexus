<script setup lang="ts">
import { Wrench } from '@lucide/vue'
import type { TechnicalDetailItem } from '../presentation/technicalDetails'

withDefaults(defineProps<{ items: TechnicalDetailItem[]; summary?: string }>(), { summary: '技术信息' })
</script>

<template>
  <details class="scheduling-technical-details">
    <summary><Wrench :size="13" aria-hidden="true" />{{ summary }}</summary>
    <dl>
      <div v-for="detail in items" :key="`${detail.label}:${detail.rawValue}`">
        <dt>{{ detail.label }}</dt>
        <dd>{{ detail.rawValue }}</dd>
      </div>
    </dl>
  </details>
</template>

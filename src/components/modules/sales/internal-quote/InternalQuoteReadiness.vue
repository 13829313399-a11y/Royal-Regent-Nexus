<script setup lang="ts">
import type { InternalQuoteReadiness } from '@/types/internalQuoteDesk'
import { computed } from 'vue'
const props = defineProps<{ readiness?: InternalQuoteReadiness | null }>()
const labels: Record<string, string> = { empty: '待填写', incomplete: '待补齐', stale: '待重算' }
const blockers = computed(() => [...(props.readiness?.blockers ?? [])].sort((a, b) => Number(a.state === 'empty') - Number(b.state === 'empty')))
</script>

<template>
  <div class="readiness">
    <template v-if="readiness">
      <strong v-if="readiness.state === 'issued'">已输出 · 保留冻结核价</strong>
      <template v-else>
        <div class="readiness-bar">
          <progress :value="readiness.ready_sections" :max="readiness.required_sections || 1" aria-label="核价就绪部门" />
          <strong>{{ readiness.ready_sections }}/{{ readiness.required_sections }} 已就绪</strong>
        </div>
        <small v-if="readiness.state === 'ready'">资料齐全，可用于核价</small>
        <small v-for="item in blockers.slice(0, 2)" :key="item.section_code" :title="item.reason">
          {{ item.section_name }}：{{ labels[item.state] || '待补齐' }}
        </small>
        <details v-if="blockers.length">
          <summary>查看{{ blockers.length }}个部门的待办详情</summary>
          <small v-for="item in blockers" :key="item.section_code">{{ item.section_name }}：{{ labels[item.state] || '待补齐' }} · {{ item.reason }}</small>
        </details>
      </template>
    </template>
    <small v-else>待读取核价状态</small>
  </div>
</template>

<style scoped>
.readiness{min-width:180px;max-width:280px;display:grid;gap:4px;color:#0f766e}.readiness-bar{display:flex;align-items:center;gap:8px}.readiness progress{width:70px;height:7px;accent-color:#0d9488}.readiness strong{font-size:11px}.readiness small{display:block;color:#64748b;font-size:10px;white-space:normal;line-height:1.5}.readiness summary{cursor:pointer;font-size:10px}.readiness details small{margin-top:4px}
</style>

<script setup lang="ts">
import { computed } from 'vue'
import type { PresenceState } from '@/api/directory'

const props = defineProps<{ state: PresenceState }>()

const label = computed(() => ({
  online: '在线',
  away: '最近在线',
  offline: '离线',
})[props.state])

const classes = computed(() => ({
  online: 'bg-teal-50 text-teal-700 ring-teal-200',
  away: 'bg-amber-50 text-amber-700 ring-amber-200',
  offline: 'bg-slate-100 text-slate-600 ring-slate-200',
})[props.state])

const dotClasses = computed(() => ({
  online: 'bg-teal-500',
  away: 'bg-amber-500',
  offline: 'bg-slate-400',
})[props.state])
</script>

<template>
  <span
    class="inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-1 text-xs font-semibold ring-1 ring-inset"
    :class="classes"
  >
    <span class="size-1.5 rounded-full" :class="dotClasses" aria-hidden="true" />
    {{ label }}
  </span>
</template>

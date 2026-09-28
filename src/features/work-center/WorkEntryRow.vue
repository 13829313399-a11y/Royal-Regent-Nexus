<script setup lang="ts">
import { ArrowUpRight, Bell, ClipboardCheck, Clock3, PackageCheck, Factory } from '@lucide/vue'
import { computed } from 'vue'
import { formatBusinessDateTime } from '@/lib/dateTime'
import type { WorkEntry } from './types'
const props = defineProps<{ entry: WorkEntry; selected?: boolean; compact?: boolean }>()
defineEmits<{ select: [id: string] }>()
const icon = computed(() => props.entry.kind === 'info' ? Bell : props.entry.module === 'carton_supplier' ? PackageCheck : props.entry.module === 'molding' ? Factory : ClipboardCheck)
</script>

<template>
  <button type="button" class="nc-row" :class="{ 'is-selected': selected, 'is-compact': compact }" :aria-pressed="selected" @click="$emit('select', entry.id)">
    <span class="nc-row-icon" :class="{ 'is-info': entry.kind === 'info' }"><component :is="icon" :size="19" :stroke-width="1.75" aria-hidden="true" /></span>
    <span class="nc-row-body">
      <span class="nc-row-heading"><strong>{{ entry.title }}</strong><span v-if="entry.personal.read_state === 'unread'" class="nc-unread" aria-label="未读" /></span>
      <span class="nc-reference">{{ entry.reference_label }}<span v-if="!compact && entry.department_label"> · {{ entry.department_label }}</span></span>
      <span class="nc-meta"><span>{{ entry.source_factory?.label || '个人账户' }}<template v-if="entry.execution_factory && entry.execution_factory.id !== entry.source_factory?.id"> → {{ entry.execution_factory.label }}</template></span><span>{{ entry.responsible_label }}</span></span>
      <span v-if="!compact" class="nc-meta"><span :class="{ 'nc-overdue': entry.priority_reasons.length }">{{ entry.due_at ? formatBusinessDateTime(entry.due_at) + ' 到期' : '未设期限' }}</span><span v-if="entry.personal.snoozed_until"><Clock3 :size="12" /> 稍后提醒</span></span>
    </span>
    <ArrowUpRight :size="16" class="nc-row-arrow" aria-hidden="true" />
  </button>
</template>

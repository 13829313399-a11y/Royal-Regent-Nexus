<script setup lang="ts">
import { computed } from 'vue'
import { ArrowRight, ArrowUpRight, Check, Clock3, Eye, Pin } from '@lucide/vue'
import { Button, Checkbox, Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui'
import StatusPill from '@/components/common/StatusPill.vue'
import WorkIconButton from './WorkIconButton.vue'
import WorkSnoozePopover from './WorkSnoozePopover.vue'
import { entrySummary, moduleMeta } from './metadata'
import { aging } from './time'
import type { WorkEntry } from './types'

const props = defineProps<{
  entry: WorkEntry
  selected?: boolean
  compact?: boolean
  selectable?: boolean
  checked?: boolean
  serverTime?: string
  busy?: boolean
}>()
defineEmits<{
  select: [id: string, trigger?: HTMLElement]
  open: [entry: WorkEntry]
  preview: [entry: WorkEntry]
  check: [entry: WorkEntry]
  pin: [entry: WorkEntry]
  read: [entry: WorkEntry]
  snoozeHour: [entry: WorkEntry]
}>()
const meta = computed(() => moduleMeta(props.entry.module))
const age = computed(() => aging(props.entry, props.serverTime))
const summary = computed(() => entrySummary(props.entry))
</script>
<template>
  <article
    class="nc-row"
    :class="[{ 'is-selected': selected, 'is-compact': compact }, 'priority-' + entry.priority]"
  >
    <Checkbox
      v-if="selectable"
      :model-value="!!checked"
      :aria-label="'勾选 ' + entry.reference_label"
      @update:model-value="$emit('check', entry)"
    />
    <Button
      type="button"
      variant="ghost"
      class="nc-row-main"
      :data-work-entry="entry.id"
      :aria-pressed="compact ? undefined : !!selected"
      @click="compact ? $emit('open', entry) : $emit('select', entry.id, $event.currentTarget as HTMLElement)"
    >
      <span class="nc-module-icon" :class="meta.color"><component :is="meta.icon" :size="17" /></span>
      <span class="nc-row-body">
        <span class="nc-row-heading"
          ><strong>{{ entry.reference_label || entry.title }}</strong
          ><Pin v-if="entry.personal.pinned" :size="13" aria-label="已置顶" /><i
            v-if="entry.personal.read_state === 'unread'"
            class="nc-unread"
            aria-label="未读" /><StatusPill
            compact
            :label="
              entry.module === 'position_reviews' && entry.can_act_now ? meta.label : entry.stage_label
            " />
          <StatusPill v-if="age.tone === 'overdue'" compact tone="red" :label="age.text"
        /></span>
        <span class="nc-meta"
          ><span v-if="entry.department_label">{{ entry.department_label }}</span
          ><span v-if="entry.source_factory"
            >{{ entry.source_factory.label
            }}<template
              v-if="entry.execution_factory && entry.execution_factory.id !== entry.source_factory.id"
              ><ArrowRight :size="11" aria-label="流转至" />{{ entry.execution_factory.label }}</template
            ></span
          ></span
        >
        <span v-if="summary" class="nc-row-summary">{{ summary }}</span>
        <span v-if="entry.verification_state === 'unverified'" class="nc-warning-text"
          >待核对 · {{ entry.unavailable_reason }}</span
        >
      </span>
    </Button>
    <div class="nc-row-foot">
      <TooltipProvider v-if="age.text"
        ><Tooltip
          ><TooltipTrigger as-child
            ><span tabindex="0" class="nc-age" :data-tone="age.tone"
              ><Clock3 :size="12" />{{ age.tone === 'overdue' ? '业务截止时间' : age.text }}</span
            ></TooltipTrigger
          ><TooltipContent>{{ age.exact }}（上海时间）</TooltipContent></Tooltip
        ></TooltipProvider
      >
      <span class="nc-row-actions">
        <WorkIconButton v-if="compact" :icon="Eye" label="在工作台预览" @activate="$emit('preview', entry)" />
        <WorkIconButton v-else :icon="ArrowUpRight" label="前往源单据" @activate="$emit('open', entry)" />
        <WorkIconButton
          v-if="!compact"
          :icon="Pin"
          :label="entry.personal.pinned ? '取消置顶' : '置顶'"
          :pressed="entry.personal.pinned"
          :disabled="busy"
          @activate="$emit('pin', entry)"
        />
        <WorkIconButton
          v-if="compact && entry.can_act_now"
          :icon="Clock3"
          label="1 小时后提醒"
          :disabled="busy || !serverTime"
          @activate="$emit('snoozeHour', entry)"
        />
        <WorkSnoozePopover v-else-if="entry.can_act_now" :entry="entry" :server-time="serverTime" />
        <WorkIconButton
          v-if="entry.personal.read_state === 'unread'"
          :icon="Check"
          label="标为已读"
          :disabled="busy"
          @activate="$emit('read', entry)"
        />
      </span>
      <Button v-if="compact" variant="link" size="sm" @click="$emit('open', entry)"
        >{{ entry.can_act_now ? '去办理' : '查看' }}<ArrowUpRight :size="14"
      /></Button>
    </div>
  </article>
</template>

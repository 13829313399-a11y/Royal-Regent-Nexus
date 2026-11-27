<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { Archive, ArrowUpRight, Pin, X } from '@lucide/vue'
import { Button } from '@/components/ui'
import { useWorkCenterStore } from '@/stores/workCenter'
import { workCenterApi } from '@/api/workCenter'
import { formatBusinessDateTime } from '@/lib/dateTime'
import { canArchive, entrySummary, moduleMeta } from './metadata'
import { entryRoute } from './routes'
import { useWorkActions } from './useWorkActions'
import WorkIconButton from './WorkIconButton.vue'
import WorkSnoozePopover from './WorkSnoozePopover.vue'
import WorkStageStepper from './WorkStageStepper.vue'
import type { WorkEntry } from './types'

const props = defineProps<{ entry: WorkEntry; spatial?: boolean; sheet?: boolean }>()
defineEmits<{ close: [] }>()
const center = useWorkCenterStore(),
  actions = useWorkActions()
const timeline = ref<{ id: string; occurred_at: string; summary: string }[]>([])
const cursor = ref<string | null>(null),
  historyError = ref(''),
  loading = ref(false)
const viewer = computed(() => center.snapshot?.context.viewer_key)
let generation = 0
async function loadHistory(append = false) {
  const seq = ++generation,
    identity = viewer.value,
    id = props.entry.id
  loading.value = true
  historyError.value = ''
  try {
    const next = await workCenterApi.events(id, append ? (cursor.value ?? undefined) : undefined)
    if (seq !== generation || viewer.value !== identity || id !== props.entry.id) return
    timeline.value = append ? [...timeline.value, ...next.items] : next.items
    cursor.value = next.next_cursor
  } catch (error) {
    if (seq === generation && viewer.value === identity && !center.accessDenied(error))
      historyError.value = '经过暂时无法读取'
  } finally {
    if (seq === generation) loading.value = false
  }
}
watch(
  [() => props.entry.id, viewer],
  () => {
    timeline.value = []
    cursor.value = null
    void loadHistory()
  },
  { immediate: true },
)
onUnmounted(() => {
  generation++
})
const summary = computed(() => entrySummary(props.entry))
const actionable = computed(() => props.entry.actions.find((action) => action.enabled))
const attribution = computed(() =>
  [
    props.entry.source_factory?.label,
    props.entry.department_label,
    props.entry.responsible_label,
    props.entry.viewer_relation === 'assignee' && props.entry.module === 'internal_quote' ? '指定审核人' : '',
  ]
    .filter(Boolean)
    .join(' · '),
)
</script>
<template>
  <section class="nc-detail" aria-label="事项预览">
    <header class="nc-detail-bar">
      <span class="nc-module-label"><span v-if="spatial" data-rr-detail-target class="nc-module-icon rr-detail-target" :class="moduleMeta(entry.module).color" aria-hidden="true"><component :is="moduleMeta(entry.module).icon" :size="17" /></span>{{ moduleMeta(entry.module).label }}</span
      ><span class="nc-tools"
        ><WorkIconButton
          :icon="Pin"
          :label="entry.personal.pinned ? '取消置顶' : '置顶'"
          :pressed="entry.personal.pinned"
          :disabled="center.personalBusy"
          @activate="
            center.patch(entry, {
              pinned: !entry.personal.pinned,
              state_version: entry.personal.state_version,
            })
          " /><WorkSnoozePopover
          v-if="entry.can_act_now"
          :entry="entry"
          :server-time="center.snapshot?.context.server_time" /><WorkIconButton
          v-if="!sheet"
          :icon="X"
          label="关闭预览"
          @activate="$emit('close')"
      /></span>
    </header>
    <div class="nc-detail-body">
      <WorkStageStepper :entry="entry" />
      <h2>{{ entry.reference_label || entry.title }}</h2>
      <p class="nc-sub">{{ attribution }}</p>
      <p v-if="summary" class="nc-detail-summary">{{ summary }}</p>
      <div v-if="entry.unavailable_reason" class="nc-alert">{{ entry.unavailable_reason }}</div>
      <template v-if="entry.details?.length"
        ><h3>{{ entry.module === 'account_requests' ? '申请详情' : '单据详情' }}</h3>
        <dl class="nc-facts">
          <div v-for="field in entry.details" :key="field.label">
            <dt>{{ field.label }}</dt>
            <dd>{{ field.format === 'datetime' ? formatBusinessDateTime(field.value) : field.value }}</dd>
          </div>
        </dl></template
      >
      <p v-if="entry.due_at" class="nc-sub">业务期限 {{ formatBusinessDateTime(entry.due_at) }}</p>
      <p
        v-if="entry.execution_factory && entry.source_factory?.id !== entry.execution_factory.id"
        class="nc-sub"
      >
        执行厂区 {{ entry.execution_factory.label }}
      </p>
      <template v-if="timeline.length || historyError"
        ><h3>最近经过</h3>
        <ol class="nc-timeline">
          <li v-for="event in timeline" :key="event.id">
            <span>{{ event.summary }}</span
            ><time>{{ formatBusinessDateTime(event.occurred_at) }}</time>
          </li>
        </ol>
        <Button
          v-if="historyError || cursor"
          variant="ghost"
          size="sm"
          :disabled="loading"
          @click="loadHistory(!!timeline.length)"
          >{{ historyError || '更早经过' }}</Button
        ></template
      >
      <div class="nc-tools">
        <Button
          v-if="entry.viewer_relation === 'watcher' && !canArchive(entry)"
          size="sm"
          variant="ghost"
          :disabled="center.personalBusy"
          @click="
            center.patch(entry, {
              following: entry.personal.following === false,
              state_version: entry.personal.state_version,
            })
          "
          >{{ entry.personal.following === false ? '恢复跟进' : '不再跟进' }}</Button
        >
        <Button
          v-if="canArchive(entry)"
          size="sm"
          variant="ghost"
          :disabled="center.personalBusy"
          @click="
            center.patch(entry, {
              archived: !entry.personal.archived_at,
              state_version: entry.personal.state_version,
            })
          "
          ><Archive :size="14" />{{ entry.personal.archived_at ? '取消归档' : '归档' }}</Button
        >
      </div>
    </div>
    <footer class="nc-detail-footer">
      <Button
        v-if="actionable && (actionable.mode === 'refresh_identity' || entryRoute(entry))"
        class="w-full"
        @click="actions.open(entry)"
        >{{ actionable.label }}<ArrowUpRight :size="16"
      /></Button>
      <p v-else class="nc-sub">源业务入口暂不可用</p>
    </footer>
  </section>
</template>

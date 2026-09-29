<script setup lang="ts">
import { ref, watch } from 'vue'
import { ArrowUpRight, Clock3, Pin, Archive, X, CheckCheck } from '@lucide/vue'
import { useWorkCenterStore } from '@/stores/workCenter'
import { useAuthStore } from '@/stores/auth'
import { workCenterApi } from '@/api/workCenter'
import { entryRoute } from './routes'
import { formatBusinessDateTime } from '@/lib/dateTime'
import Button from '@/components/ui/button/Button.vue'
import type { WorkEntry } from './types'
const props = defineProps<{ entry: WorkEntry }>()
defineEmits<{ close: [] }>()
const center = useWorkCenterStore(), auth = useAuthStore()
const timeline = ref<{ id: string; occurred_at: string; summary: string }[]>([])
const timelineCursor = ref<string | null>(null), timelineError = ref(''), customTime = ref('')
let sequence = 0
async function loadTimeline(append = false) {
  const seq = ++sequence, id = props.entry.id
  try {
    const result = await workCenterApi.events(id, append ? timelineCursor.value ?? undefined : undefined)
    if (seq !== sequence || props.entry.id !== id) return
    timeline.value = append ? [...timeline.value, ...result.items] : result.items; timelineCursor.value = result.next_cursor; timelineError.value = ''
  } catch { if (seq === sequence) timelineError.value = '经过暂时无法读取' }
}
watch(() => props.entry.id, () => { timeline.value = []; void loadTimeline() }, { immediate: true })
function snooze(until: string | null) { return center.patch(props.entry, { state_version: props.entry.personal.state_version, snoozed_until: until }) }
function customSnooze() {
  // datetime-local is explicitly interpreted in the business timezone.
  if (customTime.value) void snooze(new Date(`${customTime.value}:00+08:00`).toISOString())
}
</script>

<template>
  <section class="nc-detail" aria-label="事项预览">
    <header class="nc-detail-top"><span>事项预览</span><button type="button" aria-label="关闭预览" class="nc-icon-button" @click="$emit('close')"><X :size="18" /></button></header>
    <div class="nc-detail-content">
      <span class="nc-stage">{{ entry.lifecycle === 'superseded' ? '已被取代' : entry.lifecycle === 'resolved' ? '本阶段已完成' : entry.kind === 'info' ? '知会消息' : entry.can_act_now ? '当前可处理' : '我在等待' }}</span>
      <h2>{{ entry.title }}</h2><p class="nc-detail-ref">{{ entry.reference_label }}</p>
      <div class="nc-why"><CheckCheck :size="18" /><div><strong>为什么需要我</strong><p>{{ entry.why_me }}</p></div></div>
      <dl><div><dt>来源厂区</dt><dd>{{ entry.source_factory?.label || '个人账户' }}</dd></div><div v-if="entry.execution_factory"><dt>执行厂区</dt><dd>{{ entry.execution_factory.label }}</dd></div><div><dt>责任部门</dt><dd>{{ entry.department_label || '本人' }}</dd></div><div><dt>业务期限</dt><dd>{{ entry.due_at ? formatBusinessDateTime(entry.due_at) : '未设期限' }}</dd></div></dl>
      <p class="nc-summary-text">{{ entry.summary }}</p>
      <p v-if="entry.unavailable_reason" class="nc-message">{{ entry.unavailable_reason }}</p>
      <h3>最近经过</h3>
      <ol class="nc-timeline"><li v-for="event in timeline" :key="event.id"><p>{{ event.summary }}</p><time>{{ formatBusinessDateTime(event.occurred_at) }}</time></li></ol>
      <p v-if="!timeline.length" class="nc-muted">{{ timelineError || '当前阶段直接核验自源业务；详细审计请打开原单据。' }}</p>
      <Button v-if="timelineCursor" variant="ghost" size="sm" @click="loadTimeline(true)">更早经过</Button>
      <div class="nc-personal-actions">
        <Button v-if="entry.viewer_relation === 'watcher' && ['open', 'in_progress'].includes(entry.lifecycle || '')" variant="outline" size="sm" :disabled="center.personalBusy" @click="center.patch(entry, { state_version: entry.personal.state_version, following: entry.personal.following === false })">{{ entry.personal.following === false ? '恢复跟进' : '不再跟进' }}</Button>
        <Button variant="outline" size="sm" :disabled="center.personalBusy" @click="center.patch(entry, { state_version: entry.personal.state_version, pinned: !entry.personal.pinned })"><Pin :size="14" />{{ entry.personal.pinned ? '取消置顶' : '置顶' }}</Button>
        <Button v-if="entry.can_act_now" variant="outline" size="sm" :disabled="center.personalBusy" @click="snooze(entry.personal.snoozed_until ? null : new Date(Date.parse(center.snapshot?.context.server_time || new Date().toISOString()) + 3600000).toISOString())"><Clock3 :size="14" />{{ entry.personal.snoozed_until ? '取消稍后' : '1 小时后' }}</Button>
        <Button v-if="entry.kind === 'info' || ['resolved', 'cancelled', 'superseded'].includes(entry.lifecycle || '')" variant="outline" size="sm" :disabled="center.personalBusy" @click="center.patch(entry, { state_version: entry.personal.state_version, archived: !entry.personal.archived_at })"><Archive :size="14" />{{ entry.personal.archived_at ? '取消归档' : '归档' }}</Button>
      </div>
      <details v-if="entry.can_act_now" class="nc-custom-snooze"><summary>选择提醒时间</summary><label>上海时间<input v-model="customTime" type="datetime-local" /></label><Button variant="outline" size="sm" :disabled="!customTime || center.personalBusy" @click="customSnooze">设置提醒</Button></details>
      <p class="nc-muted" v-if="entry.can_act_now">稍后提醒只调整个人提示，仍计入当前责任。</p>
      <p v-if="center.detailError" class="nc-error" role="alert">{{ center.detailError }}</p>
    </div>
    <footer class="nc-detail-footer">
      <Button v-if="entry.actions[0]?.mode === 'refresh_identity'" class="w-full" @click="auth.refreshSession().then(() => center.refresh())">刷新账户信息</Button>
      <Button v-else-if="entryRoute(entry)" as-child class="w-full"><RouterLink :to="entryRoute(entry)!">{{ entry.actions[0]?.label }}<ArrowUpRight :size="16" /></RouterLink></Button>
      <p v-else class="nc-muted">源业务入口暂不可用，请刷新后重试。</p>
    </footer>
  </section>
</template>

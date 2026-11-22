<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowUpRight, Bell, CheckCheck, RefreshCw, Volume2, VolumeX, X } from '@lucide/vue'
import {
  Button,
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerTitle,
  DrawerTrigger,
  Popover,
  PopoverContent,
  PopoverTrigger,
  Tabs,
  TabsList,
  TabsTrigger,
} from '@/components/ui'
import { useWorkCenterStore } from '@/stores/workCenter'
import { useMediaQuery } from '@/composables/useMediaQuery'
import { workEmptyState } from './health'
import { attentionGroup } from './metadata'
import { isSnoozed, snoozePresets } from './time'
import { useWorkActions } from './useWorkActions'
import WorkEntryRow from './WorkEntryRow.vue'
import WorkCenterHealth from './WorkCenterHealth.vue'
import WorkIconButton from './WorkIconButton.vue'
import type { WorkEntry } from './types'

const center = useWorkCenterStore(),
  actions = useWorkActions()
const mobile = useMediaQuery('(width < 640px)'),
  ringing = ref(false)
const tab = computed(() => center.panelTab)
const serverTime = computed(() => center.bell?.context.server_time)
const entries = computed(() =>
  tab.value === 'info'
    ? center.information
    : (center.bell?.items ?? []).filter((e) => !isSnoozed(e, serverTime.value)),
)
const groups = computed(() =>
  tab.value === 'info'
    ? [{ name: '', items: entries.value }]
    : ['逾期 / 紧急', '指派给我', '团队队列']
        .map((name) => ({ name, items: entries.value.filter((e) => attentionGroup(e) === name) }))
        .filter((g) => g.items.length),
)
const loading = computed(() =>
  tab.value === 'info'
    ? center.informationLoading && !center.informationLoaded
    : !center.bell && center.loading,
)
const empty = computed(() => workEmptyState(center.bell, tab.value))
watch(
  () => center.bell,
  (next, previous) => {
    if (
      !next ||
      !previous ||
      next.context.viewer_key !== previous.context.viewer_key ||
      window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches
    )
      return
    const known = new Set(previous.items.map((row) => row.id + '@' + row.attention_version))
    ringing.value = next.items.some(
      (row) => row.personal.read_state === 'unread' && !known.has(row.id + '@' + row.attention_version),
    )
  },
)
function open(value: boolean) {
  center.panelOpen = value
  if (value) void center.refresh(!!center.bell)
}
function changeTab(value: unknown) {
  center.panelTab = value === 'info' ? 'info' : 'todo'
  if (value === 'info') void center.loadInformation()
}
async function snooze(entry: WorkEntry) {
  const until = snoozePresets(center.serverNow())[0]?.until
  if (
    until &&
    (await center.patch(entry, { state_version: entry.personal.state_version, snoozed_until: until }))
  )
    center.feedback = '已移至稍后提醒'
}
</script>
<template>
  <component :is="mobile ? Drawer : Popover" :open="center.panelOpen" @update:open="open">
    <component :is="mobile ? DrawerTrigger : PopoverTrigger" as-child
      ><Button
        class="nc-bell glass-chrome"
        variant="ghost"
        size="icon"
        :aria-label="
          '待办与消息，' +
          center.count +
          ' 项可处理，' +
          (center.summary?.info_unread_total ?? 0) +
          ' 条未读知会'
        "
        ><Bell :class="{ 'nc-ring': ringing }" @animationend="ringing = false" :size="20" /><span
          v-if="center.count"
          class="nc-count"
          >{{ center.count > 99 ? '99+' : center.count }}</span
        ><i v-else-if="center.summary?.info_unread_total" class="nc-info-dot" /></Button
    ></component>
    <component
      :is="mobile ? DrawerContent : PopoverContent"
      class="nc-popover"
      :class="{ 'nc-bell-sheet': mobile }"
      v-bind="mobile ? { side: 'bottom', showCloseButton: false } : { align: 'end', sideOffset: 12 }"
      aria-label="待办与消息"
    >
      <span v-if="mobile" class="nc-grip" /><DrawerDescription v-if="mobile" class="sr-only"
        >查看待办或知会，打开源单据。</DrawerDescription
      >
      <header class="nc-bell-head">
        <component :is="mobile ? DrawerTitle : 'h2'">待办与消息</component>
        <div class="nc-tools">
          <WorkCenterHealth badge :snapshot="center.bell" :syncing="center.syncing" /><WorkIconButton
            :icon="RefreshCw"
            label="刷新事项"
            :disabled="center.syncing"
            @activate="center.refresh()"
          /><WorkIconButton :icon="X" label="关闭通知面板" @activate="open(false)" />
        </div>
      </header>
      <Tabs :model-value="tab" @update:model-value="changeTab"
        ><TabsList aria-label="通知类别"
          ><TabsTrigger value="todo"
            >待办<span v-if="center.count"> {{ center.count }}</span></TabsTrigger
          ><TabsTrigger value="info"
            >知会<span v-if="center.summary?.info_unread_total">
              {{ center.summary.info_unread_total }}</span
            ></TabsTrigger
          ></TabsList
        ></Tabs
      >
      <WorkCenterHealth
        :snapshot="center.bell"
        :syncing="center.syncing"
        @retry="center.refresh()"
        @navigate="open(false)"
      />
      <div
        v-if="
          (center.error && center.bell?.health.status !== 'stale') ||
          (tab === 'info' && center.informationError)
        "
        role="alert"
        class="nc-alert"
      >
        <span>{{ tab === 'info' && center.informationError ? center.informationError : center.error }}</span
        ><Button
          size="xs"
          variant="ghost"
          @click="tab === 'info' && center.informationError ? center.loadInformation() : center.refresh()"
          >重试</Button
        >
      </div>
      <div class="nc-bell-list" :aria-busy="loading">
        <div v-if="loading" class="nc-skeletons" role="status" aria-label="加载事项">
          <i v-for="n in 3" :key="n" class="skeleton-shimmer" />
        </div>
        <template v-else
          ><section v-for="group in groups" :key="group.name">
            <h3 v-if="group.name" class="nc-group-heading">{{ group.name }}</h3>
            <WorkEntryRow
              v-for="entry in group.items"
              :key="entry.id"
              :entry="entry"
              compact
              :busy="center.personalBusy"
              :server-time="serverTime"
              @open="actions.open"
              @preview="actions.preview"
              @snooze-hour="snooze"
              @read="center.patch(entry, { observed_content_version: entry.content_version })"
            />
          </section>
          <p
            v-if="!entries.length && !center.error && !(tab === 'info' && center.informationError)"
            class="nc-empty-small"
          >
            {{ tab === 'todo' && center.bell?.summary.snoozed_total ? '待办已设稍后提醒' : empty.title }}
          </p></template
        >
      </div>
      <footer class="nc-bell-footer">
        <WorkIconButton
          :icon="center.preferences.sound_enabled ? Volume2 : VolumeX"
          :label="center.preferences.sound_enabled ? '静音' : '开启声音提醒'"
          :pressed="center.preferences.sound_enabled"
          @activate="center.savePreferences({ sound_enabled: !center.preferences.sound_enabled })"
        /><Button
          v-if="tab === 'info' && entries.some((e) => e.personal.read_state === 'unread')"
          size="sm"
          variant="ghost"
          :disabled="center.personalBusy"
          @click="center.markVisibleRead(entries.filter((e) => e.personal.read_state === 'unread'))"
          ><CheckCheck :size="15" />本页已读</Button
        ><Button as-child variant="link" class="ml-auto"
          ><RouterLink :to="{ name: 'notification-center', query: { view: tab } }" @click="open(false)"
            >打开事项工作台<ArrowUpRight :size="15" /></RouterLink
        ></Button>
      </footer>
    </component>
  </component>
</template>

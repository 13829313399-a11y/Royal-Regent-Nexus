<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Clock3,
  Inbox,
  ListTodo,
  RefreshCw,
  Search,
  SlidersHorizontal,
} from '@lucide/vue'
import {
  Button,
  Checkbox,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerTitle,
  Input,
  Popover,
  PopoverContent,
  PopoverTrigger,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Switch,
  Tabs,
  TabsList,
  TabsTrigger,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui'
import { useWorkCenterStore, defaultWorkQuery } from '@/stores/workCenter'
import { registerAssistantSelection } from '@/features/assistant/selection'
import WorkEntryRow from '@/features/work-center/WorkEntryRow.vue'
import WorkEntryDetail from '@/features/work-center/WorkEntryDetail.vue'
import WorkCenterHealth from '@/features/work-center/WorkCenterHealth.vue'
import WorkPulseBar from '@/features/work-center/WorkPulseBar.vue'
import { sourceLabel, workEmptyState, verificationCount } from '@/features/work-center/health'
import { attentionGroup, canArchive, normalizeFactory } from '@/features/work-center/metadata'
import { isSnoozed, snoozePresets } from '@/features/work-center/time'
import { useWorkActions } from '@/features/work-center/useWorkActions'
import { useWorkCenterShortcuts } from '@/features/work-center/useWorkCenterShortcuts'
import type { WorkEntry, WorkPreferences, WorkQuery, WorkView } from '@/features/work-center/types'

const center = useWorkCenterStore(),
  actions = useWorkActions(),
  router = useRouter(),
  route = useRoute()
const root = ref<HTMLElement>(),
  width = ref(window.innerWidth),
  search = ref(''),
  checked = ref<string[]>([])
const helpOpen = ref(false),
  showSnoozed = ref(false),
  loadingEntry = ref(false)
const orderedViews = [
  { id: 'todo', label: '待办' },
  { id: 'waiting', label: '我在等待' },
  { id: 'info', label: '知会' },
  { id: 'history', label: '历史' },
] as const
const views = new Set<WorkView>(['todo', 'assigned', 'team', 'waiting', 'info', 'history', 'verification'])
const primary = computed(() =>
  ['assigned', 'team'].includes(center.query.view) ? 'todo' : center.query.view,
)
const snap = computed(() => center.snapshot),
  time = computed(() => snap.value?.context.server_time)
const entryId = computed(() => (typeof route.query.entry === 'string' ? route.query.entry : ''))
const compact = computed(() => width.value < 1024)
const drawerOpen = computed(
  () => compact.value && !!entryId.value && (!!center.selected || loadingEntry.value),
)
const rows = computed(() => snap.value?.items ?? [])
const active = computed(() =>
  rows.value
    .filter((item) => !isSnoozed(item, time.value))
    .sort((a, b) => Number(b.personal.pinned) - Number(a.personal.pinned)),
)
const deferred = computed(() => rows.value.filter((item) => isSnoozed(item, time.value)))
const grouping = ref<'priority' | 'module' | 'none'>('priority')
const groups = computed(() => {
  const collected = new Map<string, WorkEntry[]>()
  for (const item of active.value) {
    const label =
      grouping.value === 'module'
        ? item.module
        : grouping.value === 'priority' && primary.value === 'todo'
          ? attentionGroup(item)
          : ''
    const group = collected.get(label) ?? []
    group.push(item)
    collected.set(label, group)
  }
  const rank = ['逾期 / 紧急', '指派给我', '团队队列']
  return [...collected].sort(([a], [b]) => rank.indexOf(a) - rank.indexOf(b))
})
const visible = computed(() => [
  ...groups.value.flatMap(([, items]) => items),
  ...(showSnoozed.value ? deferred.value : []),
])
const selected = computed(() => visible.value.filter((item) => checked.value.includes(item.id)))
const allChecked = computed(() => !!visible.value.length && selected.value.length === visible.value.length)
const eligibleArchive = computed(() => !!selected.value.length && selected.value.every(canArchive))
const filtered = computed(
  () =>
    center.query.factory_scope !== 'authorized' ||
    !!center.query.module ||
    !!center.query.q ||
    center.query.due !== 'all' ||
    center.query.unread_only ||
    ['team', 'assigned'].includes(center.query.view),
)
const verification = computed(() => verificationCount(snap.value))
const empty = computed(() => workEmptyState(snap.value, center.query.view))
const unregister = registerAssistantSelection('work-center', () => ({
  selection_id: center.selected?.id || 'work-center-filters',
  resources: center.selected
    ? [{ module_id: 'work-center', resource_type: 'entry', resource_id: center.selected.id }]
    : [],
  filters: {
    factory_id: center.query.factory_scope,
    view: center.query.view,
    module: center.query.module,
    q: center.query.q,
    due: center.query.due,
    unread_only: center.query.unread_only,
  },
}))
let trigger: HTMLElement | null = null,
  lastQuery = '',
  currentEntry = '',
  routeSequence = 0,
  recheckRoute = false
let debounce: ReturnType<typeof setTimeout> | undefined
let observer: ResizeObserver | undefined,
  frame = 0
function fitFocus() {
  if (frame) return
  frame = requestAnimationFrame(() => {
    frame = 0
    const panel = root.value?.querySelector<HTMLElement>('.nc-focus')
    if (panel)
      panel.style.setProperty('--nc-focus-top', Math.max(88, panel.getBoundingClientRect().top) + 'px')
  })
}
function navigate(values: Record<string, string | undefined>) {
  return router.replace({ query: { ...route.query, entry: undefined, cursor: undefined, ...values } })
}
function clearFilters() {
  return router.replace({ query: { view: primary.value } })
}
function choose(id: string) {
  trigger =
    Array.from(root.value?.querySelectorAll<HTMLElement>('[data-work-entry]') ?? []).find(
      (el) => el.dataset.workEntry === id,
    ) ?? (document.activeElement as HTMLElement)
  if (id === entryId.value && !center.selected && !loadingEntry.value) {
    currentEntry = ''
    return applyRoute()
  }
  return router.replace({ query: { ...route.query, entry: id } })
}
function restoreFocus() {
  void nextTick(() => {
    if (trigger?.isConnected) trigger.focus({ preventScroll: true })
    else root.value?.querySelector<HTMLElement>('[data-work-search]')?.focus()
  })
}
async function close() {
  center.clearSelection()
  if (entryId.value) await router.replace({ query: { ...route.query, entry: undefined } })
  restoreFocus()
}
async function applyRoute() {
  if (route.name !== 'notification-center') return
  const seq = ++routeSequence,
    raw = route.query
  const factory = normalizeFactory(raw.factory)
  if (raw.factory && factory === 'authorized') {
    await router.replace({ query: { ...raw, factory: undefined } })
    return
  }
  const view = views.has(raw.view as WorkView) ? (raw.view as WorkView) : 'todo'
  const value: WorkQuery = {
    ...defaultWorkQuery(),
    view,
    factory_scope: factory,
    module: typeof raw.module === 'string' ? raw.module : '',
    q: typeof raw.q === 'string' ? raw.q : '',
    due: ['today', 'overdue', 'none'].includes(String(raw.due)) ? String(raw.due) : 'all',
    unread_only: raw.unread === '1',
    cursor: typeof raw.cursor === 'string' ? raw.cursor : undefined,
  }
  const key = JSON.stringify(value),
    id = entryId.value
  if (lastQuery !== key) {
    lastQuery = key
    clearTimeout(debounce)
    search.value = value.q
    checked.value = []
    showSnoozed.value = false
    center.clearSelection()
    currentEntry = ''
    await center.setQuery(value)
  }
  if (seq !== routeSequence) return
  if (!id) {
    currentEntry = ''
    loadingEntry.value = false
    center.clearSelection()
    return
  }
  if (currentEntry !== id && !center.error) {
    currentEntry = id
    loadingEntry.value = true
    await center.selectEntry(id)
    if (seq === routeSequence) loadingEntry.value = false
  }
}
function resize() {
  width.value = window.innerWidth
  fitFocus()
}
function engaged() {
  fitFocus()
  center.workspaceEngaged =
    !!root.value?.querySelector('input:focus') ||
    window.scrollY > 80 ||
    (document.querySelector('.app-shell-content')?.scrollTop ?? 0) > 80
}
function searchFor(value: unknown, immediate = false) {
  search.value = String(value ?? '')
  clearTimeout(debounce)
  if (immediate) void navigate({ q: search.value.trim() || undefined })
  else debounce = setTimeout(() => void navigate({ q: search.value.trim() || undefined }), 280)
}
function tick(entry: WorkEntry) {
  checked.value = checked.value.includes(entry.id)
    ? checked.value.filter((id) => id !== entry.id)
    : [...checked.value, entry.id]
}
function checkPage() {
  checked.value = allChecked.value ? [] : visible.value.map((row) => row.id)
}
async function batch(action: 'read' | 'archive' | 'snooze') {
  const failed = await center.batchPatch(selected.value, action, snoozePresets(time.value)[0]?.until)
  if (failed) checked.value = failed
}
function pin(item: WorkEntry) {
  void center.patch(item, { state_version: item.personal.state_version, pinned: !item.personal.pinned })
}
function read(item: WorkEntry) {
  void center.patch(item, { observed_content_version: item.content_version })
}
function rowBinding(item: WorkEntry) {
  return {
    entry: item,
    selected: center.selected?.id === item.id,
    selectable: true,
    checked: checked.value.includes(item.id),
    busy: center.personalBusy,
    serverTime: time.value,
  }
}
const rowEvents = { select: choose, open: actions.open, check: tick, pin, read }
function nextEntry(offset: number) {
  if (!visible.value.length) return
  const index = visible.value.findIndex((item) => item.id === entryId.value)
  const row = visible.value[Math.max(0, Math.min(visible.value.length - 1, index < 0 ? 0 : index + offset))]!
  void choose(row.id)
  trigger?.focus({ preventScroll: true })
  trigger?.scrollIntoView({
    block: 'nearest',
    behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches ? 'instant' : 'smooth',
  })
}
useWorkCenterShortcuts((key) => {
  if (key === 'j' || key === 'ArrowDown') nextEntry(1)
  else if (key === 'k' || key === 'ArrowUp') nextEntry(-1)
  else if (key === '/') root.value?.querySelector<HTMLInputElement>('[data-work-search]')?.focus()
  else if (key === '?') helpOpen.value = !helpOpen.value
  else if (key === 'Escape') {
    if (checked.value.length) checked.value = []
    else if (entryId.value) void close()
    else return false
  } else {
    const item = center.selected
    if (!item) return false
    if (key === 'Enter') void actions.open(item)
    else if (key === 'm') read(item)
    else if (key === 'p') pin(item)
    else if (key === 's' && item.can_act_now)
      Array.from(root.value?.querySelectorAll<HTMLButtonElement>('[data-snooze-entry]') ?? [])
        .find((el) => el.dataset.snoozeEntry === item.id)
        ?.click()
    else return false
  }
  return true
})
watch(() => route.query, applyRoute)
watch(visible, (items) => {
  const ids = new Set(items.map((i) => i.id))
  checked.value = checked.value.filter((id) => ids.has(id))
})
watch(
  () => snap.value?.context.viewer_key,
  (value, previous) => {
    if (previous && previous !== value) {
      checked.value = []
      currentEntry = ''
      loadingEntry.value = false
      helpOpen.value = false
      recheckRoute = true
    }
    if (value && recheckRoute) {
      recheckRoute = false
      lastQuery = JSON.stringify(center.query)
      void applyRoute()
    }
  },
)
onMounted(() => {
  center.workspaceOpen = true
  center.panelOpen = false
  void applyRoute()
  observer = new ResizeObserver(fitFocus)
  root.value?.querySelectorAll('.nc-page-head,.nc-command').forEach((el) => observer?.observe(el))
  window.addEventListener('resize', resize)
  window.addEventListener('scroll', engaged, true)
})
onUnmounted(() => {
  routeSequence++
  clearTimeout(debounce)
  cancelAnimationFrame(frame)
  observer?.disconnect()
  unregister()
  window.removeEventListener('resize', resize)
  window.removeEventListener('scroll', engaged, true)
  center.workspaceOpen = false
  center.workspaceEngaged = false
  center.clearSelection()
})
</script>
<template>
  <div
    ref="root"
    class="app-page nc-workspace"
    data-yl-help="work-center.overview"
    @focusin="engaged"
    @focusout="engaged"
  >
    <header class="nc-page-head">
      <div>
        <h1>事项工作台</h1>
        <p>
          与我相关 · {{ center.query.factory_scope === 'authorized' ? '全部授权责任范围' : '按厂区查看' }}
        </p>
      </div>
      <div class="nc-tools">
        <WorkCenterHealth badge :snapshot="snap" :syncing="center.syncing" />
        <Popover
          ><PopoverTrigger as-child
            ><Button variant="ghost" size="sm" aria-label="声音与提醒设置"
              ><SlidersHorizontal :size="15" /><span class="nc-head-label">提醒设置</span></Button
            ></PopoverTrigger
          ><PopoverContent align="end" aria-label="提醒设置" class="nc-settings"
            ><h3>提醒设置</h3>
            <label
              >声音提醒<Switch
                aria-label="声音提醒"
                :model-value="center.preferences.sound_enabled"
                @update:model-value="(value) => center.savePreferences({ sound_enabled: value })" /></label
            ><label
              >弹窗范围<Select
                :model-value="center.preferences.toast_level"
                @update:model-value="
                  (value) => center.savePreferences({ toast_level: value as WorkPreferences['toast_level'] })
                "
                ><SelectTrigger aria-label="弹窗范围"><SelectValue /></SelectTrigger
                ><SelectContent
                  ><SelectItem value="assigned">仅指派给我</SelectItem
                  ><SelectItem value="all_tasks">全部待办</SelectItem
                  ><SelectItem value="none">关闭弹窗</SelectItem></SelectContent
                ></Select
              ></label
            ></PopoverContent
          ></Popover
        >
        <Button
          size="sm"
          variant="ghost"
          aria-label="刷新事项"
          :disabled="center.syncing"
          @click="center.refresh()"
          ><RefreshCw :size="15" :class="{ 'nc-spin': center.syncing }" /><span class="nc-head-label"
            >刷新</span
          ></Button
        >
        <Popover v-model:open="helpOpen"
          ><PopoverTrigger as-child
            ><Button aria-label="快捷键" variant="ghost" size="icon-sm"
              ><CircleHelp :size="16" /></Button></PopoverTrigger
          ><PopoverContent align="end" aria-label="快捷键"
            ><h3>快捷键</h3>
            <dl class="nc-keymap">
              <template
                v-for="[keys, title] in [
                  ['J / K', '下一条 / 上一条'],
                  ['Enter', '前往办理'],
                  ['M / P / S', '标读 / 置顶 / 稍后'],
                  ['/', '搜索'],
                  ['Esc', '关闭或取消选择'],
                ]"
                :key="keys"
                ><dt>
                  <kbd>{{ keys }}</kbd>
                </dt>
                <dd>{{ title }}</dd></template
              >
            </dl></PopoverContent
          ></Popover
        >
      </div>
    </header>
    <div v-if="center.error && snap?.health.status !== 'stale'" role="alert" class="nc-alert">
      <span>{{ center.error }}</span
      ><Button size="xs" variant="ghost" @click="center.refresh()">重新同步</Button>
    </div>
    <WorkCenterHealth :snapshot="snap" :syncing="center.syncing" @retry="center.refresh()" />
    <section class="nc-command glass-chrome" data-yl-help="work-center.summary" aria-label="事项视图与筛选">
      <div class="nc-command-top">
        <Tabs :model-value="primary" @update:model-value="(v) => navigate({ view: String(v) })"
          ><TabsList class="nc-tabs" aria-label="事项视图"
            ><TabsTrigger v-for="v in orderedViews" :key="v.id" :value="v.id"
              >{{ v.label
              }}<span v-if="v.id === 'todo' && snap?.summary.actionable_total" class="nc-tab-count">{{
                snap.summary.actionable_total
              }}</span></TabsTrigger
            ><TabsTrigger v-if="verification" value="verification"
              >待核对 {{ verification }}</TabsTrigger
            ></TabsList
          ></Tabs
        >
        <WorkPulseBar
          :snapshot="snap"
          :query="center.query"
          mode="pulse"
          @change="navigate"
          @snoozed="showSnoozed = !showSnoozed"
        />
      </div>
      <div data-yl-help="work-center.filters" class="nc-filters">
        <div class="nc-filter-line">
          <label class="nc-search"
            ><Search :size="16" /><Input
              data-work-search
              type="search"
              :model-value="search"
              aria-label="搜索事项"
              placeholder="搜索单号、姓名、产品…"
              @update:model-value="searchFor"
              @keydown.enter.prevent="searchFor(search, true)"
            /><kbd>/</kbd></label
          >
          <Select
            :model-value="center.query.due"
            @update:model-value="(v) => navigate({ due: v === 'all' ? undefined : String(v) })"
            ><SelectTrigger class="nc-due" aria-label="期限筛选"><SelectValue /></SelectTrigger
            ><SelectContent
              ><SelectItem value="all">全部期限</SelectItem><SelectItem value="today">今日到期</SelectItem
              ><SelectItem value="overdue">已逾期</SelectItem
              ><SelectItem value="none">无期限</SelectItem></SelectContent
            ></Select
          >
          <label class="nc-unread-filter"
            ><Checkbox
              aria-label="仅看未读"
              :model-value="center.query.unread_only"
              @update:model-value="(v) => navigate({ unread: v === true ? '1' : undefined })"
            />仅未读</label
          >
        </div>
        <WorkPulseBar mode="facets" :snapshot="snap" :query="center.query" @change="navigate" />
      </div>
    </section>
    <div class="nc-layout">
      <section class="surface-l1 nc-list-panel" data-yl-help="work-center.list" aria-label="事项列表">
        <header class="nc-list-head">
          <Checkbox
            aria-label="全选本页"
            :disabled="!visible.length"
            :model-value="allChecked ? true : selected.length ? 'indeterminate' : false"
            @update:model-value="checkPage"
          />
          <h2>事项列表</h2>
          <span v-if="filtered && snap" class="nc-sub">{{ snap.query.filtered_total }} 项匹配</span>
          <Select v-model="grouping"
            ><SelectTrigger class="nc-group-select" aria-label="列表分组"><SelectValue /></SelectTrigger
            ><SelectContent
              ><SelectItem value="priority">按优先级</SelectItem><SelectItem value="module">按模块</SelectItem
              ><SelectItem value="none">不分组</SelectItem></SelectContent
            ></Select
          >
        </header>
        <Button v-if="center.pendingRefresh" size="sm" variant="soft" @click="center.refresh()"
          >有新事项到达 · 点击刷新</Button
        >
        <div v-if="center.loading && !snap" class="nc-skeletons" role="status" aria-label="正在读取事项">
          <i v-for="n in 4" :key="n" class="skeleton-shimmer" />
        </div>
        <template v-else
          ><section v-for="[name, items] in groups" :key="name">
            <h3 v-if="name" class="nc-group-heading">
              {{ grouping === 'module' ? sourceLabel(name) : name }}
            </h3>
            <WorkEntryRow
              v-for="entry in items"
              :key="entry.id"
              v-bind="rowBinding(entry)"
              v-on="rowEvents"
            />
          </section>
          <Collapsible v-if="deferred.length" v-model:open="showSnoozed"
            ><CollapsibleTrigger as-child
              ><Button variant="ghost"
                ><Clock3 :size="15" />稍后提醒 {{ deferred.length
                }}<ChevronDown :size="14" /></Button></CollapsibleTrigger
            ><CollapsibleContent
              ><WorkEntryRow
                v-for="entry in deferred"
                :key="entry.id"
                v-bind="rowBinding(entry)"
                v-on="rowEvents" /></CollapsibleContent
          ></Collapsible>
          <div v-if="!rows.length && !center.error && snap" class="nc-empty">
            <component :is="filtered ? Search : CheckCircle2" :size="28" />
            <h3>{{ filtered ? '当前筛选无匹配' : empty.title }}</h3>
            <p v-if="filtered && primary === 'todo'">全部待办 {{ snap.summary.actionable_total }} 项</p>
            <Button v-if="filtered" size="sm" variant="soft" @click="clearFilters">清除筛选</Button>
            <div v-else class="nc-tools">
              <Button v-if="primary !== 'info'" size="sm" variant="ghost" @click="navigate({ view: 'info' })"
                ><Inbox :size="14" />查看知会</Button
              ><Button
                v-if="primary !== 'history'"
                size="sm"
                variant="ghost"
                @click="navigate({ view: 'history' })"
                >查看历史</Button
              >
            </div>
          </div>
        </template>
        <footer v-if="snap?.next_cursor || center.query.cursor" class="nc-page-controls">
          <Button
            v-if="center.query.cursor"
            size="sm"
            variant="outline"
            @click="navigate({ cursor: undefined })"
            >回到首页</Button
          ><Button
            v-if="snap?.next_cursor"
            size="sm"
            variant="outline"
            @click="navigate({ cursor: snap.next_cursor })"
            >下一页</Button
          >
        </footer>
      </section>
      <aside v-if="!compact" class="surface-l1 nc-focus">
        <WorkEntryDetail v-if="center.selected" :entry="center.selected" @close="close" />
        <div v-else class="nc-empty">
          <ListTodo :size="28" />
          <h2>{{ loadingEntry ? '正在读取事项' : center.detailError || '选择事项查看详情' }}</h2>
        </div>
      </aside>
    </div>
    <Drawer
      :open="drawerOpen"
      @update:open="
        (v) => {
          if (!v) void close()
        }
      "
      ><DrawerContent
        :side="width < 640 ? 'bottom' : 'right'"
        class="nc-detail-sheet"
        :show-close-button="false"
        @close-auto-focus.prevent="restoreFocus"
        ><DrawerTitle class="sr-only">事项预览</DrawerTitle
        ><DrawerDescription class="sr-only">业务事实、最近经过与办理入口</DrawerDescription
        ><span v-if="width < 640" class="nc-grip" /><WorkEntryDetail
          v-if="center.selected"
          :entry="center.selected"
          @close="close" /></DrawerContent
    ></Drawer>
    <p v-if="compact && center.detailError && !center.selected" role="alert" class="nc-alert">
      {{ center.detailError }}
    </p>
    <Transition name="nc-batch"
      ><div v-if="selected.length" class="nc-batch glass-float" role="toolbar" aria-label="批量操作">
        <strong>已选 {{ selected.length }} 项</strong
        ><Button size="sm" variant="ghost" @click="checked = visible.map((i) => i.id)">全选本页</Button
        ><Button size="sm" variant="ghost" :disabled="center.personalBusy" @click="batch('read')"
          >标为已读</Button
        ><Button
          size="sm"
          variant="ghost"
          :disabled="center.personalBusy || !selected.some((i) => i.can_act_now)"
          @click="batch('snooze')"
          >稍后 1 小时</Button
        ><TooltipProvider
          ><Tooltip
            ><TooltipTrigger as-child
              ><span tabindex="0"
                ><Button
                  size="sm"
                  variant="ghost"
                  :disabled="center.personalBusy || !eligibleArchive"
                  @click="batch('archive')"
                  >归档</Button
                ></span
              ></TooltipTrigger
            ><TooltipContent>{{
              eligibleArchive ? '归档所选事项' : '活跃待办需在原业务办理完成后才能结案'
            }}</TooltipContent></Tooltip
          ></TooltipProvider
        ><Button size="sm" variant="ghost" @click="checked = []">取消</Button>
      </div></Transition
    >
  </div>
</template>

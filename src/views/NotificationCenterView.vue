<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ListTodo, UserRound, Users, Clock3, Inbox, History, RefreshCw, Search, SlidersHorizontal, CheckCheck } from '@lucide/vue'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { useWorkCenterStore, defaultWorkQuery } from '@/stores/workCenter'
import WorkEntryRow from '@/features/work-center/WorkEntryRow.vue'
import WorkEntryDetail from '@/features/work-center/WorkEntryDetail.vue'
import WorkCenterHealth from '@/features/work-center/WorkCenterHealth.vue'
import { workHealth } from '@/features/work-center/health'
import type { WorkView } from '@/features/work-center/types'
import { formatBusinessDateTime } from '@/lib/dateTime'
import PageHeader from '@/components/common/PageHeader.vue'
import Button from '@/components/ui/button/Button.vue'
const center = useWorkCenterStore(), route = useRoute(), router = useRouter()
const root = ref<HTMLElement>(), compact = ref(false), settingsOpen = ref(false), showSnoozed = ref(false)
const search = ref(''), announcement = ref('')
let observer: ResizeObserver | undefined, trigger: HTMLElement | null = null
function preserveListPosition() {
  void nextTick(() => { center.workspaceEngaged = !!root.value?.querySelector('.nc-list-panel input:focus') || (root.value?.querySelector('.nc-list-scroll')?.scrollTop ?? 0) > 32 })
}
function restoreFocus() { trigger?.focus() }
const navigation = [
  { key: 'todo', label: '待办总览', icon: ListTodo, count: 'actionable_total' }, { key: 'assigned', label: '指派给我', icon: UserRound, count: 'assigned_total' },
  { key: 'team', label: '团队队列', icon: Users, count: 'team_queue_total' }, { key: 'waiting', label: '我在等待', icon: Clock3, count: 'waiting_total' },
  { key: 'info', label: '知会消息', icon: Inbox, count: 'info_unread_total' }, { key: 'history', label: '历史记录', icon: History, count: '' },
] as const
const clock = computed(() => Date.parse(center.snapshot?.context.server_time || new Date().toISOString()))
const snoozed = computed(() => (center.snapshot?.items ?? []).filter(item => item.personal.snoozed_until && Date.parse(item.personal.snoozed_until) > clock.value))
const items = computed(() => (center.snapshot?.items ?? []).filter(item => !snoozed.value.includes(item)).sort((a, b) => Number(b.personal.pinned) - Number(a.personal.pinned)))
const filtered = computed(() => center.query.factory_scope !== 'authorized' || center.query.module || center.query.q || center.query.due !== 'all' || center.query.unread_only)
function navigateQuery(values: Record<string, string | undefined>) { return router.replace({ query: { ...route.query, cursor: undefined, ...values } }) }
async function choose(id: string) { trigger = document.activeElement as HTMLElement; await router.replace({ query: { ...route.query, entry: id } }) }
async function close() { center.selected = null; await router.replace({ query: { ...route.query, entry: undefined } }); await nextTick(); trigger?.focus() }
async function applyRoute() {
  const view = String(route.query.view || 'todo') as WorkView
  const value = { ...defaultWorkQuery(), view: navigation.some(item => item.key === view) ? view : 'todo', factory_scope: String(route.query.factory || 'authorized'), module: String(route.query.module || ''), q: String(route.query.q || ''), due: String(route.query.due || 'all'), unread_only: route.query.unread === '1', cursor: route.query.cursor ? String(route.query.cursor) : undefined }
  search.value = value.q
  await center.setQuery(value)
  announcement.value = `当前筛选 ${center.snapshot?.query.filtered_total ?? 0} 项`
  if (typeof route.query.entry === 'string') await center.selectEntry(route.query.entry)
}
watch(() => route.query, applyRoute)
onMounted(() => { center.workspaceOpen = true; center.panelOpen = false; void applyRoute(); observer = new ResizeObserver(entries => { compact.value = (entries[0]?.contentRect.width ?? 1200) < 880 }); if (root.value) observer.observe(root.value) })
onUnmounted(() => { observer?.disconnect(); center.workspaceOpen = false; center.workspaceEngaged = false })
</script>

<template>
  <div ref="root" class="app-page nc-workspace" data-yl-help="work-center.overview">
    <PageHeader title="事项工作台" description="与我相关 · 全部授权责任范围">
      <template #actions><Button variant="outline" :disabled="center.syncing" @click="center.refresh()"><RefreshCw :size="16" :class="{ 'nc-spinning': center.syncing }" />刷新</Button><Button variant="outline" aria-label="声音与提醒设置" :aria-expanded="settingsOpen" @click="settingsOpen = !settingsOpen"><SlidersHorizontal :size="16" />提醒设置</Button></template>
    </PageHeader>
    <div class="nc-summary-band"><strong>现在有 <b>{{ center.summary?.actionable_total ?? '—' }}</b> 项可处理</strong><span v-if="center.summary?.snoozed_total">其中 {{ center.summary.snoozed_total }} 项已设稍后提醒</span><span class="nc-sync">{{ center.snapshot ? '上次同步 ' + formatBusinessDateTime(center.snapshot.health.as_of) : '正在读取当前责任' }}</span></div>
    <div v-if="center.error" class="nc-alert" role="alert">{{ center.error }}<button :disabled="center.syncing" @click="center.refresh()">重试同步</button></div>
    <WorkCenterHealth v-else :snapshot="center.snapshot" :syncing="center.syncing" @retry="center.refresh()" />
    <div v-if="settingsOpen" class="nc-preferences"><label><input type="checkbox" :checked="center.preferences.sound_enabled" @change="center.savePreferences({ sound_enabled: ($event.target as HTMLInputElement).checked })" />声音提醒</label><label>弹窗范围<select :value="center.preferences.toast_level" @change="center.savePreferences({ toast_level: ($event.target as HTMLSelectElement).value as 'assigned' | 'all_tasks' | 'none' })"><option value="assigned">仅指派给我</option><option value="all_tasks">当前责任（含团队）</option><option value="none">关闭弹窗</option></select></label><p>初次载入和普通知会保持安静；稍后提醒仍保留责任总数。</p></div>
    <div class="nc-metrics"><span>指派给我 <b>{{ center.summary?.assigned_total ?? '—' }}</b></span><span>团队队列 <b>{{ center.summary?.team_queue_total ?? '—' }}</b></span><span>已逾期 <b>{{ center.summary?.overdue_total ?? '—' }}</b></span><span>未读知会 <b>{{ center.summary?.info_unread_total ?? '—' }}</b></span></div>
    <div class="nc-layout">
      <nav class="nc-navigation" aria-label="事项视图"><button v-for="item in navigation" :key="item.key" :class="{ active: center.query.view === item.key }" :aria-current="center.query.view === item.key ? 'page' : undefined" @click="navigateQuery({ view: item.key, entry: undefined })"><component :is="item.icon" :size="17" /><span>{{ item.label }}</span><b v-if="item.count">{{ center.summary?.[item.count] ?? '—' }}</b></button></nav>
      <section class="nc-list-panel" aria-label="事项列表" @focusin="preserveListPosition" @focusout="preserveListPosition">
        <form class="nc-filters" @submit.prevent="navigateQuery({ q: search || undefined })"><label class="nc-search"><Search :size="16" /><input v-model="search" aria-label="搜索姓名、账号、单号或关键词" placeholder="搜索姓名 / 账号 / 单号 / 关键词" /><button type="submit">搜索</button></label><div class="nc-filter-row"><select aria-label="厂区筛选" :value="center.query.factory_scope" @change="navigateQuery({ factory: ($event.target as HTMLSelectElement).value })"><option value="authorized">全部授权厂区</option><option v-for="[id, label] in [['huakang-a','华康A'],['huakang-b','华康B'],['huakang-c','华康C'],['huakang-d','华康D'],['huadeng','华登'],['huaxing','华兴']]" :key="id" :value="id">{{ label }}</option></select><select aria-label="业务模块" :value="center.query.module" @change="navigateQuery({ module: ($event.target as HTMLSelectElement).value || undefined })"><option value="">全部模块</option><option value="molding">啤办</option><option value="internal_quote">内部报价</option><option value="carton_supplier">供应商送货</option><option value="account_requests">账户申请</option><option value="identity">任职知会</option></select><select aria-label="期限筛选" :value="center.query.due" @change="navigateQuery({ due: ($event.target as HTMLSelectElement).value })"><option value="all">全部期限</option><option value="overdue">已逾期</option><option value="today">今日到期</option><option value="none">未设期限</option></select><label><input type="checkbox" :checked="center.query.unread_only" @change="navigateQuery({ unread: ($event.target as HTMLInputElement).checked ? '1' : undefined })" />未读</label></div></form>
        <div class="nc-list-heading"><span>{{ filtered ? '当前筛选' : navigation.find(item => item.key === center.query.view)?.label }} · {{ center.snapshot?.query.filtered_total ?? '—' }} 项</span><button v-if="center.snapshot?.items.length" @click="center.markVisibleRead()"><CheckCheck :size="14" />本页已读</button><button v-if="filtered" @click="router.replace({ query: { view: center.query.view } })">清除筛选</button></div>
        <button v-if="center.pendingRefresh" class="nc-new-items" @click="center.pendingRefresh = false; center.refresh()">有新事项，点击查看</button>
        <div class="nc-list-scroll" @scroll.passive="preserveListPosition"><div v-if="center.loading" aria-label="正在加载事项" class="nc-skeletons"><div v-for="i in 4" :key="i" /></div><template v-else><WorkEntryRow v-for="entry in items" :key="entry.id" :entry="entry" :selected="center.selected?.id === entry.id" @select="choose" /><div v-if="!items.length" class="nc-empty"><Inbox :size="30" /><h2>{{ center.error && !center.snapshot ? '当前无法读取事项' : workHealth(center.snapshot)?.warning ? '暂时无法核实全部事项' : filtered ? '当前筛选没有事项' : snoozed.length ? '当前优先列表为空' : center.query.view === 'todo' ? '已接入业务范围内暂无待办' : '当前视图暂无事项' }}</h2><p>{{ snoozed.length ? `另有 ${snoozed.length} 项稍后提醒` : '可查看知会与历史，或调整筛选范围。' }}</p></div><template v-if="snoozed.length"><button class="nc-snoozed-toggle" :aria-expanded="showSnoozed" @click="showSnoozed = !showSnoozed"><Clock3 :size="15" />稍后提醒 {{ snoozed.length }} 项</button><WorkEntryRow v-for="entry in showSnoozed ? snoozed : []" :key="entry.id" :entry="entry" :selected="center.selected?.id === entry.id" @select="choose" /></template></template></div>
        <footer class="nc-list-footer"><span>责任由当前源业务核验</span><Button v-if="center.query.cursor" variant="ghost" size="sm" @click="navigateQuery({ cursor: undefined })">回到第一页</Button><Button v-if="center.snapshot?.next_cursor" variant="outline" size="sm" @click="router.replace({ query: { ...route.query, cursor: center.snapshot.next_cursor } })">下一页</Button></footer>
      </section>
      <aside v-if="!compact" class="nc-detail-panel"><WorkEntryDetail v-if="center.selected" :entry="center.selected" @close="close" /><div v-else class="nc-detail-placeholder"><ListTodo :size="28" /><h2>先预览，再处理</h2><p>{{ center.detailError || '选择一项，查看当前阶段、责任依据与最近经过。' }}</p></div></aside>
    </div>
    <p class="nc-coverage">已接入：啤办、内部报价、账户申请、供应商送货、任职知会。其他模块尚未纳入本页计数。</p>
    <span class="sr-only" aria-live="polite">{{ announcement }}</span>
    <DialogRoot :open="compact && !!center.selected" @update:open="value => { if (!value) void close() }"><DialogPortal><DialogOverlay class="nc-sheet-overlay" /><DialogContent class="nc-sheet" @close-auto-focus.prevent="restoreFocus"><DialogTitle class="sr-only">事项详情</DialogTitle><DialogDescription class="sr-only">查看当前责任，然后前往原业务处理。</DialogDescription><WorkEntryDetail v-if="center.selected" :entry="center.selected" @close="close" /></DialogContent></DialogPortal></DialogRoot>
  </div>
</template>

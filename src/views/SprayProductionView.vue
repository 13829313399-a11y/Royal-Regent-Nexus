<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft,
  CalendarClock,
  ClipboardList,
  FlaskConical,
  Gauge,
  HardHat,
  Layers,
  Package,
  RefreshCw,
  Receipt,
  Upload,
} from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { useAppStore } from '@/stores/app'
import { useSprayWorkspace, factories } from '@/features/spray-production/workspace'
import { useSprayMotionPreference } from '@/features/spray-production/composables/useSprayMotionPreference'
import BatchInspector from '@/features/spray-production/components/BatchInspector.vue'
import ExportRecords from '@/features/spray-production/components/ExportRecords.vue'
import SprayInteractions from '@/features/spray-production/components/SprayInteractions.vue'
import SpraySkeleton from '@/features/spray-production/components/ui/SpraySkeleton.vue'
import '@/features/spray-production/styles/tokens.css'
import '@/features/spray-production/styles/motion.css'
import '@/features/spray-production/styles/polish.css'
import '@/features/spray-production/workspace.css'
const route = useRoute(), router = useRouter(), app = useAppStore(), store = useSprayWorkspace()
const { motionAllowed } = useSprayMotionPreference()
/* 被动效偏好影响的不只是本组件：子组件按钮的扫光也据此关闭。 */
provide('sprayQuiet', motionAllowed)
const navRoot = ref<HTMLElement | null>(null)
const scope = computed(() => String(route.query.factory ?? app.activeFactoryId))
const root = '/modules/production/spray-production'
/* 九个业务入口按工作流分组：组只是导航分区，不改变任何页面、路由或权限。 */
const navGroups = [
  { label: '总览', items: [{ path: 'overview', label: '生产总览', hint: '沿实体批次查看工序、交接与下一步', icon: Gauge }] },
  { label: '执行', items: [
    { path: 'orders', label: '工单交付', hint: '工单、实体部件与来料交付计量', icon: Package },
    { path: 'schedule', label: '排产画布', hint: '资源与订单视角的排产草案', icon: CalendarClock },
    { path: 'reports', label: '现场报工', hint: '按班次增量记录产量与在制', icon: ClipboardList },
  ] },
  { label: '账务', items: [
    { path: 'wip', label: '在制与质量', hint: '在制状态与质量处置', icon: Layers },
    { path: 'logistics', label: '收发交接', hint: '来料、送货、退回与容器往来', icon: Receipt },
    { path: 'finance', label: '经营核算', hint: '工价、采购耗用与月结对账', icon: FlaskConical },
  ] },
  { label: '资料', items: [
    { path: 'master', label: '资料中心', hint: '本厂资源、班次与工艺资料', icon: HardHat },
    { path: 'imports', label: '历史导入', hint: '原始资料映射与历史证据归档', icon: Upload },
  ] },
]
const tabs = navGroups.flatMap(group => group.items)
const activePath = computed(() => String(route.path).slice(root.length + 1).split('/')[0])
const current = computed(() => tabs.find(tab => tab.path === activePath.value) ?? tabs[0]!)
const currentGroup = computed(() => navGroups.find(group => group.items.some(item => item.path === activePath.value))?.label ?? '')
const scopeName = computed(() => factories.find(f => f.id === scope.value)?.name ?? '')
const grouped = computed(() => scope.value === 'group')
/* 滑动胶囊指示器：位置与尺寸取真实选中链接的几何值，
   桌面纵向导航与窄屏横向滚动导航共用同一实现。
   坐标必须是“导航容器内部坐标”（即相对容器 border box 的滚动位置），
   不能用视口坐标：工作区顶部条的高度会随厂区状态文案、骨架屏与换行变化，
   一旦用视口坐标，上方任何布局位移都会让已存下的数值变成陈旧值并导致胶囊错位。 */
const activeIndex = computed(() => tabs.findIndex(tab => tab.path === activePath.value))
const navPill = ref({ left: 0, top: 0, width: 0, height: 0, ready: false })
let navObserver: ResizeObserver | undefined
function measureNav() {
  const container = navRoot.value
  const selected = container?.querySelector<HTMLElement>('a.router-link-active')
  if (!container || !selected) { navPill.value = { ...navPill.value, ready: false }; return }
  const outer = container.getBoundingClientRect()
  const rect = selected.getBoundingClientRect()
  if (!rect.width || !rect.height) { navPill.value = { ...navPill.value, ready: false }; return }
  navPill.value = {
    /* 内部坐标 = 视口相对位置 + 自身滚动量；容器与内容的视口偏移在相减时抵消。 */
    left: rect.left - outer.left + container.scrollLeft,
    top: rect.top - outer.top + container.scrollTop,
    /* 宽度按可用内容宽度夹紧，避免指示器撑出横向滚动条后再次触发测量。 */
    width: Math.min(rect.width, Math.max(0, container.clientWidth - 2)),
    height: rect.height,
    ready: true,
  }
}
/* 布局稳定后再测一次并做防抖校验：ResizeObserver 只能看到尺寸变化，
   上方元素（顶部条换行、读取状态文案切换）引起的纯位移动它不会触发。 */
let navFrame = 0
function scheduleNavMeasure() {
  if (navFrame) cancelAnimationFrame(navFrame)
  navFrame = requestAnimationFrame(() => { navFrame = 0; measureNav() })
}
onMounted(() => {
  if (typeof ResizeObserver !== 'undefined') navObserver = new ResizeObserver(scheduleNavMeasure)
  if (navRoot.value) {
    navObserver?.observe(navRoot.value)
    navRoot.value.querySelectorAll('a, .spray-nav-label').forEach(element => navObserver?.observe(element))
  }
  window.addEventListener('resize', scheduleNavMeasure)
  /* 字体与完整布局就绪后再校准，避免首帧测量落在换行之前。 */
  scheduleNavMeasure()
  void document.fonts?.ready?.then(scheduleNavMeasure)
})
onBeforeUnmount(() => {
  navObserver?.disconnect()
  if (navFrame) cancelAnimationFrame(navFrame)
  window.removeEventListener('resize', scheduleNavMeasure)
})
watch(scope, value => store.load(value), { immediate: true })
watch([activePath, () => store.summary?.revision], scheduleNavMeasure)
const timer = window.setInterval(() => { if (!document.hidden && !store.busy) void store.load() }, 60000)
onBeforeUnmount(() => { window.clearInterval(timer); store.clear() })
function changeFactory(event: Event) { void router.replace({ query: { factory: (event.target as HTMLSelectElement).value } }) }
</script>
<template>
  <div class="spray-workspace" :class="{ 'spray-quiet': !motionAllowed }">
    <SprayInteractions />
    <header class="spray-topbar">
      <div class="spray-topbar-main">
        <RouterLink :to="{ path: '/modules/production', query: { factory: scope } }" class="spray-back" aria-label="返回生产部"><ArrowLeft :size="18" aria-hidden="true" /><span class="spray-back-label">生产部</span></RouterLink>
        <h1>喷油部生产管理</h1>
      </div>
      <div class="spray-topbar-scope">
        <span class="spray-scope-chip" :class="{ pending: !scopeName }">{{ scopeName ? '执行厂区 · ' + scopeName : grouped ? '集团视图 · 不记库存' : '尚未选择执行厂区' }}</span>
        <span v-if="store.loading" class="spray-status loading" role="status"><i class="spray-dot pulse" aria-hidden="true" />正在读取本厂数据…</span>
        <span v-else class="spray-updated" role="status"><i class="spray-dot live pulse" aria-hidden="true" />{{ store.summary ? '更新于 ' + new Date(store.summary.as_of).toLocaleTimeString('zh-CN') : '等待数据' }}</span>
        <Button variant="ghost" size="sm" class="spray-icon-btn" :disabled="store.loading" aria-label="刷新喷油数据" @click="store.load()"><RefreshCw :size="16" :class="{ 'spray-spin': store.loading }" aria-hidden="true" /></Button>
      </div>
    </header>
    <div class="spray-workspace-bar">
      <label class="spray-field-label"><span>执行厂区</span><select :value="scope" :disabled="store.busy" aria-label="执行厂区" @change="changeFactory"><option value="group">集团视图（不记库存）</option><option v-for="f in factories" :key="f.id" :value="f.id">{{ f.name }}</option></select></label>
      <ExportRecords />
      <p class="spray-help">当前页：{{ current.hint }}。资料按执行厂区独立记账，工单与委托客户分开。</p>
    </div>
    <div class="spray-body">
      <nav ref="navRoot" class="spray-nav" aria-label="喷油工作区" @scroll="measureNav">
        <span
          class="spray-nav-pill"
          :style="{
            '--spray-nav-left': navPill.left + 'px',
            '--spray-nav-top': navPill.top + 'px',
            '--spray-nav-width': navPill.width + 'px',
            '--spray-nav-height': navPill.height + 'px',
            opacity: navPill.ready ? 1 : 0,
          }"
          aria-hidden="true"
        />
        <div v-for="group in navGroups" :key="group.label" class="spray-nav-group">
          <h2 class="spray-nav-label">{{ group.label }}</h2>
          <RouterLink v-for="tab in group.items" :key="tab.path" :to="{ path: root + '/' + tab.path, query: { factory: scope } }" :class="{ 'router-link-active': activePath === tab.path }" :aria-current="activePath === tab.path ? 'page' : undefined" :style="{ '--spray-enter-delay': activeIndex * 24 + 'ms' }" class="spray-enter"><component :is="tab.icon" :size="16" aria-hidden="true" /><span>{{ tab.label }}</span></RouterLink>
        </div>
        <div class="spray-nav-current">
          <strong>{{ currentGroup }} · {{ current.label }}</strong>
          <span>{{ current.hint }}</span>
          <small>四厂共用业务组件，按执行厂区独立记账与校验。</small>
        </div>
      </nav>
      <main id="spray-main" class="spray-main">
        <div v-if="store.error" role="alert" class="spray-message spray-error"><span>{{ store.error }}</span><Button variant="outline" size="sm" @click="store.load()">重试读取</Button></div>
        <div v-if="store.notice" role="status" class="spray-message spray-success"><i class="spray-dot" aria-hidden="true" /><span>{{ store.notice }}</span></div>
        <div v-if="store.truncated" role="alert" class="spray-message spray-warn">当前加载各类最近 1,000 条记录。大数据检索请使用分页接口，当前汇总明细并非完整账册。</div>
        <div v-if="!factories.some(f => f.id === scope)" class="spray-empty"><h2>选择执行厂区</h2><p>华兴、华康 A、华康 B、华登各自维护喷油资料。集团视图不记库存，也不下发任何厂区成本。</p></div>
        <SpraySkeleton v-else-if="store.loading && !store.summary" class="spray-empty" />
        <RouterView v-else-if="store.summary" :key="scope" />
      </main>
      <BatchInspector />
    </div>
  </div>
</template>

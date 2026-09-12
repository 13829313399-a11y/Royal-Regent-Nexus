<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { ArrowLeft, RefreshCw } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { useAppStore } from '@/stores/app'
import { useSprayWorkspace, factories } from '@/features/spray-production/workspace'
import BatchInspector from '@/features/spray-production/components/BatchInspector.vue'
import ExportRecords from '@/features/spray-production/components/ExportRecords.vue'
import '@/features/spray-production/workspace.css'
const route = useRoute(), router = useRouter(), app = useAppStore(), store = useSprayWorkspace()
const scope = computed(() => String(route.query.factory ?? app.activeFactoryId))
const root = '/modules/production/spray-production'
/* 九个业务入口按工作流分组：组只是导航分区，不改变任何页面、路由或权限。 */
const navGroups = [
  { label: '总览', items: [{ path: 'overview', label: '生产总览', hint: '沿实体批次查看工序、交接与下一步' }] },
  { label: '执行', items: [
    { path: 'orders', label: '工单交付', hint: '工单、实体部件与来料交付计量' },
    { path: 'schedule', label: '排产画布', hint: '资源与订单视角的排产草案' },
    { path: 'reports', label: '现场报工', hint: '按班次增量记录产量与在制' },
  ] },
  { label: '账务', items: [
    { path: 'wip', label: '在制与质量', hint: '在制状态与质量处置' },
    { path: 'logistics', label: '收发交接', hint: '来料、送货、退回与容器往来' },
    { path: 'finance', label: '经营核算', hint: '工价、采购耗用与月结对账' },
  ] },
  { label: '资料', items: [
    { path: 'master', label: '资料中心', hint: '本厂资源、班次与工艺资料' },
    { path: 'imports', label: '历史导入', hint: '原始资料映射与历史证据归档' },
  ] },
]
const tabs = navGroups.flatMap(group => group.items)
const activePath = computed(() => String(route.path).slice(root.length + 1).split('/')[0])
const current = computed(() => tabs.find(tab => tab.path === activePath.value) ?? tabs[0]!)
const currentGroup = computed(() => navGroups.find(group => group.items.some(item => item.path === activePath.value))?.label ?? '')
const scopeName = computed(() => factories.find(f => f.id === scope.value)?.name ?? '')
const grouped = computed(() => scope.value === 'group')
watch(scope, value => store.load(value), { immediate: true })
const timer = window.setInterval(() => { if (!document.hidden && !store.busy) void store.load() }, 60000)
onBeforeUnmount(() => { window.clearInterval(timer); store.clear() })
function changeFactory(event: Event) { void router.replace({ query: { factory: (event.target as HTMLSelectElement).value } }) }
</script>
<template>
  <div class="spray-workspace">
    <header class="spray-topbar">
      <div class="spray-topbar-main">
        <RouterLink :to="{ path: '/modules/production', query: { factory: scope } }" class="spray-back" aria-label="返回生产部"><ArrowLeft :size="18" aria-hidden="true" /><span class="spray-back-label">生产部</span></RouterLink>
        <h1>喷油部生产管理</h1>
      </div>
      <div class="spray-topbar-scope">
        <span class="spray-scope-chip" :class="{ pending: !scopeName }">{{ scopeName ? '执行厂区 · ' + scopeName : grouped ? '集团视图 · 不记库存' : '尚未选择执行厂区' }}</span>
        <span v-if="store.loading" class="spray-status loading" role="status">正在读取本厂数据…</span>
        <span v-else class="spray-updated" role="status">{{ store.summary ? '更新于 ' + new Date(store.summary.as_of).toLocaleTimeString('zh-CN') : '等待数据' }}</span>
        <Button variant="ghost" size="sm" :disabled="store.loading" aria-label="刷新喷油数据" @click="store.load()"><RefreshCw :size="16" aria-hidden="true" /></Button>
      </div>
    </header>
    <div class="spray-workspace-bar">
      <label class="spray-field-label"><span>执行厂区</span><select :value="scope" :disabled="store.busy" aria-label="执行厂区" @change="changeFactory"><option value="group">集团视图（不记库存）</option><option v-for="f in factories" :key="f.id" :value="f.id">{{ f.name }}</option></select></label>
      <ExportRecords />
      <p class="spray-help">当前页：{{ current.hint }}。资料按执行厂区独立记账，工单与委托客户分开。</p>
    </div>
    <div class="spray-body">
      <nav class="spray-nav" aria-label="喷油工作区">
        <div v-for="group in navGroups" :key="group.label" class="spray-nav-group">
          <h2 class="spray-nav-label">{{ group.label }}</h2>
          <RouterLink v-for="tab in group.items" :key="tab.path" :to="{ path: root + '/' + tab.path, query: { factory: scope } }" :class="{ 'router-link-active': activePath === tab.path }" :aria-current="activePath === tab.path ? 'page' : undefined">{{ tab.label }}</RouterLink>
        </div>
        <div class="spray-nav-current">
          <strong>{{ currentGroup }} · {{ current.label }}</strong>
          <span>{{ current.hint }}</span>
          <small>四厂共用业务组件，按执行厂区独立记账与校验。</small>
        </div>
      </nav>
      <main id="spray-main" class="spray-main">
        <div v-if="store.error" role="alert" class="spray-message spray-error"><span>{{ store.error }}</span><Button variant="outline" size="sm" @click="store.load()">重试读取</Button></div>
        <div v-if="store.notice" role="status" class="spray-message">{{ store.notice }}</div>
        <div v-if="store.truncated" role="alert" class="spray-message spray-warn">当前加载各类最近 1,000 条记录。大数据检索请使用分页接口，当前汇总明细并非完整账册。</div>
        <div v-if="!factories.some(f => f.id === scope)" class="spray-empty"><h2>选择执行厂区</h2><p>华兴、华康 A、华康 B、华登各自维护喷油资料。集团视图不记库存，也不下发任何厂区成本。</p></div>
        <div v-else-if="store.loading && !store.summary" class="spray-empty" role="status">正在读取工单、批次与资源…</div>
        <RouterView v-else-if="store.summary" :key="scope" />
      </main>
      <BatchInspector />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ArrowLeft, Search, RefreshCw, LayoutDashboard, CalendarRange, ClipboardCheck, PackageCheck, PaintBucket, ChartNoAxesCombined, SlidersHorizontal, FileInput, History, ArrowRight, X } from '@lucide/vue'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import { Button } from '@/components/ui/button'
import WorkspaceDialog from './components/WorkspaceDialog.vue'
import ActionQuestion from './components/ActionQuestion.vue'
import OrderPassport from './components/OrderPassport.vue'
import { provideSprayWorkspace } from './workspace'
import { registerSprayNavigationGuard } from './navigationGuard'
import { SPRAY_BASE, SPRAY_NAV, SPRAY_FACTORIES, FACTORY_NAMES, type Demand } from './contracts'
import './workspace.css'
const w = provideSprayWorkspace(), route = useRoute(), router = useRouter()
const icons = { LayoutDashboard, CalendarRange, ClipboardCheck, PackageCheck, PaintBucket, ChartNoAxesCombined, SlidersHorizontal }
const current = computed(() => SPRAY_NAV.find(item => route.path.startsWith(`${SPRAY_BASE}/${item.path}`)))
const search = ref(''), searchOpen = ref(false), found = ref<Demand[]>([])
watch(w.contextVersion,()=>{found.value=[];searchOpen.value=false;search.value=''})
const leaveOpen = ref(false), savingDraft = ref(false)
let leaveResolver: ((value: boolean) => void) | null = null
function guard() {
  if (!w.dirty.value) return true
  leaveOpen.value = true
  return new Promise<boolean>(resolve => { leaveResolver = resolve })
}
const unregisterGuard = registerSprayNavigationGuard(guard)
function finishLeave(proceed: boolean) { if (proceed) w.dirty.value = false; leaveOpen.value = false; leaveResolver?.(proceed); leaveResolver = null }
async function saveAndLeave() {
  if (!w.saveDraft.value) return
  savingDraft.value = true
  try { if (await w.saveDraft.value()) finishLeave(true) } catch (cause) { w.error.value = w.explain(cause) } finally { savingDraft.value = false }
}
function beforeUnload(event: BeforeUnloadEvent) { if (w.dirty.value || [...w.pending.values()].some(op => op.state === 'uncertain')) { event.preventDefault(); event.returnValue = '' } }
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => { unregisterGuard(); window.removeEventListener('beforeunload', beforeUnload); leaveResolver?.(false) })
async function find() {
  if (!search.value.trim()) return
  searchOpen.value = true
  try { found.value = (await w.query<Demand[]>('demands', { search: search.value, page_size: 50 }, 'global-search')).data } catch (cause) { w.error.value = w.explain(cause) }
}
async function switchFactory(event: Event) {
  const factory = (event.target as HTMLSelectElement).value
  await router.push({ path: route.params.id ? `${SPRAY_BASE}/finance/settlements` : route.path, query: { factory } })
  ;(event.target as HTMLSelectElement).value=w.factory.value??''
}
</script>
<template>
  <div class="spray-workspace spray-shell" :class="{ 'has-passport': w.passportId.value }">
    <header class="spray-identity" data-yl-help="spray-production.overview">
      <RouterLink class="spray-brand" :to="{ path: '/modules/production', query: { factory: w.factory.value } }" aria-label="返回生产部"><img src="/brand/huadeng_group_dynamic_logo_topbar.svg" alt="华登集团" /><span><strong>喷油生产管理</strong><small>ROYAL REGENT NEXUS</small></span></RouterLink>
      <div class="spray-identity__divider" />
      <label class="spray-factory"><span class="spray-status-dot" /><select :value="w.factory.value ?? ''" aria-label="执行工厂" @change="switchFactory"><option disabled value="">选择工厂</option><option v-for="factory in SPRAY_FACTORIES" :key="factory" :value="factory">{{ FACTORY_NAMES[factory] }} · 喷油部</option></select></label>
      <label class="spray-business-date"><span>业务日期</span><input v-model="w.businessDate.value" type="date" aria-label="业务日期" /></label>
      <form class="spray-search" role="search" @submit.prevent="find"><Search :size="16" /><input v-model="search" aria-label="查找订单" placeholder="查找订单、货号…" /><kbd>↵</kbd></form>
      <RouterLink class="spray-back" :to="{ path: '/modules/production', query: { factory: w.factory.value } }"><ArrowLeft :size="16" /><span>生产部</span></RouterLink>
      <AccountMenu compact />
    </header>
    <nav class="spray-rail" aria-label="喷油工作区导航">
      <RouterLink v-for="nav in SPRAY_NAV" :key="nav.path" :to="{ path: `${SPRAY_BASE}/${nav.path}`, query: { factory: w.factory.value } }" :class="{ active: current?.path === nav.path }" :aria-current="current?.path === nav.path ? 'page' : undefined"><component :is="icons[nav.icon]" :size="21" /><span>{{ nav.short }}</span><span class="spray-rail__tooltip">{{ nav.label }}</span></RouterLink>
      <div class="spray-rail__spacer" />
      <RouterLink v-if="w.can('import')" :to="{ path: `${SPRAY_BASE}/imports`, query: { factory: w.factory.value } }" aria-label="导入中心" :class="{ active: route.path.includes('/imports') }"><FileInput :size="21" /><span>导入</span></RouterLink>
      <RouterLink :to="{ path: `${SPRAY_BASE}/activity`, query: { factory: w.factory.value } }" aria-label="操作记录" :class="{ active: route.path.endsWith('/activity') }"><History :size="21" /><span>记录</span></RouterLink>
    </nav>
    <main class="spray-main">
      <div v-if="!w.valid.value" class="spray-empty spray-empty--full"><h1>请选择明确的执行工厂</h1><p>本工作区支持华兴、华登、华康A、华康B。模块尚未启用时，请返回生产部。</p><RouterLink :to="{ path: '/modules/production', query: route.query }" class="spray-primary">返回生产部</RouterLink></div>
      <div v-else-if="!w.ready.value" class="spray-empty spray-empty--full"><h1>{{ w.error.value ? '工作区暂时无法进入' : '正在确认工作区权限' }}</h1><p>{{ w.error.value || '获取当前工厂的有效授权…' }}</p><Button v-if="w.error.value" variant="outline" @click="w.retryAccess">重新连接</Button></div>
      <template v-else>
        <div v-for="operation in [...w.pending.values()].filter(op => op.state === 'uncertain' && op.factory === w.factory.value)" :key="operation.operation_id" class="spray-alert" role="alert"><span>上次保存结果待核对 · {{ operation.operation_id.slice(0, 8) }}</span><button class="spray-text-button" @click="w.resolveOperation(operation)">查询结果 / 安全重试</button></div>
        <RouterView v-slot="{ Component }"><component :is="Component" :key="`${w.factory.value}:${route.path}`" /></RouterView>
      </template>
    </main>
    <OrderPassport />
    <ActionQuestion />
    <div v-if="w.notification.value" class="spray-toast" role="status"><span>{{ w.notification.value }}</span><button class="spray-icon-button" aria-label="关闭提示" @click="w.notification.value = ''"><X :size="15" /></button></div>
    <WorkspaceDialog :open="leaveOpen" title="保留当前未保存的填写" @close="finishLeave(false)"><p>当前内容属于{{ w.factory.value ? FACTORY_NAMES[w.factory.value] : '原工厂' }}。离开前可保存到原工厂，或放弃这次填写。</p><template #footer><Button variant="outline" @click="finishLeave(false)">继续填写</Button><Button variant="outline" @click="finishLeave(true)">放弃并离开</Button><Button v-if="w.saveDraft.value" :disabled="savingDraft" @click="saveAndLeave">保存到原工厂并离开</Button></template></WorkspaceDialog>
    <WorkspaceDialog :open="searchOpen" title="查找订单" @close="searchOpen = false"><p v-if="!found.length" class="spray-empty">没有匹配的订单</p><button v-for="demand in found" :key="demand.id" class="spray-search-result" @click="w.passportId.value = demand.id; searchOpen = false"><div><strong>{{ demand.document_no }}</strong><span>{{ demand.counterparty }} · {{ demand.lines.map(line => line.item_no).join(' / ') }}</span></div><ArrowRight :size="18" /></button></WorkspaceDialog>
  </div>
</template>

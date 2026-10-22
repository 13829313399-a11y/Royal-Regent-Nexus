<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, onBeforeRouteUpdate } from 'vue-router'
import { ArrowLeft, Building2, BookOpen, LayoutDashboard, History, CalendarRange, ClipboardCheck, Boxes, CalendarCheck2, Settings2, Calculator } from '@lucide/vue'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import CuttingAcceptanceNotice from './CuttingAcceptanceNotice.vue'
import UsageGuideDialog from '@/components/common/UsageGuideDialog.vue'
import { Button } from '@/components/ui/button'
import { cuttingGuideSteps, cuttingGuideTips } from './usageGuide'
import { CUTTING_BASE, CUTTING_FACTORY, CUTTING_WORKSPACES, isCuttingFactory } from './navigation'
import { guardCuttingFactory } from './routes'
import { cuttingApi, type Access } from './api'
import './workspace.css'
import { trackCuttingWrites } from './workspaceRefresh'
const stopTrackingWrites = trackCuttingWrites()

const route = useRoute()
const main=ref<HTMLElement>()
watch(()=>route.path,()=>main.value?.scrollTo?.({top:0,left:0}),{flush:'post'})
const logoUrl = '/brand/huadeng_group_dynamic_logo_topbar.svg'
const samplesAllowed = ref(false)
const validFactory = computed(() => isCuttingFactory(route.query.factory))
const icons = { LayoutDashboard, History, CalendarRange, ClipboardCheck, Boxes, CalendarCheck2, Settings2, Calculator }
const currentTitle = computed(() => CUTTING_WORKSPACES.find(w => route.path.endsWith(`/${w.path}`))?.title ?? '裁床部')
const productionRoute = { path: '/modules/production', query: { factory: CUTTING_FACTORY } }
// Parent beforeEnter does not run for query-only or sibling navigation.
onBeforeRouteUpdate(guardCuttingFactory)
const authorizationEpoch = ref(0), verifying = ref(true), denied = ref(false), authorizationError = ref('')
let accessFingerprint: string | undefined, accessGeneration = 0, alive = true
const fingerprint = (value: Access) => JSON.stringify({ ...value, permissions: [...value.permissions].sort() })
async function revalidate() {
  const ticket = ++accessGeneration
  verifying.value = true; authorizationError.value = ''
  samplesAllowed.value = false
  try {
    const rights = await cuttingApi.access()
    const current = fingerprint(rights)
    if (!alive || ticket !== accessGeneration) return
    if (accessFingerprint !== undefined && current !== accessFingerprint) authorizationEpoch.value++
    accessFingerprint = current; denied.value = false
    samplesAllowed.value = rights.enabled && rights.permissions.includes('read')
  } catch (error) {
    if (!alive || ticket !== accessGeneration) return
    const status = (error as { response?: { status?: number } }).response?.status
    if (status === 401 || status === 403) {
      denied.value = true; authorizationEpoch.value++; accessFingerprint = undefined
      authorizationError.value = '当前账号已无权访问裁床工作区，旧表单已清除。请重新登录或联系授权负责人。'
    } else authorizationError.value = '暂时无法核验裁床权限，填写已保留；重新核验成功后可继续。'
  } finally { if (alive && ticket === accessGeneration) verifying.value = false }
}
function sessionBoundary() {
  denied.value = true; authorizationEpoch.value++; accessFingerprint = undefined
  void revalidate()
}
onMounted(() => {
  window.addEventListener('authorization-context-changed', revalidate)
  window.addEventListener('cutting-authorization-recheck', revalidate)
  window.addEventListener('auth-session-boundary-changed', sessionBoundary)
  void revalidate()
})
onBeforeUnmount(() => {
  stopTrackingWrites()
  alive = false; accessGeneration++
  window.removeEventListener('authorization-context-changed', revalidate)
  window.removeEventListener('cutting-authorization-recheck', revalidate)
  window.removeEventListener('auth-session-boundary-changed', sessionBoundary)
})
</script>

<template>
  <div v-if="validFactory" class="cutting-shell">
    <a class="cutting-skip" href="#cutting-main">跳到工作区内容</a>
    <header class="cutting-header">
      <CuttingAcceptanceNotice :show-samples="samplesAllowed" />
      <RouterLink :to="productionRoute" class="cutting-brand" aria-label="裁床部，返回华康 C 生产部">
        <img :src="logoUrl" alt="华登集团" />
        <span><strong>裁床部</strong><small>华康 C · 生产管理</small></span>
      </RouterLink>
      <RouterLink :to="productionRoute" class="cutting-back"><ArrowLeft :size="16" aria-hidden="true" />生产部</RouterLink>
      <span class="cutting-factory"><Building2 :size="17" aria-hidden="true" />华康 C</span>
      <UsageGuideDialog :title="currentTitle" description="华康 C 裁床部 · 按当前岗位权限办理，原单与更正全程保留。" :steps="cuttingGuideSteps" :tips="cuttingGuideTips">
        <template #trigger><Button variant="outline" class="cutting-help"><BookOpen :size="17" aria-hidden="true" />使用说明</Button></template>
      </UsageGuideDialog>
      <AccountMenu compact />
    </header>
    <nav class="cutting-rail" aria-label="裁床工作区导航">
      <RouterLink v-for="workspace in CUTTING_WORKSPACES" :key="workspace.path"
        :to="{ path: `${CUTTING_BASE}/${workspace.path}`, query: { factory: CUTTING_FACTORY } }"
        :aria-label="workspace.title" :aria-current="route.path === `${CUTTING_BASE}/${workspace.path}` ? 'page' : undefined">
        <component :is="icons[workspace.icon]" :size="21" aria-hidden="true" />
        <span>{{ workspace.path === 'planning' ? '生产排期' : workspace.path === 'reporting' ? '每日填数' : workspace.short }}</span>
      </RouterLink>
    </nav>
    <main ref="main" id="cutting-main" class="cutting-main" tabindex="-1">
      <p v-if="verifying" role="status">正在核验裁床工作区权限…</p>
      <div v-if="authorizationError" role="alert"><p>{{ authorizationError }}</p><button type="button" :disabled="verifying" @click="revalidate">重新核验权限</button></div>
      <div v-show="!verifying && !authorizationError">
        <RouterView v-if="!denied" v-slot="{ Component }"><component :is="Component" :key="`${route.path}:${authorizationEpoch}`" /></RouterView>
      </div>
    </main>
  </div>
</template>

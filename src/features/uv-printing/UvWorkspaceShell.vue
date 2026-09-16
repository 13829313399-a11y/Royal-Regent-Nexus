<script setup lang="ts">
import { computed, provide, ref, watch, shallowRef } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { AlertTriangle, ArrowLeft, RefreshCw, ShieldAlert, Sparkles } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { UV_NAV } from './navigation'
import { useUvWorkspace } from './composables/useUvWorkspace'
import type { UvSummary, UvWorkspaceTransport } from './contracts'
import { realUvTransport } from './transport/provider'
import { SAMPLE_ROLE_IDS, SAMPLE_ROLE_LABELS, type UvSampleRole } from './preview/roles'
import type { UvMemoryStore } from './preview/memoryStore'
import { workspaceFreshnessLabel } from './domain/workspaceFreshness'
import { UV_CONTEXT_KEY, UV_TRANSPORT_KEY, type UvPageContext } from './composables/uvPageContext'
import './styles/workspace.css'

/**
 * UV 工作区壳：厂区是固定业务上下文，不在模块里再造厂区选择器。
 *
 * 正式路由使用真实 transport；只有 DEV 显式开启的 `/__preview/uv-printing`
 * 使用内存样例 transport，并在顶部常驻「样例数据·不写入生产库」。
 * 正式路由拿到 `data_mode: sample` 视为配置错误并停止操作。
 */

const route = useRoute()
const router = useRouter()
const workspace = useUvWorkspace()

const transport = shallowRef<UvWorkspaceTransport>(realUvTransport())
const sampleStore = shallowRef<UvMemoryStore | null>(null)
const transportError = ref<string | null>(null)
const loadingPreview = ref(false)
const sampleRole = ref<UvSampleRole>('manager')
const refreshing = ref(false)
const revision = ref(0)

const isPreview = workspace.isPreview
const businessDate = workspace.business_date
const shift = workspace.shift
const contextViolation = workspace.violation

/**
 * 壳层只读取一次摘要用于导航徽标，页面自己再取各自需要的数据；
 * 两者走同一 transport 与同一份内存事实，不各自维护常量。
 */
const summary = shallowRef<UvSummary | null>(null)
const liveAsOf = ref<string | null>(null)
let summaryGeneration = 0
let summaryController: AbortController | null = null

watch(
  () => [transport.value, businessDate.value, shift.value, revision.value, contextViolation.value, loadingPreview.value, sampleStore.value] as const,
  async () => {
    const generation = ++summaryGeneration
    summaryController?.abort()
    summaryController = null
    if (contextViolation.value || loadingPreview.value || (isPreview.value && !sampleStore.value)) {
      summary.value = null
      if (!isPreview.value) liveAsOf.value = null
      return
    }
    const controller = new AbortController()
    summaryController = controller
    try {
      const response = await transport.value.summary({
        factory_id: 'huakang-a',
        business_date: businessDate.value,
        shift: shift.value === 'all' ? undefined : shift.value,
      }, controller.signal)
      if (generation === summaryGeneration) {
        summary.value = response.data
        if (!isPreview.value) liveAsOf.value = response.meta.as_of
      }
    } catch {
      // 壳层不把摘要失败当成全局错误：页面自己展示失败与重试。
      if (generation === summaryGeneration) {
        summary.value = null
        if (!isPreview.value) liveAsOf.value = null
      }
    } finally {
      if (generation === summaryGeneration) summaryController = null
    }
  },
  { immediate: true },
)

const activeKey = computed(() => String(route.path.split('/').filter(Boolean).pop() ?? 'overview'))
const basePath = computed(() => route.path.split('/').slice(0, 4).join('/') || '/modules/production/uv-printing')
const asOfLabel = computed(() => workspaceFreshnessLabel(isPreview.value, workspace.sampleAsOf.value, liveAsOf.value))

async function ensureTransport() {
  if (isPreview.value) {
    loadingPreview.value = true
    transportError.value = null
    try {
      if (!sampleStore.value) {
        const { loadSampleTransport } = await import('./transport/provider')
        const store = await loadSampleTransport()
        store.role = sampleRole.value
        sampleStore.value = store
        workspace.setSampleClock(store.asOf, businessDate.value)
      }
      const store = sampleStore.value
      if (store) transport.value = store
    } catch (error) {
      transportError.value = error instanceof Error ? error.message : String(error)
    } finally {
      loadingPreview.value = false
    }
    return
  }
  transport.value = realUvTransport()
}

function markDirty() {
  revision.value += 1
}

watch(isPreview, () => { void ensureTransport() }, { immediate: true })

watch(sampleRole, (role) => {
  if (sampleStore.value) sampleStore.value.role = role
  markDirty()
})

async function refresh() {
  refreshing.value = true
  markDirty()
  window.setTimeout(() => { refreshing.value = false }, 260)
}

function advanceSampleClock(minutes: number) {
  const store = sampleStore.value
  if (!store) return
  store.advanceClock(minutes)
  workspace.setSampleClock(store.asOf, businessDate.value)
  markDirty()
}

function toggleSampleFailure(kind: 'readFailure' | 'writeFailure') {
  const store = sampleStore.value
  if (!store) return
  store.failure[kind] = !store.failure[kind]
  markDirty()
}

function resetSample() {
  const store = sampleStore.value
  if (!store) return
  store.reset()
  store.role = sampleRole.value
  workspace.setSampleClock(store.asOf, businessDate.value)
  markDirty()
}

const visibleNav = computed(() => UV_NAV.filter((entry) => workspace.can(entry.permission ?? 'uv_printing:read')))

/** 导航上的待处理徽标来自驱动驾驶舱的同一份摘要，不写死数字。 */
const attentionBadge = computed(() => {
  const counts = summary.value?.counts
  if (!counts) return 0
  return counts.unmatched_jobs
    + counts.needs_unit_jobs
    + counts.reports_needing_quality
    + counts.low_stock_skus
    + counts.handover_differences
})

const navBadges = computed<Record<string, number>>(() => {
  const counts = summary.value?.counts
  if (!counts) return {}
  const badges: Record<string, number> = {
    production: counts.unmatched_jobs + counts.needs_unit_jobs + counts.reports_needing_quality,
    ink: counts.low_stock_skus,
  }
  if (attentionBadge.value) badges.overview = attentionBadge.value
  return badges
})
const pageContext: UvPageContext = {
  workspace,
  transport,
  revision,
  markDirty,
  isPreview,
}

provide(UV_TRANSPORT_KEY, transport)
provide(UV_CONTEXT_KEY, pageContext)

const bannerRoleLabel = computed(() =>
  SAMPLE_ROLE_LABELS[sampleRole.value] ?? '样例角色',
)
</script>

<template>
  <div class="uv-workspace" data-uv-workspace>
    <div v-if="isPreview" class="uv-sample-banner" role="status">
      <Sparkles class="size-4" aria-hidden="true" />
      <span><strong>样例数据 · 不写入生产库</strong>　全部记录带 DEMO- 标记，只读写浏览器内存。</span>
      <div class="uv-sample-banner__tools">
        <label class="uv-filter">
          <span class="uv-filter__label">样例角色</span>
          <select v-model="sampleRole" class="uv-input uv-select">
            <option v-for="role in SAMPLE_ROLE_IDS" :key="role" :value="role">
              {{ SAMPLE_ROLE_LABELS[role] }}
            </option>
          </select>
        </label>
        <Button
          variant="outline"
          size="sm"
          type="button"
          :aria-pressed="sampleStore?.failure.readFailure ?? false"
          @click="toggleSampleFailure('readFailure')"
        >
          读取失败注入
        </Button>
        <Button
          variant="outline"
          size="sm"
          type="button"
          :aria-pressed="sampleStore?.failure.writeFailure ?? false"
          @click="toggleSampleFailure('writeFailure')"
        >
          写入失败注入
        </Button>
        <Button variant="outline" size="sm" type="button" @click="advanceSampleClock(12)">
          时间 +12 分钟
        </Button>
        <Button variant="ghost" size="sm" type="button" @click="resetSample">
          重置样例
        </Button>
      </div>
    </div>

    <header class="uv-topbar">
      <div class="uv-topbar__main">
        <div class="uv-topbar__identity">
          <RouterLink to="/modules/production" class="uv-topbar__back">
            <ArrowLeft class="size-3.5" aria-hidden="true" />
            返回华康A生产部
          </RouterLink>
          <div class="uv-topbar__titles">
            <p class="uv-topbar__title">
              华康A · UV打印管理
              <span v-if="isPreview" class="uv-readonly-note">样例预览</span>
              <span v-else-if="workspace.isReadOnly.value" class="uv-readonly-note">只读</span>
            </p>
            <p class="uv-topbar__context">
              {{ businessDate }} · {{ shift === 'all' ? '全天' : shift === 'day' ? '白班' : '夜班' }}
              · 生产部 · 当前角色 {{ isPreview ? bannerRoleLabel : '宿主账号权限' }}
            </p>
          </div>
        </div>

        <div class="uv-topbar__tools">
          <label class="uv-filter">
            <span class="uv-filter__label">业务日</span>
            <input
              class="uv-input"
              type="date"
              :value="businessDate"
              @change="workspace.setBusinessDate(($event.target as HTMLInputElement).value)"
            >
          </label>
          <label class="uv-filter">
            <span class="uv-filter__label">班次</span>
            <select
              class="uv-input uv-select"
              :value="shift"
              @change="workspace.setShift(($event.target as HTMLSelectElement).value as 'day' | 'night' | 'all')"
            >
              <option value="all">全天</option>
              <option value="day">白班</option>
              <option value="night">夜班</option>
            </select>
          </label>

          <p class="uv-topbar__freshness">
            最近更新
            <strong>{{ asOfLabel }}</strong>
            <span>{{ isPreview ? '样例时钟' : '服务端时间' }}</span>
          </p>

          <Button variant="outline" size="sm" type="button" :disabled="refreshing" @click="refresh">
            <RefreshCw class="size-3.5" :class="refreshing ? 'motion-safe:animate-spin' : ''" aria-hidden="true" />
            {{ refreshing ? '刷新中…' : '刷新' }}
          </Button>
        </div>
      </div>

      <nav class="uv-nav" aria-label="UV打印管理二级导航">
        <RouterLink
          v-for="entry in visibleNav"
          :key="entry.key"
          :to="{ path: `${basePath}/${entry.path}`, query: route.query }"
          :aria-current="activeKey === entry.key ? 'page' : undefined"
        >
          {{ entry.label }}
          <span v-if="navBadges[entry.key]" class="uv-nav__badge">{{ navBadges[entry.key] }}</span>
        </RouterLink>
      </nav>
    </header>

    <main class="uv-main">
      <div v-if="transportError" class="uv-state uv-state--error" role="alert">
        <div class="uv-state__icon uv-state__icon--error" aria-hidden="true">
          <AlertTriangle class="size-5" />
        </div>
        <p class="uv-state__title">样例 transport 未能加载</p>
        <p class="uv-state__message">{{ transportError }}</p>
        <p class="uv-state__hint">需要 DEV 构建且显式设置 VITE_UV_PREVIEW=true；生产包不可达。</p>
      </div>

      <div v-else-if="contextViolation" class="uv-state uv-state--warning" role="alert">
        <div class="uv-state__icon uv-state__icon--warning" aria-hidden="true">
          <ShieldAlert class="size-5" />
        </div>
        <p class="uv-state__title">{{ contextViolation.message }}</p>
        <p class="uv-state__hint">{{ contextViolation.hint }}</p>
        <div class="uv-state__actions">
          <Button
            variant="outline"
            size="sm"
            type="button"
            @click="router.push({ path: '/modules/production', query: { factory: 'huakang-a' } })"
          >
            返回华康A生产部
          </Button>
        </div>
      </div>

      <div v-else-if="loadingPreview" class="uv-state" role="status">
        <p class="uv-state__title">正在装载样例 transport…</p>
      </div>

      <RouterView v-else v-slot="{ Component }">
        <component :is="Component" />
      </RouterView>
    </main>
  </div>
</template>

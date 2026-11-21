<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { AlertTriangle, ArrowLeft, Building2, ClipboardList, Ship, Truck, Table2, RotateCcw } from '@lucide/vue'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import { getFactoryScopedRoute } from '@/data/enterpriseMock'
import { useAppStore } from '@/stores/app'
import ShipmentTaskWorkspace from './ShipmentTaskWorkspace.vue'
import VehicleDispatchPanel from './VehicleDispatchPanel.vue'
import ShippingMasterDataPanel from './ShippingMasterDataPanel.vue'
import { isShippingFactory, SHIPPING_FACTORY_IDS, shippingFactoryProfiles } from './contracts'

type ShippingTab = 'tasks' | 'dispatch' | 'master'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

const shippingTabs: Array<{ id: ShippingTab; label: string; icon: typeof ClipboardList }> = [
  { id: 'tasks', label: '走柜任务', icon: ClipboardList },
  { id: 'dispatch', label: '交仓分车', icon: Truck },
  { id: 'master', label: '基础资料', icon: Table2 },
]

const factoryId = computed(() => appStore.activeProductionFactory.id)
const profile = computed(() => (isShippingFactory(factoryId.value) ? shippingFactoryProfiles[factoryId.value] : null))

const departmentRoute = computed(() => getFactoryScopedRoute('/modules/pmc-warehouse', factoryId.value))

function normalizeTab(value: unknown): ShippingTab {
  return value === 'dispatch' || value === 'master' ? value : 'tasks'
}

const activeTab = ref<ShippingTab>(normalizeTab(route.query.tab))
const feedback = ref('')
let feedbackTimer: ReturnType<typeof setTimeout> | undefined

const dispatchCount = computed(() => profile.value?.tasks.filter((task) => task.vehicles.length > 0).length ?? 0)
const tabCounts = computed<Record<ShippingTab, number | null>>(() => ({
  tasks: profile.value?.tasks.length ?? null,
  dispatch: profile.value ? dispatchCount.value : null,
  master: null,
}))

function setTab(tab: ShippingTab) {
  activeTab.value = tab
  void router.replace({
    query: { ...route.query, tab: tab === 'tasks' ? undefined : tab },
  })
}

async function onTabKeydown(event: KeyboardEvent, index: number) {
  if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const count = shippingTabs.length
  let next = index
  if (event.key === 'ArrowRight') next = (index + 1) % count
  if (event.key === 'ArrowLeft') next = (index - 1 + count) % count
  if (event.key === 'Home') next = 0
  if (event.key === 'End') next = count - 1
  const target = shippingTabs[next]!
  setTab(target.id)
  await nextTick()
  document.getElementById(`shipping-tab-${target.id}`)?.focus()
}

function notify(message: string) {
  feedback.value = message
  clearTimeout(feedbackTimer)
  feedbackTimer = setTimeout(() => { feedback.value = '' }, 5000)
}

/** 船务工作区自带的厂区切换：与全局厂区选择共用 app store，不跨厂合并数据。 */
function switchFactory(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  if (!isShippingFactory(value) || value === factoryId.value) return
  appStore.setActiveFactory(value)
  void router.replace({ query: { ...route.query, factory: value } })
}

watch(() => route.query.tab, (tab) => {
  activeTab.value = normalizeTab(tab)
})

onBeforeUnmount(() => clearTimeout(feedbackTimer))
</script>

<template>
  <main class="min-h-screen bg-slate-100 text-[13px] leading-relaxed text-slate-900">
    <header class="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div class="mx-auto flex max-w-[1720px] flex-wrap items-center gap-3 px-4 py-2.5 sm:px-5">
        <RouterLink
          :to="departmentRoute"
          class="inline-flex h-9 shrink-0 items-center gap-2 whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-950"
        >
          <ArrowLeft class="size-4" aria-hidden="true" />
          <span class="hidden sm:inline">PMC / 仓管模块</span>
          <span class="sm:hidden">模块中心</span>
        </RouterLink>

        <div class="flex min-w-0 items-center gap-2.5">
          <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-white">
            <Ship class="size-5" aria-hidden="true" />
          </span>
          <div class="min-w-0">
            <h1 class="truncate text-[15px] font-bold leading-tight">船务管理</h1>
            <div class="truncate text-[11px] text-slate-400">Shipping Operations · 订舱 / 走柜 / 交仓 / 回写</div>
          </div>
        </div>

        <div class="ml-auto flex flex-wrap items-center gap-2">
          <label
            v-if="profile"
            class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-[12px] font-medium text-slate-600"
          >
            <Building2 class="size-4" aria-hidden="true" />
            <span class="text-slate-500">当前厂区</span>
            <select
              :value="factoryId"
              aria-label="切换厂区"
              class="h-7 cursor-pointer rounded-md bg-transparent pr-1 text-[12px] font-semibold text-slate-800 outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
              @change="switchFactory"
            >
              <option v-for="id in SHIPPING_FACTORY_IDS" :key="id" :value="id">
                {{ shippingFactoryProfiles[id].label }}
              </option>
            </select>
          </label>
          <span
            v-else
            class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-[12px] font-medium text-slate-600"
          >
            <Building2 class="size-4" aria-hidden="true" />
            当前厂区：{{ appStore.activeProductionFactory.shortName }}
          </span>
          <span class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-2.5 text-[11px] font-semibold text-amber-800">
            <AlertTriangle class="size-3.5" aria-hidden="true" />
            界面预览 · 示例数据
          </span>
          <AccountMenu />
        </div>
      </div>

      <nav
        v-if="profile"
        class="mx-auto flex max-w-[1720px] items-center gap-1 overflow-x-auto px-4 sm:px-5"
        role="tablist"
        aria-label="船务工作区"
      >
        <button
          v-for="(tab, index) in shippingTabs"
          :id="`shipping-tab-${tab.id}`"
          :key="tab.id"
          type="button"
          role="tab"
          :aria-selected="activeTab === tab.id"
          :aria-controls="`shipping-panel-${tab.id}`"
          :tabindex="activeTab === tab.id ? 0 : -1"
          class="inline-flex items-center gap-1.5 whitespace-nowrap rounded-t-lg px-3 py-2 text-[12.5px] font-semibold transition hover:text-slate-900"
          :class="activeTab === tab.id ? 'bg-slate-900 text-white' : 'text-slate-500'"
          @click="setTab(tab.id)"
          @keydown="onTabKeydown($event, index)"
        >
          <component :is="tab.icon" class="size-4" aria-hidden="true" />
          {{ tab.label }}
          <span
            v-if="tabCounts[tab.id] !== null"
            class="rounded-full px-1.5 text-[10px] tabular-nums"
            :class="activeTab === tab.id ? 'bg-white/15 text-white' : 'bg-slate-100 text-slate-500'"
          >{{ tabCounts[tab.id] }}</span>
        </button>
      </nav>
    </header>

    <div class="mx-auto max-w-[1720px] space-y-4 px-4 pb-12 pt-4 sm:px-5">
      <div
        v-if="feedback"
        class="flex items-center gap-2 rounded-lg border border-teal-200 bg-teal-50 px-4 py-2.5 text-[12px] font-semibold text-teal-800"
        role="status"
        aria-live="polite"
      >
        <RotateCcw class="size-4 shrink-0" aria-hidden="true" />{{ feedback }}
      </div>

      <template v-if="profile">
        <p class="rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-[11px] leading-5 text-slate-500">
          示例数据按厂区隔离：{{ profile.label }} 当前 {{ profile.tasks.length }} 个任务，字段口径沿用船务业务文档（四个时间闸门、五态任务、35 CBM 分车）。
          正式接入后由船务接口提供数据，本页不写入任何业务库。
        </p>

        <section
          v-if="activeTab === 'tasks'"
          id="shipping-panel-tasks"
          role="tabpanel"
          aria-labelledby="shipping-tab-tasks"
        >
          <ShipmentTaskWorkspace :profile="profile" @notify="notify" />
        </section>

        <section
          v-else-if="activeTab === 'dispatch'"
          id="shipping-panel-dispatch"
          role="tabpanel"
          aria-labelledby="shipping-tab-dispatch"
        >
          <VehicleDispatchPanel :profile="profile" />
        </section>

        <section
          v-else
          id="shipping-panel-master"
          role="tabpanel"
          aria-labelledby="shipping-tab-master"
        >
          <ShippingMasterDataPanel :profile="profile" />
        </section>
      </template>

      <section v-else class="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
        <span class="mx-auto flex size-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-500">
          <Ship class="size-6" aria-hidden="true" />
        </span>
        <h2 class="mt-4 text-lg font-semibold text-slate-950">{{ appStore.activeProductionFactory.shortName }} 暂未开通船务管理</h2>
        <p class="mx-auto mt-2 max-w-xl text-[12px] leading-5 text-slate-500">
          船务管理目前只对华兴、华登、华康 A、华康 B、华康 D 开放；其他厂区不显示入口。
          如需开通，请联系船务与系统管理员。
        </p>
        <RouterLink
          :to="departmentRoute"
          class="mt-5 inline-flex h-9 items-center gap-2 rounded-lg bg-teal-700 px-4 text-[12px] font-semibold text-white transition hover:bg-teal-800"
        >
          <ArrowLeft class="size-4" aria-hidden="true" />返回 PMC / 仓管模块中心
        </RouterLink>
      </section>
    </div>
  </main>
</template>

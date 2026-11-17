<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  AlertTriangle,
  ArrowLeft,
  Building2,
  CalendarClock,
  ClipboardCheck,
  ClipboardList,
  Mail,
  Package,
  RotateCcw,
  Ship,
  Tags,
  Users,
} from '@lucide/vue'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import { getFactoryScopedRoute } from '@/data/enterpriseMock'
import { useAppStore } from '@/stores/app'
import ShippingOrderWorkspace from './ShippingOrderWorkspace.vue'
import ShippingEmailImportPanel from './ShippingEmailImportPanel.vue'
import ShippingCodeMappingPanel from './ShippingCodeMappingPanel.vue'
import ShippingSoSchedulePanel from './ShippingSoSchedulePanel.vue'
import ShippingTruckSheetPanel from './ShippingTruckSchedulePanel.vue'
import ShippingSupplementPanel from './ShippingSupplementPanel.vue'
import ShippingCustomsPanel from './ShippingCustomsPanel.vue'
import ShippingProductHistoryPanel from './ShippingProductHistoryPanel.vue'
import ShippingMasterDataPanel from './ShippingMasterDataPanel.vue'
import { isShippingFactory, SHIPPING_FACTORY_IDS, shippingFactoryProfiles } from './contracts'

type ShippingPage = 'email' | 'orders' | 'so' | 'truck' | 'supplement' | 'customs' | 'codes' | 'master' | 'daily'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

const menu = [
  { id: 'email', label: '邮件导入', icon: Mail, page: 'email' },
  { id: 'orders', label: '工厂排期单', icon: ClipboardList, page: 'orders' },
  { id: 'codes', label: '货号映射', icon: Tags, page: 'codes' },
  { id: 'vendor', label: '厂商映射', icon: Building2, page: 'master' },
  { id: 'daily', label: '一键出货', icon: CalendarClock, page: 'daily' },
  { id: 'pallet', label: '卡板据统计', icon: Package, page: null },
  { id: 'container', label: '提箱柜核对', icon: ClipboardCheck, page: null },
  { id: 'users', label: '用户管理', icon: Users, page: null },
] as const

const factoryId = computed(() => appStore.activeProductionFactory.id)
const profile = computed(() => (isShippingFactory(factoryId.value) ? shippingFactoryProfiles[factoryId.value] : null))
const departmentRoute = computed(() => getFactoryScopedRoute('/modules/pmc-warehouse', factoryId.value))

function normalizePage(value: unknown): ShippingPage {
  if (value === 'orders' || value === 'tasks') return 'orders'
  if (value === 'so' || value === 'loading' || value === 'zuru') return 'so'
  if (value === 'truck') return 'truck'
  if (value === 'supplement') return 'supplement'
  if (value === 'customs') return 'customs'
  if (value === 'codes') return 'codes'
  if (value === 'master') return 'master'
  if (value === 'daily') return 'daily'
  return 'email'
}

const activePage = ref<ShippingPage>(normalizePage(route.query.tab))
const feedback = ref('')
let feedbackTimer: ReturnType<typeof setTimeout> | undefined

const activeMenuId = computed(() => {
  if (activePage.value === 'orders' || activePage.value === 'so' || activePage.value === 'truck' || activePage.value === 'supplement' || activePage.value === 'customs') return 'orders'
  if (activePage.value === 'codes') return 'codes'
  if (activePage.value === 'master') return 'vendor'
  if (activePage.value === 'daily') return 'daily'
  return 'email'
})

function setPage(page: ShippingPage) {
  activePage.value = page
  void router.replace({ query: { ...route.query, tab: page === 'email' ? undefined : page } })
}

function onMenu(id: string) {
  const item = menu.find((entry) => entry.id === id)
  if (!item) return
  if (item.page) {
    setPage(item.page)
    return
  }
  notify(`界面预览：${item.label}尚未接入后端接口。`)
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
  activePage.value = normalizePage(tab)
})

onBeforeUnmount(() => clearTimeout(feedbackTimer))
</script>

<template>
  <main class="min-h-screen bg-[#eef4ef] text-[13px] leading-relaxed text-slate-900">
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
    </header>

    <div class="mx-auto max-w-[1720px] px-4 pb-12 pt-4 sm:px-5">
      <div
        v-if="feedback"
        class="mb-4 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-[12px] font-semibold text-emerald-900"
        role="status"
        aria-live="polite"
      >
        <RotateCcw class="size-4 shrink-0" aria-hidden="true" />{{ feedback }}
      </div>

      <div v-if="profile" class="flex flex-col gap-3 lg:flex-row lg:items-start">
        <aside class="shrink-0 rounded-xl bg-[#04291f] p-2 text-emerald-100/80 lg:sticky lg:top-20 lg:h-[calc(100vh-6rem)] lg:w-[220px] lg:overflow-y-auto" aria-label="船务系统菜单">
          <div class="flex items-center gap-2 px-2 py-1.5 text-white">
            <Mail class="size-4" aria-hidden="true" />
            <span class="text-[12px] font-bold">船务管理</span>
          </div>
          <nav class="flex gap-1 overflow-x-auto pb-1 lg:block lg:space-y-0.5 lg:overflow-visible lg:pb-0">
            <button
              v-for="item in menu"
              :key="item.id"
              type="button"
              class="flex shrink-0 items-center gap-2 whitespace-nowrap rounded-lg px-2.5 py-2 text-left text-[12px] font-medium transition lg:w-full"
              :class="activeMenuId === item.id ? 'bg-emerald-200 text-emerald-950' : 'text-emerald-100/80 hover:bg-white/10 hover:text-white'"
              :aria-current="activeMenuId === item.id ? 'page' : undefined"
              @click="onMenu(item.id)"
            >
              <component :is="item.icon" class="size-4 shrink-0" aria-hidden="true" />
              <span class="truncate">{{ item.label }}</span>
            </button>
          </nav>
        </aside>

        <div class="min-w-0 flex-1">
          <section v-if="activePage === 'email'" aria-label="邮件导入">
            <ShippingEmailImportPanel :factory-id="factoryId" @notify="notify" @open-module="setPage" />
          </section>
          <section v-else-if="activePage === 'so'" aria-label="SO出货表">
            <ShippingSoSchedulePanel :factory-id="factoryId" @notify="notify" @back="setPage('orders')" />
          </section>
          <section v-else-if="activePage === 'daily'" aria-label="一键出货">
            <ShippingProductHistoryPanel :factory-id="factoryId" @notify="notify" />
          </section>
          <section v-else-if="activePage === 'truck'" aria-label="车的排出货表">
            <ShippingTruckSheetPanel :factory-id="factoryId" @notify="notify" @back="setPage('orders')" />
          </section>
          <section v-else-if="activePage === 'supplement'" aria-label="补料单">
            <ShippingSupplementPanel :factory-id="factoryId" @notify="notify" @back="setPage('orders')" />
          </section>
          <section v-else-if="activePage === 'customs'" aria-label="通关一体化资料">
            <ShippingCustomsPanel :factory-id="factoryId" @notify="notify" @back="setPage('orders')" />
          </section>
          <section v-else-if="activePage === 'codes'" aria-label="货号映射">
            <ShippingCodeMappingPanel @notify="notify" />
          </section>
          <section v-else-if="activePage === 'orders'" aria-label="出货单管理">
            <ShippingOrderWorkspace :profile="profile" @notify="notify" @open-so-sheet="setPage('so')" @open-truck-sheet="setPage('truck')" @open-supplement="setPage('supplement')" @open-customs="setPage('customs')" />
          </section>
          <section v-else aria-label="基础资料">
            <ShippingMasterDataPanel :profile="profile" />
          </section>
        </div>
      </div>

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

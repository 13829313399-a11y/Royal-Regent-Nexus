<script setup lang="ts">
import { computed, onBeforeUnmount, provide, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import { House, Printer, RefreshCw } from "@lucide/vue";
import AccountMenu from "@/components/layout/AccountMenu.vue";
import { useRouteEntryOwned } from '@/features/route-motion/useModuleEntryMotion';
import { useWorkspace } from "./composables/useWorkspace";
import { useTdpNavIndicator } from "./composables/useTdpNavIndicator";
import { workspaceKey } from "./context";
import OverviewPage from "./pages/OverviewPage.vue";
import RecordsPage from "./pages/RecordsPage.vue";
import ProductsPage from "./pages/ProductsPage.vue";
import MaterialsPage from "./pages/MaterialsPage.vue";
import SchedulesPage from "./pages/SchedulesPage.vue";
import MaintenancePage from "./pages/MaintenancePage.vue";
import AuditPage from "./pages/AuditPage.vue";
import OperationsPage from "./pages/OperationsPage.vue";
import MigrationPage from "./pages/MigrationPage.vue";
import LegacyPrinterGrid from "./components/LegacyPrinterGrid.vue";
import PrinterDetail from './components/PrinterDetail.vue';
import ReportsPage from "./pages/ReportsPage.vue";
const workspace = useWorkspace();
provide(workspaceKey, workspace);
const {
  tabs,
  activeTab,
  dashboard,
  loading,
  errorMessage,
  successMessage,
  live,
  loadDashboard,
  assistantPrinter,
  assistantPrinterId,
  openPrinter,
  closePrinter,
  selectedPrinter,
  selectAssistantPrinter,
  invalidateAssistantPrinter,
} = workspace;
const detailId = ref(''), detailOpen = ref(false);
let printerTrigger: HTMLElement | null = null;
watch(selectedPrinter, id => {
  if (id) {
    const focused = document.activeElement;
    if (focused instanceof HTMLElement && focused !== document.body && !focused.closest('.printer-overlay')) printerTrigger = focused;
    detailId.value = id; detailOpen.value = true;
  } else detailOpen.value = false;
}, { immediate: true, flush: 'sync' });
function afterDetailClose() { if (!selectedPrinter.value) detailId.value = ''; }
function printerReturnFocus() { return printerTrigger?.isConnected ? printerTrigger : document.querySelector<HTMLElement>('#tdp-main'); }
const order = [
  "overview",
  "records",
  "machines",
  "materials",
  "warehouse",
  "schedules",
  "products",
  "maintenance",
  "reports",
  "audit",
];
const primaryTabs = computed(() =>
  order.flatMap((id) => tabs.value.filter((t) => t.id === id)),
);
const extraTabs = computed(() =>
  tabs.value.filter((t) => !order.includes(t.id)),
);
const title = computed(() =>
  activeTab.value === "records"
    ? "每日生产记录"
    : tabs.value.find((t) => t.id === activeTab.value)?.label,
);
const { nav, indicator } = useTdpNavIndicator(() => activeTab.value);
const firstReveal = ref(!useRouteEntryOwned());
const refreshing = ref(false);
const viewHost = ref<HTMLElement | null>(null);
let revealTimer: ReturnType<typeof setTimeout> | undefined;
watch(dashboard, (value) => {
  if (value && firstReveal.value && !revealTimer) {
    revealTimer = setTimeout(() => { firstReveal.value = false; }, 390);
  }
}, { immediate: true });
watch(activeTab, () => {
  if (!dashboard.value || !firstReveal.value) return;
  if (revealTimer) clearTimeout(revealTimer);
  revealTimer = undefined;
  firstReveal.value = false;
});
onBeforeUnmount(() => { if (revealTimer) clearTimeout(revealTimer); });
async function refresh() {
  if (refreshing.value) return;
  refreshing.value = true;
  try { await loadDashboard(); } finally { refreshing.value = false; }
}
function holdViewHeight(element: Element) {
  if (viewHost.value) viewHost.value.style.minHeight = `${element.getBoundingClientRect().height}px`;
}
function releaseViewHeight() {
  if (viewHost.value) viewHost.value.style.minHeight = '';
}
</script>
<template>
  <div translate="no" class="three-d-workspace legacy-workspace tdp-theme" :class="{ 'tdp-first-reveal': firstReveal }">
    <a class="tdp-skip-link" href="#tdp-main">跳到主要内容</a>
    <aside class="legacy-sidebar">
      <div class="legacy-brand" data-yl-help="three-d-printing.overview" :class="{ 'tdp-reveal-once': firstReveal }">
        <span class="tdp-brand-icon" data-route-motion-anchor aria-hidden="true"><Printer :size="18" /></span>
        <span>3D打印管理<small>部门生产管理系统 · 华康A</small></span>
      </div>
      <div class="legacy-sidebar-scroll">
        <nav ref="nav" data-yl-help="three-d-printing.navigation" aria-label="3D打印管理菜单" :class="{ 'tdp-reveal-once': firstReveal }"
          :style="{
            '--tdp-nav-top': `${indicator.top}px`,
            '--tdp-nav-left': `${indicator.left}px`,
            '--tdp-nav-width': `${indicator.width}px`,
            '--tdp-nav-height': `${indicator.height}px`,
          }">
          <span class="tdp-nav-indicator" :style="{ opacity: indicator.visible && primaryTabs.some(tab => tab.id === activeTab) ? 1 : 0 }" aria-hidden="true" />
          <button
            v-for="tab in primaryTabs"
            :key="tab.id"
            type="button"
            :class="{ active: activeTab === tab.id }"
            :aria-current="activeTab === tab.id ? 'page' : undefined"
            @click="activeTab = tab.id"
          >
            <component :is="tab.icon" class="size-4" aria-hidden="true" />{{ tab.label }}
          </button>
        </nav>
        <details class="legacy-more">
          <summary>更多功能</summary>
          <button
            v-for="tab in extraTabs"
            :key="tab.id"
            type="button"
            :class="{ active: activeTab === tab.id }"
            :aria-current="activeTab === tab.id ? 'page' : undefined"
            @click="activeTab = tab.id"
          >
            <component :is="tab.icon" class="size-4" aria-hidden="true" />{{ tab.label }}
          </button>
        </details>
      </div>
      <footer class="legacy-sidebar-footer">
        <div class="legacy-sync" data-yl-help="three-d-printing.sync">
          <span
            ><i :class="{ connected: live.connected.value }" />{{
              live.connected.value ? "实时同步中" : "定时同步中"
            }}</span
          >
          <button
            type="button"
            aria-label="刷新数据"
            title="刷新数据"
            :disabled="refreshing"
            :aria-busy="refreshing || undefined"
            @click="refresh"
          >
            <RefreshCw class="size-3.5" :class="{ 'tdp-refreshing': refreshing }" aria-hidden="true" />
          </button>
        </div>
        <RouterLink
          :to="{ path: '/', query: { factory: 'huakang-a' } }"
          class="legacy-home-link"
          ><House class="size-4" />返回主页</RouterLink
        >
        <div class="legacy-sidebar-account">
          <span class="legacy-account-label">当前账号</span><AccountMenu />
        </div>
      </footer>
    </aside>
    <main id="tdp-main" class="legacy-main" tabindex="-1">
      <h1 :class="{ 'tdp-reveal-once': firstReveal }">{{ title }}</h1>
      <div v-if="assistantPrinter" class="tdp-assistant-selection" role="status">
        <span>曜灵查询范围：{{ assistantPrinter.machine_no }} 号机 · {{ assistantPrinter.name }}</span>
        <button type="button" @click="openPrinter(assistantPrinter.id)">查看机台</button>
        <button type="button" @click="assistantPrinterId = ''">清除选择</button>
      </div>
      <p v-if="errorMessage" role="alert" class="legacy-error">
        {{ errorMessage }}
      </p>
      <p v-if="successMessage" role="status" class="legacy-success">
        {{ successMessage }}
      </p>
      <div v-if="loading && !dashboard" class="tdp-skeleton" role="status" aria-label="正在加载3D打印数据">
        <span class="sr-only">正在加载3D打印数据…</span>
        <div class="tdp-skeleton-block tdp-skeleton-toolbar" />
        <div v-if="activeTab === 'overview'" class="tdp-skeleton-metrics"><i v-for="n in 8" :key="n" class="tdp-skeleton-block" /></div>
        <div v-else class="tdp-skeleton-machines"><i v-for="n in 4" :key="n" class="tdp-skeleton-block" /></div>
        <div class="tdp-skeleton-panels"><i class="tdp-skeleton-block" /><i class="tdp-skeleton-block" /></div>
      </div>
      <div v-else-if="!dashboard" class="panel-card p-6" role="status">
        <p>3D打印数据暂未加载成功。</p>
        <button type="button" class="action-button mt-3" @click="refresh">重新加载</button>
      </div>
      <div v-else ref="viewHost" class="tdp-view-host">
        <Transition name="tdp-view" appear @before-leave="holdViewHeight" @after-enter="releaseViewHeight">
          <div :key="activeTab" class="tdp-view">
        <OverviewPage v-if="activeTab === 'overview'" /><RecordsPage
          v-else-if="activeTab === 'records'"
        />
        <LegacyPrinterGrid v-else-if="activeTab === 'machines'" />
        <ProductsPage v-else-if="activeTab === 'products'" />
        <MaterialsPage
          v-else-if="activeTab === 'materials' || activeTab === 'warehouse'"
          :key="activeTab"
          :mode="activeTab"
        />
        <SchedulesPage v-else-if="activeTab === 'schedules'" /><MaintenancePage
          v-else-if="activeTab === 'maintenance'"
        />
        <ReportsPage v-else-if="activeTab === 'reports'" /><AuditPage
          v-else-if="activeTab === 'audit'"
        />
        <MigrationPage v-else-if="activeTab === 'migration'" /><OperationsPage
          v-else-if="activeTab === 'operations'"
        />
          </div>
        </Transition>
      </div>
    </main>
    <PrinterDetail v-if="detailId" :key="detailId" :id="detailId" :open="detailOpen"
      :printer="dashboard?.printers.find(p => p.id === detailId)" :return-focus="printerReturnFocus"
      @close="closePrinter" @after-close="afterDetailClose"
      @ready="selectAssistantPrinter(detailId)" @unavailable="invalidateAssistantPrinter(detailId)" />
  </div>
</template>
<style src="./workspace.css"></style>
<style src="./legacy.css"></style>
<style src="./styles/polish.css"></style>
<style src="./styles/motion.css"></style>

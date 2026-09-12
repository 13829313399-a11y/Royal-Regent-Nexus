<script setup lang="ts">
import { computed, provide } from "vue";
import { RouterLink } from "vue-router";
import { House, RefreshCw } from "@lucide/vue";
import AccountMenu from "@/components/layout/AccountMenu.vue";
import { useWorkspace } from "./composables/useWorkspace";
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
} = workspace;
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
</script>
<template>
  <div class="three-d-workspace legacy-workspace">
    <aside class="legacy-sidebar">
      <div class="legacy-brand">
        3D打印管理<small>部门生产管理系统 · 华康A</small>
      </div>
      <div class="legacy-sidebar-scroll">
        <nav aria-label="3D打印管理菜单">
          <button
            v-for="tab in primaryTabs"
            :key="tab.id"
            :class="{ active: activeTab === tab.id }"
            @click="activeTab = tab.id"
          >
            <component :is="tab.icon" class="size-4" />{{ tab.label }}
          </button>
        </nav>
        <details class="legacy-more">
          <summary>更多功能</summary>
          <button
            v-for="tab in extraTabs"
            :key="tab.id"
            @click="activeTab = tab.id"
          >
            {{ tab.label }}
          </button>
        </details>
      </div>
      <footer class="legacy-sidebar-footer">
        <div class="legacy-sync">
          <span
            ><i :class="{ connected: live.connected.value }" />{{
              live.connected.value ? "实时同步中" : "定时同步中"
            }}</span
          >
          <button
            type="button"
            aria-label="刷新数据"
            title="刷新数据"
            @click="loadDashboard()"
          >
            <RefreshCw class="size-3.5" />
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
    <main class="legacy-main">
      <h1>{{ title }}</h1>
      <p v-if="errorMessage" role="alert" class="legacy-error">
        {{ errorMessage }}
      </p>
      <p v-if="successMessage" role="status" class="legacy-success">
        {{ successMessage }}
      </p>
      <div v-if="loading && !dashboard" class="panel-card p-8">
        正在加载3D打印数据…
      </div>
      <template v-else-if="dashboard">
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
      </template>
    </main>
  </div>
</template>
<style src="./workspace.css"></style>
<style src="./legacy.css"></style>

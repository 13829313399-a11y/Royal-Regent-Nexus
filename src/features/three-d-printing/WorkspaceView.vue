<script setup lang="ts">
import { provide } from "vue";
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
const workspace = useWorkspace();
provide(workspaceKey, workspace);
const {
  tabs,
  activeTab,
  dashboard,
  loading,
  saving,
  errorMessage,
  successMessage,
  live,
  canExport,
  loadDashboard,
  exportWorkbook,
  Download,
  Printer,
  RefreshCw,
} = workspace;
</script>
<template>
  <div class="three-d-workspace min-h-screen bg-slate-50">
    <header class="border-b border-slate-200 bg-white">
      <div
        class="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-4 px-5 py-5 lg:px-8"
      >
        <div>
          <div
            class="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-teal-700"
          >
            <Printer class="size-4" />
            华康A · 生产部
          </div>
          <h1 class="mt-2 text-2xl font-bold text-slate-950">3D打印机管理</h1>
          <p class="mt-1 text-sm text-slate-500">
            打印状态、生产记录、产品图片、物料库存与计划维护统一管理
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <span
            class="rounded-full bg-slate-100 px-3 py-2 text-xs text-slate-600"
          >
            {{
              live.connected.value
                ? "实时更新已连接"
                : "定时刷新 · 实时连接恢复中"
            }}
          </span>
          <span
            class="rounded-full bg-slate-100 px-3 py-2 text-xs text-slate-600"
          >
            {{
              dashboard?.generated_at
                ? `数据 ${dashboard.generated_at}`
                : "正在连接云端"
            }}
          </span>
          <button
            class="action-button secondary"
            type="button"
            :disabled="loading"
            @click="loadDashboard()"
          >
            <RefreshCw class="size-4" :class="{ 'animate-spin': loading }" />
            刷新
          </button>
          <button
            v-if="canExport"
            class="action-button"
            type="button"
            :disabled="saving"
            @click="exportWorkbook"
          >
            <Download class="size-4" />
            导出 Excel
          </button>
        </div>
      </div>
    </header>

    <main class="mx-auto max-w-[1600px] px-5 py-6 lg:px-8">
      <div
        v-if="errorMessage"
        class="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700"
      >
        {{ errorMessage }}
      </div>
      <div
        v-if="successMessage"
        class="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700"
      >
        {{ successMessage }}
      </div>

      <nav
        class="mb-6 flex gap-2 overflow-x-auto rounded-xl border border-slate-200 bg-white p-2 shadow-sm"
      >
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          class="flex shrink-0 items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition"
          :class="
            activeTab === tab.id
              ? 'bg-teal-700 text-white shadow-sm'
              : 'text-slate-600 hover:bg-slate-100'
          "
          @click="activeTab = tab.id"
        >
          <component :is="tab.icon" class="size-4" />
          {{ tab.label }}
        </button>
      </nav>

      <div
        v-if="loading && !dashboard"
        class="rounded-2xl border border-slate-200 bg-white p-16 text-center text-slate-500"
      >
        正在加载3D打印数据…
      </div>

      <template v-else-if="dashboard">
        <OverviewPage v-if="activeTab === 'overview'" />

        <RecordsPage v-else-if="activeTab === 'records'" />

        <ProductsPage v-else-if="activeTab === 'products'" />

        <MaterialsPage v-else-if="activeTab === 'materials'" />

        <SchedulesPage v-else-if="activeTab === 'schedules'" />

        <MaintenancePage v-else-if="activeTab === 'maintenance'" />

        <AuditPage v-else-if="activeTab === 'audit'" /><MigrationPage
          v-else-if="activeTab === 'migration'"
        /><OperationsPage v-else-if="activeTab === 'operations'" />
      </template>
    </main>
  </div>
</template>

<style src="./workspace.css"></style>

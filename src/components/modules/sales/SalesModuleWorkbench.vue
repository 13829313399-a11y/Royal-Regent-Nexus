<script setup lang="ts">
import { ArrowLeft, Building2, Search } from '@lucide/vue'
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import { useAppStore } from '@/stores/app'

interface SalesWorkbenchMetric {
  label: string
  value: string
  detail: string
}

withDefaults(defineProps<{
  title: string
  description: string
  badge: string
  searchPlaceholder?: string
  metrics?: SalesWorkbenchMetric[]
}>(), {
  searchPlaceholder: '',
  metrics: () => [],
})

const appStore = useAppStore()
const activeFactory = computed(() => appStore.activeProductionFactory)
</script>

<template>
  <div class="sales-workbench min-h-screen text-slate-950">
    <header class="sales-topbar">
      <div class="sales-topbar-inner">
        <div class="sales-brand">
          <span class="sales-brand-mark">
            <slot name="icon" />
          </span>
          <span>{{ title }}</span>
        </div>

        <div class="sales-topbar-spacer" />

        <label v-if="searchPlaceholder" class="sales-global-search">
          <Search class="size-4" aria-hidden="true" />
          <input type="search" :placeholder="searchPlaceholder" :aria-label="searchPlaceholder">
        </label>

        <span class="sales-factory-pill">
          <Building2 class="size-4" aria-hidden="true" />
          {{ activeFactory.shortName }}
        </span>
        <AccountMenu />
      </div>
    </header>

    <main class="sales-page">
      <header class="sales-page-head">
        <div class="min-w-0">
          <RouterLink to="/modules/sales-business" class="sales-back-link">
            <ArrowLeft class="size-[15px]" aria-hidden="true" />
            业务部模块中心
          </RouterLink>
          <div class="sales-title-row">
            <h1 class="sales-page-title">{{ title }}</h1>
            <span class="sales-badge"><span class="sales-badge-dot" />{{ badge }}</span>
          </div>
          <p class="sales-page-description">{{ description }}</p>
        </div>

        <div v-if="metrics.length" class="sales-metrics">
          <article v-for="metric in metrics" :key="metric.label" class="sales-metric">
            <p>{{ metric.label }}</p>
            <strong>{{ metric.value }}</strong>
            <span>{{ metric.detail }}</span>
          </article>
        </div>
      </header>

      <slot />
    </main>
  </div>
</template>

<style scoped>
.sales-workbench {
  background:
    radial-gradient(circle at top left, rgb(13 148 136 / 12%), transparent 34%),
    linear-gradient(180deg, #f8fafc 0%, #eef4f8 100%);
}

.sales-topbar {
  position: sticky;
  top: 0;
  z-index: 40;
  border-bottom: 1px solid #e2e8f0;
  background: rgb(248 250 252 / 90%);
  backdrop-filter: saturate(1.4) blur(10px);
}

.sales-topbar-inner {
  display: flex;
  width: min(100%, 1680px);
  min-height: 62px;
  margin: 0 auto;
  align-items: center;
  gap: 14px;
  padding: 10px 24px;
}

.sales-brand {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 11px;
  color: #020617;
  font-size: 17px;
  font-weight: 900;
  letter-spacing: -0.02em;
}

.sales-brand-mark {
  display: grid;
  width: 38px;
  height: 38px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 11px;
  background: #0f766e;
  color: #fff;
  box-shadow: 0 7px 18px rgb(13 118 110 / 28%);
}

.sales-brand-mark :deep(svg) {
  width: 19px;
  height: 19px;
}

.sales-topbar-spacer {
  min-width: 24px;
  flex: 1;
}

.sales-global-search {
  display: flex;
  width: min(320px, 26vw);
  min-width: 220px;
  align-items: center;
  gap: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  background: #fff;
  padding: 7px 12px;
  color: #94a3b8;
}

.sales-global-search:focus-within {
  border-color: #0d9488;
  box-shadow: 0 0 0 3px rgb(20 184 166 / 10%);
}

.sales-global-search input {
  min-width: 0;
  flex: 1;
  border: 0;
  background: transparent;
  color: #0f172a;
  font-size: 12px;
  outline: none;
}

.sales-factory-pill {
  display: inline-flex;
  height: 34px;
  flex: 0 0 auto;
  align-items: center;
  gap: 6px;
  border: 1px solid #e2e8f0;
  border-radius: 9px;
  background: #fff;
  padding: 0 10px;
  color: #475569;
  font-size: 11px;
  font-weight: 700;
}

.sales-page {
  width: min(100%, 1680px);
  margin: 0 auto;
  padding: 24px 40px 56px;
}

.sales-page-head {
  display: flex;
  flex-direction: column;
  gap: 18px;
  margin-bottom: 20px;
}

.sales-back-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #475569;
  font-size: 12px;
  font-weight: 800;
}

.sales-back-link:hover {
  color: #0f766e;
}

.sales-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 11px;
  margin-top: 17px;
}

.sales-page-title {
  margin: 0;
  color: #020617;
  font-size: clamp(30px, 3.3vw, 48px);
  font-weight: 950;
  line-height: 1.05;
  letter-spacing: -0.045em;
}

.sales-badge {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: 1px solid #99f6e4;
  border-radius: 999px;
  background: #f0fdfa;
  padding: 6px 10px;
  color: #0f766e;
  font-size: 11px;
  font-weight: 900;
}

.sales-badge-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: currentColor;
}

.sales-page-description {
  max-width: 850px;
  margin: 10px 0 0;
  color: #475569;
  font-size: 14px;
  line-height: 1.75;
}

.sales-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(132px, 1fr));
  gap: 9px;
}

.sales-metric {
  min-width: 0;
  border: 1px solid #dbe5ea;
  border-radius: 11px;
  background: rgb(255 255 255 / 86%);
  padding: 12px 14px;
  box-shadow: 0 10px 24px rgb(15 23 42 / 4%);
}

.sales-metric p,
.sales-metric span {
  margin: 0;
  color: #64748b;
  font-size: 10px;
}

.sales-metric strong {
  display: block;
  margin-top: 6px;
  color: #020617;
  font-size: 22px;
  line-height: 1;
}

.sales-metric span {
  display: block;
  margin-top: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (min-width: 1280px) {
  .sales-page-head {
    flex-direction: row;
    align-items: flex-end;
    justify-content: space-between;
  }
}

@media (max-width: 800px) {
  .sales-topbar-inner {
    flex-wrap: wrap;
    padding: 10px 16px;
  }

  .sales-global-search {
    order: 5;
    width: 100%;
    min-width: 0;
  }

  .sales-page {
    padding: 18px 16px 40px;
  }

  .sales-metrics {
    grid-template-columns: 1fr;
  }
}
</style>

<script setup lang="ts">
import { Calculator } from '@lucide/vue'
import { computed, nextTick, watch } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import SalesModuleWorkbench from '@/components/modules/sales/SalesModuleWorkbench.vue'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
const route = useRoute()
appStore.setActiveDepartment('sales-business')

const backNavigation = computed(() => {
  const quoteId = String(route.params.quoteId ?? '')
  if (route.name === 'internal-quote-export-summary' && quoteId) {
    return { to: `/modules/sales-business/internal-quote-desk/${quoteId}/summary`, label: '返回汇总与放行' }
  }
  if (route.name === 'internal-quote-summary' && quoteId) {
    return { to: `/modules/sales-business/internal-quote-desk/${quoteId}/collaboration`, label: '返回协作页' }
  }
  if (route.name === 'internal-quote-collaboration') {
    return { to: '/modules/sales-business/internal-quote-desk', label: '返回报价首页' }
  }
  return { to: '/modules/sales-business', label: '业务部模块' }
})

watch(() => route.fullPath, async () => {
  await nextTick()
  window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
}, { immediate: true })
</script>

<template>
  <SalesModuleWorkbench
    title="内部报价台"
    description="业务部与工程部建单，按项目启用责任分段协作核价，主管审核后由业务部最终放行并受控导出。"
    badge="内部成本协作"
    :show-page-header="false"
    factory-context="all"
    :back-to="backNavigation.to"
    :back-label="backNavigation.label"
    wide-layout
  >
    <template #icon><Calculator aria-hidden="true" /></template>
    <div class="internal-quote-desk">
      <RouterView v-slot="{ Component, route: childRoute }">
        <Transition name="quote-route" mode="out-in" appear>
          <div :key="`${String(childRoute.name ?? childRoute.path)}:${String(childRoute.params.quoteId ?? '')}`" class="quote-route-page">
            <component :is="Component" />
          </div>
        </Transition>
      </RouterView>
    </div>
  </SalesModuleWorkbench>
</template>

<style scoped>
.internal-quote-desk {
  min-width: 0;
  font-size: 13px;
}

.quote-route-page {
  min-width: 0;
  transform-origin: top center;
}

.quote-route-enter-active,
.quote-route-leave-active {
  transition: opacity 220ms ease, transform 240ms ease, filter 220ms ease;
}

.quote-route-enter-from {
  opacity: 0;
  filter: blur(2px);
  transform: translateY(10px) scale(.995);
}

.quote-route-leave-to {
  opacity: 0;
  filter: blur(1px);
  transform: translateY(-6px) scale(.997);
}

.internal-quote-desk :deep(button),
.internal-quote-desk :deep(a) {
  transition: color 180ms ease, background-color 180ms ease, border-color 180ms ease, box-shadow 180ms ease, opacity 180ms ease, transform 180ms ease;
}

.internal-quote-desk :deep(button:not(:disabled):hover),
.internal-quote-desk :deep(a:hover) {
  transform: translateY(-1px);
}

.internal-quote-desk :deep(button:not(:disabled):active),
.internal-quote-desk :deep(a:active) {
  transform: translateY(0) scale(.98);
}

.internal-quote-desk :deep(button svg),
.internal-quote-desk :deep(a svg) {
  transition: transform 180ms ease;
}

.internal-quote-desk :deep(button:not(:disabled):hover svg),
.internal-quote-desk :deep(a:hover svg) {
  transform: scale(1.08);
}

.internal-quote-desk :deep(input),
.internal-quote-desk :deep(select),
.internal-quote-desk :deep(textarea) {
  font-size: 13px !important;
  transition: color 180ms ease, background-color 180ms ease, border-color 180ms ease, box-shadow 180ms ease;
}

.internal-quote-desk :deep(button) {
  font-size: 13px !important;
}

.internal-quote-desk :deep(a),
.internal-quote-desk :deep(label),
.internal-quote-desk :deep(dt),
.internal-quote-desk :deep(dd) {
  font-size: 12px !important;
}

.internal-quote-desk :deep(small),
.internal-quote-desk :deep(code) {
  font-size: 11px !important;
}

.internal-quote-desk :deep(th) {
  font-size: 11px !important;
}

.internal-quote-desk :deep(td),
.internal-quote-desk :deep(td strong),
.internal-quote-desk :deep(td span),
.internal-quote-desk :deep(td em),
.internal-quote-desk :deep(td b) {
  font-size: 12px !important;
}

.internal-quote-desk :deep(.quote-breadcrumb),
.internal-quote-desk :deep(.quote-stage-notice),
.internal-quote-desk :deep(.quote-page-message),
.internal-quote-desk :deep(.quote-lock-banner),
.internal-quote-desk :deep(.quote-dependency-strip),
.internal-quote-desk :deep(.quote-local-message),
.internal-quote-desk :deep(.quote-backend-note) {
  font-size: 12px !important;
}

.internal-quote-desk :deep(.quote-kpi-grid article > div),
.internal-quote-desk :deep(.quote-kpi-grid article > p),
.internal-quote-desk :deep(.quote-initiator),
.internal-quote-desk :deep(.quote-version),
.internal-quote-desk :deep(.quote-status),
.internal-quote-desk :deep(.quote-progress-cell strong),
.internal-quote-desk :deep(.quote-date),
.internal-quote-desk :deep(.quote-table-footer) {
  font-size: 12px !important;
}

.internal-quote-desk :deep(.quote-collaboration-page span),
.internal-quote-desk :deep(.quote-collaboration-page p),
.internal-quote-desk :deep(.quote-collaboration-page strong),
.internal-quote-desk :deep(.quote-collaboration-page em),
.internal-quote-desk :deep(.quote-collaboration-page b),
.internal-quote-desk :deep(.quote-collaboration-page h3) {
  font-size: 12px !important;
}

.internal-quote-desk :deep(.quote-title-row h1) {
  font-size: 26px !important;
}

.internal-quote-desk :deep(.quote-head-progress strong) {
  font-size: 20px !important;
}

.internal-quote-desk :deep(.quote-editor-title-row h2) {
  font-size: 19px !important;
}

.internal-quote-desk :deep(.quote-section-rail > header strong) {
  font-size: 14px !important;
}

.internal-quote-desk :deep(.quote-live-cost > strong) {
  font-size: 24px !important;
}

.internal-quote-desk :deep(.quote-summary-page span),
.internal-quote-desk :deep(.quote-summary-page p),
.internal-quote-desk :deep(.quote-summary-page small),
.internal-quote-desk :deep(.quote-summary-page em),
.internal-quote-desk :deep(.quote-summary-page dt),
.internal-quote-desk :deep(.quote-summary-page dd),
.internal-quote-desk :deep(.quote-summary-page header strong),
.internal-quote-desk :deep(.quote-export-page span),
.internal-quote-desk :deep(.quote-export-page p),
.internal-quote-desk :deep(.quote-export-page small),
.internal-quote-desk :deep(.quote-export-page em),
.internal-quote-desk :deep(.quote-export-page code),
.internal-quote-desk :deep(.quote-export-page h2) {
  font-size: 12px !important;
}

.internal-quote-desk :deep(.quote-total-card strong) {
  font-size: 22px !important;
}

.internal-quote-desk :deep(.quote-donut span) {
  font-size: 16px !important;
}

.internal-quote-desk :deep(.quote-final-release h2) {
  font-size: 18px !important;
}

.internal-quote-desk :deep(.quote-export-kpis strong),
.internal-quote-desk :deep(.quote-integrity-card strong) {
  font-size: 14px !important;
}

.internal-quote-desk :deep(.quote-kpi-grid article),
.internal-quote-desk :deep(.quote-logistics-grid article),
.internal-quote-desk :deep(.quote-release-grid article),
.internal-quote-desk :deep(.quote-export-kpis article),
.internal-quote-desk :deep(.quote-sheet-list > span),
.internal-quote-desk :deep(.quote-revision-matrix article),
.internal-quote-desk :deep(.quote-view-records article) {
  transition: border-color 200ms ease, box-shadow 200ms ease, transform 200ms ease;
}

.internal-quote-desk :deep(.quote-kpi-grid article:hover),
.internal-quote-desk :deep(.quote-logistics-grid article:hover),
.internal-quote-desk :deep(.quote-release-grid article:hover),
.internal-quote-desk :deep(.quote-export-kpis article:hover),
.internal-quote-desk :deep(.quote-sheet-list > span:hover),
.internal-quote-desk :deep(.quote-revision-matrix article:hover),
.internal-quote-desk :deep(.quote-view-records article:hover) {
  border-color: #99f6e4;
  box-shadow: 0 12px 24px rgb(15 118 110 / 10%);
  transform: translateY(-2px);
}

@media (prefers-reduced-motion: reduce) {
  .quote-route-enter-active,
  .quote-route-leave-active,
  .internal-quote-desk :deep(button),
  .internal-quote-desk :deep(a),
  .internal-quote-desk :deep(button svg),
  .internal-quote-desk :deep(a svg),
  .internal-quote-desk :deep(.quote-kpi-grid article),
  .internal-quote-desk :deep(.quote-logistics-grid article),
  .internal-quote-desk :deep(.quote-release-grid article),
  .internal-quote-desk :deep(.quote-export-kpis article),
  .internal-quote-desk :deep(.quote-sheet-list > span),
  .internal-quote-desk :deep(.quote-revision-matrix article),
  .internal-quote-desk :deep(.quote-view-records article) {
    transition: none;
  }
}
</style>

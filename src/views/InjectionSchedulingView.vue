<script setup lang="ts">
import { ArrowLeft, Factory, Layers3 } from '@lucide/vue'
import { computed, watchEffect } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import StatusPill from '@/components/common/StatusPill.vue'
import InjectionSchedulingDashboard from '@/components/modules/injection/InjectionSchedulingDashboard.vue'
import {
  factoryContexts,
  type FactoryContext,
  getDepartmentRoute,
  isProductionFactoryContextId,
  type ProductionFactoryContextId,
  type Tone,
} from '@/data/enterpriseMock'
import { getInjectionFactoryConfig } from '@/factories/injection/registry'
import { useInjectionModuleData } from '@/factories/injection/useInjectionModuleData'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const {
  injectionOverviewMetrics,
  injectionDataSourceStatus,
} = useInjectionModuleData()

type ProductionFactoryContext = FactoryContext & { id: ProductionFactoryContextId }

const productionFactories = factoryContexts.filter(
  (factory): factory is ProductionFactoryContext => isProductionFactoryContextId(factory.id),
)

const routeFactoryId = computed(() => {
  const rawFactory = Array.isArray(route.query.factory) ? route.query.factory[0] : route.query.factory

  return typeof rawFactory === 'string' && isProductionFactoryContextId(rawFactory)
    ? rawFactory
    : null
})

const selectedFactoryId = computed<ProductionFactoryContextId>(() => {
  if (routeFactoryId.value) {
    return routeFactoryId.value
  }

  return isProductionFactoryContextId(appStore.activeProductionFactory.id)
    ? appStore.activeProductionFactory.id
    : 'huaxing'
})

const activeFactory = computed(() =>
  productionFactories.find((factory) => factory.id === selectedFactoryId.value) ?? productionFactories[0],
)

const activeFactoryConfig = computed(() => getInjectionFactoryConfig(selectedFactoryId.value))
const overviewCards = computed(() => injectionOverviewMetrics.value.slice(0, 4))
const dataSourceCards = computed(() => injectionDataSourceStatus.value.slice(0, 3))

const toneClasses: Record<Tone, string> = {
  teal: 'border-teal-200 bg-teal-50 text-teal-900',
  blue: 'border-blue-200 bg-blue-50 text-blue-900',
  amber: 'border-amber-200 bg-amber-50 text-amber-900',
  red: 'border-red-200 bg-red-50 text-red-900',
  slate: 'border-slate-200 bg-slate-50 text-slate-900',
  green: 'border-emerald-200 bg-emerald-50 text-emerald-900',
}

watchEffect(() => {
  appStore.setActiveDepartment('production')
  appStore.setActiveFactory(selectedFactoryId.value)
})

watchEffect(() => {
  if (routeFactoryId.value) {
    return
  }

  router.replace({
    query: {
      ...route.query,
      factory: selectedFactoryId.value,
    },
  })
})

function setFactory(factoryId: ProductionFactoryContextId) {
  if (factoryId === selectedFactoryId.value) {
    return
  }

  router.push({
    query: {
      ...route.query,
      factory: factoryId,
    },
  })
}
</script>

<template>
  <main class="min-h-screen bg-[radial-gradient(circle_at_top_left,rgba(14,165,233,0.12),transparent_34%),linear-gradient(180deg,#f8fafc_0%,#eef4f8_100%)] px-4 py-6 text-slate-950 sm:px-6 xl:px-10">
    <div class="mx-auto max-w-[1680px] space-y-5">
      <div class="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <RouterLink
            :to="getDepartmentRoute('production')"
            class="inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-slate-950"
          >
            <ArrowLeft class="size-4" aria-hidden="true" />
            生产部模块中心
          </RouterLink>
          <div class="mt-3 flex flex-wrap items-center gap-3">
            <h1 class="text-3xl font-semibold tracking-tight">注塑生产中枢</h1>
            <StatusPill label="全页面工作台" tone="teal" />
            <StatusPill :label="activeFactoryConfig.processStatus" tone="blue" />
          </div>
          <p class="mt-2 text-sm text-slate-600">
            {{ activeFactory.name }} · {{ activeFactoryConfig.ownership }} · {{ activeFactoryConfig.dataStatus }}
          </p>
        </div>

        <div class="space-y-3 xl:w-[860px]">
          <div class="flex justify-end">
            <AccountMenu />
          </div>
          <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
            <article
              v-for="card in overviewCards"
              :key="card.label"
              class="min-h-[92px] rounded-lg border bg-white p-4"
              :class="toneClasses[card.tone]"
            >
              <p class="text-xs font-medium opacity-80">{{ card.label }}</p>
              <p class="mt-1 text-xl font-semibold text-slate-950">{{ card.value }}</p>
              <p class="mt-1 line-clamp-2 text-xs opacity-75">{{ card.detail }}</p>
            </article>
          </div>
        </div>
      </div>

      <section class="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_16px_38px_rgba(15,23,42,0.06)]">
        <div class="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div class="max-w-3xl">
            <div class="flex items-center gap-3">
              <span class="flex size-10 items-center justify-center rounded-xl bg-sky-50 text-sky-700">
                <Layers3 class="size-5" aria-hidden="true" />
              </span>
              <div>
                <h2 class="text-xl font-semibold tracking-tight text-slate-950">{{ activeFactoryConfig.moduleTitle }}</h2>
                <p class="mt-1 text-sm text-slate-600">{{ activeFactoryConfig.workspaceSummary }}</p>
              </div>
            </div>
            <div class="mt-4 flex flex-wrap gap-2">
              <span
                v-for="note in activeFactoryConfig.implementationNotes"
                :key="note"
                class="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600"
              >
                {{ note }}
              </span>
            </div>
          </div>

          <div class="min-w-0 xl:w-[520px]">
            <p class="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
              <Factory class="size-4" aria-hidden="true" />
              Factory Scope
            </p>
            <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <button
                v-for="factory in productionFactories"
                :key="factory.id"
                type="button"
                class="rounded-lg border px-3 py-2 text-left text-sm font-semibold transition-colors"
                :class="factory.id === selectedFactoryId
                  ? 'border-slate-950 bg-slate-950 text-white'
                  : 'border-slate-200 bg-slate-50 text-slate-700 hover:border-slate-300 hover:bg-white'"
                @click="setFactory(factory.id)"
              >
                {{ factory.shortName }}
              </button>
            </div>
          </div>
        </div>
      </section>

      <div class="grid gap-3 md:grid-cols-3">
        <article
          v-for="source in dataSourceCards"
          :key="source.name"
          class="rounded-lg border bg-white p-4"
          :class="toneClasses[source.statusTone]"
        >
          <div class="flex items-start justify-between gap-3">
            <div>
              <p class="text-xs font-semibold uppercase tracking-[0.18em] opacity-70">{{ source.name }}</p>
              <p class="mt-2 text-sm font-semibold text-slate-950">{{ source.freshness }}</p>
            </div>
            <StatusPill :label="source.status" :tone="source.statusTone" compact />
          </div>
          <p class="mt-3 text-sm leading-6 opacity-80">{{ source.summary }}</p>
        </article>
      </div>

      <InjectionSchedulingDashboard :show-hero="false" />
    </div>
  </main>
</template>

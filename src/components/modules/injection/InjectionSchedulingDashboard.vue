<script setup lang="ts">
import { computed, watchEffect } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import InjectionSectionNav from '@/components/modules/injection/InjectionSectionNav.vue'
import InjectionTaskPanel from '@/components/modules/injection/InjectionTaskPanel.vue'
import { isProductionFactoryContextId } from '@/data/enterpriseMock'
import type { InjectionSectionId } from '@/data/injectionSchedulingMock'
import { getInjectionFactoryConfig } from '@/factories/injection/registry'
import { useInjectionModuleData } from '@/factories/injection/useInjectionModuleData'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const { injectionSectionNav } = useInjectionModuleData()

const props = withDefaults(defineProps<{
  showHero?: boolean
}>(), {
  showHero: true,
})

const validSectionIds: InjectionSectionId[] = [
  'monthly-plan',
  'order-import',
  'smart-scheduling',
  'scheduling-results',
  'daily-report',
  'inbound-orders',
  'master-data',
]

const legacySectionMap: Record<string, InjectionSectionId> = {
  dashboard: 'monthly-plan',
  'data-center': 'order-import',
  execution: 'smart-scheduling',
  reporting: 'daily-report',
  config: 'master-data',
  'history-db': 'master-data',
  'machine-archive': 'master-data',
  'mold-targets': 'master-data',
}

const normalizeSection = (value: unknown): InjectionSectionId | null => {
  const raw = Array.isArray(value) ? value[0] : value

  if (typeof raw !== 'string') {
    return null
  }

  if (raw in legacySectionMap) {
    return legacySectionMap[raw]
  }

  return validSectionIds.includes(raw as InjectionSectionId)
    ? (raw as InjectionSectionId)
    : null
}

const activeSection = computed<InjectionSectionId>(() => normalizeSection(route.query.section) ?? 'monthly-plan')

const activeSectionMeta = computed(() =>
  injectionSectionNav.value.find((section) => section.id === activeSection.value) ?? injectionSectionNav.value[0],
)

const activeFactory = computed(() => appStore.activeProductionFactory)
const activeProductionFactoryId = computed(() =>
  isProductionFactoryContextId(activeFactory.value.id) ? activeFactory.value.id : 'huaxing',
)
const activeFactoryConfig = computed(() => getInjectionFactoryConfig(activeProductionFactoryId.value))

watchEffect(() => {
  if (normalizeSection(route.query.section)) {
    return
  }

  router.replace({
    query: {
      ...route.query,
      section: 'monthly-plan',
    },
  })
})

const handleSectionChange = (section: InjectionSectionId) => {
  if (section === activeSection.value) {
    return
  }

  router.push({
    query: {
      ...route.query,
      section,
    },
  })
}
</script>

<template>
  <div class="space-y-6">
    <section
      v-if="props.showHero"
      class="rounded-[30px] border border-slate-200 bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(248,250,252,0.98))] p-6 shadow-[0_16px_40px_rgba(15,23,42,0.06)]"
    >
      <div class="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div class="max-w-3xl">
          <p class="text-xs uppercase tracking-[0.28em] text-sky-700">Factory Planning Workspace</p>
          <h2 class="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
            {{ activeFactoryConfig.moduleTitle }}
          </h2>
          <p class="mt-3 text-base leading-7 text-slate-600">{{ activeFactoryConfig.workspaceSummary }}</p>
        </div>

        <div class="grid gap-3 sm:grid-cols-3 lg:min-w-[360px]">
          <div class="rounded-2xl border border-slate-200 bg-white px-4 py-4">
            <p class="text-xs uppercase tracking-[0.22em] text-slate-500">当前车间</p>
            <p class="mt-3 text-xl font-semibold text-slate-950">{{ activeFactory.shortName }}</p>
          </div>
          <div class="rounded-2xl border border-slate-200 bg-white px-4 py-4">
            <p class="text-xs uppercase tracking-[0.22em] text-slate-500">数据状态</p>
            <p class="mt-3 text-base font-semibold text-slate-950">{{ activeFactoryConfig.dataStatus }}</p>
          </div>
          <div class="rounded-2xl border border-slate-200 bg-white px-4 py-4">
            <p class="text-xs uppercase tracking-[0.22em] text-slate-500">当前页面</p>
            <p class="mt-3 text-base font-semibold text-slate-950">{{ activeSectionMeta.label }}</p>
          </div>
        </div>
      </div>
    </section>

    <div class="grid gap-6 xl:grid-cols-[280px_minmax(0,1fr)]">
      <aside class="xl:sticky xl:top-6 xl:self-start">
        <InjectionSectionNav :active-section="activeSection" @change="handleSectionChange" />
      </aside>

      <section class="space-y-5">
        <article class="rounded-[28px] border border-slate-200 bg-white px-6 py-5 shadow-[0_14px_35px_rgba(15,23,42,0.05)]">
          <p class="text-xs uppercase tracking-[0.22em] text-slate-500">当前操作</p>
          <div class="mt-3 flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h3 class="text-2xl font-semibold tracking-tight text-slate-950">{{ activeSectionMeta.label }}</h3>
              <p class="mt-2 text-sm leading-6 text-slate-600">{{ activeSectionMeta.summary }}</p>
            </div>
            <div class="flex flex-wrap gap-2">
              <span
                v-for="note in activeFactoryConfig.implementationNotes"
                :key="note"
                class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600"
              >
                {{ note }}
              </span>
            </div>
          </div>
        </article>

        <InjectionTaskPanel :active-section="activeSection" />
      </section>
    </div>
  </div>
</template>

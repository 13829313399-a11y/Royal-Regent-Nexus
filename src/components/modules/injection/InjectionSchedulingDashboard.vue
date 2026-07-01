<script setup lang="ts">
import { computed, watchEffect } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SectionPanel from '@/components/common/SectionPanel.vue'
import InjectionConfigPanel from '@/components/modules/injection/InjectionConfigPanel.vue'
import InjectionDashboardPanel from '@/components/modules/injection/InjectionDashboardPanel.vue'
import InjectionDataCenterPanel from '@/components/modules/injection/InjectionDataCenterPanel.vue'
import InjectionExecutionPanel from '@/components/modules/injection/InjectionExecutionPanel.vue'
import InjectionReportingPanel from '@/components/modules/injection/InjectionReportingPanel.vue'
import InjectionSectionNav from '@/components/modules/injection/InjectionSectionNav.vue'
import { isProductionFactoryContextId } from '@/data/enterpriseMock'
import type { InjectionSectionId } from '@/data/injectionSchedulingMock'
import { getInjectionFactoryConfig } from '@/factories/injection/registry'
import { useInjectionModuleData } from '@/factories/injection/useInjectionModuleData'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const { injectionSectionNav } = useInjectionModuleData()

const validSectionIds: InjectionSectionId[] = ['dashboard', 'data-center', 'execution', 'reporting', 'config']

const normalizeSection = (value: unknown): InjectionSectionId | null => {
  const raw = Array.isArray(value) ? value[0] : value

  if (typeof raw !== 'string') {
    return null
  }

  return validSectionIds.includes(raw as InjectionSectionId)
    ? (raw as InjectionSectionId)
    : null
}

const activeSection = computed<InjectionSectionId>(() => normalizeSection(route.query.section) ?? 'dashboard')

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
      section: 'dashboard',
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
    <SectionPanel>
      <div class="rounded-[28px] border border-slate-200 bg-[radial-gradient(circle_at_top_left,rgba(13,148,136,0.14),transparent_38%),linear-gradient(180deg,rgba(255,255,255,0.98),rgba(248,250,252,0.98))] p-1">
        <div class="rounded-[24px] bg-white/85 p-6">
          <div class="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
            <div class="max-w-3xl">
              <p class="text-xs uppercase tracking-[0.28em] text-teal-700">Production Planning Workspace</p>
              <h2 class="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
                {{ activeFactoryConfig.moduleTitle }} · {{ activeSectionMeta.label }}
              </h2>
              <p class="mt-3 text-base leading-7 text-slate-600">
                {{ activeFactoryConfig.workspaceSummary }}
              </p>
              <p class="mt-3 text-sm leading-7 text-slate-500">
                当前分栏：{{ activeSectionMeta.summary }}
              </p>
            </div>

            <div class="grid gap-3 sm:grid-cols-3 xl:min-w-[360px]">
              <div class="rounded-2xl border border-slate-200 bg-white px-4 py-4">
                <p class="text-xs uppercase tracking-[0.22em] text-slate-500">当前车间</p>
                <p class="mt-3 text-2xl font-semibold text-slate-950">{{ activeFactory.shortName }}</p>
              </div>
              <div class="rounded-2xl border border-slate-200 bg-white px-4 py-4">
                <p class="text-xs uppercase tracking-[0.22em] text-slate-500">数据状态</p>
                <p class="mt-3 text-lg font-semibold text-slate-950">{{ activeFactoryConfig.dataStatus }}</p>
              </div>
              <div class="rounded-2xl border border-slate-200 bg-white px-4 py-4">
                <p class="text-xs uppercase tracking-[0.22em] text-slate-500">流程状态</p>
                <p class="mt-3 text-lg font-semibold text-slate-950">{{ activeFactoryConfig.processStatus }}</p>
              </div>
            </div>
          </div>

          <div class="mt-6">
            <InjectionSectionNav :active-section="activeSection" @change="handleSectionChange" />
          </div>

          <div class="mt-6 grid gap-3 lg:grid-cols-[1.2fr_0.8fr]">
            <div class="grid gap-3 sm:grid-cols-3">
              <article
                v-for="item in activeFactoryConfig.highlights"
                :key="`${activeFactory.id}-${item.label}`"
                class="rounded-2xl border border-slate-200 bg-white px-4 py-4"
              >
                <p class="text-xs uppercase tracking-[0.22em] text-slate-500">{{ item.label }}</p>
                <p class="mt-3 text-xl font-semibold text-slate-950">{{ item.value }}</p>
              </article>
            </div>

            <article class="rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-5 py-4">
              <p class="text-xs uppercase tracking-[0.22em] text-slate-500">车间实现说明</p>
              <p class="mt-3 text-sm leading-6 text-slate-600">
                责任范围：{{ activeFactoryConfig.ownership }}
              </p>
              <div class="mt-3 flex flex-wrap gap-2">
                <span
                  v-for="note in activeFactoryConfig.implementationNotes"
                  :key="note"
                  class="rounded-full bg-white px-3 py-1 text-xs text-slate-600"
                >
                  {{ note }}
                </span>
              </div>
            </article>
          </div>
        </div>
      </div>
    </SectionPanel>

    <InjectionDashboardPanel v-if="activeSection === 'dashboard'" />
    <InjectionDataCenterPanel v-else-if="activeSection === 'data-center'" />
    <InjectionExecutionPanel v-else-if="activeSection === 'execution'" />
    <InjectionReportingPanel v-else-if="activeSection === 'reporting'" />
    <InjectionConfigPanel v-else />
  </div>
</template>

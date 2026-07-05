<script setup lang="ts">
import { ArrowRight, CheckCircle2, CircleDot, Clock3 } from '@lucide/vue'
import { computed, watchEffect } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import StatusPill from '@/components/common/StatusPill.vue'
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
  execution: 'scheduling-results',
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
const activeSectionIndex = computed(() =>
  Math.max(0, injectionSectionNav.value.findIndex((section) => section.id === activeSection.value)),
)
const workflowStateMeta = {
  done: {
    label: '已走过',
    tone: 'green',
    icon: CheckCircle2,
  },
  active: {
    label: '当前',
    tone: 'blue',
    icon: CircleDot,
  },
  pending: {
    label: '待进入',
    tone: 'slate',
    icon: Clock3,
  },
} as const
type WorkflowState = keyof typeof workflowStateMeta
const resolveWorkflowState = (index: number): WorkflowState => {
  if (index < activeSectionIndex.value) {
    return 'done'
  }

  return index === activeSectionIndex.value ? 'active' : 'pending'
}
const workflowSections = computed(() =>
  injectionSectionNav.value.map((section, index) => {
    return {
      ...section,
      sequence: index + 1,
      state: resolveWorkflowState(index),
    }
  }),
)
const nextSection = computed(() =>
  injectionSectionNav.value[Math.min(activeSectionIndex.value + 1, injectionSectionNav.value.length - 1)] ?? null,
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

        <article class="rounded-[28px] border border-slate-200 bg-white px-6 py-5 shadow-[0_14px_35px_rgba(15,23,42,0.05)]">
          <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p class="text-xs uppercase tracking-[0.22em] text-slate-500">生产闭环</p>
              <h3 class="mt-2 text-xl font-semibold tracking-tight text-slate-950">从订单池到入库回写</h3>
            </div>
            <button
              v-if="nextSection && nextSection.id !== activeSection"
              type="button"
              class="inline-flex items-center gap-2 rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800"
              @click="handleSectionChange(nextSection.id)"
            >
              下一步：{{ nextSection.label }}
              <ArrowRight class="size-4" aria-hidden="true" />
            </button>
          </div>

          <div class="mt-5 grid gap-2 md:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-7">
            <button
              v-for="step in workflowSections"
              :key="step.id"
              type="button"
              class="flex min-h-24 items-start gap-3 rounded-xl border px-3 py-3 text-left transition"
              :class="step.state === 'active'
                ? 'border-blue-200 bg-blue-50'
                : step.state === 'done'
                  ? 'border-emerald-100 bg-emerald-50'
                  : 'border-slate-200 bg-slate-50 hover:border-slate-300 hover:bg-white'"
              @click="handleSectionChange(step.id)"
            >
              <span
                class="flex size-8 shrink-0 items-center justify-center rounded-lg"
                :class="step.state === 'active'
                  ? 'bg-blue-600 text-white'
                  : step.state === 'done'
                    ? 'bg-emerald-600 text-white'
                    : 'bg-white text-slate-500'"
              >
                <component :is="workflowStateMeta[step.state].icon" class="size-4" aria-hidden="true" />
              </span>
              <span class="min-w-0 flex-1">
                <span class="flex flex-wrap items-center gap-2">
                  <span class="text-sm font-semibold text-slate-950">{{ step.sequence }}. {{ step.label }}</span>
                  <StatusPill
                    :label="workflowStateMeta[step.state].label"
                    :tone="workflowStateMeta[step.state].tone"
                    compact
                  />
                </span>
                <span class="mt-2 line-clamp-2 block text-xs leading-5 text-slate-500">{{ step.summary }}</span>
              </span>
            </button>
          </div>
        </article>

        <InjectionTaskPanel :active-section="activeSection" @change-section="handleSectionChange" />
      </section>
    </div>
  </div>
</template>

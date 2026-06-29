<script setup lang="ts">
import { Plus } from '@lucide/vue'
import { computed } from 'vue'
import {
  engineeringModules,
  getMoldingSampleModuleStats,
  quickModuleCandidates,
} from '@/data/enterpriseMock'
import DepartmentTabs from '@/components/modules/DepartmentTabs.vue'
import ModuleCard from '@/components/modules/ModuleCard.vue'
import PermissionMatrix from '@/components/modules/PermissionMatrix.vue'
import TodoQueue from '@/components/modules/TodoQueue.vue'
import ProgressMeter from '@/components/common/ProgressMeter.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()

const title = computed(() => `${appStore.activeProductionFactory.name} · 部门模块中心`)
const activeFactoryId = computed(() => appStore.activeProductionFactory.id)
const activeFactoryModules = computed(() => engineeringModules.map((module) => {
  if (module.id !== 'molding-sample') return module

  return {
    ...module,
    owner: `${appStore.activeProductionFactory.shortName} · 工程部公共模块`,
    stats: getMoldingSampleModuleStats(activeFactoryId.value),
    to: `/modules/molding-sample?factory=${activeFactoryId.value}`,
  }
}))
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
      <div>
        <h1 class="text-3xl font-semibold tracking-tight text-slate-950">{{ title }}</h1>
        <p class="mt-2 text-sm text-slate-600">
          按部门承载模块，先把入口、权限、状态、待办统一起来
        </p>
      </div>
      <button type="button" class="inline-flex h-10 items-center gap-2 rounded-lg bg-slate-950 px-6 text-sm font-semibold text-white">
        <Plus class="size-4" aria-hidden="true" />
        新增系统模块
      </button>
    </div>

    <DepartmentTabs />

    <div class="grid gap-6 xl:grid-cols-[1fr_380px]">
      <SectionPanel
        title="工程部模块"
        subtitle="模块卡片统一展示负责人、状态、待办、关键数据"
      >
        <div class="grid gap-5 md:grid-cols-2">
          <ModuleCard v-for="module in activeFactoryModules" :key="module.id" :module="module" />
        </div>

        <div class="mt-7 rounded-lg border border-slate-200 bg-white p-5">
          <h3 class="font-semibold text-slate-950">推荐下一批模块</h3>
          <p class="mt-3 text-sm text-slate-700">
            {{ quickModuleCandidates.join('、') }}
          </p>
          <div class="mt-5">
            <ProgressMeter :value="40" tone="teal" />
          </div>
          <p class="mt-4 text-xs text-slate-500">
            优先级建议：先做会牵动生产 / QA / PMC 的跨部门流程模块
          </p>
        </div>
      </SectionPanel>

      <aside class="space-y-6">
        <PermissionMatrix />
        <TodoQueue />
      </aside>
    </div>
  </div>
</template>

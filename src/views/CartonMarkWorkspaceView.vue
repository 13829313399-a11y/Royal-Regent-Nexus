<script setup lang="ts">
import { ArrowLeft, PackageCheck } from '@lucide/vue'
import { computed, watch } from 'vue'
import { RouterLink } from 'vue-router'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import CartonMarkCheckPanel from '@/components/modules/qa/CartonMarkCheckPanel.vue'
import { getDepartmentRoute } from '@/data/enterpriseMock'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()

type CartonMarkWorkspaceMode = 'warehouse' | 'qa'

const props = defineProps<{
  workspaceMode: CartonMarkWorkspaceMode
}>()

const isWarehouseWorkspace = computed(() => props.workspaceMode === 'warehouse')
const currentDepartmentId = computed(() => isWarehouseWorkspace.value ? 'pmc-warehouse' : 'qa')
const workspaceTitle = computed(() => isWarehouseWorkspace.value ? '箱唛资料模板' : '箱唛核验')
const workspaceSubtitle = computed(() => isWarehouseWorkspace.value ? '客户箱唛 PDF 模板入库' : '实拍箱唛自动核对')
const departmentRoute = computed(() => getDepartmentRoute(currentDepartmentId.value))
const activeFactory = computed(() => appStore.activeProductionFactory)

watch(currentDepartmentId, (departmentId) => {
  appStore.setActiveDepartment(departmentId)
}, { immediate: true })
</script>

<template>
  <main class="min-h-screen bg-slate-100 text-[13px] leading-relaxed text-slate-900">
    <header class="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div class="mx-auto flex max-w-[1720px] flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5 sm:px-5">
        <RouterLink
          :to="departmentRoute"
          class="inline-flex h-9 shrink-0 items-center gap-2 whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-950"
        >
          <ArrowLeft class="size-4" aria-hidden="true" />
          <span class="hidden sm:inline">返回{{ isWarehouseWorkspace ? 'PMC / 仓管' : 'QA 部' }}</span>
          <span class="sm:hidden">返回</span>
        </RouterLink>

        <div class="flex min-w-0 items-center gap-2.5">
          <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-white">
            <PackageCheck class="size-5" aria-hidden="true" />
          </span>
          <div class="min-w-0">
            <div class="truncate text-[15px] font-bold leading-tight">{{ workspaceTitle }}</div>
            <div class="truncate text-[11px] text-slate-400">{{ workspaceSubtitle }}</div>
          </div>
        </div>

        <div class="ml-auto flex items-center gap-3">
          <span class="hidden h-8 items-center rounded-lg border border-slate-200 px-2.5 text-[12px] font-medium text-slate-600 sm:inline-flex">
            {{ activeFactory.shortName }}
          </span>
          <AccountMenu />
        </div>
      </div>
    </header>

    <section class="mx-auto max-w-[1720px] px-4 py-5 sm:px-5 sm:py-6">
      <CartonMarkCheckPanel :workspace-mode="workspaceMode" />
    </section>
  </main>
</template>

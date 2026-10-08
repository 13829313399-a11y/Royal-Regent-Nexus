<script setup lang="ts">
import { ArrowLeft, PackageCheck } from '@lucide/vue'
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import CartonMarkCheckPanel from '@/components/modules/qa/CartonMarkCheckPanel.vue'
import CartonMarkAssetLibrary from '@/components/CartonMarkAssetLibrary.vue'
import type { CartonMarkAsset } from '@/api/cartonMark'
import { getDepartmentRoute, getFactoryScopedRoute } from '@/data/enterpriseMock'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
const checkPanel = ref<InstanceType<typeof CartonMarkCheckPanel> | null>(null)
const route = useRoute()
const workspaceTab = ref<'library' | 'check'>(route.query.panel === 'check' ? 'check' : 'library')
async function useAsset(asset: CartonMarkAsset) {
  if (asset.kind === 'image') return
  workspaceTab.value = 'check'
  await checkPanel.value?.useLibraryAsset(asset)
}
async function useSources(assets: CartonMarkAsset[]) {
  workspaceTab.value = 'check'
  await nextTick()
  await Promise.all(assets.map(asset => checkPanel.value?.useLibraryAsset(asset)))
}

type CartonMarkWorkspaceMode = 'warehouse' | 'qa' | 'qc'

const props = defineProps<{
  workspaceMode: CartonMarkWorkspaceMode
}>()

const isWarehouseWorkspace = computed(() => props.workspaceMode === 'warehouse')
const isQcWorkspace = computed(() => props.workspaceMode === 'qc')
const currentDepartmentId = computed(() => {
  if (isWarehouseWorkspace.value) return 'pmc-warehouse'
  return isQcWorkspace.value ? 'qc' : 'qa'
})
const returnDepartmentLabel = computed(() => {
  if (isWarehouseWorkspace.value) return 'PMC / 仓管'
  return isQcWorkspace.value ? 'QC 部' : 'QA 部'
})
const workspaceTitle = computed(() => isWarehouseWorkspace.value ? '箱唛资料模板' : '箱唛核验')
const workspaceSubtitle = computed(() => isWarehouseWorkspace.value ? '批量存入资料仓库 · 按合同关联订单 · Excel / PDF 核对' : '打印 PDF 与现场箱唛照片核对')
const activeFactory = computed(() => appStore.activeProductionFactory)
const departmentRoute = computed(() => getFactoryScopedRoute(
  getDepartmentRoute(currentDepartmentId.value),
  activeFactory.value.id,
))

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
          <span class="hidden sm:inline">返回{{ returnDepartmentLabel }}</span>
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
      <div v-if="isWarehouseWorkspace" class="mb-4 flex gap-2" aria-label="箱唛工作区">
        <button type="button" :aria-pressed="workspaceTab === 'library'" class="rounded-lg px-4 py-2 font-semibold" :class="workspaceTab === 'library' ? 'bg-teal-700 text-white' : 'border bg-white text-slate-600'" @click="workspaceTab = 'library'">资料仓库</button>
        <button type="button" :aria-pressed="workspaceTab === 'check'" class="rounded-lg px-4 py-2 font-semibold" :class="workspaceTab === 'check' ? 'bg-teal-700 text-white' : 'border bg-white text-slate-600'" @click="workspaceTab = 'check'">Excel / PDF 核对</button>
      </div>
      <p v-if="isWarehouseWorkspace" class="mb-4 rounded-lg border border-teal-100 bg-teal-50 px-4 py-3 text-sm text-teal-800">资料仓库选取原文件 → Excel / PDF 内容核对 → 核对通过或人工放行 → QC 现场拍照核验</p>
      <CartonMarkAssetLibrary v-if="isWarehouseWorkspace" v-show="workspaceTab === 'library'" :factory-id="activeFactory.id" check-enabled @use="useAsset" @use-sources="useSources" />
      <CartonMarkCheckPanel ref="checkPanel" v-show="!isWarehouseWorkspace || workspaceTab === 'check'" :workspace-mode="workspaceMode" />
    </section>
  </main>
</template>

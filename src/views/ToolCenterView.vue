<script setup lang="ts">
import { FileSpreadsheet, Plus, ShieldCheck } from '@lucide/vue'
import { computed } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'
import PdfToExcelTool from '@/components/tools/PdfToExcelTool.vue'
import { useAppStore } from '@/stores/app'


const appStore = useAppStore()
const factoryContextLabel = computed(() => `${appStore.activeProductionFactory.shortName}厂区`)
</script>

<template>
  <div class="app-page space-y-6">
    <PageHeader
      eyebrow="Shared Tool Center"
      title="公共工具栏"
      :description="`不归属单一部门的轻量工具集合；${factoryContextLabel}及其他厂区均可直接使用。`"
    >
      <template #actions>
        <span class="inline-flex h-10 items-center gap-2 rounded-xl border border-teal-200 bg-teal-50 px-4 text-sm font-semibold text-teal-800">
          <ShieldCheck class="size-4" aria-hidden="true" />
          全厂区共享
        </span>
      </template>
    </PageHeader>

    <section class="grid gap-4 lg:grid-cols-[240px_minmax(0,1fr)]" aria-label="公共工具目录">
      <aside class="h-fit rounded-2xl border border-slate-200/90 bg-white p-3 shadow-sm">
        <div class="px-3 pb-3 pt-2">
          <p class="text-xs font-bold uppercase tracking-[0.14em] text-slate-400">工具目录</p>
          <p class="mt-1 text-xs leading-5 text-slate-500">后续公共工具会继续在这里增加。</p>
        </div>

        <a href="#pdf-to-excel" class="flex items-center gap-3 rounded-xl bg-teal-50 px-3 py-3 text-teal-900 ring-1 ring-teal-100">
          <span class="flex size-9 items-center justify-center rounded-lg bg-white text-teal-700 shadow-sm">
            <FileSpreadsheet class="size-4.5" aria-hidden="true" />
          </span>
          <span class="min-w-0">
            <strong class="block truncate text-sm">PDF 转 Excel</strong>
            <small class="mt-0.5 block text-xs text-teal-700/70">文件转换</small>
          </span>
        </a>

        <div class="mt-2 flex items-center gap-3 rounded-xl border border-dashed border-slate-200 px-3 py-3 text-slate-400">
          <span class="flex size-9 items-center justify-center rounded-lg bg-slate-50">
            <Plus class="size-4" aria-hidden="true" />
          </span>
          <span>
            <strong class="block text-sm font-medium">更多工具</strong>
            <small class="mt-0.5 block text-xs">待后续添加</small>
          </span>
        </div>
      </aside>

      <div id="pdf-to-excel" class="min-w-0 scroll-mt-24">
        <PdfToExcelTool :context-label="factoryContextLabel" />
      </div>
    </section>
  </div>
</template>

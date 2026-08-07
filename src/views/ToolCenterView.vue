<script setup lang="ts">
import { FileSpreadsheet, FileText, Languages, Plus, Scissors, ShieldCheck } from '@lucide/vue'
import { computed, ref } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'
import DocumentTranslationTool from '@/components/tools/DocumentTranslationTool.vue'
import PdfSplitTool from '@/components/tools/PdfSplitTool.vue'
import PdfToExcelTool from '@/components/tools/PdfToExcelTool.vue'
import PdfToWordTool from '@/components/tools/PdfToWordTool.vue'
import { useAppStore } from '@/stores/app'


const appStore = useAppStore()
const factoryContextLabel = computed(() => `${appStore.activeProductionFactory.shortName}厂区`)
const activeTool = ref<'pdf-to-excel' | 'pdf-to-word' | 'pdf-split' | 'document-translation'>('pdf-to-excel')
const toolItems = [
  { id: 'pdf-to-excel' as const, label: 'PDF 转 Excel', description: '表格与版式转换', icon: FileSpreadsheet },
  { id: 'pdf-to-word' as const, label: 'PDF 转 Word', description: '可编辑文档转换', icon: FileText },
  { id: 'pdf-split' as const, label: 'PDF 拆分', description: '逐页或页段拆分', icon: Scissors },
  { id: 'document-translation' as const, label: '文档翻译', description: 'Excel / Word 中英互译', icon: Languages },
]
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

        <nav class="space-y-2" aria-label="公共工具">
          <button
            v-for="tool in toolItems"
            :key="tool.id"
            type="button"
            class="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition"
            :class="activeTool === tool.id
              ? 'bg-teal-50 text-teal-900 ring-1 ring-teal-100'
              : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'"
            :aria-current="activeTool === tool.id ? 'page' : undefined"
            @click="activeTool = tool.id"
          >
            <span
              class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-white shadow-sm ring-1"
              :class="activeTool === tool.id ? 'text-teal-700 ring-teal-100' : 'text-slate-500 ring-slate-200'"
            >
              <component :is="tool.icon" class="size-4.5" aria-hidden="true" />
            </span>
            <span class="min-w-0">
              <strong class="block truncate text-sm">{{ tool.label }}</strong>
              <small class="mt-0.5 block truncate text-xs" :class="activeTool === tool.id ? 'text-teal-700/70' : 'text-slate-400'">{{ tool.description }}</small>
            </span>
          </button>
        </nav>

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

      <div class="min-w-0">
        <PdfToExcelTool v-if="activeTool === 'pdf-to-excel'" :context-label="factoryContextLabel" />
        <PdfToWordTool v-else-if="activeTool === 'pdf-to-word'" :context-label="factoryContextLabel" />
        <PdfSplitTool v-else-if="activeTool === 'pdf-split'" :context-label="factoryContextLabel" />
        <DocumentTranslationTool v-else :context-label="factoryContextLabel" />
      </div>
    </section>
  </div>
</template>

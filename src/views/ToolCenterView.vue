<script setup lang="ts">
import { ShieldCheck } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { sharedToolsApi, type DocumentToolsCapabilities } from '@/api/tools'
import PageHeader from '@/components/common/PageHeader.vue'
import DocumentToolTabs from '@/features/document-studio/components/DocumentToolTabs.vue'
import DocumentWorkspaceShell from '@/features/document-studio/components/DocumentWorkspaceShell.vue'
import PdfBatchRenameWorkspace from '@/features/document-studio/components/PdfBatchRenameWorkspace.vue'
import { isDocumentToolId, type DocumentToolId } from '@/features/document-studio/types'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
const route = useRoute()
const router = useRouter()
const factoryContextLabel = computed(() => `${appStore.activeProductionFactory.shortName}厂区`)
const activeTool = ref<DocumentToolId>(isDocumentToolId(route.query.tool) ? route.query.tool : 'pdf-to-excel')
const capabilities = ref<DocumentToolsCapabilities | null>(null)
const capabilitiesError = ref('')

onMounted(async () => {
  try {
    capabilities.value = await sharedToolsApi.getCapabilities()
  }
  catch (error) {
    capabilitiesError.value = error instanceof Error
      ? error.message
      : '无法读取服务器文档工具能力。'
  }
})

watch(activeTool, (tool) => {
  if (route.query.tool === tool) return
  void router.replace({ query: { ...route.query, tool } })
})

watch(() => route.query.tool, (tool) => {
  if (isDocumentToolId(tool) && tool !== activeTool.value) activeTool.value = tool
})
</script>

<template>
  <div class="app-page space-y-3">
    <PageHeader
      eyebrow="Public Document Studio"
      title="智能文档工作台"
      :description="`文档转换、结构化提取、翻译、拆分与批量整理；${factoryContextLabel}及其他厂区均可使用。`"
    >
      <template #actions>
        <span class="inline-flex h-10 items-center gap-2 rounded-xl border border-teal-200 bg-teal-50 px-4 text-sm font-semibold text-teal-800">
          <ShieldCheck class="size-4" aria-hidden="true" />
          全厂区共享
        </span>
      </template>
    </PageHeader>

    <section class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm" aria-label="智能文档工作台">
      <DocumentToolTabs v-model="activeTool" :capabilities="capabilities" />
      <PdfBatchRenameWorkspace
        v-if="activeTool === 'pdf-batch-rename'"
        :context-label="factoryContextLabel"
        :factory-id="String(appStore.activeProductionFactory.id)"
        :capability="capabilities?.tools['pdf-batch-rename'] ?? null"
      />
      <DocumentWorkspaceShell
        v-else
        :tool-id="activeTool"
        :context-label="factoryContextLabel"
        :factory-id="String(appStore.activeProductionFactory.id)"
        :capabilities="capabilities"
        :capabilities-error="capabilitiesError"
      />
    </section>
  </div>
</template>

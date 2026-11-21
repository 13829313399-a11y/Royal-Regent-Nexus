<script setup lang="ts">
import { X } from '@lucide/vue'
import { onBeforeUnmount, ref, useId, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { useDialogFocus } from '@/composables/useDialogFocus'
import PdfCanvas from '@/features/document-tools/PdfCanvas.vue'

const props = defineProps<{ file: File; returnFocus?: HTMLElement }>()
const emit = defineEmits<{ close: [] }>()
const root = ref<HTMLElement | null>(null)
const closeButton = ref<HTMLElement | null>(null)
const titleId = useId()
const url = ref('')
const error = ref('')
const pageIndex = ref(0)

function releaseUrl() {
  if (url.value) URL.revokeObjectURL(url.value)
  url.value = ''
}

watch(() => props.file, (file) => {
  releaseUrl()
  pageIndex.value = 0
  error.value = ''
  try { url.value = URL.createObjectURL(file) }
  catch { error.value = '无法打开原 PDF，请关闭后重试。' }
}, { immediate: true })

useDialogFocus(() => true, root, {
  onEscape: () => emit('close'),
  initialFocus: () => closeButton.value,
  returnFocus: () => props.returnFocus ?? null,
  inertBackground: true,
})
onBeforeUnmount(releaseUrl)
</script>

<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-2 sm:p-4" @click.self="emit('close')">
      <section ref="root" role="dialog" aria-modal="true" :aria-labelledby="titleId" tabindex="-1" class="flex h-[calc(100dvh-1rem)] max-h-[960px] w-full max-w-[1440px] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white text-slate-800 shadow-xl sm:h-[calc(100dvh-2rem)]">
        <header class="flex shrink-0 items-start justify-between gap-4 border-b border-slate-200 px-4 py-3">
          <div class="min-w-0">
            <h2 :id="titleId" class="text-base font-semibold text-slate-950">原 PDF 预览与补充</h2>
            <p class="mt-1 break-all text-sm text-slate-600">{{ file.name }}</p>
          </div>
          <button ref="closeButton" type="button" aria-label="关闭原 PDF 预览" class="flex size-9 shrink-0 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-teal-600" @click="emit('close')"><X class="size-5" aria-hidden="true" /></button>
        </header>
        <div class="source-preview-content min-h-0 flex-1 overflow-y-auto lg:overflow-hidden">
          <div class="source-preview-document min-h-0 min-w-0 overflow-hidden bg-slate-100" aria-label="上传的原 PDF">
            <p v-if="error" role="alert" class="p-4 text-sm text-rose-700">{{ error }}</p>
            <PdfCanvas v-else-if="url" :url="url" :page-index="pageIndex" @page="pageIndex = $event" />
          </div>
          <aside class="min-h-0 min-w-0 border-t border-slate-200 bg-white p-4 lg:overflow-y-auto lg:border-l lg:border-t-0" aria-label="核对并补充命名">
            <slot />
            <Button variant="outline" class="mt-4 w-full" @click="emit('close')">返回改名预览</Button>
          </aside>
        </div>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.source-preview-content { display: grid; grid-template-columns: minmax(0, 1fr); align-content: start; }
.source-preview-document { height: 52dvh; min-height: 240px; }
.source-preview-document :deep(.dt-pdf) { height: 100%; min-height: 0; }
.source-preview-document :deep(.dt-pdf-toolbar) { flex-wrap: wrap; flex-shrink: 0; }
.source-preview-document :deep(.dt-pdf-scroll) { min-height: 0; }
@media (min-width: 1024px) {
  .source-preview-content { grid-template-columns: minmax(0, 1fr) 320px; align-content: stretch; }
  .source-preview-document { height: 100%; min-height: 0; }
}
</style>

<script setup lang="ts">
import { FileUp, LockKeyhole } from '@lucide/vue'
import { ref } from 'vue'
import { Button } from '@/components/ui/button'
import type { DocumentToolDefinition } from '../types'
import { validateDocumentFile } from '../types'

const props = defineProps<{ tool: DocumentToolDefinition }>()
const emit = defineEmits<{
  select: [files: File[]]
  error: [message: string]
}>()

const inputRef = ref<HTMLInputElement | null>(null)
const dragging = ref(false)

function choose(files: FileList | File[] | undefined) {
  const selected = Array.from(files ?? [])
  if (!selected.length) return
  if (selected.length > 10) {
    emit('error', '单次批量最多选择 10 个文件。')
    return
  }
  for (const file of selected) {
    const error = validateDocumentFile(file, props.tool)
    if (error) {
      emit('error', `${file.name}：${error}`)
      return
    }
  }
  emit('select', selected)
}

function handleDrop(event: DragEvent) {
  dragging.value = false
  choose(event.dataTransfer?.files)
}
</script>

<template>
  <section class="grid min-h-[520px] place-items-center px-5 py-10 sm:px-10" aria-labelledby="document-dropzone-title">
    <div
      class="w-full max-w-3xl rounded-2xl border-2 border-dashed px-6 py-14 text-center transition-colors sm:px-12"
      :class="dragging ? 'border-teal-500 bg-teal-50/70' : 'border-slate-300 bg-white hover:border-teal-300 hover:bg-teal-50/20'"
      @dragenter.prevent="dragging = true"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="handleDrop"
    >
      <input
        ref="inputRef"
        class="sr-only"
        type="file"
        multiple
        :accept="tool.accept"
        @change="choose(($event.target as HTMLInputElement).files ?? undefined)"
      >
      <span class="mx-auto flex size-16 items-center justify-center rounded-2xl bg-teal-50 text-teal-700 ring-1 ring-teal-100">
        <FileUp class="size-7" aria-hidden="true" />
      </span>
      <h2 id="document-dropzone-title" class="mt-6 text-xl font-semibold tracking-tight text-slate-950">
        上传{{ tool.extensionLabel }}文件开始处理
      </h2>
      <p class="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-500">
        将一个或多个文件拖放到这里，或从本机选择。单个文件最大 20 MB，批量最多 10 个；处理结果始终生成新文件，不修改源文件。
      </p>
      <Button class="mt-6" size="lg" @click="inputRef?.click()">
        选择文件
      </Button>
      <div class="mt-6 flex items-center justify-center gap-2 text-xs font-medium text-slate-500">
        <LockKeyhole class="size-3.5 text-teal-700" aria-hidden="true" />
        当前已上线转换默认在本地确定性链路处理
      </div>
    </div>
  </section>
</template>

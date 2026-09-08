<script setup lang="ts">
import {
  FileOutput,
  FileSpreadsheet,
  FileText,
  Files,
  Languages,
  Scissors,
} from '@lucide/vue'
import { computed, nextTick, ref } from 'vue'
import type { DocumentToolsCapabilities } from '@/api/tools'
import { DOCUMENT_TOOLS } from '../constants'
import type { DocumentToolId } from '../types'

const props = defineProps<{
  modelValue: DocumentToolId
  capabilities?: DocumentToolsCapabilities | null
}>()
const emit = defineEmits<{ 'update:modelValue': [value: DocumentToolId] }>()

const icons = {
  'pdf-to-excel': FileSpreadsheet,
  'pdf-to-word': FileText,
  'word-to-pdf': FileOutput,
  'pdf-translation': Languages,
  'pdf-split': Scissors,
  'pdf-batch-rename': Files,
}
const activeIndex = computed(() => DOCUMENT_TOOLS.findIndex(tool => tool.id === props.modelValue))
const tabListRef = ref<HTMLElement | null>(null)

function capability(toolId: DocumentToolId) {
  return props.capabilities?.tools[toolId]
}

function moveFocus(offset: number) {
  const nextIndex = (activeIndex.value + offset + DOCUMENT_TOOLS.length) % DOCUMENT_TOOLS.length
  emit('update:modelValue', DOCUMENT_TOOLS[nextIndex].id)
  void nextTick(() => {
    tabListRef.value?.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]')?.focus()
  })
}
</script>

<template>
  <div
    ref="tabListRef"
    class="overflow-x-auto border-b border-slate-200 bg-white px-2 sm:px-4"
    role="tablist"
    aria-label="文档工具"
    @keydown.left.prevent="moveFocus(-1)"
    @keydown.right.prevent="moveFocus(1)"
  >
    <div class="flex min-w-max items-center gap-1">
      <button
        v-for="tool in DOCUMENT_TOOLS"
        :key="tool.id"
        type="button"
        role="tab"
        class="group relative flex h-16 items-center gap-2.5 rounded-t-lg px-4 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-600 focus-visible:ring-offset-[-2px]"
        :class="modelValue === tool.id ? 'text-teal-800' : 'text-slate-500 hover:bg-slate-50 hover:text-slate-800'"
        :aria-selected="modelValue === tool.id"
        :tabindex="modelValue === tool.id ? 0 : -1"
        @click="emit('update:modelValue', tool.id)"
      >
        <component :is="icons[tool.id]" class="size-4.5" aria-hidden="true" />
        <span>{{ tool.label }}</span>
        <span
          class="size-2 rounded-full"
          :class="capability(tool.id)?.available === false
            ? 'bg-rose-400'
            : capability(tool.id)?.available === true
              ? 'bg-emerald-500'
              : 'animate-pulse bg-slate-300'"
          :title="capability(tool.id)?.reason || (capability(tool.id)?.available ? '服务器能力可用' : '正在读取服务器能力')"
          aria-hidden="true"
        />
        <span
          v-if="capability(tool.id)?.available === false"
          class="rounded-full bg-rose-50 px-1.5 py-0.5 text-[10px] font-bold text-rose-600"
        >
          不可用
        </span>
        <span
          class="absolute inset-x-3 bottom-0 h-0.5 rounded-full bg-teal-700 transition-opacity"
          :class="modelValue === tool.id ? 'opacity-100' : 'opacity-0'"
          aria-hidden="true"
        />
      </button>
    </div>
  </div>
</template>

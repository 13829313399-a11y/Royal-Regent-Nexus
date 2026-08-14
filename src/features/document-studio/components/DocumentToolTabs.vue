<script setup lang="ts">
import {
  FileOutput,
  FileSpreadsheet,
  FileText,
  Languages,
  Scissors,
} from '@lucide/vue'
import { computed, nextTick, ref } from 'vue'
import { DOCUMENT_TOOLS } from '../constants'
import type { DocumentToolId } from '../types'

const props = defineProps<{ modelValue: DocumentToolId }>()
const emit = defineEmits<{ 'update:modelValue': [value: DocumentToolId] }>()

const icons = {
  'pdf-to-excel': FileSpreadsheet,
  'pdf-to-word': FileText,
  'word-to-pdf': FileOutput,
  'pdf-translation': Languages,
  'pdf-split': Scissors,
}
const activeIndex = computed(() => DOCUMENT_TOOLS.findIndex(tool => tool.id === props.modelValue))
const tabListRef = ref<HTMLElement | null>(null)

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
          v-if="!tool.available"
          class="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold text-slate-500"
        >
          受控开放
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

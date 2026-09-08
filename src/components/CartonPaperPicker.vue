<script setup lang="ts">
import { computed, ref } from 'vue'
const props = defineProps<{ modelValue: string; options: string[]; label: string; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const open = ref(false), root = ref<HTMLElement>()
const normalize = (value: string) => value.normalize('NFKC').toLowerCase().replace(/[\s×*]/g, '')
const matches = computed(() => props.options.filter(value => normalize(value).includes(normalize(props.modelValue))))
function leave(event: FocusEvent) { if (!root.value?.contains(event.relatedTarget as Node | null)) open.value = false }
function choose(value: string) { emit('update:modelValue', value); open.value = false }
</script>
<template>
  <div ref="root" class="relative min-w-0" @focusout="leave" @keydown.esc.stop="open = false">
    <div class="flex h-9 overflow-hidden rounded-lg border border-slate-200 bg-white focus-within:border-teal-500">
      <input :value="modelValue" :aria-label="label" :disabled="disabled" placeholder="输入或选择" autocomplete="off" class="min-w-0 w-full bg-transparent px-2 text-xs outline-none disabled:bg-slate-100" @input="emit('update:modelValue', ($event.target as HTMLInputElement).value); open = true" @focus="open = Boolean(modelValue.trim())">
      <button type="button" :aria-label="`选择${label}`" :disabled="disabled" class="px-2 text-slate-500 hover:bg-teal-50 disabled:bg-slate-100" @click="open = !open">⌄</button>
    </div>
    <div v-if="open && !disabled" class="absolute left-0 top-full z-50 mt-1 max-h-52 w-full min-w-44 overflow-auto rounded-lg border border-teal-200 bg-white p-1 shadow-lg" :aria-label="`${label}候选`">
      <button v-for="value in matches.slice(0, 30)" :key="value" type="button" class="block w-full break-words rounded px-2 py-2 text-left text-xs hover:bg-teal-50 focus:bg-teal-50" @click="choose(value)">{{ value }}</button>
      <p v-if="!matches.length" class="p-2 text-xs text-slate-500">暂无相似资料，可保留手填内容。</p>
      <p v-if="matches.length > 30" class="p-2 text-xs text-slate-500">继续输入可缩小范围。</p>
    </div>
  </div>
</template>

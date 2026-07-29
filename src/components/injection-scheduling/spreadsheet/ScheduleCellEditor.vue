<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: string | number | null | undefined
  editable?: boolean
  ariaLabel?: string
}>(), {
  editable: false,
  ariaLabel: '排程单元格',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  commit: [value: string]
}>()

const editing = ref(false)
const draft = ref('')
const inputRef = ref<HTMLInputElement | null>(null)
const displayValue = computed(() => props.modelValue == null || props.modelValue === '' ? '—' : String(props.modelValue))

async function beginEdit() {
  if (!props.editable) return
  draft.value = props.modelValue == null ? '' : String(props.modelValue)
  editing.value = true
  await nextTick()
  inputRef.value?.focus()
  inputRef.value?.select()
}

function commit() {
  if (!editing.value) return
  editing.value = false
  emit('update:modelValue', draft.value)
  emit('commit', draft.value)
}

function cancel() {
  editing.value = false
}
</script>

<template>
  <input
    v-if="editing"
    ref="inputRef"
    v-model="draft"
    class="h-6 w-full min-w-0 rounded border border-teal-500 bg-white px-1.5 text-[10px] text-slate-900 outline-none ring-2 ring-teal-100"
    :aria-label="ariaLabel"
    @blur="commit"
    @keydown.enter.prevent="commit"
    @keydown.escape.prevent="cancel"
  >
  <button
    v-else
    type="button"
    class="block w-full min-w-0 truncate text-left"
    :class="editable ? 'cursor-text rounded px-0.5 hover:bg-teal-50' : 'cursor-default'"
    :aria-label="ariaLabel"
    :title="displayValue"
    @dblclick.stop="beginEdit"
  >
    {{ displayValue }}
  </button>
</template>

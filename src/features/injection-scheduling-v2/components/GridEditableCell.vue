<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  value: string | number
  kind?: 'text' | 'number' | 'datetime' | 'select'
  options?: Array<{ value: string; label: string }>
  disabled?: boolean
  pending?: boolean
}>(), { kind: 'text', options: () => [], disabled: false, pending: false })
const emit = defineEmits<{ commit: [value: string | number] }>()
const editing = ref(false)
const draft = ref<string | number>(props.value)
const input = ref<HTMLInputElement | HTMLSelectElement | null>(null)

watch(() => props.value, (value) => { if (!editing.value) draft.value = value })

async function begin() {
  if (props.disabled) return
  draft.value = props.kind === 'datetime' ? String(props.value).replace(' ', 'T').slice(0, 16) : props.value
  editing.value = true
  await nextTick()
  input.value?.focus()
  if (input.value instanceof HTMLInputElement) input.value.select()
}

function commit() {
  if (!editing.value) return
  const value = props.kind === 'number' ? Number(draft.value) : draft.value
  editing.value = false
  emit('commit', value)
}

function cancel() {
  draft.value = props.value
  editing.value = false
}

function handleKey(event: KeyboardEvent) {
  if (event.key === 'Enter') { event.preventDefault(); commit() }
  if (event.key === 'Escape') { event.preventDefault(); cancel() }
}
</script>

<template>
  <span class="grid-editor" :class="{ pending, disabled, editing }" @click.stop>
    <select v-if="editing && kind === 'select'" ref="input" v-model="draft" @change="commit" @blur="commit" @keydown="handleKey">
      <option v-for="option in options" :key="option.value" :value="option.value">{{ option.label }}</option>
    </select>
    <input v-else-if="editing" ref="input" v-model="draft" :type="kind === 'number' ? 'number' : kind === 'datetime' ? 'datetime-local' : 'text'" :min="kind === 'number' ? 0 : undefined" @blur="commit" @keydown="handleKey" />
    <button v-else type="button" :disabled="disabled" :title="disabled ? '当前状态或权限不允许编辑' : '双击或按 Enter 编辑'" @dblclick="begin" @keydown.enter.prevent="begin">
      <slot>{{ value || '—' }}</slot><i v-if="pending"></i>
    </button>
  </span>
</template>

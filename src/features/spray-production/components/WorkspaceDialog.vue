<script setup lang="ts">
import { ref, watch, onBeforeUnmount, nextTick } from 'vue'
import { X } from '@lucide/vue'
const props = defineProps<{ open: boolean; title: string; wide?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement | null>(null)
let trigger: HTMLElement | null = null
watch(() => props.open, async open => {
  await nextTick()
  if (open) { trigger = document.activeElement as HTMLElement; dialog.value?.showModal() }
  else { dialog.value?.close(); trigger?.focus() }
}, { immediate: true })
onBeforeUnmount(() => { dialog.value?.close(); trigger?.focus() })
</script>
<template>
  <dialog ref="dialog" class="spray-dialog spray-workspace" :class="{ 'spray-dialog--wide': wide }" :aria-label="title" @cancel.prevent="emit('close')">
    <header class="spray-dialog__header"><h2>{{ title }}</h2><button type="button" class="spray-icon-button" aria-label="关闭" @click="emit('close')"><X :size="19" /></button></header>
    <div class="spray-dialog__body"><slot /></div>
    <footer v-if="$slots.footer" class="spray-dialog__footer"><slot name="footer" /></footer>
  </dialog>
</template>

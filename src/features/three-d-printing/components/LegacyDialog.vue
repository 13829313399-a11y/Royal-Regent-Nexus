<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from "vue";
defineProps<{ title: string }>();
const emit = defineEmits<{ close: [] }>();
const dialog = ref<HTMLDialogElement>();
onMounted(() => dialog.value?.showModal());
onBeforeUnmount(() => dialog.value?.close());
</script>
<template>
  <dialog
    ref="dialog"
    class="legacy-dialog three-d-workspace"
    @cancel.self.prevent.stop="emit('close')"
    @click="$event.target === dialog && emit('close')"
  >
    <header>
      <h2>{{ title }}</h2>
      <button type="button" aria-label="关闭" @click="emit('close')">×</button>
    </header>
    <div class="legacy-dialog-body"><slot /></div>
  </dialog>
</template>

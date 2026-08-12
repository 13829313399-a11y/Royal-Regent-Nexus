<script setup lang="ts">
defineProps<{
  prompts: readonly string[]
  disabled?: boolean
}>()

const emit = defineEmits<{
  select: [prompt: string]
}>()
</script>

<template>
  <div v-if="prompts.length" class="flex gap-2 overflow-x-auto px-4 pb-3 sm:px-5" aria-label="建议提问">
    <button
      v-for="prompt in prompts"
      :key="prompt"
      type="button"
      class="shrink-0 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-left text-xs font-medium text-slate-600 shadow-sm transition hover:border-sky-300 hover:bg-sky-50 hover:text-sky-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:cursor-not-allowed disabled:opacity-50"
      :disabled="disabled"
      @click="emit('select', prompt)"
    >
      {{ prompt }}
    </button>
  </div>
</template>

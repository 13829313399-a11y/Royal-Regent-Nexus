<script setup lang="ts">
withDefaults(defineProps<{
  title: string
  description?: string
  eyebrow?: string
}>(), {
  description: '',
  eyebrow: '',
})
</script>

<template>
  <header class="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
    <div class="min-w-0 max-w-4xl">
      <div v-if="eyebrow" class="mb-2.5 flex items-center gap-2">
        <span class="h-px w-7 bg-teal-600" aria-hidden="true" />
        <span class="text-[11px] font-bold uppercase tracking-[0.18em] text-teal-700">
          {{ eyebrow }}
        </span>
      </div>
      <h1 class="text-[clamp(1.65rem,2.4vw,2.25rem)] font-semibold tracking-[-0.035em] text-slate-950">
        {{ title }}
      </h1>
      <p v-if="description" class="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
        {{ description }}
      </p>
    </div>

    <div v-if="$slots.actions" class="flex shrink-0 flex-wrap items-center gap-2.5">
      <slot name="actions" />
    </div>
  </header>
</template>

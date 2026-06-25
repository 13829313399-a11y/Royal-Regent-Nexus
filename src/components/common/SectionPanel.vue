<script setup lang="ts">
defineProps<{
  title?: string
  subtitle?: string
}>()
</script>

<template>
  <section class="rounded-lg border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
    <div v-if="title || subtitle || $slots.action" class="flex items-start justify-between gap-4 px-6 pt-6">
      <div>
        <h2 v-if="title" class="text-lg font-semibold tracking-tight text-slate-950">
          {{ title }}
        </h2>
        <p v-if="subtitle" class="mt-1 text-sm text-slate-500">
          {{ subtitle }}
        </p>
      </div>
      <slot name="action" />
    </div>
    <div class="p-6" :class="title || subtitle || $slots.action ? 'pt-5' : ''">
      <slot />
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  title?: string
  subtitle?: string
}>()
</script>

<template>
  <section class="enterprise-panel rounded-xl">
    <div
      v-if="title || subtitle || $slots.action"
      class="flex flex-col gap-3 border-b border-slate-100/90 px-4 py-4 sm:flex-row sm:items-start sm:justify-between sm:px-6 sm:py-5"
    >
      <div class="min-w-0">
        <h2 v-if="title" class="text-[17px] font-semibold tracking-[-0.02em] text-slate-950">
          {{ title }}
        </h2>
        <p v-if="subtitle" class="mt-1.5 text-sm leading-5 text-slate-500">
          {{ subtitle }}
        </p>
      </div>
      <div v-if="$slots.action" class="shrink-0">
        <slot name="action" />
      </div>
    </div>
    <div class="p-4 sm:p-6" :class="title || subtitle || $slots.action ? 'pt-5 sm:pt-5' : ''">
      <slot />
    </div>
  </section>
</template>

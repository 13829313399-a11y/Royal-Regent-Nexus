<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()

const modelValue = defineModel<string | number>()
</script>

<template>
  <textarea
    v-model="modelValue"
    data-slot="textarea"
    :class="
      cn(
        'flex min-h-24 w-full min-w-0 rounded-lg border border-input bg-card px-3 py-2.5 text-sm leading-relaxed text-foreground shadow-[0_1px_2px_oklch(0.2_0.025_240/3%)] outline-none transition-[border-color,box-shadow,background-color] duration-[var(--motion-duration-fast)] ease-standard placeholder:text-muted-foreground/80 hover:border-foreground/20 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/20 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 read-only:bg-muted/50 read-only:text-foreground/85 disabled:cursor-not-allowed disabled:bg-muted/70 disabled:opacity-60',
        props.class,
      )
    "
  />
</template>

<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

interface Props {
  size?: 'default' | 'sm'
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  size: 'default',
})

const modelValue = defineModel<string | number>()
</script>

<template>
  <input
    v-model="modelValue"
    data-slot="input"
    :data-size="size"
    :class="
      cn(
        'flex w-full min-w-0 rounded-lg border border-input bg-card px-3 text-sm text-foreground shadow-[0_1px_2px_oklch(0.2_0.025_240/3%)] outline-none transition-[border-color,box-shadow,background-color] duration-[var(--motion-duration-fast)] ease-standard placeholder:text-muted-foreground/80 hover:border-foreground/20 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/20 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 read-only:bg-muted/50 read-only:text-foreground/85 disabled:cursor-not-allowed disabled:bg-muted/70 disabled:opacity-60 file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground',
        size === 'sm' ? 'h-9 text-[13px]' : 'h-10',
        props.class,
      )
    "
  >
</template>

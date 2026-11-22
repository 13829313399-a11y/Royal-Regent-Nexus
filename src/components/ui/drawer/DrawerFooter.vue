<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <div
    data-slot="drawer-footer"
    :class="cn('mt-auto flex shrink-0 flex-col-reverse gap-2 border-t border-border/60 px-6 py-4 sm:flex-row sm:justify-end', props.class)"
  >
    <slot />
  </div>
</template>

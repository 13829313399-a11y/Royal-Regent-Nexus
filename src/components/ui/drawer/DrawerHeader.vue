<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <div
    data-slot="drawer-header"
    :class="cn('flex shrink-0 flex-col gap-1.5 border-b border-border/60 px-6 py-5 pr-14', props.class)"
  >
    <slot />
  </div>
</template>

<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import type { CardVariants } from '.'
import { cn } from '@/lib/utils'
import { cardVariants } from '.'

interface Props {
  variant?: CardVariants['variant']
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()
</script>

<template>
  <div
    data-slot="card"
    :data-variant="variant ?? 'default'"
    :class="cn(cardVariants({ variant }), props.class)"
  >
    <slot />
  </div>
</template>

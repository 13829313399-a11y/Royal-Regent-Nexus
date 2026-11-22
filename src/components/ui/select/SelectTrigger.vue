<script setup lang="ts">
import type { SelectTriggerProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { ChevronDown } from '@lucide/vue'
import { SelectIcon, SelectTrigger, useForwardProps } from 'reka-ui'
import { cn } from '@/lib/utils'

interface Props extends SelectTriggerProps {
  size?: 'default' | 'sm'
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  size: 'default',
})

const delegatedProps = computed(() => {
  const { class: _class, size: _size, ...delegated } = props
  return delegated
})

const forwarded = useForwardProps(delegatedProps)
</script>

<template>
  <SelectTrigger
    data-slot="select-trigger"
    :data-size="size"
    v-bind="forwarded"
    :class="
      cn(
        'group flex w-full cursor-pointer items-center justify-between gap-2 whitespace-nowrap rounded-lg border border-input bg-card px-3 text-sm text-foreground shadow-[0_1px_2px_oklch(0.2_0.025_240/3%)] outline-none transition-[border-color,box-shadow,background-color] duration-[var(--motion-duration-fast)] ease-standard hover:border-foreground/20 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/20 data-[placeholder]:text-muted-foreground/80 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 disabled:cursor-not-allowed disabled:bg-muted/70 disabled:opacity-60 [&>span]:line-clamp-1',
        size === 'sm' ? 'h-9 text-[13px]' : 'h-10',
        props.class,
      )
    "
  >
    <slot />
    <SelectIcon as-child>
      <ChevronDown
        aria-hidden="true"
        class="size-4 shrink-0 text-muted-foreground transition-transform duration-[var(--motion-duration-fast)] ease-spring-snappy group-data-[state=open]:rotate-180"
      />
    </SelectIcon>
  </SelectTrigger>
</template>

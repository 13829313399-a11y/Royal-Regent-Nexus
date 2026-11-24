<script setup lang="ts">
import type { TabsTriggerProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { TabsTrigger, useForwardProps } from 'reka-ui'
import { cn } from '@/lib/utils'

interface Props extends TabsTriggerProps {
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()

const delegatedProps = computed(() => {
  const { class: _class, ...delegated } = props
  return delegated
})

const forwarded = useForwardProps(delegatedProps)
</script>

<template>
  <TabsTrigger
    data-slot="tabs-trigger"
    v-bind="forwarded"
    :class="
      cn(
        'relative z-10 inline-flex shrink-0 cursor-pointer items-center justify-center gap-1.5 whitespace-nowrap rounded-lg px-3.5 py-1.5 text-sm font-medium text-muted-foreground outline-none transition-[color,transform] duration-[var(--motion-duration-fast)] ease-standard hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/25 active:scale-[0.98] data-[state=active]:font-semibold data-[state=active]:text-primary disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*=size-])]:size-4',
        props.class,
      )
    "
  >
    <slot />
  </TabsTrigger>
</template>

<script setup lang="ts">
import type { CollapsibleTriggerProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { CollapsibleTrigger } from 'reka-ui'
import { cn } from '@/lib/utils'

interface Props extends CollapsibleTriggerProps {
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()

const delegatedProps = computed(() => {
  const { class: _class, ...delegated } = props
  return delegated
})
</script>

<template>
  <CollapsibleTrigger
    data-slot="collapsible-trigger"
    v-bind="delegatedProps"
    :class="cn('outline-none focus-visible:ring-3 focus-visible:ring-ring/25', props.class)"
  >
    <slot />
  </CollapsibleTrigger>
</template>

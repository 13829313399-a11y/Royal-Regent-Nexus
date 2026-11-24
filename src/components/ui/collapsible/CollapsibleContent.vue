<script setup lang="ts">
import type { CollapsibleContentProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { CollapsibleContent } from 'reka-ui'
import { cn } from '@/lib/utils'

interface Props extends CollapsibleContentProps {
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()

const delegatedProps = computed(() => {
  const { class: _class, ...delegated } = props
  return delegated
})
</script>

<template>
  <CollapsibleContent
    data-slot="collapsible-content"
    v-bind="delegatedProps"
    :class="cn('ui-collapsible-content overflow-hidden', props.class)"
  >
    <slot />
  </CollapsibleContent>
</template>

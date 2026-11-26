<script setup lang="ts">
import type { SelectSeparatorProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { SelectSeparator } from 'reka-ui'
import { cn } from '@/lib/utils'

interface Props extends SelectSeparatorProps {
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()

const delegatedProps = computed(() => {
  const { class: _class, ...delegated } = props
  return delegated
})
</script>

<template>
  <SelectSeparator
    data-slot="select-separator"
    v-bind="delegatedProps"
    :class="cn('pointer-events-none -mx-1 my-1 h-px bg-border/80', props.class)"
  />
</template>
